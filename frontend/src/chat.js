// In-app chat helpers (issue #7): context chips, the run event reducer, a small Markdown
// parser with object links, and copy-as-markdown. Pure functions, so node --test covers them.
// The parser returns a tree the panel renders as React elements: no HTML string is ever
// injected, because answers carry project text (names, descriptions, DAX) the model quoted.

export const POLL_MS = 120;
export const OBJECT_SCHEME = "object:";

// ---- Context chips ---------------------------------------------------------------------

/** The chips the chat can see. `removed` holds the ids the user took away for this chat. */
export function contextChips({ view = null, selection = null, session = null } = {}, removed = new Set()) {
  const chips = [];
  // A removed chip stays removed only for what it named: another view or selection brings a new chip.
  if (view?.id && !removed.has(`view:${view.id}`)) chips.push({ id: `view:${view.id}`, kind: "view", label: view.label || view.id, title: `Current view: ${view.label || view.id}` });
  if (selection?.id && !removed.has(`selection:${selection.id}`)) {
    chips.push({ id: `selection:${selection.id}`, kind: "selection", label: selection.name || selection.id, title: `Selected ${selection.type ? String(selection.type).toLowerCase() : "object"}: ${selection.id}` });
  }
  if (session?.session_id && !removed.has(`session:${session.session_id}`)) {
    chips.push({ id: `session:${session.session_id}`, kind: "session", label: session.display_name || "Merge session", title: "The open Merge models session. The chat can read it and make proposals." });
  }
  return chips;
}

/** The context payload of POST /api/chat/start for the chips that are still on. */
export function chatContext(chips, { view = null, selection = null, session = null } = {}) {
  const on = new Set(chips.map((chip) => chip.kind));
  return {
    view: on.has("view") && view ? { id: view.id, label: view.label } : null,
    selection: on.has("selection") && selection ? { id: selection.id, name: selection.name || "", type: selection.type || "" } : null,
    session: on.has("session") && Boolean(session),
    session_name: on.has("session") && session ? session.display_name || "" : "",
  };
}

// ---- Run events ------------------------------------------------------------------------

export function emptyAnswer(id) {
  return { id, role: "assistant", parts: [], done: false, stopReason: null };
}

/** Fold the events of one poll into the assistant message. Returns a new message. */
export function applyEvents(message, events) {
  const parts = [...message.parts];
  let { done, stopReason } = message;
  for (const event of events || []) {
    if (event.type === "text") {
      const last = parts[parts.length - 1];
      if (last?.type === "text") parts[parts.length - 1] = { ...last, text: last.text + event.text };
      else parts.push({ type: "text", text: event.text });
    } else if (event.type === "tool_call") {
      parts.push({ type: "tool", id: event.id, name: event.name, input: event.input || {}, status: "running", summary: "" });
    } else if (event.type === "tool_result") {
      const index = parts.findLastIndex((part) => part.type === "tool" && part.id === event.id && part.status === "running");
      const update = { status: event.ok ? "done" : "failed", summary: event.summary || "" };
      if (index >= 0) parts[index] = { ...parts[index], ...update };
      else parts.push({ type: "tool", id: event.id, name: event.name, input: {}, ...update });
    } else if (event.type === "proposal") {
      parts.push({ type: "proposal", item: event.item, id: event.id, kind: event.kind, target: event.target, targetName: event.target_name, summary: event.summary, reason: event.reason });
    } else if (event.type === "error") {
      parts.push({ type: "error", message: event.message || "The chat failed." });
    } else if (event.type === "done") {
      done = true;
      stopReason = event.stop_reason || "end_turn";
    }
  }
  return { ...message, parts, done, stopReason };
}

export function answerText(message) {
  return message.parts.filter((part) => part.type === "text").map((part) => part.text).join("");
}

