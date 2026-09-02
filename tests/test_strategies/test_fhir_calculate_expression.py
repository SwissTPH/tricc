"""Regression tests for FHIRStrategy.generate_calculate.

Covers three fixes:
1. Non-calculate nodes (groups / navigation, e.g. activity_start, link_out)
   must never get a calculatedExpression/initialExpression extension, even
   though they inherit a generic ``reference`` attribute for graph linking.
2. calculatedExpression must be FHIRPath — never CQL — since the target
   (openSRP/FHIR-Core) only evaluates CQL through initialExpression.
3. A calculate whose references are answered in *this* Questionnaire gets a
   live calculatedExpression (FHIRPath); one that depends on data outside the
   form (observation history via the CQL Helper) falls back to a one-time
   initialExpression (CQL), with its define recorded in the CQL library.

Run with:
    python -m pytest tests/test_strategies/test_fhir_calculate_expression.py -v
"""

import re
import types
import unittest
from unittest.mock import MagicMock

from tricc_oo.models.base import TriccNodeType, TriccOperation, TriccOperator, TriccReference, TriccStatic
from tricc_oo.models.calculate import TriccNodeCalculate
from tricc_oo.models.tricc import TriccNodeInteger
from tricc_oo.strategies.output.fhir_form import FHIRStrategy


def _make_strategy():
    project = MagicMock()
    project.start_pages = {}
    project.pages = {}
    project.code_systems = {}
    return FHIRStrategy(project, "/tmp/fhir_calculate_test_out")


def _item(link_id, item_type="decimal"):
    return {"linkId": link_id, "type": item_type}


class TestGenerateCalculateSkipsNonCalculateNodes(unittest.TestCase):
    """Fix 1: groups / navigation nodes must not get a calculate-style extension."""

    def test_activity_start_group_gets_no_extension(self):
        strategy = _make_strategy()
        strategy.questionnaires["main"] = {
            "resourceType": "Questionnaire",
            "item": [_item("registration", "group")],
        }
        # activity_start inherits a generic `reference` field from
        # TriccNodeFakeCalculateBase even though it is a group container, not
        # a value-producing calculate node.
        node = types.SimpleNamespace(
            tricc_type=TriccNodeType.activity_start,
            segment="main",
            reference=object(),
            expression_reference=None,
        )

        strategy.generate_calculate(node)

        item = strategy.questionnaires["main"]["item"][0]
        self.assertNotIn("extension", item)
        self.assertEqual(strategy.cql_defines, {})

    def test_link_out_group_gets_no_extension(self):
        strategy = _make_strategy()
        strategy.questionnaires["main"] = {
            "resourceType": "Questionnaire",
            "item": [_item("goto1", "group")],
        }
        target = types.SimpleNamespace(tricc_type=TriccNodeType.link_in)
        node = types.SimpleNamespace(
            tricc_type=TriccNodeType.link_out,
            segment="main",
            reference=target,
            expression_reference=None,
        )

        strategy.generate_calculate(node)

        item = strategy.questionnaires["main"]["item"][0]
        self.assertNotIn("extension", item)
        self.assertEqual(strategy.cql_defines, {})


