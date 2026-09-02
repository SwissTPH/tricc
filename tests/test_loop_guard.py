"""Tests for the loop / recursion guards that abort a stuck conversion."""

import os
import unittest
from unittest import mock

from tricc_oo.models.calculate import TriccNodeActivityStart, TriccNodeCalculate
from tricc_oo.models.ordered_set import OrderedSet
from tricc_oo.models.tricc import TriccNodeActivity
from tricc_oo.visitors import tricc
from tricc_oo.visitors.loop_guard import (
    DEFAULT_MAX_EXPRESSION_CALLS,
    DEFAULT_MAX_EXPRESSION_DEPTH,
    LoopGuard,
    RecursionGuard,
    TriccLoopError,
    describe_node,
)


class FakeNode:
    """Minimal stand-in for a TRICC node (guards only need get_name / activity)."""

    def __init__(self, name, activity=None):
        self.name = name
        self.activity = activity

    def get_name(self):
        return self.name


class TestLoopGuard(unittest.TestCase):
    def test_stays_quiet_within_budget(self):
        guard = LoopGuard("test_loop", max_iterations=5)
        for _ in range(5):
            guard.tick()
        self.assertEqual(guard.iterations, 5)

    def test_trips_past_budget(self):
        guard = LoopGuard("test_loop", max_iterations=3)
        with self.assertRaises(TriccLoopError) as ctx:
            for _ in range(10):
                guard.tick()
        self.assertIn("test_loop ran 4 iterations", str(ctx.exception))
        self.assertIn("TRICC_MAX_LOOP_ITERATIONS", str(ctx.exception))

    def test_context_only_evaluated_on_trip(self):
        calls = []

        def context():
            calls.append(1)
            return ["diagnostic line"]

        guard = LoopGuard("test_loop", max_iterations=1)
        guard.tick(context)
        self.assertEqual(calls, [])
        with self.assertRaises(TriccLoopError):
            guard.tick(context)
        self.assertEqual(calls, [1])

    def test_budget_read_from_environment(self):
        with mock.patch.dict(os.environ, {"TRICC_MAX_LOOP_ITERATIONS": "2"}):
            guard = LoopGuard("test_loop")
        self.assertEqual(guard.max_iterations, 2)

    def test_invalid_environment_budget_falls_back_to_default(self):
        with mock.patch.dict(os.environ, {"TRICC_MAX_EXPRESSION_DEPTH": "not-a-number"}):
            guard = RecursionGuard("test_recursion")
        self.assertEqual(guard.max_depth, DEFAULT_MAX_EXPRESSION_DEPTH)
        self.assertEqual(guard.max_calls, DEFAULT_MAX_EXPRESSION_CALLS)


