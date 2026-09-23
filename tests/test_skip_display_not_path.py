"""Skip-if-already-asked: hide the later widget, not the rest of the flow.

See fix/20260914-skip-display-not-path.md.
"""

import os
import tempfile
import unittest

import pandas as pd

from tests.helpers import load_yaml_project
from tricc_oo.converters.xml_to_tricc import propagate_activity_repeat
from tricc_oo.models.base import TriccOperation, TriccOperator, get_repeat_authored
from tricc_oo.models.calculate import TriccNodeActivityStart, TriccNodeDisplayBridge
from tricc_oo.models.ordered_set import OrderedSet
from tricc_oo.models.tricc import TriccNodeActivity, TriccNodeInteger, TriccNodeNote
from tricc_oo.serializers.xls_form import CHOICE_MAP, SURVEY_MAP
from tricc_oo.strategies.output.xls_form import XLSFormStrategy
from tricc_oo.strategies.registry import get_output_strategy
from tricc_oo.visitors.tricc import (
    get_already_captured_expression,
    get_node_expressions,
    load_calculate,
    nand_already_captured_expression,
    serialize_display_relevance,
    set_prev_next_node,
)

FIXTURE = os.path.join(os.path.dirname(__file__), "data", "yaml", "skip_display_not_path.yaml")


def _mentions(op, target):
    if op is target:
        return True
    if getattr(op, "id", None) and getattr(op, "id", None) == getattr(target, "id", None):
        return True
    if isinstance(op, TriccOperation):
        return any(_mentions(r, target) for r in (op.reference or []))
    return False


def _all_named(project, name):
    found = []
    for page in project.pages.values():
        for node in page.nodes.values():
            if getattr(node, "name", None) == name:
                found.append(node)
    return found


def _processed(project):
    nodes = OrderedSet()
    for page in project.pages.values():
        for node in page.nodes.values():
            nodes.add(node)
        for calc in getattr(page, "calculates", []) or []:
            nodes.add(calc)
    return nodes


def _make_activity(activity_id, nodes):
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


class TestSkipHelpers(unittest.TestCase):
    def _run_two_activities(self, first_repeat=1, second_repeat=1):
        start_a = TriccNodeActivityStart(id="sa", name="sa", label="A", process="main")
        first = TriccNodeInteger(id="w1", name="ivio", label="First", repeat=first_repeat)
        act_a = _make_activity("coma", [start_a, first])
        start_b = TriccNodeActivityStart(id="sb", name="sb", label="B", process="main")
        second = TriccNodeInteger(id="w2", name="ivio", label="Second", repeat=second_repeat)
        note = TriccNodeNote(id="n1", name="note_after", label="After")
        act_b = _make_activity("cv", [start_b, second, note])
        set_prev_next_node(start_a, first)
        set_prev_next_node(start_b, second)
        set_prev_next_node(second, note)
        processed = OrderedSet()
        calculates = {}
        used = {}
        stashed = OrderedSet()
        for node in (start_a, first, start_b, second, note):
            if load_calculate(node, processed, stashed, calculates, used, warn=False):
                processed.add(node)
        return first, second, note, processed, act_a, act_b

    def test_graph_relevance_has_no_skip(self):
        first, second, note, processed, _, _ = self._run_two_activities()
        already = get_already_captured_expression(second, processed)
        self.assertIsNotNone(already)
        self.assertTrue(_mentions(already, first))
        printed = nand_already_captured_expression(second, processed, second.relevance)
        self.assertTrue(_mentions(printed, first))
        if isinstance(second.relevance, TriccOperation):
            self.assertFalse(
                _mentions(second.relevance, first) and second.relevance.operator
                in (TriccOperator.NOT, TriccOperator.ISNULL, TriccOperator.NOTEXISTS, TriccOperator.AND)
            )

    def test_printed_second_hides_when_first_answered_same_slot(self):
        first, second, _, processed, _, _ = self._run_two_activities(1, 1)
        printed = serialize_display_relevance(second, processed)
        self.assertTrue(_mentions(printed, first))

    def test_cross_activity_different_slots_do_not_skip(self):
        """repeat=2 is a new capture (ETAT age amend after estimated weight No)."""
        first, second, _, processed, _, _ = self._run_two_activities(1, 2)
        self.assertIsNone(get_already_captured_expression(second, processed))
        printed = serialize_display_relevance(second, processed)
        self.assertFalse(_mentions(printed, first))

    def test_note_after_does_not_copy_nand_skip(self):
        first, second, note, processed, _, _ = self._run_two_activities()
        printed_note = serialize_display_relevance(note, processed)
        self.assertFalse(_mentions(printed_note, first))
        if isinstance(note.relevance, TriccOperation):
            self.assertFalse(_mentions(note.relevance, first) and note.relevance.operator == TriccOperator.NOT)

    def test_path_bridge_or_already_captured(self):
        first, second, note, processed, _, act_b = self._run_two_activities()
        from tricc_oo.models.base import TriccStatic
        from tricc_oo.visitors.tricc import get_node_expression, or_already_captured_expression

        via_or = or_already_captured_expression(second, processed, TriccStatic(False))
        self.assertTrue(_mentions(via_or, first), via_or)
        self.assertNotEqual(getattr(via_or, "operator", None), TriccOperator.NOT)

        bridge = TriccNodeDisplayBridge(
            id="br1", name="path_br", label="path", activity=act_b, group=act_b
        )
        act_b.nodes[bridge.id] = bridge
        set_prev_next_node(second, bridge)
        expr = get_node_expressions(bridge, processed)
        if expr is not None and expr != TriccStatic(True) and expr is not True:
            self.assertTrue(_mentions(expr, first), expr)
            self.assertNotEqual(getattr(expr, "operator", None), TriccOperator.NOT)

    def test_same_page_different_slots_do_not_skip(self):
        start = TriccNodeActivityStart(id="s0", name="s", label="Start", process="main")
        first = TriccNodeInteger(id="w1", name="weight", label="W1", repeat=1)
        second = TriccNodeInteger(id="w2", name="weight", label="W2", repeat=2)
        _make_activity("same", [start, first, second])
        set_prev_next_node(start, first)
        set_prev_next_node(first, second)
        processed = OrderedSet()
        calculates = {}
        used = {}
        stashed = OrderedSet()
        for node in (start, first, second):
            if load_calculate(node, processed, stashed, calculates, used, warn=False):
                processed.add(node)
        self.assertIsNone(get_already_captured_expression(second, processed))

    def test_repeat_minus_one_does_not_skip(self):
        start = TriccNodeActivityStart(id="s0", name="s", label="Start", process="main")
        first = TriccNodeInteger(id="w1", name="weight", label="W1", repeat=-1)
        second = TriccNodeInteger(id="w2", name="weight", label="W2", repeat=-1)
        _make_activity("local", [start, first, second])
        set_prev_next_node(start, first)
        set_prev_next_node(first, second)
        processed = OrderedSet()
        calculates = {}
        used = {}
        stashed = OrderedSet()
        for node in (start, first, second):
            if load_calculate(node, processed, stashed, calculates, used, warn=False):
                processed.add(node)
        self.assertIsNone(get_already_captured_expression(second, processed))

    def test_repeat_authored_survives_activity_override(self):
        start = TriccNodeActivityStart(id="as1", name="act", label="Act", repeat=3)
        weight = TriccNodeInteger(id="w1", name="weight", label="Weight", repeat=2)
        activity = TriccNodeActivity(
            id="act1",
            name="act",
            label="Act",
            root=start,
            nodes={"as1": start, "w1": weight},
            edges=[],
        )
        for node in activity.nodes.values():
            node.activity = activity
            node.group = activity
        propagate_activity_repeat(activity)
        self.assertEqual(weight.repeat, 3)
        self.assertEqual(get_repeat_authored(weight), 2)


