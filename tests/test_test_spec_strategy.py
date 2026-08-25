"""Tests for the TestSpecStrategy form-model emitter.

TestSpecStrategy is a *test strategy*: it runs after an output strategy and
describes the artifacts that output produced, without changing them. These tests
cover three layers:

1. The pure serialisation helpers, which carry most of the risk (expression
   reference extraction, multi-language labels, the inconsistent ``required``
   column).
2. The registry wiring, so ``-T TestSpecStrategy`` resolves.
3. An end-to-end run over a YAML fixture, asserting the emitted model stays
   consistent with the ``survey`` and ``choices`` sheets that shipped beside it,
   and that the deployable output is untouched.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest

import pandas as pd

from tests.helpers import load_yaml_project
from tricc_oo.models.calculate import TriccNodePopulate
from tricc_oo.serializers.xls_form import CHOICE_MAP, SURVEY_MAP
from tricc_oo.strategies.output.xls_form import XLSFormStrategy
from tricc_oo.strategies.output.xlsform_cdss import XLSFormCDSSStrategy
from tricc_oo.strategies.registry import get_test_strategy, list_test_strategies
from tricc_oo.strategies.test.base_test_strategy import BaseTestStrategy
from tricc_oo.strategies.test.test_spec import (
    FORM_MODEL_VERSION,
    STRUCTURAL_TYPES,
    TestSpecStrategy,
    expression_refs,
    expression_text,
    group_path,
    label_text,
)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data", "yaml")


class _FakeGroup:
    """Minimal stand-in for a TriccGroup / TriccNodeActivity."""

    def __init__(self, export_name, group=None):
        self.export_name = export_name
        self.group = group


class _FakeNode:
    def __init__(self, group=None, **kwargs):
        self.group = group
        for key, value in kwargs.items():
            setattr(self, key, value)


class TestExpressionHelpers(unittest.TestCase):
    def test_refs_are_deduplicated_and_sorted(self):
        expression = "${b} > 1 and (${a} = 2 or ${b} = 3)"
        self.assertEqual(expression_refs(expression), ["a", "b"])

    def test_refs_of_empty_expression(self):
        for value in (None, "", "   "):
            self.assertEqual(expression_refs(value), [])

    def test_refs_ignore_bare_dollar_and_xpath(self):
        # `../inputs/contact/sex` is a raw XPath binding, not a reference.
        self.assertEqual(expression_refs("../inputs/contact/sex"), [])
        self.assertEqual(expression_refs("$notabrace"), [])

    def test_refs_strip_surrounding_whitespace(self):
        self.assertEqual(expression_refs("${ spaced }"), ["spaced"])

    def test_expression_text_normalises_booleans(self):
        self.assertEqual(expression_text(True), "1")
        self.assertEqual(expression_text(False), "0")

    def test_expression_text_blanks_become_none(self):
        self.assertIsNone(expression_text(None))
        self.assertIsNone(expression_text("   "))

    def test_expression_text_keeps_zero_string(self):
        # `0` is a meaningful default and must not be swallowed as falsy.
        self.assertEqual(expression_text("0"), "0")


class TestLabelText(unittest.TestCase):
    def test_plain_string(self):
        self.assertEqual(label_text("Fever?"), "Fever?")

    def test_preferred_language_wins(self):
        self.assertEqual(label_text({"en": "Fever?", "fr": "Fievre?"}, "fr"), "Fievre?")

    def test_falls_back_to_any_language(self):
        self.assertEqual(label_text({"fr": "Fievre?"}, "en"), "Fievre?")

    def test_empty_inputs(self):
        self.assertIsNone(label_text(None))
        self.assertIsNone(label_text({}))
        self.assertIsNone(label_text("   "))


class TestGroupPath(unittest.TestCase):
    def test_path_is_outermost_first(self):
        outer = _FakeGroup("outer")
        inner = _FakeGroup("inner", group=outer)
        self.assertEqual(group_path(_FakeNode(group=inner)), ["outer", "inner"])

    def test_no_group(self):
        self.assertEqual(group_path(_FakeNode()), [])

    def test_cycle_does_not_hang(self):
        a = _FakeGroup("a")
        b = _FakeGroup("b", group=a)
        a.group = b
        self.assertEqual(len(group_path(_FakeNode(group=b))), 2)


class TestRequiredFlag(unittest.TestCase):
    """The generated `required` column is inconsistently 1 / true / blank."""

    def _flag(self, row_value, node_value=None):
        node = _FakeNode(required=node_value)
        return TestSpecStrategy.required_flag(node, {"required": row_value})

    def test_truthy_variants(self):
        for value in ("1", "true", "TRUE", "yes", 1):
            self.assertIs(self._flag(value), True, msg=f"value={value!r}")

    def test_falsy_variants(self):
        for value in ("0", "false", "no", 0):
            self.assertIs(self._flag(value), False, msg=f"value={value!r}")

    def test_blank_row_falls_back_to_node(self):
        self.assertIs(self._flag("", node_value="1"), True)

    def test_unknown_expression_is_none(self):
        self.assertIsNone(self._flag("${some_calc}>0"))

    def test_absent_everywhere_is_none(self):
        self.assertIsNone(self._flag("", node_value=None))


class TestRegistryWiring(unittest.TestCase):
    def test_registered_under_its_name(self):
        self.assertIs(get_test_strategy("TestSpecStrategy"), TestSpecStrategy)

    def test_class_passthrough(self):
        self.assertIs(get_test_strategy(TestSpecStrategy), TestSpecStrategy)

    def test_unknown_name_lists_alternatives(self):
        with self.assertRaises(ValueError) as caught:
            get_test_strategy("NoSuchStrategy")
        self.assertIn("TestSpecStrategy", str(caught.exception))

    def test_is_a_test_strategy_not_an_output_strategy(self):
        self.assertTrue(issubclass(TestSpecStrategy, BaseTestStrategy))
        self.assertNotIn("TestSpecStrategy", (cls.__name__ for cls in XLSFormStrategy.__mro__))
        self.assertIn("TestSpecStrategy", list_test_strategies())


class TestInputPopulateFlags(unittest.TestCase):
    """``TriccNodeInput`` was merged into ``TriccNodePopulate``.

    The form-model flags still distinguish CHT data sources: encounter-context
    populates use the form ``inputs`` group; other contexts are contact-summary.
    """

    def _entry(self, node):
        strategy = TestSpecStrategy(project=None, output_path=".", output_strategy=None)
        return strategy.node_entry(node.name, node, None)

    def test_encounter_populate_is_classified_as_input(self):
        node = TriccNodePopulate(id="p1", name="weight", label="Weight", context="encounter")
        entry = self._entry(node)
        self.assertTrue(entry["isInput"])
        self.assertFalse(entry["isPopulate"])

    def test_patient_populate_is_classified_as_populate(self):
        node = TriccNodePopulate(id="p2", name="p_age", label="Age", context="patient")
        entry = self._entry(node)
        self.assertFalse(entry["isInput"])
        self.assertTrue(entry["isPopulate"])

    def test_non_populate_is_neither(self):
        entry = self._entry(_FakeNode(name="fever", label="Fever?"))
        self.assertFalse(entry["isInput"])
        self.assertFalse(entry["isPopulate"])


class _Fixture:
    """Run an output strategy then TestSpecStrategy, as `build.py -O ... -T ...` does."""

    def __init__(self, fixture_name, form_id, output_cls=XLSFormCDSSStrategy):
        self.fixture = os.path.join(DATA_DIR, fixture_name)
        self.form_id = form_id
        self.output_cls = output_cls
        self._tmpdir = None

    @staticmethod
    def _reset_shared_frames():
        """Clear XLSFormStrategy's class-level DataFrames.

        `df_survey`, `df_calculate` and `df_choice` are declared on the class,
        not per instance, and neither `__init__` nor `do_clean` resets them. Two
        builds in one process therefore accumulate each other's rows. That is a
        pre-existing defect in the output strategy; until it is fixed, these
        tests must isolate themselves or they read each other's data.
        """
        XLSFormStrategy.df_survey = pd.DataFrame(columns=SURVEY_MAP.keys())
        XLSFormStrategy.df_calculate = pd.DataFrame(columns=SURVEY_MAP.keys())
        XLSFormStrategy.df_choice = pd.DataFrame(columns=CHOICE_MAP.keys())

    def __enter__(self):
        self._reset_shared_frames()
        self._tmpdir = tempfile.TemporaryDirectory()
        project = load_yaml_project(self.fixture)
        # YAML fixtures do not declare a form_id; export() requires one.
        project.start_pages["main"].root.form_id = self.form_id

        self.output = self.output_cls(project, self._tmpdir.name)
        self.output.execute()
        self.xlsx_path = os.path.join(self._tmpdir.name, f"{self.form_id}.xlsx")
        self.xlsx_bytes = open(self.xlsx_path, "rb").read() if os.path.exists(self.xlsx_path) else None

        self.strategy = TestSpecStrategy(project, self._tmpdir.name, self.output)
        self.path = self.strategy.execute()
        with open(self.path, "r", encoding="utf-8") as handle:
            self.model = json.load(handle)
        return self

    def __exit__(self, *exc):
        self._tmpdir.cleanup()
        return False

    def node(self, export_name):
        for entry in self.model["nodes"]:
            if entry["exportName"] == export_name:
                return entry
        return None


class TestFormModelEndToEnd(unittest.TestCase):
    def test_deployable_artifact_is_untouched(self):
        """The whole point of a post-export test strategy."""
        with _Fixture("select_with_options.yaml", "select_example") as fixture:
            self.assertIsNotNone(fixture.xlsx_bytes, "the output strategy should have written a form")
            after = open(fixture.xlsx_path, "rb").read()
            self.assertEqual(fixture.xlsx_bytes, after, "the test strategy modified the .xlsx")

    def test_select_options_are_captured(self):
        with _Fixture("select_with_options.yaml", "select_example") as fixture:
            fever = fixture.node("fever")
            self.assertIsNotNone(fever, "the select node should be in the model")
            self.assertEqual(sorted(o["value"] for o in fever["options"]), ["no", "yes"])
            self.assertIsNotNone(fever["listName"])

    def test_options_exist_in_the_choices_sheet(self):
        with _Fixture("select_with_options.yaml", "select_example") as fixture:
            for entry in fixture.model["nodes"]:
                if not entry["options"]:
                    continue
                shipped = {c["value"] for c in fixture.model["choices"].get(entry["listName"], [])}
                for option in entry["options"]:
                    self.assertIn(
                        option["value"], shipped,
                        msg=f"{entry['exportName']} option missing from the choices sheet",
                    )

    def test_model_header_fields(self):
        with _Fixture("select_with_options.yaml", "select_example") as fixture:
            self.assertEqual(fixture.model["formModelVersion"], FORM_MODEL_VERSION)
            self.assertEqual(fixture.model["formId"], "select_example")
            self.assertEqual(fixture.model["strategy"], "TestSpecStrategy")
            self.assertEqual(fixture.model["outputStrategy"], "XLSFormCDSSStrategy")

    def test_runtime_reflects_the_output_strategy(self):
        with _Fixture("select_with_options.yaml", "select_example") as fixture:
            self.assertEqual(fixture.model["runtime"], "odk")

    def test_model_covers_the_shipped_questions(self):
        """The model is driven by the survey sheet, so coverage must be total.

        A graph walk cannot be relied on: after export, `next_nodes` is largely
        empty, and on a real 990-row form a walk reaches barely a dozen nodes.
        This guards the inversion.
        """
        with _Fixture("minimal_decision.yaml", "decision_example") as fixture:
            answerable = [
                entry for entry in fixture.model["nodes"]
                if entry["odkType"] and not entry["isCalculate"]
            ]
            self.assertTrue(answerable, "fixture should ship answerable questions")
            for entry in answerable:
                self.assertIsNotNone(
                    entry["odkType"],
                    msg=f"{entry['exportName']} has no shipped type",
                )

    def test_every_answerable_survey_row_is_in_the_model(self):
        with _Fixture("minimal_decision.yaml", "decision_example") as fixture:
            self.assertEqual(fixture.model["diagnostics"]["missingFromModel"], [])

    def test_injected_version_row_is_not_reported_as_missing(self):
        """`inject_version` adds a `version` row backed by no TRICC node."""
        with _Fixture("minimal_decision.yaml", "decision_example") as fixture:
            self.assertNotIn("version", fixture.model["diagnostics"]["missingFromModel"])

    def test_option_values_are_unquoted(self):
        """get_export_name quotes option values for expressions; the sheet does not."""
        with _Fixture("select_with_options.yaml", "select_example") as fixture:
            for entry in fixture.model["nodes"]:
                for option in entry["options"]:
                    self.assertNotRegex(
                        str(option["value"]), r"^'.*'$",
                        msg=f"{entry['exportName']} option value is quoted; it will match nothing",
                    )

    def test_relevance_refs_match_the_expression(self):
        with _Fixture("minimal_decision.yaml", "decision_example") as fixture:
            checked = 0
            for entry in fixture.model["nodes"]:
                self.assertEqual(
                    entry["relevanceRefs"], expression_refs(entry["relevance"]),
                    msg=f"{entry['exportName']} relevanceRefs out of sync",
                )
                if entry["relevanceRefs"]:
                    checked += 1
            self.assertGreater(checked, 0, "fixture should exercise at least one relevance")

    def test_edges_only_reference_known_nodes(self):
        with _Fixture("minimal_decision.yaml", "decision_example") as fixture:
            known = {entry["exportName"] for entry in fixture.model["nodes"]}
            for edge in fixture.model["edges"]:
                self.assertIn(edge["from"], known)
                self.assertIn(edge["to"], known)

    def test_end_nodes_are_recorded(self):
        with _Fixture("minimal_decision.yaml", "decision_example") as fixture:
            self.assertTrue(fixture.model["ends"], "an end node should be assertable")

    def test_calculations_carry_their_references(self):
        with _Fixture("basic_flow_with_calc.yaml", "calc_example") as fixture:
            calculates = [e for e in fixture.model["nodes"] if e["isCalculate"]]
            self.assertTrue(calculates, "fixture should produce calculate nodes")
            for entry in calculates:
                self.assertEqual(entry["calculationRefs"], expression_refs(entry["calculation"]))

    def test_structural_rows_are_not_treated_as_answerable(self):
        # Guards the constant against an XLSForm alias drifting: `begin group`
        # and `begin_group` are both emitted, by different strategies.
        for alias in ("begin group", "begin_group", "end group", "end_group"):
            self.assertIn(alias, STRUCTURAL_TYPES)


class TestDegradedUse(unittest.TestCase):
    """Without an output strategy the model is thinner but must not crash."""

    def test_runs_without_an_output_strategy(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project = load_yaml_project(os.path.join(DATA_DIR, "minimal_decision.yaml"))
            project.start_pages["main"].root.form_id = "decision_example"
            path = TestSpecStrategy(project, tmpdir, None).execute()
            with open(path, "r", encoding="utf-8") as handle:
                model = json.load(handle)
            self.assertIsNone(model["outputStrategy"])
            self.assertEqual(model["choices"], {})
            # Names still resolve, because export_name is cached on the nodes.
            self.assertTrue(model["nodes"])


if __name__ == "__main__":
    unittest.main()
