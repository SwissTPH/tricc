from antlr4 import *
from tricc_oo.converters.cql.cqlLexer import cqlLexer
from tricc_oo.converters.cql.cqlParser import cqlParser
from tricc_oo.converters.cql.cqlVisitor import cqlVisitor
from tricc_oo.converters.utils import clean_name
from tricc_oo.models.base import  TriccOperator, TriccOperation, TriccStatic

EXPRESSION = 0
STRING = 1
NUMBER = 2
ANY = 3

FUNCTION_MAP = {
    'AgeInYears': TriccOperator.AGE_YEAR,
    'AgeInMonths': TriccOperator.AGE_MONTH,
    'AgeInDays': TriccOperator.AGE_DAY,
    'Coalesce': TriccOperator.COALESCE,
    'Izscore': TriccOperator.IZSCORE,
    'Zscore': TriccOperator.ZSCORE,
    'DrugDosage':  TriccOperator.DRUG_DOSAGE,
    'HasQualifier': TriccOperator.HAS_QUALIFIER,
}


class cqlToXlsFormVisitor(cqlVisitor):
    def __init__(self):
        self.xlsform_rows = []
        
    def resolve_scv(self, arg):
        
        # TODO 
        # look for the system, if not found fallback on default system
        # look for the code in the system
        # if no code or not found return None
        # if code found, return f"${{{clean_name(arg)}}}"
        return f"${{{clean_name(arg[1:-1].lower())}}}"
        
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
        if 'Term' not in type(ctx).__name__:
            print(f"Visiting unknown node type: {type(ctx).__name__}")
        return super().visitChildren(ctx)

    def visitExpression(self, ctx):
        print(f"Visiting expression: {ctx.getText()}")
        return self.visitChildren(ctx)
    
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

    def visitMemberInvocation(self, ctx):
        return self.visitChildren(ctx)

    def visitMembershipExpression(self, ctx):
        function_name = ctx.getChild(0).getText()
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
            op = TriccOperation(
                operator = TriccOperator.NOT,
                reference = [op]
            )
    
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
        left = self.visit(ctx.expression(0))
        right = self.visit(ctx.expression(1))
        op = TriccOperation(operator)
        op.reference = [left, right]
        return op

    def visitNotExpression(self, ctx):
        expr = self.visit(ctx.expression())
        op = TriccOperation(TriccOperator.NOT)
        op.reference = [expr]
        return op

    def visitIsTrueOrFalseExpression(self, ctx):
        expr = self.visit(ctx.expression())
        op = TriccOperation(TriccOperator.ISTRUE if ctx.TRUE() else TriccOperator.ISFALSE)
        op.reference = [expr]
        return op

    def visitInequalityExpression(self, ctx):
        return self.visitExpressionComparison(ctx)

    def visitNumberLiteral(self, ctx):
        return TriccStatic(value=float(ctx.getText()))

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
            '!=': TriccOperator.NOT_EQUAL
        }
        op = TriccOperation(op_map[op_text])
        op.reference = [left, right]
        return op

    def visitInvocationExpression(self, ctx):
        raise NotImplementedError('Invocation not supported')
    
    def visitIndexerExpression(self, ctx):
        raise NotImplementedError('Indexer not supported')    
    
    def visitPolarityExpression(self, ctx):
        raise NotImplementedError('Polarity not supported')
    
    def visitMultiplicativeExpression(self, ctx):
        # TODO
        raise NotImplementedError('Indexer not supported')
    
    def visitAdditiveExpression(self, ctx):
        # TODO
        raise NotImplementedError('Indexer not supported')
    
    def visitTypeExpression(self, ctx):
        raise NotImplementedError('cast not supported')
    
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
            if c:
                op.reference.append(c)
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
    
    
def transform_cql_to_operation(cql_input):
    cql_input = f"""
    library runner
    
    define "calc":
        {cql_input}
    """
    input_stream = InputStream(cql_input)
    lexer = cqlLexer(input_stream)
    stream = CommonTokenStream(lexer)
    parser = cqlParser(stream)
    tree = parser.library()
    visitor = cqlToXlsFormVisitor()
    visitor.visit(tree)
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
