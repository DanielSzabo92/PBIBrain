"""The compare reads and the alignment changes of the open merge session (build step S3).

The engine computes the alignment and the compare rows again from the session
state and the sources (section 1.3). The session stores only the alignment
overrides: ``alignment_overrides`` is ``{donor source ID: [override]}``, and an
override is ``{kind, target_key, donor_key}`` with the source keys of the two
objects. The kinds are ``confirm``, ``break``, and ``reject_rename``.

The HTTP reads call ``compare_rows``, ``row_diff``, and ``display_folders``.
Only the pywebview JS API calls ``alignment_override`` and
``compare_mode_set`` (ADR 0003).
"""

from __future__ import annotations

import copy
import difflib
from typing import Any, Mapping, Sequence

from backend.devcenter.alignment.align import OVERRIDE_BREAK, OVERRIDE_CONFIRM, OVERRIDE_REJECT_RENAME
from backend.devcenter.alignment.keys import fold
from backend.devcenter.compare.extract import CompareObject, load_objects
from backend.devcenter.compare.rows import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    MODE_DEFAULT,
    MODE_STRICT,
    SORT_FIELDS,
    CompareResult,
    SessionSource,
    build_rows,
    filter_rows,
    sort_rows,
    state_counts,
)
from backend.devcenter.errors import DevCenterError, not_allowed

ACTION_CLEAR = "clear"
ACTIONS = (OVERRIDE_CONFIRM, OVERRIDE_BREAK, OVERRIDE_REJECT_RENAME, ACTION_CLEAR)


def targets(document: Mapping[str, Any]) -> tuple[str | None, str | None]:
    """Give the source IDs of the target model and the target report."""

    target = document.get("target") or {}
    model = (target.get("model") or {}).get("source_id")
    report = target.get("report") or {}
    return model, report.get("source_id") if report.get("mode") == "existing" else None


def _sources(devcenter: Any, document: Mapping[str, Any]) -> list[SessionSource]:
    found = []
    for record in document["sources"]:
        objects = None
        if document["source_status"].get(record["source_id"], "ok") == "ok":
            try:
                objects = load_objects(devcenter._load(record))
            except DevCenterError:
                objects = None
        found.append(SessionSource(record["source_id"], objects))
    return found


def compute(devcenter: Any, document: Mapping[str, Any], mode: str | None = None) -> CompareResult:
    """Give the full compare row set of a session document."""

    model, report = targets(document)
    return build_rows(_sources(devcenter, document), target_model=model, target_report=report,
                      overrides=document.get("alignment_overrides") or {}, mode=mode or document.get("compare_mode") or MODE_DEFAULT,
                      merge_choices=document.get("merge_choices") or {}, marks=document.get("source_marks") or [])


def _one(query: Mapping[str, Sequence[str]], name: str) -> str | None:
    values = list(query.get(name) or [])
    return str(values[-1]) if values else None


def _integer(query: Mapping[str, Sequence[str]], name: str, default: int, maximum: int) -> int:
    value = _one(query, name)
    if value is None or value == "":
        return default
    try:
        number = int(value)
    except ValueError as exc:
        raise DevCenterError("invalid_payload", "The paging value is not valid.", {"reason": "invalid_paging", "field": name}) from exc
    if number < 0 or number > maximum:
        raise DevCenterError("invalid_payload", "The paging value is not valid.", {"reason": "invalid_paging", "field": name})
    return number


def _snapshot(devcenter: Any) -> dict[str, Any]:
    with devcenter._lock:
        return copy.deepcopy(devcenter._require_open().document)


def compare_rows(devcenter: Any, query: Mapping[str, Sequence[str]]) -> dict[str, Any]:
    """``GET compare-rows``: filters, ``q``, ``sort`` (``<field>`` or ``<field>:<asc or desc>``), ``limit`` and ``offset``."""

    sort = _one(query, "sort")
    order = _one(query, "order")
    if sort is not None and ":" in sort:
        # The form of the UI client is "<field>:<asc or desc>".
        sort, order = sort.split(":", 1)
    order = order or "asc"
    if sort is not None and sort not in SORT_FIELDS or order not in {"asc", "desc"}:
        raise DevCenterError("invalid_payload", "The sort value is not valid.", {"reason": "invalid_sort"})
    limit = _integer(query, "limit", DEFAULT_LIMIT, MAX_LIMIT)
    offset = _integer(query, "offset", 0, 10 ** 9)
    document = _snapshot(devcenter)
    result = compute(devcenter, document)
    selected = sort_rows(filter_rows(result.rows, query), sort, order)
    page = selected[offset: offset + limit]
    model, report = targets(document)
    return {
        "revision": document["revision"],
        "compare_mode": document.get("compare_mode") or MODE_DEFAULT,
        "target": {"model": model, "report": report},
        "total": len(selected),
        "state_counts": state_counts(selected),
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(page) < len(selected),
        "rows": page,
        "warnings": result.warnings,
        "orphan_marks": result.orphan_marks,
    }


