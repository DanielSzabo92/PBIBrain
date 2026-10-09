import { test, expect } from "@playwright/test";

function targetId(item) {
  const target = item?.target_id ?? item?.target ?? item?.object_id ?? item?.object;
  return target && typeof target === "object" ? target.id || target.object_id : target;
}

function issueValue(item) {
  const issue = String(item?.issue || item?.issue_type || item?.kind || item?.type || "candidate").toLowerCase();
  if (issue.includes("conflict")) return "conflict";
  if (issue.includes("stale") || issue.includes("override")) return "stale";
  return "candidate";
}

test("review queue explains snapshot failure and retries into a loaded state", async ({ page }) => {
  let failSnapshot = true;
  await page.route("**/api/brain", async (route) => {
    if (failSnapshot) {
      return route.fulfill({ status: 503, json: { error: "Review snapshot interrupted" } });
    }
    return route.continue();
  });

  await page.goto("/");
  await page.getByRole("navigation").getByRole("button", { name: /^Review queue/ }).click();
  await expect(page.getByRole("heading", { name: "Review queue unavailable", exact: true })).toBeVisible();
  await expect(page.getByRole("alert")).toContainText("Review snapshot interrupted");

  failSnapshot = false;
  await page.getByRole("button", { name: "Retry review queue", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Review queue unavailable", exact: true })).toHaveCount(0);
  await expect(page.locator(".queue-panel")).toBeVisible();
});

test("settings shows a local retry when configuration loading fails", async ({ page }) => {
  let failConfig = true;
  await page.route("**/api/config", async (route) => {
    if (failConfig) {
      return route.fulfill({ status: 503, json: { error: "Settings interrupted" } });
    }
    return route.continue();
  });

  await page.goto("/");
  await page.getByRole("navigation").getByRole("button", { name: "Settings", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Project settings unavailable", exact: true })).toBeVisible();
  failConfig = false;
  await page.getByRole("button", { name: "Retry settings", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Project settings unavailable", exact: true })).toHaveCount(0);
  await expect(page.getByRole("tab", { name: "Project", exact: true })).toBeVisible();
});

test("blank search with a type filter browses matching objects", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("navigation").getByRole("button", { name: "Search", exact: true }).click();
  await page.getByLabel("Search object type", { exact: true }).selectOption("MEASURE");

  await expect(page.getByRole("searchbox", { name: "Search the brain" })).toHaveValue("");
  await expect(page.locator(".search-result").first()).toBeVisible();
  await expect(page.locator(".search-status")).toContainText("objects");
  await expect(page.getByText("No matches", { exact: true })).toHaveCount(0);
});

test("review filters and sort survive an inspector visit and restore target focus", async ({ page, request }) => {
  const response = await request.get("/api/brain");
  expect(response.ok()).toBeTruthy();
  const brain = await response.json();
  const items = Array.isArray(brain.review_items) ? brain.review_items : [];
  const selected = items
    .map((item) => ({ item, node: (brain.nodes || []).find((node) => node.id === targetId(item)) }))
    .find(({ node }) => node);
  expect(selected).toBeTruthy();

  await page.goto("/");
  await page.getByRole("navigation").getByRole("button", { name: /^Review queue/ }).click();
  await expect(page.locator(".queue-panel")).toBeVisible();
  await page.getByLabel("Issue", { exact: true }).selectOption(issueValue(selected.item));
  await page.getByLabel("Object", { exact: true }).selectOption(selected.node.type);
  await page.getByLabel("Sort", { exact: true }).selectOption("confidence-low");
  await expect(page.locator(".review-item").first()).toBeVisible();

  const target = page.locator(".review-target").first();
  const reviewId = await target.getAttribute("data-review-id");
  expect(reviewId).toBeTruthy();
  await target.click();
  await expect(page.getByRole("button", { name: "Back to review queue", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Back to review queue", exact: true }).click();

  await expect(page.getByLabel("Issue", { exact: true })).toHaveValue(issueValue(selected.item));
  await expect(page.getByLabel("Object", { exact: true })).toHaveValue(selected.node.type);
  await expect(page.getByLabel("Sort", { exact: true })).toHaveValue("confidence-low");
  await expect.poll(() => page.locator(".review-target").evaluateAll((nodes, id) => nodes.some((node) => node.dataset.reviewId === id && document.activeElement === node), reviewId)).toBe(true);
});

test("canonical pending count drives the review badge and Reload Brain refreshes its snapshot", async ({ page, request }) => {
  const overviewResponse = await request.get("/api/overview");
  expect(overviewResponse.ok()).toBeTruthy();
  const overview = await overviewResponse.json();
  expect(typeof overview.review_count).toBe("number");
  expect(overview.review_count).toBeGreaterThan(0);

  let snapshotRequests = 0;
  await page.route("**/api/brain", async (route) => {
    snapshotRequests += 1;
    return route.continue();
  });
  await page.goto("/");
  const reviewNav = page.getByRole("navigation").getByRole("button", { name: /^Review queue/ });
  await expect(reviewNav.locator(".nav-count")).toHaveText(String(overview.review_count));
  await reviewNav.click();
  await expect(page.locator(".queue-panel")).toBeVisible();
  const loadedRequests = snapshotRequests;

  await page.getByRole("button", { name: "Reload Brain", exact: true }).click();
  await expect.poll(() => snapshotRequests).toBeGreaterThan(loadedRequests);
  await expect(page.locator(".queue-panel")).toBeVisible();
});

test("successful review stays successful when the follow-up snapshot refresh fails", async ({ page }) => {
  let reviewPosted = false;
  let reviewRequests = 0;
  await page.route("**/api/review", async (route) => {
    reviewPosted = true;
    reviewRequests += 1;
    return route.continue();
  });
  await page.route("**/api/brain", async (route) => {
    if (reviewPosted) return route.fulfill({ status: 503, json: { error: "Refresh interrupted" } });
    return route.continue();
  });

  await page.goto("/");
  await page.getByRole("navigation").getByRole("button", { name: /^Review queue/ }).click();
  const item = page.locator(".review-item").first();
  await expect(item).toBeVisible();
  const approvedReviewId = await item.locator(".review-target").getAttribute("data-review-id");
  expect(approvedReviewId).toBeTruthy();
  const approve = item.getByRole("button", { name: "Approve", exact: true });
  await expect(approve).toBeVisible();
  await approve.click();

  await expect(page.locator(".toast")).toContainText("Suggestion approved");
  await expect(page.getByText("Review failed. Try again.", { exact: true })).toHaveCount(0);
  await expect(page.locator(".review-item").first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "Review refresh failed", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Retry review queue", exact: true })).toBeVisible();
  expect(await page.locator(".review-target").evaluateAll((nodes, id) => nodes.some((node) => node.dataset.reviewId === id), approvedReviewId)).toBe(false);
  expect(reviewRequests).toBe(1);
});

test("a scan started from Overview reloads the review queue after navigation during the scan", async ({ page }) => {
  let releaseScan;
  let scanResponseReady = false;
  let snapshotRequests = 0;
  await page.route("**/api/brain", async (route) => {
    snapshotRequests += 1;
    return route.continue();
  });
  await page.route("**/api/scan", async (route) => {
    const response = await route.fetch();
    scanResponseReady = true;
    await new Promise((resolve) => { releaseScan = resolve; });
    await route.fulfill({ response });
  });

  await page.goto("/");
  await page.getByRole("button", { name: "Scan sources", exact: true }).click();
  await expect.poll(() => scanResponseReady).toBe(true);
  await page.getByRole("navigation").getByRole("button", { name: /^Review queue/ }).click();
  await expect(page.getByRole("heading", { name: "Review queue", exact: true })).toBeVisible();
  const approve = page.locator(".review-item").first().getByRole("button", { name: "Approve", exact: true });
  await expect(approve).toBeVisible();
  await expect(approve).toBeDisabled();
  const reviewLoadRequests = snapshotRequests;

  releaseScan();
  await expect.poll(() => snapshotRequests).toBeGreaterThan(reviewLoadRequests);
  await expect(page.getByRole("heading", { name: "Review queue unavailable", exact: true })).toHaveCount(0);
  await expect(page.locator(".queue-panel")).toBeVisible();
  await expect(page.locator(".review-item").first()).toBeVisible();
  await expect(page.locator(".topbar-scanning")).toHaveCount(0);
  await expect(page.locator(".queue-panel")).toHaveAttribute("aria-busy", "false");
  await expect(approve).toBeEnabled();
});

test("a delayed review response cannot overwrite a newer successful scan generation", async ({ page }) => {
  test.setTimeout(60000);
  let releaseReview;
  let reviewReady = false;
  let reviewSettled = false;
  await page.route("**/api/review", async (route) => {
    const response = await route.fetch();
    const body = await response.json();
    const snapshot = body.snapshot || body.brain || {};
    const markerTarget = snapshot.nodes?.[0]?.id || "stale-generation-target";
    body.snapshot = {
      ...snapshot,
      review_items: [
        ...(Array.isArray(snapshot.review_items) ? snapshot.review_items : []),
        {
          id: "stale-generation-review",
          review_id: "stale-generation-review",
          target_id: markerTarget,
          object_id: markerTarget,
          issue_type: "candidate",
          assertion_type: "BUSINESS_CONCEPT",
          type: "BUSINESS_CONCEPT",
          value: "STALE_GENERATION_MARKER",
          confidence: 0.01,
          status: "candidate",
          evidence: [],
        },
      ],
    };
    reviewReady = true;
    await new Promise((resolve) => { releaseReview = resolve; });
    await route.fulfill({ json: body });
    reviewSettled = true;
  });

  await page.goto("/");
  await page.getByRole("navigation").getByRole("button", { name: /^Review queue/ }).click();
  const item = page.locator(".review-item").first();
  await expect(item).toBeVisible();
  await item.getByRole("button", { name: "Approve", exact: true }).click();
  await expect.poll(() => reviewReady).toBe(true);

  await page.getByRole("navigation").getByRole("button", { name: "Overview", exact: true }).click();
  await page.getByRole("button", { name: "Scan sources", exact: true }).click();
  await expect(page.locator(".toast")).toContainText("Scan complete", { timeout: 60000 });

  releaseReview();
  await expect.poll(() => reviewSettled).toBe(true);
  await expect(page.locator(".toast")).toContainText("Scan complete");
  await expect(page.locator(".toast")).not.toContainText("Suggestion approved");

  await page.getByRole("navigation").getByRole("button", { name: /^Review queue/ }).click();
  await expect(page.locator(".queue-panel")).toBeVisible();
  await expect(page.getByText("Meaning: STALE_GENERATION_MARKER", { exact: true })).toHaveCount(0);
});
