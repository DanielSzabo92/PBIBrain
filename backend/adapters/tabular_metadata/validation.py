"""Checks over TOM output; complex filter semantics remain runtime obligations."""
from __future__ import annotations
from typing import Any
from backend.validation import ValidationResult, ValidationIssue


def validate_tabular_structure(metadata: dict[str, Any]) -> tuple[ValidationResult, list[str]]:
    result, unknown = ValidationResult(), []
    for source, artifact in sorted(metadata.items()):
        model = artifact["database"]["model"]
        tables = {table["name"]: table for table in model.get("tables", [])}
        columns = {(table["name"], column["name"]): column for table in tables.values() for column in table.get("columns", [])}
        parents = {name: name for name in tables}

        def representative(name: str) -> str:
            while parents[name] != name:
                parents[name] = parents[parents[name]]
                name = parents[name]
            return name

        for relation in sorted(model.get("relationships", []), key=lambda item: item.get("name", "")):
            name = relation.get("name", "")
            endpoints = [(relation.get(side + "Table"), relation.get(side + "Column")) for side in ("from", "to")]
            if any(endpoint not in columns for endpoint in endpoints):
                result.add(ValidationIssue("TOM_RELATIONSHIP_ENDPOINT_UNRESOLVED", "ERROR", "Relationship endpoint is unresolved", category="tabular_structure", source="TOM", evidence=[{"source_file": source, "relationship": name}]))
                continue
            left, right = [columns[endpoint].get("dataType") for endpoint in endpoints]
            if not left or not right:
                unknown.append("RELATIONSHIP_DATATYPE_UNKNOWN:" + name)
            elif left != right:
                # Different types require authoritative processing evidence.
                unknown.append("RELATIONSHIP_DATATYPE_COMPATIBILITY_NOT_VERIFIED:" + name)
            if relation.get("type", "singleColumn") != "singleColumn":
                unknown.append("UNSUPPORTED_RELATIONSHIP_TYPE:" + name)
            if relation.get("isActive", True):
                a, b = (representative(endpoint[0]) for endpoint in endpoints)
                if a == b:
                    # An undirected cycle is a conservative warning, not proof
                    # that the engine rejects weighted/limited filter paths.
                    unknown.append("ACTIVE_FILTER_TOPOLOGY_REQUIRES_RUNTIME_VERIFICATION:" + name)
                else:
                    parents[a] = b
        for table in tables.values():
            for column in table.get("columns", []):
                target = column.get("sortByColumn")
                if target and (table["name"], target) not in columns:
                    result.add(ValidationIssue("TOM_SORT_COLUMN_UNRESOLVED", "ERROR", "Sort column is unresolved", category="tabular_structure", source="TOM", evidence=[{"source_file": source, "table": table["name"], "column": column["name"]}]))
    return result, sorted(set(unknown))
