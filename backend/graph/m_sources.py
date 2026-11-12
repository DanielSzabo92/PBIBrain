"""Static, best-effort reading of the data sources that a Power Query (M) text names (issue #10).

The M text is tokenised, never evaluated. Only the common connector calls are read, with
text literals, ``let`` steps that hold a text literal, and model parameters substituted for
their arguments. A connector call that cannot be read this way, or a function call that is not
a known connector and not a standard library function, makes the result ``not_checked``:
the source is never guessed.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any
from collections.abc import Iterable, Mapping

STATUS_READ = "read"
STATUS_NOT_CHECKED = "not_checked"
STATUS_NO_SOURCE = "no_source"
REASON_M_NOT_READ = "m_not_read"

# Database connectors: (server, database) arguments, then {[Schema=..., Item=...]} navigation.
_DATABASE = {
    "Sql.Database": "sql", "Sql.Databases": "sql", "PostgreSQL.Database": "postgresql", "MySQL.Database": "mysql",
    "Oracle.Database": "oracle", "AnalysisServices.Database": "analysis_services", "Teradata.Database": "teradata",
}
# Fabric and Power BI items addressed by ids in navigation records.
_NAVIGATED = {
    "Lakehouse.Contents": "lakehouse", "PowerPlatform.Dataflows": "dataflow", "PowerBI.Dataflows": "dataflow",
    "Fabric.Warehouse": "warehouse",
}
# Calls whose first argument is a path or URL.
_LOCATION = {
    "File.Contents": "file", "Web.Contents": "web", "Folder.Files": "folder", "Folder.Contents": "folder",
    "SharePoint.Files": "sharepoint", "SharePoint.Contents": "sharepoint", "SharePoint.Tables": "sharepoint",
    "AzureStorage.DataLake": "adls", "AzureStorage.Blobs": "blob", "OData.Feed": "odata",
}
# Calls that read the format of a binary; they name no source of their own.
_FORMAT = {"Csv.Document": "csv", "Excel.Workbook": "excel", "Json.Document": "json", "Xml.Tables": "xml",
           "Xml.Document": "xml", "Parquet.Document": "parquet", "Lines.FromBinary": "text"}
# Function families of the M standard library that read no external data.
_LIBRARY = frozenset({
    "Table", "List", "Text", "Number", "Date", "DateTime", "DateTimeZone", "Time", "Duration", "Record", "Value",
    "Splitter", "Combiner", "Replacer", "Comparer", "Expression", "Binary", "BinaryFormat", "Lines", "Uri",
    "Character", "Byte", "Int8", "Int16", "Int32", "Int64", "Single", "Double", "Decimal", "Currency", "Percentage",
    "Logical", "Function", "Type", "Order", "Occurrence", "RelativePosition", "JoinKind", "JoinAlgorithm",
    "JoinSide", "ExtraValues", "MissingField", "Culture", "Precision", "Cube", "Diagnostics", "Error", "Action",
    "Variable", "Geography", "Geometry", "Embedded", "Compression", "Json", "Xml", "Csv", "QuoteStyle",
    "GroupKind", "LimitClauseKind", "RoundingMode", "TraceLevel", "Day", "Guid", "Parquet",
})
# Navigation record keys and the source fields they fill.
_NAV_KEYS = {
    "schema": "schema", "item": "object", "name": "object", "id": "object", "entity": "object",
    "workspaceid": "workspace_id", "lakehouseid": "lakehouse_id", "dataflowid": "dataflow_id",
    "warehouseid": "warehouse_id",
}
_IDENTITY_FIELDS = ("server", "database", "schema", "object", "path", "url", "workspace_id", "lakehouse_id",
                    "dataflow_id", "warehouse_id")

_TOKEN = re.compile(
    r'(?P<ws>\s+)|(?P<line>//[^\n]*)|(?P<block>/\*.*?(?:\*/|$))|(?P<qid>#"(?:[^"]|"")*")|(?P<str>"(?:[^"]|"")*")'
    r'|(?P<id>[A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)*)|(?P<num>\d+(?:\.\d+)?)|(?P<op>=>|<=|>=|<>|[^\s])',
    re.DOTALL,
)


@dataclass(slots=True)
class Token:
    kind: str
    text: str

    @property
    def value(self) -> str:
        if self.kind == "str":
            return self.text[1:-1].replace('""', '"')
        if self.kind == "qid":
            return self.text[2:-1].replace('""', '"')
        return self.text


@dataclass(slots=True)
class MSourceResult:
    status: str
    sources: list[dict[str, Any]] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    parameters: list[str] = field(default_factory=list)


def tokenize(text: str) -> list[Token]:
    tokens: list[Token] = []
    for match in _TOKEN.finditer(text or ""):
        kind = match.lastgroup or "op"
        if kind in {"ws", "line", "block"}:
            continue
        tokens.append(Token(kind, match.group()))
    return tokens


def parameter_value(text: Any) -> str | None:
    """The text value of a model parameter: an M text literal, optionally followed by ``meta [...]``."""

    tokens = tokenize(str(text or ""))
    if tokens and tokens[0].kind == "str" and (len(tokens) == 1 or tokens[1].text == "meta"):
        return tokens[0].value
    return None


def _close(tokens: list[Token], start: int) -> int:
    """Index of the bracket that closes the one at ``start``."""

    pairs = {"(": ")", "[": "]", "{": "}"}
    depth = 0
    for index in range(start, len(tokens)):
        text = tokens[index].text if tokens[index].kind == "op" else ""
        if text in pairs:
            depth += 1
        elif text in pairs.values():
            depth -= 1
            if depth == 0:
                return index
    return len(tokens) - 1


def _split(tokens: list[Token]) -> list[list[Token]]:
    """Split tokens at the commas of the outer level."""

    parts: list[list[Token]] = [[]]
    depth = 0
    for token in tokens:
        text = token.text if token.kind == "op" else ""
        if text in "([{" and text:
            depth += 1
        elif text in ")]}" and text:
            depth -= 1
        if text == "," and depth == 0:
            parts.append([])
        else:
            parts[-1].append(token)
    return [part for part in parts if part]


class _Reader:
    def __init__(self, text: str, parameters: Mapping[str, str]) -> None:
        self.tokens = tokenize(text)
        self.parameters = parameters
        self.used_parameters: set[str] = set()
        # let steps that hold one text literal: Server = "x",
        self.steps: dict[str, str] = {}
        for index in range(len(self.tokens) - 3):
            name, equals, value, after = self.tokens[index:index + 4]
            if name.kind in {"id", "qid"} and equals.text == "=" and value.kind == "str" and after.text in {",", "in"}:
                self.steps[name.value] = value.value

    def value(self, part: list[Token]) -> tuple[bool, str | None]:
        """(readable, value) of one argument."""

        if len(part) == 1:
            token = part[0]
            if token.kind == "str":
                return True, token.value
            if token.text == "null":
                return True, None
            if token.kind in {"id", "qid"}:
                if token.value in self.steps:
                    return True, self.steps[token.value]
                if token.value in self.parameters:
                    self.used_parameters.add(token.value)
                    return True, self.parameters[token.value]
        if part and all(token.kind == "str" or token.text == "&" for token in part):
            return True, "".join(token.value for token in part if token.kind == "str")
        return False, None

    def navigation(self, start: int, end: int) -> list[dict[str, str | None]]:
        """The {[key = value, ...]} records between two token indexes."""

        records: list[dict[str, str | None]] = []
        index = start
        while index < end - 1:
            if self.tokens[index].text == "{" and self.tokens[index + 1].text == "[":
                close = _close(self.tokens, index + 1)
                record: dict[str, str | None] = {}
                for part in _split(self.tokens[index + 2:close]):
                    if len(part) >= 3 and part[1].text == "=" and part[0].kind in {"id", "qid"}:
                        readable, value = self.value(part[2:])
                        record[part[0].value.casefold()] = value if readable else "\x00"
                records.append(record)
                index = close
            index += 1
        return records


def _location_name(value: str) -> str:
    stripped = value.rstrip("/\\")
    return re.split(r"[/\\]", stripped)[-1] or stripped


def source_name(source: Mapping[str, Any]) -> str:
    """A short, readable name for a data source node."""

    kind = source.get("kind")
    if kind in set(_DATABASE.values()):
        parts = [source.get("database"), source.get("schema"), source.get("object")]
        named = ".".join(str(part) for part in parts if part)
        return named or str(source.get("server") or kind)
    if source.get("object"):
        return str(source["object"])
    if source.get("path"):
        return _location_name(str(source["path"]))
    if source.get("url"):
        return re.sub(r"^\w+://", "", str(source["url"])).rstrip("/")
    return str(source.get("lakehouse_id") or source.get("dataflow_id") or source.get("warehouse_id") or kind)


def source_key(source: Mapping[str, Any]) -> str:
    """The identity of a source object, equal for two models that read the same object."""

    values = [str(source.get("kind") or "")]
    for key in _IDENTITY_FIELDS:
        value = source.get(key)
        values.append("" if value is None else str(value).strip().casefold().replace("\\", "/"))
    if source.get("native_query"):
        values.append("query:" + hashlib.sha256(str(source.get("query") or "").encode("utf-8")).hexdigest()[:12])
    return "|".join(values)


def data_source_id(source: Mapping[str, Any]) -> str:
    return "data_source:" + hashlib.sha256(source_key(source).encode("utf-8")).hexdigest()[:32]


def read_m_sources(text: Any, parameters: Mapping[str, str] | None = None) -> MSourceResult:
    """Read the data sources that one M expression names."""

    reader = _Reader(str(text or ""), parameters or {})
    tokens = reader.tokens
    calls = [index for index in range(len(tokens) - 1)
             if tokens[index].kind == "id" and "." in tokens[index].text and tokens[index + 1].text == "("]
    connector_calls = [index for index in calls if tokens[index].text in _DATABASE or tokens[index].text in _NAVIGATED
                       or tokens[index].text in _LOCATION]
    sources: list[dict[str, Any]] = []
    reasons: list[str] = []
    formats: dict[int, str] = {}
    for index in calls:
        name = tokens[index].text
        if name in _FORMAT:
            close = _close(tokens, index + 1)
            for inner in connector_calls:
                if index < inner < close:
                    formats[inner] = _FORMAT[name]
        elif name not in _DATABASE and name not in _NAVIGATED and name not in _LOCATION and name.split(".", 1)[0] not in _LIBRARY:
            reasons.append(f"{name} is not a connector that Brain reads")
    for position, index in enumerate(connector_calls):
        name = tokens[index].text
        close = _close(tokens, index + 1)
        arguments = _split(tokens[index + 2:close])
        following = connector_calls[position + 1] if position + 1 < len(connector_calls) else len(tokens)
        if name in _LOCATION and any(index < other < close for other in connector_calls):
            continue  # an outer location call wraps an inner one (Web.Contents(File.Contents(...)) is rare); read the inner.
        source: dict[str, Any] = {"connector": name}
        if name in _DATABASE:
            source["kind"] = _DATABASE[name]
            readable, server = reader.value(arguments[0]) if arguments else (False, None)
            if not readable or not server:
                reasons.append(f"the server of {name} is not a text or a parameter")
                continue
            source["server"] = server
            if len(arguments) > 1 and name != "Sql.Databases" and name != "Oracle.Database":
                readable, database = reader.value(arguments[1])
                if not readable:
                    reasons.append(f"the database of {name} is not a text or a parameter")
                    continue
                source["database"] = database
            options = arguments[-1] if len(arguments) > 2 or (name in {"Sql.Databases", "Oracle.Database"} and len(arguments) > 1) else []
            if options and options[0].text == "[":
                for part in _split(options[1:-1]):
                    if len(part) >= 3 and part[0].value.casefold() == "query":
                        source["native_query"] = True
                        source["query"] = reader.value(part[2:])[1]
        elif name in _NAVIGATED:
            source["kind"] = _NAVIGATED[name]
        else:
            source["kind"] = _LOCATION[name]
            readable, location = reader.value(arguments[0]) if arguments else (False, None)
            if not readable or not location:
                reasons.append(f"the location of {name} is not a text or a parameter")
                continue
            source["url" if re.match(r"^\w+://", location) else "path"] = location
            if index in formats:
                source["format"] = formats[index]
        unreadable = False
        for record in reader.navigation(close, following):
            for key, value in record.items():
                field_name = _NAV_KEYS.get(key)
                if field_name is None:
                    continue
                if field_name == "object" and source["kind"] in set(_DATABASE.values()) and key == "name" and "database" not in source:
                    field_name = "database"
                if value == "\x00":
                    unreadable = True
                    continue
                source.setdefault(field_name, value)
        if unreadable:
            reasons.append(f"a navigation step after {name} is not a text or a parameter")
        if source["kind"] in {"lakehouse", "dataflow", "warehouse"} and not source.get("object") and not unreadable:
            reasons.append(f"the item that {name} reads is not named")
        sources.append(source)
    for index in calls:
        if tokens[index].text == "Value.NativeQuery":
            for source in sources:
                if source["kind"] in set(_DATABASE.values()):
                    source["native_query"] = True
                    close = _close(tokens, index + 1)
                    arguments = _split(tokens[index + 2:close])
                    source["query"] = reader.value(arguments[1])[1] if len(arguments) > 1 else None
    unique: dict[str, dict[str, Any]] = {}
    for source in sources:
        unique.setdefault(source_key(source), source)
    status = STATUS_NOT_CHECKED if reasons else STATUS_READ if unique else STATUS_NO_SOURCE
    return MSourceResult(status, list(unique.values()), sorted(set(reasons)), sorted(reader.used_parameters))


def entity_source(base: Iterable[Mapping[str, Any]], *, schema: Any, entity: Any) -> list[dict[str, Any]]:
    """The sources of a Direct Lake entity partition: its expression source's location, narrowed to the table."""

    result = []
    for item in base:
        source = {key: value for key, value in item.items() if key not in {"object", "native_query", "query"}}
        if schema:
            source["schema"] = str(schema)
        if entity:
            source["object"] = str(entity)
        result.append(source)
    return result
