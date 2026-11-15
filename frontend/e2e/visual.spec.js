import { test, expect } from "@playwright/test";

// Screenshot comparison (finding 22): each main view is compared with its approved picture, so a change
// to shared styles that moves something in another view fails here instead of in a user's window.
// After an intended visual change, approve the new pictures with:
//   npx playwright test e2e/visual.spec.js --update-snapshots
// The pictures are taken in Chromium on Linux at 1440 × 1000 in the dark theme (playwright.config.js).

// Its own server (playwright.config.js, port 8768): other specs approve suggestions and rescan on 8765.
test.use({ baseURL: "http://127.0.0.1:8768" });

// The last-scan time in the status bar is masked; a fixed width keeps the mask the same size whatever
// the time ("9:02 AM" is narrower than "11:45 AM").
const SHOT = { animations: "disabled", caret: "hide", maxDiffPixels: 0, style: ".statusbar-scan { display: inline-block; width: 220px; }" };

// Times and the fixture's temporary folder change on every run; they are covered, not compared.
const DATE = /\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \d{1,2}, \d{4}|\b\d+ (seconds?|minutes?|hours?) ago\b|just now/i;
const changing = (page) => [
  page.locator("time"),
  page.getByText(DATE),
  page.getByText(/pbibrain-graph-ui-/),
  page.locator('input[value*="pbibrain-graph-ui-"]'),
];

async function settle(page) {
  await page.waitForLoadState("networkidle");
  await page.evaluate(() => document.fonts.ready);
  await expect(page.locator(".view-loading, .review-skeleton-row, .spin")).toHaveCount(0);
}

const VIEWS = [
  { name: "overview", path: "/#/", ready: (page) => page.getByRole("heading", { level: 1 }).first() },
  { name: "search", path: "/#/search?q=Net%20Sales", ready: (page) => page.locator(".search-result").first() },
  { name: "inspector-tree", path: "/#/inspector", ready: (page) => page.getByRole("tree", { name: "Project objects" }).getByRole("treeitem").first() },
  { name: "review", path: "/#/review", ready: (page) => page.locator(".review-item, .review-group-head").first() },
  { name: "settings", path: "/#/settings", ready: (page) => page.getByRole("heading", { level: 1 }).first() },
  { name: "settings-colors", path: "/#/settings/colors", ready: (page) => page.getByRole("tab", { name: "Graph colors", exact: true }) },
];

for (const view of VIEWS) {
  test(`${view.name} looks as approved`, async ({ page }) => {
    await page.goto(view.path);
    await expect(view.ready(page)).toBeVisible();
    await settle(page);
    await expect(page).toHaveScreenshot(`${view.name}.png`, { ...SHOT, mask: changing(page) });
  });
}

test("an object page looks as approved", async ({ page }) => {
  await page.goto("/#/search?q=Net%20Sales");
  await page.locator(".search-result").filter({ has: page.locator(".result-type", { hasText: "Measure" }) }).first().click();
  await expect(page.getByRole("heading", { name: "Net Sales", exact: true }).first()).toBeVisible();
  await settle(page);
  await expect(page).toHaveScreenshot("inspector-object.png", { ...SHOT, mask: changing(page) });
});
