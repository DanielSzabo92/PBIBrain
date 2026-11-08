// Unit tests of the U3 screen helpers (UI design 4.1, 4.2, 4.8, 5.1, 9.3).
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { DevCenterError } from "../src/devcenter/errors.js";
import { setSlashSearchEnabled, slashGoesToSearch, slashSearchEnabled } from "../src/devcenter/preferences.js";
import {
  agentCount, banners, defaultSessionName, deriveReadiness, draftHasModel, draftSource, listRowState, planStatus, runCreateFlow,
  sortSessions, targetLine, targetModelItems, targetNames, targetPayload, targetReportItems,
} from "../src/devcenter/screens/sessionModel.js";

const fixture = async (name) => JSON.parse(await readFile(new URL(`../../tests/fixtures/devcenter_ui/${name}`, import.meta.url), "utf-8"));

test("the target names come from the source list, because GET session has no name fields", async () => {
  const session = await fixture("default/session.json");
  assert.deepEqual(targetNames(session), { model: "Combined model", report: "Combined report", reportNew: false });
  assert.equal(targetLine(session), "Target model: Combined model. Target report: Combined report.");
  const empty = { sources: [], target: { model: null, report: { mode: "new_empty" } } };
  assert.equal(targetLine(empty), "Target model: Not set. Target report: new empty report.");
});

test("the plan status button uses GET plan counts when it has them", () => {
  assert.deepEqual(planStatus("valid"), { tone: "ok", text: "Valid" });
  assert.equal(planStatus("valid_with_warnings", { warnings: [1, 2], blocking: [] }).text, "Valid with 2 warnings");
  assert.equal(planStatus("valid_with_warnings", { warnings: [1], blocking: [] }).text, "Valid with 1 warning");
  assert.equal(planStatus("valid_with_warnings").text, "Valid with warnings");
  assert.equal(planStatus("invalid", { blocking: [1, 2], warnings: [] }).text, "Plan not valid: 2 blocking");
  assert.equal(planStatus("invalid").text, "Plan not valid");
  assert.equal(planStatus(null).text, "Plan not checked");
  assert.equal(planStatus("valid", null, true).text, "Checking plan");
});

test("deriveReadiness ensures no screen can show Valid when blocking items, missing sources, unconfirmed marks, or stale plan exist", async () => {
  const missingSession = await fixture("source-missing/session.json");
  const missingReadiness = deriveReadiness({ session: missingSession, plan: { status: "valid" } });
  assert.equal(missingReadiness.tone, "bad");
  assert.equal(missingReadiness.text, "1 source missing");
  assert.equal(missingReadiness.ready, false);

  const changedSession = await fixture("sources-changed/session.json");
  const changedReadiness = deriveReadiness({ session: changedSession, plan: { status: "valid" } });
  assert.equal(changedReadiness.tone, "warn");
  assert.equal(changedReadiness.text, "3 unconfirmed rows");
  assert.equal(changedReadiness.ready, false);

  const invalidPlan = await fixture("plan-invalid/plan.json");
  const invalidReadiness = deriveReadiness({ session: { sources: [], counts: {} }, plan: invalidPlan });
  assert.equal(invalidReadiness.tone, "bad");
  assert.equal(invalidReadiness.text, "Plan not valid: 2 blocking");
  assert.equal(invalidReadiness.ready, false);

  const staleReadiness = deriveReadiness({ session: { revision: 15, sources: [] }, plan: { revision: 12, status: "valid" } });
  assert.equal(staleReadiness.tone, "warn");
  assert.equal(staleReadiness.text, "Stale, re-check");
  assert.equal(staleReadiness.ready, false);

  const cleanReadiness = deriveReadiness({ session: { revision: 12, sources: [{ status: "ok" }], counts: { marks: 0 } }, plan: { revision: 12, status: "valid", steps: [{}], blocking: [], warnings: [] } });
  assert.equal(cleanReadiness.tone, "ok");
  assert.equal(cleanReadiness.text, "Valid");
  assert.equal(cleanReadiness.ready, true);
});

