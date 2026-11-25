"""Decision-table cells parsed with the shared FEEL grammar (feature/20261125-expression-languages.md §1.5).

The lexer is the upstream KIE ``FEEL_1_1.g4`` (through ``tricc_feel.g4``, which adds TRICC's
``'text'``), the parser ``TriccFeelParser.g4``; both live in ``tricc_oo/lang/feel/`` and are
generated into ``tricc_oo/converters/feel/``. The column type checks are in
:func:`tricc_oo.models.decision_table.parse_cell`.
"""

from __future__ import annotations

import re
from typing import Any, List, Optional, Tuple, Union

from antlr4 import CommonTokenStream, InputStream, Token
from antlr4.error.ErrorListener import ErrorListener

from tricc_oo.converters.feel.tricc_feelLexer import tricc_feelLexer
from tricc_oo.converters.feel.TriccFeelParser import TriccFeelParser

_DECIMAL = re.compile(r"^-?\d+(?:\.\d+)?$")


class _Collect(ErrorListener):
    def __init__(self) -> None:
        super().__init__()
        self.errors: List[Tuple[int, str]] = []
        self.lexer_error = False

    def syntaxError(self, recognizer, offendingSymbol, line, column, msg, e):  # noqa: N802 (ANTLR API)
        if isinstance(recognizer, tricc_feelLexer):
            self.lexer_error = True
        self.errors.append((column, msg))


def parse_cell_tree(cell: str) -> Tuple[Optional[Any], str]:
    """Parse an input cell (``cellRoot``).

    Args:
        cell: The cell text, stripped.

    Returns:
        ``(tree, "")`` when it parses; else ``(None, problem)``, ``problem`` naming a common
        mistake for the message: ``unclosed`` (quote or bracket), ``any_in_list`` (``1, -``),
        ``empty_item`` (``1,, 2``), ``range`` (a bracket that is not a range) or ``syntax``.
    """
    lexer = tricc_feelLexer(InputStream(cell))
    listener = _Collect()
    lexer.removeErrorListeners()
    lexer.addErrorListener(listener)
    stream = CommonTokenStream(lexer)
    parser = TriccFeelParser(stream)
    parser.removeErrorListeners()
    parser.addErrorListener(listener)
    tree = parser.cellRoot()
    if not listener.errors:
        return tree, ""
    tokens = [t for t in stream.tokens if t.type != Token.EOF]
    return None, _problem(tokens, listener.lexer_error)


def _problem(tokens: List[Token], lexer_error: bool) -> str:
    kinds = [t.type for t in tokens]
    opens = sum(k in (TriccFeelParser.LBRACK, TriccFeelParser.LPAREN) for k in kinds)
    closes = sum(k in (TriccFeelParser.RBRACK, TriccFeelParser.RPAREN) for k in kinds)
    if lexer_error or opens != closes or TriccFeelParser.QUOTE in kinds:
        return "unclosed"
    if TriccFeelParser.COMMA in kinds:
        for i, kind in enumerate(kinds):
            following = kinds[i + 1] if i + 1 < len(kinds) else None
            if kind == TriccFeelParser.COMMA and following in (TriccFeelParser.COMMA, None):
                return "empty_item"
            if kind == TriccFeelParser.SUB and following in (TriccFeelParser.COMMA, None):
                return "any_in_list"
    if kinds and kinds[0] in (TriccFeelParser.LBRACK, TriccFeelParser.LPAREN, TriccFeelParser.RBRACK):
        return "range"
    return "syntax"


def cell_value(text: str) -> Union[int, float, str, bool, None]:
    """The value of a ``cellValue``: a number, ``'text'`` / ``"text"`` or a boolean.

    Returns:
        The value, or None for a number the cell subset does not take (hex, ``1_000``, …).
    """
    if text in ("true", "false"):
        return text == "true"
    if text[:1] == "'":
        body = text[1:-1].replace("''", "'")
        return re.sub(r"\\(.)", r"\1", body)
    if text[:1] == '"':
        return re.sub(r"\\(.)", r"\1", text[1:-1])
    if not _DECIMAL.match(text):
        return None
    value = float(text)
    return int(value) if value.is_integer() and "." not in text else value
