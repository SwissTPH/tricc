"""Equality against a select operand, in FHIRPath and in CQL.

`fix/20260824-fhirpath-choice-equality.md` made ``select = 'code'`` emit coded
membership for a *direct* select reference. These tests cover the operands that
were left behind (see fix/20260902-select-operand-coded-equality.md):

* a yes/no select, exported as a native ``boolean`` item, compared to the
  authored ``'yes'`` / ``'no'`` code,
* an operand that only forwards a select's value (``GetRepeatedValue``),
* the CQL flavour, where a select answer is an ``Observation`` CodeableConcept.

Run with:
    python -m pytest tests/test_strategies/test_fhir_select_operand_equality.py -v
"""

import unittest
from unittest.mock import MagicMock

from tricc_oo.models.base import TriccOperation, TriccOperator, TriccReference, TriccStatic
from tricc_oo.models.tricc import TriccNodeSelectOne
from tricc_oo.strategies.output.fhir_form import FHIRStrategy


def _make_strategy():
    project = MagicMock()
    project.start_pages = {}
    project.pages = {}
    project.code_systems = {}
    strategy = FHIRStrategy(project, "/tmp/fhir_select_operand_out")
    strategy.questionnaires["main"] = {
        "resourceType": "Questionnaire",
        "item": [
            {"linkId": "fup_type", "type": "choice"},
            {"linkId": "fup_yn", "type": "boolean"},
            {"linkId": "note_txt", "type": "string"},
        ],
    }
    return strategy


def _select_node():
    return TriccNodeSelectOne(
        id="fup_type", name="fup_type", label="Follow up type", list_name="fup"
    )


class TestYesNoCodeLiteral(unittest.TestCase):
    """R1 — a yes/no code literal becomes a boolean literal."""

    def setUp(self):
        self.strategy = _make_strategy()

    def test_equal_yes_compares_to_boolean_true(self):
        expr = self.strategy.convert_expression_to_fhirpath(
            TriccOperation(TriccOperator.EQUAL, [TriccReference("fup_yn"), TriccStatic("yes")])
        )
        self.assertEqual(
            expr,
            "%resource.item.where(linkId='fup_yn').answer.where($this.exists()).value = true",
        )
        self.assertNotIn("'yes'", expr)
        self.assertNotIn("value.code", expr)

    def test_not_equal_no_compares_to_boolean_false(self):
        expr = self.strategy.convert_expression_to_fhirpath(
            TriccOperation(TriccOperator.NOTEQUAL, [TriccReference("fup_yn"), TriccStatic("no")])
        )
        self.assertEqual(
            expr,
            "%resource.item.where(linkId='fup_yn').answer.where($this.exists()).value != false",
        )
        self.assertNotIn("'no'", expr)

    def test_code_literal_on_either_side(self):
        expr = self.strategy.convert_expression_to_fhirpath(
            TriccOperation(TriccOperator.EQUAL, [TriccStatic("yes"), TriccReference("fup_yn")])
        )
        self.assertEqual(
            expr,
            "true = %resource.item.where(linkId='fup_yn').answer.where($this.exists()).value",
        )
        self.assertNotIn("'yes'", expr)

    def test_numeric_yesno_markers_are_mapped(self):
        for code, literal in (("1", "true"), ("0", "false"), ("y", "true"), ("n", "false")):
            expr = self.strategy.convert_expression_to_fhirpath(
                TriccOperation(
                    TriccOperator.EQUAL, [TriccReference("fup_yn"), TriccStatic(code)]
                )
            )
            self.assertTrue(expr.endswith(f".value = {literal}"), expr)

    def test_selected_on_boolean_item_maps_the_code(self):
        expr = self.strategy.convert_expression_to_fhirpath(
            TriccOperation(TriccOperator.SELECTED, [TriccReference("fup_yn"), TriccStatic("yes")])
        )
        self.assertEqual(
            expr,
            "(%resource.item.where(linkId='fup_yn').answer.where($this.exists()).value = true)",
        )

    def test_unknown_code_on_boolean_item_is_left_alone(self):
        # Not a yes/no marker: no boolean literal to map to.
        expr = self.strategy.convert_expression_to_fhirpath(
            TriccOperation(TriccOperator.EQUAL, [TriccReference("fup_yn"), TriccStatic("maybe")])
        )
        self.assertIn("= 'maybe'", expr)

    def test_cql_yesno_code_becomes_boolean(self):
        expr = self.strategy.convert_expression_to_cql(
            TriccOperation(TriccOperator.EQUAL, [TriccReference("fup_yn"), TriccStatic("yes")])
        )
        self.assertEqual(expr, "Helper.GetObservationValue('fup_yn') = true")


