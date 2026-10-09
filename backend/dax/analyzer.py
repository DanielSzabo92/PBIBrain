"""Deterministic DAX-to-fact analysis.

This layer consumes an already parsed AST.  It resolves only against canonical
nodes and emits factual graph edges plus traceable behavioral observations.  It
does not create business concepts, selectors, aliases, or other Phase 3
semantic candidates.
"""

from __future__ import annotations

from dataclasses import dataclass, field, is_dataclass, asdict
import hashlib
import json
import logging
import re
from typing import Any, Callable, Iterable, Mapping, Sequence

from backend.graph.schema import Edge, Node, node_from_dict

from .evidence import ast_location, make_evidence
from .visitors import (
    AstVisit,
    ReferenceInfo,
    attr,
    function_name,
    iter_functions,
    iter_references,
    iter_variables,
    node_kind,
    node_text,
    walk_ast,
)

LOGGER = logging.getLogger(__name__)


def _norm(value: Any) -> str:
    return "".join(char for char in str(value).casefold() if char.isalnum())


def _safe(value: Any, *, _seen: set[int] | None = None) -> Any:
    """Convert parser-owned values to stable JSON data."""

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if _seen is None:
        _seen = set()
    marker = id(value)
    if marker in _seen:
        return "<cycle>"
    _seen.add(marker)
    if isinstance(value, Mapping):
        return {str(key): _safe(item, _seen=_seen) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_safe(item, _seen=_seen) for item in value]
    if is_dataclass(value):
        return _safe(asdict(value), _seen=_seen)
    for method_name in ("to_dict", "as_dict", "to_json"):
        method = getattr(value, method_name, None)
        if callable(method):
            try:
                converted = method()
            except Exception:  # pragma: no cover - third-party AST guard
                continue
            return _safe(converted, _seen=_seen)
    try:
        values = vars(value)
    except TypeError:
        values = None
    if isinstance(values, Mapping) and values:
        return {str(key): _safe(item, _seen=_seen) for key, item in values.items()}
    text = node_text(value)
    return text if text is not None else str(value)


def _node_value(node: Node, *keys: str) -> Any:
    for key in keys:
        if key in node.properties and node.properties[key] is not None:
            return node.properties[key]
        value = node.get(key)
        if value is not None:
            return value
    return None


def _strip_dax_quotes(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if len(text) >= 2 and text[0] == text[-1] == "'":
        text = text[1:-1].replace("''", "'")
    if len(text) >= 2 and text[0] == text[-1] == '"':
        text = text[1:-1].replace('""', '"')
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1]
    return text or None


_COLUMN_TEXT = re.compile(r"^\s*'?((?:[^']|'')+?)'?\s*\[([^\]]+)\]\s*$")
_MEASURE_TEXT = re.compile(r"^\s*\[([^\]]+)\]\s*$")


@dataclass(frozen=True, slots=True)
class Resolution:
    """Resolver result, including ambiguity details for diagnostics."""

    reference: Any
    expected_types: tuple[str, ...]
    candidates: tuple[Node, ...] = ()

    @property
    def node(self) -> Node | None:
        return self.candidates[0] if len(self.candidates) == 1 else None

    @property
    def resolved(self) -> bool:
        return len(self.candidates) == 1

    @property
    def ambiguous(self) -> bool:
        return len(self.candidates) > 1


