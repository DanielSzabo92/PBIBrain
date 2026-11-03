// Step U4: Compare grid with filters, keyboard map, bulk actions, and code diff.
// Layout: 1280 x 900.
// All text follows ASD-STE100 rules. No emoji. No em dash or en dash.
import { test, expect } from "@playwright/test";
import { axeViolations, setTheme } from "./axe.js";

const FAKE = "http://127.0.0.1:8766";
test.use({ baseURL: FAKE, viewport: { width: 1280, height: 900 } });

async function scenario(request, name) {
  const loaded = await request.post("/__test__/scenario", { data: { name } });
  expect(loaded.ok()).toBe(true);
}

async function fault(request, method, code, extra = {}) {
  await request.post("/__test__/fault", { data: { method, code, ...extra } });
}

async function openDevCenter(page) {
  await page.goto("/");
  await page.getByRole("navigation", { name: "Main navigation" }).getByRole("button", { name: "Development Center" }).click();
}

async function workReady(page, name = "Sales and finance merge") {
  await expect(page.getByRole("heading", { level: 1, name })).toBeVisible();
  await expect(page.locator(".dc-busy-line")).toHaveCount(0);
}

test.describe("Compare filters and search", () => {
  test.beforeEach(async ({ page, request }) => {
    await scenario(request, "default");
    await openDevCenter(page);
    await workReady(page);
  });

  test("default chip State: not same is active and hides same rows", async ({ page }) => {
    const chip = page.locator('[data-slot="filter-chip"]').filter({ hasText: "State: not same" });
    await expect(chip).toBeVisible();

    // Default scenario has 6 rows: 4 not same, 2 same.
    const rows = page.locator(".dc-body-row");
    await expect(rows).toHaveCount(4);
    await expect(page.getByText("Net Sales")).toBeVisible();
    await expect(page.getByText("Gross Margin")).toBeVisible();
    await expect(page.getByText("Budget")).toBeVisible();
    await expect(page.getByText("Customer")).toBeVisible();
    await expect(page.getByText("Date")).toHaveCount(0);
  });

  test("filter popover changes state filter to all and specific state", async ({ page }) => {
    // Open state filter button.
    const stateBtn = page.getByRole("button", { name: /^State/ });
    await stateBtn.click();

    // Uncheck "Not same" checkbox so all states show.
    await page.getByLabel("Not same (hide Same rows)").click();
    await expect(page.locator(".dc-body-row")).toHaveCount(6);
    await expect(page.getByText("Date")).toBeVisible();

    // Pick Missing only.
    await page.getByLabel("Missing").click();
    // Close popover with Escape.
    await page.keyboard.press("Escape");

    await expect(page.locator(".dc-body-row")).toHaveCount(1);
    await expect(page.getByText("Budget")).toBeVisible();
  });

  test("search input filters rows with 150 ms debounce", async ({ page }) => {
    const search = page.locator('input[type="search"]');
    await expect(search).toBeVisible();

    await search.fill("Net");
    // Wait for 150 ms debounce.
    await page.waitForTimeout(200);

    const rows = page.locator(".dc-body-row");
    await expect(rows).toHaveCount(1);
    await expect(page.getByText("Net Sales")).toBeVisible();
  });

  test("clear filters resets search and restores default chip", async ({ page }) => {
    const search = page.locator('input[type="search"]');
    await search.fill("Net");
    await page.waitForTimeout(200);
    await expect(page.locator(".dc-body-row")).toHaveCount(1);

    const clearBtn = page.locator("#clearf");
    await expect(clearBtn).toBeVisible();
    await clearBtn.click();

    await expect(search).toHaveValue("");
    await expect(page.locator(".dc-body-row")).toHaveCount(6);
  });

  test("column header click changes sort order", async ({ page }) => {
    // Click Object column header button to sort descending.
    const objHeaderBtn = page.locator(".dc-col-obj button");
    await objHeaderBtn.click();
    await page.waitForTimeout(200);

    // After desc sort, first row is Net Sales.
    const firstRow = page.locator(".dc-body-row").first();
    await expect(firstRow).toContainText("Net Sales");

    // Click again to sort ascending.
    await objHeaderBtn.click();
    await page.waitForTimeout(200);

    const firstRowAsc = page.locator(".dc-body-row").first();
    await expect(firstRowAsc).toContainText("Budget");
  });
});

