"""Prerequisites (``requires``) and implied retrievals (``Retrieve``).

feature/20261125-requires-and-implied-retrievals.md (#104).
"""

from __future__ import annotations

import glob
import logging
import os
import shutil

import pandas as pd
import pytest
from pydantic import ValidationError

from tricc_oo.converters.requires import E_REQUIRES_UNKNOWN, TriccRequiresError
from tricc_oo.models.project_config import TriccProjectConfig
from tricc_oo.runner import run_project_build

REQUIRES = os.path.join(os.path.dirname(__file__), "data", "projects", "requires")


def _build(tmp_path, strategy, fixture=REQUIRES):
    logging.disable(logging.WARNING)
    try:
        assert run_project_build(str(fixture), str(tmp_path / "out"), cli_output_strategy=strategy) == 0
    finally:
        logging.disable(logging.NOTSET)
    return tmp_path / "out"


def _survey(out, form):
    (path,) = glob.glob(str(out / "**" / f"{form}.xlsx"), recursive=True)
    return pd.read_excel(path, sheet_name="survey", dtype=str).fillna("").set_index("name")


# --- §1 declaring prerequisites -------------------------------------------------------------


def _config(requires):
    return {
        "title": "t",
        "interventions": [
            {"id": "triage", "title": "Triage", "activity": ["a.yaml"]},
            {"id": "consult", "title": "Consult", "activity": ["b.yaml"], "requires": requires},
        ],
    }


def test_required_intervention_must_exist():
    TriccProjectConfig(**_config(["triage"]))
    with pytest.raises(ValidationError, match=f"{E_REQUIRES_UNKNOWN}: intervention 'consult' requires 'nope'"):
        TriccProjectConfig(**_config(["nope"]))


def test_a_cycle_of_requires_is_allowed():
    config = _config(["triage"])
    config["interventions"][0]["requires"] = ["consult"]
    TriccProjectConfig(**config)


def test_required_concept_must_be_a_project_concept(tmp_path):
    fixture = tmp_path / "project"
    shutil.copytree(REQUIRES, fixture)
    activity = fixture / "activities" / "consult.activity.yaml"
    activity.write_text(activity.read_text(encoding="utf-8").replace("code: muac}", "code: zzz}"), encoding="utf-8")
    logging.disable(logging.WARNING)
    try:
        with pytest.raises(TriccRequiresError, match=f"{E_REQUIRES_UNKNOWN}: activity 'consult' requires"):
            run_project_build(str(fixture), str(tmp_path / "out"), cli_output_strategy="XLSFormCHTStrategy")
    finally:
        logging.disable(logging.NOTSET)


def test_required_intervention_provides_its_inputs():
    from tricc_oo.converters.project_config import load_project_config_for_input
    from tricc_oo.runner import build_grouped_jobs, required_intervention_concepts, resolve_project_sources

    config = load_project_config_for_input(REQUIRES)
    jobs = build_grouped_jobs(REQUIRES, config, "YamlStrategy")
    terminology, libraries = resolve_project_sources(REQUIRES, config)
    consult = next(item for item, _ in jobs if item.id == "consult")
    triage = next(item for item, _ in jobs if item.id == "triage")
    assert required_intervention_concepts(config, jobs, consult, terminology, libraries) == {
        "weight", "temp", "resp_rate",
    }
    assert required_intervention_concepts(config, jobs, triage, terminology, libraries) == set()


# --- §2 required concepts are the first version ----------------------------------------------


