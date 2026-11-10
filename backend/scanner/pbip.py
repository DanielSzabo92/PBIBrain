"""Small, read-only adapter for file-backed PBIP projects.

The adapter turns the PBIP/TMDL/PBIR file layout into the plain mappings that
the existing normalizer already understands.  It does not call Power BI or
the Desktop Bridge, and it keeps file-format details at the scanner boundary.
"""

from __future__ import annotations

import hashlib
import json
import re
import textwrap
from pathlib import Path
from typing import Any, Iterable, Mapping


_OBJECT_RE = re.compile(r"^(\s+)(column|measure|hierarchy|partition)\s+(.+?)\s*$", re.IGNORECASE)
_LEVEL_RE = re.compile(r"^(\s+)level\s+(.+?)\s*$", re.IGNORECASE)
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

    def add(target: list[Path], value: Any) -> None:
        if not isinstance(value, str):
            return
        path = (root / value).resolve()
        if path.is_dir() and not any(item == path for item in target):
            target.append(path)

    artifacts = payload.get("artifacts", [])
    if not isinstance(artifacts, list):
        artifacts = []
    for artifact in artifacts:
        if not isinstance(artifact, Mapping):
            continue
        for key, target in (("semanticModel", models), ("semantic_model", models), ("model", models), ("report", reports)):
            item = artifact.get(key)
            add(target, item.get("path") if isinstance(item, Mapping) else None)
        kind = str(artifact.get("type", "")).casefold()
        target = reports if kind == "report" else models if kind in {"model", "semanticmodel", "semantic_model", "dataset"} else None
        if target is not None:
            add(target, artifact.get("path"))
    if not models:
        models = sorted(
            (
                path
                for path in root.iterdir()
                if path.is_dir() and path.suffix.casefold() in {".semanticmodel", ".dataset"}
            ),
            key=lambda p: p.name.casefold(),
        )
    if not reports:
        reports = sorted(
            (path for path in root.iterdir() if path.is_dir() and path.suffix.casefold() == ".report"),
            key=lambda p: p.name.casefold(),
        )
    for report in reports:
        reference = _report_model_ref(report)
        if reference:
            add(models, reference)
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


def _trimmed_end(lines: list[str], start: int, end: int) -> int:
    cursor = end
    while cursor > start + 1 and not lines[cursor - 1].strip():
        cursor -= 1
    return cursor


def _parse_table(path: Path, model_root: Path | None = None) -> dict[str, Any] | None:
    lines = path.read_text(encoding="utf-8").splitlines()
    table_index = next((i for i, line in enumerate(lines) if _TABLE_RE.match(line)), None)
    if table_index is None:
        return None
    source_file = (
        path.relative_to(model_root).as_posix()
        if model_root is not None and path.is_relative_to(model_root)
        else f"definition/tables/{path.name}"
    )
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
        "hierarchies": [],
        "ast_location": {
            "source_file": source_file,
            "span": f"L{table_index + 1}-L{_trimmed_end(lines, table_index, len(lines))}",
        },
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
        actual_end = _trimmed_end(lines, index, end)
        kind = match.group(2).casefold()
        header = match.group(3)
        if kind == "partition":
            # Issue #10: the partition source (M text or Direct Lake entity) feeds the data-source lineage.
            table.setdefault("partitions", []).append(
                _parse_partition(header, lines[index:end], source_file=source_file, start_line=index + 1, end_line=actual_end)
            )
            continue
        if kind == "hierarchy":
            table["hierarchies"].append(
                _parse_hierarchy(_unquote(header.strip()), lines[index:end], source_file=source_file, start_line=index + 1, end_line=actual_end)
            )
            continue
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
            "ast_location": {
                "source_file": source_file,
                "span": f"L{index + 1}-L{actual_end}",
            },
        }
        if expression:
            item["expression"] = expression
            item["expression_language"] = "DAX"
        item = {key: value for key, value in item.items() if value is not None}
        table["measures" if kind == "measure" else "columns"].append(item)
    if not table["hierarchies"]:
        del table["hierarchies"]
    return table


_SOURCE_RE = re.compile(r"^(\s*)source\s*(?:=\s*(.*?))?\s*$", re.IGNORECASE)


