"""Exact raw accounting for existing TMDL scalar and inline-expression edits.

TOM remains the semantic authority. This parser only proves that every changed
line corresponds to an already detected property difference. Unknown syntax,
comment edits, changed indentation and extra source lines fail closed.
"""
from __future__ import annotations
from difflib import SequenceMatcher
import re
from typing import Any

HEADERS = {"table": "TABLE", "column": "COLUMN", "measure": "MEASURE", "relationship": "RELATIONSHIP", "expression": "SHARED_EXPRESSION", "function": "USER_DEFINED_FUNCTION"}
SCALARS = {"description": "description", "formatString": "format_string", "displayFolder": "display_folder", "dataType": "datatype",
           "dataCategory": "data_category", "sourceColumn": "source_column", "summarizeBy": "summarize_by", "sortByColumn": "sort_by",
           "isHidden": "hidden", "isActive": "active", "crossFilteringBehavior": "cross_filter_direction",
           "fromCardinality": "from_cardinality", "toCardinality": "to_cardinality", "securityFilteringBehavior": "security_filter_behavior"}
NAME = r"(?:'((?:''|[^'])+)'|([A-Za-z_][A-Za-z0-9_-]*))"


def _name(match):
    return (match[1] if match[1] is not None else match[2]).replace("''", "'")


def _scopes(lines):
    stack, scopes = [], []
    for line in lines:
        header = re.fullmatch(r"([ \t]*)(" + "|".join(HEADERS) + r")\s+(" + NAME + r")(?:\s*=\s*([^\r\n]*))?(\r?\n)?", line)
        if header:
            indent, kind = len(header[1].expandtabs(4)), HEADERS[header[2]]
            name = (header[4] if header[4] is not None else header[5]).replace("''", "'")
            while stack and stack[-1][0] >= indent: stack.pop()
            stack.append((indent, kind, name))
        elif line.strip() and not line.lstrip().startswith("//"):
            indent = len(line) - len(line.lstrip(" \t"))
            if stack and len(line[:indent].expandtabs(4)) <= stack[-1][0]:
                stack.pop()
        scopes.append(tuple((kind, name) for _, kind, name in stack))
    return scopes


def _scalar(value):
    if type(value) is bool: return str(value).lower()
    if value is None or isinstance(value, (dict, list)): return None
    return str(value)


def _exact_text(text, value):
    plain = _scalar(value)
    if plain is None: return False
    if text == plain: return True
    # Quoting is syntax only; no whitespace removal or string unescaping beyond
    # TMDL's doubled quote convention.
    return isinstance(value, str) and text == '"' + value.replace('"', '""') + '"'


def account_tmdl(before: str, after: str, differences: list[dict[str, Any]], graph: dict, relative: str) -> bool:
    old, new = before.splitlines(keepends=True), after.splitlines(keepends=True)
    old_scopes, new_scopes = _scopes(old), _scopes(new)
    nodes = {node["id"]: node for node in graph.get("nodes", [])}
    parents = {edge["to_id"]: edge["from_id"] for edge in graph.get("edges", []) if edge["type"] == "CONTAINS"}
    def matches(difference, scope):
        node = nodes.get(difference["object_id"])
        if not node or not scope or (node["type"], node["name"]) != scope[-1]: return False
        if len(scope) > 1:
            parent = nodes.get(parents.get(node["id"]), {})
            if (parent.get("type"), parent.get("name")) != scope[-2]: return False
        return True
    pending_locations = []
    for tag, i, j, k, l in SequenceMatcher(a=old, b=new, autojunk=False).get_opcodes():
        if tag == "equal": continue
        if tag != "replace" or j - i != l - k: return False
        for offset in range(j - i):
            a, b = old[i + offset], new[k + offset]
            scope = old_scopes[i + offset]
            if scope != new_scopes[k + offset]: return False
            scalar_a = re.fullmatch(r"([ \t]+)(\w+): ([^\r\n]*)(\r?\n)?", a)
            scalar_b = re.fullmatch(r"([ \t]+)(\w+): ([^\r\n]*)(\r?\n)?", b)
            if scalar_a and scalar_b and (scalar_a[1], scalar_a[2], scalar_a[4]) == (scalar_b[1], scalar_b[2], scalar_b[4]) and scalar_a[2] in SCALARS:
                prop, previous, value = SCALARS[scalar_a[2]], scalar_a[3], scalar_b[3]
                candidates = [d for d in differences if d["property_path"] == prop and matches(d, scope)]
                if len(candidates) != 1 or not _exact_text(previous, candidates[0]["previous_value"]) or not _exact_text(value, candidates[0]["new_value"]): return False
            else:
                inline_a = re.fullmatch(r"([ \t]*)(measure|expression|function)\s+(" + NAME + r") = ([^\r\n]*)(\r?\n)?", a)
                inline_b = re.fullmatch(r"([ \t]*)(measure|expression|function)\s+(" + NAME + r") = ([^\r\n]*)(\r?\n)?", b)
                if not inline_a or not inline_b or inline_a.groups()[:5] != inline_b.groups()[:5] or inline_a[7] != inline_b[7]: return False
                candidates = [d for d in differences if d["property_path"] == "expression" and matches(d, scope)]
                if len(candidates) != 1 or inline_a[6] != candidates[0]["previous_value"] or inline_b[6] != candidates[0]["new_value"]: return False
            pending_locations.append((candidates[0], {"before_line": i + offset + 1, "after_line": k + offset + 1}))
    for difference, location in pending_locations:
        difference.update(source_file=relative, source_location=location)
    return True
