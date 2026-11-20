"""Display-text AST: parse HTML + ``${REF}`` at input load, Markdown at export.

Scope: TriccNodeDisplayModel fields only (label, hint, help, constraint_message,
required_message). Not for calculates / rhombus.

HTML is parsed to ``TriccMessage`` *before* Markdown conversion. See
``feature/20260909-display-message-ast.md``.
"""

from __future__ import annotations

import html
import logging
import re
from typing import Any, Callable, List, Optional, Union

from bs4 import BeautifulSoup, NavigableString, Tag

from tricc_oo.models.base import (
    TriccNodeBaseModel,
    TriccOperation,
    TriccOperator,
    TriccReference,
    TriccStatic,
)
from tricc_oo.models.message import (
    TriccMessage,
    TriccMessageBreak,
    TriccMessageList,
    TriccMessageListItem,
    TriccMessageMark,
    TriccMessageMarkKind,
    TriccMessageText,
)

logger = logging.getLogger("default")

INJECTION_TOKEN_RE = re.compile(r"\$\{([^}]+)\}")

TEXT_INJECTION_FIELDS = (
    "label",
    "hint",
    "help",
    "constraint_message",
    "required_message",
)

# Markdown: distinct wrappers so nested strong+em stay unambiguous.
STRONG_WRAP = ("**", "**")
EM_WRAP = ("_", "_")

DROP_TAGS = frozenset({"img", "table", "thead", "tbody", "tr", "td", "th"})
UNWRAP_TAGS = frozenset({"span", "font", "a", "html", "body", "[document]"})
BLOCK_TAGS = frozenset({"div", "p"})
STRONG_TAGS = frozenset({"b", "strong"})
EM_TAGS = frozenset({"i", "em"})

# More consecutive line breaks than this collapse (one blank line at most).
MAX_CONSECUTIVE_BREAKS = 2
XHTML_NS = "http://www.w3.org/1999/xhtml"
XHTML_MARK_TAGS = {
    TriccMessageMarkKind.STRONG: "strong",
    TriccMessageMarkKind.EM: "em",
    TriccMessageMarkKind.U: "u",
}


def parse_injection_text(text: str) -> Union[str, TriccMessage, TriccReference, TriccMessageText]:
    """Split plain (non-HTML) text on ``${name}`` tokens.

    No tokens → original string. Otherwise a ``TriccMessage`` of text leaves and
    ``TriccReference`` names (or a single reference / text when only one part).
    """
    if text is None:
        return text
    if not isinstance(text, str):
        return text
    if not INJECTION_TOKEN_RE.search(text):
        return text
    return _simplify_message(TriccMessage(children=_split_text_tokens(text)))


def _split_text_tokens(text: str) -> List[Any]:
    parts: list = []
    last_end = 0
    for match in INJECTION_TOKEN_RE.finditer(text):
        if match.start() > last_end:
            parts.append(TriccMessageText(value=text[last_end : match.start()]))
        name = match.group(1).strip()
        if name:
            parts.append(TriccReference(name))
        last_end = match.end()
    if last_end < len(text):
        parts.append(TriccMessageText(value=text[last_end:]))
    return parts


def _normalize_text(value: str) -> str:
    return value.replace("\xa0", " ").replace("&nbsp;", " ")


def _is_message_tree(value: Any) -> bool:
    return isinstance(
        value,
        (
            TriccMessage,
            TriccMessageText,
            TriccMessageBreak,
            TriccMessageMark,
            TriccMessageList,
            TriccMessageListItem,
        ),
    )


def _has_structure(nodes: List[Any]) -> bool:
    for node in nodes:
        if isinstance(node, (TriccReference, TriccMessageBreak, TriccMessageMark, TriccMessageList)):
            return True
        if issubclass(node.__class__, TriccNodeBaseModel) and not isinstance(node, TriccMessageText):
            return True
        if isinstance(node, TriccMessage) and _has_structure(node.children or []):
            return True
    return False


def _merge_adjacent_text(nodes: List[Any]) -> List[Any]:
    merged: List[Any] = []
    for node in nodes:
        if (
            merged
            and isinstance(merged[-1], TriccMessageText)
            and isinstance(node, TriccMessageText)
        ):
            merged[-1] = TriccMessageText(value=merged[-1].value + node.value)
        else:
            merged.append(node)
    return merged


