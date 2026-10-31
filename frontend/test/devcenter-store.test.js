// Unit tests of the Development Center store and the poll rules, with a fake clock (UI design step U2).
import assert from "node:assert/strict";
import test from "node:test";
import { DevCenterError } from "../src/devcenter/errors.js";
import { createPoller, PROGRESS_POLL_MS, SESSION_POLL_MS } from "../src/devcenter/poller.js";
import { createDevCenterStore, resourceId } from "../src/devcenter/store.js";

const flush = async (times = 5) => {
  for (let index = 0; index < times; index += 1) await new Promise((resolve) => setImmediate(resolve));
};

function fakeClock() {
  let now = 0;
  let nextId = 1;
  const timers = new Map();
  return {
    now: () => now,
    setTimeout(fn, ms) {
      const id = nextId++;
      timers.set(id, { fn, at: now + ms });
      return id;
    },
    clearTimeout(id) {
      timers.delete(id);
    },
    pending: () => timers.size,
    // Move the time forward and run each timer that is due, in time order.
    advance(ms) {
      const end = now + ms;
      for (;;) {
        const due = [...timers.entries()].filter(([, timer]) => timer.at <= end).sort((a, b) => a[1].at - b[1].at)[0];
        if (!due) break;
        timers.delete(due[0]);
        now = due[1].at;
        due[1].fn();
      }
      now = end;
    },
  };
}

// --- Poller ---

function pollerCase({ visible = true, busy = false, active = true, intervalMs = SESSION_POLL_MS } = {}) {
  const clock = fakeClock();
  const flags = { visible, busy, active };
  let ticks = 0;
  const poller = createPoller({
    clock,
    intervalMs,
    isActive: () => flags.active,
    isVisible: () => flags.visible,
    isBusy: () => flags.busy,
    tick: () => {
      ticks += 1;
    },
  });
  return { clock, flags, poller, ticks: () => ticks };
}

test("the poller ticks every 5 s while the window is visible and no call runs", () => {
  const item = pollerCase();
  item.poller.start();
  item.clock.advance(SESSION_POLL_MS - 1);
  assert.equal(item.ticks(), 0);
  item.clock.advance(1);
  assert.equal(item.ticks(), 1);
  item.clock.advance(SESSION_POLL_MS * 3);
  assert.equal(item.ticks(), 4);
  item.poller.stop();
  item.clock.advance(SESSION_POLL_MS * 3);
  assert.equal(item.ticks(), 4);
  assert.equal(item.clock.pending(), 0);
});

test("the poller does not tick while the window is hidden, and ticks again when it shows", () => {
  const item = pollerCase({ visible: false });
  item.poller.start();
  item.clock.advance(SESSION_POLL_MS * 3);
  assert.equal(item.ticks(), 0);
  item.flags.visible = true;
  item.poller.visibilityChanged();
  assert.equal(item.ticks(), 1, "a change to visible counts as a focus");
  item.clock.advance(SESSION_POLL_MS);
  assert.equal(item.ticks(), 2);
});

test("the poller does not tick while a call runs or with no open session", () => {
  const item = pollerCase({ busy: true });
  item.poller.start();
  item.clock.advance(SESSION_POLL_MS * 2);
  assert.equal(item.ticks(), 0);
  item.poller.focus();
  assert.equal(item.ticks(), 0, "focus does not poll while a call runs");
  item.flags.busy = false;
  item.flags.active = false;
  item.clock.advance(SESSION_POLL_MS * 2);
  assert.equal(item.ticks(), 0);
  item.flags.active = true;
  item.clock.advance(SESSION_POLL_MS);
  assert.equal(item.ticks(), 1);
});

test("window focus gives one poll at once and a full interval to the next poll", () => {
  const item = pollerCase();
  item.poller.start();
  item.clock.advance(4000);
  item.poller.focus();
  assert.equal(item.ticks(), 1);
  item.clock.advance(4000);
  assert.equal(item.ticks(), 1, "the timer starts again after the focus poll");
  item.clock.advance(1000);
  assert.equal(item.ticks(), 2);
  item.poller.stop();
  item.poller.focus();
  assert.equal(item.ticks(), 2, "a stopped poller does not poll on focus");
});

test("the poller does not start a second tick while one runs", async () => {
  const clock = fakeClock();
  let release;
  let ticks = 0;
  const poller = createPoller({
    clock,
    intervalMs: 100,
    isVisible: () => true,
    tick: () => {
      ticks += 1;
      return new Promise((resolve) => (release = resolve));
    },
  });
  poller.start();
  clock.advance(100);
  clock.advance(100);
  assert.equal(ticks, 1);
  release();
  await flush();
  clock.advance(100);
  assert.equal(ticks, 2);
  poller.stop();
});

// --- Store ---

