// Step U12: release checks. One sweep over each Development Center screen in both themes
// (UI design 9.1: A1, A7, A11, A15, A18, A22, A23). Layout: 1280 x 900 (scope cut 2026-11-01).
// A21 (200% zoom) is a scope cut (WORKER.md, 2026-11-01). The build record lists it.
// All text follows ASD-STE100 rules. No emoji. No em dash or en dash.
import { test, expect } from "@playwright/test";
import { axeViolations } from "./axe.js";

const FAKE = "http://127.0.0.1:8766";
const VIEWPORT = { width: 1280, height: 900 };
test.use({ baseURL: FAKE, viewport: VIEWPORT });

async function post(request, path, data) {
  const res = await request.post(path, { data });
  expect(res.ok()).toBe(true);
}

const scenario = (request, name) => post(request, "/__test__/scenario", { name });
const tab = (page, name) => page.getByRole("tablist", { name: "Work area tabs" }).getByRole("tab", { name: new RegExp(`^${name}`) });
const impactPanel = (page) => page.getByRole("tabpanel", { name: "Impact" });

async function openWork(page, name = "Sales and finance merge") {
  await page.goto("/");
  await page.getByRole("navigation", { name: "Main navigation" }).getByRole("button", { name: "Merge models" }).click();
  await expect(page.getByRole("heading", { level: 1, name })).toBeVisible();
  await expect(page.locator(".dc-busy-line")).toHaveCount(0);
}

async function openTab(page, name, ready) {
  await openWork(page);
  await tab(page, name).click();
  await expect(ready(page)).toBeVisible();
}

async function impactView(page, view, ready) {
  await openTab(page, "Impact", (p) => p.locator(".dc-impact"));
  await impactPanel(page).getByRole("radio", { name: view }).click();
  await expect(ready(page)).toBeVisible();
}

// Each screen and state of the release sweep. "start" is the element where the Tab walk starts.
const SCREENS = [
  {
    name: "session list",
    setup: async (page, request) => {
      await scenario(request, "default");
      await openWork(page);
      await page.getByRole("navigation", { name: "Breadcrumb" }).getByRole("button", { name: "Merge models" }).click();
      await expect(page.getByRole("heading", { level: 1, name: "Merge sessions" })).toBeVisible();
    },
    start: (page) => page.getByRole("heading", { level: 1, name: "Merge sessions" }),
  },
  {
    name: "session list empty",
    setup: async (page, request) => {
      await scenario(request, "no-sessions");
      await page.goto("/");
      await page.getByRole("navigation", { name: "Main navigation" }).getByRole("button", { name: "Merge models" }).click();
      await expect(page.getByRole("heading", { name: "No merge sessions yet" })).toBeVisible();
    },
    start: (page) => page.getByRole("heading", { name: "No merge sessions yet" }),
  },
  {
    name: "compare",
    setup: async (page, request) => {
      await scenario(request, "default");
      await openWork(page);
      await expect(page.locator(".dc-cell").first()).toBeVisible();
    },
  },
  {
    name: "compare large-5000-rows",
    setup: async (page, request) => {
      await scenario(request, "large-5000-rows");
      await page.goto("/");
      await page.getByRole("navigation", { name: "Main navigation" }).getByRole("button", { name: "Merge models" }).click();
      await expect(page.locator(".dc-cell").first()).toBeVisible();
      await expect(page.locator(".dc-busy-line")).toHaveCount(0);
    },
  },
  {
    name: "row detail",
    setup: async (page, request) => {
      await scenario(request, "default");
      await openWork(page);
      await page.locator('.dc-cell[data-r="0"][data-c="1"]').focus();
      await page.keyboard.press("Enter");
      await expect(page.locator("#dc-row-pane-title")).toBeFocused();
    },
    start: (page) => page.locator("#dc-row-pane-title"),
  },
  {
    name: "impact table",
    setup: async (page, request) => {
      await scenario(request, "default");
      await openTab(page, "Impact", (p) => p.getByRole("table", { name: "Impact items" }));
    },
  },
  {
    name: "impact graph",
    setup: async (page, request) => {
      await scenario(request, "default");
      await impactView(page, "Graph", (p) => p.locator(".dc-impact-node").first());
    },
  },
  {
    name: "impact wireframe",
    setup: async (page, request) => {
      await scenario(request, "default");
      await impactView(page, "Wireframe", (p) => p.getByRole("group", { name: "Page Overview" }));
    },
  },
  {
    name: "plan",
    setup: async (page, request) => {
      await scenario(request, "default");
      await openTab(page, "Plan", (p) => p.locator(".dc-plan-strip"));
    },
  },
  {
    name: "plan invalid",
    setup: async (page, request) => {
      await scenario(request, "plan-invalid");
      await openTab(page, "Plan", (p) => p.locator(".dc-plan-strip"));
    },
  },
  {
    name: "apply dialog",
    setup: async (page, request) => {
      await scenario(request, "default");
      await openTab(page, "Plan", (p) => p.locator(".dc-plan-strip"));
      await page.locator(".dc-plan-strip").getByRole("button", { name: "Apply plan" }).click();
      await expect(page.getByRole("alertdialog")).toHaveAttribute("data-phase", "confirm");
    },
    start: "active",
  },
  {
    name: "apply result",
    setup: async (page, request) => {
      await scenario(request, "apply-ready");
      await openTab(page, "Plan", (p) => p.locator(".dc-plan-strip"));
      await page.locator(".dc-plan-strip").getByRole("button", { name: "Apply plan" }).click();
      await page.getByRole("alertdialog").locator('[data-confirm="apply"]').click();
      await expect(page.getByRole("alertdialog")).toHaveAttribute("data-phase", "result");
    },
    start: "active",
  },
  {
    name: "agent",
    setup: async (page, request) => {
      await scenario(request, "default");
      await post(request, "/__test__/agent-review", {});
      await openTab(page, "Agent", (p) => p.locator(".dc-agent-row").first());
    },
  },
  {
    name: "sources",
    setup: async (page, request) => {
      await scenario(request, "default");
      await openTab(page, "Sources", (p) => p.getByRole("heading", { name: "Naming rules for Combined model" }));
    },
  },
  {
    name: "log",
    setup: async (page, request) => {
      await scenario(request, "default");
      await openTab(page, "Log", (p) => p.getByRole("tabpanel", { name: "Log" }));
    },
  },
];

