"""A running scan says what it is doing, and the status read does not wait for the scan."""

from __future__ import annotations

import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

import backend.projects as projects
from backend.graph.repository import GraphRepository
from backend.projects import ProjectService
from backend.sample_project import write_sample


def _get(app, path: str):
    seen: dict[str, str] = {}
    body = app({"REQUEST_METHOD": "GET", "PATH_INFO": path, "QUERY_STRING": "", "HTTP_HOST": "127.0.0.1:8000", "wsgi.input": io.BytesIO()},
               lambda status, headers: seen.update(status=status))
    return seen["status"], json.loads(b"".join(body))


class ScanProgressTests(unittest.TestCase):
    def test_phases_are_reported_and_cleared(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            sample = write_sample(Path(folder) / "sample")
            config = Path(folder) / "brain.json"
            config.write_text(json.dumps({"version": 1, "name": "T", "sources": [str(sample)], "database": "brain.lbug", "identity_map": "identity.json"}), encoding="utf-8")
            project = ProjectService(config)
            self.assertEqual(project.scan_progress, {"running": False})
            seen: list[dict] = []
            read = projects._read_project_source

            def watched(path):
                seen.append(dict(project.scan_progress))
                return read(path)

            with mock.patch.object(projects, "_read_project_source", watched):
                project.scan(GraphRepository(use_native=False))
            self.assertEqual(seen, [{"running": True, "phase": f"Reading {sample.name}", "done": 0, "total": 1}])
            self.assertEqual(project.scan_progress, {"running": False})

    def test_status_is_answered_while_the_request_lock_is_held(self) -> None:
        from backend.api.app import create_app

        app = create_app(GraphRepository(use_native=False))
        app.project = mock.Mock(scan_progress={"running": True, "phase": "Reading formulas and dependencies", "done": 2, "total": 2})
        answer: list = []
        with app.request_lock:
            worker = threading.Thread(target=lambda: answer.append(_get(app, "/api/scan/status")))
            worker.start()
            worker.join(timeout=5)
            self.assertFalse(worker.is_alive(), "the status read waited for the request lock")
        self.assertEqual(answer[0][0], "200 OK")
        self.assertEqual(answer[0][1]["phase"], "Reading formulas and dependencies")


if __name__ == "__main__":
    unittest.main()
