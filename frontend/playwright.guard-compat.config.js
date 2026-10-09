import { defineConfig } from "@playwright/test";
import existing from "./playwright.config.js";

export default defineConfig({
  ...existing,
  outputDir: ".guard-test-results/compat",
  testIgnore: "**/guardedDevelopment.spec.js",
  use: { ...existing.use, channel: "chrome", baseURL: "http://127.0.0.1:8774" },
  webServer: { ...existing.webServer, command: ".venv\\Scripts\\python.exe -m tests.graph_ui_server --port 8774", url: "http://127.0.0.1:8774/", reuseExistingServer: false },
});
