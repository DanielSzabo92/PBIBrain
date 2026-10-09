"""Temporary real TOM/guard/Brain services for browser acceptance; no user data."""
import argparse
from pathlib import Path
import tempfile
from wsgiref.simple_server import make_server, WSGIRequestHandler

from backend.api.app import BrainAPI, BrainApp
from backend.graph.repository import GraphRepository
from backend.scanner.pipeline import Scanner
from change_guard.orchestrator import ChangeGuard
from change_guard.service import GuardService
from tests.guarded_fixture import reference_project
from tests.test_guarded_development import proposal, modify_bim


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--port", type=int, default=8773)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="pbi-guard-ui-") as temporary:
        root = Path(temporary); source = root / "sources"; project = reference_project(source, report=True)
        guard = ChangeGuard(source, root / "trusted", "browser-fixture")
        baseline = guard.capture_baseline()
        operation = guard.prepare_change(proposal(baseline)); operation = guard.authorize(operation["operation_id"], "CONTRACT")
        candidate = Path(operation["candidate_root"])
        modify_bim(candidate, lambda model: model["relationships"][0].update(fromColumn="ShipDateKey"))
        guard.validate_candidate(operation["operation_id"])
        repository = GraphRepository(use_native=False); Scanner(repository).scan(project)
        api = BrainAPI(repository, overrides_path=root / "overrides.json")
        brain = BrainApp(api, static_dir=Path(__file__).resolve().parents[1] / "frontend/dist")
        from backend.projects import ProjectService
        project_service = ProjectService(root / "brain.json")
        project_service.save_config({"version": 1, "name": "Guard test project", "sources": [str(project)], "database": "brain.lbug", "identity_map": "identity.json"})
        brain.project = project_service
        service = GuardService(guard, "isolated-browser-test-session", f"http://127.0.0.1:{args.port}", static_dir=brain.static_dir)
        def application(environ, start_response):
            if environ["PATH_INFO"] in {"/test-proposal", "/test-source"}:
                import json
                from backend.snapshots import source_manifest
                result = guard.prepare_change(proposal(guard.capture_baseline())) if environ["PATH_INFO"] == "/test-proposal" else source_manifest(source)
                start_response("200 OK", [("Content-Type", "application/json")])
                return [json.dumps(result).encode("utf-8")]
            if environ["PATH_INFO"] == "/test-operation":
                import json
                start_response("200 OK", [("Content-Type", "application/json")])
                return [json.dumps({"operation_id": operation["operation_id"]}).encode("utf-8")]
            return service(environ, start_response) if environ["PATH_INFO"].startswith("/guard") else brain(environ, start_response)
        class Quiet(WSGIRequestHandler):
            def log_message(self, *args): pass
        try:
            with make_server("127.0.0.1", args.port, application, handler_class=Quiet) as server:
                print("Guard UI fixture ready", flush=True); server.serve_forever()
        finally: repository.close()


if __name__ == "__main__": main()
