# Generated from ./tricc_oo/converters/xlsform/g4/xlsform.g4 by ANTLR 4.13.2
from antlr4 import *
if "." in __name__:
    from .xlsformParser import xlsformParser
else:
    from xlsformParser import xlsformParser

# This class defines a complete generic visitor for a parse tree produced by xlsformParser.

class xlsformVisitor(ParseTreeVisitor):

    # Visit a parse tree produced by xlsformParser#main.
    def visitMain(self, ctx:xlsformParser.MainContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by xlsformParser#locationPath.
    def visitLocationPath(self, ctx:xlsformParser.LocationPathContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by xlsformParser#absoluteLocationPathNoroot.
    def visitAbsoluteLocationPathNoroot(self, ctx:xlsformParser.AbsoluteLocationPathNorootContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by xlsformParser#relativeLocationPath.
    def visitRelativeLocationPath(self, ctx:xlsformParser.RelativeLocationPathContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by xlsformParser#step.
    def visitStep(self, ctx:xlsformParser.StepContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by xlsformParser#axisSpecifier.
    def visitAxisSpecifier(self, ctx:xlsformParser.AxisSpecifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by xlsformParser#nodeTest.
    def visitNodeTest(self, ctx:xlsformParser.NodeTestContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by xlsformParser#predicate.
    def visitPredicate(self, ctx:xlsformParser.PredicateContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by xlsformParser#abbreviatedStep.
    def visitAbbreviatedStep(self, ctx:xlsformParser.AbbreviatedStepContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by xlsformParser#expr.
    def visitExpr(self, ctx:xlsformParser.ExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by xlsformParser#primaryExpr.
    def visitPrimaryExpr(self, ctx:xlsformParser.PrimaryExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by xlsformParser#functionCall.
    def visitFunctionCall(self, ctx:xlsformParser.FunctionCallContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by xlsformParser#unionExprNoRoot.
    def visitUnionExprNoRoot(self, ctx:xlsformParser.UnionExprNoRootContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by xlsformParser#pathExprNoRoot.
    def visitPathExprNoRoot(self, ctx:xlsformParser.PathExprNoRootContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by xlsformParser#filterExpr.
    def visitFilterExpr(self, ctx:xlsformParser.FilterExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by xlsformParser#orExpr.
    def visitOrExpr(self, ctx:xlsformParser.OrExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by xlsformParser#andExpr.
    def visitAndExpr(self, ctx:xlsformParser.AndExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by xlsformParser#equalityExpr.
    def visitEqualityExpr(self, ctx:xlsformParser.EqualityExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by xlsformParser#relationalExpr.
    def visitRelationalExpr(self, ctx:xlsformParser.RelationalExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by xlsformParser#additiveExpr.
    def visitAdditiveExpr(self, ctx:xlsformParser.AdditiveExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by xlsformParser#multiplicativeExpr.
    def visitMultiplicativeExpr(self, ctx:xlsformParser.MultiplicativeExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by xlsformParser#unaryExprNoRoot.
    def visitUnaryExprNoRoot(self, ctx:xlsformParser.UnaryExprNoRootContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by xlsformParser#qName.
    def visitQName(self, ctx:xlsformParser.QNameContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by xlsformParser#functionName.
    def visitFunctionName(self, ctx:xlsformParser.FunctionNameContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by xlsformParser#standardReference.
    def visitStandardReference(self, ctx:xlsformParser.StandardReferenceContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by xlsformParser#nternalReference.
    def visitNternalReference(self, ctx:xlsformParser.NternalReferenceContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by xlsformParser#nameTest.
    def visitNameTest(self, ctx:xlsformParser.NameTestContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by xlsformParser#nCName.
    def visitNCName(self, ctx:xlsformParser.NCNameContext):
        return self.visitChildren(ctx)



del xlsformParser