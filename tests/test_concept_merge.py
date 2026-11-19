"""Concepts authored in activities merge into the project CodeSystems; hint / help become designations."""

from __future__ import annotations

import glob
import json
import logging

import pytest

from tricc_oo.converters.datadictionnary import (
    TRICC_DESIGNATION_USE_SYSTEM,
    add_concept,
    add_concept_texts,
    add_designation,
    check_and_add_concept,
    get_designation,
    init_codesystem,
)
from tricc_oo.models.project_config import TriccProjectConfig
from tricc_oo.runner import run_project_build
from tricc_oo.strategies.input.base_input_strategy import BaseInputStrategy

SUB_PAGE_ID = "drawio_texts"


def _cell(cell_id, odk_type, label, name=None):
    name_attr = f' name="{name}"' if name else ""
    return (
        f'<object label="{label}" odk_type="{odk_type}"{name_attr} id="{cell_id}">'
        f'<mxCell style="rounded=1;" vertex="1" parent="1">'
        f'<mxGeometry x="0" y="0" width="120" height="40" as="geometry"/></mxCell></object>'
    )


def _edge(edge_id, source, target):
    return (
        f'<mxCell id="{edge_id}" edge="1" source="{source}" target="{target}" parent="1">'
        f'<mxGeometry relative="1" as="geometry"/></mxCell>'
    )


SUB_DRAWIO = (
    f'<mxfile><diagram id="{SUB_PAGE_ID}" name="Texts"><mxGraphModel><root>'
    '<mxCell id="0"/><mxCell id="1" parent="0"/>'
    + _cell("s1", "activity_start", "Texts", "sub_start")
    + _cell("q1", "integer", "Age", "age")
    + _cell("h1", "hint-message", "In completed years")
    + _cell("p1", "help-message", "Ask the caregiver")
    + _cell("e1", "activity_end", "Sub end", "sub_end")
    + _edge("ed1", "s1", "q1")
    + _edge("ed2", "q1", "e1")
    + _edge("ed3", "h1", "q1")
    + _edge("ed4", "p1", "q1")
    + "</root></mxGraphModel></diagram></mxfile>"
)

MAIN_YAML = f"""
id: texts_main
title: Texts main
process: main
nodes:
  - {{id: start, type: start, label: Texts, name: start_texts}}
  - {{id: to_drawio, type: goto, name: to_drawio, label: Sub, link: {SUB_PAGE_ID}}}
  - {{id: end, type: end, name: end_texts, label: End}}
edges:
  - {{source: start, target: to_drawio}}
  - {{source: to_drawio, target: end}}
"""

TERMINOLOGY = {
    "resourceType": "CodeSystem",
    "id": "tricc",
    "name": "tricc",
    "url": "http://example.com/fhir/CodeSystem/tricc",
    "status": "draft",
    "content": "complete",
    "concept": [{"code": "age", "display": "Age (years)"}],
}


def _project(tmp_path, terminology=False, languages=None):
    (tmp_path / "drawio").mkdir()
    (tmp_path / "yaml").mkdir()
    (tmp_path / "drawio" / "sub.drawio").write_text(SUB_DRAWIO, encoding="utf-8")
    (tmp_path / "yaml" / "main.yaml").write_text(MAIN_YAML, encoding="utf-8")
    lines = ["title: Texts", "output_strategies: [FHIRStrategy]"]
    if languages:
        lines.append(f"parameters: {{languages: {languages}}}")
    if terminology:
        (tmp_path / "terminology").mkdir()
        (tmp_path / "terminology" / "tricc.json").write_text(json.dumps(TERMINOLOGY), encoding="utf-8")
        lines.append("terminology: [terminology/*]")
    lines += [
        "interventions:",
        "  - id: texts",
        "    name: texts",
        "    title: Texts",
        "    activity:",
        "      YamlStrategy: [yaml/*]",
        "      DrawioStrategy: [drawio/*]",
    ]
    (tmp_path / "tricc.yaml").write_text("\n".join(lines), encoding="utf-8")


