import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const SRC = fileURLToPath(new URL("../src/", import.meta.url));

function linear(channel) {
  const v = channel / 255;
  return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
}

function luminance(hex) {
  const clean = hex.replace("#", "");
  const r = Number.parseInt(clean.slice(0, 2), 16);
  const g = Number.parseInt(clean.slice(2, 4), 16);
  const b = Number.parseInt(clean.slice(4, 6), 16);
  return 0.2126 * linear(r) + 0.7152 * linear(g) + 0.0722 * linear(b);
}

function contrastRatio(hex1, hex2) {
  const l1 = luminance(hex1);
  const l2 = luminance(hex2);
  const [high, low] = l1 > l2 ? [l1, l2] : [l2, l1];
  return (high + 0.05) / (low + 0.05);
}

test("Issue #49: GraphView resolves axe nested-interactive violation and lintapple label-consistency", async () => {
  const code = await readFile(path.join(SRC, "components/GraphView.jsx"), "utf8");

  // 1. Group nodes must use role="group" so the nested button.graph-group-toggle is not an axe violation
  assert.ok(
    code.includes('ariaRole: isGroup ? "group" : "button"') ||
    code.includes("ariaRole: isGroup ? 'group' : 'button'"),
    "Group nodes must use role='group' rather than role='button'"
  );

  assert.ok(
    code.includes("inside") && (code.includes("${count} inside") || code.includes("count inside")),
    "nodeLabel must include visible count inside text in the accessible name"
  );
  assert.ok(
    code.includes("nodeLabel(node, warning, isGroup)"),
    "nodeLabel must receive isGroup to include count inside"
  );

  // 3. graph-group-toggle must use a Tooltip primitive, not relying on title attribute
  assert.ok(
    code.includes("<Tooltip content={`${count} loaded objects inside`}>"),
    "graph-group-toggle must be wrapped in a Tooltip component"
  );
  assert.ok(
    !code.includes('className="graph-group-toggle nodrag nopan" aria-label={`${node.explorerExpanded ? "Collapse" : "Expand"} ${name}`} aria-expanded={node.explorerExpanded} title='),
    "graph-group-toggle must not rely on title attribute alone"
  );
});

test("Issue #49: Icon-only controls use Tooltip primitives", async () => {
  const appCode = await readFile(path.join(SRC, "App.jsx"), "utf8");

  // 1. Dev Center sidebar rail at narrow widths has tooltip
  assert.ok(
    appCode.includes('className={`nav-button ${view === key ? "active" : ""} ${key === "config" ? "nav-settings" : ""}`} tooltip={`${label} (${keys})`}') ||
    appCode.includes('tooltip={`${label} (${keys})`}') && appCode.includes("sidebar-nav"),
    "Sidebar rail nav buttons must always provide a tooltip for narrow rail widths"
  );

  // 2. Titlebar Chat button uses tooltip and aria-label rather than title
  assert.ok(
    appCode.includes('className="titlebar-chat"') &&
    appCode.includes('tooltip={`Chat (${displayKeys(shortcutKeys("chat"))})`}') &&
    appCode.includes('aria-label={`Chat (${displayKeys(shortcutKeys("chat"))})`}'),
    "Titlebar chat button must provide tooltip and aria-label"
  );

  // 3. Sidebar collapse button uses tooltip
  assert.ok(
    appCode.includes('className="sidebar-collapse"') &&
    appCode.includes('tooltip={`${sidebarCollapsed ? "Expand" : "Collapse"} side bar (${displayKeys("Ctrl+B")})`}'),
    "Sidebar collapse button must provide tooltip"
  );
});