def _find_row(result: CompareResult, key: str) -> dict[str, Any]:
    for row in result.rows:
        if key in {row["row_key"], row["row_id"]}:
            return row
    raise DevCenterError("not_found", "The row does not exist.", {"row_key": key})


def _cell(row: Mapping[str, Any], source_id: str | None) -> dict[str, Any] | None:
    return next((cell for cell in row["cells"] if cell["source_id"] == source_id and cell["present"]), None)


def row_diff(devcenter: Any, row: str, query: Mapping[str, Sequence[str]]) -> dict[str, Any]:
    """``GET compare-rows/{row}/diff?source=<id>``: the code of the row in the reference and in one source."""

    document = _snapshot(devcenter)
    result = compute(devcenter, document)
    found = _find_row(result, row)
    present = [cell for cell in found["cells"] if cell["present"]]
    reference = next((cell for cell in present if cell["role"] == "target"), present[0] if present else None)
    source_id = _one(query, "source")
    if source_id is None:
        source_id = next((cell["source_id"] for cell in present if cell is not reference), reference["source_id"] if reference else None)
    if not any(cell["source_id"] == source_id for cell in found["cells"]):
        raise DevCenterError("not_found", "The source is not in this row.", {"source_id": source_id})
    cell = _cell(found, source_id)

    def code(item: Mapping[str, Any] | None) -> tuple[str, str | None]:
        if item is None:
            return "", None
        value: CompareObject = result.objects[(item["source_id"], item["source_key"])]
        return value.code, value.language

    reference_text, reference_language = code(reference)
    source_text, source_language = code(cell)
    unified = "".join(difflib.unified_diff(reference_text.splitlines(keepends=True), source_text.splitlines(keepends=True),
                                           fromfile=reference["source_id"] if reference else "none", tofile=str(source_id)))
    return {
        "revision": document["revision"],
        "row_key": found["row_key"],
        "row_id": found["row_id"],
        "source_id": source_id,
        "reference_source_id": reference["source_id"] if reference else None,
        "language": reference_language or source_language or "json",
        "reference_text": reference_text,
        "source_text": source_text,
        "unified": unified,
    }


def display_folders(devcenter: Any, query: Mapping[str, Sequence[str]]) -> dict[str, Any]:
    """``GET display-folders?source=<id>&object_type=<type>`` (UC20; ``type`` also works). The default source is the target model."""

    document = _snapshot(devcenter)
    source_id = _one(query, "source") or targets(document)[0]
    types = {fold(part) for value in [*(query.get("type") or []), *(query.get("object_type") or [])]
             for part in str(value).split(",") if part}
    folders: set[str] = set()
    if source_id is not None:
        record = next((item for item in document["sources"] if item["source_id"] == source_id), None)
        if record is None:
            raise DevCenterError("not_found", "The source is not in the session.", {"source_id": source_id})
        for item in load_objects(devcenter._load(record)).all():
            if item.display_folder and (not types or item.kind in types):
                folders.update(part.strip() for part in item.display_folder.split(";") if part.strip())
    return {"revision": document["revision"], "source_id": source_id, "types": sorted(types),
            "folders": sorted(folders, key=lambda value: (value.casefold(), value))}


# State changes (JS API only) --------------------------------------------------


