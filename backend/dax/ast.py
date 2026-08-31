"""Canonical, source-located DAX AST nodes.

The parser owns syntax.  This module contains only source-preserving value
objects so later analyzers can inspect one deterministic tree.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator, Mapping


@dataclass(frozen=True, slots=True)
class SourceSpan:
    """A half-open source range with stable line/column coordinates."""

    start_offset: int
    end_offset: int
    start_line: int
    start_column: int
    end_line: int
    end_column: int

    @property
    def start(self) -> int:
        return self.start_offset

    @property
    def end(self) -> int:
        return self.end_offset

    @property
    def line(self) -> int:
        return self.start_line

    @property
    def column(self) -> int:
        return self.start_column

    @property
    def stop_offset(self) -> int:
        return max(self.start_offset, self.end_offset - 1)

    def to_dict(self) -> dict[str, int]:
        return {
            "start_offset": self.start_offset,
            "end_offset": self.end_offset,
            "start_line": self.start_line,
            "start_column": self.start_column,
            "end_line": self.end_line,
            "end_column": self.end_column,
        }


@dataclass(frozen=True, slots=True)
class AstNode:
    span: SourceSpan
    text: str = ""
    # Keep kind as a concrete field: ``dataclasses.asdict`` must preserve the
    # parser node type when analyzers cache the canonical AST.
    kind: str = "node"

    @property
    def location(self) -> SourceSpan:
        return self.span

    @property
    def ast_location(self) -> SourceSpan:
        return self.span

    @property
    def children(self) -> tuple[AstNode, ...]:
        return ()

    def walk(self) -> Iterator[AstNode]:
        yield self
        for child in self.children:
            yield from child.walk()

    def find(self, kind: str) -> list[AstNode]:
        wanted = str(kind).casefold()
        return [node for node in self.walk() if node.kind.casefold() == wanted]

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "kind": self.kind,
            "node_type": self.kind,
            "text": self.text,
            "location": self.span.to_dict(),
        }
        result["children"] = [child.to_dict() for child in self.children]
        return result

    as_dict = to_dict


@dataclass(frozen=True, slots=True)
class LiteralNode(AstNode):
    value: Any = None
    literal_type: str = "unknown"

    kind: str = "literal"

    def to_dict(self) -> dict[str, Any]:
        result = AstNode.to_dict(self)
        result.update({"value": self.value, "literal_type": self.literal_type})
        return result


@dataclass(frozen=True, slots=True)
class IdentifierNode(AstNode):
    name: str = ""

    kind: str = "identifier"

    def to_dict(self) -> dict[str, Any]:
        result = AstNode.to_dict(self)
        result["name"] = self.name
        return result


@dataclass(frozen=True, slots=True)
class ReferenceNode(AstNode):
    name: str = ""
    object_type: str = "UNKNOWN"
    table: str | None = None
    column: str | None = None
    qualification: str | None = None

    kind: str = "reference"

    @property
    def table_name(self) -> str | None:
        return self.table

    @property
    def column_name(self) -> str | None:
        return self.column

    @property
    def qualified_name(self) -> str:
        return self.qualification or self.name

    def to_dict(self) -> dict[str, Any]:
        result = AstNode.to_dict(self)
        result.update(
            {
                "name": self.name,
                "object_type": self.object_type,
                "table": self.table,
                "column": self.column,
                "qualification": self.qualification,
                "qualified_name": self.qualified_name,
            }
        )
        return result


@dataclass(frozen=True, slots=True)
class FunctionCallNode(AstNode):
    name: str = ""
    arguments: tuple[AstNode, ...] = ()

    kind: str = "function_call"

    @property
    def function_name(self) -> str:
        return self.name

    @property
    def children(self) -> tuple[AstNode, ...]:
        return self.arguments

    def to_dict(self) -> dict[str, Any]:
        result = AstNode.to_dict(self)
        result.update({"name": self.name, "arguments": [arg.to_dict() for arg in self.arguments]})
        return result


@dataclass(frozen=True, slots=True)
class BinaryOpNode(AstNode):
    operator: str = ""
    left: AstNode | None = None
    right: AstNode | None = None

    kind: str = "binary_operator"

    @property
    def children(self) -> tuple[AstNode, ...]:
        return tuple(child for child in (self.left, self.right) if child is not None)

    def to_dict(self) -> dict[str, Any]:
        result = AstNode.to_dict(self)
        result["operator"] = self.operator
        result["left"] = self.left.to_dict() if self.left else None
        result["right"] = self.right.to_dict() if self.right else None
        return result


@dataclass(frozen=True, slots=True)
class UnaryOpNode(AstNode):
    operator: str = ""
    operand: AstNode | None = None

    kind: str = "unary_operator"

    @property
    def children(self) -> tuple[AstNode, ...]:
        return (self.operand,) if self.operand is not None else ()

    def to_dict(self) -> dict[str, Any]:
        result = AstNode.to_dict(self)
        result.update({"operator": self.operator, "operand": self.operand.to_dict() if self.operand else None})
        return result


@dataclass(frozen=True, slots=True)
class ParenthesizedNode(AstNode):
    expression: AstNode | None = None

    kind: str = "parenthesized"

    @property
    def children(self) -> tuple[AstNode, ...]:
        return (self.expression,) if self.expression is not None else ()

    def to_dict(self) -> dict[str, Any]:
        result = AstNode.to_dict(self)
        result["expression"] = self.expression.to_dict() if self.expression else None
        return result


@dataclass(frozen=True, slots=True)
class VarDeclarationNode(AstNode):
    name: str = ""
    value: AstNode | None = None

    kind: str = "var_declaration"

    @property
    def children(self) -> tuple[AstNode, ...]:
        return (self.value,) if self.value is not None else ()

    def to_dict(self) -> dict[str, Any]:
        result = AstNode.to_dict(self)
        result.update({"name": self.name, "value": self.value.to_dict() if self.value else None})
        return result


@dataclass(frozen=True, slots=True)
class ReturnNode(AstNode):
    expression: AstNode | None = None

    kind: str = "return"

    @property
    def children(self) -> tuple[AstNode, ...]:
        return (self.expression,) if self.expression is not None else ()

    def to_dict(self) -> dict[str, Any]:
        result = AstNode.to_dict(self)
        result["expression"] = self.expression.to_dict() if self.expression else None
        return result


@dataclass(frozen=True, slots=True)
class VarBlockNode(AstNode):
    declarations: tuple[VarDeclarationNode, ...] = ()
    return_node: ReturnNode | None = None

    kind: str = "var_block"

    @property
    def children(self) -> tuple[AstNode, ...]:
        return (*self.declarations, *((self.return_node,) if self.return_node else ()))

    @property
    def return_expression(self) -> AstNode | None:
        return self.return_node.expression if self.return_node else None

    def to_dict(self) -> dict[str, Any]:
        result = AstNode.to_dict(self)
        result.update(
            {
                "declarations": [item.to_dict() for item in self.declarations],
                "return": self.return_node.to_dict() if self.return_node else None,
            }
        )
        return result


@dataclass(frozen=True, slots=True)
class TableConstructorNode(AstNode):
    values: tuple[AstNode, ...] = ()

    kind: str = "table_constructor"

    @property
    def children(self) -> tuple[AstNode, ...]:
        return self.values

    def to_dict(self) -> dict[str, Any]:
        result = AstNode.to_dict(self)
        result["values"] = [item.to_dict() for item in self.values]
        return result


@dataclass(frozen=True, slots=True)
class ErrorNode(AstNode):
    """Explicit placeholder returned only by non-raising recovery mode."""

    message: str = ""

    kind: str = "error"

    def to_dict(self) -> dict[str, Any]:
        result = AstNode.to_dict(self)
        result["message"] = self.message
        return result


# Short aliases make the AST pleasant to consume without hiding the canonical
# names used by the parser documentation.
DaxNode = AstNode
DaxExpression = AstNode
Literal = LiteralNode
Identifier = IdentifierNode
Reference = ReferenceNode
FunctionCall = FunctionCallNode
BinaryOperator = BinaryOpNode
UnaryOperator = UnaryOpNode
Parenthesized = ParenthesizedNode
VarDeclaration = VarDeclarationNode
Return = ReturnNode
VarBlock = VarBlockNode
TableConstructor = TableConstructorNode
Error = ErrorNode


def node_to_dict(node: AstNode | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(node, AstNode):
        return node.to_dict()
    return dict(node)
