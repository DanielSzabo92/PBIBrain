// Settings parts: project sources (desktop and served), keyboard preferences, and the source status hook.
import React, { useEffect, useState } from "react";
import { Check, Cloud, FileText, FolderOpen, Plus, ScanLine, X } from "lucide-react";
import { desktopRequest } from "../desktop";
import { CloudSourcePicker } from "../components/CloudSourcePicker";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Card } from "../components/ui/card";
import { Label } from "../components/ui/label";
import { Switch } from "../components/ui/switch";
import { sourceState, sourceStatusMap } from "../sourceStatus";
import { setSlashSearchEnabled, slashSearchEnabled } from "../devcenter/preferences.js";
import { t as devCopy } from "../devcenter/copy.js";
import { EmptyState, PageHeading } from "./shared";

// App setting of the "/" key (UI design 9.3, A24). It is stored in localStorage, as the theme is.
export function KeyboardSettings() {
  const [enabled, setEnabled] = useState(slashSearchEnabled);
  const change = (value) => {
    setEnabled(value);
    setSlashSearchEnabled(value);
  };
  return (
    <Card className="panel settings-keyboard">
      <h2 className="settings-keyboard-title">{devCopy("settings.keyboard.title")}</h2>
      <Switch label={devCopy("settings.slash.label")} description={devCopy("settings.slash.help")} checked={enabled} onCheckedChange={change} />
    </Card>
  );
}

/** Found or not, and what the last scan did, for each saved source. Read again while a scan runs and when it ends. */
export function useSourceStatus(transport, sources, scanning) {
  const [status, setStatus] = useState({});
  const saved = JSON.stringify(sources || []);
  useEffect(() => {
    let active = true;
    if (typeof transport?.getSourceStatus !== "function") return undefined;
    const read = () => transport.getSourceStatus().then((result) => { if (active) setStatus(sourceStatusMap(result)); }).catch(() => {});
    read();
    const timer = scanning ? setInterval(read, 1000) : null;
    return () => { active = false; if (timer) clearInterval(timer); };
  }, [transport, saved, scanning]);
  return status;
}

