"""Tests for ``${REF}`` display text → cqf-expression on ``item._text``.

See fix/20260831-fhir-dynamic-display-text.md.

Run with:
    python -m pytest tests/test_strategies/test_fhir_display_text_expression.py -v
"""

import unittest
from unittest.mock import MagicMock

from tricc_oo.converters.fhir.questionnaire_item_mapper import (
    CQF_EXT_TEXT_EXPRESSION,
    SDC_EXT_ITEM_CONTROL,
)
from tricc_oo.models.base import TriccOperation, TriccOperator, TriccReference, TriccStatic
from tricc_oo.models.calculate import TriccNodeCalculate
from tricc_oo.models.tricc import TriccNodeInteger, TriccNodeNote
from tricc_oo.strategies.output.fhir_form import FHIRStrategy


def _make_strategy():
    project = MagicMock()
    project.start_pages = {}
    project.pages = {}
    project.code_systems = {}
    return FHIRStrategy(project, "/tmp/fhir_display_text_test_out")


def _injection(*parts):
    """Build the CONCATENATE a ``${REF}`` label is loaded as."""
    operands = [
        TriccReference(p[1]) if isinstance(p, tuple) else TriccStatic(p) for p in parts
    ]
    return TriccOperation(operator=TriccOperator.CONCATENATE, reference=operands)


def _find(items, link_id):
    for item in items or []:
        if item.get("linkId") == link_id:
            return item
        found = _find(item.get("item"), link_id)
        if found is not None:
            return found
    return None


def _text_expression(item):
    for ext in (item.get("_text") or {}).get("extension") or []:
        if ext.get("url") == CQF_EXT_TEXT_EXPRESSION:
            return ext.get("valueExpression") or {}
    return None


def _child_by_control(parent, code):
    for child in parent.get("item") or []:
        for ext in child.get("extension") or []:
            if ext.get("url") != SDC_EXT_ITEM_CONTROL:
                continue
            for coding in (ext.get("valueCodeableConcept") or {}).get("coding") or []:
                if coding.get("code") == code:
                    return child
    return None


