import test from "node:test";
import assert from "node:assert/strict";
import { explainConfidence } from "../src/reviewEvidence.js";
import { SHORTCUTS } from "../src/shortcuts.js";

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

test("Review keyboard shortcuts J/K/A/R/X are defined in SHORTCUTS with group Review", () => {
  const reviewShortcuts = SHORTCUTS.filter((s) => s.group === "Review");
  assert.equal(reviewShortcuts.length, 5);

  const keys = reviewShortcuts.map((s) => s.keys);
  assert.deepEqual(keys.sort(), ["A", "J", "K", "R", "X"].sort());

  const ids = reviewShortcuts.map((s) => s.id);
  assert.ok(ids.includes("review:next"));
  assert.ok(ids.includes("review:prev"));
  assert.ok(ids.includes("review:approve"));
  assert.ok(ids.includes("review:reject"));
  assert.ok(ids.includes("review:select"));
});

test("Review shortcuts do not collide with any other shortcut keys", () => {
  const keys = SHORTCUTS.map((item) => item.keys.toUpperCase());
  assert.equal(new Set(keys).size, keys.length, "All shortcut keys must be unique");
});
