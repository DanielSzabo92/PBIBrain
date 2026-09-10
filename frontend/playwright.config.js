import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 30000,
  reporter: "list",
  use: { baseURL: "http://127.0.0.1:8765", channel: process.env.PLAYWRIGHT_CHANNEL || undefined, viewport: { width: 1440, height: 1000 }, trace: "retain-on-failure", screenshot: "only-on-failure" },
  webServer: {
    command: "python -m tests.graph_ui_server --port 8765",
    cwd: "..",
    url: "http://127.0.0.1:8765/api/overview",
    reuseExistingServer: !process.env.CI,
    timeout: 30000,
  },
});
