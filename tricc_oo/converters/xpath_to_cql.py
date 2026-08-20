"""Translate XLSForm / XPath expressions to CQL.

Pairs with ``cql_to_operation.py`` but in the opposite direction: it consumes
an XLSForm expression (as found in ``calculation``, ``relevance``,
``constraint`` columns) parsed by the ANTLR ``xlsform`` grammar, and emits an
equivalent CQL expression string.

The visitor is intentionally tolerant: unknown functions are emitted verbatim
(PascalCase name + arguments) so the output can still be inspected and
manually corrected by a user when a mapping is missing.
"""

from antlr4 import CommonTokenStream, InputStream
from antlr4.error.ErrorListener import ErrorListener

from tricc_oo.converters.xlsform.g4.xlsformLexer import xlsformLexer
from tricc_oo.converters.xlsform.g4.xlsformParser import xlsformParser
from tricc_oo.converters.xlsform.g4.xlsformVisitor import xlsformVisitor

import logging

logger = logging.getLogger("default")


# XPath / XLSForm function name -> CQL function name.
# Anything not in this map is emitted verbatim (PascalCased) so the output is
# still a syntactically reasonable CQL expression the user can inspect.
FUNCTION_MAP = {
    # boolean / control
    "true": "true",
    "false": "false",
    "not": "not",
    "coalesce": "Coalesce",
    "if": "If",
    # selection helpers (handled specially in visitFunctionCall)
    "selected": None,
    "selected-at": None,
    "count-selected": None,
    "jr:choice-name": GetChoiceName,
    # math / casting
    "int": "Integer",
    "number": "ToDecimal",
    "decimal-date-time": "DateTimeToDecimal",
    "round": "Round",
    "abs": "Abs",
    "min": "Min",
    "max": "Max",
    "sum": "Sum",
    "count": "Count",
    "concat": "Concatenate",
    # strings
    "string-length": "Length",
    "normalize-space": "NormalizeSpace",
    "substring": "Substring",
    "substr": "Substring",
    "contains": "Contains",
    "starts-with": "StartsWith",
    "ends-with": "EndsWith",
    "upper-case": "Upper",
    "lower-case": "Lower",
    # regex
    "regex": "Matches",
    # date / time
    "today": "Today",
    "now": "Now",
    "date": "ToDate",
    "format-date": "FormatDate",
    # custom / tricc specific
    "zscore": "Zscore",
    "izscore": "Izscore",
    "AgeInYears": "AgeInYears",
    "AgeInMonths": "AgeInMonths",
    "AgeInDays": "AgeInDays",
}


def _pascal(name):
    # convert kebab or snake case to PascalCase so unknown functions still
    # look reasonable in the generated CQL.
    parts = []
    for chunk in name.replace(":", "_").replace("-", "_").split("_"):
        if chunk:
            parts.append(chunk[:1].upper() + chunk[1:])
    return "".join(parts) or name


def _strip_literal(text):
    # xpath literals can be single- or double-quoted, CQL uses single quotes.
    if not text:
        return text
    if (text[0] == text[-1]) and text[0] in ("'", '"'):
        inner = text[1:-1]
    else:
        inner = text
    # escape any lone single quotes for CQL.
    return "'" + inner.replace("'", "\\'") + "'"


