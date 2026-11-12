"""Capability-based execution interfaces. Credentials never enter audit evidence."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from collections.abc import Callable
from backend.validation.powerbi import ReadOnlyValidationAdapter
from .schema import ExecutionContext


@dataclass(frozen=True)
class Capabilities:
    backend: str
    query_readonly_enforced: bool = False
    frozen_data: bool = False
    role_context: bool = False
    typed_results: bool = False
    real_execution: bool = False


@dataclass(frozen=True)
class RuntimeBinding:
    """Trusted loader attestation; never supplied by the coding agent."""
    snapshot_id: str
    model_identity: str
    context_hash: str
    load_evidence_hash: str
    read_permission_evidence_hash: str

    def matches(self, snapshot_id: str, context: ExecutionContext) -> bool:
        return self.snapshot_id == snapshot_id and self.context_hash == context.context_hash and bool(
            self.model_identity and self.load_evidence_hash and self.read_permission_evidence_hash)


class UnavailableAdapter:
    def __init__(self, backend: str = "LOCAL_ANALYSIS_SERVICES") -> None:
        self.capabilities = Capabilities(backend)

    def execute_readonly(self, query: str, params=None):
        raise RuntimeError("Required runtime backend unavailable")


class TestDouble(ReadOnlyValidationAdapter):
    """Useful for tests; never accepted as certified live runtime evidence."""
    def __init__(self, executor: Callable[..., Any]) -> None:
        super().__init__(executor)
        self.capabilities = Capabilities("TEST_DOUBLE", True, True, True, True, False)

