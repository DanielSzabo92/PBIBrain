"""Ordered property diffs plus mandatory opaque source coverage checks."""
from __future__ import annotations

from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Mapping

from backend.snapshots.manifest import Snapshot, canonical_json, content_hash, safe_path

MISSING = {"$absent": True}
REFERENCES = {"from_column_id", "to_column_id", "sort_by", "model_id", "field_ids", "target_id", "source_column"}


def classify_mutation(property_path: str) -> str:
    first = property_path.split(".")[0]
    if first in {"lineage_tag", "source_id", "identity_manifest"}:
        return "IDENTITY_CHANGED"
    if first == "name":
        return "OBJECT_RENAMED"
    return "REFERENCE_CHANGED" if first in REFERENCES or any(part in property_path.casefold() for part in ("query", "binding", "filter", "datasetreference")) else "PROPERTY_CHANGED"


def compare_properties(before: Any, after: Any, path: str = "") -> list[dict[str, Any]]:
    if canonical_json(before) == canonical_json(after):
        return []
    if isinstance(before, dict) and isinstance(after, dict):
        differences = []
        for key in sorted(set(before) | set(after)):
            differences.extend(compare_properties(before.get(key, MISSING), after.get(key, MISSING), f"{path}.{key}" if path else key))
        return differences
    # Arrays are atomic values: collection order and duplicate multiplicity stay
    # significant unless the caller has an explicit normalization policy.
    return [{"property_path": path, "previous_value": before, "new_value": after, "classification": classify_mutation(path),
             "previous_content_hash": content_hash(before), "new_content_hash": content_hash(after), "normalization": [], "confidence": "EXACT"}]


