"""PDF and scoped Markdown documentation export (issue #15)."""

from __future__ import annotations

import base64
import io
import re
import shutil
import subprocess
import tempfile
import unittest
import zlib
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from backend.api.app import BrainAPI, BrainApp
from backend.cli.main import main as cli_main
from backend.documentation_pdf import (
    DocumentationScopeError,
    build_document,
    export_documentation,
    render_document_markdown,
)
from backend.graph.repository import GraphRepository
from backend.graph.schema import Edge, Node
from backend.pdf_writer import pdf_text, wrap
from backend.projects import ProjectService

LAB = Path(__file__).resolve().parent / "fixtures" / "merge_lab"
STAMP = "2026-11-07T12:00:00Z"


def _scan(root: Path) -> tuple[GraphRepository, Path]:
    config = root / "brain.json"
    service = ProjectService(config)
    service.save_config({"version": 1, "name": "Merge Lab", "sources": [str(path) for path in sorted(LAB.glob("*/*.pbip"))],
                         "database": "brain.lbug", "identity_map": "identity.json"})
    repository = GraphRepository(use_native=False)
    service.scan(repository)
    # A data source, a query PBIBrain could not read, and a description with Hungarian letters.
    nodes = repository.all_nodes()
    sales_a = next(node for node in nodes if node.type == "MODEL" and node.name == "SalesA")
    partition = next(node for node in nodes if node.type == "PARTITION" and node.model_id == sales_a.id and node.name == "Sales")
    store = next(node for node in nodes if node.type == "PARTITION" and node.model_id == sales_a.id and node.name == "Store")
    measure = next(node for node in nodes if node.type == "MEASURE" and node.model_id == sales_a.id and node.name == "Margin")
    repository.upsert_node(Node("data_source:warehouse", "DATA_SOURCE", "dbo.FactSales",
                                properties={"connector": "Sql.Database", "location": "sql01/Sales/dbo.FactSales", "model_ids": [sales_a.id]}))
    repository.upsert_edge(Edge("edge:sources", "SOURCES_FROM", partition.id, "data_source:warehouse"))
    repository.upsert_node(Node(store.id, store.type, store.name, model_id=store.model_id, properties={
        **store.properties, "check_status": "not_checked", "not_checked_reason": "m_not_read", "not_checked_detail": "Custom.Connector( is not known"}))
    repository.upsert_node(Node(measure.id, measure.type, measure.name, description="Árbevétel mínusz költség, ő és ű", model_id=measure.model_id,
                                properties=measure.properties))
    return repository, config


def _streams(pdf: bytes) -> list[bytes]:
    return [zlib.decompress(match) for match in re.findall(rb"stream\n(.*?)\nendstream", pdf, re.S)]


class DocumentationPdfTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls._temporary.name)
        cls.repository, cls.config = _scan(cls.root)
        cls.models = {node.name: node.id for node in cls.repository.all_nodes() if node.type == "MODEL"}
        cls.reports = {node.name: node.id for node in cls.repository.all_nodes() if node.type == "REPORT"}

    @classmethod
    def tearDownClass(cls) -> None:
        cls._temporary.cleanup()

    def export(self, fmt: str = "pdf", **scope) -> dict:
        return export_documentation(self.repository, fmt=fmt, project_name="Merge Lab", generated_at=STAMP, **scope)

    def test_pdf_is_well_formed_with_bookmarks_toc_links_and_diagrams(self):
        pdf = self.export()["data"]
        self.assertTrue(pdf.startswith(b"%PDF-1.4\n"))
        self.assertTrue(pdf.endswith(b"%%EOF\n"))
        # Every xref offset points at its object.
        start = int(re.search(rb"startxref\n(\d+)", pdf).group(1))
        table = pdf[start:].split(b"trailer")[0].split(b"\n")[3:]
        offsets = [int(line[:10]) for line in table if line.strip()]
        for number, offset in enumerate(offsets, start=1):
            self.assertTrue(pdf[offset:].startswith(f"{number} 0 obj".encode()), number)
        self.assertIn(b"/PageMode /UseOutlines", pdf)
        titles = re.findall(rb"/Title \(([^)]*)\) /Parent", pdf)
        for expected in (b"Overview and scope", b"Model: SalesA", b"Measure catalogue", b"Report: SalesA", b"Page: Overview",
                         b"Lineage summary", b"Not checked and unresolved"):
            self.assertIn(expected, titles)
        pages = int(re.search(rb"/Type /Pages /Kids \[[^\]]*\] /Count (\d+)", pdf).group(1))
        self.assertGreater(pages, 5)
        # The table of contents links every chapter and section to its page.
        self.assertGreaterEqual(pdf.count(b"/Subtype /Link"), len(titles))
        content = b"\n".join(_streams(pdf))
        self.assertIn(b"(Contents) Tj", content)
        self.assertIn(b" re B", content)  # diagram boxes
        self.assertIn(b"(Sales) Tj", content)
        self.assertIn(b"([Total Sales] - [Total Cost]) Tj", content)
        self.assertIn("Árbevétel mínusz költség, ö és ü".encode("cp1252"), content)

    def test_repeated_export_is_byte_stable_except_the_timestamp(self):
        first, second = self.export()["data"], self.export()["data"]
        self.assertEqual(first, second)
        later = export_documentation(self.repository, fmt="pdf", project_name="Merge Lab", generated_at="2026-12-24T08:30:00Z")["data"]
        self.assertNotEqual(first, later)

        def normalise(pdf: bytes, stamp: str) -> list[bytes]:
            # Outside the compressed streams only /Length and /CreationDate may change.
            frame = re.sub(rb"/Length \d+|/CreationDate \(D:\d+Z\)", b"", re.sub(rb"stream\n.*?\nendstream", b"", pdf, flags=re.S))
            frame = re.sub(rb"\d{10} 00000 n|startxref\n\d+", b"", frame)
            return [frame, *(part.replace(stamp.encode(), b"<T>") for part in _streams(pdf))]

        self.assertEqual(normalise(first, STAMP), normalise(later, "2026-12-24T08:30:00Z"))
        markdown = self.export("markdown")["data"]
        self.assertEqual(markdown, self.export("markdown")["data"])

    def test_scope_limits_models_reports_and_sections(self):
        document = build_document(self.repository, project_name="Merge Lab", generated_at=STAMP,
                                  model_ids=[self.models["SalesB"]], report_ids=[], sections=["overview", "measures"])
        markdown = render_document_markdown(document)
        self.assertIn("## Model: SalesB", markdown)
        self.assertNotIn("Model: SalesA", markdown)
        self.assertNotIn("## Report:", markdown)
        self.assertNotIn("### Model diagram", markdown)
        self.assertNotIn("## Lineage summary", markdown)
        self.assertIn("DIVIDE([Sales Amount] - [Total Cost], [Sales Amount])", markdown)
        self.assertEqual(document.scope, {"model_ids": [self.models["SalesB"]], "report_ids": [], "sections": ["overview", "measures"]})
        reports_only = render_document_markdown(build_document(self.repository, generated_at=STAMP, model_ids=[], report_ids=[self.reports["SalesA"]]))
        self.assertIn("## Report: SalesA", reports_only)
        self.assertIn("| marginbymonth | clusteredColumnChart | Date[Month]; Sales[Margin] |", reports_only)
        self.assertNotIn("## Model:", reports_only)
        for bad in ({"model_ids": ["model:nope"]}, {"sections": ["everything"]}, {"sections": []}, {"model_ids": [], "report_ids": []}):
            with self.subTest(bad=bad), self.assertRaises(DocumentationScopeError):
                build_document(self.repository, **bad)
        with self.assertRaises(DocumentationScopeError):
            export_documentation(self.repository, fmt="docx")

    def test_markdown_has_diagrams_lineage_markers_and_not_checked(self):
        markdown = self.export("markdown")["data"].decode("utf-8")
        self.assertTrue(markdown.startswith("# Merge Lab documentation\n"))
        self.assertIn("```mermaid\nflowchart TB", markdown)
        self.assertIn("```mermaid\nflowchart LR", markdown)
        self.assertIn('["dbo.FactSales<br/>Data source"]', markdown)
        self.assertIn("| dbo.FactSales | Sql.Database | sql01/Sales/dbo.FactSales | Sales | SalesA |", markdown)
        self.assertIn("| Store | PARTITION | m not read | Custom.Connector( is not known |", markdown)
        self.assertIn("Description: Árbevétel mínusz költség, ő és ű", markdown)  # exact text in Markdown
        self.assertIn("| INFERRED | candidate |", markdown)
        self.assertIn("| SEMANTICALLY_MAPS_TO | INFERRED |", markdown)
        self.assertIn("| OBSERVED_WITH | OBSERVED |", markdown)
        self.assertIn("```dax\n[Total Sales] - [Total Cost]\n```", markdown)

    def test_running_app_exports_through_the_api(self):
        app = BrainApp(BrainAPI(self.repository))
        status, reply = app.handle("POST", "/api/documentation-export", {"format": "pdf", "model_ids": [self.models["Finance"]], "report_ids": []})
        self.assertEqual(status, 200, reply)
        data = base64.b64decode(reply["content_base64"])
        self.assertTrue(data.startswith(b"%PDF"))
        self.assertEqual(reply["bytes"], len(data))
        self.assertEqual((reply["filename"], reply["content_type"]), ("pbibrain-documentation.pdf", "application/pdf"))
        self.assertEqual(reply["scope"]["model_ids"], [self.models["Finance"]])
        status, reply = app.handle("POST", "/api/documentation-export", {"format": "markdown"})
        self.assertEqual(status, 200)
        self.assertIn("## Model: Finance", base64.b64decode(reply["content_base64"]).decode("utf-8"))
        for bad in ({"format": "pdf", "extra": 1}, {"model_ids": "model:x"}, {"model_ids": ["model:unknown"]}, {"format": "html"}):
            with self.subTest(bad=bad):
                self.assertEqual(app.handle("POST", "/api/documentation-export", bad)[0], 400)
        self.assertEqual(app.handle("GET", "/api/documentation-export")[0], 404)

    def test_cli_export_docs_creates_a_new_file_only(self):
        output = self.root / "out" / "doc.pdf"
        output.parent.mkdir(exist_ok=True)
        with patch("backend.cli.main.GraphRepository", return_value=self.repository), redirect_stdout(io.StringIO()):
            self.assertEqual(cli_main(["--config", str(self.config), "export-docs", "--output", str(output),
                                       "--model-id", self.models["SalesA"], "--section", "measures"]), 0)
        self.assertTrue(output.read_bytes().startswith(b"%PDF"))
        before = output.read_bytes()
        with patch("backend.cli.main.GraphRepository", return_value=self.repository), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            cli_main(["--config", str(self.config), "export-docs", "--output", str(output)])
        self.assertEqual(output.read_bytes(), before)
        with patch("backend.cli.main.GraphRepository", return_value=self.repository), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            cli_main(["--config", str(self.config), "export-docs", "--output", str(self.root / "x.md"), "--format", "markdown", "--section", "nope"])
        self.assertFalse((self.root / "x.md").exists())

    @unittest.skipUnless(shutil.which("pdftotext") and shutil.which("pdfinfo"), "poppler not installed")
    def test_a_real_pdf_reader_opens_it(self):
        path = self.root / "reader.pdf"
        path.write_bytes(self.export()["data"])
        info = subprocess.run(["pdfinfo", str(path)], capture_output=True, text=True, check=True)
        self.assertIn("Title:           Merge Lab documentation", info.stdout)
        self.assertEqual("", info.stderr)
        text = subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True, check=True).stdout
        self.assertIn("Measure catalogue", text)
        self.assertIn("dbo.FactSales", text)


