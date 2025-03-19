# Generated from cql.g4 by ANTLR 4.13.2
from antlr4 import *
if "." in __name__:
    from .cqlParser import cqlParser
else:
    from cqlParser import cqlParser

# This class defines a complete generic visitor for a parse tree produced by cqlParser.

class cqlVisitor(ParseTreeVisitor):

    # Visit a parse tree produced by cqlParser#definition.
    def visitDefinition(self, ctx:cqlParser.DefinitionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#library.
    def visitLibrary(self, ctx:cqlParser.LibraryContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#libraryDefinition.
    def visitLibraryDefinition(self, ctx:cqlParser.LibraryDefinitionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#usingDefinition.
    def visitUsingDefinition(self, ctx:cqlParser.UsingDefinitionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#includeDefinition.
    def visitIncludeDefinition(self, ctx:cqlParser.IncludeDefinitionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#localIdentifier.
    def visitLocalIdentifier(self, ctx:cqlParser.LocalIdentifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#accessModifier.
    def visitAccessModifier(self, ctx:cqlParser.AccessModifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#parameterDefinition.
    def visitParameterDefinition(self, ctx:cqlParser.ParameterDefinitionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#codesystemDefinition.
    def visitCodesystemDefinition(self, ctx:cqlParser.CodesystemDefinitionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#valuesetDefinition.
    def visitValuesetDefinition(self, ctx:cqlParser.ValuesetDefinitionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#codesystems.
    def visitCodesystems(self, ctx:cqlParser.CodesystemsContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#codesystemIdentifier.
    def visitCodesystemIdentifier(self, ctx:cqlParser.CodesystemIdentifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#libraryIdentifier.
    def visitLibraryIdentifier(self, ctx:cqlParser.LibraryIdentifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#codeDefinition.
    def visitCodeDefinition(self, ctx:cqlParser.CodeDefinitionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#conceptDefinition.
    def visitConceptDefinition(self, ctx:cqlParser.ConceptDefinitionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#codeIdentifier.
    def visitCodeIdentifier(self, ctx:cqlParser.CodeIdentifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#codesystemId.
    def visitCodesystemId(self, ctx:cqlParser.CodesystemIdContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#valuesetId.
    def visitValuesetId(self, ctx:cqlParser.ValuesetIdContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#versionSpecifier.
    def visitVersionSpecifier(self, ctx:cqlParser.VersionSpecifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#codeId.
    def visitCodeId(self, ctx:cqlParser.CodeIdContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#typeSpecifier.
    def visitTypeSpecifier(self, ctx:cqlParser.TypeSpecifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#namedTypeSpecifier.
    def visitNamedTypeSpecifier(self, ctx:cqlParser.NamedTypeSpecifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#modelIdentifier.
    def visitModelIdentifier(self, ctx:cqlParser.ModelIdentifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#listTypeSpecifier.
    def visitListTypeSpecifier(self, ctx:cqlParser.ListTypeSpecifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#intervalTypeSpecifier.
    def visitIntervalTypeSpecifier(self, ctx:cqlParser.IntervalTypeSpecifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#tupleTypeSpecifier.
    def visitTupleTypeSpecifier(self, ctx:cqlParser.TupleTypeSpecifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#tupleElementDefinition.
    def visitTupleElementDefinition(self, ctx:cqlParser.TupleElementDefinitionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#choiceTypeSpecifier.
    def visitChoiceTypeSpecifier(self, ctx:cqlParser.ChoiceTypeSpecifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#statement.
    def visitStatement(self, ctx:cqlParser.StatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#expressionDefinition.
    def visitExpressionDefinition(self, ctx:cqlParser.ExpressionDefinitionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#contextDefinition.
    def visitContextDefinition(self, ctx:cqlParser.ContextDefinitionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#fluentModifier.
    def visitFluentModifier(self, ctx:cqlParser.FluentModifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#functionDefinition.
    def visitFunctionDefinition(self, ctx:cqlParser.FunctionDefinitionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#operandDefinition.
    def visitOperandDefinition(self, ctx:cqlParser.OperandDefinitionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#functionBody.
    def visitFunctionBody(self, ctx:cqlParser.FunctionBodyContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#querySource.
    def visitQuerySource(self, ctx:cqlParser.QuerySourceContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#aliasedQuerySource.
    def visitAliasedQuerySource(self, ctx:cqlParser.AliasedQuerySourceContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#alias.
    def visitAlias(self, ctx:cqlParser.AliasContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#queryInclusionClause.
    def visitQueryInclusionClause(self, ctx:cqlParser.QueryInclusionClauseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#withClause.
    def visitWithClause(self, ctx:cqlParser.WithClauseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#withoutClause.
    def visitWithoutClause(self, ctx:cqlParser.WithoutClauseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#retrieve.
    def visitRetrieve(self, ctx:cqlParser.RetrieveContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#contextIdentifier.
    def visitContextIdentifier(self, ctx:cqlParser.ContextIdentifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#codePath.
    def visitCodePath(self, ctx:cqlParser.CodePathContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#codeComparator.
    def visitCodeComparator(self, ctx:cqlParser.CodeComparatorContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#terminology.
    def visitTerminology(self, ctx:cqlParser.TerminologyContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#qualifier.
    def visitQualifier(self, ctx:cqlParser.QualifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#query.
    def visitQuery(self, ctx:cqlParser.QueryContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#sourceClause.
    def visitSourceClause(self, ctx:cqlParser.SourceClauseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#letClause.
    def visitLetClause(self, ctx:cqlParser.LetClauseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#letClauseItem.
    def visitLetClauseItem(self, ctx:cqlParser.LetClauseItemContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#whereClause.
    def visitWhereClause(self, ctx:cqlParser.WhereClauseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#returnClause.
    def visitReturnClause(self, ctx:cqlParser.ReturnClauseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#aggregateClause.
    def visitAggregateClause(self, ctx:cqlParser.AggregateClauseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#startingClause.
    def visitStartingClause(self, ctx:cqlParser.StartingClauseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#sortClause.
    def visitSortClause(self, ctx:cqlParser.SortClauseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#sortDirection.
    def visitSortDirection(self, ctx:cqlParser.SortDirectionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#sortByItem.
    def visitSortByItem(self, ctx:cqlParser.SortByItemContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#qualifiedIdentifier.
    def visitQualifiedIdentifier(self, ctx:cqlParser.QualifiedIdentifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#qualifiedIdentifierExpression.
    def visitQualifiedIdentifierExpression(self, ctx:cqlParser.QualifiedIdentifierExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#qualifierExpression.
    def visitQualifierExpression(self, ctx:cqlParser.QualifierExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#simplePathIndexer.
    def visitSimplePathIndexer(self, ctx:cqlParser.SimplePathIndexerContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#simplePathQualifiedIdentifier.
    def visitSimplePathQualifiedIdentifier(self, ctx:cqlParser.SimplePathQualifiedIdentifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#simplePathReferentialIdentifier.
    def visitSimplePathReferentialIdentifier(self, ctx:cqlParser.SimplePathReferentialIdentifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#simpleStringLiteral.
    def visitSimpleStringLiteral(self, ctx:cqlParser.SimpleStringLiteralContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#simpleNumberLiteral.
    def visitSimpleNumberLiteral(self, ctx:cqlParser.SimpleNumberLiteralContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#durationBetweenExpression.
    def visitDurationBetweenExpression(self, ctx:cqlParser.DurationBetweenExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#inFixSetExpression.
    def visitInFixSetExpression(self, ctx:cqlParser.InFixSetExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#retrieveExpression.
    def visitRetrieveExpression(self, ctx:cqlParser.RetrieveExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#timingExpression.
    def visitTimingExpression(self, ctx:cqlParser.TimingExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#queryExpression.
    def visitQueryExpression(self, ctx:cqlParser.QueryExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#notExpression.
    def visitNotExpression(self, ctx:cqlParser.NotExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#booleanExpression.
    def visitBooleanExpression(self, ctx:cqlParser.BooleanExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#orExpression.
    def visitOrExpression(self, ctx:cqlParser.OrExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#castExpression.
    def visitCastExpression(self, ctx:cqlParser.CastExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#andExpression.
    def visitAndExpression(self, ctx:cqlParser.AndExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#betweenExpression.
    def visitBetweenExpression(self, ctx:cqlParser.BetweenExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#membershipExpression.
    def visitMembershipExpression(self, ctx:cqlParser.MembershipExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#differenceBetweenExpression.
    def visitDifferenceBetweenExpression(self, ctx:cqlParser.DifferenceBetweenExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#inequalityExpression.
    def visitInequalityExpression(self, ctx:cqlParser.InequalityExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#equalityExpression.
    def visitEqualityExpression(self, ctx:cqlParser.EqualityExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#existenceExpression.
    def visitExistenceExpression(self, ctx:cqlParser.ExistenceExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#impliesExpression.
    def visitImpliesExpression(self, ctx:cqlParser.ImpliesExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#negateMembershipExpression.
    def visitNegateMembershipExpression(self, ctx:cqlParser.NegateMembershipExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#termExpression.
    def visitTermExpression(self, ctx:cqlParser.TermExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#typeExpression.
    def visitTypeExpression(self, ctx:cqlParser.TypeExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#dateTimePrecision.
    def visitDateTimePrecision(self, ctx:cqlParser.DateTimePrecisionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#dateTimeComponent.
    def visitDateTimeComponent(self, ctx:cqlParser.DateTimeComponentContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#pluralDateTimePrecision.
    def visitPluralDateTimePrecision(self, ctx:cqlParser.PluralDateTimePrecisionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#additionExpressionTerm.
    def visitAdditionExpressionTerm(self, ctx:cqlParser.AdditionExpressionTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#indexedExpressionTerm.
    def visitIndexedExpressionTerm(self, ctx:cqlParser.IndexedExpressionTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#widthExpressionTerm.
    def visitWidthExpressionTerm(self, ctx:cqlParser.WidthExpressionTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#setAggregateExpressionTerm.
    def visitSetAggregateExpressionTerm(self, ctx:cqlParser.SetAggregateExpressionTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#timeUnitExpressionTerm.
    def visitTimeUnitExpressionTerm(self, ctx:cqlParser.TimeUnitExpressionTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#ifThenElseExpressionTerm.
    def visitIfThenElseExpressionTerm(self, ctx:cqlParser.IfThenElseExpressionTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#timeBoundaryExpressionTerm.
    def visitTimeBoundaryExpressionTerm(self, ctx:cqlParser.TimeBoundaryExpressionTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#elementExtractorExpressionTerm.
    def visitElementExtractorExpressionTerm(self, ctx:cqlParser.ElementExtractorExpressionTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#conversionExpressionTerm.
    def visitConversionExpressionTerm(self, ctx:cqlParser.ConversionExpressionTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#typeExtentExpressionTerm.
    def visitTypeExtentExpressionTerm(self, ctx:cqlParser.TypeExtentExpressionTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#predecessorExpressionTerm.
    def visitPredecessorExpressionTerm(self, ctx:cqlParser.PredecessorExpressionTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#pointExtractorExpressionTerm.
    def visitPointExtractorExpressionTerm(self, ctx:cqlParser.PointExtractorExpressionTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#multiplicationExpressionTerm.
    def visitMultiplicationExpressionTerm(self, ctx:cqlParser.MultiplicationExpressionTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#aggregateExpressionTerm.
    def visitAggregateExpressionTerm(self, ctx:cqlParser.AggregateExpressionTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#durationExpressionTerm.
    def visitDurationExpressionTerm(self, ctx:cqlParser.DurationExpressionTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#differenceExpressionTerm.
    def visitDifferenceExpressionTerm(self, ctx:cqlParser.DifferenceExpressionTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#caseExpressionTerm.
    def visitCaseExpressionTerm(self, ctx:cqlParser.CaseExpressionTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#powerExpressionTerm.
    def visitPowerExpressionTerm(self, ctx:cqlParser.PowerExpressionTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#successorExpressionTerm.
    def visitSuccessorExpressionTerm(self, ctx:cqlParser.SuccessorExpressionTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#polarityExpressionTerm.
    def visitPolarityExpressionTerm(self, ctx:cqlParser.PolarityExpressionTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#termExpressionTerm.
    def visitTermExpressionTerm(self, ctx:cqlParser.TermExpressionTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#invocationExpressionTerm.
    def visitInvocationExpressionTerm(self, ctx:cqlParser.InvocationExpressionTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#caseExpressionItem.
    def visitCaseExpressionItem(self, ctx:cqlParser.CaseExpressionItemContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#dateTimePrecisionSpecifier.
    def visitDateTimePrecisionSpecifier(self, ctx:cqlParser.DateTimePrecisionSpecifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#relativeQualifier.
    def visitRelativeQualifier(self, ctx:cqlParser.RelativeQualifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#offsetRelativeQualifier.
    def visitOffsetRelativeQualifier(self, ctx:cqlParser.OffsetRelativeQualifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#exclusiveRelativeQualifier.
    def visitExclusiveRelativeQualifier(self, ctx:cqlParser.ExclusiveRelativeQualifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#quantityOffset.
    def visitQuantityOffset(self, ctx:cqlParser.QuantityOffsetContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#temporalRelationship.
    def visitTemporalRelationship(self, ctx:cqlParser.TemporalRelationshipContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#concurrentWithIntervalOperatorPhrase.
    def visitConcurrentWithIntervalOperatorPhrase(self, ctx:cqlParser.ConcurrentWithIntervalOperatorPhraseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#includesIntervalOperatorPhrase.
    def visitIncludesIntervalOperatorPhrase(self, ctx:cqlParser.IncludesIntervalOperatorPhraseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#includedInIntervalOperatorPhrase.
    def visitIncludedInIntervalOperatorPhrase(self, ctx:cqlParser.IncludedInIntervalOperatorPhraseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#beforeOrAfterIntervalOperatorPhrase.
    def visitBeforeOrAfterIntervalOperatorPhrase(self, ctx:cqlParser.BeforeOrAfterIntervalOperatorPhraseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#withinIntervalOperatorPhrase.
    def visitWithinIntervalOperatorPhrase(self, ctx:cqlParser.WithinIntervalOperatorPhraseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#meetsIntervalOperatorPhrase.
    def visitMeetsIntervalOperatorPhrase(self, ctx:cqlParser.MeetsIntervalOperatorPhraseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#overlapsIntervalOperatorPhrase.
    def visitOverlapsIntervalOperatorPhrase(self, ctx:cqlParser.OverlapsIntervalOperatorPhraseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#startsIntervalOperatorPhrase.
    def visitStartsIntervalOperatorPhrase(self, ctx:cqlParser.StartsIntervalOperatorPhraseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#endsIntervalOperatorPhrase.
    def visitEndsIntervalOperatorPhrase(self, ctx:cqlParser.EndsIntervalOperatorPhraseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#invocationTerm.
    def visitInvocationTerm(self, ctx:cqlParser.InvocationTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#literalTerm.
    def visitLiteralTerm(self, ctx:cqlParser.LiteralTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#externalConstantTerm.
    def visitExternalConstantTerm(self, ctx:cqlParser.ExternalConstantTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#intervalSelectorTerm.
    def visitIntervalSelectorTerm(self, ctx:cqlParser.IntervalSelectorTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#tupleSelectorTerm.
    def visitTupleSelectorTerm(self, ctx:cqlParser.TupleSelectorTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#instanceSelectorTerm.
    def visitInstanceSelectorTerm(self, ctx:cqlParser.InstanceSelectorTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#listSelectorTerm.
    def visitListSelectorTerm(self, ctx:cqlParser.ListSelectorTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#codeSelectorTerm.
    def visitCodeSelectorTerm(self, ctx:cqlParser.CodeSelectorTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#conceptSelectorTerm.
    def visitConceptSelectorTerm(self, ctx:cqlParser.ConceptSelectorTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#parenthesizedTerm.
    def visitParenthesizedTerm(self, ctx:cqlParser.ParenthesizedTermContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#qualifiedMemberInvocation.
    def visitQualifiedMemberInvocation(self, ctx:cqlParser.QualifiedMemberInvocationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#qualifiedFunctionInvocation.
    def visitQualifiedFunctionInvocation(self, ctx:cqlParser.QualifiedFunctionInvocationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#qualifiedFunction.
    def visitQualifiedFunction(self, ctx:cqlParser.QualifiedFunctionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#memberInvocation.
    def visitMemberInvocation(self, ctx:cqlParser.MemberInvocationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#functionInvocation.
    def visitFunctionInvocation(self, ctx:cqlParser.FunctionInvocationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#thisInvocation.
    def visitThisInvocation(self, ctx:cqlParser.ThisInvocationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#indexInvocation.
    def visitIndexInvocation(self, ctx:cqlParser.IndexInvocationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#totalInvocation.
    def visitTotalInvocation(self, ctx:cqlParser.TotalInvocationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#function.
    def visitFunction(self, ctx:cqlParser.FunctionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#ratio.
    def visitRatio(self, ctx:cqlParser.RatioContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#booleanLiteral.
    def visitBooleanLiteral(self, ctx:cqlParser.BooleanLiteralContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#nullLiteral.
    def visitNullLiteral(self, ctx:cqlParser.NullLiteralContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#stringLiteral.
    def visitStringLiteral(self, ctx:cqlParser.StringLiteralContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#numberLiteral.
    def visitNumberLiteral(self, ctx:cqlParser.NumberLiteralContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#longNumberLiteral.
    def visitLongNumberLiteral(self, ctx:cqlParser.LongNumberLiteralContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#dateTimeLiteral.
    def visitDateTimeLiteral(self, ctx:cqlParser.DateTimeLiteralContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#dateLiteral.
    def visitDateLiteral(self, ctx:cqlParser.DateLiteralContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#timeLiteral.
    def visitTimeLiteral(self, ctx:cqlParser.TimeLiteralContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#quantityLiteral.
    def visitQuantityLiteral(self, ctx:cqlParser.QuantityLiteralContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#ratioLiteral.
    def visitRatioLiteral(self, ctx:cqlParser.RatioLiteralContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#intervalSelector.
    def visitIntervalSelector(self, ctx:cqlParser.IntervalSelectorContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#tupleSelector.
    def visitTupleSelector(self, ctx:cqlParser.TupleSelectorContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#tupleElementSelector.
    def visitTupleElementSelector(self, ctx:cqlParser.TupleElementSelectorContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#instanceSelector.
    def visitInstanceSelector(self, ctx:cqlParser.InstanceSelectorContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#instanceElementSelector.
    def visitInstanceElementSelector(self, ctx:cqlParser.InstanceElementSelectorContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#listSelector.
    def visitListSelector(self, ctx:cqlParser.ListSelectorContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#displayClause.
    def visitDisplayClause(self, ctx:cqlParser.DisplayClauseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#codeSelector.
    def visitCodeSelector(self, ctx:cqlParser.CodeSelectorContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#conceptSelector.
    def visitConceptSelector(self, ctx:cqlParser.ConceptSelectorContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#keyword.
    def visitKeyword(self, ctx:cqlParser.KeywordContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#reservedWord.
    def visitReservedWord(self, ctx:cqlParser.ReservedWordContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#keywordIdentifier.
    def visitKeywordIdentifier(self, ctx:cqlParser.KeywordIdentifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#obsoleteIdentifier.
    def visitObsoleteIdentifier(self, ctx:cqlParser.ObsoleteIdentifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#functionIdentifier.
    def visitFunctionIdentifier(self, ctx:cqlParser.FunctionIdentifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#typeNameIdentifier.
    def visitTypeNameIdentifier(self, ctx:cqlParser.TypeNameIdentifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#referentialIdentifier.
    def visitReferentialIdentifier(self, ctx:cqlParser.ReferentialIdentifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#referentialOrTypeNameIdentifier.
    def visitReferentialOrTypeNameIdentifier(self, ctx:cqlParser.ReferentialOrTypeNameIdentifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#identifierOrFunctionIdentifier.
    def visitIdentifierOrFunctionIdentifier(self, ctx:cqlParser.IdentifierOrFunctionIdentifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#identifier.
    def visitIdentifier(self, ctx:cqlParser.IdentifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#externalConstant.
    def visitExternalConstant(self, ctx:cqlParser.ExternalConstantContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#paramList.
    def visitParamList(self, ctx:cqlParser.ParamListContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#quantity.
    def visitQuantity(self, ctx:cqlParser.QuantityContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by cqlParser#unit.
    def visitUnit(self, ctx:cqlParser.UnitContext):
        return self.visitChildren(ctx)



del cqlParser