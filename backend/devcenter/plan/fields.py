"""Field locations of report pages and visuals (technical design sections 6.2 and 6.4).

A field location is one ``Column`` or ``Measure`` binding in a PBIR visual or
page file, with the JSON Pointer of the object that holds the binding. The
pointer is relative to ``visual.json`` or ``page.json``. A projection field is
a field of ``visual.query``; a filter field is a field of ``filterConfig``.
Cascade removes a visual only when no projection field stays.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator, Mapping

from backend.devcenter.compare.extract import CompareObject

COLUMN = "column"
MEASURE = "measure"
_BINDINGS = {"Column": COLUMN, "Measure": MEASURE}


@dataclass(frozen=True)
class FieldLocation:
    pointer: str
    kind: str
    entity: str
    property: str
    projection: bool
    query_ref: str | None = None
    native_query_ref: str | None = None


def _escape(part: Any) -> str:
    return str(part).replace("~", "~0").replace("/", "~1")


def _walk(value: Any, pointer: str, projection: bool, parent: Mapping[str, Any] | None) -> Iterator[FieldLocation]:
    if isinstance(value, Mapping):
        for key, kind in _BINDINGS.items():
            binding = value.get(key)
            if isinstance(binding, Mapping) and isinstance(binding.get("Property"), str):
                expression = binding.get("Expression") if isinstance(binding.get("Expression"), Mapping) else {}
                source = expression.get("SourceRef") if isinstance(expression.get("SourceRef"), Mapping) else {}
                entity = source.get("Entity")
                if isinstance(entity, str):
                    holder = parent or {}
                    yield FieldLocation(pointer, kind, entity, binding["Property"], projection,
                                        holder.get("queryRef") if isinstance(holder.get("queryRef"), str) else None,
                                        holder.get("nativeQueryRef") if isinstance(holder.get("nativeQueryRef"), str) else None)
                    return
        for key in sorted(value):
            child = value[key]
            yield from _walk(child, f"{pointer}/{_escape(key)}", projection, value if key == "field" else None)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk(child, f"{pointer}/{index}", projection, None)


def field_locations(item: CompareObject) -> list[FieldLocation]:
    """Give the field locations of a visual or a page, in pointer order."""

    found: list[FieldLocation] = []
    if item.kind == "visual":
        found.extend(_walk(item.props.get("fields"), "/visual/query", True, None))
    if item.kind in {"visual", "page"}:
        found.extend(_walk(item.props.get("filters"), "", False, None))
    return found


def new_query_ref(old: str | None, entity: str, prop: str, new_entity: str, new_prop: str) -> str | None:
    """Change ``Entity.Property`` in a ``queryRef``. Other text stays."""

    if old is None:
        return None
    return old.replace(f"{entity}.{prop}", f"{new_entity}.{new_prop}")


def new_native_query_ref(old: str | None, prop: str, new_prop: str) -> str | None:
    """Change ``nativeQueryRef`` only when it is equal to the old name (section 6.5)."""

    return new_prop if old is not None and old == prop else old
