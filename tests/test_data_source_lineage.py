"""Data-source and Power Query lineage (#10): DATA_SOURCE nodes, SOURCES_FROM links, unread M marked "not checked"."""
import tempfile
import unittest
from pathlib import Path

from backend.api.app import BrainAPI, get_overview
from backend.api.graph import get_lineage
from backend.graph.loader import build_fact_graph
from backend.graph.m_sources import data_source_id, parameter_value, read_m_sources
from backend.graph.repository import GraphRepository
from backend.validation.graph import validate_graph_integrity
from tests.fixtures.pbip_sources import (
    AMOUNT_LINEAGE, DATE_KEY_LINEAGE, DATE_LINEAGE, NET_LINEAGE, SALES_DATE_LINEAGE, SALES_LINEAGE, write_pbip_project,
)

SALES_TMDL = f"""table Sales
    lineageTag: {SALES_LINEAGE}

    column Amount
        dataType: decimal
        lineageTag: {AMOUNT_LINEAGE}
        sourceColumn: Amount

    column DateKey
        dataType: int64
        lineageTag: {SALES_DATE_LINEAGE}
        sourceColumn: DateKey

    measure 'Net Sales' = SUM(Sales[Amount])
        lineageTag: {NET_LINEAGE}
        formatString: #,##0

    partition Sales-0001 = m
        mode: import
        source =
                let
                    // The server is a model parameter.
                    Source = Sql.Database(ServerName, "SalesDb"),
                    dbo_Sales = Source{{[Schema="dbo",Item="Sales"]}}[Data]
                in
                    dbo_Sales

    annotation PBI_ResultType = Table
"""

DATE_TMDL = f"""table Date
    lineageTag: {DATE_LINEAGE}

    column DateKey
        dataType: int64
        lineageTag: {DATE_KEY_LINEAGE}
        sourceColumn: DateKey

    partition Date-0001 = m
        mode: import
        source = ```
                let
                    Source = Lakehouse.Contents(null){{[workspaceId="ws-1"]}}[Data]{{[lakehouseId="lh-1"]}}[Data],
                    dim_date = Source{{[Id="dim_date",ItemKind="Table"]}}[Data]
                in
                    dim_date
                ```
"""

BUDGET_TMDL = """table Budget
    lineageTag: 0b0b0b0b-0000-0000-0000-000000000001

    column Value
        dataType: decimal
        lineageTag: 0b0b0b0b-0000-0000-0000-000000000002
        sourceColumn: Value

    partition Budget-0001 = m
        mode: import
        source =
                let
                    Source = Odbc.Query("dsn=Finance", "select * from budget")
                in
                    Source
"""

CUSTOMER_TMDL = """table Customer
    lineageTag: 0c0c0c0c-0000-0000-0000-000000000001

    column Name
        dataType: string
        lineageTag: 0c0c0c0c-0000-0000-0000-000000000002
        sourceColumn: name

    partition Customer = entity
        mode: directLake
        source
            entityName: customer
            schemaName: dbo
            expressionSource: DatabaseQuery
"""

EXPRESSIONS_TMDL = """expression ServerName = "sql-prod.database.windows.net" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]
    lineageTag: 0d0d0d0d-0000-0000-0000-000000000001
    queryGroup: Parameters

expression DatabaseQuery =
        let
            database = Sql.Database("abc.datawarehouse.fabric.microsoft.com", "lakehouse-guid")
        in
            database
    lineageTag: 0d0d0d0d-0000-0000-0000-000000000002
"""


def write_sourced_project(root: Path) -> Path:
    """The standard PBIP fixture, with SQL (parameterised server), lakehouse, Direct Lake and unread ODBC partitions."""

    project = write_pbip_project(root)
    definition = root / "Finance.SemanticModel" / "definition"
    for name, text in {"tables/Sales.tmdl": SALES_TMDL, "tables/Date.tmdl": DATE_TMDL, "tables/Budget.tmdl": BUDGET_TMDL,
                       "tables/Customer.tmdl": CUSTOMER_TMDL, "expressions.tmdl": EXPRESSIONS_TMDL}.items():
        (definition / name).write_text(text, encoding="utf-8")
    return project


