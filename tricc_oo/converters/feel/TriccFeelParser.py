# flake8: noqa
# tricc-lang 1.0.0 (tricc_oo/lang/VERSION)
# Generated from TriccFeelParser.g4 by ANTLR 4.13.2
# encoding: utf-8
from antlr4 import *
from io import StringIO
import sys
if sys.version_info[1] > 5:
	from typing import TextIO
else:
	from typing.io import TextIO

def serializedATN():
    return [
        4,1,57,48,2,0,7,0,2,1,7,1,2,2,7,2,2,3,7,3,1,0,1,0,1,0,1,1,1,1,1,
        1,1,1,1,1,1,1,1,1,1,1,5,1,20,8,1,10,1,12,1,23,9,1,3,1,25,8,1,1,2,
        1,2,1,2,1,2,1,2,1,2,1,2,1,2,1,2,1,2,3,2,37,8,2,1,3,3,3,40,8,3,1,
        3,1,3,1,3,1,3,3,3,46,8,3,1,3,0,0,4,0,2,4,6,0,4,1,0,37,41,2,0,27,
        27,31,32,2,0,28,28,31,32,1,0,24,25,53,0,8,1,0,0,0,2,24,1,0,0,0,4,
        36,1,0,0,0,6,45,1,0,0,0,8,9,3,2,1,0,9,10,5,0,0,1,10,1,1,0,0,0,11,
        25,5,47,0,0,12,13,5,51,0,0,13,14,5,27,0,0,14,15,5,19,0,0,15,25,5,
        28,0,0,16,21,3,4,2,0,17,18,5,33,0,0,18,20,3,4,2,0,19,17,1,0,0,0,
        20,23,1,0,0,0,21,19,1,0,0,0,21,22,1,0,0,0,22,25,1,0,0,0,23,21,1,
        0,0,0,24,11,1,0,0,0,24,12,1,0,0,0,24,16,1,0,0,0,25,3,1,0,0,0,26,
        27,7,0,0,0,27,37,3,6,3,0,28,37,5,19,0,0,29,30,7,1,0,0,30,31,3,6,
        3,0,31,32,5,34,0,0,32,33,3,6,3,0,33,34,7,2,0,0,34,37,1,0,0,0,35,
        37,3,6,3,0,36,26,1,0,0,0,36,28,1,0,0,0,36,29,1,0,0,0,36,35,1,0,0,
        0,37,5,1,0,0,0,38,40,5,47,0,0,39,38,1,0,0,0,39,40,1,0,0,0,40,41,
        1,0,0,0,41,46,7,3,0,0,42,46,5,1,0,0,43,46,5,26,0,0,44,46,5,2,0,0,
        45,39,1,0,0,0,45,42,1,0,0,0,45,43,1,0,0,0,45,44,1,0,0,0,46,7,1,0,
        0,0,5,21,24,36,39,45
    ]

