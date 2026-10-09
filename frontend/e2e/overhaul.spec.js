import { test, expect } from "@playwright/test";
import { mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const noInternals = async (page) => {
  const text = await page.locator("main").innerText();
  expect(text).not.toMatch(/(?:model|table|report|semantic|edge):[\w-]|Canonical ID|Source ID|source_hash|raw_metadata|"extractor"|\{"/);
};

test("Inspector starts with browsable measures and keeps browse filters on return", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Inspector", exact: true }).click();
  await expect(page.locator(".search-result")).toHaveCount(2);
  await expect(page.getByLabel("Search object type")).toHaveValue("MEASURE");
  await page.locator(".search-result").filter({ hasText: "Net Sales" }).click();
  await expect(page.getByRole("region", { name: "DAX formula" })).toContainText("SUM('Sales'[Amount])");
  await noInternals(page);
  await page.getByRole("button", { name: "Browse objects", exact: true }).click();
  await expect(page.locator(".search-result")).toHaveCount(2);
  await page.getByLabel("Search object type").selectOption("COLUMN");
  await expect(page.locator(".search-result").first()).toContainText("Amount");
  await noInternals(page);
});

test("search has a clear focus boundary and respects reduced motion", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  const input = page.getByRole("searchbox", { name: "Search the brain" });
  await input.fill("Net Sales");
  await expect(page.locator(".search-result").first()).toBeVisible();
  await expect(input).toBeFocused();
  await expect(input).toHaveCSS("box-shadow", "none");
  await expect(page.locator(".search-field")).toHaveCSS("box-shadow", "none");
  await expect(page.locator(".search-field")).toHaveCSS("border-top-width", "0px");
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect(page.locator(".field-beam")).toHaveCount(0);
  await expect(input).toHaveCSS("outline-style", "solid");
  await expect(input).toHaveCSS("transition-duration", "0s");
  await noInternals(page);
  await page.screenshot({ path: "test-results/overhaul-search.png", fullPage: true });
});

test("graph defaults to source objects and isolates a selected neighborhood", async ({ page, request }) => {
  const graph = await (await request.get("/api/graph?status=factual&limit=30")).json();
  await page.goto("/");
  await page.getByRole("button", { name: "Graph", exact: true }).click();
  await expect.poll(() => page.locator(".react-flow__node-brain").count()).toBeLessThan(graph.nodes.length);
  await expect(page.locator(".flow-node-name").filter({ hasText: "Sales" }).first()).toBeVisible();
  await expect(page.getByRole("checkbox", { name: "Include suggestions" })).not.toBeChecked();
  await page.getByRole("tab", { name: "Full graph", exact: true }).click();
  await expect(page.locator(".react-flow__node-brain")).toHaveCount(graph.nodes.length);
  const measure = graph.nodes.find((node) => node.name === "Net Sales");
  await page.locator(`.react-flow__node-brain[data-id="${measure.id}"]`).dblclick();
  await expect(page.getByText("Focused view", { exact: true })).toBeVisible();
  await expect.poll(() => page.locator(".react-flow__node-brain").count()).toBeLessThan(graph.nodes.length);
  await noInternals(page);
  await page.getByRole("button", { name: "Back to project", exact: true }).click();
  await expect(page.locator(".react-flow__node-brain")).toHaveCount(graph.nodes.length);
  await expect(page.getByRole("tab", { name: "Full graph", exact: true })).toHaveAttribute("aria-selected", "true");
  await page.screenshot({ path: "test-results/overhaul-graph.png", fullPage: true });
});

test("palette selection persists without changing project sources", async ({ page, request }) => {
  const original = await (await request.get("/api/config")).json();
  try {
    await page.goto("/");
    await page.getByRole("button", { name: "Settings", exact: true }).click();
    await page.getByRole("tab", { name: "Graph colors", exact: true }).click();
    await page.getByRole("button", { name: /^Coast/ }).click();
    await page.getByRole("button", { name: "Save colors", exact: true }).click();
    await expect(page.getByRole("status")).toHaveText("Colors saved");
    const saved = await (await request.get("/api/config")).json();
    expect(saved.sources).toEqual(original.sources);
    expect(saved.graph_colors.types.MEASURE).toBe("#d0bf99");
    await page.reload();
    await page.getByRole("button", { name: "Settings", exact: true }).click();
    await page.getByRole("tab", { name: "Graph colors", exact: true }).click();
    await expect(page.getByRole("button", { name: /^Coast/ })).toHaveAttribute("aria-pressed", "true");
    await page.screenshot({ path: "test-results/overhaul-palettes.png", fullPage: true });
  } finally { await request.post("/api/config", { data: original }); }
});

test("review explains evidence, aligns targets left, prevents double submit, and persists decisions", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("navigation").getByRole("button", { name: /^Review queue/ }).click();
  await expect(page.locator(".review-item").first()).toBeVisible();
  const before = await page.locator(".review-item").count();
  await expect(page.locator(".review-target").first()).toHaveCSS("justify-content", "flex-start");
  await expect(page.locator(".review-evidence").first()).toContainText("Description:");
  await noInternals(page);
  let release;
  await page.route("**/api/review", async (route) => { await new Promise((resolve) => { release = resolve; }); await route.continue(); });
  const approve = page.locator(".review-item").first().getByRole("button", { name: "Approve", exact: true });
  await approve.click();
  await expect(approve).toBeDisabled();
  await expect.poll(() => Boolean(release)).toBe(true);
  release();
  await expect(page.locator(".review-item")).toHaveCount(before - 1);
  await expect(page.getByRole("status")).toHaveText("Suggestion approved");
  await expect(page.locator(".toast")).toHaveCount(0, { timeout: 5000 });
  await page.reload();
  await page.getByRole("navigation").getByRole("button", { name: /^Review queue/ }).click();
  await expect(page.locator(".review-item")).toHaveCount(before - 1);
  await page.screenshot({ path: "test-results/overhaul-review.png", fullPage: true });
});

