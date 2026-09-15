"""A FHIRPath suffix call must not bind to the last operand of its operand.

``Length(a & b)`` emitted as ``a & b.length()`` evaluates ``string & integer``,
which HAPI refuses ("right operand to & has the wrong type integer"). The
exception leaves ``initializeCalculatedExpressions`` and the whole Questionnaire
fails to render — that is what took cohort_fup down on the device as soon as any
answer existed. See fix/20260902-fhirpath-suffix-precedence.md.

Run with:
    python -m pytest tests/test_strategies/test_fhir_suffix_precedence.py -v
"""

import unittest
from unittest.mock import MagicMock

from tricc_oo.models.base import TriccOperation, TriccOperator, TriccReference
from tricc_oo.strategies.output.fhir_form import FHIRStrategy


def _make_strategy():
    project = MagicMock()
    project.start_pages = {}
    project.pages = {}
    project.code_systems = {}
    strategy = FHIRStrategy(project, "/tmp/fhir_suffix_precedence_out")
    strategy.questionnaires["main"] = {
        "resourceType": "Questionnaire",
        "item": [
            {"linkId": "s_one", "type": "string"},
            {"linkId": "s_two", "type": "string"},
            {"linkId": "num_a", "type": "decimal"},
            {"linkId": "num_b", "type": "decimal"},
        ],
    }
    return strategy


def _concat(*names):
    return TriccOperation(
        TriccOperator.CONCATENATE, [TriccReference(n) for n in names]
    )


class TestAtomHelper(unittest.TestCase):
    """R1 — only a composite operand gets parentheses."""

    def setUp(self):
        self.strategy = _make_strategy()

    def test_plain_path_is_left_alone(self):
        expr = "%resource.item.where(linkId='s_one').answer.value"
        self.assertEqual(self.strategy._fhirpath_atom(expr), expr)

    def test_already_parenthesised_is_left_alone(self):
        expr = "(a & b)"
        self.assertEqual(self.strategy._fhirpath_atom(expr), expr)

    def test_top_level_operator_gets_parentheses(self):
        self.assertEqual(self.strategy._fhirpath_atom("a & b"), "(a & b)")
        self.assertEqual(self.strategy._fhirpath_atom("a + b"), "(a + b)")
        self.assertEqual(self.strategy._fhirpath_atom("a and b"), "(a and b)")

    def test_operator_inside_a_call_or_string_does_not_count(self):
        # The '-' lives inside a quoted linkId, and the '=' inside where(...).
        expr = "%resource.item.where(linkId='a-b').answer.where($this.exists()).value"
        self.assertEqual(self.strategy._fhirpath_atom(expr), expr)
        self.assertEqual(self.strategy._fhirpath_atom("iif(a = b, 'x', 'y')"),
                         "iif(a = b, 'x', 'y')")


class TestLengthOverConcatenate(unittest.TestCase):
    """The shape that crashed cohort_fup."""

    def setUp(self):
        self.strategy = _make_strategy()

    def test_length_wraps_the_whole_concatenation(self):
        expr = self.strategy.convert_expression_to_fhirpath(
            TriccOperation(TriccOperator.LENGTH, [_concat("s_one", "s_two")])
        )
        self.assertTrue(expr.endswith(").select($this.length())"), expr)
        # The killer: the call must not sit directly after the second operand.
        self.assertNotIn(".toString().select($this.length())", expr)
        self.assertIn("&", expr)

    def test_length_of_a_plain_reference_gains_no_parentheses(self):
        expr = self.strategy.convert_expression_to_fhirpath(
            TriccOperation(TriccOperator.LENGTH, [TriccReference("s_one")])
        )
        self.assertTrue(expr.endswith(".value.select($this.length())"), expr)

    def test_round_of_arithmetic_wraps_the_arithmetic(self):
        expr = self.strategy.convert_expression_to_fhirpath(
            TriccOperation(
                TriccOperator.ROUND,
                [TriccOperation(TriccOperator.PLUS,
                                [TriccReference("num_a"), TriccReference("num_b")])],
            )
        )
        self.assertTrue(expr.endswith(").select($this.round())"), expr)
        self.assertNotIn(".toDecimal().select($this.round()) +", expr)

    def test_abs_of_arithmetic_wraps_the_arithmetic(self):
        expr = self.strategy.convert_expression_to_fhirpath(
            TriccOperation(
                TriccOperator.ABS,
                [TriccOperation(TriccOperator.MINUS,
                                [TriccReference("num_a"), TriccReference("num_b")])],
            )
        )
        self.assertTrue(expr.endswith(").select($this.abs())"), expr)

    def test_exists_over_a_composite_operand_is_parenthesised(self):
        expr = self.strategy.convert_expression_to_fhirpath(
            TriccOperation(TriccOperator.EXISTS, [_concat("s_one", "s_two")])
        )
        self.assertTrue(expr.endswith(").exists()"), expr)
        self.assertNotIn(".toString().exists()", expr)


class TestLengthOfConcatenationExport(unittest.TestCase):
    """End-to-end: the authored ``Length(Concatenate(a, b)) > 0`` guard."""

    @classmethod
    def setUpClass(cls):
        from tests.helpers import load_yaml_project

        project = load_yaml_project("tests/data/yaml/length_of_concatenation.yaml")
        strategy = FHIRStrategy(project, "/tmp/fhir_suffix_precedence_export_out")
        strategy.process_base(project.start_pages, pages=project.pages)
        strategy.process_relevance(project.start_pages, pages=project.pages)
        cls.questionnaire = strategy.questionnaires.get("main") or next(
            iter(strategy.questionnaires.values())
        )

    def _enable_when(self, link_id):
        def walk(items):
            for item in items or []:
                yield item
                yield from walk(item.get("item"))

        for item in walk(self.questionnaire.get("item")):
            if item.get("linkId") != link_id:
                continue
            for ext in item.get("extension") or []:
                if ext["url"].endswith("enableWhenExpression"):
                    return ext["valueExpression"]["expression"]
        return None

    def test_gate_expression_has_no_mis_bound_length(self):
        expr = self._enable_when("gated")
        self.assertIsNotNone(expr)
        self.assertIn(").select($this.length())", expr)
        self.assertNotIn(".toString().select($this.length())", expr)


if __name__ == "__main__":
    unittest.main()
