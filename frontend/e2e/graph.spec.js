import { test, expect } from "@playwright/test";

// The toolbar keeps display options and filters in popovers (visual contract §11.1).
const openDisplay = (page) => page.getByRole("button", { name: /^Display/ }).click();
const openFilters = (page) => page.getByRole("button", { name: /^Filters/ }).click();
const openTypes = (page) => page.getByRole("button", { name: /^Types/ }).click();
// The details pane docks beside the canvas: a complementary region, not a dialog.
const detailsPane = (page) => page.locator(".graph-detail-pane");
async function chooseObjects(page, value) {
  if (!(await page.getByLabel("Objects", { exact: true }).isVisible().catch(() => false))) await openFilters(page);
  await page.getByLabel("Objects", { exact: true }).selectOption(value);
}

async function openGraph(page) {
  await page.goto("/");
  await page.getByRole("button", { name: "Graph", exact: true }).click();
  await expect(page.locator(".react-flow__node-brain").first()).toBeVisible();
  await page.getByRole("tab", { name: "Lineage", exact: true }).click();
  await openDisplay(page);
  await page.getByRole("checkbox", { name: "Include suggestions" }).check();
  await page.getByRole("checkbox", { name: "Group by ownership" }).check();
  await page.keyboard.press("Escape");
}