class TestGenerateCalculateExpressionLanguage(unittest.TestCase):
    """Fixes 2 & 3: FHIRPath calculatedExpression in-form, CQL initialExpression otherwise."""

    def _make_bmi_node(self, weight, height):
        bmi = TriccNodeCalculate(id="bmi1", name="bmi", label="BMI")
        bmi.expression_reference = TriccOperation(TriccOperator.DIVIDED, [weight, height])
        return bmi

    def test_in_form_reference_uses_fhirpath_calculated_expression(self):
        strategy = _make_strategy()
        weight = TriccNodeInteger(id="w1", name="weight", label="Weight")
        height = TriccNodeInteger(id="h1", name="height", label="Height")
        bmi = self._make_bmi_node(weight, height)

        strategy.questionnaires["main"] = {
            "resourceType": "Questionnaire",
            "item": [_item("weight", "integer"), _item("height", "integer"), _item("bmi")],
        }

        strategy.generate_calculate(bmi)

        item = strategy.questionnaires["main"]["item"][2]
        self.assertEqual(item["linkId"], "bmi")
        extensions = item.get("extension", [])
        self.assertEqual(len(extensions), 1)
        value_expr = extensions[0]["valueExpression"]
        self.assertEqual(value_expr["language"], "text/fhirpath")
        self.assertIn("%resource.item.where(linkId='weight')", value_expr["expression"])
        self.assertIn("%resource.item.where(linkId='height')", value_expr["expression"])
        self.assertNotIn("repeat(item)", value_expr["expression"])
        # No CQL define should have been recorded for a pure in-form calculation.
        self.assertEqual(strategy.cql_defines, {})

    def test_out_of_form_reference_falls_back_to_cql_initial_expression(self):
        strategy = _make_strategy()
        # weight/height are not present as items in this Questionnaire — e.g.
        # they were captured in a different process and are only reachable via
        # the CQL Helper (observation history).
        weight = TriccNodeInteger(id="w1", name="weight", label="Weight")
        height = TriccNodeInteger(id="h1", name="height", label="Height")
        bmi = self._make_bmi_node(weight, height)

        strategy.questionnaires["main"] = {
            "resourceType": "Questionnaire",
            "item": [_item("bmi")],
        }

        strategy.generate_calculate(bmi)

        item = strategy.questionnaires["main"]["item"][0]
        extensions = item.get("extension", [])
        self.assertEqual(len(extensions), 1)
        value_expr = extensions[0]["valueExpression"]
        self.assertEqual(value_expr["language"], "text/cql-identifier")
        self.assertEqual(value_expr["expression"], "Calc_bmi")
        self.assertIn("main", strategy.cql_defines)
        self.assertTrue(any("Calc_bmi" in d for d in strategy.cql_defines["main"]))

    def test_bare_reference_treated_as_not_captured(self):
        """A raw TriccReference (unresolved placeholder) must never be trusted as
        an in-form item, even if a same-named item happens to exist."""
        strategy = _make_strategy()
        bmi = TriccNodeCalculate(id="bmi1", name="bmi", label="BMI")
        bmi.expression_reference = TriccOperation(
            TriccOperator.DIVIDED, [TriccReference("weight"), TriccReference("height")]
        )

        strategy.questionnaires["main"] = {
            "resourceType": "Questionnaire",
            "item": [_item("weight", "integer"), _item("height", "integer"), _item("bmi")],
        }

        strategy.generate_calculate(bmi)

        item = strategy.questionnaires["main"]["item"][2]
        extensions = item.get("extension", [])
        self.assertEqual(len(extensions), 1)
        self.assertEqual(extensions[0]["valueExpression"]["language"], "text/cql-identifier")

    def test_contains_calculate_item_type_is_boolean(self):
        from tricc_oo.models.tricc import TriccNodeSelectMultiple

        strategy = _make_strategy()
        select = TriccNodeSelectMultiple(
            id="select_why", name="select_why", label="Why ?", list_name="why"
        )
        flag = TriccNodeCalculate(id="demo_hungry", name="demo.hungry", label="contains: hungry")
        flag.expression_reference = TriccOperation(TriccOperator.CONTAINS, [select, "demo.hungry"])

        strategy.questionnaires["main"] = {
            "resourceType": "Questionnaire",
            "item": [
                _item("select_why", "choice"),
                {"linkId": "demo_hungry", "type": "string"},
            ],
        }

        strategy.generate_calculate(flag)

        item = strategy.questionnaires["main"]["item"][1]
        self.assertEqual(item["type"], "boolean")
        expr = item["extension"][0]["valueExpression"]["expression"]
        self.assertIn("value.code", expr)
        self.assertIn(".exists()", expr)
        self.assertNotIn("valueCoding", expr)
        self.assertIn("'demo.hungry'", expr)

    def test_age_in_months_case_uses_fhirpath_calculated_expression(self):
        """In-form searched CASE must be live FHIRPath, not CQL initialExpression."""
        strategy = _make_strategy()
        years = TriccNodeInteger(id="y1", name="p_age_years", label="Years")
        months = TriccNodeInteger(id="m1", name="p_age_months", label="Months")
        age = TriccNodeCalculate(id="age1", name="age_in_months", label="Age in months")
        age.expression_reference = TriccOperation(
            TriccOperator.CASE,
            [
                [
                    TriccOperation(
                        TriccOperator.MORE_OR_EQUAL, [months, TriccStatic(0)]
                    ),
                    TriccOperation(
                        TriccOperator.PLUS,
                        [
                            TriccOperation(TriccOperator.COALESCE, [months, TriccStatic(0)]),
                            TriccOperation(
                                TriccOperator.COALESCE,
                                [
                                    TriccOperation(
                                        TriccOperator.MULTIPLIED, [years, TriccStatic(12)]
                                    ),
                                    TriccStatic(0),
                                ],
                            ),
                        ],
                    ),
                ],
                TriccStatic(0),
            ],
        )
        strategy.questionnaires["main"] = {
            "resourceType": "Questionnaire",
            "item": [
                _item("p_age_years", "integer"),
                _item("p_age_months", "integer"),
                {"linkId": "age_in_months", "type": "string"},
            ],
        }

        strategy.generate_calculate(age)

        item = strategy.questionnaires["main"]["item"][2]
        self.assertEqual(item["type"], "decimal")
        ext = item["extension"][0]["valueExpression"]
        self.assertEqual(ext["language"], "text/fhirpath")
        self.assertTrue(ext["expression"].startswith("iif("))
        self.assertIn("linkId='p_age_months'", ext["expression"])
        self.assertEqual(strategy.cql_defines, {})

    def test_age_month_calculate_item_type_is_integer(self):
        strategy = _make_strategy()
        age = TriccNodeCalculate(id="age1", name="age_in_months", label="Age in months")
        age.expression_reference = TriccOperation(
            TriccOperator.AGE_MONTH, [TriccReference("dob")]
        )
        strategy.questionnaires["main"] = {
            "resourceType": "Questionnaire",
            "item": [{"linkId": "age_in_months", "type": "string"}],
        }

        strategy.generate_calculate(age)

        item = strategy.questionnaires["main"]["item"][0]
        self.assertEqual(item["type"], "integer")

    def test_plus_calculate_item_type_is_decimal(self):
        strategy = _make_strategy()
        years = TriccNodeInteger(id="y1", name="p_age_years", label="Years")
        months = TriccNodeInteger(id="m1", name="p_age_months", label="Months")
        age = TriccNodeCalculate(id="age1", name="age_in_months", label="Age in months")
        age.expression_reference = TriccOperation(TriccOperator.PLUS, [years, months])
        strategy.questionnaires["main"] = {
            "resourceType": "Questionnaire",
            "item": [
                _item("p_age_years", "integer"),
                _item("p_age_months", "integer"),
                {"linkId": "age_in_months", "type": "string"},
            ],
        }

        strategy.generate_calculate(age)

        item = strategy.questionnaires["main"]["item"][2]
        self.assertEqual(item["type"], "decimal")

    def test_coalesce_integer_fallback_item_type_is_integer(self):
        strategy = _make_strategy()
        years = TriccNodeInteger(id="y1", name="p_age_years", label="Years")
        age = TriccNodeCalculate(id="age1", name="age_in_years", label="Age in years")
        age.expression_reference = TriccOperation(
            TriccOperator.COALESCE, [years, TriccStatic(0)]
        )
        strategy.questionnaires["main"] = {
            "resourceType": "Questionnaire",
            "item": [
                _item("p_age_years", "integer"),
                {"linkId": "age_in_years", "type": "string"},
            ],
        }

        strategy.generate_calculate(age)

        item = strategy.questionnaires["main"]["item"][1]
        self.assertEqual(item["type"], "integer")
        expr = item["extension"][0]["valueExpression"]["expression"]
        self.assertIn(".value", expr)
        self.assertNotIn(".answer|0", expr)
        self.assertIn("|0.0", expr)


