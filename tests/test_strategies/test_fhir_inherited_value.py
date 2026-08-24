"""Regression tests for GET_INHERITED_VALUE in FHIRStrategy / OpenSRPStrategy.

The transformation engine merges the versions of a multi-path question or
calculate with ``GET_INHERITED_VALUE``. ODK/CHT serialise that as ``coalesce``;
openSRP needs different handling because only versions captured in the *current*
Questionnaire are reachable from ``%resource``, and out-of-process versions are
already prefilled by the encounter dedup ``initialExpression``.

See fix/20260820-opensrp-inherited-value.md.

Run with:
    python -m pytest tests/test_strategies/test_fhir_inherited_value.py -v
"""

import types
import unittest
from unittest.mock import MagicMock

from tricc_oo.converters.tricc_to_xls_form import get_export_name
from tricc_oo.models.base import TriccOperation, TriccOperator
from tricc_oo.models.calculate import TriccNodeCalculate, TriccNodePopulate
from tricc_oo.models.tricc import TriccNodeInteger, TriccNodeSelectOne, TriccNodeSelectOption
from tricc_oo.strategies.output.fhir_form import (
    SDC_EXT_CALCULATED_EXPR,
    SDC_EXT_INITIAL_EXPR,
    FHIRStrategy,
)

ENABLE_WHEN = "http://hl7.org/fhir/uv/sdc/StructureDefinition/sdc-questionnaire-enableWhenExpression"


def _make_strategy():
    project = MagicMock()
    project.start_pages = {}
    project.pages = {}
    project.code_systems = {}
    return FHIRStrategy(project, "/tmp/fhir_inherited_value_test_out")


def _item(link_id, item_type="decimal"):
    return {"linkId": link_id, "type": item_type}


def _versions(cls, name, count, **kwargs):
    """``count`` versions of the same concept, newest last in the returned list."""
    out = []
    for i in range(1, count + 1):
        out.append(
            cls(id=f"{name}{i}", name=name, label=name, last=False, version=i, path_len=10 * i, **kwargs)
        )
    return out


def _carrier(link_id, relevance):
    """Minimal node carrying a relevance expression (no options, no activity)."""
    return types.SimpleNamespace(
        tricc_type="note",
        export_name=link_id,
        relevance=relevance,
        activity=None,
        options=None,
    )


def _extension(item, url):
    return [e for e in item.get("extension", []) if e.get("url") == url]


class TestInheritedValueInForm(unittest.TestCase):
    """R1: versions captured in this Questionnaire stay live FHIRPath."""

    def test_choice_versions_union_newest_first(self):
        strategy = _make_strategy()
        v1, v2 = _versions(TriccNodeSelectOne, "fever", 2, list_name="fever")
        option = TriccNodeSelectOption(id="o1", name="yes", label="Yes", list_name="fever", select=v2)
        relevance = TriccOperation(
            TriccOperator.SELECTED,
            [TriccOperation(TriccOperator.GET_INHERITED_VALUE, [v2, v1]), option],
        )
        carrier = _carrier("note1", relevance)
        strategy.questionnaires["main"] = {
            "resourceType": "Questionnaire",
            "item": [
                _item(get_export_name(v1), "choice"),
                _item(get_export_name(v2), "choice"),
                _item("note1", "display"),
            ],
        }

        strategy.generate_relevance(carrier)

        item = strategy._find_item_by_link_id(strategy.questionnaires["main"]["item"], "note1")
        expr = _extension(item, ENABLE_WHEN)[0]["valueExpression"]["expression"]
        self.assertEqual(expr.count("%resource.item.where(linkId="), 2)
        self.assertNotIn("repeat(item)", expr)
        # newest version first, and only the winning answer is tested
        self.assertLess(expr.index("linkId='fever_Vv_2'"), expr.index("linkId='fever_Vv_1'"))
        self.assertIn(".where($this.exists()).first()", expr)
        self.assertTrue(expr.endswith(".where(value.code = 'yes').exists()"), expr)

    def test_scalar_comparison_keeps_value_suffix(self):
        strategy = _make_strategy()
        v1, v2 = _versions(TriccNodeInteger, "weight", 2)
        calc = TriccNodeCalculate(id="c1", name="heavy", label="Heavy")
        calc.expression_reference = TriccOperation(
            TriccOperator.MORE,
            [TriccOperation(TriccOperator.GET_INHERITED_VALUE, [v2, v1]), 5],
        )
        strategy.questionnaires["main"] = {
            "resourceType": "Questionnaire",
            "item": [
                _item(get_export_name(v1), "integer"),
                _item(get_export_name(v2), "integer"),
                _item("heavy"),
            ],
        }

        strategy.generate_calculate(calc)

        item = strategy._find_item_by_link_id(strategy.questionnaires["main"]["item"], "heavy")
        expr = _extension(item, SDC_EXT_CALCULATED_EXPR)[0]["valueExpression"]["expression"]
        self.assertIn(".where($this.exists()).first().value", expr)
        self.assertTrue(expr.endswith(".toDecimal() > 5.0"), expr)
        self.assertEqual(strategy.cql_defines, {})

    def test_out_of_process_version_is_dropped(self):
        strategy = _make_strategy()
        v1, v2, v3 = _versions(TriccNodeInteger, "weight", 3)
        calc = TriccNodeCalculate(id="c1", name="heavy", label="Heavy")
        calc.expression_reference = TriccOperation(
            TriccOperator.MORE,
            [TriccOperation(TriccOperator.GET_INHERITED_VALUE, [v3, v2, v1]), 5],
        )
        # v3 lives in another process' Questionnaire: unreachable from %resource
        strategy.questionnaires["main"] = {
            "resourceType": "Questionnaire",
            "item": [
                _item(get_export_name(v1), "integer"),
                _item(get_export_name(v2), "integer"),
                _item("heavy"),
            ],
        }

        strategy.generate_calculate(calc)

        item = strategy._find_item_by_link_id(strategy.questionnaires["main"]["item"], "heavy")
        expr = _extension(item, SDC_EXT_CALCULATED_EXPR)[0]["valueExpression"]["expression"]
        self.assertNotIn(get_export_name(v3), expr)
        self.assertIn(get_export_name(v2), expr)
        self.assertIn(get_export_name(v1), expr)

    def test_single_version_needs_no_union(self):
        strategy = _make_strategy()
        (v1,) = _versions(TriccNodeInteger, "weight", 1)
        calc = TriccNodeCalculate(id="c1", name="heavy", label="Heavy")
        calc.expression_reference = TriccOperation(
            TriccOperator.MORE,
            [TriccOperation(TriccOperator.GET_INHERITED_VALUE, [v1]), 5],
        )
        strategy.questionnaires["main"] = {
            "resourceType": "Questionnaire",
            "item": [_item(get_export_name(v1), "integer"), _item("heavy")],
        }

        strategy.generate_calculate(calc)

        item = strategy._find_item_by_link_id(strategy.questionnaires["main"]["item"], "heavy")
        expr = _extension(item, SDC_EXT_CALCULATED_EXPR)[0]["valueExpression"]["expression"]
        self.assertNotIn("|", expr)
        self.assertIn(".where($this.exists()).first().value", expr)
        self.assertTrue(expr.endswith(".toDecimal() > 5.0"), expr)

    def test_own_item_operand_becomes_this(self):
        """R1b: the item carrying the expression reads its own value as $this."""
        strategy = _make_strategy()
        (v1,) = _versions(TriccNodeInteger, "weight", 1)
        calc = TriccNodeCalculate(id="c1", name="weight_final", label="Weight")
        calc.expression_reference = TriccOperation(
            TriccOperator.GET_INHERITED_VALUE, [calc, v1]
        )
        strategy.questionnaires["main"] = {
            "resourceType": "Questionnaire",
            "item": [_item(get_export_name(v1), "integer"), _item("weight_final", "integer")],
        }

        strategy.generate_calculate(calc)

        item = strategy._find_item_by_link_id(strategy.questionnaires["main"]["item"], "weight_final")
        expr = _extension(item, SDC_EXT_CALCULATED_EXPR)[0]["valueExpression"]["expression"]
        self.assertIn("$this |", expr)
        self.assertNotIn("linkId='weight_final'", expr)


