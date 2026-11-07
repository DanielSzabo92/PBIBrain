// Step U7: Plan view without Apply (UI design 4.6, 5.5, 8, 9, 11).
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

async function setPlan(request, data) {
  const res = await request.post("/__test__/plan", { data });
  expect(res.ok()).toBe(true);
}

async function delay(request, path, ms, extra = {}) {
  await request.post("/__test__/delay", { data: { path, ms, ...extra } });
}

async function openDevCenter(page) {
  await page.goto("/");
  await page.getByRole("navigation", { name: "Main navigation" }).getByRole("button", { name: "Merge models" }).click();
}

async function workReady(page, name = "Sales and finance merge") {
  await expect(page.getByRole("heading", { level: 1, name })).toBeVisible();
  await expect(page.locator(".dc-busy-line")).toHaveCount(0);
}

async function openPlanTab(page) {
  await page.getByRole("tab", { name: /^Plan/ }).click();
  await expect(page.locator(".dc-plan-strip")).toBeVisible();
}

test.describe("Plan status strip, header sync, and empty state", () => {
  test("valid_with_warnings strip, header status button, and Plan tab count agree with GET plan", async ({ page, request }) => {
    await scenario(request, "default");
    await openDevCenter(page);
    await workReady(page);

    const headerStatusBtn = page.locator(".dc-work-head").getByRole("button", { name: /Valid with 1 warning/ });
    await expect(headerStatusBtn).toBeVisible();
    await expect(page.getByRole("tab", { name: "Plan" })).toBeVisible();

    // Clicking the header status button opens the Plan tab.
    await headerStatusBtn.click();
    const strip = page.locator(".dc-plan-strip");
    await expect(strip).toBeVisible();
    await expect(strip.locator('[data-slot="status-badge"]')).toHaveText("Valid with 1 warning");
    await expect(strip.locator(".dc-plan-strip-body")).toHaveText("3 plan steps, 1 warning. Full check 10:00.");

    // Default plan has 0 deletes, so Apply plan wears the primary (default) variant and is enabled.
    const applyBtn = strip.getByRole("button", { name: "Apply plan" });
    await expect(applyBtn).toBeEnabled();
    await expect(applyBtn).toHaveAttribute("data-variant", "default");
  });

  test("apply-ready valid strip wears the destructive variant when the plan deletes objects", async ({ page, request }) => {
    await scenario(request, "apply-ready");
    await openDevCenter(page);
    await workReady(page);

    await expect(page.locator(".dc-work-head").getByRole("button", { name: /^Valid\./ })).toBeVisible();
    await expect(page.getByRole("tab", { name: "Plan" })).toBeVisible();

    await openPlanTab(page);
    const strip = page.locator(".dc-plan-strip");
    await expect(strip.locator('[data-slot="status-badge"]')).toHaveText("Valid");
    await expect(strip.locator(".dc-plan-strip-body")).toHaveText("5 plan steps. Full check 10:00.");

    const applyBtn = strip.getByRole("button", { name: "Apply plan" });
    await expect(applyBtn).toBeEnabled();
    await expect(applyBtn).toHaveAttribute("data-variant", "destructive");
  });

  test("invalid strip disables Apply plan with the visible blocking reason in aria-describedby", async ({ page, request }) => {
    await scenario(request, "plan-invalid");
    await openDevCenter(page);
    await workReady(page);

    await expect(page.locator(".dc-work-head").getByRole("button", { name: /Plan not valid: 2 blocking/ })).toBeVisible();
    await expect(page.getByRole("tab", { name: /^Plan 2/ })).toBeVisible();

    await openPlanTab(page);
    const strip = page.locator(".dc-plan-strip");
    await expect(strip.locator('[data-slot="status-badge"]')).toHaveText("Plan not valid: 2 blocking");
    await expect(strip.locator(".dc-plan-strip-body")).toHaveText("2 blocking items in the plan. Full check 10:00.");

    const applyBtn = strip.getByRole("button", { name: "Apply plan" });
    await expect(applyBtn).toBeDisabled();
    const descId = await applyBtn.getAttribute("aria-describedby");
    expect(descId).toBe("dc-plan-apply-reason");
    await expect(page.locator(`#${descId}`)).toHaveText("Fix 2 items before you apply.");
  });

  test("empty plan state shows Nothing to apply, disables Apply plan with reason, and Open Compare switches tab", async ({ page, request }) => {
    await scenario(request, "default");
    await setPlan(request, {
      status: "valid",
      steps: [],
      operations: [],
      blocking: [],
      warnings: [],
      summary: {
        model: {
          steps: 0,
          created: { total: 0, by_type: {} },
          deleted: { total: 0, by_type: {} },
          modified: { total: 0, by_type: {} },
          renamed: { total: 0, by_type: {} },
        },
        report: {
          steps: 0,
          created: { total: 0, by_type: {} },
          deleted: { total: 0, by_type: {} },
          modified: { total: 0, by_type: {} },
          renamed: { total: 0, by_type: {} },
        },
        steps: 0,
      },
    });
    await openDevCenter(page);
    await workReady(page);

    await openPlanTab(page);
    const strip = page.locator(".dc-plan-strip");
    await expect(strip.locator('[data-slot="status-badge"]')).toHaveText("Valid");
    await expect(strip.locator(".dc-plan-strip-body")).toHaveText("The target matches your Merge Choices. Full check 10:00.");

    const applyBtn = strip.getByRole("button", { name: "Apply plan" });
    await expect(applyBtn).toBeDisabled();
    await expect(page.locator("#dc-plan-apply-reason")).toHaveText("Nothing to apply.");

    const empty = page.locator('[data-slot="empty-state"]');
    await expect(empty).toContainText("Nothing to apply");
    await expect(empty).toContainText("The target matches your Merge Choices. Change a Merge Choice in Compare to build a new plan.");

    await empty.getByRole("button", { name: "Open Compare" }).click();
    await expect(page.getByRole("tab", { name: "Compare" })).toHaveAttribute("aria-selected", "true");
  });

  test("checking state shows Checking plan in strip and disables Apply plan", async ({ page, request }) => {
    await scenario(request, "default");
    await setPlan(request, { plan_state: "checking" });
    await openDevCenter(page);
    await workReady(page);

    await openPlanTab(page);
    const strip = page.locator(".dc-plan-strip");
    await expect(strip.locator('[data-slot="status-badge"]')).toHaveText("Checking plan");
    await expect(strip.locator(".dc-plan-strip-body")).toHaveText("Validating expressions and dependencies.");
    await expect(page.locator("#dc-plan-apply-reason")).toHaveText("Wait for the plan check.");
    await expect(strip.getByRole("button", { name: "Apply plan" })).toBeDisabled();
  });
});

