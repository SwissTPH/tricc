"""The display-text schema: ProseMirror with TipTap names.

Shared with the frontend (``packages/core/src/text/schema.ts``): same node and mark names,
attributes and HTML rules, so a document written by the editor (``editor.getJSON()``) is read
here as is. See ``feature/20261120-prosemirror-display-text.md`` §1.
"""

import re
from typing import Any, Optional

from prosemirror.model import Schema

#: A picture points at a project image the FHIR way, a ``Binary`` by id.
IMAGE_SRC_RE = re.compile(r"^Binary/([a-z0-9][a-z0-9_-]*)$")
#: A CSS colour a text may carry: ``#rgb`` … ``#rrggbbaa`` or a colour name (frontend ``isColor``).
COLOR_RE = re.compile(r"^(#[0-9a-f]{3,8}|[a-z]{3,20})$", re.IGNORECASE)
_STYLE_COLOR_RE = re.compile(r"(?:^|;)\s*color\s*:\s*([^;]+)", re.IGNORECASE)


def is_color(value: Any) -> bool:
    """Whether ``value`` is a colour a text may carry."""
    return isinstance(value, str) and bool(COLOR_RE.match(value))


def style_color(style: Optional[str]) -> Optional[str]:
    """The colour of an inline ``style`` attribute, when it holds a valid one."""
    match = _STYLE_COLOR_RE.search(style or "")
    value = match.group(1).strip() if match else None
    return value if is_color(value) else None


def is_image_src(value: Any) -> bool:
    """Whether ``value`` points at a project image (``Binary/<id>``)."""
    return isinstance(value, str) and bool(IMAGE_SRC_RE.match(value))


def _image_attrs(dom: Any) -> Any:
    src = dom.get("src")
    if not is_image_src(src):
        return False  # only pictures of the image library; any other source is dropped
    return {"src": src, "alt": dom.get("alt") or None}


def _interp_attrs(dom: Any) -> Any:
    name = dom.get("data-interp")
    return {"name": name} if name else False


def _ordered_attrs(dom: Any) -> Any:
    try:
        return {"start": int(dom.get("start") or 1)}
    except ValueError:
        return {"start": 1}


def _color_attrs(dom: Any) -> Any:
    color = style_color(dom.get("style"))
    return {"color": color} if color else False


_NODES = {
    "doc": {"content": "block+"},
    "paragraph": {
        "group": "block",
        "content": "inline*",
        "parseDOM": [{"tag": "p"}, {"tag": "div"}],
        "toDOM": lambda _: ["p", 0],
    },
    "bulletList": {
        "group": "block",
        "content": "listItem+",
        "parseDOM": [{"tag": "ul"}],
        "toDOM": lambda _: ["ul", 0],
    },
    "orderedList": {
        "group": "block",
        "content": "listItem+",
        "attrs": {"start": {"default": 1}},
        "parseDOM": [{"tag": "ol", "getAttrs": _ordered_attrs}],
        "toDOM": lambda node: ["ol", 0] if node.attrs["start"] == 1 else ["ol", {"start": node.attrs["start"]}, 0],
    },
    "listItem": {
        "content": "paragraph block*",
        "defining": True,
        "parseDOM": [{"tag": "li"}],
        "toDOM": lambda _: ["li", 0],
    },
    "text": {"group": "inline"},
    "hardBreak": {
        "group": "inline",
        "inline": True,
        "selectable": False,
        "parseDOM": [{"tag": "br"}],
        "toDOM": lambda _: ["br"],
    },
    "image": {
        "group": "inline",
        "inline": True,
        "atom": True,
        "attrs": {"src": {}, "alt": {"default": None}},
        "parseDOM": [{"tag": "img[src]", "getAttrs": _image_attrs}],
        "toDOM": lambda node: [
            "img",
            {"src": node.attrs["src"], "alt": node.attrs["alt"]} if node.attrs["alt"] else {"src": node.attrs["src"]},
        ],
    },
    "interp": {
        "group": "inline",
        "inline": True,
        "atom": True,
        "attrs": {"name": {}},
        "parseDOM": [{"tag": "span[data-interp]", "getAttrs": _interp_attrs}],
        "toDOM": lambda node: ["span", {"data-interp": node.attrs["name"]}, "${" + node.attrs["name"] + "}"],
    },
}

_MARKS = {
    "bold": {
        "parseDOM": [{"tag": "strong"}, {"tag": "b"}],
        "toDOM": lambda _mark, _inline: ["strong", 0],
    },
    "italic": {
        "parseDOM": [{"tag": "em"}, {"tag": "i"}],
        "toDOM": lambda _mark, _inline: ["em", 0],
    },
    "underline": {
        "parseDOM": [{"tag": "u"}],
        "toDOM": lambda _mark, _inline: ["u", 0],
    },
    "textStyle": {
        "attrs": {"color": {"default": None}},
        "parseDOM": [{"tag": "span[style]", "getAttrs": _color_attrs}],
        "toDOM": lambda mark, _inline: ["span", {"style": f"color: {mark.attrs['color']}"}, 0],
    },
}

#: The display-text schema (``tricc_oo`` side of the shared schema).
TEXT_SCHEMA = Schema({"nodes": _NODES, "marks": _MARKS})

#: Marks Markdown can write, outermost first.
MARKDOWN_MARKS = ("bold", "italic")
LIST_TYPES = ("bulletList", "orderedList")
