"""Small, parser-agnostic visitors used by the DAX analyzer.

The parser owns AST shape.  These helpers intentionally use duck typing so a
future grammar revision can change node classes without changing graph logic.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
import re
from typing import Any, Iterable, Iterator, Mapping


_META_KEYS = {
    "location",
    "span",
    "source_span",
    "range",
    "line",
    "column",
    "start",
    "stop",
    "token",
    "tokens",
    "raw_source",
    "parent",
}


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).casefold()).strip("_")


def attr(value: Any, *names: str, default: Any = None) -> Any:
    """Read the first present mapping key or object attribute."""

    for name in names:
        if isinstance(value, Mapping):
            if name in value and value[name] is not None:
                return value[name]
            # JSON ASTs often use camelCase while Python ASTs use snake_case.
            folded = _norm(name)
            for key, candidate in value.items():
                if _norm(key) == folded and candidate is not None:
                    return candidate
        else:
            candidate = getattr(value, name, None)
            if candidate is not None:
                return candidate
    return default


def _scalar(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        nested = attr(value, "name", "value", "text", "identifier", "id")
        return _scalar(nested)
    nested = attr(value, "name", "value", "text", "identifier", "id")
    return _scalar(nested)


def node_kind(node: Any) -> str:
    """Return a stable uppercase-ish AST kind name."""

    explicit = attr(node, "kind", "node_type", "nodeType", "ast_type", "astType", "rule")
    if explicit is None:
        explicit = attr(node, "type")
    if explicit is None:
        explicit = type(node).__name__
    if not isinstance(explicit, str):
        explicit = getattr(explicit, "name", None) or str(explicit)
    return _norm(explicit).upper()


def node_text(node: Any) -> str | None:
    value = attr(node, "text", "raw_text", "raw", "source_text", "lexeme")
    if value is None:
        get_text = getattr(node, "getText", None)
        if callable(get_text):
            try:
                value = get_text()
            except Exception:  # pragma: no cover - defensive for parser contexts
                value = None
    if value is None:
        value = attr(node, "value")
    if value is None:
        return None
    return str(value)


def _is_ast_candidate(value: Any) -> bool:
    if isinstance(value, Mapping):
        return bool(
            any(key in value for key in ("kind", "node_type", "nodeType", "ast_type", "children", "arguments"))
            or any(isinstance(item, (Mapping, list, tuple)) for item in value.values())
        )
    if isinstance(value, (list, tuple)):
        return True
    if value is None or isinstance(value, (str, int, float, bool, bytes)):
        return False
    return is_dataclass(value) or bool(vars(value)) if hasattr(value, "__dict__") else True


def iter_children(node: Any) -> Iterator[Any]:
    """Yield child AST values in source/container order."""

    if node is None or isinstance(node, (str, bytes, int, float, bool)):
        return
    if isinstance(node, Mapping):
        items = node.items()
    elif isinstance(node, (list, tuple, set, frozenset)):
        for child in node:
            if _is_ast_candidate(child):
                yield child
        return
    elif is_dataclass(node):
        items = ((field.name, getattr(node, field.name)) for field in fields(node))
    else:
        try:
            items = vars(node).items()
        except TypeError:
            items = ()
    for key, child in items:
        if _norm(key) in {_norm(item) for item in _META_KEYS}:
            continue
        if isinstance(child, (list, tuple, set, frozenset)):
            for item in child:
                if _is_ast_candidate(item):
                    yield item
            continue
        if _is_ast_candidate(child):
            yield child


@dataclass(frozen=True, slots=True)
class AstVisit:
    node: Any
    kind: str
    path: tuple[int, ...]
    depth: int


def walk_ast(root: Any) -> Iterator[AstVisit]:
    """Depth-first walk with cycle protection and deterministic order."""

    seen: set[int] = set()

    def visit(value: Any, path: tuple[int, ...], depth: int) -> Iterator[AstVisit]:
        if value is None or isinstance(value, (str, bytes, int, float, bool)):
            return
        marker = id(value)
        if marker in seen:
            return
        seen.add(marker)
        yield AstVisit(value, node_kind(value), path, depth)
        for index, child in enumerate(iter_children(value)):
            yield from visit(child, path + (index,), depth + 1)

    yield from visit(root, (), 0)


def descendants(root: Any) -> Iterator[AstVisit]:
    first = True
    for item in walk_ast(root):
        if first:
            first = False
            continue
        yield item


def _unquote(value: Any) -> str | None:
    value = _scalar(value)
    if value is None:
        return None
    text = str(value).strip()
    if len(text) >= 2 and text[0] == text[-1] == "'":
        text = text[1:-1].replace("''", "'")
    elif len(text) >= 2 and text[0] == text[-1] == '"':
        text = text[1:-1].replace('""', '"')
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1]
    return text or None


@dataclass(frozen=True, slots=True)
class ReferenceInfo:
    kind: str
    name: str
    table: str | None
    node: Any
    extractor: str
    text: str | None = None


def _reference_kind(kind: str, node: Any) -> str | None:
    value = attr(node, "reference_type", "referenceType", "object_type", "objectType")
    text = _norm(value or kind)
    if any(token in text for token in ("measure_reference", "measure_ref", "measure_name")):
        return "MEASURE"
    if any(token in text for token in ("column_reference", "column_ref", "column_name")):
        return "COLUMN"
    if any(token in text for token in ("table_reference", "table_ref", "table_name")):
        return "TABLE"
    if attr(node, "is_measure", "isMeasure", default=False):
        return "MEASURE"
    if attr(node, "is_column", "isColumn", default=False):
        return "COLUMN"
    if attr(node, "is_table", "isTable", default=False):
        return "TABLE"
    return None


_COLUMN_TEXT = re.compile(r"^\s*'?((?:[^']|'')+?)'?\s*\[([^\]]+)\]\s*$")
_MEASURE_TEXT = re.compile(r"^\s*\[([^\]]+)\]\s*$")


def reference_info(node: Any) -> ReferenceInfo | None:
    """Extract an explicitly typed object reference from one AST node."""

    kind_name = node_kind(node)
    kind = _reference_kind(kind_name, node)
    nested = attr(node, "reference", "ref", "qualified_name", "qualifiedName")
    if kind is None and nested is not None and nested is not node:
        nested_info = reference_info(nested)
        if nested_info:
            return ReferenceInfo(
                nested_info.kind,
                nested_info.name,
                nested_info.table,
                node,
                "nested_reference",
                node_text(node) or nested_info.text,
            )

    table_value = attr(node, "table", "table_name", "tableName", "entity", "qualifier", "namespace")
    column_value = attr(node, "column", "column_name", "columnName", "field")
    measure_value = attr(node, "measure", "measure_name", "measureName")
    name_value = attr(node, "name", "identifier", "property", "value", "text")
    text = node_text(node)
    if kind is None:
        if measure_value is not None:
            kind = "MEASURE"
        elif column_value is not None:
            kind = "COLUMN"
        elif table_value is not None and attr(node, "column", "measure") is None:
            kind = "TABLE"
    if kind == "COLUMN":
        column = _unquote(column_value if column_value is not None else name_value)
        table = _unquote(table_value)
        if column:
            return ReferenceInfo("COLUMN", column, table, node, "column_reference", text)
    if kind == "MEASURE":
        name = _unquote(measure_value if measure_value is not None else name_value)
        if name:
            return ReferenceInfo("MEASURE", name, _unquote(table_value), node, "measure_reference", text)
    if kind == "TABLE":
        name = _unquote(table_value if table_value is not None else name_value)
        if name:
            return ReferenceInfo("TABLE", name, None, node, "table_reference", text)

    # Some lightweight ASTs retain a complete DAX reference in text only.
    if text:
        match = _COLUMN_TEXT.match(text)
        if match and ("REFERENCE" in kind_name or "QUALIFIED" in kind_name):
            return ReferenceInfo("COLUMN", _unquote(match.group(2)) or match.group(2), _unquote(match.group(1)), node, "column_reference", text)
        match = _MEASURE_TEXT.match(text)
        if match and ("REFERENCE" in kind_name or "QUALIFIED" in kind_name):
            return ReferenceInfo("MEASURE", _unquote(match.group(1)) or match.group(1), None, node, "measure_reference", text)
    return None


def iter_references(root: Any) -> Iterator[tuple[AstVisit, ReferenceInfo]]:
    for visit in walk_ast(root):
        info = reference_info(visit.node)
        if info:
            yield visit, info


def function_name(node: Any) -> str | None:
    kind = node_kind(node)
    value = attr(node, "function", "function_name", "functionName", "name", "identifier", "callee")
    if isinstance(value, Mapping):
        value = attr(value, "name", "text", "value", "identifier")
    if value is not None and ("FUNCTION" in kind or "CALL" in kind or attr(node, "arguments", "args") is not None):
        text = _unquote(value)
        if text:
            return text
    if "FUNCTION" in kind or "CALL" in kind:
        text = node_text(node)
        if text:
            match = re.match(r"\s*([A-Za-z_][A-Za-z0-9_.]*)\s*\(", text)
            if match:
                return match.group(1)
    return None


def iter_functions(root: Any) -> Iterator[tuple[AstVisit, str]]:
    for visit in walk_ast(root):
        name = function_name(visit.node)
        if name:
            yield visit, name


def variable_name(node: Any) -> str | None:
    kind = node_kind(node)
    if not any(token in kind for token in ("VARIABLE", "VAR_BINDING", "VAR_DECLARATION")):
        return None
    value = attr(node, "name", "identifier", "variable", "variable_name", "variableName")
    if isinstance(value, Mapping):
        value = attr(value, "name", "text", "value")
    return _unquote(value)


def iter_variables(root: Any) -> Iterator[tuple[AstVisit, str]]:
    for visit in walk_ast(root):
        name = variable_name(visit.node)
        if name:
            yield visit, name


__all__ = [
    "AstVisit",
    "ReferenceInfo",
    "attr",
    "descendants",
    "function_name",
    "iter_children",
    "iter_functions",
    "iter_references",
    "iter_variables",
    "node_kind",
    "node_text",
    "reference_info",
    "walk_ast",
]
