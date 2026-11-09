import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Bot, Copy, GitBranch, MessageSquarePlus, Send, Settings, Sparkles, Square, TriangleAlert, Wrench, X } from "lucide-react";
import { Button } from "./ui/button";
import { Tooltip } from "./ui/tooltip";
import {
  POLL_MS, answerText, applyEvents, chatContext, contextChips, emptyAnswer, parseMarkdown, starterPrompts, toolLabel, transcriptMarkdown,
} from "../chat";

// The docked chat panel (issue #7). Ctrl+J or the title bar button opens it on every view.
// Answers stream in through short polls of the run's events; object links open the Inspector
// (click) or the graph (the branch button next to the link).

function Inline({ tokens, onObject, onGraph }) {
  return tokens.map((token, index) => {
    if (token.type === "code") return <code key={index}>{token.text}</code>;
    if (token.type === "strong") return <strong key={index}>{token.text}</strong>;
    if (token.type === "link") return <span key={index}>{token.text} <span className="chat-url">({token.href})</span></span>;
    if (token.type === "object") {
      return (
        <span key={index} className="chat-object">
          <button type="button" className="chat-object-link" title={`Open ${token.id} in the Inspector`} onClick={() => onObject(token.id)}>{token.text}</button>
          <button type="button" className="chat-object-graph" aria-label={`Show ${token.text} in the graph`} title="Show its lineage in the graph" onClick={() => onGraph(token.id)}><GitBranch aria-hidden="true" /></button>
        </span>
      );
    }
    return <React.Fragment key={index}>{token.text}</React.Fragment>;
  });
}

function Markdown({ text, onObject, onGraph }) {
  const blocks = useMemo(() => parseMarkdown(text), [text]);
  return blocks.map((block, index) => {
    if (block.type === "code") return <pre key={index} className="chat-code"><code>{block.text}</code></pre>;
    if (block.type === "heading") return <p key={index} className="chat-heading"><Inline tokens={block.inline} onObject={onObject} onGraph={onGraph} /></p>;
    if (block.type === "list") {
      const Tag = block.ordered ? "ol" : "ul";
      return <Tag key={index}>{block.items.map((item, at) => <li key={at}><Inline tokens={item} onObject={onObject} onGraph={onGraph} /></li>)}</Tag>;
    }
    return <p key={index}><Inline tokens={block.inline} onObject={onObject} onGraph={onGraph} /></p>;
  });
}

function AnswerPart({ part, onObject, onGraph, onMerge }) {
  if (part.type === "text") return <div className="chat-text"><Markdown text={part.text} onObject={onObject} onGraph={onGraph} /></div>;
  if (part.type === "tool") {
    return (
      <div className={`chat-tool is-${part.status}`} data-testid="chat-tool">
        <Wrench aria-hidden="true" />
        <span>{toolLabel(part.name)}{part.status === "running" ? "…" : ""}</span>
        {part.summary ? <span className="chat-tool-summary">{part.summary}</span> : null}
      </div>
    );
  }
  if (part.type === "proposal") {
    return (
      <div className="chat-proposal" data-testid="chat-proposal" role="note">
        <p className="chat-proposal-title">{part.item === "question" ? "Question for you" : "Proposal"}: {part.targetName || part.target}</p>
        {part.summary ? <p>{part.summary}</p> : null}
        {part.reason ? <p className="muted-copy compact">{part.reason}</p> : null}
        <p className="muted-copy compact">Nothing changes until you accept it in Merge models.</p>
        <Button size="sm" variant="outline" onClick={onMerge}>Review in Merge models</Button>
      </div>
    );
  }
  if (part.type === "error") return <div role="alert" className="inline-error chat-error"><TriangleAlert aria-hidden="true" /><p>{part.message}</p></div>;
  return null;
}