test.describe("Before you apply block list order and fix actions", () => {
  test("orders blocks as marks, plan blocking, Desktop, non-canonical files, and validation failures", async ({ page, request }) => {
    await scenario(request, "sources-changed");
    await setPlan(request, {
      status: "invalid",
      blocking: [
        {
          actions: [],
          item_id: "dax_parse:row-net-sales",
          kind: "dax_parse",
          message: "The expression of Net Sales has a syntax error at line 4, column 8.",
          object: { name: "Net Sales", object_type: "measure", table: "Sales" },
          params: { line: 4, column: 8 },
          row_id: "row_0000000000000003",
          row_key: "row-net-sales",
          step_id: "step-3",
        },
        {
          actions: [],
          item_id: "need_missing:row-net-sales",
          kind: "need_missing",
          message: "Net Sales needs ExchangeRate, which the target does not have.",
          object: { name: "Net Sales", object_type: "measure", table: "Sales" },
          params: { needed: "ExchangeRate" },
          row_id: "row_0000000000000003",
          row_key: "row-net-sales",
          step_id: "step-3",
        },
        {
          actions: [],
          item_id: "name_clash:row-customer",
          kind: "name_clash",
          message: "Name clash: Customer exists in target and in Sales model.",
          object: { name: "Customer", object_type: "table", table: null },
          params: { name: "Customer", source_a: "target", source_b: "Sales model" },
          row_id: "row_0000000000000001",
          row_key: "row-customer",
          step_id: "step-1",
        },
      ],
      apply_preview: {
        desktop_state: "open_unsaved",
        non_canonical_files: ["definition/tables/Sales.tmdl", "definition/tables/Customer.tmdl"],
      },
    });

    await openDevCenter(page);
    await workReady(page);
    await openPlanTab(page);

    const blockRows = page.locator(".dc-plan-block-row");
    await expect(blockRows).toHaveCount(6);
    await expect(page.locator(".dc-plan-blocks-count")).toHaveText("6 items stop the apply");

    const categories = await blockRows.evaluateAll((nodes) => nodes.map((n) => n.getAttribute("data-block-category")));
    expect(categories).toEqual(["marks", "plan", "plan", "desktop", "files", "validation"]);

    await expect(blockRows.nth(0)).toContainText("3 rows changed in their source, and you did not confirm them.");
    await expect(blockRows.nth(1)).toContainText("Net Sales needs ExchangeRate, which the target does not have.");
    await expect(blockRows.nth(2)).toContainText("Name clash: Customer exists in target and in Sales model.");
    await expect(blockRows.nth(3)).toContainText("Power BI Desktop has unsaved changes in Combined model.");
    await expect(blockRows.nth(4)).toContainText("2 target files are not in the Power BI Desktop format.");
    await expect(blockRows.nth(4)).toContainText("definition/tables/Sales.tmdl");
    await expect(blockRows.nth(5)).toContainText("The expression of Net Sales has a syntax error at line 4, column 8.");

    // (1) "Show these rows" opens Compare with the Marks filter chip active.
    await blockRows.nth(0).getByRole("button", { name: "Show these rows" }).click();
    await expect(page.getByRole("tab", { name: "Compare" })).toHaveAttribute("aria-selected", "true");
    await expect(page.locator('[data-slot="filter-chip"]').filter({ hasText: "Marks" })).toBeVisible();

    // Return to Plan and click "Show impact" on the need_missing block.
    await openPlanTab(page);
    await blockRows.nth(1).getByRole("button", { name: "Show impact" }).click();
    await expect(page.getByRole("tab", { name: "Impact" })).toHaveAttribute("aria-selected", "true");
    await expect(page.locator('[data-impact-row="row-net-sales"]')).toBeVisible();

    // Return to Plan and click "Show row" on the name_clash block.
    await openPlanTab(page);
    await blockRows.nth(2).getByRole("button", { name: "Show row" }).click();
    await expect(page.getByRole("tab", { name: "Compare" })).toHaveAttribute("aria-selected", "true");
    await expect(page.locator(".dc-row-pane")).toContainText("Customer");
  });

  test("removing a donor source with choices adds choice_source_removed to Before you apply", async ({ page, request }) => {
    await scenario(request, "default");
    await openDevCenter(page);
    await workReady(page);

    await page.getByRole("tab", { name: "Sources" }).click();
    await page.getByRole("button", { name: "Remove Finance model" }).click();
    await page.getByRole("alertdialog").getByRole("button", { name: "Remove source" }).click();

    await openPlanTab(page);
    await expect(page.locator(".dc-plan-strip").locator('[data-slot="status-badge"]')).toHaveText("Plan not valid: 1 blocking");
    const block = page.locator('.dc-plan-block-row[data-block-kind="choice_source_removed"]');
    await expect(block).toContainText("The Merge Choice for Gross Margin uses removed source Finance model.");
    await expect(block.getByRole("button", { name: "Show row" })).toBeVisible();
  });
});

