"""
CQL initialExpression export that evaluates on device (fhircore / cql-to-elm 3.12).

See fix/20260929-cql-initial-expression-on-device.md and
feature/20260929-cql-populate-wiring.md.

Run with:
    python -m pytest tests/test_cql_initial_expression.py -v
"""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from tricc_oo.converters.fhir.cql_value import (
    cql_helper_value_block,
    is_observation_value_accessor,
    wrap_cql_for_item_type,
)
from tricc_oo.converters.fhir.populate_helper import cql_helper_populate_block
from tricc_oo.converters.fhir.repeat_helper import cql_helper_repeat_block
from tricc_oo.strategies.output.fhir_form import CQL_HELPER_TEMPLATE, FHIR_VERSION, SDC_EXT_INITIAL_EXPR


def _make_strategy(cls_name: str = "OpenSRPStrategy"):
    if cls_name == "OpenSRPStrategy":
        from tricc_oo.strategies.output.opensrp import OpenSRPStrategy as cls
    else:
        from tricc_oo.strategies.output.fhir_form import FHIRStrategy as cls
    project = MagicMock()
    project.nodes = {}
    project.edges = {}
    project.form_id = "demo"
    project.version = "1.0.0"
    project.intervention = None
    strategy = cls(project, tempfile.mkdtemp())
    strategy._form_id = "demo"
    return strategy


def _helper_cql(library_id: str = "demo-Helper") -> str:
    return CQL_HELPER_TEMPLATE.format(
        library_id=library_id,
        fhir_version=FHIR_VERSION,
        repeat_helpers=cql_helper_repeat_block(FHIR_VERSION),
        populate_helpers=cql_helper_populate_block(),
        value_helpers=cql_helper_value_block(),
    )


def _initial_expression(item: dict):
    for ext in item.get("extension") or []:
        if ext.get("url") == SDC_EXT_INITIAL_EXPR:
            return ext["valueExpression"]["expression"]
    return None


class TestHelperIsValidCql(unittest.TestCase):
    """Constructs cql-to-elm 3.12 rejects must not be generated (fix §2)."""

    def setUp(self):
        self.helper = _helper_cql()

    def test_no_invalid_constructs(self):
        for bad in (
            "GetObservations(code) O",
            "GetConditions(code) C",
            "GetActiveConditions(code) C",
            ".where(url",
            "\n      skip ",
            "\n      take ",
            "sort by effective desc",
            "sort by recordedDate desc",
            "exists(GetHistoryCondition",
        ):
            with self.subTest(construct=bad):
                self.assertNotIn(bad, self.helper)

    def test_value_conversion_functions_defined(self):
        for func in ("ValueAsString", "ValueAsDecimal", "ValueAsInteger", "ValueAsBoolean", "ValueAsDate",
                     "ValueAsCoding"):
            with self.subTest(func=func):
                self.assertIn(f"define function {func}(v Choice<", self.helper)


