import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { getAIStatus } from "../src/chat.js";

const SRC = fileURLToPath(new URL("../src/", import.meta.url));
const copilot = { id: "copilot", kind: "cli", needs_key: false, model: "", executable: "copilot", sign_in: "Run copilot once." };

test("a subscription CLI is ready without a model or key", () => {
  const status = getAIStatus({
    draft: { enabled: true, provider: "copilot", model: "" },
    settings: { enabled: true, provider: "copilot", ready: true, reason: "" },
    provider: copilot,
  });
  assert.equal(status.ready, true);
});

test("a subscription CLI that is not installed shows the server's reason", () => {
  const reason = "The copilot program was not found. Run copilot once.";
  const status = getAIStatus({
    draft: { enabled: true, provider: "copilot", model: "" },
    settings: { enabled: true, provider: "copilot", ready: false, reason },
    provider: copilot,
  });
  assert.deepEqual(status, { ready: false, message: reason });
});

test("the settings panel hides the key and URL for a subscription and sends neither", async () => {
  const code = await readFile(new URL("components/AISettings.jsx", `file://${SRC}`), "utf8");
  assert.ok(code.includes('provider?.kind === "cli"'));
  assert.ok(code.includes('id="ai-command"'), "the program path field exists");
  assert.ok(code.includes("apiKey.trim() && !cli"), "no key is sent to a subscription provider");
});
