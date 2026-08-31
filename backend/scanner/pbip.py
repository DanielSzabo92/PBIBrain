"""Small, read-only adapter for file-backed PBIP projects.

The adapter turns the PBIP/TMDL/PBIR file layout into the plain mappings that
the existing normalizer already understands.  It does not call Power BI or
the Desktop Bridge, and it keeps file-format details at the scanner boundary.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping


_OBJECT_RE = re.compile(r"^(\s+)(column|measure)\s+(.+?)\s*$", re.IGNORECASE)
_TABLE_RE = re.compile(r"^\s*table\s+(.+?)\s*$", re.IGNORECASE)
_MODEL_RE = re.compile(r"^\s*model\s+(.+?)\s*$", re.IGNORECASE)
_ATTRIBUTE_RE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9_]*)\s*:\s*(.*?)\s*$")
_RELATIONSHIP_RE = re.compile(r"^\s*relationship\s+(.+?)\s*$", re.IGNORECASE)
_EXPRESSION_RE = re.compile(r"^\s*expression\s+(.+?)\s*=\s*(.*?)\s*$", re.IGNORECASE)


def is_pbip_source(source: Any) -> bool:
    """Return true only for an existing ``.pbip`` path."""

    if isinstance(source, Path):
        return source.suffix.casefold() == ".pbip" and source.is_file()
    if isinstance(source, str):
        path = Path(source)
        return path.suffix.casefold() == ".pbip" and path.is_file()
    return False


def read_pbip_project(source: str | Path) -> dict[str, list[dict[str, Any]]]:
    """Read one PBIP project into model and report source mappings."""

    project = Path(source).resolve()
    if project.suffix.casefold() != ".pbip" or not project.is_file():
        raise ValueError(f"PBIP source must be an existing .pbip file: {project}")
    payload = _read_json(project)
    root = project.parent
    model_dirs, report_dirs = _artifact_dirs(root, payload)
    models = [_read_model(path) for path in model_dirs]
    model_by_dir = {path.resolve(): model for path, model in zip(model_dirs, models)}
    reports = [_read_report(path, model_by_dir, root) for path in report_dirs]
    return {"models": models, "reports": reports}


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError(f"Expected JSON object: {path}")
    return dict(value)


def _artifact_dirs(root: Path, payload: Mapping[str, Any]) -> tuple[list[Path], list[Path]]:
    models: list[Path] = []
    reports: list[Path] = []
    artifacts = payload.get("artifacts", [])
    if not isinstance(artifacts, list):
        artifacts = []
    for artifact in artifacts:
        if not isinstance(artifact, Mapping):
            continue
        for key, target in (("semanticModel", models), ("semantic_model", models), ("model", models), ("report", reports)):
            item = artifact.get(key)
            if not isinstance(item, Mapping):
                continue
            path_value = item.get("path")
            if isinstance(path_value, str):
                path = (root / path_value).resolve()
                if path.is_dir() and path not in target:
                    target.append(path)
    if not models:
        models = sorted((path for path in root.glob("*.SemanticModel") if path.is_dir()), key=lambda p: p.name.casefold())
    if not reports:
        reports = sorted((path for path in root.glob("*.Report") if path.is_dir()), key=lambda p: p.name.casefold())
    return models, reports


def _platform(directory: Path) -> dict[str, Any]:
    path = directory / ".platform"
    if not path.is_file():
        return {}
    try:
        return _read_json(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return {}


def _unquote(value: Any) -> str:
    text = str(value).strip()
    if len(text) >= 2 and text[0] == text[-1] == "'":
        return text[1:-1].replace("''", "'")
    if len(text) >= 2 and text[0] == text[-1] == '"':
        return text[1:-1].replace('""', '"')
    return text


def _platform_id(directory: Path) -> str | None:
    value = _platform(directory).get("config")
    if isinstance(value, Mapping) and value.get("logicalId"):
        return str(value["logicalId"])
    return None


def _platform_name(directory: Path) -> str | None:
    value = _platform(directory).get("metadata")
    if isinstance(value, Mapping) and value.get("displayName"):
        return str(value["displayName"])
    return None


def _attribute(lines: Iterable[str], name: str) -> str | None:
    wanted = name.casefold()
    for line in lines:
        match = _ATTRIBUTE_RE.match(line)
        if match and match.group(1).casefold() == wanted:
            return match.group(2).strip()
    return None


def _has_marker(lines: Iterable[str], name: str) -> bool:
    wanted = name.casefold()
    return any(line.strip().casefold() == wanted for line in lines)


def _comments(lines: list[str], index: int, indent: int) -> str | None:
    values: list[str] = []
    cursor = index - 1
    while cursor >= 0:
        line = lines[cursor]
        if not line.strip():
            cursor -= 1
            continue
        if len(line) - len(line.lstrip()) > indent:
            cursor -= 1
            continue
        match = re.match(r"^\s*///\s?(.*)$", line)
        if not match:
            break
        values.append(match.group(1).strip())
        cursor -= 1
    return "\n".join(reversed(values)) or None


def _formula(rhs: str, block: list[str]) -> str | None:
    value = rhs.strip()
    if not value.startswith("```"):
        return value or None
    parts: list[str] = []
    remainder = value[3:]
    if remainder:
        parts.append(remainder.split("```", 1)[0])
        if "```" in remainder:
            return "\n".join(parts).strip() or None
    for line in block[1:]:
        if "```" in line:
            parts.append(line.split("```", 1)[0])
            break
        parts.append(line)
    return "\n".join(parts).strip() or None


def _parse_table(path: Path) -> dict[str, Any] | None:
    lines = path.read_text(encoding="utf-8").splitlines()
    table_index = next((i for i, line in enumerate(lines) if _TABLE_RE.match(line)), None)
    if table_index is None:
        return None
    table_match = _TABLE_RE.match(lines[table_index])
    assert table_match is not None
    table_name = _unquote(table_match.group(1))
    table_indent = len(lines[table_index]) - len(lines[table_index].lstrip())
    table_lines = lines[table_index:]
    table_lineage = _attribute(table_lines, "lineageTag")
    table: dict[str, Any] = {
        "id": table_lineage or table_name,
        "name": table_name,
        "description": _comments(lines, table_index, table_indent),
        "hidden": _has_marker(table_lines, "isHidden"),
        "columns": [],
        "measures": [],
    }
    object_matches = [
        (index, match)
        for index, line in enumerate(lines[table_index + 1 :], table_index + 1)
        if (match := _OBJECT_RE.match(line)) and len(line) - len(line.lstrip()) > table_indent
    ]
    object_indent = min(
        (len(match.group(1)) for _, match in object_matches),
        default=table_indent + 1,
    )
    object_indexes = [
        (index, match)
        for index, match in object_matches
        if len(match.group(1)) == object_indent
    ]
    for position, (index, match) in enumerate(object_indexes):
        end = object_indexes[position + 1][0] if position + 1 < len(object_indexes) else len(lines)
        kind = match.group(2).casefold()
        header = match.group(3)
        name_part, separator, rhs = header.partition("=")
        object_name = _unquote(name_part.strip())
        block = lines[index:end]
        lineage = _attribute(block, "lineageTag")
        expression = _formula(rhs if separator else "", block)
        item: dict[str, Any] = {
            "id": lineage or f"{table_name}.{object_name}",
            "name": object_name,
            "description": _comments(lines, index, len(match.group(1))),
            "hidden": _has_marker(block, "isHidden"),
            "datatype": _attribute(block, "dataType"),
            "formatString": _attribute(block, "formatString"),
            "formatStringExpression": _attribute(block, "formatStringExpression"),
            "sortByColumn": _attribute(block, "sortByColumn"),
            "summarizeBy": _attribute(block, "summarizeBy"),
            "sourceColumn": _attribute(block, "sourceColumn"),
        }
        if expression:
            item["expression"] = expression
            item["expression_language"] = "DAX"
        item = {key: value for key, value in item.items() if value is not None}
        table["measures" if kind == "measure" else "columns"].append(item)
    return table


def _parse_model_meta(path: Path) -> dict[str, Any]:
    model_file = path / "definition" / "model.tmdl"
    lines = model_file.read_text(encoding="utf-8").splitlines() if model_file.is_file() else []
    match = next((candidate for candidate in (_MODEL_RE.match(line) for line in lines) if candidate), None)
    tmdl_name = _unquote(match.group(1)) if match else None
    platform_name = _platform_name(path)
    name = tmdl_name or platform_name or path.stem
    if name.casefold() == "model" and platform_name:
        name = platform_name
    source = _attribute(lines, "lineageTag") or _platform_id(path)
    source = source or "pbip-model-" + hashlib.sha256(str(path.resolve()).encode("utf-8")).hexdigest()[:24]
    compatibility = _attribute(
        (path / "definition" / "database.tmdl").read_text(encoding="utf-8").splitlines()
        if (path / "definition" / "database.tmdl").is_file()
        else [],
        "compatibilityLevel",
    )
    model: dict[str, Any] = {
        "id": source,
        "name": name,
        "source_path": str(path),
        "compatibility_level": compatibility,
        "tables": [],
        "relationships": _parse_relationships(path / "definition" / "relationships.tmdl"),
        "shared_expressions": _parse_expressions(path / "definition" / "expressions.tmdl"),
    }
    for table_path in sorted((path / "definition" / "tables").rglob("*.tmdl"), key=lambda item: str(item).casefold()):
        table = _parse_table(table_path)
        if table:
            model["tables"].append(table)
    return {key: value for key, value in model.items() if value not in (None, [], {})}


def _read_model(path: Path) -> dict[str, Any]:
    return _parse_model_meta(path)


def _split_endpoint(value: Any) -> dict[str, str] | str:
    text = _unquote(value)
    if "." not in text:
        return text
    table, column = text.rsplit(".", 1)
    return {"table": _unquote(table), "column": _unquote(column)}


def _parse_relationships(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    starts = [index for index, line in enumerate(lines) if _RELATIONSHIP_RE.match(line)]
    result: list[dict[str, Any]] = []
    for position, index in enumerate(starts):
        end = starts[position + 1] if position + 1 < len(starts) else len(lines)
        match = _RELATIONSHIP_RE.match(lines[index])
        assert match is not None
        block = lines[index:end]
        values: dict[str, Any] = {"id": _unquote(match.group(1))}
        for line in block[1:]:
            attr = _ATTRIBUTE_RE.match(line)
            if not attr:
                continue
            key, value = attr.group(1), attr.group(2)
            key_map = {
                "fromcolumn": "from_column",
                "tocolumn": "to_column",
                "fromcardinality": "from_cardinality",
                "tocardinality": "to_cardinality",
                "crossfilteringbehavior": "cross_filter_direction",
                "isactive": "active",
            }
            target_key = key_map.get(key.casefold(), key)
            if target_key in {"from_column", "to_column"}:
                values[target_key] = _split_endpoint(value)
            elif target_key == "active":
                values[target_key] = value.casefold() in {"true", "1", "yes"}
            else:
                values[target_key] = _unquote(value)
        result.append(values)
    return result


def _parse_expressions(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    starts = [index for index, line in enumerate(lines) if _EXPRESSION_RE.match(line)]
    result: list[dict[str, Any]] = []
    for position, index in enumerate(starts):
        end = starts[position + 1] if position + 1 < len(starts) else len(lines)
        match = _EXPRESSION_RE.match(lines[index])
        assert match is not None
        expression = match.group(2).strip()
        continuation = [line.strip() for line in lines[index + 1 : end] if line.strip() and not line.lstrip().startswith(("lineageTag:", "annotation "))]
        if continuation:
            expression = "\n".join([expression, *continuation])
        result.append(
            {
                "id": _attribute(lines[index:end], "lineageTag") or _unquote(match.group(1)),
                "name": _unquote(match.group(1)),
                "expression": expression,
                "kind": "m",
                "language": "m",
            }
        )
    return result


def _read_report(path: Path, models: Mapping[Path, Mapping[str, Any]], root: Path) -> dict[str, Any]:
    platform_name = _platform_name(path)
    report_json = path / "definition" / "report.json"
    report_payload = _read_json(report_json) if report_json.is_file() else {}
    report_id = _platform_id(path) or path.name
    model_ref = _report_model_ref(path)
    model = _model_for_ref(model_ref, models, path, root)
    pages: list[dict[str, Any]] = []
    pages_root = path / "definition" / "pages"
    pages_meta = pages_root / "pages.json"
    if not pages_meta.is_file():
        pages_meta = path / "definition" / "pages.json"
    page_order: list[str] = []
    if pages_meta.is_file():
        try:
            page_payload = _read_json(pages_meta)
            raw_order = page_payload.get("pageOrder", [])
            if isinstance(raw_order, list):
                page_order = [str(item) for item in raw_order]
        except (OSError, ValueError, json.JSONDecodeError):
            page_order = []
    if not page_order:
        page_order = sorted((item.name for item in pages_root.iterdir() if item.is_dir()), key=str.casefold) if pages_root.is_dir() else []
    for ordinal, page_name in enumerate(page_order):
        page_dir = pages_root / page_name
        page_file = page_dir / "page.json"
        page_payload = _read_json(page_file) if page_file.is_file() else {"name": page_name}
        source_name = page_payload.get("name", page_name)
        display = page_payload.get("displayName", source_name)
        visuals: list[dict[str, Any]] = []
        visuals_dir = page_dir / "visuals"
        for visual_file in sorted(visuals_dir.glob("*/visual.json"), key=lambda item: str(item).casefold()):
            visual = _read_json(visual_file)
            if "id" not in visual and visual.get("name") is not None:
                visual["id"] = visual["name"]
            visuals.append(visual)
        pages.append(
            {
                **page_payload,
                "id": source_name,
                "name": display,
                "display_name": display,
                "order": page_payload.get("ordinal", ordinal),
                "visuals": visuals,
            }
        )
    report: dict[str, Any] = {
        **report_payload,
        "id": report_id,
        "name": report_payload.get("name") or platform_name or path.stem,
        "model_id": model.get("id") if model else model_ref,
        "source_path": str(path),
        "pages": pages,
    }
    return report


def _report_model_ref(path: Path) -> str | None:
    definition = path / "definition.pbir"
    if not definition.is_file():
        return None
    try:
        payload = _read_json(definition)
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    reference = payload.get("datasetReference")
    if not isinstance(reference, Mapping):
        return None
    by_path = reference.get("byPath")
    if isinstance(by_path, Mapping) and by_path.get("path"):
        return str((path / str(by_path["path"])).resolve())
    return None


def _model_for_ref(ref: str | None, models: Mapping[Path, Mapping[str, Any]], report: Path, root: Path) -> Mapping[str, Any] | None:
    if ref:
        target = Path(ref)
        for path, model in models.items():
            if path.resolve() == target.resolve():
                return model
    if len(models) == 1:
        return next(iter(models.values()))
    return None


__all__ = ["is_pbip_source", "read_pbip_project"]
