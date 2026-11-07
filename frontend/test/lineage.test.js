import assert from "node:assert/strict";
import test from "node:test";
import { hideLanes, layoutLineage, lineageOf, laneOf, LANES, MAX_LANE_WIDTH, THROUGH, TWO_LINE_HEIGHT } from "../src/lineage.js";
import { buildImpactMatrix } from "../src/matrix.js";
import { groupVersions, versionFamilies } from "../src/versions.js";

const node = (id, type, extra = {}) => ({ id, type, name: id, status: "factual", ...extra });
const edge = (from_id, type, to_id) => ({ id: `${from_id}-${type}-${to_id}`, from_id, type, to_id });

// One model feeding one report: model › table › (column, measure) › visual › page › report, plus filters.
const nodes = [
  node("m", "MODEL"), node("t", "TABLE"), node("c", "COLUMN"), node("c2", "COLUMN"), node("x", "MEASURE"), node("y", "MEASURE"), node("unused", "MEASURE"),
  node("v", "VISUAL"), node("v2", "VISUAL"), node("p", "PAGE"), node("pf", "PAGE_FILTER"), node("r", "REPORT"),
  node("m2", "MODEL"), node("t2", "TABLE"), node("z", "COLUMN"),
];
const edges = [
  edge("m", "CONTAINS", "t"), edge("t", "CONTAINS", "c"), edge("t", "CONTAINS", "c2"), edge("t", "CONTAINS", "x"), edge("t", "CONTAINS", "y"), edge("t", "CONTAINS", "unused"),
  edge("x", "REFERENCES", "c"), edge("y", "DEPENDS_ON", "x"),
  edge("v", "USES", "y"), edge("p", "CONTAINS", "v"), edge("p", "CONTAINS", "v2"), edge("p", "CONTAINS", "pf"), edge("pf", "FILTERS", "c2"),
  edge("r", "CONTAINS", "p"), edge("r", "USES_MODEL", "m"),
  edge("m2", "CONTAINS", "t2"), edge("t2", "CONTAINS", "z"),
];

test("lineage lanes run model › tables › columns › calculations › visuals › pages › reports", () => {
  assert.equal(LANES[laneOf({ type: "FIELD_PARAMETER" })].key, "calc");
  assert.equal(LANES[laneOf({ type: "USER_DEFINED_FUNCTION" })].key, "calc");
  assert.equal(LANES[laneOf({ type: "BUSINESS_CONCEPT" })].key, "meaning");
  const layout = layoutLineage(nodes, edges);
  const x = (id) => layout.nodes.find((item) => item.node.id === id).position.x;
  assert.ok(x("m") < x("t") && x("t") < x("c") && x("c") < x("x") && x("x") < x("v") && x("v") < x("p") && x("p") < x("pf") && x("pf") < x("r"));
  assert.equal(x("x"), x("y"), "measures share one lane");
  assert.deepEqual(layout.lanes.map((lane) => lane.key), ["model", "table", "column", "calc", "visual", "page", "pageFilter", "report"]);
  // Every edge is drawn in flow direction: never from a later lane back to an earlier one.
  layout.edges.forEach(({ from, to }) => assert.ok(x(from) <= x(to), `${from} → ${to}`));
  // Same-lane dependency flows from the used measure to its user.
  assert.deepEqual((({ from, to }) => [from, to])(layout.edges.find(({ edge: item }) => item.type === "DEPENDS_ON")), ["x", "y"]);
});

test("lineage keeps each model's objects together", () => {
  const layout = layoutLineage(nodes, edges);
  const y = (id) => layout.nodes.find((item) => item.node.id === id).position.y;
  const columnsOfFirst = ["c", "c2"].map(y), other = y("z");
  assert.ok(columnsOfFirst.every((value) => value < other) || columnsOfFirst.every((value) => value > other));
});

test("selecting an object traces what feeds it and what it feeds, but not its siblings", () => {
  const layout = layoutLineage(nodes, edges);
  const { ids } = lineageOf("x", layout.edges);
  for (const id of ["x", "c", "t", "m", "y", "v", "p", "r"]) assert.ok(ids.has(id), id);
  for (const id of ["c2", "unused", "v2", "z"]) assert.ok(!ids.has(id), id);
});

