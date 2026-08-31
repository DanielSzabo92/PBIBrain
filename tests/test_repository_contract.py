"""Phase 1 repository contract tests."""

import json
import tempfile
import unittest
from pathlib import Path

from backend.graph.repository import GraphRepository, LadybugRepository
from backend.graph.schema import Edge, Node, ladybug_schema


MODEL = Node(
    id="model:model-001",
    type="MODEL",
    name="Revenue Model",
    description="Synthetic model.",
    model_id="model:model-001",
    source_id="model-001",
)
TABLE = Node(
    id="model:model-001/table:table-sales",
    type="TABLE",
    name="Sales",
    model_id="model:model-001",
    source_id="table-sales",
    properties={"hidden": False},
)
MEASURE = Node(
    id="model:model-001/measure:measure-sales",
    type="MEASURE",
    name="Sales",
    model_id="model:model-001",
    source_id="measure-sales",
    properties={"expression": "SUM('Sales'[Amount])"},
)
REPORT = Node(
    id="report:report-a",
    type="REPORT",
    name="Sales report",
    model_id="model:model-001",
    report_id="report:report-a",
    source_id="report-a",
)
VISUAL = Node(
    id="report:report-a/page:page-1/visual:visual-1",
    type="VISUAL",
    name="Sales chart",
    model_id="model:model-001",
    report_id="report:report-a",
    source_id="visual-1",
)

FACT_EDGES = [
    Edge(
        id="edge:model-contains-table",
        type="CONTAINS",
        from_id=MODEL.id,
        to_id=TABLE.id,
        source="model_metadata",
        evidence=["table belongs to model"],
    ),
    Edge(
        id="edge:table-contains-measure",
        type="CONTAINS",
        from_id=TABLE.id,
        to_id=MEASURE.id,
        source="model_metadata",
        evidence=["measure belongs to table"],
    ),
    Edge(
        id="edge:report-uses-model",
        type="USES_MODEL",
        from_id=REPORT.id,
        to_id=MODEL.id,
        source="report_metadata",
        evidence=["report model reference"],
    ),
    Edge(
        id="edge:visual-uses-measure",
        type="USES",
        from_id=VISUAL.id,
        to_id=MEASURE.id,
        source="report_metadata",
        evidence=["visual measure binding"],
    ),
]


class RepositoryContractTests(unittest.TestCase):
    def test_schema_declares_ladybug_node_and_relationship_tables(self):
        node_statement, edge_statement = ladybug_schema()
        self.assertIn("CREATE NODE TABLE", node_statement)
        self.assertIn("BrainNode", node_statement)
        self.assertIn("CREATE REL TABLE", edge_statement)
        self.assertIn("BrainEdge", edge_statement)

    def test_reopen_preserves_nodes_edges_and_queries(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "brain.lbug"
            repository = GraphRepository(path, use_native=False)
            repository.upsert_nodes([VISUAL, MEASURE, REPORT, MODEL, TABLE])
            repository.upsert_edges(FACT_EDGES)
            self.assertEqual(repository.storage, "json")
            self.assertTrue(path.exists())
            repository.close()

            reopened = GraphRepository(path, use_native=False)
            self.assertEqual(reopened.get_object(MEASURE.id).name, "Sales")
            self.assertEqual([item.id for item in reopened.get_dependencies(MEASURE.id)], [])
            self.assertEqual([item.id for item in reopened.get_usage(MEASURE.id)], [VISUAL.id])
            self.assertEqual(
                [item.id for item in reopened.get_neighbors(MODEL.id, ["CONTAINS"], direction="out")],
                [TABLE.id],
            )
            self.assertEqual(
                [item.id for item in reopened.get_neighbors(MODEL.id, ["USES_MODEL"], direction="in")],
                [REPORT.id],
            )
            self.assertEqual(
                [item.id for item in reopened.search_objects("sales")],
                [MEASURE.id, TABLE.id, REPORT.id, VISUAL.id],
            )
            self.assertEqual(
                [item.id for item in reopened.find_path(REPORT.id, TABLE.id)],
                [REPORT.id, MODEL.id, TABLE.id],
            )

            rows = reopened.query_graph("MATCH (n:BrainNode) RETURN n.*")
            self.assertEqual({row["id"] for row in rows}, {node.id for node in [MODEL, TABLE, MEASURE, REPORT, VISUAL]})
            reopened.close()

    def test_fact_edges_keep_fact_evidence_class_and_provenance(self):
        with GraphRepository(use_native=False) as repository:
            repository.upsert_nodes([MODEL, TABLE])
            edge = repository.upsert_edge(FACT_EDGES[0])
            value = edge.to_dict()
            self.assertEqual(value["status"], "factual")
            self.assertEqual(value["evidence_class"], "FACT")
            self.assertEqual(value["source"], "model_metadata")
            self.assertEqual(value["evidence"], ["table belongs to model"])

    def test_dependency_navigation_is_directional(self):
        base = Node(
            id="model:model-001/measure:measure-base",
            type="MEASURE",
            name="Base Sales",
            model_id="model:model-001",
            source_id="measure-base",
        )
        edge = Edge(
            id="edge:measure-dependency",
            type="DEPENDS_ON",
            from_id=MEASURE.id,
            to_id=base.id,
            source="dax_analysis",
            evidence=["[Base Sales]"],
        )
        with GraphRepository(use_native=False) as repository:
            repository.upsert_nodes([MEASURE, base])
            repository.upsert_edge(edge)
            self.assertEqual([item.id for item in repository.get_dependencies(MEASURE.id)], [base.id])
            self.assertEqual([item.id for item in repository.get_dependents(base.id)], [MEASURE.id])

    def test_rebuild_is_deterministic_independent_of_insert_order(self):
        with tempfile.TemporaryDirectory() as directory:
            first_path = Path(directory) / "first.lbug"
            second_path = Path(directory) / "second.lbug"
            first = GraphRepository(first_path, use_native=False)
            second = GraphRepository(second_path, use_native=False)
            nodes = [MODEL, TABLE, MEASURE, REPORT, VISUAL]
            first.upsert_nodes(nodes)
            first.upsert_edges(FACT_EDGES)
            second.upsert_nodes(reversed(nodes))
            second.upsert_edges(reversed(FACT_EDGES))
            self.assertEqual(
                [node.to_dict() for node in first.all_nodes()],
                [node.to_dict() for node in second.all_nodes()],
            )
            self.assertEqual(
                [edge.to_dict() for edge in first.all_edges()],
                [edge.to_dict() for edge in second.all_edges()],
            )
            self.assertEqual(json.loads(first_path.read_text()), json.loads(second_path.read_text()))

    def test_named_ladybug_repository_keeps_repository_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = LadybugRepository(Path(directory) / "brain.lbug", use_native=False)
            repository.upsert_node(MODEL)
            self.assertEqual(repository.get_node(MODEL.id).id, MODEL.id)


if __name__ == "__main__":
    unittest.main()
