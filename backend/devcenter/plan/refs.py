"""DAX references with token positions, and the token-exact rewrite (technical design section 6.5).

The scanner reads the lexer tokens of ``backend.dax.parser.dax_token_spans``.
Each reference keeps the exact positions of its table token and its name
token. A rewrite changes the text only at these positions. All other text
(comments, whitespace, letter case, other tokens) stays byte-equal.

A ``ModelIndex`` resolves a reference to one object of one source:

- ``T[X]``: the column ``T/X``, else the measure ``X``, else the report measure ``T/X``.
- ``[X]``: the measure ``X``, else the column ``X`` of the home table, else the
  report measure ``X``, else the one column ``X`` of the model. A name that the
  same expression makes as a string (for example ``"@Total"`` in ADDCOLUMNS)
  is a local name.
- ``'T'``: the table ``T``. A bare identifier is a table only when the table exists.
- ``F(``: the user-defined function ``F`` when it exists.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Callable, Iterable, Mapping, Sequence

from backend.dax.parser import DaxSpanToken, dax_token_spans
from backend.devcenter.alignment.keys import fold
from backend.devcenter.compare.extract import CompareObject

TABLE = "table"
COLUMN = "column"
MEASURE = "measure"
REPORT_MEASURE = "report_measure"
FUNCTION = "function"

_SIMPLE_TABLE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class RawRef:
    """One reference as written. ``table`` and ``name`` are unquoted."""

    form: str  # "qualified", "bracket", "table", "bare", "call"
    table: str | None
    name: str | None
    table_token: DaxSpanToken | None
    name_token: DaxSpanToken | None


@dataclass(frozen=True)
class Scan:
    refs: tuple[RawRef, ...]
    local_names: frozenset[str]
    failed: bool


def _unquote_table(text: str) -> str:
    return text[1:-1].replace("''", "'") if len(text) >= 2 and text[0] == "'" else text


def _bracket_name(text: str) -> str:
    return text[1:-1].replace("]]", "]")


def scan(text: str | None) -> Scan:
    """Give the references of a DAX text in text order."""

    if not text:
        return Scan((), frozenset(), False)
    tokens, failed = dax_token_spans(str(text))
    refs: list[RawRef] = []
    variables: set[str] = set()
    local: set[str] = set()
    for position, token in enumerate(tokens):
        if token.kind == "STRING":
            local.add(fold(token.text[1:-1].replace('""', '"')))
        if token.kind == "IDENTIFIER" and position > 0 and tokens[position - 1].kind == "VAR":
            variables.add(fold(token.text))
    skip = -1
    for position, token in enumerate(tokens):
        if position <= skip:
            continue
        following = tokens[position + 1] if position + 1 < len(tokens) else None
        previous = tokens[position - 1] if position > 0 else None
        if token.kind in {"TABLE_NAME", "IDENTIFIER"} and following is not None and following.kind == "BRACKET_IDENT":
            refs.append(RawRef("qualified", _unquote_table(token.text), _bracket_name(following.text), token, following))
            skip = position + 1
        elif token.kind == "BRACKET_IDENT":
            refs.append(RawRef("bracket", None, _bracket_name(token.text), None, token))
        elif token.kind == "TABLE_NAME":
            refs.append(RawRef("table", _unquote_table(token.text), None, token, None))
        elif token.kind == "IDENTIFIER":
            if following is not None and following.kind == "LPAREN":
                refs.append(RawRef("call", None, token.text, None, token))
            elif fold(token.text) not in variables and not (previous is not None and previous.kind == "VAR"):
                refs.append(RawRef("bare", token.text, None, token, None))
    return Scan(tuple(refs), frozenset(local), failed)


@dataclass(frozen=True)
class Resolved:
    """One resolved reference: the object kind and the source key, or ``key`` None when it does not resolve."""

    raw: RawRef
    kind: str
    key: str | None


@dataclass
class ModelIndex:
    """The names of the model objects (and report measures) of one source, for reference resolution."""

    tables: dict[str, CompareObject] = field(default_factory=dict)
    measures: dict[str, CompareObject] = field(default_factory=dict)
    columns: dict[tuple[str, str], CompareObject] = field(default_factory=dict)
    columns_by_name: dict[str, list[CompareObject]] = field(default_factory=dict)
    functions: dict[str, CompareObject] = field(default_factory=dict)
    report_measures: dict[tuple[str, str], CompareObject] = field(default_factory=dict)
    report_measures_by_name: dict[str, list[CompareObject]] = field(default_factory=dict)

    @classmethod
    def build(cls, model: Iterable[CompareObject], report: Iterable[CompareObject] = ()) -> "ModelIndex":
        index = cls()
        for item in model:
            if item.kind == "table":
                index.tables[fold(item.name)] = item
            elif item.kind == "measure":
                index.measures.setdefault(fold(item.name), item)
            elif item.kind == "column":
                index.columns[(fold(item.table), fold(item.name))] = item
                index.columns_by_name.setdefault(fold(item.name), []).append(item)
            elif item.kind == "function":
                index.functions[fold(item.name)] = item
        for item in report:
            if item.kind == "report_measure":
                index.report_measures[(fold(item.table), fold(item.name))] = item
                index.report_measures_by_name.setdefault(fold(item.name), []).append(item)
        return index

    def resolve(self, raw: RawRef, home_table: str | None, local_names: frozenset[str] = frozenset()) -> Resolved | None:
        """Resolve one reference. None means "not a model reference" (a variable, a local name, a DAX function)."""

        if raw.form == "qualified":
            column = self.columns.get((fold(raw.table), fold(raw.name)))
            if column is not None:
                return Resolved(raw, COLUMN, column.source_key)
            measure = self.measures.get(fold(raw.name))
            if measure is not None:
                return Resolved(raw, MEASURE, measure.source_key)
            report = self.report_measures.get((fold(raw.table), fold(raw.name)))
            if report is not None:
                return Resolved(raw, REPORT_MEASURE, report.source_key)
            return Resolved(raw, COLUMN, None)
        if raw.form == "bracket":
            name = fold(raw.name)
            if name in self.measures:
                return Resolved(raw, MEASURE, self.measures[name].source_key)
            if home_table is not None and (fold(home_table), name) in self.columns:
                return Resolved(raw, COLUMN, self.columns[(fold(home_table), name)].source_key)
            reports = self.report_measures_by_name.get(name, [])
            if len(reports) == 1:
                return Resolved(raw, REPORT_MEASURE, reports[0].source_key)
            candidates = self.columns_by_name.get(name, [])
            if len(candidates) == 1:
                return Resolved(raw, COLUMN, candidates[0].source_key)
            if candidates or name in local_names or name.startswith("@"):
                # Two or more tables have the column (row context), or the expression makes the name.
                return None
            return Resolved(raw, MEASURE, None)
        if raw.form in {"table", "bare"}:
            table = self.tables.get(fold(raw.table))
            if table is not None:
                return Resolved(raw, TABLE, table.source_key)
            return Resolved(raw, TABLE, None) if raw.form == "table" else None
        if raw.form == "call":
            function = self.functions.get(fold(raw.name))
            return Resolved(raw, FUNCTION, function.source_key) if function is not None else None
        return None

    def references(self, text: str | None, home_table: str | None) -> tuple[list[Resolved], bool]:
        """Give the resolved references of a text, and True when the lexer failed."""

        found = scan(text)
        resolved = [item for item in (self.resolve(raw, home_table, found.local_names) for raw in found.refs) if item is not None]
        return resolved, found.failed


# Token-exact rewrite ---------------------------------------------------------------


def table_token(old_token: str, name: str) -> str:
    """Write a table name in the style of the old token: keep the quotes, or add them when the name needs them."""

    if old_token.startswith("'") or not _SIMPLE_TABLE.match(name):
        return "'" + name.replace("'", "''") + "'"
    return name


def bracket_token(name: str) -> str:
    return "[" + name.replace("]", "]]") + "]"


def apply_replacements(text: str, replacements: Mapping[tuple[int, int], str]) -> str:
    """Replace each ``(start, end)`` span with its new text. The spans must not overlap."""

    result = text
    for (start, end), value in sorted(replacements.items(), reverse=True):
        result = result[:start] + value + result[end:]
    return result


# The mapper gives the new (table, name) of a resolved reference, or None to keep the reference.
Mapper = Callable[[Resolved], "tuple[str | None, str | None] | None"]


def rewrite(text: str, resolved: Sequence[Resolved], mapper: Mapper) -> tuple[str, int]:
    """Rewrite the references that the mapper changes. Give the new text and the count of changed tokens."""

    replacements: dict[tuple[int, int], str] = {}
    for item in resolved:
        target = mapper(item)
        if target is None:
            continue
        new_table, new_name = target
        raw = item.raw
        if raw.table_token is not None and new_table is not None and fold(new_table) != fold(raw.table):
            replacements[(raw.table_token.start, raw.table_token.end)] = table_token(raw.table_token.text, new_table)
        if raw.name_token is not None and new_name is not None and raw.form != "call" and fold(new_name) != fold(raw.name):
            replacements[(raw.name_token.start, raw.name_token.end)] = bracket_token(new_name)
        if raw.form == "call" and new_name is not None and fold(new_name) != fold(raw.name) and raw.name_token is not None:
            replacements[(raw.name_token.start, raw.name_token.end)] = new_name
    if not replacements:
        return text, 0
    return apply_replacements(text, replacements), len(replacements)