class ObjectResolver:
    """Resolve AST references against canonical nodes without guessing."""

    def __init__(self, nodes: Iterable[Node] | Mapping[str, Node]) -> None:
        values = nodes.values() if isinstance(nodes, Mapping) else nodes
        self.nodes: dict[str, Node] = {str(node.id): node for node in values}
        self._by_name: dict[tuple[str, str, str], set[str]] = {}
        self._by_qualified: dict[tuple[str, str, str], set[str]] = {}
        for node in sorted(self.nodes.values(), key=lambda item: item.id):
            scopes = {str(node.model_id or "global")}
            names = {node.name, node.source_id}
            for name in names:
                if name is None or not str(name).strip():
                    continue
                for scope in scopes:
                    self._by_name.setdefault((scope, node.type, _norm(name)), set()).add(node.id)
            if node.type in {"COLUMN", "MEASURE"}:
                table_id = _node_value(node, "table_id", "tableId")
                table = self.nodes.get(str(table_id)) if table_id else None
                table_names = {table.name, table.source_id, table.id} if table else set()
                for table_name in table_names:
                    if table_name is None:
                        continue
                    for scope in scopes:
                        self._by_qualified.setdefault(
                            (scope, _norm(table_name), _norm(node.name)), set()
                        ).add(node.id)
                        self._by_qualified.setdefault(
                            (scope, _norm(table_name), _norm(node.source_id)), set()
                        ).add(node.id)

    def resolve(
        self,
        reference: Any,
        expected_types: str | Sequence[str] | None = None,
        model_id: str | None = None,
    ) -> Node | None:
        """Return a node only when exactly one candidate exists."""

        return self.resolve_detailed(reference, expected_types, model_id).node

    def resolve_detailed(
        self,
        reference: Any,
        expected_types: str | Sequence[str] | None = None,
        model_id: str | None = None,
    ) -> Resolution:
        if expected_types is None:
            expected = ("MEASURE", "COLUMN", "TABLE", "RELATIONSHIP", "USER_DEFINED_FUNCTION", "SHARED_EXPRESSION")
        elif isinstance(expected_types, str):
            expected = (expected_types.upper(),)
        else:
            expected = tuple(str(item).upper() for item in expected_types)
        scope = str(model_id or "global")
        if isinstance(reference, Node):
            return Resolution(reference, expected, (reference,) if reference.id in self.nodes else ())

        direct = self._mapping_value(reference, "canonical_id", "canonicalId", "id")
        if direct is not None:
            candidate = self.nodes.get(str(direct))
            if candidate and candidate.type in expected:
                return Resolution(reference, expected, (candidate,))

        kind, name, table = self._reference_parts(reference, expected)
        if kind and kind not in expected:
            expected = (kind,)
        if name is None:
            return Resolution(reference, expected, ())
        lookup_expected = expected
        # DAX uses the same qualified ``Table[Name]`` syntax for columns and
        # measures.  Resolve the target type from the model, not the syntax.
        if kind == "COLUMN" and table is not None and expected == ("COLUMN",):
            lookup_expected = ("COLUMN", "MEASURE")
        candidates: set[str] = set()
        if kind == "COLUMN" or (table is not None and "COLUMN" in lookup_expected):
            if table is not None:
                candidates.update(self._by_qualified.get((scope, _norm(table), _norm(name)), set()))
            elif not candidates:
                candidates.update(self._lookup_names(name, lookup_expected, scope))
        else:
            candidates.update(self._lookup_names(name, lookup_expected, scope))
        values = tuple(self.nodes[item] for item in sorted(candidates) if self.nodes[item].type in lookup_expected)
        # Display names with spaces and compact column names are distinct DAX
        # identifiers. Prefer exact case-insensitive names before legacy aliases.
        exact = tuple(node for node in values if str(name).casefold() in {
            str(node.name).casefold(), str(node.source_id).casefold()
        })
        if exact:
            values = exact
        return Resolution(reference, lookup_expected, values)

    def _lookup_names(self, name: str, expected: Sequence[str], scope: str) -> set[str]:
        result: set[str] = set()
        for object_type in expected:
            result.update(self._by_name.get((scope, object_type, _norm(name)), set()))
        return result

    @staticmethod
    def _mapping_value(value: Any, *keys: str) -> Any:
        if isinstance(value, Mapping):
            for key in keys:
                if key in value and value[key] is not None:
                    return value[key]
        else:
            for key in keys:
                candidate = getattr(value, key, None)
                if candidate is not None:
                    return candidate
        return None

    def _reference_parts(self, reference: Any, expected: Sequence[str]) -> tuple[str | None, str | None, str | None]:
        if isinstance(reference, ReferenceInfo):
            return reference.kind, reference.name, reference.table
        if isinstance(reference, str):
            text = reference.strip()
            kind: str | None = expected[0] if len(expected) == 1 else None
            column_match = _COLUMN_TEXT.match(text)
            if column_match:
                return "COLUMN", _strip_dax_quotes(column_match.group(2)), _strip_dax_quotes(column_match.group(1))
            measure_match = _MEASURE_TEXT.match(text)
            if measure_match:
                return "MEASURE", _strip_dax_quotes(measure_match.group(1)), None
            return kind, _strip_dax_quotes(text), None
        kind_value = self._mapping_value(reference, "reference_type", "referenceType", "object_type", "objectType", "type")
        kind = str(kind_value).upper() if kind_value else None
        name = self._mapping_value(reference, "name", "identifier", "measure", "measure_name", "measureName", "column", "column_name", "columnName", "table", "table_name", "tableName", "value", "text")
        table = self._mapping_value(reference, "table", "table_name", "tableName", "entity", "qualifier")
        if isinstance(name, Mapping):
            name = self._mapping_value(name, "name", "value", "text", "id")
        if kind:
            if "MEASURE" in kind:
                kind = "MEASURE"
            elif "COLUMN" in kind:
                kind = "COLUMN"
            elif "TABLE" in kind:
                kind = "TABLE"
        text = name if isinstance(name, str) else self._mapping_value(reference, "text", "raw_text")
        if isinstance(text, str):
            column_match = _COLUMN_TEXT.match(text)
            if column_match:
                kind = kind or "COLUMN"
                table = table or column_match.group(1)
                name = column_match.group(2)
            else:
                measure_match = _MEASURE_TEXT.match(text)
                if measure_match:
                    kind = kind or "MEASURE"
                    name = measure_match.group(1)
        if kind is None and len(expected) == 1:
            kind = expected[0]
        if table is not None:
            table = _strip_dax_quotes(table)
        name = _strip_dax_quotes(name)
        return kind, name, table

    def resolve_relationship(self, column_ids: Iterable[str], model_id: str | None = None) -> Node | None:
        wanted = {str(item) for item in column_ids}
        if len(wanted) < 2:
            return None
        matches: list[Node] = []
        for node in sorted(self.nodes.values(), key=lambda item: item.id):
            if node.type != "RELATIONSHIP" or (model_id and node.model_id != model_id):
                continue
            endpoints = {
                str(_node_value(node, "from_column_id", "fromColumnId") or ""),
                str(_node_value(node, "to_column_id", "toColumnId") or ""),
            }
            if endpoints == wanted:
                matches.append(node)
        return matches[0] if len(matches) == 1 else None