export const TOOL_LABELS = {
  brain_overview: "Read the project overview",
  brain_search: "Searched objects",
  brain_object: "Read an object",
  brain_context: "Read object context",
  brain_graph: "Read the graph",
  brain_impact: "Checked impact",
  brain_compare: "Compared snapshots",
  brain_commonality: "Compared models and reports",
  brain_pending_changes: "Checked changed files",
  session_get: "Read the merge session",
  compare_rows_list: "Listed compare rows",
  impact_get: "Read merge impact",
  naming_rules_get: "Read naming rules",
  name_propose: "Calculated a name",
  proposal_submit: "Made a proposal",
  question_ask: "Asked you a question",
  plan_validate: "Validated the plan",
};

export function toolLabel(name) {
  return TOOL_LABELS[name] || name;
}

// ---- Markdown --------------------------------------------------------------------------

const INLINE = /(`[^`\n]+`)|\*\*([^*\n]+)\*\*|\[([^\]\n]{1,200})\]\(object:([^)\n]{1,400})\)|\[([^\]\n]{1,200})\]\((https?:[^)\s]+)\)/g;

/** Inline tokens: text, code, strong, object (a project object link), link (shown as text plus URL). */
export function parseInline(text) {
  const tokens = [];
  let last = 0;
  for (const match of String(text).matchAll(INLINE)) {
    if (match.index > last) tokens.push({ type: "text", text: text.slice(last, match.index) });
    if (match[1]) tokens.push({ type: "code", text: match[1].slice(1, -1) });
    else if (match[2]) tokens.push({ type: "strong", text: match[2] });
    else if (match[3]) tokens.push({ type: "object", text: match[3], id: match[4].trim() });
    else tokens.push({ type: "link", text: match[5], href: match[6] });
    last = match.index + match[0].length;
  }
  if (last < text.length) tokens.push({ type: "text", text: text.slice(last) });
  return tokens;
}

/** Blocks: paragraph, heading, list (ordered or not), code. */
export function parseMarkdown(source) {
  const lines = String(source || "").replace(/\r\n/g, "\n").split("\n");
  const blocks = [];
  let paragraph = [];
  let list = null;
  const flush = () => {
    if (paragraph.length) blocks.push({ type: "paragraph", inline: parseInline(paragraph.join("\n")) });
    paragraph = [];
    if (list) blocks.push(list);
    list = null;
  };
  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    const fence = line.match(/^\s*```\s*([\w-]*)\s*$/);
    if (fence) {
      flush();
      const code = [];
      index += 1;
      while (index < lines.length && !/^\s*```\s*$/.test(lines[index])) { code.push(lines[index]); index += 1; }
      blocks.push({ type: "code", language: fence[1] || "", text: code.join("\n") });
      continue;
    }
    const heading = line.match(/^(#{1,4})\s+(.*)$/);
    if (heading) { flush(); blocks.push({ type: "heading", level: heading[1].length, inline: parseInline(heading[2]) }); continue; }
    const bullet = line.match(/^\s*([-*]|\d+[.)])\s+(.*)$/);
    if (bullet) {
      const ordered = /\d/.test(bullet[1]);
      if (paragraph.length) { blocks.push({ type: "paragraph", inline: parseInline(paragraph.join("\n")) }); paragraph = []; }
      if (!list || list.ordered !== ordered) { if (list) blocks.push(list); list = { type: "list", ordered, items: [] }; }
      list.items.push(parseInline(bullet[2]));
      continue;
    }
    if (!line.trim()) { flush(); continue; }
    if (list) { blocks.push(list); list = null; }
    paragraph.push(line);
  }
  flush();
  return blocks;
}

// ---- Copy as markdown ------------------------------------------------------------------

export function transcriptMarkdown(messages) {
  return messages.map((message) => {
    if (message.role === "user") return `**You:** ${message.text}`;
    const body = message.parts.map((part) => {
      if (part.type === "text") return part.text;
      if (part.type === "tool") return `> ${toolLabel(part.name)} (${part.name})${part.summary ? `: ${part.summary}` : ""}`;
      if (part.type === "proposal") return `> ${part.item === "question" ? "Question" : "Proposal"} for ${part.targetName || part.target}: ${part.summary || part.kind || ""}. Decide in Merge models.`;
      if (part.type === "error") return `> Error: ${part.message}`;
      return "";
    }).filter(Boolean).join("\n\n");
    return `**PBIBrain:** ${body}`;
  }).join("\n\n");
}
