// Step U6: Row detail pane, Merge Choice controls, NameField, FolderPicker, Alignment, and ProposalCard.
// Layout: 1280 x 900.
// All text follows ASD-STE100 rules. No emoji. No em dash or en dash.
import { test, expect } from "@playwright/test";
import { axeViolations, setTheme } from "./axe.js";

const VIEWPORTS = [
  { width: 1024, height: 640 },
  { width: 1280, height: 900 },
  { width: 1440, height: 900 },
];

async function checkOverflow(page) {
  return page.evaluate(() => ({
    overflowX: document.documentElement.scrollWidth - document.documentElement.clientWidth,
  }));
}

const FAKE = "http://127.0.0.1:8766";
test.use({ baseURL: FAKE, viewport: { width: 1280, height: 900 } });

async function scenario(request, name) {
  const loaded = await request.post("/__test__/scenario", { data: { name } });
  expect(loaded.ok()).toBe(true);
}

async function fault(request, method, code, extra = {}) {
  await request.post("/__test__/fault", { data: { method, code, ...extra } });
}

async function delay(request, path, ms, extra = {}) {
  await request.post("/__test__/delay", { data: { path, ms, ...extra } });
}

async function openDevCenter(page) {
  await page.goto("/");
  await page
    .getByRole("navigation", { name: "Main navigation" })
    .getByRole("button", { name: "Merge models" })
    .click();
}

async function workReady(page, name = "Sales and finance merge") {
  await expect(page.getByRole("heading", { level: 1, name })).toBeVisible();
  await expect(page.locator(".dc-busy-line")).toHaveCount(0);
}

test.describe("U6 Row detail pane focus and navigation (A10)", () => {
  test.beforeEach(async ({ page, request }) => {
    await scenario(request, "default");
    await openDevCenter(page);
    await workReady(page);
  });

  test("Enter opens the pane with focus on the h2; Close and Escape return focus; Previous and Next follow grid order and filter", async ({
    page,
  }) => {
    // Default not-same rows in asc name order: Budget, Customer, Gross Margin, Net Sales.
    const cell0 = page.locator('.dc-cell[data-r="0"][data-c="1"]');
    await cell0.focus();
    await page.keyboard.press("Enter");

    const pane = page.locator(".dc-row-pane");
    await expect(pane).toBeVisible();
    const h2 = pane.locator("#dc-row-pane-title");
    await expect(h2).toHaveText("Budget");
    await expect(h2).toBeFocused();

    // Previous is disabled on row 0; Next is enabled.
    const prevBtn = pane.getByRole("button", { name: "Previous row" });
    const nextBtn = pane.getByRole("button", { name: "Next row" });
    await expect(prevBtn).toBeDisabled();
    await expect(nextBtn).toBeEnabled();

    // Next moves to Customer, then Gross Margin.
    await nextBtn.click();
    await expect(h2).toHaveText("Customer");
    await expect(prevBtn).toBeEnabled();

    await nextBtn.click();
    await expect(h2).toHaveText("Gross Margin");

    // Previous moves back to Customer.
    await prevBtn.click();
    await expect(h2).toHaveText("Customer");

    // Escape closes the pane and returns focus to the grid cell.
    await page.keyboard.press("Escape");
    await expect(pane).toHaveCount(0);
    const cell1 = page.locator('.dc-cell[data-r="1"][data-c="1"]');
    await expect(cell1).toBeFocused();

    // Filter to "Sales" (1 row: Net Sales), press Enter, and click Close button.
    const search = page.locator("#q");
    await search.fill("Net Sales");
    await page.waitForTimeout(200);

    const filteredCell = page.locator('.dc-cell[data-r="0"][data-c="1"]');
    await filteredCell.focus();
    await page.keyboard.press("Enter");
    await expect(pane).toBeVisible();
    await expect(h2).toHaveText("Net Sales");
    await expect(h2).toBeFocused();
    await expect(prevBtn).toBeDisabled();
    await expect(nextBtn).toBeDisabled();

    await pane.locator("#closepane").click();
    await expect(pane).toHaveCount(0);
    await expect(filteredCell).toBeFocused();
  });
});

