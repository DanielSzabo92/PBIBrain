import test from "node:test";
import assert from "node:assert/strict";
import { layoutGraph, layoutArtifactGraph } from "../src/graphLayout.js";
import { objectName, visualType, suggestionLabel } from "../src/presentation.js";

test("model precedes report, page, visual and bound field without reversing canonical arrows", () => {
  const nodes = ["MODEL", "REPORT", "PAGE", "VISUAL", "MEASURE"].map((type, index) => ({ id: String(index), name: type, type }));
  const edges = nodes.slice(1).map((node, index) => ({ id: `edge-${index}`, type: index === 3 ? "USES" : "CONTAINS", from_id: String(index), to_id: node.id }));
  edges.push({ id: "uses-model", type: "USES_MODEL", from_id: "1", to_id: "0" });
  const original = JSON.stringify(edges);
  for (const layout of [layoutGraph, layoutArtifactGraph]) for (const direction of ["LR", "TB"]) {
    const result = layout(nodes, edges, direction);
    const axis = direction === "LR" ? "x" : "y";
    const positions = new Map(result.nodes.map(({ node, position }) => [node.id, position[axis]]));
    for (let index = 0; index < 4; index++) assert.ok(positions.get(String(index)) < positions.get(String(index + 1)));
    const back = result.edges.find(({ edge }) => edge.id === "uses-model");
    assert.ok(back.points[0][axis] > back.points.at(-1)[axis]);
  }
  assert.equal(JSON.stringify(edges), original);
});

test("visual titles and types are readable; an opaque ID is the final fallback", () => {
  const node = { type: "VISUAL", name: "1234567890abcdef1234", properties: { title: "Revenue trend", visual_type: "lineChart" } };
  assert.equal(objectName(node), "Revenue trend");
  assert.equal(visualType(node), "Line Chart");
  delete node.properties.title;
  assert.equal(objectName(node), "Line Chart");
  delete node.properties.visual_type;
  assert.equal(objectName(node), node.name);
  assert.equal(suggestionLabel({ assertion_type: "ALIAS", value: "Revenue" }), "Alias: Revenue");
  assert.equal(suggestionLabel({ item: { properties: { assertion_type: "ROLE", meaning: "date" } } }), "Role: date");
});
