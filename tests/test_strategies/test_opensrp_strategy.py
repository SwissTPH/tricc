"""
Unit tests for OpenSRPStrategy and supporting FHIR converter utilities.

Run with:
    python -m pytest tests/test_strategies/test_opensrp_strategy.py -v
"""

import json
import unittest
from unittest.mock import MagicMock, patch, PropertyMock


# ---------------------------------------------------------------------------
# FHIR id sanitizer
# ---------------------------------------------------------------------------

class TestFhirIds(unittest.TestCase):
    def test_underscore_replaced(self):
        from tricc_oo.converters.fhir.ids import to_fhir_id, is_valid_fhir_id
        self.assertEqual(to_fhir_id("demo_tricc"), "demo-tricc")
        self.assertEqual(to_fhir_id("demo_tricc", "main", "PD"), "demo-tricc-main-PD")
        self.assertTrue(is_valid_fhir_id(to_fhir_id("demo_tricc-config")))
        self.assertFalse(is_valid_fhir_id("demo_tricc-config"))
        self.assertFalse(is_valid_fhir_id("fhir_formHelper"))

    def test_helper_id(self):
        from tricc_oo.converters.fhir.ids import to_fhir_id
        self.assertEqual(to_fhir_id("demo-tricc", "Helper"), "demo-tricc-Helper")

    def test_fhir_resource_id_is_stable_uuid(self):
        from tricc_oo.converters.fhir.ids import fhir_resource_id, is_uuid_id, is_valid_fhir_id
        a = fhir_resource_id("demo_tricc", "PlanDefinition", "main")
        b = fhir_resource_id("demo_tricc", "PlanDefinition", "main")
        c = fhir_resource_id("demo_tricc", "PlanDefinition", "triage")
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)
        self.assertTrue(is_uuid_id(a))
        self.assertTrue(is_valid_fhir_id(a))
        self.assertEqual(len(a), 36)


# ---------------------------------------------------------------------------
# FSH serializer tests (no TRICC model dependencies)
# ---------------------------------------------------------------------------

class TestFshSerializer(unittest.TestCase):
    """Tests for tricc_oo.converters.fhir.fsh_serializer.resource_to_fsh."""

    def setUp(self):
        from tricc_oo.converters.fhir.fsh_serializer import resource_to_fsh
        self.resource_to_fsh = resource_to_fsh

    def test_valueset_basic(self):
        vs = {
            "resourceType": "ValueSet",
            "id": "vs-yesno",
            "url": "http://example.org/ValueSet/vs-yesno",
            "version": "1.0.0",
            "name": "YesNo",
            "title": "Yes / No",
            "status": "active",
            "compose": {
                "include": [
                    {
                        "system": "http://example.org/CodeSystem/yesno",
                        "concept": [
                            {"code": "yes", "display": "Yes"},
                            {"code": "no", "display": "No"},
                        ],
                    }
                ]
            },
        }
        fsh = self.resource_to_fsh(vs)
        self.assertIn("ValueSet: vs-yesno", fsh)
        self.assertIn("^name = \"YesNo\"", fsh)
        self.assertIn("#active", fsh)
        self.assertIn('#yes "Yes"', fsh)
        self.assertIn('#no "No"', fsh)

    def test_library_basic(self):
        lib = {
            "resourceType": "Library",
            "id": "my-lib",
            "name": "MyLib",
            "status": "active",
            "type": {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/library-type",
                        "code": "logic-library",
                    }
                ]
            },
            "content": [
                {"contentType": "text/cql", "data": "bGlicmFyeSBNeUxpYg=="},
            ],
        }
        fsh = self.resource_to_fsh(lib)
        self.assertIn("Instance: my-lib", fsh)
        self.assertIn("InstanceOf: Library", fsh)
        self.assertIn("text/cql", fsh)

    def test_plandefinition_basic(self):
        pd = {
            "resourceType": "PlanDefinition",
            "id": "pd-registration",
            "name": "RegistrationPD",
            "status": "active",
            "type": {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/plan-definition-type",
                        "code": "eca-rule",
                    }
                ]
            },
            "trigger": [
                {"type": "named-event", "name": "cpg-common-process-registration"}
            ],
            "action": [
                {
                    "title": "Fill registration form",
                    "definitionCanonical": "http://example.org/Questionnaire/registration",
                    "condition": [
                        {
                            "kind": "applicability",
                            "expression": {
                                "language": "text/cql",
                                "expression": "Is Applicable",
                            },
                        }
                    ],
                }
            ],
        }
        fsh = self.resource_to_fsh(pd)
        self.assertIn("Instance: pd-registration", fsh)
        self.assertIn("named-event", fsh)
        self.assertIn("cpg-common-process-registration", fsh)
        self.assertIn("definitionCanonical", fsh)

    def test_composition_basic(self):
        comp = {
            "resourceType": "Composition",
            "id": "comp-demo",
            "title": "Demo Composition",
            "status": "active",
            "type": {
                "coding": [
                    {
                        "system": "http://fhir.org/guides/who/core/CodeSystem/composition-type",
                        "code": "component",
                    }
                ]
            },
            "section": [
                {
                    "title": "Questionnaires",
                    "entry": [
                        {"reference": "Questionnaire/registration"},
                    ],
                }
            ],
        }
        fsh = self.resource_to_fsh(comp)
        self.assertIn("Instance: comp-demo", fsh)
        self.assertIn("InstanceOf: Composition", fsh)
        self.assertIn("Questionnaires", fsh)
        self.assertIn("Questionnaire/registration", fsh)

    def test_binary_basic(self):
        binary = {
            "resourceType": "Binary",
            "id": "bin-config",
            "contentType": "application/json",
            "data": "e30=",
        }
        fsh = self.resource_to_fsh(binary)
        self.assertIn("Instance: bin-config", fsh)
        self.assertIn("application/json", fsh)
        self.assertIn("e30=", fsh)

    def test_generic_fallback(self):
        """Unknown resource types should use the generic fallback."""
        unknown = {
            "resourceType": "UnknownResource",
            "id": "unknown-1",
            "status": "active",
        }
        fsh = self.resource_to_fsh(unknown)
        self.assertIn("Instance: unknown-1", fsh)
        self.assertIn("InstanceOf: UnknownResource", fsh)

    def test_safe_name_special_chars(self):
        """IDs with special characters should produce valid FSH identifiers."""
        from tricc_oo.converters.fhir.fsh_serializer import _safe_name
        self.assertEqual(_safe_name("my form id"), "my_form_id")
        self.assertEqual(_safe_name("123abc"), "R_123abc")


