"""Regression tests for FHIRStrategy.convert_expression_to_fhirpath.

enableWhenExpression is declared "language": "text/fhirpath" (see
build_enable_when_expression in questionnaire_item_mapper.py) — only
initialExpression/calculatedExpression may use CQL. These tests guard against
CQL syntax (e.g. "is true", "between ... and ...", "if ... then ... else",
"Today()", prefix "not (expr)") leaking into relevance/enableWhenExpression
output.

Run with:
    python -m pytest tests/test_strategies/test_fhir_relevance_fhirpath.py -v
"""

import unittest
from unittest.mock import MagicMock

from decimal import Decimal

from tricc_oo.models.base import TriccOperation, TriccOperator, TriccReference, TriccStatic
from tricc_oo.models.tricc import TriccNodeInteger
from tricc_oo.strategies.output.fhir_form import FHIRStrategy, format_fhirpath_decimal


def _make_strategy():
    project = MagicMock()
    project.start_pages = {}
    project.pages = {}
    project.code_systems = {}
    return FHIRStrategy(project, "/tmp/fhir_relevance_test_out")


class TestFormatFhirpathDecimal(unittest.TestCase):
    def test_whole_numbers_keep_a_fractional_part(self):
        self.assertEqual(format_fhirpath_decimal(0), "0.0")
        self.assertEqual(format_fhirpath_decimal(12), "12.0")
        self.assertEqual(format_fhirpath_decimal(-3), "-3.0")
        self.assertEqual(format_fhirpath_decimal("12"), "12.0")
        self.assertEqual(format_fhirpath_decimal(12.0), "12.0")
        self.assertEqual(format_fhirpath_decimal(Decimal("12.0")), "12.0")

    def test_authored_fraction_is_preserved(self):
        self.assertEqual(format_fhirpath_decimal(4.3), "4.3")
        self.assertEqual(format_fhirpath_decimal("4.3"), "4.3")
        self.assertEqual(format_fhirpath_decimal(Decimal("4.30")), "4.3")


