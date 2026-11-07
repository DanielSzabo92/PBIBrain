// Unit tests of the Development Center JS API client and the invalidation table (UI design step U2).
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { DevCenterError } from "../src/devcenter/errors.js";
import { INVALIDATES, invalidatedBy, RESOURCE_KEYS } from "../src/devcenter/invalidation.js";
import { camelName, createDevCenterJsApi, isLongMethod, JSAPI_METHODS } from "../src/devcenter/jsapiClient.js";

const LONG = [
  "session_create", "session_open", "sources_check", "apply", "format_only_apply", "undo_apply",
  "pull_to_local", "cloud_connect", "cloud_sign_in", "merge_choice_bulk_set", "proposal_accept_all", "target_edit_apply",
];

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((ok, fail) => {
    resolve = ok;
    reject = fail;
  });
  return { promise, resolve, reject };
}

const flush = () => new Promise((resolve) => setImmediate(resolve));

// A fake pywebview API. Each call waits until the test settles it.
function fakeApi() {
  const calls = [];
  const api = new Proxy(
    {},
    {
      get(_target, method) {
        if (typeof method !== "string") return undefined;
        return (payload) => {
          const step = deferred();
          calls.push({ method, payload, ...step });
          return step.promise;
        };
      },
    },
  );
  return { api, calls };
}

function client(api, start = 7) {
  let revision = start;
  const jsapi = createDevCenterJsApi({ api, getRevision: () => revision, setRevision: (value) => (revision = value) });
  return { jsapi, revision: () => revision };
}

test("jsapi-methods.json has a name and a short or long kind for each method, with no duplicates", async () => {
  const raw = JSON.parse(await readFile(new URL("../src/devcenter/jsapi-methods.json", import.meta.url), "utf8"));
  assert.deepEqual(raw, JSAPI_METHODS);
  assert.equal(new Set(raw.map((entry) => entry.name)).size, raw.length);
  for (const entry of raw) {
    assert.deepEqual(Object.keys(entry).sort(), ["kind", "name"]);
    assert.ok(["short", "long"].includes(entry.kind), entry.name);
  }
  assert.deepEqual(raw.filter((entry) => entry.kind === "long").map((entry) => entry.name).sort(), [...LONG].sort());
  assert.ok(isLongMethod("apply"));
  assert.ok(!isLongMethod("merge_choice_set"));
});

test("each method has an invalidation entry with known resource keys only", () => {
  const names = JSAPI_METHODS.map((entry) => entry.name);
  assert.deepEqual(Object.keys(INVALIDATES).sort(), [...names].sort());
  for (const name of names) {
    const keys = invalidatedBy(name);
    assert.ok(Array.isArray(keys), name);
    for (const key of keys) assert.ok(RESOURCE_KEYS.includes(key), `${name}: ${key}`);
    assert.equal(new Set(keys).size, keys.length, `${name} has a key two times`);
  }
  assert.throws(() => invalidatedBy("no_such_method"), /no entry/);
});

test("the invalidation entries follow the refresh rules of section 10", () => {
  for (const method of ["sources_check", "session_open", "apply", "undo_apply"]) {
    assert.deepEqual([...invalidatedBy(method)].sort(), [...RESOURCE_KEYS].sort(), method);
  }
  for (const key of ["session", "compareRows", "plan", "impact", "applyPreview", "log"]) {
    assert.ok(invalidatedBy("merge_choice_set").includes(key), key);
  }
  assert.deepEqual(invalidatedBy("cloud_items_list"), []);
  assert.deepEqual(invalidatedBy("cloud_sign_in"), []);
});

test("the client has one camelCase function for each method", () => {
  const { jsapi } = client(fakeApi().api);
  assert.equal(camelName("merge_choice_bulk_set"), "mergeChoiceBulkSet");
  for (const { name } of JSAPI_METHODS) assert.equal(typeof jsapi[camelName(name)], "function", name);
});

