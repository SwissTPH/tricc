"""YAML edge labels branch the flow as in draw.io.

See fix/20261012-yaml-edge-labels.md.
"""

import glob
import os
import subprocess
import sys
import tempfile
import unittest

import pandas as pd

from tricc_oo.converters.utils import quoted_literal, unquote_literal, xpath_literal
from tricc_oo.converters.xml_to_tricc import answer_edge_condition, get_yes_no_options, parse_expression
from tricc_oo.models.base import TriccEdge, TriccOperator, TriccReference
from tricc_oo.models.tricc import (
    TriccNodeSelectMultiple,
    TriccNodeSelectOne,
    TriccNodeSelectOption,
    TriccNodeSelectYesNo,
)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = os.path.join(REPO, "tests", "data", "yaml", "edge_labels.yaml")


def _survey(output_strategy):
    """Build the fixture in a fresh interpreter; return the survey rows by name."""
    with tempfile.TemporaryDirectory() as out:
        subprocess.run(
            [sys.executable, "tests/build.py", "-i", FIXTURE, "-o", out, "-I", "YamlStrategy", "-O", output_strategy],
            cwd=REPO,
            check=True,
            capture_output=True,
        )
        xlsx = glob.glob(os.path.join(out, "**", "*.xlsx"), recursive=True)
        survey = pd.read_excel(xlsx[0], sheet_name="survey").fillna("")
    return {row["name"]: row for _, row in survey.iterrows()}


class TestYamlEdgeLabels(unittest.TestCase):
    def _check(self, rows):
        self.assertIn("fever", rows, "select_yesno without options must be exported")
        self.assertEqual(rows["fever"]["type"], "select_one yes_no")
        fever = "${fever}"
        self.assertIn(fever, rows["temperature"]["relevance"])
        self.assertIn(fever, rows["age"]["relevance"])
        self.assertNotEqual(rows["temperature"]["relevance"], rows["age"]["relevance"])
        weight = rows["weight"]["relevance"]
        self.assertIn("${cough}", weight)
        self.assertIn("'no'", weight)
        self.assertIn(">10", rows["height"]["relevance"])
        self.assertNotIn(">10", rows["muac"]["relevance"])
        self.assertIn("<=10", rows["muac"]["relevance"])
        self.assertIn("selected(${signs}, 'rash')", rows["rash_size"]["relevance"])
        self.assertNotIn("tricc_end_", rows)

    def test_xlsform(self):
        self._check(_survey("XLSFormStrategy"))

    def test_cht(self):
        self._check(_survey("XLSFormCHTStrategy"))


def _select(cls, names, labels=None):
    select = cls(id="s1", name="s", label="S", list_name="s")
    labels = labels or names
    select.options = {
        i: TriccNodeSelectOption(id=f"o{i}", name=n, label=lbl, list_name="s", select=select)
        for i, (n, lbl) in enumerate(zip(names, labels))
    }
    return select


class TestAnswerEdge(unittest.TestCase):
    """``Answer("<code>")`` becomes a CQL condition on the edge (then a rhombus)."""

    def _answer(self, select, value):
        nodes = {select.id: select, **{o.id: o for o in select.options.values()}}
        edge = TriccEdge(id="e1", source=select.id, target="t", value=value)
        answered = answer_edge_condition(edge, nodes)
        self.assertEqual(edge.source, "s1", "the edge stays on the select")
        return answered, edge.value

    def test_select_one(self):
        self.assertEqual(self._answer(_select(TriccNodeSelectOne, ["yes", "no"]), 'Answer("no")'),
                         (True, '"no" in $this'))

    def test_select_multiple(self):
        self.assertEqual(self._answer(_select(TriccNodeSelectMultiple, ["rash", "pain"]), 'Answer("rash")'),
                         (True, '"rash" in $this'))

    def test_by_concept_code(self):
        select = _select(TriccNodeSelectOne, ["opt_a", "opt_b"])
        select.options[1].concept_code = "cough.dry"
        self.assertEqual(self._answer(select, 'Answer("cough.dry")'), (True, '"opt_b" in $this'))

    def test_yes_no(self):
        yes_no = _select(TriccNodeSelectYesNo, ["true", "false"], ["Yes", "No"])
        self.assertEqual(self._answer(yes_no, 'Answer("yes")'), (True, "$this is true"))
        self.assertEqual(self._answer(yes_no, 'Answer("no")'), (True, "$this is false"))

    def test_yes_no_by_option_name(self):
        yes_no = _select(TriccNodeSelectYesNo, ["yes", "no"], ["Oui", "Non"])
        self.assertEqual(self._answer(yes_no, 'Answer("no")'), (True, "$this is false"))

    def test_legacy_single_quotes(self):
        self.assertEqual(self._answer(_select(TriccNodeSelectOne, ["yes", "no"]), "Answer('no')"),
                         (True, '"no" in $this'))

    def test_unknown_option_still_a_condition(self):
        self.assertEqual(self._answer(_select(TriccNodeSelectOne, ["yes", "no"]), 'Answer("maybe")'),
                         (True, '"maybe" in $this'))

    def test_other_labels_untouched(self):
        self.assertEqual(self._answer(_select(TriccNodeSelectOne, ["yes", "no"]), "no"), (False, "no"))


class TestYesNoOptions(unittest.TestCase):
    def test_by_name_with_translated_label(self):
        yes, no = get_yes_no_options(_select(TriccNodeSelectYesNo, ["no", "yes"], ["Non", "Oui"]))
        self.assertEqual((yes.name, no.name), ("yes", "no"))

    def test_drawio_true_false(self):
        yes, no = get_yes_no_options(_select(TriccNodeSelectYesNo, ["true", "false"], ["Yes", "No"]))
        self.assertEqual((yes.name, no.name), ("true", "false"))

    def test_label_fallback(self):
        yes, no = get_yes_no_options(_select(TriccNodeSelectYesNo, ["a", "b"], ["Yes", "No"]))
        self.assertEqual((yes.name, no.name), ("a", "b"))


class TestStringLiterals(unittest.TestCase):
    def test_quoted_literal(self):
        self.assertEqual(quoted_literal("it's"), "'it\\'s'")
        self.assertEqual(quoted_literal("a\\b"), "'a\\\\b'")

    def test_unquote_literal(self):
        self.assertEqual(unquote_literal("'it\\'s'"), "it's")
        self.assertEqual(unquote_literal("'a\\\\b'"), "a\\b")
        self.assertEqual(unquote_literal("'\\u00e9'"), "\u00e9")
        self.assertEqual(unquote_literal("'plain'"), "plain")

    def test_xpath_literal(self):
        self.assertEqual(xpath_literal("rash"), "'rash'")
        self.assertEqual(xpath_literal("it's"), '"it\'s"')
        self.assertEqual(xpath_literal("it's \"x\""), "concat('it', \"'\", 's \"x\"')")

    def test_answer_identifier_is_a_code(self):
        op = parse_expression("", '"rash" in "signs"')
        self.assertEqual(op.operator, TriccOperator.SELECTED)
        self.assertNotIsInstance(op.reference[1], TriccReference)
        self.assertEqual(op.reference[1].value, "rash")
        op = parse_expression("", '"signs" contains "rash"')
        self.assertNotIsInstance(op.reference[1], TriccReference)

    def test_condition_round_trip(self):
        op = parse_expression("", "'it\\'s' in \"cough\"")
        self.assertEqual(op.operator, TriccOperator.SELECTED)
        self.assertEqual(op.reference[1].value, "it's")


if __name__ == "__main__":
    unittest.main()
