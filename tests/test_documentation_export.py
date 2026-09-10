from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from backend.cli.main import main as cli_main
from backend.documentation_export import render_markdown, snapshot_content_identity
from backend.graph.repository import GraphRepository
from backend.graph.schema import Edge, Node


class DocumentationExportTests(unittest.TestCase):
    def _repository(self) -> GraphRepository:
        model_a = "model:sales-a"
        model_b = "model:sales-b"
        table_a = "table:sales-a"
        table_b = "table:sales-b"
        measure_a = "measure:revenue-a"
        measure_b = "measure:revenue-b"
        report = "report:portfolio"
        nodes = [
            Node(model_a, "MODEL", "Sales A", source_id="sales-a", properties={"raw_source": {"source_path": "A.SemanticModel"}}),
            Node(model_b, "MODEL", "Sales B", source_id="sales-b", properties={"raw_source": {"source_path": "B.SemanticModel"}}),
            Node(table_a, "TABLE", "Sales", model_id=model_a, source_id="sales-a-table"),
            Node(table_b, "TABLE", "Sales", model_id=model_b, source_id="sales-b-table"),
            Node(
                "table:parameter",
                "TABLE",
                "Parameter Table",
                model_id=model_a,
                source_id="parameter-table",
                properties={"raw_source": {"expression": "{(\"Árvíz\", NAMEOF([Revenue | Net]), 0)}"}},
            ),
            Node("column:a", "COLUMN", "Amount", model_id=model_a, source_id="amount-a", properties={"table_id": table_a}),
            Node("column:b", "COLUMN", "Amount", model_id=model_b, source_id="amount-b", properties={"table_id": table_b}),
            Node(
                measure_a,
                "MEASURE",
                "Revenue | Net",
                description="Source-provided label; not verified truth.",
                model_id=model_a,
                source_id="revenue-a",
                properties={
                    "table_id": table_a,
                    "expression": "VAR x = SUM('Sales'[Amount])\nRETURN x",
                    "dax_diagnostics": [
                        {"code": "unresolved_reference", "reference": "[Missing Rate]", "offset": 8},
                        {"code": "ambiguous_reference", "reference": "[Revenue | Net]", "candidates": ["a", "b"]},
                        {"code": "unresolved_relationship", "reference": "missing-relationship"},
                        {"code": "parse_error", "message": "Unexpected token", "offset": 3},
                    ],
                },
            ),
            Node(
                measure_b,
                "MEASURE",
                "Revenue | Net",
                model_id=model_b,
                source_id="revenue-b",
                properties={"table_id": table_b, "expression": "SUM('Sales'[Amount]) * 1.2"},
            ),
            Node(
                "measure:dynamic-format",
                "MEASURE",
                "Dynamic format",
                model_id=model_a,
                properties={
                    "table_id": table_a,
                    "expression": "[Revenue | Net]",
                    "format_expression": 'IF([Revenue | Net] > 0, "$#,0", "€#,0")',
                },
            ),
            Node(
                "relationship:a",
                "RELATIONSHIP",
                "Sales link",
                model_id=model_a,
                properties={
                    "from_column_id": "column:a",
                    "to_column_id": None,
                    "to_ref": {"table": "Date", "column": "Date"},
                    "cardinality": "ManyToOne",
                    "active": True,
                },
            ),
            Node(
                report,
                "REPORT",
                "Portfolio",
                model_id=model_a,
                report_id=report,
                source_id="portfolio-report",
                source="report_metadata",
                properties={"raw_source": {"source_path": "Portfolio.Report"}},
            ),
            Node("page:overview", "PAGE", "Overview", model_id=model_a, report_id=report, properties={"parent_id": report}, source="report_metadata"),
            Node(
                "visual:revenue",
                "VISUAL",
                "Revenue visual",
                model_id=model_a,
                report_id=report,
                properties={
                    "parent_id": "page:overview",
                    "field_ids": [measure_a],
                    "unresolved_field_refs": [
                        {"kind": "MEASURE", "reference": "Missing KPI", "source": "report_metadata", "status": "candidate"}
                    ],
                },
                source="report_metadata",
            ),
        ]
        edges = [
            Edge("edge:depends", "DEPENDS_ON", measure_a, "column:a", source="dax_analysis", evidence=[{"reference": "'Sales'[Amount]", "offset": 12}]),
            Edge("edge:uses", "USES", "visual:revenue", measure_a, source="report_metadata", evidence=["visual field binding"]),
            Edge("edge:model", "USES_MODEL", report, model_a, source="report_metadata", evidence=["report model reference"]),
        ]
        repository = GraphRepository(use_native=False)
        repository.replace(nodes, edges)
        return repository

    def test_render_is_deterministic_exact_and_disambiguated(self):
        repository = self._repository()

        first = render_markdown(repository, project_name="Portfolio")
        second = render_markdown(repository, project_name="Portfolio")

        self.assertEqual(first, second)
        self.assertIn("VAR x = SUM('Sales'[Amount])\nRETURN x", first)
        self.assertIn("SUM('Sales'[Amount]) * 1.2", first)
        self.assertIn('{("Árvíz", NAMEOF([Revenue | Net]), 0)}', first)
        self.assertIn('IF([Revenue | Net] > 0, "$#,0", "€#,0")', first)
        self.assertIn("Format string expression", first)
        self.assertIn("model:sales-a", first)
        self.assertIn("model:sales-b", first)
        self.assertIn("measure:revenue-a", first)
        self.assertIn("measure:revenue-b", first)
        self.assertIn("relationship:a", first)
        self.assertIn('"reference":"Missing KPI"', first)
        self.assertIn('"reference":"[Missing Rate]"', first)
        self.assertIn("ambiguous_reference", first)
        self.assertIn("unresolved_relationship", first)
        self.assertIn("parse_error", first)
        self.assertIn("Unexpected token", first)
        self.assertIn("Diagnostics and limitations", first)
        self.assertIn("Evidence class", first)
        self.assertIn("Review overrides are not applied", first)
        self.assertIn("Unknown (not stored)", first)
        self.assertNotIn("Generated at", first)

    def test_content_identity_tracks_canonical_content_only(self):
        repository = self._repository()
        before = snapshot_content_identity(repository)
        repository.last_scan = "2099-01-01T00:00:00+00:00"

        self.assertEqual(snapshot_content_identity(repository), before)

        repository.get_object("measure:revenue-a").properties["expression"] += " + 1"
        self.assertNotEqual(snapshot_content_identity(repository), before)

    def test_cli_stdout_and_exclusive_file_leave_project_inputs_untouched(self):
        repository = self._repository()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.json"
            identity = root / "identity.json"
            database = root / "brain.lbug"
            source.write_text('{"models": []}\n', encoding="utf-8")
            identity.write_text('{"version": 1}\n', encoding="utf-8")
            database.write_text("database sentinel\n", encoding="utf-8")
            config = root / "brain.json"
            config.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "name": "Portfolio",
                        "sources": ["source.json"],
                        "database": "brain.lbug",
                        "identity_map": "identity.json",
                    }
                ),
                encoding="utf-8",
            )
            originals = {path: path.read_bytes() for path in (source, identity, database, config)}

            stdout = io.StringIO()
            with patch("backend.cli.main.GraphRepository", return_value=repository), redirect_stdout(stdout):
                self.assertEqual(cli_main(["--config", str(config), "export-markdown"]), 0)
            self.assertTrue(stdout.getvalue().startswith("# PBIBrain documentation export\n"))

            for protected in (source, identity, database, config):
                with self.subTest(protected=protected), patch("backend.cli.main.GraphRepository") as graph_repository, redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
                    cli_main(["--config", str(config), "export-markdown", "--output", str(protected)])
                self.assertEqual(raised.exception.code, 2)
                graph_repository.assert_not_called()

            output = root / "export.md"
            stdout = io.StringIO()
            with patch("backend.cli.main.GraphRepository", return_value=repository), redirect_stdout(stdout):
                self.assertEqual(cli_main(["--config", str(config), "export-markdown", "--output", str(output)]), 0)
            self.assertEqual(output.read_text(encoding="utf-8"), render_markdown(repository, project_name="Portfolio"))
            for path, content in originals.items():
                self.assertEqual(path.read_bytes(), content)

            with patch("backend.cli.main.GraphRepository", return_value=repository), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
                cli_main(["--config", str(config), "export-markdown", "--output", str(output)])
            self.assertEqual(raised.exception.code, 2)
            self.assertEqual(output.read_text(encoding="utf-8"), render_markdown(repository, project_name="Portfolio"))

    def test_cli_rejects_pbip_artifact_descendant_before_opening_repository(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = root / "Finance.SemanticModel"
            artifact.mkdir()
            project = root / "Finance.pbip"
            project.write_text(
                json.dumps({"artifacts": [{"semanticModel": {"path": "Finance.SemanticModel"}}]}),
                encoding="utf-8",
            )
            config = root / "brain.json"
            config.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "name": "Finance",
                        "sources": ["Finance.pbip"],
                        "database": "brain.lbug",
                        "identity_map": "identity.json",
                    }
                ),
                encoding="utf-8",
            )
            output = artifact / "export.md"

            with patch("backend.cli.main.GraphRepository") as graph_repository, redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
                cli_main(["--config", str(config), "export-markdown", "--output", str(output)])

            self.assertEqual(raised.exception.code, 2)
            graph_repository.assert_not_called()
            self.assertFalse(output.exists())

    def test_redirected_subprocess_stdout_is_utf8(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = root / "brain.json"
            config.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "name": "Árvíztűrő projekt",
                        "sources": [],
                        "database": "brain.lbug",
                        "identity_map": "identity.json",
                    }
                ),
                encoding="utf-8",
            )
            code = "\n".join(
                (
                    "from unittest.mock import patch",
                    "from backend.cli.main import main",
                    "from backend.graph.repository import GraphRepository",
                    "from backend.graph.schema import Node",
                    "repository = GraphRepository(use_native=False)",
                    "repository.replace([Node('model:unicode', 'MODEL', 'Mérleg 🧠')], [])",
                    "with patch('backend.cli.main.GraphRepository', return_value=repository):",
                    f"    raise SystemExit(main(['--config', {str(config)!r}, 'export-markdown']))",
                )
            )

            completed = subprocess.run(
                [sys.executable, "-c", code],
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr.decode("utf-8", errors="replace"))
            decoded = completed.stdout.decode("utf-8")
            self.assertIn("Árvíztűrő projekt", decoded)
            self.assertIn("Mérleg 🧠", decoded)


if __name__ == "__main__":
    unittest.main()