export function DesktopProjectView({ api, project, overview, config, transport, scanning, onScan, onChange, onRefresh, onSaved }) {
  const sourceStatus = useSourceStatus(transport, config?.sources, scanning);
  const [sourceError, setSourceError] = useState("");
  const [sourceWorking, setSourceWorking] = useState(false);
  const [cloudOpen, setCloudOpen] = useState(false);
  const sources = Array.isArray(config?.sources) ? config.sources : [];
  const cloudSources = Array.isArray(config?.cloud_sources) ? config.cloud_sources : [];
  const removeCloudSource = async (item) => {
    setSourceWorking(true); setSourceError("");
    try {
      const saved = await transport.saveConfig({ ...config, cloud_sources: cloudSources.filter((entry) => entry.item_id !== item.item_id) });
      onSaved(saved);
    } catch (cause) { setSourceError(cause.message || "Cloud source could not be removed"); }
    finally { setSourceWorking(false); }
  };
  const addSources = async () => {
    setSourceWorking(true); setSourceError("");
    try {
      const picked = await desktopRequest(api, "choose_sources");
      if (!picked.sources?.length) return;
      await desktopRequest(api, "add_sources", picked.sources);
      await onRefresh();
    } catch (cause) { setSourceError(cause.message || "Source files could not be added"); }
    finally { setSourceWorking(false); }
  };
  const removeSource = async (source) => {
    setSourceWorking(true); setSourceError("");
    try {
      const saved = await transport.saveConfig({ ...config, sources: sources.filter((item) => item !== source) });
      onSaved(saved);
    } catch (cause) { setSourceError(cause.message || "Source could not be removed"); }
    finally { setSourceWorking(false); }
  };
  return <>
    <PageHeading title={project.name} description="Everything PBIBrain creates stays with this project folder." action={<Button variant="outline" onClick={onChange} disabled={scanning}><FolderOpen />Change project</Button>} />
    <Card className="panel desktop-project-panel">
      <div className="project-location"><div><p className="field-label">Project folder</p><strong title={project.folder}>{project.folder}</strong></div></div>
      <div className="desktop-sources"><div className="panel-heading"><div><h2>Power BI source files</h2></div><Button variant="outline" onClick={addSources} disabled={sourceWorking || scanning} tooltip={scanning ? "Cannot add sources while scan is in progress" : sourceWorking ? "Adding sources…" : undefined}><Plus />{sourceWorking ? "Adding…" : "Add source files"}</Button></div>{sources.length ? <div className="source-list">{sources.map((source) => { const state = sourceState(sourceStatus[source]); return <div className={`desktop-source-row source-${state.tone}`} key={source}><span className="source-state" role="img" aria-label={state.label} title={state.label} /><FileText className="source-icon" aria-hidden="true" /><span title={source}>{source}</span>{state.text ? <small className="source-scan" title={state.label}>{state.text}</small> : null}<Button variant="ghost" size="icon-sm" onClick={() => removeSource(source)} disabled={sourceWorking || scanning} aria-label={`Remove ${source}`}><X /></Button></div>; })}</div> : <EmptyState icon={<FileText />} title="No source files yet" detail="Add or drop .pbip, .bim or model .json files to scan them with this project." />}{sourceError ? <p className="onboarding-error" role="alert">{sourceError}</p> : null}</div>
      {typeof api?.add_cloud_source === "function" || cloudSources.length ? <div className="desktop-sources cloud-sources"><div className="panel-heading"><div><h2>Power BI service items</h2><p className="muted">Cloud semantic models and reports, read with your Microsoft sign-in.</p></div>{typeof api?.add_cloud_source === "function" ? <Button variant="outline" onClick={() => setCloudOpen(true)} disabled={sourceWorking || scanning || cloudOpen}><Cloud />Add cloud item</Button> : null}</div>
        {cloudOpen ? <CloudSourcePicker api={api} onClose={() => setCloudOpen(false)} onAdded={async () => { setCloudOpen(false); await onRefresh(); }} /> : null}
        {cloudSources.length ? <div className="source-list">{cloudSources.map((item) => <div className="desktop-source-row" key={item.item_id}><Cloud className="source-icon" aria-hidden="true" /><span title={`${item.workspace_name} · ${item.name}`}>{item.workspace_name} · {item.name} <span className="muted">({item.kind === "cloud_model" ? "semantic model" : "report"}, {item.access_type})</span></span><Button variant="ghost" size="icon-sm" onClick={() => removeCloudSource(item)} disabled={sourceWorking || scanning} aria-label={`Remove ${item.name}`}><X /></Button></div>)}</div> : null}
      </div> : null}
      <div className="config-actions" data-ui-actions=""><Button onClick={onScan} disabled={scanning} tooltip={scanning ? "Scan in progress" : undefined}><ScanLine />{scanning ? "Scanning…" : "Scan project"}</Button></div>
    </Card>
  </>;
}

/** The last part of a path: the file or folder name, which is what tells sources apart. */
export function sourceName(path) {
  return String(path || "").replace(/[\\/]+$/, "").split(/[\\/]/).pop() || "";
}
export function pathExample() {
  return /win/i.test(globalThis.navigator?.platform || "") ? "C:\\Reports\\Finance\\Finance.pbip" : "/home/me/reports/Finance/Finance.pbip";
}

