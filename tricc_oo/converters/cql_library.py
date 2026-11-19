"""Project CQL libraries (tricc.yaml ``libraries``) -> calculate nodes.

Libraries are parsed with the CQL grammar (``cqlParser.library``); a syntax error names
the file and line.

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

from antlr4 import CommonTokenStream, InputStream
from antlr4.error.ErrorListener import ErrorListener

from tricc_oo.converters.cql.cqlLexer import cqlLexer
from tricc_oo.converters.cql.cqlParser import cqlParser
from tricc_oo.converters.utils import generate_id
from tricc_oo.models.base import TriccNodeType
from tricc_oo.models.calculate import TriccNodeCalculate

logger = logging.getLogger("default")

_NAME_OK = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")
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


class _RaiseOnSyntaxError(ErrorListener):
    def __init__(self, source: str):
        super().__init__()
        self.source = source

    def syntaxError(self, recognizer, offendingSymbol, line, column, msg, e):
        raise ValueError(f"{self.source}: not valid CQL at line {line}:{column}: {msg}")


class _ParsedLibrary:
    """One library parsed with the CQL grammar: its defines and functions, in file order."""

    def __init__(self, text: str, source: str):
        self.text = text
        self.source = source
        self.input = InputStream(text)
        lexer = cqlLexer(self.input)
        lexer.removeErrorListeners()
        lexer.addErrorListener(_RaiseOnSyntaxError(source))
        self.tokens = CommonTokenStream(lexer)
        parser = cqlParser(self.tokens)
        parser.removeErrorListeners()
        parser.addErrorListener(_RaiseOnSyntaxError(source))
        self.tree = parser.library()

    def statements(self):
        for statement in self.tree.statement():
            definition = statement.expressionDefinition() or statement.functionDefinition()
            if definition is not None:
                yield definition

    def source_text(self, ctx) -> str:
        """The text of ``ctx`` exactly as written."""
        return self.input.getText(ctx.start.start, ctx.stop.stop)

    def leading_tags(self, ctx, name: str) -> Dict[str, str]:
        """Documentation tags of the ``/* */`` comment right before ``ctx``."""
        hidden = self.tokens.getHiddenTokensToLeft(ctx.start.tokenIndex) or []
        comment = None
        for token in reversed(hidden):
            if token.type == cqlLexer.WS:
                continue
            if token.type == cqlLexer.COMMENT:
                comment = token.text
            break
        if comment is None:
            return {}
        return _parse_tags(comment[2:-2], name, self.source)


def _identifier(ctx) -> str:
    """An identifier as a name: ``"quoted"`` and `` `delimited` `` without their quotes."""
    text = ctx.getText()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"`":
        return text[1:-1]
    return text


def _parse_tags(comment: str, name: str, source: str) -> Dict[str, str]:
    """``{tag: value}`` from a comment body; a line without ``@`` continues the last value."""
    tags: Dict[str, str] = {}
    current = None
    for line in comment.splitlines():
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


def _function_signature(library: _ParsedLibrary, ctx) -> FunctionSignature:
    name = _identifier(ctx.identifierOrFunctionIdentifier())
    source = library.source
    if ctx.functionBody() is not None:
        raise ValueError(
            f"{source}: CQL functions with a body are not supported yet (define {name!r}); "
            "declare it 'external'"
        )
    if ctx.typeSpecifier() is None:
        raise ValueError(f"{source}: function {name!r} must declare its type with 'returns'")
    returns = library.source_text(ctx.typeSpecifier())
    return_type = fhir_type_of_cql_type(returns)
    if return_type is None:
        raise ValueError(
            f"{source}: function {name!r} returns {returns!r}; "
            f"use one of {', '.join(sorted(set(CQL_TO_FHIR_TYPE.values())))}"
        )
    return FunctionSignature(
        name=name,
        return_type=return_type,
        arguments=tuple(
            (_identifier(operand.referentialIdentifier()), library.source_text(operand.typeSpecifier()))
            for operand in ctx.operandDefinition()
        ),
        tags=library.leading_tags(ctx, name),
        external=True,
        source=source,
    )


def parse_cql_library_functions(text: str, source: str = "<library>") -> Dict[str, FunctionSignature]:
    """Every function of a library, by name, in file order."""
    library = _ParsedLibrary(text, source)
    functions: Dict[str, FunctionSignature] = {}
    for ctx in library.statements():
        if not isinstance(ctx, cqlParser.FunctionDefinitionContext):
            continue
        signature = _function_signature(library, ctx)
        if signature.name in functions:
            raise ValueError(f"{source}: function {signature.name!r} appears twice")
        functions[signature.name] = signature
    return functions


def parse_cql_library(text: str, source: str = "<library>") -> List[Tuple[str, str]]:
    """Return ``[(define name, expression text)]`` in file order (functions: see
    :func:`parse_cql_library_functions`)."""
    library = _ParsedLibrary(text, source)
    defines: List[Tuple[str, str]] = []
    seen = set()
    for ctx in library.statements():
        if isinstance(ctx, cqlParser.FunctionDefinitionContext):
            _function_signature(library, ctx)  # rejects a body
            continue
        name = _identifier(ctx.identifier())
        if not _NAME_OK.match(name):
            raise ValueError(
                f"{source}: define {name!r} must be a plain identifier (letters, digits, _ or .) "
                "so it can be used as a calculate name"
            )
        if name in seen:
            raise ValueError(f"{source}: define {name!r} appears twice")
        seen.add(name)
        defines.append((name, library.source_text(ctx.expression())))
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
