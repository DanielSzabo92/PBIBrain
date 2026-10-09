from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from backend.snapshots.manifest import content_hash

MODES = {"EXACT", "NUMERIC_TOLERANCE", "EXPECTED_CHANGE", "PRESERVE_AGGREGATE", "EXPECTED_VALUE", "EXPECTED_DELTA", "SET_EQUIVALENCE", "SCHEMA_ONLY", "MONITOR"}


@dataclass(frozen=True)
class ExecutionContext:
    data_snapshot_id: str
    processed_state_id: str
    culture: str
    role: str | None
    parameters_json: str = "{}"
    filter_context_json: str = "{}"
    calculation_configuration_json: str = "{}"
    evaluation_time: str | None = None
    data_frozen: bool = False

    @property
    def context_hash(self) -> str:
        return content_hash(self.__dict__)


@dataclass(frozen=True)
class RegressionTest:
    test_id: str
    target_objects: tuple[str, ...]
    query: str
    mode: str = "EXACT"
    comparison_json: str = "{}"
    required: bool = True
    category: str = "affected_measure"
    covered_path_ids: tuple[str, ...] = ()
    invariant_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        import json
        if not self.test_id or not self.target_objects or not self.query.strip() or self.mode not in MODES or type(self.required) is not bool:
            raise ValueError("Invalid regression test schema")
        comparison = json.loads(self.comparison_json)
        if not isinstance(comparison, dict):
            raise ValueError("Comparison policy must be an object")
        # Merely allowing any changed number is insufficient. Expected changes
        # require explicit expected datasets or numerical delta bounds.
        if self.mode in {"EXPECTED_CHANGE", "EXPECTED_VALUE"} and "expected_result" not in comparison:
            raise ValueError("Expected behavior requires an explicit expected result")
        if self.mode == "EXPECTED_DELTA" and not {"minimum_delta", "maximum_delta"}.issubset(comparison):
            raise ValueError("Expected delta requires explicit bounds")
        if self.mode in {"NUMERIC_TOLERANCE", "PRESERVE_AGGREGATE"} and "numeric" not in comparison:
            raise ValueError("Numeric tolerance must be explicit")
