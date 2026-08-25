"""Tests for the shared output-walk callback contract.

See feature/20260824-output-walk-context.md.

Run with:
    python -m pytest tests/test_output_walk_context.py -v
"""

import inspect
import unittest
from unittest.mock import MagicMock

from tricc_oo.models.base import TriccOperation, TriccOperator, TriccStatic
from tricc_oo.models.calculate import TriccNodeActivityStart, TriccNodeCalculate
from tricc_oo.models.ordered_set import OrderedSet
from tricc_oo.models.tricc import (
    TriccNodeActivity,
    TriccNodeMainStart,
    TriccNodeNote,
    TriccProject,
)
from tricc_oo.strategies.output.base_output_strategy import BaseOutPutStrategy
from tricc_oo.strategies.output.html_form import HTMLStrategy
from tricc_oo.visitors.tricc import (
    stashed_node_func,
    walktrhough_tricc_node_processed_stached,
)


def _triage_graph():
    """main start → triage activity (root.process=triage) → note + dangling calculate."""
    main_start = TriccNodeMainStart(id="s", name="start", label="Start", process="main")
    main_act = TriccNodeActivity(id="main", name="main", label="Main", root=main_start)
    main_start.activity = main_act
    main_start.group = main_act
    main_act.activity = main_act
    main_act.group = main_act

    triage_start = TriccNodeActivityStart(
        id="ts", name="triage_start", label="Triage start", process="triage"
    )
    triage_act = TriccNodeActivity(id="ta", name="triage", label="Triage", root=triage_start)
    triage_start.activity = triage_act
    triage_start.group = triage_act
    triage_act.activity = triage_act
    triage_act.group = triage_act

    note = TriccNodeNote(id="n1", name="fever_note", label="Fever?", activity=triage_act)
    note.activity = triage_act
    note.group = triage_act
    triage_start.next_nodes.add(note)
    note.prev_nodes.add(triage_start)

    dangling = TriccNodeCalculate(
        id="c1", name="dangling_flag", label="flag", activity=triage_act
    )
    dangling.activity = triage_act
    dangling.group = triage_act
    triage_act.calculates.append(dangling)

    main_start.next_nodes.add(triage_act)
    triage_act.prev_nodes.add(main_start)
    return main_start, triage_act, note, dangling


class TestProcessForwardedOnRecursiveWalk(unittest.TestCase):
    def test_nested_activity_and_dangling_calc_keep_process_list(self):
        main_start, _triage_act, note, dangling = _triage_graph()
        process = ["main"]
        seen = []

        def callback(node, process=None, **kwargs):
            name = getattr(node, "name", None)
            value = process[0] if process else None
            seen.append((name, value, process is process_list))
            return True

        process_list = process
        walktrhough_tricc_node_processed_stached(
            main_start,
            callback,
            OrderedSet(),
            OrderedSet(),
            0,
            recursive=True,
            process=process,
        )

        by_name = {name: (value, same) for name, value, same in seen}
        self.assertIn("fever_note", by_name)
        self.assertEqual(by_name["fever_note"][0], "triage")
        self.assertTrue(by_name["fever_note"][1], "process list object must be forwarded")
        self.assertIn("dangling_flag", by_name)
        self.assertEqual(by_name["dangling_flag"][0], "triage")
        self.assertTrue(by_name["dangling_flag"][1])
        self.assertIsNotNone(process)
        self.assertEqual(process[0], "triage")

    def test_process_restored_when_callback_fails_inside_process_switch(self):
        main_start, triage_act, _note, _dangling = _triage_graph()
        process = ["main"]
        seen = []

        def callback(node, process=None, **kwargs):
            seen.append((getattr(node, "name", None), process[0] if process else None))
            if node is triage_act:
                self.assertEqual(process[0], "triage")
                return False
            return True

        walktrhough_tricc_node_processed_stached(
            triage_act,
            callback,
            OrderedSet(),
            OrderedSet(),
            0,
            recursive=False,
            process=process,
        )
        self.assertEqual(process[0], "main")
        self.assertEqual(seen[0], ("triage", "triage"))


class TestOperatorDispatchAcceptsOriginalReferences(unittest.TestCase):
    def test_html_dispatch_passes_original_references(self):
        class _Html(HTMLStrategy):
            def validate(self):
                pass

        strategy = _Html(MagicMock(), "/tmp/html_walk_context")
        op = TriccOperation(
            operator=TriccOperator.AND,
            reference=[TriccStatic(True), TriccStatic(True)],
        )
        result = strategy.get_tricc_operation_expression(op)
        self.assertEqual(result, "true && true")

    def test_base_operation_stubs_accept_original_references(self):
        params = inspect.signature(BaseOutPutStrategy.tricc_operation_and).parameters
        self.assertIn("original_references", params)


class _CountingStrategy(BaseOutPutStrategy):
    def __init__(self, project, output_path):
        super().__init__(project, output_path)
        self.relevance_calls = 0
        self.exported = False

    def generate_base(self, node, processed_nodes=None, stashed_nodes=None, process=None, warn=False, **kwargs):
        return True

    def generate_relevance(
        self, node, processed_nodes=None, stashed_nodes=None, process=None, warn=False, **kwargs
    ):
        self.relevance_calls += 1
        return True

    def generate_calculate(
        self, node, processed_nodes=None, stashed_nodes=None, process=None, warn=False, **kwargs
    ):
        return True

    def generate_export(
        self, node, processed_nodes=None, stashed_nodes=None, process=None, warn=False, **kwargs
    ):
        return True

    def export(self, start_pages=None, version=None, **kwargs):
        self.exported = True

    def validate(self):
        pass


class TestBaseExecuteRunsRelevancePass(unittest.TestCase):
    def test_execute_invokes_generate_relevance(self):
        start = TriccNodeMainStart(id="s", name="start", label="Start", process="main", form_id="walk")
        activity = TriccNodeActivity(id="a", name="main", label="Main", root=start)
        start.activity = activity
        start.group = activity
        activity.activity = activity
        activity.group = activity
        project = TriccProject(pages={"main": activity}, start_pages={"main": activity})
        strategy = _CountingStrategy(project, "/tmp/walk_context_execute")
        strategy.execute()
        self.assertGreater(strategy.relevance_calls, 0)
        self.assertTrue(strategy.exported)


class TestStashedNodeFuncStartsWithProcess(unittest.TestCase):
    def test_default_process_is_main_list_not_none(self):
        start = TriccNodeMainStart(id="s", name="start", label="Start", process="main")
        activity = TriccNodeActivity(id="a", name="main", label="Main", root=start)
        start.activity = activity
        start.group = activity
        activity.activity = activity
        activity.group = activity
        seen = []

        def callback(node, process=None, **kwargs):
            seen.append(process)
            return True

        stashed_node_func(start, callback)
        self.assertTrue(seen)
        self.assertIsNotNone(seen[0])
        self.assertEqual(seen[0][0], "main")
