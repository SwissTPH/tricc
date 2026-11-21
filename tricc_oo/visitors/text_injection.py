"""Display text at load and at export: thin wrappers over :mod:`tricc_oo.text`.

Scope: ``TriccNodeDisplayModel`` fields only (label, hint, help, constraint_message,
required_message). Not for calculates / rhombus.

At load a label string becomes a ProseMirror document (``TriccText``) or stays a plain
``str`` when it has no structure; every output renders from it. See
``feature/20261120-prosemirror-display-text.md``.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, List, Optional

from tricc_oo.models.base import (
    TriccNodeBaseModel,
    TriccOperation,
    TriccOperator,
    TriccReference,
    TriccStatic,
)
from tricc_oo.text import from_plain, from_text, simplify
from tricc_oo.text.parse import INTERP_RE, empty_doc, paragraph, text_node, interp_node, normalize
from tricc_oo.text.model import TriccText
from tricc_oo.text.render import markdown_parts, to_markdown, to_plain, to_xhtml

logger = logging.getLogger("default")

INJECTION_TOKEN_RE = INTERP_RE

TEXT_INJECTION_FIELDS = (
    "label",
    "hint",
    "help",
    "constraint_message",
    "required_message",
)

_LOADED_TYPES = (TriccText, TriccOperation, TriccReference, TriccStatic)


def text_from_doc(doc: dict) -> Any:
    """A document as a display value: a plain ``str`` without structure, else ``TriccText``."""
    simple = simplify(doc)
    return simple if isinstance(simple, str) else TriccText.from_doc(simple)


def parse_injection_text(text: Any) -> Any:
    """Split plain (non-HTML, non-Markdown) text on ``${name}`` tokens.

    No tokens → the string itself; otherwise a ``TriccText`` of text and ``interp`` nodes.
    """
    if not isinstance(text, str) or not INTERP_RE.search(text):
        return text
    content: List[dict] = []
    last = 0
    for match in INTERP_RE.finditer(text):
        name = match.group(1).strip()
        if not name:
            continue
        if match.start() > last:
            content.append(text_node(text[last:match.start()]))
        content.append(interp_node(name))
        last = match.end()
    if last < len(text):
        content.append(text_node(text[last:]))
    return text_from_doc(normalize({"type": "doc", "content": [paragraph(content)]}))


def load_display_text(raw: Any, clean_fn: Optional[Callable[[str], str]] = None, where: Optional[str] = None) -> Any:
    """Input-load entry point: a label string as a document (HTML when it holds a tag or an
    entity, else Markdown), ``${name}`` split.

    ``clean_fn`` is ignored (kept for call-site compatibility): HTML must not be
    markdownified before the document exists.
    """
    if raw is None:
        return raw
    if isinstance(raw, dict):
        return {locale: load_display_text(value, clean_fn=clean_fn, where=where) for locale, value in raw.items()}
    if isinstance(raw, _LOADED_TYPES) or not isinstance(raw, str):
        return raw
    stripped = raw.strip()
    if not stripped:
        return stripped
    return text_from_doc(from_text(stripped, where))


def apply_display_text_injections(node: TriccNodeBaseModel, clean_fn=None) -> None:
    """Load the display-text fields of a display node in place. Caller must ensure scope."""
    where = getattr(node, "id", None)
    for field in TEXT_INJECTION_FIELDS:
        if not hasattr(node, field):
            continue
        raw = getattr(node, field, None)
        if raw is None or isinstance(raw, _LOADED_TYPES):
            continue
        if isinstance(raw, dict) and any(isinstance(v, _LOADED_TYPES) for v in raw.values()):
            continue
        setattr(node, field, load_display_text(raw, clean_fn=clean_fn, where=where))


# ------------------------------------------------------------------ export


def _default_injection_name(value: Any) -> str:
    """Fallback name extractor when no export callback is provided."""
    if isinstance(value, (TriccReference, TriccStatic)):
        return str(value.value)
    export_name = getattr(value, "export_name", None)
    if export_name:
        return str(export_name)
    name = getattr(value, "name", None)
    if name:
        return str(name)
    return str(value)


def _first_value(value: Any) -> Any:
    if isinstance(value, dict):
        return next(iter(value.values()), None)
    return value


def _part_text(part: Any, reference: Callable[[Any], str]) -> str:
    """Text of one part of a leftover ``CONCATENATE`` (or of a bare value)."""
    if part is None:
        return ""
    if isinstance(part, str):
        return part
    if isinstance(part, TriccStatic):
        return str(part.value)
    if isinstance(part, TriccText):
        return to_markdown(part.doc, lambda name: reference(part.ref(name)))
    if isinstance(part, (TriccReference, TriccNodeBaseModel)):
        return reference(part)
    if isinstance(part, TriccOperation):
        if part.operator == TriccOperator.CONCATENATE:
            return "".join(_part_text(p, reference) for p in part.reference or [])
        logger.error(
            "Display text has non-CONCATENATE operation %s; cannot serialize for JS text",
            part.operator,
        )
        exit(1)
    return str(part)


def serialize_injection_for_js_text(value: Any, callback: Optional[Callable[[Any], str]] = None) -> str:
    """Render display text for ODK/CHT: Markdown with ``${export_name}`` tokens.

    ``callback`` maps a resolved node or ``TriccReference`` to its export field
    name (e.g. ``get_export_name``). Does not emit ``concat(...)``.
    """
    if callback is None:
        callback = _default_injection_name
    return _part_text(_first_value(value), lambda ref: "${" + str(callback(ref)) + "}")


def serialize_injection_markdown(value: Any, reference_text: str) -> str:
    """Markdown of display text with every reference shown as ``reference_text``."""
    return _part_text(_first_value(value), lambda ref: reference_text).strip()


def _as_doc(value: Any, reference_text: str) -> Optional[dict]:
    """A document for any display value; a plain string is taken as written."""
    value = _first_value(value)
    if value is None:
        return None
    if isinstance(value, TriccText):
        return value.doc
    if isinstance(value, str):
        return from_plain(value)
    if isinstance(value, TriccOperation) and value.operator == TriccOperator.CONCATENATE:
        content: List[dict] = []
        for part in value.reference or []:
            text = str(getattr(part, "value", part)) if isinstance(part, (TriccStatic, str)) else reference_text
            for i, line in enumerate(text.split("\n")):
                if i:
                    content.append({"type": "hardBreak"})
                if line:
                    content.append(text_node(line))
        return normalize({"type": "doc", "content": [paragraph(content)]}) if content else empty_doc()
    if isinstance(value, TriccStatic):
        return from_plain(str(value.value))
    if isinstance(value, (TriccReference, TriccNodeBaseModel)):
        return from_plain(reference_text)
    return from_plain(str(value))


def serialize_injection_plain(value: Any, reference_text: str) -> str:
    """Plain text of display text: no marks, line breaks kept, ``•`` list items, every
    reference shown as ``reference_text``. A plain string is returned as written."""
    value = _first_value(value)
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    doc = _as_doc(value, reference_text)
    return to_plain(doc, lambda name: reference_text) if doc else ""


def serialize_injection_xhtml(value: Any, reference_text: str) -> str:
    """An XHTML ``div`` (FHIR narrative style) of display text; ``""`` when empty."""
    doc = _as_doc(value, reference_text)
    return to_xhtml(doc, lambda name: reference_text) if doc else ""


def message_to_concatenate_operation(value: Any) -> Optional[TriccOperation]:
    """Serialize-time Concatenate for FHIRPath / XLSForm: the Markdown of the text cut at
    every ``${name}``, each one as what it stands for. None for static text."""
    if isinstance(value, TriccOperation) and value.operator == TriccOperator.CONCATENATE:
        return value
    if not isinstance(value, TriccText):
        return None
    parts = [value.ref(p[0]) if isinstance(p, tuple) else TriccStatic(p) for p in markdown_parts(value.doc)]
    if not any(not isinstance(p, TriccStatic) for p in parts):
        return None
    return TriccOperation(operator=TriccOperator.CONCATENATE, reference=parts)
