import assert from "node:assert/strict";
import test from "node:test";
import { answerText, applyEvents, chatContext, contextChips, emptyAnswer, parseInline, parseMarkdown, starterPrompts, toolLabel, transcriptMarkdown } from "../src/chat.js";
import { createBrainTransport } from "../src/transport.js";
import { commandFor, shortcutKeys } from "../src/shortcuts.js";

const VIEW = { id: "graph", label: "Graph" };
const MERGE_VIEW = { id: "devcenter", label: "Merge models" };
const SELECTION = { id: "measure:Sales/Net Sales", name: "Net Sales", type: "MEASURE" };
const SESSION = { session_id: "s1", display_name: "Q3 merge" };

test("context chips show the view, the selection and the merge session on merge view, and each can be removed", () => {
  const chips = contextChips({ view: MERGE_VIEW, selection: SELECTION, session: SESSION });
  assert.deepEqual(chips.map((chip) => chip.kind), ["view", "selection", "session"]);
  assert.equal(chips[1].label, "Net Sales");
  const fewer = contextChips({ view: MERGE_VIEW, selection: SELECTION, session: SESSION }, new Set(["view:devcenter", "session:s1"]));
  assert.deepEqual(fewer.map((chip) => chip.kind), ["selection"]);
  assert.equal(contextChips({ view: { id: "inspector", label: "Inspector" } }, new Set(["view:graph"])).length, 1);
  // A removed selection chip comes back for a different selection.
  const other = contextChips({ view: MERGE_VIEW, selection: { id: "column:x" }, session: null }, new Set([`selection:${SELECTION.id}`]));
  assert.deepEqual(other.map((chip) => chip.kind), ["view", "selection"]);
});

test("context chips isolate merge session context so merge does not leak into inspector, graph, or other views", () => {
  const inspectorChips = contextChips({ view: { id: "inspector", label: "Inspector" }, selection: SELECTION, session: SESSION });
  assert.deepEqual(inspectorChips.map((c) => c.kind), ["view", "selection"]);
  assert.ok(!inspectorChips.some((c) => c.kind === "session"), "merge session must not leak into inspector");

  const graphChips = contextChips({ view: VIEW, selection: SELECTION, session: SESSION });
  assert.deepEqual(graphChips.map((c) => c.kind), ["view", "selection"]);
  assert.ok(!graphChips.some((c) => c.kind === "session"), "merge session must not leak into graph");

  const overviewChips = contextChips({ view: { id: "overview", label: "Overview" }, session: SESSION });
  assert.deepEqual(overviewChips.map((c) => c.kind), ["view"]);
  assert.ok(!overviewChips.some((c) => c.kind === "session"), "merge session must not leak into overview");

  const mergeChips = contextChips({ view: { id: "merge", label: "Merge models" }, session: SESSION });
  assert.deepEqual(mergeChips.map((c) => c.kind), ["view", "session"]);
});

test("context chips include descriptive tooltips explaining what context is shared with the AI", () => {
  const chips = contextChips({
    view: { id: "inspector", label: "Inspector" },
    selection: { id: "measure:1", name: "Total Sales", type: "MEASURE" },
    session: SESSION,
  });
  assert.ok(chips[0].title.startsWith("Shared with AI: Current view context"));
  assert.ok(chips[1].title.startsWith("Shared with AI: Selected measure"));

  const mergeChips = contextChips({ view: MERGE_VIEW, session: SESSION });
  assert.ok(mergeChips[1].title.startsWith("Shared with AI: Active Merge models session"));
});

test("starter prompts are context-aware based on active view and selection", () => {
  const overviewPrompts = starterPrompts({ view: { id: "overview" } });
  assert.ok(overviewPrompts.length >= 3);
  assert.ok(overviewPrompts.some((p) => p.includes("model")));

  const inspectorNamed = starterPrompts({ view: { id: "inspector" }, selection: { name: "Profit Margin" } });
  assert.ok(inspectorNamed.some((p) => p.includes("Profit Margin")));

  const inspectorEmpty = starterPrompts({ view: { id: "inspector" } });
  assert.ok(inspectorEmpty.some((p) => p.includes("Explain the calculation")));

  const graphPrompts = starterPrompts({ view: { id: "graph" } });
  assert.ok(graphPrompts.some((p) => p.includes("graph") || p.includes("dependencies")));

  const mergePrompts = starterPrompts({ view: MERGE_VIEW, session: { display_name: "Sprint 42" } });
  assert.ok(mergePrompts.some((p) => p.includes("Sprint 42")));
});

test("the start context carries only the chips that are still on", () => {
  const all = { view: MERGE_VIEW, selection: SELECTION, session: SESSION };
  assert.deepEqual(chatContext(contextChips(all), all), {
    view: MERGE_VIEW, selection: { id: SELECTION.id, name: "Net Sales", type: "MEASURE" }, session: true, session_name: "Q3 merge",
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
