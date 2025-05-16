from antlr4 import *
from tricc_oo.converters.cql.cqlLexer import cqlLexer
from tricc_oo.converters.cql.cqlParser import cqlParser
from tricc_oo.converters.cql.cqlVisitor import cqlVisitor
from tricc_oo.converters.utils import clean_name
from tricc_oo.models.base import  TriccOperator, TriccOperation, TriccStatic, TriccReference, not_clean, or_join, and_join
import logging

logger = logging.getLogger("default")

EXPRESSION = 0
STRING = 1
NUMBER = 2
ANY = 3

FUNCTION_MAP = {
    'AgeInYears': TriccOperator.AGE_YEAR,
    'AgeInMonths': TriccOperator.AGE_MONTH,
    'AgeInDays': TriccOperator.AGE_DAY,
    'Coalesce': TriccOperator.COALESCE,
    'Concatenate': TriccOperator.CONCATENATE,
    'Izscore': TriccOperator.IZSCORE,
    'Zscore': TriccOperator.ZSCORE,
    'DrugDosage':  TriccOperator.DRUG_DOSAGE,
    'HasQualifier': TriccOperator.HAS_QUALIFIER,
}
# TODO
# Min
# Max
# Round
# this need to be done by contribution to DMN

class cqlToXlsFormVisitor(cqlVisitor):
    def __init__(self):
        self.xlsform_rows = []
        self.errors= []
        
    def resolve_scv(self, arg):
        
        # TODO 
        # look for the system, if not found fallback on default system
        # look for the code in the system
        # if no code or not found return None
        if arg.startswith('"') and arg.endswith('"'):
            return TriccReference(arg[1:-1])
        elif arg.lower() in ['true', 'false']:
            return TriccStatic(arg.lower() == 'true')
        elif arg != 'runner':
            self.errors.append(f"'{arg}' will be poccessed as reference ")
            return TriccReference(arg)
        
        else:
            return 'runner'
        
    def translate(self, arg, type=ANY):
        return self.resolve_scv(arg) or str(arg)
    
    def visitExpressionDefinition(self, ctx):
        identifier = ctx.identifier().getText()
        expression = self.visit(ctx.expression())
        self.xlsform_rows.append({
            'type': 'calculate',
            'name': clean_name(identifier[1:-1].lower()),
            'calculation': expression
        })
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
                return [
                    *aggregate,
                    nextResult
                ]
        else:
            return nextResult

    def visitExpression(self, ctx):
        return self.visitChildren(ctx)
    def visitThisInvocation(self, ctx):
        return '$this'
   
    def visitBooleanLiteral(self, ctx):
        literal =  ctx.getChild(0).getText()
        if literal == 'true':
            return TriccStatic(True)
        elif literal == 'false':
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
        args = ctx.paramList()
        if args:
            op.reference += [self.visit(arg) for arg in args.expression() if arg]
            

        return op
    
    def __std_function(self, ctx, operator=TriccOperator.NATIVE):
        args = ctx.expressions
        if args:
            args = [self.visit(arg) for arg in ctx.expression() if arg]
        op = TriccOperation(operator)
        op.reference = [
            *args
        ]

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
        if function_name == 'in':
            op = TriccOperation(TriccOperator.SELECTED)
            op.reference = [
                right, 
                left
            ]
        elif function_name == 'contains':
            op = TriccOperation(TriccOperator.CONTAINS)
            op.reference = [ 
                left,
                right
            ]
        return op
    
    def visitNegateMembershipExpression(self, ctx):
        function_name = ctx.getChild(2).getText()
        return not_clean(self._get_membership_expression(ctx, function_name))
    
    def visitInvocationExpressionTerm(self, ctx):
        result = super().visitInvocationExpressionTerm(ctx)
        if isinstance(result, list) and all(isinstance(x, TriccStatic) for x in result):
            value = '.'.join([x.value for x in result])
            logger.warning(f"guessed reference for '{value}'")
            return TriccReference(value)
        return result

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
            operator = {
            'true': TriccOperator.ISTRUE,
            'false': TriccOperator.ISFALSE,
            'null': TriccOperator.ISNULL
            }[params[-1]],
            reference = [expr]
        )
        
        if params[0] == 'not':
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
        if hasattr(ctx, 'expression'):
            left = self.visit(ctx.expression(0))
            right = self.visit(ctx.expression(1))
        elif hasattr(ctx, 'expressionTerm'):
            left = self.visit(ctx.expressionTerm(0))
            right = self.visit(ctx.expressionTerm(1))
        if  operator == TriccOperator.AND:
            return and_join([left, right])
        elif  operator == TriccOperator.OR:
            return or_join([left, right])  
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
        return TriccStatic(value=ctx.getText().strip("'"))

    def visitExpressionComparison(self, ctx):
        left = self.visit(ctx.expression(0))
        right = self.visit(ctx.expression(1))
        op_text = ctx.getChild(1).getText()
        op_map = {
            '<': TriccOperator.LESS,
            '<=': TriccOperator.LESS_OR_EQUAL,
            '>': TriccOperator.MORE,
            '>=': TriccOperator.MORE_OR_EQUAL,
            '=': TriccOperator.EQUAL,
            '!=': TriccOperator.NOTEQUAL
        }
        op = TriccOperation(op_map[op_text])
        op.reference = [left, right]
        return op

    def visitInvocationExpression(self, ctx):
        raise NotImplementedError('Invocation not supported')
    
    def visitIndexerExpression(self, ctx):
        raise NotImplementedError('Indexer not supported')
    
    def visitCastExpression(self, ctx):
        # TODO
        raise NotImplementedError('Cast not supported')
    
    def visitPolarityExpressionTerm(self, ctx):
        if ctx.getChild(0).getText() == '-':
            return TriccOperation(TriccOperator.MINUS, [self.visit(ctx.getChild(1))])
    
    def visitMultiplicationExpressionTerm(self, ctx):
        op_text = ctx.getChild(1).getText()
        op_map = {
            '*': TriccOperator.MULTIPLIED,
            'div': TriccOperator.DIVIDED,
            '/': TriccOperator.DIVIDED,
            '%': TriccOperator.MODULO,
            'mod': TriccOperator.MODULO,
        }
        return self.__std_operator(op_map.get(op_text), ctx)
    
    def visitAdditionExpressionTerm(self, ctx):
        op_text = ctx.getChild(1).getText()
        op_map = {
            '+': TriccOperator.PLUS,
            '-': TriccOperator.MINUS,
            '&': TriccOperator.AND
        }
        return self.__std_operator(op_map.get(op_text), ctx)

    
    def visitTypeExpression(self, ctx):
        to_type = ctx.getChild(2).getText()
        expression = self.visit(ctx.getChild(0))
        if to_type == 'int' or to_type == 'integer':
            return TriccOperation(TriccOperator.CAST_INTEGER, [expression])
        elif to_type == 'float' or to_type == 'number':
            return TriccOperation(TriccOperator.CAST_NUMBER, [expression])
        elif to_type == 'date':
            return TriccOperation(TriccOperator.CAST_DATE, [expression])
        else:
            raise NotImplementedError(f'cast {to_type} not supported')
    
    def visitUnionExpression(self, ctx):
        raise NotImplementedError('union not supported')

    def visitThisInvocation(self, ctx):
        # TODO
        raise NotImplementedError('Implies not supported')

    def visitQuantity(self, ctx):
        # TODO
        raise NotImplementedError('Indexer not supported')

    def visitUnit(self, ctx):
        raise NotImplementedError('Indexer not supported')

    def visistDateTimePrecision(self, ctx):
        # TODO
        raise NotImplementedError('Indexer not supported')

    def visitPluralDateTimePrecision(self, ctx):
        # TODO
        raise NotImplementedError('Indexer not supported')

    #def visitQualifiedIdentifier(self, ctx):
    #    raise NotImplementedError('qualifiedIdentifier not supported')

    def visitTypeSpecifier(self, ctx):
        raise NotImplementedError('typeSpecifier not supported')

    def visitRetrieve(self, ctx):
        # TODO
        raise NotImplementedError('retrieve not supported')
    
    def visitEqualityExpression(self, ctx):
        return self.visitExpressionComparison(ctx)

    def visitCaseExpressionTerm(self, ctx, operator=TriccOperator.CASE):
        op = TriccOperation(operator)
        op.reference = []
        for child in ctx.getChildren():
            c = self.visit(child)
            if c is not None:
                op.append(c)
        return op

    def visitCaseExpressionItem(self, ctx):
        test = self.visit(ctx.expression(0))
        result = self.visit(ctx.expression(1))
        return [test, result]

    def visitIfThenElseExpressionTerm(self, ctx):
        condition = self.visit(ctx.expression(0))
        true_value = self.visit(ctx.expression(1))
        false_value = self.visit(ctx.expression(2))
        op = TriccOperation(TriccOperator.IF)
        op.reference = [condition, true_value, false_value]
        return op
    
    
