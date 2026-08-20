"""Tests for conceptType-driven QuestionnaireResponse extraction StructureMaps."""

import unittest
from unittest.mock import MagicMock

from tricc_oo.converters.fhir.concept_mapper import classify_extraction, resolve_concept_type
from tricc_oo.converters.fhir.repeat_helper import TRICC_OBSERVATION_REPEAT_EXT
from tricc_oo.converters.fhir.structuremap import (
    SDC_EXT_TARGET_STRUCTUREMAP,
    apply_questionnaire_item_to_rule,
    build_extraction_fml,
    build_extraction_rule,
    build_extraction_structuremap,
)
from tricc_oo.models.base import TriccOperation, TriccOperator
from tricc_oo.models.calculate import TriccNodeProposedDiagnosis
from tricc_oo.models.tricc import (
    TRICC_FALSE_VALUE,
    TRICC_TRUE_VALUE,
    TriccNodeAcceptDiagnostic,
    TriccNodeInteger,
    TriccNodeNote,
    TriccNodeSelectOption,
)
from tricc_oo.models.calculate import TriccNodeCalculate
from tricc_oo.strategies.output.fhir_form import FHIRStrategy


def _accept_diag(code="malaria", label="Malaria"):
    node = TriccNodeAcceptDiagnostic(
        id=f"pre_final.{code}",
        name=f"pre_final.{code}",
        label=label,
        list_name="acc_rej",
    )
    yes = TriccNodeSelectOption(
        id=f"accept-{code}",
        name=TRICC_TRUE_VALUE,
        label="Accept",
        select=node,
        list_name=node.list_name,
    )
    no = TriccNodeSelectOption(
        id=f"reject-{code}",
        name=TRICC_FALSE_VALUE,
        label="Reject",
        select=node,
        list_name=node.list_name,
    )
    node.options = {0: yes, 1: no}
    return node


class TestClassifyExtraction(unittest.TestCase):
    def test_finding_is_observation(self):
        node = TriccNodeInteger(id="n1", name="cough", label="Cough", concept_type="finding")
        self.assertEqual(classify_extraction(node), "observation")

    def test_inferred_symptom_finding_is_observation(self):
        node = TriccNodeInteger(id="n2", name="weight", label="Weight")
        self.assertEqual(resolve_concept_type(node), "Symptom-Finding")
        self.assertEqual(classify_extraction(node), "observation")

    def test_proposed_diagnosis_is_provisional_condition(self):
        node = TriccNodeProposedDiagnosis(id="p1", name="malaria", label="Malaria")
        self.assertEqual(classify_extraction(node), "proposed_condition")

    def test_accept_diag_is_accept_condition(self):
        self.assertEqual(classify_extraction(_accept_diag()), "accept_condition")

    def test_note_is_skipped(self):
        node = TriccNodeNote(id="note1", name="demo.sorry", label="Sorry")
        self.assertIsNone(classify_extraction(node))

    def test_note_with_finding_concept_type_is_still_skipped(self):
        node = TriccNodeNote(
            id="note2", name="demo.sorry", label="Sorry", concept_type="finding"
        )
        self.assertIsNone(classify_extraction(node))

    def test_final_calculate_is_skipped(self):
        node = TriccNodeCalculate(id="final.malaria", name="final.malaria", label="Malaria")
        self.assertIsNone(classify_extraction(node))