def test_required_concept_is_the_first_version_cht(tmp_path):
    survey = _survey(_build(tmp_path, "XLSFormCHTStrategy"), "consult")
    # the encounter read of the triage weight (CHT: the task-injected inputs group)
    assert survey.loc["weight", "type"] == "hidden"
    assert survey.loc["weight_Vv_1", "calculation"] == "../inputs/contact/weight"
    # a reference before the redefinition reads it
    assert survey.loc["low_weight_note", "relevance"] == "${weight_Vv_1}<5"
    # the form's own weight is a later version, prefilled from the read (inheritance)
    assert survey.loc["weight_Vv_2", "type"] == "decimal"
    assert survey.loc["weight_Vv_2", "calculation"] == "coalesce(., ${weight_Vv_1})"
    # a reference after it reads the new version
    assert "${weight_Vv_2}" in survey.loc["heavy", "calculation"]
    # an activity prerequisite
    assert survey.loc["load_muac", "calculation"] == "../inputs/contact/muac"
    assert survey.loc["muac_note", "relevance"] == "${load_muac}<115"


def test_unreferenced_required_concept_builds_no_node(tmp_path):
    survey = _survey(_build(tmp_path, "XLSFormCHTStrategy"), "consult")
    assert not any("temp" in name or "resp_rate" in name for name in survey.index)
    # an intervention without requires reads nothing
    triage = _survey(tmp_path / "out", "triage")
    assert not any(str(calc).startswith("../inputs/contact/weight") for calc in triage["calculation"])


def test_required_concept_is_an_encounter_read_fhir(tmp_path):
    out = _build(tmp_path, "FHIRStrategy")
    (main,) = glob.glob(str(out / "**" / "consult-main.cql"), recursive=True)
    with open(main, encoding="utf-8") as f:
        cql = f.read()
    # the encounter read is a Helper define (§4)
    assert 'define Calc_weight_Vv_1: Helper."@weight"' in cql


@pytest.mark.skip(reason="#101 (function parameter fallbacks) is not implemented")
def test_function_parameter_fallback_finds_a_required_concept():
    """#101: a function parameter whose fallback concept is required finds it."""


# --- §3 Retrieve: dictionary and implied reads -------------------------------------------------

IMPLIED = os.path.join(os.path.dirname(__file__), "data", "projects", "implied_retrievals")


def _load(media_path, fixture=IMPLIED):
    from tricc_oo.converters.project_config import load_project_config_for_input
    from tricc_oo.runner import build_grouped_jobs, load_input_project, read_input_file_contents
    from tricc_oo.runner import resolve_project_sources

    config = load_project_config_for_input(str(fixture))
    ((intervention, groups),) = build_grouped_jobs(str(fixture), config, "YamlStrategy")
    terminology, libraries = resolve_project_sources(str(fixture), config)
    logging.disable(logging.WARNING)
    try:
        return load_input_project(
            [(name, files, read_input_file_contents(files)) for name, files in groups],
            str(media_path), config, intervention, terminology=terminology,
        )
    finally:
        logging.disable(logging.NOTSET)


@pytest.fixture(scope="module")
def implied_project(tmp_path_factory):
    return _load(tmp_path_factory.mktemp("implied") / "media-tmp")


@pytest.mark.parametrize(
    "expression, code",
    [
        ("Retrieve('age_months')", "#age_months"),
        ('"#age_months"', "#age_months"),
        ("Retrieve('weight', 'P3M')", "#weight@P3M"),
        ("Retrieve('weight', 'P3M', 'value')", "#weight@P3M"),
        ("Retrieve('weight', null)", "#weight@"),
        ("Retrieve('weight', 'P3M', 'date')", "#weight@P3M.date"),
        ("Retrieve('weight', 'encounter')", "#weight@encounter"),
        ("Retrieve('metformin', 'encounter', 'date')", "#metformin@encounter.date"),
    ],
)
def test_retrieve_is_a_reference_to_the_retrieval(expression, code):
    from tricc_oo.converters.cql_to_operation import transform_cql_to_operation
    from tricc_oo.models.base import TriccReference

    parsed = transform_cql_to_operation(expression)
    assert isinstance(parsed, TriccReference) and parsed.value == code


