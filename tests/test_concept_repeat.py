"""Tests for concept repeat scoping (name + repeat versioning)."""

import unittest

from tricc_oo.models.base import get_repeat, TriccOperation
from tricc_oo.models.tricc import TriccNodeInteger, TriccNodeActivity
from tricc_oo.models.calculate import TriccNodeActivityStart
from tricc_oo.models.ordered_set import OrderedSet
from tricc_oo.converters.tricc_to_xls_form import get_export_name, REPEAT_SEPARATOR
from tricc_oo.converters.xml_to_tricc import propagate_activity_repeat
from tricc_oo.visitors.tricc import get_versions, version_filter, load_calculate, set_prev_next_node

from tests.helpers import load_yaml_project


def _make_activity(activity_id, nodes):
    """Build a minimal activity shell for visitor tests."""
    root = nodes[0]
    activity = TriccNodeActivity(
        id=activity_id,
        name=activity_id,
        label=activity_id,
        root=root,
        nodes={n.id: n for n in nodes},
        edges=[],
    )
    for node in nodes:
        node.activity = activity
        node.group = activity
    return activity


class TestGetRepeat(unittest.TestCase):
    def test_default_is_one(self):
        node = TriccNodeInteger(id="n1", name="weight", label="Weight")
        self.assertEqual(get_repeat(node), 1)

    def test_explicit_repeat(self):
        node = TriccNodeInteger(id="n2", name="weight", label="Weight", repeat=2)
        self.assertEqual(get_repeat(node), 2)

    def test_repeat_zero(self):
        node = TriccNodeInteger(id="n3", name="weight", label="Weight", repeat=0)
        self.assertEqual(get_repeat(node), 0)


class TestVersionFilterRepeat(unittest.TestCase):
    def _node(self, name, repeat=None):
        data = {"id": f"id_{name}_{repeat}", "name": name, "label": name}
        if repeat is not None:
            data["repeat"] = repeat
        return TriccNodeInteger(**data)

    def test_same_name_different_repeat_are_isolated(self):
        a = self._node("weight", 1)
        b = self._node("weight", 2)
        versions = get_versions("weight", [a, b], repeat=1)
        self.assertEqual(versions, [a])

    def test_same_name_same_repeat_match(self):
        a = self._node("weight", 1)
        b = self._node("weight", 1)
        filt = version_filter("weight", 1)
        self.assertTrue(filt(a))
        self.assertTrue(filt(b))


class TestExportNameRepeat(unittest.TestCase):
    def test_no_suffix_for_default_repeat(self):
        node = TriccNodeInteger(id="e1", name="weight", label="Weight")
        node.gen_name()
        self.assertEqual(get_export_name(node), "weight")

    def test_suffix_for_repeat_two(self):
        node = TriccNodeInteger(id="e2", name="weight", label="Weight", repeat=2)
        node.gen_name()
        self.assertIn(REPEAT_SEPARATOR + "2", get_export_name(node))


class TestPropagateActivityRepeat(unittest.TestCase):
    def test_activity_repeat_overrides_nodes(self):
        root = TriccNodeActivityStart(id="as1", name="act", label="Act", repeat=3)
        weight = TriccNodeInteger(id="w1", name="weight", label="Weight", repeat=1)
        height = TriccNodeInteger(id="h1", name="height", label="Height")
        activity = TriccNodeActivity(
            id="act1",
            name="act",
            label="Act",
            root=root,
            nodes={"as1": root, "w1": weight, "h1": height},
            edges=[],
        )
        for node in activity.nodes.values():
            node.activity = activity
            node.group = activity
        propagate_activity_repeat(activity)
        self.assertEqual(get_repeat(weight), 3)
        self.assertEqual(get_repeat(height), 3)


class TestLoadCalculateRepeatSkip(unittest.TestCase):
    """Verify skip relevance is scoped to (name, repeat)."""

    def _run_chain(self, first, second):
        start = TriccNodeActivityStart(id="s0", name="s", label="Start", process="main")
        _make_activity("act_chain", [start, first, second])
        set_prev_next_node(start, first)
        set_prev_next_node(first, second)

        processed = OrderedSet()
        calculates = {}
        used_calculates = {}
        stashed = OrderedSet()

        for node in (start, first, second):
            if load_calculate(node, processed, stashed, calculates, used_calculates, warn=False):
                processed.add(node)
        return second, processed

    def test_same_repeat_gets_skip_relevance(self):
        first = TriccNodeInteger(id="w1", name="weight", label="W1", repeat=1)
        second = TriccNodeInteger(id="w2", name="weight", label="W2", repeat=1)
        second, _ = self._run_chain(first, second)
        self.assertIsInstance(second.relevance, TriccOperation)

    def test_different_repeat_no_skip_relevance(self):
        first = TriccNodeInteger(id="w1b", name="weight", label="W1", repeat=1)
        second = TriccNodeInteger(id="w2b", name="weight", label="W2", repeat=2)
        second, processed = self._run_chain(first, second)
        self.assertNotIsInstance(second.relevance, TriccOperation)
        self.assertEqual(get_versions("weight", processed, repeat=2), [second])


class TestConceptRepeatYamlIntegration(unittest.TestCase):
    def test_activity_repeat_propagation_from_yaml(self):
        project = load_yaml_project("tests/data/yaml/concept_repeat_activity_inherit.yaml")
        activity = project.pages["activity_repeat_override"]
        weight = next(n for n in activity.nodes.values() if getattr(n, "name", None) == "weight")
        height = next(n for n in activity.nodes.values() if getattr(n, "name", None) == "height")
        self.assertEqual(get_repeat(weight), 3)
        self.assertEqual(get_repeat(height), 3)


if __name__ == "__main__":
    unittest.main()