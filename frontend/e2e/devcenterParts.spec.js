import { test, expect } from "@playwright/test";
import { axeViolations, setTheme } from "./axe.js";

// Step U1: the shared parts on the specimen page of the fake server (UI design 13, U1).
const FAKE = "http://127.0.0.1:8766";
const SPECIMEN = "/__specimen__";
test.use({ baseURL: FAKE, viewport: { width: 1440, height: 900 } });

async function openSpecimen(page) {
  await page.goto(SPECIMEN);
  await expect(page.getByRole("heading", { level: 1, name: "Part specimen" })).toBeVisible();
}

const part = (page, id) => page.locator(`[data-part="${id}"]`);

test("the specimen route shows only with the fake server shim", async ({ page }) => {
  await openSpecimen(page);
  // The graph test server serves the same build with no shim: the route shows the app.
  await page.goto("http://127.0.0.1:8765/__specimen__");
  await page.waitForLoadState("networkidle");
  await expect(page.getByRole("heading", { name: "Part specimen" })).toHaveCount(0);
  await expect(page.locator(".specimen")).toHaveCount(0);
});

for (const theme of ["dark", "light"]) {
  test(`axe finds 0 violations on the specimen in the ${theme} theme`, async ({ page, context }) => {
    await setTheme(context, theme);
    await openSpecimen(page);
    if (theme === "light") await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
    else await expect(page.locator("html")).not.toHaveAttribute("data-theme", "light");
    expect(await axeViolations(page)).toEqual([]);

    // Open states: a Select listbox, a Menu, a Combobox list, a dialog, and the side pane.
    await page.getByRole("combobox", { name: "Merge Choice" }).click();
    await expect(page.getByRole("listbox")).toBeVisible();
    // A modal overlay (Radix hideOthers) puts aria-hidden on the page behind it, and its focus
    // trap keeps focus out of that page. Check the overlay itself in the open states.
    expect(await axeViolations(page, { include: "[role=listbox]" })).toEqual([]);
    await page.keyboard.press("Escape");

    await part(page, "menu").getByRole("button", { name: "Row actions" }).click();
    await expect(page.getByRole("menu")).toBeVisible();
    expect(await axeViolations(page)).toEqual([]);
    await page.keyboard.press("Escape");

    const folder = page.getByRole("combobox", { name: "Display folder" });
    await folder.fill("Fin");
    await expect(page.getByRole("listbox", { name: "Display folder" })).toBeVisible();
    expect(await axeViolations(page)).toEqual([]);
    await folder.press("Escape");

    await part(page, "sidepane").getByRole("button", { name: "Open Margin" }).click();
    await expect(page.getByRole("complementary", { name: "Margin" })).toBeVisible();
    expect(await axeViolations(page)).toEqual([]);

    await page.getByRole("button", { name: "Rename object" }).click();
    await expect(page.getByRole("dialog", { name: "Rename object" })).toBeVisible();
    expect(await axeViolations(page, { include: "[role=dialog]" })).toEqual([]);
  });
}

test("each status shows an icon and a word (A4)", async ({ page }) => {
  await openSpecimen(page);
  const badges = page.locator("[data-status]");
  expect(await badges.count()).toBeGreaterThan(6);
  for (const badge of await badges.all()) {
    await expect(badge.locator("svg")).toHaveCount(1);
    expect((await badge.innerText()).trim().length).toBeGreaterThan(0);
  }
});

