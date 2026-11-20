"""Plain ``text`` + rendering extension on ``_text`` (fix/20261120-fhir-text-format.md).

Run with:
    python -m pytest tests/test_strategies/test_fhir_text_format.py -v
"""

import unittest
from unittest.mock import MagicMock

from tricc_oo.converters.datadictionnary import add_concept
from tricc_oo.converters.fhir.questionnaire_item_mapper import CQF_EXT_TEXT_EXPRESSION
from tricc_oo.converters.fhir.text_format import (
    RENDERING_MARKDOWN_EXT,
    RENDERING_XHTML_EXT,
    markdown_to_plain,
    markdown_to_xhtml,
    tidy_markdown,
)
from tricc_oo.models.base import TriccReference
from tricc_oo.models.message import TriccMessage, TriccMessageText
from tricc_oo.models.tricc import (
    TriccNodeInteger,
    TriccNodeNote,
    TriccNodeSelectOne,
    TriccNodeSelectOption,
)
from tricc_oo.strategies.output.fhir_form import FHIRStrategy
from tricc_oo.strategies.output.opensrp import OpenSRPStrategy

CONVULSION_NOTE = (
    "**IF THE CHILD IS CONVULSING NOW - TREAT IMMEDIATELY**\n\n\n\n"
    "* Turn the child to his/her side\n"
    "* Do not put anything in the mouth\n\n"
    "For this child give **${diazepam_dose}ml** **Diazepam** per **rectum**"
)


def _make_strategy(text_format="markdown", code_systems=None):
    project = MagicMock()
    project.start_pages = {}
    project.pages = {}
    project.code_systems = code_systems or {}
    project.lang_code = "en"
    return FHIRStrategy(project, "/tmp/fhir_text_format_test_out", text_format=text_format)


def _find(items, link_id):
    for item in items or []:
        if item.get("linkId") == link_id:
            return item
        found = _find(item.get("item"), link_id)
        if found is not None:
            return found
    return None


def _ext(element, field, url):
    for ext in (element.get(f"_{field}") or {}).get("extension") or []:
        if ext.get("url") == url:
            return ext
    return None


class TestMarkdownConversion(unittest.TestCase):
    def test_plain_drops_markup_and_placeholders(self):
        plain = markdown_to_plain(CONVULSION_NOTE)
        self.assertEqual(
            plain,
            "IF THE CHILD IS CONVULSING NOW - TREAT IMMEDIATELY\n\n"
            "• Turn the child to his/her side\n"
            "• Do not put anything in the mouth\n\n"
            "For this child give …ml Diazepam per rectum",
        )

    def test_plain_keeps_snake_case_and_arithmetic(self):
        self.assertEqual(markdown_to_plain("weight_for_age 3*4*5"), "weight_for_age 3*4*5")
        self.assertEqual(markdown_to_plain("1. first\n2. second"), "1. first\n2. second")

    def test_tidy_repairs_broken_strong_emphasis(self):
        # markdownify output seen on Global Almanach labels
        cases = {
            "**Treat the child**\n**\n**\n**Child conscious**": "**Treat the child**\n\n**Child conscious**",
            "For **HIV exposed:\n**\n\nAssess": "For **HIV exposed:**\n\nAssess",
            "Give oral ********Ciprofloxacin********:": "Give oral Ciprofloxacin:",
            "For **H****erpes Zoster  **Keep": "For **Herpes Zoster**  Keep",
            "one dose of **VITAMIN **A now": "one dose of **VITAMIN** A now",
            "- apply for**  4 weeks**": "- apply for  **4 weeks**",
        }
        for broken, tidy in cases.items():
            with self.subTest(broken=broken):
                self.assertEqual(tidy_markdown(broken), tidy)
                self.assertNotIn("**", markdown_to_plain(broken))
                self.assertNotIn("**", markdown_to_xhtml(broken))

    def test_xhtml_is_a_namespaced_div(self):
        xhtml = markdown_to_xhtml(CONVULSION_NOTE + " & <more>")
        self.assertTrue(xhtml.startswith('<div xmlns="http://www.w3.org/1999/xhtml"><p><strong>'))
        self.assertIn("<ul><li>Turn the child to his/her side</li><li>", xhtml)
        self.assertIn("<strong>…ml</strong>", xhtml)
        self.assertIn("&amp; &lt;more&gt;", xhtml)
        self.assertNotIn("${", xhtml)

    def test_xhtml_numbered_list(self):
        self.assertEqual(
            markdown_to_xhtml("Steps:\n1. a\n2. b"),
            '<div xmlns="http://www.w3.org/1999/xhtml"><p>Steps:</p><ol><li>a</li><li>b</li></ol></div>',
        )