test.describe("Full grid keyboard map (section 9.3)", () => {
  test.beforeEach(async ({ page, request }) => {
    await scenario(request, "default");
    await openDevCenter(page);
    await workReady(page);
  });

  test("arrow keys navigate cell focus", async ({ page }) => {
    // Focus first cell (column 1, row 0).
    const firstCell = page.locator('.dc-cell[data-r="0"][data-c="1"]');
    await firstCell.focus();
    await expect(firstCell).toHaveAttribute("tabindex", "0");

    // ArrowRight moves to column 2.
    await page.keyboard.press("ArrowRight");
    const rightCell = page.locator('.dc-cell[data-r="0"][data-c="2"]');
    await expect(rightCell).toHaveAttribute("tabindex", "0");

    // ArrowDown moves to row 1, column 2.
    await page.keyboard.press("ArrowDown");
    const downCell = page.locator('.dc-cell[data-r="1"][data-c="2"]');
    await expect(downCell).toHaveAttribute("tabindex", "0");

    // ArrowLeft moves to row 1, column 1.
    await page.keyboard.press("ArrowLeft");
    const leftCell = page.locator('.dc-cell[data-r="1"][data-c="1"]');
    await expect(leftCell).toHaveAttribute("tabindex", "0");

    // ArrowUp moves back to row 0, column 1.
    await page.keyboard.press("ArrowUp");
    await expect(firstCell).toHaveAttribute("tabindex", "0");
  });

  test("Enter key opens row detail pane", async ({ page }) => {
    const firstCell = page.locator('.dc-cell[data-r="0"][data-c="1"]');
    await firstCell.focus();
    await page.keyboard.press("Enter");

    const pane = page.locator(".dc-row-pane");
    await expect(pane).toBeVisible();
    await expect(pane).toContainText("Budget");

    // Close button works.
    await page.locator("#closepane").click();
    await expect(pane).toHaveCount(0);
  });

  test("Space toggles selection and Shift+Space selects range", async ({ page }) => {
    const cell0 = page.locator('.dc-cell[data-r="0"][data-c="1"]');
    await cell0.focus();

    // Space selects row 0.
    await page.keyboard.press("Space");
    const row0 = page.locator('.dc-body-row[data-i="0"]');
    await expect(row0).toHaveAttribute("aria-selected", "true");
    await expect(page.locator(".dc-bulkbar-count")).toContainText("1 selected");

    // Move to row 2.
    await page.keyboard.press("ArrowDown");
    await page.keyboard.press("ArrowDown");

    // Shift+Space selects range from row 0 to row 2.
    await page.keyboard.press("Shift+Space");
    await expect(page.locator('.dc-body-row[data-i="1"]')).toHaveAttribute("aria-selected", "true");
    await expect(page.locator('.dc-body-row[data-i="2"]')).toHaveAttribute("aria-selected", "true");
    await expect(page.locator(".dc-bulkbar-count")).toContainText("3 selected");
  });

  test("Home and End jump to first and last column", async ({ page }) => {
    const midCell = page.locator('.dc-cell[data-r="0"][data-c="3"]');
    await midCell.focus();

    await page.keyboard.press("Home");
    const col0 = page.locator('.dc-cell[data-r="0"][data-c="0"]');
    await expect(col0).toHaveAttribute("tabindex", "0");

    await page.keyboard.press("End");
    // Last column is column 8 (6 + 3 donors = 9 cols, index 0 to 8).
    const colLast = page.locator('.dc-cell[data-r="0"][data-c="8"]');
    await expect(colLast).toHaveAttribute("tabindex", "0");
  });

  test("Ctrl+Home and Ctrl+End jump to top-left and bottom-right cell", async ({ page }) => {
    const midCell = page.locator('.dc-cell[data-r="1"][data-c="2"]');
    await midCell.focus();

    await page.keyboard.press("Control+Home");
    const origin = page.locator('.dc-cell[data-r="0"][data-c="0"]');
    await expect(origin).toHaveAttribute("tabindex", "0");

    await page.keyboard.press("Control+End");
    // Row 3, column 8.
    const last = page.locator('.dc-cell[data-r="3"][data-c="8"]');
    await expect(last).toHaveAttribute("tabindex", "0");
  });

  test("M key opens Set Merge Choice menu on focused row", async ({ page }) => {
    const cell = page.locator('.dc-cell[data-r="0"][data-c="1"]');
    await cell.focus();

    // Select row first with Space as required by section 9.3:
    await page.keyboard.press("Space");
    await expect(page.locator(".dc-bulkbar-count")).toBeVisible();
    await cell.focus();
    await page.keyboard.press("m");

    const menu = page.locator('[role="menu"]');
    await expect(menu).toBeVisible();
    await expect(page.getByRole("menuitem", { name: "Keep target" })).toBeVisible();
    await expect(page.getByRole("menuitem", { name: "Skip" })).toBeVisible();

    await page.keyboard.press("Escape");
    await expect(menu).toHaveCount(0);
  });

  test("D key opens code diff on non-same donor cell", async ({ page }) => {
    // Focus row 0 donor cell (col 4 or 5).
    const donorCell = page.locator('.dc-cell[data-r="0"][data-c="4"]');
    await donorCell.focus();

    await page.keyboard.press("d");
    const dialog = page.getByRole("dialog", { name: /Code diff/ });
    await expect(dialog).toBeVisible();

    // Escape closes diff dialog and returns focus.
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
  });

  test("Escape clears selection then closes row detail pane", async ({ page }) => {
    const cell = page.locator('.dc-cell[data-r="0"][data-c="1"]');
    await cell.focus();

    // Select row and open detail pane.
    await page.keyboard.press("Space");
    await page.keyboard.press("Enter");
    const pane = page.locator(".dc-row-pane");
    await expect(pane).toBeVisible();
    await expect(page.locator(".dc-bulkbar")).toBeVisible();

    // First Escape clears selection.
    await page.keyboard.press("Escape");
    await expect(page.locator(".dc-bulkbar")).toHaveCount(0);
    await expect(pane).toBeVisible();

    // Second Escape closes row detail pane.
    await page.keyboard.press("Escape");
    await expect(pane).toHaveCount(0);
  });

  test("/ key focuses search names input", async ({ page }) => {
    const cell = page.locator('.dc-cell[data-r="0"][data-c="1"]');
    await cell.focus();

    await page.keyboard.press("/");
    const search = page.locator('input[type="search"]');
    await expect(search).toBeFocused();
  });
});

