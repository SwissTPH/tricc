"""Project CQL libraries (tricc.yaml ``libraries``) -> calculate nodes.

A library is **standard CQL** unless it declares TRICC's dialect: it is parsed with the
untouched upstream grammar (``cqlParser.library``, no ``not in``, no ``{{placeholders}}``) and
TRICC's limits are checked when each define is read as a TRICC expression. A library that starts
with a comment holding ``@dialect: tricc-cql@<version>`` is parsed with the TRICC profile
(``tricc_cqlParser.library``); feature/20261125-expression-languages.md §1.8:

    /* @dialect: tricc-cql@1.0.0 */
    library Helpers
    define "not_sick": 'fever' not in "symptoms"

An unknown dialect, or a ``tricc-cql`` major version other than the one in use, is
``E_CQL_DIALECT``. A syntax error names the file and line.

A library is a list of named expressions; in TRICC terms each ``define`` is a
calculate. Only expression and function definitions are read: ``library`` / ``using`` /
``include`` / ``context`` / ``parameter`` / terminology declarations are ignored. Each body
goes through the same CQL -> operation converter as expressions written in drawio or yaml,
so references to questions, other calculates and other defines work the same way.

A ``function`` is recorded as a :class:`FunctionSignature` (``project.function_signatures``)
so outputs can type a call TRICC passes through as written (a ``native`` operation):

    /*
    @description: Weight-for-age z-score from the WHO tables
    @retrieve: false
    */
    define function Zscore(chart String, sex String, value Decimal) returns FHIR.decimal: external

* ``external`` (CQL: implemented elsewhere) is a declaration only: never written into a
  generated library. A function with a body is a calculate function
  (feature/20261125-calculate-functions.md): ``IsAdult(age_estimated)`` binds its parameters
  and is expanded where it is called; a parameter is used in the body by its name.
* ``@param.<name>: fallback=<concept> retrievals=#code …`` (one tag per parameter) says where a
  left-out argument comes from: the latest value of the fallback concept, else the argument of
  an earlier call, else the first listed retrieval.
* The calculate dictionary may describe the same function (a concept with
  ``function-parameter`` extensions, and optionally a ``function-body`` one): both are one
  function (:func:`link_functions`).
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
from typing import Any, Dict, List, Optional, Tuple

from antlr4 import CommonTokenStream, InputStream
from antlr4.error.ErrorListener import ErrorListener

from tricc_oo.converters.call_binding import CallError, CallParam
from tricc_oo.converters.cql.cqlLexer import cqlLexer
from tricc_oo.converters.cql.cqlParser import cqlParser
from tricc_oo.converters.cql.tricc_cqlLexer import tricc_cqlLexer
from tricc_oo.converters.cql.tricc_cqlParser import tricc_cqlParser
from tricc_oo.converters.lang import error_code, lang_version
from tricc_oo.converters.utils import generate_id
from tricc_oo.models.base import TriccNodeType
from tricc_oo.models.calculate import TriccNodeCalculate

logger = logging.getLogger("default")

_NAME_OK = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")
_TAG = re.compile(r"^@(?P<name>[A-Za-z_][A-Za-z0-9_.-]*)\s*:?\s*(?P<value>.*)$")
_BOOLEAN_TAGS = ("retrieve",)
#: the dialect tag in the comment that opens a library: ``@dialect: tricc-cql@1.0.0``
_DIALECT = re.compile(r"^\s*/\*(?P<body>.*?)\*/", re.S)
_DIALECT_TAG = re.compile(
    r"@dialect\s*:?\s*(?P<name>[A-Za-z0-9_.-]+?)(?:@(?P<version>[0-9][0-9A-Za-z.+-]*))?\s*$", re.M
)
#: dialect name of the TRICC profile
TRICC_DIALECT = "tricc-cql"

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


#: calculate dictionary: one extension per parameter (``name``, ``type``, ``fallback`` Coding,
#: ``retrieval`` code, repeated) and the body (``valueExpression``, ``text/cql``)
FUNCTION_PARAMETER_URL = "http://tricc.org/fhir/StructureDefinition/function-parameter"
FUNCTION_BODY_URL = "http://tricc.org/fhir/StructureDefinition/function-body"
SOURCE_DICTIONARY = "dictionary"
SOURCE_LIBRARY = "library"

E_FUNCTION_TWICE = "E_FUNCTION_TWICE"
E_FUNCTION_SIGNATURE_MISMATCH = "E_FUNCTION_SIGNATURE_MISMATCH"
E_PARAM_TAG_UNKNOWN = "E_PARAM_TAG_UNKNOWN"

#: a function parameter: name, type, fallback concept, listed retrievals
FunctionParam = CallParam

# TRICC data type (dictionary ``dataType``) -> FHIR data type
_DATA_TYPE_TO_FHIR = {
    "boolean": "boolean",
    "integer": "integer",
    "decimal": "decimal",
    "quantity": "decimal",
    "date": "date",
    "datetime": "dateTime",
    "string": "string",
    "text": "string",
    "coded": "string",
}


def fhir_type_of_cql_type(type_specifier: str) -> Optional[str]:
    """FHIR data type for a CQL type specifier, None when not a supported value type."""
    return CQL_TO_FHIR_TYPE.get(type_specifier.rsplit(".", 1)[-1].lower())


def _same_type(a: Optional[str], b: Optional[str]) -> bool:
    if not a or not b:
        return True
    fa = fhir_type_of_cql_type(a) or _DATA_TYPE_TO_FHIR.get(a.lower()) or a.lower()
    fb = fhir_type_of_cql_type(b) or _DATA_TYPE_TO_FHIR.get(b.lower()) or b.lower()
    return fa == fb


class FunctionError(CallError):
    """A function definition or call that is not valid (``E_FUNCTION_*``, ``E_PARAM_*``)."""


@dataclass(frozen=True)
class FunctionSignature:
    """A function a project library or the calculate dictionary declares (module docstring)."""

    name: str
    return_type: str  # FHIR data type
    # (name, type as written) per argument
    arguments: Tuple[Tuple[str, str], ...] = ()
    # CQL documentation tags, ``@name: value``, values as written
    tags: Dict[str, str] = field(default_factory=dict)
    # declaration only: never written into a generated library
    external: bool = True
    source: str = "<library>"
    # the body (parameters are ``TriccParameterReference``), None for a declaration
    body: Any = None
    # the body as written (CQL), for a generated library
    body_text: Optional[str] = None
    # per parameter: type, fallback concept and listed retrievals
    params: Tuple[CallParam, ...] = ()
    # where it is defined: ``dictionary`` and/or ``library``
    sources: Tuple[str, ...] = (SOURCE_LIBRARY,)

    @property
    def retrieve(self) -> bool:
        """True unless ``@retrieve: false``: the value may read recorded data (never a constant)."""
        return self.tags.get("retrieve", "true").lower() != "false"

    @property
    def param_names(self) -> List[str]:
        """The parameter names, in order."""
        return [p.name for p in self.params] or [a for a, _ in self.arguments]

    @property
    def call_params(self) -> List[CallParam]:
        """The parameters with their metadata (a bare one when only the arguments are known)."""
        return list(self.params) or [CallParam(name=a, type=t) for a, t in self.arguments]


class _RaiseOnSyntaxError(ErrorListener):
    def __init__(self, source: str):
        super().__init__()
        self.source = source

    def syntaxError(self, recognizer, offendingSymbol, line, column, msg, e):
        raise ValueError(f"{self.source}: not valid CQL at line {line}:{column}: {msg}")


def library_dialect(text: str, source: str = "<library>") -> Optional[Tuple[str, Optional[str]]]:
    """The dialect a library declares in its opening comment, else None (standard CQL).

    Args:
        text: The library.
        source: Its file, for messages.

    Returns:
        ``(name, version)``; the version may be None.

    Raises:
        ValueError: ``E_CQL_DIALECT`` for an unknown dialect or a TRICC major version other than
            the one of ``tricc_oo/lang/VERSION``.
    """
    opening = _DIALECT.match(text)
    if not opening:
        return None
    tag = _DIALECT_TAG.search(opening.group("body"))
    if not tag:
        return None
    name, version = tag.group("name"), tag.group("version")
    if name != TRICC_DIALECT:
        raise ValueError(f"{error_code('dialect')}: {source}: unknown CQL dialect {name!r}; use {TRICC_DIALECT}")
    if version and version.split(".")[0] != lang_version().split(".")[0]:
        raise ValueError(
            f"{error_code('dialect')}: {source}: {TRICC_DIALECT}@{version} is not supported by this TRICC "
            f"({TRICC_DIALECT}@{lang_version()})"
        )
    return name, version


class _ParsedLibrary:
    """One library parsed with the CQL grammar: its defines and functions, in file order.

    Standard CQL by default; the TRICC profile when the library declares ``tricc-cql``.
    """

    def __init__(self, text: str, source: str):
        self.text = text
        self.source = source
        self.dialect = library_dialect(text, source)
        lexer_class, parser_class = (tricc_cqlLexer, tricc_cqlParser) if self.dialect else (cqlLexer, cqlParser)
        self.lexer_class = lexer_class
        self.input = InputStream(text)
        lexer = lexer_class(self.input)
        lexer.removeErrorListeners()
        lexer.addErrorListener(_RaiseOnSyntaxError(source))
        self.tokens = CommonTokenStream(lexer)
        parser = parser_class(self.tokens)
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
            if token.type == self.lexer_class.WS:
                continue
            if token.type == self.lexer_class.COMMENT:
                comment = token.text
            break
        if comment is None:
            return {}
        return _parse_tags(comment[2:-2], name, self.source)


def _is_function(ctx) -> bool:
    """A function definition, from either grammar (standard CQL or the TRICC profile)."""
    return type(ctx).__name__ == "FunctionDefinitionContext"


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


_PARAM_TAG_KEYS = ("fallback", "retrievals")


def parse_param_tag(value: str, function: str, param: str, source: str) -> Tuple[Optional[str], Tuple[str, ...]]:
    """``fallback=<concept> retrievals=#a #b`` -> ``(fallback, retrievals)``.

    A ``system."code"`` fallback keeps the code (#103). The value of ``retrievals`` runs to the
    next ``key=``.

    Raises:
        FunctionError: ``E_PARAM_TAG_UNKNOWN``, a key other than ``fallback`` / ``retrievals``.
    """
    fallback = None
    retrievals: List[str] = []
    key = None
    for token in value.replace(",", " ").split():
        if "=" in token:
            key, _, token = token.partition("=")
            key = key.strip().lower()
            if key not in _PARAM_TAG_KEYS:
                raise FunctionError(
                    E_PARAM_TAG_UNKNOWN,
                    f"{source}: @param.{param} on {function!r}: unknown key {key!r} (use fallback=, retrievals=)",
                )
            if not token:
                continue
        if key == "fallback":
            code = token.rsplit(".", 1)[-1] if token.endswith('"') else token
            fallback = code.strip('"')
        elif key == "retrievals":
            retrievals.append(token)
        else:
            raise FunctionError(
                E_PARAM_TAG_UNKNOWN, f"{source}: @param.{param} on {function!r}: {token!r} has no key (fallback=…)"
            )
    return fallback, tuple(retrievals)


def _params_from_tags(name: str, arguments, tags: Dict[str, str], source: str) -> Tuple[CallParam, ...]:
    by_name = {a.lower(): (a, t) for a, t in arguments}
    meta: Dict[str, Tuple[Optional[str], Tuple[str, ...]]] = {}
    for tag, value in tags.items():
        if not tag.startswith("param."):
            continue
        param = tag[len("param."):]
        if param not in by_name:
            raise FunctionError(
                E_PARAM_TAG_UNKNOWN,
                f"{source}: @{tag} on {name!r}: no parameter {param!r} ({', '.join(a for a, _ in arguments)})",
            )
        meta[param] = parse_param_tag(value, name, param, source)
    return tuple(
        CallParam(name=a, type=t, fallback=meta.get(a.lower(), (None, ()))[0],
                  retrievals=meta.get(a.lower(), (None, ()))[1])
        for a, t in arguments
    )


def _function_signature(library: _ParsedLibrary, ctx) -> FunctionSignature:
    name = _identifier(ctx.identifierOrFunctionIdentifier())
    source = library.source
    if ctx.typeSpecifier() is None:
        raise ValueError(f"{source}: function {name!r} must declare its type with 'returns'")
    returns = library.source_text(ctx.typeSpecifier())
    return_type = fhir_type_of_cql_type(returns)
    if return_type is None:
        raise ValueError(
            f"{source}: function {name!r} returns {returns!r}; "
            f"use one of {', '.join(sorted(set(CQL_TO_FHIR_TYPE.values())))}"
        )
    arguments = tuple(
        (_identifier(operand.referentialIdentifier()), library.source_text(operand.typeSpecifier()))
        for operand in ctx.operandDefinition()
    )
    tags = library.leading_tags(ctx, name)
    body = body_text = None
    if ctx.functionBody() is not None:
        body_text = library.source_text(ctx.functionBody().expression())
        body = parse_function_body(body_text, [a for a, _ in arguments], f"{source}: function {name!r}")
    return FunctionSignature(
        name=name,
        return_type=return_type,
        arguments=arguments,
        tags=tags,
        external=body is None,
        source=source,
        body=body,
        body_text=body_text,
        params=_params_from_tags(name, arguments, tags, source),
        sources=(SOURCE_LIBRARY,),
    )


def parse_function_body(text: str, parameters: List[str], context: str) -> Any:
    """A function body as an operation, its parameters as ``TriccParameterReference``.

    Raises:
        ValueError: The body is not valid CQL.
    """
    from tricc_oo.converters.cql_to_operation import transform_cql_to_operation

    body = transform_cql_to_operation(text, context=context, parameters=parameters)
    if body is None:
        raise ValueError(f"{context}: the body is not valid CQL: {text}")
    return body


def parse_cql_library_functions(text: str, source: str = "<library>") -> Dict[str, FunctionSignature]:
    """Every function of a library, by name, in file order."""
    library = _ParsedLibrary(text, source)
    functions: Dict[str, FunctionSignature] = {}
    for ctx in library.statements():
        if not _is_function(ctx):
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
        if _is_function(ctx):
            continue  # parse_cql_library_functions
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


# ---------------------------------------------------------------- calculate dictionary functions


def _ext_value(extension, *attrs):
    for attr in attrs:
        value = getattr(extension, attr, None)
        if value not in (None, ""):
            return value
    return None


def _dictionary_param(extension, function: str, source: str) -> CallParam:
    name = ptype = fallback = None
    retrievals: List[str] = []
    for sub in getattr(extension, "extension", None) or []:
        url = getattr(sub, "url", None)
        if url == "name":
            name = _ext_value(sub, "valueString", "valueCode")
        elif url == "type":
            ptype = _ext_value(sub, "valueCode", "valueString")
        elif url == "fallback":
            coding = _ext_value(sub, "valueCoding")
            fallback = getattr(coding, "code", None) if coding is not None else _ext_value(sub, "valueCode")
        elif url in ("retrieval", "retrievals"):
            code = _ext_value(sub, "valueCode", "valueString")
            if code:
                retrievals.extend(str(code).split())
        else:
            raise FunctionError(
                E_PARAM_TAG_UNKNOWN, f"{source}: function {function!r}: unknown parameter field {url!r}"
            )
    if not name:
        raise FunctionError(E_FUNCTION_SIGNATURE_MISMATCH, f"{source}: function {function!r}: a parameter has no name")
    return CallParam(name=str(name), type=ptype, fallback=fallback, retrievals=tuple(retrievals))


def read_dictionary_functions(project) -> Dict[str, FunctionSignature]:
    """The functions the calculate dictionary describes, by name.

    A concept is a function when it has ``function-parameter`` or ``function-body``
    extensions; its ``dataType`` property is the return type.

    Raises:
        FunctionError: A parameter extension that is not valid.
        ValueError: A body that is not valid CQL.
    """
    from tricc_oo.strategies.input.param_build import calculate_code_system_key

    systems = getattr(project, "code_systems", None) or {}
    key = calculate_code_system_key(systems, getattr(project, "calculate_code_system", None))
    code_system = systems.get(key)
    functions: Dict[str, FunctionSignature] = {}
    for concept in getattr(code_system, "concept", None) or []:
        extensions = getattr(concept, "extension", None) or []
        params = [e for e in extensions if getattr(e, "url", None) == FUNCTION_PARAMETER_URL]
        bodies = [e for e in extensions if getattr(e, "url", None) == FUNCTION_BODY_URL]
        if not params and not bodies:
            continue
        name = concept.code
        source = f"{key} {name}"
        call_params = tuple(_dictionary_param(e, name, source) for e in params)
        body = body_text = None
        if bodies:
            expression = getattr(bodies[0], "valueExpression", None)
            body_text = getattr(expression, "expression", None)
            if body_text:
                body = parse_function_body(body_text, [p.name for p in call_params], f"{source}: body")
        data_type = None
        for prop in concept.property or []:
            if getattr(prop, "code", None) == "dataType":
                data_type = _ext_value(prop, "valueCode", "valueString")
        functions[name] = FunctionSignature(
            name=name,
            return_type=_DATA_TYPE_TO_FHIR.get(str(data_type or "").lower(), "string"),
            arguments=tuple((p.name, p.type or "") for p in call_params),
            external=body is None,
            source=source,
            body=body,
            body_text=body_text,
            params=call_params,
            sources=(SOURCE_DICTIONARY,),
        )
    return functions


def _merge_param(name: str, lib: CallParam, dic: CallParam) -> CallParam:
    if lib.name.lower() != dic.name.lower() or not _same_type(lib.type, dic.type):
        raise FunctionError(
            E_FUNCTION_SIGNATURE_MISMATCH,
            f"function {name!r}: parameter {lib.name} {lib.type or ''} (library) differs from "
            f"{dic.name} {dic.type or ''} (dictionary)",
        )
    for attr in ("fallback", "retrievals"):
        a, b = getattr(lib, attr), getattr(dic, attr)
        if a and b and a != b:
            raise FunctionError(
                E_FUNCTION_SIGNATURE_MISMATCH,
                f"function {name!r}: parameter {lib.name} has {attr} {a!r} in the library and {b!r} in the dictionary",
            )
    return CallParam(
        name=lib.name,
        type=lib.type or dic.type,
        fallback=lib.fallback or dic.fallback,
        retrievals=lib.retrievals or dic.retrievals,
    )


def link_functions(
    library: Dict[str, FunctionSignature], dictionary: Dict[str, FunctionSignature]
) -> Dict[str, FunctionSignature]:
    """One function per name: a library function and a dictionary concept with the same code
    are merged (parameters and their fallbacks from either, the body from the one that has it).

    Raises:
        FunctionError: ``E_FUNCTION_TWICE`` (both have a body), ``E_FUNCTION_SIGNATURE_MISMATCH``
            (different parameters, or metadata given on both sides that disagree).
    """
    from dataclasses import replace

    linked = dict(library)
    by_lower = {n.lower(): n for n in library}
    for name, dic in dictionary.items():
        lib_name = by_lower.get(name.lower())
        if lib_name is None:
            linked[name] = dic
            continue
        lib = library[lib_name]
        if lib.body is not None and dic.body is not None:
            raise FunctionError(
                E_FUNCTION_TWICE, f"function {name!r} has a body in {lib.source} and in the dictionary ({dic.source})"
            )
        lib_params, dic_params = lib.call_params, list(dic.params)
        if dic_params and len(lib_params) != len(dic_params):
            raise FunctionError(
                E_FUNCTION_SIGNATURE_MISMATCH,
                f"function {name!r}: {len(lib_params)} parameters in the library, {len(dic_params)} in the dictionary",
            )
        params = tuple(_merge_param(name, a, b) for a, b in zip(lib_params, dic_params)) if dic_params else tuple(
            lib_params
        )
        has_body = lib.body if lib.body is not None else dic.body
        linked[lib_name] = replace(
            lib,
            params=params,
            body=has_body,
            body_text=lib.body_text if lib.body is not None else dic.body_text,
            external=has_body is None,
            sources=(SOURCE_DICTIONARY, SOURCE_LIBRARY),
        )
    return linked
