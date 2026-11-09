"""Project retrieval dictionary (feature/20261109-project-retrievals.md) and populate ``source`` (#34)."""

from __future__ import annotations

import glob
import json
import logging
import os
import shutil

import pandas as pd
import pytest
from fhir.resources.codesystem import CodeSystem

from tricc_oo.converters.fhir.populate_helper import resolve_populate_reference, retrieval_cql_expression
from tricc_oo.converters.retrieval import (
    Retrieval,
    TriccRetrievalError,
    cql_quantity,
    custom_expression,
    period_days,
    read_retrieval,
)
from tricc_oo.models.calculate import TriccNodePopulate, TriccNodeRetrieval
from tricc_oo.runner import run_project_build

FIXTURE = os.path.join(os.path.dirname(__file__), "data", "projects", "retrievals")
RETRIEVE_CS = os.path.join(FIXTURE, "terminology", "demo-retrieve.codesystem.json")


def _build(tmp_path, strategy, fixture=FIXTURE):
    logging.disable(logging.WARNING)
    try:
        assert run_project_build(fixture, str(tmp_path / "out"), cli_output_strategy=strategy) == 0
    finally:
        logging.disable(logging.NOTSET)
    return tmp_path / "out"


def _survey(out):
    (form,) = glob.glob(str(out / "**" / "visit.xlsx"), recursive=True)
    return pd.read_excel(form, sheet_name="survey", dtype=str).fillna("")


def _concepts():
    with open(RETRIEVE_CS, encoding="utf-8") as f:
        return {c.code: c for c in CodeSystem.model_validate(json.load(f)).concept}


# --- reading the dictionary ------------------------------------------------------------


def test_concepts_read_as_retrievals():
    concepts = _concepts()
    age = read_retrieval(concepts["#age_months"])
    assert (age.context, age.effective_function, age.value_type) == ("patient", "AgeInMonths", "integer")
    prev = read_retrieval(concepts["#prev_weight"])
    assert (prev.reads_code, prev.period, prev.effective_function) == ("weight", "P30D", "Latest")
    custom = read_retrieval(concepts["#weight_trend"])
    assert custom.effective_function is None
    assert set(custom.expressions) == {"text/cql", "text/x-xlsform"}
    assert custom.export_name == "r_weight_trend"


def test_context_default_function():
    retrieval = Retrieval(code="#w", context="encounter", reads_code="weight")
    assert retrieval.effective_function == "Latest"
    assert Retrieval(code="#f", context="facility", reads_code="district").effective_function == "FacilityValue"


@pytest.mark.parametrize(
    "properties, message",
    [
        ([{"code": "context", "valueCode": "patient"}, {"code": "function", "valueCode": "Latest"}], "not allowed"),
        ([{"code": "context", "valueCode": "history"}], "needs 'reads'"),
        (
            [{"code": "context", "valueCode": "patient"}, {"code": "function", "valueCode": "Gender"}],
            "unknown function",
        ),
    ],
)
def test_invalid_retrievals_are_rejected(properties, message):
    concept = CodeSystem.model_validate(
        {"resourceType": "CodeSystem", "status": "draft", "content": "complete",
         "concept": [{"code": "#x", "property": properties}]}
    ).concept[0]
    with pytest.raises(TriccRetrievalError, match=message):
        read_retrieval(concept)


# --- periods and placeholders -----------------------------------------------------------


@pytest.mark.parametrize(
    "period, cql, days",
    [("P30D", "30 days", "30"), ("P2W", "2 weeks", "14"), ("P1M", "1 month", "30"),
     ("P1Y", "1 year", "365"), ("PT12H", "12 hours", "0.5")],
)
def test_period_as_cql_quantity_and_days(period, cql, days):
    assert cql_quantity(period) == cql
    assert period_days(period) == days


def test_composite_period_is_not_a_cql_quantity():
    with pytest.raises(TriccRetrievalError, match="single unit"):
        cql_quantity("P1Y6M", "#x")


def test_custom_placeholders_per_language():
    retrieval = Retrieval(
        code="#x", context="custom", reads_code="weight", period="P30D",
        expressions={"text/cql": "Foo({{code}}, {{ period }})", "text/x-xlsform": "${{{code}}} + {{period}}"},
    )
    assert custom_expression(retrieval, "text/cql", "S") == 'Foo("weight", 30 days)'
    assert custom_expression(retrieval, "text/x-xlsform", "S") == "${weight} + 30"


def test_custom_without_expression_for_the_language_fails():
    retrieval = Retrieval(code="#x", context="custom", expressions={"text/cql": "1"})
    with pytest.raises(TriccRetrievalError, match=r"#x.*text/x-xlsform.*XLSFormStrategy"):
        custom_expression(retrieval, "text/x-xlsform", "XLSFormStrategy")


