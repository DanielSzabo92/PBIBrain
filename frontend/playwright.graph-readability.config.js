import config from "./playwright.config.js";

// An isolated port avoids interfering with other local previews on 8765.
export default {
  ...config,
  use: { ...config.use, baseURL: "http://127.0.0.1:8875" },
  webServer: {
    ...config.webServer,
    command: "python -m tests.graph_ui_server --port 8875",
    url: "http://127.0.0.1:8875/api/overview",
    reuseExistingServer: false,
  },
};
