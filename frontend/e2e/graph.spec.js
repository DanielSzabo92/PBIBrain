import { test, expect } from "@playwright/test";

async function openGraph(page) {
  await page.goto("/");
  await page.getByRole("button", { name: "Graph", exact: true }).click();
  await expect(page.locator(".react-flow__node-brain").first()).toBeVisible();
  await page.getByRole("tab", { name: "Full graph", exact: true }).click();
  await page.getByRole("checkbox", { name: "Include suggestions" }).check();
  await page.getByRole("checkbox", { name: "Group by ownership" }).check();
  await page.locator(".graph-filter-details > summary").click();
}

test("native graph separates ownership, keeps cross-links, and opens a right-side detail sheet", async ({ page, request }) => {
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const graph = await (await request.get("/api/graph")).json();
  const measure = graph.nodes.find((node) => node.type === "MEASURE" && node.name === "Net Sales");
  await openGraph(page);
  await page.getByRole("tab", { name: "Full graph", exact: true }).click();
  await expect(page.locator(".react-flow__node-artifactGroup")).toHaveCount(new Set(graph.nodes.map((node) => node.artifact_group)).size);
  await expect(page.locator(".react-flow__node-brain")).toHaveCount(graph.nodes.length);
  await expect(page.locator(".react-flow__edge")).toHaveCount(graph.edges.length);
  const regions = await page.locator(".react-flow__node-artifactGroup").evaluateAll((elements) => elements.map((element) => { const box = element.getBoundingClientRect(); return { x: box.x, y: box.y, right: box.right, bottom: box.bottom }; }));
  expect(regions[0].bottom <= regions[1].y || regions[1].bottom <= regions[0].y || regions[0].right <= regions[1].x || regions[1].right <= regions[0].x).toBeTruthy();
  const node = page.locator(`.react-flow__node-brain[data-id="${measure.id}"]`);
  await node.click();
  const details = page.getByRole("dialog");
  await expect(details.getByRole("heading", { name: "Net Sales", exact: true })).toBeVisible();
  await expect(details.getByText("SUM('Sales'[Amount])", { exact: true })).toBeVisible();
  expect((await details.boundingBox()).x).toBeGreaterThan(900);
  await details.getByRole("tab", { name: "Lineage", exact: true }).click();
  await expect(details.getByRole("button", { name: /Sales Target/ })).toBeVisible();
  await details.getByRole("button", { name: /Sales Target/ }).click();
  await expect(details.getByRole("heading", { name: "Sales Target", exact: true })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(details).toHaveCount(0);
  await page.getByLabel("Layout", { exact: true }).selectOption("TB");
  await expect(page.locator(".react-flow__node-brain")).toHaveCount(graph.nodes.length);
  await page.screenshot({ path: "test-results/graph-grouped.png", fullPage: true });
  expect(errors).toEqual([]);
});

test("filters compose on the server, clear cleanly, and show empty states", async ({ page }) => {
  await openGraph(page);
  await page.getByRole("tab", { name: "Full graph", exact: true }).click();
  await page.getByRole("tab", { name: "Report", exact: true }).click();
  await expect(page.locator(".react-flow__node-artifactGroup")).toHaveCount(2);
  await expect(page.locator(".artifact-group-title").filter({ hasText: "Report artifacts" })).toContainText("Report artifacts");
  await page.getByLabel("Object type", { exact: true }).selectOption("VISUAL");
  await expect(page.locator(".react-flow__node-brain")).toHaveCount(2);
  await page.getByRole("searchbox", { name: "Filter graph objects" }).fill("Sales by region");
  await expect(page.locator(".react-flow__node-brain")).toHaveCount(1);
  await expect(page.locator(".flow-node-name")).toHaveText("Sales by region");
  await page.getByLabel("Status", { exact: true }).selectOption("rejected");
  await expect(page.getByRole("heading", { name: "No matching objects" })).toBeVisible();
  await page.getByRole("button", { name: "Clear filters", exact: true }).first().click();
  await expect(page.locator(".react-flow__node-artifactGroup")).toHaveCount(2);
  await expect(page.getByRole("searchbox", { name: "Filter graph objects" })).toHaveValue("");
  await expect(page.getByLabel("Distance", { exact: true })).toBeDisabled();
});

test("project color mapping persists through reload and drives nodes, minimap, and legend", async ({ page, request }) => {
  const original = await (await request.get("/api/config")).json();
  try {
    await page.goto("/");
    await page.getByRole("button", { name: "Settings", exact: true }).click();
    await page.getByRole("tab", { name: "Graph colors", exact: true }).click();
    await page.getByText("Customize colors", { exact: true }).click();
    await page.getByRole("textbox", { name: "Report artifacts hex color", exact: true }).fill("#f472b6");
    await page.getByRole("textbox", { name: "Visual hex color", exact: true }).fill("#34d399");
    await page.getByRole("button", { name: "Save colors", exact: true }).click();
    await expect(page.getByRole("button", { name: "Save colors", exact: true })).toBeDisabled();
    const saved = await (await request.get("/api/config")).json();
    expect(saved.graph_colors.groups.report).toBe("#f472b6");
    expect(saved.graph_colors.types.VISUAL).toBe("#34d399");
    expect(saved.sources).toEqual(original.sources);
    expect(saved.database).toEqual(original.database);
    await page.reload();
    await page.getByRole("button", { name: "Settings", exact: true }).click();
    await page.getByRole("tab", { name: "Graph colors", exact: true }).click();
    await page.getByText("Customize colors", { exact: true }).click();
    await expect(page.getByRole("textbox", { name: "Visual hex color", exact: true })).toHaveValue("#34d399");
    await page.getByRole("button", { name: "Graph", exact: true }).click();
    await expect(page.locator(".react-flow__node-brain").first()).toBeVisible();
  await page.getByRole("tab", { name: "Full graph", exact: true }).click();
    const visual = page.locator(".artifact-node").filter({ has: page.locator(".flow-node-type", { hasText: /^Column Chart$/ }) }).first();
    await expect(visual.locator(".artifact-dot")).toHaveCSS("background-color", "rgb(52, 211, 153)");
    await expect.poll(() => page.locator(".react-flow__minimap-node:not(.minimap-artifact-group)").evaluateAll((elements) => elements.filter((element) => getComputedStyle(element).fill === "rgb(52, 211, 153)").length)).toBe(2);
    await expect(page.getByLabel("Graph color legend").getByText("Visual", { exact: true }).locator(".artifact-dot")).toHaveCSS("background-color", "rgb(52, 211, 153)");
    await page.getByRole("button", { name: "Settings", exact: true }).click();
    await page.getByRole("tab", { name: "Graph colors", exact: true }).click();
    await page.getByText("Customize colors", { exact: true }).click();
    await page.getByRole("button", { name: "Restore defaults", exact: true }).click();
    await expect(page.getByRole("textbox", { name: "Report artifacts hex color", exact: true })).toHaveValue("#b4a0cd");
    await page.getByRole("button", { name: "Save colors", exact: true }).click();
    await expect(page.getByRole("button", { name: "Save colors", exact: true })).toBeDisabled();
    await page.screenshot({ path: "test-results/graph-settings.png", fullPage: true });
  } finally {
    await request.post("/api/config", { data: original });
  }
});

test("keyboard selection opens details and narrow layouts stay within the viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openGraph(page);
  const node = page.locator(".react-flow__node-brain").first();
  await expect(node).toHaveAttribute("role", "button");
  await expect(node).toHaveAttribute("tabindex", "0");
  await node.focus();
  await page.keyboard.press("Enter");
  const details = page.getByRole("dialog");
  await expect(details).toBeVisible();
  expect((await details.boundingBox()).width).toBeLessThanOrEqual(390);
  await details.getByRole("button", { name: "Close", exact: true }).click();
  await expect(details).toHaveCount(0);
  await node.focus();
  await page.keyboard.press("Space");
  await expect(details).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(details).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  await page.screenshot({ path: "test-results/graph-mobile.png", fullPage: true });
  await page.getByRole("button", { name: "Settings", exact: true }).click();
    await page.getByRole("tab", { name: "Graph colors", exact: true }).click();
    await page.getByText("Customize colors", { exact: true }).click();
  await expect(page.getByText("Graph colors", { exact: true }).last()).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
});

