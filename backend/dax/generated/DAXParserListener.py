# Generated from backend/dax/grammar/DAXParser.g4 by ANTLR 4.13.2
from antlr4 import *
if "." in __name__:
    from .DAXParser import DAXParser
else:
    from DAXParser import DAXParser

# This class defines a complete listener for a parse tree produced by DAXParser.
class DAXParserListener(ParseTreeListener):

    # Enter a parse tree produced by DAXParser#parse.
    def enterParse(self, ctx:DAXParser.ParseContext):
        pass

    # Exit a parse tree produced by DAXParser#parse.
    def exitParse(self, ctx:DAXParser.ParseContext):
        pass


    # Enter a parse tree produced by DAXParser#varExpression.
    def enterVarExpression(self, ctx:DAXParser.VarExpressionContext):
        pass

    # Exit a parse tree produced by DAXParser#varExpression.
    def exitVarExpression(self, ctx:DAXParser.VarExpressionContext):
        pass


    # Enter a parse tree produced by DAXParser#logicalExpression.
    def enterLogicalExpression(self, ctx:DAXParser.LogicalExpressionContext):
        pass

    # Exit a parse tree produced by DAXParser#logicalExpression.
    def exitLogicalExpression(self, ctx:DAXParser.LogicalExpressionContext):
        pass


    # Enter a parse tree produced by DAXParser#varBlock.
    def enterVarBlock(self, ctx:DAXParser.VarBlockContext):
        pass

    # Exit a parse tree produced by DAXParser#varBlock.
    def exitVarBlock(self, ctx:DAXParser.VarBlockContext):
        pass


    # Enter a parse tree produced by DAXParser#varBinding.
    def enterVarBinding(self, ctx:DAXParser.VarBindingContext):
        pass

    # Exit a parse tree produced by DAXParser#varBinding.
    def exitVarBinding(self, ctx:DAXParser.VarBindingContext):
        pass


    # Enter a parse tree produced by DAXParser#logicalOr.
    def enterLogicalOr(self, ctx:DAXParser.LogicalOrContext):
        pass

    # Exit a parse tree produced by DAXParser#logicalOr.
    def exitLogicalOr(self, ctx:DAXParser.LogicalOrContext):
        pass


    # Enter a parse tree produced by DAXParser#logicalAnd.
    def enterLogicalAnd(self, ctx:DAXParser.LogicalAndContext):
        pass

    # Exit a parse tree produced by DAXParser#logicalAnd.
    def exitLogicalAnd(self, ctx:DAXParser.LogicalAndContext):
        pass


    # Enter a parse tree produced by DAXParser#comparison.
    def enterComparison(self, ctx:DAXParser.ComparisonContext):
        pass

    # Exit a parse tree produced by DAXParser#comparison.
    def exitComparison(self, ctx:DAXParser.ComparisonContext):
        pass


    # Enter a parse tree produced by DAXParser#additive.
    def enterAdditive(self, ctx:DAXParser.AdditiveContext):
        pass

    # Exit a parse tree produced by DAXParser#additive.
    def exitAdditive(self, ctx:DAXParser.AdditiveContext):
        pass


    # Enter a parse tree produced by DAXParser#multiplicative.
    def enterMultiplicative(self, ctx:DAXParser.MultiplicativeContext):
        pass

    # Exit a parse tree produced by DAXParser#multiplicative.
    def exitMultiplicative(self, ctx:DAXParser.MultiplicativeContext):
        pass


    # Enter a parse tree produced by DAXParser#concatenation.
    def enterConcatenation(self, ctx:DAXParser.ConcatenationContext):
        pass

    # Exit a parse tree produced by DAXParser#concatenation.
    def exitConcatenation(self, ctx:DAXParser.ConcatenationContext):
        pass


    # Enter a parse tree produced by DAXParser#unary.
    def enterUnary(self, ctx:DAXParser.UnaryContext):
        pass

    # Exit a parse tree produced by DAXParser#unary.
    def exitUnary(self, ctx:DAXParser.UnaryContext):
        pass


    # Enter a parse tree produced by DAXParser#power.
    def enterPower(self, ctx:DAXParser.PowerContext):
        pass

    # Exit a parse tree produced by DAXParser#power.
    def exitPower(self, ctx:DAXParser.PowerContext):
        pass


    # Enter a parse tree produced by DAXParser#literalPrimary.
    def enterLiteralPrimary(self, ctx:DAXParser.LiteralPrimaryContext):
        pass

    # Exit a parse tree produced by DAXParser#literalPrimary.
    def exitLiteralPrimary(self, ctx:DAXParser.LiteralPrimaryContext):
        pass


    # Enter a parse tree produced by DAXParser#functionPrimary.
    def enterFunctionPrimary(self, ctx:DAXParser.FunctionPrimaryContext):
        pass

    # Exit a parse tree produced by DAXParser#functionPrimary.
    def exitFunctionPrimary(self, ctx:DAXParser.FunctionPrimaryContext):
        pass


    # Enter a parse tree produced by DAXParser#qualifiedReferencePrimary.
    def enterQualifiedReferencePrimary(self, ctx:DAXParser.QualifiedReferencePrimaryContext):
        pass

    # Exit a parse tree produced by DAXParser#qualifiedReferencePrimary.
    def exitQualifiedReferencePrimary(self, ctx:DAXParser.QualifiedReferencePrimaryContext):
        pass


    # Enter a parse tree produced by DAXParser#standaloneReferencePrimary.
    def enterStandaloneReferencePrimary(self, ctx:DAXParser.StandaloneReferencePrimaryContext):
        pass

    # Exit a parse tree produced by DAXParser#standaloneReferencePrimary.
    def exitStandaloneReferencePrimary(self, ctx:DAXParser.StandaloneReferencePrimaryContext):
        pass


    # Enter a parse tree produced by DAXParser#bareTableReferencePrimary.
    def enterBareTableReferencePrimary(self, ctx:DAXParser.BareTableReferencePrimaryContext):
        pass

    # Exit a parse tree produced by DAXParser#bareTableReferencePrimary.
    def exitBareTableReferencePrimary(self, ctx:DAXParser.BareTableReferencePrimaryContext):
        pass


    # Enter a parse tree produced by DAXParser#identifierPrimary.
    def enterIdentifierPrimary(self, ctx:DAXParser.IdentifierPrimaryContext):
        pass

    # Exit a parse tree produced by DAXParser#identifierPrimary.
    def exitIdentifierPrimary(self, ctx:DAXParser.IdentifierPrimaryContext):
        pass


    # Enter a parse tree produced by DAXParser#tupleConstructorPrimary.
    def enterTupleConstructorPrimary(self, ctx:DAXParser.TupleConstructorPrimaryContext):
        pass

    # Exit a parse tree produced by DAXParser#tupleConstructorPrimary.
    def exitTupleConstructorPrimary(self, ctx:DAXParser.TupleConstructorPrimaryContext):
        pass


    # Enter a parse tree produced by DAXParser#tableConstructorPrimary.
    def enterTableConstructorPrimary(self, ctx:DAXParser.TableConstructorPrimaryContext):
        pass

    # Exit a parse tree produced by DAXParser#tableConstructorPrimary.
    def exitTableConstructorPrimary(self, ctx:DAXParser.TableConstructorPrimaryContext):
        pass


    # Enter a parse tree produced by DAXParser#parenthesizedPrimary.
    def enterParenthesizedPrimary(self, ctx:DAXParser.ParenthesizedPrimaryContext):
        pass

    # Exit a parse tree produced by DAXParser#parenthesizedPrimary.
    def exitParenthesizedPrimary(self, ctx:DAXParser.ParenthesizedPrimaryContext):
        pass


    # Enter a parse tree produced by DAXParser#stringLiteral.
    def enterStringLiteral(self, ctx:DAXParser.StringLiteralContext):
        pass

    # Exit a parse tree produced by DAXParser#stringLiteral.
    def exitStringLiteral(self, ctx:DAXParser.StringLiteralContext):
        pass


    # Enter a parse tree produced by DAXParser#numberLiteral.
    def enterNumberLiteral(self, ctx:DAXParser.NumberLiteralContext):
        pass

    # Exit a parse tree produced by DAXParser#numberLiteral.
    def exitNumberLiteral(self, ctx:DAXParser.NumberLiteralContext):
        pass


    # Enter a parse tree produced by DAXParser#dateLiteral.
    def enterDateLiteral(self, ctx:DAXParser.DateLiteralContext):
        pass

    # Exit a parse tree produced by DAXParser#dateLiteral.
    def exitDateLiteral(self, ctx:DAXParser.DateLiteralContext):
        pass


    # Enter a parse tree produced by DAXParser#datetimeLiteral.
    def enterDatetimeLiteral(self, ctx:DAXParser.DatetimeLiteralContext):
        pass

    # Exit a parse tree produced by DAXParser#datetimeLiteral.
    def exitDatetimeLiteral(self, ctx:DAXParser.DatetimeLiteralContext):
        pass


    # Enter a parse tree produced by DAXParser#functionCall.
    def enterFunctionCall(self, ctx:DAXParser.FunctionCallContext):
        pass

    # Exit a parse tree produced by DAXParser#functionCall.
    def exitFunctionCall(self, ctx:DAXParser.FunctionCallContext):
        pass


    # Enter a parse tree produced by DAXParser#argumentList.
    def enterArgumentList(self, ctx:DAXParser.ArgumentListContext):
        pass

    # Exit a parse tree produced by DAXParser#argumentList.
    def exitArgumentList(self, ctx:DAXParser.ArgumentListContext):
        pass


    # Enter a parse tree produced by DAXParser#functionName.
    def enterFunctionName(self, ctx:DAXParser.FunctionNameContext):
        pass

    # Exit a parse tree produced by DAXParser#functionName.
    def exitFunctionName(self, ctx:DAXParser.FunctionNameContext):
        pass


    # Enter a parse tree produced by DAXParser#qualifiedReference.
    def enterQualifiedReference(self, ctx:DAXParser.QualifiedReferenceContext):
        pass

    # Exit a parse tree produced by DAXParser#qualifiedReference.
    def exitQualifiedReference(self, ctx:DAXParser.QualifiedReferenceContext):
        pass


    # Enter a parse tree produced by DAXParser#tableQualifier.
    def enterTableQualifier(self, ctx:DAXParser.TableQualifierContext):
        pass

    # Exit a parse tree produced by DAXParser#tableQualifier.
    def exitTableQualifier(self, ctx:DAXParser.TableQualifierContext):
        pass


    # Enter a parse tree produced by DAXParser#standaloneReference.
    def enterStandaloneReference(self, ctx:DAXParser.StandaloneReferenceContext):
        pass

    # Exit a parse tree produced by DAXParser#standaloneReference.
    def exitStandaloneReference(self, ctx:DAXParser.StandaloneReferenceContext):
        pass


    # Enter a parse tree produced by DAXParser#bareTableReference.
    def enterBareTableReference(self, ctx:DAXParser.BareTableReferenceContext):
        pass

    # Exit a parse tree produced by DAXParser#bareTableReference.
    def exitBareTableReference(self, ctx:DAXParser.BareTableReferenceContext):
        pass


    # Enter a parse tree produced by DAXParser#identifier.
    def enterIdentifier(self, ctx:DAXParser.IdentifierContext):
        pass

    # Exit a parse tree produced by DAXParser#identifier.
    def exitIdentifier(self, ctx:DAXParser.IdentifierContext):
        pass


    # Enter a parse tree produced by DAXParser#identifierPart.
    def enterIdentifierPart(self, ctx:DAXParser.IdentifierPartContext):
        pass

    # Exit a parse tree produced by DAXParser#identifierPart.
    def exitIdentifierPart(self, ctx:DAXParser.IdentifierPartContext):
        pass


    # Enter a parse tree produced by DAXParser#tableConstructor.
    def enterTableConstructor(self, ctx:DAXParser.TableConstructorContext):
        pass

    # Exit a parse tree produced by DAXParser#tableConstructor.
    def exitTableConstructor(self, ctx:DAXParser.TableConstructorContext):
        pass


    # Enter a parse tree produced by DAXParser#tupleConstructor.
    def enterTupleConstructor(self, ctx:DAXParser.TupleConstructorContext):
        pass

    # Exit a parse tree produced by DAXParser#tupleConstructor.
    def exitTupleConstructor(self, ctx:DAXParser.TupleConstructorContext):
        pass



del DAXParser