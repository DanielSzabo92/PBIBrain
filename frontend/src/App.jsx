import VisualBindings from "./components/VisualBindings";
import ImpactExplorer from "./components/ImpactExplorer";
import CommonObjects from "./components/CommonObjects";
import PendingChanges from "./components/PendingChanges";
import { hasComparableSources } from "./commonality";
import React, { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, ArrowUpRight, Boxes, Check, ChartColumn, ChevronRight, CircleCheck, Cloud, Inbox, PanelLeft, ScanSearch, Copy, Database, FileText, FolderOpen, Moon, Plus, RefreshCw, ScanLine, ShieldAlert, ShieldCheck, Sun, TriangleAlert, Waypoints, X } from "lucide-react";
import { brainTransport, normalizeSnapshot } from "./transport";
import { desktopRequest, subscribeToDesktopBridge } from "./desktop";
import NavIcon from "./NavIcon";
import BrandMark from "./components/BrandMark";
import { TypeGlyph, TypeIcon } from "./components/TypeGlyph";
import { CloudSourcePicker } from "./components/CloudSourcePicker";
import { highlightDax } from "./dax";
import { objectName, objectScope, originNote, readableText, publicProperties, scopeChoices, statusLabel, suggestionLabel } from "./presentation";
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
const DocumentationExport = lazy(() => import("./components/DocumentationExport"));
const DevCenter = lazy(() => import("./devcenter/screens/DevCenter.jsx"));
import { Switch } from "./components/ui/switch";
import { setSlashSearchEnabled, slashGoesToSearch, slashSearchEnabled } from "./devcenter/preferences.js";
import { t as devCopy } from "./devcenter/copy.js";
import { artifactColor, artifactStyle, normalizeColors, typeLabel } from "./graphPresentation";
import { AppMenuBar, ShortcutsDialog, StatusBar } from "./components/AppShell";
import { commandFor, displayKeys, shortcutKeys } from "./shortcuts";