test("impact matrix marks direct, indirect and filter use, and knows unbound blocks", () => {
  const matrix = buildImpactMatrix(nodes, edges);
  assert.equal(matrix.cell("y", "v"), 2, "direct");
  assert.equal(matrix.cell("x", "v"), 1, "through a measure");
  assert.equal(matrix.cell("c", "v"), 1, "through two measures");
  assert.equal(matrix.cell("c2", "v2"), 1, "through a page filter");
  assert.equal(matrix.cell("unused", "v"), 0);
  assert.deepEqual(matrix.usage.get("unused"), { direct: 0, indirect: 0 });
  assert.equal(matrix.bound("m", "r"), true);
  assert.equal(matrix.bound("m2", "r"), false);
  assert.deepEqual(matrix.rowGroups.map((group) => group.model.id), ["m", "m2"]);
  assert.deepEqual(matrix.colGroups[0].pages[0].visuals.map((visual) => visual.id), ["v", "v2"]);
});

test("lanes widen to their longest name and wrap longer names to two lines", () => {
  const long = { ...node("long", "MEASURE"), name: "x".repeat(60) };
  const wide = { ...node("wide", "COLUMN"), name: "y".repeat(25) };
  const layout = layoutLineage([...nodes, long, wide], edges, "LR", { measure: (text) => text.length * 7 });
  const item = (id) => layout.nodes.find((entry) => entry.node.id === id);
  assert.equal(item("long").width, MAX_LANE_WIDTH, "a lane never grows past the maximum");
  assert.equal(item("long").lines, 2);
  assert.equal(item("long").height, TWO_LINE_HEIGHT);
  assert.equal(item("x").lines, 1, "short names stay on one line in a wide lane");
  assert.ok(item("wide").width > 168 && item("wide").width < MAX_LANE_WIDTH, "the column lane fits its longest name");
  assert.ok(item("long").position.x >= item("wide").position.x + item("wide").width, "lanes do not overlap");
});

test("switching a lane off bridges the chains that ran through it", () => {
  const { nodes: shown, edges: links } = hideLanes(nodes, edges, ["calc"]);
  assert.ok(!shown.some((item) => LANES[laneOf(item)].key === "calc"));
  const through = links.filter((link) => link.type === THROUGH).map((link) => `${link.from_id}>${link.to_id}`);
  assert.ok(through.includes("c>v"), "column c reaches visual v through measures x and y");
  assert.ok(!through.includes("c2>v"), "no link where no chain existed");
  const trace = lineageOf("c", layoutLineage(shown, links).edges);
  assert.ok(trace.downstream.has("v") && trace.downstream.has("r"), "the trace still runs to the report");
});

// Two versions of one model and one report; v2 adds a measure and changes a visual.
const versionNodes = [
  node("m1", "MODEL", { name: "Sales" }), node("m1/t", "TABLE", { name: "Sales", model_id: "m1" }),
  node("m1/c", "COLUMN", { name: "Amount", model_id: "m1", table_id: "m1/t", source_hash: "a" }),
  node("m2", "MODEL", { name: "Sales v2" }), node("m2/t", "TABLE", { name: "Sales", model_id: "m2" }),
  node("m2/c", "COLUMN", { name: "Amount", model_id: "m2", table_id: "m2/t", source_hash: "a" }),
  node("m2/x", "MEASURE", { name: "Margin", model_id: "m2", table_id: "m2/t" }),
  node("r1", "REPORT", { name: "Sales report" }), node("r1/p", "PAGE", { name: "Overview", report_id: "r1", parent_id: "r1", source_id: "p01" }),
  node("r1/v", "VISUAL", { name: "Chart", report_id: "r1", parent_id: "r1/p", source_id: "v01", source_hash: "1" }),
  node("r2", "REPORT", { name: "Sales report v2" }), node("r2/p", "PAGE", { name: "Overview (new)", report_id: "r2", parent_id: "r2", source_id: "p01" }),
  node("r2/v", "VISUAL", { name: "Chart", report_id: "r2", parent_id: "r2/p", source_id: "v01", source_hash: "2" }),
];
const versionEdges = [
  edge("m1", "CONTAINS", "m1/t"), edge("m1/t", "CONTAINS", "m1/c"), edge("m2", "CONTAINS", "m2/t"), edge("m2/t", "CONTAINS", "m2/c"), edge("m2/t", "CONTAINS", "m2/x"),
  edge("r1", "CONTAINS", "r1/p"), edge("r1/p", "CONTAINS", "r1/v"), edge("r1/v", "USES", "m1/c"), edge("r1", "USES_MODEL", "m1"),
  edge("r2", "CONTAINS", "r2/p"), edge("r2/p", "CONTAINS", "r2/v"), edge("r2/v", "USES", "m2/x"), edge("r2/v", "USES", "m2/c"), edge("r2", "USES_MODEL", "m2"),
];

