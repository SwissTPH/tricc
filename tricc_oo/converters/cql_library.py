"""Project CQL libraries (tricc.yaml ``libraries``) -> calculate nodes.

A library is a list of named expressions; in TRICC terms each ``define`` is a
calculate. Only expression definitions are supported: ``library`` / ``using`` /
``include`` / ``context`` / ``parameter`` / terminology declarations are ignored, and
functions are rejected. Each body goes through the same CQL -> operation converter as
expressions written in drawio or yaml, so references to questions, other calculates
and other defines work the same way.
"""

from __future__ import annotations

import logging
import re
from typing import List, Tuple

from tricc_oo.converters.utils import generate_id
from tricc_oo.models.base import TriccNodeType
from tricc_oo.models.calculate import TriccNodeCalculate

logger = logging.getLogger("default")

_COMMENTS = re.compile(r"/\*.*?\*/|//[^\n]*", re.S)
_DEFINE = re.compile(
    r"^\s*define\s+(?:(?:public|private)\s+)?(?P<function>(?:fluent\s+)?function\s+)?"
    r"(?P<name>\"(?:[^\"\\]|\\.)+\"|[A-Za-z_][A-Za-z0-9_]*)\s*(?P<params>\([^)]*\))?[^:]*?:",
    re.M,
)
_NAME_OK = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")


def _strip_comments(text: str) -> str:
    # Keep string literals intact: only drop comments outside quotes.
    out, i = [], 0
    for m in _COMMENTS.finditer(text):
        if text[: m.start()].count("'") % 2:
            continue
        out.append(text[i : m.start()])
        i = m.end()
    out.append(text[i:])
    return "".join(out)


def parse_cql_library(text: str, source: str = "<library>") -> List[Tuple[str, str]]:
    """Return ``[(define name, expression text)]`` in file order."""
    text = _strip_comments(text)
    matches = list(_DEFINE.finditer(text))
    defines: List[Tuple[str, str]] = []
    seen = set()
    for i, m in enumerate(matches):
        name = m.group("name").strip('"')
        if m.group("function") or m.group("params"):
            raise ValueError(f"{source}: CQL functions are not supported (define {name!r})")
        if not _NAME_OK.match(name):
            raise ValueError(
                f"{source}: define {name!r} must be a plain identifier (letters, digits, _ or .) "
                "so it can be used as a calculate name"
            )
        if name in seen:
            raise ValueError(f"{source}: define {name!r} appears twice")
        seen.add(name)
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[m.end() : end].strip()
        if not body:
            raise ValueError(f"{source}: define {name!r} has no expression")
        defines.append((name, body))
    return defines


def build_library_calculates(text: str, source: str = "<library>") -> List[TriccNodeCalculate]:
    """Calculate nodes for every define of one library (not yet attached to a page)."""
    from tricc_oo.converters.xml_to_tricc import parse_expression

    nodes = []
    for name, body in parse_cql_library(text, source):
        expression = parse_expression("", body)
        if expression is None:
            raise ValueError(f"{source}: define {name!r} is not valid CQL: {body}")
        nodes.append(
            TriccNodeCalculate(
                id=generate_id(f"library:{source}:{name}"),
                tricc_type=TriccNodeType.calculate,
                name=name,
                label=name,
                expression=expression,
            )
        )
    logger.info("Library %s: %s calculate(s)", source, len(nodes))
    return nodes