const VIEWS = [
  ["overview", "Overview"],
  ["search", "Search"],
  ["graph", "Graph"],
  ["inspector", "Inspector"],
  ["review", "Review queue"],
  ["devcenter", "Merge models"],
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

const SIDEBAR_KEY = "pbibrain-sidebar";

function useSidebar() {
  const [collapsed, setCollapsed] = useState(() => { try { return globalThis.localStorage?.getItem(SIDEBAR_KEY) === "collapsed"; } catch { return false; } });
  useEffect(() => { try { globalThis.localStorage?.setItem(SIDEBAR_KEY, collapsed ? "collapsed" : "expanded"); } catch { /* Storage can be unavailable. */ } }, [collapsed]);
  return [collapsed, () => setCollapsed((current) => !current)];
}

// Only the content pane scrolls (desktop shell); views save and restore its position, not the window's.
function contentScroller() {
  return document.getElementById("main-content") || document.scrollingElement || document.documentElement;
}

function focusSearchField() {
  requestAnimationFrame(() => document.querySelector(".search-field input")?.focus());
}

// True below the compact breakpoint (app.css, max-width 760px), where the navigation shows icons only.
function useCompactNav() {
  const query = "(max-width: 760px)";
  const [compact, setCompact] = useState(() => Boolean(globalThis.matchMedia?.(query).matches));
  useEffect(() => {
    const list = globalThis.matchMedia?.(query);
    if (!list) return undefined;
    const update = () => setCompact(list.matches);
    list.addEventListener("change", update);
    return () => list.removeEventListener("change", update);
  }, []);
  return compact;
}

function App({ transport = brainTransport }) {
  const compactNav = useCompactNav();
  const desktopHost = Boolean(globalThis.__PBIBRAIN_DESKTOP__);
  const [theme, toggleTheme] = useTheme();
  const [sidebarCollapsed, toggleSidebar] = useSidebar();
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
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

  const goBack = useCallback(() => {
    if (currentView.current !== "inspector" || !selectedId) return;
    if (inspectorOrigin === "inspector") { setSelectedId(null); setInspectedObject(null); }
    else setView(inspectorOrigin);
  }, [inspectorOrigin, selectedId]);

  // Shell commands. Menus, toolbar buttons and keys all run through here (shortcuts.js holds the key map).
  const commands = useRef({});
  commands.current = {
    find: () => { setView("search"); focusSearchField(); },
    back: goBack,
    sidebar: toggleSidebar,
    theme: toggleTheme,
    shortcuts: () => setShortcutsOpen(true),
  };
  // "/" outside a text field also jumps to search; Settings can turn that key off (UI design 9.3, A24).
  // Keys are ignored while a dialog or menu owns focus, so Escape and arrows stay with it.
  useEffect(() => {
    const onKey = (event) => {
      if (event.defaultPrevented) return;
      if (slashGoesToSearch(event)) { event.preventDefault(); commands.current.find(); return; }
      const command = commandFor(event);
      if (!command) return;
      if (document.querySelector("[role=dialog], [role=alertdialog]") && command !== "shortcuts") return;
      const run = commands.current[command] || (command.startsWith("view:") ? () => commands.current.view(command.slice(5)) : null);
      if (!run) return;
      event.preventDefault();
      run();
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
  const hasSources = !config || !Array.isArray(config.sources) || config.sources.length > 0 || Boolean(activeProject?.source_count);
  const runScan = () => { if (!scanning && hasSources) applyScan(); };
  const openSettings = (tab = "project") => { setSettingsTab(tab); setView("config"); };
  commands.current.view = (key) => { navigate(key); if (key === "search") focusSearchField(); };
  commands.current.reload = () => { if (!loading && !scanning) reloadBrain(); };
  commands.current.scan = runScan;
  const lastScan = overview.last_scan ? `Scanned ${formatDate(overview.last_scan)}` : overview.scan_state === "not_scanned" ? "Not scanned" : "Last scan time unknown";
  const viewLabel = VIEWS.find(([key]) => key === view)?.[1];
  const menus = [
    { id: "file", label: "File", items: [
      activeProject ? { label: "Change project…", onSelect: closeDesktopProject, disabled: scanning } : null,
      { label: "Scan sources", keys: shortcutKeys("scan"), onSelect: runScan, disabled: scanning || !hasSources },
      { separator: true },
      { label: "Project sources…", onSelect: () => openSettings("project") },
      { label: "Export documentation…", onSelect: () => openSettings("documentation"), disabled: !counts.objects },
      { label: "Export agent context…", onSelect: () => openSettings("summary") },
      { label: "Settings", keys: shortcutKeys("view:config"), onSelect: () => openSettings(settingsTab) },
    ] },
    { id: "view", label: "View", items: [
      { label: "Reload data", keys: shortcutKeys("reload"), onSelect: commands.current.reload, disabled: loading || scanning },
      { separator: true },
      { label: "Side bar", keys: shortcutKeys("sidebar"), checked: !sidebarCollapsed, onSelect: toggleSidebar },
      { label: "Dark theme", keys: shortcutKeys("theme"), checked: theme === "dark", onSelect: toggleTheme },
      { label: "Graph colors…", onSelect: () => openSettings("colors") },
    ] },
    { id: "go", label: "Go", items: [
      ...VIEWS.filter(([key]) => key !== "config").map(([key, label]) => ({ label, keys: shortcutKeys(`view:${key}`), onSelect: () => commands.current.view(key) })),
      { separator: true },
      { label: "Find object…", keys: shortcutKeys("find"), onSelect: commands.current.find },
      { label: "Back", keys: shortcutKeys("back"), onSelect: goBack, disabled: !(view === "inspector" && selectedId) },
    ] },
    { id: "help", label: "Help", items: [
      { label: "Keyboard shortcuts", keys: shortcutKeys("shortcuts"), onSelect: () => setShortcutsOpen(true) },
    ] },
  ];
  return (
    <div className={`app-shell ${sidebarCollapsed ? "sidebar-collapsed" : ""}`}>
      <a className="skip-link" href="#main-content">Skip to content</a>
      <AppMenuBar menus={menus} projectName={projectName}>
        <button type="button" className="command-center" onClick={commands.current.find} title={`Find an object (${displayKeys("Ctrl+K")})`}>
          <ScanSearch aria-hidden="true" /><span>Find measure, table, column or visual</span><kbd aria-hidden="true">{displayKeys("Ctrl+K")}</kbd>
        </button>
      </AppMenuBar>
      <div className="workbench">
        <aside className="sidebar" aria-label="Views">
          <nav aria-label="Main navigation" className="sidebar-nav">
            {VIEWS.map(([key, label]) => {
              const keys = displayKeys(shortcutKeys(`view:${key}`));
              return (
                <Button variant="ghost" key={key} aria-current={view === key ? "page" : undefined} className={`nav-button ${view === key ? "active" : ""} ${key === "config" ? "nav-settings" : ""}`} tooltip={compactNav || sidebarCollapsed ? `${label} (${keys})` : undefined} onClick={() => navigate(key)} title={compactNav || sidebarCollapsed ? undefined : `${label} (${keys})`}>
                  <NavIcon name={key} />
                  <span className="nav-label">{label}</span>
                  {key === "review" && pending > 0 ? <span className="nav-count" data-ui-number="">{pending > 99 ? "99+" : pending}</span> : null}
                </Button>
              );
            })}
          </nav>
          <Button variant="ghost" size="icon-sm" className="sidebar-collapse" onClick={toggleSidebar} aria-label={sidebarCollapsed ? "Expand side bar" : "Collapse side bar"} aria-expanded={!sidebarCollapsed} title={`${sidebarCollapsed ? "Expand" : "Collapse"} side bar (${displayKeys("Ctrl+B")})`}><PanelLeft aria-hidden="true" /></Button>
        </aside>

      <div className="main-column">
        <header className="topbar view-toolbar">
          <div className="breadcrumb">
            <NavIcon name={view} />
            <span className="breadcrumb-view">{viewLabel}</span>
          </div>
          <div className="topbar-actions" role="toolbar" aria-label={`${viewLabel} toolbar`} data-ui-actions="">
            {activeProject ? <Button variant="ghost" size="sm" className="project-switch" onClick={closeDesktopProject} disabled={scanning}><FolderOpen />Change project</Button> : null}
            {counts.objects > 0 ? <Button variant="ghost" size="sm" onClick={runScan} disabled={scanning || !hasSources} title={hasSources ? `Re-read every source and rebuild the brain (${displayKeys("Ctrl+F5")})` : "Add sources in Settings first"}><ScanLine aria-hidden="true" />{scanning ? "Scanning…" : "Scan sources"}</Button> : null}
          </div>
        </header>

        <main id="main-content" tabIndex={-1} className={`content content-${view}`}>
          {(view !== "devcenter" && (error || configError || operationError)) || desktopError ? (
            <div className="error-banner" role="alert">
              <TriangleAlert aria-hidden="true" />
              <span>{readableText(error || configError || operationError || desktopError)}</span>
              {error || configError ? <Button variant="outline" size="sm" onClick={load}>Retry</Button> : null}
            </div>
          ) : null}
          {counts.objects > 0 && view !== "devcenter" ? <PendingChanges transport={transport} scanning={scanning} onScan={applyScan} /> : null}
          <div className="view-frame" key={view}>
            <Suspense fallback={<div className="view-loading" role="status"><RefreshCw className="spin" aria-hidden="true" />Loading view…</div>}>
            {view === "overview" ? <Overview onSelect={selectNode} overview={overview} config={config} counts={counts} colors={graphColors} loading={loading} projectName={projectName} onView={navigate} onBrowseType={(objectType) => { setSearchSession({ query: "", modelId: "", reportId: "", objectType, result: null }); setView("search"); }} onSources={() => { setSettingsTab("project"); setView("config"); }} onSummary={() => { setSettingsTab("summary"); setView("config"); }} onScan={applyScan} scanning={scanning} scanLabel={activeProject ? "Scan project" : "Scan sources"} onReview={() => navigate("review")} transport={transport} onMerge={(modelIds) => { const names = modelIds.map((id) => (overview.model_objects || []).find((item) => item.id === id)?.name || id); setNotice(`Start a merge session with ${names.join(", ")}`); navigate("devcenter"); }} /> : null}
            {view === "search" ? <div className="page page-narrow" data-ui-stack=""><SearchView session={searchSession} onSession={setSearchSession} colors={graphColors} transport={transport} overview={overview} onSelect={selectNode} /></div> : null}
            {view === "graph" ? <GraphView session={graphSession} onSession={setGraphSession} colors={graphColors} transport={transport} overview={overview} snapshot={snapshot} selectedId={selectedId} onSelect={selectNode} /> : null}
            {view === "inspector" ? <div className="page page-wide" data-ui-stack="">{selectedId ? <><Button variant="ghost" size="sm" className="inspector-back" onClick={() => { if (inspectorOrigin === "inspector") { setSelectedId(null); setInspectedObject(null); } else setView(inspectorOrigin); }}><ArrowLeft aria-hidden="true" />{inspectorOrigin === "search" ? "Back to results" : inspectorOrigin === "inspector" ? "Browse objects" : `Back to ${VIEWS.find(([key]) => key === inspectorOrigin)?.[1]?.toLowerCase() || "overview"}`}</Button><Inspector key={selectedId} transport={transport} scanning={scanning} colors={graphColors} node={selected} details={inspectedDetails} loading={Boolean(selectedId && !inspectedDetails && !inspectorError)} error={inspectorError} snapshot={snapshot} snapshotLoaded={snapshotLoaded} snapshotError={snapshotError} onEvidenceRetry={() => loadSnapshot().catch(() => {})} overview={overview} onSelect={selectNode} onRetry={() => selectNode(selectedId)} onReview={review} onGraph={() => setView("graph")} /></> : <SearchView browse session={inspectorSession} onSession={setInspectorSession} colors={graphColors} transport={transport} overview={overview} onSelect={(id) => { setInspectorOrigin("inspector"); selectNode(id); }} />}</div> : null}
            {view === "review" ? <div className="page page-wide" data-ui-stack=""><ReviewQueue colors={graphColors} scanning={scanning} session={reviewSession} onSession={setReviewSession} snapshot={snapshot} loaded={snapshotLoaded} loading={!snapshotLoaded && (snapshotLoading || !snapshotError)} error={snapshotError} onRetry={() => loadSnapshot().catch(() => {})} overview={overview} onSelect={selectNode} onReview={review} /></div> : null}
            {view === "devcenter" ? <DevCenter onOpenProject={closeDesktopProject} /> : null}
            {view === "config" ? <div className="page page-narrow" data-ui-stack=""><PageHeading title="Settings" description="Manage project sources, graph appearance, model context, and documentation." /><KeyboardSettings />{configError && !config ? <Card className="panel"><EmptyState icon={<TriangleAlert />} tone="bad" title="Project settings unavailable" detail="Retry to load your saved sources and appearance." action={<Button variant="outline" onClick={load}>Retry settings</Button>} /></Card> : <Tabs value={settingsTab} onValueChange={setSettingsTab} className="settings-tabs">
              <TabsList aria-label="Settings sections"><TabsTrigger value="project">Project</TabsTrigger><TabsTrigger value="colors">Graph colors</TabsTrigger><TabsTrigger value="summary">Model summary</TabsTrigger><TabsTrigger value="documentation">Documentation</TabsTrigger></TabsList>
              <TabsContent value="colors"><Suspense fallback={<ViewLoading />}><GraphColors config={config} transport={transport} overview={overview} onSaved={setConfig} /></Suspense></TabsContent>
              <TabsContent value="documentation"><Suspense fallback={<ViewLoading />}><DocumentationExport overview={overview} transport={transport} scanning={scanning} /></Suspense></TabsContent>
              <TabsContent value="summary"><Suspense fallback={<ViewLoading />}><ModelSummary overview={overview} transport={transport} scanning={scanning} /></Suspense></TabsContent>
              <TabsContent value="project">{activeProject ? <DesktopProjectView api={desktopApi} project={activeProject} overview={overview} config={config} transport={transport} scanning={scanning} onScan={applyScan} onChange={closeDesktopProject} onRefresh={load} onSaved={setConfig} /> : <ConfigView transport={transport} config={config} onSaved={setConfig} onScan={applyScan} scanning={scanning} />}</TabsContent></Tabs>}</div> : null}
            </Suspense>
          </div>
        </main>
      </div>
      </div>
      <StatusBar connection={connection} projectName={projectName} counts={counts} pending={pending} onReview={() => navigate("review")} scanning={scanning} lastScan={lastScan} notice={notice} noticeFailed={failedNotice} theme={theme} onTheme={toggleTheme} onShortcuts={() => setShortcutsOpen(true)} />
      <ShortcutsDialog open={shortcutsOpen} onOpenChange={setShortcutsOpen} />
    </div>
  );
}

// App setting of the "/" key (UI design 9.3, A24). It is stored in localStorage, as the theme is.
function KeyboardSettings() {
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

function ViewLoading() {
  return <div className="view-loading" role="status"><RefreshCw className="spin" aria-hidden="true" />Loading view…</div>;
}

function DesktopConnecting({ error, onRetry }) {
  return <main className="onboarding-shell"><Card className="onboarding-card connecting-card" aria-live="polite"><BrandMark size={44} className="onboarding-mark" /><h1>{error ? "Desktop connection needed" : "Opening PBIBrain"}</h1><p className="onboarding-copy">{error || "Preparing your private project workspace."}</p>{error ? <Button onClick={onRetry}><RefreshCw />Retry connection</Button> : <span className="connecting-indicator"><i /><i /><i /><span>Connecting</span></span>}</Card></main>;
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
      <div className="desktop-sources"><div className="panel-heading"><div><h2>Power BI source files</h2></div><Button variant="outline" onClick={addSources} disabled={sourceWorking || scanning}><Plus />{sourceWorking ? "Adding…" : "Add source files"}</Button></div>{sources.length ? <div className="source-list">{sources.map((source) => <div className="desktop-source-row" key={source}><FileText className="source-icon" aria-hidden="true" /><span title={source}>{source}</span><Button variant="ghost" size="icon-sm" onClick={() => removeSource(source)} disabled={sourceWorking || scanning} aria-label={`Remove ${source}`}><X /></Button></div>)}</div> : <EmptyState icon={<FileText />} title="No source files yet" detail="Add PBIP projects or model JSON files to scan them with this project." />}{sourceError ? <p className="onboarding-error" role="alert">{sourceError}</p> : null}</div>
      {typeof api?.add_cloud_source === "function" || cloudSources.length ? <div className="desktop-sources cloud-sources"><div className="panel-heading"><div><h2>Power BI service items</h2><p className="muted">Cloud semantic models and reports, read with your Microsoft sign-in.</p></div>{typeof api?.add_cloud_source === "function" ? <Button variant="outline" onClick={() => setCloudOpen(true)} disabled={sourceWorking || scanning || cloudOpen}><Cloud />Add cloud item</Button> : null}</div>
        {cloudOpen ? <CloudSourcePicker api={api} onClose={() => setCloudOpen(false)} onAdded={async () => { setCloudOpen(false); await onRefresh(); }} /> : null}
        {cloudSources.length ? <div className="source-list">{cloudSources.map((item) => <div className="desktop-source-row" key={item.item_id}><Cloud className="source-icon" aria-hidden="true" /><span title={`${item.workspace_name} · ${item.name}`}>{item.workspace_name} · {item.name} <span className="muted">({item.kind === "cloud_model" ? "semantic model" : "report"}, {item.access_type})</span></span><Button variant="ghost" size="icon-sm" onClick={() => removeCloudSource(item)} disabled={sourceWorking || scanning} aria-label={`Remove ${item.name}`}><X /></Button></div>)}</div> : null}
      </div> : null}
      <div className="config-actions" data-ui-actions=""><Button onClick={onScan} disabled={scanning}><ScanLine />{scanning ? "Scanning…" : "Scan project"}</Button></div>
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

function Overview({ overview, config, counts, colors, loading, projectName, onView, onBrowseType, onSources, onSummary, onScan, onReview, onSelect, onMerge, transport, scanning, scanLabel }) {
  const hasObjects = counts.objects > 0;
  const hasSources = Boolean(config?.sources?.length || config?.cloud_sources?.length);
  const sourceCount = config?.sources ? config.sources.length + (config.cloud_sources?.length || 0) : undefined;
  const notChecked = Array.isArray(overview.not_checked) ? overview.not_checked : [];
  const lastScan = overview.last_scan;
  const validationState = overview.validation_state || "not_run";
  const validationLabel = { valid: "Graph validation passed", invalid: "Graph validation failed", warning: "Graph validation warnings", not_run: "Graph validation not run" }[validationState] || "Graph validation unavailable";
  const issues = overview.validation_issues || [];
  const pending = counts.review;
  const ValidationIcon = validationState === "valid" ? ShieldCheck : ShieldAlert;
  const validationTone = { valid: "ok", invalid: "bad", warning: "warn" }[validationState] || "idle";
  const validation = <div className={`status-row tone-${validationTone}`} role={validationState === "invalid" ? "alert" : "status"}>
    <ValidationIcon className="status-icon" aria-hidden="true" />
    <div className="status-copy">
      <h2>{validationLabel}</h2>
      <p>{validationState === "not_run" ? "Scan sources to check graph validity." : validationState === "invalid" ? "Sources were extracted, but graph issues need attention." : "Graph validity is checked separately from source extraction and review decisions."}</p>
      {issues.length ? <details className="validation-issues"><summary>View validation issues ({issues.length})</summary><ul>{issues.map((item, index) => <li key={`${item.code}-${index}`}><span className={`severity severity-${String(item.severity).toLowerCase()}`}>{item.severity}</span><span className="issue-message">{item.message}</span>{item.object_id || item.from_id || item.to_id ? <Button variant="link" size="sm" onClick={() => onSelect(item.object_id || item.from_id || item.to_id, "inspector")}>Inspect affected object</Button> : null}</li>)}</ul></details> : null}
    </div>
  </div>;
  const sourcesRow = <div className="status-row tone-idle">
    <Database className="status-icon" aria-hidden="true" />
    <div className="status-copy">
      <h2>{scanning ? "Scanning sources…" : hasObjects ? "Sources indexed" : "Sources"}</h2>
      <p className="scan-meta">{sourceCount === undefined ? "Source settings unavailable" : `${sourceCount} ${sourceCount === 1 ? "source" : "sources"}`}{hasObjects ? ` · ${lastScan ? `Last scan ${formatDate(lastScan)}` : "Last scan time unavailable"}` : ""}</p>
    </div>
    <div className="status-actions" data-ui-actions=""><Button variant="ghost" size="sm" onClick={onSources}>Manage sources</Button></div>
  </div>;
  // Models and reports the scan could not read (issue #9): they stay in the graph, marked "Not checked".
  const notCheckedRow = notChecked.length ? <div className="status-row tone-warn" role="status">
    <TriangleAlert className="status-icon" aria-hidden="true" />
    <div className="status-copy">
      <h2>{notChecked.length} {notChecked.length === 1 ? "item" : "items"} not checked</h2>
      <ul className="not-checked-list">{notChecked.map((item) => { const note = originNote(item); return <li key={item.id}><Button variant="link" size="sm" onClick={() => onSelect(item.id, "inspector")}>{item.name}</Button> <span className="muted">{note?.title || "Not checked"}</span></li>; })}</ul>
    </div>
  </div> : null;
  const PRIMARY = ["MODEL", "TABLE", "COLUMN", "MEASURE", "REPORT", "PAGE", "VISUAL"];
  const typeCounts = Object.entries(overview.object_counts || {}).filter(([, count]) => count > 0).sort(([a], [b]) => { const ia = PRIMARY.indexOf(a), ib = PRIMARY.indexOf(b); return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib) || a.localeCompare(b); });
  const facts = [["object", "objects", counts.objects], ["relationship", "relationships", counts.edges]];
  return <div className="page page-overview" data-ui-stack="">
    <header className="overview-hero">
      <h1>{projectName}</h1>
      {hasObjects ? <dl className="project-counts" aria-label="Project counts">{facts.map(([one, many, count]) => <div key={many}><dd>{count.toLocaleString()}</dd><dt>{count === 1 ? one : many}</dt></div>)}{lastScan ? <div><dt>last scan</dt><dd className="fact-date">{formatDate(lastScan)}</dd></div> : null}</dl> : <p className="hero-meta">Connect your Power BI sources to build the project brain.</p>}
    </header>
    {hasObjects && typeCounts.length ? <nav className="type-strip" aria-label="Objects by type">{typeCounts.map(([type, count]) => <button type="button" key={type} className="type-strip-item" onClick={() => onBrowseType(type)} title={`Browse ${count.toLocaleString()} ${typeLabel(type).toLowerCase()} objects`}><TypeGlyph type={type} colors={colors} size="sm" /><span className="type-strip-count" data-ui-number="">{count.toLocaleString()}</span><span className="type-strip-label">{typeLabel(type)}</span></button>)}</nav> : null}
    {loading && !hasObjects ? <div className="overview-loading"><div className="skeleton skeleton-search" /><div className="skeleton skeleton-panel" /><p role="status" className="sr-only">{scanning ? "Scanning sources…" : "Loading project…"}</p></div> : !hasObjects ?
      <div className="overview-grid">
        <Card className="project-start" role="region" aria-labelledby="project-start-title">
          <h2 id="project-start-title">{hasSources ? "Ready for the first scan" : "Add your project sources"}</h2>
          <p>{hasSources ? "Scan your files to find models, reports, and their dependencies." : "Choose your PBIP project or exported model and report files."}</p>
          <Button size="lg" onClick={hasSources ? onScan : onSources} disabled={!config || scanning}>{hasSources ? <ScanLine /> : <Plus />}{hasSources ? scanLabel : "Add sources"}</Button>
        </Card>
        <Card className="status-panel" role="region" aria-label="Project status">{validation}{sourcesRow}{notCheckedRow}</Card>
      </div> : <>
        <Card className="status-panel" role="region" aria-label="Project status">
          <div className={`status-row ${pending ? "tone-brand" : "tone-ok"}`}>
            {pending ? <span className="status-icon status-icon-count" aria-hidden="true"><Inbox /><b data-ui-number="">{pending > 99 ? "99+" : pending}</b></span> : <CircleCheck className="status-icon" aria-hidden="true" />}
            <div className="status-copy">
              <h2>{validationState === "invalid" ? "Resolve graph issues before review" : pending ? "Ready for review" : "No pending reviews"}</h2>
              <p>{pending ? <><span className="sr-only">{pending} {pending === 1 ? "open item" : "open items"}. </span>Check suggested meanings and resolve uncertain matches.</> : "All suggestions have been reviewed."}{counts.warnings || counts.stale ? <span className="review-card-split"><span>{counts.candidates} suggestions</span>{counts.warnings ? <span>{counts.warnings} conflicts</span> : null}{counts.stale ? <span>{counts.stale} outdated decisions</span> : null}</span> : null}</p>
            </div>
            <div className="status-actions"><Button variant={pending ? "default" : "outline"} size="sm" onClick={onReview}>Open review queue <ArrowRight aria-hidden="true" /></Button></div>
          </div>
          {validation}
          {sourcesRow}
          {notCheckedRow}
        </Card>
        {transport && hasComparableSources(overview) && !scanning ? <CommonObjects transport={transport} colors={colors} onSelect={onSelect} onMerge={onMerge} refreshKey={overview.last_scan} /> : null}
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
      if (selected) { selected.focus({ preventScroll: true }); contentScroller().scrollTop = current.scrollY || 0; }
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
      <div className="search-toolbar" data-ui-actions="">
        <Label htmlFor={inputId} className="search-query-label">{browse ? "Filter by name or formula" : "Name or formula"}</Label>
        <div className="search-field"><NavIcon name="search" size={18} /><Input id={inputId} type="search" value={query} onChange={(event) => change({ query: event.target.value })} onKeyDown={(event) => { if (event.key === "Enter") runSearch(); else if (event.key === "ArrowDown" && moveInList(panel.current?.querySelector(".search-results"), "first")) event.preventDefault(); }} placeholder={browse ? "Filter objects by name…" : "Measure, table, column, or visual…"} aria-label="Search the brain" />{loading && active ? <RefreshCw className="search-spinner spin" aria-hidden="true" /> : null}</div>
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
      {active && result?.items?.length ? <div className="search-results" onKeyDown={(event) => listKeys(event, () => panel.current?.querySelector(".search-field input")?.focus())}>{result.items.map((item) => { const object = searchObject(item); const color = artifactColor(object, colors); const match = browse && !query.trim() ? "" : searchMatch(item); return <Button variant="ghost" key={object.id} data-result-id={object.id} className="search-result" style={{ "--artifact-color": color }} onClick={() => { onSession((current) => ({ ...current, selectedId: object.id, scrollY: contentScroller().scrollTop })); onSelect(object.id, "inspector"); }}><TypeGlyph node={object} colors={colors} size="sm" /><span className="result-type">{typeLabel(object.type)}</span><span className="result-copy"><strong>{labelFor(object)}</strong><small>{scopeName(object) || readableText(object.description) || typeLabel(object.type)}</small></span>{match ? <span className="result-match">{match}</span> : null}<ChevronRight className="result-chevron" aria-hidden="true" /></Button>; })}</div> : null}
      {active && result?.has_more ? <div className="search-footer"><Button variant="outline" size="sm" disabled={loading} onClick={() => runSearch(Number(result.offset || 0) + Number(result.limit || 50))}>{pending ? "Loading…" : "More results"}</Button></div> : null}
    </Card>
  </div>;
}

// Arrow-key movement through a list of buttons, as in a desktop list box. Up from the first row
// returns to the field above (onTop), so search -> results -> search works without the mouse.
function moveInList(container, where, from) {
  const rows = [...(container?.querySelectorAll(":scope > button:not(:disabled)") || [])];
  if (!rows.length) return false;
  const index = rows.indexOf(from);
  const next = where === "first" ? 0 : where === "last" ? rows.length - 1 : index + (where === "next" ? 1 : -1);
  if (next < 0 || next >= rows.length) return false;
  rows[next].focus();
  rows[next].scrollIntoView({ block: "nearest" });
  return true;
}

function listKeys(event, onTop) {
  const where = { ArrowDown: "next", ArrowUp: "previous", Home: "first", End: "last" }[event.key];
  if (!where || event.altKey || event.ctrlKey || event.metaKey) return;
  const from = event.target.closest?.("button");
  if (!from || from.parentElement !== event.currentTarget) return;
  event.preventDefault();
  if (!moveInList(event.currentTarget, where, from) && where === "previous") onTop?.();
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
      <div className="config-actions" data-ui-actions=""><Button onClick={save} disabled={saving || scanning || !dirty}>{saving ? "Saving…" : "Save configuration"}</Button><Button variant="outline" onClick={onScan} disabled={scanning || saving || dirty || !config?.sources?.length}><ScanLine />{scanning ? "Scanning…" : "Scan saved sources"}</Button>{dirty ? <span className="muted-copy compact">Save changes before scanning.</span> : null}{message ? <span role={message === "Saved" ? "status" : "alert"} className={message === "Saved" ? "success-text" : "error-copy"}>{message === "Saved" ? <Check aria-hidden="true" /> : null}{message}</span> : null}</div>
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
      <div className="object-summary-state" style={{ "--artifact-color": color }}><span className="type-chip" style={artifactStyle(node, colors)}><TypeIcon type={node.type} />{typeLabel(node.type)}</span><StatusBadge value={node.status} /></div>
    </PageHeading>
    <div className="object-workspace">
      <div className="object-main">
        <Card className="panel object-summary">
          <h2 className="panel-title">Definition</h2>
          {node.description ? <p className="description-copy">{formatValue(node.description)}</p> : null}
          {expression ? <ExpressionBlock expression={formatValue(expression)} /> : !node.description ? <p className="muted-copy">No description recorded.</p> : null}
          {fields.length ? <dl className="metadata-grid">{fields.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl> : null}
        </Card>
        <UsageRoles profile={details?.usage_roles} />
        {candidates.length || warnings.length ? <details className="object-metadata object-review panel" open><summary><span>Review &amp; evidence</span><span className="summary-count">{candidates.length} suggestions{warnings.length ? ` · ${warnings.length} warnings` : ""}</span></summary>{candidates.map((item) => <div className="object-review-item" key={item.id || item.target}><CandidateActions item={item} onReview={onReview} disabled={scanning} /><EvidenceCard item={item} /></div>)}{warnings.map((warning) => <div className="warning-card" key={warning.id || formatEvidence(warning.reason)}><strong><TriangleAlert aria-hidden="true" />Conflict</strong><p>{formatEvidence(warning.reason || warning.message || warning.description || "Conflicting evidence needs review.")}</p></div>)}</details> : null}
        {snapshotError ? <div className="inline-error" role="alert"><p>{snapshotLoaded ? "Review evidence could not be refreshed. Showing last loaded evidence." : "Review evidence unavailable."} {readableText(snapshotError)}</p><Button variant="outline" size="sm" onClick={onEvidenceRetry}>Retry evidence</Button></div> : !snapshotLoaded ? <p className="muted-copy object-review" role="status">Loading review evidence…</p> : null}
        {connected.some((edge) => !usageTypes.has(edge.type) && edge.type !== "OBSERVED_WITH") ? <details className="object-metadata object-other panel"><summary><span>Other relationships</span></summary><RelationshipGroup title="Connected objects" nodeId={node.id} edges={connected.filter((edge) => !usageTypes.has(edge.type) && edge.type !== "OBSERVED_WITH")} nodes={relatedNodes} onSelect={onSelect} empty="No other relationships." /></details> : null}
        {observations.length ? <details className="object-metadata object-observed panel"><summary><span>Observed report usage</span><span className="summary-count">{observations.length}</span></summary>{observations.map((edge) => <div className="usage-row" key={edge.id}><span>{scopeName(edge.from_id === node.id ? edge.to_id : edge.from_id)}</span><strong>{formatValue(edge.properties?.count || edge.count || "observed")}</strong></div>)}<p className="footnote">Co-occurrence does not establish compatibility.</p></details> : null}
      </div>
      <Card className="panel object-lineage">
        <h2 className="panel-title">Lineage</h2>
        <VisualBindings bindings={details?.visual_bindings} onSelect={(item) => onSelect(item.id, "inspector")} />
        <RelationshipGroup title="Used by" nodeId={node.id} edges={incoming.filter((edge) => usageTypes.has(edge.type))} nodes={relatedNodes} onSelect={onSelect} empty="No direct uses recorded." />
        <RelationshipGroup title="Dependencies" nodeId={node.id} edges={outgoing.filter((edge) => usageTypes.has(edge.type))} nodes={relatedNodes} onSelect={onSelect} empty="No direct dependencies recorded." />
        <p className="footnote">Direct links from the latest scan.</p>
        <ImpactExplorer node={node} nodes={relatedNodes} onSelect={onSelect} transport={transport} />
      </Card>
    </div>
  </>;
}

/** How the object is used in reports: INFERRED summary of the USES roles (issue #11). */
function UsageRoles({ profile }) {
  const facts = profile?.facts || [];
  if (!facts.length) return null;
  return <details className="object-metadata object-usage-roles panel" open><summary><span>How it is used</span><span className="summary-count">Inferred</span></summary>
    {facts.map((fact) => <div className="usage-row" key={`${fact.code}-${fact.text}`}><span>{fact.text}</span></div>)}
    <p className="footnote">{profile.basis}</p>
  </details>;
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
  return <section className="relationship-group" aria-label={title}><h3 className="relationship-title">{title}<span className="count-pill">{unique.length}</span></h3>{unique.length ? <div className="relationship-list" onKeyDown={(event) => listKeys(event)}>{shown.map((edge) => { const targetId = edge.from_id === nodeId ? edge.to_id : edge.from_id; const resolved = nodes.find((node) => node.id === targetId); return <Button variant="ghost" className="relationship-row" key={targetId} onClick={() => onSelect(targetId, "inspector")}><span className="edge-chip" style={{ background: EDGE_COLORS[edge.type] || "#738294" }} /><span className="relationship-copy"><strong>{resolved ? labelFor(resolved) : "Related object"}</strong><small>{typeLabel(resolved?.type || edge.type)}</small></span><ChevronRight className="row-chevron" aria-hidden="true" /></Button>; })}</div> : <p className="muted-copy compact">{empty}</p>}{unique.length > 10 ? <Button variant="link" size="sm" className="relationship-more" onClick={() => setExpanded((current) => !current)}>{expanded ? "Show fewer" : `Show all ${unique.length}`}</Button> : null}</section>;
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

// Keyboard triage (visual contract §9): J/K or ↓/↑ move between items, A approves, R rejects the focused item.
function reviewKeys(event) {
  if (event.altKey || event.ctrlKey || event.metaKey || event.target.closest("input, select, textarea")) return;
  const key = event.key.toLowerCase();
  const item = event.target.closest(".review-item");
  if (!item) return;
  if (key === "j" || key === "k" || event.key === "ArrowDown" || event.key === "ArrowUp") {
    const targets = [...event.currentTarget.querySelectorAll(".review-target:not(:disabled)")];
    const index = targets.indexOf(item.querySelector(".review-target"));
    const next = targets[index + (key === "j" || event.key === "ArrowDown" ? 1 : -1)];
    if (next) { next.focus(); next.scrollIntoView({ block: "nearest" }); event.preventDefault(); }
  } else if (key === "a" || key === "r") {
    const button = item.querySelector(key === "a" ? ".approve-button" : ".reject-button");
    if (button && !button.disabled) { button.click(); event.preventDefault(); }
  }
}

function ReviewQueue({ session, onSession, snapshot, loaded, loading, error, onRetry, overview, onSelect, onReview, scanning, colors }) {
  const { issue, objectType, modelId, reportId, sort } = session;
  const change = (values) => onSession((current) => ({ ...current, ...values }));
  const panel = useRef(null);
  useEffect(() => {
    const frame = requestAnimationFrame(() => {
      const selected = [...(panel.current?.querySelectorAll("[data-review-id]") || [])].find((element) => element.dataset.reviewId === session.selectedId);
      if (selected) { selected.focus({ preventScroll: true }); contentScroller().scrollTop = session.scrollY || 0; }
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
    <p className="review-purpose"><span className="queue-count"><strong data-ui-number="">{loading ? "…" : filtered.length}</strong>{loading ? "Loading…" : " to review"}</span><span className="review-purpose-copy">Approval saves a trusted label for search and context; rejection excludes it. Power BI files stay unchanged.</span><span className="review-keys" aria-hidden="true"><kbd>J</kbd><kbd>K</kbd> move <kbd>A</kbd> approve <kbd>R</kbd> reject</span></p>
    <div className="queue-toolbar" data-ui-actions="">
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
        <div className="queue-list" onKeyDown={reviewKeys}>{filtered.map((item) => <ReviewItem colors={colors} key={item.id || `${item.issue}-${itemTarget(item)}`} item={item} nodes={snapshot.nodes} disabled={scanning} onSelect={(id, nextView) => { change({ selectedId: item.id || itemTarget(item), scrollY: contentScroller().scrollTop }); onSelect(id, nextView); }} onReview={onReview} />)}</div>
      </> : <EmptyState icon={hasFilters ? <ShieldCheck /> : <CircleCheck />} tone={hasFilters ? undefined : "ok"} title={hasFilters ? "No matching reviews" : "Queue is clear"} detail={hasFilters ? "Choose different filters to see the remaining reviews." : "All suggestions have been reviewed."} action={hasFilters ? <Button variant="outline" onClick={() => change({ issue: "ALL", objectType: "ALL", modelId: "ALL", reportId: "ALL" })}>Clear filters</Button> : null} />}
    </Card>
    </>}
  </div>;
}

function ReviewItem({ item, nodes, onSelect, onReview, colors, disabled = false }) {
  const targetNode = nodes.find((node) => node.id === itemTarget(item));
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const decide = async (action) => { if (pending || disabled) return; setPending(true); setError(""); try { if (!await onReview(action, item)) setError("Decision could not be saved. Try again."); } finally { setPending(false); } };
  const evidence = readableText(item.evidence?.length ? item.evidence : item.item?.evidence, nodes);
  const reason = item.reason || (item.source === "object_name" ? "Only the object name supports this meaning; no description confirms it." : item.source === "description" ? "The source description suggests this meaning. Confirm that the label fits." : "An inference rule proposed this meaning. Confirm it using the recorded evidence.");
  const score = confidence(item.confidence ?? item.properties?.confidence);
  const level = score === null ? "none" : score >= 80 ? "high" : score >= 50 ? "mid" : "low";
  return <div className={`review-item issue-${item.issue}`} aria-busy={pending}>
    <Button variant="ghost" className="review-target" data-review-id={item.id || itemTarget(item)} disabled={!targetNode} onClick={() => onSelect(targetNode.id, "inspector")}>{targetNode ? <TypeGlyph node={targetNode} colors={colors} size="sm" /> : <span className={`review-dot ${item.issue}`} />}<span className="review-target-copy"><strong>{targetNode ? labelFor(targetNode) : "Source object unavailable"}</strong><small className="review-scope">{objectScope(targetNode, nodes)}</small><small className={`review-suggestion issue-${item.issue}`}>{item.issue === "conflict" ? "Conflicting suggestions" : item.issue === "stale" ? "Outdated saved decision" : suggestionLabel(item)}</small>{targetNode ? <small className="review-type">{typeLabel(targetNode.type)}</small> : null}</span></Button>
    <div className="review-evidence"><p>{readableText(reason, nodes)}</p>{evidence ? <small>{evidence}</small> : null}</div>
    <div className={`review-score level-${level}`}><strong data-ui-number="">{score === null ? "—" : `${confidence(itemConfidence(item))}%`}</strong><span className="meter" aria-hidden="true"><i style={{ transform: `scaleX(${(score ?? 0) / 100})` }} /></span><small>{item.issue === "conflict" ? "Conflict" : item.issue === "stale" ? "Outdated" : "Suggested"}</small></div>
    <div className="review-actions" data-ui-actions="">{item.issue === "stale" ? <Button variant="destructive" size="sm" disabled={pending || disabled} onClick={() => decide("remove")}>Remove decision</Button> : <><Button variant="outline" size="sm" className="approve-button" disabled={pending || disabled} onClick={() => decide("approve")}><Check aria-hidden="true" />Approve</Button><Button variant="ghost" size="sm" className="reject-button" disabled={pending || disabled} onClick={() => decide("reject")}><X aria-hidden="true" />Reject</Button></>}</div>
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
  return <fieldset className="candidate-actions" data-ui-actions="" disabled={pending || disabled}>
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