test.describe("U6 Merge Choice options, disabled reasons (A17), and immediate save", () => {
  test("each choice of section 4.4 shows its fields and disabled reason, including report measure extra choices", async ({
    page,
    request,
  }) => {
    await scenario(request, "default");
    await request.post("/__test__/compare-rows", {
      data: {
        rows: [
          {
            row_key: "measure:Sales.Net Sales",
            object_type: "measure",
            table: "Sales",
            name: "Net Sales",
            display_folder: "KPIs",
            row_state: "different",
            merge_choice: { kind: "take", source_id: "src-2" },
            marks: [],
            cells: {
              "src-1": { state: "target", present: true },
              "src-2": {
                state: "different",
                present: true,
                phrases: ["expression_changed", "format_string_changed"],
              },
            },
            properties: [
              { source_id: "src-2", property: "expression", phrase_id: "expression_changed" },
              {
                source_id: "src-2",
                property: "format_string",
                phrase_id: "format_string_changed",
                old: "#,0",
                new: "$#,0.00",
              },
            ],
          },
          {
            row_key: "measure:Sales.Budget",
            object_type: "measure",
            table: "Sales",
            name: "Budget",
            row_state: "missing",
            merge_choice: null,
            marks: [],
            cells: {
              "src-1": { state: "missing", present: false },
              "src-2": { state: "different", present: true },
            },
          },
          {
            row_key: "measure:Sales.TargetOnly",
            object_type: "measure",
            table: "Sales",
            name: "TargetOnly",
            row_state: "missing",
            merge_choice: null,
            marks: [],
            cells: {
              "src-1": { state: "target", present: true },
              "src-2": { state: "missing", present: false },
            },
          },
          {
            row_key: "measure:Report.Variance",
            object_type: "measure",
            subtype: "report_measure",
            table: "Sales",
            name: "Variance",
            row_state: "missing",
            merge_choice: null,
            marks: [],
            cells: {
              "src-1": { state: "missing", present: false },
              "src-2": { state: "different", present: true },
            },
          },
        ],
      },
    });

    await openDevCenter(page);
    await workReady(page);

    // 1. Budget (missing in target): "Take properties" and "Remove from target" are disabled with reasons.
    await page.locator(".dc-cell", { hasText: "Budget" }).click();
    const pane = page.locator(".dc-row-pane");
    await expect(pane).toBeVisible();

    const propsRadio = pane.getByRole("radio", { name: /Take properties/ });
    await expect(propsRadio).toBeDisabled();
    const propsDescId = await propsRadio.getAttribute("aria-describedby");
    expect(propsDescId).toBeTruthy();
    await expect(pane.locator(`#${propsDescId}`)).toContainText(
      "The target does not have this object. Nothing to change."
    );

    const removeRadio = pane.getByRole("radio", { name: "Remove from target" });
    await expect(removeRadio).toBeDisabled();
    const removeDescId = await removeRadio.getAttribute("aria-describedby");
    await expect(pane.locator(`#${removeDescId}`)).toContainText(
      "The target does not have this object."
    );

    // 2. TargetOnly (no donor has object): "Take from source" and "Add as new name" are disabled with reasons.
    await page.locator(".dc-cell", { hasText: "TargetOnly" }).click();
    const takeRadio = pane.getByRole("radio", { name: "Take from source" });
    await expect(takeRadio).toBeDisabled();
    const takeDescId = await takeRadio.getAttribute("aria-describedby");
    await expect(pane.locator(`#${takeDescId}`)).toContainText("No source has this object.");

    const addNewRadio = pane.getByRole("radio", { name: "Add as new name" });
    await expect(addNewRadio).toBeDisabled();
    const addNewDescId = await addNewRadio.getAttribute("aria-describedby");
    await expect(pane.locator(`#${addNewDescId}`)).toContainText("No source has this object.");

    // 3. Variance (report_measure): shows the two extra choices under "Report measure".
    await page.locator(".dc-cell", { hasText: "Variance" }).click();
    await expect(pane.getByText("Report measure").first()).toBeVisible();
    const promoteRadio = pane.getByRole("radio", { name: "Promote to target model" });
    const copyRadio = pane.getByRole("radio", { name: "Copy into target report" });
    await expect(promoteRadio).toBeEnabled();
    await expect(copyRadio).toBeEnabled();

    await promoteRadio.click();
    await expect(promoteRadio).toHaveAttribute("aria-checked", "true");
    await expect(pane.getByRole("button", { name: "Change name" })).toBeVisible();
    await expect(pane.getByRole("combobox", { name: "Display folder" })).toBeVisible();
  });

  test("save is immediate, shows Saving with aria-busy=true, and queues a second commit", async ({
    page,
    request,
  }) => {
    await scenario(request, "default");
    await openDevCenter(page);
    await workReady(page);

    await page.locator(".dc-cell", { hasText: "Net Sales" }).click();
    const pane = page.locator(".dc-row-pane");
    await expect(pane).toBeVisible();

    const payloads = [];
    await page.route("**/__test__/jsapi/merge_choice_set", async (route) => {
      payloads.push(JSON.parse(route.request().postData() || "{}"));
      await route.continue();
    });

    // Inject 400 ms delay on merge_choice_set so we can observe Saving and aria-busy.
    await delay(request, "merge_choice_set", 400, { once: true });

    const keepRadio = pane.getByRole("radio", { name: "Keep target" });
    const skipRadio = pane.getByRole("radio", { name: "Skip" });

    await keepRadio.click();
    await expect(keepRadio).toHaveAttribute("aria-busy", "true");
    await expect(pane.getByText("Saving")).toBeVisible();

    // Queue a second commit while the first is still running.
    await skipRadio.click();

    await expect(pane.getByText("Saving")).toHaveCount(0, { timeout: 5000 });
    expect(payloads.length).toBe(2);
    expect(payloads[0].choice.kind).toBe("keep");
    expect(payloads[1].choice.kind).toBe("skip");
    expect(payloads[1].base_revision).toBeGreaterThan(payloads[0].base_revision);
  });
});

