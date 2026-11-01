"""Target kinds "Empty" and "Copy of <local source>" (technical design section 2.2)."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import uuid
from typing import Any

from backend.devcenter.errors import DevCenterError, not_allowed
from backend.devcenter.sources.kinds import LocalSource

_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/"
_INVALID_NAME_CHARACTERS = set('<>:"/\\|?*')


def _check_name(name: str) -> str:
    value = str(name).strip()
    if not value or value in {".", ".."} or any(ord(c) < 32 or c in _INVALID_NAME_CHARACTERS for c in value) or value.endswith((".", " ")):
        raise DevCenterError("invalid_payload", "The target name cannot be a file name.", {"reason": "invalid_name"})
    return value


def prepare_empty_folder(raw_path: str | Path) -> Path:
    """Make sure that the target folder does not exist or is empty."""

    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        raise DevCenterError("invalid_payload", "The target folder must be a full path from the picker.", {"reason": "relative_path"})
    path = path.resolve()
    if path.exists() and (not path.is_dir() or any(path.iterdir())):
        raise not_allowed("Select an empty folder for the new target.", "folder_not_empty")
    return path


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _tmdl_bytes(lines: list[str]) -> bytes:
    # TOM writes TMDL with CRLF line ends; the skeleton uses the same form.
    return "".join(line + "\r\n" for line in lines).encode("utf-8")


def _platform(kind: str, name: str) -> dict[str, Any]:
    return {
        "$schema": _SCHEMA + "gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {"type": kind, "displayName": name},
        "config": {"version": "2.0", "logicalId": str(uuid.uuid4())},
    }


def skeleton_files(name: str) -> dict[str, bytes]:
    """Give the files of a minimal PBIP: a TMDL model and an empty PBIR report bound byPath."""

    name = _check_name(name)
    model = f"{name}.SemanticModel"
    report = f"{name}.Report"
    report_schema = _SCHEMA + "item/report/definition/"
    return {
        f"{name}.pbip": _json_bytes({
            "$schema": _SCHEMA + "pbip/pbipProperties/1.0.0/schema.json",
            "version": "1.0",
            "artifacts": [{"report": {"path": report}}],
            "settings": {"enableAutoRecovery": True},
        }),
        f"{model}/.platform": _json_bytes(_platform("SemanticModel", name)),
        f"{model}/definition.pbism": _json_bytes({"version": "4.2", "settings": {}}),
        f"{model}/definition/database.tmdl": _tmdl_bytes(["database", "\tcompatibilityLevel: 1702", ""]),
        # A model property such as "culture" on a model with no tables fails the
        # round trip check of the bridge. Power BI Desktop adds the culture itself.
        f"{model}/definition/model.tmdl": _tmdl_bytes(["model Model", ""]),
        f"{report}/.platform": _json_bytes(_platform("Report", name)),
        f"{report}/definition.pbir": _json_bytes({
            "$schema": _SCHEMA + "item/report/definitionProperties/2.0.0/schema.json",
            "version": "4.0",
            "datasetReference": {"byPath": {"path": f"../{model}"}},
        }),
        f"{report}/definition/version.json": _json_bytes({
            "$schema": report_schema + "versionMetadata/1.0.0/schema.json",
            "version": "2.0.0",
        }),
        f"{report}/definition/report.json": _json_bytes({
            "$schema": report_schema + "report/3.3.0/schema.json",
            "themeCollection": {"baseTheme": {
                "name": "CY24SU10",
                "reportVersionAtImport": {"visual": "1.8.50", "report": "2.0.50", "page": "1.3.50"},
                "type": "SharedResources",
            }},
        }),
        f"{report}/definition/pages/pages.json": _json_bytes({
            "$schema": report_schema + "pagesMetadata/1.1.0/schema.json",
            "pageOrder": ["page1"],
            "activePageName": "page1",
        }),
        f"{report}/definition/pages/page1/page.json": _json_bytes({
            "$schema": report_schema + "page/2.1.0/schema.json",
            "name": "page1",
            "displayName": "Page 1",
            "displayOption": "FitToPage",
            "height": 720,
            "width": 1280,
        }),
    }


def write_empty_target(folder: Path, name: str) -> Path:
    """Write the skeleton into an empty folder and give the path of the new .pbip file."""

    files = skeleton_files(name)
    folder.mkdir(parents=True, exist_ok=True)
    try:
        for relative, data in files.items():
            path = folder / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    except BaseException:
        remove_children(folder)
        raise
    return folder / f"{_check_name(name)}.pbip"


def remove_children(folder: Path) -> None:
    for child in list(folder.iterdir()) if folder.is_dir() else []:
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
        else:
            child.unlink(missing_ok=True)


def copy_source(source: LocalSource, folder: Path) -> Path:
    """Copy the files of a local source into an empty folder. The original stays unchanged.

    Give the path that selects the copy (the .pbip file, or the model folder).
    """

    base = source.root.parent
    if any(not item.is_relative_to(base) for item in source.artifact_paths()):
        raise not_allowed("A part of this source is outside its folder. Copy the files yourself.", "artifact_outside")
    folder.mkdir(parents=True, exist_ok=True)
    try:
        for item in source.artifact_paths():
            relative = item.relative_to(base)
            destination = folder / relative
            if item.is_dir():
                shutil.copytree(item, destination, ignore=shutil.ignore_patterns(".pbi", ".pbibrain"))
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, destination)
    except BaseException:
        remove_children(folder)
        raise
    return folder / source.root.relative_to(base)
