"""Tests for concept repeat scoping (name + repeat versioning)."""

import unittest

from tricc_oo.models.base import get_repeat, TriccOperation, TriccOperator
from tricc_oo.models.tricc import TriccNodeInteger, TriccNodeActivity
from tricc_oo.models.calculate import TriccNodeActivityStart
from tricc_oo.models.ordered_set import OrderedSet
from tricc_oo.converters.tricc_to_xls_form import get_export_name, REPEAT_SEPARATOR
from tricc_oo.converters.xml_to_tricc import propagate_activity_repeat
from tricc_oo.visitors.tricc import (
    get_versions,
    get_last_version,
    version_filter,
    load_calculate,
    set_prev_next_node,
    get_version_inheritance,
)

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

    def test_repeat_minus_one_is_resolvable_by_reference(self):
        """repeat=-1 must remain findable (references must not break)."""
        normal = self._node("weight", 1)
        local = self._node("weight", -1)
        self.assertTrue(version_filter("weight", -1)(local))
        self.assertTrue(version_filter("weight")(local))  # unrestricted includes it
        self.assertEqual(get_versions("weight", [normal, local], repeat=-1), [local])
        processed = OrderedSet()
        processed.add(normal)
        processed.add(local)
        self.assertEqual(get_last_version("weight", processed, repeat=-1), local)

    def test_set_last_version_renumbers_peers_for_unique_export_names(self):
        """Linking a new same-name node renumbers all prior peers for unique names."""
        from tricc_oo.visitors.tricc import set_last_version_false
        from tricc_oo.converters.tricc_to_xls_form import get_export_name

        a = TriccNodeInteger(id="a", name="weight", label="A", repeat=-1, path_len=1)
        b = TriccNodeInteger(id="b", name="weight", label="B", repeat=-1, path_len=2)
        c = TriccNodeInteger(id="c", name="weight", label="C", repeat=-1, path_len=3)
        processed = OrderedSet()
        processed.add(a)
        set_last_version_false(b, processed)
        processed.add(b)
        set_last_version_false(c, processed)
        self.assertEqual(a.version, 1)
        self.assertEqual(b.version, 2)
        self.assertEqual(c.version, 3)
        self.assertIs(a.last, False)
        self.assertIs(b.last, False)
        names = {get_export_name(n) for n in (a, b, c)}
        self.assertEqual(len(names), 3, names)

    def test_set_last_version_export_pool_merges_minus_one_and_default(self):
        """repeat=-1 and repeat=1 share export base → shared version renumbering."""
        from tricc_oo.visitors.tricc import set_last_version_false
        from tricc_oo.converters.tricc_to_xls_form import get_export_name

        local = TriccNodeInteger(id="local", name="weight", label="Local", repeat=-1, path_len=1)
        first = TriccNodeInteger(id="w1", name="weight", label="W1", repeat=1, path_len=2)
        second = TriccNodeInteger(id="w2", name="weight", label="W2", repeat=1, path_len=3)
        processed = OrderedSet()
        processed.add(local)
        processed.add(first)
        set_last_version_false(second, processed)
        self.assertIs(local.last, False)
        self.assertIs(first.last, False)
        # Three peers in the same export pool (no _Rr_ for either slot)
        self.assertEqual({local.version, first.version, second.version}, {1, 2, 3})
        exports = set()
        for n in (local, first, second):
            n.export_name = None
            exports.add(get_export_name(n))
        self.assertEqual(len(exports), 3, exports)


class TestVersionInheritanceRepeatMinusOne(unittest.TestCase):
    def test_get_version_inheritance_skips_repeat_minus_one_receiver(self):
        """A node with repeat=-1 does not get GET_INHERITED_VALUE expression."""
        prev = TriccNodeInteger(id="w1", name="weight", label="W1", repeat=1)
        node = TriccNodeInteger(id="w_local", name="weight", label="Local", repeat=-1)
        before = getattr(node, "expression", None)
        get_version_inheritance(node, [prev], OrderedSet())
        expr = getattr(node, "expression", None)
        self.assertEqual(expr, before)
        self.assertFalse(
            isinstance(expr, TriccOperation)
            and expr.operator == TriccOperator.GET_INHERITED_VALUE
        )

    def test_repeat_minus_one_not_in_inheritance_operands(self):
        """Prior repeat=-1 must not appear in GET_INHERITED_VALUE for normal slots."""
        from tricc_oo.visitors.tricc import _filter_inheritable_versions

        local = TriccNodeInteger(id="w_local", name="weight", label="Local", repeat=-1)
        first = TriccNodeInteger(id="w1", name="weight", label="W1", repeat=1)
        filtered = _filter_inheritable_versions([local, first])
        self.assertEqual(filtered, [first])


class TestExportNameRepeat(unittest.TestCase):
    def test_no_suffix_for_default_repeat(self):
        node = TriccNodeInteger(id="e1", name="weight", label="Weight")
        node.gen_name()
        self.assertEqual(get_export_name(node), "weight")

    def test_no_suffix_for_repeat_less_than_one(self):
        """repeat < 1 (e.g. history) must not appear in export names."""
        for repeat in (0, -1):
            node = TriccNodeInteger(
                id=f"e0_{repeat}", name="weight", label="Weight", repeat=repeat
            )
            node.gen_name()
            export = get_export_name(node)
            self.assertEqual(export, "weight", f"repeat={repeat}")
            self.assertNotIn(REPEAT_SEPARATOR, export)

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

    def test_repeat_minus_one_no_skip_relevance(self):
        """repeat=-1 is local-only: a second occurrence of the same concept must not
        be skip-suppressed because an earlier repeat=-1 occurrence was captured -
        unlike repeat=1/2/... slots, which do dedupe (test_same_repeat_gets_skip_relevance)."""
        first = TriccNodeInteger(id="w1c", name="weight", label="W1", repeat=-1)
        second = TriccNodeInteger(id="w2c", name="weight", label="W2", repeat=-1)
        second, _ = self._run_chain(first, second)
        self.assertNotIsInstance(second.relevance, TriccOperation)


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