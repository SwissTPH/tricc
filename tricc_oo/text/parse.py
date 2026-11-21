"""Display text in: draw.io HTML, Markdown, ProseMirror JSON, the old message tree.

Every reader returns a document in canonical form (:func:`normalize`), as ProseMirror JSON
(a ``dict``). See ``feature/20261120-prosemirror-display-text.md`` §1.
"""

import copy
import logging
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

import lxml.etree
import lxml.html
from markdown_it import MarkdownIt
from prosemirror.model import DOMParser, Node

from tricc_oo.text.schema import LIST_TYPES, TEXT_SCHEMA, is_color, is_image_src

logger = logging.getLogger("default")

JSONDict = Dict[str, Any]

#: ``${name}``: a value shown in the text (``interp`` node).
INTERP_RE = re.compile(r"\$\{([^}]+)\}")
#: A string holding an HTML tag or entity is read as HTML, any other as Markdown.
HTML_RE = re.compile(r"<\s*/?\s*[a-zA-Z][^>]*>|&(#\d+|#x[0-9a-fA-F]+|[a-zA-Z]+);")

MARK_RANK = {"bold": 0, "italic": 1, "underline": 2, "textStyle": 3}
#: Marks Markdown has no syntax for: a paragraph holding one is not re-read as typed Markdown.
NON_MARKDOWN_MARKS = ("underline", "textStyle")

# Markdown read in labels and YAML: lists, emphasis, line breaks, pictures and ``${name}``;
# headings, links, code, escapes, entities, … stay text.
MARKDOWN_RULES = ["list", "emphasis", "newline", "image"]
# A paragraph is re-read as typed Markdown when its text holds one of these.
_TYPED_MARKDOWN_HINT = re.compile(r"[*_]|(^|\n)[ \t]*([-+]|\d{1,9}[.)])[ \t]")

_markdown_parser: Optional[MarkdownIt] = None


class TextSchemaError(ValueError):
    """A ProseMirror document that does not fit the display-text schema."""


# ------------------------------------------------------------------ building blocks


def paragraph(content: Optional[List[JSONDict]] = None) -> JSONDict:
    """A paragraph node (no ``content`` key when empty, as ``Node.to_json`` writes it)."""
    return {"type": "paragraph", "content": content} if content else {"type": "paragraph"}


def text_node(text: str, marks: Optional[List[JSONDict]] = None) -> JSONDict:
    node = {"type": "text", "text": text}
    if marks:
        node["marks"] = sort_marks(marks)
    return node


def interp_node(name: str, marks: Optional[List[JSONDict]] = None) -> JSONDict:
    node = {"type": "interp", "attrs": {"name": name}}
    if marks:
        node["marks"] = sort_marks(marks)
    return node


def sort_marks(marks: List[JSONDict]) -> List[JSONDict]:
    """Marks in schema order, one of each type."""
    seen: Dict[str, JSONDict] = {}
    for mark in marks:
        seen.setdefault(mark["type"], mark)
    return sorted(seen.values(), key=lambda m: MARK_RANK.get(m["type"], 99))


def is_empty_paragraph(node: JSONDict) -> bool:
    return node.get("type") == "paragraph" and not node.get("content")


def _marks_key(node: JSONDict) -> Tuple:
    return tuple((m["type"], tuple(sorted((m.get("attrs") or {}).items()))) for m in node.get("marks") or [])


def empty_doc() -> JSONDict:
    return {"type": "doc", "content": [paragraph()]}


# ------------------------------------------------------------------ canonical form


def _clean_inline(content: List[JSONDict]) -> List[JSONDict]:
    """Line breaks and pictures carry no marks; empty text is dropped; neighbouring text with
    the same marks is one node."""
    out: List[JSONDict] = []
    for node in content or []:
        node = dict(node)
        if node["type"] in ("hardBreak", "image"):
            node.pop("marks", None)
        elif node["type"] == "text":
            if not node.get("text"):
                continue
            if node.get("marks"):
                node["marks"] = sort_marks(node["marks"])
            else:
                node.pop("marks", None)
        if out and node["type"] == "text" and out[-1]["type"] == "text" and _marks_key(out[-1]) == _marks_key(node):
            out[-1] = dict(out[-1], text=out[-1]["text"] + node["text"])
        else:
            out.append(node)
    return out


