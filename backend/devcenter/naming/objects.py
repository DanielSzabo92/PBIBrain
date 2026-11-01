"""The named objects of a model and a report that the naming rules check (technical design section 5).

In scope: tables, data columns, calculated columns, calculated tables,
measures, hierarchies, calculation groups, and report measures. The reader
uses the block helpers of ``backend.devcenter.sources.objects`` for TMDL.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Iterable, Iterator

from backend.devcenter.sources.kinds import MODEL_TMDL, MODEL_TMSL, REPORT_PBIR, LocalSource
from backend.devcenter.sources.objects import _blocks, _declaration, _unquote

TABLE = "table"
DATA_COLUMN = "data_column"
CALCULATED_COLUMN = "calculated_column"
CALCULATED_TABLE = "calculated_table"
MEASURE = "measure"
HIERARCHY = "hierarchy"
CALCULATION_GROUP = "calculation_group"
REPORT_MEASURE = "report_measure"
# The object types that a rule can have. A report measure uses the measure rules.
RULE_OBJECT_TYPES = (TABLE, DATA_COLUMN, CALCULATED_COLUMN, CALCULATED_TABLE, MEASURE, HIERARCHY, CALCULATION_GROUP)
OBJECT_TYPES = RULE_OBJECT_TYPES + (REPORT_MEASURE,)
TABLE_TYPES = (TABLE, CALCULATED_TABLE, CALCULATION_GROUP)
COLUMN_TYPES = (DATA_COLUMN, CALCULATED_COLUMN)

FORMAT_PERCENT = "percent"
FORMAT_CURRENCY = "currency"
FORMAT_KINDS = (FORMAT_PERCENT, FORMAT_CURRENCY)
_CURRENCY_MARKS = ("$", "€", "£", "¥", "₹", "₩", "CHF", "Currency")


@dataclass(frozen=True)
class NamedObject:
    """One named object. ``table`` is the home table (None for a table)."""

    object_type: str
    name: str
    table: str | None = None
    display_folder: str | None = None
    format_kind: str | None = None

    @property
    def row_key(self) -> str:
        """The row key form of ``backend.devcenter.sources.objects``."""

        if self.object_type in TABLE_TYPES:
            return f"table:{self.name}"
        kind = "column" if self.object_type in COLUMN_TYPES else self.object_type
        return f"{kind}:{self.table}/{self.name}"

    def view(self) -> dict[str, Any]:
        return {"object_type": self.object_type, "name": self.name, "table": self.table, "row_key": self.row_key}


def rule_type(object_type: str) -> str:
    """The rule object type of an object type. A report measure uses the measure rules."""

    return MEASURE if object_type == REPORT_MEASURE else object_type


def format_kind(format_string: str | None) -> str | None:
    """Give "percent" or "currency" for a format string, or None."""

    if not format_string:
        return None
    text = format_string.strip().strip('"')
    if "%" in text:
        return FORMAT_PERCENT
    if any(mark in text for mark in _CURRENCY_MARKS):
        return FORMAT_CURRENCY
    return None


def _property(lines: Iterable[str], name: str) -> str | None:
    prefix = name + ":"
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(prefix):
            return _unquote(stripped[len(prefix):].strip())
    return None


def _own_lines(block: list[str], level: int) -> list[str]:
    """The property lines of a block at the next tab level (no child blocks)."""

    own: list[str] = []
    for line in block[1:]:
        if line.strip() and len(line) - len(line.lstrip("\t")) == level + 1:
            own.append(line)
    return own


def _has_expression(header: str) -> bool:
    """Give True when a declaration line has "= <expression>" after the object name."""

    rest = header.partition(" ")[2].strip()
    if rest.startswith("'"):
        index = 1
        while index < len(rest):
            if rest[index] == "'":
                if rest[index + 1:index + 2] == "'":
                    index += 2
                    continue
                break
            index += 1
        rest = rest[index + 1:]
    return "=" in rest


def _tmdl_table(lines: list[str]) -> Iterator[NamedObject]:
    for start, end in _blocks(lines, 0):
        declaration = _declaration(lines[start])
        if declaration is None or declaration[0] != "table":
            continue
        table = declaration[1]
        body = lines[start + 1:end]
        children: list[tuple[str, str, list[str], str]] = []
        is_group = False
        is_calculated = False
        for child_start, child_end in _blocks(body, 1):
            child = _declaration(body[child_start])
            header = body[child_start].strip()
            if child is None:
                if header == "calculationGroup":
                    is_group = True
                continue
            keyword, name = child
            if keyword == "calculationGroup":
                is_group = True
            elif keyword == "partition" and header.rstrip().endswith("= calculated"):
                is_calculated = True
            children.append((keyword, name, body[child_start:child_end], header))
        table_type = CALCULATION_GROUP if is_group else CALCULATED_TABLE if is_calculated else TABLE
        yield NamedObject(table_type, table)
        for keyword, name, block, header in children:
            own = _own_lines(block, 1)
            folder = _property(own, "displayFolder")
            kind = format_kind(_property(own, "formatString"))
            if keyword == "measure":
                yield NamedObject(MEASURE, name, table, folder, kind)
            elif keyword in {"column", "calculatedColumn"} and not is_group:
                calculated = keyword == "calculatedColumn" or _has_expression(header) or _property(own, "type") == "calculated"
                yield NamedObject(CALCULATED_COLUMN if calculated else DATA_COLUMN, name, table, folder, kind)
            elif keyword == "hierarchy":
                yield NamedObject(HIERARCHY, name, table, folder)


def _tmdl_objects(definition: Path) -> list[NamedObject]:
    found: list[NamedObject] = []
    for path in sorted(definition.rglob("*.tmdl")):
        text = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
        found.extend(_tmdl_table(text.split("\n")))
    return found


def _named(items: Any) -> Iterator[dict[str, Any]]:
    for item in items or []:
        if isinstance(item, dict) and isinstance(item.get("name"), str):
            yield item


def _tmsl_objects(path: Path) -> list[NamedObject]:
    document = json.loads(path.read_text(encoding="utf-8-sig"))
    model = document.get("model", document) if isinstance(document, dict) else {}
    found: list[NamedObject] = []
    for table in _named(model.get("tables")):
        name = table["name"]
        is_group = isinstance(table.get("calculationGroup"), dict)
        is_calculated = any(isinstance(part.get("source"), dict) and part["source"].get("type") == "calculated"
                            for part in _named(table.get("partitions")))
        found.append(NamedObject(CALCULATION_GROUP if is_group else CALCULATED_TABLE if is_calculated else TABLE, name))
        for measure in _named(table.get("measures")):
            found.append(NamedObject(MEASURE, measure["name"], name, measure.get("displayFolder"), format_kind(measure.get("formatString"))))
        if not is_group:
            for column in _named(table.get("columns")):
                if column.get("type") == "rowNumber":
                    continue
                kind = CALCULATED_COLUMN if column.get("type") == "calculated" else DATA_COLUMN
                found.append(NamedObject(kind, column["name"], name, column.get("displayFolder"), format_kind(column.get("formatString"))))
        for hierarchy in _named(table.get("hierarchies")):
            found.append(NamedObject(HIERARCHY, hierarchy["name"], name, hierarchy.get("displayFolder")))
    return found


def _report_measures(report_dir: Path) -> list[NamedObject]:
    path = report_dir / "definition" / "reportExtensions.json"
    if not path.is_file():
        return []
    document = json.loads(path.read_text(encoding="utf-8-sig"))
    found: list[NamedObject] = []
    for entity in _named(document.get("entities") if isinstance(document, dict) else None):
        for measure in _named(entity.get("measures")):
            found.append(NamedObject(REPORT_MEASURE, measure["name"], entity["name"], measure.get("displayFolder"),
                                     format_kind(measure.get("formatString"))))
    return found


def model_objects(source: LocalSource) -> list[NamedObject]:
    """The named model objects of a source, in a fixed order."""

    if source.model_dir is not None and source.model_format == MODEL_TMDL:
        found = _tmdl_objects(source.model_dir / "definition")
    elif source.model_dir is not None and source.model_format == MODEL_TMSL:
        bim = source.root if source.root.is_file() else source.model_dir / "model.bim"
        found = _tmsl_objects(bim)
    else:
        found = []
    return sorted(found, key=lambda item: (item.object_type, item.table or "", item.name))


def report_objects(source: LocalSource | None) -> list[NamedObject]:
    """The report measures of a PBIR report (the clash check uses them)."""

    if source is None or source.report_dir is None or source.report_format != REPORT_PBIR:
        return []
    return sorted(_report_measures(source.report_dir), key=lambda item: (item.table or "", item.name))
