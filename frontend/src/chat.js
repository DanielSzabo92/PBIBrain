// In-app chat helpers (issue #7): context chips, the run event reducer, a small Markdown
// parser with object links, and copy-as-markdown. Pure functions, so node --test covers them.
// The parser returns a tree the panel renders as React elements: no HTML string is ever
// injected, because answers carry project text (names, descriptions, DAX) the model quoted.

export const POLL_MS = 120;

// ---- Context chips ---------------------------------------------------------------------

/** The chips the chat can see. `removed` holds the ids the user took away for this chat. */
export function contextChips({ view = null, selection = null, session = null } = {}, removed = new Set()) {
  const chips = [];
  // A removed chip stays removed only for what it named: another view or selection brings a new chip.
  if (view?.id && !removed.has(`view:${view.id}`)) {
    chips.push({
      id: `view:${view.id}`,
      kind: "view",
      label: view.label || view.id,
      title: `Shared with AI: Current view context (${view.label || view.id}). The AI knows which view you are working in.`,
    });
  }
  if (selection?.id && !removed.has(`selection:${selection.id}`)) {
    const selType = selection.type ? String(selection.type).toLowerCase() : "object";
    chips.push({
      id: `selection:${selection.id}`,
      kind: "selection",
      label: selection.name || selection.id,
      title: `Shared with AI: Selected ${selType} "${selection.name || selection.id}". The AI sees its definition, lineage, and related model objects.`,
    });
  }
  // Isolate merge session chip: only show when on the Merge view (devcenter / merge)
  const isMergeView = view?.id === "devcenter" || view?.id === "merge";
  if (isMergeView && session?.session_id && !removed.has(`session:${session.session_id}`)) {
    chips.push({
      id: `session:${session.session_id}`,
      kind: "session",
      label: session.display_name || "Merge session",
      title: `Shared with AI: Active Merge models session "${session.display_name || "Merge session"}". The AI can read session alignments and propose changes.`,
    });
  }
  return chips;
}

/** Suggested starter prompts tailored to the active view and selection. */
export function starterPrompts({ view = null, selection = null, session = null } = {}) {
  const viewId = view?.id || (typeof view === "string" ? view : "overview");
  const name = selection?.name || selection?.id || "";

  if (viewId === "inspector") {
    if (name) {
      return [
        `What depends on ${name}?`,
        `Explain the calculation and logic for ${name}`,
        `Which visuals or report pages use ${name}?`,
      ];
    }
    return [
      "Explain the calculation and logic for this object",
      "What are the upstream dependencies of this object?",
      "Which visuals or report pages use this object?",
    ];
  }

  if (viewId === "graph") {
    return [
      "Explain the relationships and flow in this graph",
      "Which tables have the highest incoming dependencies?",
      "Identify potential bottlenecks or unused paths",
    ];
  }

  if (viewId === "devcenter" || viewId === "merge") {
    const sessionName = session?.display_name ? ` for "${session.display_name}"` : "";
    return [
      `Summarize the merge session changes${sessionName}`,
      "Check for naming conflicts or breaking changes",
      "Propose descriptions for undocumented measures",
    ];
  }

  if (viewId === "review") {
    return [
      "Help me prioritize items in the review queue",
      "Explain why these changes were flagged for review",
      "Are any of these candidate changes breaking?",
    ];
  }

  return [
    "Summarize this Power BI model and key metrics",
    "Which measures have the most dependencies?",
    "Find measures or columns without descriptions",
    "Explain the primary data sources in this project",
  ];
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

const TOOL_LABELS = {
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

// ---- AI Settings status ----------------------------------------------------------------

/** Pure helper to compute reactive status message and readiness for AI provider settings. */
export function getAIStatus({ draft, settings, provider, apiKey = "", keySaved = false } = {}) {
  if (!draft) return { ready: false, message: "Loading AI settings…" };
  if (!draft.enabled) {
    return { ready: false, message: "Chat is off. Turn it on in Settings, AI provider." };
  }
  if (!draft.model?.trim()) {
    return { ready: false, message: "Choose a model in Settings, AI provider." };
  }
  const needsKey = provider ? provider.needs_key : true;
  const hasKey = keySaved || Boolean(apiKey?.trim());
  if (needsKey && !hasKey) {
    return { ready: false, message: "Turned on. Add an API key to finish." };
  }
  return { ready: true, message: "The chat is ready." };
}