// Set the theme the same way as the app theme switch: the "dark" class and data-theme on the root.
async function applyTheme(page, theme) {
  await page.evaluate((value) => {
    const root = document.documentElement;
    root.classList.toggle("dark", value === "dark");
    if (value === "light") root.dataset.theme = "light";
    else delete root.dataset.theme;
  }, theme);
  // Wait for the color transitions to end, because axe reads the colors as they are now.
  await page.evaluate(() => Promise.all(document.getAnimations().map((item) => item.finished.catch(() => null))));
}

// A7: walk the focus with Tab. Each focused element shows a 2 px ring and is the top element at its center.
async function focusWalk(page, screen, steps = 10) {
  if (screen.start === "active") {
    // A dialog puts the initial focus itself.
  } else {
    const start = screen.start ? screen.start(page) : page.getByRole("tablist", { name: "Work area tabs" }).getByRole("tab", { selected: true });
    await start.focus();
  }
  const problems = [];
  const seen = [];
  for (let index = 0; index < steps; index += 1) {
    await page.keyboard.press("Tab");
    const record = await page.evaluate(() => {
      const el = document.activeElement;
      if (!el || el === document.body) return null;
      // The ring can be on the element or on a near wrapper with :focus-within (the search field).
      let ring = false;
      for (let node = el, depth = 0; node && depth < 3 && !ring; node = node.parentElement, depth += 1) {
        const style = getComputedStyle(node);
        const outline = style.outlineStyle !== "none" ? parseFloat(style.outlineWidth) : 0;
        ring = outline >= 2 || (node === el && style.boxShadow && style.boxShadow !== "none");
      }
      const box = el.getBoundingClientRect();
      const x = Math.min(Math.max(box.left + box.width / 2, 0), window.innerWidth - 1);
      const y = Math.min(Math.max(box.top + box.height / 2, 0), window.innerHeight - 1);
      const hit = document.elementFromPoint(x, y);
      const visible = Boolean(hit) && (el === hit || el.contains(hit) || hit.contains(el) || hit.closest("label")?.contains(el));
      const label = el.getAttribute("aria-label") || el.textContent?.trim().slice(0, 40) || el.tagName;
      const top = hit ? `${hit.tagName}.${hit.className}`.slice(0, 60) : "none";
      return { label, ring, visible: Boolean(visible), top };
    });
    if (!record) continue;
    seen.push(record.label);
    if (!record.ring || !record.visible) problems.push(record);
  }
  expect(seen.length, `${screen.name}: Tab moves the focus`).toBeGreaterThan(0);
  expect(problems, `${screen.name}: focus ring and not hidden (A7)`).toEqual([]);
}

test.describe("U12 release sweep on each screen (A1, A7, A11, A18)", () => {
  for (const screen of SCREENS) {
    test(`${screen.name}: axe in both themes, no overflow, one polite live region, focus visible`, async ({ page, request }) => {
      await screen.setup(page, request);
      for (const theme of ["dark", "light"]) {
        await applyTheme(page, theme);
        expect(await axeViolations(page), `${screen.name} (${theme})`).toEqual([]);
        const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
        expect(overflow, `${screen.name} (${theme}) page overflow (A18)`).toBeLessThanOrEqual(0);
      }
      await expect(page.locator('[aria-live="polite"].ui-toast-region'), `${screen.name}: one toast live region (A11)`).toHaveCount(1);
      await focusWalk(page, screen);
    });
  }
});

