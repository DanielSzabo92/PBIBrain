"""ANTLR-backed DAX parser and AST builder.

The generated lexer/parser are intentionally kept in ``generated``.  This
module is the stable facade used by analyzers and callers; no semantic
interpretation happens here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from antlr4 import CommonTokenStream, InputStream
from antlr4.error.ErrorListener import ErrorListener
from antlr4.tree.Tree import TerminalNode

from .ast import (
    AstNode,
    BinaryOpNode,
    ErrorNode,
    FunctionCallNode,
    IdentifierNode,
    LiteralNode,
    ParenthesizedNode,
    ReferenceNode,
    ReturnNode,
    SourceSpan,
    TableConstructorNode,
    UnaryOpNode,
    VarBlockNode,
    VarDeclarationNode,
)
from .generated.DAXLexer import DAXLexer as _AntlrLexer
from .generated.DAXParser import DAXParser as _AntlrParser
from .generated.DAXParserVisitor import DAXParserVisitor


ANTLR_RUNTIME_VERSION = "4.13.2"


@dataclass(frozen=True, slots=True)
class DaxSyntaxIssue:
    line: int
    column: int
    message: str
    offending_text: str | None = None
    offset: int | None = None

    @property
    def text(self) -> str | None:
        return self.offending_text

    def to_dict(self) -> dict[str, Any]:
        return {
            "line": self.line,
            "column": self.column,
            "message": self.message,
            "offending_text": self.offending_text,
            "offset": self.offset,
        }


class _IssueListener(ErrorListener):
    def __init__(self, issues: list[DaxSyntaxIssue]) -> None:
        super().__init__()
        self.issues = issues

    def syntaxError(self, recognizer, offendingSymbol, line, column, msg, e):  # noqa: N802
        text = getattr(offendingSymbol, "text", None)
        offset = getattr(offendingSymbol, "start", None)
        self.issues.append(
            DaxSyntaxIssue(
                line=int(line),
                # ANTLR columns are zero-based; public diagnostics are
                # one-based so they match editor/user locations.
                column=int(column) + 1,
                message=str(msg),
                offending_text=None if text is None else str(text),
                offset=None if offset is None or offset < 0 else int(offset),
            )
        )


class DaxSyntaxError(ValueError):
    """Raised when DAX cannot be parsed into a complete expression."""

    def __init__(self, issues: Iterable[DaxSyntaxIssue]) -> None:
        self.issues = tuple(issues)
        self.errors = self.issues
        if self.issues:
            first = self.issues[0]
            message = f"DAX syntax error at {first.line}:{first.column}: {first.message}"
        else:
            message = "DAX syntax error"
        super().__init__(message)

    @property
    def line(self) -> int | None:
        return self.issues[0].line if self.issues else None

    @property
    def column(self) -> int | None:
        return self.issues[0].column if self.issues else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "message": str(self),
            "line": self.line,
            "column": self.column,
            "errors": [issue.to_dict() for issue in self.issues],
        }


@dataclass(frozen=True, slots=True)
class DaxParseResult:
    """The parsed AST plus diagnostics and the original ANTLR parse tree."""

    root: AstNode
    source: str
    errors: tuple[DaxSyntaxIssue, ...] = ()
    tree: Any = None

    @property
    def ast(self) -> AstNode:
        return self.root

    @property
    def expression(self) -> AstNode:
        return self.root

    @property
    def diagnostics(self) -> tuple[DaxSyntaxIssue, ...]:
        return self.errors

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "ast": self.root.to_dict(),
            "root": self.root.to_dict(),
            "source": self.source,
            "errors": [item.to_dict() for item in self.errors],
        }

    as_dict = to_dict

    def __getattr__(self, name: str) -> Any:
        # Small compatibility convenience: callers that only need the AST can
        # use parse_dax(...).kind or .walk() without unwrapping the result.
        return getattr(self.root, name)


def _span(ctx: Any, source: str) -> tuple[SourceSpan, str]:
    start_token = getattr(ctx, "start", None)
    stop_token = getattr(ctx, "stop", None) or start_token
    start = getattr(start_token, "start", -1)
    stop = getattr(stop_token, "stop", -1)
    if start is None or start < 0:
        start = 0
    if stop is None or stop < start:
        stop = start - 1
    end = min(len(source), stop + 1)
    start_line = int(getattr(start_token, "line", 1) or 1)
    start_column = int(getattr(start_token, "column", 0) or 0)
    text = source[start:end]
    if "\n" in text:
        lines = text.splitlines(keepends=True)
        end_line = start_line + len(lines) - 1
        end_column = len(lines[-1].rstrip("\r\n"))
    else:
        end_line = start_line
        end_column = start_column + len(text)
    return (
        SourceSpan(
            start_offset=int(start),
            end_offset=int(end),
            start_line=start_line,
            start_column=start_column,
            end_line=end_line,
            end_column=end_column,
        ),
        text,
    )


def _unquote(text: str, quote: str) -> str:
    if len(text) >= 2 and text[0] == quote and text[-1] == quote:
        return text[1:-1].replace(quote + quote, quote)
    return text


def _identifier_text(text: str) -> str:
    if text.startswith("[") and text.endswith("]"):
        return text[1:-1]
    if text.startswith("'") and text.endswith("'"):
        return _unquote(text, "'")
    return text


_BARE_TABLE_FUNCTIONS = {
    "ALL",
    "ALLEXCEPT",
    "ALLSELECTED",
    "FILTER",
    "REMOVEFILTERS",
}


def _is_bare_table_argument(ctx: Any) -> bool:
    current = ctx
    while current is not None:
        parent = getattr(current, "parentCtx", None)
        if isinstance(parent, _AntlrParser.ArgumentListContext):
            call = getattr(parent, "parentCtx", None)
            if not isinstance(call, _AntlrParser.FunctionCallContext):
                return False
            name = _identifier_text(call.functionName().getText()).upper()
            if name not in _BARE_TABLE_FUNCTIONS:
                return False
            expressions = list(parent.expression())
            try:
                index = next(index for index, expression in enumerate(expressions) if _contains_context(expression, ctx))
            except StopIteration:
                return False
            return name != "FILTER" or index == 0
        current = parent
    return False


def _contains_context(root: Any, target: Any) -> bool:
    if root is target:
        return True
    for child in root.getChildren():
        if _contains_context(child, target):
            return True
    return False


def _literal_from_token(ctx: Any, source: str, literal_type: str) -> LiteralNode:
    span, text = _span(ctx, source)
    raw = text
    if literal_type == "STRING":
        value: Any = _unquote(raw, '"').replace('\\"', '"').replace('\\\\', '\\')
    elif literal_type == "DATETIME":
        value = _unquote(raw[2:] if raw[:2].casefold() == "dt" else raw, '"')
    elif literal_type == "DATE":
        value = _unquote(raw, "#")
    else:
        try:
            value = int(raw, 10) if all(char not in raw.casefold() for char in (".", "e")) else float(raw)
        except ValueError:
            value = raw
    return LiteralNode(span=span, text=text, value=value, literal_type=literal_type)


class _AstBuilder(DAXParserVisitor):
    def __init__(self, source: str) -> None:
        super().__init__()
        self.source = source

    def _node_span(self, ctx: Any) -> tuple[SourceSpan, str]:
        return _span(ctx, self.source)

    def _visit(self, ctx: Any) -> AstNode:
        value = self.visit(ctx)
        if not isinstance(value, AstNode):
            raise ValueError(f"ANTLR AST builder produced no node for {type(ctx).__name__}")
        return value

    def visitVarExpression(self, ctx):  # noqa: N802
        return self._visit(ctx.varBlock())

    def visitLogicalExpression(self, ctx):  # noqa: N802
        return self._visit(ctx.logicalOr())

    def visitVarBlock(self, ctx):  # noqa: N802
        span, text = self._node_span(ctx)
        declarations = tuple(self._visit(item) for item in ctx.varBinding())
        expression = self._visit(ctx.expression())
        return_token = ctx.RETURN().getSymbol()
        return_start = int(getattr(return_token, "start", span.start_offset) or span.start_offset)
        return_span = SourceSpan(
            start_offset=return_start,
            end_offset=expression.span.end_offset,
            start_line=int(getattr(return_token, "line", span.start_line) or span.start_line),
            start_column=int(getattr(return_token, "column", span.start_column) or span.start_column),
            end_line=expression.span.end_line,
            end_column=expression.span.end_column,
        )
        return_node = ReturnNode(
            span=return_span,
            text=self.source[return_span.start_offset : return_span.end_offset],
            expression=expression,
        )
        return VarBlockNode(span=span, text=text, declarations=declarations, return_node=return_node)

    def visitVarBinding(self, ctx):  # noqa: N802
        span, text = self._node_span(ctx)
        name = _identifier_text(ctx.identifier().getText())
        return VarDeclarationNode(span=span, text=text, name=name, value=self._visit(ctx.expression()))

    def _fold_binary(self, ctx: Any, operands: list[Any]) -> AstNode:
        nodes = [self._visit(item) for item in operands]
        operators = [str(child.getText()) for child in ctx.getChildren() if isinstance(child, TerminalNode)]
        result = nodes[0]
        for operator, right in zip(operators, nodes[1:]):
            span = SourceSpan(
                result.span.start_offset,
                right.span.end_offset,
                result.span.start_line,
                result.span.start_column,
                right.span.end_line,
                right.span.end_column,
            )
            result = BinaryOpNode(span=span, text=self.source[span.start_offset : span.end_offset], operator=operator, left=result, right=right)
        return result

    def visitLogicalOr(self, ctx):  # noqa: N802
        return self._fold_binary(ctx, list(ctx.logicalAnd()))

    def visitLogicalAnd(self, ctx):  # noqa: N802
        return self._fold_binary(ctx, list(ctx.comparison()))

    def visitComparison(self, ctx):  # noqa: N802
        return self._fold_binary(ctx, list(ctx.concatenation()))

    def visitAdditive(self, ctx):  # noqa: N802
        return self._fold_binary(ctx, list(ctx.multiplicative()))

    def visitConcatenation(self, ctx):  # noqa: N802
        return self._fold_binary(ctx, list(ctx.additive()))

    def visitMultiplicative(self, ctx):  # noqa: N802
        return self._fold_binary(ctx, list(ctx.unary()))

    def visitPower(self, ctx):  # noqa: N802
        primaries = [self._visit(item) for item in ctx.primary()]
        if len(primaries) == 1:
            return primaries[0]
        signs: list[Any | None] = []
        after_power = False
        for child in ctx.getChildren():
            if isinstance(child, TerminalNode):
                token = child.getText()
                if token == "^":
                    after_power = True
                    signs.append(None)
                elif after_power and token in {"+", "-"} and signs:
                    signs[-1] = child
        result = primaries[0]
        for index, right in enumerate(primaries[1:]):
            sign = signs[index] if index < len(signs) else None
            if sign is not None:
                token = sign.getSymbol()
                start = int(getattr(token, "start", right.span.start_offset) or right.span.start_offset)
                line = int(getattr(token, "line", right.span.start_line) or right.span.start_line)
                column = int(getattr(token, "column", right.span.start_column) or right.span.start_column)
                span = SourceSpan(start, right.span.end_offset, line, column, right.span.end_line, right.span.end_column)
                right = UnaryOpNode(span=span, text=self.source[start : right.span.end_offset], operator=sign.getText(), operand=right)
            span = SourceSpan(
                result.span.start_offset,
                right.span.end_offset,
                result.span.start_line,
                result.span.start_column,
                right.span.end_line,
                right.span.end_column,
            )
            result = BinaryOpNode(
                span=span,
                text=self.source[span.start_offset : span.end_offset],
                operator="^",
                left=result,
                right=right,
            )
        return result

    def visitUnary(self, ctx):  # noqa: N802
        span, text = self._node_span(ctx)
        children = list(ctx.getChildren())
        if len(children) == 1:
            return self._visit(children[0])
        operator = str(children[0].getText())
        operand = self._visit(children[1])
        return UnaryOpNode(span=span, text=text, operator=operator, operand=operand)

    def visitLiteralPrimary(self, ctx):  # noqa: N802
        return self._visit(ctx.literal())

    def visitFunctionPrimary(self, ctx):  # noqa: N802
        return self._visit(ctx.functionCall())

    def visitQualifiedReferencePrimary(self, ctx):  # noqa: N802
        return self._visit(ctx.qualifiedReference())

    def visitStandaloneReferencePrimary(self, ctx):  # noqa: N802
        return self._visit(ctx.standaloneReference())

    def visitBareTableReferencePrimary(self, ctx):  # noqa: N802
        return self._visit(ctx.bareTableReference())

    def visitIdentifierPrimary(self, ctx):  # noqa: N802
        return self._visit(ctx.identifier())

    def visitTableConstructorPrimary(self, ctx):  # noqa: N802
        return self._visit(ctx.tableConstructor())

    def visitTupleConstructorPrimary(self, ctx):  # noqa: N802
        return self._visit(ctx.tupleConstructor())

    def visitParenthesizedPrimary(self, ctx):  # noqa: N802
        span, text = self._node_span(ctx)
        return ParenthesizedNode(span=span, text=text, expression=self._visit(ctx.expression()))

    def visitStringLiteral(self, ctx):  # noqa: N802
        return _literal_from_token(ctx, self.source, "STRING")

    def visitNumberLiteral(self, ctx):  # noqa: N802
        return _literal_from_token(ctx, self.source, "NUMBER")

    def visitDateLiteral(self, ctx):  # noqa: N802
        return _literal_from_token(ctx, self.source, "DATE")

    def visitDatetimeLiteral(self, ctx):  # noqa: N802
        return _literal_from_token(ctx, self.source, "DATETIME")

    def visitFunctionCall(self, ctx):  # noqa: N802
        span, text = self._node_span(ctx)
        arguments = tuple(self._visit(item) for item in (ctx.argumentList().expression() if ctx.argumentList() else ()))
        name = _identifier_text(ctx.functionName().getText())
        return FunctionCallNode(span=span, text=text, name=name, arguments=arguments)

    def visitArgumentList(self, ctx):  # noqa: N802
        # FunctionCall consumes this rule directly; this keeps direct visitor
        # use useful without creating a non-contract wrapper node.
        return tuple(self._visit(item) for item in ctx.expression())

    def visitFunctionName(self, ctx):  # noqa: N802
        return _identifier_text(ctx.getText())

    def visitQualifiedReference(self, ctx):  # noqa: N802
        span, text = self._node_span(ctx)
        table_raw = ctx.tableQualifier().getText()
        column_raw = ctx.BRACKET_IDENT().getText()
        table = _identifier_text(table_raw)
        column = _identifier_text(column_raw)
        return ReferenceNode(
            span=span,
            text=text,
            name=column,
            object_type="COLUMN",
            table=table,
            column=column,
            qualification=f"{table_raw}{column_raw}",
        )

    def visitTableQualifier(self, ctx):  # noqa: N802
        return _identifier_text(ctx.getText())

    def visitStandaloneReference(self, ctx):  # noqa: N802
        span, text = self._node_span(ctx)
        if text.startswith("["):
            name = _identifier_text(text)
            return ReferenceNode(span=span, text=text, name=name, object_type="MEASURE", qualification=text)
        name = _identifier_text(text)
        return ReferenceNode(span=span, text=text, name=name, object_type="TABLE", table=name, qualification=text)

    def visitBareTableReference(self, ctx):  # noqa: N802
        span, text = self._node_span(ctx)
        if _is_bare_table_argument(ctx):
            name = _identifier_text(text)
            return ReferenceNode(span=span, text=text, name=name, object_type="TABLE", table=name, qualification=text)
        return IdentifierNode(span=span, text=text, name=_identifier_text(text))

    def visitIdentifier(self, ctx):  # noqa: N802
        span, text = self._node_span(ctx)
        normalized = text.casefold()
        if normalized in {"true", "false"}:
            return LiteralNode(span=span, text=text, value=normalized == "true", literal_type="BOOLEAN")
        if normalized == "blank":
            return LiteralNode(span=span, text=text, value=None, literal_type="BLANK")
        return IdentifierNode(span=span, text=text, name=_identifier_text(text))

    def visitIdentifierPart(self, ctx):  # noqa: N802
        return _identifier_text(ctx.getText())

    def visitTableConstructor(self, ctx):  # noqa: N802
        span, text = self._node_span(ctx)
        return TableConstructorNode(span=span, text=text, values=tuple(self._visit(item) for item in ctx.expression()))

    def visitTupleConstructor(self, ctx):  # noqa: N802
        span, text = self._node_span(ctx)
        return TableConstructorNode(span=span, text=text, values=tuple(self._visit(item) for item in ctx.expression()), kind="tuple")


def parse_dax(
    source: str,
    *,
    raise_on_error: bool = True,
    strict: bool | None = None,
) -> DaxParseResult:
    """Parse one DAX expression into a deterministic source-located AST."""

    if isinstance(source, bytes):
        source = source.decode("utf-8")
    if not isinstance(source, str):
        raise TypeError("DAX source must be text")
    if strict is not None:
        raise_on_error = bool(strict)

    issues: list[DaxSyntaxIssue] = []
    lexer = _AntlrLexer(InputStream(source))
    lexer.removeErrorListeners()
    lexer.addErrorListener(_IssueListener(issues))
    tokens = CommonTokenStream(lexer)
    antlr_parser = _AntlrParser(tokens)
    antlr_parser.removeErrorListeners()
    antlr_parser.addErrorListener(_IssueListener(issues))
    tree = antlr_parser.parse()
    expression_ctx = tree.expression()
    if issues:
        if raise_on_error:
            raise DaxSyntaxError(issues)
        # Keep malformed syntax explicit.  A partial tree is not a canonical
        # AST and must never be mistaken for a successful parse.
        if source.count("\n"):
            lines = source.splitlines()
            end_line = len(lines)
            end_column = len(lines[-1]) if lines else 0
        else:
            end_line = 1
            end_column = len(source)
        root = ErrorNode(
            span=SourceSpan(0, len(source), 1, 0, end_line, end_column),
            text=source,
            message=issues[0].message,
        )
        return DaxParseResult(root=root, source=source, errors=tuple(issues), tree=tree)
    if expression_ctx is None:
        raise DaxSyntaxError(issues or [DaxSyntaxIssue(1, 0, "expected expression")])
    root = _AstBuilder(source).visit(expression_ctx)
    result = DaxParseResult(root=root, source=source, errors=tuple(issues), tree=tree)
    return result


parse = parse_dax


class DaxParser:
    """Reusable facade for callers that prefer an object parser."""

    def __init__(self, source: str | None = None, *, raise_on_error: bool = True, strict: bool | None = None) -> None:
        self.source = source
        self.raise_on_error = bool(raise_on_error if strict is None else strict)

    def parse(self, source: str | None = None) -> DaxParseResult:
        value = self.source if source is None else source
        if value is None:
            raise TypeError("DAX source is required")
        return parse_dax(value, raise_on_error=self.raise_on_error)

    parse_expression = parse


# Naming aliases used by integrations that use the acronym in class names.
DAXParserFacade = DaxParser
DAXParser = DaxParser
Parser = DaxParser
DAXSyntaxError = DaxSyntaxError
