"""GetRepeatedValue as a TRICC operation, scoped to one repeat slot.

See ``feature/20260821-get-repeated-value-operation.md``. Before this feature the
function fell through to ``TriccOperator.NATIVE``: the slot argument was ignored (every
slot was merged) and the function name was copied verbatim into the XLSForm calculation,
which ODK rejects with ``cannot handle function 'GetRepeatedValue'``.
"""

import os
import tempfile
import unittest

from tricc_oo.converters.xml_to_tricc import parse_expression
from tricc_oo.models.base import (
    TriccOperation,
    TriccOperator,
    TriccReference,
    TriccStatic,
)
from tricc_oo.models.calculate import TriccNodeCalculate
from tricc_oo.models.ordered_set import OrderedSet
from tricc_oo.models.tricc import (
    TriccNodeActivity,
    TriccNodeInteger,
    TriccNodeMainStart,
)
from tricc_oo.strategies.registry import get_output_strategy
from tricc_oo.visitors.tricc import (
    get_repeat_index_arg,
    process_operation_reference,
)

from tests.helpers import load_yaml_project

FIXTURE = "tests/data/yaml/repeat_value_reference.yaml"


def _repeated(reference, slot=None):
    refs = [reference] if slot is None else [reference, TriccStatic(slot)]
    return TriccOperation(TriccOperator.GET_REPEATED_VALUE, refs)


def _activity_with_nodes(*nodes):
    start = TriccNodeMainStart(id="start", name="start", label="Start")
    activity = TriccNodeActivity(
        id="act", name="act", root=start, label="Act", nodes={start.id: start}
    )
    start.activity = activity
    start.group = activity
    for node in nodes:
        node.activity = activity
        node.group = activity
        activity.nodes[node.id] = node
    return activity, start


def _resolve(expression, calc, processed):
    return process_operation_reference(
        expression,
        calc,
        processed_nodes=processed,
        calculates={},
        used_calculates=None,
        replace_reference=True,
        warn=False,
        inherit_display_versions=True,
    )


def _get_node(activity, name):
    for node in activity.nodes.values():
        if getattr(node, "name", None) == name:
            return node
    raise AssertionError(f"node {name!r} not found")


def _render(project, expression, strategy="XLSFormCDSSStrategy"):
    return get_output_strategy(strategy)(project, "/tmp").get_tricc_operation_expression(
        expression
    )


class TestSlotArgument(unittest.TestCase):
    """``get_repeat_index_arg`` — §7.1 of the spec."""

    def test_static_int(self):
        self.assertEqual(get_repeat_index_arg(_repeated(TriccReference("w"), 2)), 2)

    def test_static_numeric_string(self):
        op = TriccOperation(
            TriccOperator.GET_REPEATED_VALUE, [TriccReference("w"), TriccStatic("3")]
        )
        self.assertEqual(get_repeat_index_arg(op), 3)

    def test_plain_int(self):
        op = TriccOperation(TriccOperator.GET_REPEATED_VALUE, [TriccReference("w"), 4])
        self.assertEqual(get_repeat_index_arg(op), 4)

    def test_missing_argument_defaults_to_slot_one(self):
        self.assertEqual(get_repeat_index_arg(_repeated(TriccReference("w"))), 1)

    def test_non_literal_slot_leaves_reference_unscoped(self):
        """An expression as the slot must warn, not raise, and not scope the lookup."""
        op = TriccOperation(
            TriccOperator.GET_REPEATED_VALUE,
            [TriccReference("w"), TriccReference("n")],
        )
        self.assertIsNone(get_repeat_index_arg(op))


class TestParsing(unittest.TestCase):
    def test_parser_maps_function_to_operator(self):
        """The author's text must become the operator, not a NATIVE passthrough."""
        op = parse_expression("", 'GetRepeatedValue("weight", 2)')
        self.assertIsInstance(op, TriccOperation)
        self.assertEqual(op.operator, TriccOperator.GET_REPEATED_VALUE)
        self.assertEqual(list(op.reference), [TriccReference("weight"), TriccStatic(2)])

    def test_operand_order_is_value_then_slot(self):
        """reference[0] is the value operand (what RETURNS_CONCEPT / rendering read)."""
        op = parse_expression("", 'GetRepeatedValue("weight", 2)')
        self.assertIsInstance(op.reference[0], TriccReference)
        self.assertIsInstance(op.reference[1], TriccStatic)
        self.assertEqual(get_repeat_index_arg(op), 2)


