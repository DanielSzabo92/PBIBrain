"""Object index of a local source: one hash for each object (the row hashes of section 11).

A row key has the form ``<object type>:<qualified name>``, for example
``measure:Sales/Total Sales``. The hash covers the source text of the object
only, so a change to one object marks only that row.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

from backend.devcenter.sources.kinds import (
    MODEL_TMDL,
    MODEL_TMSL,
    REPORT_PBIR,
    REPORT_PBIR_LEGACY,
    LocalSource,
)
from backend.snapshots.manifest import content_hash

_TOP_LEVEL = {
    "table": "table",
    "relationship": "relationship",
    "role": "role",
    "expression": "expression",
    "function": "function",
    "model": "model",
    "perspective": "perspective",
    "cultureInfo": "culture",
    "dataSource": "data_source",
}
_TABLE_CHILDREN = {
    "measure": "measure",
    "column": "column",
    "calculatedColumn": "column",
    "hierarchy": "hierarchy",
    "partition": "partition",
}
_CALCULATION_ITEM = "calculationItem"
# Each row key kind that ``object_index`` makes. ``session.secrets.ROW_KEY_KINDS`` must hold the same kinds.
OBJECT_KINDS = tuple(dict.fromkeys([*_TOP_LEVEL.values(), *_TABLE_CHILDREN.values(), "calculation_item",
                                    "report", "page", "visual", "bookmark", "report_measure"]))


def _unquote(text: str) -> str:
    text = text.strip()
    if len(text) >= 2 and text[0] == "'" and text[-1] == "'":
        return text[1:-1].replace("''", "'")
    return text


def _declaration(line: str) -> tuple[str, str] | None:
    keyword, _, rest = line.strip().partition(" ")
    if not rest:
        return (keyword, "") if keyword in {"model", "calculationGroup"} else None
    name = rest
    if rest.startswith("'"):
        index = 1
        while index < len(rest):
            if rest[index] == "'":
                if index + 1 < len(rest) and rest[index + 1] == "'":
                    index += 2
                    continue
                break
            index += 1
        name = rest[: index + 1]
    else:
        for marker in (" =", "="):
            if marker in name:
                name = name.split(marker, 1)[0]
                break
    return keyword, _unquote(name)


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip("\t"))


def _blocks(lines: list[str], level: int) -> Iterator[tuple[int, int]]:
    """Give (start, end) of each block that starts at this tab level."""

    starts = [index for index, line in enumerate(lines) if line.strip() and _indent(line) == level and not line[level:].startswith((" ", "///"))]
    for start in starts:
        end = len(lines)
        for index in range(start + 1, len(lines)):
            if lines[index].strip() and _indent(lines[index]) <= level:
                end = index
                break
        yield start, end


def _hash_lines(lines: list[str]) -> str:
    return content_hash("\n".join(line.rstrip() for line in lines).strip("\n").encode("utf-8"))


def _tmdl_file(text: str, index: dict[str, str]) -> None:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    for start, end in _blocks(lines, 0):
        declaration = _declaration(lines[start])
        if declaration is None or declaration[0] not in _TOP_LEVEL:
            continue
        keyword, name = declaration
        kind = _TOP_LEVEL[keyword]
        block = lines[start:end]
        if kind != "table":
            index[f"{kind}:{name}"] = _hash_lines(block)
            continue
        own: list[str] = [block[0]]
        body = block[1:]
        skip: set[int] = set()
        for child_start, child_end in _blocks(body, 1):
            child = _declaration(body[child_start])
            if child is None:
                continue
            if child[0] in _TABLE_CHILDREN:
                index[f"{_TABLE_CHILDREN[child[0]]}:{name}/{child[1]}"] = _hash_lines(body[child_start:child_end])
                skip.update(range(child_start, child_end))
            elif child[0] == "calculationGroup":
                group = body[child_start + 1 : child_end]
                for item_start, item_end in _blocks(group, 2):
                    item = _declaration(group[item_start])
                    if item is not None and item[0] == _CALCULATION_ITEM:
                        index[f"calculation_item:{name}/{item[1]}"] = _hash_lines(group[item_start:item_end])
                        skip.update(range(child_start + 1 + item_start, child_start + 1 + item_end))
        own.extend(line for position, line in enumerate(body) if position not in skip)
        index[f"table:{name}"] = _hash_lines(own)


def _tmdl_index(definition: Path, index: dict[str, str]) -> None:
    for path in sorted(definition.rglob("*.tmdl")):
        _tmdl_file(path.read_text(encoding="utf-8-sig"), index)


def _named(items: Any) -> Iterator[dict[str, Any]]:
    for item in items or []:
        if isinstance(item, dict) and isinstance(item.get("name"), str):
            yield item


def _tmsl_index(path: Path, index: dict[str, str]) -> None:
    document = json.loads(path.read_text(encoding="utf-8-sig"))
    model = document.get("model", document) if isinstance(document, dict) else {}
    children = {"measures": "measure", "columns": "column", "hierarchies": "hierarchy", "partitions": "partition"}
    for table in _named(model.get("tables")):
        name = table["name"]
        own = {key: value for key, value in table.items() if key not in children and key != "calculationGroup"}
        index[f"table:{name}"] = content_hash(own)
        for key, kind in children.items():
            for child in _named(table.get(key)):
                index[f"{kind}:{name}/{child['name']}"] = content_hash(child)
        group = table.get("calculationGroup")
        if isinstance(group, dict):
            for item in _named(group.get("calculationItems")):
                index[f"calculation_item:{name}/{item['name']}"] = content_hash(item)
    for key, kind in (("relationships", "relationship"), ("roles", "role"), ("expressions", "expression"),
                      ("functions", "function"), ("perspectives", "perspective"), ("cultures", "culture")):
        for item in _named(model.get(key)):
            index[f"{kind}:{item['name']}"] = content_hash(item)
    settings = {key: value for key, value in model.items() if not isinstance(value, list)}
    index["model:Model"] = content_hash(settings)


def _file_hash(path: Path) -> str:
    return content_hash(path.read_bytes().replace(b"\r\n", b"\n"))


def _pbir_index(report_dir: Path, index: dict[str, str]) -> None:
    definition = report_dir / "definition"
    index["report:report"] = _file_hash(definition / "report.json")
    pages = definition / "pages"
    for page_file in sorted(pages.glob("*/page.json")):
        page = page_file.parent.name
        index[f"page:{page}"] = _file_hash(page_file)
        for visual_file in sorted(page_file.parent.glob("visuals/*/visual.json")):
            index[f"visual:{page}/{visual_file.parent.name}"] = _file_hash(visual_file)
    for bookmark in sorted((definition / "bookmarks").glob("*.bookmark.json")):
        index[f"bookmark:{bookmark.name[: -len('.bookmark.json')]}"] = _file_hash(bookmark)
    extensions = definition / "reportExtensions.json"
    if extensions.is_file():
        document = json.loads(extensions.read_text(encoding="utf-8-sig"))
        for entity in _named(document.get("entities")):
            for measure in _named(entity.get("measures")):
                index[f"report_measure:{entity['name']}/{measure['name']}"] = content_hash(measure)


def _pbir_legacy_index(report_dir: Path, index: dict[str, str]) -> None:
    document = json.loads((report_dir / "report.json").read_text(encoding="utf-8-sig"))
    settings = {key: value for key, value in document.items() if key != "sections"}
    index["report:report"] = content_hash(settings)
    for section in _named(document.get("sections")):
        page = section["name"]
        index[f"page:{page}"] = content_hash({key: value for key, value in section.items() if key != "visualContainers"})
        for position, container in enumerate(section.get("visualContainers") or []):
            name = str(position)
            config = container.get("config") if isinstance(container, dict) else None
            if isinstance(config, str):
                try:
                    name = str(json.loads(config).get("name") or name)
                except ValueError:
                    pass
            index[f"visual:{page}/{name}"] = content_hash(container)


def object_index(source: LocalSource) -> dict[str, str]:
    """Give ``{row key: hash}`` for each object of the source. The keys are sorted."""

    index: dict[str, str] = {}
    if source.model_dir is not None and source.model_format == MODEL_TMDL:
        _tmdl_index(source.model_dir / "definition", index)
    elif source.model_dir is not None and source.model_format == MODEL_TMSL:
        _tmsl_index(source.model_dir / "model.bim", index)
    if source.report_dir is not None and source.report_format == REPORT_PBIR:
        _pbir_index(source.report_dir, index)
    elif source.report_dir is not None and source.report_format == REPORT_PBIR_LEGACY:
        _pbir_legacy_index(source.report_dir, index)
    return dict(sorted(index.items()))