test("checkbox, switch, radio, and segmented control change state on click", async ({ page }) => {
  await openSpecimen(page);
  const checkbox = page.getByRole("checkbox", { name: "Include hidden objects" });
  await expect(checkbox).toHaveAttribute("aria-checked", "false");
  await checkbox.click();
  await expect(checkbox).toHaveAttribute("aria-checked", "true");
  await page.getByText("Include hidden objects").click();
  await expect(checkbox).toHaveAttribute("aria-checked", "false");
  await expect(page.getByRole("checkbox", { name: "Select page" })).toHaveAttribute("aria-checked", "mixed");
  const box = await checkbox.boundingBox();
  expect(box.width).toBeGreaterThanOrEqual(24);
  expect(box.height).toBeGreaterThanOrEqual(24);

  const toggle = page.getByRole("switch", { name: "Use the / key to go to search" });
  await expect(toggle).toHaveAttribute("aria-checked", "false");
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-checked", "true");

  const choice = part(page, "choice").getByRole("radiogroup", { name: "Merge Choice" });
  await expect(choice.getByRole("radio", { name: "Keep target" })).toHaveAttribute("aria-checked", "true");
  await choice.getByRole("radio", { name: "Use source" }).click();
  await expect(choice.getByRole("radio", { name: "Use source" })).toHaveAttribute("aria-checked", "true");
  await expect(choice.getByRole("textbox", { name: "New name" })).toBeVisible();
  const disabled = choice.getByRole("radio", { name: "Keep both" });
  await expect(disabled).toBeDisabled();
  await expect(disabled).toHaveAccessibleDescription("The names clash. Rename one object first.");

  const view = page.getByRole("group", { name: "View", exact: true });
  await expect(view.getByRole("button", { name: "Grid" })).toHaveAttribute("aria-pressed", "true");
  await view.getByRole("button", { name: "Graph" }).click();
  await expect(view.getByRole("button", { name: "Graph" })).toHaveAttribute("aria-pressed", "true");
  await expect(view.getByRole("button", { name: "Grid" })).toHaveAttribute("aria-pressed", "false");
  const mode = page.getByRole("radiogroup", { name: "Match mode" });
  await mode.getByRole("radio", { name: "Strict" }).click();
  await expect(mode.getByRole("radio", { name: "Strict" })).toHaveAttribute("aria-checked", "true");

  const theme = page.getByRole("switch", { name: "Light theme" });
  await theme.click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
});

test("Button: destructive uses bad-ink on bad, and loading is busy and does not act", async ({ page }) => {
  await openSpecimen(page);
  const destructive = part(page, "button").getByRole("button", { name: "Remove object" });
  const colors = await destructive.evaluate((node) => {
    const style = getComputedStyle(node);
    const root = getComputedStyle(document.documentElement);
    const probe = (value) => { const el = document.createElement("span"); el.style.color = value; document.body.append(el); const out = getComputedStyle(el).color; el.remove(); return out; };
    return { color: style.color, background: style.backgroundColor, ink: probe(root.getPropertyValue("--bad-ink")), bad: probe(root.getPropertyValue("--bad")) };
  });
  expect(colors.color).toBe(colors.ink);
  expect(colors.background).toBe(colors.bad);
  const loading = part(page, "button").getByRole("button", { name: "Checking sources" });
  await expect(loading).toHaveAttribute("aria-busy", "true");
  await expect(loading).toHaveAttribute("aria-disabled", "true");
});

test("Tabs: arrows, Home, and End move and select; each panel stays in the DOM; the active tab is a fill", async ({ page }) => {
  await openSpecimen(page);
  const list = page.getByRole("tablist", { name: "Work area" });
  const compare = list.getByRole("tab", { name: /^Compare/ });
  await compare.focus();
  await page.keyboard.press("ArrowRight");
  await expect(list.getByRole("tab", { name: /^Impact/ })).toBeFocused();
  await expect(list.getByRole("tab", { name: /^Impact/ })).toHaveAttribute("aria-selected", "true");
  await page.keyboard.press("End");
  await expect(list.getByRole("tab", { name: "Plan" })).toBeFocused();
  await page.keyboard.press("Home");
  await expect(compare).toHaveAttribute("aria-selected", "true");

  for (const tab of await list.getByRole("tab").all()) {
    const controls = await tab.getAttribute("aria-controls");
    await expect(page.locator(`[id="${controls}"]`)).toHaveCount(1);
  }
  await expect(page.locator('[data-part="tabs"] [role="tabpanel"]')).toHaveCount(4);
  await expect(page.locator('[data-part="tabs"] [role="tabpanel"][hidden]')).toHaveCount(3);

  const look = await compare.evaluate((node) => {
    const style = getComputedStyle(node);
    const list = getComputedStyle(node.parentElement);
    return { fill: style.backgroundColor, track: list.backgroundColor, bottom: style.borderBottomWidth, shadow: style.boxShadow, after: getComputedStyle(node, "::after").content };
  });
  expect(look.fill).not.toBe(look.track);
  expect(look.fill).not.toBe("rgba(0, 0, 0, 0)");
  expect(look.bottom).toBe("0px");
  expect(["none", "normal", ""]).toContain(look.after);
});

