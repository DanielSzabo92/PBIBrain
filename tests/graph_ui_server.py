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
        try:
            with make_server("127.0.0.1", args.port, app, handler_class=QuietHandler) as server:
                print(f"Graph UI ready at http://127.0.0.1:{args.port}", flush=True)
                server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            app.close()


if __name__ == "__main__":
    main()
