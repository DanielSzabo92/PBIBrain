// Step U10: the pure logic of the Apply, Undo, format only, and change report flows (UI design 5.5, 5.6).
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  approvalItems,
  approvalPurposes,
  changeReportName,
  deletedNames,
  desktopLine,
  failureReason,
  flowResult,
  formatElapsed,
  needsDesktopBanner,
  progressLine,
  progressRows,
  undoState,
} from "../src/devcenter/screens/plan/applyModel.js";

const PLAN = {
  steps: [{}, {}, {}],
  operations: [
    { row_key: "row-region", name: "Region", op: "DELETE" },
    { row_key: "row-margin", name: "Margin", op: "CREATE" },
  ],
};

test("approval items list Critical, then High, then Not checked, with the object names", () => {
  const preview = {
    approvals_needed: [
      { purpose: "HIGH_RISK_PROMOTION", risk: "CRITICAL", row_keys: ["row-margin"] },
      { purpose: "UNCHECKED_IMPACT", risk: null, row_keys: ["row-budget"] },
    ],
    not_checked: [{ object_id: "row-budget", object_name: "Budget" }],
  };
  const items = approvalItems(preview, PLAN);
  assert.deepEqual(items.map((item) => [item.severity, item.name]), [["critical", "Margin"], ["not_checked", "Budget"]]);
  assert.deepEqual(approvalPurposes(preview), ["HIGH_RISK_PROMOTION", "UNCHECKED_IMPACT"]);
  assert.deepEqual(approvalItems({ approvals_needed: [], not_checked: [] }, PLAN), []);
  assert.deepEqual(approvalPurposes({ not_checked: [{ object_id: "a", object_name: "A" }] }), ["UNCHECKED_IMPACT"]);
});

test("the deleted names come from the DELETE operations", () => {
  assert.deepEqual(deletedNames(PLAN), ["Region"]);
  assert.deepEqual(deletedNames({ operations: [] }), []);
});

test("the Desktop line shows for an open or a not reachable Power BI Desktop", () => {
  assert.equal(desktopLine("not_open"), null);
  assert.match(desktopLine("open_saved"), /Apply external changes/);
  assert.match(desktopLine("open_saved", "undo"), /After the undo/);
  assert.match(desktopLine("not_reachable"), /Could not check Power BI Desktop/);
  assert.equal(needsDesktopBanner({ notices: ["apply_external_changes"] }), true);
  assert.equal(needsDesktopBanner({ notices: ["desktop_not_checked"] }), false);
});

test("progress maps step_index to the list: checks done, the current row runs, the rest waits", () => {
  const rows = progressRows("apply", { available: true, step: "promotion", step_index: 9, step_count: 12 });
  assert.equal(rows.length, 11);
  const state = Object.fromEntries(rows.map((row) => [row.id, row.state]));
  assert.equal(state.source_check, "done");
  assert.equal(state.approval, "done");
  assert.equal(state.candidate_write, "done");
  assert.equal(state.guard, "done");
  assert.equal(state.promotion, "running");
  assert.equal(state.rescan, "waiting");
  assert.equal(progressLine("apply", rows, { available: true }, 12_000), "Step 9 of 11. 12 s elapsed.");
  // Before the first reply, the checks show as done and the write starts.
  const first = progressRows("apply", null);
  assert.equal(first.find((row) => row.id === "approval").state, "done");
  assert.equal(first.find((row) => row.id === "candidate_write").state, "running");
});

test("the fallback line shows the elapsed time when GET apply/progress fails", () => {
  const rows = progressRows("apply", { available: false });
  assert.equal(progressLine("apply", rows, { available: false }, 65_000), "Applying plan. 1 min 5 s elapsed.");
  assert.equal(progressLine("undo", progressRows("undo", null), { available: false }, 3_000), "Undoing apply. 3 s elapsed.");
  assert.equal(formatElapsed(0), "0 s");
});

test("the undo list has three rows and a failed step shows as failed", () => {
  const rows = progressRows("undo", { available: true, step: "rescan", step_index: 4 });
  assert.deepEqual(rows.map((row) => [row.label, row.state]), [["Restore the files", "done"], ["Rescan", "running"], ["Save the fingerprints", "waiting"]]);
  const failed = progressRows("apply", null, { failedStep: "guard" });
  assert.equal(failed.find((row) => row.id === "guard").state, "failed");
  assert.equal(failed.find((row) => row.id === "candidate_write").state, "done");
  assert.equal(failed.find((row) => row.id === "promotion").state, "waiting");
});

