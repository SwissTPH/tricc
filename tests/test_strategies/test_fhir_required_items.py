"""Regression tests for FHIRStrategy ``Questionnaire.item.required``.

TRICC inputs are required by default (``required = "1"``), and the XLSForm,
OpenMRS and DHIS2 exports honour it. The FHIR export did not emit
``item.required`` at all, so SDC renderers (OpenSRP) let a form be saved with
every question unanswered.

Run with:
    python -m pytest tests/test_strategies/test_fhir_required_items.py -v
"""

import unittest
from unittest.mock import MagicMock

from tricc_oo.models.base import TriccOperation, TriccOperator, TriccReference, TriccStatic
from tricc_oo.models.calculate import TriccNodeCalculate
from tricc_oo.models.tricc import (
    TriccNodeInteger,
    TriccNodeNote,
    TriccNodeSelectOne,
    TriccNodeText,
    TriccNodeTrigger,
)
from tricc_oo.strategies.output.fhir_form import FHIRStrategy


def _make_strategy():
    project = MagicMock()
    project.start_pages = {}
    project.pages = {}
    project.code_systems = {}
    project.images = []
    return FHIRStrategy(project, "/tmp/fhir_required_items_test_out")


def _item_for(node, strategy=None):
    strategy = strategy or _make_strategy()
    strategy.generate_base(node)
    return strategy.questionnaires["main"]["item"][0]


class TestRequiredItems(unittest.TestCase):
    def test_input_is_required_by_default(self):
        item = _item_for(TriccNodeInteger(id="sys", name="sys", label="Systolic BP"))
        self.assertIs(item.get("required"), True)

    def test_select_is_required_by_default(self):
        item = _item_for(
            TriccNodeSelectOne(id="smoke", name="smoke", label="Smoking", list_name="smoke")
        )
        self.assertIs(item.get("required"), True)

    def test_static_true_values_are_required(self):
        for value in ("1", "true", "Yes", TriccStatic(True), TriccStatic("1")):
            with self.subTest(required=value):
                item = _item_for(
                    TriccNodeText(id="note", name="note", label="Note", required=value)
                )
                self.assertIs(item.get("required"), True)

    def test_optional_input_is_not_required(self):
        # The YAML input normalises required: false to "0"; the visitor clears it with None.
        for value in ("0", "false", None, TriccStatic(False)):
            with self.subTest(required=value):
                item = _item_for(
                    TriccNodeText(id="note", name="note", label="Note", required=value)
                )
                self.assertNotIn("required", item)

    def test_conditional_required_is_not_exported(self):
        # Set on "not available" checkboxes: required only while the parent is empty.
        conditional = TriccOperation(TriccOperator.ISNULL, [TriccReference("parent")])
        for value in (conditional, TriccReference("parent")):
            with self.subTest(required=value):
                node = TriccNodeText(id="na", name="na", label="Not available")
                node.required = value
                self.assertNotIn("required", _item_for(node))

    def test_display_item_is_not_required(self):
        item = _item_for(TriccNodeNote(id="info", name="info", label="Information"))
        self.assertEqual(item["type"], "display")
        self.assertNotIn("required", item)

    def test_hidden_calculate_is_not_required(self):
        item = _item_for(TriccNodeCalculate(id="bmi", name="bmi", label="BMI"))
        self.assertNotIn("required", item)

    def test_trigger_is_not_required(self):
        item = _item_for(TriccNodeTrigger(id="ack", name="ack", label="Acknowledge"))
        self.assertNotIn("required", item)

    def test_item_hidden_by_false_relevance_is_not_required(self):
        strategy = _make_strategy()
        node = TriccNodeInteger(id="sys", name="sys", label="Systolic BP")
        item = _item_for(node, strategy)
        self.assertIs(item.get("required"), True)

        node.relevance = TriccStatic(False)
        strategy.generate_relevance(node)

        self.assertIn(
            "http://hl7.org/fhir/StructureDefinition/questionnaire-hidden",
            [ext["url"] for ext in item.get("extension", [])],
        )
        self.assertNotIn("required", item)


if __name__ == "__main__":
    unittest.main()
