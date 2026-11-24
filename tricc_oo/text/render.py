"""Display text out: plain text, Markdown, XHTML, references and dynamic text.

Every renderer walks a document in canonical form (``tricc_oo.text.parse.normalize``). Blocks
are lines: each paragraph or list item starts a line, an empty paragraph is a blank line, a
``hardBreak`` is a line break. See ``feature/20261120-prosemirror-display-text.md`` §1.
"""

import html
from typing import Any, Callable, Dict, List, Optional, Tuple

from prosemirror.model import DOMSerializer, Node
from prosemirror.model.to_dom import DocumentFragment, Element

from tricc_oo.text.schema import LIST_TYPES, MARKDOWN_MARKS, TEXT_SCHEMA

JSONDict = Dict[str, Any]
Interp = Callable[[str], str]

XHTML_NS = "http://www.w3.org/1999/xhtml"
BULLET_PLAIN = "• "
BULLET_MARKDOWN = "- "
MARKDOWN_WRAP = {"bold": ("**", "**"), "italic": ("_", "_")}


# ------------------------------------------------------------------ blocks as lines


def _render_blocks(blocks: List[JSONDict], inline: Callable[[List[JSONDict]], str], bullet: str) -> str:
    lines: List[str] = []
    for block in blocks or []:
        kind = block.get("type")
        if kind == "paragraph":
            lines.append(inline(block.get("content") or []))
        elif kind in LIST_TYPES:
            start = (block.get("attrs") or {}).get("start", 1)
            for i, item in enumerate(block.get("content") or []):
                prefix = f"{start + i}. " if kind == "orderedList" else bullet
                body = _render_blocks(item.get("content") or [], inline, bullet)
                lines.append(prefix + body.replace("\n", "\n" + " " * len(prefix)))
    return "\n".join(lines)


# ------------------------------------------------------------------ plain


def inline_plain(content: List[JSONDict], interp: Interp) -> str:
    out = []
    for node in content or []:
        kind = node["type"]
        if kind == "text":
            out.append(node["text"])
        elif kind == "hardBreak":
            out.append("\n")
        elif kind == "interp":
            out.append(interp(node["attrs"]["name"]))
        elif kind == "image":
            out.append((node.get("attrs") or {}).get("alt") or "")
    return "".join(out)


def to_plain(doc: JSONDict, interp: Interp) -> str:
    """Text without markup: line breaks kept, list items ``• `` / ``1. ``, ``interp`` as
    ``interp(name)``, a picture as its ``alt`` (or nothing)."""
    return _render_blocks(doc.get("content") or [], lambda c: inline_plain(c, interp), BULLET_PLAIN).strip()


# ------------------------------------------------------------------ Markdown


def _segments(content: List[JSONDict], interp: Interp) -> List[Tuple[frozenset, str, bool]]:
    """``(markdown marks, text, is whitespace-able text)`` per inline node."""
    segments = []
    for node in content or []:
        kind = node["type"]
        marks = frozenset(m["type"] for m in node.get("marks") or [] if m["type"] in MARKDOWN_MARKS)
        if kind == "text":
            segments.append((marks, node["text"], True))
        elif kind == "interp":
            segments.append((marks, interp(node["attrs"]["name"]), False))
        elif kind == "hardBreak":
            segments.append((frozenset(), "\n", False))
        elif kind == "image":
            attrs = node.get("attrs") or {}
            alt = (attrs.get("alt") or "").replace("[", "").replace("]", "")
            segments.append((frozenset(), f"![{alt}]({attrs.get('src')})", False))
    return segments