test("versions of a model and of a report are found by matching objects, and fold into one node each", () => {
  const { families } = versionFamilies(versionNodes);
  assert.deepEqual([...families.values()].map((members) => members.map((member) => member.id).sort()).sort(), [["m1", "m2"], ["r1", "r2"]]);
  const grouped = groupVersions(versionNodes, versionEdges);
  assert.ok(grouped.grouped);
  const byId = new Map(grouped.nodes.map((item) => [item.id, item]));
  assert.equal(grouped.nodes.length, 7, "model, table, column, measure, report, page, visual");
  assert.equal(byId.get("m1/c").versionCount, 2);
  assert.equal(byId.get("m1/c").differs, false);
  assert.equal(byId.get("r1/p").versionCount, 2, "pages match by page ID even when renamed");
  assert.equal(byId.get("r1/v").differs, true, "the visual changed between versions");
  assert.equal(byId.get("m2/x").versionCount, 1);
  assert.equal(byId.get("m2/x").familySize, 2, "the new measure is only in one of two versions");
  assert.ok(grouped.edges.some((link) => link.from_id === "r1/v" && link.to_id === "m2/x"), "links are re-pointed to folded nodes");
  const matrix = buildImpactMatrix(grouped.nodes, grouped.edges);
  assert.equal(matrix.cell("m1/c", "r1/v"), 2);
  assert.equal(matrix.cell("m2/x", "r1/v"), 2);
  assert.ok(matrix.bound("m1", "r1"));
});

test("matrix filter lanes switch off what filters count", () => {
  assert.equal(buildImpactMatrix(nodes, edges).cell("c2", "v"), 1);
  assert.equal(buildImpactMatrix(nodes, edges, { pageFilters: false }).cell("c2", "v"), 0);
});

// Issue #10: data sources and queries upstream of tables.
test("lineage traces a visual back to the data source its table's partition reads", () => {
  const sourced = [
    node("m", "MODEL"), node("e", "SHARED_EXPRESSION"), node("srv", "SHARED_EXPRESSION"), node("lake", "DATA_SOURCE"), node("sql", "DATA_SOURCE"),
    node("part", "PARTITION"), node("t", "TABLE"), node("c", "COLUMN"), node("x", "MEASURE"), node("v", "VISUAL"),
    node("t2", "TABLE"), node("part2", "PARTITION"), node("c2", "COLUMN"),
  ];
  const links = [
    edge("m", "CONTAINS", "e"), edge("m", "CONTAINS", "srv"), edge("m", "CONTAINS", "t"), edge("m", "CONTAINS", "t2"),
    edge("e", "SOURCES_FROM", "lake"), edge("part", "SOURCES_FROM", "sql"), edge("part", "REFERENCES", "srv"),
    edge("t", "CONTAINS", "part"), edge("t", "CONTAINS", "c"), edge("x", "REFERENCES", "c"), edge("v", "USES", "x"),
    edge("t2", "CONTAINS", "part2"), edge("part2", "REFERENCES", "e"), edge("t2", "CONTAINS", "c2"),
  ];
  assert.equal(LANES[laneOf({ type: "DATA_SOURCE" })].key, "source");
  assert.equal(LANES[laneOf({ type: "PARTITION" })].key, "query");
  const layout = layoutLineage(sourced, links);
  const x = (id) => layout.nodes.find((item) => item.node.id === id).position.x;
  assert.deepEqual(layout.lanes.map((lane) => lane.key), ["model", "source", "query", "table", "column", "calc", "visual"]);
  layout.edges.forEach(({ from, to }) => assert.ok(x(from) <= x(to), `${from} → ${to}`));
  const { upstream } = lineageOf("v", layout.edges);
  for (const id of ["sql", "part", "srv", "t", "c", "x"]) assert.ok(upstream.has(id), id);
  // The lakehouse feeds the other table only: the model does not pass it on to every table.
  assert.ok(!upstream.has("lake"));
  assert.ok(lineageOf("c2", layout.edges).upstream.has("lake"));
  // Hiding the Queries lane bridges source → table.
  const hidden = hideLanes(sourced, links, ["query"]);
  assert.ok(hidden.edges.some((item) => item.type === THROUGH && [item.from_id, item.to_id].includes("sql") && [item.from_id, item.to_id].includes("t")));
});
