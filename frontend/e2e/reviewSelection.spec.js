import { test, expect } from "@playwright/test";

// Review 11: rows can be ticked and decided together, and the decision is one request that can be undone.
test("ticked review rows are decided together and Undo puts them back", async ({ page }) => {
  await page.goto("/#/review");
  await expect(page.locator(".review-item, .review-group").first()).toBeVisible();
  const group = page.getByLabel("Group", { exact: true });
  if (await group.count()) await group.selectOption("none");
  const rows = page.locator(".review-item");
  await expect(rows.first()).toBeVisible();
  const total = Number((await page.locator(".queue-count strong").innerText()).replace(/\D/g, ""));
  expect(total).toBeGreaterThan(2);

  // Nothing ticked: no selection actions.
  await expect(page.locator(".selected-approve")).toHaveCount(0);
  const boxes = page.locator(".review-item .review-select");
  await boxes.nth(0).click();
  await boxes.nth(1).click();
  await expect(page.locator(".selected-approve")).toHaveText(/Approve 2 selected/);
  await expect(page.locator(".review-select-all")).toHaveAttribute("data-state", "indeterminate");

  // X on a focused row ticks it.
  await rows.nth(2).locator(".review-target").focus();
  await page.keyboard.press("x");
  await expect(page.locator(".selected-approve")).toHaveText(/Approve 3 selected/);
  await page.keyboard.press("x");
  await expect(page.locator(".selected-approve")).toHaveText(/Approve 2 selected/);

  const posts = [];
  page.on("request", (request) => { if (request.method() === "POST" && request.url().endsWith("/api/review")) posts.push(request.postDataJSON()); });
  await page.locator(".selected-approve").click();
  await expect(page.locator(".queue-count strong")).toHaveText(String(total - 2));
  expect(posts).toHaveLength(1);
  expect(posts[0].items).toHaveLength(2);
  expect(posts[0].reply).toBe("summary");
  await expect(page.locator(".selected-approve")).toHaveCount(0);

  await page.getByRole("button", { name: "Undo" }).click();
  await expect(page.locator(".queue-count strong")).toHaveText(String(total));
  expect(posts[1]).toMatchObject({ action: "undo" });
  expect(posts[1].token).toBeTruthy();
});

test("the header checkbox ticks every suggestion and clears again", async ({ page }) => {
  await page.goto("/#/review");
  await expect(page.locator(".review-item, .review-group").first()).toBeVisible();
  const group = page.getByLabel("Group", { exact: true });
  if (await group.count()) await group.selectOption("none");
  const all = page.locator(".review-select-all");
  await all.click();
  await expect(all).toHaveAttribute("data-state", "checked");
  await expect(page.locator(".selected-approve")).toHaveText(/Approve \d+ selected/);
  await page.locator(".selected-clear").click();
  await expect(all).toHaveAttribute("data-state", "unchecked");
  await expect(page.locator(".bulk-approve")).toBeVisible();
});

// Settings › Review: auto-accept is off until chosen; turning it on empties the queue of the covered suggestions and marks them.
test("auto-accept is a review setting, marks its decisions and can be turned off again", async ({ page, request }) => {
  // The server is shared by the run: start from the setting switched off, whatever an earlier failure left.
  const config = await (await request.get("/api/config")).json();
  await request.post("/api/config", { data: { ...config, review: { auto_accept: false } } });
  await page.goto("/#/review");
  await expect(page.locator(".queue-count strong")).not.toHaveText("…");
  const before = Number((await page.locator(".queue-count strong").innerText()).replace(/\D/g, ""));

  await page.goto("/#/settings/review");
  const toggle = page.getByRole("switch", { name: "Accept these suggestions without review" });
  await expect(toggle).toHaveAttribute("aria-checked", "false");
  await expect(page.getByLabel("Minimum confidence")).toBeDisabled();
  await toggle.click();
  await page.getByLabel("Minimum confidence").selectOption("0.7");
  await page.getByRole("button", { name: "Save review settings" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Saved" })).toBeVisible();

  await page.goto("/#/review");
  await expect(page.locator(".queue-count strong")).not.toHaveText("…");
  const after = Number((await page.locator(".queue-count strong").innerText()).replace(/\D/g, ""));
  expect(after).toBeLessThan(before);
  await page.getByLabel("Review views").getByText(/^Reviewed/).click();
  await expect(page.locator(".auto-mark").first()).toBeVisible();
  expect(await page.locator(".auto-mark").count()).toBeGreaterThan(0);

  await page.goto("/#/settings/review");
  await page.getByRole("switch", { name: "Accept these suggestions without review" }).click();
  await page.getByRole("button", { name: "Save review settings" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Saved" })).toBeVisible();
  await page.goto("/#/review");
  await expect(page.locator(".auto-mark")).toHaveCount(0);
  await page.getByLabel("Review views").getByText(/^To review/).click();
  await expect(page.locator(".queue-count strong")).toHaveText(String(before));
});