class TriccFeelParser ( Parser ):

    grammarFileName = "TriccFeelParser.g4"

    atn = ATNDeserializer().deserialize(serializedATN())

    decisionsToDFA = [ DFA(ds, i) for i, ds in enumerate(atn.decisionToState) ]

    sharedContextCache = PredictionContextCache()

    literalNames = [ "<INVALID>", "<INVALID>", "<INVALID>", "'for'", "'return'", 
                     "'in'", "'if'", "'then'", "'else'", "'some'", "'every'", 
                     "'satisfies'", "'instance'", "'of'", "'function'", 
                     "'external'", "'or'", "'and'", "'between'", "'null'", 
                     "'undefined'", "'true'", "'false'", "'''", "<INVALID>", 
                     "<INVALID>", "<INVALID>", "'('", "')'", "'{'", "'}'", 
                     "'['", "']'", "','", "'..'", "'.'", "'...'", "'='", 
                     "'>'", "'<'", "'<='", "'>='", "'!='", "':'", "'->'", 
                     "'**'", "'+'", "'-'", "'*'", "'/'", "'!'", "'not'", 
                     "'@'" ]

    symbolicNames = [ "<INVALID>", "TriccText", "BooleanLiteral", "FOR", 
                      "RETURN", "IN", "IF", "THEN", "ELSE", "SOME", "EVERY", 
                      "SATISFIES", "INSTANCE", "OF", "FUNCTION", "EXTERNAL", 
                      "OR", "AND", "BETWEEN", "NULL", "UNDEFINEDVALUE", 
                      "TRUE", "FALSE", "QUOTE", "IntegerLiteral", "FloatingPointLiteral", 
                      "StringLiteral", "LPAREN", "RPAREN", "LBRACE", "RBRACE", 
                      "LBRACK", "RBRACK", "COMMA", "ELIPSIS", "DOT", "SPREAD", 
                      "EQUAL", "GT", "LT", "LE", "GE", "NOTEQUAL", "COLON", 
                      "RARROW", "POW", "ADD", "SUB", "MUL", "DIV", "BANG", 
                      "NOT", "AT", "Identifier", "WS", "COMMENT", "LINE_COMMENT", 
                      "ANY_OTHER_CHAR" ]

    RULE_cellRoot = 0
    RULE_cellTests = 1
    RULE_cellTest = 2
    RULE_cellValue = 3

    ruleNames =  [ "cellRoot", "cellTests", "cellTest", "cellValue" ]

    EOF = Token.EOF
    TriccText=1
    BooleanLiteral=2
    FOR=3
    RETURN=4
    IN=5
    IF=6
    THEN=7
    ELSE=8
    SOME=9
    EVERY=10
    SATISFIES=11
    INSTANCE=12
    OF=13
    FUNCTION=14
    EXTERNAL=15
    OR=16
    AND=17
    BETWEEN=18
    NULL=19
    UNDEFINEDVALUE=20
    TRUE=21
    FALSE=22
    QUOTE=23
    IntegerLiteral=24
    FloatingPointLiteral=25
    StringLiteral=26
    LPAREN=27
    RPAREN=28
    LBRACE=29
    RBRACE=30
    LBRACK=31
    RBRACK=32
    COMMA=33
    ELIPSIS=34
    DOT=35
    SPREAD=36
    EQUAL=37
    GT=38
    LT=39
    LE=40
    GE=41
    NOTEQUAL=42
    COLON=43
    RARROW=44
    POW=45
    ADD=46
    SUB=47
    MUL=48
    DIV=49
    BANG=50
    NOT=51
    AT=52
    Identifier=53
    WS=54
    COMMENT=55
    LINE_COMMENT=56
    ANY_OTHER_CHAR=57

    def __init__(self, input:TokenStream, output:TextIO = sys.stdout):
        super().__init__(input, output)
        self.checkVersion("4.13.2")
        self._interp = ParserATNSimulator(self, self.atn, self.decisionsToDFA, self.sharedContextCache)
        self._predicates = None




    class CellRootContext(ParserRuleContext):
        __slots__ = 'parser'

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def cellTests(self):
            return self.getTypedRuleContext(TriccFeelParser.CellTestsContext,0)


        def EOF(self):
            return self.getToken(TriccFeelParser.EOF, 0)

        def getRuleIndex(self):
            return TriccFeelParser.RULE_cellRoot

        def accept(self, visitor:ParseTreeVisitor):
            if hasattr( visitor, "visitCellRoot" ):
                return visitor.visitCellRoot(self)
            else:
                return visitor.visitChildren(self)




    def cellRoot(self):

        localctx = TriccFeelParser.CellRootContext(self, self._ctx, self.state)
        self.enterRule(localctx, 0, self.RULE_cellRoot)
        try:
            self.enterOuterAlt(localctx, 1)
            self.state = 8
            self.cellTests()
            self.state = 9
            self.match(TriccFeelParser.EOF)
        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx


    class CellTestsContext(ParserRuleContext):
        __slots__ = 'parser'

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser


        def getRuleIndex(self):
            return TriccFeelParser.RULE_cellTests

     
        def copyFrom(self, ctx:ParserRuleContext):
            super().copyFrom(ctx)



    class CellNotNullContext(CellTestsContext):

        def __init__(self, parser, ctx:ParserRuleContext): # actually a TriccFeelParser.CellTestsContext
            super().__init__(parser)
            self.copyFrom(ctx)

        def NOT(self):
            return self.getToken(TriccFeelParser.NOT, 0)
        def LPAREN(self):
            return self.getToken(TriccFeelParser.LPAREN, 0)
        def NULL(self):
            return self.getToken(TriccFeelParser.NULL, 0)
        def RPAREN(self):
            return self.getToken(TriccFeelParser.RPAREN, 0)

        def accept(self, visitor:ParseTreeVisitor):
            if hasattr( visitor, "visitCellNotNull" ):
                return visitor.visitCellNotNull(self)
            else:
                return visitor.visitChildren(self)


    class CellListContext(CellTestsContext):

        def __init__(self, parser, ctx:ParserRuleContext): # actually a TriccFeelParser.CellTestsContext
            super().__init__(parser)
            self.copyFrom(ctx)

        def cellTest(self, i:int=None):
            if i is None:
                return self.getTypedRuleContexts(TriccFeelParser.CellTestContext)
            else:
                return self.getTypedRuleContext(TriccFeelParser.CellTestContext,i)

        def COMMA(self, i:int=None):
            if i is None:
                return self.getTokens(TriccFeelParser.COMMA)
            else:
                return self.getToken(TriccFeelParser.COMMA, i)

        def accept(self, visitor:ParseTreeVisitor):
            if hasattr( visitor, "visitCellList" ):
                return visitor.visitCellList(self)
            else:
                return visitor.visitChildren(self)


    class CellAnyContext(CellTestsContext):

        def __init__(self, parser, ctx:ParserRuleContext): # actually a TriccFeelParser.CellTestsContext
            super().__init__(parser)
            self.copyFrom(ctx)

        def SUB(self):
            return self.getToken(TriccFeelParser.SUB, 0)

        def accept(self, visitor:ParseTreeVisitor):
            if hasattr( visitor, "visitCellAny" ):
                return visitor.visitCellAny(self)
            else:
                return visitor.visitChildren(self)



    def cellTests(self):

        localctx = TriccFeelParser.CellTestsContext(self, self._ctx, self.state)
        self.enterRule(localctx, 2, self.RULE_cellTests)
        self._la = 0 # Token type
        try:
            self.state = 24
            self._errHandler.sync(self)
            la_ = self._interp.adaptivePredict(self._input,1,self._ctx)
            if la_ == 1:
                localctx = TriccFeelParser.CellAnyContext(self, localctx)
                self.enterOuterAlt(localctx, 1)
                self.state = 11
                self.match(TriccFeelParser.SUB)
                pass

            elif la_ == 2:
                localctx = TriccFeelParser.CellNotNullContext(self, localctx)
                self.enterOuterAlt(localctx, 2)
                self.state = 12
                self.match(TriccFeelParser.NOT)
                self.state = 13
                self.match(TriccFeelParser.LPAREN)
                self.state = 14
                self.match(TriccFeelParser.NULL)
                self.state = 15
                self.match(TriccFeelParser.RPAREN)
                pass

            elif la_ == 3:
                localctx = TriccFeelParser.CellListContext(self, localctx)
                self.enterOuterAlt(localctx, 3)
                self.state = 16
                self.cellTest()
                self.state = 21
                self._errHandler.sync(self)
                _la = self._input.LA(1)
                while _la==33:
                    self.state = 17
                    self.match(TriccFeelParser.COMMA)
                    self.state = 18
                    self.cellTest()
                    self.state = 23
                    self._errHandler.sync(self)
                    _la = self._input.LA(1)

                pass


        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx


    class CellTestContext(ParserRuleContext):
        __slots__ = 'parser'

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser


        def getRuleIndex(self):
            return TriccFeelParser.RULE_cellTest

     
        def copyFrom(self, ctx:ParserRuleContext):
            super().copyFrom(ctx)



    class CellRangeContext(CellTestContext):

        def __init__(self, parser, ctx:ParserRuleContext): # actually a TriccFeelParser.CellTestContext
            super().__init__(parser)
            self.low = None # Token
            self.up = None # Token
            self.copyFrom(ctx)

        def cellValue(self, i:int=None):
            if i is None:
                return self.getTypedRuleContexts(TriccFeelParser.CellValueContext)
            else:
                return self.getTypedRuleContext(TriccFeelParser.CellValueContext,i)

        def ELIPSIS(self):
            return self.getToken(TriccFeelParser.ELIPSIS, 0)
        def LPAREN(self):
            return self.getToken(TriccFeelParser.LPAREN, 0)
        def LBRACK(self, i:int=None):
            if i is None:
                return self.getTokens(TriccFeelParser.LBRACK)
            else:
                return self.getToken(TriccFeelParser.LBRACK, i)
        def RBRACK(self, i:int=None):
            if i is None:
                return self.getTokens(TriccFeelParser.RBRACK)
            else:
                return self.getToken(TriccFeelParser.RBRACK, i)
        def RPAREN(self):
            return self.getToken(TriccFeelParser.RPAREN, 0)

        def accept(self, visitor:ParseTreeVisitor):
            if hasattr( visitor, "visitCellRange" ):
                return visitor.visitCellRange(self)
            else:
                return visitor.visitChildren(self)


    class CellEqualsContext(CellTestContext):

        def __init__(self, parser, ctx:ParserRuleContext): # actually a TriccFeelParser.CellTestContext
            super().__init__(parser)
            self.copyFrom(ctx)

        def cellValue(self):
            return self.getTypedRuleContext(TriccFeelParser.CellValueContext,0)


        def accept(self, visitor:ParseTreeVisitor):
            if hasattr( visitor, "visitCellEquals" ):
                return visitor.visitCellEquals(self)
            else:
                return visitor.visitChildren(self)


    class CellNullContext(CellTestContext):

        def __init__(self, parser, ctx:ParserRuleContext): # actually a TriccFeelParser.CellTestContext
            super().__init__(parser)
            self.copyFrom(ctx)

        def NULL(self):
            return self.getToken(TriccFeelParser.NULL, 0)

        def accept(self, visitor:ParseTreeVisitor):
            if hasattr( visitor, "visitCellNull" ):
                return visitor.visitCellNull(self)
            else:
                return visitor.visitChildren(self)


    class CellCompareContext(CellTestContext):

        def __init__(self, parser, ctx:ParserRuleContext): # actually a TriccFeelParser.CellTestContext
            super().__init__(parser)
            self.op = None # Token
            self.copyFrom(ctx)

        def cellValue(self):
            return self.getTypedRuleContext(TriccFeelParser.CellValueContext,0)

        def LT(self):
            return self.getToken(TriccFeelParser.LT, 0)
        def GT(self):
            return self.getToken(TriccFeelParser.GT, 0)
        def LE(self):
            return self.getToken(TriccFeelParser.LE, 0)
        def GE(self):
            return self.getToken(TriccFeelParser.GE, 0)
        def EQUAL(self):
            return self.getToken(TriccFeelParser.EQUAL, 0)

        def accept(self, visitor:ParseTreeVisitor):
            if hasattr( visitor, "visitCellCompare" ):
                return visitor.visitCellCompare(self)
            else:
                return visitor.visitChildren(self)



    def cellTest(self):

        localctx = TriccFeelParser.CellTestContext(self, self._ctx, self.state)
        self.enterRule(localctx, 4, self.RULE_cellTest)
        self._la = 0 # Token type
        try:
            self.state = 36
            self._errHandler.sync(self)
            token = self._input.LA(1)
            if token in [37, 38, 39, 40, 41]:
                localctx = TriccFeelParser.CellCompareContext(self, localctx)
                self.enterOuterAlt(localctx, 1)
                self.state = 26
                localctx.op = self._input.LT(1)
                _la = self._input.LA(1)
                if not((((_la) & ~0x3f) == 0 and ((1 << _la) & 4260607557632) != 0)):
                    localctx.op = self._errHandler.recoverInline(self)
                else:
                    self._errHandler.reportMatch(self)
                    self.consume()
                self.state = 27
                self.cellValue()
                pass
            elif token in [19]:
                localctx = TriccFeelParser.CellNullContext(self, localctx)
                self.enterOuterAlt(localctx, 2)
                self.state = 28
                self.match(TriccFeelParser.NULL)
                pass
            elif token in [27, 31, 32]:
                localctx = TriccFeelParser.CellRangeContext(self, localctx)
                self.enterOuterAlt(localctx, 3)
                self.state = 29
                localctx.low = self._input.LT(1)
                _la = self._input.LA(1)
                if not((((_la) & ~0x3f) == 0 and ((1 << _la) & 6576668672) != 0)):
                    localctx.low = self._errHandler.recoverInline(self)
                else:
                    self._errHandler.reportMatch(self)
                    self.consume()
                self.state = 30
                self.cellValue()
                self.state = 31
                self.match(TriccFeelParser.ELIPSIS)
                self.state = 32
                self.cellValue()
                self.state = 33
                localctx.up = self._input.LT(1)
                _la = self._input.LA(1)
                if not((((_la) & ~0x3f) == 0 and ((1 << _la) & 6710886400) != 0)):
                    localctx.up = self._errHandler.recoverInline(self)
                else:
                    self._errHandler.reportMatch(self)
                    self.consume()
                pass
            elif token in [1, 2, 24, 25, 26, 47]:
                localctx = TriccFeelParser.CellEqualsContext(self, localctx)
                self.enterOuterAlt(localctx, 4)
                self.state = 35
                self.cellValue()
                pass
            else:
                raise NoViableAltException(self)

        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx


    class CellValueContext(ParserRuleContext):
        __slots__ = 'parser'

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def IntegerLiteral(self):
            return self.getToken(TriccFeelParser.IntegerLiteral, 0)

        def FloatingPointLiteral(self):
            return self.getToken(TriccFeelParser.FloatingPointLiteral, 0)

        def SUB(self):
            return self.getToken(TriccFeelParser.SUB, 0)

        def TriccText(self):
            return self.getToken(TriccFeelParser.TriccText, 0)

        def StringLiteral(self):
            return self.getToken(TriccFeelParser.StringLiteral, 0)

        def BooleanLiteral(self):
            return self.getToken(TriccFeelParser.BooleanLiteral, 0)

        def getRuleIndex(self):
            return TriccFeelParser.RULE_cellValue

        def accept(self, visitor:ParseTreeVisitor):
            if hasattr( visitor, "visitCellValue" ):
                return visitor.visitCellValue(self)
            else:
                return visitor.visitChildren(self)




    def cellValue(self):

        localctx = TriccFeelParser.CellValueContext(self, self._ctx, self.state)
        self.enterRule(localctx, 6, self.RULE_cellValue)
        self._la = 0 # Token type
        try:
            self.state = 45
            self._errHandler.sync(self)
            token = self._input.LA(1)
            if token in [24, 25, 47]:
                self.enterOuterAlt(localctx, 1)
                self.state = 39
                self._errHandler.sync(self)
                _la = self._input.LA(1)
                if _la==47:
                    self.state = 38
                    self.match(TriccFeelParser.SUB)


                self.state = 41
                _la = self._input.LA(1)
                if not(_la==24 or _la==25):
                    self._errHandler.recoverInline(self)
                else:
                    self._errHandler.reportMatch(self)
                    self.consume()
                pass
            elif token in [1]:
                self.enterOuterAlt(localctx, 2)
                self.state = 42
                self.match(TriccFeelParser.TriccText)
                pass
            elif token in [26]:
                self.enterOuterAlt(localctx, 3)
                self.state = 43
                self.match(TriccFeelParser.StringLiteral)
                pass
            elif token in [2]:
                self.enterOuterAlt(localctx, 4)
                self.state = 44
                self.match(TriccFeelParser.BooleanLiteral)
                pass
            else:
                raise NoViableAltException(self)

        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx





