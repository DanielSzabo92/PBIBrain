"""Completeness assessment for Dev Center impact analysis (technical design section 7, AC9).

Checks scanner coverage, unmodeled object types, unresolved visual bindings,
unreadable remote reports, bookmarks referencing changed objects, and areas
affected only by possible/inferred links.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence


def build_completeness(
    *,
    not_checked_object_types: Sequence[str] | None = None,
    unresolved_bindings: Sequence[Mapping[str, Any]] | None = None,
    unreadable_reports: Sequence[Mapping[str, Any]] | None = None,
    bookmarks: Sequence[Mapping[str, Any]] | None = None,
    possible_only_areas: Sequence[Mapping[str, Any]] | None = None,
    explicit_incomplete: bool = False,
) -> dict[str, Any]:
    """Emit a completeness block adhering to contract http/impact.reply.json."""
    types = list(not_checked_object_types or [])
    unresolved = list(unresolved_bindings or [])
    unreadable = list(unreadable_reports or [])
    bm_list = list(bookmarks or [])
    possible_areas = list(possible_only_areas or [])

    is_complete = not (
        explicit_incomplete
        or bool(types)
        or bool(unresolved)
        or bool(unreadable)
    )

    return {
        "status": "complete" if is_complete else "incomplete",
        "not_checked_object_types": types,
        "unresolved_bindings": unresolved,
        "unreadable_reports": unreadable,
        "bookmarks": bm_list,
        "possible_only_areas": possible_areas,
    }
