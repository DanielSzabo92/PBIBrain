import VisualBindings from "./components/VisualBindings";
import ImpactExplorer from "./components/ImpactExplorer";
import React, { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, ArrowUpRight, Boxes, Check, ChartColumn, ChevronRight, CircleCheck, Copy, Database, FileText, FolderOpen, Moon, Plus, RefreshCw, ScanLine, ShieldAlert, ShieldCheck, Sparkles, Sun, TriangleAlert, Waypoints, X } from "lucide-react";
import { brainTransport, normalizeSnapshot } from "./transport";
import { desktopRequest, subscribeToDesktopBridge } from "./desktop";
import NavIcon from "./NavIcon";
import BrandMark from "./components/BrandMark";
import { highlightDax } from "./dax";
import { objectName, objectScope, readableText, publicProperties, scopeChoices, statusLabel, suggestionLabel } from "./presentation";
import { Button } from "./components/ui/button";
import { Input } from "./components/ui/input";
import { NativeSelect } from "./components/ui/native-select";
import { Badge } from "./components/ui/badge";
import { Card } from "./components/ui/card";
import { Label } from "./components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "./components/ui/tabs";
const GraphView = lazy(() => import("./components/GraphView"));
const GraphColors = lazy(() => import("./components/GraphColors"));
const ModelSummary = lazy(() => import("./components/ModelSummary"));
import { artifactColor, normalizeColors, typeLabel } from "./graphPresentation";

const VIEWS = [
  ["overview", "Overview"],
  ["search", "Search"],
  ["graph", "Graph"],
  ["inspector", "Inspector"],
  ["review", "Review queue"],
  ["config", "Settings"],
];

const VIEW_HINTS = {
  overview: "Project health at a glance",
  search: "Names, formulas and descriptions",
  graph: "How objects depend on each other",
  inspector: "One object, fully explained",
  review: "Confirm what PBIBrain inferred",
  config: "Appearance, sources and agent context",
};

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
  return /expression/i.test(field) ? "In formula" : /description/i.test(field) ? "In description" : "";
}

const THEME_KEY = "pbibrain-theme";

function readTheme() {
  try { return globalThis.localStorage?.getItem(THEME_KEY) === "light" ? "light" : "dark"; } catch { return "dark"; }
}

function useTheme() {
  const [theme, setTheme] = useState(readTheme);
  useEffect(() => {
    const root = document.documentElement;
    root.classList.toggle("dark", theme === "dark");
    if (theme === "light") root.dataset.theme = "light";
    else delete root.dataset.theme;
    try { globalThis.localStorage?.setItem(THEME_KEY, theme); } catch { /* Storage can be unavailable. */ }
  }, [theme]);
  return [theme, () => setTheme((current) => current === "dark" ? "light" : "dark")];
}