test("failed graph and object requests expose retry without showing another scope", async ({ page }) => {
  await openGraph(page);
  await page.getByRole("tab", { name: "Full graph", exact: true }).click();
  await page.route("**/api/graph?**", async (route) => {
    if (new URL(route.request().url()).searchParams.get("artifact") === "report") return route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ error: "Graph unavailable for test" }) });
    return route.continue();
  });
  await page.getByRole("tab", { name: "Report", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Graph unavailable", exact: true })).toBeVisible();
  await expect(page.locator(".react-flow__node-brain")).toHaveCount(0);
  await page.unroute("**/api/graph?**");
  await page.getByRole("button", { name: "Retry graph", exact: true }).click();
  await expect(page.locator(".react-flow__node-artifactGroup")).toHaveCount(2);
  await page.route("**/api/objects/**", async (route) => route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ error: "Details unavailable for test" }) }));
  await page.locator(".react-flow__node-brain").first().click();
  await expect(page.getByRole("dialog").getByRole("alert")).toContainText("Details unavailable for test");
  await page.unroute("**/api/objects/**");
  await page.getByRole("button", { name: "Retry details", exact: true }).click();
  await expect(page.getByRole("dialog").getByRole("alert")).toHaveCount(0);
});

test("late graph and object responses cannot overwrite a newer selection", async ({ page, request }) => {
  await openGraph(page);
  await page.getByRole("tab", { name: "Full graph", exact: true }).click();
  let releaseGraph;
  let graphFinished;
  const graphDone = new Promise((resolve) => { graphFinished = resolve; });
  await page.route("**/api/graph?**", async (route) => {
    if (new URL(route.request().url()).searchParams.get("artifact") !== "report") return route.continue();
    const response = await route.fetch();
    await new Promise((resolve) => { releaseGraph = resolve; });
    await route.fulfill({ response });
    graphFinished();
  });
  await page.getByRole("tab", { name: "Report", exact: true }).click();
  await expect.poll(() => Boolean(releaseGraph)).toBe(true);
  await page.getByRole("tab", { name: "Model", exact: true }).click();
  await expect(page.locator(".artifact-group-title")).toHaveText(/Model artifacts/);
  releaseGraph(); await graphDone;
  await expect(page.locator(".artifact-group-title")).toHaveText(/Model artifacts/);
  await page.unroute("**/api/graph?**");
  await page.getByLabel("Object type", { exact: true }).selectOption("MEASURE");
  await expect(page.locator(".react-flow__node-brain")).toHaveCount(2);
  const graph = await (await request.get("/api/graph?object_type=MEASURE")).json();
  const first = graph.nodes.find((node) => node.name === "Net Sales");
  const second = graph.nodes.find((node) => node.name === "Sales Target");
  let releaseObject;
  let objectFinished;
  const objectDone = new Promise((resolve) => { objectFinished = resolve; });
  await page.route("**/api/objects/**", async (route) => {
    if (!decodeURIComponent(route.request().url()).endsWith(first.id)) return route.continue();
    const response = await route.fetch();
    await new Promise((resolve) => { releaseObject = resolve; });
    await route.fulfill({ response });
    objectFinished();
  });
  await page.locator(`.react-flow__node-brain[data-id="${first.id}"]`).click();
  await expect.poll(() => Boolean(releaseObject)).toBe(true);
  await page.locator(`.react-flow__node-brain[data-id="${second.id}"]`).click();
  const details = page.getByRole("dialog");
  await expect(details.getByText("[Net Sales] * 2", { exact: true })).toBeVisible();
  releaseObject(); await objectDone;
  await expect(details.getByRole("heading", { name: "Sales Target", exact: true })).toBeVisible();
  await expect(details.getByText("[Net Sales] * 2", { exact: true })).toBeVisible();
});