def test_cql_catalogue():
    assert retrieval_cql_expression(Retrieval(code="#a", context="patient", function="Sex")) == "PatientGender"
    count = Retrieval(code="#c", context="history", function="Count", reads_code="weight", period="P7D")
    assert "ObservationHasCode(O, 'weight')" in retrieval_cql_expression(count)
    assert "Now() - 7 days" in retrieval_cql_expression(count)
    exists = Retrieval(code="#e", context="encounter", function="Exists", reads_code="weight")
    assert retrieval_cql_expression(exists) == "exists(GetObservations('weight'))"


# --- export --------------------------------------------------------------------------------


def test_cht_emits_one_hidden_calculate_per_used_retrieval(tmp_path):
    survey = _survey(_build(tmp_path, "XLSFormCHTStrategy"))
    rows = survey.set_index("name")
    assert rows.loc["r_age_months", "type"] == "calculate"
    assert rows.loc["r_age_months", "calculation"] == "coalesce(instance('contact-summary')/context/age_months,'')"
    assert rows.loc["r_prev_weight", "calculation"] == "coalesce(instance('contact-summary')/context/prev_weight,'')"
    # custom: the text/x-xlsform expression, {{code}} the field name and {{period}} in days
    assert rows.loc["r_weight_trend", "calculation"] == "coalesce(instance('contact-summary')/context/weight_14d,'')"
    assert "r_sex" not in rows.index  # not used: not loaded
    assert "${r_age_months}" in rows.loc["young_note", "relevance"]
    assert "${r_prev_weight}" in rows.loc["weight", "relevance"]
    assert "${r_weight_trend}" in rows.loc["weight_trend", "calculation"]


def test_plain_xlsform_has_no_mapping_for_functions(tmp_path):
    logging.disable(logging.WARNING)
    try:
        message = r"#age_months: XLSFormStrategy has no mapping for function AgeInMonths"
        with pytest.raises(TriccRetrievalError, match=message):
            run_project_build(FIXTURE, str(tmp_path / "out"), cli_output_strategy="XLSFormStrategy")
    finally:
        logging.disable(logging.NOTSET)


def test_fhir_helper_defines_each_used_retrieval(tmp_path):
    out = _build(tmp_path, "FHIRStrategy")
    (helper,) = glob.glob(str(out / "**" / "*-Helper.cql"), recursive=True)
    with open(helper, encoding="utf-8") as f:
        cql = f.read()
    assert 'define "#age_months":\n  AgeInMonths' in cql
    assert (
        'define "#prev_weight":\n'
        "  ValueAsDecimal(GetHistoryObservationValueSince('weight', Now() - 30 days, 1, null))"
    ) in cql
    assert "Now() - 2 weeks, 2, null)), 0)" in cql  # custom text/cql, {{period}} as a quantity
    assert '"#sex"' not in cql
    (main,) = glob.glob(str(out / "**" / "*-main.cql"), recursive=True)
    with open(main, encoding="utf-8") as f:
        assert 'define Calc_r_age_months: Helper."#age_months"' in f.read()


def test_unknown_retrieval_is_an_error(tmp_path):
    fixture = tmp_path / "project"
    shutil.copytree(FIXTURE, fixture)
    activity = fixture / "activities" / "visit.activity.yaml"
    activity.write_text(activity.read_text(encoding="utf-8").replace('"#age_months"', '"#age_weeks"'), encoding="utf-8")
    logging.disable(logging.WARNING)
    try:
        with pytest.raises(TriccRetrievalError, match="unknown retrieval #age_weeks"):
            run_project_build(str(fixture), str(tmp_path / "out"), cli_output_strategy="FHIRStrategy")
    finally:
        logging.disable(logging.NOTSET)


# --- populate source (#34) --------------------------------------------------------------------


def test_populate_reads_its_source_concept(tmp_path):
    from tricc_oo.models.project_config import TriccProjectConfig
    from tricc_oo.runner import load_input_project, read_input_file_contents

    config = TriccProjectConfig(retrieve_code_system="demo-retrieve")
    paths = sorted(glob.glob(os.path.join(FIXTURE, "terminology", "*")))
    terminology = [(p, open(p, encoding="utf-8").read()) for p in paths]
    files = [os.path.join(FIXTURE, "activities", "visit.activity.yaml")]
    logging.disable(logging.WARNING)
    try:
        project = load_input_project(
            [("YamlStrategy", files, read_input_file_contents(files))], str(tmp_path / "media"), config, None,
            terminology=terminology,
        )
    finally:
        logging.disable(logging.NOTSET)
    populate = next(
        n for page in project.pages.values() for n in page.nodes.values()
        if isinstance(n, TriccNodePopulate) and not isinstance(n, TriccNodeRetrieval)
    )
    assert (populate.name, populate.source) == ("t_weight", "weight")
    assert resolve_populate_reference(populate).startswith("GetHistoryObservationValueSince('weight', Now() - 30 days")
    assert sorted(project.retrievals) == ["#age_months", "#prev_weight", "#weight_trend"]