function App({ transport = brainTransport }) {
  const desktopHost = Boolean(globalThis.__PBIBRAIN_DESKTOP__);
  const [theme, toggleTheme] = useTheme();
  const [snapshot, setSnapshot] = useState(() => normalizeSnapshot(null));
  const [snapshotLoaded, setSnapshotLoaded] = useState(false);
  const [snapshotLoading, setSnapshotLoading] = useState(false);
  const [snapshotError, setSnapshotError] = useState("");
  const [overview, setOverview] = useState({});
  const [config, setConfig] = useState(null);
  const [configError, setConfigError] = useState("");
  const graphColors = useMemo(() => normalizeColors(config?.graph_colors), [config?.graph_colors]);
  const [view, setView] = useState("overview");
  const currentView = useRef(view);
  currentView.current = view;
  const [searchSession, setSearchSession] = useState({ query: "", modelId: "", reportId: "", result: null });
  const [inspectorSession, setInspectorSession] = useState({ query: "", modelId: "", reportId: "", objectType: "MEASURE", result: null });
  const [settingsTab, setSettingsTab] = useState("project");
  const [graphSession, setGraphSession] = useState(null);
  const [reviewSession, setReviewSession] = useState({ issue: "ALL", objectType: "ALL", modelId: "ALL", reportId: "ALL", sort: "confidence-high" });
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
  const projectGeneration = useRef(0);

  const load = useCallback(async () => {
    const requestId = ++loadRequest.current;
    setLoading(true);
    setError("");
    setConfigError("");
    const [overviewResult, configResult] = await Promise.allSettled([transport.getOverview(), transport.getConfig()]);
    if (requestId !== loadRequest.current) return;
    if (overviewResult.status === "fulfilled") setOverview(overviewResult.value || {});
    if (configResult.status === "fulfilled") setConfig(configResult.value || {});
    else setConfigError(configResult.reason?.message || "Project settings could not be loaded");
    if (overviewResult.status === "rejected") {
      setError(overviewResult.reason?.message || "Brain could not be loaded");
    }
    setLoading(false);
  }, [transport]);

  const loadSnapshot = useCallback(async () => {
    const requestId = ++snapshotRequest.current;
    setSnapshotLoading(true);
    setSnapshotError("");
    try {
      const next = normalizeSnapshot(await transport.getSnapshot());
      if (requestId === snapshotRequest.current) {
        setSnapshot(next);
        setSnapshotLoaded(true);
      }
      return next;
    } catch (cause) {
      if (requestId === snapshotRequest.current) setSnapshotError(cause.message || "Review data could not be loaded");
      throw cause;
    } finally {
      if (requestId === snapshotRequest.current) setSnapshotLoading(false);
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
    projectGeneration.current += 1;
    loadRequest.current += 1;
    snapshotRequest.current += 1;
    selectionRequest.current += 1;
  }, []);

  const resetProjectView = useCallback(() => {
    invalidateProjectRequests();
    setSnapshot(normalizeSnapshot(null));
    setSnapshotLoaded(false);
    setSnapshotLoading(false);
    setSnapshotError("");
    setOverview({});
    setConfig(null);
    setConfigError("");
    setGraphSession(null);
    setReviewSession({ issue: "ALL", objectType: "ALL", modelId: "ALL", reportId: "ALL", sort: "confidence-high" });
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
    return { ...current, models: numberOr(overview.models, current.models), reports: numberOr(overview.reports, current.reports), objects: numberOr(overview.counts?.nodes ?? overview.objects, current.objects), edges: numberOr(overview.counts?.edges ?? overview.edges, current.edges), candidates: numberOr(overview.review_counts?.candidate ?? overview.candidate_count, current.candidates), warnings: numberOr(overview.review_counts?.conflict ?? overview.warning_count, current.warnings), stale: numberOr(overview.review_counts?.stale), review: numberOr(overview.review_count, numberOr(overview.candidate_count, current.candidates) + numberOr(overview.warning_count, current.warnings)) };
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
    invalidateProjectRequests();
    setSnapshotLoading(false);
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
      setSnapshotLoading(false);
      setSnapshotError("");
      setGraphSession(null);
      setInspectorSession((current) => ({ ...current, result: null, revision: (current.revision || 0) + 1 }));
      setSearchSession((current) => ({ ...current, result: null, selectedId: null, scrollY: 0, revision: (current.revision || 0) + 1 }));
      setNotice("Scan complete");
      await load();
      if (currentView.current === "review") await loadSnapshot();
    } catch (cause) {
      setOperationError(cause.message || "Scan failed");
    } finally {
      scanInFlight.current = false;
      setScanning(false);
      setLoading(false);
    }
  }, [invalidateProjectRequests, load, loadSnapshot, transport]);

  const review = useCallback(
    async (action, item, value = undefined) => {
      if (scanInFlight.current) return false;
      const generation = projectGeneration.current;
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
        if (generation !== projectGeneration.current) return false;
        const returned = result?.snapshot || result?.brain;
        if (returned) {
          setSnapshot(normalizeSnapshot(returned));
          setSnapshotLoaded(true);
        }
        else {
          setSnapshot((current) => ({
            ...current,
            semantic_candidates: current.semantic_candidates.map((candidate) =>
              candidate.id === item.id ? { ...candidate, value: value === undefined ? candidate.value : value, status: action === "approve" ? "approved" : action === "reject" ? "rejected" : action === "override" ? "overridden" : candidate.status || "candidate" } : candidate,
            ),
          }));
        }
        setNotice({ approve: "Suggestion approved", reject: "Suggestion rejected", edit: "Suggestion updated", override: "Meaning updated", remove: "Saved decision removed" }[action] || "Review updated");
        await Promise.allSettled([loadSnapshot(), load()]);
        return true;
      } catch (cause) {
        if (generation !== projectGeneration.current) return false;
        setNotice("Review failed. Try again.");
        return false;
      }
    },
    [transport, loadSnapshot, load],
  );

  const navigate = useCallback((key) => {
    setView(key);
    if (key === "review") loadSnapshot().catch(() => {});
  }, [loadSnapshot]);

  // Ctrl/Cmd+K (or "/" outside a text field) jumps straight to search.
  useEffect(() => {
    const onKey = (event) => {
      const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(event.target?.tagName) || event.target?.isContentEditable;
      if (((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") || (event.key === "/" && !typing && !event.ctrlKey && !event.metaKey)) {
        event.preventDefault();
        setView("search");
        requestAnimationFrame(() => document.querySelector(".search-field input")?.focus());
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (desktopHost && desktopState !== "ready") {
    return <DesktopConnecting error={desktopError} onRetry={() => setBridgeAttempt((attempt) => attempt + 1)} />;
  }

  if (desktopApi && !desktopSession?.project) {
    return <DesktopOnboarding api={desktopApi} error={desktopError} onOpen={openDesktopProject} />;
  }

  const activeProject = desktopSession?.project;
  const projectName = activeProject?.name || config?.name || "PBIBrain";
  const pending = counts.review;
  const connection = loading ? "loading" : error ? "error" : "ready";
  const reloadBrain = () => {
    setInspectorSession((current) => ({ ...current, result: null, revision: (current.revision || 0) + 1 }));
    setSearchSession((current) => ({ ...current, result: null, revision: (current.revision || 0) + 1 }));
    setGraphSession((current) => current ? { ...current, result: null, revision: (current.revision || 0) + 1 } : null);
    load();
    if (view === "inspector" && selectedId) selectNode(selectedId);
    else if (snapshotLoaded || view === "review") loadSnapshot().catch(() => {});
  };
  const failedNotice = /failed/i.test(String(notice));
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">Skip to content</a>
      <aside className="sidebar">
        <div className="sidebar-brand">
          <BrandMark size={28} />
          <span className="sidebar-wordmark">PBIBrain</span>
        </div>
        <nav aria-label="Main navigation" className="sidebar-nav">
          {VIEWS.map(([key, label]) => (
            <Button variant="ghost" key={key} aria-current={view === key ? "page" : undefined} className={`nav-button ${view === key ? "active" : ""} ${key === "config" ? "nav-settings" : ""}`} onClick={() => navigate(key)}>
              <NavIcon name={key} />
              <span className="nav-label">{label}</span>
              {key === "review" && pending > 0 ? <span className="nav-count">{pending > 99 ? "99+" : pending}</span> : null}
              {key === "search" ? <kbd className="nav-kbd" aria-hidden="true">Ctrl K</kbd> : null}
            </Button>
          ))}
        </nav>
        <div className="sidebar-footer">
          <span className={`connection connection-${connection}`} title={loading ? "Loading" : error ? "Offline" : "Connected"}><i />{loading ? "Loading" : error ? "Offline" : "Connected"}</span>
          <Button variant="ghost" size="icon-sm" className="theme-toggle" onClick={toggleTheme} aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"} title={theme === "dark" ? "Light theme" : "Dark theme"}>{theme === "dark" ? <Sun /> : <Moon />}</Button>
        </div>
      </aside>

      <div className="main-column">
        <header className="topbar">
          <div className="breadcrumb">
            <span className="project-avatar" aria-hidden="true">{projectName.trim().slice(0, 1).toUpperCase() || "P"}</span>
            <span className="breadcrumb-project" title={projectName}>{projectName}</span>
            <ChevronRight className="breadcrumb-sep" aria-hidden="true" />
            <span className="breadcrumb-view">{VIEWS.find(([key]) => key === view)?.[1]}</span>
            <span className="breadcrumb-hint">{VIEW_HINTS[view]}</span>
          </div>
          <div className="topbar-actions">
            {scanning ? <span className="topbar-scanning"><RefreshCw className="spin" aria-hidden="true" />Scanning</span> : null}
            {activeProject ? <Button variant="ghost" size="sm" className="project-switch" onClick={closeDesktopProject} disabled={scanning}><FolderOpen />Change project</Button> : null}
            <Button variant="ghost" size="icon-sm" onClick={reloadBrain} disabled={loading || scanning} title="Reload Brain" aria-label="Reload Brain"><RefreshCw className={loading ? "spin" : ""} /></Button>
          </div>
        </header>

        <main id="main-content" tabIndex={-1} className={`content content-${view}`}>
          {notice ? <div className={`toast ${failedNotice ? "toast-error" : ""}`} role="status">{failedNotice ? <TriangleAlert aria-hidden="true" /> : <CircleCheck aria-hidden="true" />}{notice}</div> : null}
          {error || configError || operationError || desktopError ? (
            <div className="error-banner" role="alert">
              <TriangleAlert aria-hidden="true" />
              <span>{readableText(error || configError || operationError || desktopError)}</span>
              {error || configError ? <Button variant="outline" size="sm" onClick={load}>Retry</Button> : null}
            </div>
          ) : null}
          <div className="view-frame" key={view}>
            <Suspense fallback={<div className="view-loading" role="status"><RefreshCw className="spin" aria-hidden="true" />Loading view…</div>}>
            {view === "overview" ? <Overview onSelect={selectNode} overview={overview} config={config} counts={counts} loading={loading} projectName={projectName} onView={navigate} onSearch={(query) => { setSearchSession({ query, modelId: "", reportId: "", result: null }); setView("search"); }} onSources={() => { setSettingsTab("project"); setView("config"); }} onSummary={() => { setSettingsTab("summary"); setView("config"); }} onScan={applyScan} scanning={scanning} scanLabel={activeProject ? "Scan project" : "Scan sources"} onReview={() => navigate("review")} /> : null}
            {view === "search" ? <div className="page page-narrow"><SearchView session={searchSession} onSession={setSearchSession} colors={graphColors} transport={transport} overview={overview} onSelect={selectNode} /></div> : null}
            {view === "graph" ? <GraphView session={graphSession} onSession={setGraphSession} colors={graphColors} transport={transport} overview={overview} snapshot={snapshot} selectedId={selectedId} onSelect={selectNode} /> : null}
            {view === "inspector" ? <div className="page page-wide">{selectedId ? <><Button variant="ghost" size="sm" className="inspector-back" onClick={() => { if (inspectorOrigin === "inspector") { setSelectedId(null); setInspectedObject(null); } else setView(inspectorOrigin); }}><ArrowLeft aria-hidden="true" />{inspectorOrigin === "search" ? "Back to results" : inspectorOrigin === "inspector" ? "Browse objects" : `Back to ${VIEWS.find(([key]) => key === inspectorOrigin)?.[1]?.toLowerCase() || "overview"}`}</Button><Inspector key={selectedId} transport={transport} scanning={scanning} colors={graphColors} node={selected} details={inspectedDetails} loading={Boolean(selectedId && !inspectedDetails && !inspectorError)} error={inspectorError} snapshot={snapshot} snapshotLoaded={snapshotLoaded} snapshotError={snapshotError} onEvidenceRetry={() => loadSnapshot().catch(() => {})} overview={overview} onSelect={selectNode} onRetry={() => selectNode(selectedId)} onReview={review} onGraph={() => setView("graph")} /></> : <SearchView browse session={inspectorSession} onSession={setInspectorSession} colors={graphColors} transport={transport} overview={overview} onSelect={(id) => { setInspectorOrigin("inspector"); selectNode(id); }} />}</div> : null}
            {view === "review" ? <div className="page page-wide"><ReviewQueue scanning={scanning} session={reviewSession} onSession={setReviewSession} snapshot={snapshot} loaded={snapshotLoaded} loading={!snapshotLoaded && (snapshotLoading || !snapshotError)} error={snapshotError} onRetry={() => loadSnapshot().catch(() => {})} overview={overview} onSelect={selectNode} onReview={review} /></div> : null}
            {view === "config" ? <div className="page page-narrow"><PageHeading title="Settings" description="Manage project sources, graph appearance, and model context." />{configError && !config ? <Card className="panel"><EmptyState icon={<TriangleAlert />} tone="bad" title="Project settings unavailable" detail="Retry to load your saved sources and appearance." action={<Button variant="outline" onClick={load}>Retry settings</Button>} /></Card> : <Tabs value={settingsTab} onValueChange={setSettingsTab} className="settings-tabs">
              <TabsList aria-label="Settings sections"><TabsTrigger value="project">Project</TabsTrigger><TabsTrigger value="colors">Graph colors</TabsTrigger><TabsTrigger value="summary">Model summary</TabsTrigger></TabsList>
              <TabsContent value="colors"><Suspense fallback={<ViewLoading />}><GraphColors config={config} transport={transport} overview={overview} onSaved={setConfig} /></Suspense></TabsContent>
              <TabsContent value="summary"><Suspense fallback={<ViewLoading />}><ModelSummary overview={overview} transport={transport} scanning={scanning} /></Suspense></TabsContent>
              <TabsContent value="project">{activeProject ? <DesktopProjectView api={desktopApi} project={activeProject} overview={overview} config={config} transport={transport} scanning={scanning} onScan={applyScan} onChange={closeDesktopProject} onRefresh={load} onSaved={setConfig} /> : <ConfigView transport={transport} config={config} onSaved={setConfig} onScan={applyScan} scanning={scanning} />}</TabsContent></Tabs>}</div> : null}
            </Suspense>
          </div>
        </main>
      </div>
    </div>
  );
}

function ViewLoading() {
  return <div className="view-loading" role="status"><RefreshCw className="spin" aria-hidden="true" />Loading view…</div>;
}

function DesktopConnecting({ error, onRetry }) {
  return <main className="onboarding-shell"><Card className="onboarding-card connecting-card" aria-live="polite"><BrandMark size={44} className="onboarding-mark" /><p className="eyebrow">PBIBrain</p><h1>{error ? "Desktop connection needed" : "Opening PBIBrain"}</h1><p className="onboarding-copy">{error || "Preparing your private project workspace."}</p>{error ? <Button onClick={onRetry}><RefreshCw />Retry connection</Button> : <span className="connecting-indicator"><i /><i /><i /><span>Connecting</span></span>}</Card></main>;
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
    <Card className="onboarding-card" aria-labelledby="onboarding-title">
      <BrandMark size={44} className="onboarding-mark" />
      <p className="eyebrow">PBIBrain</p>
      <h1 id="onboarding-title">Start a project brain</h1>
      <p className="onboarding-copy">Choose one folder. PBIBrain keeps the project, scan results, and agent-ready context together.</p>
      <form onSubmit={open} className="onboarding-form">
        <Label className="config-field"><span>Project name</span><Input autoFocus value={name} onChange={(event) => setName(event.target.value)} placeholder="Finance reporting" disabled={working} /></Label>
        <div className="config-field"><Label htmlFor="project-folder">Project folder</Label><div className="folder-picker"><Input id="project-folder" value={folder} onChange={(event) => setFolder(event.target.value)} placeholder="Paste a folder path or browse" title={folder || "Project folder path"} disabled={working} /><Button variant="outline" type="button" onClick={chooseFolder} disabled={working}><FolderOpen />{folder ? "Change folder" : "Choose folder"}</Button></div></div>
        {message ? <p className="onboarding-error" role="alert"><TriangleAlert aria-hidden="true" />{message}</p> : null}
        <Button size="lg" className="onboarding-submit" disabled={working}>{working ? "Opening…" : "Open project"} <ArrowRight aria-hidden="true" /></Button>
      </form>
      <p className="onboarding-note">Your Power BI files are only read, never changed.</p>
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
    <PageHeading kicker="Desktop project" title={project.name} description="Everything PBIBrain creates stays with this project folder." action={<Button variant="outline" onClick={onChange} disabled={scanning}><FolderOpen />Change project</Button>} />
    <Card className="panel desktop-project-panel">
      <div className="project-location"><span className="icon-tile" aria-hidden="true"><FolderOpen /></span><div><p className="eyebrow">Project folder</p><strong title={project.folder}>{project.folder}</strong></div></div>
      <div className="desktop-sources"><div className="panel-heading"><div><p className="eyebrow">Power BI inputs</p><h3>Source files</h3></div><Button variant="outline" onClick={addSources} disabled={sourceWorking || scanning}><Plus />{sourceWorking ? "Adding…" : "Add source files"}</Button></div>{sources.length ? <div className="source-list">{sources.map((source) => <div className="desktop-source-row" key={source}><FileText className="source-icon" aria-hidden="true" /><span title={source}>{source}</span><Button variant="ghost" size="icon-sm" onClick={() => removeSource(source)} disabled={sourceWorking || scanning} aria-label={`Remove ${source}`}><X /></Button></div>)}</div> : <EmptyState icon={<FileText />} title="No source files yet" detail="Add PBIP projects or model JSON files to scan them with this project." />}{sourceError ? <p className="onboarding-error" role="alert">{sourceError}</p> : null}</div>
      <div className="config-actions"><Button onClick={onScan} disabled={scanning}><ScanLine />{scanning ? "Scanning…" : "Scan project"}</Button></div>
    </Card>
  </>;
}

function PageHeading({ kicker, title, description, action, children }) {
  return (
    <div className="page-heading">
      <div className="page-heading-copy">
        {kicker ? <p className="eyebrow">{kicker}</p> : null}
        {children}
        <h1>{title}</h1>
        {description ? <p className="page-description">{description}</p> : null}
      </div>
      {action ? <div className="page-heading-action">{action}</div> : null}
    </div>
  );
}

function Overview({ overview, config, counts, loading, projectName, onView, onSearch, onSources, onSummary, onScan, onReview, onSelect, scanning, scanLabel }) {
  const [query, setQuery] = useState("");
  const hasObjects = counts.objects > 0;
  const hasSources = Boolean(config?.sources?.length);
  const sourceCount = config?.sources?.length;
  const lastScan = overview.last_scan;
  const validationState = overview.validation_state || "not_run";
  const validationLabel = { valid: "Graph validation passed", invalid: "Graph validation failed", warning: "Graph validation warnings", not_run: "Graph validation not run" }[validationState] || "Graph validation unavailable";
  const issues = overview.validation_issues || [];
  const pending = counts.review;
  const ValidationIcon = validationState === "valid" ? ShieldCheck : ShieldAlert;
  const validation = <Card className={`overview-card validation-card tone-${validationState}`} role={validationState === "invalid" ? "alert" : "status"}>
    <div className="overview-card-head"><span className="icon-tile" aria-hidden="true"><ValidationIcon /></span><h3>{validationLabel}</h3></div>
    <p className="muted-copy">{validationState === "not_run" ? "Scan sources to check graph validity." : validationState === "invalid" ? "Sources were extracted, but graph issues need attention." : "Graph validity is checked separately from source extraction and review decisions."}</p>
    {issues.length ? <details className="validation-issues"><summary>View validation issues ({issues.length})</summary><ul>{issues.map((item, index) => <li key={`${item.code}-${index}`}><span className={`severity severity-${String(item.severity).toLowerCase()}`}>{item.severity}</span><span className="issue-message">{item.message}</span>{item.object_id || item.from_id || item.to_id ? <Button variant="link" size="sm" onClick={() => onSelect(item.object_id || item.from_id || item.to_id, "inspector")}>Inspect affected object</Button> : null}</li>)}</ul></details> : null}
  </Card>;
  const sourcesCard = <Card className="overview-card project-scan-bar">
    <div className="overview-card-head"><span className="icon-tile" aria-hidden="true"><Database /></span><div><strong>{scanning ? "Scanning sources…" : hasObjects ? "Sources indexed" : "Sources"}</strong><span className="scan-meta">{sourceCount === undefined ? "Source settings unavailable" : `${sourceCount} ${sourceCount === 1 ? "source" : "sources"}`}{hasObjects ? ` · ${lastScan ? `Last scan ${formatDate(lastScan)}` : "Last scan time unavailable"}` : ""}</span></div></div>
    <div className="project-scan-actions"><Button variant="ghost" size="sm" onClick={onSources}>Manage sources</Button>{hasObjects ? <Button variant="outline" size="sm" onClick={onScan} disabled={scanning || !hasSources}><RefreshCw className={scanning ? "spin" : ""} />{scanning ? "Scanning…" : scanLabel}</Button> : null}</div>
  </Card>;
  return <div className="page page-overview">
    <header className="overview-hero">
      <p className="eyebrow">Project overview</p>
      <h1>{projectName}</h1>
      <p className="hero-meta">{hasObjects ? <>{counts.objects.toLocaleString()} objects indexed{lastScan ? <> · last scan {formatDate(lastScan)}</> : null}</> : "Connect your Power BI sources to build the project brain."}</p>
    </header>
    {loading && !hasObjects ? <div className="overview-loading"><div className="skeleton skeleton-search" /><div className="skeleton-row">{[0, 1, 2, 3].map((index) => <div className="skeleton skeleton-stat" key={index} />)}</div><p role="status" className="sr-only">{scanning ? "Scanning sources…" : "Loading project…"}</p></div> : !hasObjects ?
      <div className="overview-grid">
        <Card className="project-start">
          <span className="icon-tile icon-tile-lg" aria-hidden="true">{hasSources ? <ScanLine /> : <Plus />}</span>
          <h3>{hasSources ? "Ready for the first scan" : "Add your project sources"}</h3>
          <p>{hasSources ? "Scan your files to find models, reports, and their dependencies." : "Choose your PBIP project or exported model and report files."}</p>
          <ol className="start-steps" aria-label="Getting started">
            <li className={hasSources ? "done" : "current"}><span>{hasSources ? <Check aria-hidden="true" /> : "1"}</span>Add PBIP or model files</li>
            <li className={hasSources ? "current" : ""}><span>2</span>Scan to index objects</li>
            <li><span>3</span>Explore, review, export context</li>
          </ol>
          <Button size="lg" onClick={hasSources ? onScan : onSources} disabled={!config || scanning}>{hasSources ? <ScanLine /> : <Plus />}{hasSources ? scanLabel : "Add sources"}</Button>
        </Card>
        <div className="overview-side">{validation}{sourcesCard}</div>
      </div> : <>
        <Card className="project-search-card">
          <Label htmlFor="project-search" className="project-search-label">Find an object</Label>
          <form className="project-search-form" onSubmit={(event) => { event.preventDefault(); if (query.trim()) onSearch(query.trim()); }}>
            <div className="command-input"><NavIcon name="search" size={18} /><Input type="search" id="project-search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Measure, table, column, or visual…" /><kbd aria-hidden="true">Enter</kbd></div>
            <Button type="submit" aria-label="Search project" disabled={!query.trim()}>Search <ArrowRight aria-hidden="true" /></Button>
          </form>
        </Card>
        <dl className="project-counts" aria-label="Project counts">
          {[["Models", counts.models, Database], ["Reports", counts.reports, ChartColumn], ["Objects", counts.objects, Boxes], ["Relationships", counts.edges, Waypoints]].map(([label, count, Icon]) => <div key={label} className="stat-tile"><dt><Icon aria-hidden="true" />{label}</dt><dd>{count.toLocaleString()}</dd></div>)}
        </dl>
        <div className="overview-grid">
          <div className="overview-main">
            <Card className={`project-review-card ${pending ? "has-pending" : ""}`}>
              <div className="review-card-count" aria-hidden="true"><strong>{pending}</strong><span>{pending === 1 ? "open item" : "open items"}</span></div>
              <div className="review-card-copy"><h3>{validationState === "invalid" ? "Resolve graph issues before review" : pending ? "Ready for review" : "No pending reviews"}</h3><p>{pending ? "Check suggested meanings and resolve uncertain matches." : "All suggestions have been reviewed."}</p>{counts.warnings || counts.stale ? <p className="review-card-split"><span>{counts.candidates} suggestions</span>{counts.warnings ? <span>{counts.warnings} conflicts</span> : null}{counts.stale ? <span>{counts.stale} outdated decisions</span> : null}</p> : null}</div>
              <Button variant={pending ? "default" : "outline"} onClick={onReview}>Open review queue <ArrowRight aria-hidden="true" /></Button>
            </Card>
            <div className="quick-actions">
              <Button variant="ghost" className="quick-action project-graph-link" onClick={() => onView("graph")}><span className="icon-tile" aria-hidden="true"><Waypoints /></span><span><strong>Explore relationships in the graph</strong><small>Trace lineage from model to visual</small></span><ArrowUpRight className="quick-arrow" aria-hidden="true" /></Button>
              <Button variant="ghost" className="quick-action" onClick={() => onView("inspector")}><span className="icon-tile" aria-hidden="true"><NavIcon name="inspector" /></span><span><strong>Browse measures</strong><small>Formulas, dependencies and usage</small></span><ArrowUpRight className="quick-arrow" aria-hidden="true" /></Button>
              <Button variant="ghost" className="quick-action" onClick={onSummary}><span className="icon-tile" aria-hidden="true"><Sparkles /></span><span><strong>Export agent context</strong><small>One Markdown file per model</small></span><ArrowUpRight className="quick-arrow" aria-hidden="true" /></Button>
            </div>
          </div>
          <div className="overview-side">{validation}{sourcesCard}</div>
        </div>
      </>}
  </div>;
}

function SearchView({ transport, overview, onSelect, colors, session, onSession, browse = false }) {
  const { query, modelId, reportId, objectType = "" } = session;
  const active = Boolean(browse || query.trim() || modelId || reportId || objectType);
  const inputId = browse ? "browse-object-query" : "brain-search-query";
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
  const loading = pending || Boolean(active && !result && !error);
  const change = (values) => onSession((current) => ({ ...current, ...values, selectedId: null, scrollY: 0 }));
  const runSearch = useCallback(async (offset = 0) => {
    if (!active || inFlight.current?.key === key) return;
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
  }, [key, modelId, query, reportId, objectType, transport, onSession, active]);
  useEffect(() => {
    setPending(false);
    if (!active || latest.current.result?.key === key) return undefined;
    const timer = setTimeout(() => runSearch(), 220);
    return () => { clearTimeout(timer); request.current += 1; inFlight.current = null; };
  }, [key, runSearch, active]);
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
    <PageHeading title={browse ? "Browse objects" : "Search"} description={browse ? "Choose an object to inspect its formula, dependencies, and report usage." : "Find objects by name, description, or part of a DAX formula."} />
    <Card className="panel search-panel" aria-busy={loading}>
      <div className="search-toolbar">
        <Label htmlFor={inputId} className="search-query-label">{browse ? "Filter by name or formula" : "Name or formula"}</Label>
        <div className="search-field"><NavIcon name="search" size={18} /><Input id={inputId} type="search" value={query} onChange={(event) => change({ query: event.target.value })} onKeyDown={(event) => { if (event.key === "Enter") runSearch(); }} placeholder={browse ? "Filter objects by name…" : "Measure, table, column, or visual…"} aria-label="Search the brain" />{loading && active ? <RefreshCw className="search-spinner spin" aria-hidden="true" /> : null}</div>
        <div className="search-filters">
          <Label className="select-field"><span>Model</span><NativeSelect aria-label="Model" value={modelId} onChange={(event) => change({ modelId: event.target.value, reportId: "" })}><option value="">All models</option>{models.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</NativeSelect></Label>
          <Label className="select-field"><span>Report</span><NativeSelect aria-label="Report" value={reportId} onChange={(event) => change({ reportId: event.target.value, modelId: "" })}><option value="">All reports</option>{reports.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</NativeSelect></Label>
          <Label className="select-field"><span>Type</span><NativeSelect aria-label="Search object type" value={objectType} onChange={(event) => change({ objectType: event.target.value })}><option value="">All types</option>{Object.keys(overview.object_counts || {}).sort().map((type) => <option key={type} value={type}>{typeLabel(type)}</option>)}</NativeSelect></Label>
          {modelId || reportId || objectType ? <Button variant="ghost" size="sm" className="clear-filters" onClick={() => change({ modelId: "", reportId: "", objectType: "" })}><X />Clear filters</Button> : null}
        </div>
      </div>
      <div className="search-status" role="status" aria-live="polite">{active ? loading ? "Searching…" : result ? `${result.items.length} of ${result.total} ${!query.trim() ? "objects" : "matches"}` : "" : "Search by name, paste part of a formula, or choose a filter."}</div>
      {error ? <div className="search-error" role="alert"><TriangleAlert aria-hidden="true" /><span>{readableText(error.message)}</span><Button variant="outline" size="sm" onClick={() => runSearch(error.offset)}>Retry search</Button></div> : null}
      {!active ? <EmptyState icon={<NavIcon name="search" size={20} />} title="What are you looking for?" detail="Find a measure to inspect its formula and dependencies." action={<p className="empty-hint"><kbd>Ctrl</kbd><kbd>K</kbd> jumps here from anywhere</p>} /> : null}
      {active && !loading && !result?.items?.length && !error ? <EmptyState icon={<NavIcon name="search" size={20} />} title="No matches" detail="Try a shorter name or clear the filters." /> : null}
      {active && result?.items?.length ? <div className="search-results">{result.items.map((item) => { const object = searchObject(item); const color = artifactColor(object, colors); const match = browse && !query.trim() ? "" : searchMatch(item); return <Button variant="ghost" key={object.id} data-result-id={object.id} className="search-result" style={{ "--artifact-color": color }} onClick={() => { onSession((current) => ({ ...current, selectedId: object.id, scrollY: window.scrollY })); onSelect(object.id, "inspector"); }}><span className="result-type"><span className="artifact-dot" />{typeLabel(object.type)}</span><span className="result-copy"><strong>{labelFor(object)}</strong><small>{scopeName(object) || readableText(object.description) || typeLabel(object.type)}</small></span>{match ? <span className="result-match">{match}</span> : null}<ChevronRight className="result-chevron" aria-hidden="true" /></Button>; })}</div> : null}
      {active && result?.has_more ? <div className="search-footer"><Button variant="outline" size="sm" disabled={loading} onClick={() => runSearch(Number(result.offset || 0) + Number(result.limit || 50))}>{pending ? "Loading…" : "More results"}</Button></div> : null}
    </Card>
  </div>;
}

function ConfigView({ transport, config, onSaved, onScan, scanning }) {
  const [draft, setDraft] = useState(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  useEffect(() => {
    const loaded = config || {};
    const defaults = { version: 1, name: "PBIBrain project", sources: [], database: "", identity_map: "" };
    const next = { ...defaults, ...loaded };
    setDraft({ ...next, sources: Array.isArray(loaded.sources) ? loaded.sources : [] });
  }, [config]);
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
        <div className="settings-section-copy"><h3>Power BI inputs</h3><p>Use full Windows paths for PBIP projects or model JSON files.</p></div>
        <div className="source-editor">
          {draft.sources.length ? <div className="source-list">{draft.sources.map((source, index) => <div className="source-row" key={index}><FileText className="source-icon" aria-hidden="true" /><Input value={source} onChange={(event) => updateSource(index, event.target.value)} placeholder="C:\\Reports\\Finance\\Finance.pbip" aria-label={`Source ${index + 1}`} /><Button variant="ghost" size="icon-sm" onClick={() => setDraft({ ...draft, sources: draft.sources.filter((_, sourceIndex) => sourceIndex !== index) })} aria-label={`Remove source ${index + 1}`}><X /></Button></div>)}</div> : <EmptyState icon={<FileText />} title="No sources" detail="Add a PBIP project or model JSON file." />}
          <Button variant="outline" size="sm" className="add-source" onClick={() => setDraft({ ...draft, sources: [...draft.sources, ""] })}><Plus />Add source</Button>
        </div>
      </div>
      <div className="config-actions"><Button onClick={save} disabled={saving || scanning || !dirty}>{saving ? "Saving…" : "Save configuration"}</Button><Button variant="outline" onClick={onScan} disabled={scanning || saving || dirty || !config?.sources?.length}><ScanLine />{scanning ? "Scanning…" : "Scan saved sources"}</Button>{dirty ? <span className="muted-copy compact">Save changes before scanning.</span> : null}{message ? <span role={message === "Saved" ? "status" : "alert"} className={message === "Saved" ? "success-text" : "error-copy"}>{message === "Saved" ? <Check aria-hidden="true" /> : null}{message}</span> : null}</div>
    </Card>
  </>;
}

function Inspector({ node, details, loading, error, snapshot, snapshotLoaded, snapshotError, overview, onSelect, onRetry, onEvidenceRetry, onReview, onGraph, colors, scanning, transport }) {
  if (error) return <Card className="panel inspector-state"><div className="empty-state tone-bad"><span className="empty-icon" aria-hidden="true"><TriangleAlert /></span><h2>Object unavailable</h2><p>{readableText(error)}</p><Button variant="outline" onClick={onRetry}><RefreshCw />Retry object</Button></div></Card>;
  if (loading) return <div className="inspector-loading"><div className="skeleton skeleton-title" /><div className="skeleton-grid"><div className="skeleton skeleton-block" /><div className="skeleton skeleton-block" /></div><p role="status" className="loading-label">Loading object details…</p></div>;
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
  const color = artifactColor(node, colors);
  const scopeTrail = [node.model_id, node.report_id, properties.table_id].filter((id) => id && id !== node.id).map(scopeName).filter(Boolean);
  return <>
    <PageHeading title={labelFor(node)} description={scopeTrail.join(" · ")} action={<Button variant="outline" onClick={onGraph}><Waypoints />Show in graph</Button>}>
      <div className="object-summary-state" style={{ "--artifact-color": color }}><span className="type-chip"><span className="artifact-dot" />{typeLabel(node.type)}</span><StatusBadge value={node.status} /></div>
    </PageHeading>
    <div className="object-workspace">
      <div className="object-main">
        <Card className="panel object-summary">
          <h3 className="panel-title">Definition</h3>
          {node.description ? <p className="description-copy">{formatValue(node.description)}</p> : null}
          {expression ? <ExpressionBlock expression={formatValue(expression)} /> : !node.description ? <p className="muted-copy">No description recorded.</p> : null}
          {fields.length ? <dl className="metadata-grid">{fields.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl> : null}
        </Card>
        {candidates.length || warnings.length ? <details className="object-metadata object-review panel" open><summary><span>Review &amp; evidence</span><span className="summary-count">{candidates.length} suggestions{warnings.length ? ` · ${warnings.length} warnings` : ""}</span></summary>{candidates.map((item) => <div className="object-review-item" key={item.id || item.target}><CandidateActions item={item} onReview={onReview} disabled={scanning} /><EvidenceCard item={item} /></div>)}{warnings.map((warning) => <div className="warning-card" key={warning.id || formatEvidence(warning.reason)}><strong><TriangleAlert aria-hidden="true" />Conflict</strong><p>{formatEvidence(warning.reason || warning.message || warning.description || "Conflicting evidence needs review.")}</p></div>)}</details> : null}
        {snapshotError ? <div className="inline-error" role="alert"><p>{snapshotLoaded ? "Review evidence could not be refreshed. Showing last loaded evidence." : "Review evidence unavailable."} {readableText(snapshotError)}</p><Button variant="outline" size="sm" onClick={onEvidenceRetry}>Retry evidence</Button></div> : !snapshotLoaded ? <p className="muted-copy object-review" role="status">Loading review evidence…</p> : null}
        {connected.some((edge) => !usageTypes.has(edge.type) && edge.type !== "OBSERVED_WITH") ? <details className="object-metadata object-other panel"><summary><span>Other relationships</span></summary><RelationshipGroup title="Connected objects" nodeId={node.id} edges={connected.filter((edge) => !usageTypes.has(edge.type) && edge.type !== "OBSERVED_WITH")} nodes={relatedNodes} onSelect={onSelect} empty="No other relationships." /></details> : null}
        {observations.length ? <details className="object-metadata object-observed panel"><summary><span>Observed report usage</span><span className="summary-count">{observations.length}</span></summary>{observations.map((edge) => <div className="usage-row" key={edge.id}><span>{scopeName(edge.from_id === node.id ? edge.to_id : edge.from_id)}</span><strong>{formatValue(edge.properties?.count || edge.count || "observed")}</strong></div>)}<p className="footnote">Co-occurrence does not establish compatibility.</p></details> : null}
      </div>
      <Card className="panel object-lineage">
        <h3 className="panel-title">Lineage</h3>
        <VisualBindings bindings={details?.visual_bindings} onSelect={(item) => onSelect(item.id, "inspector")} />
        <RelationshipGroup title="Used by" nodeId={node.id} edges={incoming.filter((edge) => usageTypes.has(edge.type))} nodes={relatedNodes} onSelect={onSelect} empty="No direct uses recorded." />
        <RelationshipGroup title="Dependencies" nodeId={node.id} edges={outgoing.filter((edge) => usageTypes.has(edge.type))} nodes={relatedNodes} onSelect={onSelect} empty="No direct dependencies recorded." />
        <p className="footnote">Direct links from the latest scan.</p>
        <ImpactExplorer node={node} nodes={relatedNodes} onSelect={onSelect} transport={transport} />
      </Card>
    </div>
  </>;
}

function ExpressionBlock({ expression }) {
  const [message, setMessage] = useState("");
  useEffect(() => {
    if (message !== "Copied") return undefined;
    const timer = setTimeout(() => setMessage(""), 1800);
    return () => clearTimeout(timer);
  }, [message]);
  const copy = async () => {
    try { await navigator.clipboard.writeText(expression); setMessage("Copied"); }
    catch { setMessage("Select the formula to copy it."); }
  };
  return <section className="object-expression" aria-label="DAX formula"><div className="code-head"><h3><span className="code-lang">DAX</span>formula</h3><Button variant="ghost" size="xs" onClick={copy} className={message === "Copied" ? "is-copied" : ""}>{message === "Copied" ? <Check /> : <Copy />}{message === "Copied" ? "Copied" : "Copy formula"}</Button></div><pre tabIndex={0}><code>{highlightDax(expression)}</code></pre>{message && message !== "Copied" ? <p role="status">{message}</p> : null}</section>;
}

function RelationshipGroup({ title, nodeId, edges, nodes, onSelect, empty }) {
  const [expanded, setExpanded] = useState(false);
  const unique = [...new Map(edges.map((edge) => [edge.from_id === nodeId ? edge.to_id : edge.from_id, edge])).values()];
  const shown = expanded ? unique : unique.slice(0, 10);
  return <section className="relationship-group" aria-label={title}><h3 className="relationship-title">{title}<span className="count-pill">{unique.length}</span></h3>{unique.length ? <div className="relationship-list">{shown.map((edge) => { const targetId = edge.from_id === nodeId ? edge.to_id : edge.from_id; const resolved = nodes.find((node) => node.id === targetId); return <Button variant="ghost" className="relationship-row" key={targetId} onClick={() => onSelect(targetId, "inspector")}><span className="edge-chip" style={{ background: EDGE_COLORS[edge.type] || "#738294" }} /><span className="relationship-copy"><strong>{resolved ? labelFor(resolved) : "Related object"}</strong><small>{typeLabel(resolved?.type || edge.type)}</small></span><ChevronRight className="row-chevron" aria-hidden="true" /></Button>; })}</div> : <p className="muted-copy compact">{empty}</p>}{unique.length > 10 ? <Button variant="link" size="sm" className="relationship-more" onClick={() => setExpanded((current) => !current)}>{expanded ? "Show fewer" : `Show all ${unique.length}`}</Button> : null}</section>;
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

function ReviewQueue({ session, onSession, snapshot, loaded, loading, error, onRetry, overview, onSelect, onReview, scanning }) {
  const { issue, objectType, modelId, reportId, sort } = session;
  const change = (values) => onSession((current) => ({ ...current, ...values }));
  const panel = useRef(null);
  useEffect(() => {
    const frame = requestAnimationFrame(() => {
      const selected = [...(panel.current?.querySelectorAll("[data-review-id]") || [])].find((element) => element.dataset.reviewId === session.selectedId);
      if (selected) { selected.focus({ preventScroll: true }); window.scrollTo(0, session.scrollY || 0); }
    });
    return () => cancelAnimationFrame(frame);
  }, []);
  const external = snapshot.review_items.map((item) => ({ ...item, issue: reviewIssue(item) }));
  const candidates = snapshot.semantic_candidates.map((item) => ({ ...item, issue: "candidate" }));
  const conflicts = snapshot.conflicts.map((item) => ({ ...item, issue: "conflict", status: item.status || "candidate", confidence: item.confidence ?? 0 }));
  const staleRecords = [...snapshot.stale_overrides, ...snapshot.overrides.filter((item) => item.status === "stale"), ...external.filter((item) => item.issue === "stale")];
  const stale = staleRecords.map((item) => ({ ...item, issue: "stale", status: item.status || "candidate", confidence: item.confidence ?? 0 }));
  const all = mergeReviewItems(external.length ? external : [...candidates, ...conflicts, ...stale]).filter((item) => !["rejected", "approved", "overridden"].includes(item.status));
  const types = [...new Set(all.map((item) => snapshot.nodes.find((node) => node.id === itemTarget(item))?.type).filter(Boolean))].sort();
  const models = [...new Set(all.map((item) => itemScopeValue(item, snapshot.nodes.find((node) => node.id === itemTarget(item)), "model_id")).filter(Boolean))].sort();
  const reports = [...new Set(all.map((item) => itemScopeValue(item, snapshot.nodes.find((node) => node.id === itemTarget(item)), "report_id")).filter(Boolean))].sort();
  const filtered = all.filter((item) => {
    const targetNode = snapshot.nodes.find((node) => node.id === itemTarget(item));
    return (issue === "ALL" || item.issue === issue)
      && (objectType === "ALL" || targetNode?.type === objectType)
      && (modelId === "ALL" || itemScopeValue(item, targetNode, "model_id") === modelId)
      && (reportId === "ALL" || itemScopeValue(item, targetNode, "report_id") === reportId);
  }).sort((a, b) => {
    if (sort === "confidence-low") return itemConfidence(a) - itemConfidence(b);
    if (sort === "impact-high") return itemImpact(b) - itemImpact(a);
    if (sort === "impact-low") return itemImpact(a) - itemImpact(b);
    return itemConfidence(b) - itemConfidence(a);
  });
  const scopes = [...scopeOptions(overview, "model"), ...scopeOptions(overview, "report"), ...snapshot.nodes];
  const scopeName = (id, kind, index) => scopes.find((node) => node.id === id)?.name || `${kind} ${index + 1}`;
  const hasFilters = issue !== "ALL" || objectType !== "ALL" || modelId !== "ALL" || reportId !== "ALL";
  return <div ref={panel}>
    <PageHeading title="Review queue" description="Confirm suggested meanings with the evidence behind each one." />
    {error && !loaded ? <Card className="panel" role="alert"><EmptyState icon={<TriangleAlert />} tone="bad" title="Review queue unavailable" detail={readableText(error)} action={<Button variant="outline" onClick={onRetry}><RefreshCw />Retry review queue</Button>} /></Card> : <>
    {error ? <Card className="panel" role="alert"><EmptyState icon={<TriangleAlert />} tone="bad" title="Review refresh failed" detail={`Showing last loaded reviews. ${readableText(error)}`} action={<Button variant="outline" onClick={onRetry}><RefreshCw />Retry review queue</Button>} /></Card> : null}
    <div className="review-purpose"><span className="icon-tile" aria-hidden="true"><ShieldCheck /></span><p>Confirm the meanings PBIBrain inferred. Approval saves a trusted label for search and context; rejection excludes it. Your Power BI files stay unchanged.</p><span className="queue-count"><strong>{loading ? "…" : filtered.length}</strong>{loading ? "Loading…" : " to review"}</span></div>
    <div className="queue-toolbar">
      <Label className="select-field"><span>Issue</span><NativeSelect aria-label="Issue" value={issue} onChange={(event) => change({ issue: event.target.value })}><option value="ALL">All issues</option><option value="candidate">Suggestions</option><option value="conflict">Conflicts</option><option value="stale">Outdated decisions</option></NativeSelect></Label>
      <Label className="select-field"><span>Object</span><NativeSelect aria-label="Object" value={objectType} onChange={(event) => change({ objectType: event.target.value })}><option value="ALL">All types</option>{types.map((type) => <option key={type} value={type}>{typeLabel(type)}</option>)}</NativeSelect></Label>
      {models.length > 1 ? <Label className="select-field"><span>Model</span><NativeSelect aria-label="Model" value={modelId} onChange={(event) => change({ modelId: event.target.value, reportId: "ALL" })}><option value="ALL">All models</option>{models.map((value, index) => <option key={value} value={value}>{scopeName(value, "Model", index)}</option>)}</NativeSelect></Label> : null}
      {reports.length > 1 ? <Label className="select-field"><span>Report</span><NativeSelect aria-label="Report" value={reportId} onChange={(event) => change({ reportId: event.target.value, modelId: "ALL" })}><option value="ALL">All reports</option>{reports.map((value, index) => <option key={value} value={value}>{scopeName(value, "Report", index)}</option>)}</NativeSelect></Label> : null}
      {hasFilters ? <Button variant="ghost" size="sm" onClick={() => change({ issue: "ALL", objectType: "ALL", modelId: "ALL", reportId: "ALL" })}><X />Clear filters</Button> : null}
      <Label className="select-field select-sort"><span>Sort</span><NativeSelect aria-label="Sort" value={sort} onChange={(event) => change({ sort: event.target.value })}><option value="confidence-high">Most certain first</option><option value="confidence-low">Least certain first</option><option value="impact-high">Highest impact first</option><option value="impact-low">Lowest impact first</option></NativeSelect></Label>
    </div>
    <Card className="panel queue-panel" aria-busy={loading}>
      {loading ? <div className="queue-loading">{[0, 1, 2].map((index) => <div className="skeleton skeleton-row-item" key={index} />)}<p className="sr-only" role="status">Loading suggestions…</p></div> : filtered.length ? <>
        <div className="review-columns" aria-hidden="true"><span>Object &amp; suggestion</span><span>Why review this?</span><span>Confidence</span><span>Decision</span></div>
        <div className="queue-list">{filtered.map((item) => <ReviewItem key={item.id || `${item.issue}-${itemTarget(item)}`} item={item} nodes={snapshot.nodes} disabled={scanning} onSelect={(id, nextView) => { change({ selectedId: item.id || itemTarget(item), scrollY: window.scrollY }); onSelect(id, nextView); }} onReview={onReview} />)}</div>
      </> : <EmptyState icon={hasFilters ? <ShieldCheck /> : <CircleCheck />} tone={hasFilters ? undefined : "ok"} title={hasFilters ? "No matching reviews" : "Queue is clear"} detail={hasFilters ? "Choose different filters to see the remaining reviews." : "All suggestions have been reviewed."} action={hasFilters ? <Button variant="outline" onClick={() => change({ issue: "ALL", objectType: "ALL", modelId: "ALL", reportId: "ALL" })}>Clear filters</Button> : null} />}
    </Card>
    </>}
  </div>;
}

function ReviewItem({ item, nodes, onSelect, onReview, disabled = false }) {
  const targetNode = nodes.find((node) => node.id === itemTarget(item));
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const decide = async (action) => { if (pending || disabled) return; setPending(true); setError(""); try { if (!await onReview(action, item)) setError("Decision could not be saved. Try again."); } finally { setPending(false); } };
  const evidence = readableText(item.evidence?.length ? item.evidence : item.item?.evidence, nodes);
  const reason = item.reason || (item.source === "object_name" ? "Only the object name supports this meaning; no description confirms it." : item.source === "description" ? "The source description suggests this meaning. Confirm that the label fits." : "An inference rule proposed this meaning. Confirm it using the recorded evidence.");
  const score = confidence(item.confidence ?? item.properties?.confidence);
  const level = score === null ? "none" : score >= 80 ? "high" : score >= 50 ? "mid" : "low";
  return <div className={`review-item issue-${item.issue}`} aria-busy={pending}>
    <Button variant="ghost" className="review-target" data-review-id={item.id || itemTarget(item)} disabled={!targetNode} onClick={() => onSelect(targetNode.id, "inspector")}><span className={`review-dot ${item.issue}`} /><span className="review-target-copy"><strong>{targetNode ? labelFor(targetNode) : "Source object unavailable"}</strong><small className="review-scope">{objectScope(targetNode, nodes)}</small><small className="review-suggestion">{item.issue === "conflict" ? "Conflicting suggestions" : item.issue === "stale" ? "Outdated saved decision" : suggestionLabel(item)}</small>{targetNode ? <small className="review-type">{typeLabel(targetNode.type)}</small> : null}</span></Button>
    <div className="review-evidence"><p>{readableText(reason, nodes)}</p>{evidence ? <small>{evidence}</small> : null}</div>
    <div className={`review-score level-${level}`}><strong>{score === null ? "—" : `${confidence(itemConfidence(item))}%`}</strong><span className="meter" aria-hidden="true"><i style={{ width: `${score ?? 0}%` }} /></span><small>{item.issue === "conflict" ? "Conflict" : item.issue === "stale" ? "Outdated" : "Suggested"}</small></div>
    <div className="review-actions">{item.issue === "stale" ? <Button variant="outline" size="sm" disabled={pending || disabled} onClick={() => decide("remove")}>Remove decision</Button> : <><Button variant="outline" size="sm" className="approve-button" disabled={pending || disabled} onClick={() => decide("approve")}><Check aria-hidden="true" />Approve</Button><Button variant="ghost" size="sm" className="reject-button" disabled={pending || disabled} onClick={() => decide("reject")}><X aria-hidden="true" />Reject</Button></>}</div>
    {error ? <p className="review-decision-error" role="alert">{error}</p> : null}
  </div>;
}


function CandidateActions({ item, onReview, disabled = false }) {
  const [editingAction, setEditingAction] = useState("");
  const [value, setValue] = useState(readableText(item.value || item.meaning));
  const [pending, setPending] = useState(false);
  const beginEdit = (action) => { setValue(readableText(item.value || item.meaning)); setEditingAction(action); };
  const decide = async (action, nextValue) => {
    if (pending || disabled) return;
    setPending(true);
    try { if (await onReview(action, item, nextValue)) setEditingAction(""); }
    finally { setPending(false); }
  };
  const score = confidence(item.confidence ?? item.properties?.confidence);
  return <fieldset className="candidate-actions" disabled={pending || disabled}>
    <div className="candidate-action-title"><span>{suggestionLabel(item)}</span><span className="count-pill">{score === null ? "" : `${score}%`}</span></div>
    {editingAction ? <div className="edit-row"><Input value={value} onChange={(event) => setValue(event.target.value)} aria-label={`${editingAction} semantic value`} /><Button variant="outline" size="sm" disabled={!value.trim()} onClick={() => decide(editingAction, value)}>Save meaning</Button><Button variant="link" size="sm" onClick={() => setEditingAction("")}>Cancel</Button></div> : <div className="action-buttons"><Button variant="outline" size="sm" onClick={() => decide("approve")}>Approve</Button><Button variant="ghost" size="sm" onClick={() => beginEdit("edit")}>Edit</Button><Button variant="ghost" size="sm" onClick={() => decide("reject")}>Reject</Button><Button variant="link" size="sm" onClick={() => beginEdit("override")}>Set meaning</Button></div>}
  </fieldset>;
}

function EvidenceCard({ item }) {
  return <div className="evidence-card"><p>{readableText(item.evidence?.length ? item.evidence : item.reason) || "No explanation recorded."}</p></div>;
}

function StatusBadge({ value, large = false }) { return <Badge variant="outline" className={`status-badge ${large ? "large" : ""} ${statusClass(value)}`}><i />{statusLabel(value)}</Badge>; }
function EmptyState({ title, detail, action, icon, tone }) { return <div className={`empty-state ${tone ? `tone-${tone}` : ""}`}>{icon ? <span className="empty-icon" aria-hidden="true">{icon}</span> : null}<h2>{title}</h2><p>{detail}</p>{action}</div>; }
function formatDate(value) { if (!value || value === "Not scanned") return value || "Not scanned"; const date = new Date(value); return Number.isNaN(date.valueOf()) ? String(value) : date.toLocaleString([], { dateStyle: "medium", timeStyle: "short" }); }
function formatValue(value) { return readableText(value) || "—"; }

export default App;
