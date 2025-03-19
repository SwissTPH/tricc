# Generated from cql.g4 by ANTLR 4.13.2
from antlr4 import *
if "." in __name__:
    from .cqlParser import cqlParser
else:
    from cqlParser import cqlParser

# This class defines a complete listener for a parse tree produced by cqlParser.
class cqlListener(ParseTreeListener):

    # Enter a parse tree produced by cqlParser#definition.
    def enterDefinition(self, ctx:cqlParser.DefinitionContext):
        pass

    # Exit a parse tree produced by cqlParser#definition.
    def exitDefinition(self, ctx:cqlParser.DefinitionContext):
        pass


    # Enter a parse tree produced by cqlParser#library.
    def enterLibrary(self, ctx:cqlParser.LibraryContext):
        pass

    # Exit a parse tree produced by cqlParser#library.
    def exitLibrary(self, ctx:cqlParser.LibraryContext):
        pass


    # Enter a parse tree produced by cqlParser#libraryDefinition.
    def enterLibraryDefinition(self, ctx:cqlParser.LibraryDefinitionContext):
        pass

    # Exit a parse tree produced by cqlParser#libraryDefinition.
    def exitLibraryDefinition(self, ctx:cqlParser.LibraryDefinitionContext):
        pass


    # Enter a parse tree produced by cqlParser#usingDefinition.
    def enterUsingDefinition(self, ctx:cqlParser.UsingDefinitionContext):
        pass

    # Exit a parse tree produced by cqlParser#usingDefinition.
    def exitUsingDefinition(self, ctx:cqlParser.UsingDefinitionContext):
        pass


    # Enter a parse tree produced by cqlParser#includeDefinition.
    def enterIncludeDefinition(self, ctx:cqlParser.IncludeDefinitionContext):
        pass

    # Exit a parse tree produced by cqlParser#includeDefinition.
    def exitIncludeDefinition(self, ctx:cqlParser.IncludeDefinitionContext):
        pass


    # Enter a parse tree produced by cqlParser#localIdentifier.
    def enterLocalIdentifier(self, ctx:cqlParser.LocalIdentifierContext):
        pass

    # Exit a parse tree produced by cqlParser#localIdentifier.
    def exitLocalIdentifier(self, ctx:cqlParser.LocalIdentifierContext):
        pass


    # Enter a parse tree produced by cqlParser#accessModifier.
    def enterAccessModifier(self, ctx:cqlParser.AccessModifierContext):
        pass

    # Exit a parse tree produced by cqlParser#accessModifier.
    def exitAccessModifier(self, ctx:cqlParser.AccessModifierContext):
        pass


    # Enter a parse tree produced by cqlParser#parameterDefinition.
    def enterParameterDefinition(self, ctx:cqlParser.ParameterDefinitionContext):
        pass

    # Exit a parse tree produced by cqlParser#parameterDefinition.
    def exitParameterDefinition(self, ctx:cqlParser.ParameterDefinitionContext):
        pass


    # Enter a parse tree produced by cqlParser#codesystemDefinition.
    def enterCodesystemDefinition(self, ctx:cqlParser.CodesystemDefinitionContext):
        pass

    # Exit a parse tree produced by cqlParser#codesystemDefinition.
    def exitCodesystemDefinition(self, ctx:cqlParser.CodesystemDefinitionContext):
        pass


    # Enter a parse tree produced by cqlParser#valuesetDefinition.
    def enterValuesetDefinition(self, ctx:cqlParser.ValuesetDefinitionContext):
        pass

    # Exit a parse tree produced by cqlParser#valuesetDefinition.
    def exitValuesetDefinition(self, ctx:cqlParser.ValuesetDefinitionContext):
        pass


    # Enter a parse tree produced by cqlParser#codesystems.
    def enterCodesystems(self, ctx:cqlParser.CodesystemsContext):
        pass

    # Exit a parse tree produced by cqlParser#codesystems.
    def exitCodesystems(self, ctx:cqlParser.CodesystemsContext):
        pass


    # Enter a parse tree produced by cqlParser#codesystemIdentifier.
    def enterCodesystemIdentifier(self, ctx:cqlParser.CodesystemIdentifierContext):
        pass

    # Exit a parse tree produced by cqlParser#codesystemIdentifier.
    def exitCodesystemIdentifier(self, ctx:cqlParser.CodesystemIdentifierContext):
        pass


    # Enter a parse tree produced by cqlParser#libraryIdentifier.
    def enterLibraryIdentifier(self, ctx:cqlParser.LibraryIdentifierContext):
        pass

    # Exit a parse tree produced by cqlParser#libraryIdentifier.
    def exitLibraryIdentifier(self, ctx:cqlParser.LibraryIdentifierContext):
        pass


    # Enter a parse tree produced by cqlParser#codeDefinition.
    def enterCodeDefinition(self, ctx:cqlParser.CodeDefinitionContext):
        pass

    # Exit a parse tree produced by cqlParser#codeDefinition.
    def exitCodeDefinition(self, ctx:cqlParser.CodeDefinitionContext):
        pass


    # Enter a parse tree produced by cqlParser#conceptDefinition.
    def enterConceptDefinition(self, ctx:cqlParser.ConceptDefinitionContext):
        pass

    # Exit a parse tree produced by cqlParser#conceptDefinition.
    def exitConceptDefinition(self, ctx:cqlParser.ConceptDefinitionContext):
        pass


    # Enter a parse tree produced by cqlParser#codeIdentifier.
    def enterCodeIdentifier(self, ctx:cqlParser.CodeIdentifierContext):
        pass

    # Exit a parse tree produced by cqlParser#codeIdentifier.
    def exitCodeIdentifier(self, ctx:cqlParser.CodeIdentifierContext):
        pass


    # Enter a parse tree produced by cqlParser#codesystemId.
    def enterCodesystemId(self, ctx:cqlParser.CodesystemIdContext):
        pass

    # Exit a parse tree produced by cqlParser#codesystemId.
    def exitCodesystemId(self, ctx:cqlParser.CodesystemIdContext):
        pass


    # Enter a parse tree produced by cqlParser#valuesetId.
    def enterValuesetId(self, ctx:cqlParser.ValuesetIdContext):
        pass

    # Exit a parse tree produced by cqlParser#valuesetId.
    def exitValuesetId(self, ctx:cqlParser.ValuesetIdContext):
        pass


    # Enter a parse tree produced by cqlParser#versionSpecifier.
    def enterVersionSpecifier(self, ctx:cqlParser.VersionSpecifierContext):
        pass

    # Exit a parse tree produced by cqlParser#versionSpecifier.
    def exitVersionSpecifier(self, ctx:cqlParser.VersionSpecifierContext):
        pass


    # Enter a parse tree produced by cqlParser#codeId.
    def enterCodeId(self, ctx:cqlParser.CodeIdContext):
        pass

    # Exit a parse tree produced by cqlParser#codeId.
    def exitCodeId(self, ctx:cqlParser.CodeIdContext):
        pass


    # Enter a parse tree produced by cqlParser#typeSpecifier.
    def enterTypeSpecifier(self, ctx:cqlParser.TypeSpecifierContext):
        pass

    # Exit a parse tree produced by cqlParser#typeSpecifier.
    def exitTypeSpecifier(self, ctx:cqlParser.TypeSpecifierContext):
        pass


    # Enter a parse tree produced by cqlParser#namedTypeSpecifier.
    def enterNamedTypeSpecifier(self, ctx:cqlParser.NamedTypeSpecifierContext):
        pass

    # Exit a parse tree produced by cqlParser#namedTypeSpecifier.
    def exitNamedTypeSpecifier(self, ctx:cqlParser.NamedTypeSpecifierContext):
        pass


    # Enter a parse tree produced by cqlParser#modelIdentifier.
    def enterModelIdentifier(self, ctx:cqlParser.ModelIdentifierContext):
        pass

    # Exit a parse tree produced by cqlParser#modelIdentifier.
    def exitModelIdentifier(self, ctx:cqlParser.ModelIdentifierContext):
        pass


    # Enter a parse tree produced by cqlParser#listTypeSpecifier.
    def enterListTypeSpecifier(self, ctx:cqlParser.ListTypeSpecifierContext):
        pass

    # Exit a parse tree produced by cqlParser#listTypeSpecifier.
    def exitListTypeSpecifier(self, ctx:cqlParser.ListTypeSpecifierContext):
        pass


    # Enter a parse tree produced by cqlParser#intervalTypeSpecifier.
    def enterIntervalTypeSpecifier(self, ctx:cqlParser.IntervalTypeSpecifierContext):
        pass

    # Exit a parse tree produced by cqlParser#intervalTypeSpecifier.
    def exitIntervalTypeSpecifier(self, ctx:cqlParser.IntervalTypeSpecifierContext):
        pass


    # Enter a parse tree produced by cqlParser#tupleTypeSpecifier.
    def enterTupleTypeSpecifier(self, ctx:cqlParser.TupleTypeSpecifierContext):
        pass

    # Exit a parse tree produced by cqlParser#tupleTypeSpecifier.
    def exitTupleTypeSpecifier(self, ctx:cqlParser.TupleTypeSpecifierContext):
        pass


    # Enter a parse tree produced by cqlParser#tupleElementDefinition.
    def enterTupleElementDefinition(self, ctx:cqlParser.TupleElementDefinitionContext):
        pass

    # Exit a parse tree produced by cqlParser#tupleElementDefinition.
    def exitTupleElementDefinition(self, ctx:cqlParser.TupleElementDefinitionContext):
        pass


    # Enter a parse tree produced by cqlParser#choiceTypeSpecifier.
    def enterChoiceTypeSpecifier(self, ctx:cqlParser.ChoiceTypeSpecifierContext):
        pass

    # Exit a parse tree produced by cqlParser#choiceTypeSpecifier.
    def exitChoiceTypeSpecifier(self, ctx:cqlParser.ChoiceTypeSpecifierContext):
        pass


    # Enter a parse tree produced by cqlParser#statement.
    def enterStatement(self, ctx:cqlParser.StatementContext):
        pass

    # Exit a parse tree produced by cqlParser#statement.
    def exitStatement(self, ctx:cqlParser.StatementContext):
        pass


    # Enter a parse tree produced by cqlParser#expressionDefinition.
    def enterExpressionDefinition(self, ctx:cqlParser.ExpressionDefinitionContext):
        pass

    # Exit a parse tree produced by cqlParser#expressionDefinition.
    def exitExpressionDefinition(self, ctx:cqlParser.ExpressionDefinitionContext):
        pass


    # Enter a parse tree produced by cqlParser#contextDefinition.
    def enterContextDefinition(self, ctx:cqlParser.ContextDefinitionContext):
        pass

    # Exit a parse tree produced by cqlParser#contextDefinition.
    def exitContextDefinition(self, ctx:cqlParser.ContextDefinitionContext):
        pass


    # Enter a parse tree produced by cqlParser#fluentModifier.
    def enterFluentModifier(self, ctx:cqlParser.FluentModifierContext):
        pass

    # Exit a parse tree produced by cqlParser#fluentModifier.
    def exitFluentModifier(self, ctx:cqlParser.FluentModifierContext):
        pass


    # Enter a parse tree produced by cqlParser#functionDefinition.
    def enterFunctionDefinition(self, ctx:cqlParser.FunctionDefinitionContext):
        pass

    # Exit a parse tree produced by cqlParser#functionDefinition.
    def exitFunctionDefinition(self, ctx:cqlParser.FunctionDefinitionContext):
        pass


    # Enter a parse tree produced by cqlParser#operandDefinition.
    def enterOperandDefinition(self, ctx:cqlParser.OperandDefinitionContext):
        pass

    # Exit a parse tree produced by cqlParser#operandDefinition.
    def exitOperandDefinition(self, ctx:cqlParser.OperandDefinitionContext):
        pass


    # Enter a parse tree produced by cqlParser#functionBody.
    def enterFunctionBody(self, ctx:cqlParser.FunctionBodyContext):
        pass

    # Exit a parse tree produced by cqlParser#functionBody.
    def exitFunctionBody(self, ctx:cqlParser.FunctionBodyContext):
        pass


    # Enter a parse tree produced by cqlParser#querySource.
    def enterQuerySource(self, ctx:cqlParser.QuerySourceContext):
        pass

    # Exit a parse tree produced by cqlParser#querySource.
    def exitQuerySource(self, ctx:cqlParser.QuerySourceContext):
        pass


    # Enter a parse tree produced by cqlParser#aliasedQuerySource.
    def enterAliasedQuerySource(self, ctx:cqlParser.AliasedQuerySourceContext):
        pass

    # Exit a parse tree produced by cqlParser#aliasedQuerySource.
    def exitAliasedQuerySource(self, ctx:cqlParser.AliasedQuerySourceContext):
        pass


    # Enter a parse tree produced by cqlParser#alias.
    def enterAlias(self, ctx:cqlParser.AliasContext):
        pass

    # Exit a parse tree produced by cqlParser#alias.
    def exitAlias(self, ctx:cqlParser.AliasContext):
        pass


    # Enter a parse tree produced by cqlParser#queryInclusionClause.
    def enterQueryInclusionClause(self, ctx:cqlParser.QueryInclusionClauseContext):
        pass

    # Exit a parse tree produced by cqlParser#queryInclusionClause.
    def exitQueryInclusionClause(self, ctx:cqlParser.QueryInclusionClauseContext):
        pass


    # Enter a parse tree produced by cqlParser#withClause.
    def enterWithClause(self, ctx:cqlParser.WithClauseContext):
        pass

    # Exit a parse tree produced by cqlParser#withClause.
    def exitWithClause(self, ctx:cqlParser.WithClauseContext):
        pass


    # Enter a parse tree produced by cqlParser#withoutClause.
    def enterWithoutClause(self, ctx:cqlParser.WithoutClauseContext):
        pass

    # Exit a parse tree produced by cqlParser#withoutClause.
    def exitWithoutClause(self, ctx:cqlParser.WithoutClauseContext):
        pass


    # Enter a parse tree produced by cqlParser#retrieve.
    def enterRetrieve(self, ctx:cqlParser.RetrieveContext):
        pass

    # Exit a parse tree produced by cqlParser#retrieve.
    def exitRetrieve(self, ctx:cqlParser.RetrieveContext):
        pass


    # Enter a parse tree produced by cqlParser#contextIdentifier.
    def enterContextIdentifier(self, ctx:cqlParser.ContextIdentifierContext):
        pass

    # Exit a parse tree produced by cqlParser#contextIdentifier.
    def exitContextIdentifier(self, ctx:cqlParser.ContextIdentifierContext):
        pass


    # Enter a parse tree produced by cqlParser#codePath.
    def enterCodePath(self, ctx:cqlParser.CodePathContext):
        pass

    # Exit a parse tree produced by cqlParser#codePath.
    def exitCodePath(self, ctx:cqlParser.CodePathContext):
        pass


    # Enter a parse tree produced by cqlParser#codeComparator.
    def enterCodeComparator(self, ctx:cqlParser.CodeComparatorContext):
        pass

    # Exit a parse tree produced by cqlParser#codeComparator.
    def exitCodeComparator(self, ctx:cqlParser.CodeComparatorContext):
        pass


    # Enter a parse tree produced by cqlParser#terminology.
    def enterTerminology(self, ctx:cqlParser.TerminologyContext):
        pass

    # Exit a parse tree produced by cqlParser#terminology.
    def exitTerminology(self, ctx:cqlParser.TerminologyContext):
        pass


    # Enter a parse tree produced by cqlParser#qualifier.
    def enterQualifier(self, ctx:cqlParser.QualifierContext):
        pass

    # Exit a parse tree produced by cqlParser#qualifier.
    def exitQualifier(self, ctx:cqlParser.QualifierContext):
        pass


    # Enter a parse tree produced by cqlParser#query.
    def enterQuery(self, ctx:cqlParser.QueryContext):
        pass

    # Exit a parse tree produced by cqlParser#query.
    def exitQuery(self, ctx:cqlParser.QueryContext):
        pass


    # Enter a parse tree produced by cqlParser#sourceClause.
    def enterSourceClause(self, ctx:cqlParser.SourceClauseContext):
        pass

    # Exit a parse tree produced by cqlParser#sourceClause.
    def exitSourceClause(self, ctx:cqlParser.SourceClauseContext):
        pass


    # Enter a parse tree produced by cqlParser#letClause.
    def enterLetClause(self, ctx:cqlParser.LetClauseContext):
        pass

    # Exit a parse tree produced by cqlParser#letClause.
    def exitLetClause(self, ctx:cqlParser.LetClauseContext):
        pass


    # Enter a parse tree produced by cqlParser#letClauseItem.
    def enterLetClauseItem(self, ctx:cqlParser.LetClauseItemContext):
        pass

    # Exit a parse tree produced by cqlParser#letClauseItem.
    def exitLetClauseItem(self, ctx:cqlParser.LetClauseItemContext):
        pass


    # Enter a parse tree produced by cqlParser#whereClause.
    def enterWhereClause(self, ctx:cqlParser.WhereClauseContext):
        pass

    # Exit a parse tree produced by cqlParser#whereClause.
    def exitWhereClause(self, ctx:cqlParser.WhereClauseContext):
        pass


    # Enter a parse tree produced by cqlParser#returnClause.
    def enterReturnClause(self, ctx:cqlParser.ReturnClauseContext):
        pass

    # Exit a parse tree produced by cqlParser#returnClause.
    def exitReturnClause(self, ctx:cqlParser.ReturnClauseContext):
        pass


    # Enter a parse tree produced by cqlParser#aggregateClause.
    def enterAggregateClause(self, ctx:cqlParser.AggregateClauseContext):
        pass

    # Exit a parse tree produced by cqlParser#aggregateClause.
    def exitAggregateClause(self, ctx:cqlParser.AggregateClauseContext):
        pass


    # Enter a parse tree produced by cqlParser#startingClause.
    def enterStartingClause(self, ctx:cqlParser.StartingClauseContext):
        pass

    # Exit a parse tree produced by cqlParser#startingClause.
    def exitStartingClause(self, ctx:cqlParser.StartingClauseContext):
        pass


    # Enter a parse tree produced by cqlParser#sortClause.
    def enterSortClause(self, ctx:cqlParser.SortClauseContext):
        pass

    # Exit a parse tree produced by cqlParser#sortClause.
    def exitSortClause(self, ctx:cqlParser.SortClauseContext):
        pass


    # Enter a parse tree produced by cqlParser#sortDirection.
    def enterSortDirection(self, ctx:cqlParser.SortDirectionContext):
        pass

    # Exit a parse tree produced by cqlParser#sortDirection.
    def exitSortDirection(self, ctx:cqlParser.SortDirectionContext):
        pass


    # Enter a parse tree produced by cqlParser#sortByItem.
    def enterSortByItem(self, ctx:cqlParser.SortByItemContext):
        pass

    # Exit a parse tree produced by cqlParser#sortByItem.
    def exitSortByItem(self, ctx:cqlParser.SortByItemContext):
        pass


    # Enter a parse tree produced by cqlParser#qualifiedIdentifier.
    def enterQualifiedIdentifier(self, ctx:cqlParser.QualifiedIdentifierContext):
        pass

    # Exit a parse tree produced by cqlParser#qualifiedIdentifier.
    def exitQualifiedIdentifier(self, ctx:cqlParser.QualifiedIdentifierContext):
        pass


    # Enter a parse tree produced by cqlParser#qualifiedIdentifierExpression.
    def enterQualifiedIdentifierExpression(self, ctx:cqlParser.QualifiedIdentifierExpressionContext):
        pass

    # Exit a parse tree produced by cqlParser#qualifiedIdentifierExpression.
    def exitQualifiedIdentifierExpression(self, ctx:cqlParser.QualifiedIdentifierExpressionContext):
        pass


    # Enter a parse tree produced by cqlParser#qualifierExpression.
    def enterQualifierExpression(self, ctx:cqlParser.QualifierExpressionContext):
        pass

    # Exit a parse tree produced by cqlParser#qualifierExpression.
    def exitQualifierExpression(self, ctx:cqlParser.QualifierExpressionContext):
        pass


    # Enter a parse tree produced by cqlParser#simplePathIndexer.
    def enterSimplePathIndexer(self, ctx:cqlParser.SimplePathIndexerContext):
        pass

    # Exit a parse tree produced by cqlParser#simplePathIndexer.
    def exitSimplePathIndexer(self, ctx:cqlParser.SimplePathIndexerContext):
        pass


    # Enter a parse tree produced by cqlParser#simplePathQualifiedIdentifier.
    def enterSimplePathQualifiedIdentifier(self, ctx:cqlParser.SimplePathQualifiedIdentifierContext):
        pass

    # Exit a parse tree produced by cqlParser#simplePathQualifiedIdentifier.
    def exitSimplePathQualifiedIdentifier(self, ctx:cqlParser.SimplePathQualifiedIdentifierContext):
        pass


    # Enter a parse tree produced by cqlParser#simplePathReferentialIdentifier.
    def enterSimplePathReferentialIdentifier(self, ctx:cqlParser.SimplePathReferentialIdentifierContext):
        pass

    # Exit a parse tree produced by cqlParser#simplePathReferentialIdentifier.
    def exitSimplePathReferentialIdentifier(self, ctx:cqlParser.SimplePathReferentialIdentifierContext):
        pass


    # Enter a parse tree produced by cqlParser#simpleStringLiteral.
    def enterSimpleStringLiteral(self, ctx:cqlParser.SimpleStringLiteralContext):
        pass

    # Exit a parse tree produced by cqlParser#simpleStringLiteral.
    def exitSimpleStringLiteral(self, ctx:cqlParser.SimpleStringLiteralContext):
        pass


    # Enter a parse tree produced by cqlParser#simpleNumberLiteral.
    def enterSimpleNumberLiteral(self, ctx:cqlParser.SimpleNumberLiteralContext):
        pass

    # Exit a parse tree produced by cqlParser#simpleNumberLiteral.
    def exitSimpleNumberLiteral(self, ctx:cqlParser.SimpleNumberLiteralContext):
        pass


    # Enter a parse tree produced by cqlParser#durationBetweenExpression.
    def enterDurationBetweenExpression(self, ctx:cqlParser.DurationBetweenExpressionContext):
        pass

    # Exit a parse tree produced by cqlParser#durationBetweenExpression.
    def exitDurationBetweenExpression(self, ctx:cqlParser.DurationBetweenExpressionContext):
        pass


    # Enter a parse tree produced by cqlParser#inFixSetExpression.
    def enterInFixSetExpression(self, ctx:cqlParser.InFixSetExpressionContext):
        pass

    # Exit a parse tree produced by cqlParser#inFixSetExpression.
    def exitInFixSetExpression(self, ctx:cqlParser.InFixSetExpressionContext):
        pass


    # Enter a parse tree produced by cqlParser#retrieveExpression.
    def enterRetrieveExpression(self, ctx:cqlParser.RetrieveExpressionContext):
        pass

    # Exit a parse tree produced by cqlParser#retrieveExpression.
    def exitRetrieveExpression(self, ctx:cqlParser.RetrieveExpressionContext):
        pass


    # Enter a parse tree produced by cqlParser#timingExpression.
    def enterTimingExpression(self, ctx:cqlParser.TimingExpressionContext):
        pass

    # Exit a parse tree produced by cqlParser#timingExpression.
    def exitTimingExpression(self, ctx:cqlParser.TimingExpressionContext):
        pass


    # Enter a parse tree produced by cqlParser#queryExpression.
    def enterQueryExpression(self, ctx:cqlParser.QueryExpressionContext):
        pass

    # Exit a parse tree produced by cqlParser#queryExpression.
    def exitQueryExpression(self, ctx:cqlParser.QueryExpressionContext):
        pass


    # Enter a parse tree produced by cqlParser#notExpression.
    def enterNotExpression(self, ctx:cqlParser.NotExpressionContext):
        pass

    # Exit a parse tree produced by cqlParser#notExpression.
    def exitNotExpression(self, ctx:cqlParser.NotExpressionContext):
        pass


    # Enter a parse tree produced by cqlParser#booleanExpression.
    def enterBooleanExpression(self, ctx:cqlParser.BooleanExpressionContext):
        pass

    # Exit a parse tree produced by cqlParser#booleanExpression.
    def exitBooleanExpression(self, ctx:cqlParser.BooleanExpressionContext):
        pass


    # Enter a parse tree produced by cqlParser#orExpression.
    def enterOrExpression(self, ctx:cqlParser.OrExpressionContext):
        pass

    # Exit a parse tree produced by cqlParser#orExpression.
    def exitOrExpression(self, ctx:cqlParser.OrExpressionContext):
        pass


    # Enter a parse tree produced by cqlParser#castExpression.
    def enterCastExpression(self, ctx:cqlParser.CastExpressionContext):
        pass

    # Exit a parse tree produced by cqlParser#castExpression.
    def exitCastExpression(self, ctx:cqlParser.CastExpressionContext):
        pass


    # Enter a parse tree produced by cqlParser#andExpression.
    def enterAndExpression(self, ctx:cqlParser.AndExpressionContext):
        pass

    # Exit a parse tree produced by cqlParser#andExpression.
    def exitAndExpression(self, ctx:cqlParser.AndExpressionContext):
        pass


    # Enter a parse tree produced by cqlParser#betweenExpression.
    def enterBetweenExpression(self, ctx:cqlParser.BetweenExpressionContext):
        pass

    # Exit a parse tree produced by cqlParser#betweenExpression.
    def exitBetweenExpression(self, ctx:cqlParser.BetweenExpressionContext):
        pass


    # Enter a parse tree produced by cqlParser#membershipExpression.
    def enterMembershipExpression(self, ctx:cqlParser.MembershipExpressionContext):
        pass

    # Exit a parse tree produced by cqlParser#membershipExpression.
    def exitMembershipExpression(self, ctx:cqlParser.MembershipExpressionContext):
        pass


    # Enter a parse tree produced by cqlParser#differenceBetweenExpression.
    def enterDifferenceBetweenExpression(self, ctx:cqlParser.DifferenceBetweenExpressionContext):
        pass

    # Exit a parse tree produced by cqlParser#differenceBetweenExpression.
    def exitDifferenceBetweenExpression(self, ctx:cqlParser.DifferenceBetweenExpressionContext):
        pass


    # Enter a parse tree produced by cqlParser#inequalityExpression.
    def enterInequalityExpression(self, ctx:cqlParser.InequalityExpressionContext):
        pass

    # Exit a parse tree produced by cqlParser#inequalityExpression.
    def exitInequalityExpression(self, ctx:cqlParser.InequalityExpressionContext):
        pass


    # Enter a parse tree produced by cqlParser#equalityExpression.
    def enterEqualityExpression(self, ctx:cqlParser.EqualityExpressionContext):
        pass

    # Exit a parse tree produced by cqlParser#equalityExpression.
    def exitEqualityExpression(self, ctx:cqlParser.EqualityExpressionContext):
        pass


    # Enter a parse tree produced by cqlParser#existenceExpression.
    def enterExistenceExpression(self, ctx:cqlParser.ExistenceExpressionContext):
        pass

    # Exit a parse tree produced by cqlParser#existenceExpression.
    def exitExistenceExpression(self, ctx:cqlParser.ExistenceExpressionContext):
        pass


    # Enter a parse tree produced by cqlParser#impliesExpression.
    def enterImpliesExpression(self, ctx:cqlParser.ImpliesExpressionContext):
        pass

    # Exit a parse tree produced by cqlParser#impliesExpression.
    def exitImpliesExpression(self, ctx:cqlParser.ImpliesExpressionContext):
        pass


    # Enter a parse tree produced by cqlParser#negateMembershipExpression.
    def enterNegateMembershipExpression(self, ctx:cqlParser.NegateMembershipExpressionContext):
        pass

    # Exit a parse tree produced by cqlParser#negateMembershipExpression.
    def exitNegateMembershipExpression(self, ctx:cqlParser.NegateMembershipExpressionContext):
        pass


    # Enter a parse tree produced by cqlParser#termExpression.
    def enterTermExpression(self, ctx:cqlParser.TermExpressionContext):
        pass

    # Exit a parse tree produced by cqlParser#termExpression.
    def exitTermExpression(self, ctx:cqlParser.TermExpressionContext):
        pass


    # Enter a parse tree produced by cqlParser#typeExpression.
    def enterTypeExpression(self, ctx:cqlParser.TypeExpressionContext):
        pass

    # Exit a parse tree produced by cqlParser#typeExpression.
    def exitTypeExpression(self, ctx:cqlParser.TypeExpressionContext):
        pass


    # Enter a parse tree produced by cqlParser#dateTimePrecision.
    def enterDateTimePrecision(self, ctx:cqlParser.DateTimePrecisionContext):
        pass

    # Exit a parse tree produced by cqlParser#dateTimePrecision.
    def exitDateTimePrecision(self, ctx:cqlParser.DateTimePrecisionContext):
        pass


    # Enter a parse tree produced by cqlParser#dateTimeComponent.
    def enterDateTimeComponent(self, ctx:cqlParser.DateTimeComponentContext):
        pass

    # Exit a parse tree produced by cqlParser#dateTimeComponent.
    def exitDateTimeComponent(self, ctx:cqlParser.DateTimeComponentContext):
        pass


    # Enter a parse tree produced by cqlParser#pluralDateTimePrecision.
    def enterPluralDateTimePrecision(self, ctx:cqlParser.PluralDateTimePrecisionContext):
        pass

    # Exit a parse tree produced by cqlParser#pluralDateTimePrecision.
    def exitPluralDateTimePrecision(self, ctx:cqlParser.PluralDateTimePrecisionContext):
        pass


    # Enter a parse tree produced by cqlParser#additionExpressionTerm.
    def enterAdditionExpressionTerm(self, ctx:cqlParser.AdditionExpressionTermContext):
        pass

    # Exit a parse tree produced by cqlParser#additionExpressionTerm.
    def exitAdditionExpressionTerm(self, ctx:cqlParser.AdditionExpressionTermContext):
        pass


    # Enter a parse tree produced by cqlParser#indexedExpressionTerm.
    def enterIndexedExpressionTerm(self, ctx:cqlParser.IndexedExpressionTermContext):
        pass

    # Exit a parse tree produced by cqlParser#indexedExpressionTerm.
    def exitIndexedExpressionTerm(self, ctx:cqlParser.IndexedExpressionTermContext):
        pass


    # Enter a parse tree produced by cqlParser#widthExpressionTerm.
    def enterWidthExpressionTerm(self, ctx:cqlParser.WidthExpressionTermContext):
        pass

    # Exit a parse tree produced by cqlParser#widthExpressionTerm.
    def exitWidthExpressionTerm(self, ctx:cqlParser.WidthExpressionTermContext):
        pass


    # Enter a parse tree produced by cqlParser#setAggregateExpressionTerm.
    def enterSetAggregateExpressionTerm(self, ctx:cqlParser.SetAggregateExpressionTermContext):
        pass

    # Exit a parse tree produced by cqlParser#setAggregateExpressionTerm.
    def exitSetAggregateExpressionTerm(self, ctx:cqlParser.SetAggregateExpressionTermContext):
        pass


    # Enter a parse tree produced by cqlParser#timeUnitExpressionTerm.
    def enterTimeUnitExpressionTerm(self, ctx:cqlParser.TimeUnitExpressionTermContext):
        pass

    # Exit a parse tree produced by cqlParser#timeUnitExpressionTerm.
    def exitTimeUnitExpressionTerm(self, ctx:cqlParser.TimeUnitExpressionTermContext):
        pass


    # Enter a parse tree produced by cqlParser#ifThenElseExpressionTerm.
    def enterIfThenElseExpressionTerm(self, ctx:cqlParser.IfThenElseExpressionTermContext):
        pass

    # Exit a parse tree produced by cqlParser#ifThenElseExpressionTerm.
    def exitIfThenElseExpressionTerm(self, ctx:cqlParser.IfThenElseExpressionTermContext):
        pass


    # Enter a parse tree produced by cqlParser#timeBoundaryExpressionTerm.
    def enterTimeBoundaryExpressionTerm(self, ctx:cqlParser.TimeBoundaryExpressionTermContext):
        pass

    # Exit a parse tree produced by cqlParser#timeBoundaryExpressionTerm.
    def exitTimeBoundaryExpressionTerm(self, ctx:cqlParser.TimeBoundaryExpressionTermContext):
        pass


    # Enter a parse tree produced by cqlParser#elementExtractorExpressionTerm.
    def enterElementExtractorExpressionTerm(self, ctx:cqlParser.ElementExtractorExpressionTermContext):
        pass

    # Exit a parse tree produced by cqlParser#elementExtractorExpressionTerm.
    def exitElementExtractorExpressionTerm(self, ctx:cqlParser.ElementExtractorExpressionTermContext):
        pass


    # Enter a parse tree produced by cqlParser#conversionExpressionTerm.
    def enterConversionExpressionTerm(self, ctx:cqlParser.ConversionExpressionTermContext):
        pass

    # Exit a parse tree produced by cqlParser#conversionExpressionTerm.
    def exitConversionExpressionTerm(self, ctx:cqlParser.ConversionExpressionTermContext):
        pass


    # Enter a parse tree produced by cqlParser#typeExtentExpressionTerm.
    def enterTypeExtentExpressionTerm(self, ctx:cqlParser.TypeExtentExpressionTermContext):
        pass

    # Exit a parse tree produced by cqlParser#typeExtentExpressionTerm.
    def exitTypeExtentExpressionTerm(self, ctx:cqlParser.TypeExtentExpressionTermContext):
        pass


    # Enter a parse tree produced by cqlParser#predecessorExpressionTerm.
    def enterPredecessorExpressionTerm(self, ctx:cqlParser.PredecessorExpressionTermContext):
        pass

    # Exit a parse tree produced by cqlParser#predecessorExpressionTerm.
    def exitPredecessorExpressionTerm(self, ctx:cqlParser.PredecessorExpressionTermContext):
        pass


    # Enter a parse tree produced by cqlParser#pointExtractorExpressionTerm.
    def enterPointExtractorExpressionTerm(self, ctx:cqlParser.PointExtractorExpressionTermContext):
        pass

    # Exit a parse tree produced by cqlParser#pointExtractorExpressionTerm.
    def exitPointExtractorExpressionTerm(self, ctx:cqlParser.PointExtractorExpressionTermContext):
        pass


    # Enter a parse tree produced by cqlParser#multiplicationExpressionTerm.
    def enterMultiplicationExpressionTerm(self, ctx:cqlParser.MultiplicationExpressionTermContext):
        pass

    # Exit a parse tree produced by cqlParser#multiplicationExpressionTerm.
    def exitMultiplicationExpressionTerm(self, ctx:cqlParser.MultiplicationExpressionTermContext):
        pass


    # Enter a parse tree produced by cqlParser#aggregateExpressionTerm.
    def enterAggregateExpressionTerm(self, ctx:cqlParser.AggregateExpressionTermContext):
        pass

    # Exit a parse tree produced by cqlParser#aggregateExpressionTerm.
    def exitAggregateExpressionTerm(self, ctx:cqlParser.AggregateExpressionTermContext):
        pass


    # Enter a parse tree produced by cqlParser#durationExpressionTerm.
    def enterDurationExpressionTerm(self, ctx:cqlParser.DurationExpressionTermContext):
        pass

    # Exit a parse tree produced by cqlParser#durationExpressionTerm.
    def exitDurationExpressionTerm(self, ctx:cqlParser.DurationExpressionTermContext):
        pass


    # Enter a parse tree produced by cqlParser#differenceExpressionTerm.
    def enterDifferenceExpressionTerm(self, ctx:cqlParser.DifferenceExpressionTermContext):
        pass

    # Exit a parse tree produced by cqlParser#differenceExpressionTerm.
    def exitDifferenceExpressionTerm(self, ctx:cqlParser.DifferenceExpressionTermContext):
        pass


    # Enter a parse tree produced by cqlParser#caseExpressionTerm.
    def enterCaseExpressionTerm(self, ctx:cqlParser.CaseExpressionTermContext):
        pass

    # Exit a parse tree produced by cqlParser#caseExpressionTerm.
    def exitCaseExpressionTerm(self, ctx:cqlParser.CaseExpressionTermContext):
        pass


    # Enter a parse tree produced by cqlParser#powerExpressionTerm.
    def enterPowerExpressionTerm(self, ctx:cqlParser.PowerExpressionTermContext):
        pass

    # Exit a parse tree produced by cqlParser#powerExpressionTerm.
    def exitPowerExpressionTerm(self, ctx:cqlParser.PowerExpressionTermContext):
        pass


    # Enter a parse tree produced by cqlParser#successorExpressionTerm.
    def enterSuccessorExpressionTerm(self, ctx:cqlParser.SuccessorExpressionTermContext):
        pass

    # Exit a parse tree produced by cqlParser#successorExpressionTerm.
    def exitSuccessorExpressionTerm(self, ctx:cqlParser.SuccessorExpressionTermContext):
        pass


    # Enter a parse tree produced by cqlParser#polarityExpressionTerm.
    def enterPolarityExpressionTerm(self, ctx:cqlParser.PolarityExpressionTermContext):
        pass

    # Exit a parse tree produced by cqlParser#polarityExpressionTerm.
    def exitPolarityExpressionTerm(self, ctx:cqlParser.PolarityExpressionTermContext):
        pass


    # Enter a parse tree produced by cqlParser#termExpressionTerm.
    def enterTermExpressionTerm(self, ctx:cqlParser.TermExpressionTermContext):
        pass

    # Exit a parse tree produced by cqlParser#termExpressionTerm.
    def exitTermExpressionTerm(self, ctx:cqlParser.TermExpressionTermContext):
        pass


    # Enter a parse tree produced by cqlParser#invocationExpressionTerm.
    def enterInvocationExpressionTerm(self, ctx:cqlParser.InvocationExpressionTermContext):
        pass

    # Exit a parse tree produced by cqlParser#invocationExpressionTerm.
    def exitInvocationExpressionTerm(self, ctx:cqlParser.InvocationExpressionTermContext):
        pass


    # Enter a parse tree produced by cqlParser#caseExpressionItem.
    def enterCaseExpressionItem(self, ctx:cqlParser.CaseExpressionItemContext):
        pass

    # Exit a parse tree produced by cqlParser#caseExpressionItem.
    def exitCaseExpressionItem(self, ctx:cqlParser.CaseExpressionItemContext):
        pass


    # Enter a parse tree produced by cqlParser#dateTimePrecisionSpecifier.
    def enterDateTimePrecisionSpecifier(self, ctx:cqlParser.DateTimePrecisionSpecifierContext):
        pass

    # Exit a parse tree produced by cqlParser#dateTimePrecisionSpecifier.
    def exitDateTimePrecisionSpecifier(self, ctx:cqlParser.DateTimePrecisionSpecifierContext):
        pass


    # Enter a parse tree produced by cqlParser#relativeQualifier.
    def enterRelativeQualifier(self, ctx:cqlParser.RelativeQualifierContext):
        pass

    # Exit a parse tree produced by cqlParser#relativeQualifier.
    def exitRelativeQualifier(self, ctx:cqlParser.RelativeQualifierContext):
        pass


    # Enter a parse tree produced by cqlParser#offsetRelativeQualifier.
    def enterOffsetRelativeQualifier(self, ctx:cqlParser.OffsetRelativeQualifierContext):
        pass

    # Exit a parse tree produced by cqlParser#offsetRelativeQualifier.
    def exitOffsetRelativeQualifier(self, ctx:cqlParser.OffsetRelativeQualifierContext):
        pass


    # Enter a parse tree produced by cqlParser#exclusiveRelativeQualifier.
    def enterExclusiveRelativeQualifier(self, ctx:cqlParser.ExclusiveRelativeQualifierContext):
        pass

    # Exit a parse tree produced by cqlParser#exclusiveRelativeQualifier.
    def exitExclusiveRelativeQualifier(self, ctx:cqlParser.ExclusiveRelativeQualifierContext):
        pass


    # Enter a parse tree produced by cqlParser#quantityOffset.
    def enterQuantityOffset(self, ctx:cqlParser.QuantityOffsetContext):
        pass

    # Exit a parse tree produced by cqlParser#quantityOffset.
    def exitQuantityOffset(self, ctx:cqlParser.QuantityOffsetContext):
        pass


    # Enter a parse tree produced by cqlParser#temporalRelationship.
    def enterTemporalRelationship(self, ctx:cqlParser.TemporalRelationshipContext):
        pass

    # Exit a parse tree produced by cqlParser#temporalRelationship.
    def exitTemporalRelationship(self, ctx:cqlParser.TemporalRelationshipContext):
        pass


    # Enter a parse tree produced by cqlParser#concurrentWithIntervalOperatorPhrase.
    def enterConcurrentWithIntervalOperatorPhrase(self, ctx:cqlParser.ConcurrentWithIntervalOperatorPhraseContext):
        pass

    # Exit a parse tree produced by cqlParser#concurrentWithIntervalOperatorPhrase.
    def exitConcurrentWithIntervalOperatorPhrase(self, ctx:cqlParser.ConcurrentWithIntervalOperatorPhraseContext):
        pass


    # Enter a parse tree produced by cqlParser#includesIntervalOperatorPhrase.
    def enterIncludesIntervalOperatorPhrase(self, ctx:cqlParser.IncludesIntervalOperatorPhraseContext):
        pass

    # Exit a parse tree produced by cqlParser#includesIntervalOperatorPhrase.
    def exitIncludesIntervalOperatorPhrase(self, ctx:cqlParser.IncludesIntervalOperatorPhraseContext):
        pass


    # Enter a parse tree produced by cqlParser#includedInIntervalOperatorPhrase.
    def enterIncludedInIntervalOperatorPhrase(self, ctx:cqlParser.IncludedInIntervalOperatorPhraseContext):
        pass

    # Exit a parse tree produced by cqlParser#includedInIntervalOperatorPhrase.
    def exitIncludedInIntervalOperatorPhrase(self, ctx:cqlParser.IncludedInIntervalOperatorPhraseContext):
        pass


    # Enter a parse tree produced by cqlParser#beforeOrAfterIntervalOperatorPhrase.
    def enterBeforeOrAfterIntervalOperatorPhrase(self, ctx:cqlParser.BeforeOrAfterIntervalOperatorPhraseContext):
        pass

    # Exit a parse tree produced by cqlParser#beforeOrAfterIntervalOperatorPhrase.
    def exitBeforeOrAfterIntervalOperatorPhrase(self, ctx:cqlParser.BeforeOrAfterIntervalOperatorPhraseContext):
        pass


    # Enter a parse tree produced by cqlParser#withinIntervalOperatorPhrase.
    def enterWithinIntervalOperatorPhrase(self, ctx:cqlParser.WithinIntervalOperatorPhraseContext):
        pass

    # Exit a parse tree produced by cqlParser#withinIntervalOperatorPhrase.
    def exitWithinIntervalOperatorPhrase(self, ctx:cqlParser.WithinIntervalOperatorPhraseContext):
        pass


    # Enter a parse tree produced by cqlParser#meetsIntervalOperatorPhrase.
    def enterMeetsIntervalOperatorPhrase(self, ctx:cqlParser.MeetsIntervalOperatorPhraseContext):
        pass

    # Exit a parse tree produced by cqlParser#meetsIntervalOperatorPhrase.
    def exitMeetsIntervalOperatorPhrase(self, ctx:cqlParser.MeetsIntervalOperatorPhraseContext):
        pass


    # Enter a parse tree produced by cqlParser#overlapsIntervalOperatorPhrase.
    def enterOverlapsIntervalOperatorPhrase(self, ctx:cqlParser.OverlapsIntervalOperatorPhraseContext):
        pass

    # Exit a parse tree produced by cqlParser#overlapsIntervalOperatorPhrase.
    def exitOverlapsIntervalOperatorPhrase(self, ctx:cqlParser.OverlapsIntervalOperatorPhraseContext):
        pass


    # Enter a parse tree produced by cqlParser#startsIntervalOperatorPhrase.
    def enterStartsIntervalOperatorPhrase(self, ctx:cqlParser.StartsIntervalOperatorPhraseContext):
        pass

    # Exit a parse tree produced by cqlParser#startsIntervalOperatorPhrase.
    def exitStartsIntervalOperatorPhrase(self, ctx:cqlParser.StartsIntervalOperatorPhraseContext):
        pass


    # Enter a parse tree produced by cqlParser#endsIntervalOperatorPhrase.
    def enterEndsIntervalOperatorPhrase(self, ctx:cqlParser.EndsIntervalOperatorPhraseContext):
        pass

    # Exit a parse tree produced by cqlParser#endsIntervalOperatorPhrase.
    def exitEndsIntervalOperatorPhrase(self, ctx:cqlParser.EndsIntervalOperatorPhraseContext):
        pass


    # Enter a parse tree produced by cqlParser#invocationTerm.
    def enterInvocationTerm(self, ctx:cqlParser.InvocationTermContext):
        pass

    # Exit a parse tree produced by cqlParser#invocationTerm.
    def exitInvocationTerm(self, ctx:cqlParser.InvocationTermContext):
        pass


    # Enter a parse tree produced by cqlParser#literalTerm.
    def enterLiteralTerm(self, ctx:cqlParser.LiteralTermContext):
        pass

    # Exit a parse tree produced by cqlParser#literalTerm.
    def exitLiteralTerm(self, ctx:cqlParser.LiteralTermContext):
        pass


    # Enter a parse tree produced by cqlParser#externalConstantTerm.
    def enterExternalConstantTerm(self, ctx:cqlParser.ExternalConstantTermContext):
        pass

    # Exit a parse tree produced by cqlParser#externalConstantTerm.
    def exitExternalConstantTerm(self, ctx:cqlParser.ExternalConstantTermContext):
        pass


    # Enter a parse tree produced by cqlParser#intervalSelectorTerm.
    def enterIntervalSelectorTerm(self, ctx:cqlParser.IntervalSelectorTermContext):
        pass

    # Exit a parse tree produced by cqlParser#intervalSelectorTerm.
    def exitIntervalSelectorTerm(self, ctx:cqlParser.IntervalSelectorTermContext):
        pass


    # Enter a parse tree produced by cqlParser#tupleSelectorTerm.
    def enterTupleSelectorTerm(self, ctx:cqlParser.TupleSelectorTermContext):
        pass

    # Exit a parse tree produced by cqlParser#tupleSelectorTerm.
    def exitTupleSelectorTerm(self, ctx:cqlParser.TupleSelectorTermContext):
        pass


    # Enter a parse tree produced by cqlParser#instanceSelectorTerm.
    def enterInstanceSelectorTerm(self, ctx:cqlParser.InstanceSelectorTermContext):
        pass

    # Exit a parse tree produced by cqlParser#instanceSelectorTerm.
    def exitInstanceSelectorTerm(self, ctx:cqlParser.InstanceSelectorTermContext):
        pass


    # Enter a parse tree produced by cqlParser#listSelectorTerm.
    def enterListSelectorTerm(self, ctx:cqlParser.ListSelectorTermContext):
        pass

    # Exit a parse tree produced by cqlParser#listSelectorTerm.
    def exitListSelectorTerm(self, ctx:cqlParser.ListSelectorTermContext):
        pass


    # Enter a parse tree produced by cqlParser#codeSelectorTerm.
    def enterCodeSelectorTerm(self, ctx:cqlParser.CodeSelectorTermContext):
        pass

    # Exit a parse tree produced by cqlParser#codeSelectorTerm.
    def exitCodeSelectorTerm(self, ctx:cqlParser.CodeSelectorTermContext):
        pass


    # Enter a parse tree produced by cqlParser#conceptSelectorTerm.
    def enterConceptSelectorTerm(self, ctx:cqlParser.ConceptSelectorTermContext):
        pass

    # Exit a parse tree produced by cqlParser#conceptSelectorTerm.
    def exitConceptSelectorTerm(self, ctx:cqlParser.ConceptSelectorTermContext):
        pass


    # Enter a parse tree produced by cqlParser#parenthesizedTerm.
    def enterParenthesizedTerm(self, ctx:cqlParser.ParenthesizedTermContext):
        pass

    # Exit a parse tree produced by cqlParser#parenthesizedTerm.
    def exitParenthesizedTerm(self, ctx:cqlParser.ParenthesizedTermContext):
        pass


    # Enter a parse tree produced by cqlParser#qualifiedMemberInvocation.
    def enterQualifiedMemberInvocation(self, ctx:cqlParser.QualifiedMemberInvocationContext):
        pass

    # Exit a parse tree produced by cqlParser#qualifiedMemberInvocation.
    def exitQualifiedMemberInvocation(self, ctx:cqlParser.QualifiedMemberInvocationContext):
        pass


    # Enter a parse tree produced by cqlParser#qualifiedFunctionInvocation.
    def enterQualifiedFunctionInvocation(self, ctx:cqlParser.QualifiedFunctionInvocationContext):
        pass

    # Exit a parse tree produced by cqlParser#qualifiedFunctionInvocation.
    def exitQualifiedFunctionInvocation(self, ctx:cqlParser.QualifiedFunctionInvocationContext):
        pass


    # Enter a parse tree produced by cqlParser#qualifiedFunction.
    def enterQualifiedFunction(self, ctx:cqlParser.QualifiedFunctionContext):
        pass

    # Exit a parse tree produced by cqlParser#qualifiedFunction.
    def exitQualifiedFunction(self, ctx:cqlParser.QualifiedFunctionContext):
        pass


    # Enter a parse tree produced by cqlParser#memberInvocation.
    def enterMemberInvocation(self, ctx:cqlParser.MemberInvocationContext):
        pass

    # Exit a parse tree produced by cqlParser#memberInvocation.
    def exitMemberInvocation(self, ctx:cqlParser.MemberInvocationContext):
        pass


    # Enter a parse tree produced by cqlParser#functionInvocation.
    def enterFunctionInvocation(self, ctx:cqlParser.FunctionInvocationContext):
        pass

    # Exit a parse tree produced by cqlParser#functionInvocation.
    def exitFunctionInvocation(self, ctx:cqlParser.FunctionInvocationContext):
        pass


    # Enter a parse tree produced by cqlParser#thisInvocation.
    def enterThisInvocation(self, ctx:cqlParser.ThisInvocationContext):
        pass

    # Exit a parse tree produced by cqlParser#thisInvocation.
    def exitThisInvocation(self, ctx:cqlParser.ThisInvocationContext):
        pass


    # Enter a parse tree produced by cqlParser#indexInvocation.
    def enterIndexInvocation(self, ctx:cqlParser.IndexInvocationContext):
        pass

    # Exit a parse tree produced by cqlParser#indexInvocation.
    def exitIndexInvocation(self, ctx:cqlParser.IndexInvocationContext):
        pass


    # Enter a parse tree produced by cqlParser#totalInvocation.
    def enterTotalInvocation(self, ctx:cqlParser.TotalInvocationContext):
        pass

    # Exit a parse tree produced by cqlParser#totalInvocation.
    def exitTotalInvocation(self, ctx:cqlParser.TotalInvocationContext):
        pass


    # Enter a parse tree produced by cqlParser#function.
    def enterFunction(self, ctx:cqlParser.FunctionContext):
        pass

    # Exit a parse tree produced by cqlParser#function.
    def exitFunction(self, ctx:cqlParser.FunctionContext):
        pass


    # Enter a parse tree produced by cqlParser#ratio.
    def enterRatio(self, ctx:cqlParser.RatioContext):
        pass

    # Exit a parse tree produced by cqlParser#ratio.
    def exitRatio(self, ctx:cqlParser.RatioContext):
        pass


    # Enter a parse tree produced by cqlParser#booleanLiteral.
    def enterBooleanLiteral(self, ctx:cqlParser.BooleanLiteralContext):
        pass

    # Exit a parse tree produced by cqlParser#booleanLiteral.
    def exitBooleanLiteral(self, ctx:cqlParser.BooleanLiteralContext):
        pass


    # Enter a parse tree produced by cqlParser#nullLiteral.
    def enterNullLiteral(self, ctx:cqlParser.NullLiteralContext):
        pass

    # Exit a parse tree produced by cqlParser#nullLiteral.
    def exitNullLiteral(self, ctx:cqlParser.NullLiteralContext):
        pass


    # Enter a parse tree produced by cqlParser#stringLiteral.
    def enterStringLiteral(self, ctx:cqlParser.StringLiteralContext):
        pass

    # Exit a parse tree produced by cqlParser#stringLiteral.
    def exitStringLiteral(self, ctx:cqlParser.StringLiteralContext):
        pass


    # Enter a parse tree produced by cqlParser#numberLiteral.
    def enterNumberLiteral(self, ctx:cqlParser.NumberLiteralContext):
        pass

    # Exit a parse tree produced by cqlParser#numberLiteral.
    def exitNumberLiteral(self, ctx:cqlParser.NumberLiteralContext):
        pass


    # Enter a parse tree produced by cqlParser#longNumberLiteral.
    def enterLongNumberLiteral(self, ctx:cqlParser.LongNumberLiteralContext):
        pass

    # Exit a parse tree produced by cqlParser#longNumberLiteral.
    def exitLongNumberLiteral(self, ctx:cqlParser.LongNumberLiteralContext):
        pass


    # Enter a parse tree produced by cqlParser#dateTimeLiteral.
    def enterDateTimeLiteral(self, ctx:cqlParser.DateTimeLiteralContext):
        pass

    # Exit a parse tree produced by cqlParser#dateTimeLiteral.
    def exitDateTimeLiteral(self, ctx:cqlParser.DateTimeLiteralContext):
        pass


    # Enter a parse tree produced by cqlParser#dateLiteral.
    def enterDateLiteral(self, ctx:cqlParser.DateLiteralContext):
        pass

    # Exit a parse tree produced by cqlParser#dateLiteral.
    def exitDateLiteral(self, ctx:cqlParser.DateLiteralContext):
        pass


    # Enter a parse tree produced by cqlParser#timeLiteral.
    def enterTimeLiteral(self, ctx:cqlParser.TimeLiteralContext):
        pass

    # Exit a parse tree produced by cqlParser#timeLiteral.
    def exitTimeLiteral(self, ctx:cqlParser.TimeLiteralContext):
        pass


    # Enter a parse tree produced by cqlParser#quantityLiteral.
    def enterQuantityLiteral(self, ctx:cqlParser.QuantityLiteralContext):
        pass

    # Exit a parse tree produced by cqlParser#quantityLiteral.
    def exitQuantityLiteral(self, ctx:cqlParser.QuantityLiteralContext):
        pass


    # Enter a parse tree produced by cqlParser#ratioLiteral.
    def enterRatioLiteral(self, ctx:cqlParser.RatioLiteralContext):
        pass

    # Exit a parse tree produced by cqlParser#ratioLiteral.
    def exitRatioLiteral(self, ctx:cqlParser.RatioLiteralContext):
        pass


    # Enter a parse tree produced by cqlParser#intervalSelector.
    def enterIntervalSelector(self, ctx:cqlParser.IntervalSelectorContext):
        pass

    # Exit a parse tree produced by cqlParser#intervalSelector.
    def exitIntervalSelector(self, ctx:cqlParser.IntervalSelectorContext):
        pass


    # Enter a parse tree produced by cqlParser#tupleSelector.
    def enterTupleSelector(self, ctx:cqlParser.TupleSelectorContext):
        pass

    # Exit a parse tree produced by cqlParser#tupleSelector.
    def exitTupleSelector(self, ctx:cqlParser.TupleSelectorContext):
        pass


    # Enter a parse tree produced by cqlParser#tupleElementSelector.
    def enterTupleElementSelector(self, ctx:cqlParser.TupleElementSelectorContext):
        pass

    # Exit a parse tree produced by cqlParser#tupleElementSelector.
    def exitTupleElementSelector(self, ctx:cqlParser.TupleElementSelectorContext):
        pass


    # Enter a parse tree produced by cqlParser#instanceSelector.
    def enterInstanceSelector(self, ctx:cqlParser.InstanceSelectorContext):
        pass

    # Exit a parse tree produced by cqlParser#instanceSelector.
    def exitInstanceSelector(self, ctx:cqlParser.InstanceSelectorContext):
        pass


    # Enter a parse tree produced by cqlParser#instanceElementSelector.
    def enterInstanceElementSelector(self, ctx:cqlParser.InstanceElementSelectorContext):
        pass

    # Exit a parse tree produced by cqlParser#instanceElementSelector.
    def exitInstanceElementSelector(self, ctx:cqlParser.InstanceElementSelectorContext):
        pass


    # Enter a parse tree produced by cqlParser#listSelector.
    def enterListSelector(self, ctx:cqlParser.ListSelectorContext):
        pass

    # Exit a parse tree produced by cqlParser#listSelector.
    def exitListSelector(self, ctx:cqlParser.ListSelectorContext):
        pass


    # Enter a parse tree produced by cqlParser#displayClause.
    def enterDisplayClause(self, ctx:cqlParser.DisplayClauseContext):
        pass

    # Exit a parse tree produced by cqlParser#displayClause.
    def exitDisplayClause(self, ctx:cqlParser.DisplayClauseContext):
        pass


    # Enter a parse tree produced by cqlParser#codeSelector.
    def enterCodeSelector(self, ctx:cqlParser.CodeSelectorContext):
        pass

    # Exit a parse tree produced by cqlParser#codeSelector.
    def exitCodeSelector(self, ctx:cqlParser.CodeSelectorContext):
        pass


    # Enter a parse tree produced by cqlParser#conceptSelector.
    def enterConceptSelector(self, ctx:cqlParser.ConceptSelectorContext):
        pass

    # Exit a parse tree produced by cqlParser#conceptSelector.
    def exitConceptSelector(self, ctx:cqlParser.ConceptSelectorContext):
        pass


    # Enter a parse tree produced by cqlParser#keyword.
    def enterKeyword(self, ctx:cqlParser.KeywordContext):
        pass

    # Exit a parse tree produced by cqlParser#keyword.
    def exitKeyword(self, ctx:cqlParser.KeywordContext):
        pass


    # Enter a parse tree produced by cqlParser#reservedWord.
    def enterReservedWord(self, ctx:cqlParser.ReservedWordContext):
        pass

    # Exit a parse tree produced by cqlParser#reservedWord.
    def exitReservedWord(self, ctx:cqlParser.ReservedWordContext):
        pass


    # Enter a parse tree produced by cqlParser#keywordIdentifier.
    def enterKeywordIdentifier(self, ctx:cqlParser.KeywordIdentifierContext):
        pass

    # Exit a parse tree produced by cqlParser#keywordIdentifier.
    def exitKeywordIdentifier(self, ctx:cqlParser.KeywordIdentifierContext):
        pass


    # Enter a parse tree produced by cqlParser#obsoleteIdentifier.
    def enterObsoleteIdentifier(self, ctx:cqlParser.ObsoleteIdentifierContext):
        pass

    # Exit a parse tree produced by cqlParser#obsoleteIdentifier.
    def exitObsoleteIdentifier(self, ctx:cqlParser.ObsoleteIdentifierContext):
        pass


    # Enter a parse tree produced by cqlParser#functionIdentifier.
    def enterFunctionIdentifier(self, ctx:cqlParser.FunctionIdentifierContext):
        pass

    # Exit a parse tree produced by cqlParser#functionIdentifier.
    def exitFunctionIdentifier(self, ctx:cqlParser.FunctionIdentifierContext):
        pass


    # Enter a parse tree produced by cqlParser#typeNameIdentifier.
    def enterTypeNameIdentifier(self, ctx:cqlParser.TypeNameIdentifierContext):
        pass

    # Exit a parse tree produced by cqlParser#typeNameIdentifier.
    def exitTypeNameIdentifier(self, ctx:cqlParser.TypeNameIdentifierContext):
        pass


    # Enter a parse tree produced by cqlParser#referentialIdentifier.
    def enterReferentialIdentifier(self, ctx:cqlParser.ReferentialIdentifierContext):
        pass

    # Exit a parse tree produced by cqlParser#referentialIdentifier.
    def exitReferentialIdentifier(self, ctx:cqlParser.ReferentialIdentifierContext):
        pass


    # Enter a parse tree produced by cqlParser#referentialOrTypeNameIdentifier.
    def enterReferentialOrTypeNameIdentifier(self, ctx:cqlParser.ReferentialOrTypeNameIdentifierContext):
        pass

    # Exit a parse tree produced by cqlParser#referentialOrTypeNameIdentifier.
    def exitReferentialOrTypeNameIdentifier(self, ctx:cqlParser.ReferentialOrTypeNameIdentifierContext):
        pass


    # Enter a parse tree produced by cqlParser#identifierOrFunctionIdentifier.
    def enterIdentifierOrFunctionIdentifier(self, ctx:cqlParser.IdentifierOrFunctionIdentifierContext):
        pass

    # Exit a parse tree produced by cqlParser#identifierOrFunctionIdentifier.
    def exitIdentifierOrFunctionIdentifier(self, ctx:cqlParser.IdentifierOrFunctionIdentifierContext):
        pass


    # Enter a parse tree produced by cqlParser#identifier.
    def enterIdentifier(self, ctx:cqlParser.IdentifierContext):
        pass

    # Exit a parse tree produced by cqlParser#identifier.
    def exitIdentifier(self, ctx:cqlParser.IdentifierContext):
        pass


    # Enter a parse tree produced by cqlParser#externalConstant.
    def enterExternalConstant(self, ctx:cqlParser.ExternalConstantContext):
        pass

    # Exit a parse tree produced by cqlParser#externalConstant.
    def exitExternalConstant(self, ctx:cqlParser.ExternalConstantContext):
        pass


    # Enter a parse tree produced by cqlParser#paramList.
    def enterParamList(self, ctx:cqlParser.ParamListContext):
        pass

    # Exit a parse tree produced by cqlParser#paramList.
    def exitParamList(self, ctx:cqlParser.ParamListContext):
        pass


    # Enter a parse tree produced by cqlParser#quantity.
    def enterQuantity(self, ctx:cqlParser.QuantityContext):
        pass

    # Exit a parse tree produced by cqlParser#quantity.
    def exitQuantity(self, ctx:cqlParser.QuantityContext):
        pass


    # Enter a parse tree produced by cqlParser#unit.
    def enterUnit(self, ctx:cqlParser.UnitContext):
        pass

    # Exit a parse tree produced by cqlParser#unit.
    def exitUnit(self, ctx:cqlParser.UnitContext):
        pass



del cqlParser