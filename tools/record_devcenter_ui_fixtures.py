"""Record the Development Center UI fixtures from the merge lab (UI design step U12).

Run from the repository root on the Windows development PC (the compare, plan,
and impact engines need the .NET TOM bridge):

    python -m tools.record_devcenter_ui_fixtures --out tests/fixtures/devcenter_ui/default

The tool copies the merge lab models (tests/fixtures/merge_lab) to a temporary
project, makes one session with the sources and the target, and records each
read reply of the real backend. Each reply must pass its contract
(backend/devcenter/contracts/http). The tool writes the files in the shape
that tests/devcenter_ui_server.py reads.

The tool records reads only. The "large-5000-rows" scenario stays generated
in memory by the fake server (the repository has no large fixture file); its
base is the recorded "default" set. The hand files that a read does not give
(agent-review, cloud-items, desktop-session, and the apply replies) stay as
they are.

All text follows ASD-STE100 rules.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LAB = ROOT / "tests" / "fixtures" / "merge_lab"
DEFAULT_OUT = ROOT / "tests" / "fixtures" / "devcenter_ui" / "default"
SOURCES = ("SalesA", "SalesB")
SESSION_NAME = "Sales and finance merge"
PAGE = 200
# The fixture files that the recorder writes. Each other file in the folder stays.
RECORDED = (
    "sessions", "session", "compare-rows", "row-diffs", "display-folders", "naming-rules", "plan",
    "impact", "impact-paths", "removals", "removal", "wireframes", "wireframe", "log",
)
# The reply fields that the fake server gives itself. A fixture file does not keep them.
ENVELOPE = ("revision", "limit", "offset")

Get = Callable[[str], dict[str, Any]]


class RecordError(Exception):
    """A read failed or a reply does not pass its contract."""


def _strip(reply: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in reply.items() if key not in ENVELOPE}


def _pages(get: Get, path: str, key: str) -> list[Any]:
    items: list[Any] = []
    offset = 0
    while True:
        reply = get(f"{path}?limit={PAGE}&offset={offset}")
        if not reply.get(key):
            return items
        items.extend(reply.get(key, []))
        if not reply.get("has_more"):
            return items
        offset += PAGE


def _optional(get: Get, path: str, missing: list[str]) -> dict[str, Any] | None:
    """Read one route that needs the model engine. Add the path to ``missing`` when the read fails."""

    try:
        return get(path)
    except RecordError as error:
        missing.append(f"{path}: {error}")
        return None


def record(get: Get, missing: list[str] | None = None) -> dict[str, Any]:
    """Read each route with ``get`` and give the fixture files as {name: data}.

    A read that needs the model engine and fails goes to ``missing``; its file is not in the result.
    """

    missing = [] if missing is None else missing

    files: dict[str, Any] = {"sessions": _strip(get("sessions")), "session": get("session")}
    source_ids = [source["source_id"] for source in files["session"].get("sources", [])]
    rows = _pages(get, "compare-rows", "rows")
    files["compare-rows"] = {"rows": rows}
    # The fake server keeps one diff text pair for each row and source: {row: {source: {language, target, source}}}.
    files["row-diffs"] = {}
    for row in rows:
        if row.get("row_state") == "same":
            continue
        for source_id in row.get("cells", {}):
            diff = _optional(get, f"compare-rows/{row['row_key']}/diff?source={source_id}", missing)
            if diff is not None:
                files["row-diffs"].setdefault(row["row_key"], {})[source_id] = {
                    "language": diff.get("language", "tmdl"),
                    "target": diff.get("reference_text", diff.get("target", "")),
                    "source": diff.get("source_text", diff.get("source", "")),
                }
    # The fake server keeps the display folders of each source: {folders: {source: [...]}}.
    folders = {}
    for source_id in source_ids:
        reply = _optional(get, f"display-folders?source={source_id}", missing)
        if reply is not None:
            folders[source_id] = reply["folders"]
    if folders:
        files["display-folders"] = {"folders": folders}
    for name in ("naming-rules", "plan"):
        reply = _optional(get, name, missing)
        if reply is not None:
            files[name] = reply if name == "naming-rules" else _strip(reply)
    impact = _optional(get, f"impact?limit={PAGE}&offset=0", missing)
    if impact is not None:
        impact["items"] = _pages(get, "impact", "items")
        files["impact"] = {key: impact[key] for key in ("items", "completeness", "offers") if key in impact}
        # The fake server keeps the path list of each item: {item: [path, ...]}.
        files["impact-paths"] = {item["id"]: _pages(get, f"impact/{item['id']}/paths", "paths") for item in impact["items"]}
    removed = [row["row_key"] for row in rows if (row.get("merge_choice") or {}).get("choice") == "remove"]
    removals = {key: _optional(get, f"impact/removal/{key}", missing) for key in removed}
    files["removals"] = {key: _strip(value) for key, value in removals.items() if value is not None}
    if files["removals"]:
        files["removal"] = next(iter(files["removals"].values()))
    files["wireframes"] = {}
    for source_id in source_ids:
        try:
            files["wireframes"][source_id] = _strip(get(f"wireframe/{source_id}"))
        except RecordError:
            continue  # A source with no report has no wireframe.
    if files["wireframes"]:
        files["wireframe"] = next(iter(files["wireframes"].values()))
    files["log"] = _strip(get(f"log?limit={PAGE}&offset=0"))
    return files


def write(files: dict[str, Any], out: Path) -> list[Path]:
    """Write the recorded files into ``out``. Give the written paths."""

    out.mkdir(parents=True, exist_ok=True)
    written = []
    for name in RECORDED:
        if name not in files:
            continue
        path = out / f"{name}.json"
        path.write_text(json.dumps(files[name], indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        written.append(path)
    return written


def lab_reader(project: Path, *, use_native: bool = True) -> tuple[Get, list[str], Callable[[], None]]:
    """Make a session on a copy of the merge lab in ``project``. Give (get, source ids, close)."""

    from backend.api.app import create_app
    from backend.devcenter import contracts, http_routes, jsapi
    from backend.devcenter.session.manager import DevCenterSessions

    for name in SOURCES:
        shutil.copytree(LAB / name, project / name)
    devcenter = DevCenterSessions(app_data_dir=None)
    devcenter.attach_project(project)
    app = create_app(use_native=use_native)
    app.devcenter = devcenter

    def call(method: str, request: dict[str, Any]) -> dict[str, Any]:
        reply = jsapi.call(devcenter, method, request)
        if "error" in reply:
            raise RecordError(f"{method} failed: {reply['error']}")
        return reply

    call("session_create", {"display_name": SESSION_NAME})
    for name in SOURCES:
        call("source_add", {"base_revision": devcenter.revision, "path": str(project / name / f"{name}.pbip")})
    call("target_set", {"base_revision": devcenter.revision, "model": {"mode": "existing", "source_id": "src-1"},
                        "report": {"mode": "existing", "source_id": "src-1"}})

    def get(path: str) -> dict[str, Any]:
        status, payload = app.handle("GET", "/api/devcenter/" + path)
        if status != 200:
            raise RecordError(f"GET {path} gave {status}: {payload}")
        parts = tuple(path.split("?", 1)[0].split("/"))
        route = next(item for item in http_routes.ROUTES if item.method == "GET" and http_routes._match(item.path, parts))
        problems = contracts.errors(route.contract, payload)
        if problems:
            raise RecordError(f"GET {path} does not pass {route.contract}: {problems[:3]}")
        return payload

    def close() -> None:
        app.close()
        devcenter.close()

    return get, [f"src-{index + 1}" for index in range(len(SOURCES))], close


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record the Development Center UI fixtures from the merge lab.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="The fixture folder to write.")
    parser.add_argument("--no-native", action="store_true", help="Do not use the TOM bridge (the compare is then empty).")
    args = parser.parse_args(argv)
    with tempfile.TemporaryDirectory(prefix="t26-record-") as folder:
        get, _, close = lab_reader(Path(folder) / "project", use_native=not args.no_native)
        try:
            missing: list[str] = []
            files = record(get, missing)
        finally:
            close()
    if missing or not files["compare-rows"]["rows"]:
        print("The tool wrote no file. The compare has no rows or a read failed. Run the tool on the Windows PC"
              " with the TOM bridge.", file=sys.stderr)
        for line in missing:
            print(f"  {line}", file=sys.stderr)
        return 2
    for path in write(files, args.out):
        print(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