class TestSlotScopedResolution(unittest.TestCase):
    def test_operand_scoped_to_requested_slot(self):
        """Each term binds to its own slot — the whole point of the feature."""
        project = load_yaml_project(FIXTURE)
        activity = list(project.pages.values())[0]
        calc = _get_node(activity, "weight_delta")

        slot_2, slot_1 = calc.expression.reference[0], calc.expression.reference[1]
        for term in (slot_2, slot_1):
            self.assertEqual(term.operator, TriccOperator.GET_REPEATED_VALUE)

        self.assertEqual(slot_2.reference[0].id, "w2")
        self.assertEqual(slot_1.reference[0].id, "w1")
        # Regression: both terms used to resolve to the same all-slots merge.
        self.assertNotEqual(slot_2.reference[0], slot_1.reference[0])

    def test_no_cross_slot_inheritance(self):
        """A single-version slot must not be wrapped in a merge over the other slot."""
        project = load_yaml_project(FIXTURE)
        activity = list(project.pages.values())[0]
        calc = _get_node(activity, "weight_delta")
        for term in calc.expression.reference:
            operand = term.reference[0]
            self.assertNotIsInstance(operand, TriccOperation)

    def test_coalesces_versions_within_slot(self):
        """Several versions of the *same* slot still merge; the other slot stays out."""
        slot2_v1 = TriccNodeInteger(
            id="w2a", name="weight", label="Weight r2 v1", repeat=2, path_len=1, version=1
        )
        slot2_v2 = TriccNodeInteger(
            id="w2b", name="weight", label="Weight r2 v2", repeat=2, path_len=3, version=2
        )
        slot1 = TriccNodeInteger(
            id="w1", name="weight", label="Weight r1", repeat=1, path_len=2, version=1
        )
        calc = TriccNodeCalculate(
            id="c1",
            name="weight_copy",
            label="Copy weight",
            expression=_repeated(TriccReference("weight"), 2),
            path_len=4,
        )
        activity, start = _activity_with_nodes(slot2_v1, slot2_v2, slot1, calc)
        processed = OrderedSet()
        for node in (start, slot2_v1, slot1, slot2_v2):
            processed.add(node)

        modified = _resolve(calc.expression, calc, processed)
        operand = modified.reference[0]
        self.assertEqual(operand.operator, TriccOperator.GET_INHERITED_VALUE)
        self.assertEqual(set(operand.reference), {slot2_v1, slot2_v2})
        self.assertNotIn(slot1, operand.reference)
        # coalesce is left-to-right: newest version first
        self.assertEqual(operand.reference[0], slot2_v2)

    def test_missing_slot_defers(self):
        """No capture in that slot is an authoring error, not a fallback to another."""
        slot1 = TriccNodeInteger(
            id="w1", name="weight", label="Weight r1", repeat=1, path_len=1
        )
        calc = TriccNodeCalculate(
            id="c1",
            name="weight_copy",
            label="Copy weight",
            expression=_repeated(TriccReference("weight"), 7),
            path_len=2,
        )
        activity, start = _activity_with_nodes(slot1, calc)
        processed = OrderedSet()
        processed.add(start)
        processed.add(slot1)

        self.assertIs(_resolve(calc.expression, calc, processed), False)

    def test_repeat_minus_one_stays_local(self):
        """Slot -1 is addressable but never merged with encounter slots."""
        local = TriccNodeInteger(
            id="wl", name="weight", label="Weight local", repeat=-1, path_len=1
        )
        shared = TriccNodeInteger(
            id="w1", name="weight", label="Weight r1", repeat=1, path_len=2
        )
        calc = TriccNodeCalculate(
            id="c1",
            name="weight_copy",
            label="Copy weight",
            expression=_repeated(TriccReference("weight"), -1),
            path_len=3,
        )
        activity, start = _activity_with_nodes(local, shared, calc)
        processed = OrderedSet()
        for node in (start, local, shared):
            processed.add(node)

        modified = _resolve(calc.expression, calc, processed)
        self.assertEqual(modified.reference[0], local)


class TestXlsFormRendering(unittest.TestCase):
    def setUp(self):
        self.project = load_yaml_project(FIXTURE)
        activity = list(self.project.pages.values())[0]
        self.expression = _get_node(activity, "weight_delta").expression

    def test_renders_the_slot_field(self):
        rendered = _render(self.project, self.expression)
        self.assertIn("${weight_Rr_2}", rendered)
        self.assertIn("${weight}", rendered)

    def test_no_function_name_leaks_into_the_form(self):
        """The reported ODK failure: 'cannot handle function GetRepeatedValue'."""
        for strategy in ("XLSFormStrategy", "XLSFormCDSSStrategy", "XLSFormCHTStrategy"):
            with self.subTest(strategy=strategy):
                self.assertNotIn(
                    "GetRepeatedValue", _render(self.project, self.expression, strategy)
                )

    def test_cht_does_not_prepend_current_value(self):
        """CHT overrides GET_INHERITED_VALUE with a leading '.'; a slot read must not."""
        rendered = _render(self.project, self.expression, "XLSFormCHTStrategy")
        self.assertNotIn("coalesce(.,", rendered)


class TestXlsFormExportValidates(unittest.TestCase):
    """End-to-end guard on the reported symptom: ODK rejected the generated form with
    ``XPath evaluation: cannot handle function 'GetRepeatedValue'``."""

    def test_generated_form_passes_pyxform_validation(self):
        import pandas as pd

        with tempfile.TemporaryDirectory() as out_dir:
            project = load_yaml_project(FIXTURE)
            strategy = get_output_strategy("XLSFormCDSSStrategy")(project, out_dir)
            strategy.execute()  # process + export + validate, as tests/build.py does
            self.assertTrue(strategy.validate())

            xls = os.path.join(out_dir, "repeat_value_reference.xlsx")
            survey = pd.read_excel(xls, sheet_name="survey")
            calculation = survey.loc[
                survey["name"] == "weight_delta", "calculation"
            ].iloc[0]
            self.assertNotIn("GetRepeatedValue", calculation)
            self.assertIn("${weight_Rr_2}", calculation)
            self.assertIn("${weight}", calculation)


if __name__ == "__main__":
    unittest.main()
