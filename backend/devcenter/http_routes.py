"""One table of the Development Center HTTP routes (technical design sections 14.1 and 14.3).

``backend.api.app.BrainApp`` sends each ``/api/devcenter/...`` request to
``dispatch``. The table has read routes (GET) and agent proposal routes (POST)
only. No route changes accepted session state (ADR 0003): those changes exist
only in the pywebview JS API (``backend.devcenter.jsapi``).

The order of the checks is fixed: an unknown path gives 404, a known path with
a wrong method gives 405, and only then the route checks the open session.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from backend.devcenter.errors import DevCenterError, error_reply

READ = "read"
PROPOSAL = "proposal"
# Section 14.1: the read-only calculations with a request body. They are POST reads.
READ_POSTS = ("name-propose", "plan-validate")

Handler = Callable[[Any, Mapping[str, Sequence[str]], Any], Mapping[str, Any]]


@dataclass(frozen=True)
class Route:
    method: str
    path: tuple[str, ...]
    kind: str
    handler: Handler
    contract: str | None = None


ROUTES: list[Route] = []


def route(method: str, path: str, *, kind: str = READ, contract: str | None = None) -> Callable[[Handler], Handler]:
    """Add one route. ``path`` is relative to ``/api/devcenter/``; ``{name}`` is one path part."""

    if (kind, method) not in {(READ, "GET"), (PROPOSAL, "POST")} and not (kind == READ and method == "POST" and path in READ_POSTS):
        raise ValueError("A Development Center route is a GET read, a POST read calculation, or a POST proposal only")

    def decorator(handler: Handler) -> Handler:
        ROUTES.append(Route(method, tuple(part for part in path.split("/") if part), kind, handler, contract))
        return handler

    return decorator


def _match(pattern: tuple[str, ...], parts: Sequence[str]) -> bool:
    return len(pattern) == len(parts) and all(p.startswith("{") or p == part for p, part in zip(pattern, parts))


_STATUS = {"not_found": 404, "session_not_open": 409, "stale_revision": 409}


def dispatch(app: Any, method: str, parts: Sequence[str], query: Mapping[str, Sequence[str]], body: Any) -> tuple[int, Any]:
    """Answer one request below ``/api/devcenter/``. Give ``(HTTP status, payload)``."""

    matches = [item for item in ROUTES if _match(item.path, parts)]
    if not matches:
        return 404, error_reply("not_found", "The route does not exist.")
    selected = next((item for item in matches if item.method == method), None)
    if selected is None:
        return 405, error_reply("action_not_allowed", "The method is not allowed for this route.", {"reason": "method_not_allowed"})
    devcenter = getattr(app, "devcenter", None)
    if devcenter is None:
        return 409, error_reply("session_not_open", "No merge session is open.")
    query = {**query, **{p[1:-1]: [part] for p, part in zip(selected.path, parts) if p.startswith("{")}}
    try:
        return 200, dict(selected.handler(devcenter, query, body))
    except DevCenterError as exc:
        return _STATUS.get(exc.code, 400), exc.reply()


# Read routes of build step S2 ------------------------------------------------


@route("GET", "sessions", contract="http/sessions.reply.json")
def get_sessions(devcenter: Any, query: Mapping[str, Sequence[str]], body: Any) -> Mapping[str, Any]:
    return devcenter.sessions_list()


@route("GET", "session", contract="http/session.reply.json")
def get_session(devcenter: Any, query: Mapping[str, Sequence[str]], body: Any) -> Mapping[str, Any]:
    return devcenter.session_summary()


from backend.devcenter.compare import http_routes as _compare_routes  # noqa: E402,F401  (build step S3)
from backend.devcenter.naming import http_routes as _naming_routes  # noqa: E402,F401  (S4 read routes)
