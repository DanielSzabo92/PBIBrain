import { test, expect } from "@playwright/test";

test("home search returns to the same results and keyboard focus without refetching", async ({ page }) => {
  const errors = [];
  let searches = 0;
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("request", (request) => { if (request.url().includes("/api/search?")) searches += 1; });
  await page.goto("/");
  await expect(page.getByLabel("Find an object", { exact: true })).toBeVisible();
  await page.screenshot({ path: "test-results/product-home.png", fullPage: true });
  await page.getByLabel("Find an object", { exact: true }).fill("Net Sales");
  await page.getByLabel("Find an object", { exact: true }).press("Enter");
  const result = page.locator(".search-result").filter({ has: page.locator(".result-type", { hasText: "Measure" }) }).first();
  await expect(result).toBeVisible();
  const baseline = searches;
  await result.click();
  await expect(page.getByRole("heading", { name: "Net Sales", exact: true }).first()).toBeVisible();
  await expect(page.getByRole("region", { name: "Dependencies", exact: true }).getByRole("button", { name: /Amount/ })).toBeVisible();
  const usedBy = page.getByRole("region", { name: "Used by", exact: true });
  await expect(usedBy.getByRole("button", { name: /Sales Target/ })).toBeVisible();
  await expect(usedBy.getByRole("button", { name: /Sales by region/ })).toBeVisible();
  await expect(page.getByText("Canonical ID", { exact: true })).toHaveCount(0);
  await expect(page.getByText("SUM('Sales'[Amount])", { exact: true })).toBeVisible();
  await page.screenshot({ path: "test-results/product-inspector.png", fullPage: true });
  await page.getByRole("button", { name: "Back to results" }).click();
  await expect(page.getByRole("searchbox", { name: "Search the brain" })).toHaveValue("Net Sales");
  await expect(result).toBeFocused();
  expect(searches).toBe(baseline);
  await page.getByRole("button", { name: "Reload Brain", exact: true }).click();
  await expect.poll(() => searches).toBeGreaterThan(baseline);
  await expect(result).toBeVisible();
  expect(errors).toEqual([]);
});

test("source setup opens project settings and empty projects have one next step", async ({ page }) => {
  await page.route("**/api/overview", async (route) => {
    const response = await route.fetch();
    const data = await response.json();
    return route.fulfill({ json: { ...data, counts: { nodes: 0, edges: 0 }, models: 0, reports: 0, candidate_count: 0, scan_state: "not_scanned" } });
  });
  await page.route("**/api/config", async (route) => {
    const response = await route.fetch();
    return route.fulfill({ json: { ...await response.json(), sources: [] } });
  });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Add your project sources", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Scan sources", exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Add sources", exact: true }).click();
  await expect(page.getByRole("tab", { name: "Project", exact: true })).toHaveAttribute("aria-selected", "true");
  await page.unroute("**/api/config");
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Ready for the first scan", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Scan sources", exact: true })).toBeEnabled();
});

test("search scopes, late responses, and retry never show another query's results", async ({ page }) => {
  let release;
  let finished;
  const done = new Promise((resolve) => { finished = resolve; });
  await page.route("**/api/search?**", async (route) => {
    const q = new URL(route.request().url()).searchParams.get("q");
    if (q === "Net Sales") {
      const response = await route.fetch();
      await new Promise((resolve) => { release = resolve; });
      await route.fulfill({ response }); finished(); return;
    }
    if (q === "fail search") return route.fulfill({ status: 500, json: { error: "Search interrupted" } });
    return route.continue();
  });
  await page.goto("/");
  await page.getByRole("navigation").getByRole("button", { name: "Search", exact: true }).click();
  const input = page.getByRole("searchbox", { name: "Search the brain" });
  await input.fill("Net Sales");
  await expect.poll(() => Boolean(release)).toBe(true);
  await input.fill("Target");
  await expect(page.locator(".search-result")).not.toHaveCount(0);
  const ids = await page.locator(".search-result").evaluateAll((nodes) => nodes.map((node) => node.dataset.resultId));
  release(); await done;
  expect(await page.locator(".search-result").evaluateAll((nodes) => nodes.map((node) => node.dataset.resultId))).toEqual(ids);
  await input.fill("fail search");
  await expect(page.getByRole("alert")).toContainText("Search interrupted");
  await expect(page.locator(".search-result")).toHaveCount(0);
  await page.unroute("**/api/search?**");
  await page.getByRole("button", { name: "Retry search", exact: true }).click();
  await expect(page.getByText("No matches", { exact: true })).toBeVisible();
  await input.fill("Sales");
  await page.getByLabel("Report", { exact: true }).selectOption({ label: "Sales report" });
  await expect(page.locator(".search-result")).not.toHaveCount(0);
  await page.locator(".search-result").first().click();
  await page.getByRole("button", { name: "Back to results" }).click();
  await expect(page.getByLabel("Report", { exact: true })).toHaveValue("report:sales-report");
  await page.getByRole("button", { name: "Clear filters", exact: true }).click();
  await expect(page.getByLabel("Report", { exact: true })).toHaveValue("");
});

