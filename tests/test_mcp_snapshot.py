"""MCP without the app running, freshness, and measured reply budgets (issue #18)."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.graph.repository import GraphRepository
from backend.mcp_budget import CHARS_PER_TOKEN, COMPACT_DROPPED_KEYS, TOOL_BUDGETS, budget_for, fit_reply, size
from backend.mcp_server import ProjectClient
from backend.mcp_snapshot import SnapshotClient, freshness, load_agent_snapshot, snapshot_path, source_fingerprint
from backend.projects import ProjectService
from tests.fixtures.large_project import write_large_project

HAS_MCP = importlib.util.find_spec("mcp") is not None


def _write_small_project(root: Path, *, expression: str = "SUM('Facts'[Amount])") -> Path:
    source = root / "sources" / "sales.json"
    source.parent.mkdir(parents=True, exist_ok=True)
    model = {"id": "sales", "name": "Sales", "tables": [{
        "id": "sales-facts", "name": "Facts", "columns": [{"id": "sales-amount", "name": "Amount", "dataType": "Double"}],
        "measures": [{"id": "sales-total", "name": "Total Sales", "expression": expression}]}]}
    report = {"id": "sales-report", "name": "Sales Report", "modelId": "sales", "sections": [{
        "id": "sales-page", "name": "Overview", "visualContainers": [
            {"id": "sales-visual", "visualType": "card", "measures": [{"objectId": "sales-total"}]}]}]}
    source.write_text(json.dumps({"models": [model], "reports": [report]}), encoding="utf-8")
    config = root / ".pbibrain" / "brain.json"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(json.dumps({"version": 1, "name": "Sales", "sources": [os.path.relpath(source, config.parent)],
                                  "database": "brain.lbug", "identity_map": "identity.json"}), encoding="utf-8")
    return config


def _scan(config: Path) -> None:
    with GraphRepository(use_native=False) as repository:
        ProjectService(config).scan(repository)


def _without_ast(value):
    if isinstance(value, dict):
        return {key: _without_ast(item) for key, item in value.items() if key != "dax_ast"}
    if isinstance(value, list):
        return [_without_ast(item) for item in value]
    return value


def _measure_id(client: SnapshotClient, name: str) -> str:
    return next(node.id for node in client.app.api.repository.all_nodes() if node.type == "MEASURE" and node.name == name)


class SnapshotWriteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.config = _write_small_project(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_scan_writes_a_compact_snapshot_with_source_hashes(self) -> None:
        _scan(self.config)
        payload = load_agent_snapshot(self.config)
        self.assertEqual(1, payload["version"])
        self.assertEqual({"../sources/sales.json"}, set(payload["sources"]))
        measure = next(node for node in payload["graph"]["nodes"] if node["type"] == "MEASURE")
        # Properties are stored once, and the cached parse tree is left out.
        self.assertNotIn("dax_ast", measure.get("properties", {}))
        self.assertNotIn("expression", measure)
        self.assertEqual("SUM('Facts'[Amount])", measure["properties"]["expression"])
        self.assertFalse(list(self.root.glob(".pbibrain/.agent-snapshot.json.*.tmp")))

    def test_a_snapshot_write_failure_does_not_fail_the_scan(self) -> None:
        with patch("backend.mcp_snapshot.write_agent_snapshot", side_effect=OSError("disk full")), \
                self.assertLogs("backend.projects", "WARNING"):
            _scan(self.config)
        self.assertFalse(snapshot_path(self.config).exists())

    def test_snapshot_answers_like_the_live_api(self) -> None:
        from backend.api.app import BrainAPI, BrainApp

        with GraphRepository(use_native=False) as repository:
            ProjectService(self.config).scan(repository)
            live = BrainApp(BrainAPI(repository, overrides_path=self.root / "none.json"))
            snapshot = SnapshotClient(self.config)
            target = _measure_id(snapshot, "Total Sales")
            for path in ("search?q=Total", f"context?target={target}"):
                with self.subTest(path=path):
                    status, expected = live.handle("GET", "/api/" + path)
                    self.assertEqual(200, status)
                    route, _, query = path.partition("?")
                    key, _, value = query.partition("=")
                    # Only the cached parse tree (dax_ast) is left out of the snapshot.
                    self.assertEqual(_without_ast(expected), snapshot.get(route, **{key: value}))


class SnapshotClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.config = _write_small_project(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_without_a_snapshot_the_error_says_to_scan_in_the_app(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "scan it once"):
            ProjectClient(self.config).get("overview")

    def test_app_closed_search_and_context_answer_from_the_snapshot(self) -> None:
        _scan(self.config)
        client = ProjectClient(self.config)
        found = client.get("search", q="Total Sales")
        self.assertEqual("Total Sales", found["items"][0]["name"])
        context = client.get("context", target=found["items"][0]["id"])
        self.assertEqual(found["items"][0]["id"], context["target"]["id"])
        state = client.freshness()
        self.assertEqual("snapshot", state["source"])
        self.assertIs(False, state["stale"])
        self.assertTrue(state["snapshot_at"])

    def test_a_stale_connection_marker_falls_back_to_the_snapshot(self) -> None:
        _scan(self.config)
        marker = {"url": "http://127.0.0.1:9", "config_path": str(self.config), "connection_id": "gone"}
        (self.config.parent / "connection.json").write_text(json.dumps(marker), encoding="utf-8")
        client = ProjectClient(self.config)
        self.assertEqual(1, client.get("overview")["models"])
        self.assertEqual("snapshot", client.freshness()["source"])

    def test_the_open_app_answers_while_it_runs(self) -> None:
        _scan(self.config)

        class Live:
            def get(self, path, **params):
                return {"path": path}

        client = ProjectClient(self.config)
        with patch("backend.mcp_server.live_client", return_value=Live()):
            self.assertEqual({"path": "overview"}, client.get("overview"))
            self.assertEqual({"source": "app", "stale": False}, client.freshness())

    def test_changed_sources_mark_every_reply_stale(self) -> None:
        _scan(self.config)
        client = ProjectClient(self.config)
        client.get("overview")
        source = self.root / "sources" / "sales.json"
        source.write_text(source.read_text(encoding="utf-8").replace("SUM(", "SUMX("), encoding="utf-8")
        (self.root / "sources" / "extra.json").write_text("{}", encoding="utf-8")
        state = client.freshness()
        self.assertIs(True, state["stale"])
        # extra.json is not a configured source, so it is not listed.
        self.assertEqual(["../sources/sales.json"], state["changed_files"])
        self.assertEqual(1, state["changed_count"])

    def test_a_new_scan_is_picked_up_without_restarting(self) -> None:
        _scan(self.config)
        client = ProjectClient(self.config)
        target = _measure_id(client.current(), "Total Sales")
        self.assertEqual("SUM('Facts'[Amount])", client.get("objects/" + target)["object"]["expression"])
        _write_small_project(self.root, expression="SUM('Facts'[Amount]) * 2")
        time.sleep(0.01)
        _scan(self.config)
        self.assertEqual("SUM('Facts'[Amount]) * 2", client.get("objects/" + target)["object"]["expression"])
        self.assertIs(False, client.freshness()["stale"])

    def test_writes_and_app_only_routes_are_refused(self) -> None:
        _scan(self.config)
        client = ProjectClient(self.config)
        with self.assertRaisesRegex(RuntimeError, "running PBIBrain app"):
            client.get("review")
        with self.assertRaisesRegex(RuntimeError, "running PBIBrain app"):
            client.post("compare", {"before": "a", "after": "b"})
        reply = client.devcenter("GET", "session", None, None)
        self.assertEqual("app_not_running", reply["error"]["code"])

    def test_pbip_folders_skip_hidden_cache_files(self) -> None:
        project = self.root / "pbip"
        (project / ".pbi").mkdir(parents=True)
        (project / ".pbi" / "cache.abf").write_bytes(b"x")
        (project / "Sales.SemanticModel").mkdir()
        (project / "Sales.SemanticModel" / "model.tmdl").write_text("model", encoding="utf-8")
        (project / "Sales.pbip").write_text("{}", encoding="utf-8")
        hashes = source_fingerprint(self.config, [project / "Sales.pbip"])
        self.assertEqual({"../pbip/Sales.SemanticModel/model.tmdl", "../pbip/Sales.pbip"}, set(hashes))

    def test_the_project_folder_itself_is_not_a_source(self) -> None:
        (self.config.parent / "agent-snapshot.json").write_text("{}", encoding="utf-8")
        hashes = source_fingerprint(self.config, [self.root])
        self.assertEqual({"../sources/sales.json"}, set(hashes))

    def test_freshness_without_a_scan_is_unknown(self) -> None:
        self.assertIsNone(freshness(self.config, None)["stale"])


class AgentMcpRoutingTests(unittest.TestCase):
    def test_agent_mcp_follows_the_project_even_with_a_stale_marker(self) -> None:
        from backend import agent

        with tempfile.TemporaryDirectory() as directory:
            config = _write_small_project(Path(directory))
            (config.parent / "connection.json").write_text("{}", encoding="utf-8")
            with patch("backend.mcp_server.run") as run:
                self.assertEqual(0, agent.main(["--config", str(config), "mcp"]))
            run.assert_called_once_with(None, config_path=config.resolve())

    def test_agent_mcp_without_a_project_is_an_error(self) -> None:
        import contextlib
        import io

        from backend import agent

        with tempfile.TemporaryDirectory() as directory, patch("backend.mcp_server.run") as run, \
                contextlib.redirect_stderr(io.StringIO()) as error:
            self.assertEqual(2, agent.main(["--config", str(Path(directory) / "brain.json"), "mcp"]))
        run.assert_not_called()
        self.assertIn("No PBIBrain project", error.getvalue())


class FitReplyTests(unittest.TestCase):
    def test_small_reply_is_kept_and_measured(self) -> None:
        reply = fit_reply({"items": [1, 2], "offset": 0}, tool="brain_search")
        self.assertEqual([1, 2], reply["items"])
        self.assertNotIn("truncated", reply["budget"])
        self.assertEqual(size(reply), reply["budget"]["chars"])
        self.assertEqual(-(-reply["budget"]["chars"] // CHARS_PER_TOKEN), reply["budget"]["approx_tokens"])

    def test_compact_drops_parser_detail_and_full_keeps_it(self) -> None:
        payload = {"object": {"name": "Total", "dax_ast": {"kind": "call"}, "raw_source": {"a": 1}}}
        compact = fit_reply(payload, tool="brain_object")
        self.assertEqual({"name": "Total"}, compact["object"])
        self.assertEqual(["dax_ast", "raw_source"], compact["budget"]["omitted_fields"])
        self.assertEqual(payload["object"], fit_reply(payload, tool="brain_object", detail="full")["object"])

    def test_a_cut_result_page_continues_where_it_ends(self) -> None:
        payload = {"items": [{"id": f"object-{index}", "text": "x" * 400} for index in range(200)],
                   "offset": 40, "total": 300, "has_more": True, "next_offset": 240}
        reply = fit_reply(payload, tool="brain_search")
        kept = len(reply["items"])
        self.assertLess(kept, 200)
        self.assertEqual(40 + kept, reply["next_offset"])
        self.assertTrue(reply["budget"]["truncated"])
        self.assertEqual({"path": "items", "kept": kept, "total": 200}, reply["budget"]["trimmed_lists"][0])
        self.assertLessEqual(size(reply), budget_for("brain_search"))

    def test_a_map_with_many_keys_and_long_strings_fit(self) -> None:
        payload = {"confidence": {f"object-{index}": 0.5 for index in range(5_000)}, "note": "y" * 50_000}
        reply = fit_reply(payload, tool="brain_context", detail="full")
        self.assertLessEqual(size(reply), budget_for("brain_context", "full"))
        self.assertTrue(reply["note"].endswith("chars]"))

    def test_unknown_detail_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            fit_reply({}, tool="brain_search", detail="verbose")

    def test_every_compact_budget_is_at_most_full(self) -> None:
        for tool, budgets in TOOL_BUDGETS.items():
            self.assertLessEqual(budgets["compact"], budgets["full"], tool)
        self.assertIn("dax_ast", COMPACT_DROPPED_KEYS)


@unittest.skipUnless(HAS_MCP, "optional MCP SDK is not installed")
class LargeProjectBudgetTests(unittest.TestCase):
    """Token-budget contract: every brain_* tool on 500 measures and 50 pages, app closed."""

    @classmethod
    def setUpClass(cls) -> None:
        from backend.mcp_server import create_server

        cls.temporary = tempfile.TemporaryDirectory()
        cls.config = write_large_project(Path(cls.temporary.name))
        _scan(cls.config)
        cls.server = create_server(None, config_path=cls.config)
        snapshot = SnapshotClient(cls.config)
        cls.measure = _measure_id(snapshot, "Measure 3-10")
        cls.base_measure = _measure_id(snapshot, "Measure 3-0")
        cls.report = next(node.id for node in snapshot.app.api.repository.all_nodes() if node.type == "REPORT")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    replies: dict[str, dict] = {}

    def call(self, tool: str, **arguments):
        # The same call gives the same reply; the large context is built once for all tests.
        key = json.dumps([tool, arguments], sort_keys=True)
        if key not in self.replies:
            self.replies[key] = asyncio.run(self.server._tool_manager.call_tool(tool, arguments))
        return self.replies[key]

    def calls(self):
        return [
            ("brain_overview", {}),
            ("brain_search", {"query": "Measure", "limit": 100}),
            ("brain_object", {"object_id": self.measure}),
            ("brain_context", {"target": self.measure}),
            ("brain_graph", {"center_id": self.measure, "depth": 2}),
            ("brain_graph", {"center_id": self.report, "limit": 1000}),
            ("brain_impact", {"target_id": self.base_measure}),
            ("brain_commonality", {"limit": 200}),
        ]

    def test_every_tool_reply_stays_within_its_budget(self) -> None:
        for detail in ("compact", "full"):
            for tool, arguments in self.calls():
                with self.subTest(tool=tool, detail=detail, arguments=arguments):
                    reply = self.call(tool, detail=detail, **arguments)
                    used = len(json.dumps(reply, ensure_ascii=False, separators=(",", ":")))
                    self.assertLessEqual(used, TOOL_BUDGETS[tool][detail])
                    self.assertEqual(detail, reply["budget"]["detail"])
                    self.assertEqual("snapshot", reply["freshness"]["source"])
                    self.assertIs(False, reply["freshness"]["stale"])

    def test_search_pages_through_every_measure_within_budget(self) -> None:
        seen, offset = set(), 0
        while True:
            reply = self.call("brain_search", query="Measure", object_type="MEASURE", limit=50, offset=offset)
            seen.update(item["id"] for item in reply["items"])
            if not reply["has_more"]:
                break
            self.assertGreater(reply["next_offset"], offset)
            offset = reply["next_offset"]
        self.assertEqual(500, len(seen))

    def test_compact_context_names_what_it_cut(self) -> None:
        reply = self.call("brain_context", detail="compact", target=self.measure)
        self.assertEqual(self.measure, reply["target"]["id"])
        self.assertIn("expression", reply["target"])
        self.assertTrue(reply["budget"]["truncated"])
        self.assertIn("detail='full'", reply["budget"]["hint"])
        self.assertIn("dax_behaviors", reply["budget"]["omitted_fields"])
        self.assertIn({"path": "semantics", "kept": len(reply["semantics"]), "total": reply["budget"]["trimmed_lists"][0]["total"]},
                      reply["budget"]["trimmed_lists"])

    def test_unknown_detail_is_a_tool_error(self) -> None:
        from mcp.server.fastmcp.exceptions import ToolError

        with self.assertRaises(ToolError):
            self.call("brain_overview", detail="everything")


if __name__ == "__main__":
    unittest.main()