class TestInheritedValueOutOfProcess(unittest.TestCase):
    """R3 / R4: nothing reachable in this Questionnaire -> CQL dedup, never a crash."""

    def test_calculate_falls_back_to_cql_initial_expression(self):
        strategy = _make_strategy()
        v1, v2 = _versions(TriccNodePopulate, "fever", 2)
        calc = TriccNodeCalculate(id="c1", name="fever_any", label="Fever any")
        calc.expression_reference = TriccOperation(TriccOperator.GET_INHERITED_VALUE, [v2, v1])
        # neither version is an item here (they were answered in another process)
        strategy.questionnaires["main"] = {
            "resourceType": "Questionnaire",
            "item": [_item("fever_any")],
        }

        strategy.generate_calculate(calc)

        item = strategy._find_item_by_link_id(strategy.questionnaires["main"]["item"], "fever_any")
        self.assertEqual(_extension(item, SDC_EXT_CALCULATED_EXPR), [])
        self.assertEqual(len(_extension(item, SDC_EXT_INITIAL_EXPR)), 1)
        defines = strategy.cql_defines["main"]
        self.assertEqual(len(defines), 1)
        # concept-keyed Helper access: both versions collapse to one accessor
        self.assertNotIn("Coalesce", defines[0])

    def test_relevance_does_not_abort_the_export(self):
        strategy = _make_strategy()
        v1, v2 = _versions(TriccNodeSelectOne, "fever", 2, list_name="fever")
        option = TriccNodeSelectOption(id="o1", name="yes", label="Yes", list_name="fever", select=v2)
        relevance = TriccOperation(
            TriccOperator.SELECTED,
            [TriccOperation(TriccOperator.GET_INHERITED_VALUE, [v2, v1]), option],
        )
        carrier = _carrier("note1", relevance)
        strategy.questionnaires["main"] = {
            "resourceType": "Questionnaire",
            "item": [_item("note1", "display")],
        }

        self.assertTrue(strategy.generate_relevance(carrier))

        item = strategy._find_item_by_link_id(strategy.questionnaires["main"]["item"], "note1")
        self.assertEqual(_extension(item, ENABLE_WHEN), [])


class TestInheritedValueCqlHandler(unittest.TestCase):
    """R4 in isolation."""

    def test_identical_operands_are_deduplicated(self):
        strategy = _make_strategy()
        accessor = "Helper.GetObservationValue('fever')"
        self.assertEqual(
            strategy.tricc_operation_get_inherited_value([accessor, accessor, accessor]),
            accessor,
        )

    def test_distinct_operands_still_coalesce(self):
        strategy = _make_strategy()
        self.assertEqual(
            strategy.tricc_operation_get_inherited_value(["A", "B"]),
            "Coalesce(A, B)",
        )


if __name__ == "__main__":
    unittest.main()
