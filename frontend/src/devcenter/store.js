// Cache and session state of the Development Center (UI design section 10).
// Plain JS for useSyncExternalStore: no state library and no React import.
//
// Revision rules:
// - Each JS API call sends the last known revision. A success reply sets the new revision.
// - A read reply with a lower revision than the store is dropped and fetched again.
// - A GET session reply with a higher revision makes all other reads stale.
// - stale_revision: no automatic retry. The store fetches GET session and the visible reads,
//   then shows one shared.stale toast. The client drops the queued calls with no second toast.
import { errorReaction, normalizeError } from "./errors.js";
import { RESOURCE_READS } from "./httpClient.js";
import { invalidatedBy, RESOURCE_KEYS } from "./invalidation.js";
import { createDevCenterJsApi } from "./jsapiClient.js";
import { createPoller, documentVisible, PROGRESS_METHODS, PROGRESS_POLL_MS, SESSION_POLL_MS, systemClock } from "./poller.js";

const MAX_REFETCH = 2;

const SESSION_METHODS = new Set(["session_create", "session_open"]);
const OTHER_KEYS = RESOURCE_KEYS.filter((key) => key !== "session");

function stable(value) {
  if (Array.isArray(value)) return value.map(stable);
  if (value && typeof value === "object") {
    const result = {};
    for (const name of Object.keys(value).sort()) {
      if (value[name] !== undefined) result[name] = stable(value[name]);
    }
    return result;
  }
  return value;
}

// One ID for each read and its params. The order of the params does not change the ID.
export function resourceId(key, params = {}) {
  return `${key}:${JSON.stringify(stable(params ?? {}))}`;
}

function emptyResource(id, key, params) {
  return { id, key, params, data: null, revision: null, status: "idle", error: null, stale: false, current: false };
}

