import functools
import os
from typing import Dict

from antlr4.error.ErrorListener import ErrorListener
from antlr4 import CommonTokenStream, InputStream
from tricc_oo.converters.cql.cqlLexer import cqlLexer
from tricc_oo.converters.cql.cqlParser import cqlParser
from tricc_oo.converters.cql.tricc_cqlVisitor import tricc_cqlVisitor
from tricc_oo.converters.lang import LANG_DIR, load_lang_json, parse_cql_expression
from tricc_oo.converters.utils import clean_name, unquote_literal
from tricc_oo.converters.retrieval import RETRIEVE_FUNCTION, reject_quoted_implied, retrieve_reference
from tricc_oo.models.base import (
    TriccOperator,
    TriccOperation,
    TriccStatic,
    TriccReference,
    not_clean,
    or_join,
    and_join,
    string_join,
)
import logging

logger = logging.getLogger("default")

EXPRESSION = 0
STRING = 1
NUMBER = 2
ANY = 3


def _catalogue_function_map() -> Dict[str, TriccOperator]:
    """``{function name: TriccOperator}`` for the catalogue functions that parse to an operator."""
    return {
        entry["name"]: TriccOperator[entry["operator"]]
        for entry in load_lang_json("functions.json")["functions"]
        if entry.get("operator")
    }


#: CQL function name -> operator, from the catalogue ``tricc_oo/lang/functions.json``.
#: Decision tables (feature/20261123-decision-tables.md): ``DMN``, ``DMNFirst``, ``DMNList`` keep
#: their name as the first operand, so the expansion knows the policy or the alias; an alias
#: declared in tricc.yaml parses as NATIVE and is recognised by the expansion.
FUNCTION_MAP: Dict[str, TriccOperator] = _catalogue_function_map()

#: the catalogue, the shared list of CQL functions (tricc_oo is its authority; the frontend
#: pins a copy of ``tricc_oo/lang/``)
STORED_DATA_FUNCTIONS_FILE = os.path.join(LANG_DIR, "functions.json")


@functools.lru_cache(maxsize=1)
def stored_data_functions() -> Dict[str, str]:
    """The CQL functions that retrieve stored data, from the catalogue ``functions.json``.

    feature/20261111-block-params-and-start-node.md §18.5, §18.8 point 4.

    Returns:
        ``{function name: reads}``, ``reads`` being ``patient``, ``encounter``, ``history`` or
        ``context`` (catalogue entries with ``reads: none`` are left out).
    """
    return {
        entry["name"]: entry["reads"]
        for entry in load_lang_json("functions.json")["functions"]
        if entry.get("reads", "none") != "none"
    }


# Operators whose first argument is a concept code rather than a value expression.
CONCEPT_REF_FIRST_ARG = {
    TriccOperator.GET_REPEATED_VALUE,
}
# TODO
# Min
# Max
# Round
# this need to be done by contribution to DMN


def as_concept_reference(arg, function_name):
    """Coerce a concept-code argument into a TriccReference.

    A code written as a CQL string literal (``'weight'``) parses to a TriccStatic, which
    exposes no graph reference. Resolution would skip it and the code would be exported
    as a literal string instead of the collected value, so both spellings are normalized.

    Args:
        arg: Parsed first argument of the function invocation.
        function_name: Authored function name, for error reporting.

    Returns:
        A TriccReference when the argument is a concept code, otherwise ``arg`` unchanged.
    """
    if isinstance(arg, TriccReference):
        return arg
    if isinstance(arg, TriccStatic) and isinstance(arg.value, str):
        return TriccReference(arg.value)
    logger.error(f"{function_name} expects a concept code as first argument, got '{arg}'")
    return arg


def as_code_literal(value):
    """An identifier used as an answer code (``"rash"``) becomes the literal code."""
    if isinstance(value, TriccReference) and isinstance(value.value, str) and value.value != "$this":
        return TriccStatic(value=value.value)
    return value


