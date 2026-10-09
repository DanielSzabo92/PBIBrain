"""Isolated, authoritative metadata capture using PBIBrain's existing scanner."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from backend.adapters.tabular_metadata import TabularMetadataAdapter
from backend.adapters.tabular_metadata.validation import validate_tabular_structure
from backend.graph.repository import GraphRepository
from backend.scanner.pbip import read_pbip_project
from backend.scanner.pipeline import Scanner
from .manifest import SourceIntegrityError, source_manifest, safe_path, content_hash, OPAQUE_RESOURCE_SUFFIXES
from .safety import assert_no_credentials

ALIASES = {"dataType": "datatype", "isHidden": "hidden", "isActive": "active", "crossFilteringBehavior": "cross_filter_direction",
           "fromCardinality": "from_cardinality", "toCardinality": "to_cardinality", "securityFilteringBehavior": "security_filter_behavior",
           "formatString": "format_string", "displayFolder": "display_folder", "sortByColumn": "sort_by", "summarizeBy": "summarize_by",
           "sourceColumn": "source_column", "dataCategory": "data_category", "lineageTag": "lineage_tag"}
CHILD_COLLECTIONS = {"MODEL": {"tables", "relationships", "measures"}, "TABLE": {"columns", "measures"}, "REPORT": {"pages"}, "PAGE": {"visuals"}}
FACT_TYPES = {"MODEL", "TABLE", "COLUMN", "MEASURE", "RELATIONSHIP", "SHARED_EXPRESSION", "USER_DEFINED_FUNCTION", "CALCULATION_GROUP", "CALCULATION_ITEM", "FIELD_PARAMETER",
              "REPORT", "PAGE", "VISUAL", "VISUAL_CALCULATION", "VISUAL_FILTER", "PAGE_FILTER", "REPORT_FILTER"}


def validate_paths(root: Path, manifest: list[dict[str, Any]]) -> None:
    def walk(value: Any, source: str) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key.casefold() == "path" and isinstance(item, str):
                    # PBIR model references are relative to the report directory.
                    target = (root / source).parent / item
                    resolved = target.resolve()
                    if not resolved.is_relative_to(root.resolve()):
                        raise SourceIntegrityError("External artifact path")
                    safe_path(root, resolved.relative_to(root.resolve()).as_posix())
                    if not resolved.exists():
                        raise SourceIntegrityError("Missing referenced artifact")
                walk(item, source)
        elif isinstance(value, list):
            for item in value:
                walk(item, source)
    for record in manifest:
        if Path(record["path"]).suffix.casefold() in {".json", ".pbip", ".pbir", ".bim"} or Path(record["path"]).name == ".platform":
            walk(json.loads(safe_path(root, record["path"]).read_text(encoding="utf-8-sig")), record["path"])


def scan_snapshot(root: str | Path, *, identities: dict[str, Any] | None = None,
                  adapter: TabularMetadataAdapter | None = None) -> dict[str, Any]:
    root = Path(root).absolute()
    manifest = source_manifest(root)
    assert_no_credentials(root, manifest)
    validate_paths(root, manifest)
    adapter = adapter or TabularMetadataAdapter()
    projects = [item["path"] for item in manifest if item["path"].casefold().endswith(".pbip")]
    if len(projects) != 1:
        raise SourceIntegrityError("Guarded PBIP scan requires exactly one project file")
    bundle = read_pbip_project(safe_path(root, projects[0]))
    def relative_sources(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "source_path" and isinstance(item, str):
                    path = Path(item)
                    if path.is_absolute() and path.resolve().is_relative_to(root.resolve()):
                        value[key] = path.resolve().relative_to(root.resolve()).as_posix()
                elif isinstance(item, (dict, list)):
                    relative_sources(item)
        elif isinstance(value, list):
            for item in value:
                relative_sources(item)
    relative_sources(bundle["reports"])
    def report_filters(value: Any) -> None:
        if isinstance(value, dict):
            config = value.get("filterConfig")
            if isinstance(config, dict) and isinstance(config.get("filters"), list):
                # Schema-backed PBIR stores these separately from legacy filters.
                value["filters"] = deepcopy(config["filters"])
            for key in ("pages", "visuals"):
                for child in value.get(key, []):
                    report_filters(child)
    for report in bundle["reports"]:
        report_filters(report)
    models, metadata = [], {}
    for lightweight in bundle["models"]:
        directory = Path(lightweight["source_path"]).resolve()
        if not directory.is_relative_to(root.resolve()):
            raise SourceIntegrityError("External model source")
        relative = directory.relative_to(root.resolve()).as_posix()
        source = directory / "definition" if (directory / "definition").is_dir() else directory / "model.bim"
        authoritative = adapter.read(source)
        model = deepcopy(authoritative["database"]["model"])
        # Reuse existing PBIBrain source identities. TMDL relationship names
        # are source IDs; legacy BIM fallback IDs stay compatible.
        for relation in model.get("relationships", []):
            previous = [item for item in lightweight.get("relationships", []) if item.get("id") == relation.get("name") or item.get("name") == relation.get("name")]
            if len(previous) == 1 and previous[0].get("id"):
                relation["id"] = previous[0]["id"]
        model.update(id=lightweight["id"], name=lightweight["name"], source_path=relative)
        metadata[relative] = authoritative
        models.append(model)
    with TemporaryDirectory(prefix="pbibrain-snapshot-") as temporary:
        identity = Path(temporary) / "identity.json"
        identity.write_text(json.dumps(identities or {"version": 1, "mappings": {}}), encoding="utf-8")
        with GraphRepository(use_native=False) as repository:
            scanner = Scanner(repository, identity_path=identity)
            graph = scanner.scan(models, bundle["reports"])
            tabular_validation, topology_unknowns = validate_tabular_structure(metadata)
            scanner.last_validation.extend(tabular_validation)
            validation = scanner.last_validation.to_dict()
            objects = {}
            for node in graph.nodes:
                if node.type not in FACT_TYPES or node.source not in {"model_metadata", "report_metadata"}:
                    continue
                raw = deepcopy(node.properties.get("raw_source", {}))
                for key in CHILD_COLLECTIONS.get(node.type, set()) | {"source_path", "id"}:
                    raw.pop(key, None)
                prop = {ALIASES.get(key, key): value for key, value in raw.items()}
                prop.setdefault("name", node.name)
                if node.type == "RELATIONSHIP":
                    for key in ("fromTable", "toTable", "fromColumn", "toColumn", "from_column", "to_column"):
                        prop.pop(key, None)
                    for key in ("from_column_id", "to_column_id"):
                        prop[key] = node.properties.get(key)
                objects[node.id] = {"object_id": node.id, "object_type": node.type, "properties": prop,
                                    "source_file": node.properties.get("source_path"), "source_location": None,
                                    "provenance": "TOM+PBIBrain" if node.source == "model_metadata" else "PBIR+PBIBrain",
                                    "identity_authoritative": bool(raw.get("lineageTag") or (node.type == "RELATIONSHIP" and node.properties.get("raw_source", {}).get("id")) or node.type in {"REPORT", "PAGE", "VISUAL"}),
                                    "content_hash": content_hash(prop)}
            documents = {}
            for entry in manifest:
                path = safe_path(root, entry["path"])
                if path.suffix.casefold() in {".json", ".pbir", ".pbip"} or path.name == ".platform":
                    documents[entry["path"]] = json.loads(path.read_text(encoding="utf-8-sig"))
            # Full structured PBIR content is the comparison authority. The
            # lightweight usage graph remains separate and cannot hide fields.
            for relative, document in documents.items():
                path = Path(relative)
                kind = {"visual.json": "VISUAL", "page.json": "PAGE", "report.json": "REPORT"}.get(path.name)
                if not kind or not isinstance(document, dict):
                    continue
                matching = [node for node in graph.nodes if node.type == kind and
                            (kind == "REPORT" or str(node.source_id) == str(document.get("name"))) and
                            any(str(part).casefold().endswith(".report") for part in path.parts)]
                # Bind to owning report root to disambiguate repeated IDs.
                owners = [node.id for node in graph.nodes if node.type == "REPORT" and node.properties.get("raw_source", {}).get("source_path") == path.parts[0]]
                matching = [node for node in matching if node.id in owners or node.report_id in owners]
                if len(matching) != 1:
                    continue
                node = matching[0]
                objects[node.id].update(properties=deepcopy(document), source_file=relative, content_hash=content_hash(document), provenance="PBIR_STRUCTURED_JSON")
            blocking = ["DIAGNOSTIC:" + str(item.get("code", item.get("message", "unknown"))) for item in graph.diagnostics]
            blocking.extend("VALIDATION:" + item["code"] for item in validation["issues"] if item["severity"] in {"BLOCKING", "ERROR"})
            from backend.adapters.pbir import validate_report_documents
            report_validation = validate_report_documents(documents)
            if bundle["reports"]:
                blocking.extend(item["code"] + ":" + item["source_file"] for item in report_validation["issues"])
                if report_validation["issues"]:
                    validation["valid"] = False
                    validation["issues"].extend({"code": item["code"], "severity": "ERROR", "category": "source_integrity", "message": "Report structure or extraction coverage could not be verified", "source_file": item["source_file"]} for item in report_validation["issues"])
            if any(str(model.get("id", "")).startswith("pbip-model-") for model in bundle["models"]):
                blocking.append("SOURCE_MODEL_ID_DEPENDS_ON_WORKSPACE_PATH")
            for node in graph.nodes:
                if node.properties.get("unresolved_bindings"):
                    blocking.append("UNRESOLVED_REPORT_BINDING:" + node.id)
            supported = {"tables", "relationships", "measures", "expressions", "functions", "calculationGroups", "culture", "name", "id", "lineageTag", "source_path", "annotations",
                         "defaultPowerBIDataSourceVersion", "discourageImplicitMeasures", "dataAccessOptions"}
            unknown_properties = sorted({key for model in models for key in model if key not in supported})
            unsupported_structures = []
            for model in models:
                for table in model.get("tables", []):
                    if table.get("calculationGroup"):
                        unsupported_structures.append("CALCULATION_GROUP_EXTRACTION:" + str(table.get("name")))
                    for partition in table.get("partitions", []):
                        if partition.get("source", {}).get("type") == "calculated":
                            from .literal_tables import literal_table
                            literal = literal_table(partition["source"].get("expression", ""))
                            if not literal or set(literal["columns"]) != {column.get("name") for column in table.get("columns", [])}:
                                unsupported_structures.append("CALCULATED_TABLE_DEPENDENCIES:" + str(table.get("name")))
                if model.get("roles"):
                    unsupported_structures.append("RLS_OLS_RUNTIME_VERIFICATION_REQUIRED")
            blocking.extend(unsupported_structures)
            blocking.extend(topology_unknowns)
            if unknown_properties:
                blocking.append("IMPACT_METADATA_COVERAGE_INCOMPLETE")
            return {"objects": objects, "graph": graph.to_dict(), "documents": documents, "tabular_metadata": metadata,
                    "model_ids": sorted(node.id for node in graph.nodes if node.type == "MODEL"),
                    "report_ids": sorted(node.id for node in graph.nodes if node.type == "REPORT"),
                    "identity_manifest": json.loads(identity.read_text(encoding="utf-8")), "validation": validation, "report_validation": report_validation,
                    "validation_status": "PASSED" if validation["valid"] else "FAILED",
                    "completeness": {"status": "COMPLETE" if not blocking else "INCOMPLETE", "blocking": sorted(set(blocking)),
                                      "parsed_artifacts": len(manifest) - sum(Path(item["path"]).suffix.casefold() in OPAQUE_RESOURCE_SUFFIXES or Path(item["path"]).name in {".gitignore", ".gitattributes"} for item in manifest),
                                      "opaque_artifacts": [item["path"] for item in manifest if Path(item["path"]).suffix.casefold() in OPAQUE_RESOURCE_SUFFIXES],
                                      "source_files": len(manifest), "scan_scope": "FULL_PROJECT",
                                     "unknown_metadata_properties": unknown_properties, "unsupported_object_types": unsupported_structures, "unresolved_references": graph.diagnostics,
                                     "analysis_truncated": False, "scanner_errors": []}}