def _trim_edges(content: List[JSONDict]) -> List[JSONDict]:
    """Drop line breaks and spaces opening or closing a paragraph."""
    content = list(content)
    while content and content[0]["type"] == "hardBreak":
        content.pop(0)
    while content and content[-1]["type"] == "hardBreak":
        content.pop()
    if content and content[0]["type"] == "text":
        stripped = content[0]["text"].lstrip()
        content[0] = dict(content[0], text=stripped)
    if content and content[-1]["type"] == "text":
        stripped = content[-1]["text"].rstrip()
        content[-1] = dict(content[-1], text=stripped)
    return [n for n in content if n["type"] != "text" or n["text"]]


def _split_paragraph(node: JSONDict) -> List[JSONDict]:
    """A run of two or more line breaks is a blank line: it ends the paragraph, and an empty
    paragraph stands for the blank line."""
    content = _clean_inline(node.get("content") or [])
    chunks: List[Optional[List[JSONDict]]] = [[]]
    i = 0
    while i < len(content):
        if content[i]["type"] == "hardBreak":
            run = 1
            while i + run < len(content) and content[i + run]["type"] == "hardBreak":
                run += 1
            if run >= 2:
                chunks.extend([None, []])
            else:
                chunks[-1].append(content[i])
            i += run
            continue
        chunks[-1].append(content[i])
        i += 1
    return [paragraph() if chunk is None else paragraph(_trim_edges(chunk)) for chunk in chunks]


def _list_can_merge(first: JSONDict, second: JSONDict) -> bool:
    if first["type"] != second["type"] or first["type"] not in LIST_TYPES:
        return False
    if first["type"] == "bulletList":
        return True
    start = (first.get("attrs") or {}).get("start", 1)
    return (second.get("attrs") or {}).get("start", 1) == start + len(first.get("content") or [])


def _normalize_blocks(blocks: List[JSONDict], top: bool) -> List[JSONDict]:
    out: List[JSONDict] = []
    for block in blocks or []:
        kind = block.get("type")
        if kind == "paragraph":
            out.extend(_split_paragraph(block))
        elif kind in LIST_TYPES:
            items = []
            for item in block.get("content") or []:
                inner = _normalize_blocks(item.get("content") or [], top=False)
                if not inner or inner[0]["type"] != "paragraph":
                    inner.insert(0, paragraph())
                items.append({"type": "listItem", "content": inner})
            if items:
                out.append(dict(block, content=items))
    merged: List[JSONDict] = []
    for block in out:
        if is_empty_paragraph(block) and (not merged or is_empty_paragraph(merged[-1]) or not top):
            continue  # one blank line at most; none opening the text or inside a list item
        if merged and _list_can_merge(merged[-1], block):
            merged[-1] = dict(merged[-1], content=merged[-1]["content"] + block["content"])
            continue
        merged.append(block)
    while merged and is_empty_paragraph(merged[-1]):
        merged.pop()
    return merged


def normalize(doc: JSONDict) -> JSONDict:
    """The canonical form of a document.

    Line breaks and pictures carry no marks; text nodes with the same marks are merged; a run
    of two or more line breaks splits the paragraph and leaves one empty paragraph (a blank
    line); line breaks and spaces at a paragraph's edges are dropped; consecutive empty
    paragraphs collapse into one, none opens or closes the document or sits in a list item;
    neighbouring lists of the same kind are one list.
    """
    blocks = _normalize_blocks(doc.get("content") or [], top=True)
    return {"type": "doc", "content": blocks or [paragraph()]}


def simplify(doc: JSONDict) -> Any:
    """A plain ``str`` when the document is one paragraph of unmarked text (``""`` when
    empty), else the document."""
    blocks = doc.get("content") or []
    if not blocks:
        return ""
    if len(blocks) == 1 and blocks[0]["type"] == "paragraph":
        content = blocks[0].get("content") or []
        if all(n["type"] == "text" and not n.get("marks") for n in content):
            return "".join(n["text"] for n in content)
    return doc