test.describe("U6 Property picker, NameField, and FolderPicker", () => {
  test("property picker preselects different properties, disables Same properties, and blocks empty selection with no call", async ({
    page,
    request,
  }) => {
    await scenario(request, "default");
    await openDevCenter(page);
    await workReady(page);

    await page.locator(".dc-cell", { hasText: "Net Sales" }).click();
    const pane = page.locator(".dc-row-pane");

    let callCount = 0;
    await page.route("**/__test__/jsapi/merge_choice_set", async (route) => {
      callCount += 1;
      await route.continue();
    });

    const propsRadio = pane.getByRole("radio", { name: /Take properties from Finance model/ });
    await propsRadio.click();
    await expect(propsRadio).toHaveAttribute("aria-checked", "true");
    expect(callCount).toBe(1);

    // Net Sales has only expression_changed in the default fixture.
    const exprCheck = pane.getByRole("checkbox", { name: /Expression/ });
    const fmtCheck = pane.getByRole("checkbox", { name: /Format string/ });
    const descCheck = pane.getByRole("checkbox", { name: /Description/ });

    await expect(exprCheck).toBeChecked();
    await expect(fmtCheck).toBeDisabled();
    await expect(descCheck).toBeDisabled();

    // Uncheck Expression: 0 checked gives the error and no call.
    await exprCheck.click();
    await expect(pane.getByText("Select at least one property.")).toBeVisible();
    await expect(pane.locator(".dc-props-fieldset")).toHaveAttribute("aria-invalid", "true");
    expect(callCount).toBe(1);
  });

  test("NameField checks after 300 ms: rule break warning, clash error with Use proposed name, empty required error, and Escape restore", async ({
    page,
    request,
  }) => {
    await scenario(request, "default");
    await openDevCenter(page);
    await workReady(page);

    await page.locator(".dc-cell", { hasText: "Net Sales" }).click();
    const pane = page.locator(".dc-row-pane");

    const addNewRadio = pane.getByRole("radio", { name: "Add as new name" });
    await addNewRadio.click();

    const nameInput = pane.getByLabel("New name", { exact: true });
    await expect(nameInput).toBeVisible();
    // Auto-proposed on mount: "Net Sales (Finance model)" (since "Net Sales" clashes in target).
    await expect(nameInput).toHaveValue("Net Sales (Finance model)");

    // 1. Empty required name error.
    await nameInput.fill("");
    await expect(
      pane.getByText('Type a name. "Add as new name" needs a new name.')
    ).toBeVisible();
    await expect(nameInput).toHaveAttribute("aria-invalid", "true");

    // 2. Clash error ("Net Sales" already exists in target) + "Use proposed name" button.
    await nameInput.fill("Net Sales");
    await page.waitForTimeout(350);
    await expect(
      pane.getByText(/The target already has a measure "Net Sales" in Sales\./)
    ).toBeVisible();
    await expect(nameInput).toHaveAttribute("aria-invalid", "true");

    const useProposedBtn = pane.getByRole("button", {
      name: 'Use proposed name "Net Sales (Finance model)"',
    });
    await expect(useProposedBtn).toBeVisible();
    await useProposedBtn.click();
    await expect(nameInput).toHaveValue("Net Sales (Finance model)");
    await expect(nameInput).not.toHaveAttribute("aria-invalid", "true");

    // 3. Rule break warning (rule-1 requires Title Case: lowercase "bad_name" breaks rule-1).
    await nameInput.fill("bad_name");
    await page.waitForTimeout(350);
    await expect(
      pane.getByText(/This name breaks 1 naming rule:/)
    ).toBeVisible();

    // 4. Escape restores saved value ("Net Sales (Finance model)") without closing the pane.
    await nameInput.focus();
    await page.keyboard.press("Escape");
    await expect(nameInput).toHaveValue("Net Sales (Finance model)");
    await expect(pane).toBeVisible();
  });

  test("Display folder Combobox shows target and donor groups, new folder option, and load failure fallback", async ({
    page,
    request,
  }) => {
    await scenario(request, "default");
    await openDevCenter(page);
    await workReady(page);

    await page.locator(".dc-cell", { hasText: "Net Sales" }).click();
    const pane = page.locator(".dc-row-pane");
    await pane.getByRole("radio", { name: "Take from Finance model" }).click();

    const folderCombo = pane.getByRole("combobox", { name: "Display folder" });
    await expect(folderCombo).toBeVisible();

    // Open combobox: clear the current folder text so that all groups show.
    await folderCombo.fill("");
    await page.keyboard.press("ArrowDown");
    await expect(pane.getByText("In Finance model")).toBeVisible();
    await expect(pane.getByRole("option", { name: "Finance/Quarterly" })).toBeVisible();

    // Type a brand-new folder name to see 'Use new folder "<text>"'.
    await folderCombo.fill("Executive/Summary");
    const createOpt = pane.getByRole("option", {
      name: 'Use new folder "Executive/Summary"',
    });
    await expect(createOpt).toBeVisible();
    await createOpt.click();
    await expect(folderCombo).toHaveValue("Executive/Summary");

    // Load failure fallback: fault display-folders, load the app again, and open a measure row with a Take choice.
    await fault(request, "/api/devcenter/display-folders", "server_error", {
      status: 500,
      message: "Folder read failed",
      once: false,
    });
    await openDevCenter(page);
    await workReady(page);
    await page.locator(".dc-cell", { hasText: "Gross Margin" }).click();

    const marginFolderCombo = pane.getByRole("combobox", { name: "Display folder" });
    await marginFolderCombo.focus();
    await page.keyboard.press("ArrowDown");
    await expect(
      pane.getByText("Cannot load the folder list. You can type a folder.")
    ).toBeVisible();
    await marginFolderCombo.fill("Typed/Fallback");
    await expect(marginFolderCombo).toHaveValue("Typed/Fallback");
    await fault(request, "/api/devcenter/display-folders", null);
  });
});

