import { test, expect } from "@playwright/test";
import fs from "node:fs/promises";

// The PDF is drawn in the page with pdfcn on Takumi (WebAssembly) from the server's content blocks.
test("Export PDF draws the documentation in the app and downloads it", async ({ page }, testInfo) => {
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await page.getByRole("navigation").getByRole("button", { name: "Settings", exact: true }).click();
  await page.getByRole("tab", { name: "Documentation export", exact: true }).click();
  const request = page.waitForRequest((item) => item.url().endsWith("/api/documentation-export"));
  const downloadEvent = page.waitForEvent("download", { timeout: 60000 });
  await page.getByRole("button", { name: "Export PDF" }).click();
  expect(JSON.parse((await request).postData()).format).toBe("document");
  const download = await downloadEvent;
  expect(download.suggestedFilename()).toMatch(/-documentation\.pdf$/);
  const bytes = await fs.readFile(await download.path());
  expect(bytes.subarray(0, 5).toString("latin1")).toBe("%PDF-");
  expect(bytes.length).toBeGreaterThan(5000);
  await fs.writeFile(testInfo.outputPath("documentation.pdf"), bytes);
  await expect(page.getByRole("status").filter({ hasText: "prepared" })).toBeVisible();
  expect(errors).toEqual([]);
});