class TestExtractionFml(unittest.TestCase):
    def test_observation_rule_and_repeat_extension(self):
        node = TriccNodeInteger(id="w2", name="weight", label="Weight", repeat=2)
        rule = build_extraction_rule(node)
        self.assertIsNotNone(rule)
        self.assertEqual(rule.kind, "observation")
        self.assertEqual(rule.repeat, 2)
        fml = build_extraction_fml([rule], "https://fhir.tricc.io/StructureMap/x", "x")
        self.assertIn('uses "http://hl7.org/fhir/StructureDefinition/QuestionnaireResponse" as source', fml)
        self.assertIn("create('Observation')", fml)
        self.assertIn(TRICC_OBSERVATION_REPEAT_EXT, fml)
        self.assertIn("ext.valueInteger = 2", fml)
        self.assertIn(f"linkId = '{rule.link_id}'", fml)
        self.assertIn("item as q where(", fml)
        self.assertIn("q.answer as answer then", fml)
        self.assertNotIn("item.where(", fml)
        self.assertIn('uses "http://hl7.org/fhir/StructureDefinition/Observation" as target', fml)
        self.assertNotIn(" as produced", fml)
        # HAPI Answer/Observation expose polymorphic ``value``, not valueInteger.
        self.assertIn("answer.value : integer as val -> tgt.value = val", fml)
        self.assertNotIn("answer.valueInteger", fml)
        self.assertNotIn("tgt.valueInteger", fml)
        self.assertNotIn("answer.valueBoolean as", fml)

    def test_boolean_observation_uses_polymorphic_value(self):
        from tricc_oo.models.tricc import TriccNodeSelectYesNo

        node = TriccNodeSelectYesNo(
            id="happy",
            name="demo_is_happy",
            label="Are you happy",
            list_name="yesno",
        )
        yes = TriccNodeSelectOption(
            id="y", name=TRICC_TRUE_VALUE, label="Yes", select=node, list_name="yesno"
        )
        no = TriccNodeSelectOption(
            id="n", name=TRICC_FALSE_VALUE, label="No", select=node, list_name="yesno"
        )
        node.options = {0: yes, 1: no}
        rule = build_extraction_rule(node)
        self.assertEqual(rule.qr_value_field, "valueBoolean")
        fml = build_extraction_fml([rule], "https://fhir.tricc.io/StructureMap/x", "x")
        self.assertIn("answer.value : boolean as val -> tgt.value = val", fml)
        self.assertNotIn("answer.valueBoolean as", fml)
        self.assertNotIn("tgt.valueBoolean", fml)
        self.assertFalse(rule.only_when_true)

    def test_option_flag_observation_is_true_when_applicable(self):
        node = TriccNodeCalculate(
            id="hungry",
            name="demo.hungry",
            label="Hungry",
            expression_reference=TriccOperation(operator=TriccOperator.CONTAINS),
        )
        # Codesystem conceptType is set as an extra attribute on draw.io nodes.
        object.__setattr__(node, "concept_type", "finding")
        rule = build_extraction_rule(node)
        self.assertEqual(rule.kind, "observation")
        self.assertTrue(rule.only_when_true)
        self.assertEqual(rule.qr_value_field, "valueBoolean")
        fml = build_extraction_fml([rule], "https://fhir.tricc.io/StructureMap/x", "x")
        self.assertIn("answer.valueBoolean = true", fml)
        self.assertIn("src -> tgt.value = true", fml)
        self.assertNotIn("answer.value : string", fml)

    def test_hidden_boolean_questionnaire_item_marks_only_when_true(self):
        node = TriccNodeInteger(id="n1", name="cough", label="Cough", concept_type="finding")
        rule = build_extraction_rule(node)
        self.assertFalse(rule.only_when_true)
        apply_questionnaire_item_to_rule(
            rule,
            {
                "linkId": "cough",
                "type": "boolean",
                "extension": [
                    {
                        "url": "http://hl7.org/fhir/StructureDefinition/questionnaire-hidden",
                        "valueBoolean": True,
                    }
                ],
            },
        )
        self.assertTrue(rule.only_when_true)
        fml = build_extraction_fml([rule], "https://fhir.tricc.io/StructureMap/x", "x")
        self.assertIn("src -> tgt.value = true", fml)

    def test_proposed_diagnosis_is_provisional_condition(self):
        node = TriccNodeProposedDiagnosis(id="p1", name="malaria", label="Malaria")
        rule = build_extraction_rule(node)
        self.assertEqual(rule.kind, "proposed_condition")
        fml = build_extraction_fml([rule], "https://fhir.tricc.io/StructureMap/x", "x")
        self.assertIn("create('Condition')", fml)
        self.assertIn("provisional", fml)
        self.assertIn("valueBoolean = true", fml)
        self.assertIn("'malaria'", fml)
        self.assertIn("item as q where(", fml)
        self.assertNotIn("item.where(", fml)

    def test_accept_diag_writes_confirmed_and_refuted(self):
        rule = build_extraction_rule(_accept_diag("malaria"))
        self.assertEqual(rule.kind, "accept_condition")
        self.assertEqual(rule.concept_code, "malaria")
        fml = build_extraction_fml([rule], "https://fhir.tricc.io/StructureMap/x", "x")
        self.assertIn("confirmed", fml)
        self.assertIn("refuted", fml)
        self.assertIn("valueBoolean = true", fml)
        self.assertIn("valueBoolean = false", fml)
        self.assertNotIn("final.malaria", fml)
        self.assertIn("item as q where(", fml)
        self.assertNotIn("item.where(", fml)

    def test_structuremap_resource_shape(self):
        node = TriccNodeInteger(id="n1", name="cough", label="Cough")
        rule = build_extraction_rule(node)
        sm = build_extraction_structuremap([rule], "demo", "main", "https://fhir.tricc.io")
        self.assertEqual(sm["resourceType"], "StructureMap")
        self.assertIn("_fml", sm)
        self.assertEqual(sm["structure"][0]["mode"], "source")
        self.assertIn("QuestionnaireResponse", sm["structure"][0]["url"])
        names = [g["name"] for g in sm["group"]]
        self.assertIn("extract", names)
        self.assertIn("extractItems", names)


