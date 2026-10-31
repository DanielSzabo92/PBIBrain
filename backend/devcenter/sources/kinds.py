"""Local source kinds and write-target rules (technical design sections 2.1 and 2.2)."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from backend.devcenter.errors import DevCenterError, not_allowed

PBIP = "pbip"
TMDL_FOLDER = "tmdl_folder"
MODEL_BIM = "model_bim"
PBIR_REPORT = "pbir_report"
PBIR_LEGACY_REPORT = "pbir_legacy_report"
CLOUD_MODEL = "cloud_model"
CLOUD_REPORT = "cloud_report"
LOCAL_KINDS = (PBIP, TMDL_FOLDER, MODEL_BIM, PBIR_REPORT, PBIR_LEGACY_REPORT)
SOURCE_KINDS = LOCAL_KINDS + (CLOUD_MODEL, CLOUD_REPORT)

MODEL_TMDL = "tmdl"
MODEL_TMSL = "tmsl"
REPORT_PBIR = "pbir"
REPORT_PBIR_LEGACY = "pbir_legacy"

# The fixed refusal messages of technical design section 2.1.
MESSAGE_TMSL_TARGET = "Save as TMDL in Power BI Desktop first."
MESSAGE_PBIR_LEGACY_TARGET = "Convert to PBIR in Power BI Desktop first."
MESSAGE_PBIX = "Save as PBIP in Power BI Desktop."


@dataclass(frozen=True)
class LocalSource:
    """One local source, found from the path that the user selected."""

    kind: str
    root: Path
    display_name: str
    model_dir: Path | None
    model_format: str | None
    report_dir: Path | None
    report_format: str | None

    def artifact_paths(self) -> list[Path]:
        """Give the files and folders that belong to the source (for copy and fingerprint)."""

        paths: list[Path] = []
        if self.kind == PBIP:
            paths.append(self.root)
        for directory in (self.model_dir, self.report_dir):
            if directory is not None and directory not in paths:
                paths.append(directory)
        if self.kind == MODEL_BIM:
            paths = [self.root]
        return paths


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise DevCenterError("invalid_payload", f"The file {path.name} is not valid JSON.", {"reason": "invalid_json"}) from exc
    if not isinstance(value, dict):
        raise DevCenterError("invalid_payload", f"The file {path.name} is not a JSON object.", {"reason": "invalid_json"})
    return value


def _model_format(model_dir: Path) -> str | None:
    if (model_dir / "definition" / "model.tmdl").is_file():
        return MODEL_TMDL
    if (model_dir / "model.bim").is_file():
        return MODEL_TMSL
    return None


def _report_format(report_dir: Path) -> str | None:
    if (report_dir / "definition" / "report.json").is_file():
        return REPORT_PBIR
    if (report_dir / "report.json").is_file():
        return REPORT_PBIR_LEGACY
    return None


def _report_model_dir(report_dir: Path) -> Path | None:
    pbir = report_dir / "definition.pbir"
    if not pbir.is_file():
        return None
    reference = _read_json(pbir).get("datasetReference") or {}
    by_path = reference.get("byPath") if isinstance(reference, dict) else None
    if isinstance(by_path, dict) and isinstance(by_path.get("path"), str):
        candidate = (report_dir / by_path["path"]).resolve()
        return candidate if candidate.is_dir() else None
    return None


def _pbip(path: Path) -> LocalSource:
    payload = _read_json(path)
    model_dir: Path | None = None
    report_dir: Path | None = None
    for artifact in payload.get("artifacts") or []:
        if not isinstance(artifact, dict):
            continue
        for key, value in artifact.items():
            relative = value.get("path") if isinstance(value, dict) else None
            if not isinstance(relative, str):
                continue
            folder = (path.parent / relative).resolve()
            if key == "report" and folder.is_dir():
                report_dir = folder
            elif key in {"dataset", "semanticModel"} and folder.is_dir():
                model_dir = folder
    if model_dir is None and report_dir is not None:
        model_dir = _report_model_dir(report_dir)
    if model_dir is None:
        found = sorted(path.parent.glob(f"{path.stem}.SemanticModel"))
        model_dir = found[0].resolve() if found and found[0].is_dir() else None
    if model_dir is None and report_dir is None:
        raise DevCenterError("invalid_payload", "The PBIP file has no model and no report.", {"reason": "empty_pbip"})
    return LocalSource(
        kind=PBIP,
        root=path,
        display_name=path.stem,
        model_dir=model_dir,
        model_format=_model_format(model_dir) if model_dir else None,
        report_dir=report_dir,
        report_format=_report_format(report_dir) if report_dir else None,
    )


def _name(folder: Path) -> str:
    for suffix in (".SemanticModel", ".Report", ".Dataset"):
        if folder.name.endswith(suffix):
            return folder.name[: -len(suffix)]
    return folder.name


def detect_local_source(raw_path: str | Path) -> LocalSource:
    """Find the source kind of a path that the user selected, or refuse the path."""

    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        raise DevCenterError("invalid_payload", "The source path must be a full path from the picker.", {"reason": "relative_path"})
    path = path.resolve()
    if path.suffix.casefold() == ".pbix":
        raise not_allowed(MESSAGE_PBIX, "pbix")
    if not path.exists():
        raise DevCenterError("not_found", "The source does not exist.", {"reason": "missing"})
    if path.is_file():
        suffix = path.suffix.casefold()
        if suffix == ".pbip":
            return _pbip(path)
        if path.name.casefold() == "model.bim":
            return LocalSource(MODEL_BIM, path, _name(path.parent), path.parent, MODEL_TMSL, None, None)
        if path.name.casefold() == "definition.pbir":
            path = path.parent
        else:
            raise DevCenterError("invalid_payload", "The app cannot read this file kind.", {"reason": "unsupported_file"})
    if (path / "model.tmdl").is_file() and path.name == "definition":
        path = path.parent
    if (path / "definition" / "model.tmdl").is_file():
        return LocalSource(TMDL_FOLDER, path, _name(path), path, MODEL_TMDL, None, None)
    report_format = _report_format(path)
    if report_format is not None and (path / "definition.pbir").is_file():
        kind = PBIR_REPORT if report_format == REPORT_PBIR else PBIR_LEGACY_REPORT
        return LocalSource(kind, path, _name(path), None, None, path, report_format)
    if (path / "model.bim").is_file():
        return LocalSource(MODEL_BIM, path / "model.bim", _name(path), path, MODEL_TMSL, None, None)
    raise DevCenterError("invalid_payload", "The folder has no Power BI model and no Power BI report.", {"reason": "unsupported_folder"})


def require_model_target(source: LocalSource) -> None:
    if source.model_dir is None or source.model_format is None:
        raise not_allowed("This source has no model.", "no_model")
    if source.model_format == MODEL_TMSL:
        raise not_allowed(MESSAGE_TMSL_TARGET, "tmsl_target")


def require_report_target(source: LocalSource) -> None:
    if source.report_dir is None or source.report_format is None:
        raise not_allowed("This source has no report.", "no_report")
    if source.report_format == REPORT_PBIR_LEGACY:
        raise not_allowed(MESSAGE_PBIR_LEGACY_TARGET, "pbir_legacy_target")