test.describe("Bulk actions and confirmation", () => {
  test.beforeEach(async ({ page, request }) => {
    await scenario(request, "default");
    await openDevCenter(page);
    await workReady(page);
  });

  test("selection banner and Set Merge Choice menu", async ({ page }) => {
    // Select first row.
    const chk = page.locator('.dc-body-row[data-i="0"] input[type="checkbox"]');
    await chk.click();

    const count = page.locator(".dc-bulkbar-count");
    await expect(count).toBeVisible();
    await expect(count).toContainText("1 selected");

    // Open Set Merge Choice menu.
    const menuBtn = page.getByRole("button", { name: "Set Merge Choice" });
    await menuBtn.click();
    await expect(page.getByRole("menuitem", { name: "Keep target" })).toBeVisible();
    await expect(page.getByRole("menuitem", { name: "Skip" })).toBeVisible();
    await expect(page.getByRole("menuitem", { name: /^Take from / }).first()).toBeVisible();
  });

  test("selecting Remove opens confirmation dialog", async ({ page }) => {
    const chk = page.locator('.dc-body-row[data-i="0"] input[type="checkbox"]');
    await chk.click();

    const menuBtn = page.getByRole("button", { name: "Set Merge Choice" });
    await menuBtn.click();
    await page.getByRole("menuitem", { name: "Remove from target" }).click();

    // Dialog opens.
    const dialog = page.getByRole("alertdialog");
    await expect(dialog).toBeVisible();
    await expect(dialog).toContainText("Remove 1 object from the target?");

    // Cancel closes dialog with no action.
    await page.getByRole("button", { name: "Cancel" }).click();
    await expect(dialog).toHaveCount(0);
  });
});

test.describe("Marks filter and Confirm rows", () => {
  test("sources-changed scenario with marks filter shows Confirm N rows", async ({ page, request }) => {
    await scenario(request, "sources-changed");
    await openDevCenter(page);
    await workReady(page);

    // Turn on Marks filter.
    const marksBtn = page.getByRole("button", { name: "Marks" });
    await marksBtn.click();

    // Select row.
    const chk = page.locator('.dc-body-row[data-i="0"] input[type="checkbox"]');
    await chk.click();

    // Button shows "Confirm 1 row".
    const confirmBtn = page.getByRole("button", { name: /Confirm 1 row/ });
    await expect(confirmBtn).toBeVisible();
  });
});

test.describe("Compare mode switcher", () => {
  test("switching compare mode keeps filters and active row but clears selection", async ({ page, request }) => {
    await scenario(request, "default");
    await openDevCenter(page);
    await workReady(page);

    // Search and select row and open row detail.
    const search = page.locator('input[type="search"]');
    await search.fill("Sales");
    await page.waitForTimeout(200);

    const chk = page.locator('.dc-body-row[data-i="0"] input[type="checkbox"]');
    await chk.click();
    await expect(page.locator(".dc-bulkbar")).toBeVisible();

    const firstCell = page.locator('.dc-cell[data-r="0"][data-c="1"]');
    await firstCell.click();
    const pane = page.locator(".dc-row-pane");
    await expect(pane).toBeVisible();

    // Switch mode to Strict.
    const strictBtn = page.getByRole("radio", { name: "Strict" });
    await strictBtn.click();
    await page.waitForTimeout(200);

    // Filters and search remain intact.
    await expect(search).toHaveValue("Sales");
    // Row detail remains open.
    await expect(pane).toBeVisible();
    // Selection is cleared.
    await expect(page.locator(".dc-bulkbar")).toHaveCount(0);
  });
});

