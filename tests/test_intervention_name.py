"""The intervention ``name`` names the form; ``form_id`` is legacy-only.

See feature/20261008-intervention-name-replaces-form-id.md.
"""

from __future__ import annotations

import glob
import logging
import os

import pandas as pd
import pytest
import yaml

from tricc_oo.models.project_config import TriccInterventionConfig, TriccProjectConfig
from tricc_oo.models.tricc import TriccNodeMainStart, TriccIntervention, TriccSegment
from tricc_oo.runner import run_project_build
from tricc_oo.strategies.input.yaml import YamlActivity, YamlStrategy

WARNING = "is ignored when interventions are declared; set interventions[].name"


def _project(form_ids=(), intervention=None, title="My project"):
    project = TriccIntervention(title=title)
    project.config = intervention
    for i, form_id in enumerate(form_ids):
        root = TriccNodeMainStart(id=f"s{i}", name=f"s{i}", form_id=form_id, process="main")
        page = TriccSegment(id=f"a{i}", name=f"a{i}", root=root)
        project.pages[page.id] = page
        if i == 0:
            project.start_pages["main"] = page
    return project


def _intervention(**kwargs):
    return TriccInterventionConfig(**{"id": "peds", "title": "Pediatrics", "activity": ["*"], **kwargs})


# --- TriccIntervention.intervention_name ----------------------------------------


def test_name_wins_over_id_and_form_id(caplog):
    project = _project(["legacy"], _intervention(name="pediatrics"))
    with caplog.at_level(logging.WARNING):
        assert project.intervention_name() == "pediatrics"
    assert "'legacy' " + WARNING in caplog.text


def test_id_is_the_name_when_empty():
    assert _intervention(name="  ").name is None
    assert _project([], _intervention()).intervention_name() == "peds"


def test_warning_once_per_distinct_form_id(caplog):
    project = _project(["a", "b", "a"], _intervention(name="c"))
    with caplog.at_level(logging.WARNING):
        for _ in range(3):
            assert project.intervention_name() == "c"
    assert caplog.text.count(WARNING) == 2


def test_implicit_mode_reads_main_start_form_id():
    assert _project(["visitform", "other"]).intervention_name() == "visitform"


def test_implicit_mode_without_form_id_uses_title_slug():
    assert _project([], title="Child Health (v2)").intervention_name() == "child_health_v2"


# --- activity name -----------------------------------------------------------


def test_yaml_activity_name_names_the_activity_and_form_id_is_not_copied():
    raw = {
        "id": "weight-measurement",
        "name": "weight_measurement",
        "title": "Weight measurement",
        "intent": {"en": "Children under five"},
        "form_id": "legacy",
        "nodes": [{"id": "s", "type": "start", "label": "Weight"}, {"id": "e", "type": "end", "name": "e"}],
        "edges": [{"source": "s", "target": "e"}],
    }
    yaml_act = YamlActivity.model_validate(raw)
    assert yaml_act.nodes[0].form_id is None  # no longer copied by the model validator
    activity = YamlStrategy(None)._build_activity(yaml_act, TriccIntervention())
    assert activity.name == "weight_measurement"
    assert activity.intent == {"en": "Children under five"}
    # legacy input still reaches the start node for implicit mode
    assert activity.root.form_id == "legacy"


def test_yaml_activity_without_name_keeps_title_slug_name():
    yaml_act = YamlActivity.model_validate(
        {"id": "x", "title": "Weight measurement", "nodes": [{"id": "s", "type": "start", "label": "W"}]}
    )
    assert YamlStrategy(None)._build_activity(yaml_act, TriccIntervention()).name == "weight_measurement"


# --- project builds ----------------------------------------------------------

MAIN_YAML = """
id: main
title: Main
process: main
nodes:
  - {id: start, type: start, label: Demo, name: start_demo, form_id: stray_form}
  - {id: age, type: integer, name: age, label: Age}
  - {id: end, type: end, name: end_demo, label: End}
edges:
  - {source: start, target: age}
  - {source: age, target: end}
"""


def _build(tmp_path, outputs, name="pediatrics"):
    (tmp_path / "yaml").mkdir(exist_ok=True)
    (tmp_path / "yaml" / "main.yaml").write_text(MAIN_YAML, encoding="utf-8")
    intervention = {"id": "peds", "title": "Pediatrics", "activity": ["yaml/*"]}
    if name:
        intervention["name"] = name
    config = {
        "title": "Demo",
        "input_strategy": "YamlStrategy",
        "output_strategies": outputs,
        "interventions": [intervention],
    }
    (tmp_path / "tricc.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")
    assert run_project_build(str(tmp_path), str(tmp_path / "out")) == 0
    return tmp_path / "out"


def test_stray_form_id_is_ignored_with_a_warning(tmp_path, caplog):
    with caplog.at_level(logging.WARNING):
        out = _build(tmp_path, ["XLSFormStrategy"])
    assert caplog.text.count("'stray_form' " + WARNING) == 1
    (form,) = glob.glob(str(out / "**" / "*.xlsx"), recursive=True)
    assert os.path.basename(form) == "pediatrics.xlsx"
    settings = pd.read_excel(form, sheet_name="settings", dtype=str)
    assert settings["form_id"][0] == "pediatrics"
    assert "stray_form" not in "".join(os.listdir(os.path.dirname(form)))


@pytest.mark.parametrize(
    "output, expected",
    [
        ("XLSFormCHTStrategy", "pediatrics.xlsx"),
        ("FHIRStrategy", "pediatrics"),
        ("OpenSRPStrategy", "pediatrics"),
    ],
)
def test_intervention_name_names_every_output(tmp_path, output, expected):
    logging.disable(logging.WARNING)
    try:
        out = _build(tmp_path, [output])
    finally:
        logging.disable(logging.NOTSET)
    names = {p.name for p in out.rglob("*")}
    assert expected in names
    assert not any("stray_form" in n for n in names)


def test_intervention_id_names_the_form_without_name(tmp_path):
    logging.disable(logging.WARNING)
    try:
        out = _build(tmp_path, ["XLSFormStrategy"], name=None)
    finally:
        logging.disable(logging.NOTSET)
    (form,) = glob.glob(str(out / "**" / "*.xlsx"), recursive=True)
    assert os.path.basename(form) == "peds.xlsx"


def test_config_accepts_intervention_name():
    config = TriccProjectConfig.model_validate(
        {"interventions": [{"id": "a", "title": "A", "name": " a_form ", "activity": ["*"]}]}
    )
    assert config.interventions[0].name == "a_form"


def test_each_intervention_names_its_own_form(tmp_path):
    (tmp_path / "yaml").mkdir()
    (tmp_path / "yaml" / "main.yaml").write_text(MAIN_YAML, encoding="utf-8")
    config = {
        "title": "Demo",
        "input_strategy": "YamlStrategy",
        "output_strategies": ["XLSFormStrategy"],
        "interventions": [
            {"id": "peds", "name": "pediatrics", "title": "Pediatrics", "activity": ["yaml/*"]},
            {"id": "infants", "title": "Young infants", "activity": ["yaml/*"]},
        ],
    }
    (tmp_path / "tricc.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")
    logging.disable(logging.WARNING)
    try:
        assert run_project_build(str(tmp_path), str(tmp_path / "out")) == 0
    finally:
        logging.disable(logging.NOTSET)
    forms = sorted(os.path.basename(p) for p in glob.glob(str(tmp_path / "out" / "**" / "*.xlsx"), recursive=True))
    assert forms == ["infants.xlsx", "pediatrics.xlsx"]
