import React, { useEffect, useState } from "react";
import { Check, KeyRound, PlugZap, TriangleAlert } from "lucide-react";
import { Button } from "./ui/button";
import { Card } from "./ui/card";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { NativeSelect, NativeSelectOption } from "./ui/native-select";
import { Switch } from "./ui/switch";

import { getAIStatus } from "../chat";
export { getAIStatus };

// Settings, AI provider (issue #7, #44, #47). Layout aligned with Project settings tab:
// Card.panel.config-panel with settings-section, stacked labels, clean padding and icon alignment.
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
    return <Card className="panel config-panel ai-settings-panel">{error ? <div role="alert" className="inline-error"><TriangleAlert aria-hidden="true" /><p>{error}</p></div> : <p role="status" className="loading-label">Loading AI settings…</p>}</Card>;
  }
  const providers = settings.providers || [];
  const provider = providers.find((item) => item.id === draft.provider) || providers[0];
  const changeProvider = (id) => {
    const next = providers.find((item) => item.id === id);
    setDraft((current) => ({ ...current, provider: id, model: next?.model || "", base_url: next?.base_url || "" }));
    setTest(null);
  };

  const sameEndpoint = draft.provider === settings.provider && draft.base_url === settings.base_url;
  const keySaved = settings.has_key && sameEndpoint;

  // Single-step setup: saving an API key directly enables chat if it was off.
  const save = async (extra = {}) => {
    setBusy(true); setError(""); setNotice(""); setTest(null);
    try {
      const body = { ...draft, ...extra };
      if (apiKey.trim()) {
        body.api_key = apiKey.trim();
        body.enabled = true;
      }
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

  // Instant reactive toggle: toggling chat immediately updates draft & syncs config to backend smoothly.
  const toggleEnabled = async (checked) => {
    setDraft((current) => ({ ...current, enabled: checked }));
    setError(""); setNotice(""); setTest(null);
    try {
      const body = { ...draft, enabled: checked };
      if (apiKey.trim()) body.api_key = apiKey.trim();
      const next = await transport.saveChatSettings(body);
      accept(next);
      setNotice(checked ? "Chat enabled." : "Chat disabled.");
      return next;
    } catch (cause) {
      setError(cause.message || "AI settings could not be saved.");
      return null;
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

  const storeLabel = (settings.key_store || "memory").replace(/\s*\(until PBIBrain closes\)/i, "");
  const status = getAIStatus({ draft, settings, provider, apiKey, keySaved });

  return <Card className="panel config-panel ai-settings-panel">
    <div className="settings-section">
      <div className="settings-section-copy">
        <h3>AI provider</h3>
        <p>The chat panel (Ctrl+J) answers questions about this project and can propose changes in Merge models. It is off until you turn it on here. Nothing is sent anywhere before that.</p>
      </div>
      <div className="ai-settings-fields">
        <Switch id="ai-enabled" label="Turn on the chat" checked={draft.enabled} disabled={busy}
          description="Messages, the context chips you keep, and tool results go to the provider below."
          onCheckedChange={toggleEnabled} />
        <div className="config-field">
          <Label htmlFor="ai-provider"><span>Provider</span></Label>
          <NativeSelect id="ai-provider" value={draft.provider} disabled={busy} onChange={(event) => changeProvider(event.target.value)}>
            {providers.map((item) => <NativeSelectOption key={item.id} value={item.id}>{item.label}</NativeSelectOption>)}
          </NativeSelect>
        </div>
        <div className="config-field">
          <Label htmlFor="ai-model"><span>Model</span></Label>
          <Input id="ai-model" value={draft.model} disabled={busy} placeholder={provider?.model || "model name"} spellCheck={false}
            onChange={(event) => setDraft((current) => ({ ...current, model: event.target.value }))} />
        </div>
        <div className="config-field">
          <Label htmlFor="ai-base-url"><span>Base URL</span></Label>
          <Input id="ai-base-url" value={draft.base_url} disabled={busy} placeholder={provider?.base_url} spellCheck={false}
            onChange={(event) => setDraft((current) => ({ ...current, base_url: event.target.value }))} />
        </div>
        <div className="config-field">
          <Label htmlFor="ai-key"><span>API key{provider?.needs_key ? "" : " (optional)"}</span></Label>
          <Input id="ai-key" type="password" autoComplete="off" value={apiKey} disabled={busy} aria-describedby="ai-key-hint"
            placeholder={keySaved ? "Saved. Type a new key to replace it." : "Paste the key"} onChange={(event) => setApiKey(event.target.value)} />
          <p id="ai-key-hint" className="ai-key-hint">
            <KeyRound aria-hidden="true" className="ai-key-icon" />
            <span>The key is stored in {storeLabel}{settings.key_persistent ? "" : ". It is kept only until PBIBrain closes"}, never in brain.json. A key belongs to its provider and base URL: change the URL and you type the key again.</span>
          </p>
        </div>
      </div>
    </div>
    <div className="config-actions" data-ui-actions="">
      <Button onClick={() => save()} disabled={busy}>{busy ? "Saving…" : "Save"}</Button>
      <Button variant="outline" onClick={runTest} disabled={busy || !draft.model}><PlugZap />Test connection</Button>
      {keySaved ? <Button variant="ghost" onClick={() => save({ clear_key: true })} disabled={busy}>Remove key</Button> : null}
      {status.ready ? (
        <span className="success-text" data-testid="ai-status"><Check aria-hidden="true" />The chat is ready.</span>
      ) : (
        <span className="muted-copy compact" data-testid="ai-status">{status.message}</span>
      )}
      {test ? <span role="status" className={test.ok ? "success-text" : "inline-error-text"}>{test.ok ? <Check aria-hidden="true" /> : <TriangleAlert aria-hidden="true" />}{test.message}</span> : null}
      {error ? <div role="alert" className="inline-error"><TriangleAlert aria-hidden="true" /><p>{error}</p></div> : null}
      {notice ? <span role="status" className="success-text"><Check aria-hidden="true" />{notice}</span> : null}
    </div>
  </Card>;
}
