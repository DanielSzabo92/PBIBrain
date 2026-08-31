"""Schema bootstrap kept separate from graph business logic."""

from __future__ import annotations

from .schema import ladybug_schema


def apply_schema(connection) -> None:
    for statement in ladybug_schema():
        try:
            connection.execute(statement)
        except Exception as exc:
            if "already" not in str(exc).lower() and "exists" not in str(exc).lower():
                raise