# ---------------------------------------------------------------------------
# Phase 0 smoke test: full pipeline execution for FHIRStrategy + OpenSRPStrategy
# (added as part of FHIR output strategy hardening)
# These tests deliberately use the build harness (like launch.json) for realism.
# ---------------------------------------------------------------------------

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class TestFHIRPipelineSmoke(unittest.TestCase):
    """Smoke tests that the (currently partial) FHIR pipeline runs end-to-end
    on a real demo graph without crashing (using the same entrypoint as users).
    """

    def test_demo_fhir_build_via_build_script_produces_questionnaire_and_logs(self):
        """Run exactly like the 'DEMO FHIR' launch.json config (simplified)."""
        input_file = "tests/data/demo.drawio"
        self.assertTrue(Path(input_file).exists())

        with tempfile.TemporaryDirectory() as tmpdir:
            cmd = [
                sys.executable, "tests/build.py",
                "-i", input_file,
                "-l", "i",   # info level to keep output readable
                "-o", tmpdir,
                "-t",
                "-O", "FHIRStrategy",
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
                env={**os.environ, "PYTHONPATH": "."},
            )

            # The build should succeed (exit 0) even if the strategy is partial
            self.assertEqual(result.returncode, 0, f"build.py failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}")

            # Look for the output directory created by the strategy (form_id based)
            out_path = Path(tmpdir)
            json_files = list(out_path.rglob("*.json"))
            map_files = list(out_path.rglob("*.map"))

            self.assertTrue(any("main.json" in str(p) or "questionnaire" in str(p).lower() for p in json_files),
                            "Expected at least one Questionnaire JSON to be written")

            # The improved logging from Phase 0 should be visible
            combined_output = result.stdout + result.stderr
            self.assertIn("FHIRStrategy complete:", combined_output)
            self.assertIn("questionnaires=", combined_output)

            self.assertIn("cql_libraries=", combined_output)


# ---------------------------------------------------------------------------
# Concept mapper tests
# ---------------------------------------------------------------------------

