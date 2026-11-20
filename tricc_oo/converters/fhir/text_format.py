"""Plain and formatted Questionnaire text (fix/20261120-fhir-text-format.md).

Labels reach the FHIR export as Markdown (draw.io HTML -> ``markdownify``, see
``tricc_oo.converters.utils.remove_html``). FHIR ``string`` elements such as
``Questionnaire.item.text`` are plain text, so the export writes a plain version
there and the formatted label as a rendering extension on ``_text``:

- ``rendering-markdown`` (``valueMarkdown``), the default;
- ``rendering-xhtml`` (``valueString`` holding an XHTML ``div``).

Only the Markdown subset ``markdownify`` produces is handled: ``**strong**``,
``*em*`` / ``_em_``, ``-`` / ``*`` / ``+`` bullets, ``1.`` numbered lists, ``#``
headings, ``[text](url)`` links, ``![alt](src)`` images, backslash escapes, blank-line
paragraphs and hard line breaks.
"""

import html
import re
from typing import List, Optional

RENDERING_MARKDOWN_EXT = "http://hl7.org/fhir/StructureDefinition/rendering-markdown"
RENDERING_XHTML_EXT = "http://hl7.org/fhir/StructureDefinition/rendering-xhtml"

TEXT_FORMAT_MARKDOWN = "markdown"
TEXT_FORMAT_HTML = "html"
TEXT_FORMATS = (TEXT_FORMAT_MARKDOWN, TEXT_FORMAT_HTML)

# Stand-in for a ``${name}`` placeholder in static text: the live value comes from
# the cqf-expression on ``_text`` when the renderer evaluates it.
PLACEHOLDER_STAND_IN = "…"

XHTML_NS = "http://www.w3.org/1999/xhtml"

_PLACEHOLDER = re.compile(r"\$\{[^}]*\}")
_IMAGE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]*)[^)]*\)")
_STRONG = re.compile(r"(\*\*|__)(?=\S)(.+?)(?<=\S)\1")
_EM_STAR = re.compile(r"(?<![\*\w])\*(?=[^\s*])(.+?)(?<=[^\s*])\*(?![\*\w])")
_EM_UNDERSCORE = re.compile(r"(?<![_\w])_(?=[^\s_])(.+?)(?<=[^\s_])_(?![_\w])")
_ESCAPE = re.compile(r"\\([\\`*_{}\[\]()#+\-.!>|~])")
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$")
_BULLET = re.compile(r"^(\s*)[-*+]\s+(.*)$")
_NUMBERED = re.compile(r"^(\s*)(\d+)[.)]\s+(.*)$")
_HARD_BREAK = re.compile(r"( {2,}|\\)$")
_BLANK_RUN = re.compile(r"\n\s*\n(\s*\n)+")
# Broken strong emphasis markdownify leaves from draw.io HTML (tidy_markdown).
_EMPTY_STRONG = re.compile(r"\*{4,}")
_STRONG_CLOSED_NEXT_LINE = re.compile(r"\*\*([^*\n]+?)[ \t]*\n[ \t]*\*\*(?=[ \t]*(\n|$))")
_MARKER_ONLY_LINE = re.compile(r"^[ \t]*\*\*[ \t]*$", re.MULTILINE)
_STRONG_INNER_SPACES = re.compile(r"\*\*([ \t]*)([^*\n]*?[^*\s])([ \t]*)\*\*")
_RESIDUAL_STRONG = re.compile(r"\*\*|(?<!\w)__|__(?!\w)")


def tidy_markdown(text: str) -> str:
    """Repair the strong emphasis ``markdownify`` breaks on draw.io labels.

    ``**H****erpes**`` (empty pair), ``**VITAMIN **A`` (space inside the marker),
    ``**HIV exposed:\n**`` (closed on the next line) and lines holding only ``**``
    become valid Markdown. Runs of blank lines collapse to one.
    """
    text = str(text).replace("\r\n", "\n")
    text = _EMPTY_STRONG.sub("", text)
    text = _STRONG_CLOSED_NEXT_LINE.sub(lambda m: f"**{m.group(1)}**", text)
    text = _MARKER_ONLY_LINE.sub("", text)
    text = _STRONG_INNER_SPACES.sub(lambda m: f"{m.group(1)}**{m.group(2)}**{m.group(3)}", text)
    return _BLANK_RUN.sub("\n\n", text)