test("the banner stack has the order locked, source missing, sources changed", async () => {
  assert.deepEqual(banners(await fixture("default/session.json")), []);
  const locked = banners(await fixture("locked/session.json"));
  assert.deepEqual(locked.map((item) => item.id), ["locked"]);
  const missing = banners(await fixture("source-missing/session.json"));
  assert.equal(missing[0].text, "1 source was not found: Sales model. Find it again or remove it.");
  const changed = banners(await fixture("sources-changed/session.json"));
  assert.equal(changed[0].text, "1 source changed since the last check. You must confirm 3 rows.");
  const all = banners({ read_only: true, sources: [{ display_name: "A", status: "missing" }, { display_name: "B", status: "ok", fingerprint_state: "changed" }], counts: { marks: 1 } });
  assert.deepEqual(all.map((item) => item.id), ["locked", "missing", "changed"]);
});

test("the Agent tab count is open proposals plus open questions", async () => {
  assert.equal(agentCount(await fixture("default/session.json")), 1);
  assert.equal(agentCount({ proposals: { open: [{}, {}] }, questions: { open: [{}] } }), 3);
  assert.equal(agentCount(null), 0);
});

test("list rows: newer and damaged have no link and a reason; locked opens read-only", async () => {
  const rows = (await fixture("damaged/sessions.json")).sessions;
  assert.deepEqual(listRowState(rows[0]).openable, false);
  assert.equal(listRowState(rows[0]).label, "Cannot read");
  assert.equal(listRowState({ schema_state: "newer", lock_state: "free" }).label, "Needs a newer PBIBrain");
  assert.deepEqual(listRowState({ schema_state: "ok", lock_state: "locked" }), { openable: true, tone: "info", label: "Open in another window", reason: "Opens read-only." });
  const sorted = sortSessions([{ updated_at: "2026-10-30T00:00:00Z" }, { updated_at: null }, { updated_at: "2026-10-31T00:00:00Z" }]);
  assert.deepEqual(sorted.map((row) => row.updated_at), ["2026-10-31T00:00:00Z", "2026-10-30T00:00:00Z", null]);
});

test("a PBIX path gives the fixed refusal, and the kind comes from the path", () => {
  assert.deepEqual(draftSource("C:/models/Sales.pbix", "pbip"), { refused: 'Cannot add "Sales.pbix". Save as PBIP in Power BI Desktop.' });
  assert.deepEqual(draftSource("sources/Sales.SemanticModel", "pbip"), { path: "sources/Sales.SemanticModel", kind: "tmdl_folder", name: "Sales" });
  assert.equal(draftSource("x/Board.Report", "pbip").kind, "pbir_report");
  assert.equal(draftHasModel([{ kind: "pbir_report" }]), false);
  assert.equal(draftHasModel([{ kind: "pbir_report" }, { kind: "model_bim" }]), true);
});

test("target choices show the fixed refusals, and the default name uses the target model", () => {
  const sources = [
    { key: "1", name: "Sales", kind: "tmdl_folder" },
    { key: "2", name: "Old", kind: "model_bim" },
    { key: "3", name: "Board", kind: "pbir_legacy_report" },
  ];
  const models = targetModelItems(sources);
  assert.deepEqual(models.map((item) => item.value), ["existing:1", "copy:1", "existing:2", "copy:2", "empty"]);
  assert.equal(models[2].reason, "Save as TMDL in Power BI Desktop first.");
  assert.equal(models[1].label, "Copy of Sales");
  const reports = targetReportItems(sources);
  assert.deepEqual(reports.map((item) => [item.value, Boolean(item.disabled)]), [["new_empty", false], ["existing:3", true]]);
  assert.equal(reports[1].reason, "Convert to PBIR in Power BI Desktop first.");
  assert.equal(defaultSessionName({ sources, targetModel: "copy:1" }), "Sales merge");
  assert.equal(defaultSessionName({ sources, targetModel: null }), "");
});

