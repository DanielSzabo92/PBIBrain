"""Advisory change rules for an agent's object proposal: what the change does to the objects around it.

The plan check (``proposals._object_check``) already refuses what cannot work (a DAX parse error,
a missing object, a name clash) and the impact engine lists the dependents of the changed row.
These rules add the meaning of the change that neither of them sees:

- ``result_type_change``: a measure or calculated column now returns another kind of value
  (number, text, true/false, date, table). Visuals that sum, chart or format it, and measures that
  do arithmetic with it, can break or show errors.
- ``function_signature``: a user-defined function now takes other parameters; each call site
  whose argument count no longer fits is listed.
- ``function_result_type``: a function now returns another kind of value; its callers are listed.
- ``source_column_dropped``: a partition's M query no longer names a source column that a column
  of the table reads, so the refresh fails for that column.
- ``query_dependents``: a shared M expression (query or parameter) changed; the tables whose
  queries use it are listed.
- ``calc_item_without_measure``: a calculation item that does not use ``SELECTEDMEASURE()``
  replaces every measure it is applied to with the same value.
- ``format_string_ignored``: a measure now returns text, so its number format no longer applies.

Each rule is ``{rule, level, message, objects}`` with ``level`` "breaks" (the change can break
the listed objects) or "warning" (check the listed objects). The rules are advisory: they never
refuse a proposal, they put it in front of the user with the reason. The DAX type inference is
coarse on purpose: when a kind is not clear it is "unknown" and no rule fires.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping, Sequence

NUMBER, TEXT, BOOLEAN, DATETIME, TABLE, BLANK, UNKNOWN, MIXED = (
    "number", "text", "true/false", "date", "table", "blank", "unknown", "mixed")
SCALAR_KINDS = (NUMBER, TEXT, BOOLEAN, DATETIME)
OBJECTS_MAX = 20

_NUMBER_FUNCTIONS = {
    "SUM", "SUMX", "AVERAGE", "AVERAGEX", "AVERAGEA", "COUNT", "COUNTA", "COUNTAX", "COUNTX", "COUNTROWS", "COUNTBLANK",
    "DISTINCTCOUNT", "DISTINCTCOUNTNOBLANK", "DIVIDE", "ABS", "ROUND", "ROUNDUP", "ROUNDDOWN", "MROUND", "INT", "TRUNC",
    "MOD", "POWER", "SQRT", "EXP", "LN", "LOG", "LOG10", "SIGN", "CEILING", "FLOOR", "RANKX", "RANK", "MEDIAN", "MEDIANX",
    "PERCENTILE.INC", "PERCENTILE.EXC", "PERCENTILEX.INC", "PERCENTILEX.EXC", "STDEV.S", "STDEV.P", "STDEVX.S",
    "STDEVX.P", "VAR.S", "VAR.P", "VARX.S", "VARX.P", "PRODUCT", "PRODUCTX", "GEOMEAN", "GEOMEANX", "YEAR", "MONTH",
    "DAY", "HOUR", "MINUTE", "SECOND", "WEEKDAY", "WEEKNUM", "QUARTER", "LEN", "SEARCH", "FIND", "DATEDIFF", "VALUE",
    "TOTALYTD", "TOTALQTD", "TOTALMTD", "CURRENCY", "RAND", "RANDBETWEEN", "PI", "QUOTIENT", "GCD", "LCM", "EVEN", "ODD",
    "FACT", "CONVERT", "YEARFRAC", "NETWORKDAYS", "PATHLENGTH", "OPENINGBALANCEMONTH", "CLOSINGBALANCEMONTH",
    "OPENINGBALANCEQUARTER", "CLOSINGBALANCEQUARTER", "OPENINGBALANCEYEAR", "CLOSINGBALANCEYEAR", "ROWNUMBER",
}
_TEXT_FUNCTIONS = {
    "FORMAT", "CONCATENATE", "CONCATENATEX", "LEFT", "RIGHT", "MID", "UPPER", "LOWER", "TRIM", "SUBSTITUTE", "REPLACE",
    "REPT", "FIXED", "COMBINEVALUES", "UNICHAR", "PATH", "PATHITEM", "PATHITEMREVERSE", "USERNAME", "USERPRINCIPALNAME",
    "USEROBJECTID", "NAMEOF", "TOJSON", "TOCSV", "SELECTEDMEASURENAME", "SELECTEDMEASUREFORMATSTRING",
}
_BOOLEAN_FUNCTIONS = {
    "ISBLANK", "ISERROR", "AND", "OR", "NOT", "HASONEVALUE", "HASONEFILTER", "ISFILTERED", "ISCROSSFILTERED", "ISINSCOPE",
    "CONTAINSSTRING", "CONTAINSSTRINGEXACT", "CONTAINS", "CONTAINSROW", "ISNUMBER", "ISTEXT", "ISNONTEXT", "ISLOGICAL",
    "ISEMPTY", "EXACT", "ISEVEN", "ISODD", "TRUE", "FALSE", "ISSELECTEDMEASURE", "ISONORAFTER", "PATHCONTAINS",
    "USERCULTURE",
}
_DATETIME_FUNCTIONS = {
    "DATE", "TODAY", "NOW", "UTCNOW", "UTCTODAY", "EOMONTH", "EDATE", "DATEVALUE", "TIME", "TIMEVALUE", "FIRSTDATE",
    "LASTDATE", "STARTOFMONTH", "ENDOFMONTH", "STARTOFQUARTER", "ENDOFQUARTER", "STARTOFYEAR", "ENDOFYEAR",
}
_TABLE_FUNCTIONS = {
    "FILTER", "ALL", "ALLEXCEPT", "ALLSELECTED", "ALLNOBLANKROW", "VALUES", "DISTINCT", "SUMMARIZE", "SUMMARIZECOLUMNS",
    "ADDCOLUMNS", "SELECTCOLUMNS", "CALCULATETABLE", "DATESYTD", "DATESQTD", "DATESMTD", "DATESBETWEEN", "DATESINPERIOD",
    "SAMEPERIODLASTYEAR", "PREVIOUSYEAR", "PREVIOUSMONTH", "PREVIOUSQUARTER", "PREVIOUSDAY", "NEXTYEAR", "NEXTMONTH",
    "NEXTQUARTER", "NEXTDAY", "PARALLELPERIOD", "DATEADD", "TOPN", "UNION", "INTERSECT", "EXCEPT", "GENERATE",
    "GENERATEALL", "CROSSJOIN", "DATATABLE", "GENERATESERIES", "CALENDAR", "CALENDARAUTO", "TREATAS", "ROW",
    "NATURALINNERJOIN", "NATURALLEFTOUTERJOIN", "RELATEDTABLE", "KEEPFILTERS", "REMOVEFILTERS", "WINDOW", "OFFSET",
    "INDEX", "TOPNSKIP", "SUBSTITUTEWITHINDEX", "GROUPBY", "DETAILROWS",
}
_DATA_TYPES = {"string": TEXT, "int64": NUMBER, "double": NUMBER, "decimal": NUMBER, "datetime": DATETIME, "boolean": BOOLEAN}

_COMMENT = re.compile(r"//[^\n]*|--[^\n]*|/\*.*?\*/", re.S)
_STRING = re.compile(r'"(?:[^"]|"")*"')
_QUOTED_NAME = re.compile(r"'(?:[^']|'')*'")


def _clean(text: str) -> str:
    """The DAX text without comments, with each string literal as ``"s"`` and each quoted table name as ``T``."""

    out, i = [], 0
    while i < len(text):
        match = _STRING.match(text, i) or _QUOTED_NAME.match(text, i)
        if match:
            out.append('"s"' if match.group(0).startswith('"') else "T")
            i = match.end()
            continue
        comment = _COMMENT.match(text, i)
        if comment:
            out.append(" ")
            i = comment.end()
            continue
        out.append(text[i])
        i += 1
    return "".join(out)


def _split_top(text: str, separator: str = ",") -> list[str]:
    """``text`` split on ``separator`` outside brackets."""

    parts, depth, start = [], 0, 0
    for i, char in enumerate(text):
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        elif char == separator and depth == 0:
            parts.append(text[start:i])
            start = i + 1
    parts.append(text[start:])
    return [part.strip() for part in parts]


def _top_level(text: str) -> str:
    """The text with everything inside brackets removed, to look for operators at the top level."""

    out, depth = [], 0
    for char in text:
        if char in "([{":
            depth += 1
            out.append(char if depth == 1 else "")
        elif char in ")]}":
            depth -= 1
            out.append(char if depth == 0 else "")
        elif depth == 0:
            out.append(char)
    return "".join(out)


def _split_arithmetic(text: str) -> list[str]:
    """[operand, operator, operand, ...] of the top-level binary arithmetic of a cleaned DAX text."""

    parts, depth, start, previous = [], 0, 0, ""
    for i, char in enumerate(text):
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        elif depth == 0 and char in "+-*/^" and re.match(r"[\w\])\"]", previous):
            parts += [text[start:i].strip(), char]
            start = i + 1
        if not char.isspace():
            previous = char
    parts.append(text[start:].strip())
    return parts


def _merge(kinds: Iterable[str]) -> str:
    found = {kind for kind in kinds if kind not in {BLANK, UNKNOWN}}
    if not found:
        return UNKNOWN
    return found.pop() if len(found) == 1 else MIXED


class Inference:
    """Coarse result kinds of DAX texts against the objects of one model."""

    def __init__(self, objects: Sequence[Any]):
        self.measures = {item.name.lower(): item for item in objects if item.kind == "measure"}
        self.columns = {((item.table or "").lower(), item.name.lower()): item for item in objects if item.kind == "column"}
        self.functions = {item.name.lower(): item for item in objects if item.kind == "function"}
        self.overrides: dict[str, str] = {}
        self.busy: set[str] = set()

    def measure(self, name: str) -> str:
        key = name.lower()
        if key in self.overrides:
            return self.overrides[key]
        item = self.measures.get(key)
        if item is None or key in self.busy:
            return UNKNOWN
        self.busy.add(key)
        try:
            return self.kind(str(item.props.get("expression") or ""))
        finally:
            self.busy.discard(key)

    def column(self, table: str | None, name: str) -> str:
        if table is not None:
            item = self.columns.get((table.lower(), name.lower()))
        else:
            item = next((value for (_, column), value in self.columns.items() if column == name.lower()), None)
        if item is None:
            return UNKNOWN
        return _DATA_TYPES.get(str(item.props.get("data_type") or "").lower(), UNKNOWN)

    def function(self, name: str) -> str:
        key = "fn:" + name.lower()
        item = self.functions.get(name.lower())
        if item is None or key in self.busy:
            return UNKNOWN
        self.busy.add(key)
        try:
            return function_result(self, str(item.props.get("expression") or ""))
        finally:
            self.busy.discard(key)

    def kind(self, text: str, variables: Mapping[str, str] | None = None) -> str:
        return self._kind(_clean(text).strip(), dict(variables or {}))

    def _kind(self, text: str, variables: dict[str, str]) -> str:
        text = text.strip()
        if not text:
            return UNKNOWN
        if text.startswith("="):
            text = text[1:].strip()
        upper = text.upper()
        if re.match(r"VAR\b", upper):
            return self._var_block(text, variables)
        top = _top_level(text).upper()
        if re.search(r"&&|\|\||<>|<=|>=|(?<![<>])=|[<>]|\bIN\b|\bNOT\b", top):
            return BOOLEAN
        if "&" in top:
            return TEXT
        operands = _split_arithmetic(text)
        if len(operands) > 1:
            # Date plus or minus a number is a date; any other arithmetic gives a number.
            kinds = {self._kind(operand, dict(variables)) for operand in operands[::2]}
            return DATETIME if DATETIME in kinds and set(operands[1::2]) <= {"+", "-"} else NUMBER
        if top.startswith("-") or top.startswith("+"):
            return NUMBER if self._kind(text[1:], variables) in {NUMBER, UNKNOWN, BLANK} else UNKNOWN
        if text.startswith("(") and text.endswith(")") and _top_level(text) == "()":
            return self._kind(text[1:-1], variables)
        if text.startswith("{"):
            return TABLE
        if re.fullmatch(r"\d+(\.\d+)?([eE][-+]?\d+)?", text):
            return NUMBER
        if text == '"s"':
            return TEXT
        reference = re.fullmatch(r"(?:(T|[\w.]+))?\s*\[([^\]]+)\]", text)
        if reference:
            table, name = reference.groups()
            if table is None:
                measure = self.measure(name)
                return measure if measure != UNKNOWN or name.lower() in self.measures else self.column(None, name)
            return self.column(None if table == "T" else table, name)
        if text.lower() in variables:
            return variables[text.lower()]
        call = re.fullmatch(r"([\w.]+)\s*\((.*)\)", text, re.S)
        if call:
            return self._call(call.group(1), _split_top(call.group(2)) if call.group(2).strip() else [], variables)
        return UNKNOWN

    def _var_block(self, text: str, variables: dict[str, str]) -> str:
        # VAR a = ... VAR b = ... RETURN expr; the RETURN that closes this block is the last one at the top level.
        top = _top_level(text)
        returns = [match.start() for match in re.finditer(r"\bRETURN\b", top, re.I)]
        if not returns:
            return UNKNOWN
        # Map the position in ``top`` back to ``text`` (``top`` drops bracket contents).
        cut = _position(text, returns[-1])
        head, body = text[:cut], text[cut + len("RETURN"):]
        for match in re.finditer(r"\bVAR\s+([\w.]+)\s*=\s*(.*?)(?=\bVAR\s+[\w.]+\s*=|\Z)", head, re.I | re.S):
            variables[match.group(1).lower()] = self._kind(match.group(2), dict(variables))
        return self._kind(body, variables)

    def _call(self, name: str, args: list[str], variables: dict[str, str]) -> str:
        upper = name.upper()
        if upper == "BLANK":
            return BLANK
        if upper == "CALCULATE":
            return self._kind(args[0], variables) if args else UNKNOWN
        if upper == "IF":
            return _merge(self._kind(arg, variables) for arg in args[1:3]) if len(args) >= 2 else UNKNOWN
        if upper == "SWITCH":
            results = args[2::2] + ([args[-1]] if len(args) % 2 == 0 else [])
            return _merge(self._kind(arg, variables) for arg in results)
        if upper in {"COALESCE", "IFERROR"}:
            return _merge(self._kind(arg, variables) for arg in args)
        if upper in {"MAX", "MIN", "MAXA", "MINA"}:
            return self._kind(args[0], variables) if len(args) >= 1 else UNKNOWN
        if upper in {"MAXX", "MINX", "FIRSTNONBLANKVALUE", "LASTNONBLANKVALUE"}:
            return self._kind(args[1], variables) if len(args) >= 2 else UNKNOWN
        if upper in {"SELECTEDVALUE", "RELATED", "LOOKUPVALUE", "EARLIER", "EARLIEST"}:
            return self._kind(args[0], variables) if args else UNKNOWN
        if upper in _NUMBER_FUNCTIONS:
            return NUMBER
        if upper in _TEXT_FUNCTIONS:
            return TEXT
        if upper in _BOOLEAN_FUNCTIONS:
            return BOOLEAN
        if upper in _DATETIME_FUNCTIONS:
            return DATETIME
        if upper in _TABLE_FUNCTIONS:
            return TABLE
        return self.function(name)


def _position(text: str, top_index: int) -> int:
    """The index in ``text`` of the character at ``top_index`` of ``_top_level(text)``."""

    depth, kept = 0, -1
    for i, char in enumerate(text):
        if char in "([{":
            depth += 1
            keep = depth == 1
        elif char in ")]}":
            depth -= 1
            keep = depth == 0
        else:
            keep = depth == 0
        if keep:
            kept += 1
            if kept == top_index:
                return i
    return len(text)


# Functions -------------------------------------------------------------------------------------

_SIGNATURE = re.compile(r"^\s*\((.*?)\)\s*=>(.*)$", re.S)


def function_parameters(text: str) -> list[tuple[str, str]] | None:
    """[(name, type)] of a function text ``(a : NUMERIC, b) => body``; None when the text has no signature."""

    match = _SIGNATURE.match(_clean(text))
    if match is None:
        return None
    params = []
    for part in _split_top(match.group(1)):
        if not part:
            continue
        name, _, kind = part.partition(":")
        params.append((name.strip(), " ".join(kind.split()).upper()))
    return params


def function_result(inference: Inference, text: str) -> str:
    match = _SIGNATURE.match(_clean(text))
    if match is None:
        return UNKNOWN
    params = {name.lower(): _param_kind(kind) for name, kind in function_parameters(text) or []}
    return inference._kind(match.group(2), params)


def _param_kind(kind: str) -> str:
    if "TABLE" in kind:
        return TABLE
    if "STRING" in kind:
        return TEXT
    if "BOOLEAN" in kind:
        return BOOLEAN
    if "DATETIME" in kind:
        return DATETIME
    if any(word in kind for word in ("NUMERIC", "INT64", "DOUBLE", "DECIMAL")):
        return NUMBER
    return UNKNOWN


def _required(params: Sequence[tuple[str, str]]) -> int:
    # DAX functions have no optional parameters: every parameter is required.
    return len(params)


def call_sites(text: str, name: str) -> list[int]:
    """The argument count of each call of the function ``name`` in a DAX text."""

    cleaned = _clean(text)
    counts = []
    for match in re.finditer(r"(?<![\w.\[])" + re.escape(name) + r"\s*\(", cleaned, re.I):
        depth, i = 1, match.end()
        while i < len(cleaned) and depth:
            depth += {"(": 1, ")": -1}.get(cleaned[i], 0)
            i += 1
        inner = cleaned[match.end():i - 1].strip()
        counts.append(len(_split_top(inner)) if inner else 0)
    return counts


# M -----------------------------------------------------------------------------------------------


def m_syntax_error(text: str) -> str | None:
    """A reason code when an M text is clearly broken (open bracket or text, ``let`` without ``in``), else None."""

    stack, i, closing = [], 0, {")": "(", "]": "[", "}": "{"}
    while i < len(text):
        char = text[i]
        if char == '"':
            end = i + 1
            while end < len(text):
                if text[end] == '"' and text[end + 1:end + 2] == '"':
                    end += 2
                    continue
                if text[end] == '"':
                    break
                end += 1
            if end >= len(text):
                return "m_unclosed_text"
            i = end + 1
            continue
        if text.startswith("//", i):
            newline = text.find("\n", i)
            i = len(text) if newline < 0 else newline
            continue
        if text.startswith("/*", i):
            close = text.find("*/", i + 2)
            if close < 0:
                return "m_unclosed_comment"
            i = close + 2
            continue
        if char in "([{":
            stack.append(char)
        elif char in ")]}":
            if not stack or stack.pop() != closing[char]:
                return "m_unbalanced_brackets"
        i += 1
    if stack:
        return "m_unbalanced_brackets"
    words = re.findall(r"\b(let|in)\b", re.sub(r'"(?:[^"]|"")*"', "", text))
    if words.count("let") > words.count("in"):
        return "m_let_without_in"
    return None


def _m_names(text: str) -> set[str]:
    """The quoted texts of an M query: the column names it selects, renames, types or expands."""

    return {match.group(1).replace('""', '"') for match in re.finditer(r'"((?:[^"]|"")*)"', text or "")}


# Rules -------------------------------------------------------------------------------------------


def _rule(rule: str, level: str, message: str, objects: Iterable[str] = ()) -> dict[str, Any]:
    names = sorted(set(objects))
    return {"rule": rule, "level": level, "message": message, "objects": names[:OBJECTS_MAX]}


def _label(item: Any) -> str:
    return f"{item.kind} {item.qualified_name}"


def _dependents(items: Sequence[Mapping[str, Any]]) -> list[str]:
    # The objects that hold a value or a formula; a page or the report is reached through its visuals.
    return [f"{entry['object'].get('object_type')} {entry['object'].get('name')}" for entry in items
            if entry.get("direction") == "breaks" and (entry.get("object") or {}).get("name")
            and (entry.get("object") or {}).get("object_type") not in {"page", "report"}]


def change_rules(target: Any, new: Mapping[str, Any], objects: Sequence[Any],
                 impact: Sequence[Mapping[str, Any]] = ()) -> list[dict[str, Any]]:
    """The advisory rules of an ``object_edit`` that sets ``new`` on the target object ``target``."""

    found: list[dict[str, Any]] = []
    expression = new.get("expression")
    if not isinstance(expression, str):
        return found
    inference = Inference(objects)
    kind = target.kind
    if kind == "measure" or (kind == "column" and target.props.get("expression") is not None):
        old_kind = inference.kind(str(target.props.get("expression") or ""))
        if kind == "measure":
            inference.overrides[target.name.lower()] = UNKNOWN  # no self-reference loop
        new_kind = inference.kind(expression)
        if old_kind in SCALAR_KINDS and new_kind != old_kind and new_kind not in {UNKNOWN, BLANK}:
            found.append(_rule(
                "result_type_change", "breaks",
                f"{target.qualified_name} returned {old_kind} and now returns {new_kind}. Visuals that sum, chart or "
                f"format it, measures that calculate with it, and sorts and filters on it expect {old_kind}: they can "
                "break or show errors. Check each dependent, or keep the result type.",
                _dependents(impact)))
        if kind == "measure" and new_kind == TEXT and old_kind != TEXT and re.search(r"[0#%]", str(target.props.get("format_string") or "")):
            found.append(_rule("format_string_ignored", "warning",
                               f"{target.qualified_name} has the number format \"{target.props.get('format_string')}\"; "
                               "a text result ignores it."))
    elif kind == "function":
        found.extend(_function_rules(inference, target, expression, objects))
    elif kind == "calculation_item":
        if not re.search(r"\bSELECTEDMEASURE\s*\(", _clean(expression), re.I):
            found.append(_rule("calc_item_without_measure", "warning",
                               f"The calculation item {target.qualified_name} does not use SELECTEDMEASURE(), so it returns "
                               "the same value for every measure it is applied to."))
    elif kind == "partition":
        found.extend(_partition_rules(target, expression, objects))
    elif kind == "expression":
        users = [_label(item) for item in objects if item.kind == "partition" and _uses_query(item.props.get("m_text"), target.name)]
        users += [_label(item) for item in objects if item.kind == "expression" and item.name != target.name
                  and _uses_query(item.props.get("m_text"), target.name)]
        if users:
            found.append(_rule("query_dependents", "warning",
                               f"The tables and queries that use {target.name} load what the new query returns: check "
                               "that it still returns the columns and type they expect.", users))
    return found


def _function_rules(inference: Inference, target: Any, expression: str, objects: Sequence[Any]) -> list[dict[str, Any]]:
    found = []
    old_text = str(target.props.get("expression") or "")
    old_params, new_params = function_parameters(old_text), function_parameters(expression)
    callers = [(item, call_sites(str(item.props.get("expression") or ""), target.name)) for item in objects
               if item.kind in {"measure", "column", "calculation_item", "function", "table"} and item is not target
               and item.props.get("expression")]
    callers = [(item, counts) for item, counts in callers if counts]
    if new_params is None:
        found.append(_rule("function_signature", "breaks",
                           f"The function {target.name} needs a signature: (param : TYPE, ...) => expression."))
        return found
    if old_params is not None and old_params != new_params:
        wrong = [_label(item) for item, counts in callers if any(count != _required(new_params) for count in counts)]
        changed_types = [name for (name, kind), (_, old_kind) in zip(new_params, old_params) if kind != old_kind]
        if wrong:
            found.append(_rule("function_signature", "breaks",
                               f"{target.name} now takes {len(new_params)} parameter(s); these callers pass another "
                               "number of arguments and stop working.", wrong))
        elif changed_types and callers:
            found.append(_rule("function_signature", "warning",
                               f"The type of {', '.join(changed_types)} changed; check that each caller passes a value of the "
                               "new type.", [_label(item) for item, _ in callers]))
    old_kind = function_result(inference, old_text)
    new_kind = function_result(inference, expression)
    if old_kind in SCALAR_KINDS and new_kind != old_kind and new_kind not in {UNKNOWN, BLANK} and callers:
        found.append(_rule("function_result_type", "breaks",
                           f"{target.name} returned {old_kind} and now returns {new_kind}; the callers get the new kind.",
                           [_label(item) for item, _ in callers]))
    return found


def _partition_rules(target: Any, expression: str, objects: Sequence[Any]) -> list[dict[str, Any]]:
    old_names, new_names = _m_names(str(target.props.get("m_text") or "")), _m_names(expression)
    dropped = []
    for item in objects:
        if item.kind != "column" or (item.table or "").lower() != (target.table or "").lower():
            continue
        source = item.props.get("source_column")
        if source and source in old_names and source not in new_names:
            dropped.append(f"column {item.qualified_name} (source column {source})")
    if not dropped:
        return []
    return [_rule("source_column_dropped", "breaks",
                  "The new query no longer names source columns that columns of the table read; the refresh fails for "
                  "them, and every measure and visual on those columns breaks.", dropped)]


def _uses_query(text: Any, name: str) -> bool:
    if not text:
        return False
    return bool(re.search(r'#"' + re.escape(name) + r'"|(?<![\w"])' + re.escape(name) + r"(?![\w\"])", str(text)))
