"""Display-text `${REF}` injection: parse at input load, ODK re-serialize at export.

Scope: TriccNodeDisplayModel fields only (label, hint, help, constraint_message,
required_message). Not for calculates / rhombus.

Order: clean HTML on the full string first, then split on tokens. Never clean
per CONCATENATE segment (unbalanced HTML tags).
"""

from __future__ import annotations

import logging
import re
from typing import Any, Callable, Dict, Optional, Union

from tricc_oo.converters.utils import remove_html
from tricc_oo.models.base import (
    TriccNodeBaseModel,
    TriccOperation,
    TriccOperator,
    TriccReference,
    TriccStatic,
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


def parse_injection_text(
    text: str,
) -> Union[str, TriccOperation, TriccReference, TriccStatic]:
    """Split already HTML-cleaned text on ``${name}`` tokens.

    Returns the original string when there are no tokens. Otherwise returns a
    ``CONCATENATE`` of ``TriccStatic`` segments and ``TriccReference`` names
    (or a single ``TriccReference`` / ``TriccStatic`` when only one part).
    """
    if text is None:
        return text
    if not isinstance(text, str):
        return text
    if not INJECTION_TOKEN_RE.search(text):
        return text

    parts: list = []
    last_end = 0
    for match in INJECTION_TOKEN_RE.finditer(text):
        if match.start() > last_end:
            parts.append(TriccStatic(text[last_end : match.start()]))
        name = match.group(1).strip()
        if name:
            parts.append(TriccReference(name))
        last_end = match.end()
    if last_end < len(text):
        parts.append(TriccStatic(text[last_end:]))

    if not parts:
        return text
    if len(parts) == 1:
        return parts[0]
    return TriccOperation(operator=TriccOperator.CONCATENATE, reference=parts)


def load_display_text(
    raw: Any,
    clean_fn: Optional[Callable[[str], str]] = None,
) -> Any:
    """Input-load entrypoint: clean full string, then parse injection tokens.

    Accepts ``str`` or multi-lang ``Dict[str, str]``. Never cleans after split.
    """
    if clean_fn is None:
        clean_fn = remove_html

    if raw is None:
        return raw

    if isinstance(raw, dict):
        return {
            locale: load_display_text(value, clean_fn=clean_fn)
            for locale, value in raw.items()
        }

    if not isinstance(raw, str):
        # Already structured (op / ref / node) — leave alone
        return raw

    cleaned = clean_fn(raw.strip()) if raw.strip() else raw
    if cleaned is None:
        cleaned = ""
    return parse_injection_text(cleaned)


def apply_display_text_injections(node: TriccNodeBaseModel, clean_fn=None) -> None:
    """Load injection fields on a display node in place. Caller must ensure scope."""
    for field in TEXT_INJECTION_FIELDS:
        if not hasattr(node, field):
            continue
        raw = getattr(node, field, None)
        if raw is None:
            continue
        if isinstance(raw, (TriccOperation, TriccReference, TriccStatic)):
            continue
        if isinstance(raw, dict) and any(
            isinstance(v, (TriccOperation, TriccReference, TriccStatic)) for v in raw.values()
        ):
            continue
        setattr(node, field, load_display_text(raw, clean_fn=clean_fn))


def _default_injection_name(value: Any) -> str:
    """Fallback name extractor when no export callback is provided."""
    if isinstance(value, TriccReference):
        return str(value.value)
    if isinstance(value, TriccStatic):
        return str(value.value)
    export_name = getattr(value, "export_name", None)
    if export_name:
        return str(export_name)
    name = getattr(value, "name", None)
    if name:
        return str(name)
    return str(value)


def serialize_injection_for_js_text(
    value: Any,
    callback: Optional[Callable[[Any], str]] = None,
) -> str:
    """Render display text for ODK/CHT: static + ``${export_name}`` tokens.

    ``callback`` maps a resolved node or ``TriccReference`` to its export field
    name (e.g. ``get_export_name``). Static segments are written as plain text;
    refs/nodes become ``${callback(...)}``. Does not emit ``concat(...)``.

    Unresolved ``TriccReference`` keep their logical name inside ``${...}``.
    """
    if callback is None:
        callback = _default_injection_name

    if value is None:
        return ""
    if isinstance(value, dict):
        # Caller should pick a locale; fall back to first value
        if not value:
            return ""
        return serialize_injection_for_js_text(next(iter(value.values())), callback)
    if isinstance(value, str):
        return value
    # TriccReference subclasses TriccStatic — check reference first
    if isinstance(value, TriccReference):
        return f"${{{callback(value)}}}"
    if isinstance(value, TriccStatic):
        return str(value.value)
    if isinstance(value, TriccNodeBaseModel):
        return f"${{{callback(value)}}}"
    if isinstance(value, TriccOperation):
        if value.operator == TriccOperator.CONCATENATE:
            return "".join(
                serialize_injection_for_js_text(part, callback) for part in value.reference
            )
        # Non-concatenate ops in display text are not supported for ODK labels
        logger.error(
            "Display text has non-CONCATENATE operation %s; cannot serialize for JS text",
            value.operator,
        )
        exit(1)
    return str(value)
