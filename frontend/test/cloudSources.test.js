import assert from "node:assert/strict";
import test from "node:test";
import { layoutLineage } from "../src/lineage.js";
import { buildImpactMatrix } from "../src/matrix.js";
import { originNote } from "../src/presentation.js";

const node = (id, type, extra = {}) => ({ id, type, name: id, status: "factual", ...extra });
const edge = (from_id, type, to_id) => ({ id: `${from_id}-${type}-${to_id}`, from_id, type, to_id });

// One local model and two cloud models in one workspace; the workspace node owns its cloud roots (issue #9).
const cloud = { origin: "cloud", workspace_name: "Sales Analytics" };
const nodes = [
  node("ws", "WORKSPACE"),
  node("local", "MODEL", { name: "Zeta local" }), node("lt", "TABLE"), node("lc", "COLUMN"),
  node("cloudA", "MODEL", { name: "Alpha cloud", ...cloud }), node("at", "TABLE"), node("ac", "COLUMN"),
  node("cloudB", "MODEL", { name: "Beta cloud", ...cloud }), node("bt", "TABLE"), node("bc", "COLUMN"),
];
const edges = [
  edge("local", "CONTAINS", "lt"), edge("lt", "CONTAINS", "lc"),
  edge("ws", "CONTAINS", "cloudA"), edge("cloudA", "CONTAINS", "at"), edge("at", "CONTAINS", "ac"),
  edge("ws", "CONTAINS", "cloudB"), edge("cloudB", "CONTAINS", "bt"), edge("bt", "CONTAINS", "bc"),
];

test("the matrix keeps local models first, then each cloud workspace together", () => {
  const matrix = buildImpactMatrix(nodes, edges);
  assert.deepEqual(matrix.rowGroups.map((group) => group.model.id), ["local", "cloudA", "cloudB"]);
});

test("lineage puts the workspace in the model lane and keeps its models in one block", () => {
  const layout = layoutLineage(nodes, edges);
  const placed = (id) => layout.nodes.find((item) => item.node.id === id);
  assert.equal(placed("ws").position.x, placed("cloudA").position.x, "workspace shares the model lane");
  const ys = ["local", "cloudA", "cloudB"].map((id) => placed(id).position.y);
  // The two cloud models are neighbours: the local model is not between them.
  assert.ok(!(Math.min(ys[1], ys[2]) < ys[0] && ys[0] < Math.max(ys[1], ys[2])));
});

test("origin notes name the workspace or say why a root was not checked", () => {
  assert.equal(originNote(node("x", "MODEL")), null);
  assert.deepEqual(originNote(node("x", "MODEL", cloud)), { kind: "cloud", label: "Sales Analytics", title: "Cloud · workspace Sales Analytics" });
  const missing = originNote(node("x", "MODEL", { properties: { check_status: "not_checked", not_checked_reason: "model_not_in_project" } }));
  assert.equal(missing.label, "Not checked");
  assert.match(missing.title, /not a source of this project/);
});
