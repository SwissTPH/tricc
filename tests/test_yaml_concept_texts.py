"""YamlStrategy reads node / option texts from the project CodeSystem (tricc.yaml ``terminology``)."""

from __future__ import annotations

import glob
import json
import logging

import pandas as pd

from tricc_oo.runner import run_project_build

HL7 = "http://terminology.hl7.org/CodeSystem/designation-usage"
TRICC = "https://tricc.org/CodeSystem/designation-use"


def _designation(lang, system, code, value):
    return {"language": lang, "use": {"system": system, "code": code}, "value": value}


CODESYSTEM = {
    "resourceType": "CodeSystem",
    "id": "demo",
    "name": "demo",
    "url": "http://example.com/fhir/CodeSystem/demo",
    "status": "draft",
    "content": "complete",
    "concept": [
        {
            "code": "age",
            "display": "Age (years)",
            "designation": [
                _designation("en", TRICC, "hint", "Completed years"),
                _designation("en", TRICC, "help", "Ask the caregiver"),
                _designation("fr", HL7, "display", "Âge (années)"),
            ],
        },
        {"code": "fever", "display": "Does the child have fever?"},
        {"code": "fever_yes", "display": "Yes, fever"},
        {"code": "fever_no", "display": "No fever"},
        {"code": "intro", "display": "Welcome", "designation": [_designation("en", TRICC, "hint", "Read first")]},
    ],
}

MAIN_YAML = """
id: concept_main
title: Concept main
process: main
nodes:
  - {id: start, type: start, label: Concept demo, name: start_concept, form_id: concept_demo}
  - {id: intro, type: note, name: intro, label: Inline intro}
  - {id: age, type: integer, name: age, required: true}
  - id: fev
    type: select_one
    name: has_fever
    concept: {code: fever, system: demo}
    options:
      - {id: o1, name: yes_fever, concept: fever_yes}
      - {id: o2, concept: fever_no}
      - {id: o3, name: unknown}
  - {id: other, type: text, name: other_text, hint: Free text, concept: not_in_terminology}
  - {id: end, type: end, name: end_concept, label: End}
edges:
  - {source: start, target: intro}
  - {source: intro, target: age}
  - {source: age, target: fev}
  - {source: fev, target: other}
  - {source: other, target: end}
"""


def _build(tmp_path):
    (tmp_path / "yaml").mkdir()
    (tmp_path / "terminology").mkdir()
    (tmp_path / "yaml" / "main.yaml").write_text(MAIN_YAML, encoding="utf-8")
    (tmp_path / "terminology" / "demo.json").write_text(json.dumps(CODESYSTEM), encoding="utf-8")
    (tmp_path / "tricc.yaml").write_text(
        "\n".join(
            [
                "title: Concept demo",
                "input_strategy: YamlStrategy",
                "output_strategies: [XLSFormStrategy]",
                "terminology: [terminology/*]",
                "interventions:",
                "  - id: concept",
                "    title: Concept",
                "    activity: [yaml/*]",
            ]
        ),
        encoding="utf-8",
    )
    logging.disable(logging.WARNING)
    try:
        assert run_project_build(str(tmp_path), str(tmp_path / "out")) == 0
    finally:
        logging.disable(logging.NOTSET)
    (form,) = glob.glob(str(tmp_path / "out" / "**" / "*.xlsx"), recursive=True)
    survey = pd.read_excel(form, sheet_name="survey", dtype=str).fillna("")
    choices = pd.read_excel(form, sheet_name="choices", dtype=str).fillna("")
    return survey, choices


def _row(survey, name):
    rows = survey[survey["name"] == name]
    assert len(rows) == 1, f"{name}: {list(survey['name'])}"
    return rows.iloc[0]


def test_labels_hints_and_help_come_from_the_codesystem(tmp_path):
    survey, choices = _build(tmp_path)
    age = _row(survey, "age")
    assert age["label"] == "Age (years)"
    assert age["hint"] == "Completed years"
    assert age["help"] == "Ask the caregiver"
    assert _row(survey, "has_fever")["label"] == "Does the child have fever?"
    labels = dict(zip(choices["value"], choices["label"]))
    assert labels["yes_fever"] == "Yes, fever"
    assert labels["fever_no"] == "No fever"  # option name defaults to its concept code
    assert labels["unknown"] == "unknown"  # no concept: falls back to the name


def test_inline_text_wins_and_missing_concept_does_not_fail(tmp_path):
    survey, _ = _build(tmp_path)
    intro = _row(survey, "intro")
    assert intro["label"] == "Inline intro"
    assert intro["hint"] == "Read first"  # not authored inline: from the concept
    assert _row(survey, "other_text")["label"] == ""


# --- translations on export (parameters.languages) ---------------------------------

TRANSLATED = {
    **CODESYSTEM,
    "concept": [
        {
            "code": "age",
            "display": "Age (years)",
            "designation": [
                _designation("en", TRICC, "hint", "Completed years"),
                _designation("fr", HL7, "display", "Âge (années)"),
                _designation("fr", TRICC, "hint", "Années révolues"),
                _designation("fr", TRICC, "help", "Demander à la personne"),
                _designation("en", TRICC, "help", "Ask the caregiver"),
            ],
        },
        {"code": "fever", "display": "Does the child have fever?",
         "designation": [_designation("fr", HL7, "display", "L'enfant a-t-il de la fièvre ?")]},
        {"code": "fever_yes", "display": "Yes, fever", "designation": [_designation("fr", HL7, "display", "Oui")]},
        {"code": "fever_no", "display": "No fever"},
        {"code": "intro", "display": "Welcome"},
    ],
}