def _simplify_message(message: TriccMessage) -> Union[str, TriccMessage]:
    children = _merge_adjacent_text(list(message.children or []))
    message = TriccMessage(children=children)
    if not children:
        return ""
    if len(children) == 1 and isinstance(children[0], TriccMessageText):
        return children[0].value
    if not _has_structure(children) and all(isinstance(c, TriccMessageText) for c in children):
        return "".join(c.value for c in children)
    return message


def _is_blank(node: Any) -> bool:
    return isinstance(node, TriccMessageBreak) or (isinstance(node, TriccMessageText) and not node.value.strip())


def _split_leading_blank(children: List[Any]) -> List[Any]:
    """Pop the line breaks and spaces that open ``children``; return them in order."""
    moved: List[Any] = []
    while children and _is_blank(children[0]):
        first = children[0]
        if isinstance(first, TriccMessageText):
            stripped = first.value.lstrip()
            if stripped:
                moved.append(TriccMessageText(value=first.value[: len(first.value) - len(stripped)]))
                children[0] = TriccMessageText(value=stripped)
                break
        moved.append(children.pop(0))
    if children and isinstance(children[0], TriccMessageText) and children[0].value[:1].isspace():
        value = children[0].value
        stripped = value.lstrip()
        moved.append(TriccMessageText(value=value[: len(value) - len(stripped)]))
        children[0] = TriccMessageText(value=stripped)
    return moved


def _split_trailing_blank(children: List[Any]) -> List[Any]:
    """Pop the line breaks and spaces that close ``children``; return them in order."""
    moved: List[Any] = []
    while children:
        last = children[-1]
        if isinstance(last, TriccMessageBreak):
            moved.insert(0, children.pop())
            continue
        if isinstance(last, TriccMessageText) and last.value[-1:].isspace():
            stripped = last.value.rstrip()
            moved.insert(0, TriccMessageText(value=last.value[len(stripped):]))
            if stripped:
                children[-1] = TriccMessageText(value=stripped)
                break
            children.pop()
            continue
        break
    return moved


def _normalize_mark(mark: TriccMessageMark) -> List[Any]:
    """A mark without spaces or line breaks at its edges, or its content if it is empty."""
    children = _normalize_nodes(mark.children)
    before = _split_leading_blank(children)
    after = _split_trailing_blank(children)
    if not children:
        return before + after
    return before + [TriccMessageMark(kind=mark.kind, children=children)] + after


def _merge_adjacent_marks(nodes: List[Any]) -> List[Any]:
    merged: List[Any] = []
    for node in nodes:
        if (
            merged
            and isinstance(node, TriccMessageMark)
            and isinstance(merged[-1], TriccMessageMark)
            and merged[-1].kind == node.kind
        ):
            children = _merge_adjacent_text(list(merged[-1].children) + list(node.children))
            merged[-1] = TriccMessageMark(kind=node.kind, children=children)
        else:
            merged.append(node)
    return merged


def _cap_breaks(nodes: List[Any]) -> List[Any]:
    capped: List[Any] = []
    run = 0
    for node in nodes:
        run = run + 1 if isinstance(node, TriccMessageBreak) else 0
        if run <= MAX_CONSECUTIVE_BREAKS:
            capped.append(node)
    return capped


def _normalize_nodes(nodes: List[Any]) -> List[Any]:
    out: List[Any] = []
    for node in nodes or []:
        if isinstance(node, TriccMessageMark):
            out.extend(_normalize_mark(node))
        elif isinstance(node, TriccMessageList):
            items = [
                TriccMessageListItem(children=_strip_breaks(_normalize_nodes(item.children)))
                for item in node.items or []
            ]
            out.append(TriccMessageList(ordered=node.ordered, items=items))
        elif isinstance(node, TriccMessage):
            out.extend(_normalize_nodes(node.children))
        elif isinstance(node, TriccMessageText) and not node.value:
            continue
        else:
            out.append(node)
    return _cap_breaks(_merge_adjacent_marks(_merge_adjacent_text(out)))


def _strip_breaks(children: List[Any]) -> List[Any]:
    """Drop the line breaks opening or closing a message or a list item."""
    while children and isinstance(children[0], TriccMessageBreak):
        children.pop(0)
    while children and isinstance(children[-1], TriccMessageBreak):
        children.pop()
    return children


