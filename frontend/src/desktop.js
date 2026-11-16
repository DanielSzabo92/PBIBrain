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

/** Shown when a desktop-only action runs in a browser tab (start.sh / start.bat / `brain serve`). */
export const DESKTOP_ONLY_MESSAGE =
  "This needs the PBIBrain desktop app: a browser tab cannot open the file picker or change Power BI files. Start PBIBrain from the Windows installer, or run `pbibrain` after `pip install -e \".[desktop]\"`.";

/** Whether the desktop app's bridge is in this page (false in a plain browser tab). */
export function hasDesktopApi(scope = globalThis) {
  return Boolean(scope?.pywebview?.api);
}

export async function desktopRequest(api, method, ...args) {
  if (!api || typeof api[method] !== "function") throw new Error(DESKTOP_ONLY_MESSAGE);
  const response = await api[method](...args);
  if (!response?.ok) throw new Error(response?.error || "Desktop service failed");
  return response;
}