function fakeHttp(initial = {}) {
  const data = {
    session: { id: "s1", revision: 5, open_proposals: [] },
    compareRows: { rows: [{ row_key: "r1" }], revision: 5 },
    plan: { status: "valid", revision: 5 },
    log: { entries: [], revision: 5 },
    ...initial,
  };
  const calls = [];
  const gates = [];
  const overrides = {};
  const read = (key) => async (...args) => {
    const options = args.at(-1) ?? {};
    calls.push({ key, args });
    if (overrides[key]?.length) {
      const next = overrides[key].shift();
      if (typeof next === "function") return next(options);
      if (next instanceof Error) throw next;
      return structuredClone(next);
    }
    if (gates.length) await gates.shift();
    const value = data[key];
    if (value instanceof Error) throw value;
    return structuredClone(value ?? { revision: data.session?.revision ?? 0 });
  };
  const http = {
    getSession: read("session"),
    getSessions: read("sessions"),
    getCompareRows: read("compareRows"),
    getRowDiff: read("rowDiff"),
    getDisplayFolders: read("displayFolders"),
    getPlan: read("plan"),
    getImpact: read("impact"),
    getImpactPaths: read("impactPaths"),
    getRemoval: read("removal"),
    getWireframe: read("wireframe"),
    getNamingRules: read("namingRules"),
    getApplyPreview: read("applyPreview"),
    getApplyProgress: read("applyProgress"),
    getApplyLast: read("applyLast"),
    getLog: read("log"),
  };
  return {
    http, data, calls, overrides,
    count: (key) => calls.filter((call) => call.key === key).length,
  };
}

function fakeApi(handler) {
  const calls = [];
  const api = new Proxy({}, {
    get(_target, method) {
      if (typeof method !== "string") return undefined;
      return async (payload) => {
        calls.push({ method, payload });
        return handler(method, payload);
      };
    },
  });
  return { api, calls };
}

async function openStore({ handler = () => ({ revision: 6 }), http = fakeHttp(), visible = true } = {}) {
  const clock = fakeClock();
  const api = fakeApi(handler);
  const flags = { visible };
  const store = createDevCenterStore({ http: http.http, api: api.api, clock, isVisible: () => flags.visible });
  await store.load("session");
  return { store, http, api, clock, flags };
}

test("resourceId does not depend on the order of the params and drops undefined values", () => {
  assert.equal(resourceId("compareRows", { state: "same", limit: 200 }), resourceId("compareRows", { limit: 200, state: "same", q: undefined }));
  assert.notEqual(resourceId("compareRows", { offset: 0 }), resourceId("compareRows", { offset: 200 }));
});

test("GET session gives the first revision, and a JS API call sends it and keeps the reply revision", async () => {
  const { store, api } = await openStore();
  assert.equal(store.getState().revision, 5);
  assert.equal(store.getState().session.id, "s1");
  await store.run("merge_choice_set", { row_key: "r1", choice: "keep" });
  assert.equal(api.calls[0].payload.base_revision, 5);
  assert.equal(store.getState().revision, 6);
});

test("after a call the visible reads of INVALIDATES fetch at once and the other reads become stale", async () => {
  const http = fakeHttp();
  const { store } = await openStore({ http });
  const stopRows = store.watch("compareRows", { state: "different" });
  await store.load("plan");
  await flush();
  assert.equal(http.count("compareRows"), 1);
  http.data.plan.revision = 6;
  http.data.compareRows.revision = 6;
  http.data.session.revision = 6;
  await store.run("merge_choice_set", { row_key: "r1" });
  await flush();
  assert.equal(http.count("compareRows"), 2, "the visible compare rows fetch again");
  assert.equal(http.count("plan"), 1, "the plan is not visible, so it does not fetch");
  const plan = store.getState().resources[resourceId("plan", {})];
  assert.equal(plan.stale, true);
  store.watch("plan");
  await flush();
  assert.equal(http.count("plan"), 2, "a stale read fetches when its view shows");
  stopRows();
});

test("a read reply with a lower revision than the store is dropped and fetched again", async () => {
  const http = fakeHttp();
  const { store } = await openStore({ http });
  store.getState();
  http.overrides.compareRows = [{ rows: [{ row_key: "old" }], revision: 4 }];
  const data = await store.load("compareRows", {});
  assert.equal(http.count("compareRows"), 2);
  assert.deepEqual(data.rows, [{ row_key: "r1" }]);
  const resource = store.getState().resources[resourceId("compareRows", {})];
  assert.deepEqual([resource.revision, resource.current, resource.stale], [5, true, false]);
});

test("a read that stays older after the refetch limit is kept but marked not current", async () => {
  const http = fakeHttp();
  const { store } = await openStore({ http });
  const old = { rows: [], revision: 1 };
  http.overrides.plan = [old, old, old];
  await store.load("plan");
  assert.equal(http.count("plan"), 3);
  const resource = store.getState().resources[resourceId("plan", {})];
  assert.deepEqual([resource.current, resource.stale], [false, true]);
});

