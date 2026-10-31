import { test, expect } from "@playwright/test";

// Smoke test of the Development Center test harness: the fake server, the shim, and the test controls.
const FAKE = "http://127.0.0.1:8766";
test.use({ baseURL: FAKE });

test.beforeEach(async ({ request }) => {
  const loaded = await request.post("/__test__/scenario", { data: { name: "default" } });
  expect(loaded.ok()).toBe(true);
});

test("the fake server answers on port 8766 and loads each scenario", async ({ request }) => {
  const health = await (await request.get("/__test__/health")).json();
  expect(health.ok).toBe(true);
  for (const name of health.scenarios) {
    const loaded = await (await request.post("/__test__/scenario", { data: { name } })).json();
    expect(loaded.scenario).toBe(name);
  }
});

test("the page loads the shim before the app, and the shim forwards calls to the fake server", async ({ page, request }) => {
  await page.goto("/");
  const html = await (await request.get("/")).text();
  expect(html.indexOf("/__test__/pywebview-shim.js")).toBeGreaterThan(-1);
  expect(html.indexOf("/__test__/pywebview-shim.js")).toBeLessThan(html.indexOf('type="module"'));

  const result = await page.evaluate(async () => {
    const api = window.pywebview.api;
    const session = await (await fetch("/api/devcenter/session")).json();
    const stale = await api.sources_check({ base_revision: session.revision - 1 });
    const passed = await api.sources_check({ base_revision: session.revision });
    const desktop = await api.get_session();
    return { desktopFlag: window.__PBIBRAIN_DESKTOP__, revision: session.revision, stale, passed, desktop };
  });
  expect(result.desktopFlag).toBe(true);
  expect(result.stale.error.code).toBe("stale_revision");
  expect(result.passed.revision).toBe(result.revision + 1);
  expect(result.desktop.ok).toBe(true);
});

test("fault, delay, and agent-proposal change the next reply", async ({ page, request }) => {
  await page.goto("/");
  await request.post("/__test__/fault", { data: { method: "sources_check", code: "action_not_allowed", message: "Injected." } });
  await request.post("/__test__/delay", { data: { method: "compare_mode_set", ms: 300, once: true } });
  const result = await page.evaluate(async () => {
    const api = window.pywebview.api;
    const revision = async () => (await (await fetch("/api/devcenter/session")).json()).revision;
    const faulted = await api.sources_check({ base_revision: await revision() });
    const started = performance.now();
    const slow = await api.compare_mode_set({ base_revision: await revision(), mode: "names" });
    const elapsed = performance.now() - started;
    return { faulted, slow, elapsed };
  });
  expect(result.faulted.error).toEqual({ code: "action_not_allowed", message: "Injected.", details: {} });
  expect(result.slow.revision).toEqual(expect.any(Number));
  expect(result.elapsed).toBeGreaterThanOrEqual(300);

  const before = await (await request.get("/api/devcenter/session")).json();
  const added = await (await request.post("/__test__/agent-proposal", { data: { target_id: "row-date", target_name: "Date" } })).json();
  expect(added.revision).toBe(before.revision + 1);
  const after = await (await request.get("/api/devcenter/session")).json();
  expect(after.open_proposals.map((item) => item.target_id)).toContain("row-date");

  const network = await request.post("/__test__/fault", { data: { method: "sources_check", code: "network" } });
  expect(network.ok()).toBe(true);
  const thrown = await page.evaluate(async () => {
    try {
      await window.pywebview.api.sources_check({ base_revision: 0 });
      return null;
    } catch (error) {
      return error.reply?.error?.code || error.message;
    }
  });
  expect(thrown).toBe("network");
});
