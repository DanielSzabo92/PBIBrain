import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const SRC = fileURLToPath(new URL("../src/", import.meta.url));

test("Issue #45: Overview provides high-yield widgets and eliminates redundancy", async () => {
  const appCode = await readFile(path.join(SRC, "App.jsx"), "utf8");
  const css = await readFile(path.join(SRC, "app.css"), "utf8");

  // Overview title and count redundancy reduction
  assert.ok(appCode.includes("<h1>Overview</h1>"), "Overview uses standard page title 'Overview' rather than repeating project name");
  assert.ok(!appCode.includes('className="project-counts"'), "Removes redundant project counts DL that duplicated status bar");

  // High-yield widgets
  assert.ok(appCode.includes("overview-widgets-grid"), "Overview defines widgets grid container");
  assert.ok(appCode.includes("Validation summary"), "Overview defines Validation summary widget");
  assert.ok(appCode.includes("Most-used measures"), "Overview defines Most-used measures widget");
  assert.ok(appCode.includes("Unreviewed on hot objects"), "Overview defines Unreviewed on hot objects widget");
  assert.ok(appCode.includes("Recently changed"), "Overview defines Recently changed widget");

  // Actionable links
  assert.ok(appCode.includes("widget-link"), "Widgets provide direct inspect links for measures and hot objects");

  // CSS for widgets grid uses type scale tokens
  assert.ok(css.includes(".overview-widgets-grid"), "app.css defines .overview-widgets-grid");
  assert.ok(css.includes(".overview-widget"), "app.css defines .overview-widget");
  assert.ok(css.includes(".status-badge-inline"), "app.css defines .status-badge-inline");
});

test("Issue #45: Graph view provides minimum readable zoom, uncluttered edges, details pane refit, and circular matrix dots", async () => {
  const graphCode = await readFile(path.join(SRC, "components/GraphView.jsx"), "utf8");
  const css = await readFile(path.join(SRC, "app.css"), "utf8");

  // Minimum readable zoom fit
  assert.ok(graphCode.includes("minFitZoom"), "GraphView defines minFitZoom to prevent tiny zoom on few nodes");
  assert.ok(graphCode.includes("nodeCount <= 6 ? 1.0"), "GraphView uses readable minimum zoom for small graphs");

  // Edge label collision avoidance and uncluttered threshold
  assert.ok(graphCode.includes("shiftY") || graphCode.includes("shiftX"), "GraphView offsets parallel edge labels to avoid collision");
  assert.ok(graphCode.includes("layout.edges.length <= 12"), "GraphView guards edge labels on path to prevent clutter on dense graphs");

  // Re-fit on details pane opening/docking
  assert.ok(graphCode.includes("flow?.fitView"), "GraphView re-fits view when details pane docks");

  // Circular matrix indicators
  assert.ok(css.includes(".mx-mark {") && css.includes("border-radius: 50%"), "Matrix marks use circular border-radius 50%");
  assert.ok(css.includes(".mx-swatch-off {") && css.includes("border-radius: 50%"), "Matrix swatches use circular border-radius 50%");

  // Column header widths
  assert.ok(css.includes(".mx-col { width: 32px; min-width: 32px; height: 160px;"), "Matrix column width is expanded to avoid header truncation");
});

test("Issue #45: Merge models quiets Same indicators, hides Target repetition, separates Naming rules, and blanks empty Log cells", async () => {
  const stateCellCode = await readFile(path.join(SRC, "devcenter/components/StateCell.jsx"), "utf8");
  const compareCss = await readFile(path.join(SRC, "devcenter/components/compare.css"), "utf8");
  const sourcesCode = await readFile(path.join(SRC, "devcenter/screens/SourcesTab.jsx"), "utf8");
  const workAreaCode = await readFile(path.join(SRC, "devcenter/screens/WorkArea.jsx"), "utf8");
  const logCode = await readFile(path.join(SRC, "devcenter/screens/log/LogTab.jsx"), "utf8");

  // Same indicator quieted
  assert.ok(stateCellCode.includes('hasChanged = Boolean(cell.changed) && state !== "same";'), "Changed indicator is suppressed on 'same' state cells");
  assert.ok(compareCss.includes(".dc-st-same"), "compare.css styles .dc-st-same");
  assert.ok(compareCss.includes("opacity: 0.45;"), "compare.css sets .dc-st-same to faint neutral");

  // Target repetition hidden
  assert.ok(stateCellCode.includes('state === "target" ? <span className="sr-only">'), "StateCell wraps target word in sr-only to avoid visual repetition");

  // Sources row removal in overflow menu
  assert.ok(sourcesCode.includes("MoreHorizontal"), "SourcesTab uses overflow menu for row actions");
  assert.ok(sourcesCode.includes('source.role !== "target"'), "SourcesTab prevents removing target sources");

  // Dedicated Naming Rules tab
  assert.ok(workAreaCode.includes('"rules"'), "WorkArea defines dedicated 'rules' tab");
  assert.ok(workAreaCode.includes("<NamingRules"), "WorkArea renders NamingRules under its own tab");

  // Empty log cells left blank
  assert.ok(logCode.includes('return str === "None" ? "" : str;'), "LogTab returns blank string instead of None");
});

test("Issue #45: Inspector flattens nested cards and replaces side stripes with TypeGlyph; Doc export sizes fieldsets naturally", async () => {
  const appCode = await readFile(path.join(SRC, "App.jsx"), "utf8");
  const impactCode = await readFile(path.join(SRC, "components/ImpactExplorer.jsx"), "utf8");
  const css = await readFile(path.join(SRC, "app.css"), "utf8");

  // Flattened DAX ExpressionBlock outside Card
  assert.ok(!appCode.includes('<Card className="panel object-summary">\n        <ExpressionBlock'), "DAX ExpressionBlock is not nested inside object-summary Card");

  // Flattened ImpactExplorer
  assert.ok(!impactCode.includes('<Card className="panel impact-explorer-card">'), "ImpactExplorer does not use nested Card");
  assert.ok(impactCode.includes('className="impact-explorer-section"'), "ImpactExplorer uses clean section divider");

  // TypeGlyph on lineage relationship groups instead of colored side stripe
  assert.ok(appCode.includes('<TypeGlyph node={resolved} type={resolved?.type || edge.type} colors={colors} size="xs" />'), "Lineage relationships use TypeGlyph instead of colored side stripe");
  assert.ok(!appCode.includes('<span className="edge-chip"'), "Removed colored edge-chip side stripe from RelationshipGroup");

  // Documentation export fieldset natural sizing
  assert.ok(css.includes(".doc-export-scope {") && css.includes("align-items: start;"), "doc-export-scope has align-items: start for natural height fieldsets");
});
