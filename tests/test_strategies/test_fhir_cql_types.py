"""Regression tests for FHIR output typing bugs found on the global Almanach child package.

* ``ToBoolean(Calc_X)`` on a calculate whose define is Boolean (CQL has no
  ``ToBoolean(Boolean)``: the whole library failed to translate).
* A Boolean calculate written ``coalesce(get_inherited_value(<rule>),
  get_inherited_value(<itself>))`` kept item type ``string``, so a Boolean
  initialExpression landed on a string item (renderers reject the response).
* ``zscore(...)`` reaches the FHIR output as a ``native`` call: its item stayed
  ``string``, CQL compared ``ValueAsString(WFA) < -3``, and FHIRPath set the text
  ``'Zscore'`` as the value.
* Display text injecting one value twice wrapped it twice
  (``….value.where($this.exists()).value``, always empty).

Run with:
    python -m pytest tests/test_strategies/test_fhir_cql_types.py -v
"""

import unittest
from unittest.mock import MagicMock

from tricc_oo.models.base import TriccOperation, TriccOperator, TriccReference, TriccStatic
from tricc_oo.models.calculate import TriccNodeCalculate
from tricc_oo.strategies.output.fhir_form import FHIRStrategy


def _make_strategy():
    project = MagicMock()
    project.start_pages = {}
    project.pages = {}
    project.code_systems = {}
    return FHIRStrategy(project, "/tmp/fhir_cql_types_test_out")


def _boolean_calculate_with_fallback(name: str) -> TriccNodeCalculate:
    """``coalesce(get_inherited_value(a is true and b is true), get_inherited_value(<itself>))``."""
    calc = TriccNodeCalculate(id=name, name=name, export_name=name)
    rule = TriccOperation(
        TriccOperator.AND,
        [
            TriccOperation(TriccOperator.ISTRUE, [TriccReference("a")]),
            TriccOperation(TriccOperator.ISTRUE, [TriccReference("b")]),
        ],
    )
    calc.expression = TriccOperation(
        TriccOperator.COALESCE,
        [
            TriccOperation(TriccOperator.GET_INHERITED_VALUE, [rule]),
            TriccOperation(TriccOperator.GET_INHERITED_VALUE, [calc]),
        ],
    )
    return calc


class TestBooleanCalculate(unittest.TestCase):
    def setUp(self):
        self.strategy = _make_strategy()
        self.calc = _boolean_calculate_with_fallback("danger")
        # The calculate's item is still the default hidden string item
        self.strategy._find_item_anywhere = lambda link_id: {"linkId": link_id, "type": "string"}

    def test_coalesce_with_self_fallback_returns_boolean(self):
        self.assertTrue(self.strategy._expression_returns_boolean(self.calc))

    def test_calculate_item_becomes_boolean(self):
        item = {"linkId": "danger", "type": "string"}
        self.strategy._apply_calculate_item_type(item, self.calc.expression)
        self.assertEqual(item["type"], "boolean")

    def test_no_toboolean_on_boolean_calc_define(self):
        operand = self.strategy._cql_boolean_operand(["Calc_danger"], [self.calc])
        self.assertEqual(operand, "Calc_danger")

    def test_text_value_still_converted(self):
        text_calc = TriccNodeCalculate(id="label", name="label", export_name="label")
        text_calc.expression = TriccOperation(
            TriccOperator.COALESCE, [TriccStatic("yes"), TriccOperation(TriccOperator.GET_INHERITED_VALUE, [text_calc])]
        )
        accessor = "Helper.ValueAsString(Helper.GetObservationValue('label'))"
        self.assertEqual(
            self.strategy._cql_boolean_operand([accessor], [text_calc]), f"ToBoolean({accessor})"
        )

    def test_coalesce_with_a_number_is_not_boolean(self):
        expr = TriccOperation(
            TriccOperator.COALESCE,
            [TriccOperation(TriccOperator.ISTRUE, [TriccReference("a")]), TriccStatic(0)],
        )
        self.assertFalse(self.strategy._expression_returns_boolean(expr))


class TestNativeZscore(unittest.TestCase):
    def setUp(self):
        self.strategy = _make_strategy()
        self.zscore = TriccOperation(
            TriccOperator.NATIVE, ["Zscore", TriccStatic("wfa"), TriccReference("sex"), TriccReference("weight")]
        )

    def test_zscore_is_decimal(self):
        self.assertEqual(self.strategy._expression_fhir_number_type(self.zscore), "decimal")
        item = {"linkId": "WFA", "type": "string"}
        self.strategy._apply_calculate_item_type(item, self.zscore)
        self.assertEqual(item["type"], "decimal")

    def test_zscore_is_not_passed_through_as_text(self):
        with self.assertRaises(NotImplementedError):
            self.strategy.tricc_operation_native(["'Zscore'"], ["Zscore"])

    def test_other_native_calls_still_pass_through(self):
        self.assertEqual(self.strategy.tricc_operation_native(["Foo(1)"], ["Foo"]), "Foo(1)")


class TestDisplayTextReferencedTwice(unittest.TestCase):
    def test_reference_wrapped_once(self):
        strategy = _make_strategy()
        concat = TriccOperation(
            TriccOperator.CONCATENATE,
            [TriccStatic("give "), TriccReference("dose"), TriccStatic(" ml, then "), TriccReference("dose")],
        )
        expr = strategy.convert_expression_to_fhirpath(concat)
        self.assertNotIn(".value.where($this.exists()).value", expr)
        self.assertEqual(expr.count("linkId='dose').answer.where($this.exists()).value"), 2)


class TestNullSafeBooleanTests(unittest.TestCase):
    """`X = false` is empty for an unanswered X and blanks a whole `and`."""

    def setUp(self):
        self.strategy = _make_strategy()

    def test_isfalse_inside_and_has_no_bare_comparison(self):
        expr = self.strategy.convert_expression_to_fhirpath(
            TriccOperation(
                TriccOperator.AND,
                [
                    TriccOperation(TriccOperator.ISFALSE, [TriccReference("a")]),
                    TriccOperation(TriccOperator.ISTRUE, [TriccReference("b")]),
                ],
            )
        )
        self.assertNotIn("value = false", expr)
        self.assertNotIn("value = true", expr)
        self.assertIn(".where($this = false).exists()", expr)
        self.assertIn(".where($this = true).exists()", expr)

    def test_boolean_test_on_an_and_is_parenthesised(self):
        inner = TriccOperation(
            TriccOperator.AND,
            [
                TriccOperation(TriccOperator.ISTRUE, [TriccReference("a")]),
                TriccOperation(TriccOperator.ISTRUE, [TriccReference("b")]),
            ],
        )
        expr = self.strategy.tricc_operation_fhirpath_isnottrue(["x and y"], [inner])
        self.assertEqual(expr, "((x and y).where($this = true).empty())")


if __name__ == "__main__":
    unittest.main()
