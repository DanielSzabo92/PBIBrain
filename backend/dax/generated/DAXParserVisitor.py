# Generated from backend/dax/grammar/DAXParser.g4 by ANTLR 4.13.2
from antlr4 import *
if "." in __name__:
    from .DAXParser import DAXParser
else:
    from DAXParser import DAXParser

# This class defines a complete generic visitor for a parse tree produced by DAXParser.

class DAXParserVisitor(ParseTreeVisitor):

    # Visit a parse tree produced by DAXParser#parse.
    def visitParse(self, ctx:DAXParser.ParseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by DAXParser#varExpression.
    def visitVarExpression(self, ctx:DAXParser.VarExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by DAXParser#logicalExpression.
    def visitLogicalExpression(self, ctx:DAXParser.LogicalExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by DAXParser#varBlock.
    def visitVarBlock(self, ctx:DAXParser.VarBlockContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by DAXParser#varBinding.
    def visitVarBinding(self, ctx:DAXParser.VarBindingContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by DAXParser#logicalOr.
    def visitLogicalOr(self, ctx:DAXParser.LogicalOrContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by DAXParser#logicalAnd.
    def visitLogicalAnd(self, ctx:DAXParser.LogicalAndContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by DAXParser#comparison.
    def visitComparison(self, ctx:DAXParser.ComparisonContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by DAXParser#additive.
    def visitAdditive(self, ctx:DAXParser.AdditiveContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by DAXParser#multiplicative.
    def visitMultiplicative(self, ctx:DAXParser.MultiplicativeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by DAXParser#concatenation.
    def visitConcatenation(self, ctx:DAXParser.ConcatenationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by DAXParser#unary.
    def visitUnary(self, ctx:DAXParser.UnaryContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by DAXParser#power.
    def visitPower(self, ctx:DAXParser.PowerContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by DAXParser#literalPrimary.
    def visitLiteralPrimary(self, ctx:DAXParser.LiteralPrimaryContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by DAXParser#functionPrimary.
    def visitFunctionPrimary(self, ctx:DAXParser.FunctionPrimaryContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by DAXParser#qualifiedReferencePrimary.
    def visitQualifiedReferencePrimary(self, ctx:DAXParser.QualifiedReferencePrimaryContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by DAXParser#standaloneReferencePrimary.
    def visitStandaloneReferencePrimary(self, ctx:DAXParser.StandaloneReferencePrimaryContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by DAXParser#bareTableReferencePrimary.
    def visitBareTableReferencePrimary(self, ctx:DAXParser.BareTableReferencePrimaryContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by DAXParser#identifierPrimary.
    def visitIdentifierPrimary(self, ctx:DAXParser.IdentifierPrimaryContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by DAXParser#tupleConstructorPrimary.
    def visitTupleConstructorPrimary(self, ctx:DAXParser.TupleConstructorPrimaryContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by DAXParser#tableConstructorPrimary.
    def visitTableConstructorPrimary(self, ctx:DAXParser.TableConstructorPrimaryContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by DAXParser#parenthesizedPrimary.
    def visitParenthesizedPrimary(self, ctx:DAXParser.ParenthesizedPrimaryContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by DAXParser#stringLiteral.
    def visitStringLiteral(self, ctx:DAXParser.StringLiteralContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by DAXParser#numberLiteral.
    def visitNumberLiteral(self, ctx:DAXParser.NumberLiteralContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by DAXParser#dateLiteral.
    def visitDateLiteral(self, ctx:DAXParser.DateLiteralContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by DAXParser#datetimeLiteral.
    def visitDatetimeLiteral(self, ctx:DAXParser.DatetimeLiteralContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by DAXParser#functionCall.
    def visitFunctionCall(self, ctx:DAXParser.FunctionCallContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by DAXParser#argumentList.
    def visitArgumentList(self, ctx:DAXParser.ArgumentListContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by DAXParser#functionName.
    def visitFunctionName(self, ctx:DAXParser.FunctionNameContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by DAXParser#qualifiedReference.
    def visitQualifiedReference(self, ctx:DAXParser.QualifiedReferenceContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by DAXParser#tableQualifier.
    def visitTableQualifier(self, ctx:DAXParser.TableQualifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by DAXParser#standaloneReference.
    def visitStandaloneReference(self, ctx:DAXParser.StandaloneReferenceContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by DAXParser#bareTableReference.
    def visitBareTableReference(self, ctx:DAXParser.BareTableReferenceContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by DAXParser#identifier.
    def visitIdentifier(self, ctx:DAXParser.IdentifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by DAXParser#identifierPart.
    def visitIdentifierPart(self, ctx:DAXParser.IdentifierPartContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by DAXParser#tableConstructor.
    def visitTableConstructor(self, ctx:DAXParser.TableConstructorContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by DAXParser#tupleConstructor.
    def visitTupleConstructor(self, ctx:DAXParser.TupleConstructorContext):
        return self.visitChildren(ctx)



del DAXParser