// Step U10: Apply, Undo, format only, and change report (UI design 5.5, 5.6, 8.4).
// Layout: 1280 x 900. All text follows ASD-STE100 rules.
import { test, expect } from "@playwright/test";
import { axeViolations } from "./axe.js";

const FAKE = "http://127.0.0.1:8766";
test.use({ baseURL: FAKE, viewport: { width: 1280, height: 900 } });

async function post(request, path, data) {
  const res = await request.post(path, { data });
  expect(res.ok()).toBe(true);
}

const scenario = (request, name) => post(request, "/__test__/scenario", { name });
const setApply = (request, data) => post(request, "/__test__/apply", data);
const fault = (request, data) => post(request, "/__test__/fault", data);
const delay = (request, data) => post(request, "/__test__/delay", data);

async function openPlan(page) {
  await page.goto("/");
  await page.getByRole("navigation", { name: "Main navigation" }).getByRole("button", { name: "Development Center" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Sales and finance merge" })).toBeVisible();
  await expect(page.locator(".dc-busy-line")).toHaveCount(0);
  await page.getByRole("tab", { name: /^Plan/ }).click();
  await expect(page.locator(".dc-plan-strip")).toBeVisible();
}

const strip = (page) => page.locator(".dc-plan-strip");
const dialog = (page) => page.getByRole("alertdialog");

async function openApplyDialog(page) {
  await strip(page).getByRole("button", { name: "Apply plan" }).click();
  await expect(dialog(page)).toBeVisible();
  await expect(dialog(page)).toHaveAttribute("data-phase", "confirm");
}

async function applyAndWait(page) {
  await dialog(page).locator('[data-confirm="apply"]').click();
  await expect(dialog(page)).toHaveAttribute("data-phase", "result");
}

test.describe("Apply preview and confirm dialog", () => {
  test("preview blocks go to the block list and the dialog does not open", async ({ page, request }) => {
    await scenario(request, "default");
    await setApply(request, { "apply-preview": { desktop_state: "open_unsaved" } });
    await openPlan(page);
    await expect(page.locator('[data-block-kind="desktop"]')).toHaveCount(0);
    await strip(page).getByRole("button", { name: "Apply plan" }).click();
    await expect(page.locator('[data-block-kind="desktop"]')).toBeVisible();
    await expect(page.locator("#dc-plan-blocks-title")).toBeFocused();
    await expect(dialog(page)).toHaveCount(0);
  });

  test("the approval checkbox shows only with approval items, has the focus, and gates the confirm", async ({ page, request }) => {
    await scenario(request, "default");
    await openPlan(page);
    await openApplyDialog(page);
    const box = dialog(page).getByRole("checkbox", { name: /I approve them/ });
    await expect(dialog(page).getByRole("heading", { name: "Apply the plan to Combined model?" })).toBeVisible();
    await expect(dialog(page).locator('[data-severity="not_checked"]').first()).toContainText("Budget");
    await expect(box).toBeFocused();
    const confirm = dialog(page).locator('[data-confirm="apply"]');
    await expect(confirm).toBeDisabled();
    await expect(confirm).toHaveAttribute("data-variant", "default");
    await box.click();
    await expect(confirm).toBeEnabled();
    expect(await axeViolations(page)).toEqual([]);
  });

  test("with no approval items there is no checkbox, Cancel has the focus, and a delete makes the confirm destructive", async ({ page, request }) => {
    await scenario(request, "apply-ready");
    await openPlan(page);
    await expect(strip(page).getByRole("button", { name: "Apply plan" })).toHaveAttribute("data-variant", "destructive");
    await openApplyDialog(page);
    await expect(dialog(page).getByRole("checkbox")).toHaveCount(0);
    await expect(dialog(page).getByRole("button", { name: "Cancel" })).toBeFocused();
    await expect(dialog(page).locator('[data-apply="deletes"]')).toHaveText("Deletes 1 objects: Region.");
    const confirm = dialog(page).locator('[data-confirm="apply"]');
    await expect(confirm).toBeEnabled();
    await expect(confirm).toHaveAttribute("data-variant", "destructive");
  });

  test("the Desktop line shows in the dialog, and the banner shows after the apply", async ({ page, request }) => {
    await scenario(request, "apply-ready");
    await setApply(request, { "apply-preview": { desktop_state: "open_saved" }, replies: { apply: { desktop_state: "open_saved", notices: ["apply_external_changes"] } } });
    await openPlan(page);
    await openApplyDialog(page);
    await expect(dialog(page).locator('[data-desktop="before"]')).toContainText('After the apply, select "Apply external changes"');
    await applyAndWait(page);
    await expect(dialog(page).locator('[data-desktop="after"]')).toBeVisible();
    await dialog(page).getByRole("button", { name: "Close" }).click();
    const banner = page.locator('[data-banner="desktop"]');
    await expect(banner).toContainText('select "Apply external changes" to load the new files');
    await banner.getByRole("button", { name: "Close" }).click();
    await expect(banner).toHaveCount(0);
  });
});

test.describe("Apply progress and result", () => {
  test("progress maps step_index to the list, and Escape does nothing while it runs", async ({ page, request }) => {
    await scenario(request, "apply-ready");
    await setApply(request, { "apply-progress": { apply_id: "apl-00000000000000a1", state: "running", step: "rescan", step_index: 10, step_count: 12 } });
    await delay(request, { method: "apply", ms: 2500, once: true });
    await openPlan(page);
    await openApplyDialog(page);
    await dialog(page).locator('[data-confirm="apply"]').click();
    await expect(dialog(page)).toHaveAttribute("data-phase", "running");
    await expect(dialog(page).locator('[data-step="rescan"]')).toHaveAttribute("data-state", "running");
    await expect(dialog(page).locator('[data-step="promotion"]')).toHaveAttribute("data-state", "done");
    await expect(dialog(page).locator('[data-step="fingerprints"]')).toHaveAttribute("data-state", "waiting");
    await expect(dialog(page).locator(".dc-apply-progress-line")).toContainText(/Step 10 of 11\. \d+ s elapsed\./);
    await expect(dialog(page).getByRole("button", { name: "Close" })).toHaveCount(0);
    await page.keyboard.press("Escape");
    await expect(dialog(page)).toHaveAttribute("data-phase", "running");
    await expect(dialog(page)).toHaveAttribute("data-phase", "result", { timeout: 8000 });
    await expect(dialog(page).getByRole("heading", { name: "Plan applied" })).toBeFocused();
    await expect(dialog(page).locator(".dc-apply-result-body")).toContainText(/5 plan steps, 2 files written at \d\d:\d\d\. A backup is kept for undo\./);
  });

  test("the fallback line shows the elapsed time when GET apply/progress fails", async ({ page, request }) => {
    await scenario(request, "apply-ready");
    await fault(request, { path: "/api/devcenter/apply/progress", code: "unknown", status: 500, once: false });
    await delay(request, { method: "apply", ms: 2000, once: true });
    await openPlan(page);
    await openApplyDialog(page);
    await dialog(page).locator('[data-confirm="apply"]').click();
    await expect(dialog(page).locator(".dc-apply-progress-line")).toContainText(/^Applying plan\. \d+ s elapsed\.$/);
    await expect(dialog(page)).toHaveAttribute("data-phase", "result", { timeout: 8000 });
  });

  test("the differences panel lists each difference", async ({ page, request }) => {
    await scenario(request, "apply-ready");
    await setApply(request, { replies: { apply: { rescan_differences: [{ object: "Sales/Margin", expected: "SUM(Sales[Margin])", found: "SUM(Sales[Amount])" }] } } });
    await openPlan(page);
    await openApplyDialog(page);
    await applyAndWait(page);
    await expect(dialog(page).getByRole("heading", { name: "Plan applied with 1 differences" })).toBeFocused();
    await expect(dialog(page).locator(".dc-apply-diff tbody tr")).toHaveCount(1);
    await expect(dialog(page).locator(".dc-apply-diff")).toContainText("SUM(Sales[Amount])");
  });

  test("the failure panel says nothing was written and gives one sentence for details.check", async ({ page, request }) => {
    await scenario(request, "apply-ready");
    await fault(request, { method: "apply", code: "action_not_allowed", message: "Guard stop.", details: { step: "guard", check: "pbir", reason: "guard_rejected" } });
    await openPlan(page);
    await openApplyDialog(page);
    await applyAndWait(page);
    await expect(dialog(page).getByRole("heading", { name: "Nothing was written" })).toBeFocused();
    await expect(dialog(page).locator(".dc-apply-result-body")).toHaveText(
      "The guard check stopped the apply. A report file change does not match the plan. Your target files are the same as before.");
    await expect(dialog(page).locator(".dc-apply-result-step")).toHaveText("Failed step: Guard check.");
    await expect(dialog(page).locator('[data-step="guard"]')).toHaveAttribute("data-state", "failed");
    await expect(dialog(page).getByRole("button", { name: "Open Log" })).toBeVisible();
    expect(await axeViolations(page)).toEqual([]);
    // The app theme switch sets both the dark class and data-theme on the root.
    await page.evaluate(() => {
      document.documentElement.classList.add("dark");
      document.documentElement.dataset.theme = "dark";
    });
    expect(await axeViolations(page)).toEqual([]);
  });

  test("a stale plan shows the stale copy with Check plan", async ({ page, request }) => {
    await scenario(request, "apply-ready");
    await fault(request, { method: "apply", code: "stale_revision", message: "Stale." });
    await openPlan(page);
    await openApplyDialog(page);
    await applyAndWait(page);
    await expect(dialog(page).getByRole("heading", { name: "The plan changed after you opened this dialog. Check it again." })).toBeVisible();
    await dialog(page).getByRole("button", { name: "Check plan" }).click();
    await expect(dialog(page)).toHaveCount(0);
    await expect(page.locator(".dc-plan-view [role=status]").first()).toHaveText(/Valid\./);
  });
});

test.describe("Undo, format only, and change report", () => {
  test("undo is available only with a backup, then shows progress, the result, and a toast", async ({ page, request }) => {
    await scenario(request, "apply-ready");
    await openPlan(page);
    await expect(strip(page).getByRole("button", { name: "Undo apply" })).toHaveCount(0);
    await openApplyDialog(page);
    await applyAndWait(page);
    await dialog(page).getByRole("button", { name: "Close" }).click();
    const undo = strip(page).getByRole("button", { name: "Undo apply" });
    await expect(undo).toBeVisible();
    await delay(request, { method: "undo_apply", ms: 1500, once: true });
    await undo.click();
    await expect(dialog(page).getByRole("heading", { name: /^Undo the apply of \d\d:\d\d\?$/ })).toBeVisible();
    await expect(dialog(page).getByRole("button", { name: "Cancel" })).toBeFocused();
    const confirm = dialog(page).locator('[data-confirm="undo"]');
    await expect(confirm).toHaveAttribute("data-variant", "destructive");
    await confirm.click();
    await expect(dialog(page)).toHaveAttribute("data-phase", "running");
    await expect(dialog(page).locator(".dc-apply-step")).toHaveCount(3);
    await expect(dialog(page)).toHaveAttribute("data-phase", "result", { timeout: 8000 });
    await expect(dialog(page).getByRole("heading", { name: "Apply undone" })).toBeFocused();
    await expect(page.locator(".ui-toast-text").filter({ hasText: /^Apply undone\. The target files are the same as before/ })).toBeVisible();
    await dialog(page).getByRole("button", { name: "Close" }).click();
    await expect(strip(page).getByRole("button", { name: "Undo apply" })).toHaveCount(0);
  });

  test("undo is refused with the file list when the target changed", async ({ page, request }) => {
    await scenario(request, "apply-ready");
    await setApply(request, { "apply-last": { apply_id: "apl-00000000000000a1", kind: "apply", finished_utc: "2026-10-31T10:00:00Z", file_count: 2,
      backup_present: true, target_changed: true, changed_files: ["Sales.SemanticModel/definition/tables/Sales.tmdl"], undone: false } });
    await openPlan(page);
    await strip(page).getByRole("button", { name: "Undo apply" }).click();
    await expect(dialog(page).getByRole("heading", { name: "Cannot undo this apply" })).toBeFocused();
    await expect(dialog(page).locator(".dc-apply-result-body")).toHaveText(/^1 target files changed after the apply\./);
    await expect(dialog(page).locator(".dc-apply-files")).toContainText("Sales.tmdl");
    await expect(dialog(page).getByRole("button", { name: /Undo/ })).toHaveCount(0);
  });

  test("format only: dialog, progress, result, then an automatic Check plan", async ({ page, request }) => {
    await scenario(request, "apply-ready");
    await setApply(request, { "apply-preview": { ready: false, non_canonical_files: ["Sales.SemanticModel/definition/model.tmdl", "Sales.SemanticModel/definition/tables/Sales.tmdl"] } });
    await openPlan(page);
    await strip(page).getByRole("button", { name: "Apply plan" }).click();
    await page.locator('[data-block-kind="files"]').getByRole("button", { name: "Format files first" }).click();
    await expect(dialog(page).getByRole("heading", { name: "Format 2 target files?" })).toBeVisible();
    await expect(dialog(page).getByRole("button", { name: "Cancel" })).toBeFocused();
    const confirm = dialog(page).locator('[data-confirm="format"]');
    await expect(confirm).toHaveAttribute("data-variant", "default");
    // The automatic Check plan fails here on purpose, so the page shows that the check ran.
    await fault(request, { path: "/api/devcenter/plan-validate", code: "unknown", status: 500 });
    await delay(request, { method: "format_only_apply", ms: 1000, once: true });
    await confirm.click();
    await expect(dialog(page)).toHaveAttribute("data-phase", "running");
    await expect(dialog(page).locator(".dc-apply-step")).toHaveCount(7);
    await expect(dialog(page)).toHaveAttribute("data-phase", "result", { timeout: 8000 });
    await expect(dialog(page).getByRole("heading", { name: "Files formatted" })).toBeFocused();
    await dialog(page).getByRole("button", { name: "Close" }).click();
    await expect(page.locator(".dc-plan-view [data-slot=notice][data-tone=bad]")).toBeVisible();
  });

  test("change report: save dialog default name, toast with Show in folder, and the failure toast", async ({ page, request }) => {
    await scenario(request, "apply-ready");
    await openPlan(page);
    await openApplyDialog(page);
    await applyAndWait(page);
    await dialog(page).getByRole("button", { name: "Write change report" }).click();
    const today = await page.evaluate(() => {
      const d = new Date();
      return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    });
    await expect(dialog(page).locator('[data-report="name"]')).toHaveText(`Sales and finance merge change report ${today}.md`);
    await dialog(page).getByRole("button", { name: "Save change report" }).click();
    const toast = page.locator(".ui-toast").filter({ hasText: "Change report saved" });
    await expect(toast).toBeVisible();
    await expect(toast.getByRole("button", { name: "Show in folder" })).toBeVisible();

    await fault(request, { method: "change_report_write", code: "not_found", message: "No report.", details: { reason: "no_apply" } });
    await strip(page).getByRole("button", { name: "Write change report" }).click();
    await dialog(page).getByRole("button", { name: "Save change report" }).click();
    await expect(page.locator(".ui-toast-text").filter({ hasText: /^Could not save the change report\./ })).toBeVisible();
  });
});