class TestWrapForItemType(unittest.TestCase):
    """Every initialExpression define returns its item's type (fix §4)."""

    def test_accessor_detection(self):
        self.assertTrue(is_observation_value_accessor("Helper.GetObservationValue('w')"))
        self.assertTrue(is_observation_value_accessor("Helper.GetHistoryObservationValue('w', 'P1Y', 1, null)"))
        self.assertTrue(is_observation_value_accessor(
            "Helper.GetHistoryObservationValueSince('weight_c', Now() - 3 months, 1, null)"
        ))
        self.assertFalse(is_observation_value_accessor(
            "Helper.GetObservationValue('a') + Helper.GetObservationValue('b')"
        ))
        self.assertFalse(is_observation_value_accessor("Helper.GetConditionValue('d')"))
        self.assertFalse(is_observation_value_accessor("Today()"))

    def test_accessor_uses_value_function_for_item_type(self):
        accessor = "Helper.GetObservationValue('weight_c')"
        cases = {
            "string": "Helper.ValueAsString",
            "decimal": "Helper.ValueAsDecimal",
            "integer": "Helper.ValueAsInteger",
            "boolean": "Helper.ValueAsBoolean",
            "date": "Helper.ValueAsDate",
            "choice": "Helper.ValueAsCoding",
        }
        for item_type, func in cases.items():
            with self.subTest(item_type=item_type):
                self.assertEqual(wrap_cql_for_item_type(accessor, item_type), f"{func}({accessor})")

    def test_known_non_text_types_become_strings(self):
        self.assertEqual(wrap_cql_for_item_type("Today()", "string", source_type="date"), "ToString(Today())")
        self.assertEqual(wrap_cql_for_item_type("true", "string", source_type="boolean"), "ToString(true)")

    def test_unknown_type_left_alone(self):
        # CQL has no ToString(String): an expression that may already be text stays as is
        self.assertEqual(wrap_cql_for_item_type("'a' + 'b'", "string"), "'a' + 'b'")

    def test_integer_into_decimal(self):
        self.assertEqual(wrap_cql_for_item_type("1 + 2", "decimal", source_type="integer"), "ToDecimal(1 + 2)")
        self.assertEqual(wrap_cql_for_item_type("1.5 + 2", "decimal", source_type="decimal"), "1.5 + 2")


class TestAttachInitialExpression(unittest.TestCase):
    def setUp(self):
        self.strategy = _make_strategy("FHIRStrategy")

    def test_populate_on_string_item_is_converted(self):
        item = {"linkId": "load_w", "type": "string"}
        attached = self.strategy._attach_cql_initial_expression(
            "registration", item, "Calc_load_w", "Helper.GetHistoryObservationValue('weight_c', 'P1Y', 1, null)"
        )
        self.assertTrue(attached)
        self.assertEqual(_initial_expression(item), "Calc_load_w")
        self.assertIn(
            "define Calc_load_w: Helper.ValueAsString(Helper.GetHistoryObservationValue('weight_c', 'P1Y', 1, null))",
            self.strategy.cql_defines["registration"],
        )

    def test_no_cql_initial_expression_on_answer_option_items(self):
        item = {"linkId": "smoke", "type": "choice", "answerOption": [{"valueCoding": {"code": "never"}}]}
        attached = self.strategy._attach_cql_initial_expression(
            "registration", item, "Dedup_smoke", "Helper.GetObservationValue('smoke')"
        )
        self.assertFalse(attached)
        self.assertIsNone(_initial_expression(item))
        # still recorded (unconverted) so another define may reference it
        self.assertIn("define Dedup_smoke: Helper.GetObservationValue('smoke')",
                      self.strategy.cql_defines["registration"])

    def test_undefined_initial_expression_removed(self):
        item = {"linkId": "x", "type": "string", "extension": [{
            "url": SDC_EXT_INITIAL_EXPR,
            "valueExpression": {"language": "text/cql-identifier", "expression": "Calc_missing"},
        }]}
        kept = {"linkId": "y", "type": "string"}
        self.strategy.questionnaires = {"registration": {"item": [item, kept]}}
        self.strategy._attach_cql_initial_expression("registration", kept, "Calc_y", "'y'")
        self.strategy._drop_undefined_cql_initial_expressions()
        self.assertIsNone(_initial_expression(item))
        self.assertEqual(_initial_expression(kept), "Calc_y")

    def test_orphan_pruning_keeps_referenced_defines(self):
        self.strategy.cql_defines = {"registration": [
            "define Calc_a: Today()",
            "define Calc_b: ToString(Calc_a)",
            "define Calc_unused: 1",
        ]}
        items = [{"linkId": "b", "type": "string", "extension": [{
            "url": SDC_EXT_INITIAL_EXPR,
            "valueExpression": {"language": "text/cql-identifier", "expression": "Calc_b"},
        }]}]
        self.strategy._drop_orphan_cql_defines("registration", items)
        self.assertEqual(
            self.strategy.cql_defines["registration"],
            ["define Calc_a: Today()", "define Calc_b: ToString(Calc_a)"],
        )


