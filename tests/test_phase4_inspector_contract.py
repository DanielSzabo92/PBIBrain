"""Phase 4 Brain Inspector contracts.

These tests exercise the local transport and its pure payload builders.  The
repository remains the truth; review decisions use a separate override file.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from typing import Any
from unittest.mock import patch
from urllib.parse import quote

from backend.api.app import BrainAPI, create_app, get_overview
from backend.api.graph import get_graph
from backend.api.objects import get_object, inspect_object
from backend.api.review import (
    OverrideStore,
    approve,
    edit,
    get_review_queue,
    override,
    reject,
)
from backend.graph.repository import GraphRepository
from backend.graph.schema import Edge, Node
from backend.scanner.pipeline import Scanner

from tests.fixtures.phase1_sources import model_source


ROOT = Path(__file__).resolve().parents[1]


def _fixture_repository() -> tuple[GraphRepository, dict[str, str]]:
    """Return a small graph covering every Inspector payload section."""

    model_id = "model:inspector-model"
    table_id = f"{model_id}/table:sales"
    base_id = f"{table_id}/measure:base"
    measure_id = f"{table_id}/measure:revenue"
    column_id = f"{table_id}/column:country"
    report_id = "report:inspector-report"
    page_id = f"{report_id}/page:overview"
    visual_id = f"{page_id}/visual:revenue"
    concept_id = "semantic:business-concept:revenue"
    candidate_id = "semantic:assertion:revenue"
    conflict_id = "semantic:conflict:revenue"

    nodes = [
        Node(model_id, "MODEL", "Inspector model", properties={"raw_source": {"id": "inspector-model"}}),
        Node(table_id, "TABLE", "Sales", model_id=model_id, properties={"raw_source": {"id": "sales"}}),
        Node(
            base_id,
            "MEASURE",
            "Base revenue",
            model_id=model_id,
            source_id="base",
            properties={
                "table_id": table_id,
                "expression": "SUM(Sales[Amount])",
                "raw_source": {"id": "base", "expression": "SUM(Sales[Amount])"},
            },
        ),
        Node(
            measure_id,
            "MEASURE",
            "Revenue",
            description="Net revenue after discounts.",
            model_id=model_id,
            source_id="revenue",
            properties={
                "table_id": table_id,
                "expression": "[Base revenue]",
                "raw_source": {"id": "revenue", "expression": "[Base revenue]"},
                "confidence": 0.82,
            },
        ),
        Node(column_id, "COLUMN", "Country", model_id=model_id, properties={"table_id": table_id}),
        Node(report_id, "REPORT", "Inspector report", model_id=model_id),
        Node(page_id, "PAGE", "Overview", model_id=model_id, report_id=report_id),
        Node(visual_id, "VISUAL", "Revenue visual", model_id=model_id, report_id=report_id),
        Node(
            concept_id,
            "BUSINESS_CONCEPT",
            "Revenue",
            model_id=model_id,
            status="candidate",
            source="description",
            properties={
                "target": measure_id,
                "value": "net revenue",
                "confidence": 0.82,
                "evidence": [{"source": "description", "confidence": 0.98, "text": "Net revenue after discounts."}],
            },
        ),
        Node(
            candidate_id,
            "SEMANTIC_ASSERTION",
            "Revenue alias",
            model_id=model_id,
            status="candidate",
            source="semantic_inference",
            properties={
                "target": measure_id,
                "value": "booked revenue",
                "confidence": 0.35,
                "evidence": [{"source": "name", "confidence": 0.35, "text": "Revenue"}],
            },
        ),
        Node(
            conflict_id,
            "CONFLICT",
            "Revenue conflict",
            model_id=model_id,
            status="candidate",
            source="semantic_inference",
            properties={
                "target_id": measure_id,
                "confidence": 0.25,
                "evidence": [{"source": "dax_analysis", "text": "Description conflicts with behavior."}],
            },
        ),
    ]
    edges = [
        Edge("edge:model-table", "CONTAINS", model_id, table_id),
        Edge("edge:table-base", "CONTAINS", table_id, base_id),
        Edge("edge:table-measure", "CONTAINS", table_id, measure_id),
        Edge("edge:table-column", "CONTAINS", table_id, column_id),
        Edge("edge:report-model", "USES_MODEL", report_id, model_id, source="report_metadata"),
        Edge("edge:report-page", "CONTAINS", report_id, page_id, source="report_metadata"),
        Edge("edge:page-visual", "CONTAINS", page_id, visual_id, source="report_metadata"),
        Edge("edge:visual-measure", "USES", visual_id, measure_id, source="report_metadata", evidence=["visual binding"]),
        Edge("edge:measure-base", "DEPENDS_ON", measure_id, base_id, source="dax_analysis", evidence=[{"source": "dax_analysis", "ast_location": {"start_offset": 0}}]),
        Edge("edge:visual-country", "USES", visual_id, column_id, source="report_metadata"),
        Edge(
            "edge:concept",
            "SEMANTICALLY_MAPS_TO",
            measure_id,
            concept_id,
            source="description",
            confidence=0.82,
            status="candidate",
            evidence_class="INFERRED",
            evidence=[{"source": "description", "confidence": 0.98, "text": "Net revenue after discounts."}],
        ),
        Edge(
            "edge:assertion",
            "ALIAS_OF",
            candidate_id,
            measure_id,
            source="semantic_inference",
            confidence=0.35,
            status="candidate",
            evidence_class="INFERRED",
            evidence=[{"source": "name", "confidence": 0.35, "text": "Revenue"}],
        ),
        Edge(
            "edge:conflict",
            "CONFLICTS_WITH",
            conflict_id,
            measure_id,
            source="semantic_inference",
            confidence=0.25,
            status="candidate",
            evidence_class="INFERRED",
            evidence=[{"source": "dax_analysis", "ast_location": {"start_offset": 1}, "text": "conflict"}],
        ),
        Edge(
            "edge:observed",
            "OBSERVED_WITH",
            measure_id,
            column_id,
            source="report_usage",
            confidence=0.65,
            evidence_class="OBSERVED",
            evidence=[{"source": "report_usage", "count": 3}],
        ),
    ]
    repository = GraphRepository(use_native=False)
    repository.replace(nodes, edges)
    repository.last_scan = "2026-08-30T20:00:00Z"
    return repository, {
        "model": model_id,
        "table": table_id,
        "base": base_id,
        "measure": measure_id,
        "column": column_id,
        "report": report_id,
        "page": page_id,
        "visual": visual_id,
        "concept": concept_id,
        "candidate": candidate_id,
        "conflict": conflict_id,
    }


class Phase4TransportContractTests(unittest.TestCase):
    def setUp(self):
        self.repository, self.ids = _fixture_repository()

    def tearDown(self):
        self.repository.close()

    def test_overview_has_scan_counts_candidates_warnings_and_validation_state(self):
        overview = get_overview(self.repository)
        self.assertEqual(overview["models"], 1)
        self.assertEqual(overview["reports"], 1)
        self.assertEqual(overview["last_scan"], "2026-08-30T20:00:00Z")
        self.assertEqual(overview["scan_state"], "ready")
        self.assertGreaterEqual(overview["candidate_count"], 3)
        self.assertGreaterEqual(overview["warning_count"], 2)
        self.assertEqual(overview["validation_state"], "not_run")
        self.assertEqual(overview["object_counts"]["MEASURE"], 2)

    def test_graph_search_filters_and_connected_scope_are_deterministic(self):
        searched = get_graph(self.repository, query="Revenue")
        self.assertEqual(
            {item["id"] for item in searched["nodes"]},
            {
                self.ids["base"],
                self.ids["measure"],
                self.ids["concept"],
                self.ids["candidate"],
                self.ids["conflict"],
                self.ids["visual"],
            },
        )
        filtered = get_graph(self.repository, object_types="MEASURE")
        self.assertEqual([item["type"] for item in filtered["nodes"]], ["MEASURE", "MEASURE"])
        scoped = get_graph(self.repository, center_id=self.ids["measure"], depth=1, edge_types="DEPENDS_ON")
        self.assertEqual(scoped["scope"]["center_id"], self.ids["measure"])
        self.assertEqual(scoped["scope"]["depth"], 1)
        self.assertEqual({item["id"] for item in scoped["nodes"]}, {self.ids["measure"], self.ids["base"]})
        self.assertEqual({item["type"] for item in scoped["edges"]}, {"DEPENDS_ON"})
        self.assertNotIn("position", json.dumps(scoped))

    def test_inspector_contains_lineage_usage_semantics_and_provenance(self):
        payload = inspect_object(self.repository, self.ids["measure"])
        self.assertIsNotNone(payload)
        self.assertEqual(
            set(payload),
            {"object", "identity", "raw_metadata", "description", "dependencies", "dependents", "relationships", "usage", "semantics", "evidence", "confidence", "approval_state", "warnings", "edges"},
        )
        self.assertEqual(payload["identity"]["id"], self.ids["measure"])
        self.assertEqual(payload["raw_metadata"]["id"], "revenue")
        self.assertEqual({item["id"] for item in payload["dependencies"]}, {self.ids["base"]})
        self.assertEqual({item["id"] for item in payload["usage"]}, {self.ids["visual"]})
        semantic_blob = json.dumps(payload["semantics"], sort_keys=True)
        self.assertIn("SEMANTICALLY_MAPS_TO", semantic_blob)
        self.assertIn("description", semantic_blob)
        self.assertTrue(payload["evidence"])
        self.assertEqual(payload["confidence"], 0.82)
        self.assertEqual(payload["approval_state"], "factual")
        self.assertTrue(any(isinstance(item, dict) and item.get("source") for item in payload["evidence"]))

    def test_review_queue_filters_and_sorts_reviewable_items(self):
        queue = get_review_queue(self.repository, sort_by="confidence")
        self.assertGreaterEqual(len(queue), 3)
        confidences = [item["confidence"] for item in queue]
        self.assertEqual(confidences, sorted(confidences))
        self.assertTrue(all(item["evidence"] for item in queue))
        conflicts = get_review_queue(self.repository, issue_type="conflict")
        self.assertTrue(conflicts)
        self.assertTrue(all(item["issue_type"] == "conflict" for item in conflicts))
        measures = get_review_queue(self.repository, object_type="MEASURE", min_confidence=0.5)
        self.assertTrue(measures)
        self.assertTrue(all(item["target_id"] == self.ids["measure"] for item in measures))
        with self.assertRaises(ValueError):
            get_review_queue(self.repository, sort_by="not-a-field")

    def test_snapshot_exposes_review_queue_and_stale_override_records(self):
        with tempfile.TemporaryDirectory() as directory:
            store = OverrideStore(Path(directory) / "overrides.json")
            stale_target = "model:inspector-model/measure:removed"
            store.put(stale_target, "business_concept", "retired revenue")
            api = BrainAPI(self.repository, overrides_path=store.path)

            snapshot = api.get_snapshot()

            self.assertIn("review_items", snapshot)
            self.assertIn("review_queue", snapshot)
            self.assertIn("stale_overrides", snapshot)
            self.assertEqual(snapshot["review_items"], snapshot["review_queue"])
            stale = [item for item in snapshot["stale_overrides"] if item.get("target_id") == stale_target]
            self.assertEqual(len(stale), 1)
            self.assertEqual(stale[0]["issue_type"], "stale")
            self.assertIn(stale[0], snapshot["review_items"])

    def test_conflict_queue_deduplicates_one_logical_conflict(self):
        conflicts = get_review_queue(self.repository, issue_type="conflict")
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]["target_id"], self.ids["measure"])

    def test_in_memory_scan_records_last_scan_for_overview(self):
        repository = GraphRepository(use_native=False)
        try:
            Scanner(repository).scan(model_source(include_measure=False))
            self.assertTrue(repository.last_scan, "an in-memory scan must publish its completion timestamp")
            overview = get_overview(repository)
            self.assertEqual(overview["last_scan"], repository.last_scan)
        finally:
            repository.close()

    def test_default_override_store_persists_across_api_instances(self):
        with tempfile.TemporaryDirectory() as directory:
            default_path = Path(directory) / "config" / "overrides.json"
            with patch("backend.api.app._default_overrides_path", return_value=default_path):
                api = BrainAPI(self.repository)
                self.assertIsNotNone(api.overrides.path, "default Inspector overrides must be durable")
                self.assertEqual(api.overrides.path.resolve(), default_path.resolve())
                result = api.apply_review(
                    self.ids["measure"],
                    "override",
                    {"property": "business_concept", "value": "net revenue"},
                )
                self.assertEqual(result["result"]["status"], "overridden")
                reopened = BrainAPI(self.repository)
                self.assertEqual(reopened.overrides.records()[0]["value"], "net revenue")
                self.assertEqual(reopened.get_object(self.ids["measure"])["business_concept"], "net revenue")

    def test_stale_review_action_targets_override_and_can_resolve_it(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "overrides.json"
            store = OverrideStore(path)
            stale_target = "model:inspector-model/measure:removed"
            store.put(stale_target, "business_concept", "retired revenue")
            api = BrainAPI(self.repository, overrides_path=path)
            stale = api.get_review_queue(issue_type="stale")
            self.assertEqual(len(stale), 1)
            item = stale[0]
            self.assertEqual(item["target_id"], stale_target)
            self.assertEqual(item["item"]["target"], stale_target)

            resolved = api.apply_review(
                item["id"],
                "resolve",
                {"target": item["target_id"]},
            )
            self.assertIn(resolved["result"].get("status"), {"removed", "resolved", "rejected"})
            self.assertFalse(api.get_review_queue(issue_type="stale"))
            self.assertFalse(api.overrides.records())

    def test_review_queue_classifies_only_explicit_conflict_metadata(self):
        repository = GraphRepository(use_native=False)
        model_id = "model:classification"
        measure_id = f"{model_id}/measure:metric"
        neutral_id = "semantic:assertion:measure-conflict-probe"
        explicit_id = "semantic:assertion:explicit-conflict"
        nodes = [
            Node(model_id, "MODEL", "Classification model"),
            Node(measure_id, "MEASURE", "Metric", model_id=model_id),
            Node(
                neutral_id,
                "SEMANTIC_ASSERTION",
                "Neutral assertion",
                model_id=model_id,
                status="candidate",
                source="name",
                properties={
                    "target": measure_id,
                    "value": "neutral meaning",
                    "confidence": 0.7,
                    "evidence": [{"source": "name", "text": "conflict probe is only an ID"}],
                },
            ),
            Node(
                explicit_id,
                "SEMANTIC_ASSERTION",
                "Explicit conflict",
                model_id=model_id,
                status="candidate",
                source="semantic_inference",
                properties={
                    "target": measure_id,
                    "assertion_type": "CONFLICT",
                    "value": "conflicting meaning",
                    "confidence": 0.2,
                    "evidence": [{"source": "dax_analysis", "text": "explicit contradiction"}],
                },
            ),
        ]
        try:
            repository.replace(nodes, [])
            queue = {item["id"]: item for item in get_review_queue(repository)}
            self.assertEqual(queue[neutral_id]["issue_type"], "candidate")
            self.assertEqual(queue[explicit_id]["issue_type"], "conflict")
        finally:
            repository.close()

    def test_review_lifecycle_preserves_facts_and_stores_overrides_separately(self):
        factual_before = self.repository.get_object(self.ids["measure"]).to_dict()
        approved = approve(self.repository, self.ids["concept"])
        self.assertEqual(approved["status"], "approved")
        self.assertEqual(self.repository.get_object(self.ids["concept"]).status, "approved")
        self.assertEqual(self.repository.get_object(self.ids["measure"]).to_dict(), factual_before)
        rejected = reject(self.repository, self.ids["candidate"])
        self.assertEqual(rejected["status"], "rejected")

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "overrides.json"
            store = OverrideStore(path)
            result = override(self.repository, self.ids["measure"], "business_concept", "net revenue", store=store)
            self.assertEqual(result["status"], "overridden")
            self.assertNotIn("business_concept", self.repository.get_object(self.ids["measure"]).properties)
            effective = get_object(self.repository, self.ids["measure"], store=store)
            self.assertEqual(effective["business_concept"], "net revenue")
            self.assertEqual(effective["status"], "overridden")
            reopened = OverrideStore(path)
            self.assertEqual(reopened.records()[0]["value"], "net revenue")
            edited = edit(self.repository, self.ids["measure"], {"role": "metric"}, store=reopened)
            self.assertEqual(edited["status"], "overridden")
            self.assertNotIn("role", self.repository.get_object(self.ids["measure"]).properties)

    def test_local_wsgi_transport_exposes_read_and_review_routes(self):
        app = create_app(self.repository)
        status, overview = app.handle("GET", "/api/overview")
        self.assertEqual(status, 200)
        self.assertEqual(overview["models"], 1)
        status, graph = app.handle("GET", "/api/graph?query=Revenue&object_type=MEASURE")
        self.assertEqual(status, 200)
        self.assertEqual({item["type"] for item in graph["nodes"]}, {"MEASURE"})
        status, inspector = app.handle("GET", f"/api/objects/{quote(self.ids['measure'], safe='')}")
        self.assertEqual(status, 200)
        self.assertEqual(inspector["identity"]["id"], self.ids["measure"])
        status, body = app.handle(
            "POST",
            "/api/review",
            {"action": "approve", "target": self.ids["concept"]},
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["result"]["status"], "approved")
        app.close()

    def test_local_wsgi_transport_exposes_centered_graph_route(self):
        app = create_app(self.repository)
        try:
            status, graph = app.handle(
                "GET",
                f"/api/graph/{quote(self.ids['measure'], safe='')}?depth=1&edge_type=DEPENDS_ON",
            )
            self.assertEqual(status, 200)
            self.assertEqual(graph["scope"]["center_id"], self.ids["measure"])
            self.assertEqual(graph["scope"]["depth"], 1)
            self.assertEqual({item["id"] for item in graph["nodes"]}, {self.ids["measure"], self.ids["base"]})
            self.assertEqual({item["type"] for item in graph["edges"]}, {"DEPENDS_ON"})
        finally:
            app.close()


class Phase4FrontendContractTests(unittest.TestCase):
    def test_frontend_has_out_of_box_api_proxy(self):
        config_path = ROOT / "frontend" / "vite.config.js"
        self.assertTrue(config_path.is_file(), "frontend dev server must proxy /api to the local Brain backend")
        config_source = config_path.read_text(encoding="utf-8")
        self.assertIn('"/api"', config_source)
        self.assertIn("proxy", config_source)
        self.assertIn("BRAIN_API_URL", config_source)
        self.assertRegex(config_source, r"127\.0\.0\.1:8000")

    def test_frontend_contains_required_views_transport_and_react_flow(self):
        package = json.loads((ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))
        dependencies = {**package.get("dependencies", {}), **package.get("devDependencies", {})}
        app_source = (ROOT / "frontend" / "src" / "App.jsx").read_text(encoding="utf-8")
        transport_source = (ROOT / "frontend" / "src" / "transport.js").read_text(encoding="utf-8")
        self.assertIn("react", dependencies)
        self.assertTrue(
            any(name in dependencies for name in ("reactflow", "@xyflow/react")),
            "React Flow dependency missing",
        )
        self.assertRegex(app_source, r"ReactFlow|reactflow|@xyflow/react")
        self.assertNotIn("<svg", app_source, "Graph view must use React Flow, not custom SVG persistence/rendering")
        for label in ("Overview", "Graph", "Inspector", "Review queue"):
            self.assertIn(label, app_source)
        for name in ("createBrainTransport", "normalizeSnapshot"):
            self.assertIn(f"export function {name}", transport_source)
        for action in ("approve", "reject", "edit", "override"):
            self.assertIn(action, app_source)

    def test_frontend_jsx_modules_bind_classic_react_runtime(self):
        """Vite's current JSX transform must have a React binding at runtime."""
        for filename in ("main.jsx", "App.jsx"):
            source = (ROOT / "frontend" / "src" / filename).read_text(encoding="utf-8")
            self.assertRegex(
                source,
                r'import\s+React(?:\s*,|\s+from\s+["\']react["\'])',
                f"{filename} uses JSX but does not bind React; preview would throw React is not defined",
            )

    def test_frontend_transport_normalizes_snapshot_and_posts_review(self):
        node = shutil.which("node")
        if node is None:
            self.skipTest("node unavailable")
        script = r'''
import { createBrainTransport, normalizeSnapshot } from "./src/transport.js";
import { readFileSync } from "node:fs";
const snapshot = normalizeSnapshot({
  nodes: [{ id: "n1" }],
  edges: [],
  semanticCandidates: [{ id: "c1" }],
  status: { state: "ready" },
});
if (snapshot.nodes.length !== 1 || snapshot.semantic_candidates[0].id !== "c1" || snapshot.scan.state !== "ready") {
  throw new Error("snapshot normalization contract failed");
}
const staleSnapshot = normalizeSnapshot({
  review_queue: [{ id: "stale-1", issue_type: "stale", target_id: "gone" }],
  stale_overrides: [{ id: "stale-1", issue_type: "stale", target_id: "gone" }],
});
if (staleSnapshot.review_items.length !== 1 || staleSnapshot.review_items[0].issue_type !== "stale" || staleSnapshot.stale_overrides.length !== 1) {
  throw new Error("stale review payload normalization failed");
}
const appSource = readFileSync("./src/App.jsx", "utf8");
const itemImpactStart = appSource.indexOf("function itemImpact");
const itemImpactEnd = appSource.indexOf("\n\nfunction relatedNodeIds", itemImpactStart);
const numberOr = (value, fallback = 0) => {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
};
const itemImpact = new Function("numberOr", `${appSource.slice(itemImpactStart, itemImpactEnd)}; return itemImpact;`)(numberOr);
if (itemImpact({ impact: "critical" }) !== 4 || itemImpact({ impact: "high" }) !== 3 || itemImpact({ impact: "normal" }) !== 2 || itemImpact({ impact: "low" }) !== 1) {
  throw new Error("string impact rank contract failed");
}
if (!appSource.includes("snapshot.stale_overrides") || !appSource.includes('sort === "impact-high"')) {
  throw new Error("review queue stale/impact UI contract failed");
}
let request;
const transport = createBrainTransport({
  baseUrl: "/local",
  fetcher: async (url, options) => {
    request = { url, options };
    return { ok: true, status: 200, statusText: "OK", json: async () => ({ accepted: true }) };
  },
});
const result = await transport.review("approve", { target: "n1" });
const body = JSON.parse(request.options.body);
if (result.accepted !== true || request.url !== "/local/review" || request.options.method !== "POST" || body.action !== "approve" || body.target !== "n1") {
  throw new Error("review transport contract failed");
}
'''
        result = subprocess.run(
            [node, "--input-type=module", "-e", script],
            cwd=ROOT / "frontend",
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_frontend_builds_to_static_artifact(self):
        npm = shutil.which("npm")
        if npm is None:
            self.skipTest("npm unavailable")
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [npm, "run", "build", "--", "--outDir", directory],
                cwd=ROOT / "frontend",
                capture_output=True,
                text=True,
                timeout=120,
                env={**os.environ, "CI": "1"},
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue((Path(directory) / "index.html").is_file())


if __name__ == "__main__":
    unittest.main()
