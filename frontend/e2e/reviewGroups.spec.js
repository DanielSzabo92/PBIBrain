import { test, expect } from "@playwright/test";

// Review 11: a long queue is read as patterns (one rule, one basis, one object type) and each is decided once.
test("the review queue groups suggestions by pattern and opens a group in place", async ({ page }) => {
  await page.goto("/#/review");
  await expect(page.locator(".review-item, .review-group").first()).toBeVisible();
  await page.getByLabel("Group", { exact: true }).selectOption("pattern");
  const groups = page.locator(".review-group");
  await expect(groups.first()).toBeVisible();
  await expect(page.locator(".review-item")).toHaveCount(0);
  // Project-wide "Approve all" is not offered next to per-pattern decisions.
  await expect(page.locator(".bulk-approve")).toHaveCount(0);

  const total = await page.locator(".queue-count strong").innerText();
  const counted = await groups.evaluateAll((list) => list.reduce((sum, group) => sum + Number(group.querySelector(".review-group-count").firstChild.textContent.replace(/\D/g, "")), 0));
  expect(counted).toBe(Number(total.replace(/\D/g, "")));

  const toggle = groups.first().locator(".review-group-toggle");
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  await expect(groups.first().locator(".review-item").first()).toBeVisible();
  await toggle.click();
  await expect(page.locator(".review-item")).toHaveCount(0);

  await page.getByLabel("Group", { exact: true }).selectOption("none");
  await expect(page.locator(".review-item").first()).toBeVisible();
  await expect(groups).toHaveCount(0);
});
