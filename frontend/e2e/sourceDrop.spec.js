import { test, expect } from "@playwright/test";

// Finding 20: in the desktop window, files dragged over the app show a drop target, and the window's
// drop event (backend/desktop/host.py) reports what it added. The desktop bridge is faked here.
test("the desktop window shows a drop target and reports the sources a drop added", async ({ page }) => {
  await page.addInitScript(() => {
    window.__PBIBRAIN_DESKTOP__ = true;
    window.pywebview = { api: {
      get_session: async () => ({ ok: true, project: { name: "Dropped", folder: "/projects/dropped" } }),
      list_recent_projects: async () => ({ ok: true, projects: [] }),
    } };
  });
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Overview", exact: true })).toBeVisible();
  await page.evaluate(() => {
    const data = new DataTransfer();
    data.items.add(new File(["{}"], "Sales.bim"));
    window.dispatchEvent(new DragEvent("dragenter", { dataTransfer: data, bubbles: true }));
  });
  await expect(page.getByText("Drop to add sources")).toBeVisible();
  await page.evaluate(() => {
    window.dispatchEvent(new DragEvent("drop", { dataTransfer: new DataTransfer(), bubbles: true }));
    window.dispatchEvent(new CustomEvent("pbibrain-sources-dropped", { detail: { ok: true, added: ["Sales.bim"], sources: ["Sales.bim"], skipped: 1 } }));
  });
  await expect(page.getByText("Drop to add sources")).toHaveCount(0);
  await expect(page.locator("[data-sonner-toast]").first()).toContainText("Added 1 source. Scan to read it. 1 other file was left out.");
});
