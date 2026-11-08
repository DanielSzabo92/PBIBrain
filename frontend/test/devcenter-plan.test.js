// Unit tests of the U7 Plan view helpers (UI design 4.6, 5.5, 8).
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  buildBlockList,
  formatBlockingFix,
  formatBlockingText,
  formatCheckTime,
  planDeletesCount,
  planPhaseGroups,
  planStripState,
  planSummaryGroups,
} from "../src/devcenter/screens/plan/planModel.js";

const fixture = async (name) => JSON.parse(await readFile(new URL(`../../tests/fixtures/devcenter_ui/${name}`, import.meta.url), "utf-8"));

test("formatCheckTime extracts HH:MM from ISO timestamps and preserves HH:MM strings", () => {
  assert.equal(formatCheckTime("2026-10-31T09:30:00Z"), "09:30");
  assert.equal(formatCheckTime("14:22"), "14:22");
  assert.equal(formatCheckTime(null), "09:30");
});

test("planDeletesCount sums model and report deleted totals and drives destructive apply variant", async () => {
  const defaultPlan = await fixture("default/plan.json");
  assert.equal(planDeletesCount(defaultPlan), 0);
  const stripDefault = planStripState({ plan: defaultPlan, blocks: [], checkTime: "09:30" });
  assert.equal(stripDefault.applyVariant, "default");

  const applyReadyPlan = await fixture("apply-ready/plan.json");
  assert.equal(planDeletesCount(applyReadyPlan), 1);
  const stripReady = planStripState({ plan: applyReadyPlan, blocks: [], checkTime: "14:22" });
  assert.equal(stripReady.applyVariant, "destructive");
  assert.equal(stripReady.state, "valid");
  assert.equal(stripReady.body, "5 plan steps · 6 operations. Full check 14:22.");
});

test("planStripState covers invalid, valid_with_warnings, valid, empty, and checking states", async () => {
  const defaultPlan = await fixture("default/plan.json");
  const invalidPlan = await fixture("plan-invalid/plan.json");

  const warningsStrip = planStripState({ plan: defaultPlan, blocks: [], checkTime: "09:30" });
  assert.equal(warningsStrip.state, "valid_with_warnings");
  assert.equal(warningsStrip.badgeTone, "warn");
  assert.equal(warningsStrip.badgeLabel, "Valid with 1 warning");
  assert.equal(warningsStrip.body, "3 plan steps · 5 operations, 1 warning. Full check 09:30.");
  assert.equal(warningsStrip.applyDisabled, false);

  const staleStrip = planStripState({ plan: defaultPlan, blocks: [], checkTime: "09:30", isStale: true });
  assert.equal(staleStrip.state, "stale");
  assert.equal(staleStrip.badgeTone, "warn");
  assert.equal(staleStrip.badgeLabel, "Stale, re-check");
  assert.equal(staleStrip.applyDisabled, true);

  const missingBlocks = buildBlockList({ plan: defaultPlan, session: { sources: [{ source_id: "src-1", status: "missing", display_name: "Sales" }] } });
  assert.equal(missingBlocks.some((b) => b.kind === "missing_sources"), true);
  const missingStrip = planStripState({ plan: defaultPlan, blocks: missingBlocks, checkTime: "09:30" });
  assert.equal(missingStrip.state, "invalid");
  assert.equal(missingStrip.badgeTone, "bad");
  assert.equal(missingStrip.applyDisabled, true);

  const blocks = buildBlockList({ plan: invalidPlan });
  const invalidStrip = planStripState({ plan: invalidPlan, blocks, checkTime: "09:30" });
  assert.equal(invalidStrip.state, "invalid");
  assert.equal(invalidStrip.badgeTone, "bad");
  assert.equal(invalidStrip.badgeLabel, "Plan not valid: 2 blocking");
  assert.equal(invalidStrip.body, "2 blocking items in the plan. Full check 09:30.");
  assert.equal(invalidStrip.reason, "Fix 2 items before you apply.");
  assert.equal(invalidStrip.applyDisabled, true);

  const emptyStrip = planStripState({ plan: { status: "valid", steps: [], blocking: [], warnings: [] }, blocks: [], checkTime: "10:15" });
  assert.equal(emptyStrip.state, "empty");
  assert.equal(emptyStrip.badgeTone, "ok");
  assert.equal(emptyStrip.badgeLabel, "Valid");
  assert.equal(emptyStrip.body, "The target matches your Merge Choices. Full check 10:15.");
  assert.equal(emptyStrip.reason, "Nothing to apply.");
  assert.equal(emptyStrip.applyDisabled, true);

  const checkingStrip = planStripState({ plan: defaultPlan, blocks: [], checking: true });
  assert.equal(checkingStrip.state, "checking");
  assert.equal(checkingStrip.badgeTone, "plain");
  assert.equal(checkingStrip.badgeLabel, "Checking plan");
  assert.equal(checkingStrip.body, "Validating expressions and dependencies.");
  assert.equal(checkingStrip.reason, "Wait for the plan check.");
  assert.equal(checkingStrip.applyDisabled, true);

  const appliedStrip = planStripState({ plan: defaultPlan, blocks: [], checkTime: "12:42", applied: { time: "12:42" } });
  assert.equal(appliedStrip.state, "applied");
  assert.equal(appliedStrip.badgeTone, "ok");
  assert.equal(appliedStrip.badgeLabel, "Applied 12:42");
  assert.equal(appliedStrip.body, "Applied 12:42 · Undo · Write change report");
  assert.equal(appliedStrip.reason, "Plan already applied at 12:42.");
  assert.equal(appliedStrip.applyDisabled, true);
});