# ------------------------------------------------------------------ ${name}


def _split_interps_inline(content: List[JSONDict]) -> List[JSONDict]:
    """``${name}`` in text becomes an ``interp`` node, also when the token is split over
    neighbouring text nodes (``<span>${</span><b>dose}</b>``); it takes the marks of the
    text holding its ``$``."""
    out: List[JSONDict] = []
    run: List[JSONDict] = []

    def flush() -> None:
        if not run:
            return
        source = "".join(n["text"] for n in run)
        if "${" not in source:
            out.extend(run)
            run.clear()
            return
        owner: List[List[JSONDict]] = []
        for n in run:
            owner.extend([n.get("marks") or []] * len(n["text"]))
        pieces: List[JSONDict] = []
        last = 0

        def add_text(start: int, end: int) -> None:
            i = start
            while i < end:
                j = i
                while j < end and owner[j] == owner[i]:
                    j += 1
                pieces.append(text_node(source[i:j], owner[i]))
                i = j

        for match in INTERP_RE.finditer(source):
            name = match.group(1).strip()
            if not name:
                continue
            add_text(last, match.start())
            pieces.append(interp_node(name, owner[match.start()]))
            last = match.end()
        add_text(last, len(source))
        out.extend(pieces)
        run.clear()

    for node in content or []:
        if node["type"] == "text":
            run.append(node)
        else:
            flush()
            out.append(node)
    flush()
    return _clean_inline(out)


def _map_paragraphs(blocks: List[JSONDict], fn: Callable[[JSONDict, bool], List[JSONDict]], top: bool = True):
    out: List[JSONDict] = []
    for block in blocks or []:
        if block["type"] == "paragraph":
            out.extend(fn(block, top))
        elif block["type"] in LIST_TYPES:
            items = []
            for item in block.get("content") or []:
                items.append(dict(item, content=_map_paragraphs(item.get("content") or [], fn, top=False)))
            out.append(dict(block, content=items))
        else:
            out.append(block)
    return out


def split_interps(doc: JSONDict) -> JSONDict:
    """Every ``${name}`` in the text of ``doc`` as an ``interp`` node."""
    def fn(block: JSONDict, _top: bool) -> List[JSONDict]:
        return [paragraph(_split_interps_inline(block.get("content") or []))]

    return dict(doc, content=_map_paragraphs(doc.get("content") or [], fn))


# ------------------------------------------------------------------ HTML


def _prepare_html(root: Any) -> None:
    """Whitespace pre-pass (§1.1): prosemirror-py's ``DOMParser`` never sees whitespace-only
    text (``_wrap_lxml_text`` only wraps text that is not blank), so ``<b>a</b> <b>b</b>``
    reads ``ab``. Wrap it the way the parser wraps other text, so the parser's own rules (the
    ones prosemirror-model applies in JavaScript) decide what is kept. A non-breaking space is
    a space."""
    for element in list(root.iter()):
        if not isinstance(element.tag, str) or element.tag.lower() == "lxmltext":
            continue
        if element.text:
            element.text = element.text.replace("\xa0", " ")
            if not element.text.strip():
                holder = lxml.html.Element("lxmltext")
                holder.text = element.text
                element.text = None
                element.insert(0, holder)
        if element.tail and element is not root:
            element.tail = element.tail.replace("\xa0", " ")
            if not element.tail.strip():
                parent = element.getparent()
                holder = lxml.html.Element("lxmltext")
                holder.text = element.tail
                element.tail = None
                parent.insert(parent.index(element) + 1, holder)


def from_html(raw: str, where: Optional[str] = None) -> JSONDict:
    """A draw.io label (HTML) as a document.

    HTML import with the schema's parse rules, after the whitespace pre-pass; ``${name}``
    split; Markdown typed into a paragraph re-read (:func:`read_typed_markdown`).

    Args:
        raw: Label HTML (or plain text).
        where: What the text belongs to (node id), for warnings.
    """
    if raw is None or not raw.strip():
        return empty_doc()
    try:
        root = lxml.html.fragment_fromstring(raw, create_parent="document-fragment")
    except (lxml.etree.ParserError, ValueError):
        return from_plain(raw)
    _prepare_html(root)
    doc = DOMParser.from_schema(TEXT_SCHEMA).parse(root).to_json()
    doc = normalize(split_interps(doc))
    return normalize(read_typed_markdown(doc, where))


