"""HTTP read routes of build step S9 (technical design section 14.1, UC5, UC6, UC7). Reads only."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from backend.devcenter.apply.service import service
from backend.devcenter.http_routes import route


@route("GET", "apply/preview", contract="http/apply-preview.reply.json")
def get_apply_preview(devcenter: Any, query: Mapping[str, Sequence[str]], body: Any) -> Mapping[str, Any]:
    return service(devcenter).preview()


@route("GET", "apply/progress", contract="http/apply-progress.reply.json")
def get_apply_progress(devcenter: Any, query: Mapping[str, Sequence[str]], body: Any) -> Mapping[str, Any]:
    return service(devcenter).progress()


@route("GET", "apply/last", contract="http/apply-last.reply.json")
def get_apply_last(devcenter: Any, query: Mapping[str, Sequence[str]], body: Any) -> Mapping[str, Any]:
    return service(devcenter).last()