def _parse_partition(
    header: str,
    block: list[str],
    *,
    source_file: str | None = None,
    start_line: int | None = None,
    end_line: int | None = None,
) -> dict[str, Any]:
    """Read one TMDL partition block into the TOM shape: name, mode and source (type, expression or entity)."""

    name_part, _, source_type = header.partition("=")
    partition: dict[str, Any] = {"name": _unquote(name_part.strip())}
    if source_file and start_line is not None and end_line is not None:
        partition["ast_location"] = {"source_file": source_file, "span": f"L{start_line}-L{end_line}"}
    source: dict[str, Any] = {"type": source_type.strip() or None}
    start = next((index for index, line in enumerate(block[1:], 1) if _SOURCE_RE.match(line)), None)
    header_lines = block[:start] if start is not None else block
    mode = _attribute(header_lines[1:], "mode")
    if mode:
        partition["mode"] = mode
    if start is not None:
        match = _SOURCE_RE.match(block[start])
        assert match is not None
        indent = len(match.group(1))
        body: list[str] = []
        for line in block[start + 1:]:
            if line.strip() and len(line) - len(line.lstrip()) <= indent:
                break
            body.append(line)
        rhs = match.group(2)
        if rhs is None:
            # Direct Lake: "source" followed by entityName, schemaName and expressionSource.
            for line in body:
                attribute = _ATTRIBUTE_RE.match(line)
                if attribute:
                    source[attribute.group(1)] = _unquote(attribute.group(2))
        elif rhs.strip():
            source["expression"] = _formula(rhs, [block[start], *body])
        else:
            source["expression"] = textwrap.dedent("\n".join(body)).strip() or None
    partition["source"] = {key: value for key, value in source.items() if value is not None}
    return partition


def _parse_hierarchy(
    name: str,
    block: list[str],
    *,
    source_file: str | None = None,
    start_line: int | None = None,
    end_line: int | None = None,
) -> dict[str, Any]:
    """Read one TMDL hierarchy block and its levels."""

    starts = [index for index, line in enumerate(block) if _LEVEL_RE.match(line)]
    header = block[: starts[0]] if starts else block
    hierarchy: dict[str, Any] = {"name": name, "levels": []}
    if source_file and start_line is not None and end_line is not None:
        hierarchy["ast_location"] = {"source_file": source_file, "span": f"L{start_line}-L{end_line}"}
    lineage = _attribute(header, "lineageTag")
    if lineage:
        hierarchy["lineageTag"] = lineage
    for position, index in enumerate(starts):
        end = starts[position + 1] if position + 1 < len(starts) else len(block)
        actual_end = _trimmed_end(block, index, end)
        level_block = block[index:end]
        match = _LEVEL_RE.match(block[index])
        assert match is not None
        level: dict[str, Any] = {
            "name": _unquote(match.group(2)),
            "ordinal": position,
            "column": _unquote(_attribute(level_block, "column") or ""),
        }
        if source_file and start_line is not None:
            level["ast_location"] = {
                "source_file": source_file,
                "span": f"L{start_line + index}-L{start_line + actual_end - 1}",
            }
        lineage = _attribute(level_block, "lineageTag")
        if lineage:
            level["lineageTag"] = lineage
        hierarchy["levels"].append(level)
    return hierarchy


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
        "relationships": _parse_relationships(path / "definition" / "relationships.tmdl", model_root=path),
        "shared_expressions": _parse_expressions(path / "definition" / "expressions.tmdl", model_root=path),
    }
    if model_file.is_file():
        model["ast_location"] = {
            "source_file": "definition/model.tmdl",
            "span": f"L1-L{max(1, len(lines))}",
        }
    for table_path in sorted((path / "definition" / "tables").rglob("*.tmdl"), key=lambda item: str(item).casefold()):
        table = _parse_table(table_path, model_root=path)
        if table:
            model["tables"].append(table)
    return {key: value for key, value in model.items() if value not in (None, [], {})}