test("native graph separates ownership, keeps cross-links, and opens a right-side detail sheet", async ({ page, request }) => {
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const graph = await (await request.get("/api/graph")).json();
  const measure = graph.nodes.find((node) => node.type === "MEASURE" && node.name === "Net Sales");
  await openGraph(page);
  await page.getByRole("tab", { name: "Lineage", exact: true }).click();
  await expect(page.locator(".react-flow__node-artifactGroup")).toHaveCount(new Set(graph.nodes.map((node) => node.artifact_group)).size);
  await expect(page.locator(".react-flow__node-brain")).toHaveCount(graph.nodes.length);
  await expect(page.locator(".react-flow__edge")).toHaveCount(graph.edges.length);
  const regions = await page.locator(".react-flow__node-artifactGroup").evaluateAll((elements) => elements.map((element) => { const box = element.getBoundingClientRect(); return { x: box.x, y: box.y, right: box.right, bottom: box.bottom }; }));
  expect(regions[0].bottom <= regions[1].y || regions[1].bottom <= regions[0].y || regions[0].right <= regions[1].x || regions[1].right <= regions[0].x).toBeTruthy();
  const node = page.locator(`.react-flow__node-brain[data-id="${measure.id}"]`);
  await node.click();
  const details = detailsPane(page);
  await expect(details.getByRole("heading", { name: "Net Sales", exact: true })).toBeVisible();
  await expect(details.getByText("SUM('Sales'[Amount])", { exact: true })).toBeVisible();
  expect((await details.boundingBox()).x).toBeGreaterThan(900);
  await details.getByRole("tab", { name: "Lineage", exact: true }).click();
  await expect(details.getByRole("button", { name: /Sales Target/ })).toBeVisible();
  await details.getByRole("button", { name: /Sales Target/ }).click();
  await expect(details.getByRole("heading", { name: "Sales Target", exact: true })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(details).toHaveCount(0);
  await openDisplay(page);
  await page.getByLabel("Layout", { exact: true }).selectOption("TB");
  await expect(page.locator(".react-flow__node-brain")).toHaveCount(graph.nodes.length);
  await page.screenshot({ path: "test-results/graph-grouped.png", fullPage: true });
  expect(errors).toEqual([]);
});

test("filters compose on the server, clear cleanly, and show empty states", async ({ page }) => {
  await openGraph(page);
  await page.getByRole("tab", { name: "Lineage", exact: true }).click();
  await chooseObjects(page, "report");
  await expect(page.locator(".react-flow__node-artifactGroup")).toHaveCount(2);
  await expect(page.locator(".artifact-group-title").filter({ hasText: "Report objects" })).toContainText("Report objects");
  await page.keyboard.press("Escape");
  // The Types popover is the colour key and the type filter in one: "Only" keeps a single type.
  await openTypes(page);
  await page.getByRole("button", { name: "Show only Visual", exact: true }).click();
  await page.keyboard.press("Escape");
  await expect(page.locator(".react-flow__node-brain")).toHaveCount(2);
  await page.getByRole("searchbox", { name: "Filter graph objects" }).fill("Sales by region");
  await expect(page.locator(".react-flow__node-brain")).toHaveCount(1);
  await expect(page.locator(".flow-node-name")).toHaveText("Sales by region");
  await openFilters(page);
  await page.getByLabel("Status", { exact: true }).selectOption("rejected");
  await expect(page.getByRole("heading", { name: "No matching objects" })).toBeVisible();
  await page.getByRole("button", { name: "Clear filters", exact: true }).first().click();
  await expect(page.locator(".react-flow__node-artifactGroup")).toHaveCount(2);
  await expect(page.getByRole("searchbox", { name: "Filter graph objects" })).toHaveValue("");
  if (!(await page.getByLabel("Distance", { exact: true }).isVisible().catch(() => false))) await openFilters(page);
  await expect(page.getByLabel("Distance", { exact: true })).toBeDisabled();
  await page.keyboard.press("Escape");
  await openTypes(page);
  await expect(page.getByRole("checkbox", { name: "Visual", exact: true })).toBeChecked();
  await expect(page.getByRole("checkbox", { name: "Measure", exact: true })).toBeChecked();
});

test("project color mapping persists through reload and drives nodes, minimap, and legend", async ({ page, request }) => {
  const original = await (await request.get("/api/config")).json();
  try {
    await page.goto("/");
    await page.getByRole("button", { name: "Settings", exact: true }).click();
    await page.getByRole("tab", { name: "Graph colors", exact: true }).click();
    await page.getByText("Customize colors", { exact: true }).click();
    await page.getByRole("textbox", { name: "Report objects hex color", exact: true }).fill("#f472b6");
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
    // The minimap appears only for graphs of more than 30 objects, so pad the real graph with
    // unconnected columns; the two visuals still carry the saved colour.
    // Lineage reads the whole-scope payload (/api/lineage); the other views read /api/graph.
    const graphRequests = /\/api\/(graph|lineage)(\?|$)/;
    await page.route(graphRequests, async (route) => {
      const body = await (await route.fetch()).json();
      const filler = Array.from({ length: 30 }, (_, index) => ({ id: `filler-${index}`, name: `Filler ${index}`, type: "COLUMN", status: "factual", artifact_group: "model" }));
      await route.fulfill({ json: { ...body, nodes: [...body.nodes, ...filler], total_nodes: (body.total_nodes || body.nodes.length) + filler.length } });
    });
    await page.getByRole("button", { name: "Graph", exact: true }).click();
    await expect(page.locator(".react-flow__node-brain").first()).toBeVisible();
    await page.getByRole("tab", { name: "Lineage", exact: true }).click();
    const visual = page.locator('.flow-node[data-type="VISUAL"]').first();
    await expect(visual.locator(".type-glyph")).toHaveCSS("color", "rgb(52, 211, 153)");
    await expect.poll(() => page.locator(".react-flow__minimap-node:not(.minimap-artifact-group)").evaluateAll((elements) => elements.filter((element) => getComputedStyle(element).fill === "rgb(52, 211, 153)").length)).toBe(2);
    await openTypes(page);
    await expect(page.getByLabel("Graph color legend").locator(".graph-type-row").filter({ hasText: "Visual" }).locator(".type-glyph")).toHaveCSS("color", "rgb(52, 211, 153)");
    await page.keyboard.press("Escape");
    await page.unroute(graphRequests);
    await page.getByRole("button", { name: "Settings", exact: true }).click();
    await page.getByRole("tab", { name: "Graph colors", exact: true }).click();
    await page.getByText("Customize colors", { exact: true }).click();
    await page.getByRole("button", { name: "Restore defaults", exact: true }).click();
    await expect(page.getByRole("textbox", { name: "Report objects hex color", exact: true })).toHaveValue("#e68ac0");
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
  const details = detailsPane(page);
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
  await page.getByRole("tab", { name: "Lineage", exact: true }).click();
  await page.route("**/api/graph?**", async (route) => {
    if (new URL(route.request().url()).searchParams.get("artifact") === "report") return route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ error: "Graph unavailable for test" }) });
    return route.continue();
  });
  await chooseObjects(page, "report");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("heading", { name: "Graph unavailable", exact: true })).toBeVisible();
  await expect(page.locator(".react-flow__node-brain")).toHaveCount(0);
  await page.unroute("**/api/graph?**");
  await page.getByRole("button", { name: "Retry graph", exact: true }).click();
  await expect(page.locator(".react-flow__node-artifactGroup")).toHaveCount(2);
  await page.route("**/api/objects/**", async (route) => route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ error: "Details unavailable for test" }) }));
  await page.locator(".react-flow__node-brain").first().click();
  await expect(detailsPane(page).getByRole("alert")).toContainText("Details unavailable for test");
  await page.unroute("**/api/objects/**");
  await page.getByRole("button", { name: "Retry details", exact: true }).click();
  await expect(detailsPane(page).getByRole("alert")).toHaveCount(0);
});

