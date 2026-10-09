import { test, expect } from "@playwright/test";

async function openOverview(page) {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  await page.getByRole("button", { name: "Graph", exact: true }).click();
  await expect(page.getByRole("tab", { name: "Overview", exact: true })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("button", { name: "Expand Sales", exact: true })).toBeVisible();
  await expect(page.locator(".react-flow__edge")).toHaveCount(2);
  await expect(page.locator(".graph-zoom-value")).toHaveText("100%");
}

const nodePositions = (page) => page.locator(".react-flow__node-brain").evaluateAll((nodes) => Object.fromEntries(nodes.map((node) => [node.dataset.id, node.style.transform])));
const viewportTransform = (page) => page.locator(".react-flow__viewport").evaluate((node) => node.style.transform);

test("native overview unfolds one owner without moving existing objects or changing zoom", async ({ page, request }) => {
  const graph = await (await request.get("/api/graph?status=factual&limit=80")).json();
  await openOverview(page);
  const visible = await page.locator(".react-flow__node-brain").count();
  expect(visible).toBeLessThan(graph.nodes.length);
  await expect(page.locator(".graph-summary")).toContainText("in collapsed groups");
  await page.screenshot({ path: "test-results/graph-overview.png", fullPage: true });
  await page.getByRole("button", { name: "Zoom in", exact: true }).click();
  await expect(page.locator(".graph-zoom-value")).not.toHaveText("100%");
  const positions = await nodePositions(page);
  const viewport = await viewportTransform(page);
  await page.getByRole("button", { name: "Expand Sales", exact: true }).click();
  await expect(page.getByRole("button", { name: "Collapse Sales", exact: true })).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByRole("button", { name: "Select Net Sales", exact: true })).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(await viewportTransform(page)).toBe(viewport);
  const unfolded = await nodePositions(page);
  for (const [id, position] of Object.entries(positions)) expect(unfolded[id]).toBe(position);
  await page.getByRole("button", { name: "Collapse Sales", exact: true }).click();
  await expect(page.getByRole("button", { name: "Select Net Sales", exact: true })).toHaveCount(0);
  expect(await viewportTransform(page)).toBe(viewport);
});

