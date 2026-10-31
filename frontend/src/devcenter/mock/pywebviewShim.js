// Test shim for the pywebview JS API (UI design section 10, step U0).
// Only the fake server (tests/devcenter_ui_server.py) serves this file, at
// /__test__/pywebview-shim.js. The fake server puts the method lists in
// self.__DEVCENTER_FAKE_METHODS__ before this code. Do not import this file
// from the app: the production build must not contain it.
(function installDevCenterShim(scope) {
  "use strict";
  if (scope.pywebview && scope.pywebview.api) return;
  const methods = scope.__DEVCENTER_FAKE_METHODS__;
  if (!methods || !Array.isArray(methods.jsapi) || !Array.isArray(methods.desktop)) {
    throw new Error("The fake server did not send the method lists. Load the shim from /__test__/pywebview-shim.js.");
  }

  async function post(path, body) {
    const response = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    let reply = null;
    try {
      reply = await response.json();
    } catch {
      reply = null;
    }
    if (!response.ok) {
      // The real host has no HTTP status. A non-2xx status means that the host did not answer.
      const error = new Error(reply?.error?.message || `The fake server replied with HTTP ${response.status}.`);
      error.reply = reply;
      throw error;
    }
    return reply;
  }

  const api = {};
  for (const name of methods.jsapi) {
    // Development Center calls take one payload object that contains base_revision.
    api[name] = (payload = {}) => post(`/__test__/jsapi/${name}`, payload);
  }
  for (const name of methods.desktop) {
    // The existing desktop methods take positional arguments and reply {ok, ...}.
    api[name] = (...args) => post(`/__test__/desktop/${name}`, { args });
  }

  scope.__PBIBRAIN_DESKTOP__ = true;
  scope.pywebview = { api };
  scope.dispatchEvent(new Event("pywebviewready"));
})(self);
