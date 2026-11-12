"""HTTP read routes for Dev Center S6 impact data (technical design section 14.1).

All 4 read endpoints emit session revision and validate against contracts.
"""

from __future__ import annotations

from typing import Any
from collections.abc import Mapping, Sequence

from backend.devcenter.http_routes import route
from backend.devcenter.impact import service


@route("GET", "impact", contract="http/impact.reply.json")
def get_impact(devcenter: Any, query: Mapping[str, Sequence[str]], body: Any) -> Mapping[str, Any]:
    return service.get_impact(devcenter, query)


@route("GET", "impact/removal/{object}", contract="http/impact-removal.reply.json")
def get_removal(devcenter: Any, query: Mapping[str, Sequence[str]], body: Any) -> Mapping[str, Any]:
    return service.get_removal(devcenter, query)


@route("GET", "impact/{item}/paths", contract="http/impact-paths.reply.json")
def get_impact_paths(devcenter: Any, query: Mapping[str, Sequence[str]], body: Any) -> Mapping[str, Any]:
    return service.get_impact_paths(devcenter, query)


@route("GET", "wireframe/{report}", contract="http/wireframe.reply.json")
def get_wireframe(devcenter: Any, query: Mapping[str, Sequence[str]], body: Any) -> Mapping[str, Any]:
    return service.get_wireframe(devcenter, query)
