import assert from "node:assert/strict";
import test from "node:test";
import { layoutLineage, lineageOf, laneOf, LANES } from "../src/lineage.js";
import { buildImpactMatrix } from "../src/matrix.js";

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
