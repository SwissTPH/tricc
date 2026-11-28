// TRICC CQL profile (feature/20261125-expression-languages.md §1.2).
//
// Imports the untouched upstream HL7 grammar (cql.g4, which imports fhirpath.g4, tag v5.7.0)
// and overrides whole rules. Upstream alternative labels are kept, so the generated visitor
// methods keep their names. Every change from upstream is listed in README.md.
grammar tricc_cql;

import cql;

// Entry rule for one expression (a calculate, a condition, an argument).
triccExpression
    : expression EOF
    ;

// upstream `expression` without #retrieveExpression, #queryExpression, #inFixSetExpression
// (| union intersect except), #durationBetweenExpression and #differenceBetweenExpression
// (plural precisions); with #negateMembershipExpression (`x not in y`, not standard CQL)
expression
    : expressionTerm                                                                                #termExpression
    | expression 'is' 'not'? ('null' | 'true' | 'false')                                            #booleanExpression
    | expression ('is' | 'as') typeSpecifier                                                        #typeExpression
    | 'cast' expression 'as' typeSpecifier                                                          #castExpression
    | 'not' expression                                                                              #notExpression
    | 'exists' expression                                                                           #existenceExpression
    | expression 'properly'? 'between' expressionTerm 'and' expressionTerm                          #betweenExpression
    | expression ('<=' | '<' | '>' | '>=') expression                                               #inequalityExpression
    | expression intervalOperatorPhrase expression                                                  #timingExpression
    | expression ('=' | '!=' | '~' | '!~') expression                                               #equalityExpression
    | expression ('in' | 'contains') dateTimePrecisionSpecifier? expression                         #membershipExpression
    | expression 'not' ('in' | 'contains') dateTimePrecisionSpecifier? expression                   #negateMembershipExpression
    | expression 'and' expression                                                                   #andExpression
    | expression ('or' | 'xor') expression                                                          #orExpression
    | expression 'implies' expression                                                               #impliesExpression
    ;

// upstream `expressionTerm` without #invocationExpressionTerm (x.member, fluent x.f()),
// #indexedExpressionTerm (x[0]), #durationExpressionTerm and #differenceExpressionTerm
// (plural precisions)
expressionTerm
    : term                                                                          #termExpressionTerm
    | 'convert' expression 'to' (typeSpecifier | unit)                              #conversionExpressionTerm
    | ('+' | '-') expressionTerm                                                    #polarityExpressionTerm
    | ('start' | 'end') 'of' expressionTerm                                         #timeBoundaryExpressionTerm
    | dateTimeComponent 'from' expressionTerm                                       #timeUnitExpressionTerm
    | 'width' 'of' expressionTerm                                                   #widthExpressionTerm
    | 'successor' 'of' expressionTerm                                               #successorExpressionTerm
    | 'predecessor' 'of' expressionTerm                                             #predecessorExpressionTerm
    | 'singleton' 'from' expressionTerm                                             #elementExtractorExpressionTerm
    | 'point' 'from' expressionTerm                                                 #pointExtractorExpressionTerm
    | ('minimum' | 'maximum') namedTypeSpecifier                                    #typeExtentExpressionTerm
    | expressionTerm '^' expressionTerm                                             #powerExpressionTerm
    | expressionTerm ('*' | '/' | 'div' | 'mod') expressionTerm                     #multiplicationExpressionTerm
    | expressionTerm ('+' | '-' | '&') expressionTerm                               #additionExpressionTerm
    | 'if' expression 'then' expression 'else' expression                           #ifThenElseExpressionTerm
    | 'case' expression? caseExpressionItem+ 'else' expression 'end'                #caseExpressionTerm
    | ('distinct' | 'flatten') expression                                           #aggregateExpressionTerm
    | ('expand' | 'collapse') expression ('per' (dateTimePrecision | expression))?  #setAggregateExpressionTerm
    ;

// upstream `term` with #placeholderTerm ({{name}}, {{name | raw}})
term
    : invocation            #invocationTerm
    | literal               #literalTerm
    | externalConstant      #externalConstantTerm
    | intervalSelector      #intervalSelectorTerm
    | tupleSelector         #tupleSelectorTerm
    | instanceSelector      #instanceSelectorTerm
    | listSelector          #listSelectorTerm
    | codeSelector          #codeSelectorTerm
    | conceptSelector       #conceptSelectorTerm
    | '(' expression ')'    #parenthesizedTerm
    | PLACEHOLDER           #placeholderTerm
    ;

// upstream `literal` without #quantityLiteral and #ratioLiteral (units)
literal
    : ('true' | 'false')                                    #booleanLiteral
    | 'null'                                                #nullLiteral
    | STRING                                                #stringLiteral
    | NUMBER                                                #numberLiteral
    | LONGNUMBER                                            #longNumberLiteral
    | DATETIME                                              #dateTimeLiteral
    | DATE                                                  #dateLiteral
    | TIME                                                  #timeLiteral
    ;

// A block parameter, rendered before the build: `{{name}}`, `{{name | raw}}`
PLACEHOLDER
    : '{{' WS* IDENTIFIER WS* ('|' WS* 'raw' WS*)? '}}'
    ;
