import assert from "node:assert/strict";
import test from "node:test";
import { answerText, applyEvents, chatContext, contextChips, emptyAnswer, parseInline, parseMarkdown, toolLabel, transcriptMarkdown } from "../src/chat.js";
import { createBrainTransport } from "../src/transport.js";
import { commandFor, shortcutKeys } from "../src/shortcuts.js";

const VIEW = { id: "graph", label: "Graph" };
const SELECTION = { id: "measure:Sales/Net Sales", name: "Net Sales", type: "MEASURE" };
const SESSION = { session_id: "s1", display_name: "Q3 merge" };

test("context chips show the view, the selection and the merge session, and each can be removed", () => {
  const chips = contextChips({ view: VIEW, selection: SELECTION, session: SESSION });
  assert.deepEqual(chips.map((chip) => chip.kind), ["view", "selection", "session"]);
  assert.equal(chips[1].label, "Net Sales");
  const fewer = contextChips({ view: VIEW, selection: SELECTION, session: SESSION }, new Set(["view:graph", "session:s1"]));
  assert.deepEqual(fewer.map((chip) => chip.kind), ["selection"]);
  assert.equal(contextChips({ view: { id: "inspector", label: "Inspector" } }, new Set(["view:graph"])).length, 1);
  // A removed selection chip comes back for a different selection.
  const other = contextChips({ view: VIEW, selection: { id: "column:x" }, session: null }, new Set([`selection:${SELECTION.id}`]));
  assert.deepEqual(other.map((chip) => chip.kind), ["view", "selection"]);
});

test("the start context carries only the chips that are still on", () => {
  const all = { view: VIEW, selection: SELECTION, session: SESSION };
  assert.deepEqual(chatContext(contextChips(all), all), {
    view: VIEW, selection: { id: SELECTION.id, name: "Net Sales", type: "MEASURE" }, session: true, session_name: "Q3 merge",
  });
  const none = chatContext([], all);
  assert.deepEqual(none, { view: null, selection: null, session: false, session_name: "" });
});

test("run events fold into one answer: streamed text, a tool call, a proposal, an error, the end", () => {
  let answer = emptyAnswer("r1");
  answer = applyEvents(answer, [{ type: "text", text: "Look" }]);
  answer = applyEvents(answer, [{ type: "text", text: "ing." }, { type: "tool_call", id: "t1", name: "brain_search", input: { query: "x" } }]);
  assert.equal(answer.parts[1].status, "running");
  answer = applyEvents(answer, [
    { type: "tool_result", id: "t1", name: "brain_search", ok: true, summary: "3 items" },
    { type: "proposal", item: "proposal", id: "p1", kind: "object_edit", target: "measure:x", target_name: "x", summary: "Edit description" },
    { type: "error", message: "boom" },
    { type: "done", stop_reason: "error" },
  ]);
  assert.equal(answerText(answer), "Looking.");
  assert.deepEqual(answer.parts.map((part) => part.type), ["text", "tool", "proposal", "error"]);
  assert.equal(answer.parts[1].status, "done");
  assert.equal(answer.parts[1].summary, "3 items");
  assert.equal(answer.parts[2].targetName, "x");
  assert.equal(answer.done, true);
  assert.equal(answer.stopReason, "error");
  assert.equal(toolLabel("brain_search"), "Searched objects");
});

test("object links keep IDs with spaces and slashes; other Markdown is parsed, never raw HTML", () => {
  const tokens = parseInline("See [Net Sales](object:measure:Sales/Net Sales) and `SUM(x)` **now** <b>x</b>");
  assert.deepEqual(tokens.map((token) => token.type), ["text", "object", "text", "code", "text", "strong", "text"]);
  assert.equal(tokens[1].id, "measure:Sales/Net Sales");
  assert.equal(tokens[6].text, " <b>x</b>");
  const blocks = parseMarkdown("# Title\n\nOne\ntwo\n\n- a\n- [B](object:b)\n1. first\n\n```dax\nSUM(x)\n```");
  assert.deepEqual(blocks.map((block) => block.type), ["heading", "paragraph", "list", "list", "code"]);
  assert.equal(blocks[2].ordered, false);
  assert.equal(blocks[2].items[1][0].type, "object");
  assert.equal(blocks[3].ordered, true);
  assert.equal(blocks[4].text, "SUM(x)");
  assert.equal(parseInline("[web](https://example.com)")[0].type, "link");
});

test("copy as markdown lists the user turns, the answers, tools and proposals", () => {
  const answer = applyEvents(emptyAnswer("r1"), [
    { type: "text", text: "Done." }, { type: "tool_call", id: "t", name: "proposal_submit" },
    { type: "tool_result", id: "t", ok: true, summary: "Done" },
    { type: "proposal", item: "proposal", id: "p", kind: "object_edit", target: "m", target_name: "Margin", summary: "Edit description" },
    { type: "done" },
  ]);
  const text = transcriptMarkdown([{ id: "u", role: "user", text: "Fix it" }, answer]);
  assert.match(text, /^\*\*You:\*\* Fix it/);
  assert.match(text, /\*\*PBIBrain:\*\* Done\./);
  assert.match(text, /> Made a proposal \(proposal_submit\): Done/);
  assert.match(text, /> Proposal for Margin: Edit description\. Decide in Merge models\./);
});

test("Ctrl+J toggles the chat", () => {
  assert.equal(shortcutKeys("chat"), "Ctrl+J");
  assert.equal(commandFor({ key: "j", ctrlKey: true, target: { tagName: "TEXTAREA" } }), "chat");
});

test("the chat transport uses the backend routes and never sends a key it was not given", async () => {
  const calls = [];
  const fetcher = async (url, options = {}) => { calls.push({ url, options }); return { ok: true, json: async () => ({ run_id: "r 1", next: 3 }) }; };
  const transport = createBrainTransport({ baseUrl: "/api", fetcher });
  await transport.startChat({ text: "hi", conversationId: "c1", context: { session: false } });
  await transport.chatEvents("r 1", 3);
  await transport.stopChat("r 1");
  await transport.saveChatSettings({ enabled: true, provider: "local" });
  await transport.testChatConnection();
  assert.deepEqual(calls.map((call) => [call.options.method || "GET", call.url]), [
    ["POST", "/api/chat/start"], ["GET", "/api/chat/runs/r%201?after=3"], ["POST", "/api/chat/runs/r%201/stop"],
    ["POST", "/api/chat/settings"], ["POST", "/api/chat/test"],
  ]);
  assert.deepEqual(JSON.parse(calls[0].options.body), { text: "hi", conversation_id: "c1", context: { session: false } });
  assert.deepEqual(JSON.parse(calls[3].options.body), { enabled: true, provider: "local" });
});

test("no merge session reads as null", async () => {
  const transport = createBrainTransport({ fetcher: async () => ({ ok: false, status: 409, statusText: "Conflict", json: async () => ({ error: { code: "session_not_open" } }) }) });
  assert.equal(await transport.getMergeSession(), null);
});