class XPathToCqlVisitor(xlsformVisitor):
    """Visitor that translates an xlsform/xpath parse tree to CQL text."""

    def __init__(self):
        self.warnings = []

    # ---- entry points -----------------------------------------------------

    def visitMain(self, ctx):
        return self.visit(ctx.expr())

    def visitExpr(self, ctx):
        return self.visit(ctx.getChild(0))

    # ---- boolean combinators ---------------------------------------------

    def _binary_join(self, ctx, sub_rule, joiner):
        parts = [self.visit(c) for c in getattr(ctx, sub_rule)()]
        parts = [p for p in parts if p not in (None, "")]
        if len(parts) == 1:
            return parts[0]
        return f" {joiner} ".join(parts)

    def visitOrExpr(self, ctx):
        return self._binary_join(ctx, "andExpr", "or")

    def visitAndExpr(self, ctx):
        return self._binary_join(ctx, "equalityExpr", "and")

    # ---- comparisons ------------------------------------------------------

    def _walk_binary(self, ctx, child_rule, op_tokens):
        children = list(ctx.getChildren())
        if len(children) == 1:
            return self.visit(children[0])
        out = self.visit(children[0])
        i = 1
        while i < len(children):
            op_text = children[i].getText()
            rhs = self.visit(children[i + 1])
            cql_op = op_tokens.get(op_text, op_text)
            out = f"{out} {cql_op} {rhs}"
            i += 2
        return out

    def visitEqualityExpr(self, ctx):
        return self._walk_binary(ctx, "relationalExpr", {"=": "=", "!=": "!="})

    def visitRelationalExpr(self, ctx):
        return self._walk_binary(
            ctx,
            "additiveExpr",
            {"<": "<", "<=": "<=", ">": ">", ">=": ">="},
        )

    def visitAdditiveExpr(self, ctx):
        return self._walk_binary(ctx, "multiplicativeExpr", {"+": "+", "-": "-"})

    def visitMultiplicativeExpr(self, ctx):
        return self._walk_binary(
            ctx,
            "unaryExprNoRoot",
            {"*": "*", "div": "/", "mod": "mod"},
        )

    # ---- unary ------------------------------------------------------------

    def visitUnaryExprNoRoot(self, ctx):
        children = list(ctx.getChildren())
        prefix = ""
        idx = 0
        while idx < len(children) and children[idx].getText() == "-":
            prefix += "-"
            idx += 1
        body = self.visit(children[idx]) if idx < len(children) else ""
        return f"{prefix}{body}" if prefix else body

    # ---- union / path -----------------------------------------------------

    def visitUnionExprNoRoot(self, ctx):
        # xlsform rarely uses the full xpath path/union machinery, so we just
        # render it with the left part and warn if a '|' shows up.
        if ctx.getChildCount() == 1:
            return self.visit(ctx.getChild(0))
        pieces = [self.visit(c) for c in ctx.getChildren() if c.getText() != "|"]
        self.warnings.append("xpath union ('|') not representable in CQL; joined as 'or'")
        return " or ".join(p for p in pieces if p)

    def visitPathExprNoRoot(self, ctx):
        return self.visit(ctx.getChild(0))

    def visitFilterExpr(self, ctx):
        # primary expr (+ predicates); predicates are modeled as [ expr ], we
        # render them as `[ condition ]` similar to CQL query filter syntax.
        base = self.visit(ctx.primaryExpr())
        predicates = ctx.predicate() or []
        for p in predicates:
            base = f"{base}[{self.visit(p.expr())}]"
        return base

    def visitLocationPath(self, ctx):
        return ctx.getText()

    def visitAbsoluteLocationPathNoroot(self, ctx):
        return ctx.getText()

    def visitRelativeLocationPath(self, ctx):
        return ctx.getText()

    def visitAbbreviatedStep(self, ctx):
        # "." or ".." in xpath -> in CQL there's no exact equivalent, keep as-is
        return ctx.getText()

    # ---- primary / literals / references ---------------------------------

    def visitPrimaryExpr(self, ctx):
        if ctx.variableReference():
            return self.visit(ctx.variableReference())
        if ctx.functionCall():
            return self.visit(ctx.functionCall())
        if ctx.Literal():
            return _strip_literal(ctx.Literal().getText())
        if ctx.Number():
            return ctx.Number().getText()
        if ctx.expr():
            return f"({self.visit(ctx.expr())})"
        return ctx.getText()

    def visitStandardReference(self, ctx):
        # $qname -> "qname"
        name = ctx.qName().getText() if ctx.qName() else ctx.getText()
        return f'"{name}"'

    def visitNternalReference(self, ctx):
        # ${NCName} -> "NCName"
        name = ctx.NCName().getText() if ctx.NCName() else ctx.getText().strip("${}")
        return f'"{name}"'

    def visitQName(self, ctx):
        return ctx.getText()

    def visitNCName(self, ctx):
        return ctx.getText()

    # ---- function calls ---------------------------------------------------

    def visitFunctionCall(self, ctx):
        fname = ctx.functionName().getText()
        args = [self.visit(e) for e in (ctx.expr() or [])]

        # --- special forms -------------------------------------------------
        if fname == "selected" and len(args) == 2:
            return f"{args[1]} in {args[0]}"
        if fname == "selected-at" and len(args) == 2:
            # selected-at(${field}, n) has no direct equivalent; closest is
            # Split(field, ' ')[n]. Expose it explicitly.
            return f"Split({args[0]}, ' ')[{args[1]}]"
        if fname == "count-selected" and len(args) == 1:
            return f"Count(Split({args[0]}, ' '))"
        if fname == "not" and len(args) == 1:
            return f"not {args[0]}"
        if fname == "true" and not args:
            return "true"
        if fname == "false" and not args:
            return "false"
        if fname == "if" and len(args) == 3:
            return f"if {args[0]} then {args[1]} else {args[2]}"
        if fname == "coalesce":
            return f"Coalesce({', '.join(args)})"
        if fname in ("int", "number"):
            cast_type = "Integer" if fname == "int" else "Decimal"
            if len(args) == 1:
                return f"({args[0]} as {cast_type})"

        # --- generic mapping ----------------------------------------------
        cql_name = FUNCTION_MAP.get(fname)
        if cql_name is None:
            cql_name = _pascal(fname)
            self.warnings.append(
                f"no explicit CQL mapping for xpath function '{fname}', emitted as '{cql_name}'"
            )
        return f"{cql_name}({', '.join(args)})"

    # ---- fall-through -----------------------------------------------------

    def aggregateResult(self, aggregate, nextResult):
        if aggregate is None:
            return nextResult
        if nextResult is None:
            return aggregate
        return f"{aggregate}{nextResult}" if isinstance(aggregate, str) else nextResult


class XPathErrorListener(ErrorListener):
    def __init__(self, context=None):
        super().__init__()
        self.context = context
        self.errors = []

    def syntaxError(self, recognizer, offendingSymbol, line, column, msg, e):
        prefix = f"{self.context}\n" if self.context else ""
        self.errors.append(f"{prefix}Line {line}:{column} - {msg}")


def transform_xpath_to_cql(xpath_input, context=None):
    """Parse an XLSForm/XPath expression and return the equivalent CQL string.

    Returns ``None`` if the input cannot be parsed.
    """
    if xpath_input is None:
        return None
    text = xpath_input.strip()
    if not text:
        return ""

    input_stream = InputStream(text)
    lexer = xlsformLexer(input_stream)
    stream = CommonTokenStream(lexer)
    parser = xlsformParser(stream)

    parser.removeErrorListeners()
    lexer.removeErrorListeners()
    error_listener = XPathErrorListener(context)
    parser.addErrorListener(error_listener)
    lexer.addErrorListener(error_listener)

    tree = parser.main()

    if error_listener.errors:
        for err in error_listener.errors:
            logger.warning(f"xpath grammar error: {err}\n in: {xpath_input}")
        return None

    visitor = XPathToCqlVisitor()
    result = visitor.visit(tree)
    if visitor.warnings:
        logger.debug(f"while visiting xpath:\n{xpath_input}")
        for w in visitor.warnings:
            logger.debug(w)
    return result
