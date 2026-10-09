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
  await expect(page.getByRole("heading", { name: "Checks incomplete", exact: true })).toBeVisible();
  await expect(page.getByRole("cell", { name: "OrderDateKey", exact: true })).toBeVisible();
  await expect(page.getByRole("cell", { name: "ShipDateKey", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Accept changes", exact: true })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Reject changes", exact: true })).toBeEnabled();
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
  await expect(page.getByRole("button", { name: "Accept changes", exact: true })).toHaveCount(0);
});

test("user rejects a real proposal and original sources remain unchanged", async ({ page, request }) => {
  const before = await (await request.get("/test-source")).json();
  const { operation_id } = await (await request.get("/test-proposal")).json();
  await page.goto("/guard#session=isolated-browser-test-session");
  await page.getByLabel("Operation reference").fill(operation_id);
  await page.getByRole("button", { name: "Load candidate", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Proposal awaiting your decision", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Accept proposal", exact: true })).toBeEnabled();
  await page.getByRole("button", { name: "Reject proposal", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Changes rejected", exact: true })).toBeVisible();
  await expect(page.getByText("Your project remains unchanged.", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Accept changes", exact: true })).toBeDisabled();
  expect(await (await request.get("/test-source")).json()).toEqual(before);
});

test("accepting proposal prepares a separate copy and still requires final acceptance", async ({ page, request }) => {
  const before = await (await request.get("/test-source")).json();
  const { operation_id } = await (await request.get("/test-proposal")).json();
  await page.goto("/guard#session=isolated-browser-test-session");
  await page.getByLabel("Operation reference").fill(operation_id);
  await page.getByRole("button", { name: "Load candidate", exact: true }).click();
  await page.getByRole("button", { name: "Accept proposal", exact: true }).click();
  await expect(page.getByText("candidate ready", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Accept changes", exact: true })).toBeDisabled();
  expect(await (await request.get("/test-source")).json()).toEqual(before);
  await page.getByRole("button", { name: "Reject changes", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Changes rejected", exact: true })).toBeVisible();
});

test("verified acceptance UX uses reviewed binding before applying (transport double)", async ({ page }) => {
  const binding = { operation_id: "ui-fixture", candidate_hash: "candidate-v1", baseline_snapshot_id: "baseline-v1", contract_hash: "contract-v1", policy_hash: "policy-v1", evidence_hash: "evidence-v1" };
  const review = { operation: { state: "APPROVAL_REQUIRED", decision: { blocking_reasons: [], approval_reasons: ["HIGH_RISK_PROMOTION", "UNEXPECTED_BEHAVIOR"] } }, verification: { candidate_hash: "candidate-v1" }, contract: {}, review_binding: binding, audit: [] };
  const requests = [];
  await page.route("**/guard/*/ui-fixture", async (route) => {
    const action = new URL(route.request().url()).pathname.split("/")[2];
    if (action !== "review") requests.push({ action, body: route.request().postDataJSON() });
    if (action === "promote") review.operation = { state: "POST_PROMOTION_VERIFIED", user_decision: "ACCEPTED", decision: { blocking_reasons: [] } };
    await route.fulfill({ json: { guard_api_version: 1, ok: true, result: action === "review" ? review : {} } });
  });
  await page.goto("/guard#session=transport-test-double");
  await page.getByLabel("Operation reference").fill("ui-fixture");
  await page.getByRole("button", { name: "Load candidate", exact: true }).click();
  await expect(page.getByText("Accept also approves the behavior differences shown in the regression results.")).toBeVisible();
  await page.getByRole("button", { name: "Accept changes", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Changes applied and verified", exact: true })).toBeVisible();
  expect(requests).toEqual([{ action: "accept", body: { binding, approval_operations: ["HIGH_RISK_PROMOTION", "UNEXPECTED_BEHAVIOR", "PROMOTE"] } }, { action: "promote", body: { binding } }]);
  await expect(page.getByRole("button", { name: "Reject changes", exact: true })).toBeDisabled();
});

test("failed acceptance never issues promotion (transport double)", async ({ page }) => {
  const requests = [];
  await page.route("**/guard/*/ui-failure", async (route) => {
    const action = new URL(route.request().url()).pathname.split("/")[2]; requests.push(action);
    if (action === "accept") return route.fulfill({ status: 409, json: { guard_api_version: 1, error: { code: "REVIEW_STALE", message: "Proposal changed; review again" } } });
    await route.fulfill({ json: { guard_api_version: 1, ok: true, result: { operation: { state: "ELIGIBLE_FOR_PROMOTION", decision: { blocking_reasons: [], approval_reasons: [] } }, verification: { candidate_hash: "candidate" }, review_binding: {}, audit: [] } } });
  });
  await page.goto("/guard#session=transport-test-double");
  await page.getByLabel("Operation reference").fill("ui-failure");
  await page.getByRole("button", { name: "Load candidate", exact: true }).click();
  await page.getByRole("button", { name: "Accept changes", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("Proposal changed; review again");
  expect(requests).toEqual(["review", "accept"]);
  await expect(page.getByRole("button", { name: "Accept changes", exact: true })).toHaveCount(0);
});
