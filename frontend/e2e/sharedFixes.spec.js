import { test, expect } from "@playwright/test";
import { axeViolations, setTheme } from "./axe.js";

// Step U1 fixes on the old screens (UI design 13, U-fix-1 and U-fix-2). Graph test server, port 8765.

for (const theme of ["dark", "light"]) {
  test(`U-fix-2: axe on Graph has no aria-valid-attr-value violation (${theme})`, async ({ page, context }) => {
    await setTheme(context, theme);
    await page.goto("/");
    await page.getByRole("button", { name: "Graph", exact: true }).click();
    await expect(page.locator(".react-flow__node-brain").first()).toBeVisible();
    for (const view of ["Containers", "Lineage flow"]) {
      await page.getByRole("tab", { name: view, exact: true }).click();
      expect(await axeViolations(page, { rules: ["aria-valid-attr-value"] })).toEqual([]);
    }
    // Each tab of the Graph points to an element that exists.
    for (const tab of await page.getByRole("tab").all()) {
      const controls = await tab.getAttribute("aria-controls");
      await expect(page.locator(`[id="${controls}"]`)).toHaveCount(1);
    }
    // The active tab is a fill, not an underline.
    const look = await page.getByRole("tab", { name: "Lineage flow", exact: true }).evaluate((node) => {
      const style = getComputedStyle(node);
      return { fill: style.backgroundColor, track: getComputedStyle(node.parentElement).backgroundColor, bottom: style.borderBottomWidth };
    });
    expect(look.fill).not.toBe(look.track);
    expect(look.bottom).toBe("0px");
  });

  test(`U-fix-1: axe on the review queue with a destructive button has no color-contrast violation (${theme})`, async ({ page, context }) => {
    await setTheme(context, theme);
    // The review pages (GET /api/review/page) get one outdated saved decision, so the queue shows "Remove decision".
    await page.route("**/api/review/page**", async (route) => {
      const url = new URL(route.request().url());
      const response = await route.fetch();
      const body = await response.json();
      if (url.searchParams.get("issue") !== "stale" || url.searchParams.get("tab") === "reviewed") return route.fulfill({ json: body });
      const target = { id: "u-fix-1-target", type: "MEASURE", name: "U fix target" };
      const item = { id: "u-fix-1-stale", target_id: target.id, issue: "stale", issue_type: "stale", status: "stale", confidence: 0.5, value: "U_FIX_1_MARKER", evidence: [] };
      if (url.searchParams.get("rows") === "0") {
        Object.assign(body, { matching: body.matching + 1, standard_total: body.standard_total + 1, groups: [...(body.groups || []), { key: "stale||", title: "Decisions whose object is gone", bulk: false, count: 1, low: 0.5, high: 0.5, names: 1 }] });
      } else if (url.searchParams.get("section") !== "low") {
        Object.assign(body, { items: [...(body.items || []), item], nodes: [...(body.nodes || []), target], total: (body.total || 0) + 1 });
      }
      return route.fulfill({ json: body });
    });
    await page.goto("/");
    await page.getByRole("navigation").getByRole("button", { name: /^Review queue/ }).click();
    await page.getByRole("combobox", { name: "Issue" }).selectOption({ label: "Outdated decisions" });
    const remove = page.getByRole("button", { name: "Remove decision", exact: true }).first();
    await expect(remove).toBeVisible();
    await expect(remove).toHaveClass(/ui-button-destructive/);
    expect(await axeViolations(page, { rules: ["color-contrast"] })).toEqual([]);
    await remove.hover();
    expect(await axeViolations(page, { include: ".review-actions", rules: ["color-contrast"] })).toEqual([]);
  });
}
