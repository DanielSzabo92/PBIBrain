import { test, expect } from "@playwright/test";

// Finding 12: on a wide window the results and a preview sit side by side; arrow keys move the preview,
// Enter opens the Inspector. The palette asks the same search and hands its query to this page.
test("search shows a live preview beside the results and Enter opens the object", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/#/search?q=net");
  const preview = page.locator(".search-preview");
  await expect(preview.locator(".graph-detail-title")).toHaveText("Net Sales");
  const rows = page.locator(".search-result");
  await rows.first().focus();
  await page.keyboard.press("ArrowDown");
  await expect(preview.locator(".graph-detail-title")).toHaveText("Sales Target");
  await expect(rows.nth(1)).toHaveAttribute("aria-current", "true");
  const box = await preview.boundingBox();
  const list = await page.locator(".search-results").boundingBox();
  expect(box.x).toBeGreaterThan(list.x + list.width - 2);
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/#\/inspector\//);
  await expect(page.locator("main")).toContainText("Sales Target");
});

test("a narrow window shows the results alone", async ({ page }) => {
  await page.setViewportSize({ width: 1100, height: 800 });
  await page.goto("/#/search?q=net");
  await expect(page.locator(".search-result").first()).toBeVisible();
  await expect(page.locator(".search-preview")).toHaveCount(0);
});

test("the palette's search lands on the Search page with the same query", async ({ page }) => {
  await page.goto("/");
  await page.keyboard.press("Control+k");
  const input = page.getByRole("combobox");
  await input.fill("net");
  await expect(page.getByRole("option", { name: /Net Sales/ })).toBeVisible();
  await page.getByRole("option", { name: 'Search all objects for "net"' }).click();
  await expect(page).toHaveURL(/#\/search\?q=net/);
  await expect(page.locator(".search-result").first()).toContainText("Net Sales");
});
