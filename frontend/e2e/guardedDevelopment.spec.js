import { test, expect } from "@playwright/test";

test("real impact API includes unchanged measures and consuming visual with uncertainty", async ({ page, request }) => {
  const graph = await (await request.get("/api/graph?limit=200")).json();
  const target = graph.nodes.find((item) => item.type === "RELATIONSHIP");
  const impact = await (await request.post("/api/impact", { data: { target_id: target.id } })).json();
  expect(impact.potential_impacts.some((item) => item.name === "Sales Amount")).toBeTruthy();
  expect(impact.potential_impacts.some((item) => item.name === "Sales YTD")).toBeTruthy();
  expect(impact.potential_impacts.some((item) => item.object_type === "VISUAL")).toBeTruthy();
  await page.goto("/");
  await page.getByRole("navigation").getByRole("button", { name: "Inspector", exact: true }).click();
  await page.getByLabel("Search object type").selectOption("RELATIONSHIP");
  await page.getByRole("button", { name: /relationship-sales/ }).first().click();
  await page.getByRole("button", { name: "Impact Explorer", exact: true }).click();
  await page.getByRole("button", { name: "Analyze impact", exact: true }).click();
  await expect(page.getByText("Impact coverage incomplete", { exact: true })).toBeVisible();
  await expect(page.getByText("Runtime behavior has not been verified.")).toBeVisible();
  await expect(page.locator(".impact-flow .react-flow__node").first()).toBeVisible();
  await page.getByLabel("Impact category").selectOption("DIRECT");
  await expect(page.locator(".guard-records > li")).toHaveCount(1);
  await page.setViewportSize({ width: 1024, height: 680 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("trusted guard displays exact changes and blocks unverified approvals", async ({ page, request }, testInfo) => {
  const { operation_id } = await (await request.get("/test-operation")).json();
  const errors = []; page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/guard#session=isolated-browser-test-session");
  await page.getByLabel("Operation reference").fill(operation_id);
  await page.getByRole("button", { name: "Load candidate", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Promotion blocked", exact: true })).toBeVisible();
  await expect(page.getByRole("cell", { name: "OrderDateKey", exact: true })).toBeVisible();
  await expect(page.getByRole("cell", { name: "ShipDateKey", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Authorize verified promotion" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Promote verified candidate" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Approve high risk change" })).toBeDisabled();
  await expect(page.getByText("runtime evidence incomplete", { exact: false })).toBeVisible();
  expect(errors).toEqual([]);
  await page.screenshot({ path: testInfo.outputPath("guard-review.png"), fullPage: true });
  await page.setViewportSize({ width: 640, height: 900 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("guard rejects Brain credentials and removes stale success after errors", async ({ page, request }) => {
  const { operation_id } = await (await request.get("/test-operation")).json();
  const denied = await request.post(`/guard/promote/${operation_id}`, { headers: { "X-PBI-Guard-Session": "brain-token" }, data: {} });
  expect(denied.status()).toBe(403);
  await page.goto("/guard#session=invalid");
  await page.getByLabel("Operation reference").fill(operation_id);
  await page.getByRole("button", { name: "Load candidate", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("guard auth required");
  await expect(page.getByRole("button", { name: "Promote verified candidate" })).toHaveCount(0);
});
