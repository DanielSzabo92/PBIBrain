import { defineConfig } from "@playwright/test";

export const graphWebServer = {
  command: "python -m tests.graph_ui_server --port 8765",
  cwd: "..",
  url: "http://127.0.0.1:8765/api/overview",
  reuseExistingServer: !process.env.CI,
  timeout: 30000,
};

// Development Center fake server. The devcenter*.spec.js files use the base URL http://127.0.0.1:8766.
export const devcenterWebServer = {
  command: "python -m tests.devcenter_ui_server --port 8766",
  cwd: "..",
  url: "http://127.0.0.1:8766/__test__/health",
  reuseExistingServer: !process.env.CI,
  timeout: 30000,
};

// The chat spec (issue #7) uses its own graph server: a scripted provider and an open merge session.
export const chatWebServer = {
  command: "python -m tests.graph_ui_server --port 8767 --chat",
  cwd: "..",
  url: "http://127.0.0.1:8767/api/overview",
  reuseExistingServer: !process.env.CI,
  timeout: 60000,
};

export const chatSpec = "**/chat.spec.js";

export const devcenterSpecs = "**/devcenter*.spec.js";
// The guarded development spec needs its own server (playwright.guard.config.js, port 8773).
export const guardedSpec = "**/guardedDevelopment.spec.js";

export default defineConfig({
  testDir: "./e2e",
  testIgnore: guardedSpec,
  fullyParallel: false,
  workers: 1,
  timeout: 30000,
  reporter: "list",
  use: { baseURL: "http://127.0.0.1:8765", channel: process.env.PLAYWRIGHT_CHANNEL || undefined, viewport: { width: 1440, height: 1000 }, trace: "retain-on-failure", screenshot: "only-on-failure" },
  webServer: [graphWebServer, devcenterWebServer, chatWebServer],
});