def normalize_message(message: TriccMessage) -> TriccMessage:
    """Clean a message tree once, after it is parsed.

    Empty marks are dropped, neighbouring marks of the same kind merged, spaces and line
    breaks at a mark's edges moved outside it (``<b>VITAMIN </b>A``, ``<b>HIV:<br></b>``),
    runs of line breaks capped at :data:`MAX_CONSECUTIVE_BREAKS`, and line breaks opening
    or closing the message or a list item dropped. See fix/20261120-fhir-text-format.md.
    """
    return TriccMessage(children=_strip_breaks(_normalize_nodes(message.children)))


NON_INLINE_TAGS = BLOCK_TAGS | DROP_TAGS | frozenset({"br", "ul", "ol", "li"})


def _is_inline(node) -> bool:
    if isinstance(node, NavigableString):
        return True
    return isinstance(node, Tag) and (node.name or "").lower() not in NON_INLINE_TAGS


def _parse_html_children(children) -> List[Any]:
    nodes: List[Any] = []
    for child in children:
        nodes.extend(_parse_html_node(child, allow_leading_block_break=bool(nodes)))
    # A token split over inline elements (``<span>${</span><span>dose}</span>``) is whole
    # once the neighbouring text is merged.
    split: List[Any] = []
    for node in _merge_adjacent_text(nodes):
        if isinstance(node, TriccMessageText) and INJECTION_TOKEN_RE.search(node.value):
            split.extend(_split_text_tokens(node.value))
        else:
            split.append(node)
    return split


def _parse_html_node(node, allow_leading_block_break: bool = False) -> List[Any]:
    if isinstance(node, NavigableString):
        text = _normalize_text(str(node))
        if not text:
            return []
        if text.isspace():
            # A space between two inline elements is a word separator (``<b>a</b> <b>b</b>``);
            # around blocks, list items and line breaks it is only source layout.
            inline = _is_inline(node.previous_sibling) and _is_inline(node.next_sibling)
            return [TriccMessageText(value=" ")] if inline else []
        return _split_text_tokens(text)

    if not isinstance(node, Tag):
        return []

    name = (node.name or "").lower()
    if name in DROP_TAGS:
        return []
    if name in UNWRAP_TAGS:
        return _parse_html_children(node.children)
    if name == "br":
        return [TriccMessageBreak()]
    if name in STRONG_TAGS:
        inner = _parse_html_children(node.children)
        return [TriccMessageMark(kind=TriccMessageMarkKind.STRONG, children=inner)] if inner else []
    if name in EM_TAGS:
        inner = _parse_html_children(node.children)
        return [TriccMessageMark(kind=TriccMessageMarkKind.EM, children=inner)] if inner else []
    if name == "u":
        inner = _parse_html_children(node.children)
        return [TriccMessageMark(kind=TriccMessageMarkKind.U, children=inner)] if inner else []
    if name in BLOCK_TAGS:
        inner = _parse_html_children(node.children)
        if not inner:
            return []
        if allow_leading_block_break:
            return [TriccMessageBreak(), *inner]
        return inner
    if name in ("ul", "ol"):
        items = []
        for li in node.find_all("li", recursive=False):
            items.append(TriccMessageListItem(children=_parse_html_children(li.children)))
        if not items:
            return []
        return [TriccMessageList(ordered=(name == "ol"), items=items)]
    if name == "li":
        return _parse_html_children(node.children)
    return _parse_html_children(node.children)


def parse_html_to_message(raw: str) -> Union[str, TriccMessage]:
    """Parse an HTML (or plain) fragment into a message tree, then simplify."""
    if raw is None:
        return raw
    soup = BeautifulSoup(raw, "html.parser")
    root = soup.body if soup.body is not None else soup
    children = _parse_html_children(root.children)
    return _simplify_message(normalize_message(TriccMessage(children=children)))


def load_display_text(
    raw: Any,
    clean_fn: Optional[Callable[[str], str]] = None,
) -> Any:
    """Input-load entrypoint: parse HTML to a message tree, split ``${REF}``.

    ``clean_fn`` is ignored (kept for call-site compatibility). HTML must not be
    markdownified before the tree exists.
    """
    if raw is None:
        return raw

    if isinstance(raw, dict):
        return {locale: load_display_text(value, clean_fn=clean_fn) for locale, value in raw.items()}

    if _is_message_tree(raw) or isinstance(raw, (TriccOperation, TriccReference, TriccStatic)):
        return raw

    if not isinstance(raw, str):
        return raw

    stripped = raw.strip() if raw else raw
    if not stripped:
        return stripped
    return parse_html_to_message(stripped)