class TestConceptMapper(unittest.TestCase):
    """Tests for tricc_oo.converters.fhir.concept_mapper."""

    def setUp(self):
        from tricc_oo.converters.fhir import concept_mapper as cm
        self.cm = cm

    def test_diagnosis_maps_to_condition(self):
        from tricc_oo.models.base import TriccNodeType
        resource, profile, field = self.cm.get_fhir_resource("diagnosis", TriccNodeType.diagnosis)
        self.assertEqual(resource, "Condition")

    def test_proposed_diagnosis_maps_to_condition(self):
        from tricc_oo.models.base import TriccNodeType
        resource, profile, field = self.cm.get_fhir_resource("diagnosis", TriccNodeType.proposed_diagnosis)
        self.assertEqual(resource, "Condition")

    def test_codesystem_symptom_finding_maps_to_observation(self):
        resource, profile, field = self.cm.get_fhir_resource("Symptom-Finding")
        self.assertEqual(resource, "Observation")

    def test_codesystem_question_maps_to_observation(self):
        resource, _, _ = self.cm.get_fhir_resource("Question")
        self.assertEqual(resource, "Observation")

    def test_integer_value_field(self):
        field = self.cm.get_fhir_value_field("integer")
        self.assertEqual(field, "valueInteger")

    def test_boolean_value_field(self):
        field = self.cm.get_fhir_value_field("boolean")
        self.assertEqual(field, "valueBoolean")

    def test_unknown_value_field_defaults_to_string(self):
        field = self.cm.get_fhir_value_field("unknown_type")
        self.assertEqual(field, "valueString")


# ---------------------------------------------------------------------------
# Questionnaire item mapper tests
# ---------------------------------------------------------------------------

class TestQuestionnaireItemMapper(unittest.TestCase):
    """Tests for tricc_oo.converters.fhir.questionnaire_item_mapper."""

    def setUp(self):
        from tricc_oo.converters.fhir import questionnaire_item_mapper as qim
        self.qim = qim

    def test_select_one_maps_to_choice(self):
        from tricc_oo.models.base import TriccNodeType
        fhir_type = self.qim.get_fhir_item_type(TriccNodeType.select_one)
        self.assertEqual(fhir_type, "choice")
        self.assertFalse(self.qim.is_repeating(TriccNodeType.select_one))

    def test_select_multiple_maps_to_choice_repeating(self):
        from tricc_oo.models.base import TriccNodeType
        fhir_type = self.qim.get_fhir_item_type(TriccNodeType.select_multiple)
        self.assertEqual(fhir_type, "choice")
        self.assertTrue(self.qim.is_repeating(TriccNodeType.select_multiple))

    def test_integer_maps_to_integer(self):
        from tricc_oo.models.base import TriccNodeType
        fhir_type = self.qim.get_fhir_item_type(TriccNodeType.integer)
        self.assertEqual(fhir_type, "integer")

    def test_calculate_is_hidden(self):
        from tricc_oo.models.base import TriccNodeType
        self.assertTrue(self.qim.is_hidden(TriccNodeType.calculate))

    def test_page_should_skip(self):
        from tricc_oo.models.base import TriccNodeType
        self.assertTrue(self.qim.should_skip(TriccNodeType.page))

    def test_note_should_not_skip(self):
        from tricc_oo.models.base import TriccNodeType
        self.assertFalse(self.qim.should_skip(TriccNodeType.note))

    def test_calculate_is_calculate_type(self):
        from tricc_oo.models.base import TriccNodeType
        self.assertTrue(self.qim.is_calculate_type(TriccNodeType.calculate))

    def test_select_one_is_not_calculate_type(self):
        from tricc_oo.models.base import TriccNodeType
        self.assertFalse(self.qim.is_calculate_type(TriccNodeType.select_one))


# ---------------------------------------------------------------------------
# get_process visitor tests
# ---------------------------------------------------------------------------

