import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const SRC = fileURLToPath(new URL("../src/", import.meta.url));

test("Issue #44: app.css ensures graph canvas does not collapse at <=760px", async () => {
  const css = await readFile(path.join(SRC, "app.css"), "utf8");
  
  // Must have media query for <= 760px
  assert.ok(css.includes("@media (max-width: 760px)"));

  // Check that inside <= 760px breakpoint, graph-canvas-card expands cleanly with flex: 1 and min-width: 0
  const match760 = css.match(/@media \(max-width: 760px\) \{([\s\S]*?)\n\}/);
  assert.ok(match760, "Found @media (max-width: 760px) block");
  const block760 = match760[1];

  assert.ok(
    block760.includes(".graph-canvas-card"),
    "Defines .graph-canvas-card inside <= 760px"
  );
  assert.ok(
    !block760.includes(".graph-canvas-card { flex: none"),
    ".graph-canvas-card must not have flex: none at <= 760px"
  );
  assert.ok(
    block760.includes("min-width: 0"),
    ".graph-canvas-card or body must set min-width: 0"
  );
  assert.ok(
    block760.includes("flex-direction: column"),
    ".graph-body must stack flex-direction: column at <= 760px"
  );
});

test("Issue #44: app.css enables graph toolbar wrapping at <=1200px", async () => {
  const css = await readFile(path.join(SRC, "app.css"), "utf8");
  
  const match1200 = css.match(/@media \(max-width: 1200px\) \{([\s\S]*?)\n\}/);
  assert.ok(match1200, "Found @media (max-width: 1200px) block");
  const block1200 = match1200[1];

  assert.ok(
    block1200.includes(".graph-toolbar"),
    "Defines .graph-toolbar inside <= 1200px"
  );
  assert.ok(
    block1200.includes("flex-wrap: wrap"),
    ".graph-toolbar must allow wrapping at <= 1200px"
  );
});

test("Issue #44: screens.css stacks dc-plan-grid and adds table scroll containment at <=1200px", async () => {
  const css = await readFile(path.join(SRC, "devcenter/screens/screens.css"), "utf8");

  // dc-plan-grid stacks at <= 1200px
  assert.ok(
    css.includes("@media (max-width: 1200px)"),
    "screens.css defines @media (max-width: 1200px)"
  );
  assert.ok(
    css.includes(".dc-plan-table-wrap"),
    "screens.css defines .dc-plan-table-wrap"
  );
  assert.ok(
    css.includes("overflow-x: auto"),
    ".dc-plan-table-wrap provides horizontal overflow scrolling"
  );
});

test("Issue #44: PlanTab wraps summary table in dc-plan-table-wrap", async () => {
  const code = await readFile(path.join(SRC, "devcenter/screens/plan/PlanTab.jsx"), "utf8");
  assert.ok(
    code.includes('className="dc-plan-table-wrap"'),
    "PlanTab wraps summary table with dc-plan-table-wrap"
  );
  assert.ok(
    code.includes("dc-plan-summary-table"),
    "PlanTab contains dc-plan-summary-table"
  );
});

test("Issue #44: AISettings uses standard form layout tokens and structure", async () => {
  const code = await readFile(path.join(SRC, "components/AISettings.jsx"), "utf8");
  assert.ok(code.includes("config-panel"), "AISettings uses config-panel");
  assert.ok(code.includes("ai-settings-panel"), "AISettings uses ai-settings-panel");
  assert.ok(code.includes("settings-section"), "AISettings uses settings-section");
  assert.ok(code.includes("config-field"), "AISettings stacks labels with config-field");
  assert.ok(code.includes("ai-key-hint"), "AISettings wraps key note in ai-key-hint");
  assert.ok(code.includes("config-actions"), "AISettings uses config-actions footer");
});

test("Issue #44: GraphView renders ViewPopover for <=1200px and keeps focus chip in toolbar", async () => {
  const code = await readFile(path.join(SRC, "components/GraphView.jsx"), "utf8");
  assert.ok(code.includes("function ViewPopover"), "GraphView defines ViewPopover");
  assert.ok(code.includes("useNarrowView"), "GraphView defines useNarrowView");
  assert.ok(code.includes('data-slot="focus-chip"'), "GraphView has focus-chip slot");
  
  // Verify focus chip is inside graph-toolbar (before graph-body)
  const toolbarSection = code.match(/className="graph-toolbar"[\s\S]*?<div className="graph-body">/);
  assert.ok(toolbarSection, "GraphView has graph-toolbar before graph-body");
  assert.ok(
    toolbarSection[0].includes('data-slot="focus-chip"'),
    "Focus chip is placed inside graph-toolbar"
  );
});