test("review evidence and palettes remain usable on a narrow screen", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  for (const name of ["Inspector", "Review queue", "Settings"]) {
    await page.getByRole("navigation").getByRole("button", { name: new RegExp(`^${name}`) }).click();
    await expect(page.getByRole("navigation").getByRole("button", { name: new RegExp(`^${name}`) })).toHaveAttribute("aria-current", "page");
    await expect(page.getByRole("heading", { name: name === "Inspector" ? "Browse objects" : name, level: 1, exact: true })).toHaveCount(1);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    if (name === "Review queue") await expect(page.locator(".review-evidence").first()).toBeVisible();
    if (name === "Settings") await page.getByRole("tab", { name: "Graph colors", exact: true }).click();
    await page.screenshot({ path: `test-results/overhaul-${name.replace(" ", "-")}-mobile.png`, fullPage: true });
  }
});

test("failed decisions remain reviewable and command buttons work without WebGL", async ({ page }) => {
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.addInitScript(() => {
    const original = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (kind, ...args) { return kind.includes("webgl") ? null : original.call(this, kind, ...args); };
  });
  await page.goto("/");
  await page.getByRole("button", { name: /Open review queue/ }).click();
  await expect(page.locator(".review-item").first()).toBeVisible();
  const before = await page.locator(".review-item").count();
  await page.route("**/api/review", (route) => route.fulfill({ status: 500, json: { error: "Decision interrupted" } }));
  const first = page.locator(".review-item").first();
  await first.getByRole("button", { name: "Reject", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Review failed");
  await expect(page.locator(".review-item")).toHaveCount(before);
  await expect(first.getByRole("button", { name: "Approve", exact: true })).toBeEnabled();
  await page.unroute("**/api/review");
  await first.getByRole("button", { name: "Reject", exact: true }).click();
  await expect(page.locator(".review-item")).toHaveCount(before - 1);
  expect(errors).toEqual([]);
});

test("large native scans start bounded and search finds objects beyond the first slice", async ({ page, request }) => {
  test.setTimeout(60000);
  const original = await (await request.get("/api/config")).json();
  const folder = await mkdtemp(path.join(tmpdir(), "pbibrain-large-ui-"));
  const source = path.join(folder, "large-model.json");
  await writeFile(source, JSON.stringify({ models: [{ id: "capacity", name: "Capacity planning", tables: [{ id: "plans", name: "Plans", columns: [{ id: "amount", name: "Amount", dataType: "Double" }], measures: Array.from({ length: 180 }, (_, index) => ({ id: `scenario-${index}`, name: `Scenario ${String(index).padStart(3, "0")}`, expression: `SUM('Plans'[Amount]) * ${index + 1}` })) }] }] }));
  try {
    expect((await request.post("/api/config", { data: { ...original, sources: [source] } })).ok()).toBe(true);
    expect((await request.post("/api/scan", { data: {} })).ok()).toBe(true);
    await page.goto("/");
    await page.getByRole("button", { name: "Graph", exact: true }).click();
    await page.getByRole("tab", { name: "Full graph", exact: true }).click();
    await expect(page.locator(".react-flow__node-brain")).toHaveCount(80);
    await expect(page.locator(".scope-notice")).toContainText("80 of 183");
    await page.getByRole("searchbox", { name: "Filter graph objects" }).fill("Scenario 174");
    await expect(page.locator(".react-flow__node-brain")).toHaveCount(1);
    await expect(page.locator(".flow-node-name")).toHaveText("Scenario 174");
    await page.locator(".react-flow__node-brain").dblclick();
    await expect(page.getByText("Focused view", { exact: true })).toBeVisible();
    await expect(page.locator(".react-flow__node-brain")).toHaveCount(3);
    await noInternals(page);
    await page.screenshot({ path: "test-results/overhaul-large-focused.png", fullPage: true });
  } finally {
    await request.post("/api/config", { data: original });
    await request.post("/api/scan", { data: {} });
  }
});

test("dark default and flat selection remain clear during keyboard navigation", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "light" });
  await page.goto("/");
  await expect(page.locator("html")).toHaveClass("dark");
  await expect(page.locator("html")).toHaveCSS("color-scheme", "dark");
  await expect(page.locator("body")).toHaveCSS("background-color", "rgb(11, 12, 15)");
  const background = (control) => control.evaluate((node) => getComputedStyle(node).backgroundColor);
  const navigation = page.getByRole("navigation");
  expect(await background(navigation.locator('[aria-current="page"]'))).not.toBe(await background(navigation.getByRole("button", { name: "Graph", exact: true })));
  await navigation.getByRole("button", { name: "Settings", exact: true }).click();
  const tabs = page.getByRole("tablist", { name: "Settings sections" });
  const colors = tabs.getByRole("tab", { name: "Graph colors" });
  const project = tabs.getByRole("tab", { name: "Project", exact: true });
  expect(await background(colors)).not.toBe(await background(project));
  await colors.focus();
  await page.keyboard.press("ArrowLeft");
  await expect(project).toBeFocused();
  await expect(project).toHaveAttribute("aria-selected", "true");
  expect(await background(project)).not.toBe(await background(colors));
  await page.screenshot({ path: "test-results/dark-settings.png", fullPage: true });
});

