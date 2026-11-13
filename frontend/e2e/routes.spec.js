import { test, expect } from "@playwright/test";

// Review 10: the address holds the view and the object, so a link, a reload and Back all work.
test("a link opens its view, reload stays there and Back returns to the search", async ({ page }) => {
  await page.goto("/#/settings/colors");
  await expect(page.getByRole("tab", { name: "Graph colors", exact: true })).toHaveAttribute("aria-selected", "true");

  await page.goto("/#/search?q=Net%20Sales");
  await expect(page.getByRole("searchbox", { name: "Search objects" })).toHaveValue("Net Sales");
  const result = page.locator(".search-result").filter({ has: page.locator(".result-type", { hasText: "Measure" }) }).first();
  await result.click();
  await expect(page.getByRole("heading", { name: "Net Sales", exact: true }).first()).toBeVisible();
  await expect(page).toHaveURL(/#\/inspector\/.+/);

  await page.reload();
  await expect(page.getByRole("heading", { name: "Net Sales", exact: true }).first()).toBeVisible();

  await page.goBack();
  await expect(page).toHaveURL(/#\/search\?q=Net%20Sales/);
  await expect(page.getByRole("searchbox", { name: "Search objects" })).toHaveValue("Net Sales");
});

// Review 13: the Inspector is browsable without knowing a name.
test("the Inspector tree opens a model down to a measure and filters by name", async ({ page }) => {
  await page.goto("/#/inspector");
  const tree = page.getByRole("tree", { name: "Project objects" });
  await expect(tree.getByRole("treeitem").first()).toBeVisible();
  await page.getByLabel("Filter the object tree").fill("Net Sales");
  const row = tree.getByRole("treeitem").filter({ hasText: /^Net Sales$/ }).first();
  await expect(row).toBeVisible();
  await row.click();
  await expect(page.getByRole("heading", { name: "Net Sales", exact: true }).first()).toBeVisible();
  await expect(row).toHaveAttribute("aria-selected", "true");
});

// Review 12: a search for a measure lists the measure, not the alias record that repeats its name.
test("search lists project objects and no alias records", async ({ page }) => {
  await page.goto("/#/search?q=Sales");
  await expect(page.locator(".search-result").first()).toBeVisible();
  await expect(page.locator(".search-result .result-type", { hasText: /^Alias$/ })).toHaveCount(0);
});
