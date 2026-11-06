// Unit tests of the U8 Impact helpers (UI design 4.5, 5.3, 7.3, 8.4).
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  GRAPH_LIMIT,
  buildImpactGraph,
  canConfirmPolicy,
  completenessDefaultOpen,
  completenessEntries,
  completenessState,
  defaultGroup,
  graphKeyTarget,
  graphNodeLabel,
  graphTabOrder,
  impactQuery,
  isProposed,
  itemStatus,
  menuActions,
  missingFieldCount,
  offerTree,
  pageCheckState,
  pageToggleTargets,
  pagesFor,
  policyConfirm,
  primaryAction,
  proposalTargets,
  readingOrder,
  reportOptions,
  resolvedText,
  sortItems,
  virtualWindow,
  visibleEntries,
  wireVisualLabel,
} from "../src/devcenter/screens/impact/impactModel.js";

const fixture = async (name) => JSON.parse(await readFile(new URL(`../../tests/fixtures/devcenter_ui/${name}`, import.meta.url), "utf-8"));

test("status rule: blocking flag, information for mapped and not changed, warning for all others; possible never blocks", () => {
  assert.equal(itemStatus({ blocking: true, certainty: "certain", severity: "breaks" }), "blocking");
  assert.equal(itemStatus({ blocking: true, certainty: "possible", severity: "breaks" }), "warning");
  assert.equal(itemStatus({ blocking: false, certainty: "certain", severity: "mapped" }), "information");
  assert.equal(itemStatus({ blocking: false, certainty: "certain", severity: "not_changed_by_this_plan" }), "information");
  assert.equal(itemStatus({ blocking: false, certainty: "certain", severity: "changes_value" }), "warning");
});

test("primary action is the first allowed of the design order; the menu has the other allowed actions", () => {
  const policy = { allowed_actions: ["set_policy_block", "set_policy_cascade", "set_policy_repoint", "remove_field"] };
  assert.equal(primaryAction(policy), "set_policy_repoint");
  assert.deepEqual(menuActions(policy), ["set_policy_block", "set_policy_cascade", "remove_field"]);
  assert.equal(primaryAction({ allowed_actions: ["remove_field", "include_in_rewrite"] }), "include_in_rewrite");
  assert.equal(primaryAction({ allowed_actions: ["add_from_donor", "map_to_target", "drop_added_object"] }), "map_to_target");
  assert.equal(primaryAction({ allowed_actions: ["remove_field"] }), null);
  assert.deepEqual(menuActions({ allowed_actions: ["remove_field"] }), ["remove_field"]);
});

test("sort: blocking first, then severity, then name", async () => {
  const { items } = await fixture("default/impact.json");
  const sorted = sortItems(items.filter((item) => item.direction === "breaks"));
  assert.deepEqual(sorted.map((item) => item.id), ["imp-b02", "imp-b03", "imp-b04", "imp-b01", "imp-b05", "imp-b06", "imp-b07"]);
});

test("default group is the first group with blocking items, else Breaks", () => {
  assert.equal(defaultGroup({ breaks: 2, needs: 1 }), "breaks");
  assert.equal(defaultGroup({ breaks: 0, needs: 1 }), "needs");
  assert.equal(defaultGroup({ breaks: 0, needs: 0 }), "breaks");
  assert.equal(defaultGroup(undefined), "breaks");
});

test("the query keeps scope, group, proposals, and each filter", () => {
  assert.deepEqual(
    impactQuery({ scope: "row-budget", group: "needs", includeProposals: true, filters: { blockingOnly: true, severity: "missing", certainty: "all", source: "src-2", type: "column", q: "Region" } }),
    { target: "row-budget", includeProposals: true, direction: "needs", blocking: true, severity: "missing", source: "src-2", objectType: "column", q: "Region" },
  );
  assert.deepEqual(impactQuery({ scope: "plan", group: "breaks", filters: {} }), { target: "plan", direction: "breaks" });
});

test("the toast gives the resolved count and the blocking count", () => {
  assert.equal(resolvedText(1, 3), "1 item resolved. 3 blocking left.");
  assert.equal(resolvedText(2, 0), "2 items resolved. 0 blocking left.");
  assert.equal(resolvedText(1, 2, 1), "1 item resolved. 2 blocking left. 1 item cannot use this action.");
});

test("a proposed item is an item of a row with an open proposal while the switch is on", async () => {
  const session = await fixture("default/session.json");
  const targets = proposalTargets(session);
  assert.equal(isProposed({ cause: "row-net-sales" }, true, targets), true);
  assert.equal(isProposed({ cause: "row-net-sales" }, false, targets), false);
  assert.equal(isProposed({ cause: "row-budget" }, true, targets), false);
});

test("completeness strip: entries of each area, 20 at a time, default open only when incomplete and not closed", async () => {
  const { completeness } = await fixture("default/impact.json");
  const state = completenessState(completeness);
  assert.equal(state.label, "Incomplete: 3 areas");
  assert.equal(state.tone, "warn");
  assert.deepEqual(completenessEntries(completeness).map((entry) => entry.label), [
    "Not checked object types", "Unresolved bindings", "Bookmarks that refer to a changed object",
  ]);
  assert.equal(completenessDefaultOpen(completeness, false), true);
  assert.equal(completenessDefaultOpen(completeness, true), false);
  assert.equal(completenessDefaultOpen({ status: "complete" }, false), false);
  assert.equal(completenessState({ status: "complete" }).label, "Complete");
  const many = Array.from({ length: 45 }, (_, index) => ({ text: `e${index}` }));
  assert.deepEqual([visibleEntries(many, 20).list.length, visibleEntries(many, 20).more], [20, true]);
  assert.deepEqual([visibleEntries(many, 40).list.length, visibleEntries(many, 60).more], [40, false]);
});

