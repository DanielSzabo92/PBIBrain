// The React seam of the Development Center data layer (UI design section 10).
// This is the only module of the data layer that imports React.
import { createContext, createElement, useCallback, useContext, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { normalizeError, errorReaction } from "./errors.js";
import { resourceId } from "./store.js";

const DevCenterContext = createContext(null);

// One store for the open session. The provider starts the session poll and the focus poll.
export function DevCenterProvider({ store, children }) {
  useEffect(() => {
    store.startPoll();
    const win = globalThis.window;
    const doc = globalThis.document;
    const onFocus = () => store.focus();
    const onVisibility = () => store.visibilityChanged();
    win?.addEventListener("focus", onFocus);
    doc?.addEventListener("visibilitychange", onVisibility);
    return () => {
      win?.removeEventListener("focus", onFocus);
      doc?.removeEventListener("visibilitychange", onVisibility);
      store.stopPoll();
    };
  }, [store]);
  return createElement(DevCenterContext.Provider, { value: store }, children);
}

export function useDevCenterStore() {
  const store = useContext(DevCenterContext);
  if (!store) throw new Error("Put the component inside DevCenterProvider.");
  return store;
}

// The selector must return a value of the state, or a value that does not change between calls.
export function useDevCenterState(selector = (state) => state) {
  const store = useDevCenterStore();
  return useSyncExternalStore(store.subscribe, () => selector(store.getState()));
}

// Load a read while the component shows. A change of params stops the old read.
export function useResource(key, params = {}) {
  const store = useDevCenterStore();
  const id = resourceId(key, params);
  const paramsRef = useRef(params);
  paramsRef.current = params;
  useEffect(() => store.watch(key, paramsRef.current), [store, key, id]);
  const resource = useDevCenterState((state) => state.resources[id]);
  const reload = useCallback(() => store.load(key, paramsRef.current), [store, key, id]);
  return useMemo(
    () => ({
      data: resource?.data ?? null,
      status: resource?.status ?? "idle",
      error: resource?.error ?? null,
      stale: resource?.stale ?? false,
      current: resource?.current ?? false,
      revision: resource?.revision ?? null,
      reload,
    }),
    [resource, reload],
  );
}

// One JS API call for one control. Only this control shows its loading state.
// disabled is true while a long call of a different control runs.
export function useAction(method) {
  const store = useDevCenterStore();
  const busy = useDevCenterState((state) => state.busy);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState(null);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const run = useCallback(
    async (payload) => {
      setPending(true);
      setError(null);
      try {
        return await store.run(method, payload);
      } catch (raw) {
        const value = normalizeError(raw);
        const reaction = errorReaction(value, method);
        // The store shows stale_revision, session_not_open, and the Compare move. The control shows the rest.
        if (mounted.current && (reaction === "inline" || reaction === "region" || reaction === "agent")) setError(value);
        return null;
      } finally {
        if (mounted.current) setPending(false);
      }
    },
    [store, method],
  );
  const reset = useCallback(() => setError(null), []);
  return { run, pending, error, reset, disabled: busy === "long" && !pending };
}
