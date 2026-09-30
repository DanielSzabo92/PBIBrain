"""Small, serialisable contracts shared by every Brain layer.

The graph deliberately uses one node table and one edge table.  This keeps the
canonical model extensible while object-specific fields remain in ``properties``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

OBJECT_TYPES = frozenset(
    {
        "WORKSPACE",
        "MODEL",
        "TABLE",
        "COLUMN",
        "MEASURE",
        "RELATIONSHIP",
        "FIELD_PARAMETER",
        "SHARED_EXPRESSION",
        "USER_DEFINED_FUNCTION",
        "CALCULATION_GROUP",
        "CALCULATION_ITEM",
        "REPORT",
        "PAGE",
        "VISUAL",
        "VISUAL_CALCULATION",
        "VISUAL_FILTER",
        "PAGE_FILTER",
        "REPORT_FILTER",
        "BUSINESS_CONCEPT",
        "SELECTOR",
        "SELECTOR_OPTION",
        "CONFLICT",
        "SEMANTIC_ASSERTION",
    }
)

EDGE_TYPES = frozenset(
    {
        "CONTAINS",
        "BELONGS_TO",
        "DEPENDS_ON",
        "REFERENCES",
        "MODIFIES_FILTER",
        "ACTIVATES_RELATIONSHIP",
        "MODIFIES_RELATIONSHIP",
        "USES",
        "RELATES_TO",
        "FILTERS",
        "USES_MODEL",
        "CONTROLLED_BY",
        "HAS_OPTION",
        "DEFAULTS_TO",
        "SEMANTICALLY_MAPS_TO",
        "SIMILAR_TO",
        "OBSERVED_WITH",
        "CONFLICTS_WITH",
        "ALIAS_OF",
        "HAS_ROLE",
        "HAS_BEHAVIOR",
    }
)

STATUS_VALUES = frozenset({"factual", "candidate", "approved", "rejected", "overridden"})
EVIDENCE_CLASSES = frozenset({"FACT", "INFERRED", "OBSERVED"})


def _copy_mapping(value: Mapping[str, Any] | None) -> dict[str, Any]:
    return dict(value or {})


@dataclass(slots=True)
class Node:
    """Universal graph node contract.

    Object-specific metadata is kept in ``properties`` and mirrored at the
    top-level by :meth:`to_dict` for convenient JSON/API consumers.
    """

    id: str
    type: str
    name: str = ""
    description: str | None = None
    model_id: str | None = None
    report_id: str | None = None
    source_id: str | None = None
    status: str = "factual"
    properties: dict[str, Any] = field(default_factory=dict)
    source: str = "model_metadata"

    def __post_init__(self) -> None:
        self.id = str(self.id)
        self.type = str(self.type).upper()
        self.name = "" if self.name is None else str(self.name)
        if self.description is not None:
            self.description = str(self.description)
        if self.source_id is not None:
            self.source_id = str(self.source_id)
        self.status = str(self.status).lower()
        if self.status not in STATUS_VALUES:
            raise ValueError(f"Unsupported node status: {self.status}")
        if self.type not in OBJECT_TYPES:
            # ponytail: the ontology is intentionally extensible; unknown types
            # are preserved instead of blocking a new Power BI object.
            self.type = str(self.type)
        self.properties = _copy_mapping(self.properties)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": self.id,
            "type": self.type,
            "name": self.name,
            "description": self.description,
            "model_id": self.model_id,
            "report_id": self.report_id,
            "source_id": self.source_id,
            "status": self.status,
            "source": self.source,
            "properties": dict(self.properties),
        }
        for key, value in self.properties.items():
            result.setdefault(key, value)
        return result

    as_dict = to_dict

    def __getitem__(self, key: str) -> Any:
        return self.to_dict()[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.to_dict().get(key, default)

    def __contains__(self, key: object) -> bool:
        return key in self.to_dict()


@dataclass(slots=True)
class Edge:
    """Universal graph edge contract."""

    id: str
    type: str
    from_id: str
    to_id: str
    source: str = "model_metadata"
    confidence: float = 1.0
    status: str = "factual"
    evidence: list[Any] = field(default_factory=list)
    evidence_class: str = "FACT"
    properties: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.id = str(self.id)
        self.type = str(self.type).upper()
        self.from_id = str(self.from_id)
        self.to_id = str(self.to_id)
        self.status = str(self.status).lower()
        if self.status not in STATUS_VALUES:
            raise ValueError(f"Unsupported edge status: {self.status}")
        self.confidence = float(self.confidence)
        if not 0 <= self.confidence <= 1:
            raise ValueError("Edge confidence must be between 0 and 1")
        self.evidence_class = str(self.evidence_class).upper()
        if self.evidence_class not in EVIDENCE_CLASSES:
            raise ValueError(f"Unsupported evidence class: {self.evidence_class}")
        self.evidence = list(self.evidence or [])
        self.properties = _copy_mapping(self.properties)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "from_id": self.from_id,
            "to_id": self.to_id,
            "source": self.source,
            "confidence": self.confidence,
            "status": self.status,
            "evidence": list(self.evidence),
            "evidence_class": self.evidence_class,
            "properties": dict(self.properties),
        }

    as_dict = to_dict

    def __getitem__(self, key: str) -> Any:
        return self.to_dict()[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.to_dict().get(key, default)


def node_from_dict(value: Node | Mapping[str, Any]) -> Node:
    if isinstance(value, Node):
        return value
    data = dict(value)
    properties = dict(data.pop("properties", {}) or {})
    common = {"id", "type", "name", "description", "model_id", "report_id", "source_id", "status", "source"}
    for key in list(data):
        if key not in common:
            properties.setdefault(key, data.pop(key))
    return Node(properties=properties, **{key: data.get(key) for key in common if key in data})


def edge_from_dict(value: Edge | Mapping[str, Any]) -> Edge:
    if isinstance(value, Edge):
        return value
    data = dict(value)
    return Edge(
        id=data["id"],
        type=data["type"],
        from_id=data["from_id"],
        to_id=data["to_id"],
        source=data.get("source", "model_metadata"),
        confidence=data.get("confidence", 1.0),
        status=data.get("status", "factual"),
        evidence=data.get("evidence", []),
        evidence_class=data.get("evidence_class", "FACT"),
        properties=data.get("properties", {}),
    )


def serialize_nodes(nodes: Iterable[Node]) -> list[dict[str, Any]]:
    return [node.to_dict() for node in sorted(nodes, key=lambda item: item.id)]


def serialize_edges(edges: Iterable[Edge]) -> list[dict[str, Any]]:
    return [edge.to_dict() for edge in sorted(edges, key=lambda item: item.id)]


# Friendly aliases for callers that prefer the contract's terminology.
CanonicalNode = Node
CanonicalEdge = Edge


def ladybug_schema() -> tuple[str, str]:
    """Return the minimal Ladybug schema used by the native repository."""

    return (
        "CREATE NODE TABLE BrainNode(id STRING PRIMARY KEY, type STRING, name STRING, description STRING, model_id STRING, report_id STRING, source_id STRING, status STRING, source STRING, properties STRING)",
        "CREATE REL TABLE BrainEdge(FROM BrainNode TO BrainNode, id STRING, type STRING, source STRING, confidence DOUBLE, status STRING, evidence_class STRING, evidence STRING, properties STRING)",
    )