def from_plain(text: str) -> JSONDict:
    """Text as written: lines are line breaks, nothing else is read."""
    content: List[JSONDict] = []
    for i, line in enumerate((text or "").split("\n")):
        if i:
            content.append({"type": "hardBreak"})
        if line:
            content.append(text_node(line))
    return normalize({"type": "doc", "content": [paragraph(content)]})


# ------------------------------------------------------------------ Markdown


def _interp_rule(state: Any, silent: bool) -> bool:
    """markdown-it inline rule: ``${name}`` is one ``interp`` token."""
    if not state.src.startswith("${", state.pos):
        return False
    end = state.src.find("}", state.pos + 2)
    if end < 0:
        return False
    name = state.src[state.pos + 2:end].strip()
    if not name:
        return False
    if not silent:
        token = state.push("interp", "", 0)
        token.meta = {"name": name}
    state.pos = end + 1
    return True


def markdown_parser() -> MarkdownIt:
    """markdown-it, preset ``zero`` with :data:`MARKDOWN_RULES` and the ``interp`` rule."""
    global _markdown_parser
    if _markdown_parser is None:
        parser = MarkdownIt("zero").enable(MARKDOWN_RULES)
        parser.inline.ruler.before("text", "interp", _interp_rule)
        _markdown_parser = parser
    return _markdown_parser


_MARKDOWN_MARKS = {"strong_open": "bold", "em_open": "italic", "strong_close": "bold", "em_close": "italic"}


def _inline_from_tokens(tokens: List[Any]) -> List[JSONDict]:
    content: List[JSONDict] = []
    marks: List[str] = []
    for token in tokens or []:
        kind = token.type
        if kind in ("strong_open", "em_open"):
            marks.append(_MARKDOWN_MARKS[kind])
        elif kind in ("strong_close", "em_close"):
            if _MARKDOWN_MARKS[kind] in marks:
                marks.reverse()
                marks.remove(_MARKDOWN_MARKS[kind])
                marks.reverse()
        elif kind in ("softbreak", "hardbreak"):
            content.append({"type": "hardBreak"})
        elif kind == "interp":
            content.append(interp_node(token.meta["name"], [{"type": m} for m in marks]))
        elif kind == "image":
            src = token.attrGet("src")
            alt = token.content or None
            if is_image_src(src):
                content.append({"type": "image", "attrs": {"src": src, "alt": alt}})
            else:
                content.append(text_node(f"![{token.content}]({src})", [{"type": m} for m in marks]))
        elif token.content:
            content.append(text_node(token.content, [{"type": m} for m in marks]))
    return _clean_inline(content)


def _blocks_from_tokens(tokens: List[Any]) -> List[JSONDict]:
    """Rebuild blocks from markdown-it block tokens. Top-level blocks the source keeps apart
    by a blank line get an empty paragraph between them."""
    frames: List[Dict[str, Any]] = [{"blocks": [], "lines": []}]
    for token in tokens:
        frame = frames[-1]
        if token.type == "paragraph_open":
            frame["blocks"].append(paragraph())
            frame["lines"].append(tuple(token.map or (0, 0)))
        elif token.type == "inline":
            frame["blocks"][-1] = paragraph(_inline_from_tokens(token.children))
            for outer in frames:  # where the text ends (a list's map counts the blank line after it)
                outer["end"] = (token.map or (0, 0))[1]
        elif token.type in ("bullet_list_open", "ordered_list_open"):
            attrs = {"start": int(token.attrGet("start") or 1)} if token.type == "ordered_list_open" else None
            frames.append({
                "type": "orderedList" if attrs else "bulletList", "attrs": attrs, "items": [],
                "start": (token.map or (0, 0))[0],
            })
        elif token.type == "list_item_open":
            frames.append({"blocks": [], "lines": []})
        elif token.type == "list_item_close":
            item = frames.pop()
            frames[-1]["items"].append({"type": "listItem", "content": item["blocks"]})
        elif token.type in ("bullet_list_close", "ordered_list_close"):
            lst = frames.pop()
            node = {"type": lst["type"], "content": lst["items"]}
            if lst["attrs"]:
                node["attrs"] = lst["attrs"]
            frames[-1]["blocks"].append(node)
            frames[-1]["lines"].append((lst["start"], lst.get("end", lst["start"])))
    top = frames[0]
    out: List[JSONDict] = []
    previous_end = None
    for block, (start, end) in zip(top["blocks"], top["lines"]):
        if previous_end is not None and start > previous_end:
            out.append(paragraph())
        out.append(block)
        previous_end = end
    return out


