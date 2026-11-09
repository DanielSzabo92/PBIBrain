// Unit tests for Issue #52: Lintapple UI gate, design tokens, and policy alignment.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const THEME_CSS = path.resolve(__dirname, "../src/theme.css");
const APP_CSS = path.resolve(__dirname, "../src/app.css");
const POLICY_JSON = path.resolve(__dirname, "../ui-policy.json");
const LINT_SCRIPT = path.resolve(__dirname, "../scripts/lint-ui-states.mjs");
const COMPARE_GRID = path.resolve(__dirname, "../src/devcenter/components/CompareGrid.jsx");
const COMPARE_CSS = path.resolve(__dirname, "../src/devcenter/components/compare.css");
const DESIGN_MD = path.resolve(__dirname, "../DESIGN.md");

test("Issue #52: theme.css defines micro-radii, --fs-code alias, and DAX syntax palette", () => {
  const content = fs.readFileSync(THEME_CSS, "utf8");

  // Micro-radii
  assert.match(content, /--r-2xs:\s*2px;/, "theme.css defines --r-2xs");
  assert.match(content, /--r-3xs:\s*3px;/, "theme.css defines --r-3xs");

  // Type scale code alias
  assert.match(content, /--fs-code:\s*var\(--fs-body\);/, "theme.css defines --fs-code alias");

  // Dark DAX syntax palette
  assert.match(content, /--dax-fn:\s*#7cb8ff;/, "dark --dax-fn token defined");
  assert.match(content, /--dax-keyword:\s*#c792ea;/, "dark --dax-keyword token defined");
  assert.match(content, /--dax-string:\s*#a5d6a7;/, "dark --dax-string token defined");
  assert.match(content, /--dax-table:\s*#f0c27b;/, "dark --dax-table token defined");
  assert.match(content, /--dax-ref:\s*#ffcb8b;/, "dark --dax-ref token defined");
  assert.match(content, /--dax-number:\s*#f78c6c;/, "dark --dax-number token defined");
  assert.match(content, /--dax-comment:\s*var\(--text-3\);/, "dark --dax-comment token defined");

  // Light DAX syntax palette
  assert.match(content, /:root\[data-theme="light"\]\s*{[^}]*--dax-fn:\s*#1f63c6;/, "light --dax-fn token defined");
  assert.match(content, /:root\[data-theme="light"\]\s*{[^}]*--dax-keyword:\s*#8a2fb8;/, "light --dax-keyword token defined");
  assert.match(content, /:root\[data-theme="light"\]\s*{[^}]*--dax-string:\s*#2b7a34;/, "light --dax-string token defined");
  assert.match(content, /:root\[data-theme="light"\]\s*{[^}]*--dax-table:\s*#a45d00;/, "light --dax-table token defined");
  assert.match(content, /:root\[data-theme="light"\]\s*{[^}]*--dax-ref:\s*#b15a00;/, "light --dax-ref token defined");
  assert.match(content, /:root\[data-theme="light"\]\s*{[^}]*--dax-number:\s*#c2410c;/, "light --dax-number token defined");
});

test("Issue #52: app.css consumes DAX tokens, micro-radii, and policy gap scale", () => {
  const content = fs.readFileSync(APP_CSS, "utf8");

  // DAX classes consume tokens
  assert.match(content, /\.dax-fn\s*{\s*color:\s*var\(--dax-fn\);/, ".dax-fn uses token");
  assert.match(content, /\.dax-keyword\s*{\s*color:\s*var\(--dax-keyword\);/, ".dax-keyword uses token");
  assert.match(content, /\.dax-string\s*{\s*color:\s*var\(--dax-string\);/, ".dax-string uses token");
  assert.match(content, /\.dax-table\s*{\s*color:\s*var\(--dax-table\);/, ".dax-table uses token");
  assert.match(content, /\.dax-ref\s*{\s*color:\s*var\(--dax-ref\);/, ".dax-ref uses token");
  assert.match(content, /\.dax-number\s*{\s*color:\s*var\(--dax-number\);/, ".dax-number uses token");
  assert.match(content, /\.dax-comment\s*{\s*color:\s*var\(--dax-comment\);/, ".dax-comment uses token");

  // Micro-radii usage
  assert.match(content, /\.type-glyph-xs\s*{[^}]*border-radius:\s*var\(--r-3xs\);/, ".type-glyph-xs uses var(--r-3xs)");
  assert.match(content, /\.statusbar-progress\s*{[^}]*border-radius:\s*var\(--r-2xs\);/, ".statusbar-progress uses var(--r-2xs)");
  assert.match(content, /\.mx-heat\s*{[^}]*border-radius:\s*var\(--r-3xs\);/, ".mx-heat uses var(--r-3xs)");
  assert.match(content, /\.mx-total-bar\s*{[^}]*border-radius:\s*var\(--r-2xs\);/, ".mx-total-bar uses var(--r-2xs)");

  // Gap scale alignment
  assert.match(content, /\.type-strip\s*{[^}]*gap:\s*var\(--space-2\);/, ".type-strip uses var(--space-2)");
  assert.match(content, /\.action-buttons,\s*\.edit-row\s*{[^}]*gap:\s*var\(--space-2\);/, ".action-buttons uses var(--space-2)");
  assert.match(content, /\.graph-toolbar\s*{[^}]*gap:\s*var\(--space-2\);/, ".graph-toolbar uses var(--space-2)");
});

test("Issue #52: ui-policy.json defines code head typography, tab count badges, and intentional exceptions", () => {
  const policy = JSON.parse(fs.readFileSync(POLICY_JSON, "utf8"));

  // Type rules
  const codeHeadRule = policy.typeRules.find((r) => r.selector.includes(".code-head"));
  assert.ok(codeHeadRule, ".code-head rule present in typeRules");
  assert.deepEqual(codeHeadRule.sizes, [11, 12, 13], ".code-head sizes allow 11, 12, 13px");

  const badgeRule = policy.typeRules.find((r) => r.selector.includes(".ui-tabs-count"));
  assert.ok(badgeRule, ".ui-tabs-count included in badge typeRule");
  assert.ok(badgeRule.sizes.includes(11), "11px allowed for tab count badges");

  // Segmented control exceptions
  const segmentedException = policy.exceptions.find(
    (e) => e.selector.includes(".ui-segmented") && e.rules.includes("control-gap"),
  );
  assert.ok(segmentedException, "segmented control exception present for control-gap");

  // Closed disclosures exception
  const disclosuresException = policy.exceptions.find(
    (e) => e.selector.includes("details:not([open])") && e.rules.includes("control-size"),
  );
  assert.ok(disclosuresException, "closed disclosures exception present");
});

test("Issue #52: CompareGrid Row State column width and sticky offset avoid clipping", () => {
  const gridContent = fs.readFileSync(COMPARE_GRID, "utf8");
  const cssContent = fs.readFileSync(COMPARE_CSS, "utf8");

  // Col 2 width widened to 136px
  assert.match(gridContent, /\[40,\s*260,\s*136,\s*220,\s*132\]/, "CompareGrid Col 2 is 136px");

  // .dc-col-mc pinned left offset updated to 436px
  assert.match(cssContent, /\.dc-col-mc\s*{[^}]*left:\s*436px;/, ".dc-col-mc pinned at left: 436px");
});

test("Issue #52: lint-ui-states.mjs targets correct selectors and handles measurement artefacts", () => {
  const content = fs.readFileSync(LINT_SCRIPT, "utf8");

  // Graph details pane docked aside selector
  assert.match(content, /\.graph-detail-pane/, "lint-ui-states targets .graph-detail-pane");
  assert.doesNotMatch(content, /getByRole\("dialog"\)\.first\(\)\.waitFor/, "lint-ui-states no longer waits for modal dialog on graph details");

  // Merge models nav label
  assert.match(content, /nav\("Merge models"\)/, "lint-ui-states navigates to Merge models");
  assert.doesNotMatch(content, /nav\("Development Center"\)/, "lint-ui-states no longer uses stale Development Center nav text");

  // Disclosures opening & scroll artefact filtering
  assert.match(content, /document\.querySelectorAll\("details:not\(\[open\]\)"\)/, "lint-ui-states opens disclosures before checking page");
});

test("Issue #52: DESIGN.md documents micro-radii and DAX syntax palette", () => {
  const content = fs.readFileSync(DESIGN_MD, "utf8");

  // Frontmatter
  assert.match(content, /"2xs":\s*"2px"/, "DESIGN.md defines 2xs radius in frontmatter");
  assert.match(content, /"3xs":\s*"3px"/, "DESIGN.md defines 3xs radius in frontmatter");
  assert.match(content, /dax-fn-dark:\s*"#7cb8ff"/, "DESIGN.md defines dax-fn-dark");

  // Markdown sections
  assert.match(content, /### DAX Syntax Palette/, "DESIGN.md contains DAX Syntax Palette section");
  assert.match(content, /--r-2xs/, "DESIGN.md documents --r-2xs micro-radius");
  assert.match(content, /--r-3xs/, "DESIGN.md documents --r-3xs micro-radius");
});