class cqlToXlsFormVisitor(tricc_cqlVisitor):
    """CQL parse tree -> TriccOperation.

    Visits a ``tricc_cqlParser.triccExpression`` tree (expressions) or a ``cqlParser.library``
    tree (project libraries, ``transform_cql_lib_to_operations``): the profile keeps the
    upstream labels, so both trees have the same visitor methods.
    """

    def __init__(self):
        self.xlsform_rows = []
        self.errors = []

    def resolve_scv(self, arg):

        # TODO
        # look for the system, if not found fallback on default system
        # look for the code in the system
        # if no code or not found return None
        if arg.startswith('"') and arg.endswith('"'):
            # "#weight@P3M" is not an implied read: that is Retrieve('weight', 'P3M')
            reject_quoted_implied(arg[1:-1])
            return TriccReference(arg[1:-1])
        elif arg.lower() in ["true", "false"]:
            return TriccStatic(arg.lower() == "true")
        elif arg != "runner":
            # A bare identifier is text: a reference is a "quoted" CQL identifier, a text
            # literal 'quoted'; the legacy bare rhombus name is refused by its caller.
            return TriccStatic(arg)

        else:
            return "runner"

    def translate(self, arg, type=ANY):
        return self.resolve_scv(arg) or str(arg)

    def visitTriccExpression(self, ctx):
        return self.visit(ctx.expression())

    def visitPlaceholderTerm(self, ctx):
        # parameters are rendered before parsing (models/params.py); one left here is a bug
        self.errors.append(f"unrendered parameter {ctx.getText()}")
        return None

    def visitExpressionDefinition(self, ctx):
        identifier = ctx.identifier().getText()
        expression = self.visit(ctx.expression())
        self.xlsform_rows.append(
            {
                "type": "calculate",
                "name": clean_name(identifier[1:-1].lower()),
                "calculation": expression,
            }
        )
        return expression

    def visitIdentifier(self, arg):
        return self.translate(arg.getText(), 1)

    def visitChildren(self, ctx):
        return super().visitChildren(ctx)

    def aggregateResult(self, aggregate, nextResult):
        if aggregate is not None:
            if nextResult is None:
                return aggregate
            else:
                aggregate = aggregate if isinstance(aggregate, list) else [aggregate]
                return [*aggregate, nextResult]
        else:
            return nextResult

    def visitExpression(self, ctx):
        return self.visitChildren(ctx)

    def visitThisInvocation(self, ctx):
        return "$this"

    def visitBooleanLiteral(self, ctx):
        literal = ctx.getChild(0).getText()
        if literal == "true":
            return TriccStatic(True)
        elif literal == "false":
            return TriccStatic(False)
        else:
            return None

    def visitFunctionInvocation(self, ctx, operator=TriccOperator.NATIVE):
        if ctx.getChildCount() == 1:
            return self.visitFunctionInvocation(ctx.getChild(0))
        function_name = ctx.getChild(0).getText()
        if function_name in FUNCTION_MAP:
            operator = FUNCTION_MAP[function_name]
        # Add more function transformations here
        op = TriccOperation(operator)
        if operator == TriccOperator.NATIVE:
            op.reference = [
                function_name,
            ]
        elif operator == TriccOperator.DMN:
            op.reference = [TriccStatic(value=function_name)]
        args = ctx.paramList()
        if args:
            op.reference += [self.visit(arg) for arg in args.expression() if arg]
        if function_name == RETRIEVE_FUNCTION and operator == TriccOperator.NATIVE:
            # a retrieval: every argument is a code, never a form node
            # (feature/20261125-requires-and-implied-retrievals.md §3)
            return retrieve_reference(op.reference[1:])
        if operator in CONCEPT_REF_FIRST_ARG and op.reference:
            op.reference[0] = as_concept_reference(op.reference[0], function_name)
        if function_name in stored_data_functions():
            op.retrieves_stored_data = True
        op.update_origin()

        return op

    def __std_function(self, ctx, operator=TriccOperator.NATIVE):
        args = ctx.expressions
        if args:
            args = [self.visit(arg) for arg in ctx.expression() if arg]
        op = TriccOperation(operator)
        op.reference = [*args]
        op.update_origin()

    def visitParenthesizedTerm(self, ctx):
        return TriccOperation(TriccOperator.PARENTHESIS, [self.visitChildren(ctx)])

    def visitMemberInvocation(self, ctx):
        return self.visitChildren(ctx)

    def visitMembershipExpression(self, ctx):
        function_name = ctx.getChild(1).getText()
        return self._get_membership_expression(ctx, function_name)

    def _get_membership_expression(self, ctx, function_name):
        left = self.visit(ctx.expression(0))
        right = self.visit(ctx.expression(1))
        # The answer side is a code: "rash" in $this names the answer concept, not a
        # node to read (resolving it would find e.g. the option's own calculate).
        if function_name == "in":
            op = TriccOperation(TriccOperator.SELECTED)
            op.reference = [right, as_code_literal(left)]
        elif function_name == "contains":
            op = TriccOperation(TriccOperator.CONTAINS)
            op.reference = [left, as_code_literal(right)]
        return op

    def visitNegateMembershipExpression(self, ctx):
        function_name = ctx.getChild(2).getText()
        return not_clean(self._get_membership_expression(ctx, function_name))

    def visitBetweenExpression(self, ctx):
        ref = self.visit(ctx.expression(0))
        lower = self.visit(ctx.expression(1))
        higher = self.visit(ctx.expression(2))
        op = TriccOperation(TriccOperator.BETWEEN)
        op.reference = [ref, lower, higher]
        return op

    def visitBooleanExpression(self, ctx):
        expr = self.visit(ctx.expression())
        params = [c.getText() for c in list(ctx.getChildren())[2:]]
        op = TriccOperation(
            operator={
                "true": TriccOperator.ISTRUE,
                "false": TriccOperator.ISFALSE,
                "null": TriccOperator.ISNULL,
            }[params[-1]],
            reference=[expr],
        )

        if params[0] == "not":
            if isinstance(op, TriccStatic) and isinstance(op.value, str):
                logger.warning(f"not operator on a string {op.value}")
            op = not_clean(op)

        return op

    def visitExistenceExpression(self, ctx):
        expr = self.visit(ctx.expression())
        op = TriccOperation(TriccOperator.EXISTS)
        op.reference = [expr]
        return op

    def visitAndExpression(self, ctx):
        return self.__std_operator(TriccOperator.AND, ctx)

    def visitOrExpression(self, ctx):
        return self.__std_operator(TriccOperator.OR, ctx)

    def __std_operator(self, operator, ctx):
        if hasattr(ctx, "expression"):
            left = self.visit(ctx.expression(0))
            right = self.visit(ctx.expression(1))
        elif hasattr(ctx, "expressionTerm"):
            left = self.visit(ctx.expressionTerm(0))
            right = self.visit(ctx.expressionTerm(1))
        if operator == TriccOperator.AND:
            return and_join([left, right])
        elif operator == TriccOperator.OR:
            return or_join([left, right])
        elif operator == TriccOperator.CONCATENATE:
            left = "" if left is None else left
            right = "" if right is None else right
            return string_join(left, right)
        else:
            op = TriccOperation(operator, [left, right])
            return op

    def visitNotExpression(self, ctx):
        return not_clean(self.visit(ctx.expression()))

    def visitIsTrueOrFalseExpression(self, ctx):
        expr = self.visit(ctx.expression())
        op = TriccOperation(TriccOperator.ISTRUE if ctx.TRUE() else TriccOperator.ISFALSE)
        op.reference = [expr]
        return op

    def visitInequalityExpression(self, ctx):
        return self.visitExpressionComparison(ctx)

    def visitNumberLiteral(self, ctx):
        value = float(ctx.getText())
        value_int = int(value)
        return TriccStatic(value=value_int if value == value_int else value)

    def visitStringLiteral(self, ctx):
        return TriccStatic(value=unquote_literal(ctx.getText()))

    def visitExpressionComparison(self, ctx):
        left = self.visit(ctx.expression(0))
        right = self.visit(ctx.expression(1))
        op_text = ctx.getChild(1).getText()
        op_map = {
            "<": TriccOperator.LESS,
            "<=": TriccOperator.LESS_OR_EQUAL,
            ">": TriccOperator.MORE,
            ">=": TriccOperator.MORE_OR_EQUAL,
            "=": TriccOperator.EQUAL,
            "!=": TriccOperator.NOTEQUAL,
        }
        op = TriccOperation(op_map[op_text])
        op.reference = [left, right]
        return op

    def visitCastExpression(self, ctx):
        return self.visitTypeExpression(ctx)

    def visitPolarityExpressionTerm(self, ctx):
        if ctx.getChild(0).getText() == "-":
            return TriccOperation(TriccOperator.MINUS, [self.visit(ctx.getChild(1))])

    def visitMultiplicationExpressionTerm(self, ctx):
        op_text = ctx.getChild(1).getText()
        op_map = {
            "*": TriccOperator.MULTIPLIED,
            "div": TriccOperator.DIVIDED,
            "/": TriccOperator.DIVIDED,
            "%": TriccOperator.MODULO,
            "mod": TriccOperator.MODULO,
        }
        return self.__std_operator(op_map.get(op_text), ctx)

    def visitAdditionExpressionTerm(self, ctx):
        op_text = ctx.getChild(1).getText()
        op_map = {
            "+": TriccOperator.PLUS,
            "-": TriccOperator.MINUS,
            "&": TriccOperator.CONCATENATE,
        }
        return self.__std_operator(op_map.get(op_text), ctx)

    def visitTypeExpression(self, ctx):
        to_type = ctx.getChild(2).getText()
        expression = self.visit(ctx.getChild(0))
        if to_type == "int" or to_type.lower() == "integer":
            return TriccOperation(TriccOperator.CAST_INTEGER, [expression])
        elif to_type == "float" or to_type == "number":
            return TriccOperation(TriccOperator.CAST_NUMBER, [expression])
        elif to_type == "date":
            return TriccOperation(TriccOperator.CAST_DATE, [expression])
        else:
            raise NotImplementedError(f"cast {to_type} not supported")

    def visitQuantity(self, ctx):
        # still reachable in `within 3 days of` (timing phrases)
        raise NotImplementedError("quantity not supported")

    def visitUnit(self, ctx):
        # still reachable in `convert x to 'mg'`
        raise NotImplementedError("unit not supported")

    # def visitQualifiedIdentifier(self, ctx):
    #    raise NotImplementedError('qualifiedIdentifier not supported')

    def visitTypeSpecifier(self, ctx):
        raise NotImplementedError("typeSpecifier not supported")

    def visitRetrieve(self, ctx):
        # TODO
        raise NotImplementedError("retrieve not supported")

    def visitEqualityExpression(self, ctx):
        return self.visitExpressionComparison(ctx)

    def visitCaseExpressionTerm(self, ctx, operator=TriccOperator.CASE):
        op = TriccOperation(operator)
        op.reference = []
        for child in ctx.getChildren():
            c = self.visit(child)
            if c is not None:
                op.append(c)
        op.update_origin()
        return op

    def visitCaseExpressionItem(self, ctx):
        test = self.visit(ctx.expression(0))
        result = self.visit(ctx.expression(1))
        return [test, result]

    def visitTupleSelector(self, ctx):
        """``Tuple{ k: v, … }`` → ``TUPLE(k, v, …)``, keys as text (named DMN arguments, RFC #96)."""
        op = TriccOperation(TriccOperator.TUPLE)
        op.reference = []
        for element in ctx.tupleElementSelector():
            key = element.referentialIdentifier().getText()
            if len(key) > 1 and key[0] == key[-1] and key[0] in "\"`'":
                key = key[1:-1]
            op.reference += [TriccStatic(value=key), self.visit(element.expression())]
        return op

    def visitIfThenElseExpressionTerm(self, ctx):
        condition = self.visit(ctx.expression(0))
        true_value = self.visit(ctx.expression(1))
        false_value = self.visit(ctx.expression(2))
        op = TriccOperation(TriccOperator.IF)
        op.reference = [condition, true_value, false_value]
        return op


