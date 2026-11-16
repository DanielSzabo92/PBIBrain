import React, { useEffect, useRef, useState } from "react";
import { Check, KeyRound, Plus, PlugZap, RefreshCw, ShieldCheck, Star, TriangleAlert, X } from "lucide-react";
import { Button } from "./ui/button";
import { Card } from "./ui/card";
import { Checkbox } from "./ui/checkbox";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { NativeSelect, NativeSelectOption } from "./ui/native-select";
import { Switch } from "./ui/switch";

import { effortLabel, getAIStatus, modelEfforts } from "../chat";
export { getAIStatus };

// The saved profile of one provider, or its defaults when it was never set up.
function profileDraft(settings, id) {
  const entry = (settings.providers || []).find((item) => item.id === id) || {};
  const saved = settings.profiles?.[id];
  return {
    provider: id,
    model: saved ? saved.model || "" : entry.model || "",
    base_url: saved?.base_url || entry.base_url || "",
    command: saved?.command || "",
    effort: saved?.effort || "",
  };
}

// The rows of the favourites list: the provider's models, then the favourites it does not list.
function favouriteRows(models, favourites) {
  const rows = models.map((item) => ({ id: item.id, label: item.label, efforts: item.efforts || [] }));
  for (const fav of favourites) {
    if (!rows.some((row) => row.id === fav.model)) rows.push({ id: fav.model, label: fav.model || "Default of your plan", efforts: null, custom: true });
  }
  return rows;
}