def compare_objects(before: Mapping[str, Any] | None, after: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    obj = dict(before or after or {})
    context = {key: obj.get(key) for key in ("object_id", "object_type", "source_file", "source_location", "provenance")}
    if before is None or after is None:
        return [{**context, "property_path": "$object", "previous_value": dict(before) if before else MISSING,
                 "new_value": dict(after) if after else MISSING, "classification": "OBJECT_CREATED" if before is None else "OBJECT_DELETED",
                 "previous_content_hash": content_hash(before), "new_content_hash": content_hash(after), "normalization": [], "confidence": "EXACT"}]
    differences = compare_properties(dict(before["properties"]), dict(after["properties"]))
    if before.get("object_type") != after.get("object_type"):
        differences.append({"property_path": "$type", "previous_value": before.get("object_type"), "new_value": after.get("object_type"), "classification": "IDENTITY_CHANGED", "confidence": "EXACT"})
    for difference in differences:
        difference.update(context)
        if difference["classification"] == "OBJECT_RENAMED" and not before.get("identity_authoritative"):
            difference.update(classification="UNKNOWN_DIFFERENCE", confidence="UNCERTAIN_IDENTITY")
    return differences


def verify_source_coverage(before_manifest: list[dict[str, Any]], after_manifest: list[dict[str, Any]]) -> list[dict[str, Any]]:
    old = {item["path"]: item for item in before_manifest}
    new = {item["path"]: item for item in after_manifest}
    return [{"source_file": key, "previous_content_hash": old.get(key, {}).get("hash"), "new_content_hash": new.get(key, {}).get("hash"),
             "classification": "SOURCE_CREATED" if key not in old else "SOURCE_DELETED" if key not in new else "SOURCE_CHANGED"}
            for key in sorted(set(old) | set(new)) if old.get(key) != new.get(key)]


def _bim_covered(old: dict[str, Any], new: dict[str, Any], diffs: list[dict[str, Any]], graph: dict[str, Any]) -> bool:
    from copy import deepcopy
    from backend.snapshots.scan import ALIASES
    result = deepcopy(old)
    nodes = {item["id"]: item for item in graph.get("nodes", [])}
    aliases = {value: key for key, value in ALIASES.items()}
    for difference in diffs:
        node = nodes.get(difference["object_id"])
        if node is None or difference["classification"] in {"OBJECT_CREATED", "OBJECT_DELETED", "IDENTITY_CHANGED", "UNKNOWN_DIFFERENCE"}:
            continue
        model = result.get("model", {})
        kind = node["type"]
        targets = []
        if kind == "MODEL":
            targets = [model]
        elif kind == "RELATIONSHIP":
            targets = [item for item in model.get("relationships", []) if item.get("name") == node.get("name")]
        elif kind == "TABLE":
            targets = [item for item in model.get("tables", []) if item.get("lineageTag") == node.get("source_id") or item.get("name") == node.get("name")]
        elif kind in {"COLUMN", "MEASURE"}:
            table_id = node.get("properties", {}).get("table_id")
            table = nodes.get(table_id, {})
            for item in model.get("tables", []):
                if item.get("lineageTag") == table.get("source_id") or item.get("name") == table.get("name"):
                    targets.extend(child for child in item.get("columns" if kind == "COLUMN" else "measures", []) if child.get("lineageTag") == node.get("source_id") or child.get("name") == node.get("name"))
        if len(targets) != 1:
            continue
        target = targets[0]
        path = difference["property_path"].split(".")
        leaf = aliases.get(path[-1], path[-1])
        value = difference["new_value"]
        if path[0] in {"from_column_id", "to_column_id"}:
            endpoint = nodes.get(value, {})
            owner = nodes.get(endpoint.get("properties", {}).get("table_id"), {})
            prefix = "from" if path[0].startswith("from") else "to"
            if not endpoint or not owner:
                return False
            target[prefix + "Table"] = owner["name"]
            target[prefix + "Column"] = endpoint["name"]
            continue
        try:
            for part in path[:-1]:
                target = target[aliases.get(part, part)]
            if value == MISSING:
                target.pop(leaf, None)
            else:
                target[leaf] = value
        except (KeyError, TypeError):
            return False
    return canonical_json(result) == canonical_json(new)


def _raw_coverage(before_root: Path, after_root: Path, changes: list[dict[str, Any]], diffs: list[dict[str, Any]], graph: dict[str, Any], objects: dict[str, Any]) -> list[dict[str, Any]]:
    """Narrow verified TMDL scalar replacements. Anything else fails closed.

    TOM proves model semantics; this independent layer accounts for comments,
    unrecognized text, control files and formatting that TOM could discard.
    """
    import re
    graph_nodes = {item["id"]: item for item in graph.get("nodes", [])}
    identifier = r"(?:'((?:''|[^'])+)'|([A-Za-z_][A-Za-z0-9_]*))"

    def endpoint_text(text, object_id):
        match = re.fullmatch(identifier + r"\." + identifier, text)
        endpoint = graph_nodes.get(object_id, {})
        table = graph_nodes.get(endpoint.get("properties", {}).get("table_id"), {})
        if not match or not endpoint or not table:
            return None
        names = [(match[1] if match[1] is not None else match[2]).replace("''", "'"), (match[3] if match[3] is not None else match[4]).replace("''", "'")]
        return (match[1] is not None, match[3] is not None) if names == [table["name"], endpoint["name"]] else None
    scalar_names = {"fromColumn": "from_column_id", "toColumn": "to_column_id", "isActive": "active", "crossFilteringBehavior": "cross_filter_direction",
                    "fromCardinality": "from_cardinality", "toCardinality": "to_cardinality", "securityFilteringBehavior": "security_filter_behavior"}
    unknown = []
    for change in changes:
        relative = change["source_file"]
        if change["classification"] == "SOURCE_CHANGED" and Path(relative).suffix.casefold() in {".json", ".pbir"}:
            import json
            old = json.loads(safe_path(before_root, relative).read_text(encoding="utf-8-sig"))
            new = json.loads(safe_path(after_root, relative).read_text(encoding="utf-8-sig"))
            matching = [item for item in objects.values() if item.get("source_file") == relative and item.get("provenance") == "PBIR_STRUCTURED_JSON"]
            if len(matching) == 1:
                from copy import deepcopy
                rewritten = deepcopy(old)
                covered = True
                for difference in diffs:
                    if difference["object_id"] != matching[0]["object_id"]:
                        continue
                    path = difference["property_path"].split(".")
                    parent = rewritten
                    try:
                        for part in path[:-1]:
                            parent = parent[part]
                        if difference["new_value"] == MISSING:
                            parent.pop(path[-1], None)
                        else:
                            parent[path[-1]] = difference["new_value"]
                    except (KeyError, TypeError):
                        covered = False
                if covered and canonical_json(rewritten) == canonical_json(new):
                    continue
        if change["classification"] == "SOURCE_CHANGED" and Path(relative).suffix.casefold() == ".bim":
            import json
            old = json.loads(safe_path(before_root, relative).read_text(encoding="utf-8-sig"))
            new = json.loads(safe_path(after_root, relative).read_text(encoding="utf-8-sig"))
            if _bim_covered(old, new, diffs, graph):
                continue
        if change["classification"] != "SOURCE_CHANGED" or Path(relative).suffix.casefold() != ".tmdl":
            unknown.append({**change, "classification": "UNKNOWN_DIFFERENCE", "reason": "Source coverage requires an explicit authoritative artifact mapping"})
            continue
        from .tmdl_source import account_tmdl
        if account_tmdl(safe_path(before_root, relative).read_bytes().decode("utf-8"), safe_path(after_root, relative).read_bytes().decode("utf-8"), diffs, graph, relative):
            continue
        old = safe_path(before_root, relative).read_bytes().decode("utf-8").splitlines(keepends=True)
        new = safe_path(after_root, relative).read_bytes().decode("utf-8").splitlines(keepends=True)
        scopes = []
        scope = None
        for line in old:
            header = re.fullmatch(r"relationship\s+(.+?)(?:\r?\n)?", line)
            if header:
                scope = header.group(1).strip("'\"")
            scopes.append(scope)
        covered = True
        for tag, i, j, k, l in SequenceMatcher(a=old, b=new, autojunk=False).get_opcodes():
            if tag == "equal":
                continue
            if tag != "replace" or j - i != l - k:
                covered = False
                break
            for position in range(j - i):
                a = re.fullmatch(r"(\s+)(\w+): ([^\r\n]*)(\r?\n)?", old[i + position])
                b = re.fullmatch(r"(\s+)(\w+): ([^\r\n]*)(\r?\n)?", new[k + position])
                if not a or not b or (a[1], a[2]) != (b[1], b[2]) or a[4] != b[4] or a[2] not in scalar_names or not scopes[i + position]:
                    covered = False
                    break
                property_path = scalar_names[a[2]]
                matches = [item for item in diffs if item.get("object_type") == "RELATIONSHIP" and item["object_id"].endswith("relationship:" + scopes[i + position]) and item["property_path"] == property_path]
                if len(matches) != 1:
                    covered = False
                    break
                difference = matches[0]
                if property_path in {"from_column_id", "to_column_id"}:
                    before_style = endpoint_text(a[3], difference["previous_value"])
                    after_style = endpoint_text(b[3], difference["new_value"])
                    exact_values = before_style is not None and before_style == after_style
                else:
                    def scalar_text(value):
                        return str(value).lower() if type(value) is bool else str(value)
                    exact_values = a[3] == scalar_text(difference["previous_value"]) and b[3] == scalar_text(difference["new_value"])
                if not exact_values:
                    covered = False
                    break
                difference.update(source_file=relative, source_location={"before_line": i + position + 1, "after_line": k + position + 1})
        if not covered:
            unknown.append({**change, "classification": "UNKNOWN_DIFFERENCE", "reason": "Unaccounted raw source edit"})
    return unknown


def compare_snapshots(before: Snapshot | Mapping[str, Any], after: Snapshot | Mapping[str, Any], *,
                      before_root: str | Path | None = None, after_root: str | Path | None = None) -> dict[str, Any]:
    a = before.to_dict() if isinstance(before, Snapshot) else dict(before)
    b = after.to_dict() if isinstance(after, Snapshot) else dict(after)
    objects_a = a.get("analysis", {}).get("objects", {})
    objects_b = b.get("analysis", {}).get("objects", {})
    differences = [item for key in sorted(set(objects_a) | set(objects_b)) for item in compare_objects(objects_a.get(key), objects_b.get(key))]
    if a.get("identity_manifest") != b.get("identity_manifest"):
        differences.append({"object_id": "$identity", "object_type": "IDENTITY", "property_path": "identity_manifest", "previous_value": a.get("identity_manifest"),
                            "new_value": b.get("identity_manifest"), "classification": "IDENTITY_CHANGED", "confidence": "EXACT"})
    source_changes = verify_source_coverage(a["source_manifest"], b["source_manifest"])
    unknown = _raw_coverage(Path(before_root), Path(after_root), source_changes, differences, b.get("analysis", {}).get("graph", {}), objects_b) if before_root and after_root else (
        [{**item, "classification": "UNKNOWN_DIFFERENCE", "reason": "Raw coverage verification not run"} for item in source_changes])
    if not objects_a or not objects_b or not a.get("analysis", {}).get("tabular_metadata") or not b.get("analysis", {}).get("tabular_metadata"):
        unknown.append({"classification": "UNKNOWN_DIFFERENCE", "reason": "Authoritative metadata missing"})
    graph_a = {item["id"]: item for item in a.get("analysis", {}).get("graph", {}).get("edges", [])}
    graph_b = {item["id"]: item for item in b.get("analysis", {}).get("graph", {}).get("edges", [])}
    graph_changes = [{"edge_id": key, "before": graph_a.get(key), "after": graph_b.get(key)} for key in sorted(set(graph_a) | set(graph_b)) if graph_a.get(key) != graph_b.get(key)]
    report = {"comparison_version": 1, "before_snapshot_id": a["snapshot_id"], "after_snapshot_id": b["snapshot_id"],
              "object_changes": differences, "property_changes": [item for item in differences if item["property_path"] != "$object"],
              "reference_changes": [item for item in differences if item["classification"] == "REFERENCE_CHANGED"], "source_changes": source_changes,
              "graph_changes": graph_changes, "unknown_differences": unknown,
              "completeness": {"status": "COMPLETE" if not unknown else "INCOMPLETE", "normalization_policy": "exact-properties-v1",
                               "permitted_normalizations": ["JSON object-key ordering", "JSON insignificant whitespace", "JSON UTF-8 BOM"], "raw_coverage_verified": not unknown}}
    report["comparison_id"] = content_hash(report)
    return report