def _exported_concept(tmp_path, code):
    (path,) = glob.glob(str(tmp_path / "out" / "**" / "tricc_codesystem.json"), recursive=True)
    with open(path, encoding="utf-8") as f:
        exported = json.load(f)
    return next(c for c in exported["concept"] if c["code"] == code)


def _build(tmp_path):
    assert run_project_build(str(tmp_path), str(tmp_path / "out")) == 0


def _designations(concept):
    return {(d["language"], d["use"]["code"]): d["value"] for d in concept.get("designation", [])}


def test_drawio_hint_and_help_become_designations_in_default_language(tmp_path):
    _project(tmp_path, languages="{default: fr, available: [fr, en]}")
    _build(tmp_path)
    age = _exported_concept(tmp_path, "age")
    assert age["display"] == "Age"
    assert _designations(age) == {("fr", "hint"): "In completed years", ("fr", "help"): "Ask the caregiver"}
    assert all(d["use"]["system"] == TRICC_DESIGNATION_USE_SYSTEM for d in age["designation"])


def test_terminology_concept_wins_quietly_and_gets_missing_texts(tmp_path, caplog):
    _project(tmp_path, terminology=True)
    with caplog.at_level(logging.DEBUG, logger="default"):
        _build(tmp_path)
    age = _exported_concept(tmp_path, "age")
    assert age["display"] == "Age (years)"
    assert _designations(age) == {("en", "hint"): "In completed years", ("en", "help"): "Ask the caregiver"}
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING and "already exists" in r.getMessage()]
    assert [r for r in caplog.records if r.levelno == logging.DEBUG and "already exists" in r.getMessage()]


def test_conflicting_authored_displays_still_warn(caplog):
    code_system = init_codesystem("tricc", "tricc")
    check_and_add_concept(code_system, "age", "Age")
    with caplog.at_level(logging.DEBUG, logger="default"):
        concept = check_and_add_concept(code_system, "age", "Age of the child")
    assert concept.display == "Age"
    assert [r for r in caplog.records if r.levelno == logging.WARNING and "already exists" in r.getMessage()]


def test_terminology_marks_its_concepts():
    from tricc_oo.models.tricc import TriccIntervention

    project = TriccIntervention()
    BaseInputStrategy.load_terminology(project, [("cs.json", json.dumps(TERMINOLOGY))])
    assert ("tricc", "age") in project.terminology_concepts
    concept = add_concept(project.code_systems, "tricc", "age", "Age", {}, project.terminology_concepts)
    assert concept.display == "Age (years)"


def test_designations_are_not_duplicated():
    code_system = init_codesystem("tricc", "tricc")
    concept = check_and_add_concept(code_system, "age", "Age")
    add_concept_texts(concept, "en", hint="First hint")
    add_concept_texts(concept, "en", hint="Second hint", help="Help")
    assert not add_designation(concept, "hint", "en", "Third")
    assert get_designation(concept, "hint", "en") == "First hint"
    assert get_designation(concept, "help", "en") == "Help"
    assert len(concept.designation) == 2


@pytest.mark.parametrize(
    "raw, expected",
    [
        (None, (None, [])),
        ("fr", ("fr", ["fr"])),
        (["fr", "en"], ("fr", ["fr", "en"])),
        ({"default": "en", "available": ["fr"]}, ("en", ["en", "fr"])),
        ({"available": ["sw", "en"]}, ("sw", ["sw", "en"])),
    ],
)
def test_parameters_languages(raw, expected):
    params = {} if raw is None else {"languages": raw}
    assert TriccProjectConfig(parameters=params).languages() == expected


def test_project_default_language_comes_from_parameters():
    config = TriccProjectConfig(parameters={"languages": {"default": "fr", "available": ["fr", "en"]}})
    project = BaseInputStrategy.new_project(config)
    assert project.lang_code == "fr"
    assert project.languages == ["fr", "en"]
    assert BaseInputStrategy.new_project(TriccProjectConfig()).lang_code == "en"