class TestForwardedSelectOperand(unittest.TestCase):
    """R2 — choice-ness survives an operand that only forwards a value."""

    def setUp(self):
        self.strategy = _make_strategy()

    def _repeated(self):
        return TriccOperation(
            TriccOperator.GET_REPEATED_VALUE, [_select_node(), TriccStatic(2)]
        )

    def test_get_repeated_value_equality_uses_membership(self):
        expr = self.strategy.convert_expression_to_fhirpath(
            TriccOperation(TriccOperator.EQUAL, [self._repeated(), TriccStatic("home_visit")])
        )
        self.assertEqual(
            expr,
            "%resource.item.where(linkId='fup_type')"
            ".answer.where($this.value.code = 'home_visit').exists()",
        )
        self.assertNotIn(".answer = ", expr)

    def test_get_repeated_value_inequality_negates_membership(self):
        expr = self.strategy.convert_expression_to_fhirpath(
            TriccOperation(TriccOperator.NOTEQUAL, [self._repeated(), TriccStatic("home_visit")])
        )
        self.assertTrue(expr.endswith(".exists().not()"), expr)

    def test_parenthesised_select_uses_membership(self):
        parens = TriccOperation(TriccOperator.PARENTHESIS, [_select_node()])
        expr = self.strategy.convert_expression_to_fhirpath(
            TriccOperation(TriccOperator.EQUAL, [parens, TriccStatic("home_visit")])
        )
        self.assertIn(".where($this.value.code = 'home_visit').exists()", expr)


class TestCodeScalarOperandKeepsPlainEquality(unittest.TestCase):
    """R2 guard — an operand already reduced to a code is *not* given membership.

    ``COALESCE`` unions ``.value.code`` members and takes ``.first()``, so the
    result is a code string: ``.first().where($this.value.code = 'x')`` would be
    always false. Only an ``…answer`` collection gets the membership form.
    """

    def setUp(self):
        self.strategy = _make_strategy()
        self.strategy._current_segment = "main"
        self.v2 = TriccNodeSelectOne(
            id="fup_type", name="fup_type", label="v2", list_name="fup"
        )
        self.v1 = TriccNodeSelectOne(
            id="fup_type_Vv_1", name="fup_type_Vv_1", label="v1", list_name="fup"
        )

    def test_coalesce_of_choices_compares_the_code(self):
        coalesce = TriccOperation(TriccOperator.COALESCE, [self.v2, self.v1])
        expr = self.strategy.convert_expression_to_fhirpath(
            TriccOperation(TriccOperator.EQUAL, [coalesce, TriccStatic("home_visit")])
        )
        self.assertTrue(expr.endswith(".first() = 'home_visit'"), expr)
        self.assertNotIn(".first().where($this.value.code", expr)

    def test_inherited_value_union_still_uses_membership(self):
        # Union of `.answer` collections: `.first()` *is* an Answer, so the
        # membership form of fix/20260824-fhirpath-choice-equality.md applies.
        inherited = TriccOperation(TriccOperator.GET_INHERITED_VALUE, [self.v2, self.v1])
        expr = self.strategy.convert_expression_to_fhirpath(
            TriccOperation(TriccOperator.EQUAL, [inherited, TriccStatic("home_visit")])
        )
        self.assertTrue(
            expr.endswith(".first().where($this.value.code = 'home_visit').exists()"), expr
        )