class MSourceParserTests(unittest.TestCase):
    def test_sql_with_parameter_and_navigation(self):
        result = read_m_sources('let Source = Sql.Database(#"Server Name", "Db"), t = Source{[Schema="sales",Item="Orders"]}[Data] in t',
                                {"Server Name": "srv"})
        self.assertEqual(result.status, "read")
        self.assertEqual(result.parameters, ["Server Name"])
        self.assertEqual(result.sources, [{"connector": "Sql.Database", "kind": "sql", "server": "srv", "database": "Db",
                                           "schema": "sales", "object": "Orders"}])

    def test_let_step_literal_is_substituted(self):
        result = read_m_sources('let srv = "a.b", Source = Sql.Database(srv, "Db") in Source')
        self.assertEqual(result.sources[0]["server"], "a.b")

    def test_files_web_and_dataflows(self):
        csv = read_m_sources('let S = Csv.Document(File.Contents("C:\\data\\sales.csv"), [Delimiter=","]) in S')
        self.assertEqual((csv.sources[0]["kind"], csv.sources[0]["format"], csv.sources[0]["path"]), ("file", "csv", "C:\\data\\sales.csv"))
        excel = read_m_sources('let S = Excel.Workbook(Web.Contents("https://x.sharepoint.com/f.xlsx"), null, true), T = S{[Item="Sheet1",Kind="Sheet"]}[Data] in T')
        self.assertEqual((excel.sources[0]["kind"], excel.sources[0]["format"], excel.sources[0]["object"]), ("web", "excel", "Sheet1"))
        flow = read_m_sources('let S = PowerPlatform.Dataflows(null), W = S{[workspaceId="w"]}[Data], D = W{[dataflowId="d"]}[Data], '
                              'E = D{[entity="Customers",version=""]}[Data] in E')
        self.assertEqual({key: flow.sources[0][key] for key in ("kind", "workspace_id", "dataflow_id", "object")},
                         {"kind": "dataflow", "workspace_id": "w", "dataflow_id": "d", "object": "Customers"})

    def test_comment_markers_inside_strings_are_kept(self):
        result = read_m_sources('let S = Web.Contents("https://api.example.com/v1") /* note */ in S // done')
        self.assertEqual(result.sources[0]["url"], "https://api.example.com/v1")

    def test_unknown_connector_and_unresolved_argument_are_not_checked(self):
        unknown = read_m_sources('let S = Odbc.Query("dsn", "select 1") in S')
        self.assertEqual((unknown.status, unknown.sources), ("not_checked", []))
        self.assertIn("Odbc.Query", unknown.reasons[0])
        computed = read_m_sources('let S = Sql.Database(Text.Upper(x), "Db") in S')
        self.assertEqual(computed.status, "not_checked")
        self.assertIn("server of Sql.Database", computed.reasons[0])

    def test_entered_data_and_query_references_have_no_source(self):
        entered = read_m_sources('let S = Table.FromRows(Json.Document(Binary.Decompress(Binary.FromText("i45W", BinaryEncoding.Base64), '
                                 'Compression.Deflate)), let _t = ((type nullable text) meta [Serialized.Text = true]) in type table [A = _t]) in S')
        self.assertEqual(entered.status, "no_source")
        self.assertEqual(read_m_sources("let S = #\"Other query\" in S").status, "no_source")

    def test_native_query_keeps_the_database(self):
        result = read_m_sources('let S = Value.NativeQuery(Sql.Database("srv", "Db"), "select * from t", null, [EnableFolding=true]) in S')
        self.assertTrue(result.sources[0]["native_query"])
        self.assertEqual(result.sources[0]["query"], "select * from t")

    def test_parameter_value(self):
        self.assertEqual(parameter_value('"x" meta [IsParameterQuery=true]'), "x")
        self.assertIsNone(parameter_value("let a = 1 in a"))


class DataSourceLineageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.project = write_sourced_project(Path(temporary.name))
        self.graph = build_fact_graph(self.project, analyze_dax=True)
        self.nodes = {node.id: node for node in self.graph.nodes}
        self.repository = GraphRepository(use_native=False)
        self.graph.load(self.repository)
        self.addCleanup(self.repository.close)

    def _node(self, node_type, name):
        return next(node for node in self.graph.nodes if node.type == node_type and node.name == name)

    def _sources_of(self, node_id):
        return {self.nodes[edge.to_id].name for edge in self.graph.edges if edge.type == "SOURCES_FROM" and edge.from_id == node_id}

    def test_text_tmdl_reader_reads_partitions(self):
        sales = self._node("PARTITION", "Sales-0001")
        self.assertEqual(sales.properties["mode"], "import")
        self.assertIn("Sql.Database(ServerName", sales.properties["expression"])
        self.assertEqual(self._node("PARTITION", "Customer").properties["source_type"], "entity")

    def test_sources_appear_as_nodes(self):
        sources = {node.name: node for node in self.graph.nodes if node.type == "DATA_SOURCE"}
        # The DatabaseQuery expression reads the whole warehouse; the Direct Lake partition reads one table of it.
        self.assertEqual(set(sources), {"SalesDb.dbo.Sales", "dim_date", "lakehouse-guid", "lakehouse-guid.dbo.customer"})
        sql = sources["SalesDb.dbo.Sales"]
        self.assertEqual({key: sql.properties[key] for key in ("kind", "server", "database", "schema", "object")},
                         {"kind": "sql", "server": "sql-prod.database.windows.net", "database": "SalesDb", "schema": "dbo", "object": "Sales"})
        self.assertEqual(sources["dim_date"].properties["lakehouse_id"], "lh-1")
        self.assertIsNone(sql.model_id)
        self.assertEqual(sql.properties["model_ids"], [self._node("MODEL", "FinanceModel").id])

    def test_partitions_link_to_sources_and_parameters(self):
        sales = self._node("PARTITION", "Sales-0001")
        self.assertEqual(self._sources_of(sales.id), {"SalesDb.dbo.Sales"})
        self.assertEqual(sales.properties["source_parameters"], ["ServerName"])
        parameter = self._node("SHARED_EXPRESSION", "ServerName")
        self.assertTrue(any(edge.type == "REFERENCES" and edge.from_id == sales.id and edge.to_id == parameter.id for edge in self.graph.edges))
        self.assertEqual(parameter.properties["parameter_value"], "sql-prod.database.windows.net")
        # Direct Lake: the entity partition reads its table through the DatabaseQuery expression.
        customer = self._node("PARTITION", "Customer")
        self.assertEqual(self._sources_of(customer.id), {"lakehouse-guid.dbo.customer"})
        expression = self._node("SHARED_EXPRESSION", "DatabaseQuery")
        self.assertTrue(any(edge.type == "REFERENCES" and edge.from_id == customer.id and edge.to_id == expression.id for edge in self.graph.edges))

    def test_unread_m_is_not_checked_and_listed_in_the_overview(self):
        budget = self._node("PARTITION", "Budget-0001")
        self.assertEqual(budget.properties["check_status"], "not_checked")
        self.assertEqual(budget.properties["not_checked_reason"], "m_not_read")
        self.assertIn("Odbc.Query", budget.properties["not_checked_detail"])
        self.assertEqual(self._sources_of(budget.id), set())
        overview = get_overview(self.repository)
        listed = {item["name"]: item for item in overview["not_checked"]}
        self.assertEqual(set(listed), {"Budget-0001"})
        self.assertEqual(listed["Budget-0001"]["type"], "PARTITION")
        self.assertIn("Odbc.Query", listed["Budget-0001"]["not_checked_detail"])
        self.assertEqual(overview["data_sources"], 4)

    def test_graph_stays_valid(self):
        errors = [issue for issue in validate_graph_integrity(self.graph.to_dict()).issues if issue.severity in {"ERROR", "BLOCKING"}]
        self.assertEqual(errors, [])

    def test_lineage_of_a_model_includes_its_sources(self):
        model = self._node("MODEL", "FinanceModel")
        payload = get_lineage(self.repository, model_id=model.id)
        types = {node["id"]: node for node in payload["nodes"]}
        sql = self._node("DATA_SOURCE", "SalesDb.dbo.Sales")
        self.assertEqual(types[sql.id]["kind"], "sql")
        self.assertTrue(any(edge["type"] == "SOURCES_FROM" and edge["to_id"] == sql.id for edge in payload["edges"]))
        self.assertEqual(types[self._node("PARTITION", "Budget-0001").id]["check_status"], "not_checked")

    def test_source_to_visual_path_through_impact(self):
        api = BrainAPI(self.repository)
        sql = self._node("DATA_SOURCE", "SalesDb.dbo.Sales")
        visual = next(node for node in self.graph.nodes if node.type == "VISUAL")
        downstream = api.get_impact(sql.id)
        self.assertIn(visual.id, downstream["impacted_objects"])
        path = next(item for item in downstream["potential_impacts"] if item["object_id"] == visual.id)["path"]
        self.assertEqual(path[0]["edge_type"], "SOURCES_FROM")
        # The ODBC partition may read the same source: the closure is incomplete and says why.
        self.assertEqual(downstream["completeness"]["status"], "INCOMPLETE")
        self.assertIn("Budget-0001", {item["name"] for item in downstream["completeness"]["not_checked"]})

        upstream = api.get_impact(visual.id)
        names = {item["name"]: item for item in upstream["upstream_sources"]}
        self.assertIn("SalesDb.dbo.Sales", names)
        self.assertEqual(names["SalesDb.dbo.Sales"]["path"][0], visual.id)
        self.assertEqual(names["SalesDb.dbo.Sales"]["path"][-1], sql.id)
        self.assertNotIn("lakehouse-guid.dbo.customer", names, "only sources of the fields the visual uses")


class CrossModelSourceTests(unittest.TestCase):
    def test_two_models_reading_one_table_share_one_source_node(self):
        def model(model_id, server):
            return {"id": model_id, "name": model_id, "tables": [{"id": f"{model_id}-orders", "name": "Orders",
                    "columns": [{"id": f"{model_id}-amount", "name": "Amount"}],
                    "partitions": [{"name": "Orders", "source": {"type": "m", "expression":
                                    f'let S = Sql.Database("{server}", "Shop"), O = S{{[Schema="dbo",Item="Orders"]}}[Data] in O'}}]}]}

        graph = build_fact_graph([model("a", "SRV.contoso.com"), model("b", "srv.contoso.com")])
        sources = [node for node in graph.nodes if node.type == "DATA_SOURCE"]
        self.assertEqual(len(sources), 1, "server names compare without case")
        self.assertEqual(len(sources[0].properties["model_ids"]), 2)
        linked = {edge.from_id for edge in graph.edges if edge.type == "SOURCES_FROM" and edge.to_id == sources[0].id}
        self.assertEqual(len(linked), 2)
        self.assertEqual(sources[0].id, data_source_id({"kind": "sql", "server": "srv.contoso.com", "database": "Shop", "schema": "dbo", "object": "Orders"}))


if __name__ == "__main__":
    unittest.main()