test("Issue #49: Dev Center placeholder contrast meets WCAG AA (>= 4.5:1) and controls meet 24px target size", async () => {
  const themeCss = await readFile(path.join(SRC, "theme.css"), "utf8");
  const compareCss = await readFile(path.join(SRC, "devcenter/components/compare.css"), "utf8");
  const gridCode = await readFile(path.join(SRC, "devcenter/components/CompareGrid.jsx"), "utf8");

  // 1. --placeholder token defined in theme.css
  const darkPlaceholderMatch = themeCss.match(/--placeholder:\s*(#[0-9a-fA-F]+);/);
  assert.ok(darkPlaceholderMatch, "--placeholder token must be defined in dark theme");
  const darkPlaceholder = darkPlaceholderMatch[1];

  const lightBlock = themeCss.slice(themeCss.indexOf(':root[data-theme="light"]'));
  const lightPlaceholderMatch = lightBlock.match(/--placeholder:\s*(#[0-9a-fA-F]+);/);
  assert.ok(lightPlaceholderMatch, "--placeholder token must be defined in light theme");
  const lightPlaceholder = lightPlaceholderMatch[1];

  // Contrast check: Light theme surface-2 is #fafaf8
  const lightRatio = contrastRatio(lightPlaceholder, "#fafaf8");
  assert.ok(
    lightRatio >= 4.5,
    `Light theme placeholder ${lightPlaceholder} on #fafaf8 must meet WCAG AA >= 4.5:1 (got ${lightRatio.toFixed(2)})`
  );

  // Contrast check: Dark theme surface-2 is #1a1a1d
  const darkRatio = contrastRatio(darkPlaceholder, "#1a1a1d");
  assert.ok(
    darkRatio >= 4.5,
    `Dark theme placeholder ${darkPlaceholder} on #1a1a1d must meet WCAG AA >= 4.5:1 (got ${darkRatio.toFixed(2)})`
  );

  // 2. .dc-search-input has ::placeholder color: var(--placeholder)
  assert.ok(
    compareCss.includes(".dc-search-input::placeholder") &&
    compareCss.includes("color: var(--placeholder)"),
    ".dc-search-input::placeholder must set color: var(--placeholder)"
  );

  // 3. Row checkboxes have 24px minimum touch/click target and focus ring
  assert.ok(
    compareCss.includes(".dc-col-chk input[type=\"checkbox\"]") &&
    compareCss.includes("min-width: 24px") &&
    compareCss.includes("min-height: 24px"),
    "Row checkboxes must have minimum 24px by 24px target size"
  );
  assert.ok(
    compareCss.includes(".dc-col-chk input[type=\"checkbox\"]:focus-visible") &&
    compareCss.includes("outline: 2px solid var(--brand)"),
    "Row checkboxes must have visible focus ring"
  );

  // 4. Row checkboxes have tabIndex={0}
  assert.ok(
    gridCode.includes('tabIndex={0}') && gridCode.includes('aria-label={t("compare.select_row", { name: row.name })}'),
    "Row checkboxes must have tabIndex={0} instead of -1"
  );

  // 5. Header buttons (.dc-hcell-btn) have min-height: 24px
  assert.ok(
    compareCss.includes(".dc-hcell-btn") &&
    compareCss.includes("min-height: 24px"),
    ".dc-hcell-btn must have min-height: 24px"
  );
  assert.ok(
    compareCss.includes(".dc-hcell-btn:focus-visible"),
    ".dc-hcell-btn must have focus-visible styling"
  );
});

test("Issue #49: Search inputs clear on Esc when text present, and blur when empty", async () => {
  const appCode = await readFile(path.join(SRC, "App.jsx"), "utf8");
  const gridCode = await readFile(path.join(SRC, "devcenter/components/CompareGrid.jsx"), "utf8");
  const inputCode = await readFile(path.join(SRC, "components/ui/input.jsx"), "utf8");

  // 1. SearchView in App.jsx
  assert.ok(
    appCode.includes('event.key === "Escape"') &&
    appCode.includes('if (query) change({ query: "" }); else event.target.blur();'),
    "SearchView must clear query if present or blur input if empty on Escape"
  );

  // 2. CompareGrid search input
  assert.ok(
    gridCode.includes('e.key === "Escape"') &&
    gridCode.includes('if (q) {') &&
    gridCode.includes('setQ("");') &&
    gridCode.includes('e.target.blur();'),
    "CompareGrid search input must clear q if present or blur input if empty on Escape"
  );

  // 3. Input primitive supports search Esc clearing and blurring
  assert.ok(
    inputCode.includes('type === "search"') &&
    inputCode.includes('event.key === "Escape"') &&
    inputCode.includes('event.target.blur()'),
    "Input primitive must support search Esc clearing and blurring"
  );
});

test("Issue #49: Grid keyboard shortcuts help popover and aria-keyshortcuts attributes", async () => {
  const gridCode = await readFile(path.join(SRC, "devcenter/components/CompareGrid.jsx"), "utf8");
  const stateCellCode = await readFile(path.join(SRC, "devcenter/components/StateCell.jsx"), "utf8");
  const appShellCode = await readFile(path.join(SRC, "components/AppShell.jsx"), "utf8");

  // 1. GridShortcutsHelp component exists and announces required shortcuts: D, M, Space, Enter, diff, F5
  assert.ok(gridCode.includes("function GridShortcutsHelp()"), "GridShortcutsHelp component must exist");
  assert.ok(gridCode.includes('"D"') && gridCode.includes("code diff"), "GridShortcutsHelp must announce D for diff");
  assert.ok(gridCode.includes('"M"') && gridCode.includes("bulk merge"), "GridShortcutsHelp must announce M for bulk choices");
  assert.ok(gridCode.includes('"Space"') && gridCode.includes("row selection"), "GridShortcutsHelp must announce Space for selection");
  assert.ok(gridCode.includes('"Enter"') && gridCode.includes("row details"), "GridShortcutsHelp must announce Enter for row details");
  assert.ok(gridCode.includes('"F5"') && gridCode.includes("Reload"), "GridShortcutsHelp must announce F5 for reload");

  // 2. GridShortcutsHelp is rendered in the toolbar
  assert.ok(gridCode.includes("<GridShortcutsHelp />"), "GridShortcutsHelp must be rendered in the toolbar");

  // 3. Grid controls have aria-keyshortcuts
  assert.ok(gridCode.includes('aria-keyshortcuts="Space"'), "Row checkbox must have aria-keyshortcuts='Space'");
  assert.ok(gridCode.includes('aria-keyshortcuts="Control+A"'), "Header checkbox must have aria-keyshortcuts='Control+A'");
  assert.ok(gridCode.includes('aria-keyshortcuts="k"'), "Keep button must have aria-keyshortcuts='k'");
  assert.ok(gridCode.includes('aria-keyshortcuts="t"'), "Take button must have aria-keyshortcuts='t'");
  assert.ok(gridCode.includes('aria-keyshortcuts="s"'), "Skip button must have aria-keyshortcuts='s'");
  assert.ok(stateCellCode.includes('aria-keyshortcuts={state !== "same" && onOpenDiff ? "d" : undefined}'), "StateCell must declare aria-keyshortcuts='d' when diff is available");

  // 4. AppShell ShortcutsDialog includes Compare grid section and documents F5
  assert.ok(appShellCode.includes('<section aria-label="Compare grid">'), "ShortcutsDialog must include Compare grid section");
  assert.ok(appShellCode.includes("<dt>Reload project data</dt><dd><kbd>F5</kbd></dd>"), "ShortcutsDialog must document F5 reload");
});
