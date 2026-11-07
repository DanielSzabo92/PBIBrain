import { defineConfig } from "@playwright/test";
import existing, { chatSpec, devcenterSpecs, graphWebServer, guardedSpec } from "./playwright.config.js";

export default defineConfig({
  ...existing,
  outputDir: ".guard-test-results/compat",
  // The Development Center specs need the fake server on port 8766, the chat spec its own on 8767. The main config runs them.
  testIgnore: [guardedSpec, devcenterSpecs, chatSpec],
  use: { ...existing.use, channel: "chrome", baseURL: "http://127.0.0.1:8774" },
  webServer: { ...graphWebServer, command: ".venv\\Scripts\\python.exe -m tests.graph_ui_server --port 8774", url: "http://127.0.0.1:8774/", reuseExistingServer: false },
});
