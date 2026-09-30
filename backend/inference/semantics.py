"""Small, deterministic semantic assertion helpers.

This module turns explicit metadata and already-extracted DAX observations into
reviewable candidates.  It never changes factual nodes or factual edges.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import re
from typing import Any, Iterable, Mapping, Sequence

from backend.graph.schema import Edge, Node

from .confidence import confidence_from_evidence


_MEANINGFUL_TYPES = frozenset(
    {
        "MODEL",
        "TABLE",
        "COLUMN",
        "MEASURE",
        "FIELD_PARAMETER",
        "SHARED_EXPRESSION",
        "USER_DEFINED_FUNCTION",
        "CALCULATION_GROUP",
        "CALCULATION_ITEM",
    }
)
_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "as",
        "at",
        "by",
        "for",
        "from",
        "in",
        "is",
        "of",
        "on",
        "or",
        "the",
        "to",
        "with",
    }
)
_GENERIC_NAMES = frozenset(
    {
        "column",
        "columns",
        "field",
        "fields",
        "measure",
        "measures",
        "model",
        "table",
        "value",
        "values",
        "name",
        "id",
        "object",
    }
)
def _safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_safe(item) for item in value]
    return str(value)


def _json(value: Any) -> str:
    return json.dumps(_safe(value), ensure_ascii=False, sort_keys=True, default=str)


def _get(value: Any, *keys: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        for key in keys:
            if key in value and value[key] is not None:
                return value[key]
        return default
    for key in keys:
        candidate = getattr(value, key, None)
        if candidate is not None:
            return candidate
    return default


def _analysis_map(analyses: Any) -> dict[str, Any]:
    """Accept a DaxAnalysisBatch or its canonical ``analyses`` mapping."""

    if analyses is None:
        return {}
    batch = getattr(analyses, "analyses", None)
    if batch is not None:
        analyses = batch
    if isinstance(analyses, Mapping) and "analyses" in analyses and isinstance(analyses["analyses"], Mapping):
        analyses = analyses["analyses"]
    if isinstance(analyses, Mapping):
        return {str(key): value for key, value in analyses.items()}
    if isinstance(analyses, (list, tuple, set, frozenset)):
        result: dict[str, Any] = {}
        for item in analyses:
            source_id = _get(item, "source_object_id", "source_object", "object_id", "objectId")
            if source_id is not None:
                result[str(source_id)] = item
        return result
    return {}


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip(" \t\r\n.;:,-")


def _words(value: Any) -> set[str]:
    return {
        word
        for word in re.findall(r"[a-z][a-z0-9]*", str(value or "").casefold())
        if word not in _STOP_WORDS and len(word) > 1
    }


def _slug(value: Any) -> str:
    words = re.findall(r"[a-z0-9]+", str(value or "").casefold())
    return " ".join(words).strip()


def _hash(*parts: Any) -> str:
    marker = "|".join(_json(part) for part in parts)
    return hashlib.sha256(marker.encode("utf-8")).hexdigest()[:32]


def _value_for(candidate: Mapping[str, Any]) -> Any:
    for key in ("value", "meaning", "concept", "role", "behavior", "alias"):
        if candidate.get(key) is not None:
            return candidate[key]
    return None


@dataclass(slots=True)
class SemanticCandidate:
    """A candidate semantic assertion.  It is not factual until reviewed."""

    target: str
    type: str
    value: Any
    source: str
    confidence: float
    evidence: list[Any] = field(default_factory=list)
    status: str = "candidate"
    evidence_class: str = "INFERRED"
    edge_type: str = "SEMANTICALLY_MAPS_TO"
    id: str = ""
    properties: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.target = str(self.target)
        self.type = str(self.type).upper()
        self.source = str(self.source)
        self.status = str(self.status).lower()
        self.evidence_class = str(self.evidence_class).upper()
        self.edge_type = str(self.edge_type).upper()
        self.confidence = max(0.0, min(1.0, float(self.confidence)))
        self.evidence = [_safe(item) for item in self.evidence]
        self.properties = dict(self.properties or {})
        if not self.id:
            self.id = f"semantic:candidate:{_hash(self.target, self.type, self.value, self.edge_type)}"

    @property
    def target_id(self) -> str:
        return self.target

    @property
    def assertion(self) -> str:
        return self.type

    @property
    def meaning(self) -> Any:
        return self.value

    def to_dict(self) -> dict[str, Any]:
        result = {
            "id": self.id,
            "target": self.target,
            "target_id": self.target,
            "type": self.type,
            "assertion": self.type,
            "assertion_type": self.type,
            "value": _safe(self.value),
            "meaning": _safe(self.value),
            "source": self.source,
            "confidence": self.confidence,
            "status": self.status,
            "evidence_class": self.evidence_class,
            "evidence": list(self.evidence),
            "edge_type": self.edge_type,
            "properties": _safe(self.properties),
        }
        result.update({key: _safe(value) for key, value in self.properties.items() if key not in result})
        return result

    as_dict = to_dict

    def __getitem__(self, key: str) -> Any:
        return self.to_dict()[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.to_dict().get(key, default)


@dataclass(slots=True)
class SemanticConflict:
    """A contradiction kept visible for human review."""

    target: str
    description_candidate: str
    reason: str
    evidence: list[Any] = field(default_factory=list)
    confidence: float = 0.0
    status: str = "candidate"
    id: str = ""

    def __post_init__(self) -> None:
        self.target = str(self.target)
        self.description_candidate = str(self.description_candidate)
        self.reason = str(self.reason)
        self.confidence = max(0.0, min(1.0, float(self.confidence)))
        self.status = str(self.status).lower()
        self.evidence = [_safe(item) for item in self.evidence]
        if not self.id:
            self.id = f"semantic:conflict:{_hash(self.target, self.description_candidate, self.reason)}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "target": self.target,
            "target_id": self.target,
            "type": "CONFLICT",
            "assertion": "CONFLICT",
            "description_candidate": self.description_candidate,
            "reason": self.reason,
            "source": "semantic_conflict",
            "confidence": self.confidence,
            "status": self.status,
            "evidence_class": "INFERRED",
            "evidence": list(self.evidence),
        }

    as_dict = to_dict

    def __getitem__(self, key: str) -> Any:
        return self.to_dict()[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.to_dict().get(key, default)


def make_evidence(
    source: str,
    *,
    extractor: str,
    evidence: Any,
    confidence: float | None = None,
    target: str | None = None,
    ast_location: Any = None,
    evidence_class: str = "INFERRED",
) -> dict[str, Any]:
    """Return one stable provenance record for an inferred assertion."""

    result: dict[str, Any] = {
        "source": str(source),
        "extractor": str(extractor),
        "evidence": _safe(evidence),
        "status": "candidate",
        "evidence_class": str(evidence_class).upper(),
    }
    if confidence is not None:
        result["confidence"] = max(0.0, min(1.0, float(confidence)))
    if target is not None:
        result["target"] = str(target)
    if ast_location is not None:
        result["ast_location"] = _safe(ast_location)
    return result


def make_candidate(
    target: str,
    *,
    assertion_type: str = "BUSINESS_CONCEPT",
    value: Any,
    source: str,
    evidence: Iterable[Any] = (),
    confidence: float | None = None,
    edge_type: str = "SEMANTICALLY_MAPS_TO",
    status: str = "candidate",
    properties: Mapping[str, Any] | None = None,
) -> SemanticCandidate:
    evidence_values = [_safe(item) for item in evidence]
    score = confidence_from_evidence(evidence_values) if confidence is None else confidence
    return SemanticCandidate(
        target=str(target),
        type=assertion_type,
        value=_safe(value),
        source=source,
        confidence=score,
        evidence=evidence_values,
        status=status,
        evidence_class="INFERRED",
        edge_type=edge_type,
        properties=dict(properties or {}),
    )


def semantic_node_for(
    candidate: SemanticCandidate,
    *,
    model_id: str | None = None,
    report_id: str | None = None,
) -> Node:
    """Represent a business concept/selector/etc. in the canonical graph."""

    kind = candidate.type.upper()
    if kind == "BUSINESS_CONCEPT":
        node_id = f"semantic:business-concept:{_hash(_slug(candidate.value))}"
        name = _text(candidate.value)
    elif kind == "SELECTOR":
        stable_target = str(candidate.target or "").strip()
        if not stable_target or stable_target.casefold() in {"none", "null"}:
            raise ValueError("selector candidate requires a stable target identity")
        # Selector identity is derived only from the canonical source target.
        # Display labels can change without changing the semantic node.
        node_id = f"semantic:selector:{_hash(stable_target)}"
        name = _text(candidate.value) or "Selector"
    elif kind == "SELECTOR_OPTION":
        node_id = f"semantic:selector-option:{_hash(candidate.target, candidate.value)}"
        name = _text(candidate.value)
    else:
        node_id = f"semantic:{kind.casefold()}:{_hash(candidate.target, kind, candidate.value)}"
        name = _text(candidate.value) or kind.casefold().replace("_", " ")
    properties = {
        "assertion_type": kind,
        "meaning": _safe(candidate.value),
        "candidate_id": candidate.id,
        "candidate_source": candidate.source,
        "candidate_confidence": candidate.confidence,
        "confidence": candidate.confidence,
        "candidate_evidence": list(candidate.evidence),
        "evidence": list(candidate.evidence),
        **candidate.properties,
    }
    node = Node(
        id=node_id,
        type=kind,
        name=name,
        description=name,
        model_id=model_id or candidate.properties.get("model_id"),
        report_id=report_id or candidate.properties.get("report_id"),
        source_id=node_id.rsplit(":", 1)[-1],
        status=candidate.status,
        properties=properties,
        source=candidate.source,
    )
    return node


def edge_for(candidate: SemanticCandidate, semantic_node: Node) -> Edge:
    marker = _hash(candidate.edge_type, candidate.target, semantic_node.id, candidate.id)
    return Edge(
        id=f"edge:semantic:{marker}",
        type=candidate.edge_type,
        from_id=candidate.target,
        to_id=semantic_node.id,
        # Keep provenance in evidence/properties.  The edge itself is emitted
        # by the semantic stage, so Phase 2 consumers never mistake it for a
        # factual DAX edge merely because DAX supplied the signal.
        source="semantic_inference",
        confidence=candidate.confidence,
        status=candidate.status,
        evidence=list(candidate.evidence),
        evidence_class="INFERRED",
        properties={
            "assertion_type": candidate.type,
            "value": _safe(candidate.value),
            "candidate_id": candidate.id,
            "candidate_source": candidate.source,
            **candidate.properties,
        },
    )


def _description_evidence(node: Node) -> dict[str, Any]:
    return make_evidence(
        "description",
        extractor="description_interpretation",
        evidence=f"Description: {node.description}",
        target=node.id,
    )


def _name_evidence(node: Node) -> dict[str, Any]:
    return make_evidence(
        "object_name",
        extractor="name_interpretation",
        evidence=f"Object name: {node.name}",
        target=node.id,
    )


def description_candidates(node: Node) -> list[SemanticCandidate]:
    """Use a meaningful description before weaker name/DAX signals."""

    if node.type not in _MEANINGFUL_TYPES or not _text(node.description):
        return []
    meaning = _text(node.description)
    evidence = [_description_evidence(node)]
    candidates = [
        make_candidate(
            node.id,
            value=meaning,
            source="description",
            evidence=evidence,
            properties={"priority": 1, "description": meaning},
        )
    ]
    name = _text(node.name)
    if name and _slug(name) != _slug(meaning) and _slug(name) not in _GENERIC_NAMES:
        candidates.append(
            make_candidate(
                node.id,
                assertion_type="ALIAS",
                value=name,
                source="description",
                evidence=evidence + [_name_evidence(node)],
                edge_type="SEMANTICALLY_MAPS_TO",
                properties={"for_meaning": meaning, "priority": 1},
            )
        )
    role = role_from_text(meaning)
    if role:
        candidates.append(
            make_candidate(
                node.id,
                assertion_type="ROLE",
                value=role,
                source="description",
                evidence=evidence,
                properties={"priority": 1},
            )
        )
    return candidates


def name_candidates(node: Node) -> list[SemanticCandidate]:
    if node.type not in _MEANINGFUL_TYPES or _text(node.description):
        return []
    name = _text(node.name)
    if not name or _slug(name) in _GENERIC_NAMES or re.fullmatch(r"(?:table|column|measure)[ _-]?\d+", name, re.I):
        return []
    return [
        make_candidate(
            node.id,
            value=name,
            source="object_name",
            evidence=[_name_evidence(node)],
            properties={"priority": 5},
        )
    ]


def role_from_text(value: Any) -> str | None:
    words = _words(value)
    if words & {"date", "calendar", "time", "period"}:
        return "date_dimension"
    if words & {"customer", "client", "account"}:
        return "customer_dimension"
    if words & {"product", "item", "sku"}:
        return "product_dimension"
    if words & {"fact", "transaction", "invoice", "sales", "orders", "order"}:
        return "fact"
    if words & {"selector", "switch", "parameter", "choice", "option"}:
        return "selector"
    return None


def behavior_candidates(node: Node, analysis: Any = None) -> list[SemanticCandidate]:
    """Map existing DAX behavior facts to reviewable behavior assertions."""

    behaviors = getattr(analysis, "behaviors", None) if analysis is not None else None
    if behaviors is None:
        behaviors = node.properties.get("dax_behaviors", [])
    if not isinstance(behaviors, (list, tuple)):
        return []
    result: list[SemanticCandidate] = []
    seen: set[tuple[str, str]] = set()
    for behavior in behaviors:
        if not isinstance(behavior, Mapping):
            continue
        function = str(behavior.get("function") or behavior.get("type") or "").upper()
        kind = str(behavior.get("type") or "BEHAVIOR").upper()
        value = function or kind
        if not value or (kind, value) in seen:
            continue
        seen.add((kind, value))
        evidence = behavior.get("evidence")
        if not isinstance(evidence, Mapping):
            evidence = make_evidence(
                "dax_analysis",
                extractor=str(behavior.get("extractor") or "behavior_analysis"),
                evidence=behavior,
                target=node.id,
                ast_location=behavior.get("ast_location"),
            )
        else:
            evidence = dict(evidence)
            evidence.setdefault("source", "dax_analysis")
            evidence.setdefault("status", "candidate")
            evidence.setdefault("evidence_class", "INFERRED")
        result.append(
            make_candidate(
                node.id,
                assertion_type="BEHAVIOR",
                value=value,
                source="dax_analysis",
                evidence=[evidence],
                properties={
                    "behavior_kind": kind,
                    "function": function or None,
                    "ast_location": behavior.get("ast_location"),
                    "priority": 2,
                },
            )
        )
    return result


def infer_candidates(
    nodes: Iterable[Node] | Mapping[str, Node],
    analyses: Any = None,
) -> list[SemanticCandidate]:
    """Generate candidates from nodes and a DaxAnalysisBatch/mapping.

    ``analyses`` must be existing analyzer output.  This function never reads
    or parses raw DAX text.
    """

    values = nodes.values() if isinstance(nodes, Mapping) else nodes
    analysis_map = _analysis_map(analyses)
    result: list[SemanticCandidate] = []
    for node in sorted(values, key=lambda item: str(item.id)):
        result.extend(description_candidates(node))
        result.extend(name_candidates(node))
        result.extend(behavior_candidates(node, analysis_map.get(node.id)))
    unique: dict[str, SemanticCandidate] = {}
    for candidate in result:
        unique.setdefault(candidate.id, candidate)
    return sorted(unique.values(), key=lambda item: item.id)


def _behavior_records(analysis: Any) -> list[Mapping[str, Any]]:
    values = _get(analysis, "behaviors", default=[])
    if not isinstance(values, (list, tuple)):
        return []
    return [item for item in values if isinstance(item, Mapping)]


def _reference_target_ids(analysis: Any) -> list[str]:
    references = _get(analysis, "references", default=[])
    if not isinstance(references, (list, tuple)):
        return []
    return [str(target) for item in references if (target := _get(item, "target", "target_id"))]


def _behavior_role(behavior: Mapping[str, Any]) -> str | None:
    kind = str(behavior.get("type") or "").upper()
    function = str(behavior.get("function") or "").upper()
    label = function or kind
    if kind == "SELECTOR_CONSTRUCT" or function in {
        "SELECTEDVALUE",
        "VALUES",
        "HASONEVALUE",
        "ISFILTERED",
        "ISCROSSFILTERED",
        "FILTERS",
    }:
        return "selector"
    if kind == "FILTER_CONTEXT" or function in {
        "CALCULATE",
        "CALCULATETABLE",
        "FILTER",
        "TREATAS",
        "REMOVEFILTERS",
        "ALL",
        "ALLEXCEPT",
        "ALLSELECTED",
        "KEEPFILTERS",
    }:
        return "filter_context"
    if kind == "RELATIONSHIP_CONSTRUCT" or function in {"USERELATIONSHIP", "CROSSFILTER"}:
        return "relationship"
    if kind == "FORMAT_CONSTRUCT" or function in {"FORMAT", "SELECTEDMEASURE", "SELECTEDMEASUREFORMATSTRING"}:
        return "formatting"
    if kind == "CONDITIONAL" or function in {"IF", "SWITCH", "COALESCE"}:
        return "conditional"
    if kind == "UDF_CALL":
        return "function"
    return label.casefold() if label else None


def _declared_roles(value: Any) -> set[str]:
    words = _words(value)
    roles: set[str] = set()
    if words & {"fact", "transaction", "invoice", "sales", "orders", "order"}:
        roles.add("fact")
    if "dimension" in words or words & {"calendar", "date", "customer", "product"}:
        roles.add("dimension")
    if words & {"selector", "switch", "parameter", "choice", "option", "options"}:
        roles.add("selector")
    if words & {"measure", "metric", "calculation", "calculated"}:
        roles.add("measure")
    return roles


def _behavior_targets(analysis: Any) -> set[str]:
    target_ids: set[str] = set()
    for item in _get(analysis, "references", default=[]):
        target = _get(item, "target", "target_id")
        if target:
            target_ids.add(str(target))
    for behavior in _behavior_records(analysis):
        values = behavior.get("target_ids", [])
        if not isinstance(values, (list, tuple, set, frozenset)):
            values = [values]
        target_ids.update(str(value) for value in values if value)
    return target_ids


def _selector_behavior_for(
    node: Node,
    analyses: Mapping[str, Any],
    by_id: Mapping[str, Node],
) -> Mapping[str, Any] | None:
    # A measure's behavior belongs to that measure.  A different measure may
    # reference it while using SELECTEDVALUE for its own selector; that is not
    # behavior of the referenced measure.
    if node.type == "MEASURE":
        for behavior in _behavior_records(analyses.get(node.id)):
            if _behavior_role(behavior) == "selector":
                return behavior
        return None
    children = {
        item.id
        for item in by_id.values()
        if item.type == "COLUMN" and str(item.properties.get("table_id")) == node.id
    }
    targets = {node.id, *children}
    for analysis in analyses.values():
        for behavior in _behavior_records(analysis):
            if _behavior_role(behavior) != "selector":
                continue
            behavior_targets = behavior.get("target_ids", behavior.get("targetIds"))
            if behavior_targets is None:
                behavior_targets = behavior.get("target", behavior.get("target_id"))
            if isinstance(behavior_targets, Mapping):
                behavior_targets = behavior_targets.get("id", behavior_targets.get("target"))
            if behavior_targets is not None and not isinstance(
                behavior_targets, (list, tuple, set, frozenset)
            ):
                behavior_targets = [behavior_targets]
            if behavior_targets:
                if not ({str(value) for value in behavior_targets if value} & targets):
                    continue
            elif not (set(_reference_target_ids(analysis)) & targets):
                continue
            # Cross-object behavior is valid only when the selector construct
            # resolves to this table or one of its canonical columns.
            if targets:
                return behavior
    return None


def _negative_behavior_conflict(description: Any, behavior_role: str | None) -> bool:
    if not behavior_role:
        return False
    text = str(description or "").casefold()
    # Only explicit denial is treated as a contradiction.  Missing words are
    # uncertainty, not evidence of the opposite.
    aliases = {
        "selector": ("selector", "switch", "parameter", "selected value"),
        "filter_context": ("filter", "filtered", "filter context"),
        "relationship": ("relationship", "relation"),
        "formatting": ("format", "formatted", "formatting"),
        "conditional": ("condition", "conditional", "branch"),
        "function": ("function", "call"),
    }.get(behavior_role, (behavior_role.replace("_", " "),))
    negative = r"(?:not|never|without|no|does not|doesn't|isn't|is not)"
    return any(re.search(rf"{negative}(?:\W+\w+){{0,5}}\W+{re.escape(alias)}\b", text) for alias in aliases)


def detect_conflicts(
    nodes: Iterable[Node] | Mapping[str, Node],
    candidates: Sequence[SemanticCandidate],
    analyses: Any = None,
) -> list[SemanticConflict]:
    """Find explicit description-vs-behavior contradictions.

    ``analyses`` accepts a DaxAnalysisBatch or canonical ``analyses`` mapping.
    Contradictions require positive analyzer evidence plus either an explicit
    denial or mutually exclusive declared roles; absence of evidence alone is
    never a conflict.
    """

    values = nodes.values() if isinstance(nodes, Mapping) else nodes
    by_id = {str(node.id): node for node in values}
    analysis_map = _analysis_map(analyses)
    results: list[SemanticConflict] = []
    for candidate in candidates:
        if candidate.type != "BUSINESS_CONCEPT" or candidate.source != "description":
            continue
        node = by_id.get(candidate.target)
        if node is None:
            continue
        roles = _declared_roles(candidate.value)
        selector_behavior = _selector_behavior_for(node, analysis_map, by_id)
        behavior_records = _behavior_records(analysis_map.get(node.id))
        candidates_to_check: list[Mapping[str, Any]] = list(behavior_records)
        if selector_behavior is not None and selector_behavior not in candidates_to_check:
            candidates_to_check.append(selector_behavior)
        for behavior in candidates_to_check:
            behavior_role = _behavior_role(behavior)
            if not behavior_role:
                continue
            role_conflict = ("fact" in roles or "dimension" in roles) and behavior_role == "selector"
            explicit_conflict = _negative_behavior_conflict(candidate.value, behavior_role)
            if not role_conflict and not explicit_conflict:
                continue
            desc_evidence = candidate.evidence[0] if candidate.evidence else {}
            behavior_evidence = make_evidence(
                "dax_analysis",
                extractor="semantic_contradiction",
                evidence=(
                    f"Analyzer behavior {behavior_role} conflicts with declared description role."
                    if role_conflict
                    else f"Description explicitly denies {behavior_role} behavior."
                ),
                target=node.id,
                ast_location=behavior.get("ast_location"),
            )
            results.append(
                SemanticConflict(
                    target=node.id,
                    description_candidate=candidate.id,
                    reason=(
                        f"description declares {sorted(roles)} but analyzer reports {behavior_role} behavior"
                        if role_conflict
                        else f"description denies {behavior_role} behavior"
                    ),
                    evidence=[desc_evidence, behavior_evidence],
                    confidence=confidence_from_evidence([desc_evidence, behavior_evidence]),
                )
            )
            break
    unique = {item.id: item for item in results}
    return sorted(unique.values(), key=lambda item: item.id)


__all__ = [
    "SemanticCandidate",
    "SemanticConflict",
    "behavior_candidates",
    "description_candidates",
    "detect_conflicts",
    "edge_for",
    "infer_candidates",
    "make_candidate",
    "make_evidence",
    "name_candidates",
    "role_from_text",
    "semantic_node_for",
]
