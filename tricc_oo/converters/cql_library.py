"""Project CQL libraries (tricc.yaml ``libraries``) -> calculate nodes.

A library is a list of named expressions; in TRICC terms each ``define`` is a
calculate. Only expression definitions are supported: ``library`` / ``using`` /
``include`` / ``context`` / ``parameter`` / terminology declarations are ignored, and
functions with a body are rejected. Each body goes through the same CQL -> operation
converter as expressions written in drawio or yaml, so references to questions, other
calculates and other defines work the same way.

A ``function`` is recorded as a :class:`FunctionSignature` (``project.function_signatures``)
so outputs can type a call TRICC passes through as written (a ``native`` operation):

    /*
    @description: Weight-for-age z-score from the WHO tables
    @retrieve: false
    */
    define function Zscore(chart String, sex String, value Decimal) returns FHIR.decimal: external

* ``external`` (CQL: implemented elsewhere) is a declaration only: never written into a
  generated library. A function with a body is real CQL; not supported yet.
* The ``returns`` type is a FHIR data type (``FHIR.decimal``) or its CQL System name
  (``Decimal``, ``System.Decimal``); see :data:`CQL_TO_FHIR_TYPE`.
* CQL documentation tags (``@name: value`` in the ``/* */`` comment just before the
  definition) are kept as written. Only ``@retrieve: false`` marks a function whose value
  depends only on its arguments (foldable as a constant). Without the tag, or with
  ``@retrieve: true``, it is assumed to read recorded data and is never folded.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from tricc_oo.converters.utils import generate_id
from tricc_oo.models.base import TriccNodeType
from tricc_oo.models.calculate import TriccNodeCalculate

logger = logging.getLogger("default")

_COMMENTS = re.compile(r"/\*.*?\*/|//[^\n]*", re.S)
_DEFINE = re.compile(
    r"^\s*(?P<define>define)\s+(?:(?:public|private)\s+)?(?P<function>(?:fluent\s+)?function\s+)?"
    r"(?P<name>\"(?:[^\"\\]|\\.)+\"|[A-Za-z_][A-Za-z0-9_]*)\s*(?P<params>\([^)]*\))?(?P<tail>[^:]*?):",
    re.M,
)
_NAME_OK = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")
_RETURNS = re.compile(r"\breturns\s+(?P<type>[A-Za-z_][A-Za-z0-9_.]*)\s*$")
_TAG = re.compile(r"^@(?P<name>[A-Za-z_][A-Za-z0-9_.-]*)\s*:?\s*(?P<value>.*)$")
_BOOLEAN_TAGS = ("retrieve",)

# FHIR data type of a CQL type specifier, by its unqualified, lower-cased name
# (``FHIR.decimal``, ``System.Decimal`` and ``Decimal`` are all ``decimal``).
CQL_TO_FHIR_TYPE = {
    "boolean": "boolean",
    "integer": "integer",
    "long": "integer",
    "decimal": "decimal",
    "string": "string",
    "date": "date",
    "datetime": "dateTime",
    "time": "time",
    "quantity": "Quantity",
    "code": "Coding",
    "coding": "Coding",
    "concept": "CodeableConcept",
    "codeableconcept": "CodeableConcept",
}

# Functions TRICC itself writes as CQL calls with no operator of their own
# (``xpath_to_cql`` turns ``zscore(…)`` into ``Zscore(…)``). A project library may
# redeclare them.
BUILTIN_FUNCTION_TYPES: Dict[str, str] = {
    "zscore": "decimal",
    "izscore": "decimal",
}


def fhir_type_of_cql_type(type_specifier: str) -> Optional[str]:
    """FHIR data type for a CQL type specifier, None when not a supported value type."""
    return CQL_TO_FHIR_TYPE.get(type_specifier.rsplit(".", 1)[-1].lower())


@dataclass(frozen=True)
class FunctionSignature:
    """A function a project library declares (see the module docstring)."""

    name: str
    return_type: str  # FHIR data type
    # (name, type as written) per argument
    arguments: Tuple[Tuple[str, str], ...] = ()
    # CQL documentation tags, ``@name: value``, values as written
    tags: Dict[str, str] = field(default_factory=dict)
    # declaration only: never written into a generated library
    external: bool = True
    source: str = "<library>"

    @property
    def retrieve(self) -> bool:
        """True unless ``@retrieve: false``: the value may read recorded data (never a constant)."""
        return self.tags.get("retrieve", "true").lower() != "false"


def _blank_comments(text: str) -> str:
    """``text`` with comments replaced by spaces (positions and newlines kept)."""
    out, i = [], 0
    for m in _COMMENTS.finditer(text):
        # Keep string literals intact: only drop comments outside quotes.
        if text[: m.start()].count("'") % 2:
            continue
        out.append(text[i : m.start()])
        out.append(re.sub(r"[^\n]", " ", m.group(0)))
        i = m.end()
    out.append(text[i:])
    return "".join(out)


def _leading_tags(raw: str, position: int, name: str, source: str) -> Dict[str, str]:
    """Documentation tags of the ``/* */`` comment right before ``position``."""
    before = raw[:position].rstrip()
    if not before.endswith("*/"):
        return {}
    opening = before.rfind("/*")
    if opening < 0:
        return {}
    tags: Dict[str, str] = {}
    current = None
    for line in before[opening + 2 : -2].splitlines():
        line = line.strip().lstrip("*").strip()
        tag = _TAG.match(line)
        if tag:
            current = tag.group("name").lower()
            if current in tags:
                raise ValueError(f"{source}: tag @{current} appears twice on {name!r}")
            tags[current] = tag.group("value").strip()
        elif current and line:
            tags[current] = f"{tags[current]} {line}".strip()
    for flag in _BOOLEAN_TAGS:
        if flag in tags and tags[flag].lower() not in ("true", "false"):
            raise ValueError(f"{source}: @{flag} on {name!r} must be true or false, not {tags[flag]!r}")
    return tags


def _arguments(params: Optional[str], name: str, source: str) -> Tuple[Tuple[str, str], ...]:
    """``(name, type)`` per operand of ``(a String, b List<Decimal>)``."""
    inner = (params or "()").strip()[1:-1]
    parts, depth, current = [], 0, ""
    for char in inner:
        if char in "<{":
            depth += 1
        elif char in ">}":
            depth -= 1
        if char == "," and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += char
    parts.append(current)
    arguments = []
    for part in (p.strip() for p in parts):
        if not part:
            continue
        operand = part.split(None, 1)
        if len(operand) != 2:
            raise ValueError(f"{source}: argument {part!r} of function {name!r} needs a name and a type")
        arguments.append((operand[0].strip('"'), operand[1].strip()))
    return tuple(arguments)


def native_function_type(project, name) -> Optional[str]:
    """FHIR result type of a function called as written (a ``native`` operation), else None.

    The project's declarations first, then :data:`BUILTIN_FUNCTION_TYPES`. Names match
    case-insensitively: ``xpath_to_cql`` writes ``Zscore`` for ``zscore``.
    """
    signature = function_signature(project, name)
    if signature is not None:
        return signature.return_type
    return BUILTIN_FUNCTION_TYPES.get(name.lower()) if isinstance(name, str) else None


def function_signature(project, name) -> Optional[FunctionSignature]:
    """The project's declaration of function ``name`` (case-insensitive), else None."""
    if not isinstance(name, str):
        return None
    key = name.lower()
    for declared, signature in (getattr(project, "function_signatures", None) or {}).items():
        if declared.lower() == key:
            return signature
    return None