test("inspector retries failed objects and does not claim empty lineage while loading", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Find an object", { exact: true }).fill("Net Sales");
  await page.getByLabel("Find an object", { exact: true }).press("Enter");
  await page.route("**/api/objects/**", (route) => route.fulfill({ status: 500, json: { error: "Object interrupted" } }));
  await page.locator(".search-result").filter({ has: page.locator(".result-type", { hasText: "Measure" }) }).first().click();
  await expect(page.getByRole("heading", { name: "Object unavailable", exact: true })).toBeVisible();
  await expect(page.getByText("No direct uses recorded.", { exact: true })).toHaveCount(0);
  await page.unroute("**/api/objects/**");
  let release;
  await page.route("**/api/objects/**", async (route) => {
    const response = await route.fetch();
    await new Promise((resolve) => { release = resolve; });
    await route.fulfill({ response });
  });
  await page.getByRole("button", { name: "Retry object", exact: true }).click();
  await expect(page.getByText("Loading object details…", { exact: true })).toBeVisible();
  await expect(page.getByText("No direct uses recorded.", { exact: true })).toHaveCount(0);
  await expect.poll(() => Boolean(release)).toBe(true);
  release();
  await expect(page.getByRole("heading", { name: "Net Sales", exact: true })).toBeVisible();
  await expect(page.getByRole("region", { name: "Used by", exact: true }).getByRole("button", { name: /Sales Target/ })).toBeVisible();
});

test("home, search, and readable formulas fit narrow screens with reduced motion", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  await expect(page.getByLabel("Find an object", { exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await page.screenshot({ path: "test-results/product-home-mobile.png", fullPage: true });
  await page.getByLabel("Find an object", { exact: true }).fill("Net Sales");
  await page.getByLabel("Find an object", { exact: true }).press("Enter");
  await expect(page.locator(".search-result").first()).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await page.locator(".search-result").filter({ has: page.locator(".result-type", { hasText: "Measure" }) }).first().click();
  await expect(page.getByRole("region", { name: "DAX formula", exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await page.screenshot({ path: "test-results/product-inspector-mobile.png", fullPage: true });
  await expect(page.getByText("Canonical ID", { exact: true })).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
});

test("more results appends real API pages and survives an inspector visit", async ({ page }) => {
  let failMore = true;
  await page.route("**/api/search?**", (route) => {
    const url = new URL(route.request().url());
    if (url.searchParams.get("offset") === "2" && failMore) {
      failMore = false;
      return route.fulfill({ status: 500, json: { error: "Next page interrupted" } });
    }
    url.searchParams.set("limit", "2");
    return route.continue({ url: url.toString() });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await page.getByRole("searchbox", { name: "Search the brain" }).fill("Sales");
  await expect(page.locator(".search-result")).toHaveCount(2);
  const firstId = await page.locator(".search-result").first().getAttribute("data-result-id");
  await page.getByRole("button", { name: "More results", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Next page interrupted");
  await expect(page.locator(".search-result")).toHaveCount(2);
  await page.getByRole("button", { name: "Retry search", exact: true }).click();
  await expect(page.locator(".search-result")).toHaveCount(4);
  expect(await page.locator(".search-result").first().getAttribute("data-result-id")).toBe(firstId);
  await page.locator(".search-result").last().click();
  await page.getByRole("button", { name: "Back to results" }).click();
  await expect(page.locator(".search-result")).toHaveCount(4);
  await expect(page.locator(".search-result").last()).toBeFocused();
  await page.getByRole("searchbox", { name: "Search the brain" }).fill("definitely missing object");
  await expect(page.locator(".search-result")).toHaveCount(0);
  await expect(page.getByText("No matches", { exact: true })).toBeVisible();
});

test("every direct relationship remains reachable beyond the first ten", async ({ page, request }) => {
  const graph = await (await request.get("/api/graph?limit=100")).json();
  const selected = graph.nodes.find((node) => node.name === "Net Sales" && node.type === "MEASURE");
  const targets = graph.nodes.filter((node) => node.id !== selected.id).slice(0, 12);
  await page.route("**/api/objects/**", async (route) => {
    if (!decodeURIComponent(route.request().url()).endsWith(selected.id)) return route.continue();
    const response = await route.fetch();
    const data = await response.json();
    return route.fulfill({ json: { ...data, dependencies: targets, edges: targets.map((node, index) => ({ id: `test-dependency-${index}`, type: "REFERENCES", from_id: selected.id, to_id: node.id })) } });
  });
  await page.goto("/");
  await page.getByLabel("Find an object", { exact: true }).fill("Net Sales");
  await page.getByLabel("Find an object", { exact: true }).press("Enter");
  await page.locator(".search-result").filter({ has: page.locator(".result-type", { hasText: "Measure" }) }).first().click();
  const dependencies = page.getByRole("region", { name: "Dependencies", exact: true });
  await expect(dependencies.locator(".relationship-row")).toHaveCount(10);
  await dependencies.getByRole("button", { name: "Show all 12", exact: true }).click();
  await expect(dependencies.locator(".relationship-row")).toHaveCount(12);
  await dependencies.locator(".relationship-row").last().click();
  await expect(page.getByRole("heading", { name: targets[11].name, exact: true })).toBeVisible();
});
