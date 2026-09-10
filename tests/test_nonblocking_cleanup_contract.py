"""Small regression contracts for the post-V1 cleanup pass.

These tests cover behavior that is easy to regress while reducing retained
source payloads and polishing the Inspector.  They do not prescribe a
particular implementation.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import unittest

from backend.graph.loader import build_fact_graph
from backend.graph.schema import Node
from backend.inference.selectors import discover_selector_options
from backend.inference.semantics import SemanticCandidate

from tests.fixtures.phase3_sources import semantic_model_source, semantic_report_source


ROOT = Path(__file__).resolve().parents[1]


class SelectorCleanupContractTests(unittest.TestCase):
    def test_multi_column_fallback_candidate_keeps_all_selected_options(self):
        model_id = "model:multi-column-selector"
        table_id = f"{model_id}/table:options"
        code_id = f"{table_id}/column:code"
        label_id = f"{table_id}/column:label"
        unrelated_id = f"{table_id}/column:internal"
        nodes = [
            Node(model_id, "MODEL", "Model"),
            Node(table_id, "TABLE", "Options", model_id=model_id),
            Node(
                code_id,
                "COLUMN",
                "Code",
                model_id=model_id,
                properties={"table_id": table_id, "values": ["A", "B"]},
            ),
            Node(
                label_id,
                "COLUMN",
                "Label",
                model_id=model_id,
                properties={"table_id": table_id, "values": ["Alpha", "Beta"]},
            ),
            Node(
                unrelated_id,
                "COLUMN",
                "Internal",
                model_id=model_id,
                properties={"table_id": table_id, "values": ["secret"]},
            ),
        ]
        selector_id = "semantic:selector:multi-column"
        candidate = SemanticCandidate(
            target=selector_id,
            type="SELECTOR",
            value="Options",
            source="dax_analysis",
            confidence=0.9,
            properties={
                "table_id": table_id,
                "column_ids": [code_id, label_id],
                "selector_id": selector_id,
            },
        )

        options = discover_selector_options([candidate], nodes)

        self.assertEqual({item["value"] for item in options}, {"A", "B", "Alpha", "Beta"})
        self.assertEqual({item["column_id"] for item in options}, {code_id, label_id})
        self.assertTrue(all(item["status"] == "factual" for item in options))
        self.assertTrue(all(item["evidence"] for item in options))


class SourceRetentionCleanupContractTests(unittest.TestCase):
    def test_compact_raw_source_retains_identity_without_child_topology(self):
        graph = build_fact_graph(
            semantic_model_source(),
            semantic_report_source(),
            analyze_dax=False,
        )

        forbidden_children = {
            "MODEL": {"tables", "relationships", "measures"},
            "TABLE": {"columns", "measures", "calculations"},
            "REPORT": {"sections", "pages", "visualContainers"},
            "PAGE": {"visualContainers", "visuals"},
        }
        checked = 0
        for node in graph.nodes:
            raw = node.properties.get("raw_source")
            if not isinstance(raw, dict) or node.type not in forbidden_children:
                continue
            checked += 1
            raw_id = raw.get("id") or raw.get("source_id") or raw.get("sourceId")
            self.assertEqual(str(raw_id), str(node.source_id))
            self.assertTrue(
                forbidden_children[node.type].isdisjoint(raw),
                f"{node.type} raw source retains child topology: {sorted(set(raw) & forbidden_children[node.type])}",
            )
        self.assertGreaterEqual(checked, 4)


class InspectorCleanupContractTests(unittest.TestCase):
    def test_overview_counts_only_unresolved_semantic_items(self):
        graph_node = {"id": "n", "type": "MODEL"}
        edge = {"id": "e", "status": "factual"}
        candidates = [
            {"id": "pending", "status": "candidate"},
            {"id": "approved", "status": "approved"},
            {"id": "rejected", "status": "rejected"},
        ]
        conflicts = [
            {"id": "open", "status": "candidate"},
            {"id": "approved-conflict", "status": "approved"},
            {"id": "rejected-conflict", "status": "rejected"},
        ]
        source = (ROOT / "frontend" / "src" / "App.jsx").read_text(encoding="utf-8")
        start = source.index("function dataCounts")
        end = source.index("\n\nfunction App", start)
        # Extracting the pure function keeps this test independent of a DOM or
        # a React test runner.
        function_source = source[start:end]
        node_script = (
            "const dataCounts = new Function("
            + json.dumps(function_source + "; return dataCounts;")
            + ")();"
            + "const result = dataCounts("
            + json.dumps([graph_node])
            + ", "
            + json.dumps([edge])
            + ", "
            + json.dumps(candidates)
            + ", "
            + json.dumps(conflicts)
            + ");"
            + "if (result.candidates !== 1 || result.warnings !== 1) throw new Error(JSON.stringify(result));"
        )
        node_executable = shutil.which("node")
        if node_executable is None:
            self.skipTest("node unavailable")
        result = subprocess.run(
            [node_executable, "-e", node_script],
            cwd=ROOT / "frontend",
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_flow_nodes_are_keyboard_operable_and_semantically_focusable(self):
        source = (ROOT / "frontend" / "src" / "components" / "GraphView.jsx").read_text(encoding="utf-8")
        # React Flow owns the one focusable wrapper and its Enter/Space handler.
        # Browser acceptance also exercises both keys against the rendered nodes.
        self.assertRegex(source, r'ariaRole\s*:\s*["\']button["\']')
        self.assertIn("ariaLabel:", source)
        self.assertIn("onNodesChange=", source)
        self.assertIn('change.type === "select"', source)
        self.assertNotIn("disableKeyboardA11y={true}", source)
        self.assertNotIn("nodesFocusable={false}", source)


if __name__ == "__main__":
    unittest.main()