test("late graph and object responses cannot overwrite a newer selection", async ({ page, request }) => {
  await openGraph(page);
  await page.getByRole("tab", { name: "Lineage", exact: true }).click();
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
  await chooseObjects(page, "report");
  await expect.poll(() => Boolean(releaseGraph)).toBe(true);
  await chooseObjects(page, "model");
  await page.keyboard.press("Escape");
  await expect(page.locator(".artifact-group-title")).toHaveText(/Model artifacts/);
  releaseGraph(); await graphDone;
  await expect(page.locator(".artifact-group-title")).toHaveText(/Model artifacts/);
  await page.unroute("**/api/graph?**");
  await openTypes(page);
  await page.getByRole("button", { name: "Show only Measure", exact: true }).click();
  await page.keyboard.press("Escape");
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
  const details = detailsPane(page);
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
  await page.getByRole("searchbox", { name: "Search objects", exact: true }).fill("Net Sales");
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

test("lane chips list lanes in dependency order and switch a lane off in Lineage and Matrix", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Graph", exact: true }).click();
  await page.getByRole("tab", { name: "Lineage", exact: true }).click();
  const chips = page.getByRole("toolbar", { name: "Lanes, in dependency order" }).getByRole("button");
  await expect(chips.first()).toContainText("Models");
  const labels = await chips.allTextContents();
  const order = ["Models", "Tables", "Columns", "Calculations", "Visuals", "Pages", "Reports"];
  expect(labels.map((text) => order.findIndex((lane) => text.startsWith(lane)))).toEqual([...labels.keys()].map((index) => index));
  await expect(page.locator('.flow-node[data-type="MEASURE"]')).not.toHaveCount(0);
  await chips.filter({ hasText: "Calculations" }).click();
  await expect(chips.filter({ hasText: "Calculations" })).toHaveAttribute("aria-pressed", "false");
  await expect(page.locator('.flow-node[data-type="MEASURE"]')).toHaveCount(0);
  // The visuals still trace back to the columns their measures used.
  await page.locator(".react-flow__node-brain").filter({ hasText: "Target card" }).click();
  await expect(page.locator(".react-flow__node-brain:not(.is-dimmed)").filter({ hasText: "Amount" })).toHaveCount(1);
  await page.getByRole("tab", { name: "Matrix", exact: true }).click();
  await expect(page.locator(".mx-object-row")).toHaveCount(2);
  await expect(page.locator(".mx-object-row").filter({ hasText: "Net Sales" })).toHaveCount(0);
});
