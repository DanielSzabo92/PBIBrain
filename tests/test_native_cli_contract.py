"""Native Ladybug and CLI smoke tests for Phase 1."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from backend.graph.repository import GraphRepository
from backend.graph.schema import Edge, Node

from tests.fixtures.phase1_sources import REPORT_A_ID, model_source, report_source


def _native_available() -> bool:
    """Return whether this interpreter can open a real Ladybug database."""

    try:
        with tempfile.TemporaryDirectory() as directory:
            repository = GraphRepository(Path(directory) / "probe.lbug")
            repository.close()
        return True
    except Exception:
        return False


NATIVE_AVAILABLE = _native_available()


def _run_cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "backend.cli.main", *arguments],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )


@unittest.skipUnless(NATIVE_AVAILABLE, "Ladybug C API shared library is unavailable")
class NativeLadybugPersistenceTests(unittest.TestCase):
    def test_native_graph_reopens_with_nodes_edges_and_queries(self):
        model = Node(
            id="model:native-model",
            type="MODEL",
            name="Native model",
            description="Native persistence fixture.",
            model_id="model:native-model",
            source_id="native-model",
            status="factual",
        )
        measure = Node(
            id="model:native-model/measure:native-sales",
            type="MEASURE",
            name="Native Sales",
            model_id=model.id,
            source_id="native-sales",
            status="factual",
        )
        edge = Edge(
            id="edge:native-model-measure",
            type="CONTAINS",
            from_id=model.id,
            to_id=measure.id,
            source="model_metadata",
            status="factual",
            evidence_class="FACT",
            evidence=["native persistence fixture"],
        )

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "brain.lbug"
            repository = GraphRepository(path)
            repository.upsert_nodes([model, measure])
            repository.upsert_edge(edge)
            repository.close()

            reopened = GraphRepository(path)
            self.assertEqual(reopened.storage, "ladybug")
            self.assertEqual(reopened.get_object(measure.id).status, "factual")
            self.assertEqual([node.id for node in reopened.search_objects("Native Sales")], [measure.id])
            self.assertEqual([item.id for item in reopened.get_edges(from_id=model.id)], [edge.id])
            self.assertEqual(reopened.get_edges(from_id=model.id)[0].evidence_class, "FACT")
            reopened.close()

            script = (
                "import json, sys; "
                "from backend.graph.repository import GraphRepository; "
                "r = GraphRepository(sys.argv[1]); "
                "print(json.dumps({'storage': r.storage, 'nodes': len(r.nodes), 'edges': len(r.edges), "
                "'object': r.get_object(sys.argv[2]).to_dict(), "
                "'search': [n.id for n in r.search_objects('Native Sales')], "
                "'edge_ids': [e.id for e in r.get_edges(from_id=sys.argv[3])] })); "
                "r.close()"
            )
            process = subprocess.run(
                [sys.executable, "-c", script, str(path), measure.id, model.id],
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            payload = json.loads(process.stdout)
            self.assertEqual(payload["storage"], "ladybug")
            self.assertEqual(payload["nodes"], 2)
            self.assertEqual(payload["edges"], 1)
            self.assertEqual(payload["object"]["id"], measure.id)
            self.assertEqual(payload["object"]["status"], "factual")
            self.assertEqual(payload["search"], [measure.id])
            self.assertEqual(payload["edge_ids"], [edge.id])


@unittest.skipUnless(NATIVE_AVAILABLE, "Ladybug C API shared library is unavailable")
class NativeCliSmokeTests(unittest.TestCase):
    def test_cli_scan_then_separate_status_and_search_processes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model_path = root / "model.json"
            report_path = root / "report.json"
            database_path = root / "brain.lbug"
            identity_path = root / "identity.json"
            model_path.write_text(json.dumps(model_source()), encoding="utf-8")
            report_path.write_text(json.dumps(report_source(REPORT_A_ID)), encoding="utf-8")

            scan = _run_cli(
                "--db",
                str(database_path),
                "--identity",
                str(identity_path),
                "scan",
                str(model_path),
                "--report",
                str(report_path),
            )
            self.assertEqual(scan.returncode, 0, scan.stderr)
            scan_payload = json.loads(scan.stdout)
            self.assertGreater(scan_payload["nodes"], 0)
            self.assertGreater(scan_payload["edges"], 0)
            self.assertEqual(scan_payload["database"], str(database_path))

            status = _run_cli(
                "--db",
                str(database_path),
                "status",
                "--json",
            )
            self.assertEqual(status.returncode, 0, status.stderr)
            status_payload = json.loads(status.stdout)
            self.assertEqual(status_payload["nodes"], scan_payload["nodes"])
            self.assertEqual(status_payload["edges"], scan_payload["edges"])
            self.assertEqual(status_payload["storage"], "ladybug")

            search = _run_cli(
                "--db",
                str(database_path),
                "search",
                "Sales",
            )
            self.assertEqual(search.returncode, 0, search.stderr)
            results = json.loads(search.stdout)
            self.assertTrue(any(item["type"] == "MEASURE" and item["name"] == "Sales" for item in results))


if __name__ == "__main__":
    unittest.main()

