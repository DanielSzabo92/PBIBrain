# Generated from backend/dax/grammar/DAXParser.g4 by ANTLR 4.13.2
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
        4,1,36,220,2,0,7,0,2,1,7,1,2,2,7,2,2,3,7,3,2,4,7,4,2,5,7,5,2,6,7,
        6,2,7,7,7,2,8,7,8,2,9,7,9,2,10,7,10,2,11,7,11,2,12,7,12,2,13,7,13,
        2,14,7,14,2,15,7,15,2,16,7,16,2,17,7,17,2,18,7,18,2,19,7,19,2,20,
        7,20,2,21,7,21,2,22,7,22,2,23,7,23,2,24,7,24,1,0,1,0,1,0,1,1,1,1,
        3,1,56,8,1,1,2,1,2,1,2,1,2,5,2,62,8,2,10,2,12,2,65,9,2,1,2,1,2,1,
        2,1,3,1,3,1,3,1,3,1,4,1,4,1,4,5,4,77,8,4,10,4,12,4,80,9,4,1,5,1,
        5,1,5,5,5,85,8,5,10,5,12,5,88,9,5,1,6,1,6,1,6,5,6,93,8,6,10,6,12,
        6,96,9,6,1,7,1,7,1,7,5,7,101,8,7,10,7,12,7,104,9,7,1,8,1,8,1,8,5,
        8,109,8,8,10,8,12,8,112,9,8,1,9,1,9,1,9,5,9,117,8,9,10,9,12,9,120,
        9,9,1,10,1,10,1,10,3,10,125,8,10,1,11,1,11,1,11,3,11,130,8,11,1,
        11,5,11,133,8,11,10,11,12,11,136,9,11,1,12,1,12,1,12,1,12,1,12,1,
        12,1,12,1,12,1,12,1,12,1,12,1,12,3,12,150,8,12,1,13,1,13,1,13,1,
        13,3,13,156,8,13,1,14,1,14,1,14,3,14,161,8,14,1,14,1,14,1,15,1,15,
        1,15,5,15,168,8,15,10,15,12,15,171,9,15,1,16,1,16,1,16,5,16,176,
        8,16,10,16,12,16,179,9,16,1,17,1,17,1,17,1,18,1,18,1,19,1,19,1,20,
        1,20,1,21,1,21,1,22,1,22,1,23,1,23,1,23,1,23,5,23,198,8,23,10,23,
        12,23,201,9,23,3,23,203,8,23,1,23,1,23,1,24,1,24,1,24,1,24,1,24,
        1,24,5,24,213,8,24,10,24,12,24,216,9,24,1,24,1,24,1,24,0,0,25,0,
        2,4,6,8,10,12,14,16,18,20,22,24,26,28,30,32,34,36,38,40,42,44,46,
        48,0,9,2,0,3,3,7,12,1,0,13,14,1,0,15,17,2,0,4,4,13,14,1,0,25,26,
        2,0,27,27,33,33,1,0,27,28,3,0,2,4,27,28,33,33,3,0,2,4,27,27,33,33,
        222,0,50,1,0,0,0,2,55,1,0,0,0,4,57,1,0,0,0,6,69,1,0,0,0,8,73,1,0,
        0,0,10,81,1,0,0,0,12,89,1,0,0,0,14,97,1,0,0,0,16,105,1,0,0,0,18,
        113,1,0,0,0,20,124,1,0,0,0,22,126,1,0,0,0,24,149,1,0,0,0,26,155,
        1,0,0,0,28,157,1,0,0,0,30,164,1,0,0,0,32,172,1,0,0,0,34,180,1,0,
        0,0,36,183,1,0,0,0,38,185,1,0,0,0,40,187,1,0,0,0,42,189,1,0,0,0,
        44,191,1,0,0,0,46,193,1,0,0,0,48,206,1,0,0,0,50,51,3,2,1,0,51,52,
        5,0,0,1,52,1,1,0,0,0,53,56,3,4,2,0,54,56,3,8,4,0,55,53,1,0,0,0,55,
        54,1,0,0,0,56,3,1,0,0,0,57,58,5,1,0,0,58,63,3,6,3,0,59,60,5,1,0,
        0,60,62,3,6,3,0,61,59,1,0,0,0,62,65,1,0,0,0,63,61,1,0,0,0,63,64,
        1,0,0,0,64,66,1,0,0,0,65,63,1,0,0,0,66,67,5,2,0,0,67,68,3,2,1,0,
        68,5,1,0,0,0,69,70,3,42,21,0,70,71,5,7,0,0,71,72,3,2,1,0,72,7,1,
        0,0,0,73,78,3,10,5,0,74,75,5,5,0,0,75,77,3,10,5,0,76,74,1,0,0,0,
        77,80,1,0,0,0,78,76,1,0,0,0,78,79,1,0,0,0,79,9,1,0,0,0,80,78,1,0,
        0,0,81,86,3,12,6,0,82,83,5,6,0,0,83,85,3,12,6,0,84,82,1,0,0,0,85,
        88,1,0,0,0,86,84,1,0,0,0,86,87,1,0,0,0,87,11,1,0,0,0,88,86,1,0,0,
        0,89,94,3,18,9,0,90,91,7,0,0,0,91,93,3,18,9,0,92,90,1,0,0,0,93,96,
        1,0,0,0,94,92,1,0,0,0,94,95,1,0,0,0,95,13,1,0,0,0,96,94,1,0,0,0,
        97,102,3,16,8,0,98,99,7,1,0,0,99,101,3,16,8,0,100,98,1,0,0,0,101,
        104,1,0,0,0,102,100,1,0,0,0,102,103,1,0,0,0,103,15,1,0,0,0,104,102,
        1,0,0,0,105,110,3,20,10,0,106,107,7,2,0,0,107,109,3,20,10,0,108,
        106,1,0,0,0,109,112,1,0,0,0,110,108,1,0,0,0,110,111,1,0,0,0,111,
        17,1,0,0,0,112,110,1,0,0,0,113,118,3,14,7,0,114,115,5,18,0,0,115,
        117,3,14,7,0,116,114,1,0,0,0,117,120,1,0,0,0,118,116,1,0,0,0,118,
        119,1,0,0,0,119,19,1,0,0,0,120,118,1,0,0,0,121,122,7,3,0,0,122,125,
        3,20,10,0,123,125,3,22,11,0,124,121,1,0,0,0,124,123,1,0,0,0,125,
        21,1,0,0,0,126,134,3,24,12,0,127,129,5,19,0,0,128,130,7,1,0,0,129,
        128,1,0,0,0,129,130,1,0,0,0,130,131,1,0,0,0,131,133,3,24,12,0,132,
        127,1,0,0,0,133,136,1,0,0,0,134,132,1,0,0,0,134,135,1,0,0,0,135,
        23,1,0,0,0,136,134,1,0,0,0,137,150,3,26,13,0,138,150,3,28,14,0,139,
        150,3,34,17,0,140,150,3,38,19,0,141,150,3,40,20,0,142,150,3,42,21,
        0,143,150,3,48,24,0,144,150,3,46,23,0,145,146,5,20,0,0,146,147,3,
        2,1,0,147,148,5,21,0,0,148,150,1,0,0,0,149,137,1,0,0,0,149,138,1,
        0,0,0,149,139,1,0,0,0,149,140,1,0,0,0,149,141,1,0,0,0,149,142,1,
        0,0,0,149,143,1,0,0,0,149,144,1,0,0,0,149,145,1,0,0,0,150,25,1,0,
        0,0,151,156,5,29,0,0,152,156,5,32,0,0,153,156,5,30,0,0,154,156,5,
        31,0,0,155,151,1,0,0,0,155,152,1,0,0,0,155,153,1,0,0,0,155,154,1,
        0,0,0,156,27,1,0,0,0,157,158,3,32,16,0,158,160,5,20,0,0,159,161,
        3,30,15,0,160,159,1,0,0,0,160,161,1,0,0,0,161,162,1,0,0,0,162,163,
        5,21,0,0,163,29,1,0,0,0,164,169,3,2,1,0,165,166,5,24,0,0,166,168,
        3,2,1,0,167,165,1,0,0,0,168,171,1,0,0,0,169,167,1,0,0,0,169,170,
        1,0,0,0,170,31,1,0,0,0,171,169,1,0,0,0,172,177,3,44,22,0,173,174,
        7,4,0,0,174,176,3,44,22,0,175,173,1,0,0,0,176,179,1,0,0,0,177,175,
        1,0,0,0,177,178,1,0,0,0,178,33,1,0,0,0,179,177,1,0,0,0,180,181,3,
        36,18,0,181,182,5,28,0,0,182,35,1,0,0,0,183,184,7,5,0,0,184,37,1,
        0,0,0,185,186,7,6,0,0,186,39,1,0,0,0,187,188,5,33,0,0,188,41,1,0,
        0,0,189,190,7,7,0,0,190,43,1,0,0,0,191,192,7,8,0,0,192,45,1,0,0,
        0,193,202,5,22,0,0,194,199,3,2,1,0,195,196,5,24,0,0,196,198,3,2,
        1,0,197,195,1,0,0,0,198,201,1,0,0,0,199,197,1,0,0,0,199,200,1,0,
        0,0,200,203,1,0,0,0,201,199,1,0,0,0,202,194,1,0,0,0,202,203,1,0,
        0,0,203,204,1,0,0,0,204,205,5,23,0,0,205,47,1,0,0,0,206,207,5,20,
        0,0,207,208,3,2,1,0,208,209,5,24,0,0,209,214,3,2,1,0,210,211,5,24,
        0,0,211,213,3,2,1,0,212,210,1,0,0,0,213,216,1,0,0,0,214,212,1,0,
        0,0,214,215,1,0,0,0,215,217,1,0,0,0,216,214,1,0,0,0,217,218,5,21,
        0,0,218,49,1,0,0,0,19,55,63,78,86,94,102,110,118,124,129,134,149,
        155,160,169,177,199,202,214
    ]

