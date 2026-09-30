import { test, expect } from "@playwright/test";
import fs from "node:fs/promises";

const openSummary = async (page) => {
  await page.goto("/");
  await page.getByRole("navigation").getByRole("button", { name: "Settings", exact: true }).click();
  await page.getByRole("tab", { name: "Model summary", exact: true }).click();
};

test("native-backed summary previews and downloads the exact UTF-8 context", async ({ page, context }, testInfo) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await openSummary(page);
  const preview = page.getByLabel("Markdown preview");
  await expect(preview).toBeVisible();
  const text = await preview.inputValue();
  expect(text).toContain("# Model context: `Finance model`");
  expect(text).toContain("SUM('Sales'[Amount])");
  expect(text).toContain("Source freshness");
  await page.getByRole("button", { name: "Copy context" }).click();
  await expect(page.getByRole("status")).toContainText("Context copied.");
  // Windows clipboard uses CRLF even when the exported file uses LF.
  expect((await page.evaluate(() => navigator.clipboard.readText())).replace(/\r\n/g, "\n")).toBe(text);
  const downloadEvent = page.waitForEvent("download");
  await page.getByRole("button", { name: "Save Markdown" }).click();
  const download = await downloadEvent;
  expect(download.suggestedFilename()).toBe("model-context.md");
  expect(await fs.readFile(await download.path(), "utf8")).toBe(text);
  await page.screenshot({ path: testInfo.outputPath("model-summary.png"), fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.setViewportSize({ width: 1024, height: 680 });
  await expect(page.getByRole("button", { name: "Save Markdown" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("summary retries errors and offers selection when clipboard is unavailable", async ({ page }) => {
  let fail = true;
  await page.route("**/api/model-summary?**", (route) => fail
    ? route.fulfill({ status: 503, json: { error: "Summary interrupted" } }) : route.continue());
  await openSummary(page);
  await expect(page.getByRole("alert")).toContainText("Summary interrupted");
  await expect(page.getByRole("button", { name: "Save Markdown" })).toBeDisabled();
  fail = false;
  await page.getByRole("button", { name: "Retry summary" }).click();
  await expect(page.getByLabel("Markdown preview")).toBeVisible();
  await page.evaluate(() => Object.defineProperty(navigator, "clipboard", { value: undefined, configurable: true }));
  await page.getByRole("button", { name: "Copy context" }).click();
  await expect(page.getByLabel("Markdown preview")).toBeFocused();
  await expect(page.getByRole("status")).toContainText("press Ctrl+C");
});

test("late model response cannot replace selected model context", async ({ page }) => {
  let release;
  const models = [{ id: "model:first", name: "First" }, { id: "model:second", name: "Second" }];
  await page.route("**/api/overview", async (route) => {
    const response = await route.fetch();
    return route.fulfill({ json: { ...await response.json(), model_objects: models } });
  });
  await page.route("**/api/model-summary?**", async (route) => {
    const id = new URL(route.request().url()).searchParams.get("model_id");
    if (id === "model:first") await new Promise((resolve) => { release = resolve; });
    return route.fulfill({ json: { model_id: id, markdown: `# ${id}` } });
  });
  await openSummary(page);
  await expect.poll(() => Boolean(release)).toBe(true);
  await page.getByLabel("Semantic model").selectOption("model:second");
  await expect(page.getByLabel("Markdown preview")).toHaveValue("# model:second");
  release();
  await expect(page.getByLabel("Markdown preview")).toHaveValue("# model:second");
});

test("empty projects explain why a summary is unavailable", async ({ page }) => {
  await page.route("**/api/overview", async (route) => {
    const response = await route.fetch();
    return route.fulfill({ json: { ...await response.json(), model_objects: [] } });
  });
  await openSummary(page);
  await expect(page.getByText("Scan a semantic model to create its context file.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Save Markdown" })).toHaveCount(0);
});
