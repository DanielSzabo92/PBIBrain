import { defineConfig } from "@playwright/test";

// GUARD_PYTHON selects the Python of the guard server. The default is the local .venv of the repository.
const python = process.env.GUARD_PYTHON || ".venv\\Scripts\\python.exe";

export default defineConfig({
  outputDir: ".guard-test-results/guard",
  testDir: "./e2e", testMatch: "guardedDevelopment.spec.js", workers: 1,
  timeout: 30000, reporter: "list",
  use: { baseURL: "http://127.0.0.1:8773", channel: "chrome", viewport: { width: 1440, height: 1000 }, screenshot: "only-on-failure" },
  webServer: { command: `${python} -m tests.guard_ui_server --port 8773`, cwd: "..", url: "http://127.0.0.1:8773/api/overview", reuseExistingServer: false, timeout: 30000 },
});
