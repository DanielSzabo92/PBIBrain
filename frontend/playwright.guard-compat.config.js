import { defineConfig } from "@playwright/test";
import existing, { devcenterSpecs, graphWebServer, guardedSpec } from "./playwright.config.js";

export default defineConfig({
  ...existing,
  outputDir: ".guard-test-results/compat",
  // The Development Center specs need the fake server on port 8766. The main config runs them.
  testIgnore: [guardedSpec, devcenterSpecs],
  use: { ...existing.use, channel: "chrome", baseURL: "http://127.0.0.1:8774" },
  webServer: { ...graphWebServer, command: ".venv\\Scripts\\python.exe -m tests.graph_ui_server --port 8774", url: "http://127.0.0.1:8774/", reuseExistingServer: false },
});
