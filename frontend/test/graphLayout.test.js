import assert from "node:assert/strict";
import test from "node:test";
import {
  buildExplorerGraph,
  layoutExplorerGraph,
  layoutGraph,
  routePath,
  NODE_WIDTH,
  NODE_HEIGHT,
} from "../src/graphLayout.js";

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

test("explorer folds nested ownership and reports loaded descendants", () => {
  const explorerNodes = [
    { id: "model", name: "Model", type: "MODEL" },
    { id: "report", name: "Report", type: "REPORT" },
    { id: "table", name: "Sales", type: "TABLE" },
    { id: "column", name: "Amount", type: "COLUMN" },
    { id: "orphan", name: "Orphan", type: "MEASURE" },
  ];
  const explorerEdges = [
    { id: "model-report", type: "CONTAINS", from_id: "model", to_id: "report" },
    { id: "report-table", type: "CONTAINS", from_id: "report", to_id: "table" },
    { id: "table-column", type: "CONTAINS", from_id: "table", to_id: "column" },
    { id: "report-column-uses", type: "USES", from_id: "report", to_id: "column" },
  ];
  const collapsed = buildExplorerGraph(explorerNodes, explorerEdges);
  assert.deepEqual(collapsed.nodes.map((node) => node.id), ["model", "orphan"]);
  assert.equal(collapsed.hiddenCount, 3);
  assert.equal(collapsed.collapsedCount, 1);
  assert.equal(collapsed.nodes[0].explorerChildCount, 1);
  assert.equal(collapsed.nodes[0].explorerDescendantCount, 3);
  assert.deepEqual(collapsed.childrenById.get("model"), ["report"]);
  assert.equal(collapsed.edges.length, 0);

  const oneLevel = buildExplorerGraph(explorerNodes, explorerEdges, ["model"]);
  assert.deepEqual(oneLevel.nodes.map((node) => node.id), ["model", "orphan", "report"]);
  assert.equal(oneLevel.nodes.find((node) => node.id === "report").explorerParentId, "model");
  assert.equal(oneLevel.hiddenCount, 2);
  assert.equal(oneLevel.collapsedCount, 1);
  assert.equal(oneLevel.edges.length, 1);

  const expanded = buildExplorerGraph(explorerNodes, explorerEdges, ["model", "report", "table"]);
  assert.equal(expanded.hiddenCount, 0);
  assert.equal(expanded.collapsedCount, 0);
  assert.deepEqual(expanded.nodes.map((node) => node.id), ["column", "model", "orphan", "report", "table"]);
  assert.equal(expanded.edges.length, explorerEdges.length);
  assert.equal(expanded.nodes.find((node) => node.id === "table").explorerDescendantCount, 1);
  assert.equal(expanded.nodes.find((node) => node.id === "column").type, "COLUMN");
});

test("explorer chooses one safe owner for cycles and multiple ownership", () => {
  const nodes = [
    { id: "a", name: "A", type: "REPORT" },
    { id: "b", name: "B", type: "PAGE" },
    { id: "shared", name: "Shared", type: "TABLE" },
    { id: "orphan", name: "Orphan", type: "MEASURE" },
  ];
  const edges = [
    { id: "a-b", type: "CONTAINS", from_id: "a", to_id: "b" },
    { id: "b-a", type: "CONTAINS", from_id: "b", to_id: "a" },
    { id: "a-shared", type: "CONTAINS", from_id: "a", to_id: "shared" },
    { id: "b-shared", type: "CONTAINS", from_id: "b", to_id: "shared" },
    { id: "a-shared-uses", type: "USES", from_id: "a", to_id: "shared" },
  ];
  const result = buildExplorerGraph(nodes, edges, ["a", "b", "orphan"]);
  assert.equal(result.hiddenCount, 0);
  assert.equal(result.childrenById.get("a").filter((id) => id === "shared").length, 1);
  assert.equal(result.childrenById.get("b").filter((id) => id === "shared").length, 0);
  assert.equal(result.nodes.find((node) => node.id === "shared").explorerParentId, "a");
  assert.equal(result.edges.length, edges.length);
  assert.deepEqual(result.nodes.map((node) => node.id), ["a", "b", "orphan", "shared"]);
});

test("explorer layout uses ownership only and preserves canonical edge direction", () => {
  const nodes = [
    { id: "root", name: "Root", type: "MODEL" },
    { id: "child", name: "Child", type: "REPORT" },
    { id: "other", name: "Other", type: "MODEL" },
  ];
  const containment = [{ id: "contains", type: "CONTAINS", from_id: "root", to_id: "child" }];
  const crosslinks = [
    ...containment,
    { id: "back", type: "USES_MODEL", from_id: "child", to_id: "root" },
    { id: "parallel", type: "USES", from_id: "root", to_id: "child" },
    { id: "self", type: "REFERENCES", from_id: "child", to_id: "child" },
    { id: "other-link", type: "DEPENDS_ON", from_id: "other", to_id: "child" },
  ];
  const simple = layoutExplorerGraph(nodes, containment);
  const layout = layoutExplorerGraph([...nodes].reverse(), [...crosslinks].reverse());
  assert.deepEqual(layout.nodes, layoutExplorerGraph(nodes, crosslinks).nodes);
  assert.deepEqual(layout.nodes.map(({ node }) => node.id), ["child", "other", "root"]);
  const positions = new Map(layout.nodes.map(({ node, position }) => [node.id, position]));
  for (let i = 0; i < layout.nodes.length; i += 1) for (let j = i + 1; j < layout.nodes.length; j += 1) {
    const a = layout.nodes[i].position, b = layout.nodes[j].position;
    assert.ok(Math.abs(a.x - b.x) >= NODE_WIDTH || Math.abs(a.y - b.y) >= NODE_HEIGHT);
  }
  for (const { edge, points } of layout.edges) {
    assert.ok(points.length >= 2);
    assert.ok(points.every((point) => Number.isFinite(point.x) && Number.isFinite(point.y)));
    assert.ok(!/NaN|undefined/.test(routePath(points)));
    assert.deepEqual(edge, crosslinks.find((candidate) => candidate.id === edge.id));
  }
  const backwards = layout.edges.find(({ edge }) => edge.id === "back");
  const root = positions.get("root");
  const child = positions.get("child");
  assert.ok(backwards.points[0].x >= child.x);
  assert.ok(backwards.points.at(-1).x <= root.x + NODE_WIDTH);
  assert.deepEqual(simple.nodes.map(({ node }) => node.id), layout.nodes.map(({ node }) => node.id));
  assert.deepEqual(simple.nodes.map(({ position }) => position), layout.nodes.map(({ position }) => position));
});