class TestCqlCodedEqualityIsLeftAlone(unittest.TestCase):
    """§8 — CQL CodeableConcept equality is deferred, not rewritten.

    An earlier revision emitted
    ``exists((… as FHIR.CodeableConcept).coding Cd where Cd.code = '…')``. That
    is unverified against the CQL translator OpenSRP uses and a Library that
    fails to translate takes the whole form down, so the CQL path keeps its
    previous output until it can be validated.
    """

    def setUp(self):
        self.strategy = _make_strategy()

    def test_choice_equality_keeps_the_plain_comparison(self):
        expr = self.strategy.convert_expression_to_cql(
            TriccOperation(
                TriccOperator.EQUAL, [TriccReference("fup_type"), TriccStatic("home_visit")]
            )
        )
        self.assertEqual(expr, "Helper.GetObservationValue('fup_type') = 'home_visit'")
        self.assertNotIn("FHIR.CodeableConcept", expr)

    def test_selected_keeps_the_in_form(self):
        expr = self.strategy.convert_expression_to_cql(
            TriccOperation(
                TriccOperator.SELECTED, [TriccReference("fup_type"), TriccStatic("home_visit")]
            )
        )
        self.assertEqual(expr, "('home_visit' in Helper.GetObservationValue('fup_type'))")


class TestNonChoiceEqualityUnchanged(unittest.TestCase):
    """R4 — nothing else moves."""

    def setUp(self):
        self.strategy = _make_strategy()

    def test_choice_reference_still_uses_membership(self):
        expr = self.strategy.convert_expression_to_fhirpath(
            TriccOperation(
                TriccOperator.EQUAL, [TriccReference("fup_type"), TriccStatic("home_visit")]
            )
        )
        self.assertEqual(
            expr,
            "%resource.item.where(linkId='fup_type')"
            ".answer.where($this.value.code = 'home_visit').exists()",
        )

    def test_string_item_keeps_scalar_value_comparison(self):
        expr = self.strategy.convert_expression_to_fhirpath(
            TriccOperation(TriccOperator.EQUAL, [TriccReference("note_txt"), TriccStatic("abc")])
        )
        self.assertEqual(
            expr,
            "%resource.item.where(linkId='note_txt').answer.where($this.exists()).value = 'abc'",
        )

    def test_numeric_equality_keeps_decimal_literal(self):
        expr = self.strategy.convert_expression_to_fhirpath(
            TriccOperation(TriccOperator.EQUAL, [TriccReference("age"), TriccStatic(5)])
        )
        self.assertTrue(expr.endswith(".value = 5.0"), expr)


class TestSelectOperandEqualityExport(unittest.TestCase):
    """End-to-end: the three shapes as an author writes them in a diagram."""

    @classmethod
    def setUpClass(cls):
        from tests.helpers import load_yaml_project

        project = load_yaml_project("tests/data/yaml/select_operand_equality.yaml")
        strategy = FHIRStrategy(project, "/tmp/fhir_select_operand_export_out")
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

    def test_yesno_relevance_compares_boolean(self):
        expr = self._enable_when("days_to_visit")
        self.assertIsNotNone(expr)
        self.assertIn(".value = true", expr)
        self.assertNotIn("'yes'", expr)

    def test_choice_relevance_uses_membership(self):
        expr = self._enable_when("km_to_home")
        self.assertIsNotNone(expr)
        self.assertIn(".answer.where($this.value.code = 'home_visit').exists()", expr)

    def test_repeated_value_relevance_uses_membership(self):
        expr = self._enable_when("visits_planned")
        self.assertIsNotNone(expr)
        self.assertIn(".answer.where($this.value.code = 'home_visit').exists()", expr)
        self.assertNotIn(".answer = ", expr)


if __name__ == "__main__":
    unittest.main()