def _library_entries(text: str, source: str):
    """``(name, header match, body)`` for every define, in file order (positions as in ``text``)."""
    blanked = _blank_comments(text)
    matches = list(_DEFINE.finditer(blanked))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(blanked)
        name = m.group("name").strip('"')
        yield name, m, blanked[m.end() : end].strip()


def _return_type(name: str, tail: str, source: str) -> str:
    """FHIR type a function declares (its ``returns`` clause)."""
    returns = _RETURNS.search(tail)
    if not returns:
        raise ValueError(f"{source}: function {name!r} must declare its type with 'returns'")
    fhir_type = fhir_type_of_cql_type(returns.group("type"))
    if fhir_type is None:
        raise ValueError(
            f"{source}: function {name!r} returns {returns.group('type')!r}; "
            f"use one of {', '.join(sorted(set(CQL_TO_FHIR_TYPE.values())))}"
        )
    return fhir_type


def _is_function(m) -> bool:
    return bool(m.group("function") or m.group("params"))


def _check_external(name: str, body: str, source: str) -> None:
    """Only ``external`` functions for now; a body (real CQL to write out) is planned."""
    if body != "external":
        raise ValueError(
            f"{source}: CQL functions with a body are not supported yet (define {name!r}); "
            "declare it 'external'"
        )


def parse_cql_library_functions(text: str, source: str = "<library>") -> Dict[str, FunctionSignature]:
    """Every function of a library, by name, in file order."""
    functions: Dict[str, FunctionSignature] = {}
    for name, m, body in _library_entries(text, source):
        if not _is_function(m):
            continue
        _check_external(name, body, source)
        if name in functions:
            raise ValueError(f"{source}: function {name!r} appears twice")
        functions[name] = FunctionSignature(
            name=name,
            return_type=_return_type(name, m.group("tail"), source),
            arguments=_arguments(m.group("params"), name, source),
            tags=_leading_tags(text, m.start("define"), name, source),
            external=True,
            source=source,
        )
    return functions


def parse_cql_library(text: str, source: str = "<library>") -> List[Tuple[str, str]]:
    """Return ``[(define name, expression text)]`` in file order (functions: see
    :func:`parse_cql_library_functions`)."""
    defines: List[Tuple[str, str]] = []
    seen = set()
    for name, m, body in _library_entries(text, source):
        if _is_function(m):
            _check_external(name, body, source)
            continue
        if not _NAME_OK.match(name):
            raise ValueError(
                f"{source}: define {name!r} must be a plain identifier (letters, digits, _ or .) "
                "so it can be used as a calculate name"
            )
        if name in seen:
            raise ValueError(f"{source}: define {name!r} appears twice")
        seen.add(name)
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
