import { test, expect } from "@playwright/test";
import { axeViolations, setTheme } from "./axe.js";

// Step U5: naming rules UI, rule editor, and copy dialog (UI design 13, U5).
// One layout only: 1280 x 900 (user scope cut 2026-11-01).
const FAKE = "http://127.0.0.1:8766";
test.use({ baseURL: FAKE, viewport: { width: 1280, height: 900 } });

async function scenario(request, name) {
  const loaded = await request.post("/__test__/scenario", { data: { name } });
  expect(loaded.ok()).toBe(true);
}

async function fault(request, method, code, extra = {}) {
  await request.post("/__test__/fault", { data: { method, code, ...extra } });
}

async function setRules(request, payload) {
  await request.post("/__test__/rules", { data: payload });
}

async function openDevCenter(page) {
  page.on("pageerror", (err) => console.error("PAGE ERROR:", err));
  await page.goto("/");
  await page.getByRole("navigation", { name: "Main navigation" }).getByRole("button", { name: "Merge models" }).click();
}

async function noOverflow(page) {
  const overflow = await page.evaluate(() => document.scrollingElement.scrollWidth - document.scrollingElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
}

async function checkPage(page) {
  expect(await axeViolations(page)).toEqual([]);
  await noOverflow(page);
}

async function workReady(page, name = "Sales and finance merge") {
  await expect(page.getByRole("heading", { level: 1, name })).toBeVisible();
  await expect(page.locator(".dc-busy-line")).toHaveCount(0);
}

const tab = (page, name) => page.getByRole("tablist", { name: "Work area tabs" }).getByRole("tab", { name: new RegExp(`^${name}`) });

test.describe("status filters and rule groups", () => {
  test("status filter defaults to Proposed when proposed rules exist, and groups by object type", async ({ page, request }) => {
    await scenario(request, "default");
    await openDevCenter(page);
    await workReady(page);
    await tab(page, "Sources").click();

    await expect(page.getByRole("heading", { name: "Naming rules for Combined model" })).toBeVisible();

    // Filter toolbar shows Proposed selected by default.
    const proposedBtn = page.getByRole("button", { name: "Proposed (3)" });
    const confirmedBtn = page.getByRole("button", { name: "Confirmed (4)" });
    const rejectedBtn = page.getByRole("button", { name: "Rejected (1)" });
    const allBtn = page.getByRole("button", { name: "All (8)" });

    await expect(proposedBtn).toHaveAttribute("aria-pressed", "true");
    await expect(confirmedBtn).toHaveAttribute("aria-pressed", "false");
    await expect(rejectedBtn).toHaveAttribute("aria-pressed", "false");
    await expect(allBtn).toHaveAttribute("aria-pressed", "false");

    // Table is grouped by object type.
    const table = page.locator(".dc-rules-table");
    await expect(table.locator(".dc-rule-group-title", { hasText: "Measures" })).toBeVisible();
    await expect(table.locator(".dc-rule-group-title", { hasText: "Columns" })).toBeVisible();

    // In Proposed filter, only proposed rules are displayed.
    await expect(table.locator('tr[data-rule="nr-000000000001"]')).toBeVisible();
    await expect(table.locator('tr[data-rule="nr-000000000003"]')).toBeVisible();
    await expect(table.locator('tr[data-rule="nr-000000000005"]')).toBeVisible();
    await expect(table.locator('tr[data-rule="nr-000000000002"]')).toHaveCount(0);

    // Breaks warning icon appears on rules with breaks.
    await expect(table.locator('tr[data-rule="nr-000000000001"] .dc-breaks-warn')).toContainText("3");

    // Switch to Confirmed filter.
    await confirmedBtn.click();
    await expect(confirmedBtn).toHaveAttribute("aria-pressed", "true");
    await expect(table.locator('tr[data-rule="nr-000000000002"]')).toBeVisible();
    await expect(table.locator('tr[data-rule="nr-000000000004"]')).toBeVisible();
    await expect(table.locator('tr[data-rule="nr-000000000007"]')).toBeVisible();
    await expect(table.locator('tr[data-rule="nr-000000000008"]')).toBeVisible();
    await expect(table.locator('tr[data-rule="nr-000000000001"]')).toHaveCount(0);

    // Switch to Rejected filter.
    await rejectedBtn.click();
    await expect(rejectedBtn).toHaveAttribute("aria-pressed", "true");
    await expect(table.locator('tr[data-rule="nr-000000000006"]')).toBeVisible();
    await expect(table.locator('tr[data-rule="nr-000000000001"]')).toHaveCount(0);

    // Switch to All filter.
    await allBtn.click();
    await expect(allBtn).toHaveAttribute("aria-pressed", "true");
    await expect(table.locator("tbody tr[data-rule]")).toHaveCount(8);

    await checkPage(page);
  });

  test("empty filter state shows message and resets to all rules", async ({ page, request }) => {
    await scenario(request, "default");
    await openDevCenter(page);
    await workReady(page);
    await tab(page, "Sources").click();

    // Confirm the single rejected rule so rejected becomes 0.
    const rejectedBtn = page.getByRole("button", { name: "Rejected (1)" });
    await rejectedBtn.click();
    await page.getByRole("button", { name: "Confirm again: Key columns end with Key." }).click();
    await expect(page.locator(".ui-toast-region")).toContainText("Rule confirmed");

    // Rejected is now empty (0).
    await expect(page.getByText("No rejected rules.")).toBeVisible();
    const showAllBtn = page.getByRole("button", { name: "Show all rules" });
    await expect(showAllBtn).toBeVisible();

    await showAllBtn.click();
    await expect(page.getByRole("button", { name: "All (8)" })).toHaveAttribute("aria-pressed", "true");
    await checkPage(page);
  });
});

test.describe("actions by status and confirm selected", () => {
  test("row actions by status: confirm proposed, reject detected, confirm again rejected", async ({ page, request }) => {
    await scenario(request, "default");
    await openDevCenter(page);
    await workReady(page);
    await tab(page, "Sources").click();

    // 1. Confirm a proposed rule directly.
    const rule1Confirm = page.getByRole("button", { name: "Confirm: Measures with currency format end with Amt." });
    await rule1Confirm.click();
    await expect(page.locator(".ui-toast-region")).toContainText("Rule confirmed: Measures with currency format end with Amt.");
    await expect(page.getByRole("button", { name: "Proposed (2)" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Confirmed (5)" })).toBeVisible();

    // 2. Reject a detected confirmed rule from the more menu.
    await page.getByRole("button", { name: "Confirmed (5)" }).click();
    const rule2Row = page.locator('tr[data-rule="nr-000000000002"]');
    await rule2Row.getByRole("button", { name: "More actions: Measure names use Title Case." }).click();
    await page.getByRole("menuitem", { name: "Reject" }).click();
    await expect(page.locator(".ui-toast-region")).toContainText("Rule rejected: Measure names use Title Case.");
    await expect(page.getByRole("button", { name: "Confirmed (4)" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Rejected (2)" })).toBeVisible();

    // 3. Confirm again from rejected status.
    await page.getByRole("button", { name: "Rejected (2)" }).click();
    await page.getByRole("button", { name: "Confirm again: Measure names use Title Case." }).click();
    await expect(page.locator(".ui-toast-region")).toContainText("Rule confirmed: Measure names use Title Case.");
    await expect(page.getByRole("button", { name: "Confirmed (5)" })).toBeVisible();
  });

  test("confirm selected: sequential confirm and stop at failure", async ({ page, request }) => {
    await scenario(request, "default");
    await openDevCenter(page);
    await workReady(page);
    await tab(page, "Sources").click();

    // Select two proposed rules using checkboxes.
    const check1 = page.getByRole("checkbox", { name: "Select rule Measures with currency format end with Amt." });
    const check3 = page.getByRole("checkbox", { name: "Select rule Measures with percent format end with %." });

    await check1.click();
    await check3.click();

    const bulkBtn = page.getByRole("button", { name: "Confirm selected (2)" });
    await expect(bulkBtn).toBeVisible();

    // Inject a fault on naming_rule_confirm. The second call will fail.
    await fault(request, "naming_rule_confirm", "action_not_allowed", { message: "Rule conflict with model.", skip: 1 });

    await bulkBtn.click();

    // Expect the failure message matching copy rules.confirm_selected.stopped.
    await expect(page.locator(".ui-toast-region")).toContainText("1 of 2 rules confirmed. Measures with percent format end with %. was not confirmed: Rule conflict with model.");
    await checkPage(page);
  });
});

test.describe("rule editor in side pane", () => {
  test("add rule: side pane validation error under field and duplicate rule action", async ({ page, request }) => {
    await scenario(request, "default");
    await openDevCenter(page);
    await workReady(page);
    await tab(page, "Sources").click();

    await page.getByRole("button", { name: "Add rule" }).click();

    const pane = page.locator(".dc-rule-editor");
    await expect(pane).toBeVisible();
    await expect(pane.getByRole("heading", { name: "Add rule" })).toBeFocused();
    expect(await axeViolations(page, { include: ".dc-rule-editor" })).toEqual([]);

    // Select regex check kind.
    await page.getByRole("combobox", { name: "Check kind" }).click();
    await page.getByRole("option", { name: "Regular expression" }).click();

    // Test inline validation error under field (A16).
    const patternInput = page.getByLabel("Pattern");
    await patternInput.fill("[unclosed-regex");
    await page.getByRole("button", { name: "Save rule" }).click();

    const patternField = page.locator(".ui-field", { has: patternInput });
    await expect(patternField.locator(".ui-field-hint.is-error")).toBeVisible();
    await expect(patternField.locator(".ui-field-hint.is-error")).toContainText("This pattern is not a valid regular expression");
    await expect(patternInput).toHaveAttribute("aria-invalid", "true");

    // Test duplicate rule check: measure, scope all, letter_case title (matches nr-2).
    await page.getByRole("combobox", { name: "Check kind" }).click();
    await page.getByRole("option", { name: "Letter case" }).click();

    await page.getByRole("button", { name: "Save rule" }).click();

    // Duplicate rule error shows inline with Edit that rule action.
    const dupAlert = page.locator(".dc-duplicate-error");
    await expect(dupAlert).toBeVisible();
    await expect(dupAlert).toContainText("A rule with this scope and check kind exists: nr-000000000002. Edit that rule.");

    const editThatBtn = dupAlert.getByRole("button", { name: "Edit that rule" });
    await expect(editThatBtn).toBeVisible();
    await editThatBtn.click();

    // Side pane title switches to Edit rule for the duplicate rule.
    await expect(pane.getByRole("heading", { name: "Edit rule" })).toBeVisible();
    expect(await axeViolations(page, { include: ".dc-rule-editor" })).toEqual([]);

    await pane.getByRole("button", { name: "Close" }).click();
    await expect(pane).toHaveCount(0);

    await checkPage(page);
  });

  test("edit rule: edits and saves confirmed rule", async ({ page, request }) => {
    await scenario(request, "default");
    await openDevCenter(page);
    await workReady(page);
    await tab(page, "Sources").click();

    // Go to Confirmed filter.
    await page.getByRole("button", { name: "Confirmed (4)" }).click();

    // Click Edit on rule nr-2.
    const rule2Row = page.locator('tr[data-rule="nr-000000000002"]');
    await rule2Row.getByRole("button", { name: "Edit: Measure names use Title Case." }).click();

    const pane = page.locator(".dc-rule-editor");
    await expect(pane.getByRole("heading", { name: "Edit rule" })).toBeVisible();

    // Change check kind to suffix.
    await page.getByRole("combobox", { name: "Check kind" }).click();
    await page.getByRole("option", { name: "Suffix" }).click();
    await page.getByLabel("Value").fill("Total");

    await page.getByRole("button", { name: "Save rule" }).click();
    await expect(page.locator(".ui-toast-region")).toContainText("Rule saved.");
    await expect(pane).toHaveCount(0);
  });
});

test.describe("delete user rule", () => {
  test("destructive confirm dialog with initial focus on Cancel", async ({ page, request }) => {
    await scenario(request, "default");
    await openDevCenter(page);
    await workReady(page);
    await tab(page, "Sources").click();

    // Rule nr-4 is a user rule in Confirmed status.
    await page.getByRole("button", { name: "Confirmed (4)" }).click();
    const userRuleRow = page.locator('tr[data-rule="nr-000000000004"]');
    await expect(userRuleRow).toContainText("User");

    await userRuleRow.getByRole("button", { name: "More actions: Measure names match ^[A-Z][A-Za-z0-9 %]*$." }).click();
    await page.getByRole("menuitem", { name: "Delete" }).click();

    const dialog = page.getByRole("alertdialog", { name: "Delete this rule?" });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByText("PBIBrain stops checking names against this rule.")).toBeVisible();

    // Initial focus must be on Cancel.
    await expect(dialog.getByRole("button", { name: "Cancel" })).toBeFocused();
    expect(await axeViolations(page, { include: "[role=alertdialog]" })).toEqual([]);

    // Dismiss with Cancel.
    await dialog.getByRole("button", { name: "Cancel" }).click();
    await expect(dialog).toHaveCount(0);
    await expect(userRuleRow).toBeVisible();

    // Open again and confirm delete.
    await userRuleRow.getByRole("button", { name: "More actions: Measure names match ^[A-Z][A-Za-z0-9 %]*$." }).click();
    await page.getByRole("menuitem", { name: "Delete" }).click();
    await dialog.getByRole("button", { name: "Delete rule" }).click();

    await expect(page.locator(".ui-toast-region")).toContainText("Rule deleted.");
    await expect(userRuleRow).toHaveCount(0);
    await checkPage(page);
  });
});

test.describe("copy rules from dialog", () => {
  test("lists candidate models with counts, model with 0 rules is disabled", async ({ page, request }) => {
    await scenario(request, "default");
    await openDevCenter(page);
    await workReady(page);
    await tab(page, "Sources").click();

    await page.getByRole("button", { name: "Copy rules from" }).click();

    const dialog = page.getByRole("dialog", { name: "Copy rules from a different model" });
    await expect(dialog).toBeVisible();
    expect(await axeViolations(page, { include: "[role=dialog]" })).toEqual([]);

    // Check list of candidate models: Sales model (2 rules), Finance model (1 rule), Marketing model (0 rules).
    const salesCard = dialog.locator(".dc-radio-card", { hasText: "Sales model" });
    const financeCard = dialog.locator(".dc-radio-card", { hasText: "Finance model" });
    const marketingCard = dialog.locator(".dc-radio-card", { hasText: "Marketing model" });

    await expect(salesCard).toContainText("2 rules");
    await expect(financeCard).toContainText("1 rules");
    await expect(marketingCard).toContainText("0 rules");

    // Marketing model with 0 rules is disabled and displays explanation.
    await expect(marketingCard.locator('input[type="radio"]')).toBeDisabled();
    await expect(marketingCard).toContainText("This model has no naming rules.");

    // Select Sales model.
    await salesCard.locator('input[type="radio"]').click();
    const copyConfirmBtn = dialog.getByRole("button", { name: "Copy 2 rules" });
    await expect(copyConfirmBtn).toBeEnabled();

    await copyConfirmBtn.click();
    await expect(page.locator(".ui-toast-region")).toContainText("Copied 2 rules.");
    await expect(dialog).toHaveCount(0);

    // Filter toolbar count updates.
    await expect(page.getByRole("button", { name: "All (10)" })).toBeVisible();
  });
});

test.describe("empty, no target, detection, and locked states", () => {
  test("no target state shows empty state and Change target button", async ({ page, request }) => {
    await scenario(request, "default");
    await setRules(request, { target: null });
    await openDevCenter(page);
    await workReady(page);
    await tab(page, "Sources").click();

    await expect(page.getByRole("heading", { name: "No target model" })).toBeVisible();
    await expect(page.getByText("Set a target model to see its naming rules.")).toBeVisible();
    const rulesSection = page.locator(".dc-section", { hasText: "No target model" });
    await expect(rulesSection.getByRole("button", { name: "Change target" })).toBeVisible();
    await checkPage(page);
  });

  test("empty rules state shows No naming patterns found with Add rule and Copy rules from", async ({ page, request }) => {
    await scenario(request, "default");
    await setRules(request, { rules: [] });
    await openDevCenter(page);
    await workReady(page);
    await tab(page, "Sources").click();

    await expect(page.getByRole("heading", { name: "No naming patterns found" })).toBeVisible();
    await expect(page.getByText("Combined model has too few objects with the same pattern. Add a rule or copy rules from a different model.")).toBeVisible();
    await expect(page.getByRole("button", { name: "Add rule" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Copy rules from" })).toBeVisible();
    await checkPage(page);
  });

  test("detecting state displays spinner and reading copy while loading", async ({ page, request }) => {
    await scenario(request, "default");
    await request.post("/__test__/delay", { data: { path: "/api/devcenter/naming-rules", ms: 1200, once: true } });
    await openDevCenter(page);
    await workReady(page);
    await tab(page, "Sources").click();

    await expect(page.getByRole("heading", { name: "Finding naming patterns" })).toBeVisible();
    await expect(page.getByText("PBIBrain reads the names in Combined model.")).toBeVisible();

    // Data resolves after the delay.
    await expect(page.getByRole("button", { name: "Proposed (3)" })).toBeVisible();
  });

  test("locked state disables all change controls with aria-describedby", async ({ page, request }) => {
    await scenario(request, "locked");
    await openDevCenter(page);
    await workReady(page);
    await tab(page, "Sources").click();

    // Toolbar buttons are disabled with aria-describedby pointing to dc-locked-reason.
    const addRuleBtn = page.getByRole("button", { name: "Add rule" });
    const copyRulesBtn = page.getByRole("button", { name: "Copy rules from" });

    await expect(addRuleBtn).toBeDisabled();
    await expect(addRuleBtn).toHaveAttribute("aria-describedby", "dc-locked-reason");

    await expect(copyRulesBtn).toBeDisabled();
    await expect(copyRulesBtn).toHaveAttribute("aria-describedby", "dc-locked-reason");

    // Row actions are disabled.
    const rowConfirmBtn = page.getByRole("button", { name: "Confirm: Measures with currency format end with Amt." });
    await expect(rowConfirmBtn).toBeDisabled();
    await expect(rowConfirmBtn).toHaveAttribute("aria-describedby", "dc-locked-reason");

    await checkPage(page);
  });
});

for (const theme of ["dark", "light"]) {
  test(`theme ${theme}: naming rules section meets contrast and layout gates`, async ({ page, request, context }) => {
    await setTheme(context, theme);
    await scenario(request, "default");
    await openDevCenter(page);
    await workReady(page);
    await tab(page, "Sources").click();

    await expect(page.getByRole("heading", { name: "Naming rules for Combined model" })).toBeVisible();
    await checkPage(page);
  });
}