class TestGetProcess(unittest.TestCase):
    """Tests for tricc_oo.visitors.tricc.get_process."""

    def setUp(self):
        from tricc_oo.visitors.tricc import get_process
        self.get_process = get_process

    def test_none_returns_none(self):
        self.assertIsNone(self.get_process(None))

    def test_main_start_returns_process(self):
        from tricc_oo.models.tricc import TriccNodeMainStart
        node = MagicMock(spec=TriccNodeMainStart)
        node.process = "registration"
        # Make isinstance check work
        with patch("tricc_oo.visitors.tricc.isinstance", side_effect=lambda obj, cls: cls is TriccNodeMainStart):
            result = self.get_process(node)
        self.assertEqual(result, "registration")

    def test_node_with_no_activity_returns_none(self):
        node = MagicMock()
        node.activity = None
        node.prev_nodes = []
        # Not a TriccNodeMainStart
        from tricc_oo.models.tricc import TriccNodeMainStart
        self.assertNotIsInstance(node, TriccNodeMainStart)
        result = self.get_process(node)
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# OpenSRPStrategy unit tests (mocked project)
# ---------------------------------------------------------------------------

class TestOpenSRPStrategyInit(unittest.TestCase):
    """Smoke tests for OpenSRPStrategy instantiation."""

    def _make_mock_project(self):
        """Build a minimal mock TriccProject."""
        project = MagicMock()
        project.nodes = {}
        project.edges = {}
        project.form_id = "demo"
        project.version = "1.0.0"
        return project

    def test_instantiation(self):
        from tricc_oo.strategies.output.opensrp import OpenSRPStrategy
        project = self._make_mock_project()
        strategy = OpenSRPStrategy(project, "/tmp/opensrp_test_out")
        self.assertIsNotNone(strategy)
        self.assertIsInstance(strategy.plan_definitions, dict)

    def test_generate_intervention_plandefinition_structure(self):
        from tricc_oo.strategies.output.opensrp import OpenSRPStrategy
        from tricc_oo.converters.fhir.related_person import AVAILABLE_CARE_NAMED_EVENT
        from tricc_oo.visitors.utils import PROCESS_ORDER
        project = self._make_mock_project()
        strategy = OpenSRPStrategy(project, "/tmp/opensrp_test_out")
        strategy._form_id = "demo"
        strategy.questionnaires = {
            "registration": {
                "id": "questionnaire-registration",
                "title": "Registration",
                "item": [{"linkId": "a", "type": "boolean"}],
            }
        }
        strategy.process_chain = ["registration"]
        pd = strategy.generate_intervention_plandefinition("1.0.0")
        self.assertEqual(pd["resourceType"], "PlanDefinition")
        self.assertEqual(pd["status"], "active")
        self.assertFalse(pd.get("experimental", True))
        # Single wrapper action carries available-care once, "at the PD level"
        top_actions = pd.get("action", [])
        self.assertEqual(len(top_actions), 1)
        wrapper = top_actions[0]
        wrapper_trigger_names = [t.get("name", "") for t in wrapper.get("trigger", [])]
        self.assertEqual(wrapper_trigger_names, [AVAILABLE_CARE_NAMED_EVENT])
        # 1 process = 1 nested child action = 1 Questionnaire
        actions = wrapper.get("action", [])
        self.assertEqual(len(actions), 1)
        triggers = actions[0].get("trigger", [])
        self.assertTrue(any(t.get("type") == "named-event" for t in triggers))
        trigger_names = [t.get("name", "") for t in triggers]
        self.assertTrue(any("registration" in n for n in trigger_names))
        # available-care no longer repeats on the child action (moved to the wrapper)
        self.assertNotIn(AVAILABLE_CARE_NAMED_EVENT, trigger_names)
        # tricc-process / tricc-process-order extensions on the child action
        extensions = {e["url"]: e for e in actions[0].get("extension", [])}
        self.assertTrue(any(u.endswith("tricc-process") for u in extensions))
        self.assertTrue(any(u.endswith("tricc-process-order") for u in extensions))
        order_ext = next(e for u, e in extensions.items() if u.endswith("tricc-process-order"))
        self.assertEqual(order_ext["valueInteger"], PROCESS_ORDER["registration"])
        process_ext = next(e for u, e in extensions.items() if u.endswith("tricc-process"))
        self.assertEqual(process_ext["valueString"], "registration")
        # openSRP Start care: definitionCanonical → Questionnaire (direct launch)
        from tricc_oo.converters.fhir.ids import is_uuid_id
        def_can = actions[0].get("definitionCanonical", "")
        self.assertIn("Questionnaire/", def_can, def_can)
        self.assertFalse(def_can.startswith("#"), def_can)
        self.assertIsNone(actions[0].get("transform"))
        self.assertTrue(is_uuid_id(pd["id"]), pd["id"])
        self.assertFalse(pd.get("contained") or [])

    def test_generate_intervention_plandefinition_multi_process(self):
        from tricc_oo.strategies.output.opensrp import OpenSRPStrategy
        project = self._make_mock_project()
        strategy = OpenSRPStrategy(project, "/tmp/opensrp_test_out")
        strategy._form_id = "demo"
        strategy.questionnaires = {
            "registration": {
                "id": "demo-registration",
                "title": "Registration",
                "item": [{"linkId": "x", "type": "boolean"}],
            },
            "triage": {
                "id": "demo-triage",
                "title": "Triage",
                "item": [{"linkId": "y", "type": "boolean"}],
            },
        }
        strategy.process_chain = ["registration", "triage"]
        pd = strategy.generate_intervention_plandefinition("1.0.0")
        # One nested child action per process, in graph discovery order
        actions = pd["action"][0]["action"]
        self.assertEqual(len(actions), 2)
        for action, process in zip(actions, ["registration", "triage"]):
            def_can = action.get("definitionCanonical", "")
            self.assertIn(f"demo-{process}", def_can, def_can)

    def test_generate_intervention_plandefinition_unknown_process_order(self):
        from tricc_oo.strategies.output.opensrp import OpenSRPStrategy
        from tricc_oo.visitors.utils import PROCESS_ORDER
        project = self._make_mock_project()
        strategy = OpenSRPStrategy(project, "/tmp/opensrp_test_out")
        strategy._form_id = "demo"
        strategy.questionnaires = {
            "registration": {
                "id": "demo-registration",
                "item": [{"linkId": "x", "type": "boolean"}],
            },
            "custom-process": {
                "id": "demo-custom-process",
                "item": [{"linkId": "y", "type": "boolean"}],
            },
        }
        strategy.process_chain = ["registration", "custom-process"]
        pd = strategy.generate_intervention_plandefinition("1.0.0")
        actions = pd["action"][0]["action"]
        orders = {}
        for action in actions:
            proc = next(
                e["valueString"] for e in action["extension"] if e["url"].endswith("tricc-process")
            )
            orders[proc] = next(
                e["valueInteger"] for e in action["extension"] if e["url"].endswith("tricc-process-order")
            )
        self.assertEqual(orders["registration"], PROCESS_ORDER["registration"])
        # unrecognized process name gets the next free slot after the highest known order
        self.assertEqual(orders["custom-process"], max(PROCESS_ORDER.values()) + 10)

    def test_prune_empty_questionnaires(self):
        from tricc_oo.strategies.output.opensrp import OpenSRPStrategy
        project = self._make_mock_project()
        strategy = OpenSRPStrategy(project, "/tmp/opensrp_test_out")
        strategy._form_id = "demo"
        strategy.questionnaires = {
            "registration": {
                "id": "q-reg",
                "item": [],
            },
            "main": {
                "id": "q-main",
                "item": [{"linkId": "happy", "type": "boolean"}],
            },
        }
        strategy.cql_defines = {"registration": ["define X: true"], "main": ["define Y: true"]}
        strategy._prune_empty_questionnaires()
        self.assertNotIn("registration", strategy.questionnaires)
        self.assertIn("main", strategy.questionnaires)
        self.assertNotIn("registration", strategy.cql_defines)

    def test_task_structuremap_chains_next_process(self):
        from tricc_oo.strategies.output.opensrp import OpenSRPStrategy
        project = self._make_mock_project()
        strategy = OpenSRPStrategy(project, "/tmp/opensrp_test_out")
        strategy._form_id = "demo"
        strategy.questionnaires = {
            "registration": {
                "id": "questionnaire-registration",
                "item": [{"linkId": "a", "type": "string"}],
            },
            "main": {
                "id": "questionnaire-main",
                "item": [{"linkId": "b", "type": "boolean"}],
            },
        }
        # Graph discovery order (not hardcoded CPG list)
        strategy.process_chain = ["registration", "main"]
        sm = strategy.generate_task_structuremap("registration", "1.0.0")
        self.assertIsNotNone(sm)
        self.assertEqual(sm["resourceType"], "StructureMap")
        group_names = [g.get("name") for g in sm.get("group", [])]
        self.assertIn("extractThisTask", group_names)
        self.assertIn("extractNextTaskOnDone", group_names)
        # reasonReference targets
        this_rules = sm["group"][0]["rule"][0]["target"][0]["parameter"][0]["valueId"]
        self.assertEqual(this_rules, "Questionnaire/questionnaire-registration")
        next_rules = sm["group"][1]["rule"][0]["target"][0]["parameter"][0]["valueId"]
        self.assertEqual(next_rules, "Questionnaire/questionnaire-main")
        # last process has no next Task group
        sm_last = strategy.generate_task_structuremap("main", "1.0.0")
        last_groups = [g.get("name") for g in sm_last.get("group", [])]
        self.assertIn("extractThisTask", last_groups)
        self.assertNotIn("extractNextTaskOnDone", last_groups)

    def test_is_questionnaire_empty(self):
        from tricc_oo.strategies.output.opensrp import OpenSRPStrategy
        self.assertTrue(OpenSRPStrategy.is_questionnaire_empty(None))
        self.assertTrue(OpenSRPStrategy.is_questionnaire_empty({"item": []}))
        self.assertTrue(OpenSRPStrategy.is_questionnaire_empty({}))
        self.assertFalse(
            OpenSRPStrategy.is_questionnaire_empty(
                {"item": [{"linkId": "x", "type": "boolean"}]}
            )
        )

    def test_generate_composition_structure(self):
        from tricc_oo.strategies.output.opensrp import OpenSRPStrategy
        project = self._make_mock_project()
        strategy = OpenSRPStrategy(project, "/tmp/opensrp_test_out")
        strategy._form_id = "demo"
        strategy.questionnaires = {}
        strategy.plan_definitions = {}
        strategy.structuremaps = {}
        strategy.valuesets = {}
        strategy.binaries = []
        comp = strategy.generate_composition("1.0.0")
        self.assertEqual(comp["resourceType"], "Composition")
        self.assertIn("section", comp)
        section_titles = [s.get("title", "") for s in comp["section"]]
        self.assertIn("Libraries", section_titles)

    def test_stamp_package_app_id_tags_includes_image_binaries(self):
        from tricc_oo.strategies.output.opensrp import (
            APP_ID_TAG_SYSTEM,
            DEFAULT_OPENSRP_APP_ID,
            OpenSRPStrategy,
        )

        project = self._make_mock_project()
        strategy = OpenSRPStrategy(project, "/tmp/opensrp_test_out")
        strategy.binaries = [
            {
                "resourceType": "Binary",
                "id": "img-1",
                "contentType": "image/png",
                "data": "aGVsbG8=",
            }
        ]
        strategy._stamp_package_app_id_tags()
        tags = strategy.binaries[0]["meta"]["tag"]
        self.assertTrue(
            any(
                t.get("system") == APP_ID_TAG_SYSTEM
                and t.get("code") == DEFAULT_OPENSRP_APP_ID
                for t in tags
            ),
            tags,
        )


