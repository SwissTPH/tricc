"""The output walk must not re-walk a node's successors once it has passed it.

An output pass returns `True` for a node it has already emitted — FHIR does so deliberately, so a
node re-stashed on a fan-in is not emitted twice. The walker used to read that as permission to
walk the successors again, so a page whose nodes are each reachable by two edges cost one walk per
*path*: a 26-level navigation "goto ladder" produced 178 322 entries for a single node and neither
the XLSForm nor the FHIR export ever finished.

See fix/20260909-output-walk-path-explosion.md.

Run with:
    python -m pytest tests/test_output_walk_reentry.py -v
"""

import tempfile
import unittest
from collections import Counter

import tricc_oo.visitors.tricc as tricc_visitor
from tricc_oo.models.calculate import TriccNodeActivityStart
from tricc_oo.models.ordered_set import OrderedSet
from tricc_oo.models.tricc import (
    TriccNodeActivity,
    TriccNodeMainStart,
    TriccNodeNote,
)
from tricc_oo.strategies.output.fhir_form import FHIRStrategy
from tricc_oo.strategies.output.xls_form import XLSFormStrategy
from tricc_oo.visitors.tricc import (
    stashed_node_func,
    walktrhough_tricc_node_processed_stached,
)

from tests.helpers import load_yaml_project
from tests.test_nav_ladder_relevance import FIXTURE as LADDER_FIXTURE, LEVELS


def _diamond():
    """main start → a, b → join → tail: `join` is reached by two paths."""
    main_start = TriccNodeMainStart(id="s", name="start", label="Start", process="main")
    activity = TriccNodeActivity(id="act", name="act", label="Act", root=main_start)
    main_start.activity = activity
    main_start.group = activity
    activity.activity = activity
    activity.group = activity

    def note(node_id, name):
        n = TriccNodeNote(id=node_id, name=name, label=name, activity=activity)
        n.activity = activity
        n.group = activity
        return n

    a, b, join, tail = note("a", "a"), note("b", "b"), note("j", "join"), note("t", "tail")
    for branch in (a, b):
        main_start.next_nodes.add(branch)
        branch.prev_nodes.add(main_start)
        branch.next_nodes.add(join)
        join.prev_nodes.add(branch)
    join.next_nodes.add(tail)
    tail.prev_nodes.add(join)
    return main_start, join, tail


def _export(strategy_cls, project):
    """Run a full output pass, counting walk entries per node."""
    original = walktrhough_tricc_node_processed_stached
    per_node = Counter()

    def counting(node, callback, processed_nodes, stashed_nodes, path_len, *args, **kwargs):
        per_node[getattr(node, "name", None) or node.id] += 1
        return original(node, callback, processed_nodes, stashed_nodes, path_len, *args, **kwargs)

    patched = [tricc_visitor]
    for module_name in ("tricc_oo.strategies.output.xls_form", "tricc_oo.strategies.output.fhir_form"):
        import importlib

        module = importlib.import_module(module_name)
        if hasattr(module, "walktrhough_tricc_node_processed_stached"):
            patched.append(module)
    for module in patched:
        module.walktrhough_tricc_node_processed_stached = counting
    try:
        with tempfile.TemporaryDirectory() as out_dir:
            strategy_cls(project, out_dir).execute()
    finally:
        for module in patched:
            module.walktrhough_tricc_node_processed_stached = original
    return per_node


class TestWalkerReentryContract(unittest.TestCase):
    def test_successors_are_walked_once_when_a_node_is_reached_twice(self):
        """Output passes use the stashed (non-recursive) walk, where a processed node is re-entered.

        The recursive walk already skips a processed successor
        (``walkthrough_tricc_next_nodes``); the stashed one does not, which is where the cost
        multiplied.
        """
        main_start, join, tail = _diamond()
        seen = Counter()
        processed_nodes = OrderedSet()

        def callback(node, processed_nodes=None, **kwargs):
            seen[getattr(node, "name", None)] += 1
            # what an output pass does: already emitted, but nothing is blocking either
            return True

        stashed_node_func(
            main_start, callback, processed_nodes=processed_nodes, stashed_nodes=OrderedSet()
        )

        self.assertGreaterEqual(
            seen["join"], 2, "the join is reached by both branches, so the callback must see it twice"
        )
        self.assertEqual(
            seen["tail"], 1, "the join's successor must be walked once, not once per incoming path"
        )
        self.assertIn(join, processed_nodes)
        self.assertIn(tail, processed_nodes)


class TestLadderExportWalkCost(unittest.TestCase):
    """A goto ladder must not cost one walk per path through it, in either exporter."""

    def _assert_bounded(self, per_node):
        self.assertTrue(per_node, "no walk entries recorded")
        worst_name, worst = per_node.most_common(1)[0]
        self.assertLess(
            worst,
            20 * LEVELS,
            f"{worst_name} was walked {worst} times: the export is re-walking paths",
        )

    def test_xlsform_export(self):
        self._assert_bounded(_export(XLSFormStrategy, load_yaml_project(LADDER_FIXTURE)))

    def test_fhir_export(self):
        self._assert_bounded(_export(FHIRStrategy, load_yaml_project(LADDER_FIXTURE)))


if __name__ == "__main__":
    unittest.main()