from antlr4.error.ErrorListener import ErrorListener

class CQLErrorListener(ErrorListener):
    context = None
    def __init__(self, context=None):
        super(CQLErrorListener, self).__init__()
        self.errors = []
        self.context = context

    def syntaxError(self, recognizer, offendingSymbol, line, column, msg, e):
        error = f"{self.context} \n" if self.context else ''
        error += f"Line {line}:{column} - {msg}"
        self.errors.append(error)

def transform_cql_to_operation(cql_input, context=None):
    lib_input = f"""
    library runner
    
    define "calc":
        {cql_input.replace('−', '-')}
    """
    input_stream = InputStream(chr(10).join(lib_input.split('\n')))
    lexer = cqlLexer(input_stream)
    stream = CommonTokenStream(lexer)
    parser = cqlParser(stream)

    # Remove default error listeners and add custom listener
    parser.removeErrorListeners()
    lexer.removeErrorListeners()
    error_listener = CQLErrorListener(context)
    parser.addErrorListener(error_listener)
    lexer.addErrorListener(error_listener)
    tree = parser.library()

    # Check for errors
    if error_listener.errors:
        for error in error_listener.errors:
            print(f"CQL Grammar Error: {error} \n in:\n {cql_input}")
        return None  # Or handle errors as appropriate for your use case

    # If no errors, proceed with visitor
    visitor = cqlToXlsFormVisitor()
    
    visitor.visit(tree)
    if visitor.errors:
        logger.warning(f"while visiting cql: \n{cql_input}")
        for e in visitor.errors:
            logger.warning(e)
        
    return visitor.xlsform_rows[0]['calculation']

def transform_cql_lib_to_operations(cql_input):
    input_stream = InputStream(cql_input)
    lexer = cqlLexer(input_stream)
    stream = CommonTokenStream(lexer)
    parser = cqlParser(stream)
    tree = parser.library()
    visitor = cqlToXlsFormVisitor()
    visitor.visit(tree)
    return visitor.xlsform_rows