test("native scan exposes full report hierarchy and matching visual bindings", async ({ page, request }) => {
  test.setTimeout(60000);
  const original = await (await request.get("/api/config")).json();
  const folder = await mkdtemp(path.join(tmpdir(), "pbibrain-hierarchy-ui-"));
  const source = path.join(folder, "hierarchy.json");
  const fixture = JSON.parse(execFileSync("python", ["-c", "import json; from tests.test_report_hierarchy import hierarchy_sources; m,r=hierarchy_sources(); print(json.dumps({'models':[m], 'reports':[r]}))"], { cwd: fileURLToPath(new URL("../..", import.meta.url)), encoding: "utf8" }));
  await writeFile(source, JSON.stringify(fixture));
  try {
    expect((await request.post("/api/config", { data: { ...original, sources: [source] } })).ok()).toBe(true);
    expect((await request.post("/api/scan", { data: {} })).ok()).toBe(true);
    const graph = await (await request.get("/api/graph?status=factual&limit=80")).json();
    const visual = graph.nodes.find((node) => node.type === "VISUAL");
    expect(visual.name).toBe("Revenue trend");
    const details = await (await request.get("/api/objects/" + encodeURIComponent(visual.id))).json();
    expect(details.object.properties.unresolved_field_refs).toEqual([]);
    const groups = ["columns", "measures", "calculations", "visual_filters", "page_filters", "report_filters"];
    for (const group of groups) expect(details.visual_bindings[group]).toHaveLength(1);
    await page.goto("/");
    await page.getByRole("button", { name: "Graph", exact: true }).click();
  await page.getByRole("tab", { name: "Full graph", exact: true }).click();
    await expect(page.locator(".react-flow__node-brain")).toHaveCount(graph.nodes.length);
    const card = page.locator(".react-flow__node-brain").filter({ hasText: "Revenue trend" });
    await expect(card).toContainText("Line Chart");
    await page.getByRole("tab", { name: "Report", exact: true }).click();
    await expect(page.locator(".flow-node-name").filter({ hasText: /^Unused/ })).toHaveCount(0);
    await card.click();
    await expect(page.locator(".react-flow__edge-textbg").first()).toHaveCSS("fill", "rgb(24, 26, 31)");
    await expect(page.locator(".react-flow__edge-text").first()).toHaveCSS("fill", "rgb(237, 237, 240)");
    const sheet = page.locator(".graph-detail-sheet");
    await expect(sheet.locator(".visual-bindings .detail-section")).toHaveCount(6);
    await expect(sheet.locator(".graph-detail-body")).toHaveCSS("overflow-x", "hidden");
    for (const group of groups) await expect(sheet.locator(".visual-bindings")).toContainText(details.visual_bindings[group][0].name);
    await sheet.getByRole("button", { name: "Revenue", exact: true }).click();
    await expect(sheet.locator(".graph-detail-title")).toHaveText("Revenue");
    await sheet.getByRole("button", { name: "Close", exact: true }).click();
    await card.click();
    await sheet.getByRole("button", { name: /Full inspector/ }).click();
    await expect(page.locator(".object-workspace .visual-bindings .detail-section")).toHaveCount(6);
    await page.locator(".object-workspace .visual-bindings").getByRole("button", { name: "Running revenue", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Running revenue", exact: true })).toBeVisible();
    await page.getByRole("navigation").getByRole("button", { name: /^Review queue/ }).click();
    const canonical = await (await request.get("/api/review")).json();
    const items = canonical.items || canonical;
    await expect(page.locator(".review-item")).toHaveCount(items.length);
    const targets = await page.locator(".review-target").allTextContents();
    expect(new Set(targets).size).toBe(targets.length);
    await expect(page.locator(".review-evidence").first()).toContainText("Description:");
    await page.screenshot({ path: "test-results/native-hierarchy-review.png", fullPage: true });
  } finally {
    await request.post("/api/config", { data: original });
    await request.post("/api/scan", { data: {} });
  }
});

test("shared meaning suggestions keep separate decisions through reload and rescan", async ({ page, request }) => {
  test.setTimeout(60000);
  const original = await (await request.get("/api/config")).json();
  const folder = await mkdtemp(path.join(tmpdir(), "pbibrain-shared-review-"));
  const source = path.join(folder, "shared.json");
  const fixture = JSON.parse(execFileSync("python", ["-c", "import json; from tests.test_shared_semantic_review import SOURCE; print(json.dumps(SOURCE))"], { cwd: fileURLToPath(new URL("../..", import.meta.url)), encoding: "utf8" }));
  await writeFile(source, JSON.stringify(fixture));
  try {
    expect((await request.post("/api/config", { data: { ...original, sources: [source] } })).ok()).toBe(true);
    expect((await request.post("/api/scan", { data: {} })).ok()).toBe(true);
    await page.goto("/");
    await page.getByRole("navigation").getByRole("button", { name: /^Review queue/ }).click();
    const revenue = page.locator(".review-item").filter({ has: page.locator(".review-target strong", { hasText: /^Revenue$/ }) });
    await expect(revenue).toHaveCount(2);
    await revenue.first().getByRole("button", { name: "Approve", exact: true }).click();
    await expect(revenue).toHaveCount(1);
    const pending = (await (await request.get("/api/review")).json()).filter((row) => row.value === "Revenue");
    expect(pending).toHaveLength(1);
    await page.reload();
    await page.getByRole("navigation").getByRole("button", { name: /^Review queue/ }).click();
    await expect(revenue).toHaveCount(1);
    expect((await request.post("/api/scan", { data: {} })).ok()).toBe(true);
    const rescanned = (await (await request.get("/api/review")).json()).filter((row) => row.value === "Revenue");
    expect(rescanned.map((row) => row.candidate_id)).toEqual(pending.map((row) => row.candidate_id));
    await page.reload();
    await page.getByRole("navigation").getByRole("button", { name: /^Review queue/ }).click();
    await revenue.getByRole("button", { name: "Reject", exact: true }).click();
    await expect(revenue).toHaveCount(0);
  } finally {
    await request.post("/api/config", { data: original });
    await request.post("/api/scan", { data: {} });
  }
});

test("flat controls remain usable across navigation, graph, details, Inspector and Settings", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  const check = async () => {
    await expect(page.locator('.metal-fx-root, .metal-button, .field-beam')).toHaveCount(0);
    expect(await page.getByRole("searchbox").evaluateAll((nodes) => nodes.every((node) => node.tagName === "INPUT" && node.checkVisibility()))).toBe(true);
    const button = page.getByRole("navigation").getByRole("button").first();
    await page.keyboard.press("Tab");
    await button.focus();
    await expect(button).toBeFocused();
    expect(await button.evaluate((node) => getComputedStyle(node).outlineStyle)).toBe("solid");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  };
  await check();
  for (const name of ["Search", "Inspector", "Review queue", "Settings", "Graph"]) {
    await page.getByRole("navigation").getByRole("button", { name: new RegExp("^" + name) }).click();
    await check();
  }
  await page.getByRole("tab", { name: "Full graph", exact: true }).click();
  await page.locator(".react-flow__node-brain").filter({ hasText: "Net Sales" }).click();
  await expect(page.locator(".graph-detail-title")).toHaveText("Net Sales");
  await check();
  await page.getByRole("button", { name: "Close", exact: true }).click();
});
