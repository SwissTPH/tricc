"""Note boxes keep authored spacing, line breaks, and emphasis after conversion.

Draw.io stores HTML on notes; ODK/CHT labels are Markdown. These tests convert
the same HTML authors put in a note and check the exported label: bold/italic
markers wrap the same phrases, line breaks stay line breaks, lists stay lists,
and leftover HTML/entities are not shipped.

See feature/20260909-display-message-ast.md.
"""

from __future__ import annotations

import html as html_lib
import os
import re
import tempfile
import unittest

import pandas as pd
from lxml import etree

from tests.helpers import get_node_by_name, load_yaml_project
from tricc_oo.converters.drawio_type_map import TYPE_MAP
from tricc_oo.converters.xml_to_tricc import add_tricc_base_node
from tricc_oo.models.base import TriccNodeType
from tricc_oo.models.tricc import TriccNodeActivity, TriccNodeMainStart, TriccNodeNote
from tricc_oo.serializers.xls_form import CHOICE_MAP, SURVEY_MAP
from tricc_oo.strategies.output.xls_form import XLSFormStrategy
from tricc_oo.strategies.registry import get_output_strategy
from tricc_oo.visitors.text_injection import load_display_text, serialize_injection_for_js_text

FIXTURE = os.path.join(os.path.dirname(__file__), "data", "yaml", "note_display_formatting.yaml")

# Tags draw.io notes actually use for emphasis / structure. Leftover tags mean
# conversion skipped the string (remove_html no-ops when there is no space).
LEFTOVER_HTML_RE = re.compile(
    r"</?(?:b|strong|i|em|u|div|span|font|ul|ol|li|br|p)\b[^>]*>",
    re.IGNORECASE,
)


def normalize_odk_markdown(text):
    """Treat markdown hard-breaks (two spaces + newline) as a plain newline."""
    if not isinstance(text, str):
        return text
    return text.replace("\r\n", "\n").replace("\r", "\n").replace("  \n", "\n")


def odk_label_from_authored(raw):
    """YAML / display-text path: HTML string → ODK label."""
    return serialize_injection_for_js_text(load_display_text(raw))


def parse_drawio_note(html_label, object_id="n1"):
    """Same path as a draw.io note object (mandatory label is HTML-cleaned, then ${REF})."""
    xml = f"""
    <diagram id="d1">
      <root>
        <object id="{object_id}" odk_type="note" name="demo.note"
                label="{html_lib.escape(html_label, quote=True)}"/>
      </root>
    </diagram>
    """
    diagram = etree.fromstring(xml)
    activity = TriccNodeActivity(
        id="a1",
        name="act",
        label="Act",
        root=TriccNodeMainStart(id="s1", name="s", label="S"),
    )
    entry = TYPE_MAP[TriccNodeType.note]
    elm = diagram.find(f".//*[@id='{object_id}']")
    nodes = {}
    add_tricc_base_node(
        diagram,
        nodes,
        entry["model"],
        [elm],
        activity,
        attributes=entry["attributes"],
        mandatory_attributes=entry["mandatory_attributes"],
        defaults=entry.get("defaults"),
    )
    return [n for n in nodes.values() if isinstance(n, TriccNodeNote)][0]


def odk_label_from_drawio(html_label):
    return serialize_injection_for_js_text(parse_drawio_note(html_label).label)


# Authored HTML (as in draw.io) → expected ODK Markdown. Cases that currently
# convert correctly through remove_html + injection serialize.
PASSING_AUTHORED_CASES = [
    (
        "plain",
        "Take the child to the emergency room.",
        "Take the child to the emergency room.",
    ),
    ("bold", "<b>Hello world</b>", "**Hello world**"),
    ("strong", "<strong>Hello world</strong>", "**Hello world**"),
    ("italic", "<i>italic text</i>", "*italic text*"),
    ("inline_bold", "Give <b>dose</b> now", "Give **dose** now"),
    ("br_newline", "Line one<br>Line two", "Line one\nLine two"),
    (
        "list_with_spaces",
        "<ul><li>First item</li><li>Second item</li></ul>",
        "- First item\n- Second item",
    ),
    (
        "inject_plain",
        "Patient is ${age} years old",
        "Patient is ${age} years old",
    ),
    (
        "inject_bold_token",
        "Age is <b>${age}</b> years",
        "Age is **${age}** years",
    ),
    (
        "inject_bold_phrase",
        "<b>Give ${dose} mg</b> of amoxicillin.",
        "**Give ${dose} mg** of amoxicillin.",
    ),
]


class TestNoteAuthoredLook(unittest.TestCase):
    """HTML authored on a note becomes the same Markdown clinicians should see."""

    def test_display_text_path_matches_authored_look(self):
        for name, authored, expected in PASSING_AUTHORED_CASES:
            with self.subTest(name=name, path="yaml"):
                actual = normalize_odk_markdown(odk_label_from_authored(authored))
                self.assertEqual(actual, expected)
                self.assertIsNone(LEFTOVER_HTML_RE.search(actual))

    def test_drawio_path_matches_authored_look(self):
        for name, authored, expected in PASSING_AUTHORED_CASES:
            with self.subTest(name=name, path="drawio"):
                actual = normalize_odk_markdown(odk_label_from_drawio(authored))
                self.assertEqual(actual, expected)
                self.assertIsNone(LEFTOVER_HTML_RE.search(actual))

    def test_internal_spaces_are_kept(self):
        authored = "Give  two spaces here"
        for actual in (
            odk_label_from_authored(authored),
            odk_label_from_drawio(authored),
        ):
            with self.subTest(actual=actual):
                self.assertIn("Give", actual)
                self.assertIn("two spaces", actual)
                self.assertNotIn("Givetwo", actual)

    def test_no_trailing_blank_line_on_single_paragraph(self):
        actual = odk_label_from_authored("<b>Hello world</b>")
        self.assertEqual(actual.rstrip("\n"), actual)


