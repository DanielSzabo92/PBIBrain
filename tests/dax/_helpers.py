"""Small adapters used by DAX contract tests.

The assertions operate on the public AST/evidence shape, not on generated
ANTLR classes.  This keeps the golden corpus useful if the grammar is
regenerated.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from collections.abc import Mapping
from typing import Any


def mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    for method_name in ("to_dict", "as_dict", "model_dump", "dict"):
        method = getattr(value, method_name, None)
        if callable(method):
            result = method()
            if isinstance(result, Mapping):
                return dict(result)
    if is_dataclass(value):
        return asdict(value)
    try:
        return dict(vars(value))
    except TypeError:
        return {}


def parse_ast(expression: str) -> Any:
    from backend.dax.parser import parse_dax

    result = parse_dax(expression)
    for key in ("ast", "root", "tree"):
        candidate = result.get(key) if isinstance(result, Mapping) else getattr(result, key, None)
        if candidate is not None:
            return candidate
    return result


def walk(value: Any):
    """Yield mapping nodes from a dataclass/mapping AST in stable order."""

    if value is None or isinstance(value, (str, bytes, int, float, bool)):
        return
    if isinstance(value, Mapping):
        yield dict(value)
        for child in value.values():
            yield from walk(child)
        return
    if isinstance(value, (list, tuple, set, frozenset)):
        for child in value:
            yield from walk(child)
        return
    data = mapping(value)
    if data:
        yield data
        for child in data.values():
            yield from walk(child)


def ast_kinds(ast: Any) -> set[str]:
    kinds: set[str] = set()
    for item in walk(ast):
        value = item.get("kind") or item.get("node_type") or item.get("type")
        if value is not None:
            kinds.add(str(value).casefold().replace("-", "_").replace(" ", "_"))
    return kinds


def ast_functions(ast: Any) -> set[str]:
    names: set[str] = set()
    for item in walk(ast):
        kind = str(item.get("kind") or item.get("node_type") or "").casefold()
        if "function" not in kind and "call" not in kind:
            continue
        value = item.get("name") or item.get("function_name") or item.get("functionName") or item.get("function")
        if isinstance(value, Mapping):
            value = value.get("name") or value.get("text") or value.get("value")
        if value:
            names.add(str(value).casefold())
    return names


def locations(ast: Any) -> list[Any]:
    values: list[Any] = []
    for item in walk(ast):
        for key in ("location", "span", "ast_location", "source_span"):
            if item.get(key):
                values.append(item[key])
                break
    return values


def result_mapping(result: Any) -> dict[str, Any]:
    data = mapping(result)
    if data:
        return data
    if isinstance(result, (list, tuple)):
        return {"items": list(result)}
    return {"value": result}


def result_items(result: Any, *keys: str) -> list[Any]:
    data = result_mapping(result)
    for key in keys:
        value = data.get(key)
        if value is not None:
            if isinstance(value, (list, tuple, set, frozenset)):
                return list(value)
            return [value]
    return []


def item_mapping(item: Any) -> dict[str, Any]:
    return mapping(item)


def item_type(item: Any) -> str:
    data = item_mapping(item)
    return str(data.get("type") or data.get("edge_type") or data.get("kind") or "").upper()


def item_target(item: Any) -> str:
    data = item_mapping(item)
    return str(data.get("to_id") or data.get("target") or data.get("target_id") or data.get("name") or "")


def all_strings(value: Any):
    if value is None:
        return
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for child in value.values():
            yield from all_strings(child)
    elif isinstance(value, (list, tuple, set, frozenset)):
        for child in value:
            yield from all_strings(child)
    elif is_dataclass(value):
        yield from all_strings(asdict(value))


def analysis_edges(result: Any) -> list[Any]:
    return result_items(result, "edges", "facts", "graph_facts", "assertions")


def analysis_evidence(result: Any) -> list[Any]:
    data = result_mapping(result)
    values = result_items(result, "evidence", "evidence_items", "diagnostics")
    for edge in analysis_edges(result):
        edge_data = item_mapping(edge)
        values.extend(edge_data.get("evidence", []) if isinstance(edge_data.get("evidence"), list) else [])
    return values
