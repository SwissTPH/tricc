// TRICC FEEL parser: decision-table cells (feature/20261125-expression-languages.md §1.5).
//
// Written from the DMN simple unary tests (DMN 1.6 chapter 10, grammar rules #7-#18), over the
// upstream KIE lexer (tricc_feel.g4). Type checks (a range on a text column, a text in a number
// column) are in the visitor, not here.
parser grammar TriccFeelParser;

options { tokenVocab = tricc_feelLexer; }

// an input cell
cellRoot
    : cellTests EOF
    ;

cellTests
    : SUB                                 #cellAny
    | NOT LPAREN NULL RPAREN              #cellNotNull
    | cellTest (COMMA cellTest)*          #cellList
    ;

cellTest
    : op=(LT | GT | LE | GE | EQUAL) cellValue                                               #cellCompare
    | NULL                                                                                   #cellNull
    | low=(LPAREN | LBRACK | RBRACK) cellValue ELIPSIS cellValue up=(RPAREN | RBRACK | LBRACK) #cellRange
    | cellValue                                                                              #cellEquals
    ;

cellValue
    : SUB? (IntegerLiteral | FloatingPointLiteral)
    | TriccText
    | StringLiteral
    | BooleanLiteral
    ;
