"""process_reference should coalesce all DisplayModel versions via GET_INHERITED_VALUE."""

import unittest

from tricc_oo.models.base import TriccOperation, TriccOperator, TriccReference
from tricc_oo.models.calculate import TriccNodeCalculate
from tricc_oo.models.ordered_set import OrderedSet
from tricc_oo.models.tricc import (
    TriccNodeActivity,
    TriccNodeInteger,
    TriccNodeMainStart,
)
from tricc_oo.visitors.tricc import process_operation_reference, process_reference


def _activity_with_nodes(*nodes):
    start = TriccNodeMainStart(id="start", name="start", label="Start")
    activity = TriccNodeActivity(
        id="act",
        name="act",
        root=start,
        label="Act",
        nodes={start.id: start},
    )
    start.activity = activity
    start.group = activity
    for n in nodes:
        n.activity = activity
        n.group = activity
        activity.nodes[n.id] = n
    return activity, start


class TestDisplayReferenceInheritance(unittest.TestCase):
    def test_multi_version_display_uses_get_inherited_value(self):
        """Referencing a multi-version input expands to GET_INHERITED_VALUE(all versions)."""
        activity, start = _activity_with_nodes()
        v1 = TriccNodeInteger(
            id="w1", name="weight", label="Weight v1", path_len=1, version=1
        )
        v2 = TriccNodeInteger(
            id="w2", name="weight", label="Weight v2", path_len=3, version=2
        )
        calc = TriccNodeCalculate(
            id="c1",
            name="weight_copy",
            label="Copy weight",
            expression=TriccOperation(TriccOperator.CAST_NUMBER, [TriccReference("weight")]),
            path_len=4,
        )
        for n in (v1, v2, calc):
            n.activity = activity
            n.group = activity
            activity.nodes[n.id] = n

        processed = OrderedSet()
        processed.add(start)
        processed.add(v1)
        processed.add(v2)

        modified = process_operation_reference(
            calc.expression,
            calc,
            processed_nodes=processed,
            calculates={},
            used_calculates=None,
            replace_reference=True,
            warn=False,
            inherit_display_versions=True,
        )
        self.assertIsNotNone(modified)
        self.assertIsInstance(modified, TriccOperation)
        # Outer op still CAST_NUMBER; its operand should be GET_INHERITED_VALUE
        operand = modified.reference[0]
        self.assertIsInstance(operand, TriccOperation)
        self.assertEqual(operand.operator, TriccOperator.GET_INHERITED_VALUE)
        # Both versions present; newer (higher path_len) first for coalesce priority
        self.assertEqual(set(operand.reference), {v1, v2})
        self.assertEqual(operand.reference[0], v2)
        self.assertEqual(operand.reference[1], v1)

    def test_single_version_display_stays_node(self):
        """A single DisplayModel version is kept as a plain node reference."""
        activity, start = _activity_with_nodes()
        age = TriccNodeInteger(id="a1", name="age", label="Age", path_len=1)
        calc = TriccNodeCalculate(
            id="c1",
            name="age_copy",
            label="Copy age",
            expression=TriccOperation(TriccOperator.CAST_NUMBER, [TriccReference("age")]),
            path_len=2,
        )
        for n in (age, calc):
            n.activity = activity
            n.group = activity
            activity.nodes[n.id] = n

        processed = OrderedSet()
        processed.add(start)
        processed.add(age)

        modified = process_operation_reference(
            calc.expression,
            calc,
            processed_nodes=processed,
            calculates={},
            used_calculates=None,
            replace_reference=True,
            warn=False,
            inherit_display_versions=True,
        )
        self.assertIsNotNone(modified)
        self.assertIsInstance(modified, TriccOperation)
        self.assertEqual(modified.reference[0], age)

    def test_process_reference_rewrites_expression(self):
        """process_reference with replace_reference updates node.expression."""
        activity, start = _activity_with_nodes()
        v1 = TriccNodeInteger(id="w1", name="weight", label="W1", path_len=1, version=1)
        v2 = TriccNodeInteger(id="w2", name="weight", label="W2", path_len=2, version=2)
        calc = TriccNodeCalculate(
            id="c1",
            name="bmi_weight",
            label="Weight for BMI",
            expression=TriccOperation(TriccOperator.CAST_NUMBER, [TriccReference("weight")]),
            path_len=3,
        )
        for n in (v1, v2, calc):
            n.activity = activity
            n.group = activity
            activity.nodes[n.id] = n

        processed = OrderedSet()
        for n in (start, v1, v2):
            processed.add(n)

        ok = process_reference(
            calc,
            processed_nodes=processed,
            calculates={},
            used_calculates=None,
            replace_reference=True,
            warn=False,
        )
        self.assertTrue(ok)
        self.assertIsInstance(calc.expression, TriccOperation)
        operand = calc.expression.reference[0]
        self.assertIsInstance(operand, TriccOperation)
        self.assertEqual(operand.operator, TriccOperator.GET_INHERITED_VALUE)
        self.assertEqual(set(operand.reference), {v1, v2})

    def test_relevance_does_not_use_get_inherited_value(self):
        """Relevance keeps a single last-version DisplayModel ref (no coalesce)."""
        activity, start = _activity_with_nodes()
        v1 = TriccNodeInteger(id="w1", name="weight", label="W1", path_len=1, version=1)
        v2 = TriccNodeInteger(id="w2", name="weight", label="W2", path_len=2, version=2)
        note = TriccNodeInteger(
            id="n1",
            name="note_weight",
            label="Depends on weight",
            relevance=TriccOperation(TriccOperator.EXISTS, [TriccReference("weight")]),
            path_len=3,
        )
        for n in (v1, v2, note):
            n.activity = activity
            n.group = activity
            activity.nodes[n.id] = n

        processed = OrderedSet()
        for n in (start, v1, v2):
            processed.add(n)

        ok = process_reference(
            note,
            processed_nodes=processed,
            calculates={},
            used_calculates=None,
            replace_reference=True,
            warn=False,
        )
        self.assertTrue(ok)
        self.assertIsInstance(note.relevance, TriccOperation)
        self.assertEqual(note.relevance.operator, TriccOperator.EXISTS)
        # Single version only — not GET_INHERITED_VALUE of all versions
        ref = note.relevance.reference[0]
        self.assertNotIsInstance(ref, TriccOperation)
        self.assertIn(ref, (v1, v2))

    def test_relevance_path_explicitly_disables_inherit(self):
        """inherit_display_versions=False must not wrap multi-version display refs."""
        activity, start = _activity_with_nodes()
        v1 = TriccNodeInteger(id="w1", name="weight", label="W1", path_len=1, version=1)
        v2 = TriccNodeInteger(id="w2", name="weight", label="W2", path_len=2, version=2)
        calc = TriccNodeCalculate(
            id="c1",
            name="gate",
            label="Gate",
            expression=TriccOperation(TriccOperator.EXISTS, [TriccReference("weight")]),
            path_len=3,
        )
        for n in (v1, v2, calc):
            n.activity = activity
            n.group = activity
            activity.nodes[n.id] = n

        processed = OrderedSet()
        for n in (start, v1, v2):
            processed.add(n)

        modified = process_operation_reference(
            calc.expression,
            calc,
            processed_nodes=processed,
            calculates={},
            used_calculates=None,
            replace_reference=True,
            warn=False,
            inherit_display_versions=False,
        )
        self.assertIsNotNone(modified)
        ref = modified.reference[0]
        self.assertIn(ref, (v1, v2))
        self.assertNotIsInstance(ref, TriccOperation)
        self.assertNotEqual(
            getattr(ref, "operator", None),
            TriccOperator.GET_INHERITED_VALUE,
        )


if __name__ == "__main__":
    unittest.main()