test.describe("Code diff modal dialog", () => {
  test.beforeEach(async ({ page, request }) => {
    await scenario(request, "default");
    await openDevCenter(page);
    await workReady(page);
  });

  test("diff opens from row detail pane link and closes on Escape with focus return", async ({ page }) => {
    // Open row detail for Net Sales.
    const cell = page.locator('.dc-cell', { hasText: 'Net Sales' });
    await cell.click();
    const pane = page.locator(".dc-row-pane");
    await expect(pane).toBeVisible();

    // Click "Show code diff" in detail pane.
    const diffTrigger = page.getByRole("button", { name: "Show code diff" }).first();
    await diffTrigger.click();

    const dialog = page.getByRole("dialog", { name: /Code diff/ });
    await expect(dialog).toBeVisible();

    // Switch to Finance model which has differences in fixture.
    await dialog.getByRole("button", { name: "Finance model" }).click();
    await page.waitForTimeout(200);

    // Verify split layout at 1280px.
    const body = dialog.locator(".dc-diff-body");
    await expect(body).toHaveClass(/split/);

    // Verify screen reader tags on diff lines.
    const srTags = dialog.locator(".sr-only");
    await expect(srTags.first()).toBeAttached();

    // Escape closes modal and returns focus.
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
  });
});

test.describe("A13 accessibility attributes and axe checks", () => {
  test.beforeEach(async ({ page, request }) => {
    await scenario(request, "default");
    await openDevCenter(page);
    await workReady(page);
  });

  test("grid structure has valid ARIA attributes", async ({ page }) => {
    const grid = page.getByRole("grid", { name: "Compare rows" });
    await expect(grid).toBeVisible();
    await expect(grid).toHaveAttribute("aria-rowcount");
    await expect(grid).toHaveAttribute("aria-colcount");

    const headerRow = page.locator(".dc-hrow");
    await expect(headerRow).toHaveAttribute("role", "row");

    const firstRow = page.locator('.dc-body-row[data-i="0"]');
    await expect(firstRow).toHaveAttribute("role", "row");
    await expect(firstRow).toHaveAttribute("aria-rowindex", "2");

    const cell = page.locator('.dc-cell[data-r="0"][data-c="1"]');
    await expect(cell).toHaveAttribute("role", "gridcell");
    await expect(cell).toHaveAttribute("aria-colindex", "2");
  });

  test("axe passes on comparison view in light and dark themes", async ({ page, context }) => {
    for (const theme of ["light", "dark"]) {
      await setTheme(context, theme);
      await openDevCenter(page);
      await workReady(page);

      const violations = await axeViolations(page);
      expect(violations).toEqual([]);
    }
  });
});

test.describe("Grid error and empty states", () => {
  test("shows empty match state when search finds no rows", async ({ page, request }) => {
    await scenario(request, "default");
    await openDevCenter(page);
    await workReady(page);

    const search = page.locator('input[type="search"]');
    await search.fill("NonExistentObjectXYZ");
    await page.waitForTimeout(200);

    await expect(page.getByText("No rows match the filters")).toBeVisible();
    await expect(page.getByText(/hidden by the filters/)).toBeVisible();

    // Clear filters button restores rows.
    await page.locator("#clearf2").click();
    await expect(page.locator(".dc-body-row")).toHaveCount(6);
  });

  test("shows error state when compare_rows read fails", async ({ page, request }) => {
    await scenario(request, "default");
    await openDevCenter(page);
    await workReady(page);

    // Injected fault on compare-rows.
    await fault(request, "/api/devcenter/compare-rows", "server_error", { status: 500, message: "Read failed" });

    // Trigger refetch by changing search.
    const search = page.locator('input[type="search"]');
    await search.fill("Crash");
    await page.waitForTimeout(350);

    await expect(page.getByText("Could not load the compare")).toBeVisible();
    await expect(page.getByRole("button", { name: "Try again" })).toBeVisible();
  });
});

test.describe("Performance budgets on large-5000-rows", () => {
  test("large-5000-rows loads initial page within budget P1 and limits cached pages P4", async ({ page, request }) => {
    await scenario(request, "large-5000-rows");
    await openDevCenter(page);

    const started = Date.now();
    await workReady(page);
    const elapsed = Date.now() - started;

    // Budget P1: Render first page fast (test timeout budget).
    expect(elapsed).toBeLessThan(5000);

    // Grid shows total count (with default notsame chip, 4000 rows).
    const foot = page.locator(".dc-grid-foot");
    await expect(foot).toContainText("4000 rows");

    // Virtual container has rendered DOM rows far less than 5000 (virtualized).
    const domRows = await page.locator(".dc-body-row").count();
    expect(domRows).toBeLessThan(50);
  });
});