class TestItemText(unittest.TestCase):
    def test_note_text_is_plain_and_label_goes_to_rendering_markdown(self):
        strategy = _make_strategy()
        note = TriccNodeNote(id="n", name="label_convulsion", label=CONVULSION_NOTE)
        strategy.generate_base(note)

        item = _find(strategy.questionnaires["main"]["item"], "label_convulsion")
        self.assertEqual(item["text"], markdown_to_plain(CONVULSION_NOTE))
        ext = _ext(item, "text", RENDERING_MARKDOWN_EXT)
        self.assertIsNotNone(ext)
        self.assertTrue(ext["valueMarkdown"].startswith("**IF THE CHILD IS CONVULSING NOW"))
        self.assertIn("**…ml**", ext["valueMarkdown"])
        self.assertNotIn("\n\n\n", ext["valueMarkdown"])

    def test_html_format_writes_rendering_xhtml(self):
        strategy = _make_strategy(text_format="html")
        note = TriccNodeNote(id="n", name="label_convulsion", label=CONVULSION_NOTE)
        strategy.generate_base(note)

        item = _find(strategy.questionnaires["main"]["item"], "label_convulsion")
        self.assertIsNone(_ext(item, "text", RENDERING_MARKDOWN_EXT))
        ext = _ext(item, "text", RENDERING_XHTML_EXT)
        self.assertTrue(ext["valueString"].startswith('<div xmlns="http://www.w3.org/1999/xhtml">'))

    def test_plain_label_gets_no_extension(self):
        strategy = _make_strategy()
        strategy.generate_base(TriccNodeInteger(id="a", name="age", label="Age in months"))

        item = _find(strategy.questionnaires["main"]["item"], "age")
        self.assertEqual(item["text"], "Age in months")
        self.assertNotIn("_text", item)

    def test_text_comes_from_the_concept_display(self):
        code_systems = {}
        add_concept(code_systems, "tricc", "weight", "Weight", {})
        strategy = _make_strategy(code_systems=code_systems)
        strategy.generate_base(TriccNodeInteger(id="w", name="weight", label="**Weight** (kg)"))

        item = _find(strategy.questionnaires["main"]["item"], "weight")
        self.assertEqual(item["text"], "Weight")
        self.assertEqual(_ext(item, "text", RENDERING_MARKDOWN_EXT)["valueMarkdown"], "**Weight** (kg)")

    def test_help_and_hint_children_are_plain(self):
        strategy = _make_strategy()
        question = TriccNodeInteger(id="c", name="muac", label="MUAC")
        question.help = "Measure on the **left** arm"
        question.hint = "in *mm*"
        strategy.generate_base(question)

        parent = _find(strategy.questionnaires["main"]["item"], "muac")
        help_item = _find(parent["item"], "muac-help")
        hint_item = _find(parent["item"], "muac-hint")
        self.assertEqual(help_item["text"], "Measure on the left arm")
        help_markdown = _ext(help_item, "text", RENDERING_MARKDOWN_EXT)["valueMarkdown"]
        self.assertEqual(help_markdown, "Measure on the **left** arm")
        self.assertEqual(hint_item["text"], "in mm")
        self.assertEqual(_ext(hint_item, "text", RENDERING_MARKDOWN_EXT)["valueMarkdown"], "in *mm*")

    def test_answer_option_display_is_plain(self):
        strategy = _make_strategy()
        select = TriccNodeSelectOne(id="s", name="danger", label="Danger sign", list_name="danger")
        select.options = {
            0: TriccNodeSelectOption(
                id="o1", name="lethargic", label="**Lethargic** or unconscious", select=select, list_name="danger"
            ),
            1: TriccNodeSelectOption(id="o2", name="none", label="None", select=select, list_name="danger"),
        }
        strategy.generate_base(select)

        options = _find(strategy.questionnaires["main"]["item"], "danger")["answerOption"]
        lethargic, none = (o["valueCoding"] for o in options)
        self.assertEqual(lethargic["display"], "Lethargic or unconscious")
        self.assertEqual(
            _ext(lethargic, "display", RENDERING_MARKDOWN_EXT)["valueMarkdown"], "**Lethargic** or unconscious"
        )
        self.assertEqual(none["display"], "None")
        self.assertNotIn("_display", none)

    def test_dynamic_text_keeps_cqf_expression_next_to_rendering(self):
        strategy = _make_strategy()
        age = TriccNodeInteger(id="a", name="age", label="Age")
        note = TriccNodeNote(id="n", name="note_age", label="")
        note.label = TriccMessage(
            children=[
                TriccMessageText(value="Patient is **"),
                TriccReference("age"),
                TriccMessageText(value="** years old"),
            ]
        )
        strategy.generate_base(age)
        strategy.generate_base(note)
        strategy.process_display_text()

        item = _find(strategy.questionnaires["main"]["item"], "note_age")
        self.assertEqual(item["text"], "Patient is … years old")
        self.assertEqual(_ext(item, "text", RENDERING_MARKDOWN_EXT)["valueMarkdown"], "Patient is **…** years old")
        self.assertIsNotNone(_ext(item, "text", CQF_EXT_TEXT_EXPRESSION))

    def test_unknown_text_format_is_rejected(self):
        with self.assertRaises(ValueError):
            _make_strategy(text_format="rtf")

    def test_opensrp_forwards_text_format(self):
        project = MagicMock()
        strategy = OpenSRPStrategy(project, "/tmp/fhir_text_format_test_out", text_format="html")
        self.assertEqual(strategy.text_format, "html")


if __name__ == "__main__":
    unittest.main()