@dataclass(slots=True)
class DaxAnalysis:
    source_object_id: str
    expression: str
    ast: Any = None
    references: list[dict[str, Any]] = field(default_factory=list)
    behaviors: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    diagnostics: list[dict[str, Any]] = field(default_factory=list)

    @property
    def facts(self) -> list[Edge]:
        return self.edges

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_object_id": self.source_object_id,
            "expression": self.expression,
            "ast": _safe(self.ast),
            "references": _safe(self.references),
            "behaviors": _safe(self.behaviors),
            "evidence": _safe(self.evidence),
            "edges": [edge.to_dict() for edge in self.edges],
            "diagnostics": _safe(self.diagnostics),
        }

    as_dict = to_dict


@dataclass(slots=True)
class DaxAnalysisBatch:
    analyses: dict[str, DaxAnalysis] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)
    diagnostics: list[dict[str, Any]] = field(default_factory=list)

    @property
    def facts(self) -> list[Edge]:
        return self.edges

    @property
    def evidence(self) -> list[dict[str, Any]]:
        return [item for analysis in self.analyses.values() for item in analysis.evidence]

    def to_dict(self) -> dict[str, Any]:
        return {
            "analyses": {key: value.to_dict() for key, value in sorted(self.analyses.items())},
            "edges": [edge.to_dict() for edge in self.edges],
            "diagnostics": _safe(self.diagnostics),
        }

    as_dict = to_dict


_REFERENCE_OBJECT_TYPES = {"MEASURE", "CALCULATION_ITEM", "SHARED_EXPRESSION", "USER_DEFINED_FUNCTION", "COLUMN"}
_SELECTOR_FUNCTIONS = {"SELECTEDVALUE", "VALUES", "HASONEVALUE", "ISFILTERED", "ISCROSSFILTERED", "FILTERS"}
_FILTER_FUNCTIONS = {
    "CALCULATE",
    "CALCULATETABLE",
    "FILTER",
    "TREATAS",
    "REMOVEFILTERS",
    "ALL",
    "ALLEXCEPT",
    "ALLSELECTED",
    "KEEPFILTERS",
}
_RELATIONSHIP_FUNCTIONS = {"USERELATIONSHIP", "CROSSFILTER"}
_CONDITIONAL_FUNCTIONS = {"IF", "SWITCH", "COALESCE"}
_FORMAT_FUNCTIONS = {"FORMAT", "SELECTEDMEASURE", "SELECTEDMEASUREFORMATSTRING"}


