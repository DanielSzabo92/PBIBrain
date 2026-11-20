// The desktop first screens: connecting to the host, and opening a project (recent projects or a folder).
import React, { useCallback, useEffect, useState } from "react";
import { ArrowRight, FolderOpen, RefreshCw, TriangleAlert } from "lucide-react";
import { desktopRequest } from "../desktop";
import BrandMark from "../components/BrandMark";
import { MAKER_NAME } from "../brand";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Card } from "../components/ui/card";
import { Label } from "../components/ui/label";

export function DesktopConnecting({ error, onRetry }) {
  return <main className="onboarding-shell"><Card className="onboarding-card connecting-card" aria-live="polite"><BrandMark size={44} className="onboarding-mark" /><h1>{error ? "Desktop connection needed" : "Opening PBIBrain"}</h1><p className="onboarding-copy">{error || "Preparing your private project workspace."}</p>{error ? <Button onClick={onRetry}><RefreshCw />Retry connection</Button> : <span className="connecting-indicator"><i /><i /><i /><span>Connecting</span></span>}<p className="brand-credit">by {MAKER_NAME}</p></Card></main>;
}

/** The projects opened last (desktop only), read again when the open project changes or the switcher opens. */
export function useRecentProjects(api, openFolder) {
  const [recent, setRecent] = useState([]);
  const reload = useCallback(() => {
    if (!api) return;
    desktopRequest(api, "recent_projects").then((reply) => setRecent(Array.isArray(reply.projects) ? reply.projects : [])).catch(() => setRecent([]));
  }, [api]);
  useEffect(() => { reload(); }, [reload, openFolder]);
  return [recent, reload];
}

export function DesktopOnboarding({ api, error, onOpen, recent = [] }) {
  const [name, setName] = useState("");
  const [folder, setFolder] = useState("");
  const [working, setWorking] = useState(false);
  const [message, setMessage] = useState(error);
  useEffect(() => setMessage(error), [error]);
  const chooseFolder = async () => {
    setWorking(true); setMessage("");
    try {
      const result = await desktopRequest(api, "choose_folder");
      if (result.folder) setFolder(result.folder);
    } catch (cause) { setMessage(cause.message || "Folder picker could not open"); }
    finally { setWorking(false); }
  };
  const openRecent = async (entry) => {
    setWorking(true); setMessage("");
    try { await onOpen(entry.name, entry.folder); }
    catch (cause) { setMessage(cause.message || "Project could not be opened"); }
    finally { setWorking(false); }
  };
  const open = async (event) => {
    event.preventDefault();
    if (!name.trim() || !folder.trim()) { setMessage("Name the project and choose its folder."); return; }
    setWorking(true); setMessage("");
    try { await onOpen(name.trim(), folder.trim()); }
    catch (cause) { setMessage(cause.message || "Project could not be opened"); }
    finally { setWorking(false); }
  };
  return <main className="onboarding-shell">
    <Card className="onboarding-card" aria-labelledby="onboarding-title">
      <BrandMark size={44} className="onboarding-mark" />
      <h1 id="onboarding-title">Start a project brain</h1>
      <p className="onboarding-copy">Choose one folder. PBIBrain keeps the project, scan results, and agent-ready context together.</p>
      {recent.length ? <nav className="onboarding-recent" aria-label="Recent projects">
        <h2>Recent projects</h2>
        <ul>{recent.map((entry) => <li key={entry.folder}><button type="button" disabled={working} onClick={() => openRecent(entry)}><FolderOpen aria-hidden="true" /><span className="recent-name">{entry.name}</span><span className="recent-folder" title={entry.folder}>{entry.folder}</span></button></li>)}</ul>
      </nav> : null}
      <form onSubmit={open} className="onboarding-form">
        <Label className="config-field"><span>Project name</span><Input autoFocus value={name} onChange={(event) => setName(event.target.value)} placeholder="Finance reporting" disabled={working} /></Label>
        <div className="config-field"><Label htmlFor="project-folder">Project folder</Label><div className="folder-picker"><Input id="project-folder" value={folder} onChange={(event) => setFolder(event.target.value)} placeholder="Paste a folder path or browse" title={folder || "Project folder path"} disabled={working} /><Button variant="outline" type="button" onClick={chooseFolder} disabled={working}><FolderOpen />{folder ? "Change folder" : "Choose folder"}</Button></div></div>
        {message ? <p className="onboarding-error" role="alert"><TriangleAlert aria-hidden="true" />{message}</p> : null}
        <Button size="lg" className="onboarding-submit" disabled={working}>{working ? "Opening…" : "Open project"} <ArrowRight aria-hidden="true" /></Button>
      </form>
      <p className="brand-credit">by {MAKER_NAME}</p>
      <p className="onboarding-note">Your Power BI files are read-only until you explicitly apply changes.</p>
    </Card>
  </main>;
}
