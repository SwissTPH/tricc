"""Regression tests for output-pass calculate derivation.

`generate_calculate` derives a value for nodes with no authored expression by
calling `get_node_expressions`, which computes nothing unless the node is ready
in *that pass*. The pass does not retry, so nodes reached before their prevs used
to fall back to `TriccStatic(True)` — a path condition silently exported as a
constant `true` (45 of the 71 defines in the etat OpenSRP library).

Now: the node is deferred (stashed and revisited), an underivable expression stays
absent instead of becoming a constant, ODK gets its `1` default at serialization
time, and one CQL define is emitted per name rather than one per visit.

See fix/20260821-output-pass-calculate-readiness.md.

Run with:
    python -m pytest tests/test_output_pass_readiness.py -v
"""

import unittest
from unittest.mock import MagicMock

from tricc_oo.models.base import TriccNodeType
from tricc_oo.models.calculate import TriccNodeCalculate
from tricc_oo.models.tricc import TriccNodeActivity, TriccNodeMainStart, TriccNodeSelectYesNo
from tricc_oo.serializers.xls_form import ODK_TRICC_TYPE_MAP, _empty_calculation_default
from tricc_oo.strategies.output.fhir_form import FHIRStrategy
from tricc_oo.models.ordered_set import OrderedSet
from tricc_oo.visitors.tricc import get_node_expressions


def _make_strategy():
    project = MagicMock()
    project.start_pages = {}
    project.pages = {}
    project.code_systems = {}
    strategy = FHIRStrategy(project, "/tmp/fhir_readiness_test_out")
    strategy.questionnaires["main"] = {
        "resourceType": "Questionnaire",
        "item": [{"linkId": "flag", "type": "boolean"}],
    }
    return strategy


def _unready_calculate():
    """A calculate whose prev has not been visited by the current pass."""
    activity = TriccNodeActivity(
        id="a1", name="act", label="Act", root=TriccNodeMainStart(id="s1", name="s", label="S")
    )
    prev = TriccNodeSelectYesNo(
        id="q1", name="asked", label="Asked?", activity=activity, list_name="yes_no"
    )
    node = TriccNodeCalculate(id="c1", name="flag", label="Flag", activity=activity)
    node.prev_nodes.add(prev)
    return node, prev


class TestUnreadyNodesAreDeferred(unittest.TestCase):
    def test_generate_calculate_defers_instead_of_guessing(self):
        strategy = _make_strategy()
        node, _prev = _unready_calculate()

        deferred = strategy.generate_calculate(node, processed_nodes=OrderedSet(), process="main")

        self.assertFalse(deferred, "an unready node must be stashed, not resolved to a constant")
        self.assertIsNone(getattr(node, "expression", None))
        item = strategy.questionnaires["main"]["item"][0]
        self.assertNotIn("extension", item)
        self.assertEqual(strategy.cql_defines, {})

    def test_last_attempt_stops_deferring(self):
        """`warn` marks the attempt before stashed_node_func gives up (it exit(1)s)."""
        strategy = _make_strategy()
        node, _prev = _unready_calculate()

        result = strategy.generate_calculate(
            node, processed_nodes=OrderedSet(), process="main", warn=True
        )

        self.assertTrue(result)


class TestNoConstantSubstitution(unittest.TestCase):
    def test_underivable_expression_stays_absent(self):
        node, _prev = _unready_calculate()

        expression = get_node_expressions(node, OrderedSet(), process="main")

        self.assertIsNone(expression, "must not become TriccStatic(True)")


class TestOdkCalculationDefault(unittest.TestCase):
    def test_calculate_row_defaults_to_one(self):
        node = TriccNodeCalculate(id="c1", name="flag", label="Flag")
        self.assertEqual(_empty_calculation_default(node, "calculation"), "1")

    def test_other_columns_and_question_rows_stay_empty(self):
        calc = TriccNodeCalculate(id="c1", name="flag", label="Flag")
        question = TriccNodeSelectYesNo(id="q1", name="asked", label="Asked?", list_name="yes_no")
        self.assertEqual(_empty_calculation_default(calc, "relevance"), "")
        self.assertEqual(_empty_calculation_default(question, "calculation"), "")

    def test_every_calculate_tricc_type_is_covered(self):
        """The default keys off the ODK type map, so all calculate-ish types get it."""
        for tricc_type, odk_type in ODK_TRICC_TYPE_MAP.items():
            if odk_type != "calculate":
                continue
            node = TriccNodeCalculate(id="c", name="n", label="L")
            node.tricc_type = tricc_type
            self.assertEqual(_empty_calculation_default(node, "calculation"), "1", tricc_type)


class TestCqlDefinesAreKeyedByName(unittest.TestCase):
    def test_revisiting_a_node_does_not_duplicate_its_define(self):
        strategy = _make_strategy()
        for _ in range(3):
            strategy._record_cql_define("main", "Calc_flag", "Helper.GetObservationValue('flag')")
        self.assertEqual(
            strategy.cql_defines["main"], ["define Calc_flag: Helper.GetObservationValue('flag')"]
        )

    def test_a_changed_body_replaces_the_previous_definition(self):
        strategy = _make_strategy()
        strategy._record_cql_define("main", "Calc_flag", "true")
        strategy._record_cql_define("main", "Calc_flag", "asked = 'true'")
        self.assertEqual(strategy.cql_defines["main"], ["define Calc_flag: asked = 'true'"])

    def test_distinct_names_are_all_kept_in_order(self):
        strategy = _make_strategy()
        strategy._record_cql_define("main", "Calc_a", "1")
        strategy._record_cql_define("main", "Calc_b", "2")
        strategy._record_cql_define("main", "Calc_a", "1")
        self.assertEqual(strategy.cql_defines["main"], ["define Calc_a: 1", "define Calc_b: 2"])


if __name__ == "__main__":
    unittest.main()
