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


def _project(folder: str, *extra_sources: str):
    from backend.api.app import create_app

    sample = write_sample(Path(folder) / "sample")
    config = Path(folder) / "brain.json"
    config.write_text(json.dumps({"version": 1, "name": "T", "sources": [str(sample), *extra_sources], "database": "brain.lbug", "identity_map": "identity.json"}), encoding="utf-8")
    app = create_app(GraphRepository(use_native=False), overrides_path=Path(folder) / "overrides.json")
    app.project = ProjectService(config)
    return app, sample


def _wait(app, timeout: float = 30.0) -> dict:
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = app.scan_status()
        if not status["running"] and "last" in status:
            return status
        time.sleep(0.02)
    raise AssertionError("the background scan did not finish")


class BackgroundScanTests(unittest.TestCase):
    def test_a_background_scan_returns_at_once_and_reports_how_it_ended(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            app, sample = _project(folder)
            gate = threading.Event()
            read = projects._read_project_source

            def held(path):
                gate.wait(10)
                return read(path)

            with mock.patch.object(projects, "_read_project_source", held):
                status, started = app.handle("POST", "/api/scan", {"background": True})
                self.assertEqual((status, started["running"]), (200, True))
                # While the scan reads its sources, other requests are answered and a second scan is refused.
                with app.request_lock:
                    self.assertTrue(app.scan_status()["running"])
                self.assertEqual(app.handle("GET", "/api/overview")[1]["counts"]["nodes"], 0)
                self.assertEqual(app.handle("POST", "/api/scan", {"background": True})[0], 400)
                self.assertEqual(app.handle("POST", "/api/scan")[0], 400)
                gate.set()
                finished = _wait(app)
            self.assertEqual(finished["last"]["state"], "done")
            self.assertEqual(finished["last"]["source_count"], 1)
            self.assertGreater(app.handle("GET", "/api/overview")[1]["counts"]["nodes"], 0)
            sources = app.handle("GET", "/api/config/sources")[1]["sources"]
            self.assertEqual(sources[0]["scan"]["state"], "scanned")
            self.assertEqual((sources[0]["scan"]["models"], sources[0]["scan"]["reports"]), (1, 1))
            app.close()

    def test_while_the_graph_is_published_reads_get_the_previous_answers_and_collection_resumes(self) -> None:
        # Review 04: reads during a scan answer in under 200 ms, also while the new graph is being published.
        import gc

        with tempfile.TemporaryDirectory() as folder:
            app, _ = _project(folder)
            self.assertEqual(_get(app, "/api/overview")[1]["counts"]["nodes"], 0)
            publishing, release = threading.Event(), threading.Event()
            replace = GraphRepository.replace

            def held(repository, *args, **kwargs):
                publishing.set()
                release.wait(10)
                return replace(repository, *args, **kwargs)

            with mock.patch.object(GraphRepository, "replace", held):
                app.handle("POST", "/api/scan", {"background": True})
                self.assertTrue(publishing.wait(10))
                self.assertFalse(gc.isenabled(), "collection waits while the scan runs")
                answered: list = []
                reader = threading.Thread(target=lambda: answered.append(_get(app, "/api/overview")))
                reader.start()
                reader.join(5)
                self.assertFalse(reader.is_alive(), "a cached read does not wait for the publish")
                self.assertEqual(answered[0][1]["counts"]["nodes"], 0)
                release.set()
                self.assertEqual(_wait(app)["last"]["state"], "done")
            self.assertTrue(gc.isenabled())
            self.assertGreater(_get(app, "/api/overview")[1]["counts"]["nodes"], 0)
            app.close()

    def test_cancel_stops_the_scan_before_anything_is_published(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            app, sample = _project(folder)
            gate = threading.Event()
            read = projects._read_project_source

            def held(path):
                gate.wait(10)
                return read(path)

            with mock.patch.object(projects, "_read_project_source", held):
                app.handle("POST", "/api/scan", {"background": True})
                status, cancelling = app.handle("POST", "/api/scan/cancel")
                self.assertEqual(status, 200)
                self.assertTrue(cancelling.get("cancelling"))
                gate.set()
                finished = _wait(app)
            self.assertEqual(finished["last"]["state"], "cancelled")
            self.assertEqual(app.handle("GET", "/api/overview")[1]["counts"]["nodes"], 0, "nothing was published")
            self.assertEqual(app.handle("GET", "/api/config/sources")[1]["sources"][0]["scan"]["state"], "not_scanned")
            # The next scan runs normally.
            app.handle("POST", "/api/scan", {"background": True})
            self.assertEqual(_wait(app)["last"]["state"], "done")
            app.close()

    def test_a_source_that_cannot_be_read_is_marked_failed(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            broken = Path(folder) / "broken.json"
            broken.write_text("{ not json", encoding="utf-8")
            app, sample = _project(folder, str(broken))
            app.handle("POST", "/api/scan", {"background": True})
            finished = _wait(app)
            self.assertEqual(finished["last"]["state"], "failed")
            self.assertTrue(finished["last"]["error"])
            first, second = app.handle("GET", "/api/config/sources")[1]["sources"]
            self.assertEqual(first["scan"]["state"], "not_scanned", "it was read, but the scan was not published")
            self.assertEqual(second["scan"]["state"], "failed")
            self.assertTrue(second["scan"]["detail"])
            app.close()

            # A restart reads the same states back.
            restarted = ProjectService(app.project.config_path)
            self.assertEqual(restarted.source_states[str(broken)]["state"], "failed")

    def test_a_cancel_during_formula_analysis_stops_at_the_next_expression(self) -> None:
        from backend.dax.analyzer import DaxAnalyzer

        with tempfile.TemporaryDirectory() as folder:
            sample = write_sample(Path(folder) / "sample")
            config = Path(folder) / "brain.json"
            config.write_text(json.dumps({"version": 1, "name": "T", "sources": [str(sample)], "database": "brain.lbug", "identity_map": "identity.json"}), encoding="utf-8")
            project = ProjectService(config)
            cancel = threading.Event()
            analysed: list[str] = []
            analyse = DaxAnalyzer.analyze_object

            def first_then_cancel(self, node, *args, **kwargs):
                analysed.append(str(getattr(node, "id", node)))
                cancel.set()  # the user presses Cancel while the first expression is analysed
                return analyse(self, node, *args, **kwargs)

            repository = GraphRepository(use_native=False)
            with mock.patch.object(DaxAnalyzer, "analyze_object", first_then_cancel):
                with self.assertRaises(projects.ScanCancelled):
                    project.scan(repository, cancel=cancel)
            self.assertEqual(len(analysed), 1, "the analysis stops before the next expression")
            self.assertEqual(repository.all_nodes(), [], "nothing is published")


if __name__ == "__main__":
    unittest.main()