def _parse_model_bim(path: Path) -> dict[str, Any]:
    bim_file = path / "model.bim"
    bim_lines = len(bim_file.read_text(encoding="utf-8").splitlines()) if bim_file.is_file() else 1
    payload = _read_json(bim_file)
    value = payload.get("model", payload)
    model = dict(value) if isinstance(value, Mapping) else {}
    platform_name = _platform_name(path)
    name = model.get("name") or payload.get("name") or platform_name or path.stem
    source = model.get("id") or payload.get("id") or _platform_id(path)
    source = source or "pbip-model-" + hashlib.sha256(str(path.resolve()).encode("utf-8")).hexdigest()[:24]
    compatibility = (
        model.get("compatibility_level")
        or model.get("compatibilityLevel")
        or payload.get("compatibilityLevel")
    )
    model.update(
        {
            "id": source,
            "name": name,
            "source_path": str(path),
            "compatibility_level": compatibility,
            "ast_location": {
                "source_file": "model.bim",
                "span": f"L1-L{max(1, bim_lines)}",
            },
        }
    )
    return {key: value for key, value in model.items() if value not in (None, [], {})}


def _read_model(path: Path) -> dict[str, Any]:
    if (path / "definition" / "model.tmdl").is_file():
        return _parse_model_meta(path)
    if (path / "model.bim").is_file():
        return _parse_model_bim(path)
    return _parse_model_meta(path)


def _split_endpoint(value: Any) -> dict[str, str] | str:
    text = _unquote(value)
    if "." not in text:
        return text
    table, column = text.rsplit(".", 1)
    return {"table": _unquote(table), "column": _unquote(column)}


def _parse_relationships(path: Path, model_root: Path | None = None) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    source_file = (
        path.relative_to(model_root).as_posix()
        if model_root is not None and path.is_relative_to(model_root)
        else "definition/relationships.tmdl"
    )
    lines = path.read_text(encoding="utf-8").splitlines()
    starts = [index for index, line in enumerate(lines) if _RELATIONSHIP_RE.match(line)]
    result: list[dict[str, Any]] = []
    for position, index in enumerate(starts):
        end = starts[position + 1] if position + 1 < len(starts) else len(lines)
        actual_end = _trimmed_end(lines, index, end)
        match = _RELATIONSHIP_RE.match(lines[index])
        assert match is not None
        block = lines[index:end]
        values: dict[str, Any] = {
            "id": _unquote(match.group(1)),
            "ast_location": {
                "source_file": source_file,
                "span": f"L{index + 1}-L{actual_end}",
            },
        }
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


def _parse_expressions(path: Path, model_root: Path | None = None) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    source_file = (
        path.relative_to(model_root).as_posix()
        if model_root is not None and path.is_relative_to(model_root)
        else "definition/expressions.tmdl"
    )
    lines = path.read_text(encoding="utf-8").splitlines()
    starts = [index for index, line in enumerate(lines) if _EXPRESSION_RE.match(line)]
    result: list[dict[str, Any]] = []
    for position, index in enumerate(starts):
        end = starts[position + 1] if position + 1 < len(starts) else len(lines)
        actual_end = _trimmed_end(lines, index, end)
        match = _EXPRESSION_RE.match(lines[index])
        assert match is not None
        expression = match.group(2).strip()
        continuation = [line.strip() for line in lines[index + 1 : end] if line.strip()
                        and not line.lstrip().startswith(("lineageTag:", "annotation ", "queryGroup:", "mAttributes:", "changedProperty "))]
        if continuation:
            expression = "\n".join([expression, *continuation])
        result.append(
            {
                "id": _attribute(lines[index:end], "lineageTag") or _unquote(match.group(1)),
                "name": _unquote(match.group(1)),
                "expression": expression,
                "kind": "m",
                "language": "m",
                "ast_location": {
                    "source_file": source_file,
                    "span": f"L{index + 1}-L{actual_end}",
                },
            }
        )
    return result


