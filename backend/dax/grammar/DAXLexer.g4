lexer grammar DAXLexer;

// DAX keywords are case-insensitive.  Keep only grammar-significant words as
// tokens; function names stay identifiers so new DAX functions need no lexer
// change.
VAR: V A R;
RETURN: R E T U R N;
IN: I N;
NOT: N O T;

OR_OP: '||';
AND_OP: '&&';
EQ: '==' | '=';
NEQ: '<>' | '!=';
LTE: '<=';
GTE: '>=';
LT: '<';
GT: '>';
PLUS: '+';
MINUS: '-';
STAR: '*';
SLASH: '/';
PERCENT: '%';
AMP: '&';
POW: '^';
LPAREN: '(';
RPAREN: ')';
LBRACE: '{';
RBRACE: '}';
COMMA: ',';
DOT: '.';
COLON2: '::';

// A quoted table name and a bracketed measure/column name are separate from
// string literals in DAX, which use double quotes.
TABLE_NAME: '\'' ('\'\'' | ~['\r\n])* '\'';
BRACKET_IDENT: '[' ~[\]\r\n]+ ']';
STRING: '"' ('""' | '\\' . | ~["\r\n])* '"';
DATE_LITERAL: '#' ~[#\r\n]* '#';
DATETIME_LITERAL: D T '"' ('""' | '\\' . | ~["\r\n])* '"';
NUMBER: DIGIT+ ('.' DIGIT+)? ([eE] [+-]? DIGIT+)?;
IDENTIFIER: [a-zA-Z_\u0080-\uFFFF] [a-zA-Z0-9_\u0080-\uFFFF]*;

LINE_COMMENT: '//' ~[\r\n]* -> channel(HIDDEN);
BLOCK_COMMENT: '/*' .*? '*/' -> channel(HIDDEN);
WS: [ \t\r\n]+ -> channel(HIDDEN);

fragment DIGIT: [0-9];
fragment D: [dD];
fragment A: [aA];
fragment E: [eE];
fragment I: [iI];
fragment N: [nN];
fragment O: [oO];
fragment R: [rR];
fragment T: [tT];
fragment U: [uU];
fragment V: [vV];