class TestDisplayTextExpression(unittest.TestCase):
    def test_note_keeps_tokens_in_text_and_gets_fhirpath_expression(self):
        strategy = _make_strategy()
        age = TriccNodeInteger(id="a", name="age", label="Age")
        note = TriccNodeNote(id="n", name="note_age", label="")
        note.label = _injection("Patient is ", ("ref", "age"), " years old")

        strategy.generate_base(age)
        strategy.generate_base(note)
        strategy.process_display_text()

        item = _find(strategy.questionnaires["main"]["item"], "note_age")
        self.assertEqual(item["text"], "Patient is ${age} years old")

        expression = _text_expression(item)
        self.assertIsNotNone(expression, item)
        self.assertEqual(expression["language"], "text/fhirpath")
        self.assertIn("&", expression["expression"])
        self.assertIn("linkId='age'", expression["expression"])
        self.assertIn(".toString()", expression["expression"])
        # The CQL rendering (' + age + ') must never reach the Questionnaire.
        self.assertNotIn(" + ", expression["expression"])
        self.assertNotIn(" + ", item["text"])

    def test_integer_reference_is_cast_to_string(self):
        strategy = _make_strategy()
        age = TriccNodeInteger(id="a", name="age", label="Age")
        note = TriccNodeNote(id="n", name="note_age", label="")
        note.label = _injection("Age: ", ("ref", "age"))

        strategy.generate_base(age)
        strategy.generate_base(note)
        strategy.process_display_text()

        expression = _text_expression(_find(strategy.questionnaires["main"]["item"], "note_age"))
        self.assertTrue(
            expression["expression"].endswith(".value).toString()"), expression["expression"]
        )

    def test_choice_reference_renders_the_option_label(self):
        strategy = _make_strategy()
        from tricc_oo.models.tricc import TriccNodeSelectOne, TriccNodeSelectOption

        sex = TriccNodeSelectOne(id="s", name="sex", label="Sex", list_name="sex")
        sex.options = {
            0: TriccNodeSelectOption(id="m", name="male", label="Male", list_name="sex", select=sex),
        }
        note = TriccNodeNote(id="n", name="note_sex", label="")
        note.label = _injection("Sex is ", ("ref", "sex"))

        strategy.generate_base(sex)
        strategy.generate_base(note)
        strategy.process_display_text()

        expression = _text_expression(_find(strategy.questionnaires["main"]["item"], "note_sex"))
        self.assertIn(".value.display", expression["expression"])
        self.assertNotIn(".value.code", expression["expression"])

    def test_help_and_hint_children_carry_their_own_expression(self):
        strategy = _make_strategy()
        age = TriccNodeInteger(id="a", name="age", label="Age")
        question = TriccNodeInteger(id="c", name="confirm_age", label="Confirm")
        question.help = _injection("Recorded age is ", ("ref", "age"))
        question.hint = _injection("e.g. ", ("ref", "age"))

        strategy.generate_base(age)
        strategy.generate_base(question)
        strategy.process_display_text()

        parent = _find(strategy.questionnaires["main"]["item"], "confirm_age")
        help_item = _child_by_control(parent, "help")
        hint_item = _child_by_control(parent, "flyover")

        self.assertEqual(help_item["text"], "Recorded age is ${age}")
        self.assertIn("linkId='age'", _text_expression(help_item)["expression"])
        self.assertEqual(hint_item["text"], "e.g. ${age}")
        self.assertIn("linkId='age'", _text_expression(hint_item)["expression"])

    def test_plain_label_gets_no_text_element(self):
        strategy = _make_strategy()
        node = TriccNodeInteger(id="w", name="weight", label="Weight (kg)")

        strategy.generate_base(node)
        strategy.process_display_text()

        item = _find(strategy.questionnaires["main"]["item"], "weight")
        self.assertEqual(item["text"], "Weight (kg)")
        self.assertNotIn("_text", item)

    def test_hidden_calculate_gets_no_text_expression(self):
        strategy = _make_strategy()
        age = TriccNodeInteger(id="a", name="age", label="Age")
        calc = TriccNodeCalculate(id="c", name="age_note", label="")
        calc.label = _injection("Age is ", ("ref", "age"))

        strategy.generate_base(age)
        strategy.generate_base(calc)
        strategy.process_display_text()

        item = _find(strategy.questionnaires["main"]["item"], "age_note")
        self.assertIsNotNone(item)
        self.assertNotIn("_text", item)


class TestDisplayTextYamlWalk(unittest.TestCase):
    def test_full_pipeline_from_yaml(self):
        from tests.helpers import load_yaml_project

        project = load_yaml_project("tests/data/yaml/display_text_injection.yaml")
        strategy = FHIRStrategy(project, "/tmp/fhir_display_text_yaml_out")
        strategy.process_base(project.start_pages, pages=project.pages)
        strategy.process_display_text(project.start_pages, pages=project.pages)
        q = strategy.questionnaires.get("main") or next(iter(strategy.questionnaires.values()))

        note = _find(q.get("item"), "note_patient")
        self.assertIsNotNone(note, q.get("item"))
        self.assertEqual(note["text"], "Patient is ${age} years old and ${sex}")

        expression = _text_expression(note)["expression"]
        self.assertTrue(expression.startswith("'Patient is ' & "), expression)
        self.assertIn("linkId='age'", expression)
        self.assertIn("linkId='sex'", expression)
        self.assertIn(".value.display", expression)
        self.assertNotIn(" + ", expression)

    def test_dynamic_text_reference_keeps_hidden_calculate(self):
        """A calculate shown only inside a note's text must survive pruning."""
        from tests.helpers import load_yaml_project

        project = load_yaml_project("tests/data/yaml/display_text_injection.yaml")
        strategy = FHIRStrategy(project, "/tmp/fhir_display_text_prune_out")
        strategy.process_base(project.start_pages, pages=project.pages)
        note = _find(strategy.questionnaires["main"]["item"], "note_patient")
        note["_text"] = {
            "extension": [
                {
                    "url": CQF_EXT_TEXT_EXPRESSION,
                    "valueExpression": {
                        "language": "text/fhirpath",
                        "expression": "%resource.item.where(linkId='is_adult').answer.value.toString()",
                    },
                }
            ]
        }
        referenced = strategy._collect_expression_link_ids(strategy.questionnaires["main"]["item"])
        self.assertIn("is_adult", referenced)


if __name__ == "__main__":
    unittest.main()
