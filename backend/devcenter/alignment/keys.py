"""Alignment keys for objects with no lineageTag (technical design section 4.1).

Each key is case-insensitive, because Power BI names are case-insensitive.
``table`` is the home table after the table alignment: a donor object of a
renamed table uses the target table name.
"""

from __future__ import annotations

from typing import Any
from collections.abc import Sequence


def fold(value: Any) -> str:
    return str(value if value is not None else "").casefold()


def relationship_key(ends: Sequence[tuple[str, str]]) -> tuple[Any, ...]:
    """The two columns at the ends of the relationship, in any order."""

    return ("relationship", tuple(sorted((fold(table), fold(column)) for table, column in ends)))


def calculation_item_key(group_table: str, item: str) -> tuple[Any, ...]:
    """Calculation group + item name."""

    return ("calculation_item", fold(group_table), fold(item))


def role_key(role: str) -> tuple[Any, ...]:
    """RLS role: the role name."""

    return ("role", fold(role))


def ols_key(role: str, table: str, column: str | None = None) -> tuple[str, ...]:
    """OLS permission: role + table (+ column)."""

    return (fold(role), fold(table)) if column is None else (fold(role), fold(table), fold(column))


def partition_key(table: str, partition: str) -> tuple[Any, ...]:
    """Partition: table + partition name. ``partition_table_key`` is the second pass."""

    return ("partition", fold(table), fold(partition))


def partition_table_key(table: str) -> tuple[Any, ...]:
    """Partition, second pass: the table alone, when each side has one partition in the table."""

    return ("partition_table", fold(table))


def page_id_key(page_id: str) -> tuple[Any, ...]:
    """Report page, first pass: the page ID."""

    return ("page", fold(page_id))


def page_name_key(display_name: str | None) -> tuple[Any, ...] | None:
    """Report page, second pass: the page display name."""

    return ("page_name", fold(display_name)) if display_name else None


def visual_key(visual_id: str) -> tuple[Any, ...]:
    """Visual: the visual ID only. Version 1 has no approximate visual alignment."""

    return ("visual", fold(visual_id))


def report_measure_key(table: str, name: str) -> tuple[Any, ...]:
    """Report measure: home table + name."""

    return ("report_measure", fold(table), fold(name))


def qualified_key(kind: str, table: str | None, name: str) -> tuple[Any, ...]:
    """Same qualified name and type: tables, columns, measures, hierarchies, shared expressions, functions."""

    return (kind, fold(table), fold(name)) if table is not None else (kind, fold(name))


def field_key(table: str | None, name: str) -> tuple[Any, ...]:
    """The name space of the fields of a table: a column and a measure with the same name have a type conflict."""

    return ("field", fold(table), fold(name))