def neutralise_placeholders(text: str) -> str:
    """Replace every ``${name}`` placeholder with :data:`PLACEHOLDER_STAND_IN`."""
    return _PLACEHOLDER.sub(PLACEHOLDER_STAND_IN, text)


def _inline_plain(text: str) -> str:
    text = _IMAGE.sub(lambda m: m.group(1), text)
    text = _LINK.sub(lambda m: m.group(1), text)
    for _ in range(2):  # nested emphasis: ***x*** -> *x* -> x
        text = _STRONG.sub(lambda m: m.group(2), text)
        text = _EM_STAR.sub(lambda m: m.group(1), text)
        text = _EM_UNDERSCORE.sub(lambda m: m.group(1), text)
    return _ESCAPE.sub(lambda m: m.group(1), _RESIDUAL_STRONG.sub("", text))


def markdown_to_plain(text: Optional[str]) -> str:
    """Plain text from a label's Markdown.

    Emphasis, links, headings and escapes are dropped, bullets become ``•``, line
    breaks are kept, runs of blank lines collapse to one, and ``${name}``
    placeholders become :data:`PLACEHOLDER_STAND_IN`.

    Args:
        text: Markdown label (or plain text).

    Returns:
        Plain text, stripped.
    """
    if not text:
        return ""
    lines = []
    for raw in tidy_markdown(text).split("\n"):
        line = _HARD_BREAK.sub("", raw.rstrip("\t")).rstrip()
        heading = _HEADING.match(line)
        bullet = _BULLET.match(line)
        if heading:
            line = heading.group(1)
        elif bullet:
            line = f"{bullet.group(1)}• {bullet.group(2)}"
        lines.append(_inline_plain(line))
    plain = _BLANK_RUN.sub("\n\n", "\n".join(lines)).strip()
    return neutralise_placeholders(plain)


def _inline_xhtml(text: str) -> str:
    text = html.escape(text, quote=False)
    text = _IMAGE.sub(lambda m: m.group(1), text)
    text = _LINK.sub(lambda m: f'<a href="{m.group(2).replace(chr(34), "&quot;")}">{m.group(1)}</a>', text)
    for _ in range(2):
        text = _STRONG.sub(lambda m: f"<strong>{m.group(2)}</strong>", text)
        text = _EM_STAR.sub(lambda m: f"<em>{m.group(1)}</em>", text)
        text = _EM_UNDERSCORE.sub(lambda m: f"<em>{m.group(1)}</em>", text)
    return _ESCAPE.sub(lambda m: m.group(1), _RESIDUAL_STRONG.sub("", text))


def _blocks(text: str) -> List[List[str]]:
    """Split Markdown into blocks separated by blank lines."""
    blocks: List[List[str]] = [[]]
    for raw in tidy_markdown(text).split("\n"):
        if raw.strip():
            blocks[-1].append(raw.rstrip("\t"))
        elif blocks[-1]:
            blocks.append([])
    return [b for b in blocks if b]


def _list_kind(line: str) -> Optional[str]:
    if _BULLET.match(line):
        return "ul"
    if _NUMBERED.match(line):
        return "ol"
    return None


