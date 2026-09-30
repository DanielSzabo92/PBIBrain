import VisualBindings from "./components/VisualBindings";
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { brainTransport, normalizeSnapshot } from "./transport";
import { desktopRequest, subscribeToDesktopBridge } from "./desktop";
import NavIcon from "./NavIcon";
import { objectName, objectScope, readableText, publicProperties, scopeChoices, statusLabel, suggestionLabel } from "./presentation";
import { Button } from "./components/ui/button";
import { Input } from "./components/ui/input";
import { NativeSelect } from "./components/ui/native-select";
import { Badge } from "./components/ui/badge";
import { Card } from "./components/ui/card";
import { Label } from "./components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "./components/ui/tabs";
import GraphView from "./components/GraphView";
import GraphColors from "./components/GraphColors";
import ModelSummary from "./components/ModelSummary";
import { artifactColor, normalizeColors, typeLabel } from "./graphPresentation";

const VIEWS = [
  ["overview", "Overview"],
  ["search", "Search"],
  ["graph", "Graph"],
  ["inspector", "Inspector"],
  ["review", "Review queue"],
  ["config", "Settings"],
];

const EDGE_COLORS = {
  DEPENDS_ON: "#8cb9ff",
  REFERENCES: "#83d7bd",
  USES: "#e8b879",
  CONTROLLED_BY: "#de9cff",
  OBSERVED_WITH: "#8997a7",
};