def apply_display_text_injections(node: TriccNodeBaseModel, clean_fn=None) -> None:
    """Load injection fields on a display node in place. Caller must ensure scope."""
    for field in TEXT_INJECTION_FIELDS:
        if not hasattr(node, field):
            continue
        raw = getattr(node, field, None)
        if raw is None:
            continue
        if _is_message_tree(raw) or isinstance(raw, (TriccOperation, TriccReference, TriccStatic)):
            continue
        if isinstance(raw, dict) and any(
            _is_message_tree(v) or isinstance(v, (TriccOperation, TriccReference, TriccStatic))
            for v in raw.values()
        ):
            continue
        setattr(node, field, load_display_text(raw, clean_fn=clean_fn))


def _default_injection_name(value: Any) -> str:
    """Fallback name extractor when no export callback is provided."""
    if isinstance(value, TriccReference):
        return str(value.value)
    if isinstance(value, TriccStatic):
        return str(value.value)
    if isinstance(value, TriccMessageText):
        return str(value.value)
    export_name = getattr(value, "export_name", None)
    if export_name:
        return str(export_name)
    name = getattr(value, "name", None)
    if name:
        return str(name)
    return str(value)


def _interp_token(value: Any, callback: Callable[[Any], str]) -> str:
    return f"${{{callback(value)}}}"


def _markdown_nodes(nodes: List[Any], token: Callable[[Any], str]) -> str:
    chunks: List[str] = []
    for node in nodes or []:
        chunks.append(_markdown_node(node, token))
    return "".join(chunks)


def _markdown_node(node: Any, token: Callable[[Any], str]) -> str:
    """Markdown of a message node; ``token`` renders a reference (``${name}`` for ODK)."""
    if node is None:
        return ""
    if isinstance(node, dict):
        if not node:
            return ""
        return _markdown_node(next(iter(node.values())), token)
    if isinstance(node, str):
        return node
    if isinstance(node, TriccMessageText):
        return node.value
    if isinstance(node, TriccMessageBreak):
        return "\n"
    if isinstance(node, TriccReference):
        return token(node)
    if isinstance(node, TriccStatic):
        return str(node.value)
    if isinstance(node, TriccMessageMark):
        inner = _markdown_nodes(node.children, token)
        if node.kind == TriccMessageMarkKind.STRONG:
            open_, close = STRONG_WRAP
            return f"{open_}{inner}{close}"
        if node.kind == TriccMessageMarkKind.EM:
            open_, close = EM_WRAP
            return f"{open_}{inner}{close}"
        return inner
    if isinstance(node, TriccMessageListItem):
        return _markdown_nodes(node.children, token)
    if isinstance(node, TriccMessageList):
        lines = []
        for i, item in enumerate(node.items or [], start=1):
            prefix = f"{i}. " if node.ordered else "- "
            lines.append(prefix + _markdown_nodes(item.children, token))
        return "\n".join(lines)
    if isinstance(node, TriccMessage):
        return _markdown_nodes(node.children, token)
    if isinstance(node, TriccNodeBaseModel):
        return token(node)
    if isinstance(node, TriccOperation):
        if node.operator == TriccOperator.CONCATENATE:
            return "".join(_markdown_node(part, token) for part in node.reference or [])
        logger.error(
            "Display text has non-CONCATENATE operation %s; cannot serialize for JS text",
            node.operator,
        )
        exit(1)
    return str(node)


def serialize_injection_for_js_text(
    value: Any,
    callback: Optional[Callable[[Any], str]] = None,
) -> str:
    """Render display text for ODK/CHT: Markdown with ``${export_name}`` tokens.

    ``callback`` maps a resolved node or ``TriccReference`` to its export field
    name (e.g. ``get_export_name``). Does not emit ``concat(...)``.
    """
    if callback is None:
        callback = _default_injection_name
    if value is None:
        return ""
    return _markdown_node(value, lambda ref: _interp_token(ref, callback))


def serialize_injection_markdown(value: Any, reference_text: str) -> str:
    """Markdown of display text with every reference shown as ``reference_text``."""
    if value is None:
        return ""
    return _markdown_node(value, lambda ref: reference_text).strip()


def _plain_nodes(nodes: List[Any], reference_text: str) -> str:
    return "".join(_plain_node(node, reference_text) for node in nodes or [])


