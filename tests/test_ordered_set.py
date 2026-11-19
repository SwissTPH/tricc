"""OrderedSet copy, membership, and order-preserving ops."""

import unittest

from tricc_oo.models.ordered_set import OrderedSet


class TestOrderedSet(unittest.TestCase):
    def test_preserves_insertion_order_and_uniqueness(self):
        s = OrderedSet(["a", "b", "a", "c"])
        self.assertEqual(list(s), ["a", "b", "c"])

    def test_copy_is_independent(self):
        s = OrderedSet(["a", "b"])
        c = s.copy()
        c.add("d")
        self.assertEqual(list(s), ["a", "b"])
        self.assertEqual(list(c), ["a", "b", "d"])

    def test_copy_from_ordered_set_init(self):
        s = OrderedSet(["a", "b"])
        c = OrderedSet(s)
        c.add("d")
        self.assertEqual(list(s), ["a", "b"])

    def test_insert_at_top_moves_existing(self):
        s = OrderedSet(["a", "b", "c"])
        s.insert_at_top("b")
        self.assertEqual(list(s), ["b", "a", "c"])

    def test_pop_from_front(self):
        s = OrderedSet(["a", "b", "c"])
        self.assertEqual(s.pop(), "a")
        self.assertEqual(list(s), ["b", "c"])

    def test_union_does_not_mutate(self):
        a = OrderedSet(["a"])
        b = OrderedSet(["b"])
        c = a | b
        self.assertEqual(list(a), ["a"])
        self.assertEqual(list(c), ["a", "b"])

    def test_ior_mutates_in_place(self):
        a = OrderedSet(["a"])
        a |= ["b", "a"]
        self.assertEqual(list(a), ["a", "b"])

    def test_reversed_without_list_copy(self):
        s = OrderedSet(["a", "b", "c"])
        self.assertEqual(list(reversed(s)), ["c", "b", "a"])

    def test_getitem_and_slice(self):
        s = OrderedSet(["a", "b", "c", "d"])
        self.assertEqual(s[0], "a")
        self.assertEqual(s[-1], "d")
        self.assertEqual(s[1:3], ["b", "c"])
        with self.assertRaises(IndexError):
            _ = s[10]

    def test_find_prev_skips_from_object(self):
        s = OrderedSet(["a", "b", "c", "d"])
        self.assertEqual(s.find_prev("c", lambda x: x in ("a", "b")), "b")
        self.assertEqual(s.find_prev("missing", lambda x: x == "d"), "d")

    def test_find_last_and_first(self):
        s = OrderedSet([1, 2, 3, 4])
        self.assertEqual(s.find_last(lambda x: x % 2 == 0), 4)
        self.assertEqual(s.find_first(lambda x: x % 2 == 0), 2)

    def test_same_members_ignores_order(self):
        a = OrderedSet(["a", "b"])
        b = OrderedSet(["b", "a"])
        self.assertTrue(a.same_members(b))
        self.assertEqual(a, b)
        self.assertFalse(a.same_members(OrderedSet(["a"])))

    def test_append_alias(self):
        s = OrderedSet()
        s.append("x")
        s.append("x")
        self.assertEqual(list(s), ["x"])

    def test_eq_is_membership(self):
        self.assertEqual(OrderedSet(["a", "b"]), OrderedSet(["a", "b"]))
        self.assertEqual(OrderedSet(["a", "b"]), OrderedSet(["b", "a"]))
        self.assertNotEqual(OrderedSet(["a", "b"]), OrderedSet(["a"]))
        self.assertNotEqual(list(OrderedSet(["a", "b"])), list(OrderedSet(["b", "a"])))


if __name__ == "__main__":
    unittest.main()
