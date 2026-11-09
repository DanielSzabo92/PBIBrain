import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { getAIStatus } from "../src/chat.js";

const SRC = fileURLToPath(new URL("../src/", import.meta.url));

test("Issue #47: getAIStatus provides instant reactive status feedback without contradictory round-trips", () => {
  const anthropicProvider = { id: "anthropic", label: "Anthropic", needs_key: true, model: "claude-opus-5-5" };
  const localProvider = { id: "local", label: "Local endpoint", needs_key: false, model: "llama3.1" };

  // 1. When chat is disabled
  const offStatus = getAIStatus({
    draft: { enabled: false, provider: "anthropic", model: "claude-opus-5-5" },
    settings: { enabled: false, has_key: false, reason: "Chat is off. Turn it on in Settings, AI provider." },
    provider: anthropicProvider,
    keySaved: false,
    apiKey: "",
  });
  assert.equal(offStatus.ready, false);
  assert.equal(offStatus.message, "Chat is off. Turn it on in Settings, AI provider.");

  // 2. When toggle is flipped ON before an API key is saved (reactive instant feedback)
  const toggledOnStatus = getAIStatus({
    draft: { enabled: true, provider: "anthropic", model: "claude-opus-5-5" },
    settings: { enabled: false, has_key: false, reason: "Chat is off. Turn it on in Settings, AI provider." },
    provider: anthropicProvider,
    keySaved: false,
    apiKey: "",
  });
  assert.equal(toggledOnStatus.ready, false);
  assert.equal(toggledOnStatus.message, "Turned on. Add an API key to finish.");

  // 3. When an API key is typed into the draft input
  const typingKeyStatus = getAIStatus({
    draft: { enabled: true, provider: "anthropic", model: "claude-opus-5-5" },
    settings: { enabled: false, has_key: false },
    provider: anthropicProvider,
    keySaved: false,
    apiKey: "sk-ant-test12345",
  });
  assert.equal(typingKeyStatus.ready, true);
  assert.equal(typingKeyStatus.message, "The chat is ready.");

  // 4. When an API key was already saved
  const savedKeyStatus = getAIStatus({
    draft: { enabled: true, provider: "anthropic", model: "claude-opus-5-5" },
    settings: { enabled: true, has_key: true },
    provider: anthropicProvider,
    keySaved: true,
    apiKey: "",
  });
  assert.equal(savedKeyStatus.ready, true);
  assert.equal(savedKeyStatus.message, "The chat is ready.");

  // 5. When a provider does not need a key (e.g. Ollama / local)
  const localStatus = getAIStatus({
    draft: { enabled: true, provider: "local", model: "llama3.1" },
    settings: { enabled: true, has_key: false },
    provider: localProvider,
    keySaved: false,
    apiKey: "",
  });
  assert.equal(localStatus.ready, true);
  assert.equal(localStatus.message, "The chat is ready.");

  // 6. When model is missing
  const noModelStatus = getAIStatus({
    draft: { enabled: true, provider: "anthropic", model: "" },
    settings: { enabled: true, has_key: true },
    provider: anthropicProvider,
    keySaved: true,
    apiKey: "",
  });
  assert.equal(noModelStatus.ready, false);
  assert.equal(noModelStatus.message, "Choose a model in Settings, AI provider.");
});

test("Issue #47: AISettings source code implements single-step key setup and eliminates duplicate copy", async () => {
  const code = await readFile(path.join(SRC, "components/AISettings.jsx"), "utf8");

  // Single-step setup: entering API key automatically enables chat
  assert.ok(code.includes("body.enabled = true"), "AISettings enables chat automatically when saving API key");

  // Instant reactive toggle function wired to Switch
  assert.ok(code.includes("toggleEnabled"), "AISettings defines toggleEnabled for immediate smooth config sync");
  assert.ok(code.includes("onCheckedChange={toggleEnabled}"), "AISettings Switch triggers toggleEnabled directly");

  // Eliminates duplicated sentence: "stored in memory (until PBIBrain closes). It is kept only until PBIBrain closes"
  assert.ok(code.includes(".replace(/\\s*\\(until PBIBrain closes\\)/i, \"\")"), "AISettings sanitizes key_store label to eliminate duplicated copy");
  assert.ok(!code.includes("{settings.key_store}{settings.key_persistent"), "AISettings does not blindly concatenate un-sanitized key_store with persistent copy");
});

test("Issue #47: ChatPanel source code includes tooltips on header buttons, chips, and view starter prompts", async () => {
  const code = await readFile(path.join(SRC, "components/ChatPanel.jsx"), "utf8");
  const css = await readFile(path.join(SRC, "app.css"), "utf8");

  // Header button tooltips and labels
  assert.ok(code.includes('aria-label="Copy transcript"'), "Copy transcript button has explicit accessible label");
  assert.ok(code.includes('tooltip={copied ? "Copied" : "Copy transcript as Markdown"}'), "Copy transcript button has tooltip");
  assert.ok(code.includes('aria-label="New chat"') && code.includes('tooltip="Start a new chat"'), "New chat button has tooltip and label");
  assert.ok(code.includes('aria-label="Close chat"') && code.includes('tooltip="Close chat (Ctrl+J)"'), "Close chat button has tooltip and label");

  // Context chips with Tooltip component
  assert.ok(code.includes("<Tooltip key={chip.id} content={chip.title}"), "Context chips are wrapped in Radix Tooltip");

  // Starter prompts
  assert.ok(code.includes("starterPrompts({ view, selection, session })"), "ChatPanel computes view-specific starter prompts");
  assert.ok(code.includes("chat-starter-chip"), "ChatPanel renders clickable starter prompt chips");
  assert.ok(code.includes("handleStarter"), "ChatPanel handles starter prompt selection");

  // CSS rules for starter prompts and empty state
  assert.ok(css.includes(".chat-starters"), "app.css includes .chat-starters");
  assert.ok(css.includes(".chat-starter-chip"), "app.css includes .chat-starter-chip");
  assert.ok(css.includes(".chat-starter-icon"), "app.css includes .chat-starter-icon");
});
