"""get_node_expression builds each shared predecessor once per top-level call.

Regression test for fix/20261006-expression-memoisation.md: a navigation "ladder", where
every step merges two paths that both come from the previous step, used to re-expand the
previous step once per path, doubling the work at every step until the recursion guard
tripped.
"""

import unittest
from unittest import mock

from tricc_oo.models.base import TriccOperation
from tricc_oo.models.calculate import (
    TriccNodeActivityStart,
    TriccNodeCalculate,
    TriccNodeDisplayBridge,
    TriccNodeRhombus,
)
from tricc_oo.models.ordered_set import OrderedSet
from tricc_oo.models.tricc import TriccNodeActivity
from tricc_oo.visitors import tricc
from tricc_oo.visitors.loop_guard import RecursionGuard

# 2^30 paths: hopeless without memoisation, a few hundred calls with it
LADDER_STEPS = 30


def _link(prev, node):
    prev.next_nodes.add(node)
    node.prev_nodes.add(prev)


def _ladder(steps):
    """Build a navigation ladder of ``steps`` decisions and return the last merge.

    Each decision ``rhombus_k`` follows the previous merge (its ``path``). Its "Yes"
    branch goes through ``goto_k`` and its "continue" branch goes straight on, and both
    meet again in the display bridge ``step_k`` -- the shape the Navigation page of a
    dispatching project produces. Every step therefore reaches the previous one along
    two paths.
    """
    root = TriccNodeActivityStart(id="start", name="start", label="start")
    activity = TriccNodeActivity(id="act", name="act", label="act", root=root)
    root.activity = activity
    previous = root
    for step in range(steps):
        flag = TriccNodeCalculate(id=f"flag_{step}", name=f"flag_{step}", label=f"flag {step}", activity=activity)
        rhombus = TriccNodeRhombus(
            id=f"rhombus_{step}", name=f"rhombus_{step}", label=f"rhombus {step}",
            activity=activity, reference=[flag], path=previous,
        )
        goto = TriccNodeCalculate(id=f"goto_{step}", name=f"goto_{step}", label=f"goto {step}", activity=activity)
        merge = TriccNodeDisplayBridge(id=f"step_{step}", name=f"step_{step}", label=f"step {step}", activity=activity)
        _link(previous, rhombus)
        _link(rhombus, goto)
        _link(goto, merge)
        _link(rhombus, merge)
        previous = merge
    return previous


class TestExpressionMemoisation(unittest.TestCase):
    def test_ladder_of_merging_paths_is_expanded_linearly(self):
        last = _ladder(LADDER_STEPS)
        # tight budget: linear work fits easily, the old 2^steps expansion cannot
        guard = RecursionGuard("get_node_expression", max_calls=20 * LADDER_STEPS, max_depth=10 * LADDER_STEPS)
        with mock.patch.object(tricc, "EXPRESSION_GUARD", guard):
            tricc.get_node_expression(last, processed_nodes=OrderedSet())
        self.assertEqual(guard.path, [])

    def test_cache_does_not_outlive_the_top_level_call(self):
        last = _ladder(3)
        tricc.get_node_expression(last, processed_nodes=OrderedSet())
        self.assertIsNone(tricc._EXPRESSION_CACHE)

    def test_cached_results_are_not_shared_between_callers(self):
        last = _ladder(3)
        processed = OrderedSet()
        with mock.patch.object(tricc, "_EXPRESSION_CACHE", {}):
            first = tricc.get_node_expression(last, processed_nodes=processed, is_prev=True)
            second = tricc.get_node_expression(last, processed_nodes=processed, is_prev=True)
        self.assertIsInstance(first, TriccOperation)
        self.assertEqual(first, second)
        self.assertIsNot(first, second)
        self.assertIsNot(first.reference, second.reference)


if __name__ == "__main__":
    unittest.main()