def _build_translated(tmp_path, output="XLSFormStrategy", languages="{default: en, available: [en, fr]}"):
    (tmp_path / "yaml").mkdir()
    (tmp_path / "terminology").mkdir()
    (tmp_path / "yaml" / "main.yaml").write_text(MAIN_YAML, encoding="utf-8")
    (tmp_path / "terminology" / "demo.json").write_text(json.dumps(TRANSLATED), encoding="utf-8")
    (tmp_path / "tricc.yaml").write_text(
        "\n".join(
            [
                "title: Concept demo",
                "input_strategy: YamlStrategy",
                f"output_strategies: [{output}]",
                f"parameters: {{languages: {languages}}}",
                "terminology: [terminology/*]",
                "interventions:",
                "  - id: concept",
                "    title: Concept",
                "    activity: [yaml/*]",
            ]
        ),
        encoding="utf-8",
    )
    logging.disable(logging.WARNING)
    try:
        assert run_project_build(str(tmp_path), str(tmp_path / "out")) == 0
    finally:
        logging.disable(logging.NOTSET)
    (form,) = glob.glob(str(tmp_path / "out" / "**" / "*.xlsx"), recursive=True)
    return {
        sheet: pd.read_excel(form, sheet_name=sheet, dtype=str).fillna("")
        for sheet in ("survey", "choices", "settings")
    }


def test_xlsform_has_one_text_column_per_language_from_designations(tmp_path):
    sheets = _build_translated(tmp_path)
    survey, choices = sheets["survey"], sheets["choices"]
    assert "label" not in survey.columns
    cols = list(survey.columns)
    assert cols[cols.index("label::en") + 1] == "label::fr"
    age = _row(survey, "age")
    assert (age["label::en"], age["label::fr"]) == ("Age (years)", "Âge (années)")
    assert (age["hint::en"], age["hint::fr"]) == ("Completed years", "Années révolues")
    assert (age["help::en"], age["help::fr"]) == ("Ask the caregiver", "Demander à la personne")
    assert _row(survey, "age_more_info")["label::fr"] == "Demander à la personne"
    assert _row(survey, "has_fever")["label::fr"] == "L'enfant a-t-il de la fièvre ?"
    # no designation: the default-language text is kept
    assert _row(survey, "intro")["label::fr"] == "Inline intro"
    fr = dict(zip(choices["value"], choices["label::fr"]))
    assert fr["yes_fever"] == "Oui"
    assert fr["fever_no"] == "No fever"
    assert sheets["settings"].iloc[0]["default_language"] == "en"


def test_cht_export_is_translated_too(tmp_path):
    sheets = _build_translated(tmp_path, output="XLSFormCHTStrategy", languages="[fr, en]")
    survey = sheets["survey"]
    assert {"label::fr", "label::en"} <= set(survey.columns)
    age = _row(survey, "age")
    assert (age["label::fr"], age["label::en"]) == ("Age (years)", "Age (years)")
    # the default language (fr) was resolved by the yaml input; en comes from the designations
    assert (age["hint::fr"], age["hint::en"]) == ("Années révolues", "Completed years")
    assert sheets["settings"].iloc[0]["default_language"] == "fr"


def _walk_items(items):
    for item in items or []:
        yield item
        yield from _walk_items(item.get("item"))


def _translations(element, field):
    return {
        {e["url"]: e.get("valueCode") or e.get("valueString") for e in ext["extension"]}["lang"]:
        {e["url"]: e.get("valueCode") or e.get("valueString") for e in ext["extension"]}["content"]
        for ext in (element.get(f"_{field}") or {}).get("extension", [])
        if ext["url"] == "http://hl7.org/fhir/StructureDefinition/translation"
    }


def test_fhir_questionnaire_carries_translation_extensions(tmp_path):
    (tmp_path / "yaml").mkdir()
    (tmp_path / "terminology").mkdir()
    (tmp_path / "yaml" / "main.yaml").write_text(MAIN_YAML, encoding="utf-8")
    (tmp_path / "terminology" / "demo.json").write_text(json.dumps(TRANSLATED), encoding="utf-8")
    (tmp_path / "tricc.yaml").write_text(
        "\n".join(
            [
                "title: Concept demo",
                "input_strategy: YamlStrategy",
                "output_strategies: [FHIRStrategy]",
                "parameters: {languages: {default: en, available: [en, fr]}}",
                "terminology: [terminology/*]",
                "interventions:",
                "  - id: concept",
                "    title: Concept",
                "    activity: [yaml/*]",
            ]
        ),
        encoding="utf-8",
    )
    logging.disable(logging.WARNING)
    try:
        assert run_project_build(str(tmp_path), str(tmp_path / "out")) == 0
    finally:
        logging.disable(logging.NOTSET)
    items = {}
    for path in glob.glob(str(tmp_path / "out" / "**" / "*.json"), recursive=True):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if data.get("resourceType") == "Questionnaire":
            items.update({i["linkId"]: i for i in _walk_items(data.get("item"))})
    age = items["age"]
    assert _translations(age, "text") == {"fr": "Âge (années)"}
    children = {c["linkId"]: c for c in age.get("item", [])}
    assert _translations(children["age-hint"], "text") == {"fr": "Années révolues"}
    assert _translations(children["age-help"], "text") == {"fr": "Demander à la personne"}
    assert _translations(items["intro"], "text") == {}
    options = {o["valueCoding"]["code"]: o["valueCoding"] for o in items["has_fever"]["answerOption"]}
    assert _translations(options["yes_fever"], "display") == {"fr": "Oui"}
