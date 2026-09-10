import assert from "node:assert/strict";
import test from "node:test";
import { artifactGroup, artifactColor, normalizeColors } from "../src/graphPresentation.js";
import { layoutArtifactGraph, routePath, NODE_WIDTH, NODE_HEIGHT } from "../src/graphLayout.js";

const nodes = [
  { id: "report", type: "REPORT", model_id: "model", report_id: "report" },
  { id: "page", type: "PAGE", model_id: "model", report_id: "report" },
  { id: "visual", type: "VISUAL", model_id: "model", report_id: "report" },
  { id: "model", type: "MODEL" },
  { id: "table", type: "TABLE", model_id: "model" },
  { id: "measure", type: "MEASURE", model_id: "model" },
  { id: "other", type: "WORKSPACE" },
];
const edges = [
  { id: "report-page", from_id: "report", to_id: "page" },
  { id: "page-visual", from_id: "page", to_id: "visual" },
  { id: "visual-measure", from_id: "visual", to_id: "measure" },
  { id: "model-table", from_id: "model", to_id: "table" },
  { id: "table-measure", from_id: "table", to_id: "measure" },
];

test("report artifacts with both ownership IDs stay in the report group", () => {
  for (const node of nodes.slice(0, 3)) assert.equal(artifactGroup(node), "report");
  assert.equal(artifactGroup({ type: "FUTURE_VISUAL", report_id: "r", model_id: "m" }), "report");
  assert.equal(artifactGroup({ type: "MEASURE", report_id: "r", model_id: "m" }), "model");
  assert.equal(artifactGroup({ type: "FUTURE_OBJECT" }), "other");
  assert.equal(artifactGroup({ type: "ALIAS", model_id: "m" }), "other");
});

test("status never overrides artifact colors and reset restores group inheritance", () => {
  const colors = normalizeColors({ groups: { model: "#112233" }, types: { MEASURE: "#AABBCC" } });
  for (const status of ["factual", "candidate", "approved", "rejected", "overridden"]) {
    assert.equal(artifactColor({ type: "MEASURE", status }, colors), "#aabbcc");
    assert.equal(artifactColor({ type: "TABLE", status }, colors), "#112233");
  }
  delete colors.types.MEASURE;
  assert.equal(artifactColor({ type: "MEASURE" }, colors), "#112233");
  assert.deepEqual(normalizeColors({ groups: { model: "red", bad: "#ffffff" }, types: { MEASURE: "url(x)", __proto__: "#ffffff" } }), normalizeColors());
});

for (const direction of ["LR", "TB"]) {
  test(`artifact regions are disjoint and contain their nodes (${direction})`, () => {
    const original = structuredClone({ nodes, edges });
    const result = layoutArtifactGraph(nodes, edges, direction);
    assert.deepEqual({ nodes, edges }, original);
    assert.deepEqual(layoutArtifactGraph([...nodes].reverse(), [...edges].reverse(), direction), result);
    assert.equal(result.nodes.length, nodes.length);
    assert.equal(result.edges.length, edges.length);
    for (const group of result.groups) {
      assert.ok(Number.isFinite(group.width) && group.width > 0);
      for (const item of result.nodes.filter(({ node }) => artifactGroup(node) === group.key)) {
        assert.ok(item.position.x >= group.position.x);
        assert.ok(item.position.y >= group.position.y + 28, "group label has reserved space");
        assert.ok(item.position.x + NODE_WIDTH <= group.position.x + group.width);
        assert.ok(item.position.y + NODE_HEIGHT <= group.position.y + group.height);
      }
    }
    for (let i = 0; i < result.groups.length; i++) for (let j = i + 1; j < result.groups.length; j++) {
      const a = result.groups[i], b = result.groups[j];
      assert.ok(a.position.x + a.width <= b.position.x || b.position.x + b.width <= a.position.x || a.position.y + a.height <= b.position.y || b.position.y + b.height <= a.position.y);
    }
    assert.ok(result.edges.every(({ points }) => points.every(({ x, y }) => Number.isFinite(x) && Number.isFinite(y))));
  });
}

test("grouped layout preserves cycles, parallel edges, self-loops, unknown nodes and ID collisions", () => {
  const complexNodes = [...nodes, { id: "__pbibrain_group_report", type: "NEW_OBJECT" }];
  const complexEdges = [...edges, { id: "parallel", from_id: "visual", to_id: "measure" }, { id: "cycle", from_id: "measure", to_id: "visual" }, { id: "self", from_id: "measure", to_id: "measure" }, { id: "missing", from_id: "gone", to_id: "measure" }];
  for (const direction of ["LR", "TB"]) {
    const result = layoutArtifactGraph(complexNodes, complexEdges, direction);
    assert.equal(result.nodes.length, complexNodes.length);
    assert.equal(result.edges.length, complexEdges.length - 1);
    assert.equal(new Set([...result.nodes.map(({ node }) => node.id), ...result.groups.map(({ id }) => id)]).size, result.nodes.length + result.groups.length);
    for (const { points } of result.edges) assert.ok(!/NaN|undefined|Infinity/.test(routePath(points)));
    assert.notDeepEqual(result.edges.find(({ edge }) => edge.id === "parallel").points, result.edges.find(({ edge }) => edge.id === "visual-measure").points);
  }
  assert.deepEqual(layoutArtifactGraph([], []), { nodes: [], edges: [], groups: [] });
  assert.equal(layoutArtifactGraph([{ id: "only", type: "MEASURE" }], []).nodes.length, 1);
});