class TestConvertExpressionToFhirpath(unittest.TestCase):
    def setUp(self):
        self.strategy = _make_strategy()

    def test_istrue_uses_equality_not_cql_is_true(self):
        op = TriccOperation(TriccOperator.ISTRUE, [TriccReference("smoker")])
        expr = self.strategy.convert_expression_to_fhirpath(op)
        self.assertNotIn("is true", expr)
        self.assertIn("= true", expr)
        self.assertIn("%resource.repeat(item).where(linkId='smoker').answer", expr)
        self.assertIn(".value", expr)
        self.assertNotIn("valueCoding", expr)

    def test_isnottrue_uses_not_equal(self):
        op = TriccOperation(TriccOperator.ISNOTTRUE, [TriccReference("smoker")])
        expr = self.strategy.convert_expression_to_fhirpath(op)
        self.assertNotIn("is not true", expr)
        self.assertIn("!= true", expr)

    def test_isnull_uses_empty_not_cql_is_null(self):
        op = TriccOperation(TriccOperator.ISNULL, [TriccReference("age")])
        expr = self.strategy.convert_expression_to_fhirpath(op)
        self.assertNotIn("is null", expr)
        self.assertEqual(expr, "%resource.repeat(item).where(linkId='age').answer.empty()")

    def test_isnotnull_uses_exists(self):
        op = TriccOperation(TriccOperator.ISNOTNULL, [TriccReference("age")])
        expr = self.strategy.convert_expression_to_fhirpath(op)
        self.assertNotIn("is not null", expr)
        self.assertEqual(expr, "%resource.repeat(item).where(linkId='age').answer.exists()")

    def test_exists_notexists_use_fhirpath_functions(self):
        exists_expr = self.strategy.convert_expression_to_fhirpath(
            TriccOperation(TriccOperator.EXISTS, [TriccReference("age")])
        )
        notexists_expr = self.strategy.convert_expression_to_fhirpath(
            TriccOperation(TriccOperator.NOTEXISTS, [TriccReference("age")])
        )
        self.assertNotIn("is not null", exists_expr)
        self.assertNotIn("is null", notexists_expr)
        self.assertTrue(exists_expr.endswith(".exists()"))
        self.assertTrue(notexists_expr.endswith(".empty()"))

    def test_between_expands_to_range_comparison(self):
        op = TriccOperation(
            TriccOperator.BETWEEN,
            [TriccReference("age"), TriccStatic(1), TriccStatic(5)],
        )
        expr = self.strategy.convert_expression_to_fhirpath(op)
        self.assertNotIn("between", expr)
        self.assertIn(">= 1.0", expr)
        self.assertIn("<= 5.0", expr)
        self.assertIn(".value", expr)
        self.assertIn(".toDecimal()", expr)

    def test_more_or_equal_casts_item_and_literal_to_decimal(self):
        """HAPI refuses string >= integer; age calculates used to be type string."""
        op = TriccOperation(
            TriccOperator.MORE_OR_EQUAL, [TriccReference("age_in_months"), TriccStatic(2)]
        )
        expr = self.strategy.convert_expression_to_fhirpath(op)
        self.assertIn("linkId='age_in_months'", expr)
        self.assertIn(".toDecimal()", expr)
        self.assertIn(">= 2.0", expr)
        self.assertIn(".value", expr)

    def test_less_wraps_answer_value_and_casts_to_decimal(self):
        op = TriccOperation(TriccOperator.LESS, [TriccReference("age_in_months"), TriccStatic(2)])
        expr = self.strategy.convert_expression_to_fhirpath(op)
        self.assertIn(".value", expr)
        self.assertIn(".toDecimal()", expr)
        self.assertIn("< 2.0", expr)

    def test_searched_case_uses_nested_iif(self):
        """XLSForm nested if(); FHIRPath nested iif() — age_in_months formula."""
        years = TriccNodeInteger(id="y1", name="p_age_years", label="Years")
        months = TriccNodeInteger(id="m1", name="p_age_months", label="Months")
        when_true = TriccOperation(
            TriccOperator.PLUS,
            [
                TriccOperation(TriccOperator.COALESCE, [months, TriccStatic(0)]),
                TriccOperation(
                    TriccOperator.COALESCE,
                    [
                        TriccOperation(TriccOperator.MULTIPLIED, [years, TriccStatic(12)]),
                        TriccStatic(0),
                    ],
                ),
            ],
        )
        op = TriccOperation(
            TriccOperator.CASE,
            [
                [
                    TriccOperation(
                        TriccOperator.MORE_OR_EQUAL, [months, TriccStatic(0)]
                    ),
                    when_true,
                ],
                TriccStatic(0),
            ],
        )
        expr = self.strategy.convert_expression_to_fhirpath(op)
        self.assertTrue(expr.startswith("iif("))
        self.assertIn("linkId='p_age_months'", expr)
        self.assertIn("linkId='p_age_years'", expr)
        self.assertIn(".value", expr)
        self.assertIn("* 12.0", expr)
        self.assertIn("|0.0", expr)
        self.assertTrue(expr.endswith(", 0.0)"))
        self.assertNotIn("case ", expr)
        self.assertNotIn(" then ", expr)

    def test_value_case_uses_nested_iif_equality(self):
        op = TriccOperation(
            TriccOperator.CASE,
            [
                TriccReference("age_in_months"),
                [TriccStatic(0), TriccStatic("newborn")],
                [TriccStatic(1), TriccStatic("newborn")],
                TriccStatic("child"),
            ],
        )
        expr = self.strategy.convert_expression_to_fhirpath(op)
        self.assertTrue(expr.startswith("iif("))
        self.assertIn("linkId='age_in_months'", expr)
        self.assertIn("= 0", expr)
        self.assertIn("'newborn'", expr)
        self.assertIn("'child'", expr)
        self.assertNotIn("case ", expr)

    def test_if_uses_iif_not_cql_if_then_else(self):
        cond = TriccOperation(TriccOperator.ISTRUE, [TriccReference("smoker")])
        op = TriccOperation(
            TriccOperator.IF,
            [cond, TriccStatic("high"), TriccStatic("low")],
        )
        expr = self.strategy.convert_expression_to_fhirpath(op)
        self.assertNotIn("then", expr)
        self.assertNotIn(" else ", expr)
        self.assertTrue(expr.startswith("iif("))

    def test_today_now_lowercase_no_args(self):
        today_expr = self.strategy.convert_expression_to_fhirpath(TriccOperation(TriccOperator.TODAY, []))
        now_expr = self.strategy.convert_expression_to_fhirpath(TriccOperation(TriccOperator.NOW, []))
        self.assertEqual(today_expr, "today()")
        self.assertEqual(now_expr, "now()")

    def test_length_uses_suffix_function(self):
        op = TriccOperation(TriccOperator.LENGTH, [TriccReference("name")])
        expr = self.strategy.convert_expression_to_fhirpath(op)
        self.assertNotIn("Length(", expr)
        self.assertIn(".length()", expr)
        self.assertIn(".value", expr)

    def test_round_abs_use_suffix_functions(self):
        round_expr = self.strategy.convert_expression_to_fhirpath(
            TriccOperation(TriccOperator.ROUND, [TriccReference("bmi")])
        )
        abs_expr = self.strategy.convert_expression_to_fhirpath(
            TriccOperation(TriccOperator.ABS, [TriccReference("delta")])
        )
        self.assertNotIn("Round(", round_expr)
        self.assertIn(".round()", round_expr)
        self.assertNotIn("Abs(", abs_expr)
        self.assertIn(".abs()", abs_expr)

    def test_concatenate_uses_ampersand_not_plus(self):
        op = TriccOperation(TriccOperator.CONCATENATE, [TriccStatic("a"), TriccStatic("b")])
        expr = self.strategy.convert_expression_to_fhirpath(op)
        self.assertIn("&", expr)
        self.assertNotIn("+", expr)

    def test_not_uses_suffix_function_not_cql_prefix(self):
        # openSRP/HAPI: `not (expr)` is parsed as not(expr) and fails with
        # "The function \"not\" requires 0 parameters". FHIRPath is `.not()`.
        op = TriccOperation(TriccOperator.NOT, [TriccReference("smoker")])
        expr = self.strategy.convert_expression_to_fhirpath(op)
        self.assertFalse(expr.lstrip().startswith("not "))
        self.assertNotIn("not (", expr)
        self.assertTrue(expr.endswith(".not()"))

    def test_not_selected_uses_suffix_not(self):
        # The demo form's demo_agree enableWhen: NOT(SELECTED(select_why, hungry)).
        selected = TriccOperation(
            TriccOperator.SELECTED,
            [TriccReference("select_why"), TriccStatic("demo.hungry")],
        )
        expr = self.strategy.convert_expression_to_fhirpath(
            TriccOperation(TriccOperator.NOT, [selected])
        )
        self.assertFalse(expr.lstrip().startswith("not "))
        self.assertNotIn("not (", expr)
        self.assertTrue(expr.endswith(".not()"))
        self.assertIn("demo.hungry", expr)
        self.assertIn("select_why", expr)
        self.assertIn("repeat(item)", expr)
        self.assertIn("value.code", expr)
        self.assertIn(".exists()", expr)
        self.assertNotIn("valueCoding", expr)
        self.assertNotIn(" in %resource.repeat(item).where(linkId='select_why').answer)", expr)

    def test_equal_and_selected_still_use_shared_syntax(self):
        # Sanity check the "identical in both languages" operators weren't broken
        # by removing the dead duplicate stubs.
        eq_expr = self.strategy.convert_expression_to_fhirpath(
            TriccOperation(TriccOperator.EQUAL, [TriccReference("age"), TriccStatic(5)])
        )
        self.assertIn("=", eq_expr)
        self.assertIn(".value", eq_expr)

    def test_equal_choice_to_code_uses_membership_not_value_code_equals(self):
        from tricc_oo.models.tricc import TriccNodeSelectOne, TriccNodeSelectOption

        select = TriccNodeSelectOne(
            id="CHE_B3_DE06",
            name="CHE_B3_DE06",
            label="Type of Consultation",
            list_name="consult",
        )
        opt = TriccNodeSelectOption(
            id="init",
            name="CHE.B3.DE04",
            label="Initial visit",
            select=select,
            list_name="consult",
        )
        select.options = {0: opt}
        self.strategy.questionnaires["main"] = {
            "resourceType": "Questionnaire",
            "item": [{"linkId": "CHE_B3_DE06", "type": "choice"}],
        }
        expr = self.strategy.convert_expression_to_fhirpath(
            TriccOperation(TriccOperator.EQUAL, [select, TriccStatic("CHE.B3.DE04")])
        )
        self.assertEqual(
            expr,
            "%resource.item.where(linkId='CHE_B3_DE06')"
            ".answer.where(value.code = 'CHE.B3.DE04').exists()",
        )
        self.assertNotIn("where($this.exists()).value.code =", expr)
        self.assertNotIn("valueCoding", expr)
        self.assertNotIn("repeat(item)", expr)

    def test_not_equal_choice_to_code_negates_membership(self):
        from tricc_oo.models.tricc import TriccNodeSelectOne

        select = TriccNodeSelectOne(
            id="CHE_B3_DE06",
            name="CHE_B3_DE06",
            label="Type of Consultation",
            list_name="consult",
        )
        self.strategy.questionnaires["main"] = {
            "resourceType": "Questionnaire",
            "item": [{"linkId": "CHE_B3_DE06", "type": "choice"}],
        }
        expr = self.strategy.convert_expression_to_fhirpath(
            TriccOperation(TriccOperator.NOTEQUAL, [select, TriccStatic("CHE.B3.DE04")])
        )
        self.assertEqual(
            expr,
            "%resource.item.where(linkId='CHE_B3_DE06')"
            ".answer.where(value.code = 'CHE.B3.DE04').exists().not()",
        )

    def test_no_clean_fhirpath_equivalent_raises_not_implemented(self):
        for operator in (
            TriccOperator.MIN,
            TriccOperator.MAX,
            TriccOperator.SUM,
            TriccOperator.AGE_DAY,
            TriccOperator.AGE_MONTH,
            TriccOperator.AGE_YEAR,
            TriccOperator.FORMAT_DATE,
        ):
            with self.assertRaises(NotImplementedError):
                self.strategy.convert_expression_to_fhirpath(
                    TriccOperation(operator, [TriccReference("dob")])
                )

    def test_selected_uses_repeat_item_and_value_coding_code(self):
        op = TriccOperation(
            TriccOperator.SELECTED,
            [TriccReference("select_why"), TriccStatic("demo.hungry")],
        )
        expr = self.strategy.convert_expression_to_fhirpath(op)
        self.assertEqual(
            expr,
            "%resource.repeat(item).where(linkId='select_why').answer.where(value.code = 'demo.hungry').exists()",
        )

    def test_nested_item_uses_group_path_instead_of_repeat(self):
        from tricc_oo.models.tricc import TriccNodeSelectOne, TriccNodeSelectOption

        select = TriccNodeSelectOne(
            id="CHE_B3_DE06",
            name="CHE_B3_DE06",
            label="Type of Consultation",
            list_name="consult",
        )
        select.options = {
            0: TriccNodeSelectOption(
                id="init",
                name="CHE.B3.DE04",
                label="Initial visit",
                select=select,
                list_name="consult",
            )
        }
        self.strategy.questionnaires["main"] = {
            "resourceType": "Questionnaire",
            "item": [
                {
                    "linkId": "page_reg",
                    "type": "group",
                    "item": [
                        {
                            "linkId": "activity_reg",
                            "type": "group",
                            "item": [{"linkId": "CHE_B3_DE06", "type": "choice"}],
                        }
                    ],
                }
            ],
        }
        expr = self.strategy.convert_expression_to_fhirpath(
            TriccOperation(TriccOperator.EQUAL, [select, TriccStatic("CHE.B3.DE04")])
        )
        self.assertEqual(
            expr,
            "%resource.item.where(linkId='page_reg')"
            ".item.where(linkId='activity_reg')"
            ".item.where(linkId='CHE_B3_DE06')"
            ".answer.where(value.code = 'CHE.B3.DE04').exists()",
        )
        self.assertNotIn("repeat(item)", expr)

    def test_contains_uses_in_on_value_coding_code(self):
        from tricc_oo.models.tricc import TriccNodeSelectMultiple

        select = TriccNodeSelectMultiple(
            id="select_why", name="select_why", label="Why ?", list_name="why"
        )
        op = TriccOperation(TriccOperator.CONTAINS, [select, "demo.bad_p"])
        expr = self.strategy.convert_expression_to_fhirpath(op)
        self.assertEqual(
            expr,
            "%resource.repeat(item).where(linkId='select_why').answer.where(value.code = 'demo.bad_p').exists()",
        )

    def test_contains_on_text_item_stays_substring(self):
        from tricc_oo.models.tricc import TriccNodeText

        note = TriccNodeText(id="comment", name="comment", label="Comment")
        op = TriccOperation(TriccOperator.CONTAINS, [note, "hungry"])
        expr = self.strategy.convert_expression_to_fhirpath(op)
        self.assertIn("contains", expr)
        self.assertIn(".value contains 'hungry'", expr)
        self.assertNotIn("valueCoding", expr)

    def test_count_minus_none_option_uses_iif_not_todecimal(self):
        selected = TriccOperation(
            TriccOperator.SELECTED,
            [TriccReference("select_why"), TriccStatic("opt_none")],
        )
        op = TriccOperation(
            TriccOperator.MINUS,
            [
                TriccOperation(TriccOperator.COUNT, [TriccReference("select_why")]),
                TriccOperation(TriccOperator.CAST_NUMBER, [selected]),
            ],
        )
        expr = self.strategy.convert_expression_to_fhirpath(op)
        self.assertIn("iif(", expr)
        self.assertIn("opt_none", expr)
        self.assertIn("value.code", expr)
        self.assertIn(".exists()", expr)
        self.assertNotIn("valueCoding", expr)
        # CAST_NUMBER of the boolean uses iif, not `.toDecimal()` on the exists() test.
        # Outer arithmetic may still wrap the minus operands as decimals.
        self.assertNotIn(".exists()).toDecimal()", expr)
        self.assertIn(".count()", expr)

    def test_multiplied_wraps_item_answer_value_and_casts_to_decimal(self):
        """HAPI rejects ``.answer * 30`` — the left operand must be a number."""
        years = TriccNodeInteger(id="y1", name="p_age_years", label="Years")
        op = TriccOperation(TriccOperator.MULTIPLIED, [years, TriccStatic(12)])
        expr = self.strategy.convert_expression_to_fhirpath(op)
        self.assertIn("linkId='p_age_years'", expr)
        self.assertIn(".value", expr)
        self.assertIn(".toDecimal()", expr)
        self.assertIn("* 12.0", expr)
        self.assertNotIn(".answer *", expr)

    def test_age_in_days_coalesce_multiply_reads_answer_value(self):
        """Registration ``age_in_days``: COALESCE(months, 0) * 30 + 365 * COALESCE(years, 0)."""
        years = TriccNodeInteger(id="y1", name="p_age_years", label="Years")
        months = TriccNodeInteger(id="m1", name="p_age_months", label="Months")
        op = TriccOperation(
            TriccOperator.PLUS,
            [
                TriccOperation(
                    TriccOperator.MULTIPLIED,
                    [
                        TriccOperation(TriccOperator.COALESCE, [months, TriccStatic(0)]),
                        TriccStatic(30),
                    ],
                ),
                TriccOperation(
                    TriccOperator.MULTIPLIED,
                    [
                        TriccStatic(365),
                        TriccOperation(TriccOperator.COALESCE, [years, TriccStatic(0)]),
                    ],
                ),
            ],
        )
        expr = self.strategy.convert_expression_to_fhirpath(op)
        self.assertIn("linkId='p_age_months'", expr)
        self.assertIn("linkId='p_age_years'", expr)
        self.assertIn(".value", expr)
        self.assertIn(".toDecimal()", expr)
        self.assertIn("* 30.0", expr)
        self.assertIn("365.0 *", expr)
        self.assertNotIn(".answer *", expr)
        self.assertNotIn(".answer|0", expr)
        self.assertNotIn("|0)", expr)
        self.assertIn("|0.0", expr)

    def test_selected_on_boolean_item_compares_value(self):
        self.strategy.questionnaires["main"] = {
            "resourceType": "Questionnaire",
            "item": [{"linkId": "demo_is_happy", "type": "boolean"}],
        }
        op = TriccOperation(
            TriccOperator.SELECTED,
            [TriccReference("demo_is_happy"), TriccStatic(True)],
        )
        expr = self.strategy.convert_expression_to_fhirpath(op)
        self.assertIn(".value = true", expr)
        self.assertNotIn("valueCoding", expr)


