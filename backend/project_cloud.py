"""Cloud models and cloud reports as sources of a Brain project (issue #9).

``brain.json`` keeps local sources in ``sources`` (paths) and cloud items in
``cloud_sources``: one object for each cloud model (XMLA) or cloud report
(Fabric REST) with the workspace ID and name, the item ID, a display name and
the access type. The project never stores a token or an account name.

A scan reads each cloud item again with the Development Center ``CloudService``
(the same sign-in, TMDL export and report definition read) into
``<project config folder>/tmp/cloud/<item ID>/``. ``.pbibrain/.gitignore``
excludes ``tmp/``. When the live read is not possible (no sign-in, no network,
no permission, or no cloud service, as in the stand-alone agent), the scan uses
the last export in the cache. Without a cache, the item stays in the graph as a
root marked ``not_checked`` with the reason, so that a scan never fails because
of one cloud item.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import shutil
from typing import Any
from collections.abc import Mapping
import uuid

CLOUD_MODEL = "cloud_model"
CLOUD_REPORT = "cloud_report"
CLOUD_SOURCE_KINDS = (CLOUD_MODEL, CLOUD_REPORT)
ACCESS_TYPES = ("Read", "Read/Write")

STATUS_LIVE = "live"
STATUS_CACHED = "cached"
STATUS_NOT_CHECKED = "not_checked"

REASON_NO_CLOUD_SERVICE = "cloud_service_not_available"
REASON_SIGN_IN_REQUIRED = "sign_in_required"
REASON_READ_FAILED = "cloud_read_failed"
REASON_REPORT_NOT_READABLE = "report_not_readable"
REASON_MODEL_NOT_IN_PROJECT = "model_not_in_project"

NOT_CHECKED_TEXT = {
    REASON_NO_CLOUD_SERVICE: "not checked: the cloud item was not read (open the project in the app and sign in)",
    REASON_SIGN_IN_REQUIRED: "not checked: sign in with Microsoft to read the cloud item",
    REASON_READ_FAILED: "not checked: the Power BI service did not give the item",
    REASON_REPORT_NOT_READABLE: "not checked: report not readable",
    REASON_MODEL_NOT_IN_PROJECT: "not checked: the semantic model is not a source of this project",
}

_ENTRY_KEYS = frozenset({"kind", "workspace_id", "workspace_name", "item_id", "name", "dataset_id", "access_type"})
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_GUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


class CloudSourceConfigError(ValueError):
    """A ``cloud_sources`` entry is malformed."""


def validate_cloud_sources(value: Any) -> list[dict[str, Any]]:
    """Give the normalized ``cloud_sources`` list, or raise ``CloudSourceConfigError``."""

    if value is None:
        return []
    if not isinstance(value, list):
        raise CloudSourceConfigError("cloud_sources must be a JSON array of cloud items")
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(value):
        entry = validate_cloud_source(raw, index)
        key = entry["item_id"].casefold()
        if key in seen:
            raise CloudSourceConfigError(f"Duplicate cloud source: {entry['item_id']}")
        seen.add(key)
        entries.append(entry)
    return entries


def validate_cloud_source(raw: Any, index: int = 0) -> dict[str, Any]:
    where = f"cloud_sources[{index}]"
    if not isinstance(raw, Mapping):
        raise CloudSourceConfigError(f"{where} must be an object")
    unknown = sorted(str(key) for key in raw if key not in _ENTRY_KEYS)
    if unknown:
        raise CloudSourceConfigError(f"{where} has unsupported field(s): {', '.join(unknown)}")
    kind = raw.get("kind")
    if kind not in CLOUD_SOURCE_KINDS:
        raise CloudSourceConfigError(f"{where}.kind must be one of {', '.join(CLOUD_SOURCE_KINDS)}")
    entry: dict[str, Any] = {"kind": kind}
    for key in ("workspace_id", "item_id"):
        text = raw.get(key)
        if not isinstance(text, str) or not _ID.fullmatch(text.strip()):
            raise CloudSourceConfigError(f"{where}.{key} must be a cloud item ID")
        entry[key] = text.strip()
    workspace_name = raw.get("workspace_name")
    if not isinstance(workspace_name, str) or not workspace_name.strip() or len(workspace_name) > 256:
        raise CloudSourceConfigError(f"{where}.workspace_name must be a non-empty name")
    entry["workspace_name"] = workspace_name.strip()
    name = raw.get("name", entry["item_id"])
    if not isinstance(name, str) or not name.strip() or len(name) > 256:
        raise CloudSourceConfigError(f"{where}.name must be a non-empty name")
    entry["name"] = name.strip()
    dataset_id = raw.get("dataset_id")
    if kind == CLOUD_REPORT and dataset_id is not None:
        if not isinstance(dataset_id, str) or not _ID.fullmatch(dataset_id.strip()):
            raise CloudSourceConfigError(f"{where}.dataset_id must be a cloud item ID")
        entry["dataset_id"] = dataset_id.strip()
    elif dataset_id is not None:
        raise CloudSourceConfigError(f"{where}.dataset_id is only for a cloud report")
    access = raw.get("access_type", "Read")
    if access not in ACCESS_TYPES:
        raise CloudSourceConfigError(f"{where}.access_type must be Read or Read/Write")
    entry["access_type"] = access
    return entry


@dataclass(frozen=True)
class CloudFetch:
    """The result of one cloud read: the folder to scan (or None) and its state."""

    entry: Mapping[str, Any]
    folder: Path | None
    status: str
    reason: str | None = None

    def not_checked(self) -> dict[str, Any] | None:
        if self.reason is None:
            return None
        return {
            "kind": self.entry["kind"],
            "item_id": self.entry["item_id"],
            "name": self.entry["name"],
            "workspace_name": self.entry["workspace_name"],
            "status": self.status,
            "reason": self.reason,
            "text": NOT_CHECKED_TEXT.get(self.reason, "not checked"),
        }


class ProjectCloudReader:
    """Read the cloud items of a project into its cache, with a fallback to the last export."""

    def __init__(self, cache: Path, service: Any = None) -> None:
        self.cache = Path(cache)
        self.service = service

    def folder(self, entry: Mapping[str, Any]) -> Path:
        return self.cache / _safe_name(entry["item_id"])

    def fetch(self, entry: Mapping[str, Any]) -> CloudFetch:
        target = self.folder(entry)
        if self.service is None:
            return self._fallback(entry, target, REASON_NO_CLOUD_SERVICE)
        self.cache.mkdir(parents=True, exist_ok=True)
        staging = self.cache / f".{_safe_name(entry['item_id'])}.{uuid.uuid4().hex}.tmp"
        try:
            if entry["kind"] == CLOUD_MODEL:
                self.service.read_model(entry["workspace_name"], entry["item_id"], staging / "definition")
            else:
                self.service.report_to_folder(entry["workspace_id"], entry["item_id"], staging)
        except Exception as exc:  # A cloud item never fails the whole scan.
            _remove(staging)
            return self._fallback(entry, target, _reason(exc))
        _remove(target)
        os.replace(staging, target)
        return CloudFetch(entry, target, STATUS_LIVE)

    def _fallback(self, entry: Mapping[str, Any], target: Path, reason: str) -> CloudFetch:
        if target.is_dir() and any(target.iterdir()):
            return CloudFetch(entry, target, STATUS_CACHED, reason)
        return CloudFetch(entry, None, STATUS_NOT_CHECKED, reason)


def _reason(exc: BaseException) -> str:
    name = type(exc).__name__
    if name == "ReportNotReadable":
        return REASON_REPORT_NOT_READABLE
    details = getattr(exc, "details", None)
    if name == "SignInRequired" or (isinstance(details, Mapping) and details.get("reason") in {"sign_in_required", "interaction_required"}):
        return REASON_SIGN_IN_REQUIRED
    return REASON_READ_FAILED


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", value)


def _remove(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    elif path.exists():
        path.unlink(missing_ok=True)


# Report → model bindings ---------------------------------------------------------


def connection_keys(reference: Any) -> dict[str, str]:
    """Read a report's ``byConnection`` reference: semantic model ID, catalog name and workspace name.

    ``reference`` is the scanner's ``byConnection:<value>`` text, where the
    value is a ``semanticmodelid``, a ``pbiModelDatabaseName`` or a connection
    string such as ``Data Source=powerbi://api.powerbi.com/v1.0/myorg/Sales;Initial Catalog=Model``.
    """

    text = str(reference or "")
    if text.startswith("byConnection"):
        text = text[len("byConnection"):].lstrip(":")
    keys: dict[str, str] = {}
    if not text:
        return keys
    if "=" not in text:
        keys["model"] = text.strip()
        return keys
    for part in text.split(";"):
        name, _, value = part.partition("=")
        name, value = name.strip().casefold(), value.strip().strip('"')
        if not value:
            continue
        if name in {"semanticmodelid", "datasetid", "dataset id"}:
            keys["model"] = value
        elif name in {"initial catalog", "database"}:
            keys.setdefault("catalog", value)
        elif name == "data source" and value.casefold().startswith("powerbi://"):
            path = [item for item in value.split("/") if item]
            if len(path) >= 5:
                keys["workspace"] = path[-1]
    if "model" not in keys and "catalog" in keys and _GUID.fullmatch(keys["catalog"]):
        keys["model"] = keys["catalog"]
    return keys


def bind_reports(models: list[dict[str, Any]], reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Point each report at a scanned model, across the local/cloud boundary.

    A report whose model is not a project source gets a ``not_checked`` model
    root, so that the report still shows its binding. Gives the not-checked
    items of the scan.
    """

    by_id = {str(model.get("id")).casefold(): model for model in models if model.get("id") is not None}
    by_cloud = {str(model["cloud_source"]["item_id"]).casefold(): model for model in models if isinstance(model.get("cloud_source"), Mapping)}
    by_name: dict[str, list[dict[str, Any]]] = {}
    for model in models:
        by_name.setdefault(str(model.get("name") or "").casefold(), []).append(model)
        source_path = model.get("source_path")
        if source_path:
            p = Path(source_path)
            if p.stem and p.stem.casefold() not in by_name:
                by_name.setdefault(p.stem.casefold(), []).append(model)
            if p.name and p.name.casefold() not in by_name:
                by_name.setdefault(p.name.casefold(), []).append(model)
        if model.get("database_name"):
            db_name = str(model["database_name"]).casefold()
            if db_name not in by_name:
                by_name.setdefault(db_name, []).append(model)

    placeholders: dict[str, dict[str, Any]] = {}
    items: dict[str, dict[str, Any]] = {}
    for report in reports:
        cloud = report.get("cloud_source") if isinstance(report.get("cloud_source"), Mapping) else None
        reference = report.get("model_id")
        keys: dict[str, str] = {}
        if cloud is not None and cloud.get("dataset_id"):
            keys = {"model": str(cloud["dataset_id"])}
        elif isinstance(reference, str) and reference.startswith("byConnection"):
            keys = connection_keys(reference)
        elif isinstance(reference, str) and reference:
            if reference.casefold() in by_id:
                continue
            keys = {"path": reference}
        else:
            continue

        target = None
        if keys.get("model"):
            wanted = keys["model"].casefold()
            target = by_cloud.get(wanted) or by_id.get(wanted)
            if target is None:
                matches = by_name.get(wanted, [])
                if len(matches) == 1:
                    target = matches[0]
            if target is None and wanted in {"referencedobject", "model"}:
                # In Power BI Desktop, 'ReferencedObject' is the standard placeholder for a live/external connection.
                # If there is exactly one model in the project, bind to it.
                if len(models) == 1:
                    target = models[0]
        if target is None and keys.get("catalog"):
            matches = by_name.get(keys["catalog"].casefold(), [])
            if keys.get("workspace"):
                matches = [model for model in matches
                           if str((model.get("cloud_source") or {}).get("workspace_name") or "").casefold() == keys["workspace"].casefold()] or matches
            if len(matches) == 1:
                target = matches[0]
        if target is None and keys.get("path"):
            path_ref = Path(keys["path"])
            for m in models:
                m_path = m.get("source_path")
                if m_path:
                    try:
                        if Path(m_path).resolve() == path_ref.resolve():
                            target = m
                            break
                    except Exception:
                        pass
                    if path_ref.name.casefold() == Path(m_path).name.casefold() or path_ref.stem.casefold() == Path(m_path).stem.casefold():
                        target = m
                        break
            if target is None:
                stem_matches = by_name.get(path_ref.stem.casefold(), [])
                if len(stem_matches) == 1:
                    target = stem_matches[0]
            if target is None and len(models) == 1:
                target = models[0]

        if target is not None:
            report["model_id"] = target["id"]
            continue

        key = (keys.get("model") or keys.get("path") or "|".join(filter(None, (keys.get("workspace"), keys.get("catalog")))) or "unknown").casefold()
        placeholder = placeholders.get(key)
        if placeholder is None:
            name = keys.get("catalog") or keys.get("model") or (Path(keys["path"]).stem if keys.get("path") else "Semantic model")
            placeholder = {
                "id": f"not-checked-{_safe_name(key)}",
                "name": name,
                "check_status": STATUS_NOT_CHECKED,
                "not_checked_reason": REASON_MODEL_NOT_IN_PROJECT,
            }
            workspace = keys.get("workspace") or (cloud or {}).get("workspace_name")
            if workspace:
                placeholder["connection_workspace"] = workspace
            placeholders[key] = placeholder
            items[key] = {"kind": "model", "item_id": keys.get("model"), "name": name, "workspace_name": workspace,
                          "status": STATUS_NOT_CHECKED, "reason": REASON_MODEL_NOT_IN_PROJECT,
                          "text": NOT_CHECKED_TEXT[REASON_MODEL_NOT_IN_PROJECT], "reports": []}
        report["model_id"] = placeholder["id"]
        items[key]["reports"].append(str(report.get("name") or report.get("id")))
    models.extend(placeholders.values())
    return list(items.values())


__all__ = [
    "ACCESS_TYPES",
    "CLOUD_MODEL",
    "CLOUD_REPORT",
    "CLOUD_SOURCE_KINDS",
    "CloudFetch",
    "CloudSourceConfigError",
    "ProjectCloudReader",
    "STATUS_CACHED",
    "STATUS_LIVE",
    "STATUS_NOT_CHECKED",
    "bind_reports",
    "connection_keys",
    "validate_cloud_sources",
]