test("Select: keys open, move, select, and close", async ({ page }) => {
  await openSpecimen(page);
  // An open listbox hides the rest of the page from the accessibility tree, so use the element.
  const trigger = page.locator('[data-part="select"] .ui-select-trigger').first();
  await expect(page.getByRole("combobox", { name: "Merge Choice" })).toHaveAttribute("aria-haspopup", "listbox");
  await trigger.focus();
  await page.keyboard.press("Enter");
  await expect(trigger).toHaveAttribute("aria-expanded", "true");
  const listbox = page.getByRole("listbox");
  await expect(listbox.getByRole("option", { name: /Keep target/ })).toBeFocused();
  const disabled = listbox.getByRole("option", { name: /Keep both/ });
  await expect(disabled).toHaveAttribute("aria-disabled", "true");
  await expect(disabled).toContainText("The names clash. Rename one object first.");
  await page.keyboard.press("ArrowDown");
  await expect(listbox.getByRole("option", { name: /Use source/ })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(listbox).toHaveCount(0);
  await expect(trigger).toHaveText(/Use source/);
  await expect(trigger).toBeFocused();

  await page.keyboard.press("Space");
  await expect(page.getByRole("listbox")).toBeVisible();
  await page.keyboard.press("Home");
  await expect(page.getByRole("option", { name: /Keep target/ })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("listbox")).toHaveCount(0);
  await expect(trigger).toHaveText(/Use source/);
  await expect(trigger).toBeFocused();

  const invalid = page.locator('[data-part="select"] [aria-invalid="true"]');
  await expect(invalid).toHaveAccessibleDescription("Select a sort order.");
});

test("Combobox: typing filters, arrows move, Enter selects, Escape closes and then clears", async ({ page }) => {
  await openSpecimen(page);
  const input = page.getByRole("combobox", { name: "Display folder" });
  await input.focus();
  await page.keyboard.press("ArrowDown");
  await expect(input).toHaveAttribute("aria-expanded", "true");
  const listbox = page.getByRole("listbox", { name: "Display folder" });
  await expect(listbox.getByRole("option")).toHaveCount(4);
  await page.keyboard.type("fin");
  await expect(listbox.getByRole("option")).toHaveCount(2);
  await expect(listbox.getByRole("option").first()).toHaveText(/Use new folder "fin"/);
  await page.keyboard.press("ArrowDown");
  const active = await input.getAttribute("aria-activedescendant");
  await expect(page.locator(`[id="${active}"]`)).toHaveText("Finance");
  await page.keyboard.press("Enter");
  await expect(input).toHaveValue("Finance");
  await expect(input).toHaveAttribute("aria-expanded", "false");

  await page.keyboard.press("ArrowDown");
  await expect(input).toHaveAttribute("aria-expanded", "true");
  await page.keyboard.press("Escape");
  await expect(input).toHaveAttribute("aria-expanded", "false");
  await expect(input).toHaveValue("Finance");
  await page.keyboard.press("Escape");
  await expect(input).toHaveValue("");

  await page.keyboard.type("Q4 reports");
  await page.keyboard.press("Enter");
  await expect(input).toHaveValue("Q4 reports");
  await expect(page.getByRole("combobox", { name: "Folder name" })).toHaveAccessibleDescription("Type a folder name.");
});

test("Menu: keys open, move, select, and Escape returns focus to the trigger", async ({ page }) => {
  await openSpecimen(page);
  const trigger = part(page, "menu").getByRole("button", { name: "Row actions" });
  await expect(trigger).toHaveAttribute("aria-haspopup", "menu");
  await trigger.focus();
  await page.keyboard.press("Enter");
  const menu = page.getByRole("menu");
  await expect(menu).toBeVisible();
  await expect(trigger).toHaveAttribute("aria-expanded", "true");
  await expect(menu.getByRole("menuitem", { name: "Rename" })).toBeFocused();
  await page.keyboard.press("ArrowDown");
  await expect(menu.getByRole("menuitem", { name: "Copy name" })).toBeFocused();
  await page.keyboard.press("End");
  await expect(menu.getByRole("menuitem", { name: "Remove from plan" })).toBeFocused();
  await page.keyboard.press("Home");
  await expect(menu.getByRole("menuitem", { name: "Rename" })).toBeFocused();
  await expect(menu.getByRole("menuitem", { name: "Show code" })).toHaveAttribute("aria-disabled", "true");
  await expect(menu.getByRole("menuitemcheckbox", { name: "Show hidden objects" })).toHaveAttribute("aria-checked", "true");
  await page.keyboard.press("Escape");
  await expect(menu).toHaveCount(0);
  await expect(trigger).toBeFocused();

  await page.keyboard.press("ArrowDown");
  await expect(page.getByRole("menu")).toBeVisible();
  await page.keyboard.press("c");
  await expect(page.getByRole("menuitem", { name: "Copy name" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("menu")).toHaveCount(0);
  await expect(part(page, "menu").getByRole("status")).toHaveText("Last action: Copy name");
  await expect(trigger).toBeFocused();
});

test("SegmentedControl: toggle mode uses Tab and Space, radio mode uses arrows", async ({ page }) => {
  await openSpecimen(page);
  const view = page.getByRole("group", { name: "View", exact: true });
  await view.getByRole("button", { name: "Grid" }).focus();
  await page.keyboard.press("Tab");
  await expect(view.getByRole("button", { name: "Graph" })).toBeFocused();
  await page.keyboard.press("Space");
  await expect(view.getByRole("button", { name: "Graph" })).toHaveAttribute("aria-pressed", "true");

  const mode = page.getByRole("radiogroup", { name: "Match mode" });
  const def = mode.getByRole("radio", { name: "Default" });
  const strict = mode.getByRole("radio", { name: "Strict" });
  await expect(strict).toHaveAttribute("tabindex", "-1");
  await def.focus();
  await page.keyboard.press("ArrowRight");
  await expect(strict).toBeFocused();
  await expect(strict).toHaveAttribute("aria-checked", "true");
  await page.keyboard.press("ArrowRight");
  await expect(def).toBeFocused();
  await expect(def).toHaveAttribute("aria-checked", "true");
  await page.keyboard.press("ArrowLeft");
  await expect(strict).toHaveAttribute("aria-checked", "true");
  // Only the checked radio is a Tab stop.
  await expect(def).toHaveAttribute("tabindex", "-1");
});

test("Dialog: initial focus on the first field, focus trap, Escape, and focus return (A9)", async ({ page }) => {
  await openSpecimen(page);
  const trigger = page.getByRole("button", { name: "Rename object" });
  await trigger.click();
  const dialog = page.getByRole("dialog", { name: "Rename object" });
  await expect(dialog).toHaveAttribute("aria-modal", "true");
  await expect(dialog.getByRole("textbox", { name: "New name" })).toBeFocused();
  for (let index = 0; index < 6; index += 1) {
    await page.keyboard.press("Tab");
    expect(await dialog.evaluate((node) => node.contains(document.activeElement))).toBe(true);
  }
  await page.keyboard.press("Shift+Tab");
  expect(await dialog.evaluate((node) => node.contains(document.activeElement))).toBe(true);
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(trigger).toBeFocused();

  await trigger.press("Enter");
  await page.getByRole("dialog", { name: "Rename object" }).getByRole("button", { name: "Save name" }).click();
  await expect(trigger).toBeFocused();
});

test("AlertDialog: initial focus on Cancel for a destructive action, and focus return", async ({ page }) => {
  await openSpecimen(page);
  const trigger = part(page, "dialog").getByRole("button", { name: "Delete rule" });
  await trigger.click();
  const dialog = page.getByRole("alertdialog", { name: "Delete the naming rule?" });
  await expect(dialog.getByRole("button", { name: "Cancel" })).toBeFocused();
  await expect(dialog.getByRole("button", { name: "Delete rule" })).toHaveClass(/ui-button-destructive/);
  await page.keyboard.press("Tab");
  await page.keyboard.press("Tab");
  expect(await dialog.evaluate((node) => node.contains(document.activeElement))).toBe(true);
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(trigger).toBeFocused();
});

test("Dialog in progress mode: no close button, and Escape does nothing", async ({ page }) => {
  await openSpecimen(page);
  const trigger = page.getByRole("button", { name: "Apply plan", exact: true }).last();
  await trigger.click();
  const dialog = page.getByRole("dialog", { name: "Apply the plan" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Close" })).toHaveCount(0);
  await page.keyboard.press("Escape");
  await expect(dialog).toBeVisible();
  await page.mouse.click(10, 10);
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "Finish demo" }).click();
  await expect(dialog).toHaveCount(0);
  await expect(trigger).toBeFocused();
});

test("Toast: one polite region, a close button, and it stays at least 8 s", async ({ page }) => {
  await page.clock.install();
  await openSpecimen(page);
  const region = page.getByRole("status", { name: "Notifications" });
  await expect(region).toHaveAttribute("aria-live", "polite");
  const trigger = page.getByRole("button", { name: "Show toast" });
  await trigger.click();
  await expect(region).toContainText("Merge Choice set for 3 rows.");
  await expect(trigger).toBeFocused();
  await page.clock.runFor(7900);
  await expect(region).toContainText("Merge Choice set for 3 rows.");
  // The fake clock stops animation frames, so skip the stable check of hover.
  await region.locator(".ui-toast").hover({ force: true });
  await page.clock.runFor(5000);
  await expect(region).toContainText("Merge Choice set for 3 rows.");
  await page.mouse.move(5, 5);
  await page.clock.runFor(500);
  await expect(region.locator(".ui-toast")).toHaveCount(0);
  await trigger.click();
  await region.getByRole("button", { name: "Close notification" }).click();
  await expect(region.locator(".ui-toast")).toHaveCount(0);
});

for (const size of [{ width: 1440, height: 900, mode: "aside" }, { width: 1024, height: 640, mode: "sheet" }]) {
  test(`SidePane at ${size.width} x ${size.height}: focus on the h2, ${size.mode} rules, focus return (A10)`, async ({ page }) => {
    await page.setViewportSize({ width: size.width, height: size.height });
    await openSpecimen(page);
    const opener = part(page, "sidepane").getByRole("button", { name: "Open Margin" });
    await opener.focus();
    await page.keyboard.press("Enter");
    const heading = page.getByRole("heading", { level: 2, name: "Margin" });
    await expect(heading).toBeFocused();
    if (size.mode === "aside") {
      await expect(page.getByRole("complementary", { name: "Margin" })).toBeVisible();
      await expect(page.getByRole("dialog")).toHaveCount(0);
    } else {
      const sheet = page.getByRole("dialog", { name: "Margin" });
      await expect(sheet).toHaveAttribute("aria-modal", "true");
      // Measure after the sheet-in animation ends, because the slide changes the box.
      await sheet.evaluate((node) => Promise.all(node.getAnimations({ subtree: true }).map((animation) => animation.finished)));
      const width = await sheet.evaluate((node) => parseFloat(getComputedStyle(node).width));
      expect(width).toBeLessThanOrEqual(400);
      for (let index = 0; index < 8; index += 1) {
        await page.keyboard.press("Tab");
        expect(await sheet.evaluate((node) => node.contains(document.activeElement))).toBe(true);
      }
    }
    const next = page.getByRole("button", { name: "Next row" });
    await next.click();
    await expect(page.getByRole("heading", { level: 2, name: "Region" })).toBeVisible();
    // At the last row, Next row stays in place and keeps focus (UI design 9.2).
    await expect(next).toHaveAttribute("aria-disabled", "true");
    await expect(next).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("heading", { level: 2, name: "Region" })).toBeVisible();
    await expect(next).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("heading", { level: 2, name: "Region" })).toHaveCount(0);
    await expect(opener).toBeFocused();

    await opener.press("Enter");
    await expect(page.getByRole("heading", { level: 2, name: "Margin" })).toBeFocused();
    await page.getByRole("button", { name: "Close", exact: true }).click();
    await expect(opener).toBeFocused();
  });
}
