"""Deterministic Markdown export of one canonical Brain snapshot."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from backend.graph.repository import GraphRepository
from backend.graph.schema import Edge, Node


UNKNOWN = "Unknown (not provided)"
_DAX_EXPRESSION_TYPES = frozenset(
    {"CALCULATION_ITEM", "COLUMN", "FIELD_PARAMETER", "MEASURE", "TABLE", "USER_DEFINED_FUNCTION"}
)
_LINEAGE_TYPES = frozenset(
    {
        "ACTIVATES_RELATIONSHIP",
        "CONTROLLED_BY",
        "DEFAULTS_TO",
        "DEPENDS_ON",
        "FILTERS",
        "HAS_OPTION",
        "MODIFIES_FILTER",
        "MODIFIES_RELATIONSHIP",
        "REFERENCES",
        "RELATES_TO",
        "USES",
        "USES_MODEL",
    }
)


class UnsafeExportPathError(ValueError):
    """The requested output could alter project inputs or state."""


def _safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _safe(value[key]) for key in sorted(value, key=lambda item: str(item))}
    if isinstance(value, (list, tuple)):
        return [_safe(item) for item in value]
    if isinstance(value, (set, frozenset)):
        values = [_safe(item) for item in value]
        return sorted(values, key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True, default=str))
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return _safe(to_dict())
    return str(value)


def _json(value: Any) -> str:
    return json.dumps(_safe(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def snapshot_content_identity(repository: GraphRepository) -> str:
    """Hash the canonical graph content, independent of runtime scan metadata."""

    payload = {
        "nodes": [node.to_dict() for node in repository.all_nodes()],
        "edges": [edge.to_dict() for edge in repository.all_edges()],
    }
    return "sha256:" + hashlib.sha256(_json(payload).encode("utf-8")).hexdigest()


def _inline(value: Any, *, unknown: str = UNKNOWN) -> str:
    if value is None or value == "":
        return unknown
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\n", "\\n")
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    delimiter = "`" * max(1, longest + 1)
    padding = " " if text.startswith("`") or text.endswith("`") else ""
    return f"{delimiter}{padding}{text}{padding}{delimiter}"


def _cell(value: Any, *, unknown: str = UNKNOWN) -> str:
    if value is None or value == "":
        return unknown
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("\n", "<br>")


def _table(headers: Sequence[str], rows: Iterable[Sequence[Any]]) -> list[str]:
    result = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    result.extend("| " + " | ".join(_cell(value) for value in row) + " |" for row in rows)
    return result


def _fenced(value: str, language: str = "") -> list[str]:
    longest = max((len(run) for run in re.findall(r"`+", value)), default=0)
    fence = "`" * max(3, longest + 1)
    return [f"{fence}{language}", value, fence]


def _properties(node: Node) -> Mapping[str, Any]:
    return node.properties if isinstance(node.properties, Mapping) else {}


def _source_path(node: Node) -> Any:
    properties = _properties(node)
    raw = properties.get("raw_source")
    if isinstance(raw, Mapping):
        return (
            properties.get("source_path")
            or properties.get("sourcePath")
            or raw.get("source_path")
            or raw.get("sourcePath")
        )
    return properties.get("source_path") or properties.get("sourcePath")


def _label(node_id: Any, nodes: Mapping[str, Node]) -> str:
    if node_id is None or node_id == "":
        return UNKNOWN
    identifier = str(node_id)
    node = nodes.get(identifier)
    return f"{node.name or UNKNOWN} [{identifier}]" if node else f"{identifier} [not present in snapshot]"


def _expression_language(node: Node, label: str) -> str:
    properties = _properties(node)
    raw = properties.get("raw_source")
    raw = raw if isinstance(raw, Mapping) else {}
    declared = (
        properties.get("expression_language")
        or properties.get("language")
        or raw.get("expression_language")
        or raw.get("expressionLanguage")
        or raw.get("language")
        or raw.get("kind")
    )
    if declared:
        return str(declared)
    if label == "Format string expression" or node.type in _DAX_EXPRESSION_TYPES:
        return "DAX"
    return UNKNOWN


def _expression_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return "\n".join(str(item) for item in value)
    return str(value)


def _expression_items(node: Node) -> list[tuple[str, str]]:
    properties = _properties(node)
    raw = properties.get("raw_source")
    sources = (properties, raw if isinstance(raw, Mapping) else {})
    groups = (
        ("Expression", ("expression", "formula", "dax", "expressionText", "code")),
        (
            "Format string expression",
            ("format_expression", "formatExpression", "formatStringExpression", "format_string_expression"),
        ),
    )
    items: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for label, keys in groups:
        for source in sources:
            for key in keys:
                text = _expression_text(source.get(key))
                marker = (label, text or "")
                if text is not None and marker not in seen:
                    seen.add(marker)
                    items.append((label, text))
    return items


def _diagnostics(repository: GraphRepository) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for node in repository.all_nodes():
        raw = _properties(node).get("dax_diagnostics", [])
        values = raw if isinstance(raw, (list, tuple)) else [raw]
        for diagnostic in values:
            if diagnostic in (None, "", [], {}):
                continue
            code = diagnostic.get("code") if isinstance(diagnostic, Mapping) else None
            items.append(
                {
                    "object_id": node.id,
                    "code": str(code) if code else UNKNOWN,
                    "evidence": diagnostic,
                }
            )
    return sorted(items, key=lambda item: (item["object_id"], item["code"], _json(item["evidence"])))


def _root_counts(nodes: Sequence[Node], root_id: str, *, model: bool) -> Counter[str]:
    if model:
        return Counter(node.type for node in nodes if node.model_id == root_id)
    return Counter(node.type for node in nodes if node.report_id == root_id)


def _unresolved(repository: GraphRepository) -> list[dict[str, Any]]:
    nodes = {node.id: node for node in repository.all_nodes()}
    items: list[dict[str, Any]] = []
    for node in nodes.values():
        properties = _properties(node)
        if node.type == "REPORT" and (not node.model_id or node.model_id not in nodes):
            items.append(
                {
                    "object_id": node.id,
                    "kind": "report model binding",
                    "evidence": {"model_id": node.model_id, "model_ref": properties.get("model_ref")},
                }
            )
        if node.type == "RELATIONSHIP":
            for side in ("from", "to"):
                if not properties.get(f"{side}_column_id"):
                    items.append(
                        {
                            "object_id": node.id,
                            "kind": f"relationship {side} endpoint",
                            "evidence": properties.get(f"{side}_ref"),
                        }
                    )
        if node.type == "VISUAL":
            raw = properties.get("unresolved_field_refs", [])
            values = raw if isinstance(raw, (list, tuple)) else [raw]
            for value in values:
                if value not in (None, "", [], {}):
                    items.append({"object_id": node.id, "kind": "visual field binding", "evidence": value})
        if node.type in {"VISUAL_FILTER", "PAGE_FILTER", "REPORT_FILTER"}:
            value = properties.get("unresolved_target")
            if value is not None or (properties.get("target_ref") is not None and not properties.get("target_id")):
                items.append(
                    {
                        "object_id": node.id,
                        "kind": "filter target binding",
                        "evidence": value if value is not None else properties.get("target_ref"),
                    }
                )
        if node.type == "FIELD_PARAMETER":
            entries = properties.get("entries", [])
            if isinstance(entries, (list, tuple)):
                for entry in entries:
                    if isinstance(entry, Mapping) and not entry.get("resolved_id"):
                        items.append({"object_id": node.id, "kind": "field parameter entry", "evidence": entry})
    for diagnostic in _diagnostics(repository):
        code = diagnostic["code"].casefold()
        if any(marker in code for marker in ("unresolved", "ambiguous", "missing")):
            items.append(
                {
                    "object_id": diagnostic["object_id"],
                    "kind": f"DAX diagnostic: {diagnostic['code']}",
                    "evidence": diagnostic["evidence"],
                }
            )
    return sorted(items, key=lambda item: (item["object_id"], item["kind"], _json(item["evidence"])))


def render_markdown(repository: GraphRepository, *, project_name: str = "PBIBrain") -> str:
    """Render a read-only, deterministic Markdown view of the loaded graph."""

    all_nodes = repository.all_nodes()
    all_edges = repository.all_edges()
    nodes = {node.id: node for node in all_nodes}
    models = [node for node in all_nodes if node.type == "MODEL"]
    reports = [node for node in all_nodes if node.type == "REPORT"]
    last_scan = next(
        (getattr(repository, name, None) for name in ("last_scan", "scan_timestamp", "last_scan_at") if getattr(repository, name, None)),
        None,
    )
    validation_state = getattr(repository, "validation_state", None) or "not_run"
    lines: list[str] = [
        "# PBIBrain documentation export",
        "",
        "This is a canonical, read-only metadata snapshot. Source expressions and descriptions are reproduced as evidence; they are not verified business facts. Review overrides are not applied.",
        "",
        "## Snapshot identity",
        "",
    ]
    lines.extend(
        _table(
            ("Field", "Value"),
            (
                ("Project", project_name),
                ("Content identity", snapshot_content_identity(repository)),
                ("Persisted scan identifier", "Unknown (not stored)"),
                ("Last scan time", last_scan or "Unknown (not available in this repository session)"),
                ("Validation state", validation_state),
                ("Repository storage", repository.storage),
                ("Models", len(models)),
                ("Reports", len(reports)),
                ("Nodes", len(all_nodes)),
                ("Edges", len(all_edges)),
            ),
        )
    )

    lines.extend(["", "## Semantic model inventory", ""])
    model_rows: list[Sequence[Any]] = []
    for model in models:
        counts = _root_counts(all_nodes, model.id, model=True)
        model_rows.append(
            (
                model.id,
                model.name or UNKNOWN,
                model.source_id or UNKNOWN,
                model.source or UNKNOWN,
                _source_path(model) or UNKNOWN,
                counts["TABLE"],
                counts["MEASURE"],
                counts["RELATIONSHIP"],
            )
        )
    lines.extend(
        _table(
            ("Canonical ID", "Name", "Source ID", "Evidence source", "Source path", "Tables", "Measures", "Relationships"),
            model_rows,
        )
        if model_rows
        else ["No semantic models recorded in the canonical snapshot."]
    )

    lines.extend(["", "## Report inventory", ""])
    report_rows: list[Sequence[Any]] = []
    for report in reports:
        counts = _root_counts(all_nodes, report.id, model=False)
        binding = "Resolved in snapshot" if report.model_id in nodes and nodes[report.model_id].type == "MODEL" else "Not resolved in snapshot"
        report_rows.append(
            (
                report.id,
                report.name or UNKNOWN,
                report.source_id or UNKNOWN,
                report.model_id or UNKNOWN,
                binding,
                _source_path(report) or UNKNOWN,
                counts["PAGE"],
                counts["VISUAL"],
            )
        )
    lines.extend(
        _table(
            ("Canonical ID", "Name", "Source ID", "Model ID", "Model binding", "Source path", "Pages", "Visuals"),
            report_rows,
        )
        if report_rows
        else ["No reports recorded in the canonical snapshot."]
    )

    lines.extend(["", "## Stored expressions (exact)", ""])
    expressions = [(node, _expression_items(node)) for node in all_nodes]
    expressions = [(node, items) for node, items in expressions if items]
    if not expressions:
        lines.append("No expressions recorded in the canonical snapshot.")
    for node, items in expressions:
        table_id = _properties(node).get("table_id") or _properties(node).get("calculation_group_id")
        description = node.description
        lines.extend(
            [
                f"### {_inline(node.name or UNKNOWN)} ({_inline(node.id)})",
                "",
                f"- Object type: {_inline(node.type)}",
                f"- Model ID: {_inline(node.model_id)}",
                f"- Parent table or group: {_inline(_label(table_id, nodes))}",
                f"- Source ID: {_inline(node.source_id)}",
                f"- Evidence source: {_inline(node.source)}",
                f"- Source description: {_inline(description, unknown=UNKNOWN)}",
                "",
            ]
        )
        for label, expression in items:
            language = _expression_language(node, label)
            lines.extend(
                [
                    f"#### {label}",
                    "",
                    f"Declared language: {_inline(language)}",
                    "",
                    *_fenced(expression, "dax" if language.casefold() == "dax" else ""),
                    "",
                ]
            )

    lines.extend(["## Relationships", ""])
    relationship_rows: list[Sequence[Any]] = []
    for relationship in (node for node in all_nodes if node.type == "RELATIONSHIP"):
        properties = _properties(relationship)
        relationship_rows.append(
            (
                relationship.model_id or UNKNOWN,
                relationship.id,
                relationship.name or UNKNOWN,
                _label(properties.get("from_column_id"), nodes),
                _label(properties.get("to_column_id"), nodes),
                properties.get("cardinality") or UNKNOWN,
                properties.get("cross_filter_direction") or UNKNOWN,
                properties.get("active") if properties.get("active") is not None else UNKNOWN,
                relationship.source or UNKNOWN,
            )
        )
    lines.extend(
        _table(
            ("Model ID", "Relationship ID", "Name", "From", "To", "Cardinality", "Cross-filter", "Active", "Evidence source"),
            relationship_rows,
        )
        if relationship_rows
        else ["No relationships recorded in the canonical snapshot."]
    )

    lines.extend(["", "## Report structure", ""])
    report_objects = [node for node in all_nodes if node.type in {"PAGE", "VISUAL", "VISUAL_FILTER", "PAGE_FILTER", "REPORT_FILTER"}]
    structure_rows: list[Sequence[Any]] = []
    for node in report_objects:
        properties = _properties(node)
        parent_id = properties.get("parent_id")
        resolved = properties.get("field_ids") if node.type == "VISUAL" else properties.get("target_id")
        unresolved = properties.get("unresolved_field_refs") if node.type == "VISUAL" else properties.get("unresolved_target")
        structure_rows.append(
            (
                node.report_id or UNKNOWN,
                node.model_id or UNKNOWN,
                node.type,
                node.id,
                node.name or UNKNOWN,
                parent_id or UNKNOWN,
                _json(resolved) if resolved not in (None, [], {}) else UNKNOWN,
                _json(unresolved) if unresolved not in (None, [], {}) else "None recorded",
                node.source or UNKNOWN,
            )
        )
    lines.extend(
        _table(
            ("Report ID", "Model ID", "Type", "Canonical ID", "Name", "Parent ID", "Resolved binding IDs", "Unresolved binding evidence", "Evidence source"),
            structure_rows,
        )
        if structure_rows
        else ["No report pages, visuals, or filters recorded in the canonical snapshot."]
    )

    lines.extend(["", "## Lineage and usage evidence", ""])
    lineage = [edge for edge in all_edges if edge.type in _LINEAGE_TYPES]
    lineage_rows = [
        (
            edge.type,
            edge.id,
            _label(edge.from_id, nodes),
            _label(edge.to_id, nodes),
            edge.evidence_class,
            edge.status,
            edge.source,
            _json(edge.evidence) if edge.evidence else "None recorded",
        )
        for edge in lineage
    ]
    lines.extend(
        _table(
            ("Edge type", "Edge ID", "From", "To", "Evidence class", "Status", "Evidence source", "Exact evidence"),
            lineage_rows,
        )
        if lineage_rows
        else ["No lineage or usage edges recorded in the canonical snapshot."]
    )

    lines.extend(["", "## Unresolved bindings", ""])
    unresolved = _unresolved(repository)
    if unresolved:
        lines.extend(
            _table(
                ("Object ID", "Binding kind", "Exact evidence"),
                ((item["object_id"], item["kind"], _json(item["evidence"])) for item in unresolved),
            )
        )
    else:
        lines.append("None recorded in the canonical snapshot.")

    lines.extend(["", "## Diagnostics and limitations", ""])
    diagnostics = _diagnostics(repository)
    if diagnostics:
        lines.extend(
            _table(
                ("Object ID", "Diagnostic code", "Exact evidence"),
                ((item["object_id"], item["code"], _json(item["evidence"])) for item in diagnostics),
            )
        )
    else:
        lines.append("No DAX diagnostics are persisted on canonical objects in this snapshot.")
    lines.extend(
        [
            "",
            "Runtime-only validation details and scan diagnostics that were not persisted on canonical objects are unavailable in this export.",
        ]
    )

    lines.extend(["", "## Canonical source evidence", ""])
    source_rows = [
        (
            node.id,
            node.type,
            node.model_id or UNKNOWN,
            node.report_id or UNKNOWN,
            node.source_id or UNKNOWN,
            node.source or UNKNOWN,
            _source_path(node) or UNKNOWN,
            node.status,
        )
        for node in all_nodes
    ]
    lines.extend(
        _table(
            ("Canonical ID", "Type", "Model ID", "Report ID", "Source ID", "Evidence source", "Source path", "Status"),
            source_rows,
        )
        if source_rows
        else ["No canonical objects recorded in the snapshot."]
    )
    lines.extend(["", "### Canonical edge evidence", ""])
    edge_rows = [
        (
            edge.id,
            edge.type,
            edge.from_id,
            edge.to_id,
            edge.evidence_class,
            edge.status,
            edge.source,
            _json(edge.evidence) if edge.evidence else "None recorded",
        )
        for edge in all_edges
    ]
    lines.extend(
        _table(
            ("Edge ID", "Type", "From ID", "To ID", "Evidence class", "Status", "Evidence source", "Exact evidence"),
            edge_rows,
        )
        if edge_rows
        else ["No canonical edges recorded in the snapshot."]
    )
    return "\n".join(lines).rstrip() + "\n"


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _pbip_artifact_roots(source: Path) -> list[Path]:
    if source.suffix.casefold() != ".pbip" or not source.is_file():
        return []
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        payload = {}
    roots: list[Path] = []
    artifacts = payload.get("artifacts", []) if isinstance(payload, Mapping) else []
    if isinstance(artifacts, list):
        for artifact in artifacts:
            if not isinstance(artifact, Mapping):
                continue
            candidates: list[Any] = [artifact.get("path")]
            for key in ("semanticModel", "semantic_model", "model", "report"):
                value = artifact.get(key)
                if isinstance(value, Mapping):
                    candidates.append(value.get("path"))
            for value in candidates:
                if isinstance(value, str) and value.strip():
                    root = (source.parent / value).resolve()
                    if root not in roots:
                        roots.append(root)
    for sibling in source.parent.iterdir():
        if sibling.is_dir() and sibling.suffix.casefold() in {".semanticmodel", ".dataset", ".report"}:
            resolved = sibling.resolve()
            if resolved not in roots:
                roots.append(resolved)
    return roots


def validate_output_path(
    output: str | Path,
    *,
    config_path: str | Path,
    database_paths: Iterable[str | Path],
    identity_paths: Iterable[str | Path],
    source_paths: Iterable[str | Path],
) -> Path:
    """Reject output paths that overlap project configuration, state, or inputs."""

    target = Path(output).resolve()
    config = Path(config_path).resolve()
    databases = [Path(value).resolve() for value in database_paths]
    identities = [Path(value).resolve() for value in identity_paths]
    protected_files = {config, *(path for identity in identities for path in (identity, identity.with_name("overrides.json")))}
    if target in protected_files or any(target == database or _inside(target, database) for database in databases):
        raise UnsafeExportPathError(f"Export output is a protected project path: {target}")
    for value in source_paths:
        source = Path(value).resolve()
        if target == source or (source.is_dir() and _inside(target, source)):
            raise UnsafeExportPathError(f"Export output overlaps a configured source: {target}")
        for root in _pbip_artifact_roots(source):
            if target == root or _inside(target, root):
                raise UnsafeExportPathError(f"Export output overlaps a PBIP artifact: {target}")
    return target


def write_markdown(path: str | Path, content: str) -> Path:
    """Create a new UTF-8 Markdown file without replacing an existing path."""

    target = Path(path)
    with target.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(content)
    return target


__all__ = [
    "UnsafeExportPathError",
    "render_markdown",
    "snapshot_content_identity",
    "validate_output_path",
    "write_markdown",
]
