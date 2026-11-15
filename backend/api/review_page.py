"""The review queue answered a page at a time (finding 01 of the adversarial review).

The page never receives the project: ``ReviewIndex`` is built once per graph state from the slim review
snapshot, and each request filters, sorts, groups and cuts it on the server. A page carries its rows, the
nodes and links those rows show, and the counts the filters and tabs need (``facets``).

The rules mirror the page's own (``frontend/src/views/ReviewQueue.jsx``, ``reviewEvidence.js``,
``reviewGroups.js``): which records are one suggestion, what is low evidence, how patterns are formed.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterable, Mapping
from typing import Any

DECIDED = frozenset({"rejected", "approved", "overridden"})
PAGE_LIMIT = 25
MAX_LIMIT = 500
SORTS = frozenset({"confidence-high", "confidence-low", "impact-high", "impact-low"})
SECTIONS = frozenset({"all", "standard", "low"})

_KIND_NAMES = {"ALIAS": "Other name", "ROLE": "Table role", "BUSINESS_CONCEPT": "Meaning", "SEMANTICALLY_MAPS_TO": "Meaning", "BEHAVIOR": "Behaviour", "SELECTOR": "Selector"}
_BASIS_NAMES = {"object_name": "from the name", "name": "from the name", "description": "from the description", "dax_ast": "from the formula", "dax_analysis": "from the formula"}
_TYPE_PLURALS = {"MEASURE": "measures", "COLUMN": "columns", "TABLE": "tables", "VISUAL": "visuals", "PAGE": "pages", "REPORT": "reports", "SEMANTIC_MODEL": "models", "RELATIONSHIP": "relationships"}
_IMPACT_RANKS = {"critical": 4, "high": 3, "medium": 2, "normal": 2, "low": 1, "none": 0}
# Object identifiers inside free text (reasons, evidence), as the page's readableText finds them.
_IDENTITY = re.compile(
    r"\b(?:model|report|table|column|measure|page|visual|workspace|semantic|edge|override|relationship|selector|conflict):[^\s,;\"{}]+"
    r"|\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b|\b[0-9a-f]{32,64}\b",
    re.IGNORECASE,
)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _first(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def review_issue(item: Mapping[str, Any]) -> str:
    value = str(item.get("issue") or item.get("issue_type") or item.get("kind") or item.get("type") or "candidate").lower()
    if "conflict" in value:
        return "conflict"
    if "stale" in value or "override" in value:
        return "stale"
    return "candidate"


def item_target(item: Mapping[str, Any]) -> str | None:
    value = item.get("target") or item.get("target_id") or item.get("object") or item.get("object_id") or item.get("source_object")
    if isinstance(value, Mapping):
        return value.get("id") or value.get("object_id")
    return value


def _number(value: Any, fallback: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return number if math.isfinite(number) else fallback


def item_confidence(item: Mapping[str, Any]) -> float:
    return _number(_first(item.get("confidence"), _mapping(item.get("properties")).get("confidence")), 0.0)


def item_impact(item: Mapping[str, Any]) -> float:
    properties = _mapping(item.get("properties"))
    raw = _first(item.get("impact"), item.get("impact_score"), properties.get("impact"), properties.get("impact_score"))
    value = _first(raw.get("score"), raw.get("value")) if isinstance(raw, Mapping) else raw
    if isinstance(value, str) and value.strip().lower() in _IMPACT_RANKS:
        return float(_IMPACT_RANKS[value.strip().lower()])
    return _number(value, 0.0)


def _safe_json(value: Any) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, separators=(",", ":"))
    except (TypeError, ValueError):
        return str(value)


def merge_review_items(items: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Records that describe one suggestion become one row (the page's mergeReviewItems)."""

    merged: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(item for item in items if item):
        issue = review_issue(item)
        nested = _mapping(item.get("item"))
        semantic = f"{issue}:{item_target(item) or 'unknown'}:{_safe_json(_first(item.get('value'), item.get('meaning'), item.get('reason'), item.get('message'), index))}"
        candidate = (item.get("candidate_id") or _mapping(item.get("properties")).get("candidate_id")
                     or nested.get("candidate_id") or _mapping(nested.get("properties")).get("candidate_id"))
        key = semantic if issue == "conflict" else candidate or item.get("id") or semantic
        merged[key] = {**merged.get(key, {}), **item, "issue": issue}
    return list(merged.values())


