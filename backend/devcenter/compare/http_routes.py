"""HTTP read routes of build step S3: compare rows, the code diff of a row, and display folders.

A path part such as ``{row}`` comes to the handler as the query value ``row``.
"""

from __future__ import annotations

from typing import Any
from collections.abc import Mapping, Sequence

from backend.devcenter.compare import service
from backend.devcenter.errors import DevCenterError
from backend.devcenter.http_routes import route


@route("GET", "compare-rows", contract="http/compare-rows.reply.json")
def get_compare_rows(devcenter: Any, query: Mapping[str, Sequence[str]], body: Any) -> Mapping[str, Any]:
    return service.compare_rows(devcenter, query)


@route("GET", "compare-rows/{row}/diff", contract="http/compare-row-diff.reply.json")
def get_compare_row_diff(devcenter: Any, query: Mapping[str, Sequence[str]], body: Any) -> Mapping[str, Any]:
    rows = list(query.get("row") or [])
    if not rows:
        raise DevCenterError("not_found", "The row does not exist.")
    return service.row_diff(devcenter, str(rows[-1]), query)


@route("GET", "display-folders", contract="http/display-folders.reply.json")
def get_display_folders(devcenter: Any, query: Mapping[str, Sequence[str]], body: Any) -> Mapping[str, Any]:
    return service.display_folders(devcenter, query)