@pytest.mark.parametrize(
    "expression, error",
    [
        ("Retrieve('weight', '3 months')", "E_RETRIEVAL_IMPLIED_PERIOD"),
        ('Retrieve("weight", \'P3M\')', "E_RETRIEVAL_STATIC"),
        ("Retrieve('weight', 'P' + '3M')", "E_RETRIEVAL_STATIC"),
        ("Retrieve('weight', 'P3M', 'foo')", "E_RETRIEVAL_READ_UNSUPPORTED"),
    ],
)
def test_retrieve_arguments_are_literals(expression, error):
    from tricc_oo.converters.cql_to_operation import transform_cql_to_operation
    from tricc_oo.converters.retrieval import TriccRetrievalError

    with pytest.raises(TriccRetrievalError, match=error):
        transform_cql_to_operation(expression)


def test_implied_reads_are_generated_retrievals(implied_project):
    retrievals = implied_project.retrievals
    # used twice, and once with `value` spelled out: one node
    assert sum(1 for code in retrievals if code == "#weight@P3M") == 1
    latest = retrievals["#weight@P3M"]
    assert (latest.context, latest.effective_function, latest.period, latest.reads_code) == (
        "history", "Latest", "P3M", "weight",
    )
    assert (latest.export_name, latest.value_type) == ("r_weight_P3M", "decimal")
    assert retrievals["#weight@"].period is None and retrievals["#weight@"].export_name == "r_weight_any"
    assert [retrievals[f"#weight@P3M.{field}"].effective_function for field in ("date", "exists", "count")] == [
        "LatestDate", "Exists", "Count",
    ]
    here = retrievals["#weight@encounter"]
    assert (here.context, here.period, here.effective_function) == ("encounter", None, "Latest")
    assert retrievals["#metformin@.drugs"].effective_function == "ActiveDrugs"
    assert retrievals["#metformin@encounter.date"].label == "Date of the latest Metformin, this encounter"
    # the dictionary retrieval, written both ways: one node
    assert [code for code in retrievals if not retrievals[code].implied] == ["#age_months"]


def test_the_forms_own_concept_is_not_read_by_an_implied_read(tmp_path):
    survey = _survey(_build(tmp_path, "XLSFormCHTStrategy", IMPLIED), "visit")
    assert survey.loc["r_weight_P3M", "calculation"] == "coalesce(instance('contact-summary')/context/weight_P3M,'')"
    assert survey.loc["weight", "relevance"] == "${r_weight_P3M}=''"
    assert survey.loc["weight_gain", "calculation"] == "number(coalesce(${weight},'') - ${r_weight_P3M})"
    assert survey.loc["young_note", "relevance"] == survey.loc["young_note2", "relevance"] == "${r_age_months}<6"


def test_implied_reads_in_the_fhir_helper(tmp_path):
    out = _build(tmp_path, "FHIRStrategy", IMPLIED)
    (helper,) = glob.glob(str(out / "**" / "*-Helper.cql"), recursive=True)
    with open(helper, encoding="utf-8") as f:
        cql = f.read()
    assert 'define "#weight@P3M":' in cql and "Now() - 3 months" in cql
    assert 'define "#weight@":' in cql
    assert 'define "#metformin@P6M.dosage":' in cql


@pytest.mark.parametrize(
    "replace, error",
    [
        ("Retrieve('weight', null)", "E_RETRIEVAL_IMPLIED_CONCEPT"),
        ("Retrieve('weight', 'P3M', 'date')", "E_RETRIEVAL_READ_UNSUPPORTED"),
        ("Retrieve('age_months')", "E_RETRIEVAL_UNKNOWN"),
    ],
)
def test_implied_read_errors(tmp_path, replace, error):
    from tricc_oo.converters.retrieval import TriccRetrievalError

    by = {
        "E_RETRIEVAL_IMPLIED_CONCEPT": "Retrieve('height', null)",  # not a project concept
        "E_RETRIEVAL_READ_UNSUPPORTED": "Retrieve('weight', 'P3M', 'drugs')",  # drugs of an Observation
        "E_RETRIEVAL_UNKNOWN": "Retrieve('age_weeks')",  # not in the dictionary
    }[error]
    fixture = tmp_path / "project"
    shutil.copytree(IMPLIED, fixture)
    activity = fixture / "activities" / "visit.activity.yaml"
    activity.write_text(activity.read_text(encoding="utf-8").replace(replace, by), encoding="utf-8")
    logging.disable(logging.WARNING)
    try:
        with pytest.raises(TriccRetrievalError, match=error):
            run_project_build(str(fixture), str(tmp_path / "out"), cli_output_strategy="XLSFormCHTStrategy")
    finally:
        logging.disable(logging.NOTSET)