class TestGenerateRelevanceEmitsFhirpath(unittest.TestCase):
    """Integration check: generate_relevance must attach an enableWhenExpression
    whose expression string is valid FHIRPath, even when the underlying relevance
    condition uses an operator whose CQL and FHIRPath spellings differ."""

    def test_between_relevance_has_no_cql_leak(self):
        strategy = _make_strategy()
        strategy.questionnaires["main"] = {
            "resourceType": "Questionnaire",
            "item": [{"linkId": "followup", "type": "boolean"}],
        }

        node = MagicMock()
        node.segment = "main"
        node.relevance = TriccOperation(
            TriccOperator.BETWEEN,
            [TriccReference("age"), TriccStatic(1), TriccStatic(5)],
        )

        with unittest.mock.patch(
            "tricc_oo.strategies.output.fhir_form.get_export_name", return_value="followup"
        ):
            strategy.generate_relevance(node)

        item = strategy.questionnaires["main"]["item"][0]
        extension = item["extension"][0]
        self.assertEqual(
            extension["url"],
            "http://hl7.org/fhir/uv/sdc/StructureDefinition/sdc-questionnaire-enableWhenExpression",
        )
        self.assertEqual(extension["valueExpression"]["language"], "text/fhirpath")
        expr = extension["valueExpression"]["expression"]
        self.assertNotIn("between", expr)

    def test_activity_start_uses_activity_relevance(self):
        from tricc_oo.models.calculate import TriccNodeActivityStart

        strategy = _make_strategy()
        strategy.questionnaires["main"] = {
            "resourceType": "Questionnaire",
            "item": [{"linkId": "page2", "type": "group", "text": "Page-2", "item": []}],
        }
        node = TriccNodeActivityStart(id="page2", name="page2", label="Page-2")
        node.relevance = TriccStatic(True)
        node.activity = MagicMock()
        node.activity.relevance = TriccOperation(
            TriccOperator.OR,
            [
                TriccOperation(
                    TriccOperator.SELECTED,
                    [TriccReference("select_why"), TriccStatic("demo.bad_p")],
                ),
                TriccOperation(
                    TriccOperator.SELECTED,
                    [TriccReference("select_why"), TriccStatic("demo.hungry")],
                ),
            ],
        )
        strategy.generate_relevance(node)
        item = strategy.questionnaires["main"]["item"][0]
        exprs = [
            ext["valueExpression"]["expression"]
            for ext in item.get("extension", [])
            if ext.get("url")
            == "http://hl7.org/fhir/uv/sdc/StructureDefinition/sdc-questionnaire-enableWhenExpression"
        ]
        self.assertEqual(len(exprs), 1)
        self.assertIn("demo.bad_p", exprs[0])
        self.assertIn("demo.hungry", exprs[0])
        self.assertIn(".exists()", exprs[0])
        self.assertIn(" or ", exprs[0])