test.describe("U12 reduced motion on each screen (A15)", () => {
  test.use({ reducedMotion: "reduce" });
  for (const screen of SCREENS) {
    test(`${screen.name}: no element has a running transition or animation`, async ({ page, request }) => {
      await screen.setup(page, request);
      const moving = await page.evaluate(() => {
        const seconds = (value) => value.split(",").map((part) => parseFloat(part) || 0);
        const list = [];
        for (const el of document.querySelectorAll("body *")) {
          const style = getComputedStyle(el);
          const transition = Math.max(...seconds(style.transitionDuration));
          const animation = style.animationName !== "none" ? Math.max(...seconds(style.animationDuration)) : 0;
          if (transition > 0 || animation > 0) list.push(`${el.tagName}.${el.className}`.slice(0, 80));
        }
        return list.slice(0, 10);
      });
      expect(moving, `${screen.name} (A15)`).toEqual([]);
    });
  }
});

test.describe("U12 async results and toasts in the app (A11, A23)", () => {
  test("the sources check result goes to the polite region, stays 8 s, stays on hover, and has a close button", async ({ page, request }) => {
    await scenario(request, "default");
    await page.clock.install({ time: new Date("2026-01-01T00:00:00Z") });
    await openWork(page);
    await page.clock.pauseAt(new Date("2026-01-01T00:10:00Z"));
    await tab(page, "Sources").click();
    await page.getByRole("button", { name: "Check sources" }).click();
    const region = page.locator('[aria-live="polite"].ui-toast-region');
    const toast = region.locator(".ui-toast").filter({ hasText: "All sources are the same as at the last check." });
    await expect(toast).toHaveCount(1);
    // The toast never takes the focus by itself.
    expect(await page.evaluate(() => Boolean(document.activeElement?.closest(".ui-toast")))).toBe(false);

    await page.clock.runFor(7900);
    await expect(toast).toHaveCount(1);
    await toast.hover();
    await page.clock.runFor(5000);
    await expect(toast).toHaveCount(1);
    await page.mouse.move(5, 5);
    await page.clock.runFor(500);
    await expect(toast).toHaveCount(0);

    // A new toast closes with its close button.
    await page.getByRole("button", { name: "Check sources" }).click();
    await expect(toast).toHaveCount(1);
    await toast.getByRole("button", { name: "Close notification" }).click();
    await expect(toast).toHaveCount(0);
  });
});

test.describe("U12 no action needs a drag (A22)", () => {
  test("graph zoom in, zoom out, and fit buttons work, and each graph node gets focus with Tab", async ({ page, request }) => {
    await scenario(request, "default");
    await impactView(page, "Graph", (p) => p.locator(".dc-impact-node").first());
    const zoom = page.locator(".dc-impact-zoom-value");
    const before = await zoom.innerText();
    await page.getByRole("button", { name: "Zoom in" }).click();
    await expect(zoom).not.toHaveText(before);
    await page.getByRole("button", { name: "Zoom out" }).click();
    await page.getByRole("button", { name: "Zoom out" }).click();
    await expect(zoom).not.toHaveText(before);
    await page.getByRole("button", { name: "Fit view" }).click();

    const nodes = page.locator(".dc-impact-node");
    const ids = await nodes.evaluateAll((list) => list.map((node) => node.dataset.nodeId));
    expect(ids.length).toBeGreaterThan(1);
    await nodes.first().focus();
    const reached = [ids[0]];
    for (let index = 1; index < ids.length; index += 1) {
      await page.keyboard.press("Tab");
      reached.push(await page.evaluate(() => document.activeElement?.dataset.nodeId));
    }
    expect(reached).toEqual(ids);
  });

  test("the compare grid scrolls with the keys and with the wheel", async ({ page, request }) => {
    await scenario(request, "large-5000-rows");
    await page.goto("/");
    await page.getByRole("navigation", { name: "Main navigation" }).getByRole("button", { name: "Merge models" }).click();
    const first = page.locator('.dc-cell[data-r="0"][data-c="1"]');
    await expect(first).toBeVisible();
    await first.focus();
    await page.keyboard.press("PageDown");
    const row = await page.evaluate(() => Number(document.activeElement?.dataset.r));
    expect(row).toBeGreaterThan(0);

    const scroll = page.locator(".dc-grid-scroll");
    const before = await scroll.evaluate((el) => el.scrollTop);
    const box = await scroll.boundingBox();
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.wheel(0, 2000);
    await expect.poll(() => scroll.evaluate((el) => el.scrollTop)).toBeGreaterThan(before);
    // The grid scrolls in its own box, not the page, so P4 (80 rows or fewer in the DOM) holds after the scroll.
    const size = await scroll.evaluate((el) => ({ box: el.clientHeight, page: window.innerHeight }));
    expect(size.box).toBeLessThan(size.page);
    expect(await page.locator(".dc-body-row").count()).toBeLessThanOrEqual(80);
  });
});