test.describe("U6 Alignment actions, source marks, multi-row, and read-only", () => {
  test("Confirm and Reject rename, Split row confirm dialog, and Join with a row dialog", async ({
    page,
    request,
  }) => {
    await scenario(request, "default");
    await request.post("/__test__/compare-rows", {
      data: {
        rows: [
          {
            row_key: "measure:Sales.Net Sales",
            object_type: "measure",
            table: "Sales",
            name: "Net Sales",
            row_state: "different",
            merge_choice: { kind: "take", source_id: "src-2" },
            marks: [],
            cells: {
              "src-1": { state: "target", present: true },
              "src-2": {
                state: "different",
                present: true,
                notes: [
                  {
                    note_id: "possible_rename",
                    other_row_key: "measure:Sales.Total Net Sales",
                    other_name: "Total Net Sales",
                  },
                ],
              },
            },
          },
          {
            row_key: "measure:Sales.Budget",
            object_type: "measure",
            table: "Sales",
            name: "Budget",
            row_state: "missing",
            merge_choice: null,
            marks: [],
            cells: {
              "src-1": { state: "missing", present: false },
              "src-2": { state: "different", present: true },
            },
          },
        ],
      },
    });

    await openDevCenter(page);
    await workReady(page);

    await page.locator(".dc-cell", { hasText: "Net Sales" }).click();
    const pane = page.locator(".dc-row-pane");

    // 1. Possible rename notice is visible; Reject rename removes the notice.
    await expect(
      pane.getByText("Possible rename: Total Net Sales in Finance model and Net Sales in the target.")
    ).toBeVisible();
    await pane.getByRole("button", { name: "Reject rename" }).click();
    await expect(
      pane.getByText("Possible rename: Total Net Sales in Finance model and Net Sales in the target.")
    ).toHaveCount(0);

    // 2. Expand Alignment section and click Split row.
    await pane.getByRole("button", { name: "Alignment" }).click();
    await pane.getByRole("button", { name: "Split row" }).click();

    const splitDialog = page.getByRole("alertdialog");
    await expect(splitDialog).toBeVisible();
    await expect(splitDialog).toContainText("Split the row of Net Sales?");
    // Initial focus is on Cancel.
    await expect(splitDialog.getByRole("button", { name: "Cancel" })).toBeFocused();

    await splitDialog.getByRole("button", { name: "Split row" }).click();
    await expect(splitDialog).toHaveCount(0);

    // After split, Net Sales keeps the target row and its Merge Choice is removed.
    await expect(pane.locator("#dc-row-pane-title")).toHaveText("Net Sales");
    const keepRadio = pane.getByRole("radio", { name: "Keep target" });
    const takeRadio = pane.getByRole("radio", { name: "Take from source" });
    await expect(keepRadio).toHaveAttribute("aria-checked", "false");
    await expect(takeRadio).toBeDisabled();

    // 3. Join with a row opens the Join dialog and joins with Budget.
    await pane.getByRole("button", { name: "Join with a row" }).click();
    const joinDialog = page.getByRole("dialog", { name: "Join Net Sales with a row" });
    await expect(joinDialog).toBeVisible();

    const searchCombo = joinDialog.getByRole("combobox", {
      name: "Search objects of the same type",
    });
    await searchCombo.focus();
    await page.keyboard.press("ArrowDown");
    await joinDialog.getByRole("option", { name: /Budget/ }).click();
    await joinDialog.getByRole("button", { name: "Join rows" }).click();
    await expect(joinDialog).toHaveCount(0);

    // After join, Finance model donor is back on Net Sales so Take from Finance model is enabled.
    await expect(
      pane.getByRole("radio", { name: "Take from Finance model" })
    ).toBeEnabled();
  });

  test("source mark Confirm row and ProposalCard blocked state on marked row", async ({
    page,
    request,
  }) => {
    await scenario(request, "sources-changed");
    await openDevCenter(page);
    await workReady(page);

    await page.locator(".dc-cell", { hasText: "Net Sales" }).click();
    const pane = page.locator(".dc-row-pane");
    await expect(pane).toBeVisible();

    // ProposalCard is visible, and Accept is disabled while row has a mark.
    const propCard = pane.locator('[data-slot="proposal-card"]');
    await expect(propCard).toBeVisible();
    await expect(propCard).toContainText("Proposed by agent");
    const acceptBtn = propCard.getByRole("button", {
      name: /Accept|Replace with agent choice/,
    });
    await expect(acceptBtn).toBeDisabled();

    // Click Confirm row in the source mark notice.
    const confirmRowBtn = pane.getByRole("button", { name: "Confirm row" }).first();
    await confirmRowBtn.click();
    await expect(page.locator(".ui-toast").last()).toContainText("Row confirmed.");

    // Mark notice is gone and ProposalCard Accept button becomes enabled.
    await expect(acceptBtn).toBeEnabled();
  });

  test("many rows selected shows multi-row summary and Clear selection", async ({
    page,
    request,
  }) => {
    await scenario(request, "default");
    await openDevCenter(page);
    await workReady(page);

    // Open row detail pane, then select 2 rows in the grid.
    await page.locator(".dc-cell", { hasText: "Net Sales" }).click();
    await page.locator('.dc-body-row[data-i="0"] input[type="checkbox"]').click();
    await page.locator('.dc-body-row[data-i="1"] input[type="checkbox"]').click();

    const pane = page.locator(".dc-row-pane");
    await expect(pane.locator("#dc-row-pane-title")).toHaveText("2 rows selected");
    await expect(
      pane.getByText("Use the bar above the grid to set one Merge Choice for all selected rows.")
    ).toBeVisible();

    await pane.getByRole("button", { name: "Clear selection" }).click();
    await expect(pane.locator("#dc-row-pane-title")).toHaveText("Net Sales");
  });

  test("read-only session disables change controls in pane while keeping code diff and impact links active", async ({
    page,
    request,
  }) => {
    await scenario(request, "locked");
    await openDevCenter(page);
    await workReady(page);

    await page.locator(".dc-cell", { hasText: "Net Sales" }).click();
    const pane = page.locator(".dc-row-pane");
    await expect(pane).toBeVisible();
    await expect(
      pane.getByText("This session is read-only. Another PBIBrain window has it open.")
    ).toBeVisible();

    // All Merge Choice radios are disabled.
    const radios = pane.getByRole("radio");
    const count = await radios.count();
    expect(count).toBeGreaterThan(0);
    for (let i = 0; i < count; i++) {
      await expect(radios.nth(i)).toBeDisabled();
    }

    // Show code diff and Show impact of this row remain active.
    const diffBtn = pane.getByRole("button", { name: "Show code diff" }).first();
    const impactBtn = pane.getByRole("button", { name: "Show impact of this row" });
    await expect(diffBtn).toBeEnabled();
    await expect(impactBtn).toBeEnabled();
  });
});

test.describe("U6 Accessibility (A1) and viewport overflow (A18)", () => {
  test("axe passes with row detail pane open in light and dark themes and zero page overflow across viewports", async ({
    page,
    context,
    request,
  }) => {
    await scenario(request, "default");

    for (const theme of ["light", "dark"]) {
      await setTheme(context, theme);
      for (const vp of VIEWPORTS) {
        await page.setViewportSize({ width: vp.width, height: vp.height });
        await openDevCenter(page);
        await workReady(page);

        await page.locator(".dc-cell", { hasText: "Net Sales" }).click();
        await expect(page.locator(".dc-row-pane")).toBeVisible();

        const violations = await axeViolations(page);
        expect(violations).toEqual([]);

        const overflow = await checkOverflow(page);
        expect(overflow.overflowX).toBeLessThanOrEqual(0);
      }
    }
  });
});
