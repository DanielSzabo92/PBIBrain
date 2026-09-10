import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { brainTransport, normalizeSnapshot } from "./transport";
import { desktopRequest, subscribeToDesktopBridge } from "./desktop";
import NavIcon from "./NavIcon";
import { Button } from "./components/ui/button";
import { Input } from "./components/ui/input";
import { NativeSelect } from "./components/ui/native-select";
import { Badge } from "./components/ui/badge";
import { Card } from "./components/ui/card";
import { Label } from "./components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "./components/ui/tabs";
import GraphView from "./components/GraphView";
import GraphColors from "./components/GraphColors";
import { artifactColor, normalizeColors } from "./graphPresentation";

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


function nodeProperty(node, key, fallback = "") {
  return node?.[key] ?? node?.properties?.[key] ?? fallback;
}

function confidence(value) {
  const number = Number(value);
  return Number.isFinite(number) ? Math.round(number * 100) : null;
}

function statusClass(value) {
  return String(value || "factual").toLowerCase().replace(/[^a-z]+/g, "-");
}

function labelFor(node) {
  return node?.name || node?.id || "Unnamed object";
}

function shortId(value) {
  const text = String(value || "");
  return text.length > 31 ? `${text.slice(0, 15)}…${text.slice(-12)}` : text;
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
  return safeJson(value === undefined || value === null ? "Evidence attached" : value);
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

function scopeOptions(overview, key) {
  const items = overview?.[`${key}_objects`];
  if (Array.isArray(items) && items.length) return items.map((item) => typeof item === "string" ? { id: item, name: item } : { id: item.id, name: item.name || item.id }).filter((item) => item.id);
  return (overview?.[`${key}_ids`] || []).map((id) => ({ id, name: id }));
}

function searchObject(item) {
  return item?.object && typeof item.object === "object" ? item.object : item;
}

function searchMatch(item) {
  const match = item?.match || {};
  return match.evidence?.[0]?.field || match.field || match.kind || item?.match_field || "match";
}

function App({ transport = brainTransport }) {
  const desktopHost = Boolean(globalThis.__PBIBRAIN_DESKTOP__);
  const [snapshot, setSnapshot] = useState(() => normalizeSnapshot(null));
  const [snapshotLoaded, setSnapshotLoaded] = useState(false);
  const [overview, setOverview] = useState({});
  const [config, setConfig] = useState(null);
  const graphColors = useMemo(() => normalizeColors(config?.graph_colors), [config?.graph_colors]);
  const [view, setView] = useState("overview");
  const [selectedId, setSelectedId] = useState(null);
  const [inspectedObject, setInspectedObject] = useState(null);
  const [inspectorError, setInspectorError] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [operationError, setOperationError] = useState("");
  const [notice, setNotice] = useState("");
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
    setSelectedId(null);
    setInspectedObject(null);
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
    if (session.source_count === 0) setView("config");
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
    setInspectorError("");
    if (nextView) setView(nextView);
    try {
      const result = await transport.getObject(id);
      if (requestId !== selectionRequest.current) return;
      setInspectedObject(result?.object || result?.item || result);
      loadSnapshot().catch(() => {});
    } catch (cause) {
      if (requestId !== selectionRequest.current) return;
      setSelectedId(null);
      setInspectedObject(null);
      setInspectorError(cause.message || "Object could not be loaded");
    }
  }, [loadSnapshot, transport]);

  const applyScan = useCallback(async () => {
    if (scanInFlight.current) return;
    scanInFlight.current = true;
    setScanning(true);
    setLoading(true);
    setOperationError("");
    try {
      const result = await transport.scan();
      if (result?.overview) setOverview(result.overview);
      setSelectedId(null);
      setInspectedObject(null);
      setInspectorError("");
      setSnapshot(normalizeSnapshot(null));
      setSnapshotLoaded(false);
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
      const property = item?.property || item?.item?.property || item?.meaning_type || "business_concept";
      const actionValue = value === undefined ? item?.value ?? item?.item?.value : value;
      setNotice("");
      try {
        const payload = {
          target,
          candidate_id: reviewId,
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
        setNotice(`${action[0].toUpperCase()}${action.slice(1)}d ${shortId(target)}`);
      } catch (cause) {
        setNotice(cause.message || "Review action failed");
      }
    },
    [transport],
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
          <h1>{activeProject?.name || "Project brain"}</h1>
        </div>
        <div className="topbar-spacer" />
        <span className={`connection-dot ${loading ? "is-loading" : error ? "is-error" : "is-ready"}`} />
        <span className="connection-label">{loading ? "Loading" : error ? "Offline" : "Connected"}</span>
        {activeProject ? <Button variant="ghost" className="project-switch" onClick={closeDesktopProject} disabled={scanning}>Change project</Button> : null}
        <Button variant="ghost" size="icon" onClick={load} title="Reload Brain" aria-label="Reload Brain">↻</Button>
      </header>

      <div className="workspace">
        <aside className="sidebar">
          <p className="nav-label">Workspace</p>
          <nav aria-label="Main navigation">
            {VIEWS.map(([key, label]) => (
              <Button variant="ghost" key={key} aria-current={view === key ? "page" : undefined} className={`nav-button ${view === key ? "active" : ""}`} onClick={() => { setView(key); if (key === "review") loadSnapshot().catch(() => {}); }}>
                <NavIcon name={key} />
                {label}
                {key === "review" && counts.candidates + counts.warnings > 0 ? <span className="nav-count">{counts.candidates + counts.warnings}</span> : null}
              </Button>
            ))}
          </nav>
          <div className="sidebar-footer">
            <p className="nav-label">Store</p>
            <span className="store-pill">LadybugDB</span>
            <span className="store-detail">Canonical graph</span>
          </div>
        </aside>

        <main className={`content ${view === "graph" ? "content-graph" : ""}`}>
          {notice ? <div className="toast" role="status">{notice}</div> : null}
          {error || operationError || desktopError ? (
            <div className="error-banner" role="alert">
              <span>{error || operationError || desktopError}</span>
              {error ? <Button variant="link" onClick={load}>Retry</Button> : null}
            </div>
          ) : null}
          {view === "overview" ? <Overview snapshot={snapshot} snapshotLoaded={snapshotLoaded} overview={overview} counts={counts} onView={setView} onSelect={selectNode} onScan={applyScan} scanning={scanning} scanLabel={activeProject ? "Scan project" : "Scan sources"} onReview={() => { setView("review"); loadSnapshot().catch(() => {}); }} /> : null}
          {view === "search" ? <SearchView colors={graphColors} transport={transport} overview={overview} onSelect={selectNode} /> : null}
          {view === "graph" ? <GraphView colors={graphColors} transport={transport} overview={overview} snapshot={snapshot} selectedId={selectedId} onSelect={selectNode} /> : null}
          {view === "inspector" ? <Inspector colors={graphColors} node={selected} error={inspectorError} snapshot={snapshot} onSelect={selectNode} onReview={review} onGraph={() => setView("graph")} /> : null}
          {view === "review" ? <ReviewQueue snapshot={snapshot} onSelect={selectNode} onReview={review} /> : null}
          {view === "config" ? <Tabs defaultValue="colors" className="settings-tabs">
            <PageHeading kicker="Preferences" title="Settings" description="Graph appearance and project sources." />
            <TabsList aria-label="Settings sections"><TabsTrigger value="colors">Graph colors</TabsTrigger><TabsTrigger value="project">Project</TabsTrigger></TabsList>
            <TabsContent value="colors"><GraphColors config={config} transport={transport} overview={overview} onSaved={setConfig} /></TabsContent>
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
  const hasScan = Boolean(overview.last_scan || overview.counts?.nodes || overview.objects);
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
      <div className="desktop-readiness"><div><span className={`readiness-dot ${hasScan ? "" : "is-pending"}`} /><div><strong>{hasScan ? "Ready for agents" : "Awaiting first scan"}</strong><p>{hasScan ? "Scan results are saved in this folder and available through the local project context." : "Scan this project to create its agent-ready context."}</p></div></div><div><span className="readiness-dot" /><div><strong>Project storage</strong><p>PBIBrain keeps its project data alongside this folder.</p></div></div></div>
      <div className="desktop-sources"><div className="panel-heading"><div><p className="eyebrow">Power BI inputs</p><h3>Source files</h3></div><Button variant="outline" onClick={addSources} disabled={sourceWorking || scanning}>{sourceWorking ? "Adding…" : "Add source files"}</Button></div>{sources.length ? <div className="source-list">{sources.map((source) => <div className="desktop-source-row" key={source}><span title={source}>{source}</span><Button variant="ghost" size="icon" onClick={() => removeSource(source)} disabled={sourceWorking || scanning} aria-label={`Remove ${source}`}>×</Button></div>)}</div> : <p className="muted-copy">Add PBIP projects or model JSON files to scan them with this project.</p>}{sourceError ? <p className="onboarding-error" role="alert">{sourceError}</p> : null}</div>
      <div className="config-actions"><Button onClick={onScan} disabled={scanning}>{scanning ? "Scanning…" : "Scan project"}</Button></div>
    </Card>
  </>;
}

function PageHeading({ kicker, title, description, action }) {
  return (
    <div className="page-heading">
      <div>
        <p className="eyebrow">{kicker}</p>
        <h2>{title}</h2>
        {description ? <p className="page-description">{description}</p> : null}
      </div>
      {action}
    </div>
  );
}

function Overview({ snapshot, snapshotLoaded, overview, counts, onView, onSelect, onScan, onReview, scanning, scanLabel }) {
  const scan = snapshot.scan || {};
  const validation = snapshot.validation || {};
  const rawLastScan = overview.last_scan || scan.last_scan || scan.lastScan || scan.timestamp || scan.completed_at;
  const lastScan = rawLastScan || (counts.objects ? "Time unavailable" : "Not scanned");
  const scanState = overview.scan_state || overview.state || scan.state || scan.status || (counts.objects ? "ready" : "awaiting scan");
  const candidates = snapshot.semantic_candidates.filter((item) => item.status !== "rejected");
  const recent = [...candidates].sort((a, b) => Number(b.confidence || 0) - Number(a.confidence || 0)).slice(0, 4);

  return (
    <>
      <PageHeading kicker="Workspace overview" title="Project overview" description="Your models, reports, and source health." action={<Button onClick={() => onView("graph")}>Explore graph <span>→</span></Button>} />
      <Card className="block gap-0 p-0 shadow-none stat-grid" aria-label="Brain counts">
        <StatCard label="Models" value={counts.models} detail="Semantic models" tone="blue" />
        <StatCard label="Reports" value={counts.reports} detail="Connected reports" tone="purple" />
        <StatCard label="Objects" value={counts.objects} detail="Indexed objects" tone="green" />
        <StatCard label="Relationships" value={counts.edges} detail="Known relationships" tone="amber" />
      </Card>
      <Card className="block gap-0 p-0 shadow-none overview-grid">
        <div className="panel scan-panel">
          <div className="panel-heading"><div><p className="eyebrow">Source state</p><h3>Last scan</h3></div><StatusBadge value={scanState} /></div>
          <div className="scan-value">{formatDate(lastScan)}</div>
          <div className="scan-meta"><span>Graph storage</span><strong>{overview.storage || overview.storage_name || "Local graph"}</strong></div>
          <div className="scan-meta"><span>Validation</span><strong className={validation.valid === false ? "danger-text" : "success-text"}>{validation.valid === false ? "Needs attention" : validation.state || "Not run"}</strong></div>
          <div className="split-actions"><Button variant="outline" onClick={() => onView("graph")}>Open graph</Button><Button onClick={onScan} disabled={scanning}>{scanning ? "Scanning…" : scanLabel}</Button></div>
        </div>
        <div className="panel review-panel">
          <div className="panel-heading"><div><p className="eyebrow">Human review</p><h3>Needs attention</h3></div><Button variant="link" onClick={() => onView("review")}>View all →</Button></div>
          <div className="attention-row"><span className="attention-icon candidate">◌</span><span>Semantic candidates</span><strong>{counts.candidates}</strong></div>
          <div className="attention-row"><span className="attention-icon warning">!</span><span>Conflicts &amp; warnings</span><strong>{counts.warnings}</strong></div>
          <div className="attention-row"><span className="attention-icon approved">✓</span><span>Approved semantics</span><strong>{overview.approved_count ?? (snapshotLoaded ? snapshot.semantic_candidates.filter((item) => item.status === "approved").length : "—")}</strong></div>
        </div>
      </Card>
      <Card className="block gap-0 p-0 shadow-none panel candidate-panel">
        <div className="panel-heading"><div><p className="eyebrow">Semantic layer</p><h3>Review candidates</h3></div><span className="muted-label">Description-first inference</span></div>
        {!snapshotLoaded ? <EmptyState title="Review details are ready" detail="Open the review queue to load candidate evidence." action={<Button variant="outline" onClick={onReview}>Open review queue</Button>} /> : recent.length ? <div className="candidate-list">{recent.map((item) => <CandidateRow key={item.id || `${item.target}-${item.value}`} item={item} onSelect={onSelect} onReview={onReview} />)}</div> : <EmptyState title="No semantic candidates" detail="This scan has no reviewable semantic candidates." />}
      </Card>
    </>
  );
}

function StatCard({ label, value, detail, tone }) {
  return <Card className={`block gap-0 p-0 shadow-none stat-card ${tone}`}><div className="stat-top"><span>{label}</span></div><strong>{value}</strong><small>{detail}</small></Card>;
}

function SearchView({ transport, overview, onSelect, colors }) {
  const [query, setQuery] = useState("");
  const [modelId, setModelId] = useState("");
  const [reportId, setReportId] = useState("");
  const [result, setResult] = useState({ items: [], total: 0, limit: 50, offset: 0, has_more: false });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const request = useRef(0);
  const key = `${query}\u0000${modelId}\u0000${reportId}`;
  const requestedKey = useRef(key);
  requestedKey.current = key;
  const runSearch = useCallback(async (offset = 0) => {
    const requestId = ++request.current;
    if (!query.trim()) { setResult({ items: [], total: 0, limit: 50, offset: 0, has_more: false }); setLoading(false); setError(""); return; }
    setLoading(true); setError("");
    try {
      const next = await transport.search({ query: query.trim(), modelId, reportId, offset });
      if (requestId === request.current && requestedKey.current === key) setResult(next);
    } catch (cause) {
      if (requestId === request.current && requestedKey.current === key) setError(cause.message || "Search failed");
    } finally {
      if (requestId === request.current && requestedKey.current === key) setLoading(false);
    }
  }, [key, modelId, query, reportId, transport]);
  useEffect(() => {
    const timer = setTimeout(() => runSearch(), 220);
    return () => clearTimeout(timer);
  }, [runSearch]);
  const models = scopeOptions(overview, "model");
  const reports = scopeOptions(overview, "report");
  return <>
    <PageHeading kicker="Objects" title="Search the project" description="Find measures, tables, and report objects across your sources." />
    <Card className="block gap-0 p-0 shadow-none panel search-panel">
      <div className="graph-toolbar search-toolbar">
        <Label className="search-field"><span>⌕</span><Input autoFocus value={query} onChange={(event) => { request.current += 1; setQuery(event.target.value); }} onKeyDown={(event) => { if (event.key === "Enter") runSearch(); }} placeholder="Measure, table, visual, page, expression…" aria-label="Search the brain" /></Label>
        <Label className="select-field"><span>Model</span><NativeSelect value={modelId} onChange={(event) => { request.current += 1; setModelId(event.target.value); setReportId(""); }}><option value="">All models</option>{models.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</NativeSelect></Label>
        <Label className="select-field"><span>Report</span><NativeSelect value={reportId} onChange={(event) => { request.current += 1; setReportId(event.target.value); setModelId(""); }}><option value="">All reports</option>{reports.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</NativeSelect></Label>
      </div>
      {error ? <p className="error-copy">{error}</p> : null}
      {!query.trim() ? <EmptyState title="Search ready" detail="Start with a business term, DAX object, visual, or page." /> : null}
      {query.trim() && !loading && !result.items?.length && !error ? <EmptyState title="No matches" detail="Try a broader term or remove a scope filter." /> : null}
      {result.items?.length ? <div className="search-results">{result.items.map((item) => { const object = searchObject(item); return <Button variant="ghost" key={object.id} className="search-result" onClick={() => onSelect(object.id, "inspector")}><span className="result-type" style={{ borderColor: artifactColor(object, colors), color: artifactColor(object, colors) }}>{object.type || "OBJECT"}</span><span><strong>{labelFor(object)}</strong><small>{shortId(object.id)} · {object.model_id || object.report_id || "project"}</small></span><span className="result-match">{searchMatch(item)}</span></Button>; })}</div> : null}
      {result.items?.length ? <div className="search-footer"><span>{result.total} match{result.total === 1 ? "" : "es"}</span>{result.has_more ? <Button variant="outline" onClick={() => runSearch(Number(result.offset || 0) + Number(result.limit || 50))}>More results</Button> : null}</div> : null}
    </Card>
  </>;
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
    <PageHeading kicker="Project configuration" title="Sources and storage" description="Add absolute PBIP or model JSON paths. A project can contain multiple reports and models." />
    <Card className="block gap-0 p-0 shadow-none panel config-panel">
      <Label className="config-field"><span>Project name</span><Input value={draft.name || ""} onChange={(event) => setDraft({ ...draft, name: event.target.value })} placeholder="Finance reporting" /></Label>
      <div className="config-section"><div className="panel-heading"><div><p className="eyebrow">Sources</p><h3>Power BI inputs</h3></div><Button variant="outline" onClick={() => setDraft({ ...draft, sources: [...draft.sources, ""] })}>Add source</Button></div><p className="muted-copy">Use full Windows paths for PBIP projects or model JSON files.</p>{draft.sources.length ? <div className="source-list">{draft.sources.map((source, index) => <div className="source-row" key={index}><Input value={source} onChange={(event) => updateSource(index, event.target.value)} placeholder="C:\\Reports\\Finance\\Finance.pbip" aria-label={`Source ${index + 1}`} /><Button variant="ghost" size="icon" onClick={() => setDraft({ ...draft, sources: draft.sources.filter((_, sourceIndex) => sourceIndex !== index) })} aria-label={`Remove source ${index + 1}`}>×</Button></div>)}</div> : <EmptyState title="No sources" detail="Add a PBIP project or model JSON file." />}</div>
      <div className="readonly-grid"><Label className="config-field"><span>Brain database</span><Input value={draft.database || ""} readOnly /><small>Configured by the local server. Restart after changing it on disk.</small></Label><Label className="config-field"><span>Identity map</span><Input value={draft.identity_map || ""} readOnly /><small>Configured by the local server. Restart after changing it on disk.</small></Label></div>
      <div className="config-actions"><Button onClick={save} disabled={saving}>{saving ? "Saving…" : "Save configuration"}</Button><Button variant="outline" onClick={onScan}>Scan saved sources</Button>{message ? <span className={message === "Saved" ? "success-text" : "error-copy"}>{message}</span> : null}</div>
    </Card>
  </>;
}

function Inspector({ node, error, snapshot, onSelect, onReview, onGraph, colors }) {
  if (!node) return <><PageHeading kicker="Object inspector" title={error ? "Object unavailable" : "Select an object"} description={error || "Choose a node from the graph or a target from the review queue."} action={<Button onClick={onGraph}>Open graph <span>→</span></Button>} /><div className="panel empty-inspector"><EmptyState title={error ? "Could not load object" : "Nothing selected"} detail={error || "The inspector shows identity, lineage, evidence, and review actions."} /></div></>;
  const outgoing = snapshot.edges.filter((edge) => edge.from_id === node.id);
  const incoming = snapshot.edges.filter((edge) => edge.to_id === node.id);
  const candidates = snapshot.semantic_candidates.filter((item) => itemTarget(item) === node.id);
  const warnings = snapshot.conflicts.filter((item) => itemTarget(item) === node.id);
  const properties = node.properties || {};
  const internalKeys = new Set(["raw_source", "raw_metadata", "dax_ast", "daxAst", "dax_behaviors", "dax_evidence", "behaviors", "evidence"]);
  const fieldPriority = { expression: 0, format_string: 1, data_type: 2 };
  const fields = Object.entries(properties)
    .filter(([key]) => !internalKeys.has(key))
    .sort(([left], [right]) => (fieldPriority[left] ?? 999) - (fieldPriority[right] ?? 999) || left.localeCompare(right));
  const rawMetadata = node.raw_metadata ?? node.rawMetadata ?? node.properties?.raw_metadata ?? node.properties?.rawMetadata;
  const rawSource = node.raw_source ?? node.rawSource ?? node.properties?.raw_source ?? node.properties?.rawSource;
  const internalProperties = Object.fromEntries(Object.entries(properties).filter(([key]) => ["dax_ast", "daxAst", "dax_behaviors", "dax_evidence", "behaviors", "evidence"].includes(key)));
  const disclosedMetadata = Object.keys(internalProperties).length ? { ...(rawMetadata && typeof rawMetadata === "object" ? rawMetadata : rawMetadata === undefined ? {} : { raw_metadata: rawMetadata }), internal_properties: internalProperties } : rawMetadata;
  return (
    <>
      <PageHeading kicker="Object inspector" title={labelFor(node)} description={`${node.type} · ${shortId(node.id)}`} action={<Button variant="outline" onClick={onGraph}>Show in graph <span>↗</span></Button>} />
      <div className="inspector-layout">
        <div className="inspector-main">
          <Card className="block gap-0 p-0 shadow-none panel identity-panel"><div className="object-heading"><span className="object-icon" style={{ color: artifactColor(node, colors), backgroundColor: `${artifactColor(node, colors)}20` }}>{node.type.slice(0, 2)}</span><div><p className="eyebrow">{node.type}</p><h3>{labelFor(node)}</h3></div><StatusBadge value={node.status} /></div><dl className="identity-grid"><div><dt>Canonical ID</dt><dd className="mono">{node.id}</dd></div><div><dt>Source ID</dt><dd className="mono">{node.source_id || "—"}</dd></div><div><dt>Model</dt><dd>{node.model_id || "—"}</dd></div><div><dt>Report</dt><dd>{node.report_id || "—"}</dd></div></dl></Card>
          <Card className="block gap-0 p-0 shadow-none panel"><PanelTitle eyebrow="Meaning" title="Description & metadata" />{node.description ? <p className="description-copy">{formatValue(node.description)}</p> : <p className="muted-copy">No description available.</p>}{fields.length ? <div className="metadata-table">{fields.map(([key, value]) => <div key={key}><span>{key.replace(/_/g, " ")}</span><strong>{formatValue(value)}</strong></div>)}</div> : null}<RawDetails rawMetadata={disclosedMetadata} rawSource={rawSource} /></Card>
          <Card className="block gap-0 p-0 shadow-none panel"><PanelTitle eyebrow="Lineage" title="Relationships" /><RelationshipGroup title="Dependencies" nodeId={node.id} edges={outgoing.filter((edge) => edge.type === "DEPENDS_ON")} nodes={snapshot.nodes} onSelect={onSelect} empty="No measure dependencies." /><RelationshipGroup title="Dependents" nodeId={node.id} edges={incoming.filter((edge) => edge.type === "DEPENDS_ON")} nodes={snapshot.nodes} onSelect={onSelect} empty="No dependents." /><RelationshipGroup title="All connected" nodeId={node.id} edges={[...outgoing, ...incoming].filter((edge) => edge.type !== "DEPENDS_ON")} nodes={snapshot.nodes} onSelect={onSelect} empty="No other relationships." /></Card>
        </div>
        <aside className="inspector-side"><Card className="block gap-0 p-0 shadow-none panel action-panel"><PanelTitle eyebrow="Review state" title="Human decision" /><StatusBadge value={node.status} large />{candidates.length ? <div className="action-list">{candidates.map((item) => <CandidateActions key={item.id || item.target} item={item} onReview={onReview} />)}</div> : <p className="muted-copy">No semantic candidate targets this object.</p>}</Card><Card className="block gap-0 p-0 shadow-none panel"><PanelTitle eyebrow="Evidence" title="Semantic signals" />{candidates.length ? <div className="evidence-list">{candidates.map((item) => <EvidenceCard key={item.id || item.target} item={item} />)}</div> : <p className="muted-copy">No inferred meaning recorded.</p>}{warnings.map((warning) => <div className="warning-card" key={warning.id || formatEvidence(warning.reason)}><strong>Conflict</strong><p>{formatEvidence(warning.reason || warning.message || warning.description || "Conflicting evidence needs review.")}</p></div>)}</Card><Card className="block gap-0 p-0 shadow-none panel"><PanelTitle eyebrow="Usage" title="Observed report usage" />{snapshot.edges.filter((edge) => edge.type === "OBSERVED_WITH" && (edge.from_id === node.id || edge.to_id === node.id)).map((edge) => <div className="usage-row" key={edge.id}><span>{shortId(edge.from_id === node.id ? edge.to_id : edge.from_id)}</span><strong>{formatValue(edge.properties?.count || edge.count || "observed")}</strong></div>)}{!snapshot.edges.some((edge) => edge.type === "OBSERVED_WITH" && (edge.from_id === node.id || edge.to_id === node.id)) ? <p className="muted-copy">No observed co-occurrence.</p> : null}<p className="footnote">Observed usage is evidence, not compatibility.</p></Card></aside>
      </div>
    </>
  );
}

function RawDetails({ rawMetadata, rawSource }) {
  if (rawMetadata === undefined && rawSource === undefined) return null;
  return <details className="raw-details"><summary>Raw source payload</summary><div className="raw-blocks">{rawMetadata !== undefined ? <div><span>raw_metadata</span><pre>{safeJson(rawMetadata)}</pre></div> : null}{rawSource !== undefined ? <div><span>raw_source</span><pre>{safeJson(rawSource)}</pre></div> : null}</div></details>;
}

function RelationshipGroup({ title, nodeId, edges, nodes, onSelect, empty }) {
  return <div className="relationship-group"><div className="relationship-title">{title}<span>{edges.length}</span></div>{edges.length ? <div className="relationship-list">{edges.slice(0, 10).map((edge) => { const targetId = edge.from_id === nodeId ? edge.to_id : edge.from_id; const resolved = nodes.find((node) => node.id === targetId); return <Button variant="ghost" className="relationship-row" key={edge.id} onClick={() => resolved && onSelect(resolved.id, "inspector")}><span className="edge-chip" style={{ background: EDGE_COLORS[edge.type] || "#738294" }} /> <span>{edge.type}</span><strong>{resolved ? labelFor(resolved) : shortId(targetId)}</strong></Button>; })}</div> : <p className="muted-copy compact">{empty}</p>}</div>;
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
    const key = issue === "conflict" ? semanticKey : item.id || semanticKey;
    merged.set(key, { ...merged.get(key), ...item, issue });
  });
  return [...merged.values()];
}

function itemScopeValue(item, node, key) {
  return item?.[key] ?? item?.properties?.[key] ?? node?.[key] ?? node?.properties?.[key] ?? "";
}

function ReviewQueue({ snapshot, onSelect, onReview }) {
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
  const all = mergeReviewItems([...candidates, ...conflicts, ...external, ...stale]);
  const types = [...new Set(all.map((item) => snapshot.nodes.find((node) => node.id === itemTarget(item))?.type).filter(Boolean))].sort();
  const models = [...new Set(all.map((item) => itemScopeValue(item, snapshot.nodes.find((node) => node.id === itemTarget(item)), "model_id")).filter(Boolean))].sort();
  const reports = [...new Set(all.map((item) => itemScopeValue(item, snapshot.nodes.find((node) => node.id === itemTarget(item)), "report_id")).filter(Boolean))].sort();
  const filtered = all.filter((item) => {
    const targetNode = snapshot.nodes.find((node) => node.id === itemTarget(item));
    return (issue === "ALL" || item.issue === issue)
      && (objectType === "ALL" || targetNode?.type === objectType)
      && (modelId === "ALL" || itemScopeValue(item, targetNode, "model_id") === modelId)
      && (reportId === "ALL" || itemScopeValue(item, targetNode, "report_id") === reportId)
      && item.status !== "rejected" && item.status !== "approved";
  }).sort((a, b) => {
    if (sort === "confidence-low") return itemConfidence(a) - itemConfidence(b);
    if (sort === "impact-high") return itemImpact(b) - itemImpact(a);
    if (sort === "impact-low") return itemImpact(a) - itemImpact(b);
    return itemConfidence(b) - itemConfidence(a);
  });
  return <><PageHeading kicker="Human review" title="Review queue" description="Resolve semantic uncertainty and conflicts. Facts stay automatic." action={<span className="queue-count">{filtered.length} open items</span>} /><div className="queue-toolbar panel"><Label className="select-field"><span>Issue</span><NativeSelect value={issue} onChange={(event) => setIssue(event.target.value)}><option value="ALL">All issues</option><option value="candidate">Candidates</option><option value="conflict">Conflicts</option><option value="stale">Stale overrides</option></NativeSelect></Label><Label className="select-field"><span>Object</span><NativeSelect value={objectType} onChange={(event) => setObjectType(event.target.value)}><option value="ALL">All types</option>{types.map((type) => <option key={type} value={type}>{type}</option>)}</NativeSelect></Label><Label className="select-field"><span>Model</span><NativeSelect value={modelId} onChange={(event) => setModelId(event.target.value)}><option value="ALL">All models</option>{models.map((value) => <option key={value} value={value}>{shortId(value)}</option>)}</NativeSelect></Label><Label className="select-field"><span>Report</span><NativeSelect value={reportId} onChange={(event) => setReportId(event.target.value)}><option value="ALL">All reports</option>{reports.map((value) => <option key={value} value={value}>{shortId(value)}</option>)}</NativeSelect></Label><Label className="select-field"><span>Sort</span><NativeSelect value={sort} onChange={(event) => setSort(event.target.value)}><option value="confidence-high">Confidence ↓</option><option value="confidence-low">Confidence ↑</option><option value="impact-high">Impact ↓</option><option value="impact-low">Impact ↑</option></NativeSelect></Label></div><Card className="block gap-0 p-0 shadow-none panel queue-panel">{filtered.length ? <div className="queue-list">{filtered.map((item) => <ReviewItem key={item.id || `${item.issue}-${itemTarget(item)}`} item={item} nodes={snapshot.nodes} onSelect={onSelect} onReview={onReview} />)}</div> : <EmptyState title="Queue is clear" detail="No unresolved semantic items match these filters." />}</Card></>;
}

function ReviewItem({ item, nodes, onSelect, onReview }) {
  const target = itemTarget(item);
  const targetNode = nodes.find((node) => node.id === target);
  return <div className="review-item"><Button variant="ghost" className="review-target" onClick={() => targetNode && onSelect(targetNode.id, "inspector")}><span className={`review-dot ${item.issue}`} /> <span><strong>{formatValue(item.value || item.meaning || item.reason || item.message || item.issue)}</strong><small>{targetNode ? `${targetNode.type} · ${labelFor(targetNode)}` : shortId(target)}</small></span></Button><div className="review-evidence">{formatEvidence(item.evidence?.[0] ?? item.reason)}</div><div className="review-score"><strong>{confidence(itemConfidence(item)) === null ? "—" : `${confidence(itemConfidence(item))}%`}</strong><small>impact {itemImpact(item)} · {item.status || "candidate"}</small></div><div className="review-actions"><Button variant="ghost" className="approve-button" onClick={() => onReview("approve", item)}>Approve</Button><Button variant="ghost" className="reject-button" onClick={() => onReview("reject", item)}>Reject</Button></div></div>;
}

function CandidateRow({ item, onSelect, onReview }) {
  const target = itemTarget(item);
  return <div className="candidate-row"><Button variant="ghost" onClick={() => onSelect(target)}><span className="candidate-symbol">◌</span><span><strong>{formatValue(item.value || item.meaning || "Semantic candidate")}</strong><small>{shortId(target)}</small></span></Button><span className="confidence-pill">{confidence(itemConfidence(item)) ?? "—"}%</span><Button variant="link" onClick={onReview}>Review →</Button></div>;
}

function CandidateActions({ item, onReview }) {
  const [editingAction, setEditingAction] = useState("");
  const [value, setValue] = useState(item.value || item.meaning || "");
  const beginEdit = (action) => { setValue(item.value || item.meaning || ""); setEditingAction(action); };
  return <div className="candidate-actions"><div className="candidate-action-title"><span>{formatValue(item.value || item.meaning || "Unlabeled candidate")}</span><span>{confidence(itemConfidence(item)) ?? "—"}%</span></div>{editingAction ? <div className="edit-row"><Input value={value} onChange={(event) => setValue(event.target.value)} aria-label={`${editingAction} semantic value`} /><Button variant="ghost" className="approve-button" onClick={() => { onReview(editingAction, item, value); setEditingAction(""); }}>{editingAction === "edit" ? "Save edit" : "Save override"}</Button><Button variant="link" onClick={() => setEditingAction("")}>Cancel</Button></div> : <div className="action-buttons"><Button variant="ghost" className="approve-button" onClick={() => onReview("approve", item)}>Approve</Button><Button variant="outline" onClick={() => beginEdit("edit")}>Edit</Button><Button variant="ghost" className="reject-button" onClick={() => onReview("reject", item)}>Reject</Button><Button variant="link" onClick={() => beginEdit("override")}>Override</Button></div>}</div>;
}

function EvidenceCard({ item }) {
  return <div className="evidence-card"><div><span className="evidence-source">{formatValue(item.source || "inference")}</span><StatusBadge value={item.status || "candidate"} /></div><p>{formatEvidence(item.evidence?.[0] ?? item.reason ?? "Evidence recorded by the inference engine.")}</p><small>{formatValue(item.evidence_class || "INFERRED")} · deterministic score</small></div>;
}

function PanelTitle({ eyebrow, title }) { return <div className="panel-heading"><div><p className="eyebrow">{eyebrow}</p><h3>{title}</h3></div></div>; }
function StatusBadge({ value, large = false }) { return <Badge variant="outline" className={`status-badge ${large ? "large" : ""} ${statusClass(value)}`}><i />{value || "factual"}</Badge>; }
function LegendDot({ className, label }) { return <span><i className={`legend-dot ${className}`} />{label}</span>; }
function LegendLine({ className, label }) { return <span><i className={`legend-line ${className}`} />{label}</span>; }
function EmptyState({ title, detail, action }) { return <div className="empty-state"><span className="empty-mark">○</span><strong>{title}</strong><p>{detail}</p>{action}</div>; }
function truncate(value, length) { const text = String(value || ""); return text.length > length ? `${text.slice(0, length - 1)}…` : text; }
function formatDate(value) { if (!value || value === "Not scanned") return value || "Not scanned"; const date = new Date(value); return Number.isNaN(date.valueOf()) ? String(value) : date.toLocaleString([], { dateStyle: "medium", timeStyle: "short" }); }
function formatValue(value) { return safeJson(value); }

export default App;