def _plain_node(node: Any, reference_text: str) -> str:
    if node is None:
        return ""
    if isinstance(node, dict):
        return _plain_node(next(iter(node.values()), None), reference_text)
    if isinstance(node, str):
        return node
    if isinstance(node, TriccMessageText):
        return node.value
    if isinstance(node, TriccMessageBreak):
        return "\n"
    if isinstance(node, TriccStatic):
        return str(node.value)
    if isinstance(node, (TriccReference, TriccNodeBaseModel)):
        return reference_text
    if isinstance(node, (TriccMessage, TriccMessageMark, TriccMessageListItem)):
        return _plain_nodes(node.children, reference_text)
    if isinstance(node, TriccMessageList):
        return "\n".join(
            (f"{i}. " if node.ordered else "• ") + _plain_nodes(item.children, reference_text)
            for i, item in enumerate(node.items or [], start=1)
        )
    if isinstance(node, TriccOperation) and node.operator == TriccOperator.CONCATENATE:
        return _plain_nodes(node.reference, reference_text)
    return str(node)


def serialize_injection_plain(value: Any, reference_text: str) -> str:
    """Plain text of display text: no marks, line breaks kept, ``•`` list items, every
    reference shown as ``reference_text``."""
    return _plain_node(value, reference_text).strip()


def _xhtml_list(node: TriccMessageList, reference_text: str) -> str:
    tag = "ol" if node.ordered else "ul"
    items = "".join(f"<li>{_xhtml_nodes(item.children, reference_text)}</li>" for item in node.items or [])
    return f"<{tag}>{items}</{tag}>"


def _xhtml_nodes(nodes: List[Any], reference_text: str) -> str:
    return "".join(_xhtml_node(node, reference_text) for node in nodes or [])


def _xhtml_node(node: Any, reference_text: str) -> str:
    if node is None:
        return ""
    if isinstance(node, str):
        return html.escape(node, quote=False).replace("\n", "<br/>")
    if isinstance(node, TriccMessageText):
        return html.escape(node.value, quote=False).replace("\n", "<br/>")
    if isinstance(node, TriccMessageBreak):
        return "<br/>"
    if isinstance(node, TriccStatic):
        return html.escape(str(node.value), quote=False)
    if isinstance(node, (TriccReference, TriccNodeBaseModel)):
        return html.escape(reference_text, quote=False)
    if isinstance(node, TriccMessageMark):
        tag = XHTML_MARK_TAGS.get(node.kind)
        inner = _xhtml_nodes(node.children, reference_text)
        return f"<{tag}>{inner}</{tag}>" if tag else inner
    if isinstance(node, TriccMessageList):
        return _xhtml_list(node, reference_text)
    if isinstance(node, (TriccMessage, TriccMessageListItem)):
        return _xhtml_nodes(node.children, reference_text)
    if isinstance(node, TriccOperation) and node.operator == TriccOperator.CONCATENATE:
        return _xhtml_nodes(node.reference, reference_text)
    return html.escape(str(node), quote=False)


def serialize_injection_xhtml(value: Any, reference_text: str) -> str:
    """An XHTML ``div`` (FHIR narrative style) of display text.

    A blank line (two or more line breaks) separates ``p`` blocks, one line break is a
    ``br``, a list is a ``ul`` / ``ol`` block, marks are ``strong`` / ``em`` / ``u``, text
    is escaped and every reference is shown as ``reference_text``. Empty text gives ``""``.
    """
    if isinstance(value, dict):
        value = next(iter(value.values()), None)
    if value is None:
        return ""
    if isinstance(value, TriccMessage):
        nodes = list(value.children or [])
    elif isinstance(value, TriccOperation) and value.operator == TriccOperator.CONCATENATE:
        nodes = list(value.reference or [])
    elif isinstance(value, str):
        nodes = []
        for i, line in enumerate(value.split("\n")):
            if i:
                nodes.append(TriccMessageBreak())
            nodes.append(TriccMessageText(value=line))
    else:
        nodes = [value]
    blocks: List[str] = []
    paragraph: List[str] = []
    breaks = 0

    def flush() -> None:
        if paragraph:
            blocks.append(f"<p>{''.join(paragraph)}</p>")
            paragraph.clear()

    for node in nodes:
        if isinstance(node, TriccMessageBreak):
            breaks += 1
            continue
        if isinstance(node, TriccMessageList):
            flush()
            blocks.append(_xhtml_list(node, reference_text))
        else:
            if breaks >= 2:
                flush()
            elif breaks == 1 and paragraph:
                paragraph.append("<br/>")
            inline = _xhtml_node(node, reference_text)
            if inline.strip() or paragraph:
                paragraph.append(inline)
        breaks = 0
    flush()
    return f'<div xmlns="{XHTML_NS}">{"".join(blocks)}</div>' if blocks else ""


