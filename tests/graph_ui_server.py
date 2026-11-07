"""Isolated native project + real HTTP API for browser acceptance tests.

Run from the repository root: python -m tests.graph_ui_server --port 8765
All generated data stays in a temporary directory, never the user's project.
"""

import argparse
import json
import tempfile
from pathlib import Path
from wsgiref.simple_server import WSGIRequestHandler, make_server

from backend.api.app import create_app
from backend.graph.repository import GraphRepository
from backend.projects import ProjectService


class QuietHandler(WSGIRequestHandler):
    def log_message(self, *_args):
        pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--chat", action="store_true", help="Issue #7: a scripted chat provider and an open merge-lab session.")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="pbibrain-graph-ui-") as temporary:
        folder = Path(temporary)
        source = folder / "source.json"
        source.write_text(json.dumps({
            "models": [{
                "id": "finance-model", "name": "Finance model",
                "tables": [{"id": "sales-table", "name": "Sales", "columns": [
                    {"id": "sales-amount", "name": "Amount", "dataType": "Double"},
                    {"id": "sales-region", "name": "Region", "dataType": "String"},
                ], "measures": [
                    {"id": "net-sales", "name": "Net Sales", "description": "Total invoiced sales.", "expression": "SUM('Sales'[Amount])"},
                    {"id": "double-sales", "name": "Sales Target", "description": "Twice the current sales.", "expression": "[Net Sales] * 2"},
                ]}],
            }],
            "reports": [{
                "id": "sales-report", "name": "Sales report", "modelId": "finance-model",
                "sections": [{"id": "overview-page", "name": "Overview page", "visualContainers": [
                    {"id": "sales-visual", "name": "Sales by region", "title": "Sales by region", "visualType": "columnChart", "fields": [{"objectId": "sales-region", "kind": "column"}], "measures": [{"objectId": "net-sales"}]},
                    {"id": "target-visual", "name": "Target card", "title": "Target card", "visualType": "card", "measures": [{"objectId": "double-sales"}]},
                ]}],
            }],
        }), encoding="utf-8")
        project = ProjectService(folder / "brain.json")
        project.save_config({"version": 1, "name": "Graph acceptance project", "sources": [str(source)], "database": "brain.lbug", "identity_map": "identity.json"})
        # Native scan, close, and reopen exercise the same persisted data the app reads.
        with GraphRepository(folder / "brain.lbug") as repository:
            project.scan(repository)
        app = create_app(database_path=folder / "brain.lbug", overrides_path=folder / "overrides.json")
        app.project = project
        app.static_dir = root / "frontend" / "dist"
        if args.chat:
            attach_chat(app, folder)
        try:
            with make_server("127.0.0.1", args.port, app, handler_class=QuietHandler) as server:
                print(f"Graph UI ready at http://127.0.0.1:{args.port}", flush=True)
                server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            app.close()


def attach_chat(app, folder: Path) -> None:
    """The chat e2e (issue #7): a scripted provider, chat off until Settings turns it on, and a merge session."""

    import shutil

    from backend.devcenter import jsapi
    from backend.devcenter.session.manager import DevCenterSessions
    from tests.chat_fake_provider import install

    install(app, settings_file=folder / "settings.json")
    lab = Path(__file__).resolve().parent / "fixtures" / "merge_lab"
    merge_root = folder / "merge"
    for name in ("SalesA", "SalesB"):
        shutil.copytree(lab / name, merge_root / name)
    devcenter = DevCenterSessions(app_data_dir=None)
    devcenter.attach_project(merge_root)
    app.devcenter = devcenter

    def call(method: str, request: dict) -> None:
        reply = jsapi.call(devcenter, method, {"base_revision": devcenter.revision, **request} if method != "session_create" else request)
        if "error" in reply:
            raise RuntimeError(f"{method}: {reply['error']}")

    call("session_create", {"display_name": "Chat merge"})
    for name in ("SalesA", "SalesB"):
        call("source_add", {"path": str(merge_root / name / f"{name}.pbip")})
    call("target_set", {"model": {"mode": "existing", "source_id": "src-1"}, "report": {"mode": "existing", "source_id": "src-1"}})


if __name__ == "__main__":
    main()