export function createDevCenterStore({
  http,
  api,
  createJsApi = createDevCenterJsApi,
  clock = systemClock,
  isVisible = documentVisible,
  createAbortController = () => new AbortController(),
} = {}) {
  if (!http) throw new TypeError("createDevCenterStore needs an http client.");

  let state = Object.freeze({
    revision: null,
    session: null,
    busy: "idle",
    running: null,
    queued: 0,
    progress: null,
    resources: Object.freeze({}),
    notices: Object.freeze([]),
  });
  const listeners = new Set();
  const watchers = new Map();
  const controllers = new Map();
  const tokens = new Map();
  let sequence = 0;
  let noticeId = 0;

  function setState(patch) {
    state = Object.freeze({ ...state, ...patch });
    for (const listener of [...listeners]) listener();
  }

  function setResource(id, key, params, patch) {
    const previous = state.resources[id] ?? emptyResource(id, key, params);
    setState({ resources: Object.freeze({ ...state.resources, [id]: Object.freeze({ ...previous, ...patch }) }) });
  }

  function pushNotice(notice) {
    const item = Object.freeze({ id: ++noticeId, ...notice });
    setState({ notices: Object.freeze([...state.notices, item]) });
    return item;
  }

  function isWatched(id, key) {
    return key === "session" ? state.session !== null || (watchers.get(id) ?? 0) > 0 : (watchers.get(id) ?? 0) > 0;
  }

  function closeSession({ banner }) {
    const hadSession = state.session !== null;
    const kept = {};
    for (const [id, resource] of Object.entries(state.resources)) {
      if (resource.key === "sessions") kept[id] = resource;
    }
    for (const [id, controller] of controllers) {
      if (!id.startsWith("sessions:")) controller.abort();
    }
    setState({ session: null, revision: null, resources: Object.freeze(kept) });
    if (banner && hadSession) pushNotice({ kind: "banner", place: "list", code: "session_not_open", key: "shared.session_not_open" });
  }

  function acceptSession(data) {
    const previous = state.revision;
    const revision = Number.isInteger(data?.revision) ? data.revision : previous;
    setState({ session: data, revision });
    if (Number.isInteger(previous) && Number.isInteger(revision) && revision > previous) return markStale(OTHER_KEYS);
    return Promise.resolve([]);
  }

  async function load(key, params = {}, { attempt = 0 } = {}) {
    const reader = RESOURCE_READS[key];
    if (!reader) throw new Error(`The store has no read for the resource key ${key}.`);
    const id = resourceId(key, params);
    controllers.get(id)?.abort();
    const controller = createAbortController();
    controllers.set(id, controller);
    const token = ++sequence;
    tokens.set(id, token);
    setResource(id, key, params, { status: "loading" });

    let data;
    try {
      data = await reader(http, params, { signal: controller.signal });
    } catch (raw) {
      if (tokens.get(id) !== token) return null;
      controllers.delete(id);
      const error = normalizeError(raw, { source: "http" });
      const previous = state.resources[id];
      if (error.code === "aborted") {
        if (previous) setResource(id, key, params, { status: previous.data === null ? "idle" : "ready" });
        return null;
      }
      if (error.code === "session_not_open") {
        closeSession({ banner: true });
        if (key === "session") return null;
      }
      // The region keeps its old data and marks it not current.
      setResource(id, key, params, { status: "error", error, current: false });
      return null;
    }
    if (tokens.get(id) !== token) return null;
    controllers.delete(id);

    const revision = Number.isInteger(data?.revision) ? data.revision : null;
    const older = revision !== null && Number.isInteger(state.revision) && revision < state.revision;
    if (older && attempt < MAX_REFETCH) return load(key, params, { attempt: attempt + 1 });
    setResource(id, key, params, { data, revision, status: "ready", error: null, stale: older, current: !older });
    // A newer session revision fetches the visible reads. The session read waits for them.
    if (key === "session" && !older) await acceptSession(data);
    return data;
  }

  // Mark the reads of these keys stale. A visible read fetches at once.
  function markStale(keys) {
    const wanted = new Set(keys);
    const reload = [];
    for (const resource of Object.values(state.resources)) {
      if (!wanted.has(resource.key)) continue;
      setResource(resource.id, resource.key, resource.params, { stale: true });
      if (isWatched(resource.id, resource.key)) reload.push(resource);
    }
    if (wanted.has("session") && state.session !== null && !reload.some((item) => item.key === "session")) {
      reload.push({ key: "session", params: {} });
    }
    return Promise.all(reload.map((resource) => load(resource.key, resource.params)));
  }

  function refreshVisible() {
    const reload = Object.values(state.resources).filter((resource) => isWatched(resource.id, resource.key));
    return Promise.all(reload.map((resource) => load(resource.key, resource.params)));
  }

  // A view shows a read: load it when it is not in the cache or stale. The return value stops the watch.
  function watch(key, params = {}) {
    const id = resourceId(key, params);
    watchers.set(id, (watchers.get(id) ?? 0) + 1);
    const resource = state.resources[id];
    if (!resource || resource.stale || resource.status === "idle") load(key, params);
    let active = true;
    return () => {
      if (!active) return;
      active = false;
      const count = (watchers.get(id) ?? 1) - 1;
      if (count > 0) {
        watchers.set(id, count);
        return;
      }
      watchers.delete(id);
      // The view closed: stop its read.
      controllers.get(id)?.abort();
    };
  }

  const jsapi = createJsApi({
    api,
    getRevision: () => state.revision,
    setRevision: (revision) => setState({ revision }),
  });

  const sessionPoller = createPoller({
    clock,
    intervalMs: SESSION_POLL_MS,
    isActive: () => state.session !== null,
    isVisible,
    isBusy: () => state.busy !== "idle",
    tick: () => load("session"),
  });

  const progressPoller = createPoller({
    clock,
    intervalMs: PROGRESS_POLL_MS,
    isActive: () => PROGRESS_METHODS.includes(state.running),
    isVisible: () => true,
    tick: async () => {
      try {
        const progress = await http.getApplyProgress();
        if (PROGRESS_METHODS.includes(state.running)) setState({ progress: Object.freeze({ ...progress, available: true }) });
      } catch (raw) {
        if (PROGRESS_METHODS.includes(state.running)) {
          setState({ progress: Object.freeze({ available: false, error: normalizeError(raw, { source: "http" }) }) });
        }
      }
    },
  });

  jsapi.subscribe(() => {
    const { running, queued } = jsapi.pending();
    const method = running?.method ?? null;
    const wasProgress = PROGRESS_METHODS.includes(state.running);
    const isProgress = PROGRESS_METHODS.includes(method);
    setState({ busy: jsapi.busy(), running: method, queued: queued.length, ...(isProgress && !wasProgress ? { progress: null } : {}) });
    if (isProgress && !wasProgress) progressPoller.start();
    if (!isProgress && wasProgress) {
      progressPoller.stop();
      setState({ progress: null });
    }
  });

  async function onError(method, error) {
    if (error.code === "stale_revision") {
      const before = state.revision;
      await load("session");
      // A newer session revision already made the other reads stale.
      if (state.revision === before) await markStale(OTHER_KEYS);
      pushNotice({ kind: "toast", code: "stale_revision", key: "shared.stale" });
      return;
    }
    if (error.code === "session_not_open") {
      closeSession({ banner: true });
      return;
    }
    if (errorReaction(error, method) === "compare_marks") {
      pushNotice({ kind: "navigate", code: "source_changed", tab: "compare", filters: Object.freeze({ marks: true }) });
    }
    // Inline, region, and agent errors go back to the control that made the call.
  }

  function afterReply(method, reply) {
    if (method === "session_close") {
      closeSession({ banner: false });
      return markStale(["sessions"]);
    }
    if (SESSION_METHODS.has(method)) {
      // The S2 reply has revision, session_id, read_only, migrated, and mark_count, but no session.
      // Always load GET session. A reply.session (an old host reply) only shows the session sooner.
      if (reply.session) acceptSession(reply.session);
      return Promise.all([load("session"), markStale(OTHER_KEYS)]);
    }
    return markStale(invalidatedBy(method));
  }

  // Run one JS API call. The promise rejects with DevCenterError; the store reacts first.
  async function run(method, payload = {}) {
    let reply;
    try {
      reply = await jsapi.call(method, payload);
    } catch (raw) {
      const error = normalizeError(raw, { source: "jsapi" });
      await onError(method, error);
      throw error;
    }
    afterReply(method, reply);
    return reply;
  }

  return {
    jsapi,
    getState: () => state,
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    load,
    watch,
    markStale,
    refreshVisible,
    run,
    dismissNotice(id) {
      setState({ notices: Object.freeze(state.notices.filter((notice) => notice.id !== id)) });
    },
    startPoll: () => sessionPoller.start(),
    stopPoll() {
      sessionPoller.stop();
      progressPoller.stop();
    },
    focus: () => sessionPoller.focus(),
    visibilityChanged: () => sessionPoller.visibilityChanged(),
  };
}
