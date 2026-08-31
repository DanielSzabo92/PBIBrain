parser grammar DAXParser;

options { tokenVocab=DAXLexer; }

// The generic function-call rule deliberately covers IF, SWITCH, SELECTEDVALUE,
// VALUES, HASONEVALUE, ISFILTERED, CALCULATE, FILTER, TREATAS, REMOVEFILTERS,
// ALL, ALLSELECTED, KEEPFILTERS, USERELATIONSHIP, CROSSFILTER, dynamic format
// functions, and user-defined functions without hardcoding a finite function
// catalogue.

parse
    : expression EOF
    ;

expression
    : varBlock                         # varExpression
    | logicalOr                        # logicalExpression
    ;

varBlock
    : VAR varBinding (VAR varBinding)* RETURN expression
    ;

varBinding
    : identifier EQ expression
    ;

logicalOr
    : logicalAnd (OR_OP logicalAnd)*
    ;

logicalAnd
    : comparison (AND_OP comparison)*
    ;

comparison
    : concatenation ((EQ | NEQ | LTE | LT | GTE | GT | IN) concatenation)*
    ;

additive
    : multiplicative ((PLUS | MINUS) multiplicative)*
    ;

multiplicative
    : unary ((STAR | SLASH | PERCENT) unary)*
    ;

concatenation
    : additive (AMP additive)*
    ;

unary
    : (NOT | PLUS | MINUS) unary
    | power
    ;

power
    : primary (POW (PLUS | MINUS)? primary)*
    ;

primary
    : literal                           # literalPrimary
    | functionCall                      # functionPrimary
    | qualifiedReference                # qualifiedReferencePrimary
    | standaloneReference               # standaloneReferencePrimary
    | bareTableReference                # bareTableReferencePrimary
    | identifier                         # identifierPrimary
    | tupleConstructor                   # tupleConstructorPrimary
    | tableConstructor                   # tableConstructorPrimary
    | LPAREN expression RPAREN          # parenthesizedPrimary
    ;

literal
    : STRING                            # stringLiteral
    | NUMBER                            # numberLiteral
    | DATE_LITERAL                      # dateLiteral
    | DATETIME_LITERAL                  # datetimeLiteral
    ;

functionCall
    : functionName LPAREN argumentList? RPAREN
    ;

argumentList
    : expression (COMMA expression)*
    ;

functionName
    : identifierPart ((DOT | COLON2) identifierPart)*
    ;

qualifiedReference
    : tableQualifier BRACKET_IDENT
    ;

tableQualifier
    : TABLE_NAME
    | IDENTIFIER
    ;

standaloneReference
    : BRACKET_IDENT                      // measure reference, normally [Name]
    | TABLE_NAME                         // table reference, normally 'Table'
    ;

bareTableReference
    : IDENTIFIER                         // table argument such as FILTER(Sales, ...)
    ;

identifier
    : IDENTIFIER
    | RETURN
    | IN
    | NOT
    | BRACKET_IDENT
    | TABLE_NAME
    ;

identifierPart
    : IDENTIFIER
    | RETURN
    | IN
    | NOT
    | TABLE_NAME
    ;

tableConstructor
    : LBRACE (expression (COMMA expression)*)? RBRACE
    ;

tupleConstructor
    : LPAREN expression COMMA expression (COMMA expression)* RPAREN
    ;
