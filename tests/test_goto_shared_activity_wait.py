"""Regression test for the role of the injected Wait node when a *single* nested
activity instance is called from two independent places in the diagram.

Scenario (see docs/troubleshooting.md, "Repeated / shared activity instances"):

    Act A: node_b (gated by trigger_a) -> goto module_c (instance=1) -> node_c
    Act D: node_e (gated by trigger_d) -> goto module_c (instance=1) -> node_f

Both gotos target the *same* instance number of the *same* module, so
`TriccNodeActivity.make_instance` returns the identical cached activity object for
both call sites (see tricc_oo/models/tricc.py, `make_instance`'s `self.instances`
cache) - module_c is one shared node in the graph, entered from two places.

The Wait node that `inject_bridge_path`/`get_activity_wait` insert around every goto
with outgoing edges (tricc_oo/converters/xml_to_tricc.py::get_nodes) exists precisely
so that node_c's and node_f's relevance stay tied to *their own* caller (trigger_a /
trigger_d respectively) rather than to "module_c has been entered", which either
caller alone would satisfy. If node_c/node_f were wired as direct next_nodes of the
shared module_c activity object instead of going through their own caller-specific
Wait, module_c completing via *either* caller would make *both* node_c and node_f
relevant - i.e. Act D alone would leak node_c, and Act A alone would leak node_f.

This also guards the fix in `walktrhough_tricc_node_processed_stached` that schedules
a TriccNodeActivity's own `next_nodes` once its content is fully processed (added to
fix goto_instance_multi_caller): that fix only touches `next_nodes` that hang directly
off the Activity node. When the Wait is in place - as it always is for goto-authored
"call, then continue" diagrams - module_c's own `next_nodes` stays empty and the
continuation is scheduled independently for each caller via that caller's Wait
instead, so the fix cannot reintroduce the cross-caller leak this test guards against.
"""

import unittest
from pathlib import Path

import yaml as pyyaml

from tricc_oo.models.ordered_set import OrderedSet
from tricc_oo.models.tricc import TriccProject, TriccNodeGoTo
from tricc_oo.strategies.input.drawio import DrawioStrategy
from tricc_oo.strategies.input.yaml import YamlActivity, YamlStrategy
from tricc_oo.visitors.tricc import (
    get_activity_wait,
    inject_bridge_path,
    load_calculate,
    remove_prev_next,
    set_prev_next_node,
    stashed_node_func,
)

DATA = Path(__file__).parent / "data" / "yaml"


def _inject_goto_bridge_and_wait(page):
    """Mirror the goto handling in xml_to_tricc.get_nodes (drawio-only preprocessing
    that the lightweight YAML test strategy skips).

    In the real draw.io pipeline this runs inside create_activity, before
    prev_nodes/next_nodes are wired from edges, so the helpers below only need to
    rewrite `page.edges` (they use edge_only=True throughout). The YAML strategy
    used by this test already wired prev_nodes/next_nodes from the *original*
    edges when it built the activity, so after rewriting the edges we also patch
    the pointer sets by hand (remove the direct link the bridge replaces, add the
    bridge/wait links) to reach the same end state a draw.io-sourced diagram would
    have - this patch-up is a test-harness-ordering detail, not new production
    logic.
    """
    for node in list(page.nodes.values()):
        if isinstance(node, TriccNodeGoTo) and getattr(node, "instance", 1) != -1:
            prev_nodes_before = list(node.prev_nodes)
            path = inject_bridge_path(node, page.nodes)
            if path:
                page.nodes[path.id] = path
                for prev_node in prev_nodes_before:
                    remove_prev_next(prev_node, node, page)
                    set_prev_next_node(prev_node, path, edge_only=False, activity=page)
                set_prev_next_node(path, node, edge_only=False, activity=page)
            next_nodes_id = [e.target for e in page.edges if e.source == node.id]
            if next_nodes_id:
                calc = get_activity_wait(path, [node], next_nodes_id, node, edge_only=True)
                page.nodes[calc.id] = calc
                set_prev_next_node(path, calc, edge_only=False, activity=page)
                for goto_next_node in next_nodes_id:
                    goto_next_obj = page.nodes[goto_next_node]
                    remove_prev_next(node, goto_next_obj, page)
                    set_prev_next_node(calc, goto_next_obj, edge_only=False, activity=page)


def _build_and_process(name: str):
    path = DATA / name
    content = path.read_text(encoding="utf-8")
    strategy = YamlStrategy(str(path))
    project = TriccProject()
    for loaded in pyyaml.safe_load_all(content):
        if not loaded:
            continue
        activity = strategy._build_activity(YamlActivity(**loaded), project)
        if activity is not None:
            project.pages[activity.id] = activity
            strategy._assign_start_page(activity, project)

    parent = project.start_pages.get("main")

    for page in project.pages.values():
        _inject_goto_bridge_and_wait(page)

    temp = DrawioStrategy.__new__(DrawioStrategy)
    temp.processes = strategy.processes
    temp.linking_nodes = DrawioStrategy.linking_nodes.__get__(temp, DrawioStrategy)
    temp.walkthrough_goto_node = DrawioStrategy.walkthrough_goto_node.__get__(temp, DrawioStrategy)
    temp.linking_nodes(parent.root, parent, project.pages, OrderedSet(), [])

    stashed_node_func(
        parent.root,
        load_calculate,
        used_calculates={},
        calculates={},
        recursive=False,
        codesystems=project.code_systems,
        process=[parent.root.process],
    )
    return project, parent


class TestGotoSharedActivityWait(unittest.TestCase):
    def test_continuation_stays_scoped_to_its_own_caller(self):
        _, parent = _build_and_process("goto_shared_activity_two_callers.yaml")

        by_name = {getattr(n, "name", None): n for n in parent.nodes.values() if getattr(n, "name", None)}
        node_c = by_name["node_c"]
        node_f = by_name["node_f"]

        self.assertIsNotNone(node_c.relevance)
        self.assertIsNotNone(node_f.relevance)

        node_c_refs = {getattr(r, "name", None) for r in node_c.relevance.get_references()}
        node_f_refs = {getattr(r, "name", None) for r in node_f.relevance.get_references()}

        # node_c must depend on its own caller's gate (trigger_a) and nothing tied to
        # the other caller's gate (trigger_d) - and vice versa for node_f.
        self.assertIn("trigger_a", node_c_refs)
        self.assertNotIn("trigger_d", node_c_refs)

        self.assertIn("trigger_d", node_f_refs)
        self.assertNotIn("trigger_a", node_f_refs)

    def test_shared_module_instance_has_no_direct_downstream_next_nodes(self):
        # module_c is the single shared activity instance both callers resolve to.
        # Its own next_nodes must stay empty: the continuation for each caller is
        # scheduled via that caller's own Wait node, not via the activity directly.
        # (If this ever becomes non-empty, the ended-activity scheduling fix in
        # walktrhough_tricc_node_processed_stached would push BOTH callers'
        # continuations onto the stash the moment either caller finishes.)
        project, parent = _build_and_process("goto_shared_activity_two_callers.yaml")

        from tricc_oo.models.tricc import TriccNodeActivity

        shared_instances = [
            n
            for n in parent.nodes.values()
            if isinstance(n, TriccNodeActivity) and getattr(n.base_instance, "id", None) == "module_c"
        ]
        self.assertEqual(len(shared_instances), 1, "expected a single shared module_c instance")
        self.assertEqual(list(shared_instances[0].next_nodes), [])


if __name__ == "__main__":
    unittest.main()