def _pair_keys(result: CompareResult, document: Mapping[str, Any], request: Mapping[str, Any]) -> tuple[str, str, list[str]]:
    """Give the target source key, the donor source key, and the row keys of the action."""

    action = request.get("action")
    source_id = request.get("source_id")
    model, report = targets(document)
    row = _find_row(result, str(request.get("row_key")))
    target_id = model if row["domain"] == "model" else report
    target_cell = _cell(row, target_id)
    if target_cell is None:
        raise not_allowed("This row has no target object.", "no_target_object", row_key=row["row_key"])
    if source_id == target_id:
        raise not_allowed("Select a donor source.", "source_is_target", source_id=source_id)
    if action in {OVERRIDE_BREAK, ACTION_CLEAR}:
        donor = _cell(row, source_id)
        if donor is None and action == OVERRIDE_BREAK:
            raise not_allowed("The row has no object of this source.", "no_source_object", row_key=row["row_key"])
        return target_cell["source_key"], donor["source_key"] if donor else "", [row["row_key"]]
    if _cell(row, source_id) is not None:
        raise not_allowed("The row has an object of this source already. Break that match first.", "already_aligned",
                          row_key=row["row_key"])
    other = _find_row(result, str(request.get("other_row_key") or ""))
    donor = _cell(other, source_id)
    if donor is None or other["domain"] != row["domain"] or _cell(other, target_id) is not None:
        raise not_allowed("The other row has no free object of this source.", "no_source_object", row_key=other["row_key"])
    return target_cell["source_key"], donor["source_key"], [row["row_key"], other["row_key"]]


def alignment_override(devcenter: Any, request: Mapping[str, Any]) -> dict[str, Any]:
    """Confirm a match, break a match, reject a possible rename, or clear the overrides of a row (UC21)."""

    action = request.get("action")
    if action not in ACTIONS:
        raise DevCenterError("invalid_payload", "The action is not valid.", {"reason": "invalid_action"})
    reply: dict[str, Any] = {}
    with devcenter._lock:
        def mutate(document: dict[str, Any]) -> tuple[Any, Any]:
            source_id = request.get("source_id")
            if not any(item["source_id"] == source_id for item in document["sources"]):
                raise DevCenterError("not_found", "The source is not in the session.", {"source_id": source_id})
            before_rows = compute(devcenter, document)
            target_key, donor_key, row_keys = _pair_keys(before_rows, document, request)
            overrides = document.setdefault("alignment_overrides", {})
            entries = list(overrides.get(source_id, []))
            before = copy.deepcopy(entries)
            if action == ACTION_CLEAR:
                entries = [item for item in entries if item.get("target_key") != target_key]
            else:
                entries = [item for item in entries if not (item.get("target_key") == target_key and item.get("donor_key") == donor_key)
                           and not (action == OVERRIDE_CONFIRM and item.get("kind") == OVERRIDE_CONFIRM
                                    and (item.get("target_key") == target_key or item.get("donor_key") == donor_key))]
                entries.append({"kind": action, "target_key": target_key, "donor_key": donor_key})
            entries.sort(key=lambda item: (item["target_key"], item["donor_key"], item["kind"]))
            if entries:
                overrides[source_id] = entries
            else:
                overrides.pop(source_id, None)
            removed = []
            if action != OVERRIDE_REJECT_RENAME:
                for key in row_keys:
                    if key in document["merge_choices"]:
                        removed.append(key)
                        del document["merge_choices"][key]
            after_rows = compute(devcenter, document)
            new_keys = sorted({row["row_key"] for row in after_rows.rows
                               if (_cell(row, source_id) or {}).get("source_key") == donor_key
                               or any(cell["present"] and cell["role"] == "target" and cell["source_key"] == target_key
                                      for cell in row["cells"])})
            reply.update(row_keys=new_keys, removed_choices=removed)
            return {"overrides": before, "merge_choices": removed}, {"overrides": copy.deepcopy(entries)}

        document = devcenter._change(request, "alignment_override", request.get("row_key"), mutate)
    return {"revision": document["revision"], "action": action, **reply}


def compare_mode_set(devcenter: Any, request: Mapping[str, Any]) -> dict[str, Any]:
    mode = request.get("compare_mode")
    if mode not in {MODE_DEFAULT, MODE_STRICT}:
        raise DevCenterError("invalid_payload", "The compare mode is not valid.", {"reason": "invalid_mode"})
    with devcenter._lock:
        def mutate(document: dict[str, Any]) -> tuple[Any, Any]:
            before = document.get("compare_mode")
            document["compare_mode"] = mode
            return before, mode

        document = devcenter._change(request, "compare_mode_set", "compare_mode", mutate)
    return {"revision": document["revision"], "compare_mode": document["compare_mode"]}