test("nested report groups expand by keyboard and overview survives an Inspector visit", async ({ page }) => {
  await openOverview(page);
  const report = page.getByRole("button", { name: "Expand Sales report", exact: true });
  await report.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("button", { name: "Expand Overview page", exact: true })).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByRole("button", { name: "Expand Overview page", exact: true }).click();
  await expect(page.getByRole("button", { name: "Select Sales by region", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Expand Sales", exact: true }).click();
  const positions = await nodePositions(page);
  await page.getByRole("button", { name: "Select Net Sales", exact: true }).click();
  await page.getByRole("button", { name: /Full inspector/ }).click();
  await expect(page.getByRole("heading", { name: "Net Sales", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Back to graph", exact: true }).click();
  await expect(page.getByRole("tab", { name: "Overview", exact: true })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("button", { name: "Collapse Sales report", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Collapse Overview page", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Select Sales by region", exact: true })).toBeVisible();
  expect(await nodePositions(page)).toEqual(positions);
});

test("connections follow native edges and can expand a neighborhood", async ({ page, request }) => {
  const graph = await (await request.get("/api/graph?status=factual&limit=80")).json();
  const measure = graph.nodes.find((node) => node.name === "Net Sales" && node.type === "MEASURE");
  await openOverview(page);
  await page.getByRole("button", { name: "Expand Sales", exact: true }).click();
  await page.getByRole("button", { name: "Select Net Sales", exact: true }).dblclick();
  await expect(page.getByRole("tab", { name: "Connections", exact: true })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByText("Focused view", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Close", exact: true }).click();
  const focused = await (await request.get(`/api/graph?status=factual&center_id=${encodeURIComponent(measure.id)}&depth=1&limit=80`)).json();
  await expect(page.locator(".react-flow__edge")).toHaveCount(focused.edges.length);
  const edgeNames = await page.locator(".react-flow__edge").evaluateAll((edges) => edges.map((edge) => edge.getAttribute("aria-label")));
  expect(edgeNames).toContain("Sales Target Depends on Net Sales");
  expect(edgeNames).toContain("Net Sales References Amount");
  const initialCount = await page.locator(".react-flow__node-brain").count();
  await page.getByRole("button", { name: "Expand connections", exact: true }).click();
  await expect.poll(() => page.locator(".react-flow__node-brain").count()).toBeGreaterThan(initialCount);
  await page.getByRole("button", { name: "Back to project", exact: true }).click();
  await expect(page.getByRole("tab", { name: "Overview", exact: true })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("button", { name: "Collapse Sales", exact: true })).toBeVisible();
});

test("a dense loaded slice starts compact, keeps counts honest, and retains the optional full graph", async ({ page }) => {
  // Large-slice renderer check. Native persistence is covered by the tests above.
  const nodes = [{ id: "model", name: "Commercial model", type: "MODEL", status: "factual", artifact_group: "model" }];
  const edges = [];
  for (const [index, name] of ["Sales", "Customers", "Products", "Calendar", "Targets"].entries()) {
    const id = `table-${index}`;
    nodes.push({ id, name, type: "TABLE", status: "factual", artifact_group: "model" });
    edges.push({ id: `owner-${id}`, from_id: "model", to_id: id, type: "CONTAINS", evidence_class: "FACT" });
    for (let field = 1; field <= 12; field++) {
      const childId = `${id}-field-${field}`;
      nodes.push({ id: childId, name: `${name} field ${field}`, type: field > 8 ? "MEASURE" : "COLUMN", status: "factual", artifact_group: "model" });
      edges.push({ id: `owner-${childId}`, from_id: id, to_id: childId, type: "CONTAINS", evidence_class: "FACT" });
    }
  }
  nodes.push({ id: "report", name: "Commercial dashboard", type: "REPORT", status: "factual", artifact_group: "report" });
  edges.push({ id: "report-model", from_id: "report", to_id: "model", type: "USES_MODEL", evidence_class: "FACT" });
  nodes.push({ id: "page", name: "Sales overview", type: "PAGE", status: "factual", artifact_group: "report" });
  edges.push({ id: "report-page", from_id: "report", to_id: "page", type: "CONTAINS", evidence_class: "FACT" });
  for (let visual = 1; visual <= 12; visual++) {
    const id = `visual-${visual}`;
    nodes.push({ id, name: `Revenue chart ${visual}`, type: "VISUAL", status: "factual", artifact_group: "report", properties: { visual_type: "columnChart" } });
    edges.push({ id: `page-${id}`, from_id: "page", to_id: id, type: "CONTAINS", evidence_class: "FACT" });
    edges.push({ id: `usage-${id}`, from_id: id, to_id: `table-0-field-${visual}`, type: "USES", evidence_class: "FACT" });
  }
  await page.route("**/api/graph?**", (route) => route.fulfill({ json: { nodes, edges, total_nodes: 400, truncated: true } }));
  await page.goto("/");
  await page.getByRole("button", { name: "Graph", exact: true }).click();
  await expect(page.locator(".react-flow__node-brain")).toHaveCount(7);
  await expect(page.locator(".react-flow__edge")).toHaveCount(6);
  await expect(page.locator(".graph-summary")).toContainText("80 of 400 matching objects loaded");
  await expect(page.getByRole("button", { name: "Expand Sales", exact: true })).toHaveAttribute("title", "12 loaded objects inside");
  const readable = await page.locator(".flow-node-name").evaluateAll((labels) => labels.every((label) => label.getBoundingClientRect().height >= 12));
  expect(readable).toBe(true);
  await page.screenshot({ path: "test-results/graph-dense-overview.png", fullPage: true });
  await page.getByRole("tab", { name: "Full graph", exact: true }).click();
  await expect(page.locator(".react-flow__node-brain")).toHaveCount(nodes.length);
  await expect(page.locator(".react-flow__edge")).toHaveCount(edges.length);
  await page.getByRole("tab", { name: "Overview", exact: true }).click();
  await expect(page.locator(".react-flow__node-brain")).toHaveCount(7);
});

test("small screens retain readable group controls without page overflow", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  await page.getByRole("button", { name: "Graph", exact: true }).click();
  const group = page.getByRole("button", { name: "Expand Sales", exact: true });
  await expect(group).toBeVisible();
  expect((await group.boundingBox()).height).toBeGreaterThanOrEqual(22);
  await group.focus();
  await page.keyboard.press("Space");
  await expect(page.getByRole("button", { name: "Collapse Sales", exact: true })).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: "test-results/graph-explorer-mobile.png", fullPage: true });
});

test("an explicit relationship filter stays visible in overview", async ({ page }) => {
  await openOverview(page);
  await page.locator(".graph-filter-details > summary").click();
  await page.getByLabel("Relationship", { exact: true }).selectOption("REFERENCES");
  await expect(page.locator(".react-flow__edge")).toHaveCount(1);
  const relationship = page.getByRole("img", { name: "Net Sales References Amount", exact: true });
  await expect(relationship).toBeAttached();
  // A straight vertical SVG path has zero-width bounds but still draws a line.
  await expect.poll(() => relationship.locator(".react-flow__edge-path").evaluate((path) => path.getTotalLength())).toBeGreaterThan(0);
  await page.getByRole("checkbox", { name: "Relationship labels", exact: true }).check();
  await expect(relationship).toBeVisible();
  await expect(relationship.locator(".react-flow__edge-text")).toHaveText("References");
  await expect(page.getByRole("tab", { name: "Overview", exact: true })).toHaveAttribute("aria-selected", "true");
});
