"""Structural hash, origin signature, and get_node_expression memoization."""

import unittest
from types import SimpleNamespace

from tricc_oo.models.base import (
    TriccOperation,
    TriccOperator,
    TriccReference,
    TriccStatic,
    and_join,
    clear_operation_join_cache,
)
from tricc_oo.models.calculate import TriccNodeActivityStart, TriccNodeRhombus
from tricc_oo.models.ordered_set import OrderedSet
from tricc_oo.models.tricc import TriccNodeInteger
from tricc_oo.visitors.tricc import (
    clear_expression_walk_caches,
    get_node_expression,
    group_prev_versions_by_origin_signature,
)


def _mult_rate(operand):
    return TriccOperation(TriccOperator.MULTIPLIED, [operand, TriccStatic(30)])


class TestStructuralHash(unittest.TestCase):
    def test_equivalent_ops_are_equal_and_hash_equal(self):
        a = _mult_rate(TriccReference("fluid_rate"))
        b = _mult_rate(TriccReference("fluid_rate"))
        self.assertEqual(a, b)
        self.assertEqual(hash(a), hash(b))

    def test_different_operators_are_not_equal(self):
        a = TriccOperation(TriccOperator.PLUS, [TriccStatic(1), TriccStatic(2)])
        b = TriccOperation(TriccOperator.MINUS, [TriccStatic(1), TriccStatic(2)])
        self.assertNotEqual(a, b)

    def test_live_hash_uses_node_id_not_name(self):
        n1 = TriccNodeInteger(id="i1", name="fluid_rate")
        n2 = TriccNodeInteger(id="i2", name="fluid_rate")
        a = _mult_rate(n1)
        b = _mult_rate(n2)
        self.assertNotEqual(a, b)
        self.assertNotEqual(hash(a), hash(b))

    def test_append_invalidates_cached_hash(self):
        op = TriccOperation(TriccOperator.AND, [TriccReference("a")])
        before = hash(op)
        op.append(TriccReference("b"))
        after = hash(op)
        self.assertNotEqual(before, after)
        self.assertEqual(op, TriccOperation(TriccOperator.AND, [TriccReference("a"), TriccReference("b")]))

    def test_hash_does_not_go_through_str(self):
        op = TriccOperation(TriccOperator.ISTRUE, [TriccReference("x")])
        # Structural hash must be stable even if __str__ would walk a large tree.
        first = hash(op)
        second = hash(op)
        self.assertEqual(first, second)
        self.assertIsInstance(first, int)


class TestOriginSignature(unittest.TestCase):
    def test_origin_is_an_int_not_a_cloned_tree(self):
        op = _mult_rate(TriccReference("fluid_rate"))
        self.assertIsInstance(op.origin, int)
        self.assertEqual(op.origin, op.origin_signature)

    def test_same_name_different_node_ids_share_origin(self):
        n1 = TriccNodeInteger(id="i1", name="fluid_rate")
        n2 = TriccNodeInteger(id="i2", name="fluid_rate")
        a = _mult_rate(n1)
        b = _mult_rate(n2)
        self.assertEqual(a.origin_signature, b.origin_signature)

    def test_node_and_reference_share_origin(self):
        node = TriccNodeInteger(id="i1", name="fluid_rate")
        by_node = _mult_rate(node)
        by_ref = _mult_rate(TriccReference("fluid_rate"))
        self.assertEqual(by_node.origin_signature, by_ref.origin_signature)
        self.assertNotEqual(by_node, by_ref)

    def test_update_origin_after_mutation(self):
        op = TriccOperation(TriccOperator.ISTRUE, [TriccReference("a")])
        first = op.origin_signature
        op.reference = [TriccReference("b")]
        op.update_origin()
        self.assertNotEqual(first, op.origin_signature)

    def test_group_prev_versions_by_name_only_origin(self):
        n1 = TriccNodeInteger(id="i1", name="fluid_rate")
        n2 = TriccNodeInteger(id="i2", name="fluid_rate")
        current = _mult_rate(n1)
        sibling = SimpleNamespace(expression=_mult_rate(n2))
        other = SimpleNamespace(expression=TriccOperation(TriccOperator.PLUS, [n1, TriccStatic(1)]))
        sib, groups = group_prev_versions_by_origin_signature("dose", current, [sibling, other])
        self.assertEqual(sib, [sibling])
        self.assertEqual(len(groups), 1)
        self.assertEqual(list(groups.values())[0], [other])


class TestExpressionMemo(unittest.TestCase):
    def setUp(self):
        clear_expression_walk_caches()

    def test_and_join_reuses_same_object_for_same_operands(self):
        clear_operation_join_cache()
        left = TriccOperation(TriccOperator.ISTRUE, [TriccReference("x")])
        right = TriccOperation(TriccOperator.ISFALSE, [TriccReference("y")])
        first = and_join([left, right])
        second = and_join([left, right])
        self.assertIs(first, second)

    def test_get_node_expression_returns_cached_object(self):
        start = TriccNodeActivityStart(id="s0")
        processed = OrderedSet()
        first = get_node_expression(start, processed)
        second = get_node_expression(start, processed)
        self.assertIs(first, second)
        self.assertEqual(first, TriccStatic(True))

    def test_rhombus_prefix_is_reused(self):
        start = TriccNodeActivityStart(id="s0")
        prev = start
        rhombi = []
        for i in range(5):
            term = TriccOperation(TriccOperator.ISTRUE, [TriccReference(f"t{i}")])
            rh = TriccNodeRhombus(
                id=f"r{i}",
                reference=[TriccReference(f"t{i}")],
                expression_reference=term,
                path=prev,
            )
            rhombi.append(rh)
            prev = rh
        processed = OrderedSet()
        last = get_node_expression(rhombi[-1], processed, is_prev=True)
        again = get_node_expression(rhombi[-1], processed, is_prev=True)
        self.assertIs(last, again)
        prefix = get_node_expression(rhombi[0], processed, is_prev=True)
        via_last = get_node_expression(rhombi[0], processed, is_prev=True)
        self.assertIs(prefix, via_last)


if __name__ == "__main__":
    unittest.main()