def _clean_token(value: Any) -> str:
    text = re.sub(r"^['\"\[]+|['\"\]]+$", "", str(value or "").strip()).lower()
    return re.sub(r"[\s_\-]+", "", text)


def is_low_evidence(item: Mapping[str, Any], node: Mapping[str, Any] | None) -> bool:
    """A suggestion that only restates the object's name, or rests on the name alone (reviewEvidence.js)."""

    issue = str(item.get("issue") or item.get("issue_type") or "").lower()
    if issue in {"conflict", "stale"}:
        return False
    nested = _mapping(item.get("item"))
    properties = _mapping(item.get("properties"))
    target_name = (node or {}).get("name") or item.get("name") or item.get("target_name") or ""
    value = str(_first(item.get("value"), item.get("meaning"), properties.get("value"), properties.get("meaning"), nested.get("value"), "") or "").strip()
    name, suggested = _clean_token(target_name), _clean_token(value)
    if name and suggested and name == suggested:
        return True
    source = str(item.get("source") or properties.get("candidate_source") or nested.get("source") or "").lower()
    evidence = item.get("evidence") or nested.get("evidence") or []
    if not isinstance(evidence, list):
        evidence = []

    def origin(entry: Any) -> str:
        return entry.lower() if isinstance(entry, str) else str(_mapping(entry).get("source") or _mapping(entry).get("origin") or "").lower()

    only_name = bool(evidence) and all(origin(entry) in {"object_name", "name"} for entry in evidence)
    raw = _first(item.get("confidence"), properties.get("confidence"), nested.get("confidence"))
    score = None
    if raw is not None:
        number = _number(raw, math.nan)
        if not math.isnan(number):
            score = round(number * 100 if number <= 1 else number)
    if source in {"object_name", "name"} and (len(evidence) <= 1 or only_name):
        return True
    if only_name:
        return True
    return score is not None and score <= 35 and (not evidence or only_name)


def _review_kind(item: Mapping[str, Any]) -> str:
    nested = _mapping(item.get("item"))
    return (item.get("assertion_type") or _mapping(item.get("properties")).get("assertion_type") or nested.get("assertion_type")
            or _mapping(nested.get("properties")).get("assertion_type") or item.get("type") or "")


def _review_basis(item: Mapping[str, Any]) -> str:
    return (_mapping(_mapping(item.get("item")).get("properties")).get("candidate_source")
            or _mapping(item.get("properties")).get("candidate_source") or item.get("source") or "")


def _plural(object_type: str) -> str:
    return _TYPE_PLURALS.get(object_type) or f"{(object_type or 'object').lower().replace('_', ' ')}s"


def group_key(item: Mapping[str, Any], node: Mapping[str, Any] | None) -> tuple[str, str, str, str]:
    """(key, kind, basis, type) of the pattern a row belongs to (reviewGroups.js)."""

    special = item["issue"] if item.get("issue") in {"conflict", "stale"} else ""
    kind = special or _review_kind(item)
    basis = "" if special else _BASIS_NAMES.get(_review_basis(item), "from a rule")
    object_type = (node or {}).get("type") or ""
    return f"{kind}|{basis}|{object_type}", kind, basis, object_type


def _scope_value(item: Mapping[str, Any], node: Mapping[str, Any] | None, key: str) -> str:
    value = _first(item.get(key), _mapping(item.get("properties")).get(key), (node or {}).get(key), _mapping((node or {}).get("properties")).get(key))
    return value or ""


def row_key(item: Mapping[str, Any]) -> str:
    """The page's reviewItemKey: the row's own identifier, else its issue and target."""

    return str(item.get("id") or f"{item.get('issue')}-{item_target(item)}")


def decision_id(item: Mapping[str, Any]) -> str | None:
    """The identifier a decision on this row is recorded under (the page's bulkReview payload)."""

    nested = _mapping(item.get("item"))
    review_id = item.get("review_id") or item.get("override_id") or item.get("id")
    return (_mapping(item.get("properties")).get("candidate_id") or nested.get("candidate_id")
            or _mapping(nested.get("properties")).get("candidate_id") or review_id or item_target(item))


_PREVIEW_LINKS = 3
_ALIASES = {"review_id": "id", "key": "id", "object_id": "target_id", "type": "assertion_type"}
_NESTED_FIELDS = ("candidate_id", "assertion_type", "source", "confidence", "property")
_NESTED_PROPERTIES = ("candidate_id", "candidate_source", "assertion_type")
_NODE_FIELDS = ("id", "type", "name", "displayName", "title", "source_id", "visual_type", "visualType", "model_id", "report_id", "table_id", "page_id", "status")
_NODE_PROPERTIES = ("name", "display_name", "displayName", "visualType", "table_id", "parent_id", "calculation_group_id", "model_id", "report_id",
                    "visual_type", "title", "page_name", "data_type", "is_hidden")


