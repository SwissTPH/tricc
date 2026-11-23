"""Plain and formatted Questionnaire text (fix/20261120-fhir-text-format.md).

FHIR ``string`` elements such as ``Questionnaire.item.text`` are plain text. The export
writes a plain rendering of the display-text tree there, and the formatted rendering of
the same tree as an extension on ``_text``:

- ``rendering-markdown`` (``valueMarkdown``), the default;
- ``rendering-xhtml`` (``valueString`` holding an XHTML ``div``).

The renderers live with the tree, in ``tricc_oo.visitors.text_injection``.
"""

from typing import Any, Optional

from tricc_oo.visitors.text_injection import (
    serialize_injection_markdown,
    serialize_injection_plain,
    serialize_injection_xhtml,
)

RENDERING_MARKDOWN_EXT = "http://hl7.org/fhir/StructureDefinition/rendering-markdown"
RENDERING_XHTML_EXT = "http://hl7.org/fhir/StructureDefinition/rendering-xhtml"

TEXT_FORMAT_MARKDOWN = "markdown"
TEXT_FORMAT_HTML = "html"
TEXT_FORMATS = (TEXT_FORMAT_MARKDOWN, TEXT_FORMAT_HTML)

# Stand-in for a ``${name}`` reference in static text: the live value comes from the
# cqf-expression on ``_text`` when the renderer evaluates it.
REFERENCE_STAND_IN = "…"


def plain_text(value: Any) -> str:
    """Plain text of a display-text value (tree, string, or dict of locales)."""
    return serialize_injection_plain(value, REFERENCE_STAND_IN)


def build_text_rendering_extension(value: Any, text_format: str) -> Optional[dict]:
    """The rendering extension carrying ``value`` formatted in ``text_format``.

    Args:
        value: Display-text value (``TriccMessage``, string, …).
        text_format: :data:`TEXT_FORMAT_MARKDOWN` or :data:`TEXT_FORMAT_HTML`.

    Returns:
        A ``rendering-markdown`` or ``rendering-xhtml`` extension, or None when blank.
    """
    if text_format == TEXT_FORMAT_HTML:
        xhtml = serialize_injection_xhtml(value, REFERENCE_STAND_IN)
        return {"url": RENDERING_XHTML_EXT, "valueString": xhtml} if xhtml else None
    markdown = serialize_injection_markdown(value, REFERENCE_STAND_IN)
    return {"url": RENDERING_MARKDOWN_EXT, "valueMarkdown": markdown} if markdown else None


def set_text_rendering(element: dict, field: str, value: Any, text_format: str) -> None:
    """Put the formatted version of ``element[field]`` on ``element._<field>``.

    Nothing is written when the value carries no formatting and is already the plain
    text in ``element[field]``. An existing rendering extension is replaced; other
    ``_<field>`` extensions (translation, cqf-expression) are kept.

    Args:
        element: Questionnaire item, Coding, … dict to mutate.
        field: Primitive field name (``text``, ``display``, ``prefix``).
        value: Display-text value the plain text was rendered from.
        text_format: :data:`TEXT_FORMAT_MARKDOWN` or :data:`TEXT_FORMAT_HTML`.
    """
    if value is None or serialize_injection_markdown(value, REFERENCE_STAND_IN) == (element.get(field) or ""):
        return
    extension = build_text_rendering_extension(value, text_format)
    if extension is None:
        return
    shadow = element.setdefault(f"_{field}", {})
    others = [
        ext
        for ext in shadow.get("extension") or []
        if ext.get("url") not in (RENDERING_MARKDOWN_EXT, RENDERING_XHTML_EXT)
    ]
    shadow["extension"] = [extension] + others
