"""Project-wide common / divergent / unique objects (issue #14).

The Development Center alignment (``backend.devcenter.alignment``) runs over every
model (and every report) of the Brain project, with no target. Each aligned group
lands in one bucket:

* ``identical``: in two or more sources, and the compared properties are equal;
* ``differs``: in two or more sources, and at least one compared property differs;
* ``renamed``: the same logic under another name in other sources (the N-way form
  of the merge "possible rename" note: one expression, at most one object per source);
* ``unique``: in one source only.

The duplicate-logic finder (spec section 13) groups DAX objects of all models by their
normalized DAX, also inside one model: the same logic under different names.

The input is the project graph, not the TOM bridge, so cloud models and reports read
by #9 take part, and no app or bridge is needed. A model or report that was not read
(``check_status: not_checked``) has no objects, so the result is marked incomplete.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable, Mapping, Sequence

from backend.devcenter.alignment import keys
from backend.devcenter.alignment.align import DomainSources, align_domain
from backend.devcenter.compare.extract import MODEL, REPORT, CompareObject
from backend.devcenter.compare.normalize import dax_key, exact_text

BUCKETS = ("differs", "renamed", "identical", "unique")

# Node type -> compare kind (the kinds the alignment keys know).
MODEL_KINDS = {
    "TABLE": "table", "COLUMN": "column", "MEASURE": "measure", "HIERARCHY": "hierarchy",
    "CALCULATION_ITEM": "calculation_item", "PARTITION": "partition", "SHARED_EXPRESSION": "shared_expression",
    "RELATIONSHIP": "relationship", "SECURITY_ROLE": "role",
}
REPORT_KINDS = {"PAGE": "page", "VISUAL": "visual"}
_DAX_TYPES = {"MEASURE", "COLUMN", "TABLE", "CALCULATION_ITEM"}
_M_TYPES = {"SHARED_EXPRESSION", "PARTITION"}
# Objects whose logic is an expression: the rename and duplicate-logic checks read it.
_LOGIC_TYPES = {"MEASURE", "COLUMN", "TABLE", "CALCULATION_ITEM", "SHARED_EXPRESSION"}
_DUPLICATE_TYPES = {"MEASURE", "COLUMN", "CALCULATION_ITEM"}

# Properties that are scan bookkeeping, links or layout, not the definition of the object.
_IGNORED = {
    "raw_source", "dax_ast", "source_hash", "lineage_tag", "lineageTag", "check_status", "not_checked_reason",
    "not_checked_detail", "model_ids", "field_roles", "binding_evidence", "unresolved_field_refs", "query",
    "visual_name", "x", "y", "z", "width", "height", "from_ref", "to_ref", "origin", "workspace_name",
    "source_status", "parameters", "sources",
}

DEFAULT_LIMIT = 50
MAX_LIMIT = 200
EXPRESSION_PREVIEW = 120


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _short(value: str, size: int = 12) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:size]


def _normal(node_type: str, key: str, value: Any) -> Any:
    """The compared form of one property value: normalized DAX or M for expressions."""

    if key == "expression":
        if node_type in _DAX_TYPES:
            return dax_key(_text(value)) if value is not None else None
        if node_type in _M_TYPES:
            return exact_text(_text(value)) if value is not None else None
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (list, dict)):
        return json.dumps(value, sort_keys=True, default=str)
    return value


def _compared(node: Any) -> dict[str, Any]:
    props: dict[str, Any] = {}
    for key, value in node.properties.items():
        if key in _IGNORED or key.endswith("_id") or key.endswith("_ids"):
            continue
        props[key] = _normal(node.type, key, value)
    if node.description:
        props["description"] = node.description.strip()
    return props


def _signature(node: Any) -> tuple[Any, ...] | None:
    """The "same logic" value: kind and normalized expression."""

    if node.type not in _LOGIC_TYPES:
        return None
    expression = node.properties.get("expression")
    if expression is None or not _text(expression).strip():
        return None
    return (node.type, _normal(node.type, "expression", expression))


def _ref_pair(value: Any) -> tuple[str, str]:
    if isinstance(value, Mapping):
        return _text(value.get("table")), _text(value.get("column"))
    return "", _text(value)


def _root_of(node: Any, domain: str) -> str | None:
    return node.model_id if domain == MODEL else node.report_id


class _Project:
    """The project graph, split into sources (models and reports) and compare objects."""

    def __init__(self, nodes: Iterable[Any]) -> None:
        self.nodes = list(nodes)
        self.by_id = {node.id: node for node in self.nodes}
        self.roots = {MODEL: [node for node in self.nodes if node.type == "MODEL"],
                      REPORT: [node for node in self.nodes if node.type == "REPORT"]}
        for domain in self.roots:
            self.roots[domain].sort(key=lambda node: (node.name.casefold(), node.id))
        self.refs: dict[str, str] = {}
        for domain, prefix in ((MODEL, "m"), (REPORT, "r")):
            for index, node in enumerate(self.roots[domain], start=1):
                self.refs[node.id] = f"{prefix}{index}"
        self.objects: dict[str, CompareObject] = {}
        self.node_of: dict[int, Any] = {}

    def owner_name(self, node: Any) -> str | None:
        owner = node.properties.get("table_id") or node.properties.get("parent_id")
        owner_node = self.by_id.get(owner) if owner else None
        return owner_node.name if owner_node is not None else None

    def compare_object(self, node: Any, domain: str) -> CompareObject:
        kind = (MODEL_KINDS if domain == MODEL else REPORT_KINDS)[node.type]
        table = self.owner_name(node) if node.type not in {"TABLE", "SHARED_EXPRESSION", "RELATIONSHIP", "SECURITY_ROLE", "PAGE"} else None
        extra: dict[str, Any] = {}
        if node.type == "RELATIONSHIP":
            extra["ends"] = [_ref_pair(node.properties.get("from_ref")), _ref_pair(node.properties.get("to_ref"))]
        elif node.type == "PAGE":
            raw = node.properties.get("raw_source") if isinstance(node.properties.get("raw_source"), Mapping) else {}
            extra.update(page_id=_text(raw.get("name") or node.source_id or node.name), display_name=node.properties.get("display_name") or node.name)
        elif node.type == "VISUAL":
            extra["visual_id"] = _text(node.properties.get("visual_name") or node.source_id or node.name)
        item = CompareObject(kind=kind, subtype=kind, domain=domain, source_key=node.id, name=node.name or "", table=table,
                             lineage_tag=_lineage_tag(node), props=_compared(node), extra=extra)
        self.node_of[id(item)] = node
        return item

    def sources(self, domain: str, scope_ids: set[str] | None) -> list[tuple[str, list[CompareObject]]]:
        kinds = MODEL_KINDS if domain == MODEL else REPORT_KINDS
        members: dict[str, list[CompareObject]] = {node.id: [] for node in self.roots[domain]
                                                     if scope_ids is None or node.id in scope_ids}
        for node in self.nodes:
            root = _root_of(node, domain)
            if node.type in kinds and root in members and node.status in (None, "", "factual"):
                members[root].append(self.compare_object(node, domain))
        # The partition second-pass key needs the number of partitions of the table.
        for items in members.values():
            counts: dict[str | None, int] = {}
            for item in items:
                if item.kind == "partition":
                    counts[item.table] = counts.get(item.table, 0) + 1
            for item in items:
                if item.kind == "partition":
                    item.extra["partition_count"] = counts[item.table]
            items.sort(key=lambda item: item.source_key)
        return list(members.items())


def _lineage_tag(node: Any) -> str | None:
    raw = node.properties.get("raw_source") if isinstance(node.properties.get("raw_source"), Mapping) else {}
    tag = node.properties.get("lineage_tag") or raw.get("lineageTag") or raw.get("lineage_tag")
    return str(tag) if tag else None


def _differs(items: Sequence[CompareObject], *, names: bool = False) -> tuple[list[str], int]:
    """The compared properties that are not equal in every member, and the number of variants."""

    keys_: set[str] = set()
    for item in items:
        keys_.update(item.props)
    differs = sorted(key for key in keys_ if len({json.dumps(item.props.get(key), sort_keys=True, default=str) for item in items}) > 1)
    if names and len({keys.fold(item.name) for item in items}) > 1:
        differs = ["name", *differs]
    variants = len({json.dumps(item.props, sort_keys=True, default=str) for item in items})
    return differs, variants


def _domain_groups(project: _Project, domain: str, members: list[tuple[str, list[CompareObject]]]) -> list[dict[str, Any]]:
    source_ids = [source_id for source_id, _ in members]
    alignment = align_domain(DomainSources(domain, members, None))
    rows = [dict(row.members) for row in alignment.rows]

    # Renamed: rows whose members all share one logic signature, merged when the rows hold
    # at most one object of each source and their names differ (the N-way possible rename).
    by_signature: dict[Any, list[int]] = {}
    for index, row in enumerate(rows):
        signatures = {_signature(project.node_of[id(item)]) for item in row.values()}
        if len(signatures) == 1 and None not in signatures:
            by_signature.setdefault(repr(next(iter(signatures))), []).append(index)
    renamed: dict[int, list[int]] = {}
    for indexes in by_signature.values():
        if len(indexes) < 2:
            continue
        seen = [source for index in indexes for source in rows[index]]
        names = {keys.fold(item.name) for index in indexes for item in rows[index].values()}
        if len(seen) == len(set(seen)) and len(names) > 1:
            renamed[indexes[0]] = indexes
    absorbed = {index for indexes in renamed.values() for index in indexes[1:]}

    groups: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if index in absorbed:
            continue
        merged = dict(row)
        for other in renamed.get(index, [])[1:]:
            merged.update(rows[other])
        ordered = [(source_id, merged[source_id]) for source_id in source_ids if source_id in merged]
        items = [item for _, item in ordered]
        reference = project.node_of[id(items[0])]
        differs, variants = _differs(items)
        if index in renamed:
            bucket = "renamed"
        elif len(items) == 1:
            bucket = "unique"
        else:
            bucket = "differs" if differs else "identical"
        key = "|".join(sorted(item.source_key for item in items))
        group: dict[str, Any] = {
            "id": f"{reference.type.lower()}:{_short(key)}",
            "domain": domain,
            "type": reference.type,
            "name": items[0].name,
            "bucket": bucket,
            "in": [project.refs[source_id] for source_id, _ in ordered],
            "present": len(items),
            "of": len(source_ids),
            "objects": {project.refs[source_id]: item.source_key for source_id, item in ordered},
        }
        if items[0].table:
            group["table"] = items[0].table
        if bucket in {"differs", "renamed"} and differs:
            group["differs"] = differs
        if variants > 1:
            group["variants"] = variants
        if bucket == "renamed":
            group["names"] = {project.refs[source_id]: item.name for source_id, item in ordered}
        groups.append(group)
    return groups


def _duplicate_logic(project: _Project, scope_ids: set[str] | None) -> list[dict[str, Any]]:
    """DAX objects of all models with the same normalized DAX and different names."""

    found: dict[str, list[Any]] = {}
    for node in project.nodes:
        if node.type not in _DUPLICATE_TYPES or node.status not in (None, "", "factual"):
            continue
        if node.model_id not in project.refs or (scope_ids is not None and node.model_id not in scope_ids):
            continue
        signature = _signature(node)
        if signature is None:
            continue
        found.setdefault(repr(signature), []).append(node)
    result = []
    for signature, nodes in found.items():
        if len(nodes) < 2 or len({keys.fold(node.name) for node in nodes}) < 2:
            continue
        nodes.sort(key=lambda node: (project.refs[node.model_id], node.name.casefold(), node.id))
        expression = " ".join(_text(nodes[0].properties.get("expression")).split())
        result.append({
            "id": f"dup:{_short(signature)}",
            "type": nodes[0].type,
            "expression": expression if len(expression) <= EXPRESSION_PREVIEW else expression[:EXPRESSION_PREVIEW - 1] + "…",
            "count": len(nodes),
            "members": [{"in": project.refs[node.model_id], "name": node.name, "table": project.owner_name(node), "object_id": node.id}
                        for node in nodes],
        })
    result.sort(key=lambda item: (-item["count"], item["type"], item["members"][0]["name"].casefold()))
    return result


def _scope_ids(project: _Project, scope: str | Sequence[str] | None) -> tuple[set[str] | None, set[str]]:
    """``scope``: None/"all", "models", "reports", or model/report ids (or their refs m1, r2…)."""

    domains = {MODEL, REPORT}
    if scope is None or scope == "" or scope == "all":
        return None, domains
    if scope == "models":
        return None, {MODEL}
    if scope == "reports":
        return None, {REPORT}
    values = [scope] if isinstance(scope, str) else list(scope)
    wanted = {part.strip() for value in values for part in str(value).split(",") if part.strip()}
    by_ref = {ref: node_id for node_id, ref in project.refs.items()}
    ids = {by_ref.get(value, value) for value in wanted}
    unknown = sorted(value for value in ids if value not in project.refs)
    if unknown:
        raise ValueError(f"Unknown model or report in scope: {', '.join(unknown)}")
    return ids, {MODEL if project.by_id[node_id].type == "MODEL" else REPORT for node_id in ids}


def build_commonality(nodes: Iterable[Any], *, scope: str | Sequence[str] | None = None) -> dict[str, Any]:
    """The whole overview: sources, every group, counts and duplicate-logic groups."""

    project = _Project(nodes)
    scope_ids, domains = _scope_ids(project, scope)
    sources = []
    groups: list[dict[str, Any]] = []
    for domain in (MODEL, REPORT):
        if domain not in domains:
            continue
        members = project.sources(domain, scope_ids)
        for source_id, _ in members:
            root = project.by_id[source_id]
            entry = {"ref": project.refs[source_id], "id": source_id, "name": root.name, "domain": domain}
            if root.properties.get("check_status") == "not_checked":
                entry["not_checked"] = True
            sources.append(entry)
        if members:
            groups.extend(_domain_groups(project, domain, members))
    order = {bucket: index for index, bucket in enumerate(BUCKETS)}
    groups.sort(key=lambda group: (order[group["bucket"]], group["domain"] != MODEL, group["type"], group["name"].casefold(), group["id"]))
    counts: dict[str, dict[str, int]] = {}
    for group in groups:
        counts.setdefault(group["type"], dict.fromkeys(BUCKETS, 0))[group["bucket"]] += 1
    totals = {bucket: sum(item[bucket] for item in counts.values()) for bucket in BUCKETS}
    duplicates = _duplicate_logic(project, scope_ids) if MODEL in domains else []
    return {
        "sources": sources,
        "counts": dict(sorted(counts.items())),
        "totals": totals,
        "groups": groups,
        "duplicate_logic": duplicates,
        "incomplete": any(source.get("not_checked") for source in sources),
    }


def _page(items: list[dict[str, Any]], offset: int, limit: int) -> tuple[list[dict[str, Any]], bool]:
    return items[offset:offset + limit], offset + limit < len(items)


def get_commonality(
    nodes: Iterable[Any],
    *,
    object_type: str | None = None,
    scope: str | Sequence[str] | None = None,
    bucket: str | None = None,
    group_id: str | None = None,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    compact: bool = False,
    max_chars: int | None = None,
) -> dict[str, Any]:
    """A filtered, paginated page of the overview.

    ``compact`` (the MCP form) leaves out object ids; ask again with ``group_id`` for
    them. ``max_chars`` drops groups from the end of the page until the JSON reply fits,
    and sets ``has_more`` so the caller pages on.
    """

    if bucket and bucket not in BUCKETS:
        raise ValueError(f"bucket must be one of {', '.join(BUCKETS)}")
    limit = max(1, min(int(limit), MAX_LIMIT))
    offset = max(0, int(offset))
    full = build_commonality(nodes, scope=scope)
    if group_id:
        group = next((item for item in full["groups"] if item["id"] == group_id), None)
        if group is None:
            duplicate = next((item for item in full["duplicate_logic"] if item["id"] == group_id), None)
            if duplicate is None:
                raise ValueError(f"Unknown group: {group_id}")
            return {"sources": full["sources"], "duplicate": duplicate}
        return {"sources": [source for source in full["sources"] if source["ref"] in group["in"]], "group": group}
    wanted_type = object_type.upper() if object_type else None
    groups = [group for group in full["groups"] if (wanted_type is None or group["type"] == wanted_type)
              and (bucket is None or group["bucket"] == bucket)]
    duplicates = [item for item in full["duplicate_logic"] if wanted_type is None or item["type"] == wanted_type]
    page, has_more = _page(groups, offset, limit)
    duplicate_page, duplicates_more = _page(duplicates, 0, min(limit, 20) if compact else limit)
    if compact:
        page = [{key: value for key, value in group.items() if key not in {"objects", "domain", "present"}} for group in page]
        duplicate_page = [{**item, "members": [{key: value for key, value in member.items() if key != "object_id"}
                                               for member in item["members"]]} for item in duplicate_page]
    reply = {
        "sources": full["sources"],
        "counts": full["counts"] if wanted_type is None else {wanted_type: full["counts"].get(wanted_type, dict.fromkeys(BUCKETS, 0))},
        "totals": full["totals"],
        "incomplete": full["incomplete"],
        "filter": {"type": wanted_type, "scope": scope, "bucket": bucket},
        "total_groups": len(groups),
        "offset": offset,
        "limit": limit,
        "groups": page,
        "has_more": has_more,
        "duplicate_logic_total": len(duplicates),
        "duplicate_logic": duplicate_page,
        "duplicate_logic_more": duplicates_more,
    }
    def finish() -> None:
        reply["returned"] = len(reply["groups"])
        reply["next_offset"] = offset + len(reply["groups"]) if reply["has_more"] else None

    finish()
    if max_chars is not None:
        while len(json.dumps(reply, ensure_ascii=False, default=str)) > max_chars and (reply["groups"] or reply["duplicate_logic"]):
            if reply["duplicate_logic"] and len(reply["duplicate_logic"]) >= len(reply["groups"]):
                reply["duplicate_logic"].pop()
                reply["duplicate_logic_more"] = True
            else:
                reply["groups"].pop()
                reply["has_more"] = True
            finish()
    return reply
