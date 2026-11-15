import test from "node:test";
import assert from "node:assert/strict";
import { buildExplorerGraph, bundleExplorerEdges, layoutExplorerGraph } from "../src/graphLayout.js";
import { foldLineage, layoutLineage, FOLD_ABOVE } from "../src/lineage.js";
import { formatCount, linksOf, objectName } from "../src/presentation.js";

// A project of `models` models, each with `tables` tables of `columns` columns and `measures` measures,
// and one report per model with `visuals` visuals that each use one measure.
function project({ models = 2, tables = 10, columns = 12, measures = 6, visuals = 30 } = {}) {
  const nodes = [], edges = [];
  let n = 0;
  const link = (type, from_id, to_id) => edges.push({ id: `e${n++}`, type, from_id, to_id, status: "factual" });
  for (let m = 0; m < models; m += 1) {
    const model = `model:${m}`, report = `report:${m}`, page = `${report}/page:0`;
    nodes.push({ id: model, type: "MODEL", name: `Model ${m}` }, { id: report, type: "REPORT", name: `Report ${m}` }, { id: page, type: "PAGE", name: "Page" });
    link("USES_MODEL", report, model); link("CONTAINS", report, page);
    const allMeasures = [];
    for (let t = 0; t < tables; t += 1) {
      const table = `${model}/table:${t}`;
      nodes.push({ id: table, type: "TABLE", name: `Table ${t}` }); link("CONTAINS", model, table);
      for (let c = 0; c < columns; c += 1) { const id = `${table}/column:${c}`; nodes.push({ id, type: "COLUMN", name: `Column ${c}` }); link("CONTAINS", table, id); }
      for (let k = 0; k < measures; k += 1) { const id = `${table}/measure:${k}`; nodes.push({ id, type: "MEASURE", name: `Measure ${k}` }); link("CONTAINS", table, id); link("REFERENCES", id, `${table}/column:0`); allMeasures.push(id); }
    }
    for (let v = 0; v < visuals; v += 1) { const id = `${page}/visual:${v}`; nodes.push({ id, type: "VISUAL", name: `Visual ${v}`, title: `Visual ${v}` }); link("CONTAINS", page, id); link("USES", id, allMeasures[v % allMeasures.length]); }
  }
  return { nodes, edges };
}

test("a collapsed project shows every model and report with what is inside, by type", () => {
  const { nodes, edges } = project();
  const explorer = buildExplorerGraph(nodes, edges, []);
  assert.deepEqual(explorer.nodes.map((node) => node.type).sort(), ["MODEL", "MODEL", "REPORT", "REPORT"]);
  const model = explorer.nodes.find((node) => node.id === "model:0");
  assert.deepEqual(model.explorerTypeCounts, { TABLE: 10, COLUMN: 120, MEASURE: 60 });
  assert.equal(explorer.hiddenCount, nodes.length - 4);
});

test("links between hidden objects are lifted to the owners that are shown, with a count", () => {
  const { nodes, edges } = project();
  // Both collapsed: the report already has a direct "uses model" link, so no bundle doubles it.
  assert.deepEqual(bundleExplorerEdges(buildExplorerGraph(nodes, edges, []), edges), []);
  // Model 0 opened: its tables are shown and the report's uses are counted per table.
  const open = buildExplorerGraph(nodes, edges, ["model:0"]);
  const bundles = bundleExplorerEdges(open, edges);
  assert.ok(bundles.length > 0 && bundles.every((bundle) => bundle.bundle && bundle.count >= 1));
  const total = bundles.filter((bundle) => bundle.from_id === "report:0" || bundle.to_id === "report:0").reduce((sum, bundle) => sum + bundle.count, 0);
  assert.equal(total, 30, "every use by a visual of report 0 is counted once");
  const shown = new Set(open.nodes.map((node) => node.id));
  assert.ok(bundles.every((bundle) => shown.has(bundle.from_id) && shown.has(bundle.to_id)), "no bundle ends at a hidden object");
});

test("in a large picture, reports are laid out after everything opened inside a model", () => {
  const { nodes, edges } = project();
  const open = buildExplorerGraph(nodes, edges, ["model:0"]);
  const layout = layoutExplorerGraph(open.nodes, open.edges, "LR", null, undefined, { reportsLast: true });
  const x = (id) => layout.nodes.find((item) => item.node.id === id).position.x;
  assert.ok(x("model:0") < x("model:0/table:0"));
  assert.ok(x("model:0/table:0") < x("report:0"), "the report stands right of the tables");
});

test("a large lineage folds long lanes by owner and counts the links between rows", () => {
  const { nodes, edges } = project();
  assert.ok(nodes.length > FOLD_ABOVE);
  const folded = foldLineage(nodes, edges);
  assert.ok(folded.nodes.length < nodes.length / 4);
  const fold = folded.nodes.find((node) => node.id === "fold:column:model:0/table:0");
  assert.deepEqual([fold.fold, fold.foldCount, fold.type, fold.name], [true, 12, "COLUMN", "Table 0"]);
  assert.equal(folded.folded, nodes.length - (folded.nodes.length - folded.nodes.filter((node) => node.fold).length));
  const ids = new Set(folded.nodes.map((node) => node.id));
  assert.ok(folded.edges.every((edge) => ids.has(edge.from_id) && ids.has(edge.to_id)), "no link ends at a folded object");
  const uses = folded.edges.find((edge) => edge.bundle && edge.from_id === "fold:calc:model:0/table:0" && edge.to_id === "fold:column:model:0/table:0");
  assert.equal(uses.count, 6);
  // The lane header counts objects, not rows.
  const layout = layoutLineage(folded.nodes, folded.edges);
  assert.equal(layout.lanes.find((lane) => lane.key === "column").count, 240);
});

