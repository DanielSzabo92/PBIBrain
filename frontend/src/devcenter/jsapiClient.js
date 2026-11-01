// Client for the pywebview JS API of the Development Center (technical design sections 14.2 and 14.4).
// All calls go into one FIFO queue. When a call starts, the client adds base_revision from getRevision().
// A success reply gives setRevision(reply.revision). A stale_revision error drops the queued calls.
import METHOD_LIST from "./jsapi-methods.json" with { type: "json" };
import { DevCenterError, isErrorShape, isOldErrorShape, normalizeError } from "./errors.js";

export const JSAPI_METHODS = Object.freeze(METHOD_LIST.map((entry) => Object.freeze({ ...entry })));

const KINDS = new Map(JSAPI_METHODS.map((entry) => [entry.name, entry.kind]));

export function methodKind(method) {
  return KINDS.get(method) ?? null;
}

export function isLongMethod(method) {
  return KINDS.get(method) === "long";
}

// merge_choice_set gives mergeChoiceSet.
export function camelName(method) {
  return method.replace(/_([a-z])/g, (_match, letter) => letter.toUpperCase());
}

function resolveApi(api) {
  const value = typeof api === "function" ? api() : api;
  return value ?? null;
}

export function createDevCenterJsApi({ api, getRevision = () => null, setRevision = () => {} } = {}) {
  const queue = [];
  const listeners = new Set();
  let running = null;

  function notify() {
    for (const listener of [...listeners]) listener();
  }

  function snapshot(entry) {
    return { id: entry.id, method: entry.method, kind: entry.kind };
  }

  let nextId = 1;

  async function execute(entry) {
    const target = resolveApi(api);
    const fn = target?.[entry.method];
    if (typeof fn !== "function") {
      throw new DevCenterError({
        code: "unknown",
        message: `The desktop API has no method ${entry.method}. Start PBIBrain from the desktop app.`,
        details: { method: entry.method },
        source: "jsapi",
      });
    }
    let reply;
    try {
      reply = await fn.call(target, { ...entry.payload, base_revision: getRevision() });
    } catch (error) {
      throw normalizeError(error, { source: "jsapi" });
    }
    if (isErrorShape(reply) || isOldErrorShape(reply)) throw normalizeError(reply, { source: "jsapi" });
    if (reply === null || typeof reply !== "object") {
      throw new DevCenterError({ code: "unknown", message: `The reply of ${entry.method} is not an object.`, source: "jsapi" });
    }
    if (Number.isInteger(reply.revision)) setRevision(reply.revision);
    return reply;
  }

  function dropQueued(cause) {
    const dropped = queue.splice(0, queue.length);
    for (const entry of dropped) {
      entry.reject(
        new DevCenterError({
          code: "dropped",
          message: `The call ${entry.method} did not run, because ${cause.method} failed with ${cause.code}.`,
          details: { cause: cause.code, after: cause.method },
          source: "jsapi",
        }),
      );
    }
    return dropped.length;
  }

  async function pump() {
    if (running || queue.length === 0) return;
    const entry = queue.shift();
    running = entry;
    notify();
    try {
      entry.resolve(await execute(entry));
    } catch (error) {
      const normalized = normalizeError(error, { source: "jsapi" });
      if (normalized.code === "stale_revision") {
        normalized.details = { ...normalized.details, dropped: dropQueued({ method: entry.method, code: normalized.code }) };
      }
      entry.reject(normalized);
    } finally {
      running = null;
      notify();
      pump();
    }
  }

  function call(method, payload = {}) {
    const kind = methodKind(method);
    if (!kind) {
      return Promise.reject(
        new DevCenterError({ code: "unknown", message: `jsapi-methods.json has no method ${method}.`, details: { method }, source: "jsapi" }),
      );
    }
    return new Promise((resolve, reject) => {
      queue.push({ id: nextId++, method, kind, payload: payload ?? {}, resolve, reject });
      notify();
      pump();
    });
  }

  // The calls that run and wait. running is null when no call runs.
  function pending() {
    return { running: running ? snapshot(running) : null, queued: queue.map(snapshot) };
  }

  // "long" while a long call runs or waits, "short" while another call runs or waits, else "idle".
  function busy() {
    const all = running ? [running, ...queue] : queue;
    if (all.length === 0) return "idle";
    return all.some((entry) => entry.kind === "long") ? "long" : "short";
  }

  function subscribe(listener) {
    listeners.add(listener);
    return () => listeners.delete(listener);
  }

  const client = { call, pending, busy, subscribe };
  for (const { name } of JSAPI_METHODS) client[camelName(name)] = (payload) => call(name, payload);
  return client;
}
