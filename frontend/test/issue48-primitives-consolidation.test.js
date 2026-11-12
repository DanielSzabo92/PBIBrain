import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const SRC = fileURLToPath(new URL("../src/", import.meta.url));

test("Issue #48: Primitives consolidation (ContextMenu, Breadcrumb, Skeleton, Accordion, Sonner)", async () => {
  const contextMenuCode = await readFile(path.join(SRC, "components/ui/context-menu.jsx"), "utf8");
  assert.ok(contextMenuCode.includes("ContextMenuTrigger"), "ContextMenuTrigger is exported");
  assert.ok(contextMenuCode.includes("ContextMenuContent"), "ContextMenuContent is exported");
  assert.ok(contextMenuCode.includes("ContextMenuItem"), "ContextMenuItem is exported");

  const breadcrumbCode = await readFile(path.join(SRC, "components/ui/breadcrumb.jsx"), "utf8");
  assert.ok(breadcrumbCode.includes("BreadcrumbList"), "BreadcrumbList is exported");
  assert.ok(breadcrumbCode.includes("BreadcrumbItem"), "BreadcrumbItem is exported");
  assert.ok(breadcrumbCode.includes("BreadcrumbLink"), "BreadcrumbLink is exported");
  assert.ok(breadcrumbCode.includes("BreadcrumbPage"), "BreadcrumbPage is exported");

  const skeletonCode = await readFile(path.join(SRC, "components/ui/skeleton.jsx"), "utf8");
  assert.ok(skeletonCode.includes("function Skeleton"), "Skeleton is exported");

  const toastCode = await readFile(path.join(SRC, "components/ui/toast.jsx"), "utf8");
  assert.ok(toastCode.includes("sonnerToast"), "toast.jsx unifies on sonner");
  assert.ok(toastCode.includes("ToastProvider"), "ToastProvider is exported");
});

test("Issue #48: Graph canvas nodes have ContextMenu with required actions", async () => {
  const graphCode = await readFile(path.join(SRC, "components/GraphView.jsx"), "utf8");

  assert.ok(graphCode.includes("ContextMenu"), "GraphView imports ContextMenu");
  assert.ok(graphCode.includes("Open in Inspector"), "ContextMenu provides 'Open in Inspector'");
  assert.ok(graphCode.includes("Focus"), "ContextMenu provides 'Focus'");
  assert.ok(graphCode.includes("Copy name"), "ContextMenu provides 'Copy name'");
  assert.ok(graphCode.includes("Copy DAX"), "ContextMenu provides 'Copy DAX'");
});

test("Issue #48: Native <details> elements are completely eliminated", async () => {
  const appCode = await readFile(path.join(SRC, "App.jsx"), "utf8");
  const graphColorsCode = await readFile(path.join(SRC, "components/GraphColors.jsx"), "utf8");

  assert.ok(!appCode.includes("<details"), "App.jsx contains no native <details>");
  assert.ok(!graphColorsCode.includes("<details"), "GraphColors.jsx contains no native <details>");

  assert.ok(appCode.includes("<Disclosure"), "App.jsx uses Disclosure for collapsible sections");
  assert.ok(graphColorsCode.includes("<Disclosure"), "GraphColors.jsx uses Disclosure");
});

test("Issue #48: Status color harmonization (Renamed is consistent info tone)", async () => {
  const stateCellCode = await readFile(path.join(SRC, "devcenter/components/StateCell.jsx"), "utf8");
  assert.ok(
    stateCellCode.includes('if (key === "renamed" || key === "moved") return "info";'),
    "StateCell maps renamed and moved to info tone"
  );

  const rowDetailCode = await readFile(path.join(SRC, "devcenter/components/CompareRowDetail.jsx"), "utf8");
  assert.ok(
    rowDetailCode.includes("stateTone(row.row_state)"),
    "CompareRowDetail uses stateTone(row.row_state) for consistent tone"
  );
});

test("Issue #48: Switch knob and Repoint combobox fixes", async () => {
  const devcenterCss = await readFile(path.join(SRC, "devcenter/devcenter.css"), "utf8");

  // Switch knob off state is clean in light theme
  assert.ok(
    devcenterCss.includes(".ui-switch-thumb") && devcenterCss.includes("var(--surface)"),
    "devcenter.css uses --surface for switch thumb so off knob is light in light theme"
  );

  // Combobox input full width to prevent floating chevron
  assert.ok(
    devcenterCss.includes(".ui-combobox-input") && devcenterCss.includes("width: 100%"),
    "devcenter.css sets .ui-combobox-input width: 100% to keep chevron positioned correctly"
  );
});

test("Issue #48: Design tokens for graph colors and radius", async () => {
  const themeCss = await readFile(path.join(SRC, "theme.css"), "utf8");
  const appCss = await readFile(path.join(SRC, "app.css"), "utf8");
  const graphPresentation = await readFile(path.join(SRC, "graphPresentation.js"), "utf8");

  // Tokens in theme.css
  assert.ok(themeCss.includes("--radius-full: 9999px;"), "theme.css defines --radius-full");
  assert.ok(themeCss.includes("--artifact-report:"), "theme.css defines --artifact-report");
  assert.ok(themeCss.includes("--artifact-model:"), "theme.css defines --artifact-model");
  assert.ok(themeCss.includes("--artifact-other:"), "theme.css defines --artifact-other");

  // Lane chip off-token 13px radius migrated to token
  assert.ok(!appCss.includes("border-radius: 13px;"), "app.css eliminated off-token 13px border-radius");
  assert.ok(appCss.includes("var(--radius-full)"), "app.css uses var(--radius-full) for lane-chip");

  // Graph presentation uses CSS tokens
  assert.ok(graphPresentation.includes("var(--artifact-report"), "graphPresentation uses --artifact-report token");
  assert.ok(graphPresentation.includes("var(--artifact-model"), "graphPresentation uses --artifact-model token");
  assert.ok(graphPresentation.includes("var(--artifact-other"), "graphPresentation uses --artifact-other token");
});