test("an opened fold shows its objects again; a small lineage is never folded", () => {
  const { nodes, edges } = project();
  const opened = foldLineage(nodes, edges, ["fold:column:model:0/table:0"]);
  assert.ok(opened.nodes.some((node) => node.id === "model:0/table:0/column:3"));
  assert.ok(!opened.nodes.some((node) => node.id === "fold:column:model:0/table:0"));
  const small = project({ models: 1, tables: 2, columns: 3, measures: 2, visuals: 4 });
  assert.equal(foldLineage(small.nodes, small.edges), null);
});

test("ordering 10,000 objects stays fast", () => {
  const { nodes, edges } = project({ models: 8, tables: 30, columns: 18, measures: 10, visuals: 180 });
  assert.ok(nodes.length > 8000);
  const start = performance.now();
  buildExplorerGraph(nodes, edges, []);
  foldLineage(nodes, edges);
  assert.ok(performance.now() - start < 1500, "explorer and fold build in well under the old 3.6 s");
});

test("counts read as people write them; links of one object come from an index", () => {
  assert.equal(formatCount(13731), "13,731");
  const edges = [{ id: "a", from_id: "x", to_id: "y" }, { id: "b", from_id: "y", to_id: "z" }];
  assert.deepEqual(linksOf(edges, "y").incoming.map((edge) => edge.id), ["a"]);
  assert.deepEqual(linksOf(edges, "y").outgoing.map((edge) => edge.id), ["b"]);
  assert.deepEqual(linksOf(edges, "none").incoming, []);
  const node = { type: "MEASURE", name: "Sales" };
  assert.equal(objectName(node), "Sales");
  node.name = "Net Sales";
  assert.equal(objectName(node), "Net Sales", "a renamed object is not served a stale name");
});

test("search folds the copies of one object across models and keeps same-model namesakes apart", async () => {
  const { foldSearchResults, matchSnippet } = await import("../src/presentation.js");
  const items = [
    { id: "a", type: "MEASURE", name: "Total", model_id: "m1" },
    { id: "x", type: "COLUMN", name: "Total", model_id: "m1" },
    { id: "b", type: "MEASURE", name: "Total", model_id: "m2" },
    { id: "c", type: "TABLE", name: "Dup", model_id: "m1" },
    { id: "d", type: "TABLE", name: "Dup", model_id: "m1" },
  ];
  const rows = foldSearchResults(items);
  assert.deepEqual(rows.map((row) => [row.item.id, row.copies.length]), [["a", 2], ["x", 1], ["c", 1], ["d", 1]]);
  assert.deepEqual(matchSnippet("VAR x = 1\nRETURN DIVIDE([Sales], x)", "divide"), ["RETURN ", "DIVIDE", "([Sales], x)"]);
  assert.equal(matchSnippet("abc", "zzz"), null);
});

test("the object tree lists owners first, opens on demand and filters by name with owners kept", async () => {
  const { objectForest } = await import("../src/graphLayout.js");
  const { ownersOf, treeRows } = await import("../src/objectTree.js");
  const nodes = [
    { id: "r", type: "REPORT", name: "A report" }, { id: "m", type: "MODEL", name: "Sales" },
    { id: "t", type: "TABLE", name: "Orders" }, { id: "c", type: "COLUMN", name: "Amount" }, { id: "x", type: "MEASURE", name: "Total" },
  ];
  const edges = [["m", "t"], ["t", "c"], ["t", "x"]].map(([from_id, to_id]) => ({ id: `${from_id}>${to_id}`, type: "CONTAINS", from_id, to_id }));
  const forest = objectForest(nodes, edges);
  assert.deepEqual(treeRows(forest).map((row) => row.id), ["m", "r"]);
  assert.deepEqual(treeRows(forest, new Set(["m", "t"])).map((row) => [row.id, row.depth]), [["m", 0], ["t", 1], ["x", 2], ["c", 2], ["r", 0]]);
  assert.deepEqual(treeRows(forest, new Set(), "amou").map((row) => row.id), ["m", "t", "c"]);
  assert.deepEqual(ownersOf(forest, "c"), ["m", "t"]);
});

test("models stamped from one template are not folded as versions; real copies are", async () => {
  const { versionFamilies, versionStem } = await import("../src/versions.js");
  assert.equal(versionStem("Sales Analytics v2"), "sales analytics");
  assert.equal(versionStem("Sales Analytics (copy)"), "sales analytics");
  assert.equal(versionStem("Sales Analytics - DEV 2024-05-01"), "sales analytics");
  assert.notEqual(versionStem("HR Analytics"), versionStem("Sales Analytics"));
  const model = (id, name) => [{ id, type: "MODEL", name }, { id: `${id}/t`, type: "TABLE", name: "Orders", model_id: id }, { id: `${id}/m`, type: "MEASURE", name: "Total", model_id: id, table_id: `${id}/t` }];
  const { families } = versionFamilies([...model("a", "Sales Analytics"), ...model("b", "HR Analytics"), ...model("c", "Sales Analytics v2")]);
  assert.deepEqual([...families.values()].map((members) => members.map((member) => member.id)).sort(), [["a", "c"], ["b"]]);
});