class DaxAnalyzer:
    """Parse each unique expression once, then emit deterministic facts."""

    def __init__(self, nodes: Iterable[Node] | Mapping[str, Node], parser: Any = None) -> None:
        values = nodes.values() if isinstance(nodes, Mapping) else nodes
        self.nodes = {}
        for value in values:
            node = value if isinstance(value, Node) else node_from_dict(value)
            self.nodes[str(node.id)] = node
        self.resolver = ObjectResolver(self.nodes)
        self.parser = parser
        self._ast_cache: dict[str, Any] = {}
        self._edges: dict[str, Edge] = {}

    def analyze(self, nodes: Iterable[Node] | Mapping[str, Node] | None = None) -> DaxAnalysisBatch:
        values = nodes.values() if isinstance(nodes, Mapping) else nodes
        target_values = list(values) if values is not None else list(self.nodes.values())
        target_nodes = [value if isinstance(value, Node) else node_from_dict(value) for value in target_values]
        result = DaxAnalysisBatch()
        for node in sorted(target_nodes, key=lambda item: str(item.id)):
            if node.type not in _REFERENCE_OBJECT_TYPES or self._is_m_shared_expression(node):
                continue
            expression = _node_value(node, "expression", "dax", "formula", "expression_text")
            if not isinstance(expression, str) or not expression.strip():
                continue
            analysis = self.analyze_object(node, expression)
            result.analyses[node.id] = analysis
            result.diagnostics.extend(analysis.diagnostics)
        result.edges = sorted(self._edges.values(), key=lambda item: item.id)
        result.diagnostics.sort(key=lambda item: json.dumps(item, sort_keys=True, default=str))
        return result

    analyse = analyze

    @staticmethod
    def _is_m_shared_expression(node: Node) -> bool:
        if node.type != "SHARED_EXPRESSION":
            return False
        kind = _node_value(node, "kind", "language", "expression_kind")
        if kind is None:
            raw_source = node.properties.get("raw_source")
            if isinstance(raw_source, Mapping):
                kind = raw_source.get("kind")
        return str(kind or "").strip().casefold() == "m"

    def analyze_object(self, node: Node | str, expression: str | None = None, ast: Any = None) -> DaxAnalysis:
        source = self.nodes.get(str(node)) if isinstance(node, str) else node
        if source is None:
            source_id = str(node)
            source = Node(id=source_id, type="UNKNOWN", name=source_id)
        if source.id not in self.nodes:
            self.nodes[source.id] = source
            self.resolver = ObjectResolver(self.nodes)
        text = expression if expression is not None else _node_value(source, "expression", "dax", "formula", "expression_text")
        text = str(text or "")
        if self._is_m_shared_expression(source):
            analysis = DaxAnalysis(source.id, text)
            self._store_analysis(source, analysis)
            return analysis
        if ast is None:
            ast, parse_diagnostic = self._parse(text)
        else:
            parse_diagnostic = None
        analysis = DaxAnalysis(source.id, text, ast=ast)
        if parse_diagnostic:
            parse_diagnostic = dict(parse_diagnostic)
            parse_diagnostic.setdefault("source_object", source.id)
            analysis.diagnostics.append(parse_diagnostic)
            self._store_analysis(source, analysis)
            return analysis
        if ast is None:
            self._store_analysis(source, analysis)
            return analysis
        # Keep the parsed form on the canonical node.  It is JSON data, not a
        # parser object, so graph persistence remains deterministic.
        source.properties["dax_ast"] = _safe(ast)
        self._analyze_ast(source, analysis)
        for key, extra in self._additional_expressions(source, text):
            extra_ast, extra_diagnostic = self._parse(extra)
            if extra_diagnostic:
                diagnostic = dict(extra_diagnostic)
                diagnostic["expression_property"] = key
                diagnostic["source_object"] = source.id
                analysis.diagnostics.append(diagnostic)
                continue
            if extra_ast is None:
                continue
            source.properties.setdefault("dax_asts", {})[key] = _safe(extra_ast)
            self._analyze_ast(source, analysis, extra_ast)
        self._store_analysis(source, analysis)
        return analysis

    analyze_expression = analyze_object

    def analyze_ast(self, source_object: Node | str, ast: Any, expression: str = "") -> DaxAnalysis:
        return self.analyze_object(source_object, expression, ast)

    def _parse(self, expression: str) -> tuple[Any, dict[str, Any] | None]:
        key = expression
        if key in self._ast_cache:
            return self._ast_cache[key], None
        parser = self.parser
        if parser is None:
            try:
                from . import parser as parser_module  # type: ignore

                parser = parser_module
            except Exception as exc:
                diagnostic = {
                    "code": "parser_unavailable",
                    "message": str(exc),
                    "expression": expression,
                    "source": "dax_ast",
                }
                return None, diagnostic
        parse_callable: Callable[..., Any] | None = None
        if callable(parser):
            parse_callable = parser
        else:
            for name in ("parse_dax", "parse_expression", "parse"):
                candidate = getattr(parser, name, None)
                if callable(candidate):
                    parse_callable = candidate
                    break
            if parse_callable is None:
                for name in ("DaxParser", "Parser"):
                    candidate = getattr(parser, name, None)
                    if callable(candidate):
                        try:
                            instance = candidate()
                        except TypeError:
                            instance = candidate
                        parse_callable = getattr(instance, "parse", None) or getattr(instance, "parse_expression", None)
                        if callable(parse_callable):
                            break
        if parse_callable is None:
            diagnostic = {
                "code": "parser_unavailable",
                "message": "DAX parser exposes no parse function",
                "expression": expression,
                "source": "dax_ast",
            }
            return None, diagnostic
        try:
            parsed = parse_callable(expression)
        except Exception as exc:
            diagnostic = {
                "code": "parse_error",
                "message": str(exc),
                "expression": expression,
                "source": "dax_ast",
            }
            return None, diagnostic
        errors: Any = None
        if isinstance(parsed, tuple) and len(parsed) == 2:
            parsed, errors = parsed
        # The stable parser facade returns DaxParseResult.  Store/analyze its
        # canonical root, not the wrapper and its ANTLR parse tree.
        parsed_errors = getattr(parsed, "errors", None)
        parsed_root = getattr(parsed, "root", None)
        if parsed_root is not None:
            if errors is None:
                errors = parsed_errors
            parsed = parsed_root
        if errors:
            error_text = errors if isinstance(errors, str) else "; ".join(str(item) for item in errors)
            return parsed, {
                "code": "parse_error",
                "message": error_text,
                "expression": expression,
                "source": "dax_ast",
            }
        self._ast_cache[key] = parsed
        return parsed, None

    def _additional_expressions(self, source: Node, primary: str) -> Iterable[tuple[str, str]]:
        for key in ("format_expression", "formatStringExpression", "format_string_expression", "expression_format"):
            value = _node_value(source, key)
            if isinstance(value, str) and value.strip() and value.strip() != primary.strip():
                yield key, value

    def _contextual_reference(self, source: Node, info: ReferenceInfo) -> ReferenceInfo:
        if source.type != "COLUMN" or info.kind != "MEASURE" or info.table is not None:
            return info
        table_id = _node_value(source, "table_id", "tableId")
        table = self.nodes.get(str(table_id)) if table_id is not None else None
        table_name = table.name if table is not None else table_id
        return ReferenceInfo(
            "COLUMN",
            info.name,
            str(table_name) if table_name is not None else None,
            info.node,
            info.extractor,
            info.text,
        )

    def _analyze_ast(self, source: Node, analysis: DaxAnalysis, ast: Any | None = None) -> None:
        ast = analysis.ast if ast is None else ast
        local_variables = {_norm(name) for _, name in iter_variables(ast)}
        seen_refs: set[tuple[str, str, str | None, str]] = set()
        references: list[tuple[AstVisit, ReferenceInfo, Node]] = []
        for visit, info in iter_references(ast):
            marker = (info.kind, info.name, info.table, json.dumps(ast_location(info.node), sort_keys=True, default=str))
            if marker in seen_refs:
                continue
            seen_refs.add(marker)
            # A VAR name shadows a same-named model measure.  It is a local
            # value, not an unresolved/structural object reference.
            if (
                info.kind == "MEASURE"
                and _norm(info.name) in local_variables
                and not _MEASURE_TEXT.fullmatch((info.text or "").strip())
            ):
                analysis.references.append(self._reference_record(source, info, None, scope="variable"))
                continue
            contextual_info = self._contextual_reference(source, info)
            resolution = self.resolver.resolve_detailed(
                contextual_info,
                (contextual_info.kind,),
                source.model_id,
            )
            if not resolution.resolved:
                analysis.diagnostics.append(self._resolution_diagnostic(source, contextual_info, resolution))
                analysis.references.append(self._reference_record(source, info, None))
                continue
            target = resolution.node
            assert target is not None
            references.append((visit, info, target))
            resolved_kind = target.type if target.type in {"MEASURE", "COLUMN", "TABLE"} else info.kind
            edge_type = "DEPENDS_ON" if resolved_kind == "MEASURE" else "REFERENCES"
            evidence = make_evidence(
                source.id,
                edge_type,
                target.id,
                node=info.node,
                extractor=info.extractor,
                source="dax_ast",
                evidence=self._reference_text(info),
            )
            analysis.evidence.append(evidence)
            analysis.references.append(self._reference_record(source, info, target.id, evidence=evidence, kind=resolved_kind))
            self._record_edge(analysis, edge_type, source.id, target.id, source="dax_analysis", evidence=[evidence])

        for visit, name in iter_functions(ast):
            self._analyze_function(source, analysis, visit, name, references)
        for visit, variable in iter_variables(ast):
            behavior = self._behavior_record(
                source,
                visit,
                "VARIABLE",
                extractor="variable_binding",
                function=variable,
                evidence=f"VAR {variable}",
            )
            analysis.behaviors.append(behavior)
            analysis.evidence.append(behavior["evidence"])

        if local_variables:
            declaration_ids = {id(visit.node) for visit, _ in iter_variables(ast)}
            for visit in walk_ast(ast):
                if id(visit.node) in declaration_ids or node_kind(visit.node) != "IDENTIFIER":
                    continue
                name = attr(visit.node, "name", "identifier", "text", "value")
                if _norm(name) not in local_variables:
                    continue
                behavior = self._behavior_record(
                    source,
                    visit,
                    "VARIABLE_REFERENCE",
                    extractor="variable_reference",
                    function=str(name),
                    evidence=f"Variable reference {name}",
                )
                analysis.behaviors.append(behavior)
                analysis.evidence.append(behavior["evidence"])

        # Lightweight ASTs may represent constructs as expression nodes rather
        # than FunctionCall nodes.  Preserve those facts as observations.
        for visit in self._iter_construct_nodes(ast):
            kind = node_kind(visit.node)
            if kind in {
                "IF",
                "SWITCH",
                "CONDITIONAL",
                "IF_EXPRESSION",
                "SWITCH_EXPRESSION",
                "CONDITIONAL_EXPRESSION",
            }:
                behavior = self._behavior_record(source, visit, "CONDITIONAL", extractor="conditional_construct", evidence=kind)
                self._append_unique(analysis.behaviors, behavior)
                self._append_unique(analysis.evidence, behavior["evidence"])

    def _analyze_function(
        self,
        source: Node,
        analysis: DaxAnalysis,
        visit: AstVisit,
        name: str,
        all_references: list[tuple[AstVisit, ReferenceInfo, Node]],
    ) -> None:
        upper = str(name).upper()
        category: str | None = None
        if upper in _SELECTOR_FUNCTIONS:
            category = "SELECTOR_CONSTRUCT"
        elif upper in _FILTER_FUNCTIONS:
            category = "FILTER_CONTEXT"
        elif upper in _RELATIONSHIP_FUNCTIONS:
            category = "RELATIONSHIP_CONSTRUCT"
        elif upper in _CONDITIONAL_FUNCTIONS:
            category = "CONDITIONAL"
        elif upper in _FORMAT_FUNCTIONS:
            category = "FORMAT_CONSTRUCT"
        elif self.resolver.resolve(name, ("USER_DEFINED_FUNCTION",), source.model_id) is not None:
            category = "UDF_CALL"
        if upper == "SWITCH" and self._looks_like_format_switch(visit.node):
            category = "FORMAT_CONSTRUCT"
        if category is None:
            return

        function_evidence = make_evidence(
            source.id,
            category,
            None,
            node=visit.node,
            extractor="function_call",
            source="dax_analysis",
            evidence=f"DAX function {upper}",
        )
        behavior = self._behavior_record(
            source,
            visit,
            category,
            extractor="function_call",
            function=upper,
            evidence=function_evidence,
            depth=visit.depth,
        )
        # Keep one evidence object per behavior, but make its human-readable
        # evidence available directly too.
        behavior["evidence"] = function_evidence
        analysis.behaviors.append(behavior)
        analysis.evidence.append(function_evidence)
        if visit.depth > 0:
            nested_evidence = make_evidence(
                source.id,
                "NESTED_FUNCTION",
                None,
                node=visit.node,
                extractor="nested_expression",
                source="dax_analysis",
                evidence=f"Nested DAX function {upper}",
            )
            nested = self._behavior_record(
                source,
                visit,
                "NESTED_FUNCTION",
                extractor="nested_expression",
                function=upper,
                evidence=nested_evidence,
                depth=visit.depth,
            )
            analysis.behaviors.append(nested)
            analysis.evidence.append(nested_evidence)

        nested_refs = list(iter_references(visit.node))
        target_refs = nested_refs
        if upper == "TREATAS":
            arguments = attr(visit.node, "arguments", "args", default=())
            if isinstance(arguments, (list, tuple)):
                target_refs = [item for argument in arguments[1:] for item in iter_references(argument)]
            else:
                target_refs = []
        resolved_targets: list[Node] = []
        seen_targets: set[str] = set()
        for _, info in target_refs:
            contextual_info = self._contextual_reference(source, info)
            resolution = self.resolver.resolve_detailed(
                contextual_info,
                (contextual_info.kind,),
                source.model_id,
            )
            if resolution.resolved and resolution.node and resolution.node.id not in seen_targets:
                seen_targets.add(resolution.node.id)
                resolved_targets.append(resolution.node)
        behavior["target_ids"] = [node.id for node in sorted(resolved_targets, key=lambda item: item.id)]

        if category == "UDF_CALL":
            udf = self.resolver.resolve(name, ("USER_DEFINED_FUNCTION",), source.model_id)
            if udf:
                evidence = make_evidence(
                    source.id,
                    "DEPENDS_ON",
                    udf.id,
                    node=visit.node,
                    extractor="udf_call",
                    source="dax_analysis",
                    evidence=f"DAX call {upper}",
                )
                analysis.evidence.append(evidence)
                self._record_edge(analysis, "DEPENDS_ON", source.id, udf.id, source="dax_analysis", evidence=[evidence])

        if upper in _FILTER_FUNCTIONS:
            for target in resolved_targets:
                if target.type not in {"COLUMN", "TABLE"}:
                    continue
                evidence = make_evidence(
                    source.id,
                    "MODIFIES_FILTER",
                    target.id,
                    node=visit.node,
                    extractor="filter_context_function",
                    source="dax_analysis",
                    evidence=f"DAX function {upper}",
                )
                analysis.evidence.append(evidence)
                self._record_edge(analysis, "MODIFIES_FILTER", source.id, target.id, source="dax_analysis", evidence=[evidence])

        if upper in _RELATIONSHIP_FUNCTIONS:
            columns = [target.id for target in resolved_targets if target.type == "COLUMN"]
            relationship = self.resolver.resolve_relationship(columns, source.model_id)
            edge_type = "ACTIVATES_RELATIONSHIP" if upper == "USERELATIONSHIP" else "MODIFIES_RELATIONSHIP"
            if relationship:
                evidence = make_evidence(
                    source.id,
                    edge_type,
                    relationship.id,
                    node=visit.node,
                    extractor=upper.casefold(),
                    source="dax_analysis",
                    evidence=f"DAX function {upper}",
                )
                analysis.evidence.append(evidence)
                self._record_edge(analysis, edge_type, source.id, relationship.id, source="dax_analysis", evidence=[evidence])
            else:
                analysis.diagnostics.append(
                    {
                        "code": "unresolved_relationship",
                        "source_object": source.id,
                        "function": upper,
                        "message": f"No unique relationship matches {upper} column arguments",
                        "source": "dax_analysis",
                        "evidence": function_evidence,
                    }
                )

    @staticmethod
    def _iter_construct_nodes(ast: Any) -> Iterable[AstVisit]:
        from .visitors import walk_ast

        for visit in walk_ast(ast):
            yield visit

    @staticmethod
    def _looks_like_format_switch(node: Any) -> bool:
        """Recognize dynamic-format SWITCH literals mechanically.

        A SWITCH containing format masks (for example ``"$#,##0"``) is a
        formatting behavior even when the expression does not call FORMAT.
        This records syntax only; it does not infer a business concept.
        """

        from .visitors import walk_ast

        for visit in walk_ast(node):
            literal_type = str(attr(visit.node, "literal_type", "literalType", default="")).upper()
            if literal_type != "STRING":
                continue
            value = attr(visit.node, "value", "text")
            if isinstance(value, Mapping):
                value = attr(value, "value", "text")
            if isinstance(value, str) and re.search(r"(?:[#0%]|\$|€|£|¥)", value):
                return True
        return False

    @staticmethod
    def _reference_text(info: ReferenceInfo) -> str:
        if info.text:
            return info.text
        return f"{info.table + '[' if info.table else '['}{info.name}{']' if info.table else ']'}"

    @staticmethod
    def _reference_record(
        source: Node,
        info: ReferenceInfo,
        target: str | None,
        *,
        evidence: Mapping[str, Any] | None = None,
        scope: str | None = None,
        kind: str | None = None,
    ) -> dict[str, Any]:
        result = {
            "source_object": source.id,
            "type": kind or info.kind,
            "name": info.name,
            "table": info.table,
            "target": target,
            "ast_location": ast_location(info.node),
            "extractor": info.extractor,
            "source": "dax_ast",
            "status": "factual",
            "evidence_class": "FACT",
            "evidence": evidence or {},
        }
        if scope is not None:
            result["scope"] = scope
        return result

    @staticmethod
    def _behavior_record(
        source: Node,
        visit: AstVisit,
        kind: str,
        *,
        extractor: str,
        evidence: Any,
        function: str | None = None,
        depth: int | None = None,
    ) -> dict[str, Any]:
        value = evidence if isinstance(evidence, Mapping) and "source_object" in evidence else make_evidence(
            source.id,
            kind,
            None,
            node=visit.node,
            extractor=extractor,
            source="dax_analysis",
            evidence=evidence,
        )
        record: dict[str, Any] = {
            "source_object": source.id,
            "type": kind,
            "function": function,
            "ast_location": ast_location(visit.node),
            "extractor": extractor,
            "source": "dax_analysis",
            "status": "factual",
            "evidence_class": "FACT",
            "evidence": value,
        }
        if depth is not None:
            record["depth"] = depth
        return record

    def _resolution_diagnostic(self, source: Node, info: ReferenceInfo, resolution: Resolution) -> dict[str, Any]:
        code = "ambiguous_reference" if resolution.ambiguous else "unresolved_reference"
        return {
            "code": code,
            "source_object": source.id,
            "reference_type": info.kind,
            "reference": self._reference_text(info),
            "table": info.table,
            "expected_types": list(resolution.expected_types),
            "candidates": [node.id for node in resolution.candidates],
            "ast_location": ast_location(info.node),
            "extractor": info.extractor,
            "source": "dax_ast",
            "status": "factual",
            "evidence_class": "FACT",
        }

    def _record_edge(
        self,
        analysis: DaxAnalysis,
        edge_type: str,
        from_id: str,
        to_id: str,
        *,
        source: str,
        evidence: Iterable[Any],
    ) -> None:
        edge = self._add_edge(edge_type, from_id, to_id, source=source, evidence=evidence)
        if edge is not None and all(item.id != edge.id for item in analysis.edges):
            analysis.edges.append(edge)

    def _add_edge(
        self,
        edge_type: str,
        from_id: str,
        to_id: str,
        *,
        source: str,
        evidence: Iterable[Any],
    ) -> Edge | None:
        if from_id not in self.nodes or to_id not in self.nodes:
            return None
        marker = f"dax|{edge_type.upper()}|{from_id}|{to_id}"
        edge_id = "edge:" + hashlib.sha256(marker.encode("utf-8")).hexdigest()[:32]
        values = list(evidence)
        current = self._edges.get(edge_id)
        if current is None:
            current = Edge(
                id=edge_id,
                type=edge_type,
                from_id=from_id,
                to_id=to_id,
                source=source,
                confidence=1.0,
                status="factual",
                evidence=values,
                evidence_class="FACT",
            )
            self._edges[edge_id] = current
            return current
        merged = {
            json.dumps(item, sort_keys=True, default=str): item
            for item in [*current.evidence, *values]
        }
        current.evidence = [merged[key] for key in sorted(merged)]
        return current

    @staticmethod
    def _append_unique(values: list[Any], value: Any) -> None:
        marker = json.dumps(value, sort_keys=True, default=str)
        if all(json.dumps(item, sort_keys=True, default=str) != marker for item in values):
            values.append(value)

    @staticmethod
    def _store_analysis(source: Node, analysis: DaxAnalysis) -> None:
        source.properties["dax_behaviors"] = list(analysis.behaviors)
        source.properties["dax_evidence"] = list(analysis.evidence)
        if analysis.diagnostics:
            source.properties["dax_diagnostics"] = list(analysis.diagnostics)


def analyze_dax(
    source_object: Node,
    expression: str,
    *,
    nodes: Iterable[Node] | Mapping[str, Node],
    parser: Any = None,
) -> DaxAnalysis:
    """Analyze one expression using the canonical object set."""

    return DaxAnalyzer(nodes, parser=parser).analyze_object(source_object, expression)


def analyze_nodes(
    nodes: Iterable[Node] | Mapping[str, Node],
    *,
    parser: Any = None,
) -> DaxAnalysisBatch:
    """Analyze all canonical expression-bearing objects once."""

    return DaxAnalyzer(nodes, parser=parser).analyze()


analyze = analyze_nodes
Analyzer = DaxAnalyzer
DAXAnalyzer = DaxAnalyzer


__all__ = [
    "Analyzer",
    "DAXAnalyzer",
    "DaxAnalysis",
    "DaxAnalysisBatch",
    "DaxAnalyzer",
    "ObjectResolver",
    "Resolution",
    "analyze",
    "analyze_dax",
    "analyze_nodes",
]
