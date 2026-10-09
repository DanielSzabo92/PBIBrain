from __future__ import annotations

from collections import Counter
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from backend.snapshots.manifest import canonical_json, content_hash


def canonical_result(result: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(result, Mapping) or set(result) - {"columns", "rows", "error"} or "error" in result:
        raise ValueError("Invalid/error query result")
    columns, rows = result.get("columns"), result.get("rows")
    if not isinstance(columns, list) or not isinstance(rows, list):
        raise ValueError("Query result requires typed columns and rows")
    names = [item["name"] for item in columns]
    if len(names) != len(set(names)) or any(set(item) != {"name", "type"} for item in columns):
        raise ValueError("Result column metadata invalid")
    def cell(value: Any) -> Any:
        if isinstance(value, Decimal):
            if not value.is_finite():
                raise ValueError("Non-finite number")
            number = format(value, "f")
            if "." in number: number = number.rstrip("0").rstrip(".")
            return {"$decimal": "0" if value == 0 else number}
        if isinstance(value, dict) and set(value) == {"$decimal"} and isinstance(value["$decimal"], str):
            return cell(Decimal(value["$decimal"]))
        if isinstance(value, dict) and set(value) == {"$datetime"} and isinstance(value["$datetime"], str):
            return cell(datetime.fromisoformat(value["$datetime"]))
        if isinstance(value, dict) and set(value) == {"$date"} and isinstance(value["$date"], str):
            return cell(date.fromisoformat(value["$date"]))
        if isinstance(value, datetime):
            return {"$datetime": value.isoformat()}
        if isinstance(value, date):
            return {"$date": value.isoformat()}
        if value is None or type(value) in {bool, int, float, str}:
            canonical_json(value)
            return value
        raise ValueError("Unsupported result cell")
    normalized = []
    for row in rows:
        if isinstance(row, Mapping):
            if set(row) != set(names):
                raise ValueError("Missing/additional result cell")
            row = [row[name] for name in names]
        if not isinstance(row, (list, tuple)) or len(row) != len(names):
            raise ValueError("Invalid result row shape")
        normalized.append([cell(value) for value in row])
    return {"columns": columns, "rows": normalized}


def _number(value: Any) -> Decimal | None:
    if isinstance(value, dict) and set(value) == {"$decimal"}:
        return Decimal(value["$decimal"])
    if type(value) in {int, float}:
        return Decimal(str(value))
    return None


def compare_results(before: Mapping[str, Any], after: Mapping[str, Any], mode: str = "EXACT", policy: Mapping[str, Any] | None = None) -> dict[str, Any]:
    config = dict(policy or {})
    if mode in {"EXPECTED_VALUE", "EXPECTED_CHANGE"} and config.get("expected_comparison_mode", "EXACT") not in {"EXACT", "NUMERIC_TOLERANCE", "SET_EQUIVALENCE"}:
        raise ValueError("Expected-result comparison must use a bounded comparison mode")
    try:
        a, b = canonical_result(before), canonical_result(after)
    except (ValueError, KeyError, TypeError) as error:
        return {"status": "FAILED", "assertions": [{"code": "RESULT_ERROR", "message": str(error)}], "changed": True}
    changed = canonical_json(a) != canonical_json(b)
    errors = []
    if a["columns"] != b["columns"]:
        errors.append({"code": "COLUMN_SCHEMA_CHANGED"})
    shape = config.get("result_shape", {})
    if len(a["rows"]) > len(b["rows"]) and not shape.get("allow_missing_rows", False):
        errors.append({"code": "MISSING_ROWS"})
    if len(a["rows"]) < len(b["rows"]) and not shape.get("allow_new_rows", False):
        errors.append({"code": "ADDITIONAL_ROWS"})
    numeric = config.get("numeric", {})
    absolute = Decimal(str(numeric.get("absolute_tolerance", 0)))
    relative = Decimal(str(numeric.get("relative_tolerance", 0)))
    if not absolute.is_finite() or not relative.is_finite() or absolute < 0 or relative < 0:
        raise ValueError("Invalid numeric tolerance")
    if mode == "EXPECTED_DELTA":
        minimum, maximum = Decimal(str(config["minimum_delta"])), Decimal(str(config["maximum_delta"]))
        if not minimum.is_finite() or not maximum.is_finite() or minimum > maximum:
            raise ValueError("Invalid expected delta bounds")
    if mode == "MONITOR":
        return {"status": "INCONCLUSIVE", "changed": changed, "assertions": [{"code": "MONITOR_REQUIRES_ACCEPTANCE"}], "before_hash": content_hash(a), "after_hash": content_hash(b)}
    if mode == "SCHEMA_ONLY":
        pass
    elif mode == "SET_EQUIVALENCE":
        if Counter(canonical_json(row) for row in a["rows"]) != Counter(canonical_json(row) for row in b["rows"]):
            errors.append({"code": "ROW_SET_CHANGED"})
    elif mode in {"EXPECTED_VALUE", "EXPECTED_CHANGE"}:
        expected = config.get("expected_result")
        if expected is None:
            errors.append({"code": "EXPECTED_RESULT_MISSING"})
        else:
            result = compare_results(expected, after, config.get("expected_comparison_mode", "EXACT"), {"numeric": numeric})
            errors.extend(result.get("assertions", []) if result["status"] != "PASSED" else [])
    elif mode in {"EXACT", "NUMERIC_TOLERANCE", "PRESERVE_AGGREGATE", "EXPECTED_DELTA"}:
        rows_a, rows_b = a["rows"], b["rows"]
        if len(rows_a) != len(rows_b):
            errors.append({"code": "ROW_COUNT_CHANGED", "before": len(rows_a), "after": len(rows_b)})
        for i, (row_a, row_b) in enumerate(zip(rows_a, rows_b)):
            for j, (x, y) in enumerate(zip(row_a, row_b)):
                nx, ny = _number(x), _number(y)
                matches = canonical_json(x) == canonical_json(y)
                delta = None
                if mode != "EXACT" and nx is not None and ny is not None:
                    delta = ny - nx
                    if mode == "EXPECTED_DELTA":
                        matches = Decimal(str(config["minimum_delta"])) <= delta <= Decimal(str(config["maximum_delta"]))
                    else:
                        matches = abs(delta) <= max(absolute, relative * max(abs(nx), abs(ny)))
                elif type(x) is str and type(y) is str and config.get("text_collation") == "CASE_INSENSITIVE":
                    matches = x.casefold() == y.casefold()
                if not matches:
                    errors.append({"code": "CELL_CHANGED", "row": i, "column": j, "before": x, "after": y, "delta": str(delta) if delta is not None else None})
        if mode == "PRESERVE_AGGREGATE" and (len(rows_a) != 1 or len(rows_b) != 1):
            errors.append({"code": "AGGREGATE_QUERY_MUST_RETURN_ONE_ROW"})
    else:
        raise ValueError("Unsupported comparison mode")
    return {"status": "FAILED" if errors else "PASSED", "changed": changed, "assertions": errors,
            "before_hash": content_hash(a), "after_hash": content_hash(b), "row_count_before": len(a["rows"]), "row_count_after": len(b["rows"]), "tolerance_policy_version": "explicit-1"}
