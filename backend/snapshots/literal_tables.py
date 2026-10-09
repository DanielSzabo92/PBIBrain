"""Prove a deliberately narrow calculated-table source has no dependencies.

DATATABLE with literal rows is data embedded in metadata. Other calculated
tables retain the existing incomplete-coverage diagnostic.
"""
from backend.dax.parser import parse_dax

TYPES = {"BOOLEAN", "LOGICAL", "CURRENCY", "DECIMAL", "DATETIME", "DOUBLE", "INTEGER", "INT64", "STRING", "TEXT"}


def literal_table(expression: str) -> dict | None:
    try:
        root = parse_dax(expression).ast.to_dict()
    except (ValueError, TypeError):
        return None
    if root.get("kind") != "function_call" or root.get("name", "").upper() != "DATATABLE":
        return None
    arguments = root.get("arguments", [])
    if len(arguments) < 3 or len(arguments) % 2 != 1:
        return None
    columns = []
    for index in range(0, len(arguments) - 1, 2):
        name, datatype = arguments[index:index + 2]
        if name.get("kind") != "literal" or name.get("literal_type") != "STRING" or datatype.get("kind") != "identifier" or datatype.get("name", "").upper() not in TYPES:
            return None
        columns.append(name["value"])
    if len(set(columns)) != len(columns):
        return None

    def constant(node):
        kind = node.get("kind")
        if kind == "literal":
            return True
        if kind == "unary_operator" and node.get("operator") == "-":
            return constant(node.get("operand", {}))
        if kind == "function_call":
            arguments = node.get("arguments", [])
            name = node.get("name", "").upper()
            return (name == "BLANK" and not arguments) or (name in {"DATE", "TIME"} and len(arguments) == 3 and all(item.get("kind") == "literal" and item.get("literal_type") == "NUMBER" for item in arguments))
        return False

    rows = arguments[-1]
    if rows.get("kind") != "table_constructor":
        return None
    for row in rows.get("values", []):
        if row.get("kind") not in {"table_constructor", "tuple_constructor"} or len(row.get("values", [])) != len(columns) or not all(constant(item) for item in row["values"]):
            return None
    return {"rule": "DAX_LITERAL_DATATABLE_V1", "columns": columns, "row_count": len(rows.get("values", []))}
