# Generated from ./tricc_oo/converters/xlsform/g4/xlsform.g4 by ANTLR 4.13.2
from antlr4 import *
if "." in __name__:
    from .xlsformParser import xlsformParser
else:
    from xlsformParser import xlsformParser

# This class defines a complete listener for a parse tree produced by xlsformParser.
class xlsformListener(ParseTreeListener):

    # Enter a parse tree produced by xlsformParser#main.
    def enterMain(self, ctx:xlsformParser.MainContext):
        pass

    # Exit a parse tree produced by xlsformParser#main.
    def exitMain(self, ctx:xlsformParser.MainContext):
        pass


    # Enter a parse tree produced by xlsformParser#locationPath.
    def enterLocationPath(self, ctx:xlsformParser.LocationPathContext):
        pass

    # Exit a parse tree produced by xlsformParser#locationPath.
    def exitLocationPath(self, ctx:xlsformParser.LocationPathContext):
        pass


    # Enter a parse tree produced by xlsformParser#absoluteLocationPathNoroot.
    def enterAbsoluteLocationPathNoroot(self, ctx:xlsformParser.AbsoluteLocationPathNorootContext):
        pass

    # Exit a parse tree produced by xlsformParser#absoluteLocationPathNoroot.
    def exitAbsoluteLocationPathNoroot(self, ctx:xlsformParser.AbsoluteLocationPathNorootContext):
        pass


    # Enter a parse tree produced by xlsformParser#relativeLocationPath.
    def enterRelativeLocationPath(self, ctx:xlsformParser.RelativeLocationPathContext):
        pass

    # Exit a parse tree produced by xlsformParser#relativeLocationPath.
    def exitRelativeLocationPath(self, ctx:xlsformParser.RelativeLocationPathContext):
        pass


    # Enter a parse tree produced by xlsformParser#step.
    def enterStep(self, ctx:xlsformParser.StepContext):
        pass

    # Exit a parse tree produced by xlsformParser#step.
    def exitStep(self, ctx:xlsformParser.StepContext):
        pass


    # Enter a parse tree produced by xlsformParser#axisSpecifier.
    def enterAxisSpecifier(self, ctx:xlsformParser.AxisSpecifierContext):
        pass

    # Exit a parse tree produced by xlsformParser#axisSpecifier.
    def exitAxisSpecifier(self, ctx:xlsformParser.AxisSpecifierContext):
        pass


    # Enter a parse tree produced by xlsformParser#nodeTest.
    def enterNodeTest(self, ctx:xlsformParser.NodeTestContext):
        pass

    # Exit a parse tree produced by xlsformParser#nodeTest.
    def exitNodeTest(self, ctx:xlsformParser.NodeTestContext):
        pass


    # Enter a parse tree produced by xlsformParser#predicate.
    def enterPredicate(self, ctx:xlsformParser.PredicateContext):
        pass

    # Exit a parse tree produced by xlsformParser#predicate.
    def exitPredicate(self, ctx:xlsformParser.PredicateContext):
        pass


    # Enter a parse tree produced by xlsformParser#abbreviatedStep.
    def enterAbbreviatedStep(self, ctx:xlsformParser.AbbreviatedStepContext):
        pass

    # Exit a parse tree produced by xlsformParser#abbreviatedStep.
    def exitAbbreviatedStep(self, ctx:xlsformParser.AbbreviatedStepContext):
        pass


    # Enter a parse tree produced by xlsformParser#expr.
    def enterExpr(self, ctx:xlsformParser.ExprContext):
        pass

    # Exit a parse tree produced by xlsformParser#expr.
    def exitExpr(self, ctx:xlsformParser.ExprContext):
        pass


    # Enter a parse tree produced by xlsformParser#primaryExpr.
    def enterPrimaryExpr(self, ctx:xlsformParser.PrimaryExprContext):
        pass

    # Exit a parse tree produced by xlsformParser#primaryExpr.
    def exitPrimaryExpr(self, ctx:xlsformParser.PrimaryExprContext):
        pass


    # Enter a parse tree produced by xlsformParser#functionCall.
    def enterFunctionCall(self, ctx:xlsformParser.FunctionCallContext):
        pass

    # Exit a parse tree produced by xlsformParser#functionCall.
    def exitFunctionCall(self, ctx:xlsformParser.FunctionCallContext):
        pass


    # Enter a parse tree produced by xlsformParser#unionExprNoRoot.
    def enterUnionExprNoRoot(self, ctx:xlsformParser.UnionExprNoRootContext):
        pass

    # Exit a parse tree produced by xlsformParser#unionExprNoRoot.
    def exitUnionExprNoRoot(self, ctx:xlsformParser.UnionExprNoRootContext):
        pass


    # Enter a parse tree produced by xlsformParser#pathExprNoRoot.
    def enterPathExprNoRoot(self, ctx:xlsformParser.PathExprNoRootContext):
        pass

    # Exit a parse tree produced by xlsformParser#pathExprNoRoot.
    def exitPathExprNoRoot(self, ctx:xlsformParser.PathExprNoRootContext):
        pass


    # Enter a parse tree produced by xlsformParser#filterExpr.
    def enterFilterExpr(self, ctx:xlsformParser.FilterExprContext):
        pass

    # Exit a parse tree produced by xlsformParser#filterExpr.
    def exitFilterExpr(self, ctx:xlsformParser.FilterExprContext):
        pass


    # Enter a parse tree produced by xlsformParser#orExpr.
    def enterOrExpr(self, ctx:xlsformParser.OrExprContext):
        pass

    # Exit a parse tree produced by xlsformParser#orExpr.
    def exitOrExpr(self, ctx:xlsformParser.OrExprContext):
        pass


    # Enter a parse tree produced by xlsformParser#andExpr.
    def enterAndExpr(self, ctx:xlsformParser.AndExprContext):
        pass

    # Exit a parse tree produced by xlsformParser#andExpr.
    def exitAndExpr(self, ctx:xlsformParser.AndExprContext):
        pass


    # Enter a parse tree produced by xlsformParser#equalityExpr.
    def enterEqualityExpr(self, ctx:xlsformParser.EqualityExprContext):
        pass

    # Exit a parse tree produced by xlsformParser#equalityExpr.
    def exitEqualityExpr(self, ctx:xlsformParser.EqualityExprContext):
        pass


    # Enter a parse tree produced by xlsformParser#relationalExpr.
    def enterRelationalExpr(self, ctx:xlsformParser.RelationalExprContext):
        pass

    # Exit a parse tree produced by xlsformParser#relationalExpr.
    def exitRelationalExpr(self, ctx:xlsformParser.RelationalExprContext):
        pass


    # Enter a parse tree produced by xlsformParser#additiveExpr.
    def enterAdditiveExpr(self, ctx:xlsformParser.AdditiveExprContext):
        pass

    # Exit a parse tree produced by xlsformParser#additiveExpr.
    def exitAdditiveExpr(self, ctx:xlsformParser.AdditiveExprContext):
        pass


    # Enter a parse tree produced by xlsformParser#multiplicativeExpr.
    def enterMultiplicativeExpr(self, ctx:xlsformParser.MultiplicativeExprContext):
        pass

    # Exit a parse tree produced by xlsformParser#multiplicativeExpr.
    def exitMultiplicativeExpr(self, ctx:xlsformParser.MultiplicativeExprContext):
        pass


    # Enter a parse tree produced by xlsformParser#unaryExprNoRoot.
    def enterUnaryExprNoRoot(self, ctx:xlsformParser.UnaryExprNoRootContext):
        pass

    # Exit a parse tree produced by xlsformParser#unaryExprNoRoot.
    def exitUnaryExprNoRoot(self, ctx:xlsformParser.UnaryExprNoRootContext):
        pass


    # Enter a parse tree produced by xlsformParser#qName.
    def enterQName(self, ctx:xlsformParser.QNameContext):
        pass

    # Exit a parse tree produced by xlsformParser#qName.
    def exitQName(self, ctx:xlsformParser.QNameContext):
        pass


    # Enter a parse tree produced by xlsformParser#functionName.
    def enterFunctionName(self, ctx:xlsformParser.FunctionNameContext):
        pass

    # Exit a parse tree produced by xlsformParser#functionName.
    def exitFunctionName(self, ctx:xlsformParser.FunctionNameContext):
        pass


    # Enter a parse tree produced by xlsformParser#standardReference.
    def enterStandardReference(self, ctx:xlsformParser.StandardReferenceContext):
        pass

    # Exit a parse tree produced by xlsformParser#standardReference.
    def exitStandardReference(self, ctx:xlsformParser.StandardReferenceContext):
        pass


    # Enter a parse tree produced by xlsformParser#nternalReference.
    def enterNternalReference(self, ctx:xlsformParser.NternalReferenceContext):
        pass

    # Exit a parse tree produced by xlsformParser#nternalReference.
    def exitNternalReference(self, ctx:xlsformParser.NternalReferenceContext):
        pass


    # Enter a parse tree produced by xlsformParser#nameTest.
    def enterNameTest(self, ctx:xlsformParser.NameTestContext):
        pass

    # Exit a parse tree produced by xlsformParser#nameTest.
    def exitNameTest(self, ctx:xlsformParser.NameTestContext):
        pass


    # Enter a parse tree produced by xlsformParser#nCName.
    def enterNCName(self, ctx:xlsformParser.NCNameContext):
        pass

    # Exit a parse tree produced by xlsformParser#nCName.
    def exitNCName(self, ctx:xlsformParser.NCNameContext):
        pass



del xlsformParser