def from_markdown(text: str) -> JSONDict:
    """Markdown (YAML labels, ``value`` of a designation, typed Markdown) as a document."""
    if text is None or not text.strip():
        return empty_doc()
    tokens = markdown_parser().parse(text)
    return normalize({"type": "doc", "content": _blocks_from_tokens(tokens)})


def from_text(raw: str, where: Optional[str] = None) -> JSONDict:
    """A label string: HTML when it holds a tag or an entity, else Markdown."""
    if raw and HTML_RE.search(raw):
        return from_html(raw, where)
    return from_markdown(raw)


# ------------------------------------------------------------------ typed Markdown (§1.2)


def _plain_of(content: List[JSONDict]) -> str:
    return "".join(
        n["text"] if n["type"] == "text" else "\n" if n["type"] == "hardBreak" else "x" for n in content
    )


def _markdown_for_reread(content: List[JSONDict]) -> str:
    """The paragraph as Markdown: its marks written as markers, so markers typed in other
    HTML elements meet them. Text is not escaped: typed markers are what is read."""
    from tricc_oo.text.render import inline_markdown

    return inline_markdown(content, lambda name: "${" + name + "}", italic="*")


def read_typed_markdown(doc: JSONDict, where: Optional[str] = None) -> JSONDict:
    """Re-read Markdown typed into the paragraphs of an imported label (``**bold**``,
    ``* item``, ``1. item``) as marks and lists. A paragraph holding underline or a colour is
    not re-read (Markdown has none); it keeps its literal text and a warning is logged."""

    def fn(block: JSONDict, top: bool) -> List[JSONDict]:
        content = block.get("content") or []
        if not _TYPED_MARKDOWN_HINT.search(_plain_of(content)):
            return [block]
        if any(m["type"] in NON_MARKDOWN_MARKS for n in content for m in n.get("marks") or []):
            logger.warning(
                "Display text%s: Markdown typed in text with underline or colour is kept as typed",
                f" of {where}" if where else "",
            )
            return [block]
        tokens = markdown_parser().parse(_markdown_for_reread(content))
        if not any(
            t.type in ("bullet_list_open", "ordered_list_open")
            or any(c.type in ("strong_open", "em_open") for c in t.children or [])
            for t in tokens
        ):
            return [block]
        blocks = _blocks_from_tokens(tokens)
        if not top and (len(blocks) != 1 or blocks[0]["type"] != "paragraph"):
            return [block]  # a list item keeps its text: a list cannot open one
        return blocks or [block]

    return dict(doc, content=_map_paragraphs(doc.get("content") or [], fn))


# ------------------------------------------------------------------ JSON


def _check_attrs(node: Node) -> None:
    for mark in node.marks:
        if mark.type.name == "textStyle" and not is_color(mark.attrs.get("color")):
            raise TextSchemaError(f"invalid colour {mark.attrs.get('color')!r}")
    if node.type.name == "image" and not is_image_src(node.attrs.get("src")):
        raise TextSchemaError(f"invalid picture source {node.attrs.get('src')!r}")
    if node.type.name == "interp" and not str(node.attrs.get("name") or "").strip():
        raise TextSchemaError("interp without a name")
    for child in node.content.content:
        _check_attrs(child)