test.describe("Summary, warnings, phases, filters, expand operations, Check plan, and proposals", () => {
  test("summary table, phases, All/Model/Report toggle, text filter (/ shortcut), and operation diff", async ({ page, request }) => {
    await scenario(request, "apply-ready");
    await openDevCenter(page);
    await workReady(page);
    await openPlanTab(page);

    // Summary table has Model and Report groups and styles delete count > 0 in .dc-plan-del.
    const summaryTable = page.locator(".dc-plan-summary-table");
    await expect(summaryTable).toContainText("Model");
    await expect(summaryTable).toContainText("Report");
    await expect(summaryTable.locator(".dc-plan-del")).toHaveText("1");

    // All 6 phases are visible in order.
    const phaseHeads = page.locator(".dc-plan-phase-head");
    await expect(phaseHeads).toHaveText([
      "Deletes (1)",
      "Renames (1)",
      "Creates (1)",
      "Changes (1)",
      "Expression rewrites (1)",
      "Report changes (1)",
    ]);

    // Filter by Model hides Report changes.
    const seg = page.getByRole("radiogroup", { name: "Filter steps by domain" });
    await seg.getByRole("radio", { name: "Model" }).click();
    await expect(phaseHeads).toHaveCount(5);
    await expect(page.locator('.dc-plan-phase[data-phase="report"]')).toHaveCount(0);

    // Filter by Report shows only Report changes.
    await seg.getByRole("radio", { name: "Report" }).click();
    await expect(phaseHeads).toHaveText(["Report changes (1)"]);

    // Back to All.
    await seg.getByRole("radio", { name: "All" }).click();
    await expect(phaseHeads).toHaveCount(6);

    // Pressing "/" focuses the step filter search box.
    await page.keyboard.press("/");
    const search = page.getByRole("searchbox", { name: "Filter steps by name" });
    await expect(search).toBeFocused();
    await search.fill("Gross Margin");
    await expect(phaseHeads).toHaveText(["Expression rewrites (1)"]);

    // Expand the Gross Margin rewrite step to inspect old and new text.
    const stepBtn = page.locator(".dc-plan-step-btn").first();
    await stepBtn.click();
    await expect(stepBtn).toHaveAttribute("aria-expanded", "true");
    const opDiff = page.locator(".dc-plan-op-diff");
    await expect(opDiff).toContainText("- DIVIDE([Net Sales], COUNTROWS(Customers))");
    await expect(opDiff).toContainText("+ DIVIDE([Net Sales], COUNTROWS(Customer))");
  });

  test("Check plan runs full validation, shows loading state, and updates full check time", async ({ page, request }) => {
    await scenario(request, "default");
    await openDevCenter(page);
    await workReady(page);
    await openPlanTab(page);

    // Warnings card and open proposals banner are visible in default scenario.
    await expect(page.locator(".dc-plan-warning-list")).toContainText(
      "Target differs from Finance model on format string, and the choice is Keep target.",
    );
    const proposalsInfo = page.locator(".dc-plan-proposals-info");
    await expect(proposalsInfo).toContainText("This plan uses accepted choices only. 1 agent proposal is open and is not in it.");

    // Delay plan-validate to observe the loading state.
    await delay(request, "/api/devcenter/plan-validate", 400, { once: true });
    const checkBtn = page.locator(".dc-plan-strip").getByRole("button", { name: "Check plan" });
    await checkBtn.click();
    await expect(page.locator(".dc-plan-strip").getByRole("button", { name: "Checking plan" })).toBeVisible();

    // After completion, full check time updates to 14:22.
    await expect(page.locator(".dc-plan-strip-body")).toHaveText("3 plan steps, 1 warning. Full check 14:22.");

    // Clicking "Open Agent" on the proposals info line opens the Agent tab.
    await proposalsInfo.getByRole("button", { name: "Open Agent" }).click();
    await expect(page.getByRole("tab", { name: /^Agent/ })).toHaveAttribute("aria-selected", "true");
  });
});

test.describe("Accessibility, themes, reduced motion, and 1280x900 layout (A1, A8, A15, A18)", () => {
  test("axe has zero violations in dark and light themes across plan states, and no page overflow", async ({ page, request }) => {
    for (const name of ["default", "plan-invalid", "apply-ready"]) {
      await scenario(request, name);
      await openDevCenter(page);
      await workReady(page);
      await openPlanTab(page);

      for (const theme of ["dark", "light"]) {
        await setTheme(page, theme);
        expect(await axeViolations(page), `${name} (${theme})`).toEqual([]);
      }

      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
      expect(overflow, `${name} horizontal overflow`).toBe(false);
    }
  });

  test("prefers-reduced-motion disables chevron transition on step rows", async ({ page, request }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await scenario(request, "default");
    await openDevCenter(page);
    await workReady(page);
    await openPlanTab(page);

    const transitionDuration = await page.locator(".dc-plan-chev").first().evaluate(
      (node) => getComputedStyle(node).transitionDuration,
    );
    expect(transitionDuration).toBe("0s");
  });
});