class TestRecursionGuard(unittest.TestCase):
    def test_trips_on_depth(self):
        guard = RecursionGuard("test_recursion", max_depth=4, max_calls=1000)

        def recurse(depth):
            with guard(FakeNode(f"node_{depth}")):
                recurse(depth + 1)

        with self.assertRaises(TriccLoopError) as ctx:
            recurse(0)
        self.assertIn("recursed 5 levels deep", str(ctx.exception))
        self.assertIn("TRICC_MAX_EXPRESSION_DEPTH", str(ctx.exception))

    def test_trips_on_call_count_when_depth_stays_low(self):
        """An exponential re-expansion of a shallow graph must be caught too."""
        guard = RecursionGuard("test_recursion", max_depth=100, max_calls=20)

        def fan_out(depth):
            with guard(FakeNode(f"node_{depth}")):
                if depth < 8:
                    fan_out(depth + 1)
                    fan_out(depth + 1)

        with self.assertRaises(TriccLoopError) as ctx:
            fan_out(0)
        self.assertIn("recursive calls", str(ctx.exception))
        self.assertIn("TRICC_MAX_EXPRESSION_CALLS", str(ctx.exception))

    def test_call_budget_resets_after_top_level_call(self):
        guard = RecursionGuard("test_recursion", max_depth=10, max_calls=4)
        for _ in range(10):
            with guard(FakeNode("node")):
                with guard(FakeNode("child")):
                    pass
        self.assertEqual(guard.calls, 0)
        self.assertEqual(guard.path, [])

    def test_path_unwinds_on_unrelated_exception(self):
        guard = RecursionGuard("test_recursion", max_depth=10, max_calls=10)
        with self.assertRaises(ValueError):
            with guard(FakeNode("node")):
                raise ValueError("boom")
        self.assertEqual(guard.path, [])
        self.assertEqual(guard.calls, 0)

    def test_state_reset_after_trip(self):
        guard = RecursionGuard("test_recursion", max_depth=2, max_calls=100)

        def recurse(depth):
            with guard(FakeNode(f"node_{depth}")):
                recurse(depth + 1)

        with self.assertRaises(TriccLoopError):
            recurse(0)
        self.assertEqual(guard.path, [])
        self.assertEqual(guard.calls, 0)

    def test_diagnostics_report_revisited_nodes(self):
        guard = RecursionGuard("test_recursion", max_depth=3, max_calls=100)
        looping = FakeNode("looping_node")

        def recurse():
            with guard(looping):
                recurse()

        with mock.patch("tricc_oo.visitors.loop_guard.logger") as logger:
            with self.assertRaises(TriccLoopError):
                recurse()
        logged = "\n".join(str(call.args[0]) for call in logger.critical.call_args_list)
        self.assertIn("nodes revisited on that path", logged)
        self.assertIn("looping_node", logged)
        self.assertIn("stack trace at the moment the guard tripped", logged)


class TestGuardsWiredIntoThePipeline(unittest.TestCase):
    """The guards must actually cover the two loops that used to hang a conversion."""

    @staticmethod
    def _looping_activity():
        """Two calculates that depend on each other: an unresolvable dependency loop."""
        root = TriccNodeActivityStart(id="start", name="start", label="start")
        activity = TriccNodeActivity(id="act", name="act", label="act", root=root)
        root.activity = activity
        first = TriccNodeCalculate(id="a", name="calc_a", label="A", activity=activity)
        second = TriccNodeCalculate(id="b", name="calc_b", label="B", activity=activity)
        first.prev_nodes = OrderedSet([second])
        second.prev_nodes = OrderedSet([first])
        first.next_nodes = OrderedSet([second])
        second.next_nodes = OrderedSet([first])
        return activity, first

    def test_get_node_expression_aborts_on_dependency_loop(self):
        _activity, node = self._looping_activity()
        guard = RecursionGuard("get_node_expression", max_depth=8, max_calls=1000)
        with mock.patch.object(tricc, "EXPRESSION_GUARD", guard):
            with self.assertRaises(TriccLoopError):
                tricc.get_node_expression(node, processed_nodes=OrderedSet())
        self.assertEqual(guard.path, [])

    def test_stashed_node_func_aborts_when_the_stash_never_drains(self):
        _activity, node = self._looping_activity()

        def never_ready(in_node, **kwargs):
            return False

        with mock.patch.dict(os.environ, {"TRICC_MAX_LOOP_ITERATIONS": "3"}):
            with self.assertRaises(TriccLoopError) as ctx:
                tricc.stashed_node_func(node, never_ready)
        self.assertIn("stashed_node_func(never_ready)", str(ctx.exception))


class TestDescribeNode(unittest.TestCase):
    def test_includes_class_and_name(self):
        self.assertEqual(describe_node(FakeNode("bp_status")), "FakeNode::bp_status")

    def test_includes_activity_context(self):
        activity = FakeNode("Navigation")
        activity.instance = 2
        node = FakeNode("bp_status", activity=activity)
        self.assertEqual(describe_node(node), "FakeNode::Navigation:2|bp_status")

    def test_survives_a_broken_node(self):
        class Broken:
            def get_name(self):
                raise RuntimeError("half-built node")

        self.assertIn("Broken", describe_node(Broken()))
        self.assertEqual(describe_node(None), "None")


if __name__ == "__main__":
    unittest.main()
