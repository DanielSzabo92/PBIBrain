// Step U8: Impact views and removal policy (UI design 4.5, 5.3, 7.3, 8.4, 9, 11).
// Layout: 1280 x 900 (scope cut 2026-11-01). All text follows ASD-STE100 rules.
import { test, expect } from "@playwright/test";
import { axeViolations } from "./axe.js";

const FAKE = "http://127.0.0.1:8766";
test.use({ baseURL: FAKE, viewport: { width: 1280, height: 900 } });

async function scenario(request, name) {
  const loaded = await request.post("/__test__/scenario", { data: { name } });
  expect(loaded.ok()).toBe(true);
}

async function setImpact(request, data) {
  const res = await request.post("/__test__/impact", { data });
  expect(res.ok()).toBe(true);
}

async function openImpact(page) {
  await page.goto("/");
  await page.getByRole("navigation", { name: "Main navigation" }).getByRole("button", { name: "Development Center" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Sales and finance merge" })).toBeVisible();
  await expect(page.locator(".dc-busy-line")).toHaveCount(0);
  await page.getByRole("tab", { name: "Impact" }).click();
  await expect(page.locator(".dc-impact")).toBeVisible();
}

const panel = (page) => page.getByRole("tabpanel", { name: "Impact" });
const table = (page) => page.getByRole("table", { name: "Impact items" });
const row = (page, name) => table(page).getByRole("row").filter({ has: page.getByRole("button", { name, exact: true }) });
const groupButton = (page, group) => page.locator(`[data-group-value="${group}"]`);

async function chooseSelect(page, label, option) {
  await panel(page).getByRole("combobox", { name: label, exact: true }).click();
  await page.getByRole("option", { name: option, exact: true }).click();
}

test.describe("Scope, group, and view switches", () => {
  test("the default group is the first with blocking items, and the view switch keeps scope, filters, and selection", async ({ page, request }) => {
    await scenario(request, "default");
    await openImpact(page);
    const breaks = groupButton(page, "breaks");
    await expect(breaks).toHaveAttribute("aria-checked", "true");
    await expect(breaks).toContainText("Breaks (7)");
    await expect(breaks.locator(".dc-impact-group-blocking")).toHaveText("(4 blocking)");
    await expect(groupButton(page, "needs")).toContainText("Needs (4)");
    await expect(groupButton(page, "offers")).toContainText("Offers (5)");
    await expect(table(page).locator("tbody tr.dc-impact-row")).toHaveCount(7);

    // Group switch: Needs shows only the needs items.
    await groupButton(page, "needs").click();
    await expect(table(page).locator("tbody tr.dc-impact-row")).toHaveCount(4);
    await groupButton(page, "breaks").click();

    // A filter, a search, and a selection.
    await chooseSelect(page, "Certainty", "Certain");
    await expect(table(page).locator("tbody tr.dc-impact-row")).toHaveCount(6);
    await row(page, "Sales by region").getByRole("button", { name: "Sales by region", exact: true }).click();
    await expect(page.getByRole("heading", { level: 2, name: "Sales by region" })).toBeFocused();

    // View switch to Graph and back keeps scope, filters, and selection.
    await panel(page).getByRole("radio", { name: "Graph" }).click();
    await expect(page.locator('.dc-impact-node[data-node-id="visual:Overview/Sales by region"]')).toHaveAttribute("aria-pressed", "true");
    await expect(page.locator(".dc-impact-node")).not.toHaveCount(0);
    await panel(page).getByRole("radio", { name: "Table" }).click();
    await expect(panel(page).getByRole("combobox", { name: "Certainty" })).toHaveText(/Certain/);
    await expect(table(page).locator("tbody tr.dc-impact-row")).toHaveCount(6);
    await expect(row(page, "Sales by region")).toHaveAttribute("aria-selected", "true");
    await expect(page.getByRole("heading", { level: 2, name: "Sales by region" })).toBeVisible();
    await expect(panel(page).getByRole("combobox", { name: "Scope" })).toHaveText(/Whole plan/);

    // Row 2 is hidden in Offers.
    await groupButton(page, "offers").click();
    await expect(page.getByRole("group", { name: "Impact filters" })).toHaveCount(0);
  });

  test("a row link from Compare sets the row scope", async ({ page, request }) => {
    await scenario(request, "default");
    await page.goto("/");
    await page.getByRole("navigation", { name: "Main navigation" }).getByRole("button", { name: "Development Center" }).click();
    await expect(page.locator(".dc-busy-line")).toHaveCount(0);
    await page.locator(".dc-cell", { hasText: "Budget" }).first().click();
    await page.getByRole("button", { name: "Show impact of this row" }).click();
    await expect(page.getByRole("tab", { name: "Impact" })).toHaveAttribute("aria-selected", "true");
    await expect(panel(page).getByRole("combobox", { name: "Scope" })).toHaveText(/Row: Budget/);
  });
});

test.describe("Status rule, actions, bulk, and toast", () => {
  test("status chips, primary action order, row menu, pane actions, bulk actions, and the toast blocking count", async ({ page, request }) => {
    await scenario(request, "default");
    await openImpact(page);

    // Status rule: blocking flag, information for "not changed by this plan", warning for the rest. Possible never blocks.
    await expect(row(page, "Budget Variance").locator('[data-slot="status-badge"]')).toHaveText("Blocking");
    await expect(row(page, "Budget card").locator('[data-slot="status-badge"]')).toHaveText("Information");
    await expect(row(page, "Region slicer").locator('[data-slot="status-badge"]')).toHaveText("Warning");
    await expect(row(page, "Region slicer")).toContainText("Possible");
    // Sort: blocking, severity, name.
    const names = await table(page).locator("tbody tr.dc-impact-row .dc-impact-name").allTextContents();
    expect(names).toEqual(["Budget Variance", "Margin %", "Margin trend", "Sales by region", "Sales YTD", "Region slicer", "Budget card"]);

    // Primary action order: Include in rewrite before others; Repoint before Cascade.
    await expect(row(page, "Margin trend").getByRole("button", { name: "Include in rewrite" })).toBeVisible();
    await expect(row(page, "Sales by region").getByRole("button", { name: "Repoint" })).toBeVisible();
    await row(page, "Sales by region").getByRole("button", { name: "More actions for Sales by region" }).click();
    const menu = page.getByRole("menu");
    await expect(menu.getByRole("menuitem")).toHaveText(["Open item", "Keep blocked", "Cascade", "Remove field"]);
    await page.keyboard.press("Escape");

    // Single action: the toast gives the blocking count.
    await row(page, "Margin %").getByRole("button", { name: "Include in rewrite" }).click();
    await expect(page.getByText("1 item resolved. 5 blocking left.")).toBeVisible();
    await expect(row(page, "Margin %").locator('[data-slot="status-badge"]')).toHaveText("Warning");

    // Bulk Include in rewrite: one item can, one cannot.
    await row(page, "Margin trend").getByRole("checkbox").click();
    await row(page, "Budget Variance").getByRole("checkbox").click();
    const bulk = page.getByRole("group", { name: "Bulk actions" });
    await expect(bulk).toContainText("2 selected");
    await bulk.getByRole("button", { name: "Include in rewrite" }).click();
    await expect(page.getByText("1 item resolved. 4 blocking left. 1 item cannot use this action.")).toBeVisible();
    await expect(bulk).toContainText("1 selected");
    await bulk.getByRole("button", { name: "Clear selection" }).click();

    // Bulk Add from donor on Needs.
    await groupButton(page, "needs").click();
    await row(page, "Region Code").getByRole("checkbox").click();
    await row(page, "Currency").getByRole("checkbox").click();
    await page.getByRole("group", { name: "Bulk actions" }).getByRole("button", { name: "Add from donor" }).click();
    await expect(page.getByText("2 items resolved. 2 blocking left.")).toBeVisible();

    // Pane actions: each action has one line; Map to target takes its input in the pane.
    await groupButton(page, "breaks").click();
    await row(page, "Sales by region").getByRole("button", { name: "Sales by region", exact: true }).click();
    const pane = page.locator('[data-slot="side-pane"]');
    await expect(pane).toContainText("The plan stays not valid until you resolve this item.");
    await expect(pane.getByRole("button", { name: "Select removal policy" })).toBeVisible();
    await expect(pane).toContainText("Remove the field from this visual.");
    await pane.getByRole("button", { name: "Show other paths" }).click();
    await expect(pane.getByRole("heading", { name: "Other paths" })).toBeVisible();
    await expect(pane).toContainText("Budget Total");
    await pane.getByRole("button", { name: "Close" }).click();
    await expect(row(page, "Sales by region").getByRole("button", { name: "Sales by region", exact: true })).toBeFocused();
  });

  test("Map to target from a row opens the pane with the input; the action resolves the item", async ({ page, request }) => {
    await scenario(request, "default");
    await openImpact(page);
    await groupButton(page, "needs").click();
    await row(page, "Currency").getByRole("button", { name: "Map to target" }).click();
    const field = page.getByLabel("Target object");
    await expect(field).toBeFocused();
    await field.fill("Rates");
    await page.locator('[data-slot="side-pane"]').getByRole("button", { name: "Map to target" }).click();
    await expect(page.getByText("1 item resolved. 5 blocking left.")).toBeVisible();
  });
});

test.describe("Completeness strip", () => {
  test("open by default when incomplete, closed after the user closes it, and Show 20 more", async ({ page, request }) => {
    await scenario(request, "default");
    const many = Array.from({ length: 45 }, (_, index) => `Type ${String(index).padStart(2, "0")}`);
    await setImpact(request, { completeness: { status: "incomplete", not_checked_object_types: many, unresolved_bindings: [], unreadable_reports: [], bookmarks: [], possible_only_areas: [] } });
    await openImpact(page);
    const strip = page.locator(".dc-complete");
    await expect(strip.locator('[data-slot="status-badge"]')).toHaveText("Incomplete: 45 areas");
    await expect(strip.locator(".dc-complete-entry")).toHaveCount(20);
    await strip.getByRole("button", { name: "Show 20 more" }).click();
    await expect(strip.locator(".dc-complete-entry")).toHaveCount(40);
    await strip.getByRole("button", { name: "Show 20 more" }).click();
    await expect(strip.locator(".dc-complete-entry")).toHaveCount(45);
    await expect(strip.getByRole("button", { name: "Show 20 more" })).toHaveCount(0);
    await strip.getByRole("button", { name: "Hide areas" }).click();
    await expect(strip.locator(".dc-complete-entry")).toHaveCount(0);

    // After a reload of the tab in the same session, the areas stay closed.
    await page.getByRole("tab", { name: "Compare" }).click();
    await page.getByRole("tab", { name: "Impact" }).click();
    await expect(strip.getByRole("button", { name: "Show areas" })).toBeVisible();

    await setImpact(request, { completeness: { status: "complete" } });
    await page.reload();
    await page.getByRole("navigation", { name: "Main navigation" }).getByRole("button", { name: "Development Center" }).click();
    await page.getByRole("tab", { name: "Impact" }).click();
    await expect(page.locator(".dc-complete [data-slot='status-badge']")).toHaveText("Complete");
    await expect(page.locator(".dc-complete-entry")).toHaveCount(0);
  });
});

test.describe("Graph view", () => {
  test("rank order Tab, arrows along edges, node names (A12), zoom buttons, and Show as table keeps the selection", async ({ page, request }) => {
    await scenario(request, "default");
    await openImpact(page);
    await panel(page).getByRole("radio", { name: "Graph" }).click();
    const nodes = page.locator(".dc-impact-node");
    await expect(nodes.first()).toBeVisible();
    await expect(page.getByRole("button", { name: "visual Sales by region, Blocking, breaks, 2 steps from the change" })).toBeVisible();
    // Solid edge = certain, dashed = possible.
    expect(await page.locator('.dc-impact-edge[data-certain="false"]').count()).toBeGreaterThan(0);
    expect(await page.locator('.dc-impact-edge[data-certain="true"]').count()).toBeGreaterThan(0);

    // Tab in rank order: DOM order is rank order.
    const ranks = await nodes.evaluateAll((list) => list.map((node) => Number(/, (\d+) steps from the change$/.exec(node.getAttribute("aria-label"))[1])));
    expect(ranks).toEqual([...ranks].sort((a, b) => a - b));
    await nodes.first().focus();
    await page.keyboard.press("Tab");
    await expect(nodes.nth(1)).toBeFocused();

    // Arrows along edges.
    const budget = page.locator('.dc-impact-node[data-node-id="table:Budget"]');
    await budget.focus();
    await page.keyboard.press("ArrowRight");
    const next = await page.evaluate(() => document.activeElement.dataset.nodeId);
    expect(["measure:Budget/Budget Amount", "visual:Budget page/Budget card"]).toContain(next);
    await page.keyboard.press("ArrowLeft");
    await expect(budget).toBeFocused();

    // Zoom buttons (A22).
    await page.getByRole("button", { name: "Zoom out" }).click();
    await expect(page.locator(".dc-impact-zoom-value")).toHaveText("80%");
    await page.getByRole("button", { name: "Fit view" }).click();

    // Enter opens the item; Show as table keeps the selection.
    await page.locator('.dc-impact-node[data-node-id="visual:Overview/Margin trend"]').focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("heading", { level: 2, name: "Margin trend" })).toBeVisible();
    await page.getByRole("button", { name: "Show as table" }).click();
    await expect(row(page, "Margin trend")).toHaveAttribute("aria-selected", "true");
  });

  test("more than 150 items show Too many items with Open table", async ({ page, request }) => {
    test.setTimeout(60000);
    await scenario(request, "large-5000-rows");
    await openImpact(page);
    await panel(page).getByRole("radio", { name: "Graph" }).click();
    await expect(page.getByRole("heading", { name: "Too many items for the graph" })).toBeVisible();
    await page.getByRole("button", { name: "Open table" }).click();
    await expect(panel(page).getByRole("radio", { name: "Table" })).toHaveAttribute("aria-checked", "true");
  });
});

test.describe("Wireframe view", () => {
  test("each status has pattern, icon, and word (A4); Visual list in reading order; donor offer checkboxes", async ({ page, request }) => {
    await scenario(request, "default");
    await openImpact(page);
    await panel(page).getByRole("radio", { name: "Wireframe" }).click();
    const canvas = page.getByRole("group", { name: "Page Overview" });
    await expect(canvas).toBeVisible();
    const expected = {
      removed: { word: "Removed", style: "solid", width: "1px" },
      breaks: { word: "Breaks", style: "solid", width: "3px" },
      changes: { word: "Changes", style: "dashed", width: "2px" },
      new: { word: "New", style: "dotted", width: "2px" },
      not_checked: { word: "Not checked", style: "dashed", width: "1px" },
    };
    for (const [status, spec] of Object.entries(expected)) {
      const box = canvas.locator(`.dc-wire-box[data-status="${status}"]`).first();
      await expect(box.locator(".dc-wire-status svg")).toHaveCount(1);
      await expect(box.locator(".dc-wire-status")).toHaveText(spec.word);
      const css = await box.evaluate((node) => {
        const style = getComputedStyle(node);
        return { style: style.borderTopStyle, width: style.borderTopWidth, image: style.backgroundImage };
      });
      expect([css.style, css.width], status).toEqual([spec.style, spec.width]);
      if (status === "removed") expect(css.image).toContain("repeating-linear-gradient");
    }
    await expect(canvas.locator('.dc-wire-box[data-status="unchanged"] .dc-wire-status')).toHaveCount(0);
    await expect(page.getByRole("button", { name: "gauge Budget gauge, Removed" })).toBeVisible();

    // Tab in reading order.
    const order = await canvas.locator(".dc-wire-title").allTextContents();
    expect(order).toEqual(["Sales by region", "Margin trend", "Budget gauge", "Net sales card", "Target card", "Custom map"]);

    // Visual list in reading order.
    await panel(page).getByRole("button", { name: "Visual list" }).click();
    const list = page.getByRole("list", { name: "Page Overview" });
    await expect(list.locator(".dc-wire-list-open")).toHaveText(order);

    // Page list.
    await panel(page).getByRole("button", { name: "Drawing" }).click();
    await page.getByRole("navigation", { name: "Pages" }).getByRole("button", { name: "Details" }).click();
    await expect(page.getByRole("group", { name: "Page Details" })).toBeVisible();

    // A donor report: offer visuals have a checkbox that calls offer_select.
    await chooseSelect(page, "Report", "Sales model (donor, now)");
    const offer = page.getByRole("checkbox", { name: "Copy Top products to the target report" });
    await expect(offer).toHaveAttribute("aria-checked", "false");
    await offer.click();
    await expect(offer).toHaveAttribute("aria-checked", "true");
    await expect(page.getByRole("checkbox", { name: "Copy Sales KPI to the target report" })).toHaveCount(0);
  });
});

test.describe("Offers", () => {
  test("page checkbox mixed state and the Needs banner with Open Needs", async ({ page, request }) => {
    await scenario(request, "default");
    await openImpact(page);
    await groupButton(page, "offers").click();
    const pageBox = page.getByRole("checkbox", { name: "Select all items on page Overview" });
    await expect(pageBox).toHaveAttribute("aria-checked", "false");
    await page.getByRole("checkbox", { name: "Top products", exact: true }).click();
    await expect(pageBox).toHaveAttribute("aria-checked", "mixed");
    const banner = page.locator('[data-banner="offer-needs"]');
    await expect(banner).toContainText("1 field needs an action before the copy can work.");
    await pageBox.click();
    await expect(pageBox).toHaveAttribute("aria-checked", "true");
    await expect(page.getByRole("checkbox", { name: "Year filter", exact: true })).toHaveAttribute("aria-checked", "true");
    await pageBox.click();
    await expect(pageBox).toHaveAttribute("aria-checked", "false");
    await expect(banner).toHaveCount(0);

    // A bookmark is information only and has no checkbox.
    const bookmark = page.locator('[data-offer-id="bookmark:Finance report/Year end"]');
    await expect(bookmark).toContainText("Information only");
    await expect(bookmark.getByRole("checkbox")).toHaveCount(0);

    await page.getByRole("checkbox", { name: "Margin by month", exact: true }).click();
    await expect(banner).toContainText("2 fields need an action before the copy can work.");
    await banner.getByRole("button", { name: "Open Needs" }).click();
    await expect(groupButton(page, "needs")).toHaveAttribute("aria-checked", "true");
  });
});

test.describe("Include open proposals", () => {
  test("the switch adds proposal items with the Proposed tag and shows the banner", async ({ page, request }) => {
    await scenario(request, "default");
    await openImpact(page);
    await expect(page.locator('[data-banner="proposals"]')).toHaveCount(0);
    await expect(row(page, "Net sales card")).toHaveCount(0);
    await page.getByRole("switch", { name: "Include open proposals" }).click();
    await expect(page.locator('[data-banner="proposals"]')).toHaveText("This view includes 1 open agent proposal. Apply uses only accepted choices.");
    await expect(row(page, "Net sales card")).toContainText("Proposed");
    await expect(row(page, "Margin %")).not.toContainText("Proposed");
    await page.getByRole("switch", { name: "Include open proposals" }).click();
    await expect(row(page, "Net sales card")).toHaveCount(0);
  });
});

test.describe("Removal policy dialog", () => {
  test("Block, Cascade (destructive), Repoint (disabled until a candidate), and focus rules (A9)", async ({ page, request }) => {
    await scenario(request, "default");
    await openImpact(page);
    await row(page, "Sales by region").getByRole("button", { name: "Sales by region", exact: true }).click();
    const trigger = page.locator('[data-slot="side-pane"]').getByRole("button", { name: "Select removal policy" });
    await trigger.click();
    const dialog = page.getByRole("dialog", { name: "Removal policy for Budget" });
    await expect(dialog).toBeVisible();
    // Initial focus: the policy radio group.
    await expect(dialog.getByRole("radio", { name: "Block" })).toBeFocused();
    await expect(dialog).toContainText("3 objects use this table.");
    await expect(dialog.getByRole("button", { name: "Use Block" })).toHaveAttribute("data-variant", "default");
    expect(await axeViolations(page, { include: '[role="dialog"]' })).toEqual([]);

    // Focus trap: Tab stays in the dialog.
    for (let index = 0; index < 8; index += 1) {
      await page.keyboard.press("Tab");
      expect(await page.evaluate(() => Boolean(document.activeElement.closest('[role="dialog"]')))).toBe(true);
    }

    // Cascade: table of effects, destructive confirm.
    await dialog.getByRole("radio", { name: "Cascade" }).click();
    await expect(dialog.getByRole("table")).toContainText("Field removed from visual");
    const cascade = dialog.getByRole("button", { name: "Use Cascade (remove 3 objects)" });
    await expect(cascade).toHaveAttribute("data-variant", "destructive");

    // Repoint: disabled until a candidate; a type warning shows.
    await dialog.getByRole("radio", { name: "Repoint" }).click();
    const repoint = dialog.getByRole("button", { name: "Use Repoint" });
    await expect(repoint).toBeDisabled();
    await dialog.getByRole("combobox", { name: "Replace each reference with" }).click();
    await dialog.getByRole("combobox", { name: "Replace each reference with" }).press("ArrowDown");
    await page.getByRole("option", { name: /Targets/ }).click();
    await expect(dialog).toContainText("Data type is different: string, not table");
    await expect(repoint).toBeEnabled();

    // Escape keeps the old policy and returns focus to the trigger.
    await page.keyboard.press("Escape");
    if (await dialog.isVisible()) await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
    await expect(trigger).toBeFocused();
    await expect(page.locator('[data-slot="side-pane"]')).toContainText("Policy");
    await expect(page.locator(".dc-impact-pane-facts")).toContainText("Block");

    // Confirm Cascade: the items of the row stop blocking; focus returns to the trigger.
    await trigger.click();
    await dialog.getByRole("radio", { name: "Cascade" }).click();
    await dialog.getByRole("button", { name: "Use Cascade (remove 3 objects)" }).click();
    await expect(dialog).toHaveCount(0);
    await expect(trigger).toBeFocused();
    await expect(page.getByText("2 items resolved. 4 blocking left.")).toBeVisible();
    await expect(page.locator(".dc-impact-pane-facts")).toContainText("Cascade");
    await expect(row(page, "Budget Variance").locator('[data-slot="status-badge"]')).toHaveText("Warning");
  });

  test("the row primary Repoint opens the dialog with Repoint selected", async ({ page, request }) => {
    await scenario(request, "default");
    await openImpact(page);
    const primary = row(page, "Sales by region").getByRole("button", { name: "Repoint" });
    await primary.click();
    const dialog = page.getByRole("dialog", { name: "Removal policy for Budget" });
    await expect(dialog.getByRole("radio", { name: "Repoint" })).toBeFocused();
    await expect(dialog.getByRole("radio", { name: "Repoint" })).toHaveAttribute("aria-checked", "true");
    await dialog.getByRole("button", { name: "Cancel" }).click();
    await expect(primary).toBeFocused();
  });
});

test.describe("Accessibility and layout (A1, A18)", () => {
  test("axe has zero violations in both themes on each view, and no page overflow at 1280 x 900", async ({ page, request }) => {
    await scenario(request, "default");
    await openImpact(page);
    for (const view of ["Table", "Graph", "Wireframe"]) {
      await panel(page).getByRole("radio", { name: view }).click();
      await page.waitForTimeout(100);
      for (const theme of ["dark", "light"]) {
        // The same change as the app theme switch (App.jsx useTheme).
        await page.evaluate((value) => {
          const root = document.documentElement;
          root.classList.toggle("dark", value === "dark");
          if (value === "light") root.dataset.theme = "light";
          else delete root.dataset.theme;
        }, theme);
        await page.waitForTimeout(250);
        expect(await axeViolations(page), `${view} (${theme})`).toEqual([]);
      }
      expect(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth), `${view} overflow`).toBe(false);
    }
    await groupButton(page, "offers").click();
    expect(await axeViolations(page), "Offers").toEqual([]);
  });
});

