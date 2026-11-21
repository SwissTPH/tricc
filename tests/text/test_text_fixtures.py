"""Shared display-text fixtures (feature/20261120-prosemirror-display-text.md §3).

``tests/text/fixtures/*.json`` are the source of truth for both sides: the frontend copies
them (``scripts/sync-text-fixtures.sh``) and runs the same checks. One case per file::

    {"name": …,
     "input": {"html" | "markdown" | "json": …},
     "doc": <ProseMirror JSON, canonical form>,
     "plain": <plain text, an interp as "…">,
     "markdown": <Markdown, an interp as "${name}">,
     "xhtml": <XHTML div, an interp as "…">}

Run with:
    python -m pytest tests/text -v
"""

import glob
import json
import os

import lxml.html
import pytest
from prosemirror.model import DOMParser

from tricc_oo.text import (
    from_html,
    from_json,
    from_markdown,
    to_markdown,
    to_plain,
    to_xhtml,
)
from tricc_oo.text.schema import TEXT_SCHEMA

FIXTURES = sorted(glob.glob(os.path.join(os.path.dirname(__file__), "fixtures", "*.json")))
READERS = {"html": from_html, "markdown": from_markdown, "json": from_json}


def _load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _ids():
    return [os.path.basename(p)[:-5] for p in FIXTURES]


@pytest.mark.parametrize("path", FIXTURES, ids=_ids())
def test_input_reads_as_doc(path):
    case = _load(path)
    (kind, value), = case["input"].items()
    assert READERS[kind](value) == case["doc"]


@pytest.mark.parametrize("path", FIXTURES, ids=_ids())
def test_doc_renders(path):
    case = _load(path)
    doc = case["doc"]
    assert to_plain(doc, lambda name: "…") == case["plain"]
    assert to_markdown(doc, lambda name: "${" + name + "}") == case["markdown"]
    assert to_xhtml(doc, lambda name: "…") == case["xhtml"]


@pytest.mark.parametrize("path", FIXTURES, ids=_ids())
def test_doc_is_canonical(path):
    doc = _load(path)["doc"]
    assert from_json(doc) == doc


@pytest.mark.parametrize("path", FIXTURES, ids=_ids())
def test_markdown_reads_back_to_the_same_text(path):
    """``value`` (Markdown) is the fallback of ``designation-doc``: read back, it renders the
    same Markdown. Not for colours and foreign pictures (no Markdown), nor for a line right
    after a list: CommonMark reads it into the last item (lazy continuation)."""
    case = _load(path)
    if "textStyle" in json.dumps(case["doc"]) or "![x](http" in case["markdown"]:
        pytest.skip("colour / foreign picture: not in Markdown")
    blocks = case["doc"]["content"]
    if any(a["type"].endswith("List") and b.get("content") for a, b in zip(blocks, blocks[1:])):
        pytest.skip("a line right after a list continues its last item in CommonMark")
    again = from_markdown(case["markdown"])
    assert to_markdown(again, lambda name: "${" + name + "}") == case["markdown"]


def test_fixture_set_is_not_empty():
    assert len(FIXTURES) >= 30


def test_upstream_whitespace_bug_still_present():
    """prosemirror-py drops whitespace-only text between inline elements (the JavaScript
    parser keeps it); ``tricc_oo.text.parse._prepare_html`` works around it. When this test
    fails, the bug is fixed upstream and the pre-pass can go."""
    root = lxml.html.fragment_fromstring("<b>a</b> <b>b</b>", create_parent="document-fragment")
    doc = DOMParser.from_schema(TEXT_SCHEMA).parse(root)
    assert doc.text_content == "ab"
