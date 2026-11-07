import { test, expect } from "@playwright/test";

test("graph exploration keeps filters, focus, and layout after an Inspector round trip", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Graph", exact: true }).click();
  await expect(page.locator(".react-flow__node-brain").first()).toBeVisible();
  await page.getByRole("button", { name: "Expand Sales", exact: true }).click();

  const node = page.locator(".react-flow__node-brain").filter({ hasText: "Net Sales" }).first();
  await expect(node).toBeVisible();
  await node.dblclick();
  await expect(page.getByText("Focused view", { exact: true })).toBeVisible();

  // Centering intentionally resets the query and scope. Set the exploration
  // state after centering, then carry that state through the Inspector.
  // Display options and the type key live in toolbar popovers.
  await page.getByRole("button", { name: /^Display/ }).click();
  await page.getByRole("checkbox", { name: "Include suggestions" }).uncheck();
  await page.getByRole("checkbox", { name: "Group by ownership" }).check();
  await page.getByLabel("Layout", { exact: true }).selectOption("TB");
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: /^Types/ }).click();
  await page.getByRole("button", { name: "Show only Measure", exact: true }).click();
  await page.keyboard.press("Escape");
  await page.getByRole("searchbox", { name: "Filter graph objects" }).fill("Net Sales");

  // Filter changes close the sheet; reopen it from the focused node before
  // taking the Inspector round trip.
  await page.getByRole("button", { name: "Measure Net Sales", exact: true }).click();
  await page.getByRole("button", { name: "Open in Inspector", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Net Sales", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Back to graph", exact: true }).click();

  await expect(page.getByText("Focused view", { exact: true })).toBeVisible();
  await expect(page.getByRole("searchbox", { name: "Filter graph objects" })).toHaveValue("Net Sales");
  await page.getByRole("button", { name: /^Types/ }).click();
  await expect(page.getByRole("checkbox", { name: "Measure", exact: true })).toBeChecked();
  await expect(page.getByRole("checkbox", { name: "Column", exact: true })).not.toBeChecked();
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: /^Display/ }).click();
  await expect(page.getByLabel("Layout", { exact: true })).toHaveValue("TB");
  await expect(page.getByRole("checkbox", { name: "Include suggestions" })).not.toBeChecked();
  await expect(page.getByRole("checkbox", { name: "Group by ownership" })).toBeChecked();
  await expect(page.locator(".graph-center")).toContainText("Net Sales");
});
