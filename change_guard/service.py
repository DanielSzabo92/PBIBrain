"""Separate loopback service; Brain agent sessions are never accepted here."""
from __future__ import annotations

import hmac
import json
from pathlib import Path
import secrets
from urllib.parse import urlsplit, unquote
from wsgiref.simple_server import make_server
from backend.snapshots.manifest import canonical_json


class GuardService:
    def __init__(self, guard, token: str, origin: str, *, static_dir: str | Path | None = None):
        self.guard, self._token, self.origin = guard, token, origin
        self.static_dir = Path(static_dir).resolve() if static_dir else None

    def handle(self, method: str, path: str, body: dict | None, *, token: str, origin: str | None = None):
        if not hmac.compare_digest(token, self._token) or (origin is not None and origin != self.origin):
            return 403, {"guard_api_version": 1, "error": {"code": "GUARD_AUTH_REQUIRED"}}
        parts = [unquote(item) for item in urlsplit(path).path.strip("/").split("/")]
        try:
            if len(parts) == 3 and parts[:2] == ["guard", "review"] and method == "GET":
                result = self.guard.review(parts[2])
            elif len(parts) == 3 and parts[:2] == ["guard", "authorize"] and method == "POST":
                if set(body or {}) != {"purpose"}:
                    raise ValueError("Exact authorization purpose required")
                result = self.guard.authorize(parts[2], body["purpose"])
            elif len(parts) == 3 and parts[:2] == ["guard", "promote"] and method == "POST":
                if body:
                    raise ValueError("Promotion accepts no agent-supplied evidence")
                result = self.guard.promote_candidate(parts[2])
            else:
                return 404, {"guard_api_version": 1, "error": {"code": "ROUTE_NOT_FOUND"}}
            return 200, {"guard_api_version": 1, "ok": True, "result": result}
        except Exception as error:
            return 409, {"guard_api_version": 1, "error": {"code": getattr(error, "code", "INVALID_INPUT"), "message": str(error)}}

    def __call__(self, environ, start_response):
        method, path = environ["REQUEST_METHOD"], environ["PATH_INFO"]
        host = environ.get("HTTP_HOST", "")
        if host != urlsplit(self.origin).netloc:
            start_response("403 Forbidden", [("Content-Type", "application/json")])
            return [b'{"error":{"code":"INVALID_HOST"}}']
        # Static entry has no privileges. Authorization token lives in URL
        # fragment, never sent in requests, access logs, source files or audits.
        if method == "GET" and self.static_dir and (path == "/guard" or path.startswith("/assets/")):
            target = self.static_dir / ("index.html" if path == "/guard" else path.lstrip("/"))
            if target.resolve().is_relative_to(self.static_dir) and target.is_file() and not target.is_symlink():
                import mimetypes
                start_response("200 OK", [("Content-Type", mimetypes.guess_type(target.name)[0] or "application/octet-stream"), ("Cache-Control", "no-store"), ("Referrer-Policy", "no-referrer"),
                                           ("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'none'")])
                return [target.read_bytes()]
        try:
            length = int(environ.get("CONTENT_LENGTH") or 0)
            if length < 0 or length > 1_000_000:
                raise ValueError("Request too large")
            body = json.loads(environ["wsgi.input"].read(length)) if length else None
            status, result = self.handle(method, path, body, token=environ.get("HTTP_X_PBI_GUARD_SESSION", ""), origin=environ.get("HTTP_ORIGIN"))
        except (ValueError, TypeError):
            status, result = 400, {"guard_api_version": 1, "error": {"code": "INVALID_INPUT"}}
        start_response(f"{status} " + {200: "OK", 400: "Bad Request", 403: "Forbidden", 404: "Not Found", 409: "Conflict"}[status],
                       [("Content-Type", "application/json"), ("Cache-Control", "no-store"), ("X-Content-Type-Options", "nosniff"), ("Referrer-Policy", "no-referrer")])
        return [canonical_json(result).encode("utf-8")]


def serve_guard(guard, *, port: int = 8051):
    token = secrets.token_urlsafe(32)
    origin = f"http://127.0.0.1:{port}"
    static_dir = Path(__file__).resolve().parents[1] / "frontend" / "dist"
    application = GuardService(guard, token, origin, static_dir=static_dir)
    with make_server("127.0.0.1", port, application) as server:
        print(canonical_json({"guard_api_version": 1, "status": "READY", "url": origin + "/guard#session=" + token}), flush=True)
        server.serve_forever()