class CQLErrorListener(ErrorListener):
    context = None

    def __init__(self, context=None):
        super(CQLErrorListener, self).__init__()
        self.errors = []
        self.context = context

    def syntaxError(self, recognizer, offendingSymbol, line, column, msg, e):
        error = f"{self.context} \n" if self.context else ""
        error += f"Line {line}:{column} - {msg}"
        self.errors.append(error)


def transform_cql_to_operation(cql_input, context=None, quiet=False):
    """Parse a CQL expression into a TriccOperation / TriccReference / TriccStatic.

    The text is parsed with the TRICC profile (``tricc_oo/lang/cql/tricc_cql.g4``, entry
    ``triccExpression``). A bare identifier is text (``TriccStatic``); a reference is a
    ``"quoted"`` identifier.

    Args:
        cql_input: The expression.
        context: Shown in error messages.
        quiet: Do not report grammar errors (the caller treats unparsable input as text).

    Returns:
        The parsed expression, or None when it does not parse (a construct outside the
        profile is reported with its message from ``tricc_oo/lang/errors.json``).
    """
    tree, errors = parse_cql_expression(cql_input)
    if errors:
        if not quiet:
            where = f"{context} \n" if context else ""
            for error in errors:
                logger.error(f"CQL Grammar Error: {where}{error} \n in:\n {cql_input}")
        return None

    visitor = cqlToXlsFormVisitor()
    result = visitor.visit(tree)
    if visitor.errors:
        logger.warning(f"while visiting cql: \n{cql_input}")
        for e in visitor.errors:
            logger.warning(e)

    return result


def transform_cql_lib_to_operations(cql_input):
    input_stream = InputStream(cql_input)
    lexer = cqlLexer(input_stream)
    stream = CommonTokenStream(lexer)
    parser = cqlParser(stream)
    tree = parser.library()
    visitor = cqlToXlsFormVisitor()
    visitor.visit(tree)
    return visitor.xlsform_rows