export default function ChatPanel({ open, onClose, transport, view, selection, onObject, onGraph, onMerge, onSettings }) {
  const [settings, setSettings] = useState(null);
  const [settingsError, setSettingsError] = useState("");
  const [session, setSession] = useState(null);
  const [removed, setRemoved] = useState(() => new Set());
  const [messages, setMessages] = useState([]);
  const [conversationId, setConversationId] = useState(null);
  const [runId, setRunId] = useState(null);
  const [text, setText] = useState("");
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);
  const input = useRef(null);
  const list = useRef(null);
  const runRef = useRef(null);
  runRef.current = runId;

  useEffect(() => {
    if (!open) return undefined;
    let live = true;
    setSettingsError("");
    transport.getChatSettings().then((next) => { if (live) setSettings(next); }).catch((cause) => { if (live) setSettingsError(cause.message || "Chat settings could not be loaded."); });
    transport.getMergeSession?.().then((next) => { if (live) setSession(next && next.session_id ? next : null); });
    requestAnimationFrame(() => input.current?.focus());
    return () => { live = false; };
  }, [open, transport]);

  // Poll the running answer. Each poll returns only the events after the last one seen.
  useEffect(() => {
    if (!runId) return undefined;
    let live = true;
    let after = 0;
    let timer = null;
    const tick = async () => {
      try {
        const page = await transport.chatEvents(runId, after);
        if (!live) return;
        after = page.next;
        setMessages((current) => current.map((message) => (message.id === runId ? applyEvents(message, page.events) : message)));
        if (page.done) { setRunId(null); return; }
      } catch (cause) {
        if (!live) return;
        setMessages((current) => current.map((message) => (message.id === runId ? applyEvents(message, [{ type: "error", message: cause.message || "The answer could not be read." }, { type: "done", stop_reason: "error" }]) : message)));
        setRunId(null);
        return;
      }
      timer = setTimeout(tick, POLL_MS);
    };
    tick();
    return () => { live = false; if (timer) clearTimeout(timer); };
  }, [runId, transport]);

  useEffect(() => {
    const element = list.current;
    if (element) element.scrollTop = element.scrollHeight;
  }, [messages]);

  const chips = contextChips({ view, selection, session }, removed);
  const prompts = starterPrompts({ view, selection, session });
  const send = useCallback(async (event, textOverride) => {
    event?.preventDefault();
    const value = (typeof textOverride === "string" ? textOverride : text).trim();
    if (!value || runRef.current) return;
    setError("");
    try {
      const reply = await transport.startChat({ text: value, conversationId, context: chatContext(chips, { view, selection, session }) });
      setConversationId(reply.conversation_id);
      setMessages((current) => [...current, { id: `${reply.run_id}-user`, role: "user", text: value }, emptyAnswer(reply.run_id)]);
      setText("");
      setRunId(reply.run_id);
    } catch (cause) {
      setError(cause.message || "The message could not be sent.");
    }
  }, [chips, conversationId, selection, session, text, transport, view]);

  const handleStarter = (promptText) => {
    setText(promptText);
    send(undefined, promptText);
  };

  const stop = async () => {
    if (!runId) return;
    try { await transport.stopChat(runId); } catch { /* the poll ends the run either way */ }
  };
  const fresh = () => { if (runId) return; setMessages([]); setConversationId(null); setRemoved(new Set()); setError(""); input.current?.focus(); };
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(transcriptMarkdown(messages));
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setError("The conversation could not be copied.");
    }
  };

  if (!open) return null;
  const ready = settings?.ready;
  return (
    <aside className="chat-panel" aria-label="Chat" data-testid="chat-panel" onKeyDown={(event) => { if (event.key === "Escape" && !runId) { event.stopPropagation(); onClose(); } }}>
      <header className="chat-head">
        <h2><Bot aria-hidden="true" />Chat</h2>
        <div className="chat-head-actions" role="toolbar" aria-label="Chat actions">
          <Button variant="ghost" size="icon-sm" onClick={copy} disabled={!messages.length} aria-label="Copy transcript" tooltip={copied ? "Copied" : "Copy transcript as Markdown"}><Copy aria-hidden="true" /></Button>
          <Button variant="ghost" size="icon-sm" onClick={fresh} disabled={Boolean(runId) || !messages.length} aria-label="New chat" tooltip="Start a new chat"><MessageSquarePlus aria-hidden="true" /></Button>
          <Button variant="ghost" size="icon-sm" onClick={onClose} aria-label="Close chat" tooltip="Close chat (Ctrl+J)"><X aria-hidden="true" /></Button>
        </div>
      </header>
      {copied ? <p role="status" className="sr-only">Copied as Markdown</p> : null}
      {settingsError ? <div role="alert" className="inline-error chat-error"><TriangleAlert aria-hidden="true" /><p>{settingsError}</p></div> : null}
      {settings && !ready ? (
        <div className="chat-setup" data-testid="chat-setup">
          <p>{settings.reason}</p>
          <p className="muted-copy compact">Choose Anthropic, an OpenAI-compatible endpoint, or a local endpoint such as Ollama. With a local endpoint the chat works offline.</p>
          <Button onClick={onSettings}><Settings />Set up the AI provider</Button>
        </div>
      ) : null}
      {ready ? <>
        <ul className="chat-chips" aria-label="What the chat can see">
          {chips.map((chip) => (
            <Tooltip key={chip.id} content={chip.title} side="bottom">
              <li className={`chat-chip is-${chip.kind}`} data-testid={`context-chip-${chip.kind}`}>
                <span>{chip.kind === "view" ? "View" : chip.kind === "selection" ? "Selected" : "Merge"}: {chip.label}</span>
                <button type="button" aria-label={`Remove ${chip.label} from the chat context`} onClick={() => setRemoved((current) => new Set([...current, chip.id]))}><X aria-hidden="true" /></button>
              </li>
            </Tooltip>
          ))}
          {!chips.length ? <li className="muted-copy compact">No context. The chat sees only what you type and what its tools read.</li> : null}
        </ul>
        <div className="chat-messages" ref={list} aria-live="polite" aria-busy={Boolean(runId)}>
          {!messages.length ? (
            <div className="chat-empty-state">
              <p className="muted-copy chat-empty">Ask about measures, lineage, report usage or the open merge session. The chat reads the project with the same tools as the MCP server and can only propose changes.</p>
              {prompts.length ? (
                <div className="chat-starters" data-testid="chat-starters" aria-label="Suggested starter prompts">
                  <span className="chat-starters-label">Suggested prompts</span>
                  <div className="chat-starters-list">
                    {prompts.map((promptText, index) => (
                      <button
                        key={index}
                        type="button"
                        className="chat-starter-chip"
                        data-testid="chat-starter-prompt"
                        onClick={() => handleStarter(promptText)}
                        title={`Ask: "${promptText}"`}
                      >
                        <Sparkles aria-hidden="true" className="chat-starter-icon" />
                        <span>{promptText}</span>
                      </button>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          ) : null}
          {messages.map((message) => message.role === "user" ? (
            <div key={message.id} className="chat-message is-user"><p>{message.text}</p></div>
          ) : (
            <div key={message.id} className="chat-message is-assistant" data-testid="chat-answer">
              {message.parts.map((part, index) => <AnswerPart key={index} part={part} onObject={onObject} onGraph={onGraph} onMerge={onMerge} />)}
              {!message.done && !answerText(message) ? <p className="loading-label" role="status">Thinking…</p> : null}
              {message.stopReason === "stopped" ? <p className="muted-copy compact">Stopped.</p> : null}
            </div>
          ))}
        </div>
        {error ? <div role="alert" className="inline-error chat-error"><TriangleAlert aria-hidden="true" /><p>{error}</p></div> : null}
        <form className="chat-compose" onSubmit={send}>
          <label htmlFor="chat-input" className="sr-only">Message</label>
          <textarea id="chat-input" ref={input} rows={3} value={text} placeholder="Ask about this project…" maxLength={8000}
            onChange={(event) => setText(event.target.value)}
            onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) send(event); }} />
          {runId ? <Button type="button" variant="outline" onClick={stop}><Square aria-hidden="true" />Stop</Button>
            : <Button type="submit" disabled={!text.trim()}><Send aria-hidden="true" />Send</Button>}
        </form>
      </> : null}
    </aside>
  );
}