class PdfTextTests(unittest.TestCase):
    def test_letters_fall_back_to_the_nearest_glyph(self):
        self.assertEqual(pdf_text("Árvíz ő ű Ő Ű"), "Árvíz ö ü Ö Ü")
        self.assertEqual(pdf_text("売上 → x"), "?? -> x")

    def test_wrap_breaks_long_words_and_keeps_code_spaces(self):
        lines = wrap("A" * 300, "regular", 10, 100)
        self.assertGreater(len(lines), 3)
        self.assertTrue(all(lines))
        self.assertEqual(wrap("VAR  x = 1\nRETURN x", "mono", 8, 400), ["VAR  x = 1", "RETURN x"])


if __name__ == "__main__":
    unittest.main()


class LargeModelLayoutTests(unittest.TestCase):
    def test_long_dax_many_tables_and_long_cells_lay_out_on_pages(self):
        model = "model:big"
        nodes = [Node(model, "MODEL", "Big")]
        for index in range(60):
            nodes.append(Node(f"{model}/table:{index}", "TABLE", f"Table {index:02d} " + "x" * (index % 7) * 9, model_id=model,
                              description="Long description " * 40))
        nodes.append(Node(f"{model}/column:a", "COLUMN", "Key", model_id=model, properties={"table_id": f"{model}/table:0"}))
        nodes.append(Node(f"{model}/column:b", "COLUMN", "Key", model_id=model, properties={"table_id": f"{model}/table:1"}))
        nodes.append(Node(f"{model}/relationship:r", "RELATIONSHIP", "r", model_id=model,
                          properties={"from_column_id": f"{model}/column:a", "to_column_id": f"{model}/column:b", "cardinality": "manyToOne", "active": False}))
        dax = "\n".join(f"VAR v{index} = CALCULATE([Base], 'Table'[Column] = {index}) + " + "1" * 150 for index in range(400)) + "\nRETURN v1"
        nodes.append(Node(f"{model}/measure:m", "MEASURE", "Huge", model_id=model, properties={"table_id": f"{model}/table:0", "expression": dax}))
        repository = GraphRepository(use_native=False)
        repository.replace(nodes, [])
        document = build_document(repository, generated_at=STAMP)
        result = export_documentation(repository, fmt="pdf", generated_at=STAMP)
        content = b"\n".join(_streams(result["data"]))
        pages = int(re.search(rb"/Type /Pages /Kids \[[^\]]*\] /Count (\d+)", result["data"]).group(1))
        self.assertGreater(pages, 10)
        self.assertIn(b"VAR v399", content)  # the whole expression is printed across pages
        self.assertIn(b"(*:1) Tj", content)  # cardinality label on the diagram line
        self.assertIn(b"[3 2] 0 d", content)  # inactive relationship is dashed
        markdown = render_document_markdown(document)
        self.assertIn("-.-|*:1|", markdown)