// Settings, AI provider (issue #7, #44, #47). Layout aligned with Project settings tab:
// Card.panel.config-panel with settings-section, stacked labels, clean padding and icon alignment.
// Each provider keeps its own profile; saving one makes it the chat's default. The favourites
// list narrows the chat's model picker to the models marked here, each with its default effort.
export default function AISettings({ transport, onSaved }) {
  const [settings, setSettings] = useState(null);
  const [draft, setDraft] = useState(null);
  const [apiKey, setApiKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [test, setTest] = useState(null);
  const [catalog, setCatalog] = useState({ provider: "", models: [], source: "", error: "" });
  const [loadingModels, setLoadingModels] = useState(false);
  const [favourites, setFavourites] = useState([]);
  const [favouritesDirty, setFavouritesDirty] = useState(false);
  const [customModel, setCustomModel] = useState("");
  const [favouritesNotice, setFavouritesNotice] = useState("");
  // The provider being edited: a models reply for a provider the user already left is dropped.
  const draftProviderRef = useRef("");

  const accept = (next) => {
    setSettings(next);
    setDraft({ enabled: next.enabled, ...profileDraft(next, next.provider) });
    onSaved?.(next);
  };
  useEffect(() => {
    let live = true;
    transport.getChatSettings().then((next) => { if (live) accept(next); }).catch((cause) => { if (live) setError(cause.message || "AI settings could not be loaded."); });
    return () => { live = false; };
  }, [transport]); // eslint-disable-line react-hooks/exhaustive-deps

  const draftProvider = draft?.provider || "";
  draftProviderRef.current = draftProvider;
  const loadModels = async (id, refresh = false) => {
    if (!id || !transport.getChatModels) return;
    setLoadingModels(true);
    try {
      const reply = await transport.getChatModels(id, refresh);
      setCatalog((current) => (id === draftProviderRef.current ? { ...reply, provider: id } : current));
    } catch (cause) {
      setCatalog((current) => (id === draftProviderRef.current ? { provider: id, models: [], source: "", error: cause.message || "The models could not be listed." } : current));
    } finally {
      setLoadingModels(false);
    }
  };
  useEffect(() => {
    if (!draftProvider) return;
    setCatalog({ provider: draftProvider, models: [], source: "", error: "" });
    setFavourites(settings?.favourites?.[draftProvider] || []);
    setFavouritesDirty(false);
    setFavouritesNotice("");
    setCustomModel("");
    loadModels(draftProvider);
  }, [draftProvider]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!draft) {
    return <Card className="panel config-panel ai-settings-panel">{error ? <div role="alert" className="inline-error"><TriangleAlert aria-hidden="true" /><p>{error}</p></div> : <p role="status" className="loading-label">Loading AI settings…</p>}</Card>;
  }
  const providers = settings.providers || [];
  const provider = providers.find((item) => item.id === draft.provider) || providers[0];
  const changeProvider = (id) => {
    setDraft((current) => ({ ...current, ...profileDraft(settings, id) }));
    setApiKey("");
    setTest(null);
  };

  const cli = provider?.kind === "cli";
  const models = catalog.provider === draft.provider ? catalog.models || [] : [];
  const efforts = modelEfforts(draft.model, models, provider?.efforts);
  const effort = efforts.includes(draft.effort) ? draft.effort : "";
  // A subscription CLI takes no key and no URL: send only what it accepts.
  const fields = (values) => {
    const { base_url: _url, command, ...rest } = values;
    const body = { ...rest, effort: efforts.includes(values.effort) ? values.effort : "" };
    return cli ? { ...body, command: command || "" } : { ...body, base_url: values.base_url };
  };
  const profile = settings.profiles?.[draft.provider];
  const sameEndpoint = profile ? draft.base_url === profile.base_url : draft.provider === settings.provider && draft.base_url === settings.base_url;
  const keySaved = (profile ? profile.has_key : settings.has_key) && sameEndpoint;

  // Single-step setup: saving an API key directly enables chat if it was off.
  const save = async (extra = {}) => {
    setBusy(true); setError(""); setNotice(""); setTest(null);
    try {
      const body = fields({ ...draft, ...extra });
      if (apiKey.trim() && !cli) {
        body.api_key = apiKey.trim();
        body.enabled = true;
      }
      const next = await transport.saveChatSettings(body);
      setApiKey("");
      accept(next);
      setNotice(extra.clear_key ? "API key removed." : "AI settings saved.");
      if (!cli && body.api_key) loadModels(draft.provider, true);
      return next;
    } catch (cause) {
      setError(cause.message || "AI settings could not be saved.");
      return null;
    } finally {
      setBusy(false);
    }
  };

  // The switch saves at once.
  const toggleEnabled = async (checked) => {
    setDraft((current) => ({ ...current, enabled: checked }));
    setError(""); setNotice(""); setTest(null);
    try {
      const body = fields({ ...draft, enabled: checked });
      if (apiKey.trim() && !cli) body.api_key = apiKey.trim();
      const next = await transport.saveChatSettings(body);
      // Keep edits made while this save was in flight (a provider picked right after the switch);
      // only the switch takes the saved value.
      setSettings(next);
      setDraft((current) => ({ ...current, enabled: next.enabled }));
      onSaved?.(next);
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

  // ---- Favourites -----------------------------------------------------------------------
  const rows = favouriteRows(models, favourites);
  const favouriteOf = (id) => favourites.find((item) => item.model === id);
  const changeFavourites = (update) => { setFavourites(update); setFavouritesDirty(true); setFavouritesNotice(""); };
  const toggleFavourite = (row, checked) => changeFavourites((current) => (checked
    ? [...current.filter((item) => item.model !== row.id), { model: row.id, effort: models.find((item) => item.id === row.id)?.default_effort || "" }]
    : current.filter((item) => item.model !== row.id)));
  const setFavouriteEffort = (id, value) => changeFavourites((current) => current.map((item) => (item.model === id ? { ...item, effort: value } : item)));
  const addCustom = (event) => {
    event?.preventDefault();
    const id = customModel.trim();
    if (!id || favouriteOf(id)) { setCustomModel(""); return; }
    changeFavourites((current) => [...current, { model: id, effort: "" }]);
    setCustomModel("");
  };
  const saveFavourites = async () => {
    setBusy(true); setError(""); setFavouritesNotice("");
    try {
      const next = await transport.saveChatSettings({ favourites: { [draft.provider]: favourites } });
      // Only the favourites changed: keep the profile being edited above.
      setSettings(next);
      onSaved?.(next);
      setFavourites(next.favourites?.[draft.provider] || []);
      setFavouritesDirty(false);
      setFavouritesNotice("Favourites saved.");
    } catch (cause) {
      setError(cause.message || "The favourites could not be saved.");
    } finally {
      setBusy(false);
    }
  };

  const storeLabel = (settings.key_store || "memory").replace(/\s*\(until PBIBrain closes\)/i, "");
  const status = getAIStatus({ draft, settings, provider, apiKey, keySaved });
  const listedFrom = catalog.source === "live" ? `Listed by ${provider?.label}.` : catalog.source === "catalog" ? "Built-in list." : "";

  return <Card className="panel config-panel ai-settings-panel">
    <div className="settings-section">
      <div className="settings-section-copy">
        <h3>AI provider</h3>
        <p>The chat panel (Ctrl+J) answers questions about this project and can propose changes in Merge models. It is off until you turn it on here. Nothing is sent anywhere before that.</p>
        <p>Each provider keeps its own settings. The one you save last is the chat's default; the chat can switch to any provider you set up.</p>
      </div>
      <div className="ai-settings-fields">
        <Switch id="ai-enabled" label="Turn on the chat" checked={draft.enabled} disabled={busy}
          description="Messages, the context chips you keep, and tool results go to the provider below."
          onCheckedChange={toggleEnabled} />
        <div className="config-field">
          <Label htmlFor="ai-provider"><span>Provider</span></Label>
          <NativeSelect id="ai-provider" value={draft.provider} disabled={busy} onChange={(event) => changeProvider(event.target.value)}>
            {providers.map((item) => <NativeSelectOption key={item.id} value={item.id}>
              {item.label}{settings.profiles?.[item.id]?.configured ? (item.id === settings.provider ? " (default)" : " (set up)") : ""}
            </NativeSelectOption>)}
          </NativeSelect>
        </div>
        <div className="config-field">
          <Label htmlFor="ai-model"><span>Model</span></Label>
          <Input id="ai-model" value={draft.model} disabled={busy} placeholder={cli ? "Default of your plan" : provider?.model || "model name"} spellCheck={false}
            list="ai-model-options" onChange={(event) => setDraft((current) => ({ ...current, model: event.target.value }))} />
          <datalist id="ai-model-options">
            {models.filter((item) => item.id).map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
          </datalist>
        </div>
        {efforts.length ? <div className="config-field">
          <Label htmlFor="ai-effort"><span>Thinking effort</span></Label>
          <NativeSelect id="ai-effort" value={effort} disabled={busy} aria-describedby="ai-effort-hint"
            onChange={(event) => setDraft((current) => ({ ...current, effort: event.target.value }))}>
            {["", ...efforts].map((level) => <NativeSelectOption key={level} value={level}>{effortLabel(level)}</NativeSelectOption>)}
          </NativeSelect>
          <p id="ai-effort-hint" className="ai-key-hint"><span>Higher effort thinks longer and costs more. Default leaves it to the provider.</span></p>
        </div> : null}
        {cli ? <div className="config-field">
          <Label htmlFor="ai-command"><span>Program (optional)</span></Label>
          <Input id="ai-command" value={draft.command || ""} disabled={busy} placeholder={`${provider.executable} (found on PATH)`} spellCheck={false}
            aria-describedby="ai-cli-hint" onChange={(event) => setDraft((current) => ({ ...current, command: event.target.value }))} />
          <p id="ai-cli-hint" className="ai-key-hint">
            <ShieldCheck aria-hidden="true" className="ai-key-icon" />
            <span>{provider.sign_in} PBIBrain runs it in an empty folder with its own tools turned off: it reads and proposes only through the chat's PBIBrain tools, and never gets an API key.</span>
          </p>
        </div> : null}
        {cli ? null : <><div className="config-field">
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
        </div></>}
      </div>
    </div>
    <div className="config-actions" data-ui-actions="">
      <Button onClick={() => save()} disabled={busy}>{busy ? "Saving…" : "Save"}</Button>
      <Button variant="outline" onClick={runTest} disabled={busy || (!draft.model && !cli)}><PlugZap />Test connection</Button>
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
    <div className="settings-section ai-favourites" data-testid="ai-favourites">
      <div className="settings-section-copy">
        <h3>Favourite models</h3>
        <p>Mark the models of {provider?.label} the chat's model picker offers, each with its default thinking effort. With no favourites the picker offers every model in this list.</p>
        {cli ? <p>Your plan decides which models you can use. Add a model by the name the program takes if it is not listed.</p> : null}
      </div>
      <div className="ai-settings-fields">
        <div className="ai-favourites-head">
          <span className="muted-copy compact">{loadingModels ? "Listing models…" : listedFrom}</span>
          <Button size="sm" variant="ghost" onClick={() => loadModels(draft.provider, true)} disabled={loadingModels}><RefreshCw aria-hidden="true" />Refresh</Button>
        </div>
        {catalog.error ? <p className="ai-key-hint"><TriangleAlert aria-hidden="true" className="ai-key-icon" /><span>The live list failed: {catalog.error}</span></p> : null}
        {rows.length ? <ul className="ai-favourites-list" aria-label={`Models of ${provider?.label}`}>
          {rows.map((row) => {
            const fav = favouriteOf(row.id);
            const levels = row.efforts || provider?.efforts || [];
            const rowId = `ai-fav-${row.id || "default"}`.replace(/[^A-Za-z0-9_-]/g, "-");
            return <li key={row.id || "default"} className={fav ? "is-favourite" : ""} data-testid="ai-favourite-row">
              <Checkbox id={rowId} checked={Boolean(fav)} disabled={busy} onCheckedChange={(checked) => toggleFavourite(row, checked === true)} />
              <label htmlFor={rowId} className="ai-favourite-name">
                <span>{row.label}</span>
                {row.id && row.label !== row.id ? <code>{row.id}</code> : null}
              </label>
              {fav && levels.length ? <NativeSelect size="sm" aria-label={`Default thinking effort of ${row.label}`} value={levels.includes(fav.effort) ? fav.effort : ""} disabled={busy}
                onChange={(event) => setFavouriteEffort(row.id, event.target.value)}>
                {["", ...levels].map((level) => <NativeSelectOption key={level} value={level}>{effortLabel(level)}</NativeSelectOption>)}
              </NativeSelect> : null}
              {row.custom ? <Button size="icon-sm" variant="ghost" aria-label={`Remove ${row.label}`} tooltip="Remove" disabled={busy}
                onClick={() => toggleFavourite(row, false)}><X aria-hidden="true" /></Button> : null}
            </li>;
          })}
        </ul> : <p className="muted-copy compact">{loadingModels ? "" : "No models listed. Add the model names you use."}</p>}
        <form className="ai-favourites-add" onSubmit={addCustom}>
          <Label htmlFor="ai-favourite-custom" className="sr-only">Model name</Label>
          <Input id="ai-favourite-custom" value={customModel} disabled={busy} spellCheck={false} placeholder="Add a model by name"
            onChange={(event) => setCustomModel(event.target.value)} />
          <Button type="submit" variant="outline" size="sm" disabled={busy || !customModel.trim()}><Plus aria-hidden="true" />Add</Button>
        </form>
      </div>
    </div>
    <div className="config-actions" data-ui-actions="">
      <Button onClick={saveFavourites} disabled={busy || !favouritesDirty}><Star aria-hidden="true" />Save favourites</Button>
      <span className="muted-copy compact">{favourites.length ? `${favourites.length} favourite${favourites.length === 1 ? "" : "s"} for ${provider?.label}.` : `No favourites for ${provider?.label}: the picker shows every listed model.`}</span>
      {favouritesNotice ? <span role="status" className="success-text"><Check aria-hidden="true" />{favouritesNotice}</span> : null}
    </div>
  </Card>;
}
