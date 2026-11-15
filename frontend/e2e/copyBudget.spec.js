import { test, expect } from "@playwright/test";

// Finding 14: a sentence belongs in an empty state, a dialog or an error. Each view may show at most two
// text runs longer than 60 characters outside those places (rule 7 of the finding).
async function longText(page) {
  return page.evaluate(() => {
    const out = [];
    const walker = document.createTreeWalker(document.querySelector("#main-content") || document.body, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
      const text = walker.currentNode.textContent.trim();
      const element = walker.currentNode.parentElement;
      if (text.length <= 60 || !element) continue;
      if (element.closest("[data-empty-state], [role=dialog], [role=alertdialog], [role=alert], .sr-only, pre, code, [translate=no]")) continue;
      const box = element.getBoundingClientRect();
      if (box.width && box.height) out.push(text);
    }
    return out;
  });
}

test("graph app views keep to two long text runs each", async ({ page, request }) => {
  const graph = await (await request.get("/api/graph?limit=200")).json();
  const pick = (type) => graph.nodes.find((node) => node.type === type)?.id;
  const routes = ["#/", "#/search", "#/review", "#/settings", ...["MEASURE", "TABLE", "MODEL", "VISUAL", "REPORT"].map(pick).filter(Boolean).map((id) => `#/inspector/${encodeURIComponent(id)}`)];
  for (const route of routes) {
    await page.goto(`/${route}`);
    await expect(page.locator("#main-content")).toBeVisible();
    await page.waitForLoadState("networkidle");
    const runs = await longText(page);
    expect(runs.length, `${route}: ${runs.join(" | ")}`).toBeLessThanOrEqual(2);
  }
});

test("Merge models keeps to two long text runs per tab", async ({ page, request }) => {
  await request.post("http://127.0.0.1:8766/__test__/scenario", { data: { name: "default" } });
  await page.goto("http://127.0.0.1:8766/");
  await page.getByRole("navigation", { name: "Main navigation" }).getByRole("button", { name: "Merge models" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Sales and finance merge" })).toBeVisible();
  for (const tab of ["Compare", "Impact", "Plan", "Sources", "Naming rules", "Log"]) {
    await page.getByRole("tablist", { name: "Work area tabs" }).getByRole("tab", { name: new RegExp(`^${tab}`) }).click();
    await page.waitForLoadState("networkidle");
    const runs = await longText(page);
    expect(runs.length, `${tab}: ${runs.join(" | ")}`).toBeLessThanOrEqual(2);
  }
});