# ---------------------------------------------------------------------------
# RelatedPerson contract helpers
# ---------------------------------------------------------------------------


class TestRelatedPersonContract(unittest.TestCase):
    def test_build_related_person_patient_is_child(self):
        from tricc_oo.converters.fhir.related_person import build_related_person

        rp = build_related_person(
            child_patient_id_or_ref="jean",
            guardian_patient_id_or_ref="marie",
            role="mother",
            related_person_id="rp-1",
            guardian_display_name="Marie",
        )
        self.assertEqual(rp["resourceType"], "RelatedPerson")
        self.assertEqual(rp["patient"]["reference"], "Patient/jean")
        self.assertEqual(rp["relationship"][0]["coding"][0]["code"], "MTH")
        ident = rp["identifier"][0]
        self.assertEqual(ident["use"], "secondary")
        self.assertEqual(ident["type"]["coding"][0]["code"], "PI")
        self.assertEqual(ident["system"], "urn:ietf:rfc:3986")
        self.assertEqual(ident["value"], "Patient/marie")

    def test_guardian_role_uses_guard(self):
        from tricc_oo.converters.fhir.related_person import build_related_person

        rp = build_related_person(
            child_patient_id_or_ref="Patient/c1",
            guardian_patient_id_or_ref="Patient/g1",
            role="guardian",
        )
        self.assertEqual(rp["relationship"][0]["coding"][0]["code"], "GUARD")

    def test_unknown_role_raises(self):
        from tricc_oo.converters.fhir.related_person import relationship_coding

        with self.assertRaises(ValueError):
            relationship_coding("cousin")


if __name__ == "__main__":
    unittest.main()
