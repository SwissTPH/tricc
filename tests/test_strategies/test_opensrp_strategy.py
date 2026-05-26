"""
Unit tests for OpenSRPStrategy and supporting FHIR converter utilities.

Run with:
    python -m pytest tests/test_strategies/test_opensrp_strategy.py -v
"""

import json
import unittest
from unittest.mock import MagicMock, patch, PropertyMock


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
        self.assertIn("ValueSet: YesNo", fsh)
        self.assertIn("#active", fsh)
        self.assertIn('"yes" "Yes"', fsh)
        self.assertIn('"no" "No"', fsh)

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
                "python", "tests/build.py",
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

            # Validate that our new warnings for incomplete state appear (they are expected today)
            self.assertIn("No CQL libraries generated", combined_output)


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
        fhir_type, repeats, hidden = self.qim.get_fhir_item_type(TriccNodeType.select_one)
        self.assertEqual(fhir_type, "choice")
        self.assertFalse(repeats)

    def test_select_multiple_maps_to_choice_repeating(self):
        from tricc_oo.models.base import TriccNodeType
        fhir_type, repeats, hidden = self.qim.get_fhir_item_type(TriccNodeType.select_multiple)
        self.assertEqual(fhir_type, "choice")
        self.assertTrue(repeats)

    def test_integer_maps_to_integer(self):
        from tricc_oo.models.base import TriccNodeType
        fhir_type, repeats, hidden = self.qim.get_fhir_item_type(TriccNodeType.integer)
        self.assertEqual(fhir_type, "integer")

    def test_calculate_is_hidden(self):
        from tricc_oo.models.base import TriccNodeType
        _, _, hidden = self.qim.get_fhir_item_type(TriccNodeType.calculate)
        self.assertTrue(hidden)

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

    def test_generate_plandefinition_structure(self):
        from tricc_oo.strategies.output.opensrp import OpenSRPStrategy
        project = self._make_mock_project()
        strategy = OpenSRPStrategy(project, "/tmp/opensrp_test_out")
        pd = strategy.generate_plandefinition("registration", "1.0.0")
        self.assertEqual(pd["resourceType"], "PlanDefinition")
        self.assertEqual(pd["status"], "active")
        # Must have a named-event trigger for cpg-common-process
        triggers = pd.get("trigger", [])
        self.assertTrue(any(t.get("type") == "named-event" for t in triggers))
        trigger_names = [t.get("name", "") for t in triggers]
        self.assertTrue(any("registration" in n for n in trigger_names))

    def test_generate_composition_structure(self):
        from tricc_oo.strategies.output.opensrp import OpenSRPStrategy
        project = self._make_mock_project()
        strategy = OpenSRPStrategy(project, "/tmp/opensrp_test_out")
        comp = strategy.generate_composition("1.0.0")
        self.assertEqual(comp["resourceType"], "Composition")
        self.assertIn("section", comp)
        section_titles = [s.get("title", "") for s in comp["section"]]
        self.assertIn("Questionnaires", section_titles)
        self.assertIn("PlanDefinitions", section_titles)

    def test_generate_binary_config_structure(self):
        from tricc_oo.strategies.output.opensrp import OpenSRPStrategy
        import base64
        project = self._make_mock_project()
        strategy = OpenSRPStrategy(project, "/tmp/opensrp_test_out")
        binary = strategy.generate_binary_config("1.0.0")
        self.assertEqual(binary["resourceType"], "Binary")
        self.assertEqual(binary["contentType"], "application/json")
        # data must be valid base64 JSON
        decoded = base64.b64decode(binary["data"]).decode("utf-8")
        config = json.loads(decoded)
        self.assertIsInstance(config, dict)


if __name__ == "__main__":
    unittest.main()