class ReviewIndex:
    """Every open suggestion of one graph state, ready to be filtered and cut into pages."""

    def __init__(self, snapshot: Mapping[str, Any]) -> None:
        self.nodes: dict[str, dict[str, Any]] = {node["id"]: node for node in snapshot.get("nodes") or [] if isinstance(node, Mapping) and node.get("id")}
        self.edges_of: dict[str, list[dict[str, Any]]] = {}
        for edge in snapshot.get("edges") or []:
            for end in (edge.get("from_id"), edge.get("to_id")):
                if end:
                    self.edges_of.setdefault(end, []).append(edge)
        external = [{**item, "issue": review_issue(item)} for item in snapshot.get("review_items") or []]
        if external:
            records = external
        else:
            candidates = [{**item, "issue": "candidate"} for item in snapshot.get("semantic_candidates") or []]
            conflicts = [{**item, "issue": "conflict", "status": item.get("status") or "candidate", "confidence": item.get("confidence") or 0} for item in snapshot.get("conflicts") or []]
            stale_records = [*(snapshot.get("stale_overrides") or []), *(item for item in snapshot.get("overrides") or [] if item.get("status") == "stale")]
            stale = [{**item, "issue": "stale", "status": item.get("status") or "candidate", "confidence": item.get("confidence") or 0} for item in stale_records]
            records = [*candidates, *conflicts, *stale]
        self.rows: list[dict[str, Any]] = []
        for item in merge_review_items(records):
            if item.get("status") in DECIDED:
                continue
            node = self.nodes.get(item_target(item) or "")
            key, kind, basis, object_type = group_key(item, node)
            self.rows.append({**item, "key": row_key(item), "low_evidence": is_low_evidence(item, node), "pattern": key,
                              "_kind": kind, "_basis": basis, "_type": object_type,
                              "_model": _scope_value(item, node, "model_id"), "_report": _scope_value(item, node, "report_id")})
        self.types = sorted({row["_type"] for row in self.rows if row["_type"]})
        self.models = sorted({row["_model"] for row in self.rows if row["_model"]})
        self.reports = sorted({row["_report"] for row in self.rows if row["_report"]})
        # Decided suggestions, then saved decisions (edits) that still apply; ``reviewed_kind`` tells them apart.
        self.reviewed = [{**item, "reviewed_kind": "suggestion"} for item in snapshot.get("semantic_candidates") or [] if item.get("status") in DECIDED]
        self.reviewed += [{**item, "reviewed_kind": "override"} for item in snapshot.get("overrides") or [] if item.get("status") != "stale"]
        self.scan = snapshot.get("scan") or {}

    def matching(self, *, issue: str = "ALL", object_type: str = "ALL", model_id: str = "ALL", report_id: str = "ALL",
                 pattern: str = "", section: str = "all", sort: str = "confidence-high", target: str = "") -> list[dict[str, Any]]:
        def keep(row: Mapping[str, Any]) -> bool:
            if target and item_target(row) != target:
                return False
            if issue == "low-evidence":
                if not row["low_evidence"]:
                    return False
            elif issue != "ALL" and row["issue"] != issue:
                return False
            if object_type != "ALL" and row["_type"] != object_type:
                return False
            if model_id != "ALL" and row["_model"] != model_id:
                return False
            if report_id != "ALL" and row["_report"] != report_id:
                return False
            if pattern and row["pattern"] != pattern:
                return False
            if section == "low":
                return row["low_evidence"]
            if section == "standard":
                return not row["low_evidence"]
            return True

        rows = [row for row in self.rows if keep(row)]
        if sort == "confidence-low":
            rows.sort(key=item_confidence)
        elif sort == "impact-high":
            rows.sort(key=item_impact, reverse=True)
        elif sort == "impact-low":
            rows.sort(key=item_impact)
        else:
            rows.sort(key=item_confidence, reverse=True)
        return rows

    def groups(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        found: dict[str, dict[str, Any]] = {}
        for row in rows:
            group = found.get(row["pattern"])
            if group is None:
                special = row["issue"] if row["issue"] in {"conflict", "stale"} else ""
                title = ("Conflicts" if special == "conflict" else "Decisions whose object is gone" if special == "stale"
                         else f"{_KIND_NAMES.get(row['_kind'], 'Suggestion')} {row['_basis']}")
                group = {"key": row["pattern"], "kind": row["_kind"], "basis": row["_basis"], "type": row["_type"], "title": title,
                         "scope": _plural(row["_type"]) if row["_type"] else "", "bulk": not special, "count": 0, "low": 1.0, "high": 0.0, "_names": set()}
                found[row["pattern"]] = group
            group["count"] += 1
            score = _number(_first(row.get("confidence"), _mapping(row.get("properties")).get("confidence")), 0.0)
            group["low"] = min(group["low"], score)
            group["high"] = max(group["high"], score)
            name = (self.nodes.get(item_target(row) or "") or {}).get("name")
            if name:
                group["_names"].add(name)
        result = [{**{key: value for key, value in group.items() if key != "_names"}, "names": len(group["_names"])} for group in found.values()]
        return sorted(result, key=lambda group: (group["bulk"], -group["count"], group["key"]))

    def context(self, rows: list[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """The rows of a page, each with its links counted, and the objects they show.

        A row's own object comes whole (its preview shows the description and formula). Its links come as
        counts with the first few objects each way (``links``), as the preview shows them. Owners and objects
        the text names come with names only.
        """

        full: set[str] = set()
        named: set[str] = set()
        answered: list[dict[str, Any]] = []
        for row in rows:
            row = _public(row)
            target = item_target(row)
            if target:
                full.add(target)
                used_by: list[str] = []
                depends_on: list[str] = []
                incoming = outgoing = 0
                for edge in self.edges_of.get(target, []):
                    if edge.get("to_id") == target:
                        incoming += 1
                        if len(used_by) < _PREVIEW_LINKS and edge.get("from_id"):
                            used_by.append(edge["from_id"])
                    elif edge.get("from_id") == target:
                        outgoing += 1
                        if len(depends_on) < _PREVIEW_LINKS and edge.get("to_id"):
                            depends_on.append(edge["to_id"])
                named.update(used_by + depends_on)
                row["links"] = {"incoming": incoming, "outgoing": outgoing, "used_by": used_by, "depends_on": depends_on}
            for text in (row.get("reason"), row.get("evidence"), _mapping(row.get("item")).get("evidence"), row.get("value")):
                if text:
                    named.update(_IDENTITY.findall(text if isinstance(text, str) else json.dumps(text, default=str)))
            answered.append(_slim_row(row))
        wanted = full | named
        pending = [node for node in (self.nodes.get(node_id) for node_id in wanted if node_id) if node]
        while pending:
            node = pending.pop()
            properties = _mapping(node.get("properties"))
            for owner in (node.get("model_id"), node.get("report_id"), node.get("table_id"), node.get("page_id"),
                          properties.get("table_id"), properties.get("parent_id"), properties.get("calculation_group_id")):
                if owner and owner not in wanted and owner in self.nodes:
                    wanted.add(owner)
                    pending.append(self.nodes[owner])
        nodes = [_whole_node(self.nodes[node_id]) if node_id in full else _slim_node(self.nodes[node_id])
                 for node_id in sorted(node_id for node_id in wanted if node_id in self.nodes)]
        return answered, nodes


def _slim_row(row: dict[str, Any]) -> dict[str, Any]:
    """A suggestion row without the copies of its text that the nested record repeats.

    Conflicts and outdated decisions keep their record whole: undoing one writes it back.
    """

    # Copies under another name: the page reads ``id``, ``target_id`` and ``assertion_type``.
    row = {key: value for key, value in row.items()
           if not (key in _ALIASES and value is not None and value == row.get(_ALIASES[key]))}
    if isinstance(row.get("evidence"), list):
        target = item_target(row)
        row["evidence"] = [{key: value for key, value in entry.items() if key not in {"status", "evidence_class"} and not (key == "target" and value == target)}
                           if isinstance(entry, Mapping) else entry for entry in row["evidence"]]
    nested = row.get("item")
    if row.get("issue") != "candidate" or not isinstance(nested, Mapping):
        return row
    properties = _mapping(nested.get("properties"))
    slim = {key: nested[key] for key in _NESTED_FIELDS if nested.get(key) is not None}
    kept = {key: properties[key] for key in _NESTED_PROPERTIES if properties.get(key) is not None}
    if kept:
        slim["properties"] = kept
    if row.get("value") is None and nested.get("meaning") is not None:
        slim["meaning"] = nested["meaning"]
    if not row.get("evidence") and nested.get("evidence"):
        slim["evidence"] = nested["evidence"]
    return {**row, "item": slim}


def _whole_node(node: Mapping[str, Any]) -> dict[str, Any]:
    """A row's own object, without the copies its properties keep of the formula and description."""

    properties = _mapping(node.get("properties"))
    twice = {key for key in ("expression", "description") if node.get(key) is not None and properties.get(key) == node.get(key)}
    if not twice:
        return dict(node)
    return {**node, "properties": {key: value for key, value in properties.items() if key not in twice}}


def _slim_node(node: Mapping[str, Any]) -> dict[str, Any]:
    """What a name, a glyph and a scope line need of an object that is not a row's own."""

    slim = {key: node[key] for key in _NODE_FIELDS if node.get(key) is not None}
    properties = {key: value for key, value in _mapping(node.get("properties")).items() if key in _NODE_PROPERTIES and value is not None}
    if properties:
        slim["properties"] = properties
    return slim


def _public(row: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if not key.startswith("_")}


def _choice(value: Any, default: str = "ALL") -> str:
    text = str(value).strip() if value is not None else ""
    return text or default


def review_page(index: ReviewIndex, params: Mapping[str, Any]) -> dict[str, Any]:
    """One page of the queue, of one pattern, or of the reviewed decisions, with the counts the page shows."""

    tab = _choice(params.get("tab"), "queue")
    sort = _choice(params.get("sort"), "confidence-high")
    if sort not in SORTS:
        raise ValueError(f"unsupported review sort: {sort}")
    section = _choice(params.get("section"), "all")
    if section not in SECTIONS:
        raise ValueError(f"unsupported review section: {section}")
    offset = max(0, int(_number(params.get("offset"), 0)))
    limit = max(1, min(MAX_LIMIT, int(_number(params.get("limit"), PAGE_LIMIT))))
    filters = {key: _choice(params.get(key)) for key in ("issue", "object_type", "model_id", "report_id")}
    facets = {"types": index.types, "models": index.models, "reports": index.reports, "open": len(index.rows), "reviewed": len(index.reviewed)}
    if tab == "reviewed":
        rows, nodes = index.context(index.reviewed[offset:offset + limit])
        return {"tab": tab, "total": len(index.reviewed), "offset": offset, "limit": limit, "has_more": offset + limit < len(index.reviewed),
                "items": rows, "nodes": nodes, "facets": facets, "scan": index.scan}
    # ``target`` answers one object's open suggestions and conflicts (the Inspector's review block).
    matching = index.matching(**filters, sort=sort, target=str(params.get("target") or ""))
    low_total = sum(1 for row in matching if row["low_evidence"])
    answer: dict[str, Any] = {"tab": tab, "matching": len(matching), "standard_total": len(matching) - low_total, "low_total": low_total,
                              "approvable": sum(1 for row in matching if row["issue"] == "candidate"), "facets": facets, "offset": offset, "limit": limit}
    if params.get("grouping") == "pattern":
        answer["groups"] = index.groups(matching)
    pattern = str(params.get("pattern") or "")
    if pattern or params.get("rows", "1") not in {"0", "false"}:
        rows = [row for row in matching if (not pattern or row["pattern"] == pattern)
                and (section == "all" or (section == "low") == row["low_evidence"])]
        items, nodes = index.context(rows[offset:offset + limit])
        answer.update({"total": len(rows), "has_more": offset + limit < len(rows), "items": items, "nodes": nodes,
                       "approvable_total": sum(1 for row in rows if row["issue"] == "candidate")})
    return answer


def matching_decision_ids(index: ReviewIndex, selector: Mapping[str, Any]) -> list[str]:
    """The suggestions a bulk decision by view covers: what the page shows for these filters, candidates only.

    Conflicts and outdated decisions need a choice each, so a filter never decides them.
    """

    allowed = {"issue", "object_type", "model_id", "report_id", "pattern", "section"}
    if set(selector) - allowed:
        raise ValueError("unsupported review view filter")
    section = _choice(selector.get("section"), "all")
    if section not in SECTIONS:
        raise ValueError(f"unsupported review section: {section}")
    rows = index.matching(**{key: _choice(selector.get(key)) for key in ("issue", "object_type", "model_id", "report_id")},
                          pattern=str(selector.get("pattern") or ""), section=section)
    return [identifier for identifier in (decision_id(row) for row in rows if row["issue"] == "candidate") if identifier]
