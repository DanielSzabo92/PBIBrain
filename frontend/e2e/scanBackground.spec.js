import { test, expect } from "@playwright/test";

// Review 04: the scan runs as a background job. The page stays usable, shows what the scan is doing and can cancel it.
test("a scan is one background request that the page waits for by reading its status", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Scan sources" }).first()).toBeEnabled();
  const calls = [];
  page.on("request", (request) => { if (request.url().includes("/api/scan")) calls.push(`${request.method()} ${new URL(request.url()).pathname}`); });
  const posted = page.waitForRequest((request) => request.method() === "POST" && request.url().endsWith("/api/scan"));
  await page.getByRole("button", { name: "Scan sources" }).first().click();
  expect((await posted).postDataJSON()).toEqual({ background: true });
  await expect(page.locator(".app-statusbar")).toContainText(/Scan complete: \d+ objects/);
  expect(calls[0]).toBe("POST /api/scan");
  expect(calls).toContain("GET /api/scan/status");
});

test("Cancel stops the scan and says that nothing changed", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Scan sources" }).first()).toBeEnabled();
  // The fixture scans in well under a second; hold the status answers so the scan is seen running.
  let cancelled = false;
  await page.route("**/api/scan/status", async (route) => {
    if (!cancelled) return route.fulfill({ json: { running: true, phase: "Reading formulas and dependencies", done: 1, total: 1 } });
    return route.fulfill({ json: { running: false, last: { scan: 1, state: "cancelled" } } });
  });
  await page.route("**/api/scan", (route) => route.fulfill({ json: { running: true, scan: 1 } }));
  await page.route("**/api/scan/cancel", (route) => { cancelled = true; return route.fulfill({ json: { running: true, cancelling: true } }); });
  await page.getByRole("button", { name: "Scan sources" }).first().click();
  const cancel = page.getByRole("button", { name: "Cancel", exact: true });
  await expect(cancel).toBeVisible();
  await expect(page.locator(".topbar-scanning")).toContainText("Reading formulas and dependencies");
  await cancel.click();
  await expect(page.locator(".app-statusbar")).toContainText("Scan cancelled. Nothing was changed.");
  await expect(page.getByRole("button", { name: "Scan sources" }).first()).toBeEnabled();
});

test("Settings shows what the last scan did with each source", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Scan sources" }).first().click();
  await expect(page.locator(".app-statusbar")).toContainText(/Scan complete/);
  await page.goto("/#/settings");
  await expect(page.locator(".source-row .source-scan").first()).toHaveText(/^Scanned · 1 model, 1 report$/);
  await expect(page.locator(".source-row").first()).toHaveClass(/source-ok/);
});
