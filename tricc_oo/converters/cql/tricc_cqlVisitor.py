# flake8: noqa
# tricc-lang 1.0.0 (tricc_oo/lang/VERSION)
# Generated from tricc_cql.g4 by ANTLR 4.13.2
from antlr4 import *
if "." in __name__:
    from .tricc_cqlParser import tricc_cqlParser
else:
    from tricc_cqlParser import tricc_cqlParser

# This class defines a complete generic visitor for a parse tree produced by tricc_cqlParser.

class tricc_cqlVisitor(ParseTreeVisitor):

    # Visit a parse tree produced by tricc_cqlParser#triccExpression.
    def visitTriccExpression(self, ctx:tricc_cqlParser.TriccExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#timingExpression.
    def visitTimingExpression(self, ctx:tricc_cqlParser.TimingExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#notExpression.
    def visitNotExpression(self, ctx:tricc_cqlParser.NotExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#booleanExpression.
    def visitBooleanExpression(self, ctx:tricc_cqlParser.BooleanExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#orExpression.
    def visitOrExpression(self, ctx:tricc_cqlParser.OrExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#castExpression.
    def visitCastExpression(self, ctx:tricc_cqlParser.CastExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#andExpression.
    def visitAndExpression(self, ctx:tricc_cqlParser.AndExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#betweenExpression.
    def visitBetweenExpression(self, ctx:tricc_cqlParser.BetweenExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#membershipExpression.
    def visitMembershipExpression(self, ctx:tricc_cqlParser.MembershipExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#inequalityExpression.
    def visitInequalityExpression(self, ctx:tricc_cqlParser.InequalityExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#equalityExpression.
    def visitEqualityExpression(self, ctx:tricc_cqlParser.EqualityExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#existenceExpression.
    def visitExistenceExpression(self, ctx:tricc_cqlParser.ExistenceExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#impliesExpression.
    def visitImpliesExpression(self, ctx:tricc_cqlParser.ImpliesExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#negateMembershipExpression.
    def visitNegateMembershipExpression(self, ctx:tricc_cqlParser.NegateMembershipExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#termExpression.
    def visitTermExpression(self, ctx:tricc_cqlParser.TermExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#typeExpression.
    def visitTypeExpression(self, ctx:tricc_cqlParser.TypeExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#additionExpressionTerm.
    def visitAdditionExpressionTerm(self, ctx:tricc_cqlParser.AdditionExpressionTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#widthExpressionTerm.
    def visitWidthExpressionTerm(self, ctx:tricc_cqlParser.WidthExpressionTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#setAggregateExpressionTerm.
    def visitSetAggregateExpressionTerm(self, ctx:tricc_cqlParser.SetAggregateExpressionTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#timeUnitExpressionTerm.
    def visitTimeUnitExpressionTerm(self, ctx:tricc_cqlParser.TimeUnitExpressionTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#ifThenElseExpressionTerm.
    def visitIfThenElseExpressionTerm(self, ctx:tricc_cqlParser.IfThenElseExpressionTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#timeBoundaryExpressionTerm.
    def visitTimeBoundaryExpressionTerm(self, ctx:tricc_cqlParser.TimeBoundaryExpressionTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#elementExtractorExpressionTerm.
    def visitElementExtractorExpressionTerm(self, ctx:tricc_cqlParser.ElementExtractorExpressionTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#conversionExpressionTerm.
    def visitConversionExpressionTerm(self, ctx:tricc_cqlParser.ConversionExpressionTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#typeExtentExpressionTerm.
    def visitTypeExtentExpressionTerm(self, ctx:tricc_cqlParser.TypeExtentExpressionTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#predecessorExpressionTerm.
    def visitPredecessorExpressionTerm(self, ctx:tricc_cqlParser.PredecessorExpressionTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#pointExtractorExpressionTerm.
    def visitPointExtractorExpressionTerm(self, ctx:tricc_cqlParser.PointExtractorExpressionTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#multiplicationExpressionTerm.
    def visitMultiplicationExpressionTerm(self, ctx:tricc_cqlParser.MultiplicationExpressionTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#aggregateExpressionTerm.
    def visitAggregateExpressionTerm(self, ctx:tricc_cqlParser.AggregateExpressionTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#caseExpressionTerm.
    def visitCaseExpressionTerm(self, ctx:tricc_cqlParser.CaseExpressionTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#powerExpressionTerm.
    def visitPowerExpressionTerm(self, ctx:tricc_cqlParser.PowerExpressionTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#successorExpressionTerm.
    def visitSuccessorExpressionTerm(self, ctx:tricc_cqlParser.SuccessorExpressionTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#polarityExpressionTerm.
    def visitPolarityExpressionTerm(self, ctx:tricc_cqlParser.PolarityExpressionTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#termExpressionTerm.
    def visitTermExpressionTerm(self, ctx:tricc_cqlParser.TermExpressionTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#invocationTerm.
    def visitInvocationTerm(self, ctx:tricc_cqlParser.InvocationTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#literalTerm.
    def visitLiteralTerm(self, ctx:tricc_cqlParser.LiteralTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#externalConstantTerm.
    def visitExternalConstantTerm(self, ctx:tricc_cqlParser.ExternalConstantTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#intervalSelectorTerm.
    def visitIntervalSelectorTerm(self, ctx:tricc_cqlParser.IntervalSelectorTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#tupleSelectorTerm.
    def visitTupleSelectorTerm(self, ctx:tricc_cqlParser.TupleSelectorTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#instanceSelectorTerm.
    def visitInstanceSelectorTerm(self, ctx:tricc_cqlParser.InstanceSelectorTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#listSelectorTerm.
    def visitListSelectorTerm(self, ctx:tricc_cqlParser.ListSelectorTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#codeSelectorTerm.
    def visitCodeSelectorTerm(self, ctx:tricc_cqlParser.CodeSelectorTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#conceptSelectorTerm.
    def visitConceptSelectorTerm(self, ctx:tricc_cqlParser.ConceptSelectorTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#parenthesizedTerm.
    def visitParenthesizedTerm(self, ctx:tricc_cqlParser.ParenthesizedTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#placeholderTerm.
    def visitPlaceholderTerm(self, ctx:tricc_cqlParser.PlaceholderTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#booleanLiteral.
    def visitBooleanLiteral(self, ctx:tricc_cqlParser.BooleanLiteralContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#nullLiteral.
    def visitNullLiteral(self, ctx:tricc_cqlParser.NullLiteralContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#stringLiteral.
    def visitStringLiteral(self, ctx:tricc_cqlParser.StringLiteralContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#numberLiteral.
    def visitNumberLiteral(self, ctx:tricc_cqlParser.NumberLiteralContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#longNumberLiteral.
    def visitLongNumberLiteral(self, ctx:tricc_cqlParser.LongNumberLiteralContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#dateTimeLiteral.
    def visitDateTimeLiteral(self, ctx:tricc_cqlParser.DateTimeLiteralContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#dateLiteral.
    def visitDateLiteral(self, ctx:tricc_cqlParser.DateLiteralContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#timeLiteral.
    def visitTimeLiteral(self, ctx:tricc_cqlParser.TimeLiteralContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#definition.
    def visitDefinition(self, ctx:tricc_cqlParser.DefinitionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#library.
    def visitLibrary(self, ctx:tricc_cqlParser.LibraryContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#libraryDefinition.
    def visitLibraryDefinition(self, ctx:tricc_cqlParser.LibraryDefinitionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#usingDefinition.
    def visitUsingDefinition(self, ctx:tricc_cqlParser.UsingDefinitionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#includeDefinition.
    def visitIncludeDefinition(self, ctx:tricc_cqlParser.IncludeDefinitionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#localIdentifier.
    def visitLocalIdentifier(self, ctx:tricc_cqlParser.LocalIdentifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#accessModifier.
    def visitAccessModifier(self, ctx:tricc_cqlParser.AccessModifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#parameterDefinition.
    def visitParameterDefinition(self, ctx:tricc_cqlParser.ParameterDefinitionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#codesystemDefinition.
    def visitCodesystemDefinition(self, ctx:tricc_cqlParser.CodesystemDefinitionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#valuesetDefinition.
    def visitValuesetDefinition(self, ctx:tricc_cqlParser.ValuesetDefinitionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#codesystems.
    def visitCodesystems(self, ctx:tricc_cqlParser.CodesystemsContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#codesystemIdentifier.
    def visitCodesystemIdentifier(self, ctx:tricc_cqlParser.CodesystemIdentifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#libraryIdentifier.
    def visitLibraryIdentifier(self, ctx:tricc_cqlParser.LibraryIdentifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#codeDefinition.
    def visitCodeDefinition(self, ctx:tricc_cqlParser.CodeDefinitionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#conceptDefinition.
    def visitConceptDefinition(self, ctx:tricc_cqlParser.ConceptDefinitionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#codeIdentifier.
    def visitCodeIdentifier(self, ctx:tricc_cqlParser.CodeIdentifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#codesystemId.
    def visitCodesystemId(self, ctx:tricc_cqlParser.CodesystemIdContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#valuesetId.
    def visitValuesetId(self, ctx:tricc_cqlParser.ValuesetIdContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#versionSpecifier.
    def visitVersionSpecifier(self, ctx:tricc_cqlParser.VersionSpecifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#codeId.
    def visitCodeId(self, ctx:tricc_cqlParser.CodeIdContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#typeSpecifier.
    def visitTypeSpecifier(self, ctx:tricc_cqlParser.TypeSpecifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#namedTypeSpecifier.
    def visitNamedTypeSpecifier(self, ctx:tricc_cqlParser.NamedTypeSpecifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#modelIdentifier.
    def visitModelIdentifier(self, ctx:tricc_cqlParser.ModelIdentifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#listTypeSpecifier.
    def visitListTypeSpecifier(self, ctx:tricc_cqlParser.ListTypeSpecifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#intervalTypeSpecifier.
    def visitIntervalTypeSpecifier(self, ctx:tricc_cqlParser.IntervalTypeSpecifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#tupleTypeSpecifier.
    def visitTupleTypeSpecifier(self, ctx:tricc_cqlParser.TupleTypeSpecifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#tupleElementDefinition.
    def visitTupleElementDefinition(self, ctx:tricc_cqlParser.TupleElementDefinitionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#choiceTypeSpecifier.
    def visitChoiceTypeSpecifier(self, ctx:tricc_cqlParser.ChoiceTypeSpecifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#statement.
    def visitStatement(self, ctx:tricc_cqlParser.StatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#expressionDefinition.
    def visitExpressionDefinition(self, ctx:tricc_cqlParser.ExpressionDefinitionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#contextDefinition.
    def visitContextDefinition(self, ctx:tricc_cqlParser.ContextDefinitionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#fluentModifier.
    def visitFluentModifier(self, ctx:tricc_cqlParser.FluentModifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#functionDefinition.
    def visitFunctionDefinition(self, ctx:tricc_cqlParser.FunctionDefinitionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#operandDefinition.
    def visitOperandDefinition(self, ctx:tricc_cqlParser.OperandDefinitionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#functionBody.
    def visitFunctionBody(self, ctx:tricc_cqlParser.FunctionBodyContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#querySource.
    def visitQuerySource(self, ctx:tricc_cqlParser.QuerySourceContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#aliasedQuerySource.
    def visitAliasedQuerySource(self, ctx:tricc_cqlParser.AliasedQuerySourceContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#alias.
    def visitAlias(self, ctx:tricc_cqlParser.AliasContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#queryInclusionClause.
    def visitQueryInclusionClause(self, ctx:tricc_cqlParser.QueryInclusionClauseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#withClause.
    def visitWithClause(self, ctx:tricc_cqlParser.WithClauseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#withoutClause.
    def visitWithoutClause(self, ctx:tricc_cqlParser.WithoutClauseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#retrieve.
    def visitRetrieve(self, ctx:tricc_cqlParser.RetrieveContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#contextIdentifier.
    def visitContextIdentifier(self, ctx:tricc_cqlParser.ContextIdentifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#codePath.
    def visitCodePath(self, ctx:tricc_cqlParser.CodePathContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#codeComparator.
    def visitCodeComparator(self, ctx:tricc_cqlParser.CodeComparatorContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#terminology.
    def visitTerminology(self, ctx:tricc_cqlParser.TerminologyContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#qualifier.
    def visitQualifier(self, ctx:tricc_cqlParser.QualifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#query.
    def visitQuery(self, ctx:tricc_cqlParser.QueryContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#sourceClause.
    def visitSourceClause(self, ctx:tricc_cqlParser.SourceClauseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#letClause.
    def visitLetClause(self, ctx:tricc_cqlParser.LetClauseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#letClauseItem.
    def visitLetClauseItem(self, ctx:tricc_cqlParser.LetClauseItemContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#whereClause.
    def visitWhereClause(self, ctx:tricc_cqlParser.WhereClauseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#returnClause.
    def visitReturnClause(self, ctx:tricc_cqlParser.ReturnClauseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#aggregateClause.
    def visitAggregateClause(self, ctx:tricc_cqlParser.AggregateClauseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#startingClause.
    def visitStartingClause(self, ctx:tricc_cqlParser.StartingClauseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#sortClause.
    def visitSortClause(self, ctx:tricc_cqlParser.SortClauseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#sortDirection.
    def visitSortDirection(self, ctx:tricc_cqlParser.SortDirectionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#sortByItem.
    def visitSortByItem(self, ctx:tricc_cqlParser.SortByItemContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#qualifiedIdentifier.
    def visitQualifiedIdentifier(self, ctx:tricc_cqlParser.QualifiedIdentifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#qualifiedIdentifierExpression.
    def visitQualifiedIdentifierExpression(self, ctx:tricc_cqlParser.QualifiedIdentifierExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#qualifierExpression.
    def visitQualifierExpression(self, ctx:tricc_cqlParser.QualifierExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#simplePathIndexer.
    def visitSimplePathIndexer(self, ctx:tricc_cqlParser.SimplePathIndexerContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#simplePathQualifiedIdentifier.
    def visitSimplePathQualifiedIdentifier(self, ctx:tricc_cqlParser.SimplePathQualifiedIdentifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#simplePathReferentialIdentifier.
    def visitSimplePathReferentialIdentifier(self, ctx:tricc_cqlParser.SimplePathReferentialIdentifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#simpleStringLiteral.
    def visitSimpleStringLiteral(self, ctx:tricc_cqlParser.SimpleStringLiteralContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#simpleNumberLiteral.
    def visitSimpleNumberLiteral(self, ctx:tricc_cqlParser.SimpleNumberLiteralContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#dateTimePrecision.
    def visitDateTimePrecision(self, ctx:tricc_cqlParser.DateTimePrecisionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#dateTimeComponent.
    def visitDateTimeComponent(self, ctx:tricc_cqlParser.DateTimeComponentContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#pluralDateTimePrecision.
    def visitPluralDateTimePrecision(self, ctx:tricc_cqlParser.PluralDateTimePrecisionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#caseExpressionItem.
    def visitCaseExpressionItem(self, ctx:tricc_cqlParser.CaseExpressionItemContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#dateTimePrecisionSpecifier.
    def visitDateTimePrecisionSpecifier(self, ctx:tricc_cqlParser.DateTimePrecisionSpecifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#relativeQualifier.
    def visitRelativeQualifier(self, ctx:tricc_cqlParser.RelativeQualifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#offsetRelativeQualifier.
    def visitOffsetRelativeQualifier(self, ctx:tricc_cqlParser.OffsetRelativeQualifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#exclusiveRelativeQualifier.
    def visitExclusiveRelativeQualifier(self, ctx:tricc_cqlParser.ExclusiveRelativeQualifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#quantityOffset.
    def visitQuantityOffset(self, ctx:tricc_cqlParser.QuantityOffsetContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#temporalRelationship.
    def visitTemporalRelationship(self, ctx:tricc_cqlParser.TemporalRelationshipContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#concurrentWithIntervalOperatorPhrase.
    def visitConcurrentWithIntervalOperatorPhrase(self, ctx:tricc_cqlParser.ConcurrentWithIntervalOperatorPhraseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#includesIntervalOperatorPhrase.
    def visitIncludesIntervalOperatorPhrase(self, ctx:tricc_cqlParser.IncludesIntervalOperatorPhraseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#includedInIntervalOperatorPhrase.
    def visitIncludedInIntervalOperatorPhrase(self, ctx:tricc_cqlParser.IncludedInIntervalOperatorPhraseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#beforeOrAfterIntervalOperatorPhrase.
    def visitBeforeOrAfterIntervalOperatorPhrase(self, ctx:tricc_cqlParser.BeforeOrAfterIntervalOperatorPhraseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#withinIntervalOperatorPhrase.
    def visitWithinIntervalOperatorPhrase(self, ctx:tricc_cqlParser.WithinIntervalOperatorPhraseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#meetsIntervalOperatorPhrase.
    def visitMeetsIntervalOperatorPhrase(self, ctx:tricc_cqlParser.MeetsIntervalOperatorPhraseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#overlapsIntervalOperatorPhrase.
    def visitOverlapsIntervalOperatorPhrase(self, ctx:tricc_cqlParser.OverlapsIntervalOperatorPhraseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#startsIntervalOperatorPhrase.
    def visitStartsIntervalOperatorPhrase(self, ctx:tricc_cqlParser.StartsIntervalOperatorPhraseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#endsIntervalOperatorPhrase.
    def visitEndsIntervalOperatorPhrase(self, ctx:tricc_cqlParser.EndsIntervalOperatorPhraseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#qualifiedMemberInvocation.
    def visitQualifiedMemberInvocation(self, ctx:tricc_cqlParser.QualifiedMemberInvocationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#qualifiedFunctionInvocation.
    def visitQualifiedFunctionInvocation(self, ctx:tricc_cqlParser.QualifiedFunctionInvocationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#qualifiedFunction.
    def visitQualifiedFunction(self, ctx:tricc_cqlParser.QualifiedFunctionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#memberInvocation.
    def visitMemberInvocation(self, ctx:tricc_cqlParser.MemberInvocationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#functionInvocation.
    def visitFunctionInvocation(self, ctx:tricc_cqlParser.FunctionInvocationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#thisInvocation.
    def visitThisInvocation(self, ctx:tricc_cqlParser.ThisInvocationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#indexInvocation.
    def visitIndexInvocation(self, ctx:tricc_cqlParser.IndexInvocationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#totalInvocation.
    def visitTotalInvocation(self, ctx:tricc_cqlParser.TotalInvocationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#function.
    def visitFunction(self, ctx:tricc_cqlParser.FunctionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#ratio.
    def visitRatio(self, ctx:tricc_cqlParser.RatioContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#externalConstant.
    def visitExternalConstant(self, ctx:tricc_cqlParser.ExternalConstantContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#intervalSelector.
    def visitIntervalSelector(self, ctx:tricc_cqlParser.IntervalSelectorContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#tupleSelector.
    def visitTupleSelector(self, ctx:tricc_cqlParser.TupleSelectorContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#tupleElementSelector.
    def visitTupleElementSelector(self, ctx:tricc_cqlParser.TupleElementSelectorContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#instanceSelector.
    def visitInstanceSelector(self, ctx:tricc_cqlParser.InstanceSelectorContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#instanceElementSelector.
    def visitInstanceElementSelector(self, ctx:tricc_cqlParser.InstanceElementSelectorContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#listSelector.
    def visitListSelector(self, ctx:tricc_cqlParser.ListSelectorContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#displayClause.
    def visitDisplayClause(self, ctx:tricc_cqlParser.DisplayClauseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#codeSelector.
    def visitCodeSelector(self, ctx:tricc_cqlParser.CodeSelectorContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#conceptSelector.
    def visitConceptSelector(self, ctx:tricc_cqlParser.ConceptSelectorContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#keyword.
    def visitKeyword(self, ctx:tricc_cqlParser.KeywordContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#reservedWord.
    def visitReservedWord(self, ctx:tricc_cqlParser.ReservedWordContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#keywordIdentifier.
    def visitKeywordIdentifier(self, ctx:tricc_cqlParser.KeywordIdentifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#obsoleteIdentifier.
    def visitObsoleteIdentifier(self, ctx:tricc_cqlParser.ObsoleteIdentifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#functionIdentifier.
    def visitFunctionIdentifier(self, ctx:tricc_cqlParser.FunctionIdentifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#typeNameIdentifier.
    def visitTypeNameIdentifier(self, ctx:tricc_cqlParser.TypeNameIdentifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#referentialIdentifier.
    def visitReferentialIdentifier(self, ctx:tricc_cqlParser.ReferentialIdentifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#referentialOrTypeNameIdentifier.
    def visitReferentialOrTypeNameIdentifier(self, ctx:tricc_cqlParser.ReferentialOrTypeNameIdentifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#identifierOrFunctionIdentifier.
    def visitIdentifierOrFunctionIdentifier(self, ctx:tricc_cqlParser.IdentifierOrFunctionIdentifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#identifier.
    def visitIdentifier(self, ctx:tricc_cqlParser.IdentifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#paramList.
    def visitParamList(self, ctx:tricc_cqlParser.ParamListContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#quantity.
    def visitQuantity(self, ctx:tricc_cqlParser.QuantityContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by tricc_cqlParser#unit.
    def visitUnit(self, ctx:tricc_cqlParser.UnitContext):
        return self.visitChildren(ctx)



del tricc_cqlParser