test("calls run one at a time in FIFO order, and each call sends the revision of the reply before it", async () => {
  const fake = fakeApi();
  const { jsapi, revision } = client(fake.api, 7);
  const first = jsapi.mergeChoiceSet({ row_key: "r1", choice: "keep" });
  const second = jsapi.rowConfirm({ row_keys: ["r2"] });
  const third = jsapi.proposalReject({ proposal_id: "p1" });
  await flush();
  assert.equal(fake.calls.length, 1, "the second call waits for the first");
  assert.deepEqual(fake.calls[0].payload, { row_key: "r1", choice: "keep", base_revision: 7 });
  assert.deepEqual(jsapi.pending().queued.map((entry) => entry.method), ["row_confirm", "proposal_reject"]);

  fake.calls[0].resolve({ revision: 8 });
  assert.deepEqual(await first, { revision: 8 });
  await flush();
  assert.equal(fake.calls.length, 2);
  assert.equal(fake.calls[1].method, "row_confirm");
  assert.equal(fake.calls[1].payload.base_revision, 8);

  fake.calls[1].resolve({ revision: 9 });
  await second;
  await flush();
  assert.equal(fake.calls[2].payload.base_revision, 9);
  fake.calls[2].resolve({ revision: 10 });
  await third;
  assert.equal(revision(), 10);
  assert.deepEqual(jsapi.pending(), { running: null, queued: [] });
});

test("stale_revision rejects the call and drops the queued calls", async () => {
  const fake = fakeApi();
  const { jsapi, revision } = client(fake.api, 3);
  const first = jsapi.call("merge_choice_set", { row_key: "r1" });
  const second = jsapi.call("row_confirm", { row_keys: ["r1"] });
  const third = jsapi.call("apply", {});
  await flush();
  fake.calls[0].resolve({ error: { code: "stale_revision", message: "Changed.", details: { revision: 5 } } });
  await assert.rejects(first, (error) => error.code === "stale_revision" && error.details.dropped === 2);
  await assert.rejects(second, (error) => error.code === "dropped" && error.details.cause === "stale_revision");
  await assert.rejects(third, (error) => error.code === "dropped");
  await flush();
  assert.equal(fake.calls.length, 1, "the dropped calls never run");
  assert.equal(revision(), 3);
  assert.equal(jsapi.busy(), "idle");
});

test("another error rejects only its own call, and the queue goes on", async () => {
  const fake = fakeApi();
  const { jsapi } = client(fake.api, 1);
  const first = jsapi.call("merge_choice_set", {});
  const second = jsapi.call("row_confirm", {});
  await flush();
  fake.calls[0].resolve({ error: { code: "invalid_payload", message: "Bad.", details: { field: "choice" } } });
  await assert.rejects(first, (error) => error instanceof DevCenterError && error.code === "invalid_payload");
  await flush();
  fake.calls[1].resolve({ revision: 2 });
  assert.deepEqual(await second, { revision: 2 });
});

test("the old reply shape, a thrown error, and a shim error are normalized", async () => {
  const fake = fakeApi();
  const { jsapi } = client(fake.api);
  const old = jsapi.call("session_close", {});
  await flush();
  fake.calls[0].resolve({ ok: false, error: "No project." });
  await assert.rejects(old, (error) => error.code === "unknown" && error.message === "No project.");

  const thrown = jsapi.call("session_close", {});
  await flush();
  fake.calls[1].reject(new Error("bridge closed"));
  await assert.rejects(thrown, (error) => error.code === "unknown" && error.message === "bridge closed");

  const shim = jsapi.call("session_close", {});
  await flush();
  const failure = new Error("HTTP 409");
  failure.reply = { error: { code: "session_not_open", message: "No session is open.", details: {} } };
  fake.calls[2].reject(failure);
  await assert.rejects(shim, (error) => error.code === "session_not_open");
});

test("a missing API or an unknown method rejects with a clear error", async () => {
  const { jsapi } = client(() => undefined);
  await assert.rejects(jsapi.call("apply", {}), (error) => error.code === "unknown" && /has no method apply/.test(error.message));
  const known = client(fakeApi().api).jsapi;
  await assert.rejects(known.call("delete_everything", {}), (error) => /jsapi-methods.json has no method/.test(error.message));
});

test("busy is long while a long call runs or waits, short for short calls, and listeners see each change", async () => {
  const fake = fakeApi();
  const { jsapi } = client(fake.api);
  const seen = [];
  const stop = jsapi.subscribe(() => seen.push(jsapi.busy()));
  assert.equal(jsapi.busy(), "idle");
  const short = jsapi.call("merge_choice_set", {});
  assert.equal(jsapi.busy(), "short");
  const long = jsapi.call("sources_check", {});
  assert.equal(jsapi.busy(), "long", "a queued long call makes the client busy long");
  await flush();
  fake.calls[0].resolve({ revision: 2 });
  await short;
  await flush();
  assert.equal(jsapi.pending().running.method, "sources_check");
  assert.equal(jsapi.busy(), "long");
  fake.calls[1].resolve({ revision: 3 });
  await long;
  await flush();
  assert.equal(jsapi.busy(), "idle");
  stop();
  assert.ok(seen.includes("short") && seen.includes("long") && seen.at(-1) === "idle");
});