class TestFHIRStrategyExtraction(unittest.TestCase):
    def test_generate_export_collects_observation_not_note(self):
        project = MagicMock()
        project.start_pages = {}
        project.pages = {}
        project.code_systems = {}
        strategy = FHIRStrategy(project, "/tmp/fhir-sm-out")
        strategy.questionnaires["main"] = {
            "resourceType": "Questionnaire",
            "item": [{"linkId": "cough", "type": "boolean"}],
        }
        finding = TriccNodeInteger(id="n1", name="cough", label="Cough", concept_type="finding")
        note = TriccNodeNote(id="n2", name="sorry", label="Sorry")
        strategy.generate_export(finding)
        strategy.generate_export(note)
        rules = strategy.extraction_rules.get("main") or []
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0].kind, "observation")

    def test_assemble_extraction_maps(self):
        project = MagicMock()
        project.start_pages = {}
        project.pages = {}
        project.code_systems = {}
        strategy = FHIRStrategy(project, "/tmp/fhir-sm-out")
        strategy._form_id = "demo"
        strategy.questionnaires["main"] = {
            "resourceType": "Questionnaire",
            "id": "q-main",
            "item": [{"linkId": "cough", "type": "boolean"}],
        }
        strategy.generate_export(
            TriccNodeInteger(id="n1", name="cough", label="Cough", concept_type="finding")
        )
        strategy._assemble_extraction_maps()
        sm = strategy.extraction_maps["main"]
        self.assertEqual(sm["resourceType"], "StructureMap")
        self.assertIn("create('Observation')", sm["_fml"])
        self.assertIn("main", strategy.fml_mappings)


class TestOpenSRPTargetStructureMap(unittest.TestCase):
    def test_questionnaire_gets_target_structuremap(self):
        from tricc_oo.strategies.output.opensrp import OpenSRPStrategy

        project = MagicMock()
        project.start_pages = {}
        project.pages = {}
        project.code_systems = {}
        strategy = OpenSRPStrategy(project, "/tmp/opensrp-sm-out")
        strategy._form_id = "demo"
        strategy.questionnaires["main"] = {
            "resourceType": "Questionnaire",
            "id": "q-main",
            "extension": [],
        }
        strategy.extraction_maps["main"] = {
            "id": "sm-extract",
            "url": "https://fhir.tricc.io/StructureMap/sm-extract",
        }
        pd = {"id": "pd-1"}
        strategy._wire_questionnaire_extensions("main", pd, "1.0.0")
        urls = [e.get("url") for e in strategy.questionnaires["main"]["extension"]]
        self.assertIn(SDC_EXT_TARGET_STRUCTUREMAP, urls)
        ext = next(
            e
            for e in strategy.questionnaires["main"]["extension"]
            if e["url"] == SDC_EXT_TARGET_STRUCTUREMAP
        )
        self.assertEqual(ext["valueCanonical"], "https://fhir.tricc.io/StructureMap/sm-extract")


if __name__ == "__main__":
    unittest.main()
