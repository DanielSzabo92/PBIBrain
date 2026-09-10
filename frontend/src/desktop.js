function bridgeFrom(scope) {
  const api = scope?.pywebview?.api;
  return api && typeof api.get_session === "function" ? api : null;
}

/**
 * Detect the native host without delaying normal browser development.
 * pywebview injects its API before, or announces it with, pywebviewready.
 */
export function subscribeToDesktopBridge(onReady, scope = globalThis) {
  let delivered = false;
  const deliver = () => {
    if (delivered) return;
    const api = bridgeFrom(scope);
    if (!api) return;
    delivered = true;
    onReady(api);
  };
  deliver();
  const listener = () => deliver();
  scope?.addEventListener?.("pywebviewready", listener, { once: true });
  return () => scope?.removeEventListener?.("pywebviewready", listener);
}

export async function desktopRequest(api, method, ...args) {
  if (!api || typeof api[method] !== "function") throw new Error("Desktop service is unavailable");
  const response = await api[method](...args);
  if (!response?.ok) throw new Error(response?.error || "Desktop service failed");
  return response;
}
