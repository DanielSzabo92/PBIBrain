"""Durable configuration and all-at-once scanning for one Brain project."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from backend.graph.loader import FactGraph, build_fact_graph
from backend.graph.repository import GraphRepository
from backend.scanner.metadata_reader import load_metadata, pick, source_id
from backend.scanner.model_reader import ModelReader
from backend.scanner.normalization import StableIdentity
from backend.scanner.pbip import is_pbip_source, read_pbip_project
from backend.scanner.pipeline import Scanner
from backend.scanner.report_reader import ReportReader
from backend.sync import preserve_review_statuses


PROJECT_VERSION = 1
_CONFIG_KEYS = frozenset({"version", "name", "sources", "database", "identity_map", "graph_colors"})


class ProjectConfigError(ValueError):
    """The project file is malformed or internally inconsistent."""


class ProjectSourceError(ValueError):
    """A configured source cannot be read as Power BI metadata."""


class ProjectSourceCollisionError(ProjectSourceError):
    """Two source objects resolve to the same canonical graph identity."""


@dataclass(frozen=True, slots=True)
class ProjectScanResult:
    graph: FactGraph
    source_count: int
    model_count: int
    report_count: int
    scanned_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_count": self.source_count,
            "model_count": self.model_count,
            "report_count": self.report_count,
            "scanned_at": self.scanned_at,
            "node_count": len(self.graph.nodes),
            "edge_count": len(self.graph.edges),
        }


class ProjectConfigStore:
    """Read and atomically replace one small versioned project file."""

    def __init__(self, path: str | Path = "config/brain.json") -> None:
        self.path = Path(path).resolve()

    def get(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ProjectConfigError(f"Project configuration not found: {self.path}") from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise ProjectConfigError(f"Cannot read project configuration {self.path}: {exc}") from exc
        return self.validate(payload)

    load = get

    def save(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        config = self.validate(payload)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(config, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
        return config

    def validate(self, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, Mapping):
            raise ProjectConfigError("Project configuration must be a JSON object")
        unknown = sorted(str(key) for key in payload if key not in _CONFIG_KEYS)
        if unknown:
            raise ProjectConfigError(f"Unsupported project setting(s): {', '.join(unknown)}")
        version = payload.get("version", PROJECT_VERSION)
        if isinstance(version, bool) or version != PROJECT_VERSION:
            raise ProjectConfigError(f"Unsupported project version: {version!r}")
        name = _required_text(payload.get("name", "PBIBrain"), "name")
        database = _required_text(payload.get("database"), "database")
        identity_map = _required_text(payload.get("identity_map"), "identity_map")
        raw_sources = payload.get("sources", [])
        if not isinstance(raw_sources, list):
            raise ProjectConfigError("sources must be a JSON array of paths")
        sources = [_required_text(value, f"sources[{index}]") for index, value in enumerate(raw_sources)]
        _reject_duplicate_paths(sources, self.path.parent)
        config = {
            "version": PROJECT_VERSION,
            "name": name,
            "sources": sources,
            "database": database,
            "identity_map": identity_map,
        }
        _reject_path_aliases(config, self.path)
        if "graph_colors" in payload:
            config["graph_colors"] = _graph_colors(payload["graph_colors"])
        return config


def _graph_colors(value: Any) -> dict[str, dict[str, str]]:
    """Accept only hex colors, keeping optional presentation settings out of facts."""
    import re

    if not isinstance(value, Mapping) or set(value) - {"groups", "types"}:
        raise ProjectConfigError("graph_colors must contain groups and/or types")
    result = {}
    for section in ("groups", "types"):
        colors = value.get(section, {})
        if not isinstance(colors, Mapping) or len(colors) > 200:
            raise ProjectConfigError(f"graph_colors.{section} must be a color mapping")
        result[section] = {}
        for key, color in colors.items():
            valid_key = key in {"report", "model", "other"} if section == "groups" else isinstance(key, str) and re.fullmatch(r"[A-Z][A-Z0-9_]{0,79}", key)
            if not valid_key or not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
                raise ProjectConfigError(f"Invalid graph color: {section}.{key}")
            result[section][key] = color.lower()
    return result


class ProjectService:
    """Coordinate project configuration and one safe, combined graph scan."""

    def __init__(self, config_path: str | Path = "config/brain.json") -> None:
        self.config_store = ProjectConfigStore(config_path)

    @property
    def config_path(self) -> Path:
        return self.config_store.path

    def get_config(self) -> dict[str, Any]:
        return self.config_store.get()

    def save_config(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self.config_store.save(payload)

    def paths(self) -> dict[str, Path]:
        return _project_paths(self.get_config(), self.config_path.parent)

    def source_paths(self) -> list[Path]:
        config = self.get_config()
        return [_resolve_path(value, self.config_path.parent) for value in config["sources"]]

    def scan(self, repository: GraphRepository) -> ProjectScanResult:
        config = self.get_config()
        source_paths = [_resolve_path(value, self.config_path.parent) for value in config["sources"]]
        if not source_paths:
            raise ProjectConfigError("Project has no configured sources")

        project_paths = _project_paths(config, self.config_path.parent)
        return self._scan_paths(repository, source_paths, project_paths)

    def _scan_paths(
        self,
        repository: GraphRepository,
        source_paths: list[Path],
        project_paths: dict[str, Path],
    ) -> ProjectScanResult:
        """Scan one immutable configuration snapshot."""

        models: list[dict[str, Any]] = []
        reports: list[dict[str, Any]] = []
        for source_path in source_paths:
            source_models, source_reports = _read_project_source(source_path)
            models.extend(_stable_roots(source_models, source_path, "model"))
            reports.extend(_stable_roots(source_reports, source_path, "report"))
        if not models:
            raise ProjectSourceError("Project sources contain no semantic models")
        models = _deduplicate_roots(models, "model")
        reports = _deduplicate_roots(reports, "report")

        staged_identity = _temporary_identity(project_paths["identity_map"])
        try:
            identity = _CollisionCheckingIdentity(staged_identity)
            build_fact_graph(models, reports, identity=identity, analyze_dax=False)

            staging = GraphRepository(use_native=False)
            scanner = Scanner(
                staging,
                identity_path=staged_identity,
                overrides_path=project_paths["overrides"],
            )
            graph = scanner.scan(models, reports)
            previous_nodes = repository.all_nodes()
            previous_edges = repository.all_edges()
            preserve_review_statuses(graph.nodes, graph.edges, previous_nodes, previous_edges)

            identity_path = project_paths["identity_map"]
            previous_identity = identity_path.read_bytes() if identity_path.is_file() else None
            _publish_identity(staged_identity, identity_path)
            try:
                repository.replace(graph.nodes, graph.edges)
            except Exception as publish_error:
                try:
                    _restore_identity(identity_path, previous_identity)
                except Exception as restore_error:
                    raise RuntimeError(
                        f"Graph publication failed and identity rollback failed: {restore_error}"
                    ) from publish_error
                raise
            scanned_at = datetime.now(timezone.utc).isoformat()
            repository.last_scan = scanned_at
            if scanner.last_validation is not None:
                repository.set_validation_result(scanner.last_validation)
            return ProjectScanResult(
                graph=graph,
                source_count=len(source_paths),
                model_count=sum(node.type == "MODEL" for node in graph.nodes),
                report_count=sum(node.type == "REPORT" for node in graph.nodes),
                scanned_at=scanned_at,
            )
        finally:
            staged_identity.unlink(missing_ok=True)


def _project_paths(config: Mapping[str, Any], base: Path) -> dict[str, Path]:
    identity = _resolve_path(str(config["identity_map"]), base)
    return {
        "database": _resolve_path(str(config["database"]), base),
        "identity_map": identity,
        "overrides": identity.with_name("overrides.json"),
    }


class _CollisionCheckingIdentity(StableIdentity):
    def __init__(self, mapping_path: str | Path) -> None:
        super().__init__(mapping_path)
        self._owners: dict[str, str] = {}

    def object_id(
        self,
        object_type: str,
        source: Any = None,
        *,
        parent_id: str | None = None,
        fallback: str = "object",
    ) -> tuple[str, str]:
        object_id, token = super().object_id(
            object_type,
            source,
            parent_id=parent_id,
            fallback=fallback,
        )
        owner = f"{str(object_type).upper()} source {source!r} under {parent_id or 'project'}"
        previous = self._owners.get(object_id)
        if previous is not None:
            raise ProjectSourceCollisionError(
                f"Canonical identity collision for {object_id!r}: {previous}; {owner}"
            )
        self._owners[object_id] = owner
        return object_id, token


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProjectConfigError(f"{field} must be a non-empty path or name")
    return value.strip()


def _resolve_path(value: str, base: Path) -> Path:
    path = Path(value)
    return (path if path.is_absolute() else base / path).resolve()


def _path_key(value: str | Path, base: Path) -> str:
    return str(_resolve_path(str(value), base)).casefold()


def _reject_duplicate_paths(sources: list[str], base: Path) -> None:
    seen: dict[str, str] = {}
    for source in sources:
        key = _path_key(source, base)
        previous = seen.get(key)
        if previous is not None:
            raise ProjectConfigError(f"Duplicate project source path: {previous!r} and {source!r}")
        seen[key] = source


def _reject_path_aliases(config: Mapping[str, Any], config_path: Path) -> None:
    base = config_path.parent
    identity = _resolve_path(str(config["identity_map"]), base)
    writable = {
        "configuration": config_path.resolve(),
        "database": _resolve_path(str(config["database"]), base),
        "identity map": identity,
        "overrides": identity.with_name("overrides.json"),
    }
    by_path: dict[str, str] = {}
    for label, path in writable.items():
        key = str(path).casefold()
        previous = by_path.get(key)
        if previous is not None:
            raise ProjectConfigError(f"{label} path cannot also be the {previous} path: {path}")
        by_path[key] = label
    for source in config["sources"]:
        path = _resolve_path(str(source), base)
        label = by_path.get(str(path).casefold())
        if label is not None:
            raise ProjectConfigError(f"Source path cannot also be the {label} path: {path}")


def _read_project_source(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not path.is_file():
        raise ProjectSourceError(f"Project source not found: {path}")
    try:
        if is_pbip_source(path):
            bundle = read_pbip_project(path)
            return list(bundle["models"]), list(bundle["reports"])
        payload = load_metadata(path)
        if not isinstance(payload, Mapping):
            return ModelReader().read_many(payload), []
        has_models = any(pick(payload, key) is not None for key in ("models", "semanticModels", "semantic_models"))
        has_reports = pick(payload, "reports") is not None
        if has_models or has_reports:
            models = ModelReader().read_many(payload) if has_models else []
            reports = ReportReader().read_many(payload) if has_reports else []
            return models, reports
        if pick(payload, "report", "reportDefinition") is not None:
            return [], [ReportReader().read(payload)]
        return ModelReader().read_many(payload), []
    except ProjectSourceError:
        raise
    except Exception as exc:
        raise ProjectSourceError(f"Cannot read project source {path}: {exc}") from exc


def _stable_roots(values: list[dict[str, Any]], path: Path, kind: str) -> list[dict[str, Any]]:
    stable: list[dict[str, Any]] = []
    source_marker = str(path.resolve()).casefold()
    for index, value in enumerate(values):
        item = copy.deepcopy(value)
        if source_id(item) is None:
            digest = hashlib.sha256(f"{source_marker}|{kind}|{index}".encode("utf-8")).hexdigest()[:24]
            item["id"] = f"project-{digest}"
        stable.append(item)
    return stable


def _deduplicate_roots(values: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    seen: dict[str, str] = {}
    for value in values:
        identifier = source_id(value)
        assert identifier is not None
        key = str(identifier).casefold()
        payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
        previous = seen.get(key)
        if previous is None:
            seen[key] = payload
            unique.append(value)
            continue
        if previous != payload:
            raise ProjectSourceCollisionError(
                f"Conflicting {kind} definitions share canonical identity {kind}:{identifier}"
            )
    return unique


def _temporary_identity(identity_path: Path) -> Path:
    identity_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{identity_path.name}.", suffix=".tmp", dir=identity_path.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    if identity_path.is_file():
        temporary.write_bytes(identity_path.read_bytes())
    return temporary


def _publish_identity(staged: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    os.replace(staged, target)


def _restore_identity(target: Path, previous: bytes | None) -> None:
    if previous is None:
        target.unlink(missing_ok=True)
        return
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".rollback", dir=target.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(previous)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def load_project_config(path: str | Path = "config/brain.json") -> dict[str, Any]:
    return ProjectConfigStore(path).get()


def save_project_config(payload: Mapping[str, Any], path: str | Path = "config/brain.json") -> dict[str, Any]:
    return ProjectConfigStore(path).save(payload)


def scan_project(
    repository: GraphRepository,
    config_path: str | Path = "config/brain.json",
) -> ProjectScanResult:
    return ProjectService(config_path).scan(repository)


__all__ = [
    "PROJECT_VERSION",
    "ProjectConfigError",
    "ProjectConfigStore",
    "ProjectScanResult",
    "ProjectService",
    "ProjectSourceCollisionError",
    "ProjectSourceError",
    "load_project_config",
    "save_project_config",
    "scan_project",
]