test("an old reply of a load that a newer load replaced is dropped", async () => {
  const http = fakeHttp();
  const { store } = await openStore({ http });
  let releaseFirst;
  http.overrides.compareRows = [
    () => new Promise((resolve) => (releaseFirst = () => resolve({ rows: [{ row_key: "first" }], revision: 5 }))),
    { rows: [{ row_key: "second" }], revision: 5 },
  ];
  const first = store.load("compareRows", {});
  const second = store.load("compareRows", {});
  await second;
  releaseFirst();
  assert.equal(await first, null);
  assert.deepEqual(store.getState().resources[resourceId("compareRows", {})].data.rows, [{ row_key: "second" }]);
});

test("a GET session poll with a higher revision makes the visible reads fetch again", async () => {
  const http = fakeHttp();
  const { store, clock } = await openStore({ http });
  store.watch("log", {});
  await flush();
  store.startPoll();
  http.data.session.revision = 9;
  http.data.log.revision = 9;
  clock.advance(SESSION_POLL_MS);
  await flush();
  assert.equal(store.getState().revision, 9);
  assert.equal(http.count("log"), 2);
  store.stopPoll();
});

test("the store polls GET session every 5 s and once on focus, and not while hidden or while a call runs", async () => {
  const http = fakeHttp();
  let release;
  const handler = () => new Promise((resolve) => (release = () => resolve({ revision: 6 })));
  const { store, clock, flags } = await openStore({ http, handler });
  store.startPoll();
  clock.advance(SESSION_POLL_MS);
  await flush();
  assert.equal(http.count("session"), 2);

  flags.visible = false;
  clock.advance(SESSION_POLL_MS * 2);
  await flush();
  assert.equal(http.count("session"), 2, "no poll while the window is hidden");
  flags.visible = true;
  store.focus();
  await flush();
  assert.equal(http.count("session"), 3, "one poll on focus");

  const running = store.run("sources_check", {});
  await flush();
  assert.equal(store.getState().busy, "long");
  clock.advance(SESSION_POLL_MS * 2);
  store.focus();
  await flush();
  assert.equal(http.count("session"), 3, "no poll while a call runs");
  release();
  await running;
  await flush();
  store.stopPoll();
});

test("stale_revision refetches GET session and the visible reads, shows one toast, and drops the queued calls", async () => {
  const http = fakeHttp();
  const { store, api } = await openStore({
    http,
    handler: (method) => (method === "merge_choice_set" ? { error: { code: "stale_revision", message: "Changed.", details: {} } } : { revision: 99 }),
  });
  store.watch("compareRows", {});
  await flush();
  http.data.session.revision = 8;
  http.data.compareRows.revision = 8;
  const results = await Promise.allSettled([
    store.run("merge_choice_set", { row_key: "r1" }),
    store.run("row_confirm", { row_keys: ["r1"] }),
    store.run("proposal_accept", { proposal_id: "p1" }),
  ]);
  await flush();
  assert.deepEqual(results.map((item) => item.reason?.code), ["stale_revision", "dropped", "dropped"]);
  assert.equal(api.calls.length, 1, "no automatic retry, and the queued calls never run");
  assert.equal(store.getState().revision, 8);
  assert.equal(http.count("session"), 2);
  assert.equal(http.count("compareRows"), 2);
  const toasts = store.getState().notices.filter((notice) => notice.kind === "toast");
  assert.deepEqual(toasts.map((notice) => notice.key), ["shared.stale"]);
  assert.equal(store.getState().busy, "idle", "the failed control does not keep a loading state");
  store.dismissNotice(toasts[0].id);
  assert.equal(store.getState().notices.length, 0);
});

test("session_not_open closes the session and shows the list banner", async () => {
  const { store } = await openStore({ handler: () => ({ error: { code: "session_not_open", message: "No session.", details: {} } }) });
  store.watch("plan");
  await flush();
  await assert.rejects(store.run("merge_choice_set", {}), (error) => error.code === "session_not_open");
  const state = store.getState();
  assert.equal(state.session, null);
  assert.equal(state.revision, null);
  assert.deepEqual(state.notices.map((notice) => [notice.kind, notice.place, notice.key]), [["banner", "list", "shared.session_not_open"]]);
  assert.equal(state.resources[resourceId("plan", {})], undefined);
});

test("no session at start gives no banner", async () => {
  const http = fakeHttp({ session: new DevCenterError({ code: "session_not_open", source: "http", status: 409 }) });
  const store = createDevCenterStore({ http: http.http, api: fakeApi(() => ({})).api, clock: fakeClock(), isVisible: () => true });
  await store.load("session");
  assert.equal(store.getState().session, null);
  assert.deepEqual(store.getState().notices, []);
});

