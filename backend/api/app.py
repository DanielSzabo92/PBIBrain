"""Local Inspector API and small dependency-free WSGI transport."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import parse_qs, unquote, urlsplit

from backend.context import get_context as build_context
from backend.graph.repository import GraphRepository

from .graph import find_path, get_graph
from .objects import (
    get_dependencies,
    get_dependents,
    get_neighbors,
    get_object,
    get_semantics,
    get_usage,
    inspect_object,
    search_objects,
)
from .queries import validate_selection
from .review import (
    OverrideStore,
    apply_overrides_to_dict,
    approve,
    edit,
    get_review_queue,
    override,
    reject,
    remove_override,
)


def _last_scan(repository: GraphRepository) -> Any:
    for name in ("last_scan", "scan_timestamp", "last_scan_at"):
        value = getattr(repository, name, None)
        if value:
            return value
    path = getattr(repository, "path", None)
    if path is not None:
        try:
            return datetime.fromtimestamp(Path(path).stat().st_mtime, tz=timezone.utc).isoformat()
        except OSError:
            pass
    if getattr(repository, "nodes", None):
        value = datetime.now(timezone.utc).isoformat()
        try:
            repository.last_scan = value
        except AttributeError:
            pass
        return value
    return None


def _default_overrides_path() -> Path:
    return Path("config") / "overrides.json"


def get_overview(repository: GraphRepository, *, store: OverrideStore | None = None) -> dict[str, Any]:
    """Return the compact status/count payload used by the Overview screen."""

    nodes = repository.all_nodes()
    edges = repository.all_edges()
    counts = Counter(node.type for node in nodes)
    candidate_count = sum(1 for node in nodes if node.status == "candidate") + sum(
        1 for edge in edges if edge.status == "candidate"
    )
    warning_count = sum(1 for node in nodes if node.type == "CONFLICT") + sum(
        1 for edge in edges if edge.type == "CONFLICTS_WITH"
    )
    validation = getattr(repository, "validation_result", None)
    validation_state = getattr(repository, "validation_state", None)
    if validation_state is None:
        validation_state = getattr(validation, "state", "not_run") if validation is not None else "not_run"
    return {
        "models": sum(1 for node in nodes if node.type == "MODEL"),
        "reports": sum(1 for node in nodes if node.type == "REPORT"),
        "model_ids": sorted(node.id for node in nodes if node.type == "MODEL"),
        "report_ids": sorted(node.id for node in nodes if node.type == "REPORT"),
        "last_scan": _last_scan(repository),
        "scan_state": "ready" if nodes else "empty",
        "state": "ready" if nodes else "empty",
        "object_counts": dict(sorted(counts.items())),
        "counts": {"nodes": len(nodes), "edges": len(edges)},
        "candidate_count": candidate_count,
        "warning_count": warning_count,
        "validation_state": str(validation_state),
    }


def apply_review(
    repository: GraphRepository,
    item_id: str,
    action: str,
    payload: Mapping[str, Any] | None = None,
    *,
    store: OverrideStore | None = None,
) -> dict[str, Any]:
    """Apply one review command through the same facade used by HTTP."""

    api = BrainAPI(repository)
    api.overrides = store or OverrideStore(_default_overrides_path())
    return api.apply_review(item_id, action, payload)


def get_context(
    repository: GraphRepository,
    target: str,
    task: str | Mapping[str, Any] | None = None,
    *,
    store: OverrideStore | None = None,
) -> dict[str, Any]:
    """Return one canonical, task-scoped context package."""

    return build_context(repository, target, task, store=store)


def _snapshot(repository: GraphRepository, store: OverrideStore | None = None) -> dict[str, Any]:
    """Build the JSON shape consumed by the local Inspector."""

    nodes = repository.all_nodes()
    edges = repository.all_edges()
    node_payloads = {node.id: apply_overrides_to_dict(node.to_dict(), store) for node in nodes}
    edge_payloads = [apply_overrides_to_dict(edge.to_dict(), store) for edge in edges]
    candidates: dict[str, dict[str, Any]] = {}
    conflicts: dict[str, dict[str, Any]] = {}
    for edge in edge_payloads:
        if edge.get("evidence_class") != "INFERRED":
            continue
        props = edge.get("properties") if isinstance(edge.get("properties"), Mapping) else {}
        conflict_node_id = next(
            (
                endpoint
                for endpoint in (edge.get("from_id"), edge.get("to_id"))
                if node_payloads.get(str(endpoint), {}).get("type") == "CONFLICT"
            ),
            None,
        )
        candidate_id = conflict_node_id or props.get("candidate_id") or edge.get("id")
        record = {
            "id": candidate_id,
            "target": edge.get("from_id"),
            "target_id": edge.get("from_id"),
            "type": props.get("assertion_type", edge.get("type")),
            "value": edge.get("value") if edge.get("value") is not None else props.get("value", edge.get("meaning")),
            "meaning": edge.get("meaning") if edge.get("meaning") is not None else props.get("value", edge.get("value")),
            "source": edge.get("source"),
            "confidence": edge.get("confidence", 0.0),
            "status": edge.get("status", "candidate"),
            "evidence_class": edge.get("evidence_class"),
            "evidence": edge.get("evidence", []),
            "edge_id": edge.get("id"),
            "edge_type": edge.get("type"),
            "properties": props,
        }
        target_node = node_payloads.get(str(edge.get("from_id")))
        if target_node is not None:
            record["model_id"] = target_node.get("model_id")
            record["report_id"] = target_node.get("report_id")
        if edge.get("type") == "CONFLICTS_WITH":
            conflicts.setdefault(str(candidate_id), record)
        else:
            candidates.setdefault(str(candidate_id), record)
    for node in node_payloads.values():
        if node.get("type") != "CONFLICT":
            continue
        props = node.get("properties") if isinstance(node.get("properties"), Mapping) else {}
        record = dict(props)
        record.setdefault("id", node.get("id"))
        record.setdefault("target", record.get("target_id"))
        record.setdefault("target_id", record.get("target"))
        record.setdefault("type", "CONFLICT")
        record.setdefault("status", node.get("status", "candidate"))
        record.setdefault("confidence", props.get("confidence", 0.0))
        record.setdefault("evidence", props.get("evidence", []))
        target_node = node_payloads.get(str(record.get("target") or record.get("target_id")))
        if target_node is not None:
            record.setdefault("model_id", target_node.get("model_id"))
            record.setdefault("report_id", target_node.get("report_id"))
        conflicts[str(record["id"])] = record
    overview = get_overview(repository, store=store)
    review_items = get_review_queue(repository, store)
    validation_result = getattr(repository, "validation_result", None)
    if validation_result is None:
        validation_payload: dict[str, Any] = {"state": overview["validation_state"], "checked": False}
    elif hasattr(validation_result, "to_dict") and callable(validation_result.to_dict):
        validation_payload = validation_result.to_dict()
    elif isinstance(validation_result, Mapping):
        validation_payload = dict(validation_result)
    else:
        validation_payload = {"state": overview["validation_state"]}
    return {
        "nodes": list(node_payloads.values()),
        "edges": edge_payloads,
        "semantic_candidates": sorted(candidates.values(), key=lambda item: str(item.get("id", ""))),
        "conflicts": sorted(conflicts.values(), key=lambda item: str(item.get("id", ""))),
        "observations": [edge for edge in edge_payloads if edge.get("evidence_class") == "OBSERVED"],
        "diagnostics": [],
        "scan": {
            "state": overview["scan_state"],
            "last_scan": overview["last_scan"],
        },
        "validation": validation_payload,
        "overrides": store.records() if store is not None else [],
        "review_items": review_items,
        "review_queue": review_items,
        "stale_overrides": [item for item in review_items if item.get("issue_type") == "stale"],
        "overview": overview,
    }


class BrainAPI:
    """In-process API facade shared by the UI transport and tests."""

    def __init__(
        self,
        repository: GraphRepository | None = None,
        *,
        database_path: str | Path | None = None,
        overrides_path: str | Path | None = None,
        use_native: bool | None = None,
    ) -> None:
        self._owns_repository = repository is None
        self.repository = repository or GraphRepository(database_path, use_native=use_native)
        self.overrides = OverrideStore(overrides_path or _default_overrides_path())

    def get_overview(self) -> dict[str, Any]:
        return get_overview(self.repository, store=self.overrides)

    def get_snapshot(self) -> dict[str, Any]:
        return _snapshot(self.repository, self.overrides)

    def search_objects(
        self,
        query: str = "",
        *,
        object_type: str | Sequence[str] | None = None,
        model_id: str | None = None,
        report_id: str | None = None,
    ) -> list[dict[str, Any]]:
        return search_objects(
            self.repository,
            query,
            object_type=object_type,
            model_id=model_id,
            report_id=report_id,
            store=self.overrides,
        )

    def get_object(self, object_id: str) -> dict[str, Any] | None:
        return get_object(self.repository, object_id, store=self.overrides)

    def inspect_object(self, object_id: str) -> dict[str, Any] | None:
        return inspect_object(self.repository, object_id, store=self.overrides)

    def get_neighbors(
        self,
        object_id: str,
        edge_types: Sequence[str] | None = None,
        *,
        direction: str = "both",
    ) -> list[dict[str, Any]]:
        return get_neighbors(self.repository, object_id, edge_types, direction=direction, store=self.overrides)

    def get_dependencies(self, object_id: str) -> list[dict[str, Any]]:
        return get_dependencies(self.repository, object_id, store=self.overrides)

    def get_dependents(self, object_id: str) -> list[dict[str, Any]]:
        return get_dependents(self.repository, object_id, store=self.overrides)

    def get_usage(self, object_id: str) -> list[dict[str, Any]]:
        return get_usage(self.repository, object_id, store=self.overrides)

    def get_semantics(self, object_id: str) -> list[dict[str, Any]]:
        return get_semantics(self.repository, object_id, store=self.overrides)

    def get_context(
        self,
        target: str,
        task: str | Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        return get_context(self.repository, target, task, store=self.overrides)

    def find_path(self, from_id: str, to_id: str) -> list[dict[str, Any]]:
        return find_path(self.repository, from_id, to_id, store=self.overrides)

    def validate_selection(self, object_ids: Sequence[str] | str | Mapping[str, Any] | None) -> dict[str, Any]:
        return validate_selection(self.repository, object_ids, store=self.overrides)

    def get_graph(self, **kwargs: Any) -> dict[str, Any]:
        return get_graph(self.repository, store=self.overrides, **kwargs)

    def get_review_queue(self, **kwargs: Any) -> list[dict[str, Any]]:
        return get_review_queue(self.repository, self.overrides, **kwargs)

    def remove_override(self, item_id: str, property: str | None = None) -> dict[str, Any]:
        return remove_override(self.repository, item_id, property=property, store=self.overrides)

    def apply_review(self, item_id: str, action: str, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        payload = dict(payload or {})
        action = str(action).casefold()
        item_id = str(payload.get("candidate_id") or item_id)
        if item_id.startswith("override:") and action in {"approve", "reject", "remove", "resolve"}:
            result = self.remove_override(item_id, payload.get("override_property") or payload.get("property"))
            if action == "resolve":
                result["status"] = "resolved"
            return {"result": result, "snapshot": self.get_snapshot()}
        if action in {"remove", "resolve"}:
            result = self.remove_override(item_id, payload.get("override_property") or payload.get("property"))
            if action == "resolve":
                result["status"] = "resolved"
            return {"result": result, "snapshot": self.get_snapshot()}
        if action == "approve":
            result = approve(self.repository, item_id)
            return {"result": result, "snapshot": self.get_snapshot()}
        if action == "reject":
            result = reject(self.repository, item_id)
            return {"result": result, "snapshot": self.get_snapshot()}
        if action == "edit":
            changes = payload.get("changes")
            if changes is not None and not isinstance(changes, Mapping):
                raise ValueError("edit changes must be an object")
            result = edit(
                self.repository,
                item_id,
                changes,
                property=payload.get("property"),
                value=payload.get("value"),
                store=self.overrides,
            )
            return {"result": result, "snapshot": self.get_snapshot()}
        if action in {"override", "apply_override"}:
            patch = payload.get("patch")
            if patch is not None and not isinstance(patch, Mapping):
                raise ValueError("override patch must be an object")
            result = override(
                self.repository,
                item_id,
                payload.get("property"),
                payload.get("value"),
                patch=patch,
                store=self.overrides,
            )
            return {"result": result, "snapshot": self.get_snapshot()}
        raise ValueError(f"unsupported review action: {action}")

    def close(self) -> None:
        if self._owns_repository:
            self.repository.close()

    def __enter__(self) -> "BrainAPI":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()


class BrainApp:
    """Minimal WSGI app; no web framework is needed for local Inspector use."""

    def __init__(self, api: BrainAPI) -> None:
        self.api = api

    @staticmethod
    def _json_body(body: bytes | str | Mapping[str, Any] | None) -> dict[str, Any]:
        if body is None or body == b"" or body == "":
            return {}
        if isinstance(body, Mapping):
            return dict(body)
        try:
            value = json.loads(body.decode("utf-8") if isinstance(body, bytes) else body)
        except (TypeError, ValueError) as exc:
            raise ValueError("request body must be valid JSON") from exc
        if not isinstance(value, Mapping):
            raise ValueError("request body must be a JSON object")
        return dict(value)

    @staticmethod
    def _query_values(query: Mapping[str, Sequence[str]], key: str) -> str | list[str] | None:
        values = list(query.get(key, []))
        if not values:
            return None
        if len(values) == 1 and "," in values[0]:
            return [item for item in values[0].split(",") if item]
        return values[0] if len(values) == 1 else values

    def handle(
        self,
        method: str,
        path: str,
        body: bytes | str | Mapping[str, Any] | None = None,
    ) -> tuple[int, Any]:
        method = str(method).upper()
        parsed = urlsplit(path)
        raw_parts = [part for part in parsed.path.rstrip("/").split("/") if part]
        parts = [unquote(part) for part in raw_parts]
        query = parse_qs(parsed.query, keep_blank_values=True)
        if parts and parts[0].casefold() == "api":
            parts = parts[1:]
        try:
            if method == "OPTIONS":
                return 204, None
            if method == "GET" and parts == ["overview"]:
                return 200, self.api.get_overview()
            if method == "GET" and parts == ["brain"]:
                return 200, self.api.get_snapshot()
            if method == "GET" and parts == ["objects"]:
                object_type = self._query_values(query, "object_type") or self._query_values(query, "type")
                return 200, self.api.search_objects(
                    str(self._query_values(query, "query") or ""),
                    object_type=object_type,
                    model_id=self._query_values(query, "model_id"),
                    report_id=self._query_values(query, "report_id"),
                )
            if method == "GET" and len(parts) >= 3 and parts[0] in {"objects", "object"}:
                object_id = "/".join(parts[1:-1])
                operation = parts[-1].casefold()
                if operation == "neighbors":
                    edge_types = self._query_values(query, "edge_type") or self._query_values(query, "edge_types")
                    direction = str(self._query_values(query, "direction") or "both")
                    return 200, self.api.get_neighbors(object_id, edge_types, direction=direction)
                if operation in {"dependencies", "dependents", "usage", "semantics"}:
                    return 200, getattr(self.api, f"get_{operation}")(object_id)
            if method == "GET" and len(parts) >= 2 and parts[0] in {"objects", "object"}:
                object_id = "/".join(parts[1:])
                value = self.api.inspect_object(object_id)
                return (200, value) if value is not None else (404, {"error": "object not found"})
            if method == "GET" and parts == ["path"]:
                from_id = self._query_values(query, "from_id") or self._query_values(query, "from")
                to_id = self._query_values(query, "to_id") or self._query_values(query, "to")
                if from_id is None or to_id is None:
                    raise ValueError("path requires from_id and to_id")
                return 200, self.api.find_path(str(from_id), str(to_id))
            if method == "GET" and len(parts) >= 3 and parts[0] == "path":
                return 200, self.api.find_path("/".join(parts[1:-1]), parts[-1])
            if method == "GET" and parts in (["validate-selection"], ["selection", "validate"]):
                object_ids = self._query_values(query, "object_id") or self._query_values(query, "object_ids") or self._query_values(query, "ids")
                return 200, self.api.validate_selection(object_ids)
            if method == "POST" and parts in (["validate-selection"], ["selection", "validate"]):
                payload = self._json_body(body)
                object_ids = payload.get("object_ids", payload.get("ids", payload.get("objects", [])))
                return 200, self.api.validate_selection(object_ids)
            if method == "GET" and parts and parts[0] == "graph":
                params: dict[str, Any] = {
                    "query": str(self._query_values(query, "query") or ""),
                    "object_types": self._query_values(query, "object_type") or self._query_values(query, "type"),
                    "edge_types": self._query_values(query, "edge_type") or self._query_values(query, "edge_types"),
                    "center_id": self._query_values(query, "center_id"),
                }
                if len(parts) > 1:
                    params["center_id"] = "/".join(parts[1:])
                for key in ("depth", "limit"):
                    value = self._query_values(query, key)
                    if value is not None:
                        params[key] = int(str(value))
                return 200, self.api.get_graph(**{key: value for key, value in params.items() if value is not None})
            if method == "GET" and parts == ["review"]:
                params: dict[str, Any] = {
                    "object_type": self._query_values(query, "object_type") or self._query_values(query, "type"),
                    "model_id": self._query_values(query, "model_id"),
                    "report_id": self._query_values(query, "report_id"),
                    "issue_type": self._query_values(query, "issue_type"),
                    "sort_by": str(self._query_values(query, "sort_by") or "confidence"),
                }
                for key in ("min_confidence", "max_confidence"):
                    value = self._query_values(query, key)
                    if value is not None:
                        params[key] = float(str(value))
                return 200, self.api.get_review_queue(**{key: value for key, value in params.items() if value is not None})
            if method == "GET" and parts and parts[0] == "context":
                target = "/".join(parts[1:]) or str(
                    self._query_values(query, "target")
                    or self._query_values(query, "object_id")
                    or self._query_values(query, "id")
                    or ""
                )
                if not target:
                    raise ValueError("context target is required")
                return 200, self.api.get_context(target, task=self._query_values(query, "task"))
            if method == "POST" and len(parts) >= 3 and parts[0] == "review":
                item_id = "/".join(parts[1:-1])
                return 200, self.api.apply_review(item_id, parts[-1], self._json_body(body))
            if method == "POST" and parts == ["review"]:
                payload = self._json_body(body)
                action = str(payload.pop("action", ""))
                item_id = str(payload.get("candidate_id") or payload.get("target") or "")
                if not item_id:
                    raise ValueError("review target is required")
                return 200, self.api.apply_review(item_id, action, payload)
            if method == "POST" and len(parts) == 2 and parts[0] == "review":
                payload = self._json_body(body)
                return 200, self.api.apply_review(parts[1], str(payload.pop("action", "")), payload)
            if method not in {"GET", "POST", "OPTIONS"}:
                return 405, {"error": "method not allowed"}
            return 404, {"error": "route not found"}
        except KeyError as exc:
            return 404, {"error": str(exc).strip("'")}
        except (TypeError, ValueError) as exc:
            return 400, {"error": str(exc)}

    def __call__(self, environ: Mapping[str, Any], start_response: Any) -> list[bytes]:
        method = str(environ.get("REQUEST_METHOD", "GET"))
        path = str(environ.get("PATH_INFO", "/"))
        query = str(environ.get("QUERY_STRING", ""))
        length = int(environ.get("CONTENT_LENGTH") or 0)
        stream = environ.get("wsgi.input")
        body = stream.read(length) if stream is not None and length else b""
        status, payload = self.handle(method, f"{path}?{query}" if query else path, body)
        status_text = {200: "OK", 204: "No Content", 400: "Bad Request", 404: "Not Found", 405: "Method Not Allowed"}.get(status, "Error")
        raw = b"" if payload is None else json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        headers = [("Content-Type", "application/json"), ("Content-Length", str(len(raw))), ("Access-Control-Allow-Origin", "*")]
        if method == "OPTIONS":
            headers.extend([("Access-Control-Allow-Methods", "GET, POST, OPTIONS"), ("Access-Control-Allow-Headers", "Content-Type")])
        start_response(f"{status} {status_text}", headers)
        return [raw]

    def close(self) -> None:
        self.api.close()


def create_app(
    repository: GraphRepository | None = None,
    *,
    database_path: str | Path | None = None,
    overrides_path: str | Path | None = None,
    use_native: bool | None = None,
) -> BrainApp:
    return BrainApp(
        BrainAPI(
            repository,
            database_path=database_path,
            overrides_path=overrides_path,
            use_native=use_native,
        )
    )


def serve(
    host: str = "127.0.0.1",
    port: int = 8000,
    *,
    database_path: str | Path = "data/brain.lbug",
    overrides_path: str | Path | None = None,
    use_native: bool | None = None,
) -> None:
    """Serve the local API directly with the Python standard library."""

    from wsgiref.simple_server import make_server

    application = create_app(
        database_path=database_path,
        overrides_path=overrides_path,
        use_native=use_native,
    )
    try:
        with make_server(host, int(port), application) as server:
            server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        application.close()


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="python -m backend.api", description="Power BI Brain Inspector API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--db", default="data/brain.lbug")
    parser.add_argument("--overrides", default=None)
    args = parser.parse_args(argv)
    serve(args.host, args.port, database_path=args.db, overrides_path=args.overrides)
    return 0


__all__ = [
    "BrainAPI",
    "BrainApp",
    "apply_review",
    "create_app",
    "find_path",
    "get_dependencies",
    "get_dependents",
    "get_neighbors",
    "get_object",
    "get_overview",
    "get_semantics",
    "get_usage",
    "main",
    "search_objects",
    "serve",
    "validate_selection",
]