class TestEmptySafeMathCalculatedExpression(unittest.TestCase):
    """fix/20260831-fhirpath-empty-safe-math.md

    HAPI's math functions raise on an empty focus instead of returning empty,
    and ``initializeCalculatedExpressions`` runs every calculatedExpression at
    render time with all answers still empty — so a bare ``.round()`` kills the
    whole Questionnaire before the first item is drawn.
    """

    # `.round()` / `.abs()` that is not the body of a select($this. …) projection.
    _BARE_MATH = re.compile(r"(?<!\$this)\.(?:round|abs)\(\)")

    def _bmi_item(self):
        strategy = _make_strategy()
        weight = TriccNodeInteger(id="w1", name="weight", label="Weight")
        height = TriccNodeInteger(id="h1", name="height", label="Height")
        height_m = TriccOperation(TriccOperator.DIVIDED, [height, TriccStatic(100)])
        bmi = TriccNodeCalculate(id="bmi1", name="bmi", label="BMI")
        bmi.expression_reference = TriccOperation(
            TriccOperator.ROUND,
            [
                TriccOperation(
                    TriccOperator.DIVIDED,
                    [weight, TriccOperation(TriccOperator.MULTIPLIED, [height_m, height_m])],
                )
            ],
        )
        strategy.questionnaires["main"] = {
            "resourceType": "Questionnaire",
            "item": [_item("weight", "integer"), _item("height", "integer"), _item("bmi")],
        }

        strategy.generate_calculate(bmi)

        return strategy.questionnaires["main"]["item"][2]

    def test_round_over_in_form_answers_is_empty_safe(self):
        item = self._bmi_item()
        value_expr = item["extension"][0]["valueExpression"]
        expr = value_expr["expression"]
        self.assertEqual(value_expr["language"], "text/fhirpath")
        self.assertIn(".select($this.round())", expr)
        self.assertIsNone(
            self._BARE_MATH.search(expr),
            f"bare math call outside select($this. …): {expr}",
        )
        # The operand keeps its answer-value scalar wrap and decimal cast.
        self.assertIn(".answer.where($this.exists()).value", expr)
        self.assertIn(".toDecimal()", expr)

    def test_abs_over_in_form_answers_is_empty_safe(self):
        strategy = _make_strategy()
        a = TriccNodeInteger(id="a1", name="a", label="A")
        b = TriccNodeInteger(id="b1", name="b", label="B")
        delta = TriccNodeCalculate(id="d1", name="delta", label="Delta")
        delta.expression_reference = TriccOperation(
            TriccOperator.ABS, [TriccOperation(TriccOperator.MINUS, [a, b])]
        )
        strategy.questionnaires["main"] = {
            "resourceType": "Questionnaire",
            "item": [_item("a", "integer"), _item("b", "integer"), _item("delta")],
        }

        strategy.generate_calculate(delta)

        expr = strategy.questionnaires["main"]["item"][2]["extension"][0]["valueExpression"]["expression"]
        self.assertIn(".select($this.abs())", expr)
        self.assertIsNone(self._BARE_MATH.search(expr), expr)


if __name__ == "__main__":
    unittest.main()
