import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { buildGraph } from "../src/graph/build.js";
import { readGraph } from "../src/graph/write.js";
import { callersOf, calleesOf, impactOf, resolveSymbol } from "../src/graph/traverse.js";
import { ask } from "../src/ask/ask.js";

function writeRepoFile(root: string, rel: string, content: string): void {
  const full = join(root, rel);
  mkdirSync(join(full, ".."), { recursive: true });
  writeFileSync(full, content, "utf8");
}

test("trail-pbi indexes full Fabric + Power BI repo (TMDL, DAX, M, PBIR, SQL, KQL, Python) with exact spans and lineage edges", async () => {
  const dir = mkdtempSync(join(tmpdir(), "trail-pbi-test-"));
  try {
    writeRepoFile(
      dir,
      "Sales.SemanticModel/.platform",
      JSON.stringify({
        metadata: { type: "SemanticModel", displayName: "Sales Semantic Model" },
        config: { logicalId: "sm-001" },
      }),
    );

    writeRepoFile(
      dir,
      "Sales.SemanticModel/definition/model.tmdl",
      [
        "model Model",
        "\tculture: en-US",
        "\tdefaultPowerBIDataSourceVersion: powerBI_V3",
      ].join("\n"),
    );

    writeRepoFile(
      dir,
      "Sales.SemanticModel/definition/expressions.tmdl",
      [
        "expression ServerHost = \"sql.fabric.windows.net\" meta [IsParameterQuery=true, Type=\"Text\"]",
        "\tlineageTag: expr-host",
      ].join("\n"),
    );

    writeRepoFile(
      dir,
      "Sales.SemanticModel/definition/relationships.tmdl",
      [
        "relationship rel_sales_date",
        "\tfromColumn: Sales.OrderDate",
        "\ttoColumn: 'Date'.Date",
        "\tcrossFilteringBehavior: oneDirection",
      ].join("\n"),
    );

    writeRepoFile(
      dir,
      "Sales.SemanticModel/definition/tables/Sales.tmdl",
      [
        "table Sales",
        "\tlineageTag: tbl-sales",
        "",
        "\tcolumn OrderDate",
        "\t\tdataType: dateTime",
        "\t\tsourceColumn: OrderDate",
        "",
        "\tcolumn Amount",
        "\t\tdataType: decimal",
        "\t\tsourceColumn: Amount",
        "",
        "\tmeasure 'Total Revenue' = ```",
        "\t\tSUMX(",
        "\t\t    Sales,",
        "\t\t    Sales[Amount]",
        "\t\t)",
        "\t```",
        "\t\tformatString: $#,0.00",
        "",
        "\tmeasure 'YoY Revenue' =",
        "\t\tCALCULATE(",
        "\t\t    [Total Revenue],",
        "\t\t    SAMEPERIODLASTYEAR('Date'[Date]),",
        "\t\t    USERELATIONSHIP(Sales[OrderDate], 'Date'[Date])",
        "\t\t)",
        "",
        "\tpartition Sales-Partition = m",
        "\t\tmode: import",
        "\t\tsource =",
        "\t\t\tlet",
        "\t\t\t    Source = Sql.Database(\"sql.fabric.windows.net\", \"SalesDW\"),",
        "\t\t\t    View = Source{[Schema=\"dbo\",Item=\"v_FactSales\"]}[Data]",
        "\t\t\tin",
        "\t\t\t    View",
      ].join("\n"),
    );

    writeRepoFile(
      dir,
      "Sales.SemanticModel/definition/tables/Date.tmdl",
      [
        "table 'Date'",
        "\tdataCategory: Time",
        "",
        "\tcolumn Date",
        "\t\tdataType: dateTime",
        "\t\tisKey",
        "",
        "\tcolumn Year",
        "\t\tdataType: int64",
        "",
        "\thierarchy Calendar",
        "\t\tlevel Year",
        "\t\t\tcolumn: Year",
      ].join("\n"),
    );

    writeRepoFile(
      dir,
      "Sales.SemanticModel/definition/roles/EMEA.tmdl",
      [
        "role EMEA",
        "\tmodelPermission: read",
        "\ttablePermission Sales = Sales[Amount] > 0",
      ].join("\n"),
    );

    writeRepoFile(
      dir,
      "Sales.Report/.platform",
      JSON.stringify({
        metadata: { type: "Report", displayName: "Sales Report" },
        config: { logicalId: "rpt-001" },
      }),
    );

    writeRepoFile(
      dir,
      "Sales.Report/definition.pbir",
      JSON.stringify({
        version: "4.0",
        datasetReference: {
          byPath: { path: "../Sales.SemanticModel" },
        },
      }),
    );

    writeRepoFile(
      dir,
      "Sales.Report/definition/report.json",
      JSON.stringify({
        name: "Executive Sales Report",
      }),
    );

    writeRepoFile(
      dir,
      "Sales.Report/definition/reportExtensions.json",
      JSON.stringify({
        entities: [
          {
            name: "Sales",
            measures: [
              {
                name: "Report Margin",
                expression: "DIVIDE([Total Revenue], 2)",
              },
            ],
          },
        ],
      }),
    );

    writeRepoFile(
      dir,
      "Sales.Report/definition/pages/Overview/page.json",
      JSON.stringify({
        name: "OverviewPage",
        displayName: "Executive Overview",
      }),
    );

    writeRepoFile(
      dir,
      "Sales.Report/definition/pages/Overview/visuals/RevenueCard/visual.json",
      JSON.stringify({
        name: "RevenueCard",
        visual: {
          visualType: "card",
          query: {
            queryState: {
              Values: {
                projections: [
                  {
                    field: {
                      Measure: {
                        Expression: { SourceRef: { Entity: "Sales" } },
                        Property: "Total Revenue",
                      },
                    },
                  },
                  {
                    field: {
                      HierarchyLevel: {
                        Expression: {
                          Hierarchy: {
                            Expression: { SourceRef: { Entity: "Date" } },
                            Hierarchy: "Calendar",
                          },
                        },
                        Level: "Year",
                      },
                    },
                  },
                ],
              },
            },
          },
        },
      }),
    );

    writeRepoFile(
      dir,
      "warehouse/dbo/v_FactSales.sql",
      [
        "CREATE TABLE dbo.FactSales (",
        "    OrderDate DATETIME2,",
        "    Amount DECIMAL(18, 2)",
        ");",
        "",
        "CREATE VIEW dbo.v_FactSales AS",
        "SELECT OrderDate, Amount",
        "FROM dbo.FactSales;",
      ].join("\n"),
    );

    writeRepoFile(
      dir,
      "kql/Telemetry.kql",
      [
        ".create table RawEvents (Timestamp: datetime, Amount: real)",
        "",
        ".create-or-alter function HighValueEvents() {",
        "    RawEvents",
        "    | where Amount > 100",
        "}",
      ].join("\n"),
    );

    writeRepoFile(
      dir,
      "fabric_app/ingest.py",
      [
        "class FabricIngestor:",
        "    def load_batch(self):",
        "        return True",
        "",
        "def run_pipeline():",
        "    ingestor = FabricIngestor()",
        "    return ingestor.load_batch()",
      ].join("\n"),
    );

    const buildRes = await buildGraph(dir);
    assert.equal(buildRes.errors.length, 0, `Expected 0 build errors, got: ${buildRes.errors.join("; ")}`);
    for (const lang of ["tmdl", "pbir", "sql", "kql", "python"]) {
      assert.ok(buildRes.languages.includes(lang), `Expected language ${lang} in ${buildRes.languages.join(", ")}`);
    }

    const graph = readGraph(buildRes.graphPath);
    assert.ok(graph, "Expected wiring.json graph to be readable");

    // 1. Verify exact shifted TMDL spans
    const totalRev = resolveSymbol(graph, "Total Revenue").find((n) => n.kind === "measure");
    assert.ok(totalRev, "Expected Total Revenue measure node");
    assert.equal(totalRev.path, "Sales.SemanticModel/definition/tables/Sales.tmdl");
    assert.equal(totalRev.span, "L12-L18");

    // 2. Verify DAX dependencies: Total Revenue -> Sales[Amount]
    const totalRevCallees = calleesOf(graph, totalRev);
    assert.ok(
      totalRevCallees.some((h) => h.node?.name === "Amount" && h.node?.kind === "column" && h.relation === "depends_on"),
      "Expected Total Revenue to depend on column Sales[Amount]",
    );

    // 3. Verify YoY Revenue -> Total Revenue (depends_on) and OrderDate (activates_relationship)
    const yoyRev = resolveSymbol(graph, "YoY Revenue").find((n) => n.kind === "measure");
    assert.ok(yoyRev, "Expected YoY Revenue measure node");
    const yoyCallees = calleesOf(graph, yoyRev);
    assert.ok(
      yoyCallees.some((h) => h.node?.id === totalRev.id && h.relation === "depends_on"),
      "Expected YoY Revenue to depend on Total Revenue",
    );
    assert.ok(
      yoyCallees.some((h) => h.node?.name === "OrderDate" && h.relation === "activates_relationship"),
      "Expected YoY Revenue USERELATIONSHIP to emit activates_relationship edge",
    );

    // 4. Verify PBIR visual -> Measure & Hierarchy Level
    const visual = resolveSymbol(graph, "RevenueCard").find((n) => n.kind === "visual");
    assert.ok(visual, "Expected RevenueCard visual node");
    const visualCallees = calleesOf(graph, visual);
    assert.ok(
      visualCallees.some((h) => h.node?.id === totalRev.id && h.relation === "uses"),
      "Expected RevenueCard visual to use Total Revenue measure",
    );
    assert.ok(
      visualCallees.some((h) => h.node?.name === "Year" && h.relation === "uses"),
      "Expected RevenueCard visual to use Year hierarchy level",
    );

    // 5. Verify Report -> SemanticModel (uses_model)
    const reportNode = graph.nodes.find((n) => n.kind === "report" && n.path.endsWith("definition.pbir"));
    assert.ok(reportNode, "Expected PBIR report node");
    const reportCallees = calleesOf(graph, reportNode);
    assert.ok(
      reportCallees.some((h) => h.node?.kind === "semantic_model" && h.relation === "uses_model"),
      "Expected PBIR report to link to semantic_model via uses_model",
    );

    // 6. Verify Partition -> Data Source & SQL View (sources_from), and SQL View -> SQL Table (depends_on)
    const partition = resolveSymbol(graph, "Sales-Partition").find((n) => n.kind === "partition");
    assert.ok(partition, "Expected Sales-Partition node");
    const partCallees = calleesOf(graph, partition);
    assert.ok(
      partCallees.some((h) => h.node?.kind === "data_source" && h.relation === "sources_from"),
      "Expected partition to link to data_source via sources_from",
    );
    const sqlView = resolveSymbol(graph, "dbo.v_FactSales").find((n) => n.kind === "table");
    assert.ok(sqlView, "Expected SQL view dbo.v_FactSales node");
    assert.ok(
      partCallees.some((h) => h.node?.id === sqlView.id && h.relation === "sources_from"),
      "Expected partition to link to SQL view dbo.v_FactSales via sources_from",
    );
    const viewCallees = calleesOf(graph, sqlView);
    assert.ok(
      viewCallees.some((h) => h.node?.name === "dbo.FactSales" && h.relation === "sources_from"),
      "Expected SQL view dbo.v_FactSales to source from SQL table dbo.FactSales",
    );

    // 7. Verify KQL Function -> KQL Table
    const kqlFn = resolveSymbol(graph, "HighValueEvents").find((n) => n.kind === "function");
    assert.ok(kqlFn, "Expected KQL function HighValueEvents");
    assert.ok(
      calleesOf(graph, kqlFn).some((h) => h.node?.name === "RawEvents" && h.relation === "sources_from"),
      "Expected KQL function HighValueEvents to source from table RawEvents",
    );

    // 8. Verify multi-hop blast radius (impactOf) on column Sales[Amount]:
    // Changing Sales[Amount] impacts Total Revenue (depth 1) and RevenueCard visual + YoY Revenue + Report Margin (depth 2)
    const amountCol = resolveSymbol(graph, "Sales.Amount")[0];
    assert.ok(amountCol, "Expected Sales.Amount column");
    const blast = impactOf(graph, amountCol, 3);
    const impactedNames = new Set(blast.map((h) => h.node?.name));
    assert.ok(impactedNames.has("Total Revenue"), "Expected Total Revenue in blast radius of Sales[Amount]");
    assert.ok(impactedNames.has("YoY Revenue"), "Expected YoY Revenue in blast radius of Sales[Amount]");
    assert.ok(impactedNames.has("RevenueCard"), "Expected RevenueCard visual in blast radius of Sales[Amount]");
    assert.ok(impactedNames.has("Report Margin"), "Expected Report Margin report measure in blast radius of Sales[Amount]");

    // 9. Verify Python AST extraction still works side-by-side
    const pyFn = resolveSymbol(graph, "run_pipeline").find((n) => n.kind === "function");
    assert.ok(pyFn, "Expected Python function run_pipeline");
    assert.ok(
      calleesOf(graph, pyFn).some((h) => h.node?.name === "load_batch" && h.relation === "calls"),
      "Expected Python run_pipeline -> FabricIngestor.load_batch call edge",
    );

    // 10. Verify `ask` structural query on Power BI measure with spaces
    const askRes = ask(dir, "what visuals use [Total Revenue]", { contextDir: buildRes.contextDir });
    assert.equal(askRes.mode, "structural");
    assert.ok(
      askRes.hits.some((h) => h.title.includes("RevenueCard") || h.title.includes("YoY Revenue")),
      "Expected structural ask query to return callers/users of [Total Revenue]",
    );
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("trail-pbi indexes legacy TMSL model.bim, standalone .dax queries, and .pq dataflows", async () => {
  const dir = mkdtempSync(join(tmpdir(), "trail-pbi-tmsl-"));
  try {
    writeRepoFile(
      dir,
      "LegacySales.Dataset/model.bim",
      JSON.stringify(
        {
          name: "LegacySales",
          model: {
            culture: "en-US",
            tables: [
              {
                name: "Orders",
                columns: [{ name: "NetAmount", dataType: "decimal", sourceColumn: "NetAmount" }],
                measures: [
                  {
                    name: "Net Sales",
                    expression: ["SUM(", "    Orders[NetAmount]", ")"],
                  },
                ],
                partitions: [
                  {
                    name: "Orders-Part",
                    source: {
                      type: "m",
                      expression: [
                        "let",
                        '    Source = Lakehouse.Contents("lh-workspace"),',
                        '    Tbl = Source{[Item="fact_orders"]}[Data]',
                        "in",
                        "    Tbl",
                      ],
                    },
                  },
                ],
              },
            ],
          },
        },
        null,
        2,
      ),
    );

    writeRepoFile(
      dir,
      "queries/AuditSales.dax",
      [
        "DEFINE",
        "    MEASURE Orders[Audit Margin] = [Net Sales] * 0.25",
        "EVALUATE",
        "    SUMMARIZECOLUMNS(Orders[NetAmount], \"Margin\", [Audit Margin])",
      ].join("\n"),
    );

    writeRepoFile(
      dir,
      "dataflows/StagingOrders.pq",
      [
        "section Section1;",
        "shared StagingOrders = let",
        '    Source = Fabric.Warehouse("wh-prod"),',
        '    Data = Source{[Schema="dbo",Item="raw_orders"]}[Data]',
        "in",
        "    Data;",
      ].join("\n"),
    );

    const buildRes = await buildGraph(dir);
    assert.equal(buildRes.errors.length, 0);
    for (const lang of ["tmsl", "dax", "pq"]) {
      assert.ok(buildRes.languages.includes(lang), `Expected ${lang} in ${buildRes.languages.join(", ")}`);
    }

    const graph = readGraph(buildRes.graphPath)!;
    const netSales = resolveSymbol(graph, "Net Sales").find((n) => n.kind === "measure");
    assert.ok(netSales, "Expected Net Sales measure from model.bim");
    assert.ok(
      calleesOf(graph, netSales).some((h) => h.node?.name === "NetAmount" && h.relation === "depends_on"),
      "Expected Net Sales to depend on Orders[NetAmount]",
    );

    const auditMargin = resolveSymbol(graph, "Audit Margin").find((n) => n.kind === "measure");
    assert.ok(auditMargin, "Expected Audit Margin measure from .dax file");
    assert.ok(
      calleesOf(graph, auditMargin).some((h) => h.node?.id === netSales.id && h.relation === "depends_on"),
      "Expected standalone .dax measure Audit Margin to resolve cross-file to model.bim Net Sales",
    );

    const pqBinding = resolveSymbol(graph, "StagingOrders").find((n) => n.kind === "shared_expression");
    assert.ok(pqBinding, "Expected StagingOrders shared_expression from .pq file");
    assert.ok(
      calleesOf(graph, pqBinding).some((h) => h.node?.kind === "data_source" && h.relation === "sources_from"),
      "Expected .pq StagingOrders to link to Fabric.Warehouse data_source",
    );
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