class TestNoteAuthoredLookKnownGaps(unittest.TestCase):
    """Desired look that convert incorrectly today (space-guard / stripped divs).

    Remove ``expectedFailure`` when feature/20260909-display-message-ast.md lands.
    """

    @unittest.expectedFailure
    def test_short_bold_without_space_is_markdown_not_html(self):
        for actual in (
            odk_label_from_authored("<b>Yes</b>"),
            odk_label_from_drawio("<b>Yes</b>"),
        ):
            with self.subTest(actual=actual):
                self.assertEqual(actual, "**Yes**")
                self.assertNotIn("<b>", actual)

    @unittest.expectedFailure
    def test_div_line_break_is_kept(self):
        # draw.io uses <div> when the author presses Enter in a note.
        authored = "Line one<div>Line two</div>"
        for actual in (
            normalize_odk_markdown(odk_label_from_authored(authored)),
            normalize_odk_markdown(odk_label_from_drawio(authored)),
        ):
            with self.subTest(actual=actual):
                self.assertEqual(actual, "Line one\nLine two")
                self.assertNotEqual(actual, "Line oneLine two")

    @unittest.expectedFailure
    def test_nbsp_becomes_a_space(self):
        for actual in (
            odk_label_from_authored("Hello&nbsp;world"),
            odk_label_from_drawio("Hello&nbsp;world"),
        ):
            with self.subTest(actual=actual):
                self.assertEqual(actual, "Hello world")
                self.assertNotIn("&nbsp;", actual)

    @unittest.expectedFailure
    def test_short_list_items_become_markdown(self):
        authored = "<ul><li>First</li><li>Second</li></ul>"
        for actual in (
            normalize_odk_markdown(odk_label_from_authored(authored)),
            normalize_odk_markdown(odk_label_from_drawio(authored)),
        ):
            with self.subTest(actual=actual):
                self.assertEqual(actual, "- First\n- Second")
                self.assertNotIn("<li>", actual)

    @unittest.expectedFailure
    def test_div_after_bold_sentence_starts_a_new_line(self):
        authored = (
            "<b>Emergency case</b>: Child needs "
            "<b>immediate emergency treatment!</b>"
            "<div>Take child to ER.</div>"
        )
        expected = (
            "**Emergency case**: Child needs **immediate emergency treatment!**\n"
            "Take child to ER."
        )
        for actual in (
            normalize_odk_markdown(odk_label_from_authored(authored)),
            normalize_odk_markdown(odk_label_from_drawio(authored)),
        ):
            with self.subTest(actual=actual):
                self.assertEqual(actual, expected)


class TestNoteXlsFormSurveyLabels(unittest.TestCase):
    """Full YAML → XLSForm conversion: survey labels match the authored look."""

    @classmethod
    def _reset_shared_frames(cls):
        XLSFormStrategy.df_survey = pd.DataFrame(columns=SURVEY_MAP.keys())
        XLSFormStrategy.df_calculate = pd.DataFrame(columns=SURVEY_MAP.keys())
        XLSFormStrategy.df_choice = pd.DataFrame(columns=CHOICE_MAP.keys())

    def _survey_labels(self):
        self._reset_shared_frames()
        with tempfile.TemporaryDirectory() as out_dir:
            project = load_yaml_project(FIXTURE)
            strategy = get_output_strategy("XLSFormStrategy")(project, out_dir)
            strategy.execute()
            xls = os.path.join(out_dir, "note-display-formatting.xlsx")
            survey = pd.read_excel(xls, sheet_name="survey")
        labels = {}
        for _, row in survey.iterrows():
            name = row.get("name")
            if isinstance(name, str) and name:
                raw = row.get("label")
                labels[name] = "" if pd.isna(raw) else str(raw)
        return labels

    def test_xlsform_note_labels_match_authored_look(self):
        labels = self._survey_labels()
        expected = {
            "note_plain": "Take the child to the emergency room.",
            "note_bold": "**Hello world**",
            "note_italic": "*italic text*",
            "note_inline_bold": "Give **dose** now",
            "note_br": "Line one\nLine two",
            "note_list": "- First item\n- Second item",
            "note_inject": "Patient is ${age} years old",
            "note_inject_bold": "Age is **${age}** years",
            "note_bold_phrase_with_ref": "**Give ${age} mg** of amoxicillin.",
        }
        for name, want in expected.items():
            with self.subTest(name=name):
                self.assertIn(name, labels)
                actual = normalize_odk_markdown(labels[name])
                self.assertEqual(actual, want)
                self.assertIsNone(LEFTOVER_HTML_RE.search(actual))

    def test_yaml_nodes_keep_the_same_labels_before_export(self):
        project = load_yaml_project(FIXTURE)
        activity = project.pages["note_display_formatting"]
        cases = {
            "note_plain": "Take the child to the emergency room.",
            "note_bold": "**Hello world**",
            "note_italic": "*italic text*",
            "note_br": "Line one\nLine two",
            "note_inject": "Patient is ${age} years old",
        }
        for name, want in cases.items():
            with self.subTest(name=name):
                node = get_node_by_name(activity, name)
                self.assertIsInstance(node, TriccNodeNote)
                actual = normalize_odk_markdown(serialize_injection_for_js_text(node.label))
                self.assertEqual(actual, want)


if __name__ == "__main__":
    unittest.main()