class TestOptionRelevanceToggleExpression(unittest.TestCase):
    """Option relevance must become SDC answerOptionsToggleExpression on the parent item."""

    def test_option_relevance_emits_toggle_extension(self):
        from tricc_oo.models.tricc import TriccNodeSelectMultiple, TriccNodeSelectOption
        from tricc_oo.converters.fhir.questionnaire_item_mapper import (
            SDC_EXT_ANSWER_OPTIONS_TOGGLE,
        )

        strategy = _make_strategy()
        select = TriccNodeSelectMultiple(
            id="select_why", name="select_why", label="Why ?", list_name="why"
        )
        angry = TriccNodeSelectOption(
            id="opt_angry",
            name="demo.angry",
            label="Angry",
            select=select,
            list_name="why",
        )
        angry.relevance = TriccOperation(TriccOperator.ISTRUE, [TriccReference("demo_filter")])
        hungry = TriccNodeSelectOption(
            id="opt_hungry",
            name="demo.hungry",
            label="Hungry",
            select=select,
            list_name="why",
        )
        select.options = {0: hungry, 1: angry}

        strategy.questionnaires["main"] = {
            "resourceType": "Questionnaire",
            "item": [
                {
                    "linkId": "select_why",
                    "type": "choice",
                    "answerOption": [
                        {"valueCoding": {"code": "demo.hungry", "display": "Hungry"}},
                        {"valueCoding": {"code": "demo.angry", "display": "Angry"}},
                    ],
                }
            ],
        }

        strategy.generate_relevance(select)

        item = strategy.questionnaires["main"]["item"][0]
        toggles = [
            ext
            for ext in item.get("extension", [])
            if ext.get("url") == SDC_EXT_ANSWER_OPTIONS_TOGGLE
        ]
        self.assertEqual(len(toggles), 1)
        option_codes = [
            nested["valueCoding"]["code"]
            for nested in toggles[0]["extension"]
            if nested.get("url") == "option"
        ]
        self.assertEqual(option_codes, ["demo.angry"])
        expr_ext = next(n for n in toggles[0]["extension"] if n.get("url") == "expression")
        expr = expr_ext["valueExpression"]["expression"]
        self.assertEqual(expr_ext["valueExpression"]["language"], "text/fhirpath")
        self.assertIn("demo_filter", expr)
        self.assertIn("repeat(item)", expr)
        self.assertIn("= true", expr)

    def test_no_option_relevance_emits_no_toggle(self):
        from tricc_oo.models.tricc import TriccNodeSelectMultiple, TriccNodeSelectOption
        from tricc_oo.converters.fhir.questionnaire_item_mapper import (
            SDC_EXT_ANSWER_OPTIONS_TOGGLE,
        )

        strategy = _make_strategy()
        select = TriccNodeSelectMultiple(
            id="select_why", name="select_why", label="Why ?", list_name="why"
        )
        hungry = TriccNodeSelectOption(
            id="opt_hungry",
            name="demo.hungry",
            label="Hungry",
            select=select,
            list_name="why",
        )
        select.options = {0: hungry}
        strategy.questionnaires["main"] = {
            "resourceType": "Questionnaire",
            "item": [{"linkId": "select_why", "type": "choice"}],
        }

        strategy.generate_relevance(select)

        for ext in strategy.questionnaires["main"]["item"][0].get("extension") or []:
            self.assertNotEqual(ext.get("url"), SDC_EXT_ANSWER_OPTIONS_TOGGLE)


if __name__ == "__main__":
    unittest.main()
