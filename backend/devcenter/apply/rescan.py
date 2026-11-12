"""Rescan of the target after an apply (technical design section 13 step 10).

The rescan compares the object index of the target before and after the apply
with the plan operations. Each difference names the object, the expected state,
and the found state (UC7).
"""

from __future__ import annotations

from typing import Any
from collections.abc import Mapping, Sequence

PRESENT = "present"
ABSENT = "absent"
CHANGED = "changed"
UNCHANGED = "unchanged"

_CREATES = {"CREATE", "CREATE_REPORT_MEASURE"}
_COPIES = {"COPY_PAGE", "COPY_VISUAL"}
_DELETES = {"DELETE", "DELETE_PAGE", "DELETE_VISUAL", "DELETE_REPORT_MEASURE"}
_RENAMES = {"RENAME", "RENAME_PAIR"}
# Report row kinds: a report write can change a row that has no own operation (for example ``pages.json``).
_REPORT_KINDS = {"report", "page", "visual", "bookmark", "report_measure"}


def _key(object_type: str, name: str, table: str | None) -> str:
    return f"{object_type}:{table}/{name}" if table else f"{object_type}:{name}"


def _row_key(operation: Mapping[str, Any]) -> str:
    return str(operation.get("row_key") or "").split("@", 1)[0]


def _kind(key: str) -> str:
    return key.split(":", 1)[0]


def _table_renames(operations: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    return {str(item.get("old_name")): str(item.get("new_name")) for item in operations
            if item.get("op") in _RENAMES and item.get("object_type") == "table" and item.get("old_name") and item.get("new_name")}


def _object_renames(operations: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    """The row key of each renamed object that is not a table, to its key after the rename (in its old table)."""

    found = {}
    for item in operations:
        if item.get("op") in _RENAMES and item.get("object_type") != "table" and item.get("old_name") and item.get("new_name"):
            key = _row_key(item)
            if key:
                found[key] = _key(str(item.get("object_type") or ""), str(item["new_name"]), item.get("table"))
    return found


def _moved(key: str, tables: Mapping[str, str], objects: Mapping[str, str] | None = None) -> str:
    """Give the key after the object renames and the table renames of the plan."""

    key = (objects or {}).get(key, key)
    kind, _, rest = key.partition(":")
    if kind == "table" and rest in tables:
        return f"table:{tables[rest]}"
    table, slash, name = rest.partition("/")
    if slash and table in tables:
        return f"{kind}:{tables[table]}/{name}"
    return key


def differences(operations: Sequence[Mapping[str, Any]], before: Mapping[str, str], after: Mapping[str, str]) -> list[dict[str, str]]:
    """Give each difference between the rescan and the plan. An empty list is a full match."""

    found: dict[tuple[str, str], dict[str, str]] = {}
    tables = _table_renames(operations)
    objects = _object_renames(operations)
    touched: set[str] = set()

    def expect(key: str, expected: str) -> None:
        touched.add(key)
        if expected == PRESENT and key not in after:
            found[(key, expected)] = {"object": key, "expected": PRESENT, "found": ABSENT}
        elif expected == ABSENT and key in after:
            found[(key, expected)] = {"object": key, "expected": ABSENT, "found": PRESENT}
        elif expected == CHANGED:
            if key not in after:
                found[(key, expected)] = {"object": key, "expected": CHANGED, "found": ABSENT}
            elif before.get(key) == after.get(key):
                found[(key, expected)] = {"object": key, "expected": CHANGED, "found": UNCHANGED}

    copies: dict[str, int] = {}
    for operation in operations:
        op = operation.get("op")
        object_type = str(operation.get("object_type") or "")
        key = _row_key(operation)
        table = operation.get("table")
        if op in _RENAMES and operation.get("old_name") and operation.get("new_name"):
            old_table = table
            new_table = tables.get(str(table), table) if table else None
            if object_type == "table":
                expect(f"table:{operation['old_name']}", ABSENT)
                expect(f"table:{operation['new_name']}", PRESENT)
            else:
                expect(_key(object_type, str(operation["old_name"]), old_table), ABSENT)
                expect(_key(object_type, str(operation["new_name"]), new_table), PRESENT)
        elif op in _DELETES and key:
            expect(key, ABSENT)
        elif op in _CREATES and operation.get("name"):
            new_type = "measure" if operation.get("domain") == "model" and object_type == "report_measure" else object_type
            expect(_moved(_key(new_type, str(operation["name"]), table), tables), PRESENT)
        elif op in _COPIES:
            copies[object_type] = copies.get(object_type, 0) + 1
        elif op == "REWRITE_EXPRESSION" and operation.get("domain") == "model" and key and object_type != "table":
            expect(_moved(key, tables, objects), CHANGED)
        elif key:
            expect(_moved(key, tables, objects), PRESENT)
    for object_type, count in sorted(copies.items()):
        added = [key for key in after if _kind(key) == object_type and key not in before]
        if len(added) < count:
            found[(object_type, "copy")] = {"object": object_type, "expected": f"{count} {PRESENT}", "found": f"{len(added)} {PRESENT}"}
        touched.update(added)
    # A model object that no operation names must stay. With no rename in the plan, it must also be equal.
    renames = any(item.get("op") in _RENAMES for item in operations)
    moved_before = {_moved(key, tables): value for key, value in before.items()}
    for key in sorted(set(moved_before) | set(after)):
        if key in touched or _kind(key) in _REPORT_KINDS or any(key == _moved(item, tables) for item in touched):
            continue
        if key not in after:
            found[(key, "kept")] = {"object": key, "expected": PRESENT, "found": ABSENT}
        elif key not in moved_before:
            found[(key, "kept")] = {"object": key, "expected": ABSENT, "found": PRESENT}
        elif moved_before[key] != after[key] and key in before and not renames:
            found[(key, "kept")] = {"object": key, "expected": UNCHANGED, "found": CHANGED}
    return sorted(found.values(), key=lambda item: (item["object"], item["expected"]))
