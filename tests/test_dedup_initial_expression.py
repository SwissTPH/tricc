"""Tests for auto-wired dedup ``initialExpression`` on Observation/Condition-typed items.

See feature/20260812-intervention-order-and-dedup.md.
"""

import unittest
from unittest.mock import MagicMock

from tricc_oo.models.calculate import TriccNodeActivityStart
from tricc_oo.models.tricc import TriccNodeInteger, TriccNodeNote
from tricc_oo.converters.fhir.questionnaire_item_mapper import (
    SDC_EXT_INITIAL_EXPR,
    SDC_EXT_CALCULATED_EXPR,
    build_calculated_expression_fhirpath,
    build_initial_expression,
    item_allows_initial,
)
from tricc_oo.strategies.output.fhir_form import FHIRStrategy


def _make_strategy():
    project = MagicMock()
    project.start_pages = {}
    project.pages = {}
    project.code_systems = {}
    return FHIRStrategy(project, "/tmp/fhir-dedup-out")


class TestDedupInitialExpression(unittest.TestCase):
    def test_observation_item_gets_dedup_initial_expression(self):
        strategy = _make_strategy()
        strategy.questionnaires["main"] = {
            "resourceType": "Questionnaire",
            "item": [{"linkId": "cough", "type": "boolean"}],
        }
        node = TriccNodeInteger(
            id="n1", name="cough", label="Cough", concept_type="finding"
        )
        strategy.generate_export(node)
        item = strategy.questionnaires["main"]["item"][0]
        exts = item.get("extension", [])
        self.assertTrue(any(e["url"] == SDC_EXT_INITIAL_EXPR for e in exts))
        cql_defines = "\n".join(strategy.cql_defines.get("main", []))
        self.assertIn("Helper.GetObservationValue('cough')", cql_defines)

    def test_observation_repeat_slot_uses_get_repeated_value(self):
        strategy = _make_strategy()
        strategy.questionnaires["main"] = {
            "resourceType": "Questionnaire",
            "item": [{"linkId": "weight_Rr_2", "type": "decimal"}],
        }
        node = TriccNodeInteger(
            id="n2",
            name="weight",
            label="Weight",
            concept_type="finding",
            repeat=2,
        )
        strategy.generate_export(node)
        cql_defines = "\n".join(strategy.cql_defines.get("main", []))
        self.assertIn("Helper.GetRepeatedValue('weight', 2)", cql_defines)
        self.assertNotIn("Helper.GetObservationValue('weight')", cql_defines)

    def test_condition_item_gets_dedup_initial_expression(self):
        strategy = _make_strategy()
        strategy.questionnaires["main"] = {
            "resourceType": "Questionnaire",
            "item": [{"linkId": "malaria", "type": "boolean"}],
        }
        node = TriccNodeInteger(
            id="n3", name="malaria", label="Malaria", concept_type="diagnosis"
        )
        strategy.generate_export(node)
        item = strategy.questionnaires["main"]["item"][0]
        exts = item.get("extension", [])
        self.assertTrue(any(e["url"] == SDC_EXT_INITIAL_EXPR for e in exts))
        cql_defines = "\n".join(strategy.cql_defines.get("main", []))
        self.assertIn("Helper.GetConditionValue('malaria')", cql_defines)

    def test_author_authored_calculated_expression_is_not_overwritten(self):
        strategy = _make_strategy()
        item = {"linkId": "cough", "type": "boolean"}
        item.setdefault("extension", []).append(
            build_calculated_expression_fhirpath("true")
        )
        strategy.questionnaires["main"] = {"resourceType": "Questionnaire", "item": [item]}
        node = TriccNodeInteger(
            id="n4", name="cough", label="Cough", concept_type="finding"
        )
        strategy.generate_export(node)
        exts = item.get("extension", [])
        self.assertEqual(len(exts), 1)
        self.assertEqual(exts[0]["url"], SDC_EXT_CALCULATED_EXPR)

    def test_non_dedup_concept_type_is_untouched(self):
        strategy = _make_strategy()
        strategy.questionnaires["main"] = {
            "resourceType": "Questionnaire",
            "item": [{"linkId": "med", "type": "string"}],
        }
        node = TriccNodeInteger(
            id="n5", name="med", label="Medication", concept_type="drug"
        )
        strategy.generate_export(node)
        item = strategy.questionnaires["main"]["item"][0]
        self.assertNotIn("extension", item)

    def test_note_display_item_gets_no_dedup_initial_expression(self):
        """SDC + openSRP $populate: display items must not carry initialExpression."""
        strategy = _make_strategy()
        strategy.questionnaires["main"] = {
            "resourceType": "Questionnaire",
            "item": [{"linkId": "demo_sorry", "type": "display"}],
        }
        node = TriccNodeNote(id="n6", name="demo_sorry", label="Sorry")
        strategy.generate_export(node)
        item = strategy.questionnaires["main"]["item"][0]
        exts = item.get("extension") or []
        self.assertFalse(any(e["url"] == SDC_EXT_INITIAL_EXPR for e in exts))
        self.assertEqual(strategy.cql_defines, {})

    def test_note_with_finding_concept_type_still_skipped(self):
        """Even an explicit finding concept_type cannot put initialExpression on display."""
        strategy = _make_strategy()
        strategy.questionnaires["main"] = {
            "resourceType": "Questionnaire",
            "item": [{"linkId": "demo_sorry", "type": "display"}],
        }
        node = TriccNodeNote(
            id="n7", name="demo_sorry", label="Sorry", concept_type="finding"
        )
        strategy.generate_export(node)
        item = strategy.questionnaires["main"]["item"][0]
        exts = item.get("extension") or []
        self.assertFalse(any(e["url"] == SDC_EXT_INITIAL_EXPR for e in exts))
        self.assertEqual(strategy.cql_defines, {})

    def test_activity_start_group_gets_no_dedup_initial_expression(self):
        """SDC + openSRP $populate: group items must not carry initialExpression."""
        strategy = _make_strategy()
        strategy.questionnaires["main"] = {
            "resourceType": "Questionnaire",
            "item": [{"linkId": "act1", "type": "group", "item": []}],
        }
        node = TriccNodeActivityStart(id="act1", name="act1", label="Act")
        strategy.generate_export(node)
        item = strategy.questionnaires["main"]["item"][0]
        exts = item.get("extension") or []
        self.assertFalse(any(e["url"] == SDC_EXT_INITIAL_EXPR for e in exts))
        self.assertEqual(strategy.cql_defines, {})

    def test_sanitize_strips_illegal_initial_expression_from_group_and_display(self):
        strategy = _make_strategy()
        group = {
            "linkId": "g1",
            "type": "group",
            "extension": [build_initial_expression("Dedup_g1")],
            "item": [
                {
                    "linkId": "note1",
                    "type": "display",
                    "extension": [build_initial_expression("Dedup_note1")],
                    "initial": [{"valueString": "x"}],
                },
                {"linkId": "cough", "type": "boolean",
                 "extension": [build_initial_expression("Dedup_cough")]},
            ],
        }
        strategy.questionnaires["main"] = {"resourceType": "Questionnaire", "item": [group]}
        strategy._sanitize_questionnaires()
        self.assertFalse(item_allows_initial(group))
        self.assertFalse(any(
            e["url"] == SDC_EXT_INITIAL_EXPR for e in (group.get("extension") or [])
        ))
        note = group["item"][0]
        self.assertNotIn("initial", note)
        self.assertFalse(any(
            e["url"] == SDC_EXT_INITIAL_EXPR for e in (note.get("extension") or [])
        ))
        cough = group["item"][1]
        self.assertTrue(any(e["url"] == SDC_EXT_INITIAL_EXPR for e in cough["extension"]))


if __name__ == "__main__":
    unittest.main()
