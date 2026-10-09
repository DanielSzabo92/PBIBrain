import base from "../../../frontend/playwright.config.js";

export default {
  ...base,
  testDir: "../../../frontend/e2e",
  outputDir: "../../../frontend/test-results",
  use: { ...base.use, channel: "chrome", baseURL: "http://127.0.0.1:18765" },
  webServer: undefined,
};