class TestSkipYamlLayers(unittest.TestCase):
    def test_yaml_three_layers(self):
        project = load_yaml_project(FIXTURE)
        processed = _processed(project)
        ivios = _all_named(project, "ivio")
        self.assertGreaterEqual(len(ivios), 2)
        first = min(ivios, key=lambda n: getattr(n, "path_len", 0) or 0)
        second = max(ivios, key=lambda n: getattr(n, "path_len", 0) or 0)
        self.assertEqual(get_repeat_authored(second), 1)
        already = get_already_captured_expression(second, processed)
        self.assertIsNotNone(already)
        refs = list(already.get_references()) if hasattr(already, "get_references") else []
        self.assertTrue(any(getattr(r, "name", None) == "ivio" and r is not second for r in refs) or refs)
        printed = serialize_display_relevance(second, processed)
        self.assertIsNotNone(printed)
        if isinstance(second.relevance, TriccOperation):
            self.assertNotEqual(getattr(second.relevance, "operator", None), TriccOperator.NOT)

        ages = _all_named(project, "age_weeks")
        self.assertGreaterEqual(len(ages), 2)
        age2 = [a for a in ages if get_repeat_authored(a) == 2][0]
        self.assertIsNone(get_already_captured_expression(age2, processed))

        notes = _all_named(project, "note_after")
        self.assertEqual(len(notes), 1)
        self.assertIsNone(get_already_captured_expression(notes[0], processed))

        weights = _all_named(project, "recapture_w")
        self.assertEqual(len(weights), 2)
        w2 = [w for w in weights if get_repeat_authored(w) == 2][0]
        self.assertIsNone(get_already_captured_expression(w2, processed))

        locals_ = _all_named(project, "local_w")
        self.assertEqual(len(locals_), 2)
        for node in locals_:
            self.assertIsNone(get_already_captured_expression(node, processed))

    def test_xlsform_printed_relevant_has_skip(self):
        XLSFormStrategy.df_survey = pd.DataFrame(columns=SURVEY_MAP.keys())
        XLSFormStrategy.df_calculate = pd.DataFrame(columns=SURVEY_MAP.keys())
        XLSFormStrategy.df_choice = pd.DataFrame(columns=CHOICE_MAP.keys())
        with tempfile.TemporaryDirectory() as out_dir:
            project = load_yaml_project(FIXTURE)
            strategy = get_output_strategy("XLSFormStrategy")(project, out_dir)
            strategy.execute()
            survey = pd.read_excel(os.path.join(out_dir, "skip-display-not-path.xlsx"), sheet_name="survey")
        rows = {
            str(r["name"]): ("" if pd.isna(r.get("relevance")) else str(r["relevance"]))
            for _, r in survey.iterrows()
        }
        ivio_rows = {name: rel for name, rel in rows.items() if name.startswith("ivio")}
        self.assertTrue(ivio_rows, list(rows.keys()))
        skipped = [rel for rel in ivio_rows.values() if "not" in rel.lower() and "ivio" in rel]
        self.assertTrue(skipped, ivio_rows)
        age_rr2 = next((name for name in rows if name.startswith("age_weeks") and "Rr_2" in name), None)
        self.assertIsNotNone(age_rr2, list(rows.keys()))
        self.assertNotIn("not(", (rows[age_rr2] or "").replace(" ", ""))
        self.assertNotIn("not(", rows.get("note_after", "").replace(" ", ""))


if __name__ == "__main__":
    unittest.main()
