import config, { devcenterSpecs, graphWebServer, guardedSpec } from "./playwright.config.js";

// An isolated port avoids interfering with other local previews on 8765.
// The Development Center specs need the fake server on port 8766. The main config runs them.
export default {
  ...config,
  testIgnore: [guardedSpec, devcenterSpecs],
  use: { ...config.use, baseURL: "http://127.0.0.1:8875" },
  webServer: {
    ...graphWebServer,
    command: "python -m tests.graph_ui_server --port 8875",
    url: "http://127.0.0.1:8875/api/overview",
    reuseExistingServer: false,
  },
};