test("the target_set payload uses the source IDs of the source_add replies", () => {
  const ids = new Map([["1", "src-1"], ["2", "src-2"]]);
  assert.deepEqual(targetPayload({ targetModel: "copy:1", copyFolder: "target/Copy", targetReport: "existing:2" }, ids),
    { model: { mode: "copy_of", source_id: "src-1", path: "target/Copy" }, report: { mode: "existing", source_id: "src-2" } });
  assert.deepEqual(targetPayload({ targetModel: "existing:2", targetReport: "new_empty" }, ids), { model: { mode: "existing", source_id: "src-2" }, report: { mode: "new_empty" } });
  assert.equal(targetPayload({ targetModel: "existing:9" }, ids), null);
});

function fakeRun(fail = {}) {
  const calls = [];
  let next = 1;
  const run = async (method, payload) => {
    calls.push([method, payload]);
    if (fail[method] && fail[method](payload)) throw new DevCenterError({ code: "action_not_allowed", message: "Injected.", source: "jsapi" });
    if (method === "session_create") return { revision: 1, session_id: "a".repeat(32), read_only: false };
    if (method === "source_add") return { revision: 2, source: { source_id: `src-${next++}` } };
    return { revision: 3 };
  };
  return { run, calls };
}

const DRAFT = {
  name: "Sales merge",
  sources: [{ key: "1", name: "Sales", path: "sources/Sales.SemanticModel", kind: "tmdl_folder" }, { key: "2", name: "Finance", path: "sources/Finance.SemanticModel", kind: "tmdl_folder" }],
  targetModel: "existing:1",
  targetReport: "new_empty",
};

test("the create flow calls session_create, source_add in list order, then target_set", async () => {
  const { run, calls } = fakeRun();
  const steps = [];
  const result = await runCreateFlow({ draft: DRAFT, run, onStep: (lines) => steps.push(lines) });
  assert.deepEqual(calls.map(([method]) => method), ["session_create", "source_add", "source_add", "target_set"]);
  assert.deepEqual(calls[1][1], { path: "sources/Sales.SemanticModel" });
  assert.deepEqual(calls[3][1], { model: { mode: "existing", source_id: "src-1" }, report: { mode: "new_empty" } });
  assert.equal(result.targetSet, true);
  assert.deepEqual(steps.at(-1).map((line) => line.state), ["done", "done", "done", "done"]);
});

test("a source_add fault keeps the session, marks the failed item, and still sets the target", async () => {
  const { run, calls } = fakeRun({ source_add: (payload) => payload.path.includes("Finance") });
  const result = await runCreateFlow({ draft: DRAFT, run, describe: (error) => error.message });
  assert.equal(result.created, true);
  assert.deepEqual(result.failed.map((source) => source.key), ["2"]);
  assert.equal(result.lines[2].state, "failed");
  assert.equal(result.lines[2].text, "Finance not added: Injected.");
  assert.equal(calls.at(-1)[0], "target_set");
});

test("a failed session_create stops the flow with no other call", async () => {
  const { run, calls } = fakeRun({ session_create: () => true });
  const result = await runCreateFlow({ draft: DRAFT, run });
  assert.equal(result.created, false);
  assert.equal(calls.length, 1);
});

test("the / key switch: on by default, off in storage, and never in a text field or a dialog", () => {
  const store = new Map();
  const storage = { getItem: (key) => store.get(key) ?? null, setItem: (key, value) => store.set(key, value) };
  assert.equal(slashSearchEnabled(storage), true);
  setSlashSearchEnabled(false, storage);
  assert.equal(slashSearchEnabled(storage), false);
  assert.equal(slashSearchEnabled({ getItem: () => { throw new Error("blocked"); } }), true);
  const doc = { querySelector: () => null };
  const key = (target = { tagName: "DIV" }) => ({ key: "/", target });
  assert.equal(slashGoesToSearch(key(), { enabled: true, doc }), true);
  assert.equal(slashGoesToSearch(key(), { enabled: false, doc }), false);
  assert.equal(slashGoesToSearch(key({ tagName: "INPUT" }), { enabled: true, doc }), false);
  assert.equal(slashGoesToSearch(key(), { enabled: true, doc: { querySelector: () => ({}) } }), false);
});