class DAXParser ( Parser ):

    grammarFileName = "DAXParser.g4"

    atn = ATNDeserializer().deserialize(serializedATN())

    decisionsToDFA = [ DFA(ds, i) for i, ds in enumerate(atn.decisionToState) ]

    sharedContextCache = PredictionContextCache()

    literalNames = [ "<INVALID>", "<INVALID>", "<INVALID>", "<INVALID>", 
                     "<INVALID>", "'||'", "'&&'", "<INVALID>", "<INVALID>", 
                     "'<='", "'>='", "'<'", "'>'", "'+'", "'-'", "'*'", 
                     "'/'", "'%'", "'&'", "'^'", "'('", "')'", "'{'", "'}'", 
                     "','", "'.'", "'::'" ]

    symbolicNames = [ "<INVALID>", "VAR", "RETURN", "IN", "NOT", "OR_OP", 
                      "AND_OP", "EQ", "NEQ", "LTE", "GTE", "LT", "GT", "PLUS", 
                      "MINUS", "STAR", "SLASH", "PERCENT", "AMP", "POW", 
                      "LPAREN", "RPAREN", "LBRACE", "RBRACE", "COMMA", "DOT", 
                      "COLON2", "TABLE_NAME", "BRACKET_IDENT", "STRING", 
                      "DATE_LITERAL", "DATETIME_LITERAL", "NUMBER", "IDENTIFIER", 
                      "LINE_COMMENT", "BLOCK_COMMENT", "WS" ]

    RULE_parse = 0
    RULE_expression = 1
    RULE_varBlock = 2
    RULE_varBinding = 3
    RULE_logicalOr = 4
    RULE_logicalAnd = 5
    RULE_comparison = 6
    RULE_additive = 7
    RULE_multiplicative = 8
    RULE_concatenation = 9
    RULE_unary = 10
    RULE_power = 11
    RULE_primary = 12
    RULE_literal = 13
    RULE_functionCall = 14
    RULE_argumentList = 15
    RULE_functionName = 16
    RULE_qualifiedReference = 17
    RULE_tableQualifier = 18
    RULE_standaloneReference = 19
    RULE_bareTableReference = 20
    RULE_identifier = 21
    RULE_identifierPart = 22
    RULE_tableConstructor = 23
    RULE_tupleConstructor = 24

    ruleNames =  [ "parse", "expression", "varBlock", "varBinding", "logicalOr", 
                   "logicalAnd", "comparison", "additive", "multiplicative", 
                   "concatenation", "unary", "power", "primary", "literal", 
                   "functionCall", "argumentList", "functionName", "qualifiedReference", 
                   "tableQualifier", "standaloneReference", "bareTableReference", 
                   "identifier", "identifierPart", "tableConstructor", "tupleConstructor" ]

    EOF = Token.EOF
    VAR=1
    RETURN=2
    IN=3
    NOT=4
    OR_OP=5
    AND_OP=6
    EQ=7
    NEQ=8
    LTE=9
    GTE=10
    LT=11
    GT=12
    PLUS=13
    MINUS=14
    STAR=15
    SLASH=16
    PERCENT=17
    AMP=18
    POW=19
    LPAREN=20
    RPAREN=21
    LBRACE=22
    RBRACE=23
    COMMA=24
    DOT=25
    COLON2=26
    TABLE_NAME=27
    BRACKET_IDENT=28
    STRING=29
    DATE_LITERAL=30
    DATETIME_LITERAL=31
    NUMBER=32
    IDENTIFIER=33
    LINE_COMMENT=34
    BLOCK_COMMENT=35
    WS=36

    def __init__(self, input:TokenStream, output:TextIO = sys.stdout):
        super().__init__(input, output)
        self.checkVersion("4.13.2")
        self._interp = ParserATNSimulator(self, self.atn, self.decisionsToDFA, self.sharedContextCache)
        self._predicates = None




    class ParseContext(ParserRuleContext):
        __slots__ = 'parser'

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def expression(self):
            return self.getTypedRuleContext(DAXParser.ExpressionContext,0)


        def EOF(self):
            return self.getToken(DAXParser.EOF, 0)

        def getRuleIndex(self):
            return DAXParser.RULE_parse

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterParse" ):
                listener.enterParse(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitParse" ):
                listener.exitParse(self)

        def accept(self, visitor:ParseTreeVisitor):
            if hasattr( visitor, "visitParse" ):
                return visitor.visitParse(self)
            else:
                return visitor.visitChildren(self)




    def parse(self):

        localctx = DAXParser.ParseContext(self, self._ctx, self.state)
        self.enterRule(localctx, 0, self.RULE_parse)
        try:
            self.enterOuterAlt(localctx, 1)
            self.state = 50
            self.expression()
            self.state = 51
            self.match(DAXParser.EOF)
        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx


    class ExpressionContext(ParserRuleContext):
        __slots__ = 'parser'

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser


        def getRuleIndex(self):
            return DAXParser.RULE_expression

     
        def copyFrom(self, ctx:ParserRuleContext):
            super().copyFrom(ctx)



    class VarExpressionContext(ExpressionContext):

        def __init__(self, parser, ctx:ParserRuleContext): # actually a DAXParser.ExpressionContext
            super().__init__(parser)
            self.copyFrom(ctx)

        def varBlock(self):
            return self.getTypedRuleContext(DAXParser.VarBlockContext,0)


        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterVarExpression" ):
                listener.enterVarExpression(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitVarExpression" ):
                listener.exitVarExpression(self)

        def accept(self, visitor:ParseTreeVisitor):
            if hasattr( visitor, "visitVarExpression" ):
                return visitor.visitVarExpression(self)
            else:
                return visitor.visitChildren(self)


    class LogicalExpressionContext(ExpressionContext):

        def __init__(self, parser, ctx:ParserRuleContext): # actually a DAXParser.ExpressionContext
            super().__init__(parser)
            self.copyFrom(ctx)

        def logicalOr(self):
            return self.getTypedRuleContext(DAXParser.LogicalOrContext,0)


        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterLogicalExpression" ):
                listener.enterLogicalExpression(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitLogicalExpression" ):
                listener.exitLogicalExpression(self)

        def accept(self, visitor:ParseTreeVisitor):
            if hasattr( visitor, "visitLogicalExpression" ):
                return visitor.visitLogicalExpression(self)
            else:
                return visitor.visitChildren(self)



    def expression(self):

        localctx = DAXParser.ExpressionContext(self, self._ctx, self.state)
        self.enterRule(localctx, 2, self.RULE_expression)
        try:
            self.state = 55
            self._errHandler.sync(self)
            token = self._input.LA(1)
            if token in [1]:
                localctx = DAXParser.VarExpressionContext(self, localctx)
                self.enterOuterAlt(localctx, 1)
                self.state = 53
                self.varBlock()
                pass
            elif token in [2, 3, 4, 13, 14, 20, 22, 27, 28, 29, 30, 31, 32, 33]:
                localctx = DAXParser.LogicalExpressionContext(self, localctx)
                self.enterOuterAlt(localctx, 2)
                self.state = 54
                self.logicalOr()
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


    class VarBlockContext(ParserRuleContext):
        __slots__ = 'parser'

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def VAR(self, i:int=None):
            if i is None:
                return self.getTokens(DAXParser.VAR)
            else:
                return self.getToken(DAXParser.VAR, i)

        def varBinding(self, i:int=None):
            if i is None:
                return self.getTypedRuleContexts(DAXParser.VarBindingContext)
            else:
                return self.getTypedRuleContext(DAXParser.VarBindingContext,i)


        def RETURN(self):
            return self.getToken(DAXParser.RETURN, 0)

        def expression(self):
            return self.getTypedRuleContext(DAXParser.ExpressionContext,0)


        def getRuleIndex(self):
            return DAXParser.RULE_varBlock

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterVarBlock" ):
                listener.enterVarBlock(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitVarBlock" ):
                listener.exitVarBlock(self)

        def accept(self, visitor:ParseTreeVisitor):
            if hasattr( visitor, "visitVarBlock" ):
                return visitor.visitVarBlock(self)
            else:
                return visitor.visitChildren(self)




    def varBlock(self):

        localctx = DAXParser.VarBlockContext(self, self._ctx, self.state)
        self.enterRule(localctx, 4, self.RULE_varBlock)
        self._la = 0 # Token type
        try:
            self.enterOuterAlt(localctx, 1)
            self.state = 57
            self.match(DAXParser.VAR)
            self.state = 58
            self.varBinding()
            self.state = 63
            self._errHandler.sync(self)
            _la = self._input.LA(1)
            while _la==1:
                self.state = 59
                self.match(DAXParser.VAR)
                self.state = 60
                self.varBinding()
                self.state = 65
                self._errHandler.sync(self)
                _la = self._input.LA(1)

            self.state = 66
            self.match(DAXParser.RETURN)
            self.state = 67
            self.expression()
        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx


    class VarBindingContext(ParserRuleContext):
        __slots__ = 'parser'

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def identifier(self):
            return self.getTypedRuleContext(DAXParser.IdentifierContext,0)


        def EQ(self):
            return self.getToken(DAXParser.EQ, 0)

        def expression(self):
            return self.getTypedRuleContext(DAXParser.ExpressionContext,0)


        def getRuleIndex(self):
            return DAXParser.RULE_varBinding

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterVarBinding" ):
                listener.enterVarBinding(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitVarBinding" ):
                listener.exitVarBinding(self)

        def accept(self, visitor:ParseTreeVisitor):
            if hasattr( visitor, "visitVarBinding" ):
                return visitor.visitVarBinding(self)
            else:
                return visitor.visitChildren(self)




    def varBinding(self):

        localctx = DAXParser.VarBindingContext(self, self._ctx, self.state)
        self.enterRule(localctx, 6, self.RULE_varBinding)
        try:
            self.enterOuterAlt(localctx, 1)
            self.state = 69
            self.identifier()
            self.state = 70
            self.match(DAXParser.EQ)
            self.state = 71
            self.expression()
        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx


    class LogicalOrContext(ParserRuleContext):
        __slots__ = 'parser'

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def logicalAnd(self, i:int=None):
            if i is None:
                return self.getTypedRuleContexts(DAXParser.LogicalAndContext)
            else:
                return self.getTypedRuleContext(DAXParser.LogicalAndContext,i)


        def OR_OP(self, i:int=None):
            if i is None:
                return self.getTokens(DAXParser.OR_OP)
            else:
                return self.getToken(DAXParser.OR_OP, i)

        def getRuleIndex(self):
            return DAXParser.RULE_logicalOr

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterLogicalOr" ):
                listener.enterLogicalOr(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitLogicalOr" ):
                listener.exitLogicalOr(self)

        def accept(self, visitor:ParseTreeVisitor):
            if hasattr( visitor, "visitLogicalOr" ):
                return visitor.visitLogicalOr(self)
            else:
                return visitor.visitChildren(self)




    def logicalOr(self):

        localctx = DAXParser.LogicalOrContext(self, self._ctx, self.state)
        self.enterRule(localctx, 8, self.RULE_logicalOr)
        self._la = 0 # Token type
        try:
            self.enterOuterAlt(localctx, 1)
            self.state = 73
            self.logicalAnd()
            self.state = 78
            self._errHandler.sync(self)
            _la = self._input.LA(1)
            while _la==5:
                self.state = 74
                self.match(DAXParser.OR_OP)
                self.state = 75
                self.logicalAnd()
                self.state = 80
                self._errHandler.sync(self)
                _la = self._input.LA(1)

        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx


    class LogicalAndContext(ParserRuleContext):
        __slots__ = 'parser'

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def comparison(self, i:int=None):
            if i is None:
                return self.getTypedRuleContexts(DAXParser.ComparisonContext)
            else:
                return self.getTypedRuleContext(DAXParser.ComparisonContext,i)


        def AND_OP(self, i:int=None):
            if i is None:
                return self.getTokens(DAXParser.AND_OP)
            else:
                return self.getToken(DAXParser.AND_OP, i)

        def getRuleIndex(self):
            return DAXParser.RULE_logicalAnd

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterLogicalAnd" ):
                listener.enterLogicalAnd(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitLogicalAnd" ):
                listener.exitLogicalAnd(self)

        def accept(self, visitor:ParseTreeVisitor):
            if hasattr( visitor, "visitLogicalAnd" ):
                return visitor.visitLogicalAnd(self)
            else:
                return visitor.visitChildren(self)




    def logicalAnd(self):

        localctx = DAXParser.LogicalAndContext(self, self._ctx, self.state)
        self.enterRule(localctx, 10, self.RULE_logicalAnd)
        self._la = 0 # Token type
        try:
            self.enterOuterAlt(localctx, 1)
            self.state = 81
            self.comparison()
            self.state = 86
            self._errHandler.sync(self)
            _la = self._input.LA(1)
            while _la==6:
                self.state = 82
                self.match(DAXParser.AND_OP)
                self.state = 83
                self.comparison()
                self.state = 88
                self._errHandler.sync(self)
                _la = self._input.LA(1)

        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx


    class ComparisonContext(ParserRuleContext):
        __slots__ = 'parser'

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def concatenation(self, i:int=None):
            if i is None:
                return self.getTypedRuleContexts(DAXParser.ConcatenationContext)
            else:
                return self.getTypedRuleContext(DAXParser.ConcatenationContext,i)


        def EQ(self, i:int=None):
            if i is None:
                return self.getTokens(DAXParser.EQ)
            else:
                return self.getToken(DAXParser.EQ, i)

        def NEQ(self, i:int=None):
            if i is None:
                return self.getTokens(DAXParser.NEQ)
            else:
                return self.getToken(DAXParser.NEQ, i)

        def LTE(self, i:int=None):
            if i is None:
                return self.getTokens(DAXParser.LTE)
            else:
                return self.getToken(DAXParser.LTE, i)

        def LT(self, i:int=None):
            if i is None:
                return self.getTokens(DAXParser.LT)
            else:
                return self.getToken(DAXParser.LT, i)

        def GTE(self, i:int=None):
            if i is None:
                return self.getTokens(DAXParser.GTE)
            else:
                return self.getToken(DAXParser.GTE, i)

        def GT(self, i:int=None):
            if i is None:
                return self.getTokens(DAXParser.GT)
            else:
                return self.getToken(DAXParser.GT, i)

        def IN(self, i:int=None):
            if i is None:
                return self.getTokens(DAXParser.IN)
            else:
                return self.getToken(DAXParser.IN, i)

        def getRuleIndex(self):
            return DAXParser.RULE_comparison

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterComparison" ):
                listener.enterComparison(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitComparison" ):
                listener.exitComparison(self)

        def accept(self, visitor:ParseTreeVisitor):
            if hasattr( visitor, "visitComparison" ):
                return visitor.visitComparison(self)
            else:
                return visitor.visitChildren(self)




    def comparison(self):

        localctx = DAXParser.ComparisonContext(self, self._ctx, self.state)
        self.enterRule(localctx, 12, self.RULE_comparison)
        self._la = 0 # Token type
        try:
            self.enterOuterAlt(localctx, 1)
            self.state = 89
            self.concatenation()
            self.state = 94
            self._errHandler.sync(self)
            _la = self._input.LA(1)
            while (((_la) & ~0x3f) == 0 and ((1 << _la) & 8072) != 0):
                self.state = 90
                _la = self._input.LA(1)
                if not((((_la) & ~0x3f) == 0 and ((1 << _la) & 8072) != 0)):
                    self._errHandler.recoverInline(self)
                else:
                    self._errHandler.reportMatch(self)
                    self.consume()
                self.state = 91
                self.concatenation()
                self.state = 96
                self._errHandler.sync(self)
                _la = self._input.LA(1)

        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx


    class AdditiveContext(ParserRuleContext):
        __slots__ = 'parser'

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def multiplicative(self, i:int=None):
            if i is None:
                return self.getTypedRuleContexts(DAXParser.MultiplicativeContext)
            else:
                return self.getTypedRuleContext(DAXParser.MultiplicativeContext,i)


        def PLUS(self, i:int=None):
            if i is None:
                return self.getTokens(DAXParser.PLUS)
            else:
                return self.getToken(DAXParser.PLUS, i)

        def MINUS(self, i:int=None):
            if i is None:
                return self.getTokens(DAXParser.MINUS)
            else:
                return self.getToken(DAXParser.MINUS, i)

        def getRuleIndex(self):
            return DAXParser.RULE_additive

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterAdditive" ):
                listener.enterAdditive(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitAdditive" ):
                listener.exitAdditive(self)

        def accept(self, visitor:ParseTreeVisitor):
            if hasattr( visitor, "visitAdditive" ):
                return visitor.visitAdditive(self)
            else:
                return visitor.visitChildren(self)




    def additive(self):

        localctx = DAXParser.AdditiveContext(self, self._ctx, self.state)
        self.enterRule(localctx, 14, self.RULE_additive)
        self._la = 0 # Token type
        try:
            self.enterOuterAlt(localctx, 1)
            self.state = 97
            self.multiplicative()
            self.state = 102
            self._errHandler.sync(self)
            _la = self._input.LA(1)
            while _la==13 or _la==14:
                self.state = 98
                _la = self._input.LA(1)
                if not(_la==13 or _la==14):
                    self._errHandler.recoverInline(self)
                else:
                    self._errHandler.reportMatch(self)
                    self.consume()
                self.state = 99
                self.multiplicative()
                self.state = 104
                self._errHandler.sync(self)
                _la = self._input.LA(1)

        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx


    class MultiplicativeContext(ParserRuleContext):
        __slots__ = 'parser'

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def unary(self, i:int=None):
            if i is None:
                return self.getTypedRuleContexts(DAXParser.UnaryContext)
            else:
                return self.getTypedRuleContext(DAXParser.UnaryContext,i)


        def STAR(self, i:int=None):
            if i is None:
                return self.getTokens(DAXParser.STAR)
            else:
                return self.getToken(DAXParser.STAR, i)

        def SLASH(self, i:int=None):
            if i is None:
                return self.getTokens(DAXParser.SLASH)
            else:
                return self.getToken(DAXParser.SLASH, i)

        def PERCENT(self, i:int=None):
            if i is None:
                return self.getTokens(DAXParser.PERCENT)
            else:
                return self.getToken(DAXParser.PERCENT, i)

        def getRuleIndex(self):
            return DAXParser.RULE_multiplicative

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterMultiplicative" ):
                listener.enterMultiplicative(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitMultiplicative" ):
                listener.exitMultiplicative(self)

        def accept(self, visitor:ParseTreeVisitor):
            if hasattr( visitor, "visitMultiplicative" ):
                return visitor.visitMultiplicative(self)
            else:
                return visitor.visitChildren(self)




    def multiplicative(self):

        localctx = DAXParser.MultiplicativeContext(self, self._ctx, self.state)
        self.enterRule(localctx, 16, self.RULE_multiplicative)
        self._la = 0 # Token type
        try:
            self.enterOuterAlt(localctx, 1)
            self.state = 105
            self.unary()
            self.state = 110
            self._errHandler.sync(self)
            _la = self._input.LA(1)
            while (((_la) & ~0x3f) == 0 and ((1 << _la) & 229376) != 0):
                self.state = 106
                _la = self._input.LA(1)
                if not((((_la) & ~0x3f) == 0 and ((1 << _la) & 229376) != 0)):
                    self._errHandler.recoverInline(self)
                else:
                    self._errHandler.reportMatch(self)
                    self.consume()
                self.state = 107
                self.unary()
                self.state = 112
                self._errHandler.sync(self)
                _la = self._input.LA(1)

        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx


    class ConcatenationContext(ParserRuleContext):
        __slots__ = 'parser'

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def additive(self, i:int=None):
            if i is None:
                return self.getTypedRuleContexts(DAXParser.AdditiveContext)
            else:
                return self.getTypedRuleContext(DAXParser.AdditiveContext,i)


        def AMP(self, i:int=None):
            if i is None:
                return self.getTokens(DAXParser.AMP)
            else:
                return self.getToken(DAXParser.AMP, i)

        def getRuleIndex(self):
            return DAXParser.RULE_concatenation

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterConcatenation" ):
                listener.enterConcatenation(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitConcatenation" ):
                listener.exitConcatenation(self)

        def accept(self, visitor:ParseTreeVisitor):
            if hasattr( visitor, "visitConcatenation" ):
                return visitor.visitConcatenation(self)
            else:
                return visitor.visitChildren(self)




    def concatenation(self):

        localctx = DAXParser.ConcatenationContext(self, self._ctx, self.state)
        self.enterRule(localctx, 18, self.RULE_concatenation)
        self._la = 0 # Token type
        try:
            self.enterOuterAlt(localctx, 1)
            self.state = 113
            self.additive()
            self.state = 118
            self._errHandler.sync(self)
            _la = self._input.LA(1)
            while _la==18:
                self.state = 114
                self.match(DAXParser.AMP)
                self.state = 115
                self.additive()
                self.state = 120
                self._errHandler.sync(self)
                _la = self._input.LA(1)

        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx


    class UnaryContext(ParserRuleContext):
        __slots__ = 'parser'

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def unary(self):
            return self.getTypedRuleContext(DAXParser.UnaryContext,0)


        def NOT(self):
            return self.getToken(DAXParser.NOT, 0)

        def PLUS(self):
            return self.getToken(DAXParser.PLUS, 0)

        def MINUS(self):
            return self.getToken(DAXParser.MINUS, 0)

        def power(self):
            return self.getTypedRuleContext(DAXParser.PowerContext,0)


        def getRuleIndex(self):
            return DAXParser.RULE_unary

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterUnary" ):
                listener.enterUnary(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitUnary" ):
                listener.exitUnary(self)

        def accept(self, visitor:ParseTreeVisitor):
            if hasattr( visitor, "visitUnary" ):
                return visitor.visitUnary(self)
            else:
                return visitor.visitChildren(self)




    def unary(self):

        localctx = DAXParser.UnaryContext(self, self._ctx, self.state)
        self.enterRule(localctx, 20, self.RULE_unary)
        self._la = 0 # Token type
        try:
            self.state = 124
            self._errHandler.sync(self)
            la_ = self._interp.adaptivePredict(self._input,8,self._ctx)
            if la_ == 1:
                self.enterOuterAlt(localctx, 1)
                self.state = 121
                _la = self._input.LA(1)
                if not((((_la) & ~0x3f) == 0 and ((1 << _la) & 24592) != 0)):
                    self._errHandler.recoverInline(self)
                else:
                    self._errHandler.reportMatch(self)
                    self.consume()
                self.state = 122
                self.unary()
                pass

            elif la_ == 2:
                self.enterOuterAlt(localctx, 2)
                self.state = 123
                self.power()
                pass


        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx


    class PowerContext(ParserRuleContext):
        __slots__ = 'parser'

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def primary(self, i:int=None):
            if i is None:
                return self.getTypedRuleContexts(DAXParser.PrimaryContext)
            else:
                return self.getTypedRuleContext(DAXParser.PrimaryContext,i)


        def POW(self, i:int=None):
            if i is None:
                return self.getTokens(DAXParser.POW)
            else:
                return self.getToken(DAXParser.POW, i)

        def PLUS(self, i:int=None):
            if i is None:
                return self.getTokens(DAXParser.PLUS)
            else:
                return self.getToken(DAXParser.PLUS, i)

        def MINUS(self, i:int=None):
            if i is None:
                return self.getTokens(DAXParser.MINUS)
            else:
                return self.getToken(DAXParser.MINUS, i)

        def getRuleIndex(self):
            return DAXParser.RULE_power

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterPower" ):
                listener.enterPower(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitPower" ):
                listener.exitPower(self)

        def accept(self, visitor:ParseTreeVisitor):
            if hasattr( visitor, "visitPower" ):
                return visitor.visitPower(self)
            else:
                return visitor.visitChildren(self)




    def power(self):

        localctx = DAXParser.PowerContext(self, self._ctx, self.state)
        self.enterRule(localctx, 22, self.RULE_power)
        self._la = 0 # Token type
        try:
            self.enterOuterAlt(localctx, 1)
            self.state = 126
            self.primary()
            self.state = 134
            self._errHandler.sync(self)
            _la = self._input.LA(1)
            while _la==19:
                self.state = 127
                self.match(DAXParser.POW)
                self.state = 129
                self._errHandler.sync(self)
                _la = self._input.LA(1)
                if _la==13 or _la==14:
                    self.state = 128
                    _la = self._input.LA(1)
                    if not(_la==13 or _la==14):
                        self._errHandler.recoverInline(self)
                    else:
                        self._errHandler.reportMatch(self)
                        self.consume()


                self.state = 131
                self.primary()
                self.state = 136
                self._errHandler.sync(self)
                _la = self._input.LA(1)

        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx


    class PrimaryContext(ParserRuleContext):
        __slots__ = 'parser'

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser


        def getRuleIndex(self):
            return DAXParser.RULE_primary

     
        def copyFrom(self, ctx:ParserRuleContext):
            super().copyFrom(ctx)



    class QualifiedReferencePrimaryContext(PrimaryContext):

        def __init__(self, parser, ctx:ParserRuleContext): # actually a DAXParser.PrimaryContext
            super().__init__(parser)
            self.copyFrom(ctx)

        def qualifiedReference(self):
            return self.getTypedRuleContext(DAXParser.QualifiedReferenceContext,0)


        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterQualifiedReferencePrimary" ):
                listener.enterQualifiedReferencePrimary(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitQualifiedReferencePrimary" ):
                listener.exitQualifiedReferencePrimary(self)

        def accept(self, visitor:ParseTreeVisitor):
            if hasattr( visitor, "visitQualifiedReferencePrimary" ):
                return visitor.visitQualifiedReferencePrimary(self)
            else:
                return visitor.visitChildren(self)


    class IdentifierPrimaryContext(PrimaryContext):

        def __init__(self, parser, ctx:ParserRuleContext): # actually a DAXParser.PrimaryContext
            super().__init__(parser)
            self.copyFrom(ctx)

        def identifier(self):
            return self.getTypedRuleContext(DAXParser.IdentifierContext,0)


        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterIdentifierPrimary" ):
                listener.enterIdentifierPrimary(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitIdentifierPrimary" ):
                listener.exitIdentifierPrimary(self)

        def accept(self, visitor:ParseTreeVisitor):
            if hasattr( visitor, "visitIdentifierPrimary" ):
                return visitor.visitIdentifierPrimary(self)
            else:
                return visitor.visitChildren(self)


    class StandaloneReferencePrimaryContext(PrimaryContext):

        def __init__(self, parser, ctx:ParserRuleContext): # actually a DAXParser.PrimaryContext
            super().__init__(parser)
            self.copyFrom(ctx)

        def standaloneReference(self):
            return self.getTypedRuleContext(DAXParser.StandaloneReferenceContext,0)


        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterStandaloneReferencePrimary" ):
                listener.enterStandaloneReferencePrimary(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitStandaloneReferencePrimary" ):
                listener.exitStandaloneReferencePrimary(self)

        def accept(self, visitor:ParseTreeVisitor):
            if hasattr( visitor, "visitStandaloneReferencePrimary" ):
                return visitor.visitStandaloneReferencePrimary(self)
            else:
                return visitor.visitChildren(self)


    class ParenthesizedPrimaryContext(PrimaryContext):

        def __init__(self, parser, ctx:ParserRuleContext): # actually a DAXParser.PrimaryContext
            super().__init__(parser)
            self.copyFrom(ctx)

        def LPAREN(self):
            return self.getToken(DAXParser.LPAREN, 0)
        def expression(self):
            return self.getTypedRuleContext(DAXParser.ExpressionContext,0)

        def RPAREN(self):
            return self.getToken(DAXParser.RPAREN, 0)

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterParenthesizedPrimary" ):
                listener.enterParenthesizedPrimary(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitParenthesizedPrimary" ):
                listener.exitParenthesizedPrimary(self)

        def accept(self, visitor:ParseTreeVisitor):
            if hasattr( visitor, "visitParenthesizedPrimary" ):
                return visitor.visitParenthesizedPrimary(self)
            else:
                return visitor.visitChildren(self)


    class FunctionPrimaryContext(PrimaryContext):

        def __init__(self, parser, ctx:ParserRuleContext): # actually a DAXParser.PrimaryContext
            super().__init__(parser)
            self.copyFrom(ctx)

        def functionCall(self):
            return self.getTypedRuleContext(DAXParser.FunctionCallContext,0)


        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterFunctionPrimary" ):
                listener.enterFunctionPrimary(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitFunctionPrimary" ):
                listener.exitFunctionPrimary(self)

        def accept(self, visitor:ParseTreeVisitor):
            if hasattr( visitor, "visitFunctionPrimary" ):
                return visitor.visitFunctionPrimary(self)
            else:
                return visitor.visitChildren(self)


    class BareTableReferencePrimaryContext(PrimaryContext):

        def __init__(self, parser, ctx:ParserRuleContext): # actually a DAXParser.PrimaryContext
            super().__init__(parser)
            self.copyFrom(ctx)

        def bareTableReference(self):
            return self.getTypedRuleContext(DAXParser.BareTableReferenceContext,0)


        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterBareTableReferencePrimary" ):
                listener.enterBareTableReferencePrimary(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitBareTableReferencePrimary" ):
                listener.exitBareTableReferencePrimary(self)

        def accept(self, visitor:ParseTreeVisitor):
            if hasattr( visitor, "visitBareTableReferencePrimary" ):
                return visitor.visitBareTableReferencePrimary(self)
            else:
                return visitor.visitChildren(self)


    class TableConstructorPrimaryContext(PrimaryContext):

        def __init__(self, parser, ctx:ParserRuleContext): # actually a DAXParser.PrimaryContext
            super().__init__(parser)
            self.copyFrom(ctx)

        def tableConstructor(self):
            return self.getTypedRuleContext(DAXParser.TableConstructorContext,0)


        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterTableConstructorPrimary" ):
                listener.enterTableConstructorPrimary(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitTableConstructorPrimary" ):
                listener.exitTableConstructorPrimary(self)

        def accept(self, visitor:ParseTreeVisitor):
            if hasattr( visitor, "visitTableConstructorPrimary" ):
                return visitor.visitTableConstructorPrimary(self)
            else:
                return visitor.visitChildren(self)


    class LiteralPrimaryContext(PrimaryContext):

        def __init__(self, parser, ctx:ParserRuleContext): # actually a DAXParser.PrimaryContext
            super().__init__(parser)
            self.copyFrom(ctx)

        def literal(self):
            return self.getTypedRuleContext(DAXParser.LiteralContext,0)


        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterLiteralPrimary" ):
                listener.enterLiteralPrimary(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitLiteralPrimary" ):
                listener.exitLiteralPrimary(self)

        def accept(self, visitor:ParseTreeVisitor):
            if hasattr( visitor, "visitLiteralPrimary" ):
                return visitor.visitLiteralPrimary(self)
            else:
                return visitor.visitChildren(self)


    class TupleConstructorPrimaryContext(PrimaryContext):

        def __init__(self, parser, ctx:ParserRuleContext): # actually a DAXParser.PrimaryContext
            super().__init__(parser)
            self.copyFrom(ctx)

        def tupleConstructor(self):
            return self.getTypedRuleContext(DAXParser.TupleConstructorContext,0)


        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterTupleConstructorPrimary" ):
                listener.enterTupleConstructorPrimary(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitTupleConstructorPrimary" ):
                listener.exitTupleConstructorPrimary(self)

        def accept(self, visitor:ParseTreeVisitor):
            if hasattr( visitor, "visitTupleConstructorPrimary" ):
                return visitor.visitTupleConstructorPrimary(self)
            else:
                return visitor.visitChildren(self)



    def primary(self):

        localctx = DAXParser.PrimaryContext(self, self._ctx, self.state)
        self.enterRule(localctx, 24, self.RULE_primary)
        try:
            self.state = 149
            self._errHandler.sync(self)
            la_ = self._interp.adaptivePredict(self._input,11,self._ctx)
            if la_ == 1:
                localctx = DAXParser.LiteralPrimaryContext(self, localctx)
                self.enterOuterAlt(localctx, 1)
                self.state = 137
                self.literal()
                pass

            elif la_ == 2:
                localctx = DAXParser.FunctionPrimaryContext(self, localctx)
                self.enterOuterAlt(localctx, 2)
                self.state = 138
                self.functionCall()
                pass

            elif la_ == 3:
                localctx = DAXParser.QualifiedReferencePrimaryContext(self, localctx)
                self.enterOuterAlt(localctx, 3)
                self.state = 139
                self.qualifiedReference()
                pass

            elif la_ == 4:
                localctx = DAXParser.StandaloneReferencePrimaryContext(self, localctx)
                self.enterOuterAlt(localctx, 4)
                self.state = 140
                self.standaloneReference()
                pass

            elif la_ == 5:
                localctx = DAXParser.BareTableReferencePrimaryContext(self, localctx)
                self.enterOuterAlt(localctx, 5)
                self.state = 141
                self.bareTableReference()
                pass

            elif la_ == 6:
                localctx = DAXParser.IdentifierPrimaryContext(self, localctx)
                self.enterOuterAlt(localctx, 6)
                self.state = 142
                self.identifier()
                pass

            elif la_ == 7:
                localctx = DAXParser.TupleConstructorPrimaryContext(self, localctx)
                self.enterOuterAlt(localctx, 7)
                self.state = 143
                self.tupleConstructor()
                pass

            elif la_ == 8:
                localctx = DAXParser.TableConstructorPrimaryContext(self, localctx)
                self.enterOuterAlt(localctx, 8)
                self.state = 144
                self.tableConstructor()
                pass

            elif la_ == 9:
                localctx = DAXParser.ParenthesizedPrimaryContext(self, localctx)
                self.enterOuterAlt(localctx, 9)
                self.state = 145
                self.match(DAXParser.LPAREN)
                self.state = 146
                self.expression()
                self.state = 147
                self.match(DAXParser.RPAREN)
                pass


        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx


    class LiteralContext(ParserRuleContext):
        __slots__ = 'parser'

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser


        def getRuleIndex(self):
            return DAXParser.RULE_literal

     
        def copyFrom(self, ctx:ParserRuleContext):
            super().copyFrom(ctx)



    class DatetimeLiteralContext(LiteralContext):

        def __init__(self, parser, ctx:ParserRuleContext): # actually a DAXParser.LiteralContext
            super().__init__(parser)
            self.copyFrom(ctx)

        def DATETIME_LITERAL(self):
            return self.getToken(DAXParser.DATETIME_LITERAL, 0)

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterDatetimeLiteral" ):
                listener.enterDatetimeLiteral(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitDatetimeLiteral" ):
                listener.exitDatetimeLiteral(self)

        def accept(self, visitor:ParseTreeVisitor):
            if hasattr( visitor, "visitDatetimeLiteral" ):
                return visitor.visitDatetimeLiteral(self)
            else:
                return visitor.visitChildren(self)


    class StringLiteralContext(LiteralContext):

        def __init__(self, parser, ctx:ParserRuleContext): # actually a DAXParser.LiteralContext
            super().__init__(parser)
            self.copyFrom(ctx)

        def STRING(self):
            return self.getToken(DAXParser.STRING, 0)

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterStringLiteral" ):
                listener.enterStringLiteral(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitStringLiteral" ):
                listener.exitStringLiteral(self)

        def accept(self, visitor:ParseTreeVisitor):
            if hasattr( visitor, "visitStringLiteral" ):
                return visitor.visitStringLiteral(self)
            else:
                return visitor.visitChildren(self)


    class DateLiteralContext(LiteralContext):

        def __init__(self, parser, ctx:ParserRuleContext): # actually a DAXParser.LiteralContext
            super().__init__(parser)
            self.copyFrom(ctx)

        def DATE_LITERAL(self):
            return self.getToken(DAXParser.DATE_LITERAL, 0)

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterDateLiteral" ):
                listener.enterDateLiteral(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitDateLiteral" ):
                listener.exitDateLiteral(self)

        def accept(self, visitor:ParseTreeVisitor):
            if hasattr( visitor, "visitDateLiteral" ):
                return visitor.visitDateLiteral(self)
            else:
                return visitor.visitChildren(self)


    class NumberLiteralContext(LiteralContext):

        def __init__(self, parser, ctx:ParserRuleContext): # actually a DAXParser.LiteralContext
            super().__init__(parser)
            self.copyFrom(ctx)

        def NUMBER(self):
            return self.getToken(DAXParser.NUMBER, 0)

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterNumberLiteral" ):
                listener.enterNumberLiteral(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitNumberLiteral" ):
                listener.exitNumberLiteral(self)

        def accept(self, visitor:ParseTreeVisitor):
            if hasattr( visitor, "visitNumberLiteral" ):
                return visitor.visitNumberLiteral(self)
            else:
                return visitor.visitChildren(self)



    def literal(self):

        localctx = DAXParser.LiteralContext(self, self._ctx, self.state)
        self.enterRule(localctx, 26, self.RULE_literal)
        try:
            self.state = 155
            self._errHandler.sync(self)
            token = self._input.LA(1)
            if token in [29]:
                localctx = DAXParser.StringLiteralContext(self, localctx)
                self.enterOuterAlt(localctx, 1)
                self.state = 151
                self.match(DAXParser.STRING)
                pass
            elif token in [32]:
                localctx = DAXParser.NumberLiteralContext(self, localctx)
                self.enterOuterAlt(localctx, 2)
                self.state = 152
                self.match(DAXParser.NUMBER)
                pass
            elif token in [30]:
                localctx = DAXParser.DateLiteralContext(self, localctx)
                self.enterOuterAlt(localctx, 3)
                self.state = 153
                self.match(DAXParser.DATE_LITERAL)
                pass
            elif token in [31]:
                localctx = DAXParser.DatetimeLiteralContext(self, localctx)
                self.enterOuterAlt(localctx, 4)
                self.state = 154
                self.match(DAXParser.DATETIME_LITERAL)
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


    class FunctionCallContext(ParserRuleContext):
        __slots__ = 'parser'

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def functionName(self):
            return self.getTypedRuleContext(DAXParser.FunctionNameContext,0)


        def LPAREN(self):
            return self.getToken(DAXParser.LPAREN, 0)

        def RPAREN(self):
            return self.getToken(DAXParser.RPAREN, 0)

        def argumentList(self):
            return self.getTypedRuleContext(DAXParser.ArgumentListContext,0)


        def getRuleIndex(self):
            return DAXParser.RULE_functionCall

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterFunctionCall" ):
                listener.enterFunctionCall(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitFunctionCall" ):
                listener.exitFunctionCall(self)

        def accept(self, visitor:ParseTreeVisitor):
            if hasattr( visitor, "visitFunctionCall" ):
                return visitor.visitFunctionCall(self)
            else:
                return visitor.visitChildren(self)




    def functionCall(self):

        localctx = DAXParser.FunctionCallContext(self, self._ctx, self.state)
        self.enterRule(localctx, 28, self.RULE_functionCall)
        self._la = 0 # Token type
        try:
            self.enterOuterAlt(localctx, 1)
            self.state = 157
            self.functionName()
            self.state = 158
            self.match(DAXParser.LPAREN)
            self.state = 160
            self._errHandler.sync(self)
            _la = self._input.LA(1)
            if (((_la) & ~0x3f) == 0 and ((1 << _la) & 17050918942) != 0):
                self.state = 159
                self.argumentList()


            self.state = 162
            self.match(DAXParser.RPAREN)
        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx


    class ArgumentListContext(ParserRuleContext):
        __slots__ = 'parser'

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def expression(self, i:int=None):
            if i is None:
                return self.getTypedRuleContexts(DAXParser.ExpressionContext)
            else:
                return self.getTypedRuleContext(DAXParser.ExpressionContext,i)


        def COMMA(self, i:int=None):
            if i is None:
                return self.getTokens(DAXParser.COMMA)
            else:
                return self.getToken(DAXParser.COMMA, i)

        def getRuleIndex(self):
            return DAXParser.RULE_argumentList

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterArgumentList" ):
                listener.enterArgumentList(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitArgumentList" ):
                listener.exitArgumentList(self)

        def accept(self, visitor:ParseTreeVisitor):
            if hasattr( visitor, "visitArgumentList" ):
                return visitor.visitArgumentList(self)
            else:
                return visitor.visitChildren(self)




    def argumentList(self):

        localctx = DAXParser.ArgumentListContext(self, self._ctx, self.state)
        self.enterRule(localctx, 30, self.RULE_argumentList)
        self._la = 0 # Token type
        try:
            self.enterOuterAlt(localctx, 1)
            self.state = 164
            self.expression()
            self.state = 169
            self._errHandler.sync(self)
            _la = self._input.LA(1)
            while _la==24:
                self.state = 165
                self.match(DAXParser.COMMA)
                self.state = 166
                self.expression()
                self.state = 171
                self._errHandler.sync(self)
                _la = self._input.LA(1)

        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx


    class FunctionNameContext(ParserRuleContext):
        __slots__ = 'parser'

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def identifierPart(self, i:int=None):
            if i is None:
                return self.getTypedRuleContexts(DAXParser.IdentifierPartContext)
            else:
                return self.getTypedRuleContext(DAXParser.IdentifierPartContext,i)


        def DOT(self, i:int=None):
            if i is None:
                return self.getTokens(DAXParser.DOT)
            else:
                return self.getToken(DAXParser.DOT, i)

        def COLON2(self, i:int=None):
            if i is None:
                return self.getTokens(DAXParser.COLON2)
            else:
                return self.getToken(DAXParser.COLON2, i)

        def getRuleIndex(self):
            return DAXParser.RULE_functionName

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterFunctionName" ):
                listener.enterFunctionName(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitFunctionName" ):
                listener.exitFunctionName(self)

        def accept(self, visitor:ParseTreeVisitor):
            if hasattr( visitor, "visitFunctionName" ):
                return visitor.visitFunctionName(self)
            else:
                return visitor.visitChildren(self)




    def functionName(self):

        localctx = DAXParser.FunctionNameContext(self, self._ctx, self.state)
        self.enterRule(localctx, 32, self.RULE_functionName)
        self._la = 0 # Token type
        try:
            self.enterOuterAlt(localctx, 1)
            self.state = 172
            self.identifierPart()
            self.state = 177
            self._errHandler.sync(self)
            _la = self._input.LA(1)
            while _la==25 or _la==26:
                self.state = 173
                _la = self._input.LA(1)
                if not(_la==25 or _la==26):
                    self._errHandler.recoverInline(self)
                else:
                    self._errHandler.reportMatch(self)
                    self.consume()
                self.state = 174
                self.identifierPart()
                self.state = 179
                self._errHandler.sync(self)
                _la = self._input.LA(1)

        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx


    class QualifiedReferenceContext(ParserRuleContext):
        __slots__ = 'parser'

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def tableQualifier(self):
            return self.getTypedRuleContext(DAXParser.TableQualifierContext,0)


        def BRACKET_IDENT(self):
            return self.getToken(DAXParser.BRACKET_IDENT, 0)

        def getRuleIndex(self):
            return DAXParser.RULE_qualifiedReference

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterQualifiedReference" ):
                listener.enterQualifiedReference(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitQualifiedReference" ):
                listener.exitQualifiedReference(self)

        def accept(self, visitor:ParseTreeVisitor):
            if hasattr( visitor, "visitQualifiedReference" ):
                return visitor.visitQualifiedReference(self)
            else:
                return visitor.visitChildren(self)




    def qualifiedReference(self):

        localctx = DAXParser.QualifiedReferenceContext(self, self._ctx, self.state)
        self.enterRule(localctx, 34, self.RULE_qualifiedReference)
        try:
            self.enterOuterAlt(localctx, 1)
            self.state = 180
            self.tableQualifier()
            self.state = 181
            self.match(DAXParser.BRACKET_IDENT)
        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx


    class TableQualifierContext(ParserRuleContext):
        __slots__ = 'parser'

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def TABLE_NAME(self):
            return self.getToken(DAXParser.TABLE_NAME, 0)

        def IDENTIFIER(self):
            return self.getToken(DAXParser.IDENTIFIER, 0)

        def getRuleIndex(self):
            return DAXParser.RULE_tableQualifier

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterTableQualifier" ):
                listener.enterTableQualifier(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitTableQualifier" ):
                listener.exitTableQualifier(self)

        def accept(self, visitor:ParseTreeVisitor):
            if hasattr( visitor, "visitTableQualifier" ):
                return visitor.visitTableQualifier(self)
            else:
                return visitor.visitChildren(self)




    def tableQualifier(self):

        localctx = DAXParser.TableQualifierContext(self, self._ctx, self.state)
        self.enterRule(localctx, 36, self.RULE_tableQualifier)
        self._la = 0 # Token type
        try:
            self.enterOuterAlt(localctx, 1)
            self.state = 183
            _la = self._input.LA(1)
            if not(_la==27 or _la==33):
                self._errHandler.recoverInline(self)
            else:
                self._errHandler.reportMatch(self)
                self.consume()
        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx


    class StandaloneReferenceContext(ParserRuleContext):
        __slots__ = 'parser'

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def BRACKET_IDENT(self):
            return self.getToken(DAXParser.BRACKET_IDENT, 0)

        def TABLE_NAME(self):
            return self.getToken(DAXParser.TABLE_NAME, 0)

        def getRuleIndex(self):
            return DAXParser.RULE_standaloneReference

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterStandaloneReference" ):
                listener.enterStandaloneReference(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitStandaloneReference" ):
                listener.exitStandaloneReference(self)

        def accept(self, visitor:ParseTreeVisitor):
            if hasattr( visitor, "visitStandaloneReference" ):
                return visitor.visitStandaloneReference(self)
            else:
                return visitor.visitChildren(self)




    def standaloneReference(self):

        localctx = DAXParser.StandaloneReferenceContext(self, self._ctx, self.state)
        self.enterRule(localctx, 38, self.RULE_standaloneReference)
        self._la = 0 # Token type
        try:
            self.enterOuterAlt(localctx, 1)
            self.state = 185
            _la = self._input.LA(1)
            if not(_la==27 or _la==28):
                self._errHandler.recoverInline(self)
            else:
                self._errHandler.reportMatch(self)
                self.consume()
        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx


    class BareTableReferenceContext(ParserRuleContext):
        __slots__ = 'parser'

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def IDENTIFIER(self):
            return self.getToken(DAXParser.IDENTIFIER, 0)

        def getRuleIndex(self):
            return DAXParser.RULE_bareTableReference

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterBareTableReference" ):
                listener.enterBareTableReference(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitBareTableReference" ):
                listener.exitBareTableReference(self)

        def accept(self, visitor:ParseTreeVisitor):
            if hasattr( visitor, "visitBareTableReference" ):
                return visitor.visitBareTableReference(self)
            else:
                return visitor.visitChildren(self)




    def bareTableReference(self):

        localctx = DAXParser.BareTableReferenceContext(self, self._ctx, self.state)
        self.enterRule(localctx, 40, self.RULE_bareTableReference)
        try:
            self.enterOuterAlt(localctx, 1)
            self.state = 187
            self.match(DAXParser.IDENTIFIER)
        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx


    class IdentifierContext(ParserRuleContext):
        __slots__ = 'parser'

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def IDENTIFIER(self):
            return self.getToken(DAXParser.IDENTIFIER, 0)

        def RETURN(self):
            return self.getToken(DAXParser.RETURN, 0)

        def IN(self):
            return self.getToken(DAXParser.IN, 0)

        def NOT(self):
            return self.getToken(DAXParser.NOT, 0)

        def BRACKET_IDENT(self):
            return self.getToken(DAXParser.BRACKET_IDENT, 0)

        def TABLE_NAME(self):
            return self.getToken(DAXParser.TABLE_NAME, 0)

        def getRuleIndex(self):
            return DAXParser.RULE_identifier

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterIdentifier" ):
                listener.enterIdentifier(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitIdentifier" ):
                listener.exitIdentifier(self)

        def accept(self, visitor:ParseTreeVisitor):
            if hasattr( visitor, "visitIdentifier" ):
                return visitor.visitIdentifier(self)
            else:
                return visitor.visitChildren(self)




    def identifier(self):

        localctx = DAXParser.IdentifierContext(self, self._ctx, self.state)
        self.enterRule(localctx, 42, self.RULE_identifier)
        self._la = 0 # Token type
        try:
            self.enterOuterAlt(localctx, 1)
            self.state = 189
            _la = self._input.LA(1)
            if not((((_la) & ~0x3f) == 0 and ((1 << _la) & 8992587804) != 0)):
                self._errHandler.recoverInline(self)
            else:
                self._errHandler.reportMatch(self)
                self.consume()
        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx


    class IdentifierPartContext(ParserRuleContext):
        __slots__ = 'parser'

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def IDENTIFIER(self):
            return self.getToken(DAXParser.IDENTIFIER, 0)

        def RETURN(self):
            return self.getToken(DAXParser.RETURN, 0)

        def IN(self):
            return self.getToken(DAXParser.IN, 0)

        def NOT(self):
            return self.getToken(DAXParser.NOT, 0)

        def TABLE_NAME(self):
            return self.getToken(DAXParser.TABLE_NAME, 0)

        def getRuleIndex(self):
            return DAXParser.RULE_identifierPart

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterIdentifierPart" ):
                listener.enterIdentifierPart(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitIdentifierPart" ):
                listener.exitIdentifierPart(self)

        def accept(self, visitor:ParseTreeVisitor):
            if hasattr( visitor, "visitIdentifierPart" ):
                return visitor.visitIdentifierPart(self)
            else:
                return visitor.visitChildren(self)




    def identifierPart(self):

        localctx = DAXParser.IdentifierPartContext(self, self._ctx, self.state)
        self.enterRule(localctx, 44, self.RULE_identifierPart)
        self._la = 0 # Token type
        try:
            self.enterOuterAlt(localctx, 1)
            self.state = 191
            _la = self._input.LA(1)
            if not((((_la) & ~0x3f) == 0 and ((1 << _la) & 8724152348) != 0)):
                self._errHandler.recoverInline(self)
            else:
                self._errHandler.reportMatch(self)
                self.consume()
        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx


    class TableConstructorContext(ParserRuleContext):
        __slots__ = 'parser'

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def LBRACE(self):
            return self.getToken(DAXParser.LBRACE, 0)

        def RBRACE(self):
            return self.getToken(DAXParser.RBRACE, 0)

        def expression(self, i:int=None):
            if i is None:
                return self.getTypedRuleContexts(DAXParser.ExpressionContext)
            else:
                return self.getTypedRuleContext(DAXParser.ExpressionContext,i)


        def COMMA(self, i:int=None):
            if i is None:
                return self.getTokens(DAXParser.COMMA)
            else:
                return self.getToken(DAXParser.COMMA, i)

        def getRuleIndex(self):
            return DAXParser.RULE_tableConstructor

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterTableConstructor" ):
                listener.enterTableConstructor(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitTableConstructor" ):
                listener.exitTableConstructor(self)

        def accept(self, visitor:ParseTreeVisitor):
            if hasattr( visitor, "visitTableConstructor" ):
                return visitor.visitTableConstructor(self)
            else:
                return visitor.visitChildren(self)




    def tableConstructor(self):

        localctx = DAXParser.TableConstructorContext(self, self._ctx, self.state)
        self.enterRule(localctx, 46, self.RULE_tableConstructor)
        self._la = 0 # Token type
        try:
            self.enterOuterAlt(localctx, 1)
            self.state = 193
            self.match(DAXParser.LBRACE)
            self.state = 202
            self._errHandler.sync(self)
            _la = self._input.LA(1)
            if (((_la) & ~0x3f) == 0 and ((1 << _la) & 17050918942) != 0):
                self.state = 194
                self.expression()
                self.state = 199
                self._errHandler.sync(self)
                _la = self._input.LA(1)
                while _la==24:
                    self.state = 195
                    self.match(DAXParser.COMMA)
                    self.state = 196
                    self.expression()
                    self.state = 201
                    self._errHandler.sync(self)
                    _la = self._input.LA(1)



            self.state = 204
            self.match(DAXParser.RBRACE)
        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx


    class TupleConstructorContext(ParserRuleContext):
        __slots__ = 'parser'

        def __init__(self, parser, parent:ParserRuleContext=None, invokingState:int=-1):
            super().__init__(parent, invokingState)
            self.parser = parser

        def LPAREN(self):
            return self.getToken(DAXParser.LPAREN, 0)

        def expression(self, i:int=None):
            if i is None:
                return self.getTypedRuleContexts(DAXParser.ExpressionContext)
            else:
                return self.getTypedRuleContext(DAXParser.ExpressionContext,i)


        def COMMA(self, i:int=None):
            if i is None:
                return self.getTokens(DAXParser.COMMA)
            else:
                return self.getToken(DAXParser.COMMA, i)

        def RPAREN(self):
            return self.getToken(DAXParser.RPAREN, 0)

        def getRuleIndex(self):
            return DAXParser.RULE_tupleConstructor

        def enterRule(self, listener:ParseTreeListener):
            if hasattr( listener, "enterTupleConstructor" ):
                listener.enterTupleConstructor(self)

        def exitRule(self, listener:ParseTreeListener):
            if hasattr( listener, "exitTupleConstructor" ):
                listener.exitTupleConstructor(self)

        def accept(self, visitor:ParseTreeVisitor):
            if hasattr( visitor, "visitTupleConstructor" ):
                return visitor.visitTupleConstructor(self)
            else:
                return visitor.visitChildren(self)




    def tupleConstructor(self):

        localctx = DAXParser.TupleConstructorContext(self, self._ctx, self.state)
        self.enterRule(localctx, 48, self.RULE_tupleConstructor)
        self._la = 0 # Token type
        try:
            self.enterOuterAlt(localctx, 1)
            self.state = 206
            self.match(DAXParser.LPAREN)
            self.state = 207
            self.expression()
            self.state = 208
            self.match(DAXParser.COMMA)
            self.state = 209
            self.expression()
            self.state = 214
            self._errHandler.sync(self)
            _la = self._input.LA(1)
            while _la==24:
                self.state = 210
                self.match(DAXParser.COMMA)
                self.state = 211
                self.expression()
                self.state = 216
                self._errHandler.sync(self)
                _la = self._input.LA(1)

            self.state = 217
            self.match(DAXParser.RPAREN)
        except RecognitionException as re:
            localctx.exception = re
            self._errHandler.reportError(self, re)
            self._errHandler.recover(self, re)
        finally:
            self.exitRule()
        return localctx





