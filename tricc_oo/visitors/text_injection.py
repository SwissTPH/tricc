"""Display-text AST: parse HTML + ``${REF}`` at input load, Markdown at export.

Scope: TriccNodeDisplayModel fields only (label, hint, help, constraint_message,
required_message). Not for calculates / rhombus.

HTML is parsed to ``TriccMessage`` *before* Markdown conversion. See
``feature/20260909-display-message-ast.md``.
"""

from __future__ import annotations

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


def _parse_html_children(children) -> List[Any]:
    nodes: List[Any] = []
    for child in children:
        nodes.extend(_parse_html_node(child, allow_leading_block_break=bool(nodes)))
    return _merge_adjacent_text(nodes)


def _parse_html_node(node, allow_leading_block_break: bool = False) -> List[Any]:
    if isinstance(node, NavigableString):
        text = _normalize_text(str(node))
        if not text or text.isspace():
            return []
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
    return _simplify_message(TriccMessage(children=children))


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


def _markdown_nodes(nodes: List[Any], callback: Callable[[Any], str]) -> str:
    chunks: List[str] = []
    for node in nodes or []:
        chunks.append(_markdown_node(node, callback))
    return "".join(chunks)


def _markdown_node(node: Any, callback: Callable[[Any], str]) -> str:
    if node is None:
        return ""
    if isinstance(node, dict):
        if not node:
            return ""
        return _markdown_node(next(iter(node.values())), callback)
    if isinstance(node, str):
        return node
    if isinstance(node, TriccMessageText):
        return node.value
    if isinstance(node, TriccMessageBreak):
        return "\n"
    if isinstance(node, TriccReference):
        return _interp_token(node, callback)
    if isinstance(node, TriccStatic):
        return str(node.value)
    if isinstance(node, TriccMessageMark):
        inner = _markdown_nodes(node.children, callback)
        if node.kind == TriccMessageMarkKind.STRONG:
            open_, close = STRONG_WRAP
            return f"{open_}{inner}{close}"
        if node.kind == TriccMessageMarkKind.EM:
            open_, close = EM_WRAP
            return f"{open_}{inner}{close}"
        return inner
    if isinstance(node, TriccMessageListItem):
        return _markdown_nodes(node.children, callback)
    if isinstance(node, TriccMessageList):
        lines = []
        for i, item in enumerate(node.items or [], start=1):
            prefix = f"{i}. " if node.ordered else "- "
            lines.append(prefix + _markdown_nodes(item.children, callback))
        return "\n".join(lines)
    if isinstance(node, TriccMessage):
        return _markdown_nodes(node.children, callback)
    if isinstance(node, TriccNodeBaseModel):
        return _interp_token(node, callback)
    if isinstance(node, TriccOperation):
        if node.operator == TriccOperator.CONCATENATE:
            return "".join(_markdown_node(part, callback) for part in node.reference or [])
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
    return _markdown_node(value, callback)


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
            and not isinstance(merged[-1], TriccReference)
        )
        this_static = isinstance(part, TriccStatic) and not isinstance(part, TriccReference)
        if last_static and this_static:
            merged[-1] = TriccStatic(str(merged[-1].value) + str(part.value))
        else:
            merged.append(part)
    return merged


def _wrap_concat_parts(parts: List[Any], open_: str, close: str) -> List[Any]:
    if not parts:
        return []
    wrapped = list(parts)
    first_static = isinstance(wrapped[0], TriccStatic) and not isinstance(wrapped[0], TriccReference)
    last_static = isinstance(wrapped[-1], TriccStatic) and not isinstance(wrapped[-1], TriccReference)
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
    if len(parts) == 1 and isinstance(parts[0], TriccStatic) and not isinstance(parts[0], TriccReference):
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