def _block_xhtml(lines: List[str]) -> List[str]:
    """Render one block: a heading, list items and paragraph text, in order."""
    out: List[str] = []
    paragraph: List[str] = []
    open_list: Optional[str] = None

    def flush_paragraph() -> None:
        if paragraph:
            # a single newline inside a block is a line break in a label
            out.append(f"<p>{'<br/>'.join(paragraph)}</p>")
            paragraph.clear()

    def close_list() -> None:
        nonlocal open_list
        if open_list:
            out.append(f"</{open_list}>")
            open_list = None

    for raw in lines:
        line = _HARD_BREAK.sub("", raw).rstrip()
        heading = _HEADING.match(line)
        kind = _list_kind(line)
        if heading:
            flush_paragraph()
            close_list()
            out.append(f"<p><strong>{_inline_xhtml(heading.group(1))}</strong></p>")
        elif kind:
            flush_paragraph()
            if open_list != kind:
                close_list()
                out.append(f"<{kind}>")
                open_list = kind
            match = _BULLET.match(line) if kind == "ul" else _NUMBERED.match(line)
            out.append(f"<li>{_inline_xhtml(match.group(match.lastindex))}</li>")
        elif open_list and raw[:1].isspace() and out:
            # continuation of the previous list item
            out[-1] = out[-1][: -len("</li>")] + f"<br/>{_inline_xhtml(line.strip())}</li>"
        else:
            close_list()
            paragraph.append(_inline_xhtml(line.strip()))
    flush_paragraph()
    close_list()
    return out


def markdown_to_xhtml(text: Optional[str]) -> str:
    """An XHTML ``div`` (FHIR narrative style) from a label's Markdown.

    ``${name}`` placeholders become :data:`PLACEHOLDER_STAND_IN`.

    Args:
        text: Markdown label.

    Returns:
        ``<div xmlns="http://www.w3.org/1999/xhtml">…</div>``, or ``""`` for blank input.
    """
    if not text or not str(text).strip():
        return ""
    body = []
    for block in _blocks(neutralise_placeholders(str(text))):
        body.extend(_block_xhtml(block))
    return f'<div xmlns="{XHTML_NS}">{"".join(body)}</div>'


def build_text_rendering_extension(formatted: str, text_format: str) -> Optional[dict]:
    """The rendering extension carrying ``formatted`` (Markdown) in ``text_format``.

    Args:
        formatted: The label's Markdown.
        text_format: :data:`TEXT_FORMAT_MARKDOWN` or :data:`TEXT_FORMAT_HTML`.

    Returns:
        A ``rendering-markdown`` or ``rendering-xhtml`` extension, or None when blank.
    """
    if text_format == TEXT_FORMAT_HTML:
        xhtml = markdown_to_xhtml(formatted)
        return {"url": RENDERING_XHTML_EXT, "valueString": xhtml} if xhtml else None
    markdown = formatted_markdown(formatted)
    return {"url": RENDERING_MARKDOWN_EXT, "valueMarkdown": markdown} if markdown else None


def formatted_markdown(formatted: Optional[str]) -> str:
    """The label Markdown as written to ``rendering-markdown``: placeholders neutralised,
    blank-line runs collapsed, stripped."""
    return tidy_markdown(neutralise_placeholders(str(formatted or ""))).strip()


def set_text_rendering(element: dict, field: str, formatted: Optional[str], text_format: str) -> None:
    """Put the formatted version of ``element[field]`` on ``element._<field>``.

    Nothing is written when the label is already the plain value in
    ``element[field]`` (no formatting, same wording). An existing rendering extension is replaced;
    other ``_<field>`` extensions (translation, cqf-expression) are kept.

    Args:
        element: Questionnaire item, Coding, … dict to mutate.
        field: Primitive field name (``text``, ``display``, ``prefix``).
        formatted: The label's Markdown.
        text_format: :data:`TEXT_FORMAT_MARKDOWN` or :data:`TEXT_FORMAT_HTML`.
    """
    if not formatted or formatted_markdown(formatted) == (element.get(field) or ""):
        return
    extension = build_text_rendering_extension(formatted, text_format)
    if extension is None:
        return
    shadow = element.setdefault(f"_{field}", {})
    others = [
        ext
        for ext in shadow.get("extension") or []
        if ext.get("url") not in (RENDERING_MARKDOWN_EXT, RENDERING_XHTML_EXT)
    ]
    shadow["extension"] = [extension] + others