class TestLibraryWiring(unittest.TestCase):
    """Library canonical, depends-on, encounterid and cqf-library (fix §1, feature §1-3)."""

    def test_library_url_ends_in_cql_name(self):
        strategy = _make_strategy("FHIRStrategy")
        lib = strategy._make_library_resource(
            "6dc3a855-2431-55c3-92a9-e3398a2ee830", "library x", "demo", name="demo-registration",
            depends_on=["https://fhir.tricc.io/Library/demo-Helper"],
        )
        self.assertEqual(lib["id"], "6dc3a855-2431-55c3-92a9-e3398a2ee830")
        self.assertTrue(lib["url"].endswith("/Library/demo-registration"))
        self.assertEqual(lib["relatedArtifact"],
                         [{"type": "depends-on", "resource": "https://fhir.tricc.io/Library/demo-Helper"}])
        self.assertEqual(lib["parameter"][0]["name"], "encounterid")
        self.assertEqual(lib["parameter"][0]["use"], "in")

    def test_cqf_library_only_with_library_and_cql_items(self):
        from tricc_oo.strategies.output.opensrp import CQF_EXT_LIBRARY, FHIRCORE_EXT_CQL_INPUT
        strategy = _make_strategy()
        cql_item = {"linkId": "a", "type": "string", "extension": [{
            "url": SDC_EXT_INITIAL_EXPR,
            "valueExpression": {"language": "text/cql-identifier", "expression": "Calc_a"},
        }]}
        strategy.questionnaires = {
            "registration": {"id": "q-reg", "item": [{"linkId": "g", "type": "group", "item": [cql_item]}]},
            "triage": {"id": "q-tri", "item": [{"linkId": "b", "type": "string"}]},
            "main": {"id": "q-main", "item": [cql_item]},
        }
        lib_url = "https://fhir.tricc.io/Library/demo-registration"
        strategy.libraries = {
            "registration": {"id": "lib-reg", "url": lib_url},
            "triage": {"id": "lib-tri", "url": "https://fhir.tricc.io/Library/demo-triage"},
        }
        for process in ("registration", "triage", "main"):
            strategy._wire_questionnaire_extensions(process, {"id": "pd-1"}, "1.0.0")

        def ext(process, url):
            return [e for e in strategy.questionnaires[process].get("extension", []) if e["url"] == url]

        self.assertEqual(ext("registration", CQF_EXT_LIBRARY), [{"url": CQF_EXT_LIBRARY, "valueCanonical": lib_url}])
        self.assertEqual(ext("registration", FHIRCORE_EXT_CQL_INPUT)[0]["valueReference"]["reference"], lib_url)
        self.assertEqual(ext("triage", CQF_EXT_LIBRARY), [])  # no CQL expression on the form
        self.assertEqual(ext("main", CQF_EXT_LIBRARY), [])  # no generated Library


_TRANSLATOR_CP = os.environ.get("TRICC_CQL_TRANSLATOR_CP")


@unittest.skipUnless(_TRANSLATOR_CP and shutil.which("java"), "set TRICC_CQL_TRANSLATOR_CP to a cql-to-elm classpath")
class TestHelperCompiles(unittest.TestCase):
    """Generated Helper compiles with zero errors (fix acceptance criterion 2).

    TRICC_CQL_TRANSLATOR_CP is a classpath holding cql-to-elm, quick (FHIRHelpers) and
    their dependencies, e.g. from the Gradle cache of a fhircore build (3.12.0).
    """

    def test_helper_translates_without_errors(self):
        runner = Path(__file__).parent / "tools" / "CqlCompile.java"
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "demo-Helper-1.0.0.cql"
            source.write_text(_helper_cql(), encoding="utf-8")
            result = subprocess.run(
                ["java", "-cp", _TRANSLATOR_CP, str(runner), tmp, str(source)],
                capture_output=True, text=True, timeout=300,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(": 0 error(s)", result.stdout, result.stdout)


if __name__ == "__main__":
    unittest.main()