def _expel_whitespace(segments: List[Tuple[frozenset, str, bool]]) -> List[Tuple[frozenset, str]]:
    """Spaces at the edge of a marked run go outside the markers: the leading spaces of a
    node keep only the marks it shares with the node before, the trailing ones the marks it
    shares with the node after."""
    out: List[Tuple[frozenset, str]] = []
    for i, (marks, text, is_text) in enumerate(segments):
        if not is_text or not marks:
            out.append((marks, text))
            continue
        before = segments[i - 1][0] if i > 0 else frozenset()
        after = segments[i + 1][0] if i + 1 < len(segments) else frozenset()
        core = text.strip()
        if not core:
            out.append((marks & before & after, text))
            continue
        lead = text[: len(text) - len(text.lstrip())]
        trail = text[len(text.rstrip()):]
        if lead:
            out.append((marks & before, lead))
        out.append((marks, core))
        if trail:
            out.append((marks & after, trail))
    merged: List[Tuple[frozenset, str]] = []
    for marks, text in out:
        if merged and merged[-1][0] == marks:
            merged[-1] = (marks, merged[-1][1] + text)
        else:
            merged.append((marks, text))
    return merged


def inline_markdown(content: List[JSONDict], interp: Interp, italic: str = "_") -> str:
    """Markdown of a paragraph's content: marks opened and closed around runs, so
    ``**Give ${dose} mg**`` stays one span; bold outside italic; underline and colour have no
    Markdown and are dropped; text is not escaped."""
    wrap = dict(MARKDOWN_WRAP, italic=(italic, italic))
    out: List[str] = []
    stack: List[str] = []
    for marks, text in _expel_whitespace(_segments(content, interp)):
        keep = 0
        while keep < len(stack) and stack[keep] in marks:
            keep += 1
        while len(stack) > keep:
            out.append(wrap[stack.pop()][1])
        for mark in MARKDOWN_MARKS:
            if mark in marks and mark not in stack:
                stack.append(mark)
                out.append(wrap[mark][0])
        out.append(text)
    while stack:
        out.append(wrap[stack.pop()][1])
    return "".join(out)


def to_markdown(doc: JSONDict, interp: Interp) -> str:
    """Markdown as ODK and CHT render it: ``**bold**``, ``_italic_``, ``- `` / ``1. `` list
    items, a line break as a newline, an empty paragraph as a blank line, ``interp`` as
    ``interp(name)``, a picture as ``![alt](Binary/<id>)``."""
    return _render_blocks(doc.get("content") or [], lambda c: inline_markdown(c, interp), BULLET_MARKDOWN)


# ------------------------------------------------------------------ XHTML


class _Raw(str):
    """Text the XHTML writer escapes itself (``DOMSerializer`` escapes with quotes)."""


_VOID = frozenset({"br", "img"})


def _write_xhtml(node: Any) -> str:
    if isinstance(node, str):
        return html.escape(node, quote=False)
    if isinstance(node, Element):
        attrs = "".join(f' {k}="{html.escape(v, quote=True)}"' for k, v in node.attrs.items())
        if node.name in _VOID:
            return f"<{node.name}{attrs}/>"
        return f"<{node.name}{attrs}>{''.join(_write_xhtml(c) for c in node.children)}</{node.name}>"
    if isinstance(node, DocumentFragment):
        return "".join(_write_xhtml(c) for c in node.children)
    return html.escape(str(node), quote=False)


def _serializer(interp: Interp) -> DOMSerializer:
    nodes = DOMSerializer.nodes_from_schema(TEXT_SCHEMA)
    nodes["text"] = lambda node: {"dom": _Raw(node.text)}
    nodes["interp"] = lambda node: {"dom": _Raw(interp(node.attrs["name"]))}
    return DOMSerializer(nodes, DOMSerializer.marks_from_schema(TEXT_SCHEMA))


def _inline_xhtml(content: List[JSONDict], serializer: DOMSerializer) -> str:
    if not content:
        return ""
    node = Node.from_json(TEXT_SCHEMA, {"type": "paragraph", "content": content})
    return _write_xhtml(serializer.serialize_fragment(node.content))


def _join_lines(paragraphs: List[JSONDict]) -> List[JSONDict]:
    content: List[JSONDict] = []
    for p in paragraphs:
        if content:
            content.append({"type": "hardBreak"})
        content.extend(p.get("content") or [])
    return content


