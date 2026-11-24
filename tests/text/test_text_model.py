"""Readers, renderers and ``TriccText`` (feature/20261120-prosemirror-display-text.md).

Run with:
    python -m pytest tests/text -v
"""

import pytest

from tricc_oo.models.base import TriccOperation, TriccOperator, TriccReference, TriccStatic
from tricc_oo.models.tricc import TriccNodeInteger
from tricc_oo.text import (
    TextSchemaError,
    from_html,
    from_json,
    from_markdown,
    from_message_json,
    from_text,
    simplify,
    to_concatenate,
    to_markdown,
    to_plain,
)
from tricc_oo.text.model import TriccText


def _md(doc):
    return to_markdown(doc, lambda name: "${" + name + "}")


class TestReaders:
    def test_html_or_markdown_by_content(self):
        assert _md(from_text("<b>x</b>\n* y")) == "**x** * y"
        assert _md(from_text("**x**\n* y")) == "**x**\n- y"
        assert _md(from_text("Tom &amp; Jerry")) == "Tom & Jerry"

    def test_simplify(self):
        assert simplify(from_html("<b></b>Age in months")) == "Age in months"
        assert simplify(from_html("")) == ""
        assert isinstance(simplify(from_html("Age ${age}")), dict)
        assert isinstance(simplify(from_html("a<br>b")), dict)

    def test_json_rejects_what_the_schema_does_not_hold(self):
        bad = [
            {"type": "doc", "content": [{"type": "heading", "content": []}]},
            {"type": "doc", "content": [{"type": "text", "text": "loose text"}]},
            {"type": "paragraph"},
            {"type": "doc", "content": [{"type": "paragraph", "content": [
                {"type": "text", "text": "x", "marks": [{"type": "textStyle", "attrs": {"color": "url(x)"}}]}]}]},
            {"type": "doc", "content": [{"type": "paragraph", "content": [
                {"type": "image", "attrs": {"src": "http://example.org/x.png"}}]}]},
            "not a document",
        ]
        for data in bad:
            with pytest.raises(TextSchemaError):
                from_json(data)

    def test_old_message_tree(self):
        tree = {"type": "message", "children": [
            {"type": "mark", "kind": "strong", "children": [
                {"type": "text", "value": "Give "},
                {"type": "interp", "name": "dose"},
                {"type": "text", "value": " mg"},
            ]},
            {"type": "break"}, {"type": "break"},
            {"type": "list", "ordered": False, "items": [
                {"type": "item", "children": [{"type": "text", "value": "with food"}]},
                {"type": "item", "children": [
                    {"type": "mark", "kind": "color", "color": "#d32f2f",
                     "children": [{"type": "text", "value": "red"}]},
                ]},
            ]},
            {"type": "image", "src": "Binary/rash", "alt": "Rash"},
        ]}
        doc = from_message_json(tree)
        assert _md(doc) == "**Give ${dose} mg**\n\n- with food\n- red\n![Rash](Binary/rash)"
        assert to_plain(doc, lambda name: "…") == "Give … mg\n\n• with food\n• red\nRash"

    def test_old_message_tree_unknown_node(self):
        with pytest.raises(TextSchemaError):
            from_message_json({"type": "message", "children": [{"type": "table"}]})


class TestTriccText:
    def _text(self):
        return TriccText.from_doc(from_html("Give <b>${dose} mg</b> to ${name}, ${dose}"))

    def test_references_in_order_once(self):
        text = self._text()
        assert text.names() == ["dose", "name"]
        assert list(text.get_references()) == [TriccReference("dose"), TriccReference("name")]

    def test_replace_and_copy(self):
        text = self._text()
        dose = TriccNodeInteger(id="d", name="dose", label="Dose")
        text.replace_node(TriccReference("dose"), dose)
        assert text.ref("dose") is dose
        assert text.copy(keep_node=True).ref("dose") is dose
        assert text.copy().ref("dose") == TriccReference("dose")
        assert dose in list(text.get_references())

    def test_operation_reference(self):
        text = self._text()
        a, b = TriccNodeInteger(id="a", name="dose", label="A"), TriccNodeInteger(id="b", name="dose", label="B")
        text.refs["dose"] = TriccOperation(TriccOperator.GET_INHERITED_VALUE, [a, b])
        assert a in list(text.get_references()) and b in list(text.get_references())

    def test_first_text(self):
        assert TriccText.from_doc(from_html("${a} <b>Hello</b>")).first_text() == "Hello"

    def test_concatenate(self):
        operation = to_concatenate(from_html("Give <b>${dose} mg</b><br>now"), TriccReference)
        assert operation.operator == TriccOperator.CONCATENATE
        assert operation.reference == [TriccStatic("Give **"), TriccReference("dose"), TriccStatic(" mg**\nnow")]
        assert to_concatenate(from_html("<b>static</b>"), TriccReference) is None

    def test_markdown_list_reads_back(self):
        assert _md(from_markdown("- a\n- b")) == "- a\n- b"