test("success, differences, and failure results have their copy", () => {
  const ok = flowResult("apply", { reply: { file_count: 4, rescan_differences: [] }, planSteps: 3, time: "14:22" });
  assert.equal(ok.type, "success");
  assert.equal(ok.title, "Plan applied");
  assert.equal(ok.body, "The target matches the plan. 3 plan steps, 4 files written at 14:22. A backup is kept for undo.");
  const diff = flowResult("apply", { reply: { file_count: 1, rescan_differences: [{ object: "Sales/Margin", expected: "a", found: "b" }] } });
  assert.equal(diff.type, "differences");
  assert.equal(diff.title, "Plan applied with 1 differences");
  const fail = flowResult("apply", { error: { code: "action_not_allowed", details: { step: "guard", check: "scope" } } });
  assert.equal(fail.title, "Nothing was written");
  assert.equal(fail.body, "The guard check stopped the apply. The candidate changes an object that is not in the plan. Your target files are the same as before.");
  assert.equal(fail.step, "Guard check");
  const stale = flowResult("apply", { error: { code: "stale_revision", details: {} } });
  assert.equal(stale.type, "stale");
  assert.equal(stale.title, "The plan changed after you opened this dialog. Check it again.");
});

test("each details.check has one sentence, and a step with no check uses its step sentence", () => {
  for (const check of ["scope", "canonical", "tree_compare", "pbir", "policy", "approval", "write", "rescan"]) {
    const text = failureReason({ details: { step: "guard", check } });
    assert.ok(!text.startsWith("details."), check);
    assert.equal(text.split(". ").length, 1, check);
  }
  assert.equal(failureReason({ details: { step: "desktop_check" } }), "Power BI Desktop has unsaved changes in the target. Save or close the target, then apply again.");
  assert.equal(failureReason({ details: { step: "write" } }), "PBIBrain could not write the candidate copy.");
});

test("undo is available only with a backup, and it is refused with the file list when the target changed", () => {
  assert.equal(undoState(null).available, false);
  assert.equal(undoState({ apply_id: "apl-1", backup_present: false }).available, false);
  assert.equal(undoState({ apply_id: "apl-1", backup_present: true, undone: true }).available, false);
  assert.deepEqual(undoState({ apply_id: "apl-1", backup_present: true, target_changed: true, changed_files: ["a.tmdl"] }),
    { available: true, refused: true, files: ["a.tmdl"] });
  const refused = flowResult("undo", { error: { code: "action_not_allowed", details: { reason: "target_changed", files: ["a.tmdl", "b.json"] } } });
  assert.equal(refused.type, "refused");
  assert.equal(refused.title, "Cannot undo this apply");
  assert.deepEqual(refused.files, ["a.tmdl", "b.json"]);
  assert.match(refused.body, /^2 target files changed after the apply/);
});

test("format result and the change report default name", () => {
  assert.equal(flowResult("format", { reply: { file_count: 2 } }).title, "Files formatted");
  assert.equal(flowResult("format", { error: { code: "action_not_allowed", details: { step: "guard", check: "tree_compare" } } }).body,
    "The guard found a model change in the formatted files, so it stopped the write.");
  const date = new Date(2026, 10, 6);
  assert.equal(changeReportName("Sales and finance merge", date), "Sales and finance merge change report 2026-11-06.md");
  assert.equal(changeReportName("A/B: merge", date), "A B merge change report 2026-11-06.md");
  assert.equal(changeReportName("", date), "Merge session change report 2026-11-06.md");
});

test("a cloud target adds the CLOUD_WRITE approval item and purpose (issue #16)", () => {
  const preview = {
    approvals_needed: [{ purpose: "CLOUD_WRITE", risk: null, row_keys: [] }],
    not_checked: [],
    cloud_target: { workspace_name: "Sales Analytics", model_name: "Sales Cloud", report_name: null, checks: [], warnings: ["pbix_download_blocked"] },
  };
  const items = approvalItems(preview, PLAN);
  assert.equal(items.length, 1);
  assert.equal(items[0].severity, "cloud");
  assert.match(items[0].name, /Sales Cloud in Sales Analytics/);
  assert.deepEqual(approvalPurposes(preview), ["CLOUD_WRITE"]);
});
