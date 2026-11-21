"""YamlStrategy reads formatted concept texts: ``designation-doc``, then the old
``designation-message``, then ``value`` (feature/20261120-prosemirror-display-text.md §1.3).

Run with:
    python -m pytest tests/test_yaml_designation_doc.py -v
"""

from __future__ import annotations

import glob
import json
import logging

import pandas as pd
from fhir.resources.codesystem import CodeSystemConcept

from tricc_oo.converters.datadictionnary import (
    DESIGNATION_DOC_EXT,
    DESIGNATION_MESSAGE_EXT,
    add_concept_texts,
    concept_display_text,
    find_designation,
)
from tricc_oo.runner import run_project_build
from tricc_oo.text import from_html
from tricc_oo.text.model import TriccText
from tricc_oo.visitors.text_injection import load_display_text

HL7 = "http://terminology.hl7.org/CodeSystem/designation-usage"
TRICC = "https://tricc.org/CodeSystem/designation-use"

GIVE_DOC = {"type": "doc", "content": [{"type": "paragraph", "content": [
    {"type": "text", "text": "Give ", "marks": [{"type": "bold"}]},
    {"type": "interp", "attrs": {"name": "age"}, "marks": [{"type": "bold"}]},
    {"type": "text", "text": " mg", "marks": [{"type": "bold"}]},
    {"type": "hardBreak"},
    {"type": "text", "text": "with food"},
]}]}
OLD_TREE = {"type": "message", "children": [
    {"type": "text", "value": "Weigh "},
    {"type": "mark", "kind": "em", "children": [{"type": "text", "value": "naked"}]},
]}


def _designation(lang, system, code, value, extension=None):
    designation = {"language": lang, "use": {"system": system, "code": code}, "value": value}
    if extension:
        designation["extension"] = [extension]
    return designation


def _ext(url, data):
    return {"url": url, "valueString": data if isinstance(data, str) else json.dumps(data)}


CODESYSTEM = {
    "resourceType": "CodeSystem",
    "id": "demo",
    "name": "demo",
    "url": "http://example.com/fhir/CodeSystem/demo",
    "status": "draft",
    "content": "complete",
    "concept": [
        {"code": "age", "display": "Age (years)"},
        {
            "code": "dose_note",
            "display": "Give ${age} mg (stale)",
            "designation": [
                _designation(
                    "en", HL7, "display", "**Give ${age} mg**\nwith food", _ext(DESIGNATION_DOC_EXT, GIVE_DOC)
                ),
                _designation("en", TRICC, "hint", "Weigh _naked_", _ext(DESIGNATION_MESSAGE_EXT, OLD_TREE)),
                _designation("en", TRICC, "help", "**Fallback** help", _ext(DESIGNATION_DOC_EXT, "{not json")),
            ],
        },
    ],
}

MAIN_YAML = """
id: concept_main
title: Concept main
process: main
nodes:
  - {id: start, type: start, label: Concept demo, name: start_concept}
  - {id: age, type: integer, name: age, required: true}
  - {id: note, type: note, name: dose_note}
  - {id: end, type: end, name: end_concept, label: End}
edges:
  - {source: start, target: age}
  - {source: age, target: note}
  - {source: note, target: end}
"""


def _build(tmp_path):
    (tmp_path / "yaml").mkdir()
    (tmp_path / "terminology").mkdir()
    (tmp_path / "yaml" / "main.yaml").write_text(MAIN_YAML, encoding="utf-8")
    (tmp_path / "terminology" / "demo.json").write_text(json.dumps(CODESYSTEM), encoding="utf-8")
    (tmp_path / "tricc.yaml").write_text(
        "\n".join([
            "title: Concept demo",
            "input_strategy: YamlStrategy",
            "output_strategies: [XLSFormStrategy]",
            "terminology: [terminology/*]",
            "interventions:",
            "  - id: concept",
            "    name: concept_demo",
            "    title: Concept",
            "    activity: [yaml/*]",
        ]),
        encoding="utf-8",
    )
    logging.disable(logging.WARNING)
    try:
        assert run_project_build(str(tmp_path), str(tmp_path / "out")) == 0
    finally:
        logging.disable(logging.NOTSET)
    (form,) = glob.glob(str(tmp_path / "out" / "**" / "*.xlsx"), recursive=True)
    survey = pd.read_excel(form, sheet_name="survey", dtype=str).fillna("")
    return survey[survey["name"] == "dose_note"].iloc[0]


def test_designation_doc_then_message_then_value(tmp_path):
    note = _build(tmp_path)
    assert note["label"] == "**Give ${age} mg**\nwith food"  # designation-doc, not the stale display
    assert note["hint"] == "Weigh _naked_"  # designation-message, read for compatibility
    assert note["help"] == "**Fallback** help"  # unreadable designation-doc: value


def test_concept_display_text_returns_the_document():
    concept = CodeSystemConcept(**CODESYSTEM["concept"][1])
    text = concept_display_text(concept, "display", "en", "en")
    assert isinstance(text, TriccText)
    assert text.doc == GIVE_DOC
    assert concept_display_text(CodeSystemConcept(code="x", display="Plain"), "display", "en", "en") == "Plain"


def test_designation_doc_round_trip():
    concept = CodeSystemConcept(code="muac")
    help_text = load_display_text("Measure on the <b>left</b> arm")
    add_concept_texts(concept, "en", hint="in mm", help=help_text)
    help_designation = find_designation(concept, "help", "en")
    assert help_designation.value == "Measure on the **left** arm"
    (extension,) = help_designation.extension
    assert extension.url == DESIGNATION_DOC_EXT
    assert json.loads(extension.valueString) == from_html("Measure on the <b>left</b> arm")
    again = concept_display_text(concept, "help", "en", "en")
    assert isinstance(again, TriccText) and again.doc == help_text.doc
    # a plain string costs no extension
    assert not find_designation(concept, "hint", "en").extension