def _concat_parts_from_nodes(nodes: List[Any]) -> List[Any]:
    parts: List[Any] = []
    for node in nodes or []:
        parts.extend(_concat_parts_from_node(node))
    return _merge_concat_statics(parts)


def _merge_concat_statics(parts: List[Any]) -> List[Any]:
    merged: List[Any] = []
    for part in parts:
        last_static = (
            merged
            and isinstance(merged[-1], TriccStatic)
        )
        this_static = isinstance(part, TriccStatic)
        if last_static and this_static:
            merged[-1] = TriccStatic(str(merged[-1].value) + str(part.value))
        else:
            merged.append(part)
    return merged


def _wrap_concat_parts(parts: List[Any], open_: str, close: str) -> List[Any]:
    if not parts:
        return []
    wrapped = list(parts)
    first_static = isinstance(wrapped[0], TriccStatic)
    last_static = isinstance(wrapped[-1], TriccStatic)
    if first_static:
        wrapped[0] = TriccStatic(open_ + str(wrapped[0].value))
    else:
        wrapped.insert(0, TriccStatic(open_))
    if last_static:
        wrapped[-1] = TriccStatic(str(wrapped[-1].value) + close)
    else:
        wrapped.append(TriccStatic(close))
    return wrapped


def _concat_parts_from_node(node: Any) -> List[Any]:
    if node is None:
        return []
    if isinstance(node, str):
        return [TriccStatic(node)] if node else []
    if isinstance(node, TriccMessageText):
        return [TriccStatic(node.value)] if node.value else []
    if isinstance(node, TriccMessageBreak):
        return [TriccStatic("\n")]
    if isinstance(node, TriccReference):
        return [node]
    if isinstance(node, TriccStatic):
        return [node]
    if issubclass(node.__class__, TriccNodeBaseModel):
        return [node]
    if isinstance(node, TriccMessageMark):
        inner = _concat_parts_from_nodes(node.children)
        if node.kind == TriccMessageMarkKind.STRONG:
            return _wrap_concat_parts(inner, *STRONG_WRAP)
        if node.kind == TriccMessageMarkKind.EM:
            return _wrap_concat_parts(inner, *EM_WRAP)
        return inner
    if isinstance(node, TriccMessageListItem):
        return _concat_parts_from_nodes(node.children)
    if isinstance(node, TriccMessageList):
        lines: List[Any] = []
        for i, item in enumerate(node.items or [], start=1):
            prefix = f"{i}. " if node.ordered else "- "
            item_parts = _concat_parts_from_nodes(item.children)
            piece = _wrap_concat_parts(item_parts, prefix, "") if item_parts else [TriccStatic(prefix)]
            if lines:
                lines.append(TriccStatic("\n"))
            lines.extend(piece)
        return lines
    if isinstance(node, TriccMessage):
        return _concat_parts_from_nodes(node.children)
    if isinstance(node, TriccOperation):
        if node.operator == TriccOperator.CONCATENATE:
            return list(node.reference or [])
        return [node]
    return [TriccStatic(str(node))]


def message_to_concatenate_operation(value: Any) -> Optional[TriccOperation]:
    """Serialize-time Concatenate for FHIRPath. Never stored as the message type."""
    if isinstance(value, TriccOperation) and value.operator == TriccOperator.CONCATENATE:
        return value
    if not isinstance(value, TriccMessage):
        return None
    parts = _concat_parts_from_nodes(value.children)
    if not parts:
        return None
    if len(parts) == 1 and isinstance(parts[0], TriccStatic):
        return None

    def _is_interp(part: Any) -> bool:
        if isinstance(part, TriccReference):
            return True
        if isinstance(part, TriccStatic):
            return False
        if isinstance(part, TriccOperation):
            return True
        return issubclass(part.__class__, TriccNodeBaseModel)

    if not any(_is_interp(p) for p in parts):
        return None
    return TriccOperation(operator=TriccOperator.CONCATENATE, reference=parts)