def _read_report(path: Path, models: Mapping[Path, Mapping[str, Any]], root: Path) -> dict[str, Any]:
    platform_name = _platform_name(path)
    report_json = path / "definition" / "report.json"
    if not report_json.is_file():
        report_json = path / "report.json"
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
            v_lines = len(visual_file.read_text(encoding="utf-8").splitlines())
            visual["ast_location"] = {
                "source_file": visual_file.relative_to(path).as_posix(),
                "span": f"L1-L{max(1, v_lines)}",
            }
            visuals.append(visual)
        page_item: dict[str, Any] = {
            **page_payload,
            "id": source_name,
            "name": display,
            "display_name": display,
            "order": page_payload.get("ordinal", ordinal),
            "visuals": visuals,
        }
        if page_file.is_file():
            p_lines = len(page_file.read_text(encoding="utf-8").splitlines())
            page_item["ast_location"] = {
                "source_file": page_file.relative_to(path).as_posix(),
                "span": f"L1-L{max(1, p_lines)}",
            }
        pages.append(page_item)
    extensions_file = path / "definition" / "reportExtensions.json"
    extensions = _read_json(extensions_file) if extensions_file.is_file() else {}
    report: dict[str, Any] = {
        **report_payload,
        "report_extensions": extensions.get("entities", []) if isinstance(extensions, Mapping) else [],
        "bookmarks": _read_bookmarks(path / "definition" / "bookmarks"),
        "id": report_id,
        "name": report_payload.get("name") or platform_name or path.stem,
        "model_id": model.get("id") if model else model_ref,
        "source_path": str(path),
        "pages": pages,
    }
    if report_json.is_file():
        r_lines = len(report_json.read_text(encoding="utf-8").splitlines())
        report["ast_location"] = {
            "source_file": report_json.relative_to(path).as_posix(),
            "span": f"L1-L{max(1, r_lines)}",
        }
    return report


def _read_bookmarks(folder: Path) -> list[dict[str, Any]]:
    """Read the PBIR bookmarks in the order of bookmarks.json, with their group names."""

    if not folder.is_dir():
        return []
    files = {item.name[: -len(".bookmark.json")]: item for item in folder.glob("*.bookmark.json")}
    ordered: list[tuple[str, str | None]] = []
    metadata = folder / "bookmarks.json"
    if metadata.is_file():
        def visit(items: Any, group: str | None) -> None:
            for item in items if isinstance(items, list) else []:
                if not isinstance(item, Mapping) or item.get("name") is None:
                    continue
                if isinstance(item.get("children"), list):
                    visit(item["children"], str(item["name"]))
                else:
                    ordered.append((str(item["name"]), group))
        try:
            items = _read_json(metadata).get("items")
        except (OSError, ValueError):
            # A bookmarks.json that is not a JSON object gives no order. The PBIR
            # validation still reports the file, thus the guarded scan stays blocked.
            items = None
        visit(items, None)
    listed = {name for name, _ in ordered}
    ordered.extend((name, None) for name in sorted(files, key=str.casefold) if name not in listed)
    bookmarks: list[dict[str, Any]] = []
    for ordinal, (name, group) in enumerate(ordered):
        if name not in files:
            continue
        payload = _read_json(files[name])
        rel_file = files[name].relative_to(folder.parent.parent).as_posix()
        b_lines = len(files[name].read_text(encoding="utf-8").splitlines())
        bookmarks.append(
            {
                **payload,
                "id": payload.get("name", name),
                "order": ordinal,
                "group_name": group,
                "source_file": rel_file,
                "ast_location": {
                    "source_file": rel_file,
                    "span": f"L1-L{max(1, b_lines)}",
                },
            }
        )
    return bookmarks


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
    by_connection = reference.get("byConnection")
    if isinstance(by_connection, Mapping):
        connection_id = (
            by_connection.get("semanticmodelid")
            or by_connection.get("pbiModelDatabaseName")
            or by_connection.get("connectionString")
        )
        if connection_id:
            return f"byConnection:{connection_id}"
        return "byConnection"
    return None


def _model_for_ref(ref: str | None, models: Mapping[Path, Mapping[str, Any]], report: Path, root: Path) -> Mapping[str, Any] | None:
    if ref is not None:
        target = Path(ref)
        for path, model in models.items():
            if path.resolve() == target.resolve():
                return model
        return None
    if len(models) == 1:
        return next(iter(models.values()))
    return None


def read_model_folder(path: str | Path) -> dict[str, Any]:
    """Read one semantic model folder (``definition/*.tmdl`` or ``model.bim``) outside a PBIP project."""

    return _read_model(Path(path).resolve())


def read_report_folder(path: str | Path) -> dict[str, Any]:
    """Read one PBIR report folder outside a PBIP project. Its model binding stays a reference."""

    folder = Path(path).resolve()
    return _read_report(folder, {}, folder)


__all__ = ["is_pbip_source", "read_model_folder", "read_pbip_project", "read_report_folder"]
