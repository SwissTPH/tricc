"""Tests for FHIR / CQL concept repeat export (phase 4)."""

import unittest

from tricc_oo.models.tricc import TriccNodeInteger
from tricc_oo.models.calculate import TriccNodePopulate
from tricc_oo.converters.fhir.populate_helper import cql_helper_populate_block
from tricc_oo.converters.fhir.repeat_helper import (
    TRICC_OBSERVATION_REPEAT_EXT,
    TRICC_QUESTIONNAIRE_REPEAT_EXT,
    build_questionnaire_repeat_extension,
    cql_helper_repeat_block,
    get_observation_cql_accessor,
    get_observation_cql_accessor_for_node,
    should_emit_repeat_metadata,
)
from tricc_oo.strategies.output.fhir_form import FHIRStrategy, CQL_HELPER_TEMPLATE, FHIR_VERSION


class TestRepeatHelper(unittest.TestCase):
    def test_default_repeat_no_metadata(self):
        node = TriccNodeInteger(id="n1", name="weight", label="Weight")
        self.assertFalse(should_emit_repeat_metadata(node))

    def test_repeat_two_emits_metadata(self):
        node = TriccNodeInteger(id="n2", name="weight", label="Weight", repeat=2)
        self.assertTrue(should_emit_repeat_metadata(node))

    def test_questionnaire_extension(self):
        ext = build_questionnaire_repeat_extension(3)
        self.assertEqual(ext["url"], TRICC_QUESTIONNAIRE_REPEAT_EXT)
        self.assertEqual(ext["valueInteger"], 3)

    def test_cql_accessor_default_slot(self):
        self.assertEqual(
            get_observation_cql_accessor("weight", 1),
            "Helper.GetObservationValue('weight')",
        )

    def test_cql_accessor_repeat_slot(self):
        self.assertEqual(
            get_observation_cql_accessor("weight", 2),
            "Helper.GetRepeatedValue('weight', 2)",
        )

    def test_cql_accessor_for_input_node(self):
        node = TriccNodePopulate(id="i1", name="temperature", label="Temp", repeat=2)
        self.assertEqual(
            get_observation_cql_accessor_for_node(node),
            "Helper.GetRepeatedValue('temperature', 2)",
        )

    def test_cql_helper_block_contains_repeat_functions(self):
        block = cql_helper_repeat_block()
        self.assertIn("GetRepeated", block)
        self.assertIn("GetNumberOfRepeat", block)
        self.assertIn("GetHistoryObservationValue", block)
        self.assertNotIn("GetLast", block)
        self.assertIn(TRICC_OBSERVATION_REPEAT_EXT, block)

    def test_cql_helper_block_encounter_scoped(self):
        block = cql_helper_repeat_block()
        self.assertIn("encounterid", block)
        self.assertIn("O.encounter.reference = 'Encounter/' + encounterid", block)

    def test_cql_helper_block_contains_condition_family(self):
        block = cql_helper_repeat_block()
        for fn in (
            "GetConditions",
            "GetCondition",
            "GetConditionValue",
            "GetHistoryCondition",
            "GetHistoryConditionValue",
            "HasConfirmedCondition",
            "HasProvisionalCondition",
            "HasRefutedCondition",
            "ConditionVerificationCode",
        ):
            self.assertIn(f"define function {fn}", block)

    def test_fml_repeat_extension_rule_is_executable(self):
        from tricc_oo.converters.fhir.repeat_helper import fml_repeat_extension_rule

        rule = fml_repeat_extension_rule("weight_Rr_2", "Observation", 2)
        self.assertFalse(any(line.strip().startswith("//") for line in rule.splitlines()))
        self.assertIn("Observation.extension", rule)
        self.assertIn(TRICC_OBSERVATION_REPEAT_EXT, rule)
        self.assertIn("ext.value = 2", rule)


class TestFHIRStrategyRepeatCQL(unittest.TestCase):
    def test_helper_template_includes_repeat_block(self):
        helper = CQL_HELPER_TEMPLATE.format(
            library_id="demo",
            fhir_version=FHIR_VERSION,
            repeat_helpers=cql_helper_repeat_block(FHIR_VERSION),
            populate_helpers=cql_helper_populate_block(),
        )
        self.assertIn("define function GetRepeated", helper)
        self.assertIn("define function GetNumberOfRepeat", helper)
        self.assertIn("define function GetHistoryObservationValue", helper)
        self.assertIn("define function GetPatientValue", helper)
        self.assertIn("parameter encounterid String default null", helper)
        self.assertNotIn("define function GetLast", helper)
        self.assertIn("define function GetObservations", helper)
        self.assertEqual(helper.count("define function GetObservation(code String)"), 1)

    def test_questionnaire_item_repeat_extension(self):
        from unittest.mock import MagicMock

        project = MagicMock()
        project.start_pages = {}
        project.pages = {}
        project.code_systems = {}
        strategy = FHIRStrategy(project, "/tmp/fhir-out")
        strategy.questionnaires["main"] = {"resourceType": "Questionnaire", "item": []}

        node = TriccNodeInteger(
            id="w1",
            name="weight",
            label="Weight",
            repeat=2,
            tricc_type="integer",
        )
        node.activity = MagicMock()
        node.activity.root = MagicMock(process="main")

        strategy.generate_base(node)
        item = strategy.questionnaires["main"]["item"][0]
        self.assertEqual(item["linkId"], "weight_Rr_2")
        repeat_exts = [
            e for e in item.get("extension", [])
            if e.get("url") == TRICC_QUESTIONNAIRE_REPEAT_EXT
        ]
        self.assertEqual(len(repeat_exts), 1)
        self.assertEqual(repeat_exts[0]["valueInteger"], 2)


if __name__ == "__main__":
    unittest.main()