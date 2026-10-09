"""Capability-based execution interfaces. Credentials never enter audit evidence."""
from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Callable
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler
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


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise RuntimeError("Validation redirects forbidden")


class SemanticModelQueryAPI:
    """Power BI ExecuteQueries endpoint has a query-only server command surface.

    Configuration and token supplier belong to the trusted evaluator. Use an
    isolated model, Read+Build grants, and an independently frozen data state.
    RLS impersonation and authoritative column types are unsupported here, so
    this backend reports typed_results=False and cannot certify full regression.
    """
    def __init__(self, model_id: str, token_supplier: Callable[[], str], context: ExecutionContext, *, timeout: int = 30) -> None:
        import uuid
        uuid.UUID(model_id)
        if not callable(token_supplier):
            raise TypeError("Trusted credential supplier required")
        self.model_id, self.token_supplier, self.context, self.timeout = model_id, token_supplier, context, timeout
        self.capabilities = Capabilities("POWER_BI_EXECUTE_QUERIES", True, context.data_frozen, False, False, True)
        self.opener = build_opener(ProxyHandler({}), _NoRedirect())

    def execute_readonly(self, query: str, params=None):
        if params or self.context.role:
            raise ValueError("This query API does not support parameters or role contexts")
        request = Request(f"https://api.powerbi.com/v1.0/myorg/datasets/{self.model_id}/executeQueries",
                          data=json.dumps({"queries": [{"query": query}], "serializerSettings": {"includeNulls": True}}).encode("utf-8"),
                          headers={"Content-Type": "application/json", "Authorization": "Bearer " + self.token_supplier()}, method="POST")
        with self.opener.open(request, timeout=self.timeout) as response:
            value = json.load(response)
        results = value.get("results", [])
        if len(results) != 1 or results[0].get("error") or len(results[0].get("tables", [])) != 1:
            raise RuntimeError("Query response failed or incomplete")
        rows = results[0]["tables"][0].get("rows", [])
        names = sorted({key for row in rows for key in row})
        return {"columns": [{"name": name, "type": "UNKNOWN"} for name in names], "rows": rows}
