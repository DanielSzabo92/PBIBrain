// Step U9: Agent tab, Log tab, proposal and question cards, and the grid badge (UI design 4.3, 4.4, 4.7, 5.4, A19).
// Layout: 1280 x 900. The agent data comes from POST /__test__/agent-review.
// All text follows ASD-STE100 rules. No emoji. No em dash or en dash.
import { test, expect } from "@playwright/test";
import { axeViolations, setTheme } from "./axe.js";

const FAKE = "http://127.0.0.1:8766";
test.use({ baseURL: FAKE, viewport: { width: 1280, height: 900 } });

async function agentReview(request) {
  const loaded = await request.post("/__test__/agent-review", { data: {} });
  expect(loaded.ok()).toBe(true);
}

async function fault(request, method, code, extra = {}) {
  const res = await request.post("/__test__/fault", { data: { method, code, ...extra } });
  expect(res.ok()).toBe(true);
}

async function openTab(page, name) {
  await page.goto("/");
  await page.getByRole("navigation", { name: "Main navigation" }).getByRole("button", { name: "Development Center" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Sales and finance merge" })).toBeVisible();
  await expect(page.locator(".dc-busy-line")).toHaveCount(0);
  await page.getByRole("tab", { name: new RegExp(`^${name}`) }).click();
}

const proposalRows = (page) => page.locator(".dc-agent-row");
const proposalRow = (page, id) => page.locator(`.dc-agent-row[data-proposal="${id}"]`);
const lastToast = (page) => page.locator(".ui-toast").last();

async function pick(page, label, option) {
  await page.getByRole("combobox", { name: label }).click();
  await page.getByRole("option", { name: option, exact: true }).click();
}

test.describe("U9 Agent tab", () => {
  test.beforeEach(async ({ request }) => {
    await agentReview(request);
  });

  test("the first open question leads, and Answer moves it to Answered", async ({ page }) => {
    await openTab(page, "Agent");
    const tab = page.locator('[data-slot="agent-tab"]');
    const firstSection = tab.locator(".dc-agent-section").first();
    await expect(firstSection.getByRole("heading", { level: 2 })).toHaveText("Questions (2)");
    await expect(firstSection.locator('[data-slot="question-card"]')).toHaveCount(1);
    const card = firstSection.locator('[data-slot="question-card"][data-question="q-1"]');
    await expect(card).toBeVisible();
    // The recommended option is preselected and has the "Recommended" word.
    await expect(card.getByRole("radio", { name: "Take from Finance model" })).toBeChecked();
    await expect(card.locator(".dc-question-rec")).toHaveText("Recommended");
    await expect(card).toContainText("Sets Merge Choice");

    await firstSection.getByRole("button", { name: "1 more open questions. Show them" }).click();
    await expect(firstSection.locator('[data-slot="question-card"]')).toHaveCount(2);

    await card.getByRole("radio", { name: "Keep target" }).click();
    await card.getByRole("button", { name: "Answer" }).click();
    await expect(lastToast(page)).toContainText("Answer saved.");
    await expect(page.locator('[data-slot="question-card"][data-question="q-1"]')).toHaveCount(0);
    await expect(tab.locator(".dc-agent-section").first().getByRole("heading", { level: 2 })).toHaveText("Questions (1)");

    const answered = tab.getByRole("button", { name: "Answered (2)" });
    await expect(answered).toHaveAttribute("aria-expanded", "false");
    await answered.click();
    await expect(tab.locator('#dc-agent-answered li[data-question="q-1"]')).toContainText("Answer: Keep target");
  });

  test("the proposals table has the status values, the filters, the sticky actions, Accept, and Reject", async ({ page }) => {
    await openTab(page, "Agent");
    // Newest first.
    await expect(proposalRows(page)).toHaveCount(4);
    await expect(proposalRows(page).first()).toHaveAttribute("data-proposal", "p-4");
    await expect(page.getByRole("heading", { level: 2, name: "Proposals (4)" })).toBeVisible();

    const statuses = { "p-1": "Ready to accept", "p-2": "Ready to accept", "p-3": "Conflicts with your choice", "p-4": "Confirm row first" };
    for (const [id, word] of Object.entries(statuses)) await expect(proposalRow(page, id).locator('[data-slot="status-badge"]')).toHaveText(word);
    // Only the ready rows have a checkbox.
    await expect(page.locator(".dc-agent-row [role=checkbox]")).toHaveCount(2);
    // The row action follows the status.
    await expect(proposalRow(page, "p-1").getByRole("button", { name: "Accept", exact: true })).toBeVisible();
    await expect(proposalRow(page, "p-3").getByRole("button", { name: "Replace with agent choice" })).toBeVisible();
    await expect(proposalRow(page, "p-4").getByRole("button", { name: "Open row" })).toBeVisible();
    for (const id of Object.keys(statuses)) await expect(proposalRow(page, id).getByRole("button", { name: "Reject" })).toBeVisible();
    // The confidence is a whole percent, and the reason expands.
    await expect(proposalRow(page, "p-1").locator(".dc-agent-col-conf")).toHaveText("94%");
    const reason = proposalRow(page, "p-2").locator(".dc-agent-reason");
    await expect(reason).toHaveAttribute("aria-expanded", "false");
    await reason.click();
    await expect(reason).toHaveAttribute("aria-expanded", "true");
    // The Actions column is sticky.
    const position = await proposalRow(page, "p-1").locator(".dc-agent-col-actions").evaluate((cell) => getComputedStyle(cell).position);
    expect(position).toBe("sticky");

    await pick(page, "Status", "Confirm row first");
    await expect(proposalRows(page)).toHaveCount(1);
    await pick(page, "Status", "All");
    await pick(page, "Kind", "Name");
    await expect(proposalRows(page)).toHaveCount(0);
    await pick(page, "Kind", "All");
    await page.getByLabel("Search target").fill("gross");
    await expect(proposalRows(page)).toHaveCount(1);
    await expect(proposalRows(page).first()).toHaveAttribute("data-proposal", "p-3");
    await page.getByLabel("Search target").fill("");

    await proposalRow(page, "p-1").getByRole("button", { name: "Accept", exact: true }).click();
    await expect(lastToast(page)).toContainText("Proposal accepted.");
    await expect(proposalRow(page, "p-1")).toHaveCount(0);
    await proposalRow(page, "p-3").getByRole("button", { name: "Replace with agent choice" }).click();
    await expect(proposalRow(page, "p-3")).toHaveCount(0);
    await proposalRow(page, "p-2").getByRole("button", { name: "Reject" }).click();
    await expect(lastToast(page)).toContainText("Proposal rejected.");
    await expect(proposalRow(page, "p-2")).toHaveCount(0);
    await expect(proposalRows(page)).toHaveCount(1);
  });

  test("Accept selected runs in sequence and shows the partial failure toast", async ({ page, request }) => {
    await openTab(page, "Agent");
    await page.getByRole("checkbox", { name: "Select all ready proposals" }).click();
    const acceptSelected = page.getByRole("button", { name: "Accept selected (2)" });
    await expect(acceptSelected).toBeEnabled();
    // The first call passes and the second call fails.
    await fault(request, "proposal_accept", "source_changed", { skip: 1 });
    await acceptSelected.click();
    await expect(lastToast(page)).toContainText("1 of 2 proposals accepted. 1 was not accepted. See the marked row.");
    await expect(proposalRow(page, "p-2")).toHaveCount(0);
    const failed = proposalRow(page, "p-1");
    await expect(failed).toHaveAttribute("data-failed", "true");
    await expect(failed.getByRole("alert")).toContainText("A source of this row changed after the agent made this proposal.");
    await expect(page.getByRole("button", { name: "Accept selected (1)" })).toBeVisible();
  });

  test("Accept all shows the plan now and after, the skipped list, and the focus on Cancel", async ({ page }) => {
    await openTab(page, "Agent");
    const trigger = page.getByRole("button", { name: "Accept all" });
    await trigger.click();
    const dialog = page.getByRole("alertdialog");
    await expect(dialog.getByRole("heading", { name: "Accept 2 agent proposals?" })).toBeVisible();
    await expect(dialog.getByRole("button", { name: "Cancel" })).toBeFocused();
    await expect(dialog.locator('[data-plan="now"]')).toHaveText("Plan not valid: 1 blocking");
    await expect(dialog.locator('[data-plan="after"]')).toHaveText("Valid with 1 warning");
    await expect(dialog.locator('[data-plan="change"]')).toHaveText("Change: 1 fewer blocking items, 0 more warnings");
    await expect(dialog.getByRole("list", { name: "Proposals to accept" })).toContainText("Merge Choice: 2");
    await expect(dialog.getByRole("heading", { name: "Skipped (2)" })).toBeVisible();
    await expect(dialog.locator(".dc-accept-skipped li")).toHaveText([
      "Gross Margin: you already set a Merge Choice. Decide in the row detail.",
      "Customer: a source changed. Confirm the row first.",
    ]);
    expect(await axeViolations(page, { include: '[role="alertdialog"]' })).toEqual([]);

    await dialog.getByRole("button", { name: "Accept 2 proposals" }).click();
    await expect(dialog).toHaveCount(0);
    await expect(lastToast(page)).toContainText("2 proposals accepted. 2 skipped.");
    await expect(proposalRows(page)).toHaveCount(2);
    await expect(page.getByRole("button", { name: "Accept all" })).toBeDisabled();
  });

  test("the error copy of user_choice_exists and source_changed shows at the row", async ({ page, request }) => {
    await openTab(page, "Agent");
    await fault(request, "proposal_accept", "user_choice_exists");
    await proposalRow(page, "p-1").getByRole("button", { name: "Accept", exact: true }).click();
    await expect(proposalRow(page, "p-1").getByRole("alert")).toHaveText(
      "You already set a Merge Choice on this row. Change the choice in the row detail, or reject the proposal.",
    );
    await fault(request, "proposal_accept", "source_changed");
    await proposalRow(page, "p-2").getByRole("button", { name: "Accept", exact: true }).click();
    await expect(proposalRow(page, "p-2").getByRole("alert")).toHaveText(
      "A source of this row changed after the agent made this proposal. Confirm the row first, then accept or reject the proposal.",
    );
    // A source_changed error gives "Open row", and the tab stays the Agent tab.
    await expect(proposalRow(page, "p-2").getByRole("button", { name: "Open row" })).toBeVisible();
    await expect(page.getByRole("tab", { name: /^Agent/ })).toHaveAttribute("aria-selected", "true");
  });

  test("A19: a new agent proposal shows the notice after the poll, and the focus and the list stay the same", async ({ page, request }) => {
    await openTab(page, "Agent");
    const reject = proposalRow(page, "p-1").getByRole("button", { name: "Reject" });
    await reject.focus();
    const added = await request.post("/__test__/agent-proposal", {
      data: { target_id: "row-region", target_name: "Region", summary: "Keep target", payload: { choice: "keep" } },
    });
    expect(added.ok()).toBe(true);
    const notice = page.getByRole("status").filter({ hasText: "1 new proposal. Show it" });
    await expect(notice).toBeVisible({ timeout: 12000 });
    await expect(reject).toBeFocused();
    await expect(proposalRows(page)).toHaveCount(4);
    await expect(page.getByRole("tab", { name: /^Agent/ })).toContainText("7");
    await notice.getByRole("button", { name: "1 new proposal. Show it" }).click();
    await expect(proposalRows(page)).toHaveCount(5);
    await expect(notice).toHaveCount(0);
  });

  test("A1: the Agent tab has no axe violations in the light and the dark theme, and no overflow", async ({ page, context }) => {
    for (const theme of ["light", "dark"]) {
      await setTheme(context, theme);
      await openTab(page, "Agent");
      await expect(proposalRows(page)).toHaveCount(4);
      expect(await axeViolations(page, { include: '[data-slot="agent-tab"]' }), theme).toEqual([]);
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(overflow).toBeLessThanOrEqual(0);
    }
  });
});

test.describe("U9 Grid badge and row detail cards", () => {
  test.beforeEach(async ({ request }) => {
    await agentReview(request);
  });

  test("the badge priority is Confirm row first, Question, Proposed, and the tooltip has the proposed choice", async ({ page }) => {
    await openTab(page, "Compare");
    const badge = (name) => page.getByRole("row").filter({ hasText: name }).locator("[data-badge]");
    await expect(badge("Customer")).toHaveText("Confirm row first");
    await expect(badge("Budget")).toHaveText("Question");
    await expect(badge("Budget")).toHaveAttribute("title", "Must Budget stay in the target model?");
    await expect(badge("Gross Margin")).toHaveText("Proposed");
    await expect(badge("Gross Margin")).toHaveAttribute("title", "Agent proposes: Keep target");
    await expect(badge("Net Sales")).toHaveAttribute("title", "Agent proposes: Take from Finance model");
  });

  test("the row detail card on a marked row disables Accept and offers Confirm row", async ({ page }) => {
    await openTab(page, "Compare");
    await page.locator(".dc-cell", { hasText: "Customer" }).first().click();
    const card = page.locator(".dc-row-pane [data-slot=proposal-card]");
    await expect(card).toBeVisible();
    await expect(card).toContainText("Test agent, ");
    await expect(card).toContainText("Confidence: 92%");
    await expect(card.getByRole("button", { name: /^(Accept|Replace with agent choice)$/ })).toBeDisabled();
    await card.getByRole("button", { name: "Confirm row" }).click();
    await expect(card.getByRole("button", { name: /^(Accept|Replace with agent choice)$/ })).toBeEnabled();
  });

  test("an open card tells that the agent replaced its proposal", async ({ page, request }) => {
    await openTab(page, "Compare");
    await page.locator(".dc-cell", { hasText: "Net Sales" }).first().click();
    const card = page.locator(".dc-row-pane [data-slot=proposal-card]");
    await expect(card).toHaveAttribute("data-proposal", "p-1");
    const added = await request.post("/__test__/agent-proposal", {
      data: { target_id: "row-net-sales", target_name: "Net Sales", summary: "Keep target", payload: { choice: "keep" } },
    });
    expect(added.ok()).toBe(true);
    await expect(card).toContainText("The agent replaced this proposal.", { timeout: 12000 });
    await expect(card.locator(".dc-proposal-summary")).toHaveText("Keep target");
  });
});

test.describe("U9 Log tab", () => {
  test.beforeEach(async ({ request }) => {
    await agentReview(request);
  });

  const logRows = (page) => page.locator(".dc-log-row");

  test("Show more loads the next page, and an empty value shows None", async ({ page }) => {
    await openTab(page, "Log");
    await expect(logRows(page)).toHaveCount(50);
    await expect(page.locator(".dc-log-more")).toContainText("Showing 50 entries.");
    // The open of the session runs sources_check, so the newest entry is "Checked sources".
    const first = logRows(page).first();
    await expect(first).toContainText("You");
    await expect(first).toContainText("Checked sources");
    await expect(first.locator('[data-col="before"]')).toHaveText("None");
    await expect(first.locator('[data-col="after"]')).toHaveText("None");
    await expect(logRows(page).nth(1).locator('[data-col="after"]')).toHaveText('{"choice":"take_from","source":"src-2"}');
    await page.getByRole("button", { name: "Show more" }).click();
    await expect(logRows(page)).toHaveCount(63);
    await expect(page.getByRole("button", { name: "Show more" })).toHaveCount(0);
  });

  test("the Author, Action, and target filters and the proposal chip filter the log", async ({ page }) => {
    await openTab(page, "Log");
    await pick(page, "Author", "Agent");
    await expect(logRows(page)).toHaveCount(1);
    await expect(logRows(page).first()).toContainText("Agent: Test agent");
    await expect(logRows(page).first()).toContainText("Proposed Merge Choice");
    await pick(page, "Author", "All");
    await expect(logRows(page)).toHaveCount(50);

    await page.getByRole("button", { name: "p-1" }).click();
    await expect(page.locator('[data-slot="filter-chip"]')).toHaveText("Proposal p-1");
    await expect(logRows(page)).toHaveCount(1);
    await page.getByRole("button", { name: "Remove filter Proposal p-1" }).click();
    await expect(logRows(page)).toHaveCount(50);

    await page.getByLabel("Search target").fill("row-gross-margin");
    await expect(logRows(page)).toHaveCount(1);
    await pick(page, "Action", "Accepted proposal");
    await expect(page.getByRole("heading", { name: "No changes yet" })).toBeVisible();
    await page.getByRole("button", { name: "Clear filters" }).click();
    await expect(logRows(page)).toHaveCount(50);
  });

  test("A1: the Log tab has no axe violations in the light and the dark theme", async ({ page, context }) => {
    for (const theme of ["light", "dark"]) {
      await setTheme(context, theme);
      await openTab(page, "Log");
      await expect(logRows(page)).toHaveCount(50);
      expect(await axeViolations(page, { include: '[data-slot="log-tab"]' }), theme).toEqual([]);
    }
  });
});
