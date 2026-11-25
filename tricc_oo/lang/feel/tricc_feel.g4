// TRICC FEEL lexer (feature/20261125-expression-languages.md §1.5).
//
// Imports the untouched upstream Apache KIE grammar FEEL_1_1.g4 (release 10.2.0) for its lexer
// only: its parser rules carry Java actions and cannot be generated for Python or TypeScript.
// The generation script keeps the generated lexer (tricc_feelLexer) and drops the parser;
// TriccFeelParser.g4 is the parser.
grammar tricc_feel;

import FEEL_1_1;

// TRICC's 'text' (FEEL writes "text"); '' or \' escapes a quote
TriccText
    : '\'' ( ~['\\\r\n] | '\\' . | '\'\'' )* '\''
    ;
