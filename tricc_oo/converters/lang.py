"""The shared expression-language package ``tricc_oo/lang/`` (feature/20261125-expression-languages.md).

Reads the package's data files (``VERSION``, ``errors.json``, ``functions.json``,
``meaning.json``) and parses CQL expressions with the TRICC profile (``tricc_cql.g4``), naming a
construct outside the profile with the message of ``errors.json``.
"""

from __future__ import annotations

import functools
import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from antlr4 import CommonTokenStream, InputStream, Token
from antlr4.error.ErrorListener import ErrorListener

from tricc_oo.converters.cql.tricc_cqlLexer import tricc_cqlLexer
from tricc_oo.converters.cql.tricc_cqlParser import tricc_cqlParser

#: the package folder, shipped in the wheel (``package-data``)
LANG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "lang")


@functools.lru_cache(maxsize=1)
def lang_version() -> str:
    """The package version (``tricc_oo/lang/VERSION``)."""
    with open(os.path.join(LANG_DIR, "VERSION"), encoding="utf-8") as file:
        return file.read().strip()


@functools.lru_cache(maxsize=None)
def load_lang_json(name: str) -> Dict[str, Any]:
    """A JSON file of the package, e.g. ``errors.json`` or ``feel/cells.json``.

    Args:
        name: Path relative to ``tricc_oo/lang/``.

    Returns:
        The parsed JSON object.
    """
    with open(os.path.join(LANG_DIR, name), encoding="utf-8") as file:
        return json.load(file)


def error_code(kind: str) -> str:
    """The code of an error kind of ``errors.json`` (``syntax``, ``profile``, ``unknown_function``, …)."""
    return load_lang_json("errors.json")["codes"][kind]


@dataclass(frozen=True)
class CqlSyntaxError:
    """A CQL text that does not parse.

    ``line`` is 1-based, ``column`` 0-based, both in the text itself. ``construct`` names the
    construct outside the profile (``query``, ``indexer``, …), None for a plain syntax error.
    """

    code: str
    message: str
    line: int
    column: int
    construct: Optional[str] = None

    def __str__(self) -> str:
        return f"Line {self.line}:{self.column} - {self.code}: {self.message}"


def _symbolic_name(token: Token, names: Sequence[str]) -> Optional[str]:
    return names[token.type] if 0 <= token.type < len(names) else None


def profile_construct(tokens: List[Token], names: Sequence[str]) -> Optional[Tuple[Dict[str, Any], Token]]:
    """The first construct of ``errors.json`` the tokens use, with the token that shows it.

    Args:
        tokens: The default-channel tokens of the text, in order (EOF excluded).
        names: The lexer's symbolic token names, by token type.

    Returns:
        ``(construct entry, token)``, or None when no construct matches.
    """
    data = load_lang_json("errors.json")
    operand_types = set(data["operand_types"])
    operand_texts = set(data["operand_texts"])
    previous = None
    for token in tokens:
        name = _symbolic_name(token, names)
        for construct in data["constructs"]:
            if token.text not in construct.get("texts", ()) and name not in construct.get("types", ()):
                continue
            after = construct.get("after")
            previous_name = _symbolic_name(previous, names) if previous is not None else None
            if after == "operand" and not (
                previous is not None and (previous_name in operand_types or previous.text in operand_texts)
            ):
                continue
            if after == "number" and previous_name != "NUMBER":
                continue
            return construct, token
        previous = token
    return None


class _CollectErrors(ErrorListener):
    def __init__(self) -> None:
        super().__init__()
        self.errors: List[Tuple[int, int, str]] = []

    def syntaxError(self, recognizer, offendingSymbol, line, column, msg, e):  # noqa: N802 (ANTLR API)
        self.errors.append((line, column, msg))


def normalise_cql(text: str) -> str:
    """The text as the lexer reads it: the typographic minus ``−`` becomes ``-``."""
    return text.replace("−", "-")


def parse_cql_expression(text: str) -> Tuple[Optional[Any], List[CqlSyntaxError]]:
    """Parse one expression with the TRICC profile (``triccExpression``).

    Args:
        text: The expression (placeholders may be left unrendered).

    Returns:
        ``(tree, errors)``: the parse tree when there is no error, else None and the errors; a
        construct outside the profile gives one ``E_CQL_PROFILE`` error at its first token.
    """
    lexer = tricc_cqlLexer(InputStream(normalise_cql(text)))
    listener = _CollectErrors()
    lexer.removeErrorListeners()
    lexer.addErrorListener(listener)
    stream = CommonTokenStream(lexer)
    parser = tricc_cqlParser(stream)
    parser.removeErrorListeners()
    parser.addErrorListener(listener)
    tree = parser.triccExpression()
    if not listener.errors:
        return tree, []
    tokens = [t for t in stream.tokens if t.channel == Token.DEFAULT_CHANNEL and t.type != Token.EOF]
    found = profile_construct(tokens, tricc_cqlParser.symbolicNames)
    if found is not None:
        construct, token = found
        message = construct["message"]
        return None, [CqlSyntaxError(error_code("profile"), message, token.line, token.column, construct["construct"])]
    return None, [CqlSyntaxError(error_code("syntax"), msg, line, column) for line, column, msg in listener.errors]
