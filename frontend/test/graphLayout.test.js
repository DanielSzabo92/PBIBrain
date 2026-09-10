import assert from "node:assert/strict";
import test from "node:test";
import { layoutGraph, routePath, NODE_WIDTH, NODE_HEIGHT } from "../src/graphLayout.js";

const nodes = ["visual", "measure", "column", "isolated"].map((id) => ({ id }));
const edges = [
  { id: "uses", from_id: "visual", to_id: "measure" },
  { id: "depends", from_id: "measure", to_id: "column" },
];

test("dependency chains flow left to right without overlapping nodes", () => {
  const layout = layoutGraph(nodes, edges);
  const positions = new Map(layout.nodes.map(({ node, position }) => [node.id, position]));
  for (const edge of edges) assert.ok(positions.get(edge.from_id).x + NODE_WIDTH < positions.get(edge.to_id).x);
  for (let i = 0; i < layout.nodes.length; i++) for (let j = i + 1; j < layout.nodes.length; j++) {
    const a = layout.nodes[i].position, b = layout.nodes[j].position;
    assert.ok(Math.abs(a.x - b.x) >= NODE_WIDTH || Math.abs(a.y - b.y) >= NODE_HEIGHT);
  }
  assert.deepEqual(layoutGraph([...nodes].reverse(), [...edges].reverse()), layout);
});

test("cycles, self loops, parallel edges and disconnected objects remain finite", () => {
  const allEdges = [...edges,
    { id: "parallel", from_id: "visual", to_id: "measure" },
    { id: "cycle", from_id: "column", to_id: "visual" },
    { id: "self", from_id: "measure", to_id: "measure" },
    { id: "missing", from_id: "absent", to_id: "measure" },
  ];
  const original = structuredClone({ nodes, allEdges });
  const result = layoutGraph(nodes, allEdges);
  assert.equal(result.nodes.length, nodes.length);
  assert.equal(result.edges.length, allEdges.length - 1);
  for (const { edge, points } of result.edges) {
    assert.deepEqual(edge, allEdges.find((item) => item.id === edge.id));
    assert.ok(points.length >= 2);
    assert.ok(points.every((p) => Number.isFinite(p.x) && Number.isFinite(p.y)));
    assert.ok(!/NaN|undefined/.test(routePath(points)));
  }
  assert.deepEqual({ nodes, allEdges }, original);
  assert.notDeepEqual(result.edges.find((e) => e.edge.id === "uses").points, result.edges.find((e) => e.edge.id === "parallel").points);
});

test("empty and single-object scopes are safe", () => {
  assert.deepEqual(layoutGraph([], []), { nodes: [], edges: [] });
  assert.equal(layoutGraph([{ id: "only" }], []).nodes.length, 1);
  assert.equal(routePath([]), "");
});
