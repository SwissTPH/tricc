# flake8: noqa
# tricc-lang 1.0.0 (tricc_oo/lang/VERSION)
# Generated from TriccFeelParser.g4 by ANTLR 4.13.2
from antlr4 import *
if "." in __name__:
    from .TriccFeelParser import TriccFeelParser
else:
    from TriccFeelParser import TriccFeelParser

# This class defines a complete generic visitor for a parse tree produced by TriccFeelParser.

class TriccFeelParserVisitor(ParseTreeVisitor):

    # Visit a parse tree produced by TriccFeelParser#cellRoot.
    def visitCellRoot(self, ctx:TriccFeelParser.CellRootContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TriccFeelParser#cellAny.
    def visitCellAny(self, ctx:TriccFeelParser.CellAnyContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TriccFeelParser#cellNotNull.
    def visitCellNotNull(self, ctx:TriccFeelParser.CellNotNullContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TriccFeelParser#cellList.
    def visitCellList(self, ctx:TriccFeelParser.CellListContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TriccFeelParser#cellCompare.
    def visitCellCompare(self, ctx:TriccFeelParser.CellCompareContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TriccFeelParser#cellNull.
    def visitCellNull(self, ctx:TriccFeelParser.CellNullContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TriccFeelParser#cellRange.
    def visitCellRange(self, ctx:TriccFeelParser.CellRangeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TriccFeelParser#cellEquals.
    def visitCellEquals(self, ctx:TriccFeelParser.CellEqualsContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by TriccFeelParser#cellValue.
    def visitCellValue(self, ctx:TriccFeelParser.CellValueContext):
        return self.visitChildren(ctx)



del TriccFeelParser