test("explorer layout anchors surviving nodes while expanding without overlap", () => {
  const nodes = [
    { id: "model", name: "Model", type: "MODEL" },
    { id: "report", name: "Report", type: "REPORT" },
    { id: "table", name: "Sales", type: "TABLE" },
    { id: "column", name: "Amount", type: "COLUMN" },
    { id: "orphan", name: "Orphan", type: "MEASURE" },
  ];
  const edges = [
    { id: "model-report", type: "CONTAINS", from_id: "model", to_id: "report" },
    { id: "report-table", type: "CONTAINS", from_id: "report", to_id: "table" },
    { id: "table-column", type: "CONTAINS", from_id: "table", to_id: "column" },
    { id: "uses", type: "USES", from_id: "report", to_id: "column" },
  ];
  const collapsed = buildExplorerGraph(nodes, edges);
  const expanded = buildExplorerGraph(nodes, edges, ["model", "report", "table"]);
  for (const direction of ["LR", "TB"]) {
    const first = layoutExplorerGraph(collapsed.nodes, collapsed.edges, direction);
    const previous = new Map(first.nodes.map(({ node, position }) => [node.id, position]));
    const second = layoutExplorerGraph(expanded.nodes, expanded.edges, direction, previous);
    const raw = layoutExplorerGraph(expanded.nodes, expanded.edges, direction);
    const rawPositions = new Map(raw.nodes.map(({ node, position }) => [node.id, position]));
    const rank = direction === "LR" ? "x" : "y";
    const before = new Map(first.nodes.map(({ node, position }) => [node.id, position]));
    for (const { node, position } of second.nodes) {
      if (before.has(node.id)) assert.deepEqual(position, before.get(node.id));
      else assert.equal(position[rank], rawPositions.get(node.id)[rank]);
    }
    for (let i = 0; i < second.nodes.length; i += 1) for (let j = i + 1; j < second.nodes.length; j += 1) {
      const a = second.nodes[i].position, b = second.nodes[j].position;
      assert.ok(Math.abs(a.x - b.x) >= NODE_WIDTH || Math.abs(a.y - b.y) >= NODE_HEIGHT);
    }
    const positions = new Map(second.nodes.map(({ node, position }) => [node.id, position]));
    const onBoundary = (point, position) => {
      const inX = point.x >= position.x - 1e-6 && point.x <= position.x + NODE_WIDTH + 1e-6;
      const inY = point.y >= position.y - 1e-6 && point.y <= position.y + NODE_HEIGHT + 1e-6;
      const boundary = Math.abs(point.x - position.x) < 1e-6
        || Math.abs(point.x - (position.x + NODE_WIDTH)) < 1e-6
        || Math.abs(point.y - position.y) < 1e-6
        || Math.abs(point.y - (position.y + NODE_HEIGHT)) < 1e-6;
      return inX && inY && boundary;
    };
    for (const { edge, points } of second.edges) {
      assert.ok(onBoundary(points[0], positions.get(edge.from_id)));
      assert.ok(onBoundary(points.at(-1), positions.get(edge.to_id)));
    }
  }
});

test("explorer ranks models before reports without changing USES_MODEL facts", () => {
  const nodes = [
    { id: "model", name: "Model", type: "MODEL" },
    { id: "report", name: "Report", type: "REPORT" },
    { id: "page", name: "Page", type: "PAGE" },
  ];
  const edges = [
    { id: "report-model", type: "USES_MODEL", from_id: "report", to_id: "model" },
    { id: "report-page", type: "CONTAINS", from_id: "report", to_id: "page" },
  ];
  const collapsed = buildExplorerGraph(nodes, edges);
  assert.equal(collapsed.nodes.find((node) => node.id === "model").explorerChildCount, 0);
  assert.equal(collapsed.nodes.find((node) => node.id === "report").explorerChildCount, 1);
  const expanded = buildExplorerGraph(nodes, edges, ["report"]);
  assert.deepEqual(expanded.nodes.map((node) => node.id), ["model", "page", "report"]);
  assert.equal(expanded.nodes.find((node) => node.id === "report").explorerDescendantCount, 1);
  const layout = layoutExplorerGraph(expanded.nodes, expanded.edges);
  const positions = new Map(layout.nodes.map(({ node, position }) => [node.id, position]));
  assert.ok(positions.get("model").x < positions.get("report").x);
  assert.ok(positions.get("report").x < positions.get("page").x);
  const scope = layout.edges.find(({ edge }) => edge.id === "report-model");
  assert.equal(scope.edge.from_id, "report");
  assert.equal(scope.edge.to_id, "model");
  assert.ok(scope.points[0].x >= positions.get("report").x);
  assert.ok(scope.points.at(-1).x <= positions.get("model").x + NODE_WIDTH);
});