test.describe("Performance budgets on large-5000-rows (P1 to P5, CI limit 2 times the budget)", () => {
  const median = (values) => [...values].sort((a, b) => a - b)[Math.floor(values.length / 2)];

  test("P1, P2, P3, P4, and P5", async ({ page, request }) => {
    test.setTimeout(120000);
    await scenario(request, "large-5000-rows");
    await openImpact(page);
    await expect(table(page).locator("tbody tr.dc-impact-row").first()).toBeVisible();

    // P1 (reply to first rows painted, 300 ms) and P2 (filter input to new rows painted, 500 ms): 5 runs each.
    const p1 = [];
    const p2 = [];
    const blockingSwitch = page.getByRole("switch", { name: "Blocking only" });
    for (let run = 0; run < 5; run += 1) {
      await page.evaluate(() => performance.clearMarks());
      await blockingSwitch.click();
      await page.waitForFunction(() => {
        const painted = performance.getEntriesByName("dc-impact-painted");
        const reply = performance.getEntriesByName("dc-impact-reply");
        return painted.length && reply.length && painted.at(-1).startTime >= reply.at(-1).startTime;
      });
      const values = await page.evaluate(() => {
        const painted = performance.getEntriesByName("dc-impact-painted").at(-1).startTime;
        const reply = performance.getEntriesByName("dc-impact-reply").at(-1).startTime;
        const input = performance.getEntriesByName("dc-impact-input")[0].startTime;
        return { p1: painted - reply, p2: painted - input };
      });
      p1.push(values.p1);
      p2.push(values.p2);
    }
    expect(median(p1), `P1 runs ${p1.join(", ")}`).toBeLessThanOrEqual(600);
    expect(median(p2), `P2 runs ${p2.join(", ")}`).toBeLessThanOrEqual(1000);
    if (await blockingSwitch.getAttribute("aria-checked") === "true") await blockingSwitch.click();
    await expect(page.locator(".dc-impact-large")).toContainText("of 3", { timeout: 10000 });

    // P3 (no long task over 50 ms during wheel and jump scroll) and P4 (80 rows or fewer in the DOM).
    await page.evaluate(() => {
      window.__longTasks = [];
      new PerformanceObserver((list) => window.__longTasks.push(...list.getEntries().map((entry) => entry.duration))).observe({ type: "longtask", buffered: false });
    });
    const scroller = page.locator(".dc-impact-scroll");
    await scroller.hover();
    let maxRows = 0;
    for (let step = 0; step < 10; step += 1) {
      await page.mouse.wheel(0, 900);
      await page.waitForTimeout(30);
      maxRows = Math.max(maxRows, await page.locator(".dc-impact-row").count());
    }
    for (const fraction of [0.3, 0.7, 0.95, 0.1]) {
      await scroller.evaluate((node, value) => { node.scrollTop = node.scrollHeight * value; }, fraction);
      await page.waitForTimeout(150);
      maxRows = Math.max(maxRows, await page.locator(".dc-impact-row").count());
    }
    await expect(table(page).locator("tbody tr.dc-impact-row:not(.dc-impact-row-wait)").first()).toBeVisible();
    const longTasks = await page.evaluate(() => window.__longTasks);
    expect(Math.max(0, ...longTasks), `P3 long tasks ${longTasks.join(", ")}`).toBeLessThanOrEqual(100);
    expect(maxRows, "P4 rows in the DOM").toBeLessThanOrEqual(80);

    // P5 (graph of 150 nodes or fewer: reply to layout and paint, 500 ms): 5 runs.
    await chooseSelect(page, "Certainty", "Possible");
    await panel(page).getByRole("radio", { name: "Graph" }).click();
    await expect(page.locator(".dc-impact-node").first()).toBeVisible();
    const p5 = [];
    for (let run = 0; run < 5; run += 1) {
      await page.evaluate(() => performance.clearMarks());
      // The source filter changes the query but keeps the same 100 possible items, so each run draws the graph.
      await panel(page).getByRole("combobox", { name: "Model or report" }).click();
      await page.getByRole("option").nth(run % 2 === 0 ? 1 : 0).click();
      await page.waitForFunction(() => {
        const painted = performance.getEntriesByName("dc-impact-graph-painted");
        const reply = performance.getEntriesByName("dc-impact-reply");
        return painted.length && reply.length && painted.at(-1).startTime >= reply.at(-1).startTime;
      }, null, { timeout: 10000 }).catch(() => null);
      const value = await page.evaluate(() => {
        const painted = performance.getEntriesByName("dc-impact-graph-painted").at(-1);
        const reply = performance.getEntriesByName("dc-impact-reply").at(-1);
        return painted && reply ? painted.startTime - reply.startTime : null;
      });
      if (value !== null) p5.push(value);
    }
    expect(p5.length, "P5 runs with a graph").toBe(5);
    expect(median(p5), `P5 runs ${p5.join(", ")}`).toBeLessThanOrEqual(1000);
    expect(await page.locator(".dc-impact-node").count()).toBeLessThanOrEqual(150);
  });
});
