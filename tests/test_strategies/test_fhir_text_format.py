"""Plain ``text`` + rendering extension on ``_text`` (fix/20261120-fhir-text-format.md).

Labels are built from draw.io-style HTML through ``load_display_text``, the load path.

Run with:
    python -m pytest tests/test_strategies/test_fhir_text_format.py -v
"""

import unittest
from unittest.mock import MagicMock

from tricc_oo.converters.datadictionnary import add_concept
from tricc_oo.converters.fhir.questionnaire_item_mapper import CQF_EXT_TEXT_EXPRESSION
from tricc_oo.converters.fhir.text_format import RENDERING_MARKDOWN_EXT, RENDERING_XHTML_EXT
from tricc_oo.models.tricc import (
    TriccNodeInteger,
    TriccNodeNote,
    TriccNodeSelectOne,
    TriccNodeSelectOption,
)
from tricc_oo.strategies.output.fhir_form import FHIRStrategy
from tricc_oo.strategies.output.opensrp import OpenSRPStrategy
from tricc_oo.text.model import TriccText
from tricc_oo.visitors.text_injection import (
    load_display_text as parse_html_to_message,
    serialize_injection_for_js_text,
    serialize_injection_plain,
    serialize_injection_xhtml,
)

# The convulsion note of Global Almanach (label_Zj12BMWfe8zrtVdUCvmG_78), shortened.
CONVULSION_HTML = (
    "<b>IF THE CHILD IS CONVULSING NOW - TREAT IMMEDIATELY</b><br><br><br><br>"
    "<ul><li>Turn the child to his/her side</li><li>Do not put anything in the mouth</li></ul>"
    "<br>For this child give <b>${diazepam_dose}ml</b> <b>Diazepam</b> per <b>rectum</b>"
)
CONVULSION_PLAIN = (
    "IF THE CHILD IS CONVULSING NOW - TREAT IMMEDIATELY\n\n"
    "• Turn the child to his/her side\n"
    "• Do not put anything in the mouth\n\n"  # the <br> opening the line after the list
    "For this child give …ml Diazepam per rectum"
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


class TestMessageNormalisation(unittest.TestCase):
    """Broken marks seen on Global Almanach labels are cleaned when the tree is built."""

    def test_markdown_of_broken_marks(self):
        cases = {
            "Give one dose of <b>VITAMIN </b>A now": "Give one dose of **VITAMIN** A now",
            "For <b>HIV exposed:<br></b><br>Refer": "For **HIV exposed:**\n\nRefer",
            "For <b>H</b><b>erpes Zoster </b>Keep": "For **Herpes Zoster** Keep",
            # spaces collapse as in HTML (before: "apply for  **4 weeks**")
            "apply for<b>  4 weeks</b>": "apply for **4 weeks**",
            "Give oral <b></b><b> </b>Ciprofloxacin": "Give oral Ciprofloxacin",
            "a<br><br><br><br>b": "a\n\nb",
            "<ul><li>a<br><br></li><li>b</li></ul>": "- a\n- b",
        }
        for html, markdown in cases.items():
            with self.subTest(html=html):
                self.assertEqual(serialize_injection_for_js_text(parse_html_to_message(html)), markdown)

    def test_marks_keep_their_kind(self):
        message = parse_html_to_message("<b>a</b><i>b</i><b>c</b>")
        kinds = [n["marks"][0]["type"] for n in message.doc["content"][0]["content"]]
        self.assertEqual(kinds, ["bold", "italic", "bold"])

    def test_token_split_over_inline_elements_is_a_reference(self):
        message = parse_html_to_message('give <span>${</span><span style="x">ors_dose} ml</span> of ORS')
        self.assertIsInstance(message, TriccText)
        self.assertEqual(message.names(), ["ors_dose"])

    def test_a_label_without_formatting_stays_a_string(self):
        self.assertEqual(parse_html_to_message("<b></b>Age in months"), "Age in months")


class TestTypedMarkdown(unittest.TestCase):
    """Markdown the author typed into the label HTML is read as marks and lists at load."""

    def _markdown(self, html):
        return serialize_injection_for_js_text(parse_html_to_message(html))

    def test_typed_bold_and_bullets(self):
        html = (
            "<div>**IF CONVULSING NOW**</div><div><br></div><div>* Turn the child</div>"
            "<div>* Avoid things</div><div><br></div><div>Give **Diazepam rectally**</div>"
        )
        message = parse_html_to_message(html)
        self.assertEqual(
            serialize_injection_plain(message, "…"),
            "IF CONVULSING NOW\n\n• Turn the child\n• Avoid things\n\nGive Diazepam rectally",
        )
        self.assertEqual(
            self._markdown(html),
            "**IF CONVULSING NOW**\n\n- Turn the child\n- Avoid things\n\nGive **Diazepam rectally**",
        )

    def test_markers_around_a_reference_split_over_spans(self):
        message = parse_html_to_message('give **<span>${</span><span style="x">ors_dose} ml&nbsp;</span>ORS** now')
        interp = next(n for n in message.doc["content"][0]["content"] if n["type"] == "interp")
        self.assertEqual(interp["marks"], [{"type": "bold"}])
        self.assertEqual(serialize_injection_plain(message, "…"), "give … ml ORS now")

    def test_markers_in_their_own_bold_elements(self):
        html = 'Give oral <b>**</b><b style="x">Ciprofloxacin</b><b>**</b>:<ul><li>**2** times per day</li></ul>'
        self.assertEqual(self._markdown(html), "Give oral **Ciprofloxacin**:\n- **2** times per day")

    def test_bold_closed_before_an_html_list(self):
        html = "<p>Give first dose of&nbsp;**CEFTRIAXONE (IM)**</p><ul><li>80-100mg/kg/dose</li></ul><p>Dissolving</p>"
        self.assertEqual(
            serialize_injection_plain(parse_html_to_message(html), "…"),
            "Give first dose of CEFTRIAXONE (IM)\n• 80-100mg/kg/dose\nDissolving",
        )

    def test_typed_ordered_list(self):
        message = parse_html_to_message("1. Give **extra fluid**<br>2. Continue feeding")
        self.assertEqual(message.doc["content"][0]["type"], "orderedList")

    def test_text_without_markdown_is_unchanged(self):
        for text in ("weight_for_age in kg", "Age (months) - 2 * 3", "Headache # 2 [left]"):
            with self.subTest(text=text):
                self.assertEqual(parse_html_to_message(text), text)


class TestRenderers(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(serialize_injection_plain(parse_html_to_message(CONVULSION_HTML), "…"), CONVULSION_PLAIN)

    def test_plain_keeps_text_as_written(self):
        self.assertEqual(serialize_injection_plain("weight_for_age 3*4*5", "…"), "weight_for_age 3*4*5")

    def test_xhtml(self):
        xhtml = serialize_injection_xhtml(parse_html_to_message(CONVULSION_HTML + " &amp; &lt;more&gt;"), "…")
        self.assertEqual(
            xhtml,
            '<div xmlns="http://www.w3.org/1999/xhtml">'
            "<p><strong>IF THE CHILD IS CONVULSING NOW - TREAT IMMEDIATELY</strong></p>"
            "<ul><li>Turn the child to his/her side</li><li>Do not put anything in the mouth</li></ul>"
            "<p>For this child give <strong>…ml</strong> <strong>Diazepam</strong> per <strong>rectum</strong>"
            " &amp; &lt;more&gt;</p></div>",
        )

    def test_xhtml_line_break_and_ordered_list(self):
        message = parse_html_to_message("<i>Steps</i><br>now<ol><li>a</li><li>b</li></ol>")
        self.assertEqual(
            serialize_injection_xhtml(message, "…"),
            '<div xmlns="http://www.w3.org/1999/xhtml">'
            "<p><em>Steps</em><br/>now</p><ol><li>a</li><li>b</li></ol></div>",
        )

    def test_xhtml_of_a_plain_string(self):
        self.assertEqual(
            serialize_injection_xhtml("a < b\nc", "…"),
            '<div xmlns="http://www.w3.org/1999/xhtml"><p>a &lt; b<br/>c</p></div>',
        )


class TestItemText(unittest.TestCase):
    def test_note_text_is_plain_and_label_goes_to_rendering_markdown(self):
        strategy = _make_strategy()
        note = TriccNodeNote(id="n", name="label_convulsion", label=parse_html_to_message(CONVULSION_HTML))
        strategy.generate_base(note)

        item = _find(strategy.questionnaires["main"]["item"], "label_convulsion")
        self.assertEqual(item["text"], CONVULSION_PLAIN)
        markdown = _ext(item, "text", RENDERING_MARKDOWN_EXT)["valueMarkdown"]
        self.assertTrue(markdown.startswith("**IF THE CHILD IS CONVULSING NOW - TREAT IMMEDIATELY**\n\n- Turn"))
        self.assertIn("**…ml**", markdown)
        self.assertNotIn("${", markdown)

    def test_html_format_writes_rendering_xhtml(self):
        strategy = _make_strategy(text_format="html")
        note = TriccNodeNote(id="n", name="label_convulsion", label=parse_html_to_message(CONVULSION_HTML))
        strategy.generate_base(note)

        item = _find(strategy.questionnaires["main"]["item"], "label_convulsion")
        self.assertIsNone(_ext(item, "text", RENDERING_MARKDOWN_EXT))
        ext = _ext(item, "text", RENDERING_XHTML_EXT)
        self.assertTrue(ext["valueString"].startswith('<div xmlns="http://www.w3.org/1999/xhtml"><p><strong>'))

    def test_plain_label_gets_no_extension(self):
        strategy = _make_strategy()
        strategy.generate_base(TriccNodeInteger(id="a", name="age", label="Age in months"))

        item = _find(strategy.questionnaires["main"]["item"], "age")
        self.assertEqual(item["text"], "Age in months")
        self.assertNotIn("_text", item)

    def test_curated_concept_display_wins(self):
        code_systems = {}
        add_concept(code_systems, "tricc", "weight", "Weight", {})
        strategy = _make_strategy(code_systems=code_systems)
        label = parse_html_to_message("<b>Weight</b> (kg)")
        strategy.generate_base(TriccNodeInteger(id="w", name="weight", label=label))

        item = _find(strategy.questionnaires["main"]["item"], "weight")
        self.assertEqual(item["text"], "Weight")
        self.assertEqual(_ext(item, "text", RENDERING_MARKDOWN_EXT)["valueMarkdown"], "**Weight** (kg)")

    def test_concept_display_filled_from_the_label_is_not_used(self):
        # At load the concept display is the label's Markdown (check_and_add_concept).
        label = parse_html_to_message("<b>Weight</b> (kg)")
        code_systems = {}
        add_concept(code_systems, "tricc", "weight", label, {})
        strategy = _make_strategy(code_systems=code_systems)
        strategy.generate_base(TriccNodeInteger(id="w", name="weight", label=label))

        item = _find(strategy.questionnaires["main"]["item"], "weight")
        self.assertEqual(item["text"], "Weight (kg)")

    def test_help_and_hint_children_are_plain(self):
        strategy = _make_strategy()
        question = TriccNodeInteger(id="c", name="muac", label="MUAC")
        question.help = parse_html_to_message("Measure on the <b>left</b> arm")
        question.hint = parse_html_to_message("in <i>mm</i>")
        strategy.generate_base(question)

        parent = _find(strategy.questionnaires["main"]["item"], "muac")
        help_item = _find(parent["item"], "muac-help")
        hint_item = _find(parent["item"], "muac-hint")
        self.assertEqual(help_item["text"], "Measure on the left arm")
        help_markdown = _ext(help_item, "text", RENDERING_MARKDOWN_EXT)["valueMarkdown"]
        self.assertEqual(help_markdown, "Measure on the **left** arm")
        self.assertEqual(hint_item["text"], "in mm")
        self.assertEqual(_ext(hint_item, "text", RENDERING_MARKDOWN_EXT)["valueMarkdown"], "in _mm_")

    def test_answer_option_display_is_plain(self):
        strategy = _make_strategy()
        select = TriccNodeSelectOne(id="s", name="danger", label="Danger sign", list_name="danger")
        select.options = {
            0: TriccNodeSelectOption(
                id="o1",
                name="lethargic",
                label=parse_html_to_message("<b>Lethargic</b> or unconscious"),
                select=select,
                list_name="danger",
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
        note.label = parse_html_to_message("Patient is <b>${age}</b> years old")
        self.assertIsInstance(note.label, TriccText)
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
