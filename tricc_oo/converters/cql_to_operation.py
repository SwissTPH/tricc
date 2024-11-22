from antlr4 import *
from tricc_og.builders.cql.cqlLexer import cqlLexer
from tricc_og.builders.cql.cqlParser import cqlParser
from tricc_og.builders.cql.cqlVisitor import cqlVisitor
from tricc_og.builders.utils import clean_name

EXPRESSION = 0
STRING = 1
NUMBER = 2
ANY = 3


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
    
    def visitFunctionInvocation(self, ctx):
        if ctx.getChildCount() == 1:
            return self.visitFunctionInvocation(ctx.getChild(0))
        function_name = ctx.getChild(0).getText()
        args = ctx.paramList()
        if args:
            args = [self.translate(arg) for arg in args if arg]
        # args = [self.visit(arg) for arg in ctx.paramList().expression()]
        if function_name == 'Coalesce':
            return f'coalesce(({"", "".join(args) if args else ""})'
        if function_name == 'AgeInYears':
            return f'int((today() - date(${{{args[0] if args else "birth_date"}}})) div 365.25)'
        elif function_name == 'AgeInMonths':
            return f'int((today() - date(${{{args[0] if args else "birth_date"}}})) div 30.5)'
        elif function_name == 'AgeInDays':
            return f'int(today() - date(${{{args[0] if args else "birth_date"}}}))'
        # Add more function transformations here
        return f'{function_name}({", ".join(args)})'
    
    def visitMemberInvocation(self, ctx):
        return self.visitChildren(ctx)
    # in and contains
    def visistMembershipExpression(self, ctx):
        # TODO 
        ...
 
        
    def visitBetweenExpression(self, ctx):
        # TODO 
        ...

    def visitExistenceExpression(self, ctx):
        # TODO 
        ...
        
    def visitAndExpression(self, ctx):
        left = self.visit(ctx.expression(0))
        right = self.visit(ctx.expression(1))
        return f'{left} and {right}'

    def visitOrExpression(self, ctx):
        left = self.visit(ctx.expression(0))
        right = self.visit(ctx.expression(1))
        return f'{left} or {right}'

    def visitNotExpression(self, ctx):
        expr = self.visit(ctx.expression())
        return f'not({expr})'

    def visitIsTrueOrFalseExpression(self, ctx):
        expr = self.visit(ctx.expression())
        if ctx.TRUE():
            return f'{expr} > 0'
        else:
            return f'{expr} = 0'

    def visitInExpression(self, ctx):
        left = self.visit(ctx.expression(0))
        right = self.visit(ctx.expression(1))
        return f'selected({right}, {left})'

    def visitInequalityExpression(self, ctx):
        return self.visitExpressionComparison(ctx)
    
    def visitNumberLiteral(self, ctx):
        return ctx.getText()
    
    def visitStringLiteral(self, ctx):
        return ctx.getText()
    
    def visitExpressionComparison(self, ctx):
        left = self.visit(ctx.expression(0))
        right = self.visit(ctx.expression(1))
        op = ctx.getChild(1).getText()
        return f'{left} {op} {right}'

    def visitEqualityExpression(self, ctx):
        left = self.visit(ctx.expression(0))
        right = self.visit(ctx.expression(1))
        op = '=' if ctx.getChild(1).getText() == '=' else '!='
        return f'{left} {op} {right}'

    def secure_xform_ref(self, out):
        return out.replace('{}', '##').replace('{', '{{').replace('}', '}}').replace('##', '{}')


    def visitCaseExpressionTerm(self, ctx):
        out = "{}"
        ref = ''
        # test first child
        for i in range(0, ctx.getChildCount()):
            c = self.visit(ctx.getChild(i))
            
            if c:
                if i == 1 and 'if(' not in c:
                    ref = c
                else:
                    out = self.secure_xform_ref(out)
                    if ref:
                        c = c.format(ref, '{}')
                    out = out.format(c)
        if '{}' in out:
            out = self.secure_xform_ref(out)
            out = out.format("''")
        return out
    
    

    def visitCaseExpressionItem(self, ctx):
        test = ctx.expression(0)
        test_str = self.visit(test)
        if ctx.expression(0).getChildCount() == 1:
            test_str = f"{{}} = {test_str}"
        return f"if({test_str}, {self.visit(ctx.expression(1))}, {{}})"
    
    def visitIfThenElseExpression(self, ctx):
        return self.visitCaseExpressionTerm(ctx)
    # Add more visit methods for other expression types

def transform_cql_to_operation(cql_input):
    input_stream = InputStream(cql_input)
    lexer = cqlLexer(input_stream)
    stream = CommonTokenStream(lexer)
    parser = cqlParser(stream)
    tree = parser.library()

    visitor = cqlToXlsFormVisitor()
    visitor.visit(tree)

    return visitor.xlsform_rows