test("buildBlockList orders marks, plan blocking items, Desktop, non-canonical files, and validation failures", () => {
  const plan = {
    status: "invalid",
    blocking: [
      {
        item_id: "dax_parse:row-net-sales",
        kind: "dax_parse",
        row_key: "row-net-sales",
        object: { name: "Net Sales", object_type: "measure", table: "Sales" },
        message: "{object} syntax error",
        params: { line: 3, column: 12 },
      },
      {
        item_id: "need_missing:row-net-sales",
        kind: "need_missing",
        row_key: "row-net-sales",
        object: { name: "Net Sales", object_type: "measure", table: "Sales" },
        message: "{object} needs {needed}",
        params: { needed: "ExchangeRate" },
      },
      {
        item_id: "name_clash:row-customer",
        kind: "name_clash",
        row_key: "row-customer",
        object: { name: "Customer", object_type: "table", table: null },
        message: "Customer clashes with an existing table name.",
        params: { name: "Customer", clash: { object_type: "table", name: "Customer", table: null } },
      },
    ],
  };
  const session = { counts: { marks: 3 } };
  const applyPreview = {
    desktop_state: "open_unsaved",
    non_canonical_files: ["definition/tables/Sales.tmdl", "definition/tables/Customer.tmdl"],
  };

  const list = buildBlockList({ plan, session, applyPreview, targetModelName: "Combined model" });
  assert.deepEqual(list.map((b) => b.category), ["marks", "plan", "plan", "desktop", "files", "validation"]);
  assert.deepEqual(list.map((b) => b.actionLabel), [
    "Show these rows",
    "Show impact",
    "Show row",
    "Check again",
    "Format files first",
    "Show row",
  ]);
  assert.equal(list[0].text, "3 rows changed in their source, and you did not confirm them.");
  assert.equal(list[1].text, "Net Sales needs ExchangeRate, which the target does not have.");
  assert.equal(list[3].text, "Power BI Desktop has unsaved changes in Combined model.");
  assert.equal(list[4].text, "2 target files are not in the Power BI Desktop format.");
  assert.deepEqual(list[4].files, ["definition/tables/Sales.tmdl", "definition/tables/Customer.tmdl"]);
  assert.equal(list[5].text, "The expression of Net Sales has a syntax error at line 3, column 12.");
});

test("planSummaryGroups and planPhaseGroups group steps and operations by domain and phase", async () => {
  const readyPlan = await fixture("apply-ready/plan.json");
  const summary = planSummaryGroups(readyPlan);
  const tableRow = summary.modelRows.find((r) => r.key === "table");
  const colRow = summary.modelRows.find((r) => r.key === "column");
  assert.deepEqual(tableRow, { key: "table", label: "Tables", created: 1, deleted: 0, modified: 0, renamed: 1 });
  assert.deepEqual(colRow, { key: "column", label: "Columns", created: 0, deleted: 1, modified: 0, renamed: 0 });

  const allPhases = planPhaseGroups(readyPlan);
  assert.deepEqual(allPhases.map((p) => p.baseName), [
    "Deletes",
    "Renames",
    "Creates",
    "Changes",
    "Expression rewrites",
    "Report changes",
  ]);
  assert.deepEqual(allPhases.map((p) => p.label), [
    "Deletes (1)",
    "Renames (1)",
    "Creates (1)",
    "Changes (1)",
    "Expression rewrites (1)",
    "Report changes (1)",
  ]);

  const modelOnly = planPhaseGroups(readyPlan, { domainFilter: "model" });
  assert.equal(modelOnly.some((p) => p.phase === "report"), false);

  const reportOnly = planPhaseGroups(readyPlan, { domainFilter: "report" });
  assert.deepEqual(reportOnly.map((p) => p.phase), ["report"]);

  const filtered = planPhaseGroups(readyPlan, { query: "Gross Margin" });
  assert.deepEqual(filtered.map((p) => p.phase), ["rewrites"]);
  assert.equal(filtered[0].items[0].operations[0].oldLine, "DIVIDE([Net Sales], COUNTROWS(Customers))");
  assert.equal(filtered[0].items[0].operations[0].newLine, "DIVIDE([Net Sales], COUNTROWS(Customer))");
});

test("formatBlockingText and formatBlockingFix interpolate S5 templates", () => {
  const item = {
    kind: "choice_source_removed",
    row_key: "row-gross-margin",
    object: { name: "Gross Margin", object_type: "measure", table: "Sales" },
    message: "{object} uses {source}",
    params: { source_name: "Finance model" },
  };
  assert.equal(formatBlockingText(item), "The source of this Merge Choice was removed: Finance model.");
  assert.equal(formatBlockingFix(item), "Blocking. Select a different source or a different Merge Choice.");
});