# --- §4 export: one read per record ------------------------------------------------------------


def _fhir_libraries(out):
    libraries = {}
    for path in glob.glob(str(out / "**" / "*.cql"), recursive=True):
        with open(path, encoding="utf-8") as f:
            libraries[os.path.basename(path)] = f.read()
    return libraries


def test_fields_of_one_concept_and_window_share_one_records_list(tmp_path):
    import re

    libraries = _fhir_libraries(_build(tmp_path, "FHIRStrategy", IMPLIED))
    (helper,) = [cql for name, cql in libraries.items() if name.endswith("-Helper.cql")]
    assert helper.count('define "#weight@P3M:records":') == 1
    for field_define in ('"#weight@P3M"', '"#weight@P3M.date"', '"#weight@P3M.count"', '"#weight@P3M.exists"'):
        body = helper.split(f"define {field_define}:\n", 1)[1].split("\n\n", 1)[0]
        assert '"#weight@P3M:records"' in body and "(" + "'weight'" not in body
    # the records lists read the shared retrieves, never a bare one
    for records in re.findall(r'define "[^"]+:(?:records|dispenses)":\n  (.*)', helper):
        assert records.startswith('("History') or records.startswith('("Encounter')
    for resource in ("Observation", "Condition", "Procedure", "MedicationRequest", "MedicationDispense"):
        assert helper.count(f"[{resource}]") == 1


def test_items_name_defines_not_helper_function_calls(tmp_path):
    import re

    for fixture in (IMPLIED, REQUIRES):
        out = _build(tmp_path / os.path.basename(fixture), "FHIRStrategy", fixture)
        for name, cql in _fhir_libraries(out).items():
            if name.endswith("-Helper.cql"):
                continue
            for define, body in re.findall(r"^define (\w+): (.*)$", cql, re.M):
                assert not re.search(r"\bHelper\.\w+\(\s*[^)\s]", body), f"{name}: {define}: {body}"


def test_encounter_reads_are_helper_defines(tmp_path):
    libraries = _fhir_libraries(_build(tmp_path, "FHIRStrategy"))
    assert 'define Calc_weight_Vv_1: Helper."@weight"' in libraries["consult-main.cql"]
    assert 'define "@weight":\n  ValueAsDecimal(GetEncounterObservationValue(\'weight\', null, null))' in (
        libraries["consult-Helper.cql"]
    )


def test_cht_contact_summary_keys_grouped_by_concept_and_window(tmp_path):
    import json

    out = _build(tmp_path, "XLSFormCHTStrategy", IMPLIED)
    (path,) = glob.glob(str(out / "**" / "visit.contact-summary.json"), recursive=True)
    with open(path, encoding="utf-8") as f:
        keys = json.load(f)
    weight = next(g for g in keys["concepts"] if (g["concept"], g["window"]) == ("weight", "P3M"))
    assert weight["fields"] == {
        "value": "weight_P3M", "date": "weight_P3M_date", "exists": "weight_P3M_exists", "count": "weight_P3M_count",
    }
    assert {(g["concept"], g["context"], g["window"]) for g in keys["concepts"]} >= {
        ("weight", "history", None), ("weight", "encounter", None), ("metformin", "history", "P6M"),
    }
    assert keys["other"] == [{"key": "age_months", "retrieval": "#age_months", "function": "AgeInMonths"}]