export function ConfigView({ transport, config, onSaved, onScan, scanning }) {
  const [draft, setDraft] = useState(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  useEffect(() => {
    const loaded = config || {};
    const defaults = { version: 1, name: "PBIBrain project", sources: [], database: "", identity_map: "" };
    const next = { ...defaults, ...loaded };
    setDraft({ ...next, sources: Array.isArray(loaded.sources) ? loaded.sources : [] });
  }, [config]);
  // Which saved paths exist on disk: a wrong path is flagged here, before a scan fails on it.
  const sourceStatus = useSourceStatus(transport, config?.sources, scanning);
  if (!draft) return <Card className="panel"><EmptyState title="Loading configuration" detail="Reading the local project settings." /></Card>;
  const updateSource = (index, value) => setDraft((current) => ({ ...current, sources: current.sources.map((source, sourceIndex) => sourceIndex === index ? value : source) }));
  const dirty = draft.name !== config?.name || JSON.stringify(draft.sources) !== JSON.stringify(config?.sources || []);
  const save = async () => {
    setSaving(true); setMessage("");
    try { const saved = await transport.saveConfig(draft); setDraft(saved); onSaved(saved); setMessage("Saved"); }
    catch (cause) { setMessage(cause.message || "Could not save configuration"); }
    finally { setSaving(false); }
  };
  return <>
    <Card className="panel config-panel">
      <div className="settings-section">
        <div className="settings-section-copy"><h3>Project</h3><p>Shown in the header and in exported context.</p></div>
        <Label className="config-field"><span>Project name</span><Input value={draft.name || ""} onChange={(event) => setDraft({ ...draft, name: event.target.value })} placeholder="Finance reporting" /></Label>
      </div>
      <div className="settings-section config-section">
        <div className="settings-section-copy"><h3>Power BI inputs</h3><p>PBIP project folders or model JSON files, as full paths.</p></div>
        <div className="source-editor">
          {draft.sources.length ? <div className="source-list">{draft.sources.map((source, index) => {
            const state = sourceState(source === config?.sources?.[index] ? sourceStatus[source] : undefined);
            const tone = state.tone;
            return <div className={`source-row source-${tone}`} key={index}>
              <span className="source-state" role="img" aria-label={state.label} title={state.label} />
              <span className="source-name" title={source}><strong>{sourceName(source) || "New source"}</strong>{state.text ? <small className="source-scan" title={state.label}>{state.text}</small> : null}</span>
              <Input value={source} onChange={(event) => updateSource(index, event.target.value)} placeholder={pathExample()} aria-label={`Source ${index + 1}`} aria-invalid={(tone === "bad" && !sourceStatus[source]?.exists) || undefined} />
              <Button variant="ghost" size="icon-sm" onClick={() => setDraft({ ...draft, sources: draft.sources.filter((_, sourceIndex) => sourceIndex !== index) })} aria-label={`Remove source ${index + 1}`}><X /></Button>
            </div>;
          })}</div> : <EmptyState icon={<FileText />} title="No sources" detail="Add a PBIP project or model JSON file." />}
          <Button variant="outline" size="sm" className="add-source" onClick={() => setDraft({ ...draft, sources: [...draft.sources, ""] })}><Plus />Add source</Button>
        </div>
      </div>
      <div className="config-actions" data-ui-actions="">
        <Button
          onClick={save}
          disabled={saving || scanning || !dirty}
          tooltip={saving ? "Saving…" : scanning ? "Cannot save while scan is in progress" : !dirty ? "No configuration changes to save" : undefined}
        >
          {saving ? "Saving…" : "Save configuration"}
        </Button>
        <Button
          variant="outline"
          onClick={onScan}
          disabled={scanning || saving || dirty || !config?.sources?.length}
          tooltip={scanning ? "Scan in progress" : saving ? "Wait for configuration to save" : dirty ? "Save configuration changes before scanning" : !config?.sources?.length ? "Add at least one source file to scan" : undefined}
        >
          <ScanLine />{scanning ? "Scanning…" : "Scan saved sources"}
        </Button>
        {dirty ? <span className="muted-copy compact">Save changes before scanning.</span> : null}
        {message ? <span role={message === "Saved" ? "status" : "alert"} className={message === "Saved" ? "success-text" : "error-copy"}>{message === "Saved" ? <Check aria-hidden="true" /> : null}{message}</span> : null}
      </div>
    </Card>
  </>;
}