test("graph: union of shortest paths, rank order, arrows along edges, solid or dashed edges, and node names (A12)", async () => {
  const { items } = await fixture("default/impact.json");
  const breaks = items.filter((item) => item.direction === "breaks");
  const graph = buildImpactGraph(breaks);
  const budget = graph.nodes.find((node) => node.id === "table:Budget");
  assert.equal(budget.rank, 0);
  assert.equal(graph.nodes.filter((node) => node.id === "visual:Overview/Sales by region").length, 1);
  const slicerEdge = graph.edges.find((edge) => edge.to_id === "visual:Details/Region slicer");
  assert.equal(slicerEdge.certain, false);
  assert.equal(graph.edges.find((edge) => edge.from_id === "table:Budget" && edge.to_id === "measure:Budget/Budget Amount").certain, true);
  const placed = graph.nodes.map((node, index) => ({ node, position: { x: node.rank * 300, y: index * 100 } }));
  const ordered = graphTabOrder(placed);
  assert.deepEqual([...new Set(ordered.map((entry) => entry.node.rank))], [0, 1, 2]);
  assert.equal(graphKeyTarget(graph, ordered, "table:Budget", "ArrowRight"), ordered.find((entry) => graph.edges.some((edge) => edge.from_id === "table:Budget" && edge.to_id === entry.node.id)).node.id);
  assert.equal(graphKeyTarget(graph, ordered, "measure:Budget/Budget Amount", "ArrowLeft"), "table:Budget");
  const rank0 = ordered.filter((entry) => entry.node.rank === 0).map((entry) => entry.node.id);
  assert.equal(graphKeyTarget(graph, ordered, rank0[0], "ArrowDown"), rank0[1]);
  assert.equal(graphKeyTarget(graph, ordered, rank0[1], "ArrowUp"), rank0[0]);
  const sales = graph.nodes.find((node) => node.id === "visual:Overview/Sales by region");
  assert.equal(graphNodeLabel(sales), "visual Sales by region, Blocking, breaks, 2 steps from the change");
  assert.equal(GRAPH_LIMIT, 150);
});

test("wireframe: reading order, the visual name, and the report trigger", async () => {
  const wireframe = await fixture("default/wireframe.json");
  const order = readingOrder(wireframe.pages[0].visuals).map((visual) => visual.title);
  assert.deepEqual(order, ["Sales by region", "Margin trend", "Budget gauge", "Net sales card", "Target card", "Custom map"]);
  assert.equal(wireVisualLabel(wireframe.pages[0].visuals[2]), "gauge Budget gauge, Removed");
  const session = await fixture("default/session.json");
  assert.deepEqual(reportOptions(session, "Combined report").map((option) => option.label), [
    "Combined report (target, after apply)", "Sales model (donor, now)", "Finance model (donor, now)",
  ]);
});

test("offers: tree by donor and page, mixed page state, toggle targets, and the Needs count", async () => {
  const { offers } = await fixture("default/impact.json");
  const tree = offerTree(offers);
  assert.deepEqual(tree.map((donor) => donor.sourceName), ["Sales model", "Finance model"]);
  assert.deepEqual(tree[0].pages[0].items.map((offer) => offer.name), ["Top products", "Sales map", "Year filter"]);
  assert.deepEqual(tree[1].bookmarks.map((offer) => offer.name), ["Year end"]);
  const items = tree[0].pages[0].items;
  assert.equal(pageCheckState(items), false);
  const mixed = items.map((offer, index) => ({ ...offer, selected: index === 0 }));
  assert.equal(pageCheckState(mixed), "indeterminate");
  assert.equal(pageCheckState(items.map((offer) => ({ ...offer, selected: true }))), true);
  assert.deepEqual(pageToggleTargets(mixed, true).map((offer) => offer.name), ["Sales map", "Year filter"]);
  assert.deepEqual(pageToggleTargets(mixed, false).map((offer) => offer.name), ["Top products"]);
  assert.equal(missingFieldCount(mixed), 1);
  assert.equal(missingFieldCount(offers.map((offer) => ({ ...offer, selected: true }))), 3);
});

test("removal policy confirm texts and the Repoint rule (UI design 8.4)", () => {
  assert.deepEqual(policyConfirm("block", 3), { text: "Use Block", variant: "default" });
  assert.deepEqual(policyConfirm("cascade", 3), { text: "Use Cascade (remove 3 objects)", variant: "destructive" });
  assert.deepEqual(policyConfirm("repoint", 3), { text: "Use Repoint", variant: "default" });
  assert.equal(canConfirmPolicy("repoint", ""), false);
  assert.equal(canConfirmPolicy("repoint", "table:Forecast"), true);
  assert.equal(canConfirmPolicy("cascade", ""), true);
});

test("virtual window keeps 80 rows or fewer in the DOM (budget P4) and asks for the right pages", () => {
  const view = virtualWindow({ scrollTop: 64 * 2400, height: 520, rowHeight: 64, total: 5000 });
  assert.ok(view.last - view.first <= 80);
  assert.deepEqual(pagesFor(view), [4]);
  assert.deepEqual(pagesFor({ first: 495, last: 510 }), [0, 1]);
  assert.deepEqual(pagesFor({ first: 0, last: 0 }), [0]);
});
