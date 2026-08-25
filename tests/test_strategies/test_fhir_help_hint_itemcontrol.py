"""Tests for help-message → itemControl help child, hint-message → entryFormat.

See feature/20260824-fhir-help-hint-itemcontrol.md.

Run with:
    python -m pytest tests/test_strategies/test_fhir_help_hint_itemcontrol.py -v
"""

import unittest
from unittest.mock import MagicMock

from tricc_oo.converters.fhir.questionnaire_item_mapper import (
    SDC_EXT_ENTRY_FORMAT,
    SDC_EXT_ITEM_CONTROL,
    build_entry_format_extension,
)
from tricc_oo.converters.tricc_to_xls_form import get_export_name
from tricc_oo.models.base import TriccNodeType
from tricc_oo.models.calculate import TriccNodeCalculate
from tricc_oo.models.tricc import TriccNodeInteger, TriccNodeNote, TriccNodeSelectOne
from tricc_oo.strategies.output.fhir_form import FHIRStrategy


def _make_strategy():
    project = MagicMock()
    project.start_pages = {}
    project.pages = {}
    project.code_systems = {}
    return FHIRStrategy(project, "/tmp/fhir_help_hint_test_out")


def _item_control_codes(item):
    codes = []
    for ext in item.get("extension") or []:
        if ext.get("url") != SDC_EXT_ITEM_CONTROL:
            continue
        for coding in (ext.get("valueCodeableConcept") or {}).get("coding") or []:
            if coding.get("code"):
                codes.append(coding["code"])
    return codes


def _child_by_control(parent, code):
    for child in parent.get("item") or []:
        if code in _item_control_codes(child):
            return child
    return None


def _entry_format(item):
    for ext in item.get("extension") or []:
        if ext.get("url") == SDC_EXT_ENTRY_FORMAT:
            return ext.get("valueString")
    return None


class TestHelpHintItemControl(unittest.TestCase):
    def test_entry_format_uses_official_fhir_url(self):
        ext = build_entry_format_extension("e.g. 12.5")
        self.assertEqual(ext["url"], "http://hl7.org/fhir/StructureDefinition/entryFormat")
        self.assertEqual(ext["valueString"], "e.g. 12.5")

    def test_help_and_hint_become_help_child_and_entry_format(self):
        strategy = _make_strategy()
        node = TriccNodeInteger(id="w", name="weight", label="Weight (kg)")
        node.help = "Enter the weight in kilograms"
        node.hint = "e.g. 12.5"

        self.assertTrue(strategy.generate_base(node))
        parent = strategy.questionnaires["main"]["item"][0]
        link_id = get_export_name(node)
        children = parent.get("item") or []
        self.assertEqual(len(children), 1)

        help_item = children[0]
        self.assertEqual(help_item["type"], "display")
        self.assertEqual(help_item["linkId"], f"{link_id}-help")
        self.assertEqual(help_item["text"], "Enter the weight in kilograms")
        self.assertEqual(_item_control_codes(help_item), ["help"])

        self.assertEqual(_entry_format(parent), "e.g. 12.5")
        self.assertNotIn("help", _item_control_codes(parent))
        self.assertIsNone(_child_by_control(parent, "flyover"))

    def test_only_help(self):
        strategy = _make_strategy()
        node = TriccNodeInteger(id="w", name="weight", label="Weight")
        node.help = "Use kilograms"

        strategy.generate_base(node)
        parent = strategy.questionnaires["main"]["item"][0]
        self.assertEqual(len(parent.get("item") or []), 1)
        self.assertIsNotNone(_child_by_control(parent, "help"))
        self.assertIsNone(_entry_format(parent))

    def test_only_hint(self):
        strategy = _make_strategy()
        node = TriccNodeInteger(id="w", name="weight", label="Weight")
        node.hint = "e.g. 12.5"

        strategy.generate_base(node)
        parent = strategy.questionnaires["main"]["item"][0]
        self.assertEqual(parent.get("item") or [], [])
        self.assertEqual(_entry_format(parent), "e.g. 12.5")
        self.assertIsNone(_child_by_control(parent, "help"))

    def test_hidden_calculate_does_not_get_help_or_hint(self):
        strategy = _make_strategy()
        node = TriccNodeCalculate(id="c", name="flag", label="Flag")
        node.help = "Should not appear"
        node.hint = "e.g. hidden"

        strategy.generate_base(node)
        parent = strategy.questionnaires["main"]["item"][0]
        self.assertTrue(parent.get("extension"))
        self.assertEqual(parent.get("item") or [], [])
        self.assertIsNone(_entry_format(parent))

    def test_blank_help_and_missing_hint_emit_no_children(self):
        strategy = _make_strategy()
        node = TriccNodeInteger(id="w", name="weight", label="Weight")
        node.help = "   "

        strategy.generate_base(node)
        parent = strategy.questionnaires["main"]["item"][0]
        self.assertEqual(parent.get("item") or [], [])
        self.assertIsNone(_entry_format(parent))

    def test_parent_widget_item_control_stays_on_parent(self):
        strategy = _make_strategy()
        node = TriccNodeSelectOne(id="s", name="sex", label="Sex", list_name="sex")
        node.help = "Pick one"

        strategy.generate_base(node)
        parent = strategy.questionnaires["main"]["item"][0]
        self.assertIn("radio-button", _item_control_codes(parent))
        self.assertNotIn("help", _item_control_codes(parent))
        self.assertEqual(_item_control_codes(_child_by_control(parent, "help")), ["help"])

    def test_standalone_help_message_node_is_skipped(self):
        strategy = _make_strategy()
        node = TriccNodeNote(id="h", name="help_box", label="Help text")
        node.tricc_type = TriccNodeType.help

        self.assertTrue(strategy.generate_base(node))
        self.assertEqual(strategy.questionnaires, {})


class TestHelpHintYamlWalk(unittest.TestCase):
    def test_process_base_nests_help_and_hint_from_yaml(self):
        from tests.helpers import load_yaml_project

        project = load_yaml_project("tests/data/yaml/help_hint_itemcontrol.yaml")
        strategy = FHIRStrategy(project, "/tmp/fhir_help_hint_yaml_out")
        strategy.process_base(project.start_pages, pages=project.pages)
        q = strategy.questionnaires.get("main") or next(iter(strategy.questionnaires.values()))

        def find(items, link_id):
            for it in items or []:
                if it.get("linkId") == link_id:
                    return it
                found = find(it.get("item"), link_id)
                if found is not None:
                    return found
            return None

        weight = find(q.get("item"), "weight")
        self.assertIsNotNone(weight, q.get("item"))
        help_item = _child_by_control(weight, "help")
        self.assertIsNotNone(help_item)
        self.assertEqual(help_item["text"], "Enter the weight in kilograms")
        self.assertEqual(_entry_format(weight), "e.g. 12.5")
        self.assertIsNone(_child_by_control(weight, "flyover"))