test("shared shadcn controls preserve search, full inspector, review, and source settings", async ({ page, request }) => {
  const original = await (await request.get("/api/config")).json();
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await expect(page.locator('[data-slot="card"]')).not.toHaveCount(0);
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await page.getByRole("searchbox", { name: "Search the brain", exact: true }).fill("Net Sales");
  await page.locator(".search-result").filter({ has: page.locator(".result-type", { hasText: "Measure" }) }).first().click();
  await expect(page.getByRole("heading", { name: "Net Sales", exact: true }).first()).toBeVisible();
  await expect(page.getByText("SUM('Sales'[Amount])", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: /Show in graph/ }).click();
  await expect(page.getByText("Focused view", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: /^Review queue/ }).click();
  await expect(page.getByRole("navigation").getByRole("button", { name: /^Review queue/ })).toHaveAttribute("aria-current", "page");
  await expect(page.locator(".review-purpose")).toContainText("Approval");
  await page.getByRole("button", { name: "Settings", exact: true }).click();
    await page.getByRole("tab", { name: "Graph colors", exact: true }).click();
    await page.getByText("Customize colors", { exact: true }).click();
  await page.getByRole("tab", { name: "Project", exact: true }).click();
  await expect(page.getByLabel("Project name", { exact: true })).toHaveValue(original.name);
  await expect(page.getByRole("textbox", { name: "Source 1", exact: true })).toHaveValue(original.sources[0]);
  await expect(page.getByLabel("Brain database", { exact: false })).toHaveCount(0);
  await page.screenshot({ path: "test-results/project-settings.png", fullPage: true });
  expect(errors).toEqual([]);
});
