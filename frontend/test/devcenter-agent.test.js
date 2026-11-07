// Unit tests of the U9 Agent tab and Log tab helpers (UI design 4.7, 5.4).
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  acceptAllSummary,
  acceptSelectedToast,
  checkText,
  confidenceText,
  filterProposals,
  newProposalCount,
  optionEffect,
  proposalAction,
  proposalStatus,
  questionSections,
  readyProposals,
  statusText,
  visibleProposals,
} from "../src/devcenter/screens/agent/agentModel.js";
import { actionText, authorText, LOG_ACTIONS, logParams, targetRowKey, valueText } from "../src/devcenter/screens/log/logModel.js";

const bundle = async () =>
  JSON.parse(await readFile(new URL("../../tests/fixtures/devcenter_ui/default/agent-review.json", import.meta.url), "utf-8")).files;

test("the status, the status word, and the row action come from the blocked field", () => {
  assert.equal(proposalStatus({ blocked: null }), "ready");
  assert.equal(proposalStatus({ blocked: "source_changed" }), "source_changed");
  assert.equal(proposalStatus({ blocked: "user_choice_conflict" }), "user_choice_conflict");
  assert.deepEqual(["ready", "source_changed", "user_choice_conflict"].map(statusText), [
    "Ready to accept",
    "Confirm row first",
    "Conflicts with your choice",
  ]);
  assert.equal(proposalAction({ blocked: null }), "accept");
  assert.equal(proposalAction({ blocked: "user_choice_conflict" }), "replace");
  assert.equal(proposalAction({ blocked: "source_changed" }), "open_row");
  assert.equal(confidenceText(0.944), "94%");
});

test("the filters keep kind, status, and target search, and the list is newest first", async () => {
  const open = (await bundle()).session.proposals.open;
  assert.deepEqual(filterProposals(open).map((item) => item.id), ["p-4", "p-3", "p-2", "p-1"]);
  assert.deepEqual(filterProposals(open, { status: "ready" }).map((item) => item.id), ["p-2", "p-1"]);
  assert.deepEqual(filterProposals(open, { status: "source_changed" }).map((item) => item.id), ["p-4"]);
  assert.deepEqual(filterProposals(open, { q: "gross" }).map((item) => item.id), ["p-3"]);
  assert.deepEqual(filterProposals(open, { kind: "name" }), []);
  assert.deepEqual(readyProposals(open).map((item) => item.id), ["p-1", "p-2"]);
});

test("A19: new proposals only change the count until the user shows them", async () => {
  const open = (await bundle()).session.proposals.open;
  const shown = new Set(["p-1", "p-2"]);
  assert.deepEqual(visibleProposals(open, shown).map((item) => item.id), ["p-1", "p-2"]);
  assert.equal(newProposalCount(open, shown), 2);
});

test("the Accept all summary has the kinds, the plan now and after, the change, and the skipped items", async () => {
  const files = await bundle();
  const summary = acceptAllSummary({ open: files.session.proposals.open, planNow: files.plan, planAfter: files["plan-proposals"] });
  assert.equal(summary.n, 2);
  assert.deepEqual(summary.kinds.map((item) => item.text), ["Merge Choice: 2"]);
  assert.equal(summary.nowText, "Plan not valid: 1 blocking");
  assert.equal(summary.afterText, "Valid with 1 warning");
  assert.equal(summary.changeText, "Change: 1 fewer blocking items, 0 more warnings");
  assert.deepEqual(summary.skipped.map((item) => item.text), [
    "Gross Margin: you already set a Merge Choice. Decide in the row detail.",
    "Customer: a source changed. Confirm the row first.",
  ]);
});

test("the Accept selected toast tells the partial failure", () => {
  assert.deepEqual(acceptSelectedToast(2, 2), { tone: "ok", text: "2 proposals accepted. 0 skipped." });
  assert.deepEqual(acceptSelectedToast(1, 2), { tone: "warn", text: "1 of 2 proposals accepted. 1 was not accepted. See the marked row." });
});

test("the question sections lead with the first open question, and an option shows its effect", async () => {
  const { session } = await bundle();
  const sections = questionSections(session.questions);
  assert.equal(sections.first.id, "q-1");
  assert.deepEqual(sections.more.map((item) => item.id), ["q-2"]);
  assert.deepEqual(sections.answered.map((item) => item.id), ["q-0"]);
  assert.equal(optionEffect(sections.first.options[1], () => "Keep target"), "Sets Merge Choice: Keep target");
  assert.equal(optionEffect({ id: "x", label: "No change" }, () => ""), null);
});

test("the log helpers give the author, the action label, None for an empty value, and the GET log params", () => {
  assert.equal(authorText({ author: "user" }), "You");
  assert.equal(authorText({ author: "agent", mcp_client: "Test agent" }), "Agent: Test agent");
  assert.equal(actionText({ action: "merge_choice_set" }), "Set Merge Choice");
  assert.equal(actionText({ action: "proposal_submit", after: { choice: "keep" } }), "Proposed Merge Choice");
  assert.equal(actionText({ action: "new_action" }), "new_action");
  assert.ok(LOG_ACTIONS.includes("proposal_accept") && !LOG_ACTIONS.includes("alignment_override.break"));
  assert.equal(valueText(null), "None");
  assert.equal(valueText(""), "None");
  assert.equal(valueText({ choice: "keep" }), '{"choice":"keep"}');
  assert.equal(targetRowKey(["a", "b"]), null);
  assert.deepEqual(logParams(), { limit: 50 });
  assert.deepEqual(logParams({ author: "agent", action: "proposal_accept", target: " row-1 ", proposalId: "p-1", pages: 2 }), {
    limit: 100, author: "agent", action: "proposal_accept", target: "row-1", proposalId: "p-1",
  });
});

test("issue #13: a destructive object proposal needs review and stays out of Accept all", () => {
  const review = { id: "p-1", kind: "object_delete", blocked: null, needs_review: true, target_name: "Total Sales",
                   check: { breaks: 2, needs: 0, blocking: [{ kind: "removed" }] } };
  const edit = { id: "p-2", kind: "object_edit", blocked: null, needs_review: false };
  assert.equal(proposalStatus(review), "needs_review");
  assert.equal(proposalAction(review), "accept");
  assert.equal(statusText("needs_review"), "Review first");
  assert.deepEqual(readyProposals([review, edit]).map((item) => item.id), ["p-2"]);
  assert.equal(checkText(review), "Safety check: 2 breaks, 0 needs, 1 blocking items");
  assert.equal(checkText(edit), null);
  const summary = acceptAllSummary({ open: [review, edit] });
  assert.equal(summary.n, 1);
  assert.deepEqual(summary.skipped.map((item) => item.reason), ["needs_review"]);
  assert.match(summary.skipped[0].text, /^Total Sales: this change can break/);
});
