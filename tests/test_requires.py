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
    read = "Helper.ValueAsDecimal(Helper.GetEncounterObservationValue('weight', null, null))"
    assert f"define Calc_weight_Vv_1: {read}" in cql


@pytest.mark.skip(reason="#101 (function parameter fallbacks) is not implemented")
def test_function_parameter_fallback_finds_a_required_concept():
    """#101: a function parameter whose fallback concept is required finds it."""
