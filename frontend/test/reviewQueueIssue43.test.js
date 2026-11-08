import test from "node:test";
import assert from "node:assert/strict";
import { isLowEvidence, explainConfidence } from "../src/reviewEvidence.js";
import { SHORTCUTS } from "../src/shortcuts.js";

test("isLowEvidence identifies name-only tautologies regardless of casing, spacing, and quotes", () => {
  const node = { id: "model:sales/table:Sales", name: "Sales" };
  const tautologyItem = {
    target: "model:sales/table:Sales",
    value: "Sales",
    source: "object_name",
    confidence: 0.30,
  };
  assert.equal(isLowEvidence(tautologyItem, [node]), true);

  // With quotes and extra spacing
  const quotedTautology = {
    target: "model:sales/table:Sales",
    value: " 'Sales' ",
    source: "object_name",
    confidence: 0.30,
  };
  assert.equal(isLowEvidence(quotedTautology, [node]), true);

  // Different value: not a tautology
  const distinctItem = {
    target: "model:sales/table:Sales",
    value: "Transactions recorded from POS and web",
    source: "description",
    confidence: 0.96,
  };
  assert.equal(isLowEvidence(distinctItem, [node]), false);
});

test("isLowEvidence identifies alias equal to object name", () => {
  const node = { id: "model:sales/column:Revenue", name: "Revenue" };
  const aliasItem = {
    target: "model:sales/column:Revenue",
    value: "Revenue",
    evidence: [{ source: "object_name" }],
    confidence: 0.97, // Miscalibrated confidence
  };
  assert.equal(isLowEvidence(aliasItem, [node]), true);
});

test("isLowEvidence preserves conflict and stale review items", () => {
  const conflictItem = {
    issue: "conflict",
    target: "t1",
    value: "t1",
  };
  assert.equal(isLowEvidence(conflictItem), false);

  const staleItem = {
    issue: "stale",
    target: "t1",
    value: "t1",
  };
  assert.equal(isLowEvidence(staleItem), false);
});

test("explainConfidence details the exact evidence contributing to confidence", () => {
  const node = { id: "model:sales/measure:TotalSales", name: "TotalSales" };

  // Tautology explanation
  const tautologyItem = {
    target: "model:sales/measure:TotalSales",
    value: "TotalSales",
    confidence: 0.30,
  };
  const tautologyExplanation = explainConfidence(tautologyItem, node);
  assert.match(tautologyExplanation, /Low evidence/i);
  assert.match(tautologyExplanation, /TotalSales/);

  // Multi-source explanation (description + dax)
  const richItem = {
    target: "model:sales/measure:TotalSales",
    value: "Sum of all sales transactions",
    confidence: 0.95,
    source: "description",
    evidence: [{ source: "description" }, { source: "dax_analysis" }],
  };
  const richExplanation = explainConfidence(richItem, node);
  assert.match(richExplanation, /95%/);
  assert.match(richExplanation, /source description/);
  assert.match(richExplanation, /DAX formula analysis/);
});

test("Review keyboard shortcuts J/K/A/R are defined in SHORTCUTS with group Review", () => {
  const reviewShortcuts = SHORTCUTS.filter((s) => s.group === "Review");
  assert.equal(reviewShortcuts.length, 4);

  const keys = reviewShortcuts.map((s) => s.keys);
  assert.deepEqual(keys.sort(), ["A", "J", "K", "R"].sort());

  const ids = reviewShortcuts.map((s) => s.id);
  assert.ok(ids.includes("review:next"));
  assert.ok(ids.includes("review:prev"));
  assert.ok(ids.includes("review:approve"));
  assert.ok(ids.includes("review:reject"));
});

test("Review shortcuts do not collide with any other shortcut keys", () => {
  const keys = SHORTCUTS.map((item) => item.keys.toUpperCase());
  assert.equal(new Set(keys).size, keys.length, "All shortcut keys must be unique");
});
