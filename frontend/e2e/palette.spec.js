// The command palette must be laid out by its stylesheet. The class names in the component and in
// app.css once drifted apart and the palette shipped unstyled; these checks fail if that happens again.
import { test, expect } from "@playwright/test";

test("command palette rows are laid out and show a readable scope", async ({ page, request }) => {
  // Earlier specs rescan the shared server, so the object comes from the current graph, not from a fixed name.
  const overview = await (await request.get("/api/overview")).json();
  const graph = await (await request.get("/api/graph")).json();
  const measure = graph.nodes.find((node) => node.type === "MEASURE");
  const model = overview.model_objects.find((item) => item.id === measure.model_id);
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1, name: "Overview" })).toBeVisible();
  await page.keyboard.press("Control+k");
  const input = page.getByRole("combobox");
  await expect(input).toBeVisible();
  await input.fill(measure.name);
  const row = page.getByRole("option").filter({ hasText: measure.name }).first();
  await expect(row).toBeVisible();
  // One line per row: icon, name and scope side by side.
  expect(await row.evaluate((element) => getComputedStyle(element).display)).toBe("flex");
  const box = await row.boundingBox();
  expect(box.height).toBeLessThanOrEqual(36);
  // The header keeps the search icon and the field on one line.
  const header = await page.locator(".command-palette-header").boundingBox();
  expect(header.height).toBeLessThanOrEqual(48);
  // The scope is a name, never a raw graph ID.
  await expect(row).not.toContainText(/model:|report:|table:/);
  await expect(row).toContainText(model.name);
  // The dialog title stays for assistive technology only.
  expect((await page.getByRole("heading", { name: "Command palette" }).boundingBox()).width).toBeLessThanOrEqual(2);
});
