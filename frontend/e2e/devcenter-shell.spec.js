import { test, expect } from "@playwright/test";
import { axeViolations, setTheme } from "./axe.js";

// Step U3: shell, session list, create flow, work area frame, Sources and Target (UI design 13, U3).
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

// Open the app and the Development Center sidebar item.
async function openDevCenter(page) {
  await page.goto("/");
  await page.getByRole("navigation", { name: "Main navigation" }).getByRole("button", { name: "Development Center" }).click();
}

async function noOverflow(page) {
  const overflow = await page.evaluate(() => document.scrollingElement.scrollWidth - document.scrollingElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
}

async function checkPage(page) {
  expect(await axeViolations(page)).toEqual([]);
  await noOverflow(page);
}

// The work area is ready when the automatic sources_check on open ended.
async function workReady(page, name = "Sales and finance merge") {
  await expect(page.getByRole("heading", { level: 1, name })).toBeVisible();
  await expect(page.locator(".dc-busy-line")).toHaveCount(0);
}

const tab = (page, name) => page.getByRole("tablist", { name: "Work area tabs" }).getByRole("tab", { name: new RegExp(`^${name}`) });

test.describe("screens and banners of sections 4.1 and 4.2", () => {
  test("no-project: GET sessions refuses with no_project and the list shows the empty state", async ({ page, request }) => {
    // The app shows its onboarding page while the host has no project, so switch the scenario after the app loads.
    await scenario(request, "default");
    await page.goto("/");
    await expect(page.getByRole("navigation", { name: "Main navigation" })).toBeVisible();
    await scenario(request, "no-project");
    await page.getByRole("navigation", { name: "Main navigation" }).getByRole("button", { name: "Development Center" }).click();
    await expect(page.getByRole("heading", { name: "Open a project to start a merge session" })).toBeVisible();
    await expect(page.getByText("Merge sessions are saved in the project folder. Open a PBIP project first.")).toBeVisible();
    await expect(page.getByRole("button", { name: "Open project" })).toBeVisible();
    await checkPage(page);
  });

  test("no-sessions: the empty state and its action", async ({ page, request }) => {
    await scenario(request, "no-sessions");
    await openDevCenter(page);
    await expect(page.getByRole("heading", { name: "No merge sessions yet" })).toBeVisible();
    await expect(page.getByRole("button", { name: "New merge session" })).toBeVisible();
    await checkPage(page);
  });

  for (const theme of ["dark", "light"]) {
    test(`default in the ${theme} theme: the work area frame and the session list`, async ({ page, request, context }) => {
      await setTheme(context, theme);
      await scenario(request, "default");
      await openDevCenter(page);
      await workReady(page);
      await expect(page.getByText("Target model: Combined model. Target report: Combined report.")).toBeVisible();
      await expect(page.getByRole("button", { name: /^Valid with 1 warning\. Open the Plan tab$/ })).toBeVisible();
      await expect(tab(page, "Compare")).toHaveAttribute("aria-selected", "true");
      await expect(tab(page, "Agent")).toContainText("1");
      for (const name of ["Compare", "Impact", "Plan", "Agent", "Sources", "Log"]) await expect(tab(page, name)).toBeVisible();
      await expect(page.getByRole("navigation", { name: "Breadcrumb" })).toContainText("Development Center");
      await checkPage(page);

      // The first part of the breadcrumb shows the list. The session stays open.
      await page.getByRole("navigation", { name: "Breadcrumb" }).getByRole("button", { name: "Development Center" }).click();
      await expect(page.getByRole("heading", { level: 1, name: "Merge sessions" })).toBeVisible();
      const table = page.getByRole("table", { name: /Merge sessions of this project/ });
      for (const header of ["Name", "Target", "Sources", "Plan", "Last change", "Status"]) await expect(table.getByRole("columnheader", { name: header })).toBeVisible();
      await expect(table.getByRole("row")).toHaveCount(3);
      await expect(table.getByText("Open now")).toBeVisible();
      await checkPage(page);

      // A click on the open session shows its work area again.
      await table.getByRole("button", { name: "Sales and finance merge" }).click();
      await workReady(page);
    });
  }

  test("newer-schema and damaged: rows with no link and a reason line", async ({ page, request }) => {
    for (const [name, label, reason] of [
      ["newer-schema", "Needs a newer PBIBrain", "This session was saved by a newer PBIBrain version. Update PBIBrain to open it."],
      ["damaged", "Cannot read", "The session file is not valid JSON or has merge conflict marks. Fix the file, then try again."],
    ]) {
      await scenario(request, name);
      await openDevCenter(page);
      const table = page.getByRole("table", { name: /Merge sessions of this project/ });
      await expect(table.getByText(label, { exact: true })).toBeVisible();
      await expect(table.getByText(reason)).toBeVisible();
      await expect(table.getByRole("button")).toHaveCount(1);
      await expect(table.getByRole("button", { name: "Budget merge" })).toBeVisible();
      await checkPage(page);
    }
  });

  test("locked: the banner, and each change control is disabled", async ({ page, request }) => {
    await scenario(request, "locked");
    await openDevCenter(page);
    await expect(page.getByRole("heading", { level: 1, name: "Sales and finance merge" })).toBeVisible();
    const banner = page.locator('[data-banner="locked"]');
    await expect(banner).toContainText("Another PBIBrain window has this session open. You can read it, but you cannot change it.");
    await expect(banner.getByRole("button", { name: "Try again" })).toBeEnabled();
    await expect(page.getByRole("button", { name: "Check sources" })).toBeDisabled();
    await expect(page.getByRole("button", { name: "Check sources" })).toHaveAttribute("aria-describedby", "dc-locked-reason");
    await tab(page, "Sources").click();
    for (const name of ["Remove Sales model", "Remove Finance model", "Remove Marketing model"]) await expect(page.getByRole("button", { name })).toBeDisabled();
    await expect(page.getByRole("button", { name: "Change target" })).toBeDisabled();
    await checkPage(page);

    // "Try again" opens the session again. Another window still has it, so it stays read-only.
    await banner.getByRole("button", { name: "Try again" }).click();
    await expect(page.locator('[data-banner="locked"]')).toBeVisible();
    await expect(page.getByRole("heading", { level: 1, name: "Sales and finance merge" })).toBeVisible();
  });

  test("sources-changed: the warn banner and Show these rows", async ({ page, request }) => {
    await scenario(request, "sources-changed");
    await openDevCenter(page);
    await workReady(page);
    const banner = page.locator('[data-banner="changed"]');
    await expect(banner).toContainText("1 source changed since the last check. You must confirm 3 rows.");
    await checkPage(page);
    await tab(page, "Sources").click();
    await banner.getByRole("button", { name: "Show these rows" }).click();
    await expect(tab(page, "Compare")).toHaveAttribute("aria-selected", "true");
    await expect(page.getByText("Filter: rows with marks.")).toBeVisible();
  });

  test("source-missing: the bad banner, Open Sources, and Find source", async ({ page, request }) => {
    await scenario(request, "source-missing");
    await openDevCenter(page);
    await workReady(page);
    const banner = page.locator('[data-banner="missing"]');
    await expect(banner).toHaveAttribute("role", "alert");
    await expect(banner).toContainText("1 source was not found: Sales model. Find it again or remove it.");
    await checkPage(page);
    await banner.getByRole("button", { name: "Open Sources" }).click();
    await expect(tab(page, "Sources")).toHaveAttribute("aria-selected", "true");
    // The banner is hidden on the Sources tab.
    await expect(page.locator('[data-banner="missing"]')).toHaveCount(0);
    const row = page.locator('[data-source="src-1"]');
    await expect(row).toContainText("Not found");
    await row.getByRole("button", { name: "Find Sales model" }).click();
    await expect(page.locator(".ui-toast-region")).toContainText("Sales model found.");
    await expect(row).toContainText("Found");
    await checkPage(page);
  });
});

test.describe("create flow", () => {
  async function addTwoSources(page) {
    await page.getByRole("button", { name: "New merge session" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "New merge session" })).toBeVisible();
    for (let index = 0; index < 2; index += 1) {
      await page.getByRole("button", { name: "Add source" }).click();
      await page.getByRole("menuitem", { name: "PBIP project" }).click();
    }
    const list = page.getByRole("list", { name: "Sources of the new session" });
    await expect(list.getByRole("listitem")).toHaveCount(2);
  }

  test("success opens Compare", async ({ page, request }) => {
    await scenario(request, "no-sessions");
    await openDevCenter(page);
    await page.getByRole("button", { name: "New merge session" }).click();
    // Next needs at least one model source.
    await page.getByRole("button", { name: "Next" }).click();
    await expect(page.getByRole("alert")).toHaveText("Add at least 1 model source to go to the next step.");
    await page.getByRole("button", { name: "Add source" }).click();
    await expect(page.getByRole("menu")).toBeVisible();
    expect(await axeViolations(page, { include: "[role=menu]" })).toEqual([]);
    await page.getByRole("menuitem", { name: "PBIP project" }).click();
    await page.getByRole("button", { name: "Add source" }).click();
    await page.getByRole("menuitem", { name: "PBIP project" }).click();
    await checkPage(page);
    await page.getByRole("button", { name: "Next" }).click();

    await expect(page.getByRole("heading", { level: 2, name: "Target" })).toBeVisible();
    await page.getByRole("radio", { name: "Copy of Sales" }).click();
    await expect(page.getByText("New folder: merge-lab")).toBeVisible();
    await expect(page.getByRole("radio", { name: "New empty report" })).toBeChecked();
    await checkPage(page);
    await page.getByRole("button", { name: "Next" }).click();

    await expect(page.getByRole("textbox", { name: "Session name" })).toHaveValue("Sales merge");
    await checkPage(page);
    await page.getByRole("button", { name: "Create session" }).click();
    await workReady(page, "Sales merge");
    await expect(tab(page, "Compare")).toHaveAttribute("aria-selected", "true");
    await tab(page, "Sources").click();
    await expect(page.locator('[data-source="src-1"]')).toContainText("Sales model");
    await expect(page.locator('[data-source="src-3"]')).toContainText("Target");
  });

  test("a fault on source_add shows the partial failure and Open session", async ({ page, request }) => {
    await scenario(request, "no-sessions");
    await openDevCenter(page);
    await addTwoSources(page);
    await page.getByRole("button", { name: "Next" }).click();
    await page.getByRole("radio", { name: "Finance", exact: true }).click();
    await page.getByRole("button", { name: "Next" }).click();
    await fault(request, "source_add", "action_not_allowed", { message: "The folder has no model." });
    await page.getByRole("button", { name: "Create session" }).click();
    const progress = page.getByRole("list", { name: "Create progress" });
    await expect(progress).toContainText("Sales not added:");
    await expect(progress).toContainText("Finance added");
    await expect(page.getByText("The session exists, but 1 source was not added. Open the session to add it again.")).toBeVisible();
    await checkPage(page);
    await page.getByRole("button", { name: "Open session" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Finance merge" })).toBeVisible();
    await expect(tab(page, "Sources")).toHaveAttribute("aria-selected", "true");
  });

  test("Cancel sends no JS API call", async ({ page, request }) => {
    await scenario(request, "no-sessions");
    await openDevCenter(page);
    await expect(page.getByRole("heading", { name: "No merge sessions yet" })).toBeVisible();
    const calls = [];
    page.on("request", (item) => { if (item.url().includes("/__test__/jsapi/")) calls.push(item.url()); });
    await addTwoSources(page);
    await page.getByRole("button", { name: "Next" }).click();
    await page.getByRole("radio", { name: "Sales", exact: true }).click();
    await page.getByRole("button", { name: "Next" }).click();
    await page.getByRole("button", { name: "Cancel" }).click();
    await expect(page.getByRole("heading", { name: "No merge sessions yet" })).toBeVisible();
    expect(calls).toEqual([]);
  });
});

test.describe("Sources tab and data refresh", () => {
  test("Remove source: destructive confirm with no count, then the reply count in the toast", async ({ page, request }) => {
    await scenario(request, "default");
    await openDevCenter(page);
    await workReady(page);
    await tab(page, "Sources").click();
    const trigger = page.getByRole("button", { name: "Remove Finance model" });
    await trigger.click();
    const dialog = page.getByRole("alertdialog", { name: "Remove Finance model from this session?" });
    await expect(dialog).toBeVisible();
    await expect(dialog).toContainText("Merge Choices that take from Finance model stay, but the plan is not valid until you change them.");
    await expect(dialog.getByRole("button", { name: "Cancel" })).toBeFocused();
    expect(await axeViolations(page, { include: "[role=alertdialog]" })).toEqual([]);
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
    await expect(trigger).toBeFocused();
    await trigger.click();
    await dialog.getByRole("button", { name: "Remove source" }).click();
    await expect(page.locator(".ui-toast-region")).toContainText("Finance model removed. 1 Merge Choice needs a new source.");
    await expect(page.locator('[data-source="src-2"]')).toHaveCount(0);
    await checkPage(page);
  });

  test("Change target sets the target model", async ({ page, request }) => {
    await scenario(request, "default");
    await openDevCenter(page);
    await workReady(page);
    await tab(page, "Sources").click();
    await page.getByRole("button", { name: "Change target" }).click();
    const dialog = page.getByRole("dialog", { name: "Change target" });
    await expect(dialog).toBeVisible();
    expect(await axeViolations(page, { include: "[role=dialog]" })).toEqual([]);
    await dialog.getByRole("radio", { name: "Sales model", exact: true }).click();
    await dialog.getByRole("button", { name: "Set target" }).click();
    await expect(dialog).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Change target" })).toBeFocused();
    await expect(page.getByText("Target model: Sales model. Target report: Combined report.")).toBeVisible();
  });

  test("stale_revision gives shared.stale and the refreshed view", async ({ page, request }) => {
    await scenario(request, "default");
    await openDevCenter(page);
    await workReady(page);
    await tab(page, "Sources").click();
    // Another window changes the session; the next call of this window is stale.
    await request.post("/__test__/agent-proposal", { data: { target_id: "row-date", target_name: "Date" } });
    await fault(request, "source_remove", "stale_revision");
    await page.getByRole("button", { name: "Remove Finance model" }).click();
    await page.getByRole("alertdialog").getByRole("button", { name: "Remove source" }).click();
    await expect(page.locator(".ui-toast-region")).toContainText("This session changed in another place. The view shows the latest state. Do the action again.");
    await expect(tab(page, "Agent")).toContainText("2");
    await expect(page.locator('[data-source="src-2"]')).toHaveCount(1);
    await expect(page.locator(".ui-toast-region")).toHaveCount(1);
  });

  test("a slow long call disables the change controls and shows the reason", async ({ page, request }) => {
    await scenario(request, "default");
    await openDevCenter(page);
    await workReady(page);
    await tab(page, "Sources").click();
    await request.post("/__test__/delay", { data: { method: "sources_check", ms: 1500, once: true } });
    await page.getByRole("button", { name: "Check sources" }).click();
    await expect(page.locator(".dc-busy-line")).toHaveText("Checking sources. Changes wait until this ends.");
    await expect(page.getByRole("button", { name: "Remove Finance model" })).toBeDisabled();
    await expect(page.getByRole("button", { name: "Change target" })).toBeDisabled();
    await expect(page.locator(".ui-toast-region")).toContainText("All sources are the same as at the last check.");
    await expect(page.getByRole("button", { name: "Remove Finance model" })).toBeEnabled();
  });

  test("a new revision from the poll updates the tab counts within 6 s", async ({ page, request }) => {
    await scenario(request, "default");
    await page.clock.install({ time: new Date("2026-01-01T00:00:00Z") });
    await openDevCenter(page);
    await workReady(page);
    // pauseAt after the load, so that only runFor moves time (U1 learning).
    await page.clock.pauseAt(new Date("2026-01-01T00:10:00Z"));
    await expect(tab(page, "Agent")).toContainText("1");
    await request.post("/__test__/agent-proposal", { data: { target_id: "row-date", target_name: "Date" } });
    await page.clock.runFor(6000);
    await expect(tab(page, "Agent")).toContainText("2");
  });
});

test.describe("keyboard, focus, live region, and motion", () => {
  test("the Settings switch turns the / key off and on (A24)", async ({ page, request }) => {
    await scenario(request, "default");
    await page.goto("/");
    const nav = page.getByRole("navigation", { name: "Main navigation" });
    await nav.getByRole("button", { name: "Settings" }).click();
    const control = page.getByRole("switch", { name: "Use the / key to go to search" });
    await expect(control).toBeChecked();
    await control.click();
    await expect(control).not.toBeChecked();
    await nav.getByRole("button", { name: "Development Center" }).click();
    await workReady(page);
    await page.locator("body").click({ position: { x: 5, y: 5 } });
    await page.keyboard.press("/");
    await expect(page.getByRole("heading", { level: 1, name: "Sales and finance merge" })).toBeVisible();

    await nav.getByRole("button", { name: "Settings" }).click();
    await control.click();
    await expect(control).toBeChecked();
    await nav.getByRole("button", { name: "Development Center" }).click();
    await workReady(page);
    await page.locator("body").click({ position: { x: 5, y: 5 } });
    await page.keyboard.press("/");
    await expect(page.locator(".search-field input")).toBeFocused();
  });

  test("focus order is header, banners, then tabs (A8), with one polite live region (A11)", async ({ page, request }) => {
    await scenario(request, "sources-changed");
    await openDevCenter(page);
    await workReady(page);
    await page.getByRole("button", { name: /Open the Plan tab$/ }).focus();
    const order = [];
    for (let index = 0; index < 5; index += 1) {
      order.push(await page.evaluate(() => document.activeElement?.getAttribute("aria-label") || document.activeElement?.textContent?.trim()));
      await page.keyboard.press("Tab");
    }
    expect(order[0]).toMatch(/Open the Plan tab$/);
    expect(order.slice(1)).toEqual(["Check sources", "More actions", "Show these rows", "Compare"]);
    await expect(page.locator('[aria-live="polite"].ui-toast-region')).toHaveCount(1);
  });

  test("reduced motion stops the spinner of a long call and keeps its status text (A15)", async ({ browser, request }) => {
    const context = await browser.newContext({ baseURL: FAKE, viewport: { width: 1280, height: 900 }, reducedMotion: "reduce" });
    const page = await context.newPage();
    await scenario(request, "default");
    await openDevCenter(page);
    await workReady(page);
    await request.post("/__test__/delay", { data: { method: "sources_check", ms: 1500, once: true } });
    await page.getByRole("button", { name: "Check sources" }).click();
    const line = page.locator(".dc-busy-line");
    await expect(line).toHaveText("Checking sources. Changes wait until this ends.");
    const names = await page.locator(".dc-root .spin").evaluateAll((items) => items.map((item) => getComputedStyle(item).animationName));
    expect(names.length).toBeGreaterThan(0);
    expect(new Set(names)).toEqual(new Set(["none"]));
    await context.close();
  });
});
