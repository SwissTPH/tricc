"""Tests for goto instance=-1 snippet injection."""

import unittest
from pathlib import Path

import yaml

from tricc_oo.models.calculate import (
    TriccNodeActivityEnd,
    TriccNodeBridge,
    TriccNodeEnd,
    TriccNodeWait,
)
from tricc_oo.models.ordered_set import OrderedSet
from tricc_oo.models.tricc import (
    TriccNodeActivity,
    TriccNodeGoTo,
    TriccNodeInteger,
    TriccNodeNote,
    TriccProject,
)
from tricc_oo.strategies.input.drawio import DrawioStrategy
from tricc_oo.strategies.input.yaml import YamlStrategy, YamlActivity

DATA = Path(__file__).parent / "data" / "yaml"


def _load_yaml(name: str):
    path = DATA / name
    content = path.read_text(encoding="utf-8")
    strategy = YamlStrategy(str(path))
    return strategy.execute([content], media_path=str(DATA / "media-tmp"))


def _project_after_linking(name: str) -> TriccProject:
    """Build activities from YAML and run linking_nodes only (no load_calculate)."""
    path = DATA / name
    content = path.read_text(encoding="utf-8")
    strategy = YamlStrategy(str(path))
    project = TriccProject()
    for loaded in yaml.safe_load_all(content):
        if not loaded:
            continue
        activity = strategy._build_activity(YamlActivity(**loaded), project)
        if activity is not None:
            project.pages[activity.id] = activity
            strategy._assign_start_page(activity, project)

    parent = project.start_pages.get("main")
    assert parent is not None
    temp = DrawioStrategy.__new__(DrawioStrategy)
    temp.processes = strategy.processes
    temp.linking_nodes = DrawioStrategy.linking_nodes.__get__(temp, DrawioStrategy)
    temp.walkthrough_goto_node = DrawioStrategy.walkthrough_goto_node.__get__(
        temp, DrawioStrategy
    )
    # Fresh set: linking_nodes uses a mutable default for processed_nodes
    temp.linking_nodes(parent.root, parent, project.pages, OrderedSet(), [])
    return project


class TestGotoSnippetInjection(unittest.TestCase):
    def test_instance_minus_one_inlines_module(self):
        project = _load_yaml("goto_snippet_injection.yaml")
        self.assertIsNotNone(project)
        parent = project.start_pages.get("main")
        self.assertIsNotNone(parent)

        nodes = list(parent.nodes.values())

        # Goto removed from parent
        self.assertFalse(any(isinstance(n, TriccNodeGoTo) for n in nodes))

        # No nested activity object as a graph node on parent for the module call
        activity_nodes = [n for n in nodes if isinstance(n, TriccNodeActivity)]
        self.assertEqual(activity_nodes, [])

        # Module content present on parent
        by_name = {getattr(n, "name", None): n for n in nodes if getattr(n, "name", None)}
        self.assertIn("mod_age", by_name)
        self.assertIsInstance(by_name["mod_age"], TriccNodeInteger)
        self.assertIn("mod_is_adult", by_name)
        self.assertIn("note_before", by_name)
        self.assertIn("note_after", by_name)

        # Entry/exit bridges exist
        bridges = [n for n in nodes if isinstance(n, TriccNodeBridge)]
        self.assertGreaterEqual(len(bridges), 2)

        # No wait introduced for the snippet goto
        self.assertFalse(any(isinstance(n, TriccNodeWait) for n in nodes))

        # No end / activity_end left on parent from the module (only the form end remains).
        # Residual ends would falsely mark the parent activity as processed during walkthrough.
        self.assertFalse(any(isinstance(n, TriccNodeActivityEnd) for n in nodes))
        end_ids = {n.id for n in nodes if isinstance(n, TriccNodeEnd)}
        self.assertEqual(end_ids, {"end"}, f"unexpected end nodes on parent after snippet inject: {end_ids}")

        # Path continuity: note_before → … → note_after via next_nodes / edges
        note_before = by_name["note_before"]
        note_after = by_name["note_after"]
        self.assertIsInstance(note_before, TriccNodeNote)
        self.assertIsInstance(note_after, TriccNodeNote)

        # note_before should reach a bridge (entry)
        next_of_before = list(note_before.next_nodes)
        self.assertTrue(next_of_before)
        self.assertTrue(
            any(isinstance(n, TriccNodeBridge) for n in next_of_before),
            f"expected bridge after note_before, got {next_of_before}",
        )

        # note_after should be reachable from some bridge (exit)
        prev_of_after = list(note_after.prev_nodes)
        self.assertTrue(prev_of_after)
        self.assertTrue(
            any(isinstance(n, TriccNodeBridge) for n in prev_of_after),
            f"expected bridge before note_after, got {prev_of_after}",
        )

        # Exit bridge must list note_after in next_nodes (walkthrough only follows next_nodes;
        # empty next_nodes leaves the end unstashed and stalls waits on the caller activity).
        exit_bridges = [
            n
            for n in bridges
            if note_after in getattr(n, "next_nodes", [])
            or any(getattr(x, "id", None) == note_after.id for x in getattr(n, "next_nodes", []))
        ]
        self.assertTrue(
            exit_bridges,
            "snippet exit bridge must have note_after in next_nodes",
        )

        # Injected field reparented to parent activity
        self.assertEqual(by_name["mod_age"].activity.id, parent.id)

    def test_instance_one_keeps_nested_activity(self):
        # Full YAML execute + load_calculate is not required here: nested activity
        # without draw.io bridge/wait is a pre-existing edge case. Linking is enough
        # to assert that instance=1 still instances rather than inlines.
        project = _project_after_linking("goto_instance_nested.yaml")
        parent = project.start_pages.get("main")
        self.assertIsNotNone(parent)

        activity_nodes = [n for n in parent.nodes.values() if isinstance(n, TriccNodeActivity)]
        self.assertTrue(
            activity_nodes,
            "expected nested TriccNodeActivity for instance=1 goto",
        )
        self.assertFalse(any(isinstance(n, TriccNodeGoTo) for n in parent.nodes.values()))

        parent_names = {
            getattr(n, "name", None) for n in parent.nodes.values() if getattr(n, "name", None)
        }
        found_on_nested = any(
            getattr(n, "name", None) == "mod_age"
            for act in activity_nodes
            for n in act.nodes.values()
        )
        self.assertTrue(found_on_nested, "mod_age should be on nested activity instance")
        self.assertNotIn("mod_age", parent_names)


if __name__ == "__main__":
    unittest.main()