test("source_changed opens Compare with the marks filter, but an accept shows it inline", async () => {
  const handler = () => ({ error: { code: "source_changed", message: "A source changed.", details: {} } });
  const { store } = await openStore({ handler });
  await assert.rejects(store.run("merge_choice_set", {}));
  assert.deepEqual(store.getState().notices.map((notice) => [notice.kind, notice.tab, notice.filters.marks]), [["navigate", "compare", true]]);
  const second = await openStore({ handler });
  await assert.rejects(second.store.run("proposal_accept", {}), (error) => error.code === "source_changed");
  assert.deepEqual(second.store.getState().notices, []);
});

test("an inline error goes back to the control with no notice", async () => {
  const { store } = await openStore({ handler: () => ({ error: { code: "user_choice_exists", message: "Set.", details: {} } }) });
  await assert.rejects(store.run("proposal_accept", {}), (error) => error.code === "user_choice_exists");
  assert.deepEqual(store.getState().notices, []);
});

test("a failed read keeps its old data and is marked not current", async () => {
  const http = fakeHttp();
  const { store } = await openStore({ http });
  await store.load("plan");
  http.overrides.plan = [new DevCenterError({ code: "unknown", message: "Boom", source: "http", status: 500 })];
  await store.load("plan");
  const resource = store.getState().resources[resourceId("plan", {})];
  assert.deepEqual([resource.status, resource.error.code, resource.current, resource.data.status], ["error", "unknown", false, "valid"]);
});

test("a view that closes stops its read", async () => {
  const http = fakeHttp();
  const { store } = await openStore({ http });
  let signal;
  http.overrides.compareRows = [(options) => {
    signal = options.signal;
    return new Promise((_resolve, reject) => {
      options.signal.addEventListener("abort", () => {
        const error = new Error("aborted");
        error.name = "AbortError";
        reject(error);
      });
    });
  }];
  const stop = store.watch("compareRows", { q: "net" });
  await flush();
  stop();
  await flush();
  assert.equal(signal.aborted, true);
  assert.equal(store.getState().resources[resourceId("compareRows", { q: "net" })].status, "idle");
});

test("session_open sets the session, and session_close keeps only the session list", async () => {
  const http = fakeHttp();
  const opened = { id: "s2", revision: 20 };
  const { store } = await openStore({
    http,
    handler: (method) => (method === "session_open" ? { revision: 20, session: opened } : { revision: 21 }),
  });
  await store.load("sessions");
  await store.run("session_open", { session_id: "s2" });
  assert.equal(store.getState().session.id, "s2");
  assert.equal(store.getState().revision, 20);
  await store.run("session_close", {});
  await flush();
  const state = store.getState();
  assert.equal(state.session, null);
  assert.deepEqual(Object.values(state.resources).map((resource) => resource.key), ["sessions"]);
});

test("the Apply progress poll runs every 500 ms only while apply runs", async () => {
  const http = fakeHttp({ applyProgress: { apply_id: "a1", step: "guard", step_index: 8, step_count: 11, state: "running", revision: 5 } });
  let release;
  const { store, clock } = await openStore({
    http,
    handler: (method) => (method === "apply" ? new Promise((resolve) => (release = () => resolve({ revision: 6 }))) : { revision: 6 }),
  });
  await store.run("merge_choice_set", {});
  clock.advance(PROGRESS_POLL_MS * 4);
  await flush();
  assert.equal(http.count("applyProgress"), 0, "no progress poll outside apply");

  const running = store.run("apply", { plan_hash: "h1" });
  await flush();
  assert.equal(store.getState().running, "apply");
  clock.advance(PROGRESS_POLL_MS);
  await flush();
  clock.advance(PROGRESS_POLL_MS);
  await flush();
  assert.equal(http.count("applyProgress"), 2);
  assert.equal(store.getState().progress.step_index, 8);
  assert.equal(store.getState().progress.available, true);
  release();
  await running;
  await flush();
  clock.advance(PROGRESS_POLL_MS * 4);
  await flush();
  assert.equal(http.count("applyProgress"), 2, "the progress poll stops after apply");
  assert.equal(store.getState().progress, null);
});

test("a missing progress endpoint gives progress.available false", async () => {
  const http = fakeHttp({ applyProgress: new DevCenterError({ code: "not_found", source: "http", status: 404 }) });
  let release;
  const { store, clock } = await openStore({ http, handler: () => new Promise((resolve) => (release = () => resolve({ revision: 6 }))) });
  const running = store.run("undo_apply", {});
  await flush();
  clock.advance(PROGRESS_POLL_MS);
  await flush();
  assert.equal(store.getState().progress.available, false);
  release();
  await running;
});
