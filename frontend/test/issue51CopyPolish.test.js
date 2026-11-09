// Unit tests for Issue #51: Copy polish, pluralisation, punctuation cleanup, and visual styling.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { COPY, formatPlural, plural, t, tn } from "../src/devcenter/copy.js";
import { progressRows } from "../src/devcenter/screens/plan/applyModel.js";
import { readableText, sanitizeDoublePunctuation, formatPlural as presFormatPlural } from "../src/presentation.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

test("Issue #51: formatPlural and plural helpers correctly pluralize words", () => {
  assert.equal(formatPlural(1, "object"), "1 object");
  assert.equal(formatPlural(0, "object"), "0 objects");
  assert.equal(formatPlural(2, "object"), "2 objects");
  assert.equal(formatPlural(1, "item"), "1 item");
  assert.equal(formatPlural(5, "item"), "5 items");

  // Custom plural form
  assert.equal(formatPlural(1, "category", "categories"), "1 category");
  assert.equal(formatPlural(2, "category", "categories"), "2 categories");

  // Re-exported plural alias
  assert.equal(plural(1, "match", "matches"), "1 match");
  assert.equal(plural(3, "match", "matches"), "3 matches");

  // Presentation helper
  assert.equal(presFormatPlural(1, "visual"), "1 visual");
  assert.equal(presFormatPlural(4, "visual"), "4 visuals");
});

test("Issue #51: tn handles singular, plural, and zero counts accurately", () => {
  // apply.deletes
  assert.equal(tn("apply.deletes", 1, { list: "Region" }), "Deletes 1 object: Region.");
  assert.equal(tn("apply.deletes", 2, { list: "Region, Sales" }), "Deletes 2 objects: Region, Sales.");

  // apply.deletes.heading
  assert.equal(tn("apply.deletes.heading", 1), "Deletes 1 object:");
  assert.equal(tn("apply.deletes.heading", 2), "Deletes 2 objects:");

  // apply.step.approval
  assert.equal(tn("apply.step.approval", 0), "No items required approval");
  assert.equal(tn("apply.step.approval", 1), "You approved 1 item");
  assert.equal(tn("apply.step.approval", 3), "You approved 3 items");

  // plan.before_apply.count
  assert.equal(tn("plan.before_apply.count", 1), "1 item stops the apply");
  assert.equal(tn("plan.before_apply.count", 4), "4 items stop the apply");
});

test("Issue #51: apply progress rows use accurate approval context for 0 items", () => {
  const rowsZero = progressRows("apply", null, { approvalCount: 0 });
  const approvalRowZero = rowsZero.find((r) => r.id === "approval");
  assert.equal(approvalRowZero.label, "No items required approval");

  const rowsOne = progressRows("apply", null, { approvalCount: 1 });
  const approvalRowOne = rowsOne.find((r) => r.id === "approval");
  assert.equal(approvalRowOne.label, "You approved 1 item");

  const rowsMany = progressRows("apply", null, { approvalCount: 3 });
  const approvalRowMany = rowsMany.find((r) => r.id === "approval");
  assert.equal(approvalRowMany.label, "You approved 3 items");
});

test("Issue #51: sanitizeDoublePunctuation eliminates trailing periods inside quotes before sentence punctuation", () => {
  const inputCurly = "The source description says “Twice the current sales.”. Confirm that the suggested label captures its meaning.";
  const expectedCurly = "The source description says “Twice the current sales”. Confirm that the suggested label captures its meaning.";
  assert.equal(sanitizeDoublePunctuation(inputCurly), expectedCurly);

  const inputStraight = 'The source description says "Twice the current sales.". Confirm that the suggested label captures its meaning.';
  const expectedStraight = 'The source description says "Twice the current sales". Confirm that the suggested label captures its meaning.';
  assert.equal(sanitizeDoublePunctuation(inputStraight), expectedStraight);

  // Clean single sentence trailing period
  assert.equal(sanitizeDoublePunctuation('He said "Done.".'), 'He said "Done".');

  // Double period collapse
  assert.equal(sanitizeDoublePunctuation("Check sources.. Then apply."), "Check sources. Then apply.");

  // readableText integrates punctuation sanitization
  assert.equal(
    readableText("Review reason: says “Budget amount.”. Confirm"),
    "Review reason: says “Budget amount”. Confirm"
  );
});

test("Issue #51: apply.desktop_after matches Power BI Desktop actual banner copy", () => {
  assert.equal(COPY["apply.desktop_after"], "Click Apply changes in Power BI Desktop to load modifications.");
});

test("Issue #51: removal policy strings support dynamic object kind and effect title", () => {
  assert.equal(t("row.policy.repoint.help", { type: "table" }), "Replace each reference with one other table.");
  assert.equal(t("row.policy.repoint.help", { type: "measure" }), "Replace each reference with one other measure.");
  assert.equal(
    t("row.policy.title.effect", { object: "Budget", effect: "Budget Variance" }),
    "Removal policy for Budget (affects Budget Variance)"
  );
});

test("Issue #51: ImpactExplorer contains friendly read-only guidance", () => {
  const code = fs.readFileSync(path.join(__dirname, "../src/components/ImpactExplorer.jsx"), "utf8");
  assert.ok(
    code.includes("Read-only view · Changes can be made in Dev Center or Power BI Desktop."),
    "ImpactExplorer must include friendly read-only guidance"
  );
});

test("Issue #51: active nav marker is flush with pill at left: 0", () => {
  const css = fs.readFileSync(path.join(__dirname, "../src/app.css"), "utf8");
  assert.ok(
    css.includes('.nav-button[aria-current="page"]::before { content: ""; position: absolute; left: 0;'),
    "Active nav marker must be flush at left: 0"
  );
  assert.ok(
    !css.includes("left: -6px"),
    "Old detached marker at left: -6px must be eliminated"
  );
});

test("Issue #51: menu shortcuts are right-aligned with fixed tabular column styling", () => {
  const appShellCode = fs.readFileSync(path.join(__dirname, "../src/components/AppShell.jsx"), "utf8");
  assert.ok(
    appShellCode.includes('className="app-menu-keys ml-auto pl-4 font-mono text-xs tabular-nums"'),
    "AppShell MenuItem keys must have right-aligned tabular column classes"
  );

  const css = fs.readFileSync(path.join(__dirname, "../src/app.css"), "utf8");
  assert.ok(css.includes(".app-menu-keys {"), "app-menu-keys rule must exist");
  assert.ok(css.includes("tabular-nums"), "app-menu-keys must use tabular-nums");
  assert.ok(css.includes("text-align: right"), "app-menu-keys must be right-aligned");
});