function confidence(value) {
  if (value == null || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? Math.round(number * 100) : null;
}

function statusClass(value) {
  return String(value || "factual").toLowerCase().replace(/[^a-z]+/g, "-");
}

function labelFor(node) {
  return objectName(node);
}

function itemTarget(item) {
  const value = item?.target || item?.target_id || item?.object || item?.object_id || item?.source_object;
  return value && typeof value === "object" ? value.id || value.object_id : value;
}

function safeJson(value) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function formatEvidence(value) {
  return readableText(value) || "No explanation recorded.";
}

function numberOr(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function itemConfidence(item) {
  return numberOr(item?.confidence ?? item?.properties?.confidence, 0);
}

function itemImpact(item) {
  const raw = item?.impact ?? item?.impact_score ?? item?.properties?.impact ?? item?.properties?.impact_score;
  const value = raw && typeof raw === "object" ? raw.score ?? raw.value : raw;
  if (typeof value === "string") {
    const rank = { critical: 4, high: 3, medium: 2, normal: 2, low: 1, none: 0 }[value.trim().toLowerCase()];
    if (rank !== undefined) return rank;
  }
  return numberOr(value, 0);
}

function dataCounts(nodes, edges, candidates, conflicts) {
  const isOpen = (item) => !["approved", "rejected", "overridden"].includes(String(item.status || "candidate").toLowerCase());
  return {
    models: nodes.filter((node) => node.type === "MODEL").length,
    reports: nodes.filter((node) => node.type === "REPORT").length,
    objects: nodes.length,
    edges: edges.length,
    candidates: candidates.filter(isOpen).length,
    warnings: conflicts.filter(isOpen).length,
  };
}

const scopeOptions = scopeChoices;

function searchObject(item) {
  return item?.object && typeof item.object === "object" ? item.object : item;
}

function searchMatch(item) {
  const match = item?.match || {};
  const field = match.evidence?.[0]?.field || match.field || item?.match_field || "";
  return /expression/i.test(field) ? "In formula" : /description/i.test(field) ? "In description" : "Open →";
}

function App({ transport = brainTransport }) {
  const desktopHost = Boolean(globalThis.__PBIBRAIN_DESKTOP__);
  const [snapshot, setSnapshot] = useState(() => normalizeSnapshot(null));
  const [snapshotLoaded, setSnapshotLoaded] = useState(false);
  const [overview, setOverview] = useState({});
  const [config, setConfig] = useState(null);
  const graphColors = useMemo(() => normalizeColors(config?.graph_colors), [config?.graph_colors]);
  const [view, setView] = useState("overview");
  const [searchSession, setSearchSession] = useState({ query: "", modelId: "", reportId: "", result: null });
  const [inspectorSession, setInspectorSession] = useState({ query: "", modelId: "", reportId: "", objectType: "MEASURE", result: null });
  const [settingsTab, setSettingsTab] = useState("colors");
  const [inspectorOrigin, setInspectorOrigin] = useState("search");
  const [selectedId, setSelectedId] = useState(null);
  const [inspectedObject, setInspectedObject] = useState(null);
  const [inspectedDetails, setInspectedDetails] = useState(null);
  const [inspectorError, setInspectorError] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [operationError, setOperationError] = useState("");
  const [notice, setNotice] = useState("");
  useEffect(() => {
    if (!notice) return undefined;
    const timer = setTimeout(() => setNotice(""), 3000);
    return () => clearTimeout(timer);
  }, [notice]);
  const [desktopApi, setDesktopApi] = useState(null);
  const [desktopSession, setDesktopSession] = useState(null);
  const [desktopError, setDesktopError] = useState("");
  const [desktopState, setDesktopState] = useState(() => desktopHost ? "connecting" : "browser");
  const [bridgeAttempt, setBridgeAttempt] = useState(0);
  const [scanning, setScanning] = useState(false);
  const loadRequest = useRef(0);
  const snapshotRequest = useRef(0);
  const selectionRequest = useRef(0);
  const scanInFlight = useRef(false);

  const load = useCallback(async () => {
    const requestId = ++loadRequest.current;
    setLoading(true);
    setError("");
    const [overviewResult, configResult] = await Promise.allSettled([transport.getOverview(), transport.getConfig()]);
    if (requestId !== loadRequest.current) return;
    if (overviewResult.status === "fulfilled") setOverview(overviewResult.value || {});
    if (configResult.status === "fulfilled") setConfig(configResult.value || {});
    if (overviewResult.status === "rejected") {
      setError(overviewResult.reason?.message || "Brain could not be loaded");
    }
    setLoading(false);
  }, [transport]);

  const loadSnapshot = useCallback(async () => {
    const requestId = ++snapshotRequest.current;
    try {
      const next = normalizeSnapshot(await transport.getSnapshot());
      if (requestId === snapshotRequest.current) {
        setSnapshot(next);
        setSnapshotLoaded(true);
      }
      return next;
    } catch (cause) {
      if (requestId === snapshotRequest.current) setOperationError(cause.message || "Review data could not be loaded");
      throw cause;
    }
  }, [transport]);

  useEffect(() => {
    if (!desktopHost) return undefined;
    let disposed = false;
    let settled = false;
    let timeout = null;
    setDesktopState("connecting");
    setDesktopError("");
    const stop = subscribeToDesktopBridge((api) => {
      desktopRequest(api, "get_session")
        .then((session) => {
          if (disposed || settled) return;
          settled = true;
          if (timeout) clearTimeout(timeout);
          setDesktopApi(api);
          setDesktopSession(session);
          setDesktopState("ready");
        })
        .catch((cause) => {
          if (disposed || settled) return;
          settled = true;
          if (timeout) clearTimeout(timeout);
          setDesktopState("failed");
          setDesktopError(cause.message || "PBIBrain could not start its desktop service.");
        });
    });
    timeout = setTimeout(() => {
      if (disposed || settled) return;
      settled = true;
      setDesktopState("failed");
      setDesktopError("PBIBrain could not connect to its desktop service. Retry the connection or restart the app.");
    }, 7000);
    return () => { disposed = true; if (timeout) clearTimeout(timeout); stop(); };
  }, [bridgeAttempt, desktopHost]);

  useEffect(() => {
    if (!desktopHost || desktopSession?.project) load();
  }, [desktopHost, desktopSession?.project, load]);

  const invalidateProjectRequests = useCallback(() => {
    loadRequest.current += 1;
    snapshotRequest.current += 1;
    selectionRequest.current += 1;
  }, []);

  const resetProjectView = useCallback(() => {
    invalidateProjectRequests();
    setSnapshot(normalizeSnapshot(null));
    setSnapshotLoaded(false);
    setOverview({});
    setConfig(null);
    setSearchSession({ query: "", modelId: "", reportId: "", result: null });
    setInspectorOrigin("search");
    setInspectorSession({ query: "", modelId: "", reportId: "", objectType: "MEASURE", result: null });
    setSelectedId(null);
    setInspectedObject(null);
    setInspectedDetails(null);
    setInspectorError("");
    setError("");
    setOperationError("");
    setNotice("");
    setView("overview");
  }, [invalidateProjectRequests]);

  const openDesktopProject = useCallback(async (name, folder) => {
    if (!desktopApi) return;
    setDesktopError("");
    resetProjectView();
    const session = await desktopRequest(desktopApi, "open_project", name, folder);
    setDesktopSession(session);
    if (session.source_count === 0) { setSettingsTab("project"); setView("config"); }
    setNotice("Project ready");
  }, [desktopApi, resetProjectView]);

  const closeDesktopProject = useCallback(async () => {
    if (!desktopApi) return;
    if (scanInFlight.current) {
      setDesktopError("Wait for the project scan to finish before changing projects.");
      return;
    }
    setDesktopError("");
    invalidateProjectRequests();
    try {
      const session = await desktopRequest(desktopApi, "close_project");
      setDesktopSession(session);
      resetProjectView();
    } catch (cause) {
      setDesktopError(cause.message || "Project could not be closed");
    }
  }, [desktopApi, invalidateProjectRequests, resetProjectView]);

  const nodes = snapshot.nodes;
  const edges = snapshot.edges;
  const candidates = snapshot.semantic_candidates;
  const conflicts = snapshot.conflicts;
  const selected = inspectedObject || nodes.find((node) => node.id === selectedId) || null;
  const counts = useMemo(() => {
    const current = dataCounts(nodes, edges, candidates, conflicts);
    return { ...current, models: numberOr(overview.models, current.models), reports: numberOr(overview.reports, current.reports), objects: numberOr(overview.counts?.nodes ?? overview.objects, current.objects), edges: numberOr(overview.counts?.edges ?? overview.edges, current.edges), candidates: numberOr(overview.candidate_count, current.candidates), warnings: numberOr(overview.warning_count, current.warnings) };
  }, [candidates, conflicts, edges, nodes, overview]);

  const selectNode = useCallback(async (id, nextView = "inspector") => {
    const requestId = ++selectionRequest.current;
    setSelectedId(id);
    setInspectedObject(null);
    setInspectedDetails(null);
    setInspectorError("");
    if (view !== "inspector") setInspectorOrigin(view);
    if (nextView) setView(nextView);
    try {
      const result = await transport.getObject(id);
      if (requestId !== selectionRequest.current) return;
      setInspectedObject(result?.object || result?.item || result);
      setInspectedDetails(result);
      loadSnapshot().catch(() => {});
    } catch (cause) {
      if (requestId !== selectionRequest.current) return;
      setInspectedObject(null);
      setInspectorError(cause.message || "Object could not be loaded");
    }
  }, [loadSnapshot, transport, view]);

  const applyScan = useCallback(async () => {
    if (scanInFlight.current) return;
    scanInFlight.current = true;
    setScanning(true);
    setLoading(true);
    setOperationError("");
    try {
      const result = await transport.scan();
      selectionRequest.current += 1;
      snapshotRequest.current += 1;
      if (result?.overview) setOverview(result.overview);
      setSelectedId(null);
      setInspectedObject(null);
      setInspectedDetails(null);
      setInspectorError("");
      setSnapshot(normalizeSnapshot(null));
      setSnapshotLoaded(false);
      setInspectorSession((current) => ({ ...current, result: null, revision: (current.revision || 0) + 1 }));
      setSearchSession((current) => ({ ...current, result: null, selectedId: null, scrollY: 0, revision: (current.revision || 0) + 1 }));
      setNotice("Scan complete");
      await load();
    } catch (cause) {
      setOperationError(cause.message || "Scan failed");
    } finally {
      scanInFlight.current = false;
      setScanning(false);
      setLoading(false);
    }
  }, [load, transport]);

  const review = useCallback(
    async (action, item, value = undefined) => {
      const target = itemTarget(item);
      if (!target) return;
      const stale = item?.issue === "stale" || item?.issue_type === "stale" || item?.status === "stale";
      const reviewId = item?.review_id || item?.override_id || item?.id;
      const candidateId = item?.properties?.candidate_id || item?.item?.candidate_id || item?.item?.properties?.candidate_id || reviewId;
      const property = item?.override_property || item?.property || item?.item?.property || item?.meaning_type || "business_concept";
      const actionValue = value === undefined ? item?.value ?? item?.item?.value : value;
      setNotice("");
      try {
        const payload = {
          target,
          candidate_id: candidateId,
          review_id: reviewId,
          value: actionValue,
          property,
        };
        if (stale) {
          payload.override_id = reviewId;
          payload.override_record = item.item || item;
        }
        const result = await transport.review(action, {
          ...payload,
        });
        const returned = result?.snapshot || result?.brain;
        if (returned) setSnapshot(normalizeSnapshot(returned));
        else {
          setSnapshot((current) => ({
            ...current,
            semantic_candidates: current.semantic_candidates.map((candidate) =>
              candidate.id === item.id ? { ...candidate, value: value === undefined ? candidate.value : value, status: action === "approve" ? "approved" : action === "reject" ? "rejected" : action === "override" ? "overridden" : candidate.status || "candidate" } : candidate,
            ),
          }));
        }
        setNotice({ approve: "Suggestion approved", reject: "Suggestion rejected", edit: "Suggestion updated", override: "Meaning updated", remove: "Saved decision removed" }[action] || "Review updated");
        await Promise.all([loadSnapshot(), load()]);
        return true;
      } catch (cause) {
        setNotice("Review failed. Try again.");
        return false;
      }
    },
    [transport, loadSnapshot, load],
  );

  if (desktopHost && desktopState !== "ready") {
    return <DesktopConnecting error={desktopError} onRetry={() => setBridgeAttempt((attempt) => attempt + 1)} />;
  }

  if (desktopApi && !desktopSession?.project) {
    return <DesktopOnboarding api={desktopApi} error={desktopError} onOpen={openDesktopProject} />;
  }

  const activeProject = desktopSession?.project;
  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand-mark" aria-hidden="true">PB</div>
        <div>
          <p className="eyebrow">PBIBRAIN</p>
          <h1>{activeProject?.name || config?.name || "PBIBrain"}</h1>
        </div>
        <div className="topbar-spacer" />
        <span className={`connection-dot ${loading ? "is-loading" : error ? "is-error" : "is-ready"}`} />
        <span className="connection-label">{loading ? "Loading" : error ? "Offline" : "Connected"}</span>
        {activeProject ? <Button variant="ghost" className="project-switch" onClick={closeDesktopProject} disabled={scanning}>Change project</Button> : null}
        <Button variant="ghost" size="icon" onClick={() => { setInspectorSession((current) => ({ ...current, result: null, revision: (current.revision || 0) + 1 })); setSearchSession((current) => ({ ...current, result: null, revision: (current.revision || 0) + 1 })); load(); if (view === "inspector" && selectedId) selectNode(selectedId); }} title="Reload Brain" aria-label="Reload Brain">↻</Button>
      </header>

      <div className="workspace">
        <aside className="sidebar">
          <nav aria-label="Main navigation">
            {VIEWS.map(([key, label]) => (
              <Button variant="ghost" key={key} aria-current={view === key ? "page" : undefined} className={`nav-button ${view === key ? "active" : ""}`} onClick={() => { setView(key); if (key === "review") loadSnapshot().catch(() => {}); }}>
                <NavIcon name={key} />
                {label}
                {key === "review" && counts.candidates + counts.warnings > 0 ? <span className="nav-pending" aria-label="Pending reviews" /> : null}
              </Button>
            ))}
          </nav>
        </aside>

        <main className={`content ${view === "graph" ? "content-graph" : ""}`}>
          {notice ? <div className="toast" role="status">{notice}</div> : null}
          {error || operationError || desktopError ? (
            <div className="error-banner" role="alert">
              <span>{readableText(error || operationError || desktopError)}</span>
              {error ? <Button variant="link" onClick={load}>Retry</Button> : null}
            </div>
          ) : null}
          {view === "overview" ? <Overview onSelect={selectNode} overview={overview} config={config} counts={counts} loading={loading} onView={setView} onSearch={(query) => { setSearchSession({ query, modelId: "", reportId: "", result: null }); setView("search"); }} onSources={() => { setSettingsTab("project"); setView("config"); }} onScan={applyScan} scanning={scanning} scanLabel={activeProject ? "Scan project" : "Scan sources"} onReview={() => { setView("review"); loadSnapshot().catch(() => {}); }} /> : null}
          {view === "search" ? <SearchView session={searchSession} onSession={setSearchSession} colors={graphColors} transport={transport} overview={overview} onSelect={selectNode} /> : null}
          {view === "graph" ? <GraphView colors={graphColors} transport={transport} overview={overview} snapshot={snapshot} selectedId={selectedId} onSelect={selectNode} /> : null}
          {view === "inspector" ? selectedId ? <><Button variant="ghost" className="inspector-back" onClick={() => { if (inspectorOrigin === "inspector") { setSelectedId(null); setInspectedObject(null); } else setView(inspectorOrigin); }}><span aria-hidden="true">←</span>{inspectorOrigin === "search" ? "Back to results" : inspectorOrigin === "inspector" ? "Browse objects" : `Back to ${VIEWS.find(([key]) => key === inspectorOrigin)?.[1]?.toLowerCase() || "overview"}`}</Button><Inspector key={selectedId} colors={graphColors} node={selected} details={inspectedDetails} loading={Boolean(selectedId && !inspectedDetails && !inspectorError)} error={inspectorError} snapshot={snapshot} snapshotLoaded={snapshotLoaded} overview={overview} onSelect={selectNode} onRetry={() => selectNode(selectedId)} onReview={review} onGraph={() => setView("graph")} /></> : <SearchView browse session={inspectorSession} onSession={setInspectorSession} colors={graphColors} transport={transport} overview={overview} onSelect={(id) => { setInspectorOrigin("inspector"); selectNode(id); }} /> : null}
          {view === "review" ? <ReviewQueue snapshot={snapshot} loading={!snapshotLoaded} overview={overview} onSelect={selectNode} onReview={review} /> : null}
          {view === "config" ? <Tabs value={settingsTab} onValueChange={setSettingsTab} className="settings-tabs">
            <TabsList aria-label="Settings sections"><TabsTrigger value="colors">Graph colors</TabsTrigger><TabsTrigger value="project">Project</TabsTrigger><TabsTrigger value="summary">Model summary</TabsTrigger></TabsList>
            <TabsContent value="colors"><GraphColors config={config} transport={transport} overview={overview} onSaved={setConfig} /></TabsContent>
            <TabsContent value="summary"><ModelSummary overview={overview} transport={transport} scanning={scanning} /></TabsContent>
            <TabsContent value="project">{activeProject ? <DesktopProjectView api={desktopApi} project={activeProject} overview={overview} config={config} transport={transport} scanning={scanning} onScan={applyScan} onChange={closeDesktopProject} onRefresh={load} onSaved={setConfig} /> : <ConfigView transport={transport} config={config} onSaved={setConfig} onScan={applyScan} />}</TabsContent></Tabs> : null}
        </main>
      </div>
    </div>
  );
}

function DesktopConnecting({ error, onRetry }) {
  return <main className="onboarding-shell"><Card className="block gap-0 p-0 shadow-none onboarding-card connecting-card" aria-live="polite"><div className="brand-mark onboarding-mark" aria-hidden="true">PB</div><p className="eyebrow">PBIBRAIN</p><h1>{error ? "Desktop connection needed" : "Opening PBIBrain"}</h1><p className="onboarding-copy">{error || "Preparing your private project workspace."}</p>{error ? <Button onClick={onRetry}>Retry connection</Button> : <span className="connecting-indicator"><i />Connecting</span>}</Card></main>;
}

function DesktopOnboarding({ api, error, onOpen }) {
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
  const open = async (event) => {
    event.preventDefault();
    if (!name.trim() || !folder.trim()) { setMessage("Name the project and choose its folder."); return; }
    setWorking(true); setMessage("");
    try { await onOpen(name.trim(), folder.trim()); }
    catch (cause) { setMessage(cause.message || "Project could not be opened"); }
    finally { setWorking(false); }
  };
  return <main className="onboarding-shell">
    <Card className="block gap-0 p-0 shadow-none onboarding-card" aria-labelledby="onboarding-title">
      <div className="brand-mark onboarding-mark" aria-hidden="true">PB</div>
      <p className="eyebrow">PBIBRAIN</p>
      <h1 id="onboarding-title">Start a project brain</h1>
      <p className="onboarding-copy">Choose one folder. PBIBrain keeps the project, scan results, and agent-ready context together.</p>
      <form onSubmit={open} className="onboarding-form">
        <Label className="config-field"><span>Project name</span><Input autoFocus value={name} onChange={(event) => setName(event.target.value)} placeholder="Finance reporting" disabled={working} /></Label>
        <div className="config-field"><Label htmlFor="project-folder">Project folder</Label><div className="folder-picker"><Input id="project-folder" value={folder} onChange={(event) => setFolder(event.target.value)} placeholder="Paste a folder path or browse" title={folder || "Project folder path"} disabled={working} /><Button variant="ghost" type="button" className="secondary-button" onClick={chooseFolder} disabled={working}>{folder ? "Change folder" : "Choose folder"}</Button></div></div>
        {message ? <p className="onboarding-error" role="alert">{message}</p> : null}
        <Button variant="ghost" className="primary-button onboarding-submit" disabled={working}>{working ? "Opening…" : "Open project"} <span>→</span></Button>
      </form>
      <p className="onboarding-note">Scan when the project opens.</p>
    </Card>
  </main>;
}

function DesktopProjectView({ api, project, overview, config, transport, scanning, onScan, onChange, onRefresh, onSaved }) {
  const [sourceError, setSourceError] = useState("");
  const [sourceWorking, setSourceWorking] = useState(false);
  const sources = Array.isArray(config?.sources) ? config.sources : [];
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
    <PageHeading kicker="Desktop project" title={project.name} description="Everything PBIBrain creates stays with this project folder." action={<Button variant="outline" onClick={onChange} disabled={scanning}>Change project</Button>} />
    <Card className="block gap-0 p-0 shadow-none panel desktop-project-panel">
      <div className="project-location"><span className="project-location-icon" aria-hidden="true">⌂</span><div><p className="eyebrow">Project folder</p><strong title={project.folder}>{project.folder}</strong></div></div>
      <div className="desktop-sources"><div className="panel-heading"><div><p className="eyebrow">Power BI inputs</p><h3>Source files</h3></div><Button variant="outline" onClick={addSources} disabled={sourceWorking || scanning}>{sourceWorking ? "Adding…" : "Add source files"}</Button></div>{sources.length ? <div className="source-list">{sources.map((source) => <div className="desktop-source-row" key={source}><span title={source}>{source}</span><Button variant="ghost" size="icon" onClick={() => removeSource(source)} disabled={sourceWorking || scanning} aria-label={`Remove ${source}`}>×</Button></div>)}</div> : <p className="muted-copy">Add PBIP projects or model JSON files to scan them with this project.</p>}{sourceError ? <p className="onboarding-error" role="alert">{sourceError}</p> : null}</div>
      <div className="config-actions"><Button onClick={onScan} disabled={scanning}>{scanning ? "Scanning…" : "Scan project"}</Button></div>
    </Card>
  </>;
}

function PageHeading({ kicker, title, description, action }) {
  return (
    <div className="page-heading">
      <div>
        {kicker ? <p className="eyebrow">{kicker}</p> : null}
        <h2>{title}</h2>
        {description ? <p className="page-description">{description}</p> : null}
      </div>
      {action}
    </div>
  );
}

function Overview({ overview, config, counts, loading, onView, onSearch, onSources, onScan, onReview, onSelect, scanning, scanLabel }) {
  const [query, setQuery] = useState("");
  const hasObjects = counts.objects > 0;
  const hasSources = Boolean(config?.sources?.length);
  const sourceCount = config?.sources?.length;
  const lastScan = overview.last_scan;
  const validationState = overview.validation_state || "not_run";
  const validationLabel = { valid: "Graph validation passed", invalid: "Graph validation failed", warning: "Graph validation warnings", not_run: "Graph validation not run" }[validationState] || "Graph validation unavailable";
  const issues = overview.validation_issues || [];
  return <>
    <Card className="project-start mb-5" role={validationState === "invalid" ? "alert" : "status"}>
      <h3>{validationLabel}</h3>
      <p className="muted-copy">{validationState === "not_run" ? "Scan sources to check graph validity." : validationState === "invalid" ? "Sources were extracted, but graph issues need attention." : "Graph validity is checked separately from source extraction and review decisions."}</p>
      {issues.length ? <details><summary>View validation issues ({issues.length})</summary><ul>{issues.map((item, index) => <li key={`${item.code}-${index}`}><strong>{item.severity}</strong>: {item.message}{item.object_id || item.from_id || item.to_id ? <Button variant="link" onClick={() => onSelect(item.object_id || item.from_id || item.to_id, "inspector")}>Inspect affected object</Button> : null}</li>)}</ul></details> : null}
    </Card>
    {loading && !hasObjects ? <p role="status" className="muted-copy">{scanning ? "Scanning sources…" : "Loading project…"}</p> : !hasObjects ?
      <Card className="project-start">
        <NavIcon name="config" />
        <h3>{hasSources ? "Ready for the first scan" : "Add your project sources"}</h3>
        <p>{hasSources ? "Scan your files to find models, reports, and their dependencies." : "Choose your PBIP project or exported model and report files."}</p>
        <Button onClick={hasSources ? onScan : onSources} disabled={!config || scanning}>{hasSources ? scanLabel : "Add sources"}</Button>
      </Card> : <>
        <Card className="project-search-card">
          <Label htmlFor="project-search">Find an object</Label>
          <form className="project-search-form" onSubmit={(event) => { event.preventDefault(); if (query.trim()) onSearch(query.trim()); }}>
            <Input type="search" id="project-search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Measure, table, column, or visual…" />
            <Button type="submit" aria-label="Search project" disabled={!query.trim()}>Search <span aria-hidden="true">→</span></Button>
          </form>
          <Button variant="link" className="project-graph-link" onClick={() => onView("graph")}><NavIcon name="graph" />Explore relationships in the graph <span aria-hidden="true">→</span></Button>
        </Card>
        <dl className="project-counts" aria-label="Project counts">
          {[["Models", counts.models], ["Reports", counts.reports], ["Objects", counts.objects], ["Relationships", counts.edges]].map(([label, count]) => <div key={label}><dt>{label}</dt><dd>{count.toLocaleString()}</dd></div>)}
        </dl>
        <Card className="project-review-card">
          <div><h3>{validationState === "invalid" ? "Resolve graph issues before review" : counts.candidates || counts.warnings ? "Ready for review" : "No pending reviews"}</h3><p>{counts.candidates || counts.warnings ? "Check suggested meanings and resolve uncertain matches." : "All suggestions have been reviewed."}</p></div>
          <Button variant="outline" onClick={onReview}>Open review queue <span aria-hidden="true">→</span></Button>
        </Card>
      </>}
    <div className="project-scan-bar">
      <div><strong>{scanning ? "Scanning sources…" : hasObjects ? "Sources indexed" : "Sources"}</strong><span>{sourceCount === undefined ? "Source settings unavailable" : `${sourceCount} ${sourceCount === 1 ? "source" : "sources"}`}{hasObjects ? ` · ${lastScan ? `Last scan ${formatDate(lastScan)}` : "Last scan time unavailable"}` : ""}</span></div>
      <div className="project-scan-actions"><Button variant="ghost" onClick={onSources}>Manage sources</Button>{hasObjects ? <Button variant="outline" onClick={onScan} disabled={scanning || !hasSources}>{scanning ? "Scanning…" : scanLabel}</Button> : null}</div>
    </div>
  </>;
}

function SearchView({ transport, overview, onSelect, colors, session, onSession, browse = false }) {
  const { query, modelId, reportId, objectType = "" } = session;
  const [pending, setPending] = useState(false);
  const [failure, setFailure] = useState(null);
  const request = useRef(0);
  const inFlight = useRef(null);
  const panel = useRef(null);
  const latest = useRef(session);
  latest.current = session;
  const revision = session.revision || 0;
  const key = JSON.stringify([query.trim(), modelId, reportId, objectType, revision]);
  const requestedKey = useRef(key);
  requestedKey.current = key;
  const result = session.result?.key === key ? session.result.data : null;
  const error = failure?.key === key ? failure : null;
  const loading = pending || Boolean((browse || query.trim()) && !result && !error);
  const change = (values) => onSession((current) => ({ ...current, ...values, selectedId: null, scrollY: 0 }));
  const runSearch = useCallback(async (offset = 0) => {
    if ((!browse && !query.trim()) || inFlight.current?.key === key) return;
    const requestId = ++request.current;
    inFlight.current = { key, requestId };
    setPending(true); setFailure(null);
    try {
      const next = await transport.search({ query: query.trim(), modelId, reportId, objectType, offset });
      if (requestId !== request.current || requestedKey.current !== key) return;
      onSession((current) => {
        if (JSON.stringify([current.query.trim(), current.modelId, current.reportId, current.objectType || "", current.revision || 0]) !== key) return current;
        const previous = offset && current.result?.key === key ? current.result.data.items : [];
        const items = [...new Map([...previous, ...(next.items || [])].map((item) => [searchObject(item).id, item])).values()];
        return { ...current, result: { key, data: { ...next, items } } };
      });
    } catch (cause) {
      if (requestId === request.current && requestedKey.current === key) setFailure({ key, offset, message: cause.message || "Search failed" });
    } finally {
      if (requestId === request.current) { setPending(false); inFlight.current = null; }
    }
  }, [key, modelId, query, reportId, objectType, transport, onSession, browse]);
  useEffect(() => {
    setPending(false);
    if ((!browse && !query.trim()) || latest.current.result?.key === key) return undefined;
    const timer = setTimeout(() => runSearch(), 220);
    return () => { clearTimeout(timer); request.current += 1; inFlight.current = null; };
  }, [key, query, runSearch, browse]);
  useEffect(() => {
    const frame = requestAnimationFrame(() => {
      const current = latest.current;
      const selected = [...(panel.current?.querySelectorAll("[data-result-id]") || [])].find((element) => element.dataset.resultId === current.selectedId);
      if (selected) { selected.focus({ preventScroll: true }); window.scrollTo(0, current.scrollY || 0); }
      else panel.current?.querySelector("input")?.focus({ preventScroll: true });
    });
    return () => { cancelAnimationFrame(frame); request.current += 1; };
  }, []);
  const models = scopeOptions(overview, "model");
  const reports = scopeOptions(overview, "report");
  const scopeName = (object) => [...models, ...reports].find((item) => item.id === (object.report_id || object.model_id))?.name;
  return <div ref={panel}>
    <Card className="block gap-0 p-0 shadow-none panel search-panel" aria-busy={loading}>
      <div className="graph-toolbar search-toolbar">
        <Label className="search-field"><NavIcon name="search" /><Input type="search" value={query} onChange={(event) => change({ query: event.target.value })} onKeyDown={(event) => { if (event.key === "Enter") runSearch(); }} placeholder="Measure, table, column, or visual…" aria-label="Search the brain" /></Label>
        <Label className="select-field"><span>Model</span><NativeSelect aria-label="Model" value={modelId} onChange={(event) => change({ modelId: event.target.value, reportId: "" })}><option value="">All models</option>{models.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</NativeSelect></Label>
        <Label className="select-field"><span>Report</span><NativeSelect aria-label="Report" value={reportId} onChange={(event) => change({ reportId: event.target.value, modelId: "" })}><option value="">All reports</option>{reports.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</NativeSelect></Label>
        <Label className="select-field"><span>Type</span><NativeSelect aria-label="Search object type" value={objectType} onChange={(event) => change({ objectType: event.target.value })}><option value="">All types</option>{Object.keys(overview.object_counts || {}).sort().map((type) => <option key={type} value={type}>{typeLabel(type)}</option>)}</NativeSelect></Label>
        {modelId || reportId || objectType ? <Button variant="ghost" onClick={() => change({ modelId: "", reportId: "", objectType: "" })}>Clear filters</Button> : null}
      </div>
      <div className="search-status" role="status" aria-live="polite">{browse || query.trim() ? loading ? "Searching…" : result ? `${result.items.length} of ${result.total} ${browse && !query.trim() ? "objects" : "matches"}` : "" : "Search by name or paste part of a formula."}</div>
      {error ? <div className="search-error" role="alert"><span>{readableText(error.message)}</span><Button variant="outline" onClick={() => runSearch(error.offset)}>Retry search</Button></div> : null}
      {!browse && !query.trim() ? <EmptyState title="What are you looking for?" detail="Find a measure to inspect its formula and dependencies." /> : null}
      {(browse || query.trim()) && !loading && !result?.items?.length && !error ? <EmptyState title="No matches" detail="Try a shorter name or clear the filters." /> : null}
      {(browse || query.trim()) && result?.items?.length ? <div className="search-results">{result.items.map((item) => { const object = searchObject(item); return <Button variant="ghost" key={object.id} data-result-id={object.id} className="search-result" onClick={() => { onSession((current) => ({ ...current, selectedId: object.id, scrollY: window.scrollY })); onSelect(object.id, "inspector"); }}><span className="result-type" style={{ borderColor: artifactColor(object, colors), color: artifactColor(object, colors) }}>{typeLabel(object.type)}</span><span><strong>{labelFor(object)}</strong><small>{scopeName(object) || readableText(object.description) || typeLabel(object.type)}</small></span><span className="result-match">{browse && !query.trim() ? "Open →" : searchMatch(item)}</span></Button>; })}</div> : null}
      {(browse || query.trim()) && result?.has_more ? <div className="search-footer"><Button variant="outline" disabled={loading} onClick={() => runSearch(Number(result.offset || 0) + Number(result.limit || 50))}>{pending ? "Loading…" : "More results"}</Button></div> : null}
    </Card>
  </div>;
}

function ConfigView({ transport, config, onSaved, onScan }) {
  const [draft, setDraft] = useState(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  useEffect(() => {
    const loaded = config || {};
    const defaults = { version: 1, name: "PBIBrain project", sources: [], database: "", identity_map: "" };
    const next = { ...defaults, ...loaded };
    setDraft({ ...next, sources: Array.isArray(loaded.sources) ? loaded.sources : [] });
  }, [config]);
  if (!draft) return <div className="panel"><EmptyState title="Loading configuration" detail="Reading the local project settings." /></div>;
  const updateSource = (index, value) => setDraft((current) => ({ ...current, sources: current.sources.map((source, sourceIndex) => sourceIndex === index ? value : source) }));
  const save = async () => {
    setSaving(true); setMessage("");
    try { const saved = await transport.saveConfig(draft); setDraft(saved); onSaved(saved); setMessage("Saved"); }
    catch (cause) { setMessage(cause.message || "Could not save configuration"); }
    finally { setSaving(false); }
  };
  return <>
    <Card className="block gap-0 p-0 shadow-none panel config-panel">
      <Label className="config-field"><span>Project name</span><Input value={draft.name || ""} onChange={(event) => setDraft({ ...draft, name: event.target.value })} placeholder="Finance reporting" /></Label>
      <div className="config-section"><div className="panel-heading"><div><p className="eyebrow">Sources</p><h3>Power BI inputs</h3></div><Button variant="outline" onClick={() => setDraft({ ...draft, sources: [...draft.sources, ""] })}>Add source</Button></div><p className="muted-copy">Use full Windows paths for PBIP projects or model JSON files.</p>{draft.sources.length ? <div className="source-list">{draft.sources.map((source, index) => <div className="source-row" key={index}><Input value={source} onChange={(event) => updateSource(index, event.target.value)} placeholder="C:\\Reports\\Finance\\Finance.pbip" aria-label={`Source ${index + 1}`} /><Button variant="ghost" size="icon" onClick={() => setDraft({ ...draft, sources: draft.sources.filter((_, sourceIndex) => sourceIndex !== index) })} aria-label={`Remove source ${index + 1}`}>×</Button></div>)}</div> : <EmptyState title="No sources" detail="Add a PBIP project or model JSON file." />}</div>
      <div className="config-actions"><Button onClick={save} disabled={saving}>{saving ? "Saving…" : "Save configuration"}</Button><Button variant="outline" onClick={onScan}>Scan saved sources</Button>{message ? <span className={message === "Saved" ? "success-text" : "error-copy"}>{message}</span> : null}</div>
    </Card>
  </>;
}

function Inspector({ node, details, loading, error, snapshot, snapshotLoaded, overview, onSelect, onRetry, onReview, onGraph, colors }) {
  if (error) return <><PageHeading title="Object unavailable" description={readableText(error)} /><Button variant="outline" onClick={onRetry}>Retry object</Button></>;
  if (loading) return <div className="inspector-loading" role="status">Loading object details…</div>;
  if (!node) return <><PageHeading title="Select an object" description="Choose an object from Search or the graph." action={<Button onClick={onGraph}>Open graph</Button>} /></>;
  const connected = details?.edges || [];
  const outgoing = connected.filter((edge) => edge.from_id === node.id);
  const incoming = connected.filter((edge) => edge.to_id === node.id);
  const usageTypes = new Set(["DEPENDS_ON", "REFERENCES", "USES"]);
  const relatedNodes = [...new Map([...snapshot.nodes, ...(details?.dependencies || []), ...(details?.dependents || []), ...(details?.usage || []), ...(details?.relationships?.nodes || []), node].map((item) => [item.id, item])).values()];
  const scopes = [...scopeOptions(overview, "model"), ...scopeOptions(overview, "report"), ...relatedNodes];
  const scopeName = (id) => readableText(scopes.find((item) => item.id === id)?.name);
  const candidates = snapshot.semantic_candidates.filter((item) => itemTarget(item) === node.id && !["approved", "rejected", "overridden"].includes(item.status));
  const warnings = snapshot.conflicts.filter((item) => itemTarget(item) === node.id);
  const observations = connected.filter((edge) => edge.type === "OBSERVED_WITH");
  const properties = node.properties || {};
  const expression = node.expression ?? properties.expression;
  const fields = publicProperties(node);
  return <>
    <PageHeading title={labelFor(node)} description={[node.model_id, node.report_id, properties.table_id].filter((id) => id && id !== node.id).map(scopeName).filter(Boolean).join(" · ")} action={<Button variant="outline" onClick={onGraph}>Show in graph <span aria-hidden="true">↗</span></Button>} />
    <div className="object-workspace">
      <Card className="block gap-0 p-0 shadow-none panel object-summary">
        <div className="object-summary-state"><span className="artifact-dot" style={{ backgroundColor: artifactColor(node, colors) }} /><span>{typeLabel(node.type)}</span><StatusBadge value={node.status} /></div>
        {node.description ? <p className="description-copy">{formatValue(node.description)}</p> : null}
        {expression ? <ExpressionBlock expression={formatValue(expression)} /> : !node.description ? <p className="muted-copy">No description recorded.</p> : null}
      </Card>
      <Card className="block gap-0 p-0 shadow-none panel object-lineage">
        <VisualBindings bindings={details?.visual_bindings} onSelect={(item) => onSelect(item.id, "inspector")} />
        <RelationshipGroup title="Used by" nodeId={node.id} edges={incoming.filter((edge) => usageTypes.has(edge.type))} nodes={relatedNodes} onSelect={onSelect} empty="No direct uses recorded." />
        <RelationshipGroup title="Dependencies" nodeId={node.id} edges={outgoing.filter((edge) => usageTypes.has(edge.type))} nodes={relatedNodes} onSelect={onSelect} empty="No direct dependencies recorded." />
        <p className="footnote">Direct links from the latest scan.</p>
      </Card>
      {candidates.length || warnings.length ? <details className="object-metadata object-review panel"><summary>Review &amp; evidence <span>{candidates.length} suggestions{warnings.length ? ` · ${warnings.length} warnings` : ""}</span></summary>{candidates.map((item) => <div className="object-review-item" key={item.id || item.target}><CandidateActions item={item} onReview={onReview} /><EvidenceCard item={item} /></div>)}{warnings.map((warning) => <div className="warning-card" key={warning.id || formatEvidence(warning.reason)}><strong>Conflict</strong><p>{formatEvidence(warning.reason || warning.message || warning.description || "Conflicting evidence needs review.")}</p></div>)}</details> : null}
      {!snapshotLoaded ? <p className="muted-copy object-review" role="status">Review evidence has not loaded yet.</p> : null}
      {fields.length ? <details className="object-metadata object-identity panel"><summary>Object details</summary><dl className="metadata-table">{fields.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl></details> : null}
      {connected.some((edge) => !usageTypes.has(edge.type) && edge.type !== "OBSERVED_WITH") ? <details className="object-metadata object-other panel"><summary>Other relationships</summary><RelationshipGroup title="Connected objects" nodeId={node.id} edges={connected.filter((edge) => !usageTypes.has(edge.type) && edge.type !== "OBSERVED_WITH")} nodes={relatedNodes} onSelect={onSelect} empty="No other relationships." /></details> : null}
      {observations.length ? <details className="object-metadata object-observed panel"><summary>Observed report usage <span>{observations.length}</span></summary>{observations.map((edge) => <div className="usage-row" key={edge.id}><span>{scopeName(edge.from_id === node.id ? edge.to_id : edge.from_id)}</span><strong>{formatValue(edge.properties?.count || edge.count || "observed")}</strong></div>)}<p className="footnote">Co-occurrence does not establish compatibility.</p></details> : null}
    </div>
  </>;
}

function ExpressionBlock({ expression }) {
  const [message, setMessage] = useState("");
  const copy = async () => {
    try { await navigator.clipboard.writeText(expression); setMessage("Copied"); }
    catch { setMessage("Select the formula to copy it."); }
  };
  return <section className="object-expression" aria-label="DAX formula"><div><h3>DAX formula</h3><Button variant="ghost" size="sm" onClick={copy}>Copy formula</Button></div><pre tabIndex={0}><code>{expression}</code></pre>{message ? <p role="status">{message}</p> : null}</section>;
}

function RelationshipGroup({ title, nodeId, edges, nodes, onSelect, empty }) {
  const [expanded, setExpanded] = useState(false);
  const unique = [...new Map(edges.map((edge) => [edge.from_id === nodeId ? edge.to_id : edge.from_id, edge])).values()];
  const shown = expanded ? unique : unique.slice(0, 10);
  return <section className="relationship-group" aria-label={title}><h3 className="relationship-title">{title}<span>{unique.length}</span></h3>{unique.length ? <div className="relationship-list">{shown.map((edge) => { const targetId = edge.from_id === nodeId ? edge.to_id : edge.from_id; const resolved = nodes.find((node) => node.id === targetId); return <Button variant="ghost" className="relationship-row" key={targetId} onClick={() => onSelect(targetId, "inspector")}><span className="edge-chip" style={{ background: EDGE_COLORS[edge.type] || "#738294" }} /><span><strong>{resolved ? labelFor(resolved) : "Related object"}</strong><small>{typeLabel(resolved?.type || edge.type)}</small></span><span aria-hidden="true">→</span></Button>; })}</div> : <p className="muted-copy compact">{empty}</p>}{unique.length > 10 ? <Button variant="link" className="relationship-more" onClick={() => setExpanded((current) => !current)}>{expanded ? "Show fewer" : `Show all ${unique.length}`}</Button> : null}</section>;
}

function reviewIssue(item) {
  const value = String(item?.issue || item?.issue_type || item?.kind || item?.type || "candidate").toLowerCase();
  if (value.includes("conflict")) return "conflict";
  if (value.includes("stale") || value.includes("override")) return "stale";
  return "candidate";
}

function mergeReviewItems(items) {
  const merged = new Map();
  items.filter(Boolean).forEach((item, index) => {
    const issue = reviewIssue(item);
    const semanticKey = `${issue}:${itemTarget(item) || "unknown"}:${safeJson(item.value ?? item.meaning ?? item.reason ?? item.message ?? index)}`;
    const candidateId = item.candidate_id || item.properties?.candidate_id || item.item?.candidate_id || item.item?.properties?.candidate_id;
    const key = issue === "conflict" ? semanticKey : candidateId || item.id || semanticKey;
    merged.set(key, { ...merged.get(key), ...item, issue });
  });
  return [...merged.values()];
}

function itemScopeValue(item, node, key) {
  return item?.[key] ?? item?.properties?.[key] ?? node?.[key] ?? node?.properties?.[key] ?? "";
}

function ReviewQueue({ snapshot, loading, overview, onSelect, onReview }) {
  const [issue, setIssue] = useState("ALL");
  const [objectType, setObjectType] = useState("ALL");
  const [modelId, setModelId] = useState("ALL");
  const [reportId, setReportId] = useState("ALL");
  const [sort, setSort] = useState("confidence-high");
  const external = snapshot.review_items.map((item) => ({ ...item, issue: reviewIssue(item) }));
  const candidates = snapshot.semantic_candidates.map((item) => ({ ...item, issue: "candidate" }));
  const conflicts = snapshot.conflicts.map((item) => ({ ...item, issue: "conflict", status: item.status || "candidate", confidence: item.confidence ?? 0 }));
  const staleRecords = [...snapshot.stale_overrides, ...snapshot.overrides.filter((item) => item.status === "stale"), ...external.filter((item) => item.issue === "stale")];
  const stale = staleRecords.map((item) => ({ ...item, issue: "stale", status: item.status || "candidate", confidence: item.confidence ?? 0 }));
  const all = mergeReviewItems(external.length ? external : [...candidates, ...conflicts, ...stale]);
  const types = [...new Set(all.map((item) => snapshot.nodes.find((node) => node.id === itemTarget(item))?.type).filter(Boolean))].sort();
  const models = [...new Set(all.map((item) => itemScopeValue(item, snapshot.nodes.find((node) => node.id === itemTarget(item)), "model_id")).filter(Boolean))].sort();
  const reports = [...new Set(all.map((item) => itemScopeValue(item, snapshot.nodes.find((node) => node.id === itemTarget(item)), "report_id")).filter(Boolean))].sort();
  const filtered = all.filter((item) => {
    const targetNode = snapshot.nodes.find((node) => node.id === itemTarget(item));
    return (issue === "ALL" || item.issue === issue)
      && (objectType === "ALL" || targetNode?.type === objectType)
      && (modelId === "ALL" || itemScopeValue(item, targetNode, "model_id") === modelId)
      && (reportId === "ALL" || itemScopeValue(item, targetNode, "report_id") === reportId)
      && !["rejected", "approved", "overridden"].includes(item.status);
  }).sort((a, b) => {
    if (sort === "confidence-low") return itemConfidence(a) - itemConfidence(b);
    if (sort === "impact-high") return itemImpact(b) - itemImpact(a);
    if (sort === "impact-low") return itemImpact(a) - itemImpact(b);
    return itemConfidence(b) - itemConfidence(a);
  });
  const scopes = [...scopeOptions(overview, "model"), ...scopeOptions(overview, "report"), ...snapshot.nodes];
  const scopeName = (id, kind, index) => scopes.find((node) => node.id === id)?.name || `${kind} ${index + 1}`;
  return <>
    <div className="review-purpose"><p>Confirm the meanings PBIBrain inferred. Approval saves a trusted label for search and context; rejection excludes it. Your Power BI files stay unchanged.</p><span className="queue-count">{loading ? "Loading…" : `${filtered.length} to review`}</span></div>
    <div className="queue-toolbar">
      <Label className="select-field"><span>Issue</span><NativeSelect value={issue} onChange={(event) => setIssue(event.target.value)}><option value="ALL">All issues</option><option value="candidate">Suggestions</option><option value="conflict">Conflicts</option><option value="stale">Outdated decisions</option></NativeSelect></Label>
      <Label className="select-field"><span>Object</span><NativeSelect value={objectType} onChange={(event) => setObjectType(event.target.value)}><option value="ALL">All types</option>{types.map((type) => <option key={type} value={type}>{typeLabel(type)}</option>)}</NativeSelect></Label>
      {models.length > 1 ? <Label className="select-field"><span>Model</span><NativeSelect value={modelId} onChange={(event) => setModelId(event.target.value)}><option value="ALL">All models</option>{models.map((value, index) => <option key={value} value={value}>{scopeName(value, "Model", index)}</option>)}</NativeSelect></Label> : null}
      {reports.length > 1 ? <Label className="select-field"><span>Report</span><NativeSelect value={reportId} onChange={(event) => setReportId(event.target.value)}><option value="ALL">All reports</option>{reports.map((value, index) => <option key={value} value={value}>{scopeName(value, "Report", index)}</option>)}</NativeSelect></Label> : null}
      <Label className="select-field"><span>Sort</span><NativeSelect value={sort} onChange={(event) => setSort(event.target.value)}><option value="confidence-high">Most certain first</option><option value="confidence-low">Least certain first</option><option value="impact-high">Highest impact first</option><option value="impact-low">Lowest impact first</option></NativeSelect></Label>
    </div>
    <Card className="block gap-0 p-0 shadow-none panel queue-panel" aria-busy={loading}>
      {loading ? <p className="empty-state" role="status">Loading suggestions…</p> : filtered.length ? <>
        <div className="review-columns" aria-hidden="true"><span>Object &amp; suggestion</span><span>Why review this?</span><span>Confidence</span><span>Decision</span></div>
        <div className="queue-list">{filtered.map((item) => <ReviewItem key={item.id || `${item.issue}-${itemTarget(item)}`} item={item} nodes={snapshot.nodes} onSelect={onSelect} onReview={onReview} />)}</div>
      </> : <EmptyState title="Queue is clear" detail="No unresolved suggestions match these filters." />}
    </Card>
  </>;
}

function ReviewItem({ item, nodes, onSelect, onReview }) {
  const targetNode = nodes.find((node) => node.id === itemTarget(item));
  const [pending, setPending] = useState(false);
  const decide = async (action) => { if (pending) return; setPending(true); try { await onReview(action, item); } finally { setPending(false); } };
  const evidence = readableText(item.evidence?.length ? item.evidence : item.item?.evidence, nodes);
  const reason = item.reason || (item.source === "object_name" ? "Only the object name supports this meaning; no description confirms it." : item.source === "description" ? "The source description suggests this meaning. Confirm that the label fits." : "An inference rule proposed this meaning. Confirm it using the recorded evidence.");
  return <div className="review-item" aria-busy={pending}>
    <Button variant="ghost" className="review-target" disabled={!targetNode} onClick={() => onSelect(targetNode.id, "inspector")}><span className={`review-dot ${item.issue}`} /><span><strong>{targetNode ? labelFor(targetNode) : "Source object unavailable"}</strong><small>{objectScope(targetNode, nodes)}</small><small>{item.issue === "conflict" ? "Conflicting suggestions" : item.issue === "stale" ? "Outdated saved decision" : suggestionLabel(item)}</small>{targetNode ? <small>{typeLabel(targetNode.type)}</small> : null}</span></Button>
    <div className="review-evidence"><p>{readableText(reason, nodes)}</p>{evidence ? <small>{evidence}</small> : null}</div>
    <div className="review-score"><strong>{confidence(item.confidence ?? item.properties?.confidence) === null ? "—" : `${confidence(itemConfidence(item))}%`}</strong><small>{item.issue === "conflict" ? "Conflict" : item.issue === "stale" ? "Outdated" : "Suggested"}</small></div>
    <div className="review-actions">{item.issue === "stale" ? <Button variant="outline" disabled={pending} onClick={() => decide("remove")}>Remove decision</Button> : <><Button variant="outline" disabled={pending} onClick={() => decide("approve")}>Approve</Button><Button variant="ghost" disabled={pending} onClick={() => decide("reject")}>Reject</Button></>}</div>
  </div>;
}


function CandidateActions({ item, onReview }) {
  const [editingAction, setEditingAction] = useState("");
  const [value, setValue] = useState(readableText(item.value || item.meaning));
  const [pending, setPending] = useState(false);
  const beginEdit = (action) => { setValue(readableText(item.value || item.meaning)); setEditingAction(action); };
  const decide = async (action, nextValue) => {
    if (pending) return;
    setPending(true);
    try { if (await onReview(action, item, nextValue)) setEditingAction(""); }
    finally { setPending(false); }
  };
  const score = confidence(item.confidence ?? item.properties?.confidence);
  return <fieldset className="candidate-actions" disabled={pending}>
    <div className="candidate-action-title"><span>{suggestionLabel(item)}</span><span>{score === null ? "" : `${score}%`}</span></div>
    {editingAction ? <div className="edit-row"><Input value={value} onChange={(event) => setValue(event.target.value)} aria-label={`${editingAction} semantic value`} /><Button variant="outline" disabled={!value.trim()} onClick={() => decide(editingAction, value)}>Save meaning</Button><Button variant="link" onClick={() => setEditingAction("")}>Cancel</Button></div> : <div className="action-buttons"><Button variant="outline" onClick={() => decide("approve")}>Approve</Button><Button variant="ghost" onClick={() => beginEdit("edit")}>Edit</Button><Button variant="ghost" onClick={() => decide("reject")}>Reject</Button><Button variant="link" onClick={() => beginEdit("override")}>Set meaning</Button></div>}
  </fieldset>;
}

function EvidenceCard({ item }) {
  return <div className="evidence-card"><p>{readableText(item.evidence?.length ? item.evidence : item.reason) || "No explanation recorded."}</p></div>;
}

function StatusBadge({ value, large = false }) { return <Badge variant="outline" className={`status-badge ${large ? "large" : ""} ${statusClass(value)}`}><i />{statusLabel(value)}</Badge>; }
function EmptyState({ title, detail, action }) { return <div className="empty-state"><strong>{title}</strong><p>{detail}</p>{action}</div>; }
function formatDate(value) { if (!value || value === "Not scanned") return value || "Not scanned"; const date = new Date(value); return Number.isNaN(date.valueOf()) ? String(value) : date.toLocaleString([], { dateStyle: "medium", timeStyle: "short" }); }
function formatValue(value) { return readableText(value) || "—"; }

export default App;
