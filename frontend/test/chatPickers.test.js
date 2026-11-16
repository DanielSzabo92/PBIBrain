import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";
import { effortLabel, modelEfforts, pickerEffort, pickerModels, pickerProvider } from "../src/chat.js";
import { createBrainTransport } from "../src/transport.js";

const EFFORTS = ["low", "medium", "high", "xhigh", "max"];
const MODELS = [
  { id: "claude-opus-5-5", label: "Claude Opus 5.5", efforts: EFFORTS, default_effort: "medium" },
  { id: "claude-sonnet-5-5", label: "Claude Sonnet 5.5", efforts: EFFORTS, default_effort: "high" },
  { id: "claude-haiku-4-5", label: "Claude Haiku 4.5", efforts: [], default_effort: "" },
];

test("without favourites the picker offers every listed model with its own default effort", () => {
  const options = pickerModels({ profile: { model: "claude-opus-5-5", effort: "" }, models: MODELS, providerEfforts: EFFORTS });
  assert.deepEqual(options.map((item) => item.id), ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-4-5"]);
  assert.equal(pickerEffort(options[1]), "high");
  assert.equal(pickerEffort(options[2]), "", "a model without efforts has none");
});

test("favourites narrow the picker and the saved model stays first", () => {
  const options = pickerModels({
    profile: { model: "claude-opus-5-5", effort: "xhigh" },
    favourites: [{ model: "claude-sonnet-5-5", effort: "low" }, { model: "my-tuned-model", effort: "" }],
    models: MODELS, providerEfforts: EFFORTS,
  });
  assert.deepEqual(options.map((item) => [item.id, item.effort]), [["claude-opus-5-5", "xhigh"], ["claude-sonnet-5-5", "low"], ["my-tuned-model", ""]]);
  const marked = pickerModels({ profile: { model: "claude-opus-5-5", effort: "high" }, favourites: [{ model: "claude-opus-5-5", effort: "max" }], models: MODELS });
  assert.deepEqual(marked.map((item) => [item.id, item.effort]), [["claude-opus-5-5", "max"]], "the favourite's effort wins");
  assert.deepEqual(options[2].efforts, EFFORTS, "a model the list does not know takes the provider's levels");
});

test("a subscription's plan default is an option and an effort the model does not take is dropped", () => {
  const options = pickerModels({ profile: { model: "", effort: "" }, models: [{ id: "", label: "Default of your plan", efforts: ["low", "medium", "high"] }], providerEfforts: ["low", "medium", "high"] });
  assert.deepEqual(options.map((item) => item.label), ["Default of your plan"]);
  assert.equal(pickerEffort({ efforts: ["low"], effort: "max" }), "");
  assert.deepEqual(modelEfforts("claude-haiku-4-5", MODELS, EFFORTS), []);
  assert.deepEqual(modelEfforts("unlisted", MODELS, EFFORTS), EFFORTS);
  assert.equal(effortLabel("xhigh"), "Extra high");
  assert.equal(effortLabel(""), "Default");
});

test("the chat starts on the default provider if it is set up, else on the first one that is", () => {
  assert.equal(pickerProvider({ provider: "anthropic", configured: ["anthropic", "local"] }), "anthropic");
  assert.equal(pickerProvider({ provider: "openai", configured: ["local", "codex"] }), "local");
  assert.equal(pickerProvider({ provider: "anthropic", configured: ["anthropic", "local"] }, "local"), "local");
  assert.equal(pickerProvider({ provider: "anthropic", configured: [] }), "");
});

test("the transport lists models and sends the picked provider, model and effort", async () => {
  const calls = [];
  const fetcher = async (url, options = {}) => { calls.push({ url, options }); return { ok: true, json: async () => ({}) }; };
  const transport = createBrainTransport({ baseUrl: "/api", fetcher });
  await transport.getChatModels("claude_code", true);
  await transport.startChat({ text: "hi", provider: "anthropic", model: "claude-opus-5-5", effort: "" });
  assert.equal(calls[0].url, "/api/chat/models?provider=claude_code&refresh=true");
  assert.deepEqual(JSON.parse(calls[1].options.body), { text: "hi", conversation_id: null, context: {}, provider: "anthropic", model: "claude-opus-5-5", effort: "" });
});

test("the chat panel has the pickers and the settings have the favourites", async () => {
  const panel = await readFile(new URL("../src/components/ChatPanel.jsx", import.meta.url), "utf8");
  assert.ok(panel.includes('data-testid="chat-pickers"') && panel.includes('aria-label="Thinking effort"'));
  assert.ok(panel.includes("...pick }"), "the picks go with each message");
  const settings = await readFile(new URL("../src/components/AISettings.jsx", import.meta.url), "utf8");
  assert.ok(settings.includes('data-testid="ai-favourites"') && settings.includes("favourites: { [draft.provider]: favourites }"));
  assert.ok(settings.includes('id="ai-effort"'));
});