def _blocks_xhtml(blocks: List[JSONDict], serializer: DOMSerializer, in_item: bool) -> str:
    out: List[str] = []
    lines: List[JSONDict] = []

    def flush() -> None:
        if lines:
            inline = _inline_xhtml(_join_lines(lines), serializer)
            out.append(inline if in_item and not out else f"<p>{inline}</p>")
            lines.clear()

    for block in blocks or []:
        kind = block.get("type")
        if kind == "paragraph":
            if block.get("content"):
                lines.append(block)
            else:
                flush()
        elif kind in LIST_TYPES:
            flush()
            tag = "ol" if kind == "orderedList" else "ul"
            start = (block.get("attrs") or {}).get("start", 1)
            items = "".join(
                f"<li>{_blocks_xhtml(item.get('content') or [], serializer, True)}</li>"
                for item in block.get("content") or []
            )
            out.append(f"<{tag}>{items}</{tag}>" if start == 1 else f'<{tag} start="{start}">{items}</{tag}>')
    flush()
    return "".join(out)


def to_xhtml(doc: JSONDict, interp: Interp) -> str:
    """An XHTML ``div`` (FHIR narrative style): lines one after the other are one ``p`` with
    ``<br/>`` between them, a blank line starts a new ``p``, lists are ``ul`` / ``ol``, marks
    are the schema's ``toDOM`` (``strong``, ``em``, ``u``, ``span style="color: …"``), text is
    escaped. ``""`` for an empty document."""
    body = _blocks_xhtml(doc.get("content") or [], _serializer(interp), False)
    return f'<div xmlns="{XHTML_NS}">{body}</div>' if body else ""


# ------------------------------------------------------------------ references, dynamic text


def references(doc: JSONDict) -> List[str]:
    """The ``interp`` names of ``doc``, in reading order, each once."""
    names: List[str] = []

    def walk(node: JSONDict) -> None:
        if node.get("type") == "interp":
            name = node["attrs"]["name"]
            if name not in names:
                names.append(name)
        for child in node.get("content") or []:
            walk(child)

    walk(doc)
    return names


def first_text(doc: JSONDict) -> Optional[str]:
    """The first non-empty text of ``doc`` (skipping ``interp``)."""
    def walk(node: JSONDict) -> Optional[str]:
        if node.get("type") == "text" and node.get("text", "").strip():
            return node["text"]
        for child in node.get("content") or []:
            found = walk(child)
            if found:
                return found
        return None

    return walk(doc)


_SLOT = ""


def markdown_parts(doc: JSONDict) -> List[Any]:
    """The Markdown of ``doc`` cut at every ``interp``: text (``str``) and ``interp`` names
    (``(name,)`` tuples) in order. The dynamic text (CONCATENATE) is built from it."""
    order: List[str] = []

    def slot(name: str) -> str:
        order.append(name)
        return _SLOT

    markdown = to_markdown(doc, slot)
    parts: List[Any] = []
    for i, piece in enumerate(markdown.split(_SLOT)):
        if i:
            parts.append((order[i - 1],))
        if piece:
            parts.append(piece)
    return parts


def to_concatenate(doc: JSONDict, resolve: Callable[[str], Any]) -> Optional[Any]:
    """The dynamic text of ``doc`` for CQL / XLSForm: a ``CONCATENATE`` of its Markdown cut
    at every ``interp``, each ``interp`` as ``resolve(name)``. None when ``doc`` has no
    ``interp`` (its text is static)."""
    from tricc_oo.models.base import TriccOperation, TriccOperator, TriccStatic

    parts = [resolve(p[0]) if isinstance(p, tuple) else TriccStatic(p) for p in markdown_parts(doc)]
    if not any(not isinstance(p, TriccStatic) for p in parts):
        return None
    return TriccOperation(operator=TriccOperator.CONCATENATE, reference=parts)