def from_json(data: Any) -> JSONDict:
    """A ProseMirror document (editor JSON) as a document in canonical form.

    Raises:
        TextSchemaError: when ``data`` does not fit the schema; nothing is half-read.
    """
    try:
        node = Node.from_json(TEXT_SCHEMA, copy.deepcopy(data))
        node.check()
    except TextSchemaError:
        raise
    except Exception as exc:  # prosemirror raises ValueError, KeyError, … on bad input
        raise TextSchemaError(f"not a display-text document: {exc}") from exc
    if node.type.name != "doc":
        raise TextSchemaError(f"not a display-text document: top node is {node.type.name!r}")
    _check_attrs(node)
    return normalize(node.to_json())


# ------------------------------------------------------------------ old message tree (§1.3)

_OLD_MARKS = {"strong": "bold", "em": "italic", "u": "underline"}


def from_message_json(data: Any) -> JSONDict:
    """The old ``designation-message`` tree (read only) as a document.

    ``{"type": "message"|"text"|"interp"|"break"|"mark"|"list"|"item"|"image", …}``; marks
    ``strong`` / ``em`` / ``u`` / ``color``. A list at the top is a block; one inside a phrase
    keeps its items as lines.

    Raises:
        TextSchemaError: on an unknown node type or a malformed tree.
    """
    if not isinstance(data, dict) or data.get("type") != "message":
        raise TextSchemaError("not a message tree")
    blocks: List[JSONDict] = []
    inline: List[JSONDict] = []

    def flush() -> None:
        blocks.append(paragraph(list(inline)))
        inline.clear()

    def mark_of(node: JSONDict) -> Optional[JSONDict]:
        kind = node.get("kind")
        if kind == "color":
            return {"type": "textStyle", "attrs": {"color": node["color"]}} if is_color(node.get("color")) else None
        if kind in _OLD_MARKS:
            return {"type": _OLD_MARKS[kind]}
        raise TextSchemaError(f"unknown mark kind {kind!r}")

    def inline_of(nodes: List[Any], marks: List[JSONDict], out: List[JSONDict]) -> None:
        for node in nodes or []:
            if not isinstance(node, dict):
                raise TextSchemaError("message node is not an object")
            kind = node.get("type")
            if kind == "text":
                if node.get("value"):
                    out.append(text_node(str(node["value"]), marks))
            elif kind == "interp":
                out.append(interp_node(str(node["name"]), marks))
            elif kind == "break":
                out.append({"type": "hardBreak"})
            elif kind == "image":
                if is_image_src(node.get("src")):
                    out.append({"type": "image", "attrs": {"src": node["src"], "alt": node.get("alt") or None}})
            elif kind == "mark":
                mark = mark_of(node)
                inline_of(node.get("children"), marks + [mark] if mark else marks, out)
            elif kind == "list":
                for i, item in enumerate(node.get("items") or [], start=1):
                    out.append({"type": "hardBreak"})
                    out.append(text_node(f"{i}. " if node.get("ordered") else "- ", marks))
                    inline_of(item.get("children"), marks, out)
            else:
                raise TextSchemaError(f"unknown message node type {kind!r}")

    def walk(nodes: List[Any], marks: List[JSONDict]) -> None:
        for node in nodes or []:
            if isinstance(node, dict) and node.get("type") == "list" and not marks:
                if inline:
                    flush()
                items = []
                for item in node.get("items") or []:
                    content: List[JSONDict] = []
                    inline_of(item.get("children"), [], content)
                    items.append({"type": "listItem", "content": [paragraph(content)]})
                if items:
                    lst = {"type": "orderedList" if node.get("ordered") else "bulletList", "content": items}
                    if node.get("ordered"):
                        lst["attrs"] = {"start": 1}
                    blocks.append(lst)
            elif isinstance(node, dict) and node.get("type") == "mark" and not marks:
                mark = mark_of(node)
                inline_of(node.get("children"), [mark] if mark else [], inline)
            else:
                inline_of([node], marks, inline)

    walk(data.get("children"), [])
    if inline or not blocks:
        flush()
    return normalize({"type": "doc", "content": blocks})
