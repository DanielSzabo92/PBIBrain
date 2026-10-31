// Vite plugin for browser dev mode with the Development Center fake server (UI design section 10).
// With DEVCENTER_FAKE=1, index.html gets the test shim tag, and the dev proxy sends
// /api and /__test__ to tests/devcenter_ui_server.py. Without it, the plugin does nothing.

export const DEVCENTER_SHIM_PATH = "/__test__/pywebview-shim.js";
export const DEVCENTER_FAKE_DEFAULT_URL = "http://127.0.0.1:8766";

export function devcenterFakeEnabled(env = {}) {
  return env.DEVCENTER_FAKE === "1";
}

export function devcenterFakePlugin({ enabled }) {
  return {
    name: "pbibrain-devcenter-fake",
    transformIndexHtml() {
      if (!enabled) return undefined;
      // A classic script runs before the deferred app module, so the shim is ready first.
      return [{ tag: "script", attrs: { src: DEVCENTER_SHIM_PATH }, injectTo: "head-prepend" }];
    },
  };
}

export function devcenterFakeProxy(env = {}) {
  const target = env.DEVCENTER_FAKE_URL || DEVCENTER_FAKE_DEFAULT_URL;
  return {
    "/api": { target, changeOrigin: true },
    "/__test__": { target, changeOrigin: true },
  };
}
