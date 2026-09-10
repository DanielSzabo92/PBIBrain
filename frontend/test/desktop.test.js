import assert from "node:assert/strict";
import test from "node:test";
import { desktopRequest, subscribeToDesktopBridge } from "../src/desktop.js";

test("desktop bridge is available immediately when injected", () => {
  const events = new Map();
  const api = { get_session() {} };
  const scope = {
    pywebview: { api },
    addEventListener(name, callback) { events.set(name, callback); },
    removeEventListener(name) { events.delete(name); },
  };
  let received = null;
  const stop = subscribeToDesktopBridge((value) => { received = value; }, scope);
  assert.equal(received, api);
  stop();
  assert.equal(events.size, 0);
});

test("desktop bridge waits for pywebviewready without affecting browser mode", () => {
  const events = new Map();
  const scope = {
    addEventListener(name, callback) { events.set(name, callback); },
    removeEventListener(name) { events.delete(name); },
  };
  let received = null;
  subscribeToDesktopBridge((value) => { received = value; }, scope);
  assert.equal(received, null);
  scope.pywebview = { api: { get_session() {} } };
  events.get("pywebviewready")();
  assert.equal(typeof received.get_session, "function");
});

test("desktop requests return bridge failures as useful errors", async () => {
  await assert.rejects(desktopRequest({ choose_folder: async () => ({ ok: false, error: "Picker cancelled" }) }, "choose_folder"), /Picker cancelled/);
  const result = await desktopRequest({ get_session: async () => ({ ok: true, project: null, api_url: null }) }, "get_session");
  assert.equal(result.project, null);
});

test("desktop requests carry selected source files to the native bridge", async () => {
  let received = null;
  await desktopRequest({ add_sources: async (sources) => { received = sources; return { ok: true, sources }; } }, "add_sources", ["C:\\Finance\\Finance.pbip", "C:\\Finance\\model.json"]);
  assert.deepEqual(received, ["C:\\Finance\\Finance.pbip", "C:\\Finance\\model.json"]);
});
