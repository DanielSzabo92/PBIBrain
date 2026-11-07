import React, { useEffect, useState } from "react";
import { KeyRound, PlugZap, TriangleAlert } from "lucide-react";
import { Button } from "./ui/button";
import { Card } from "./ui/card";
import { Input } from "./ui/input";
import { NativeSelect, NativeSelectOption } from "./ui/native-select";
import { Switch } from "./ui/switch";

// Settings, AI provider (issue #7). The API key goes to the backend once and is stored in the OS
// credential store; this page only ever learns whether a key is saved (has_key).
export default function AISettings({ transport, onSaved }) {
  const [settings, setSettings] = useState(null);
  const [draft, setDraft] = useState(null);
  const [apiKey, setApiKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [test, setTest] = useState(null);

  const accept = (next) => {
    setSettings(next);
    setDraft({ enabled: next.enabled, provider: next.provider, model: next.model, base_url: next.base_url });
    onSaved?.(next);
  };
  useEffect(() => {
    let live = true;
    transport.getChatSettings().then((next) => { if (live) accept(next); }).catch((cause) => { if (live) setError(cause.message || "AI settings could not be loaded."); });
    return () => { live = false; };
  }, [transport]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!draft) {
    return <Card className="panel ai-settings">{error ? <div role="alert" className="inline-error"><TriangleAlert aria-hidden="true" /><p>{error}</p></div> : <p role="status" className="loading-label">Loading AI settings…</p>}</Card>;
  }
  const providers = settings.providers || [];
  const provider = providers.find((item) => item.id === draft.provider) || providers[0];
  const changeProvider = (id) => {
    const next = providers.find((item) => item.id === id);
    setDraft((current) => ({ ...current, provider: id, model: next?.model || "", base_url: next?.base_url || "" }));
    setTest(null);
  };
  const save = async (extra = {}) => {
    setBusy(true); setError(""); setNotice(""); setTest(null);
    try {
      const body = { ...draft, ...extra };
      if (apiKey.trim()) body.api_key = apiKey.trim();
      const next = await transport.saveChatSettings(body);
      setApiKey("");
      accept(next);
      setNotice(extra.clear_key ? "API key removed." : "AI settings saved.");
      return next;
    } catch (cause) {
      setError(cause.message || "AI settings could not be saved.");
      return null;
    } finally {
      setBusy(false);
    }
  };
  const runTest = async () => {
    const saved = await save();
    if (!saved) return;
    setBusy(true);
    try {
      setTest(await transport.testChatConnection());
    } catch (cause) {
      setTest({ ok: false, message: cause.message || "The connection test failed." });
    } finally {
      setBusy(false);
    }
  };
  const sameEndpoint = draft.provider === settings.provider && draft.base_url === settings.base_url;
  const keySaved = settings.has_key && sameEndpoint;

  return <Card className="panel ai-settings">
    <div className="settings-panel-head"><div><h2>AI provider</h2><p className="muted-copy">The chat panel (Ctrl+J) answers questions about this project and can propose changes in Merge models. It is off until you turn it on here. Nothing is sent anywhere before that.</p></div></div>
    <Switch id="ai-enabled" label="Turn on the chat" checked={draft.enabled} disabled={busy}
      description="Messages, the context chips you keep, and tool results go to the provider below."
      onCheckedChange={(checked) => setDraft((current) => ({ ...current, enabled: checked }))} />
    <div className="ai-settings-grid">
      <label className="ui-field-label" htmlFor="ai-provider">Provider</label>
      <NativeSelect id="ai-provider" value={draft.provider} disabled={busy} onChange={(event) => changeProvider(event.target.value)}>
        {providers.map((item) => <NativeSelectOption key={item.id} value={item.id}>{item.label}</NativeSelectOption>)}
      </NativeSelect>
      <label className="ui-field-label" htmlFor="ai-model">Model</label>
      <Input id="ai-model" value={draft.model} disabled={busy} placeholder={provider?.model || "model name"} spellCheck={false}
        onChange={(event) => setDraft((current) => ({ ...current, model: event.target.value }))} />
      <label className="ui-field-label" htmlFor="ai-base-url">Base URL</label>
      <Input id="ai-base-url" value={draft.base_url} disabled={busy} placeholder={provider?.base_url} spellCheck={false}
        onChange={(event) => setDraft((current) => ({ ...current, base_url: event.target.value }))} />
      <label className="ui-field-label" htmlFor="ai-key">API key{provider?.needs_key ? "" : " (optional)"}</label>
      <Input id="ai-key" type="password" autoComplete="off" value={apiKey} disabled={busy} aria-describedby="ai-key-hint"
        placeholder={keySaved ? "Saved. Type a new key to replace it." : "Paste the key"} onChange={(event) => setApiKey(event.target.value)} />
    </div>
    <p id="ai-key-hint" className="muted-copy compact"><KeyRound aria-hidden="true" className="inline-icon" /> The key is stored in {settings.key_store}{settings.key_persistent ? "" : ". It is kept only until PBIBrain closes"}, never in brain.json. A key belongs to its provider and base URL: change the URL and you type the key again.</p>
    <div className="doc-export-actions" data-ui-actions="">
      <Button onClick={() => save()} disabled={busy}>{busy ? "Saving…" : "Save"}</Button>
      <Button variant="outline" onClick={runTest} disabled={busy || !draft.model}><PlugZap />Test connection</Button>
      {keySaved ? <Button variant="ghost" onClick={() => save({ clear_key: true })} disabled={busy}>Remove key</Button> : null}
    </div>
    {settings.reason ? <p className="muted-copy compact" data-testid="ai-status">{settings.reason}</p> : <p className="success-text" data-testid="ai-status">The chat is ready.</p>}
    {test ? <p role="status" className={test.ok ? "success-text" : "inline-error-text"}>{test.message}</p> : null}
    {error ? <div role="alert" className="inline-error"><TriangleAlert aria-hidden="true" /><p>{error}</p></div> : null}
    {notice ? <p role="status" className="success-text">{notice}</p> : null}
  </Card>;
}
