import VisualBindings from "./components/VisualBindings";
import ObjectContents from "./components/ObjectContents";
import CommonObjects from "./components/CommonObjects";
import PendingChanges from "./components/PendingChanges";
import { hasComparableSources } from "./commonality";
import React, { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, Boxes, Calculator, Check, ChevronDown, ChevronRight, CircleCheck, Clock, Cloud, Flame, Inbox, PanelLeft, ScanSearch, Copy, Bot, Database, FileText, FolderOpen, Link2, Plus, RefreshCw, ScanLine, ShieldAlert, ShieldCheck, TriangleAlert, Waypoints, X } from "lucide-react";
import { ToastProvider, useToast } from "./components/ui/toast";
import { Tooltip } from "./components/ui/tooltip";
import ReviewDecision from "./components/ReviewDecision";
import { explainConfidence } from "./reviewEvidence";
import { brainTransport, normalizeSnapshot } from "./transport";
import { desktopRequest, subscribeToDesktopBridge } from "./desktop";
import NavIcon from "./NavIcon";
import BrandMark from "./components/BrandMark";
import { MAKER_NAME, PRODUCT_CREDIT, PRODUCT_NAME } from "./brand";
import { TypeGlyph, TypeIcon } from "./components/TypeGlyph";
import { CloudSourcePicker } from "./components/CloudSourcePicker";
import { highlightDax } from "./dax";
import { parseRoute, routeHash } from "./routes";
import { compactCount, foldSearchResults, formatCount, formatPlural, matchSnippet, objectName, originNote, readableText, publicProperties, scopeChoices, suggestionLabel, isBackendUnreachableError } from "./presentation";
import { Button } from "./components/ui/button";
import { Input } from "./components/ui/input";
import { NativeSelect } from "./components/ui/native-select";
import { Card } from "./components/ui/card";
import { Label } from "./components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "./components/ui/tabs";
import { Disclosure } from "./components/ui/collapsible";
import { Breadcrumb, BreadcrumbList, BreadcrumbItem, BreadcrumbLink, BreadcrumbPage, BreadcrumbSeparator } from "./components/ui/breadcrumb";
import { Skeleton } from "./components/ui/skeleton";
import { shared as devCenterShared } from "./devcenter/sharedStore.js";
import { Switch } from "./components/ui/switch";
import { sourceState, sourceStatusMap } from "./sourceStatus";
import { setSlashSearchEnabled, slashGoesToSearch, slashSearchEnabled } from "./devcenter/preferences.js";
import { t as devCopy } from "./devcenter/copy.js";
import { artifactColor, artifactStyle, normalizeColors, pluralType, typeLabel } from "./graphPresentation";
import { AppMenuBar, ShortcutsDialog, StatusBar } from "./components/AppShell";
import { commandFor, displayKeys, shortcutKeys } from "./shortcuts";
import CommandPalette from "./components/CommandPalette";
import InspectorEmpty from "./components/InspectorEmpty";
import ExportDialog from "./components/ExportDialog";
import { confidence, labelFor, itemTarget, formatEvidence, numberOr, contentScroller, PageHeading, StatusBadge, EmptyState, formatDate, formatValue } from "./views/shared";
const GraphView = lazy(() => import("./components/GraphView"));
const GraphColors = lazy(() => import("./components/GraphColors"));
const ModelSummary = lazy(() => import("./components/ModelSummary"));
const DocumentationExport = lazy(() => import("./components/DocumentationExport"));
const ChatPanel = lazy(() => import("./components/ChatPanel"));
const AISettings = lazy(() => import("./components/AISettings"));
// It draws with the graph library, which the first screen does not need.
const ImpactExplorer = lazy(() => import("./components/ImpactExplorer"));
const ObjectTree = lazy(() => import("./components/ObjectTree"));
const ReviewSettings = lazy(() => import("./components/ReviewSettings"));
// The review queue is a view of its own; the first screen does not need it.
const ReviewQueue = lazy(() => import("./views/ReviewQueue"));
// Merge models is about a fifth of the code and most sessions never open it.
const DevCenter = lazy(() => import("./devcenter/screens/DevCenter.jsx"));

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
  DEPENDS_ON: "var(--edge-depends-on, #8cb9ff)",
  REFERENCES: "var(--edge-references, #83d7bd)",
  USES: "var(--edge-uses, #e8b879)",
  CONTROLLED_BY: "var(--edge-controlled-by, #de9cff)",
  OBSERVED_WITH: "var(--edge-observed-with, #8997a7)",
};


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

/** Why a row matched when its name does not show it: the matching line of the formula or description. */
function searchSnippet(item, query) {
  const evidence = (item?.match?.evidence || []).find((entry) => /expression|description/i.test(entry.field || ""));
  const first = item?.match?.evidence?.[0]?.field || "";
  if (!evidence || first === "name") return null;
  const parts = matchSnippet(evidence.value, query);
  return parts ? { parts, formula: /expression/i.test(evidence.field) } : null;
}

/** A name with the typed query marked in it. */
function Marked({ text, query }) {
  const parts = matchSnippet(text, query, 400);
  return parts ? <>{parts[0]}<mark>{parts[1]}</mark>{parts[2]}</> : text;
}

function searchMatch(item) {
  const match = item?.match || {};
  const field = match.evidence?.[0]?.field || match.field || item?.match_field || "";
  return /expression/i.test(field) ? "In formula" : /description/i.test(field) ? "In description" : "";
}

const THEME_KEY = "pbibrain-theme";

const LIGHT_QUERY = "(prefers-color-scheme: light)";

/** The saved choice, or "system" when the user never chose (or chose to follow the OS). */
function readThemeChoice() {
  try {
    const saved = globalThis.localStorage?.getItem(THEME_KEY);
    return saved === "light" || saved === "dark" ? saved : "system";
  } catch { return "system"; }
}

function systemTheme() {
  try { return globalThis.matchMedia?.(LIGHT_QUERY).matches ? "light" : "dark"; } catch { return "dark"; }
}

/** Theme follows the operating system until the user picks light or dark; "system" hands it back. */
function useTheme() {
  const [choice, setChoice] = useState(readThemeChoice);
  const [system, setSystem] = useState(systemTheme);
  useEffect(() => {
    const query = globalThis.matchMedia?.(LIGHT_QUERY);
    if (!query?.addEventListener) return undefined;
    const onChange = () => setSystem(query.matches ? "light" : "dark");
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);
  const theme = choice === "system" ? system : choice;
  useEffect(() => {
    const root = document.documentElement;
    root.classList.toggle("dark", theme === "dark");
    if (theme === "light") root.dataset.theme = "light";
    else delete root.dataset.theme;
    try {
      if (choice === "system") globalThis.localStorage?.removeItem(THEME_KEY);
      else globalThis.localStorage?.setItem(THEME_KEY, choice);
    } catch { /* Storage can be unavailable. */ }
  }, [theme, choice]);
  const toggle = useCallback(() => setChoice(theme === "dark" ? "light" : "dark"), [theme]);
  return [theme, toggle, choice, setChoice];
}

const SIDEBAR_KEY = "pbibrain-sidebar";

function useSidebar() {
  const [collapsed, setCollapsed] = useState(() => { try { return globalThis.localStorage?.getItem(SIDEBAR_KEY) === "collapsed"; } catch { return false; } });
  useEffect(() => { try { globalThis.localStorage?.setItem(SIDEBAR_KEY, collapsed ? "collapsed" : "expanded"); } catch { /* Storage can be unavailable. */ } }, [collapsed]);
  return [collapsed, () => setCollapsed((current) => !current)];
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

function AppInner({ transport = brainTransport }) {
  const toast = useToast();
  const [auditTrail, setAuditTrail] = useState([]);
  const compactNav = useCompactNav();
  const desktopHost = Boolean(globalThis.__PBIBRAIN_DESKTOP__);
  const [theme, toggleTheme, themeChoice, setThemeChoice] = useTheme();
  const [sidebarCollapsed, toggleSidebar] = useSidebar();
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [exportTab, setExportTab] = useState("documentation");
  const [recentObjects, setRecentObjects] = useState(() => {
    try {
      const saved = localStorage.getItem("pbibrain-recent-objects");
      return saved ? JSON.parse(saved) : [];
    } catch {
      return [];
    }
  });

  const recordRecentObject = useCallback((node) => {
    if (!node || !node.id) return;
    setRecentObjects((current) => {
      const filtered = current.filter((item) => item.id !== node.id);
      const updated = [{
        id: node.id,
        name: labelFor(node) || node.name || node.id,
        type: node.type,
        model_id: node.model_id,
        report_id: node.report_id,
      }, ...filtered].slice(0, 10);
      try { localStorage.setItem("pbibrain-recent-objects", JSON.stringify(updated)); } catch {}
      return updated;
    });
  }, []);
  const [chatOpen, setChatOpen] = useState(false);
  const [snapshot, setSnapshot] = useState(() => normalizeSnapshot(null));
  const [snapshotLoaded, setSnapshotLoaded] = useState(false);
  const [snapshotLoading, setSnapshotLoading] = useState(false);
  const [snapshotError, setSnapshotError] = useState("");
  const [overview, setOverview] = useState({});
  const [config, setConfig] = useState(null);
  const [configError, setConfigError] = useState("");
  const graphColors = useMemo(() => normalizeColors(config?.graph_colors), [config?.graph_colors]);
  // The page opens where its address points: a reload or a pasted link lands on the same view.
  const [startRoute] = useState(() => parseRoute(globalThis.location?.hash));
  const [view, setView] = useState(startRoute.view);
  const currentView = useRef(view);
  currentView.current = view;
  const [searchSession, setSearchSession] = useState({ query: startRoute.query, modelId: "", reportId: "", result: null });
  const [inspectorSession, setInspectorSession] = useState({ query: "", modelId: "", reportId: "", objectType: "MEASURE", result: null });
  const [settingsTab, setSettingsTab] = useState(startRoute.settingsTab || "project");
  const [graphSession, setGraphSession] = useState(startRoute.focus ? { centerId: startRoute.focus, selectionId: startRoute.focus } : null);
  const [reviewSession, setReviewSession] = useState({ issue: "ALL", objectType: "ALL", modelId: "ALL", reportId: "ALL", sort: "confidence-high" });
  const [inspectorOrigin, setInspectorOrigin] = useState("search");
  const [selectedId, setSelectedId] = useState(startRoute.selectedId);
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

  const selectNode = useCallback(async (id, nextView = "inspector", origin = null) => {
    const requestId = ++selectionRequest.current;
    setSelectedId(id);
    setInspectedObject(null);
    setInspectedDetails(null);
    setInspectorError("");
    if (origin) setInspectorOrigin(origin);
    else if (view !== "inspector") setInspectorOrigin(view);
    if (nextView) setView(nextView);
    try {
      const result = await transport.getObject(id);
      if (requestId !== selectionRequest.current) return;
      const targetObj = result?.object || result?.item || result;
      setInspectedObject(targetObj);
      setInspectedDetails(result);
      if (targetObj) recordRecentObject(targetObj);
      loadSnapshot().catch(() => {});
    } catch (cause) {
      if (requestId !== selectionRequest.current) return;
      setInspectedObject(null);
      setInspectorError(cause.message || "Object could not be loaded");
    }
  }, [loadSnapshot, recordRecentObject, transport, view]);

  // Address <-> state. Moving to another view or object adds a history entry, so Back returns to it;
  // typing a query or refocusing the graph only rewrites the current entry.
  const selectedRef = useRef(selectedId);
  selectedRef.current = selectedId;
  const selectRef = useRef(selectNode);
  selectRef.current = selectNode;
  const applyRoute = useCallback((route) => {
    if (route.view === "inspector") {
      if (route.selectedId && route.selectedId !== selectedRef.current) selectRef.current(route.selectedId, "inspector");
      else {
        if (!route.selectedId) { setSelectedId(null); setInspectedObject(null); }
        setView("inspector");
      }
      return;
    }
    setView(route.view);
    if (route.view === "config") setSettingsTab(route.settingsTab || "project");
    if (route.view === "search") setSearchSession((current) => current.query === route.query ? current : { ...current, query: route.query, selectedId: null, scrollY: 0 });
    if (route.view === "graph" && route.focus) setGraphSession((current) => current?.centerId === route.focus ? current : { ...(current || {}), centerId: route.focus, selectionId: route.focus });
  }, []);
  useEffect(() => {
    if (startRoute.view === "inspector" && startRoute.selectedId) selectRef.current(startRoute.selectedId, "inspector", "inspector");
    const onMove = () => applyRoute(parseRoute(globalThis.location.hash));
    globalThis.addEventListener("popstate", onMove);
    return () => globalThis.removeEventListener("popstate", onMove);
  }, [applyRoute, startRoute]);
  const hash = routeHash({ view, selectedId, settingsTab, query: searchSession.query, focus: graphSession?.centerId || "" });
  const place = `${view}|${view === "inspector" ? selectedId || "" : ""}`;
  const lastPlace = useRef(place);
  useEffect(() => {
    const samePlace = lastPlace.current === place;
    lastPlace.current = place;
    const current = globalThis.location?.hash || "";
    if (current === hash || (!current && hash === "#/")) return;
    try { globalThis.history?.[samePlace ? "replaceState" : "pushState"](null, "", hash); } catch { /* A sandboxed frame can refuse history changes. */ }
  }, [hash, place]);

  const applyScan = useCallback(async () => {
    if (scanInFlight.current) return;
    scanInFlight.current = true;
    setScanning(true);
    setLoading(true);
    setOperationError("");
    invalidateProjectRequests();
    setSnapshotLoading(false);
    const started = Date.now();
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
      const objects = result?.overview?.counts?.nodes;
      const seconds = Math.max(1, Math.round((Date.now() - started) / 1000));
      setNotice(objects ? `Scan complete: ${formatCount(objects)} objects in ${seconds} s` : "Scan complete");
      await load();
      if (currentView.current === "review") await loadSnapshot();
    } catch (cause) {
      if (cause?.cancelled) setNotice("Scan cancelled. Nothing was changed.");
      else setOperationError(cause.message || "Scan failed");
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
        const actionLabel = {
          approve: "Suggestion approved",
          reject: "Suggestion rejected",
          edit: "Suggestion updated",
          override: "Meaning updated",
          remove: "Saved decision removed",
        }[action] || "Review updated";

        const auditEntry = {
          id: `audit-${Date.now()}-${reviewId}`,
          reviewId,
          candidateId,
          targetId: target,
          action,
          actor: "You",
          timestamp: new Date().toISOString(),
          label: suggestionLabel(item),
          value: actionValue,
          property,
          item,
          previousStatus: item.status || "candidate",
        };
        setAuditTrail((current) => [auditEntry, ...current]);

        toast.show({
          tone: "ok",
          text: actionLabel,
          action: {
            label: "Undo",
            onClick: async () => {
              await handleUndoReview(auditEntry);
            },
          },
        });
        await Promise.allSettled([loadSnapshot(), load()]);
        return true;
      } catch (cause) {
        if (generation !== projectGeneration.current) return false;
        toast.show({ tone: "warn", text: "Review failed. Try again." });
        return false;
      }
    },
    [transport, loadSnapshot, load, toast],
  );

  const handleUndoReview = useCallback(
    async (auditEntry) => {
      if (auditEntry.isBulk) {
        try {
          // The token restores what each suggestion was before; without one (after a restart) they reopen.
          if (auditEntry.undoToken && typeof transport.reviewBulkUndo === "function") {
            try { await transport.reviewBulkUndo(auditEntry.undoToken); }
            catch { await transport.reviewBulk("reopen", auditEntry.itemIds || []); }
          } else await transport.reviewBulk("reopen", auditEntry.itemIds || []);
          setAuditTrail((current) => current.filter((entry) => entry.id !== auditEntry.id));
          toast.show({ tone: "ok", text: "Bulk decision undone" });
          await Promise.allSettled([loadSnapshot(), load()]);
          return true;
        } catch {
          toast.show({ tone: "warn", text: "Could not undo bulk decision. Try again." });
          return false;
        }
      }
      const { item, reviewId, candidateId, targetId, property } = auditEntry;
      const stale = item?.issue === "stale" || item?.issue_type === "stale" || item?.status === "stale";
      const payload = {
        target: targetId,
        candidate_id: candidateId,
        review_id: reviewId,
        property,
      };
      if (stale) {
        payload.override_id = reviewId;
        payload.override_record = item?.item || item;
      }
      try {
        const result = await transport.review("undo", payload);
        const returned = result?.snapshot || result?.brain;
        if (returned) {
          setSnapshot(normalizeSnapshot(returned));
          setSnapshotLoaded(true);
        } else {
          setSnapshot((current) => ({
            ...current,
            semantic_candidates: current.semantic_candidates.map((candidate) =>
              candidate.id === (candidateId || reviewId) ? { ...candidate, status: "candidate" } : candidate
            ),
          }));
        }
        setAuditTrail((current) => current.filter((entry) => entry.id !== auditEntry.id));
        toast.show({ tone: "ok", text: "Decision undone" });
        await Promise.allSettled([loadSnapshot(), load()]);
        return true;
      } catch {
        toast.show({ tone: "warn", text: "Could not undo decision. Try again." });
        return false;
      }
    },
    [transport, loadSnapshot, load, toast],
  );

  const bulkReview = useCallback(
    async (action, items) => {
      if (scanInFlight.current || !items?.length) return false;
      const generation = projectGeneration.current;
      setNotice("");
      try {
        const itemPayloads = items.map((item) => {
          const reviewId = item?.review_id || item?.override_id || item?.id;
          const candidateId = item?.properties?.candidate_id || item?.item?.candidate_id || item?.item?.properties?.candidate_id || reviewId;
          const target = itemTarget(item);
          return candidateId || target;
        }).filter(Boolean);

        const result = await transport.reviewBulk(action, itemPayloads);
        if (generation !== projectGeneration.current) return false;
        const returned = result?.snapshot || result?.brain;
        if (returned) {
          setSnapshot(normalizeSnapshot(returned));
          setSnapshotLoaded(true);
        }

        const actionText = action === "approve" ? "Approved" : action === "reject" ? "Rejected" : "Updated";
        const count = items.length;
        const actionLabel = `${actionText} ${count} ${count === 1 ? "suggestion" : "suggestions"}`;

        const bulkAuditEntry = {
          id: `audit-${Date.now()}-bulk`,
          isBulk: true,
          action,
          items,
          itemIds: itemPayloads,
          undoToken: result?.result?.undo_token || "",
          count,
          actor: "You",
          timestamp: new Date().toISOString(),
          label: actionLabel,
        };
        setAuditTrail((current) => [bulkAuditEntry, ...current]);

        toast.show({
          tone: "ok",
          text: actionLabel,
          action: {
            label: "Undo",
            onClick: async () => {
              await handleUndoReview(bulkAuditEntry);
            },
          },
        });
        await Promise.allSettled([loadSnapshot(), load()]);
        return true;
      } catch (cause) {
        if (generation !== projectGeneration.current) return false;
        toast.show({ tone: "warn", text: `Bulk ${action} failed. Try again.` });
        return false;
      }
    },
    [handleUndoReview, load, loadSnapshot, transport, toast],
  );

  const navigate = useCallback((key) => { setView(key); }, []);
  // The review queue reads the snapshot however the view was reached: the sidebar, a link or Back.
  useEffect(() => {
    if (view === "review") loadSnapshot().catch(() => {});
  }, [view, loadSnapshot]);

  const goBack = useCallback(() => {
    if (currentView.current !== "inspector" || !selectedId) return;
    if (inspectorOrigin === "inspector") { setSelectedId(null); setInspectedObject(null); }
    else setView(inspectorOrigin);
  }, [inspectorOrigin, selectedId]);

  // Shell commands. Menus, toolbar buttons and keys all run through here (shortcuts.js holds the key map).
  const commands = useRef({});
  commands.current = {
    find: () => setPaletteOpen(true),
    back: goBack,
    sidebar: toggleSidebar,
    theme: toggleTheme,
    shortcuts: () => setShortcutsOpen(true),
    chat: () => setChatOpen((current) => !current),
  };
  // "/" outside a text field jumps to search; Settings can turn that key off (UI design 9.3, A24).
  // Keys are ignored while a dialog or menu owns focus, so Escape and arrows stay with it.
  useEffect(() => {
    const onKey = (event) => {
      if (event.defaultPrevented) return;
      if (slashGoesToSearch(event)) { event.preventDefault(); setView("search"); focusSearchField(); return; }
      // Alt+Left / Alt+Right walk the history, also in the desktop window, which has no browser chrome.
      if (event.altKey && !event.ctrlKey && !event.metaKey && !event.shiftKey && (event.key === "ArrowLeft" || event.key === "ArrowRight") && !/^(INPUT|TEXTAREA|SELECT)$/.test(event.target?.tagName || "")) {
        event.preventDefault();
        if (event.key === "ArrowLeft") globalThis.history.back(); else globalThis.history.forward();
        return;
      }
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

  // Manage focus on view changes so focus moves to view heading or primary control instead of landing on <body>
  useEffect(() => {
    const timer = setTimeout(() => {
      if (view === "search") {
        const searchInput = document.querySelector("#brain-search-query, .search-field input");
        if (searchInput) { searchInput.focus({ preventScroll: true }); return; }
      }
      if (view === "graph") {
        const canvas = document.querySelector(".graph-canvas, [tabindex='0'].react-flow, .graph-search input");
        if (canvas) { canvas.focus({ preventScroll: true }); return; }
      }
      const heading = document.querySelector(".view-frame h1, .page-heading h1, [data-ui-stack] h1");
      if (heading) {
        if (!heading.hasAttribute("tabindex")) heading.setAttribute("tabindex", "-1");
        heading.focus({ preventScroll: true });
        return;
      }
      document.querySelector("#main-content")?.focus({ preventScroll: true });
    }, 40);
    return () => clearTimeout(timer);
  }, [view]);

  if (desktopHost && desktopState !== "ready") {
    return <DesktopConnecting error={desktopError} onRetry={() => setBridgeAttempt((attempt) => attempt + 1)} />;
  }

  if (desktopApi && !desktopSession?.project) {
    return <DesktopOnboarding api={desktopApi} error={desktopError} onOpen={openDesktopProject} />;
  }

  const activeProject = desktopSession?.project;
  const projectName = activeProject?.name || config?.name || PRODUCT_NAME;
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
  // The sample: one click from an empty project to every view with content.
  const openSample = async () => {
    if (scanning || typeof transport.addSample !== "function") return;
    try {
      setConfig(await transport.addSample());
      await applyScan();
    } catch (cause) {
      setOperationError(cause?.message || "The sample project could not be added");
    }
  };
  const openSettings = (tab = "project") => { setSettingsTab(tab); setView("config"); };
  commands.current.view = (key) => { navigate(key); if (key === "search") focusSearchField(); };
  commands.current.reload = () => { if (!loading && !scanning) reloadBrain(); };
  commands.current.scan = runScan;
  const lastScan = overview.last_scan ? `Scanned ${formatDate(overview.last_scan)}` : overview.scan_state === "not_scanned" || !counts.objects ? "Not scanned" : "Last scan time unknown";
  const viewLabel = VIEWS.find(([key]) => key === view)?.[1];
  // What the chat's selection chip shows: the graph's selected node on the graph, else the inspected object.
  const graphPick = view === "graph" && graphSession?.selectionId ? graphSession.selectionId : null;
  const graphNode = graphPick ? (graphSession?.result?.nodes || nodes).find((node) => node.id === graphPick) : null;
  const chatSelection = graphPick
    ? { id: graphPick, name: graphNode ? objectName(graphNode) : graphPick, type: graphNode?.type || "" }
    : selectedId ? { id: selectedId, name: selected ? objectName(selected) : selectedId, type: selected?.type || "" } : null;
  const menus = [
    { id: "file", label: "File", items: [
      activeProject ? { label: "Change project…", onSelect: closeDesktopProject, disabled: scanning } : null,
      { label: "Scan sources", keys: shortcutKeys("scan"), onSelect: runScan, disabled: scanning || !hasSources },
      { separator: true },
      { label: "Project sources…", onSelect: () => openSettings("project") },
      { label: "Export documentation…", onSelect: () => { setExportTab("documentation"); setExportOpen(true); }, disabled: !counts.objects },
      { label: "Export model summary / agent context…", onSelect: () => { setExportTab("summary"); setExportOpen(true); } },
      { label: "Settings", keys: shortcutKeys("view:config"), onSelect: () => openSettings(settingsTab) },
    ] },
    { id: "view", label: "View", items: [
      { label: "Reload data", keys: shortcutKeys("reload"), onSelect: commands.current.reload, disabled: loading || scanning },
      { separator: true },
      { label: "Side bar", keys: shortcutKeys("sidebar"), checked: !sidebarCollapsed, onSelect: toggleSidebar },
      { label: "Dark theme", keys: shortcutKeys("theme"), checked: theme === "dark", onSelect: toggleTheme },
      { label: "Match system theme", checked: themeChoice === "system", onSelect: () => setThemeChoice(themeChoice === "system" ? theme : "system") },
      { label: "Graph colors…", onSelect: () => openSettings("colors") },
      { separator: true },
      { label: "Chat", keys: shortcutKeys("chat"), checked: chatOpen, onSelect: commands.current.chat },
      { label: "AI provider…", onSelect: () => openSettings("ai") },
    ] },
    { id: "go", label: "Go", items: [
      ...VIEWS.filter(([key]) => key !== "config").map(([key, label]) => ({ label, keys: shortcutKeys(`view:${key}`), onSelect: () => commands.current.view(key) })),
      { separator: true },
      { label: "Command palette…", keys: shortcutKeys("find"), onSelect: () => setPaletteOpen(true) },
      { label: "Back", keys: shortcutKeys("back"), onSelect: goBack, disabled: !(view === "inspector" && selectedId) },
    ] },
    { id: "help", label: "Help", items: [
      { label: "Keyboard shortcuts", keys: shortcutKeys("shortcuts"), onSelect: () => setShortcutsOpen(true) },
      { separator: true },
      { label: `About ${PRODUCT_NAME}`, onSelect: () => toast.show({ tone: "ok", text: `${PRODUCT_CREDIT}. Semantic graph workbench for Power BI.` }) },
    ] },
  ];
  return (
    <div className={`app-shell ${sidebarCollapsed ? "sidebar-collapsed" : ""} ${chatOpen ? "chat-open" : ""}`}>
      <a className="skip-link" href="#main-content">Skip to content</a>
      <AppMenuBar menus={menus} projectName={projectName}>
        <button type="button" className="command-center" onClick={() => setPaletteOpen(true)} title={`Command palette (${displayKeys("Ctrl+K")})`}>
          <ScanSearch aria-hidden="true" /><span>Type a command or search objects…</span><kbd aria-hidden="true">{displayKeys("Ctrl+K")}</kbd>
        </button>
        <Button variant="ghost" size="sm" className="titlebar-chat" aria-pressed={chatOpen} onClick={commands.current.chat} tooltip={`Chat (${displayKeys(shortcutKeys("chat"))})`} aria-label={`Chat (${displayKeys(shortcutKeys("chat"))})`}><Bot aria-hidden="true" /><span>Chat</span></Button>
      </AppMenuBar>
      <div className="workbench">
        <aside className="sidebar" aria-label="Views">
          <nav aria-label="Main navigation" className="sidebar-nav">
            {VIEWS.map(([key, label]) => {
              const keys = displayKeys(shortcutKeys(`view:${key}`));
              return (
                <Button variant="ghost" key={key} aria-current={view === key ? "page" : undefined} className={`nav-button ${view === key ? "active" : ""} ${key === "config" ? "nav-settings" : ""}`} tooltip={`${label} (${keys})`} onClick={() => navigate(key)} title={compactNav || sidebarCollapsed ? undefined : `${label} (${keys})`}>
                  <NavIcon name={key} />
                  <span className="nav-label">{label}</span>
                  {key === "review" && pending > 0 ? <span className="nav-count" data-ui-number="">{compactCount(pending)}</span> : null}
                </Button>
              );
            })}
          </nav>
          <Button variant="ghost" size="icon-sm" className="sidebar-collapse" onClick={toggleSidebar} aria-label={sidebarCollapsed ? "Expand side bar" : "Collapse side bar"} aria-expanded={!sidebarCollapsed} tooltip={`${sidebarCollapsed ? "Expand" : "Collapse"} side bar (${displayKeys("Ctrl+B")})`}><PanelLeft aria-hidden="true" /></Button>
        </aside>

      <div className="main-column">
        <header className="topbar view-toolbar">
          <Breadcrumb className="breadcrumb">
            <BreadcrumbList>
              <NavIcon name={view} />
              {view === "inspector" && selected ? (
                <>
                  <BreadcrumbItem>
                    <BreadcrumbLink asChild>
                      <button
                        type="button"
                        className="breadcrumb-view breadcrumb-link"
                        onClick={() => {
                          if (inspectorOrigin === "inspector") {
                            setSelectedId(null);
                            setInspectedObject(null);
                          } else {
                            setView(inspectorOrigin);
                          }
                        }}
                        title={inspectorOrigin === "inspector" ? "Inspector" : `Back to ${VIEWS.find(([k]) => k === inspectorOrigin)?.[1] || "overview"}`}
                      >
                        {inspectorOrigin === "inspector" ? "Inspector" : VIEWS.find(([k]) => k === inspectorOrigin)?.[1] || "Inspector"}
                      </button>
                    </BreadcrumbLink>
                  </BreadcrumbItem>
                  <BreadcrumbSeparator />
                  <BreadcrumbItem>
                    <BreadcrumbPage className="breadcrumb-leaf" title={labelFor(selected)}>{labelFor(selected)}</BreadcrumbPage>
                  </BreadcrumbItem>
                </>
              ) : (
                <BreadcrumbItem>
                  <BreadcrumbPage className="breadcrumb-view">{viewLabel}</BreadcrumbPage>
                </BreadcrumbItem>
              )}
            </BreadcrumbList>
          </Breadcrumb>
          <div className="topbar-actions" role="toolbar" aria-label={`${viewLabel} toolbar`} data-ui-actions="">
            {activeProject ? <Button variant="ghost" size="sm" className="project-switch" onClick={closeDesktopProject} disabled={scanning}><FolderOpen />Change project</Button> : null}
            {counts.objects > 0 ? <Button variant="ghost" size="sm" onClick={runScan} disabled={scanning || !hasSources} title={hasSources ? `Re-read every source and rebuild the brain (${displayKeys("Ctrl+F5")})` : "Add sources in Settings first"}><ScanLine aria-hidden="true" />{scanning ? "Scanning…" : "Scan sources"}</Button> : null}
          </div>
        </header>

        <main id="main-content" tabIndex={-1} className={`content content-${view}`}>
          {(view !== "devcenter" && (error || configError || operationError)) || desktopError ? (
            <div className="error-banner" role="alert">
              <TriangleAlert aria-hidden="true" />
              <span>
                {isBackendUnreachableError(error || configError)
                  ? "Can't reach the PBIBrain service. Make sure the service is running, then retry."
                  : readableText(error || configError || operationError || desktopError)}
              </span>
              {error || configError ? <Button variant="outline" size="sm" onClick={load}>Retry</Button> : null}
            </div>
          ) : null}
          {counts.objects > 0 && view !== "devcenter" ? <PendingChanges transport={transport} scanning={scanning} onScan={applyScan} /> : null}
          <div className="view-frame" key={view}>
            <Suspense fallback={<div className="view-loading" role="status"><RefreshCw className="spin" aria-hidden="true" />Loading view…</div>}>
            {view === "overview" ? <Overview onSelect={selectNode} overview={overview} config={config} counts={counts} colors={graphColors} loading={loading} projectName={projectName} onView={navigate} onBrowseType={(objectType) => { setSearchSession({ query: "", modelId: "", reportId: "", objectType, result: null }); setView("search"); }} onSources={() => { setSettingsTab("project"); setView("config"); }} onSample={openSample} onSummary={() => { setSettingsTab("summary"); setView("config"); }} onScan={applyScan} scanning={scanning} scanLabel={activeProject ? "Scan project" : "Scan sources"} onReview={() => navigate("review")} transport={transport} onMerge={(modelIds) => { const names = modelIds.map((id) => (overview.model_objects || []).find((item) => item.id === id)?.name || id); setNotice(`Start a merge session with ${names.join(", ")}`); navigate("devcenter"); }} error={error || configError} onRetry={load} snapshot={snapshot} auditTrail={auditTrail} /> : null}
            {view === "search" ? <div className="page page-narrow" data-ui-stack=""><SearchView session={searchSession} onSession={setSearchSession} colors={graphColors} transport={transport} overview={overview} onSelect={selectNode} /></div> : null}
            {view === "graph" ? <GraphView session={graphSession} onSession={setGraphSession} colors={graphColors} transport={transport} overview={overview} snapshot={snapshot} selectedId={selectedId} onSelect={selectNode} versionLinks={config?.version_links || null} onVersionLinks={config ? async (links) => { setConfig(await transport.saveConfig({ ...config, version_links: links })); } : undefined} /> : null}
            {view === "inspector" ? <div className="inspector-layout">
              {counts.objects > 0 ? <Suspense fallback={<aside className="object-tree" />}><ObjectTree transport={transport} colors={graphColors} selectedId={selectedId} refreshKey={overview.last_scan} onSelect={(id) => selectNode(id, "inspector", inspectorOrigin === "inspector" || !selectedId ? "inspector" : inspectorOrigin)} /></Suspense> : <span />}
              <div className="inspector-main page page-wide" data-ui-stack="">{selectedId ? <><Button variant="ghost" size="sm" className="inspector-back" onClick={() => { if (inspectorOrigin === "inspector") { setSelectedId(null); setInspectedObject(null); } else setView(inspectorOrigin); }}><ArrowLeft aria-hidden="true" />{inspectorOrigin === "search" ? "Back to search results" : inspectorOrigin === "inspector" ? "Inspect another object" : `Back to ${VIEWS.find(([key]) => key === inspectorOrigin)?.[1]?.toLowerCase() || "overview"}`}</Button><Inspector key={selectedId} transport={transport} scanning={scanning} colors={graphColors} node={selected} details={inspectedDetails} loading={Boolean(selectedId && !inspectedDetails && !inspectorError)} error={inspectorError} snapshot={snapshot} snapshotLoaded={snapshotLoaded} snapshotError={snapshotError} onEvidenceRetry={() => loadSnapshot().catch(() => {})} overview={overview} onSelect={selectNode} onRetry={() => selectNode(selectedId)} onReview={review} onGraph={() => setView("graph")} /></> : <InspectorEmpty overview={overview} colors={graphColors} recentObjects={recentObjects} onSelect={(id) => { setInspectorOrigin("inspector"); selectNode(id); }} onOpenSearch={() => { setView("search"); focusSearchField(); }} onOpenPalette={() => setPaletteOpen(true)} onOpenGraph={() => setView("graph")} />}</div>
            </div> : null}
            {view === "review" ? <div className="page page-wide" data-ui-stack=""><ReviewQueue colors={graphColors} scanning={scanning} session={reviewSession} onSession={setReviewSession} snapshot={snapshot} loaded={snapshotLoaded} loading={!snapshotLoaded && (snapshotLoading || !snapshotError)} error={snapshotError} onRetry={() => loadSnapshot().catch(() => {})} overview={overview} onSelect={selectNode} onReview={review} onBulkReview={bulkReview} auditTrail={auditTrail} onUndoReview={handleUndoReview} /></div> : null}
            {view === "devcenter" ? <DevCenter onOpenProject={closeDesktopProject} /> : null}
            {view === "config" ? <div className="page page-narrow" data-ui-stack=""><PageHeading quiet title="Settings" />{configError && !config ? <Card className="panel"><EmptyState icon={<TriangleAlert />} tone="bad" title="Project settings unavailable" detail="Retry to load your saved sources and appearance." action={<Button variant="outline" onClick={load}>Retry settings</Button>} /></Card> : <Tabs value={settingsTab} onValueChange={setSettingsTab} className="settings-tabs">
              <TabsList aria-label="Settings sections"><TabsTrigger value="project">Project</TabsTrigger><TabsTrigger value="review">Review</TabsTrigger><TabsTrigger value="colors">Graph colors</TabsTrigger><TabsTrigger value="summary">Model summary / agent context</TabsTrigger><TabsTrigger value="documentation">Documentation export</TabsTrigger><TabsTrigger value="ai">AI provider</TabsTrigger><TabsTrigger value="keyboard">Keyboard</TabsTrigger></TabsList>
              <TabsContent value="ai"><Suspense fallback={<ViewLoading />}><AISettings transport={transport} /></Suspense></TabsContent>
              <TabsContent value="colors"><Suspense fallback={<ViewLoading />}><GraphColors config={config} transport={transport} overview={overview} onSaved={setConfig} /></Suspense></TabsContent>
              <TabsContent value="documentation"><Suspense fallback={<ViewLoading />}><DocumentationExport overview={overview} transport={transport} scanning={scanning} /></Suspense></TabsContent>
              <TabsContent value="summary"><Suspense fallback={<ViewLoading />}><ModelSummary overview={overview} transport={transport} scanning={scanning} /></Suspense></TabsContent>
              <TabsContent value="review"><Suspense fallback={<ViewLoading />}><ReviewSettings transport={transport} config={config} onSaved={setConfig} scanning={scanning} onChanged={() => Promise.allSettled([load(), snapshotLoaded ? loadSnapshot() : null])} /></Suspense></TabsContent>
              <TabsContent value="keyboard"><KeyboardSettings /></TabsContent>
              <TabsContent value="project">{activeProject ? <DesktopProjectView api={desktopApi} project={activeProject} overview={overview} config={config} transport={transport} scanning={scanning} onScan={applyScan} onChange={closeDesktopProject} onRefresh={load} onSaved={setConfig} /> : <ConfigView transport={transport} config={config} onSaved={setConfig} onScan={applyScan} scanning={scanning} />}</TabsContent></Tabs>}</div> : null}
            </Suspense>
          </div>
        </main>
      </div>
      {chatOpen ? <Suspense fallback={<aside className="chat-panel" aria-label="Chat"><p role="status" className="loading-label">Loading chat…</p></aside>}>
        <ChatPanel open={chatOpen} onClose={() => setChatOpen(false)} transport={transport} view={{ id: view, label: viewLabel }} selection={chatSelection}
          onObject={(id) => selectNode(id, "inspector", "inspector")} onGraph={(id) => { setGraphSession({ centerId: id, selectionId: id }); setView("graph"); }}
          onMerge={() => navigate("devcenter")} onSettings={() => openSettings("ai")} />
      </Suspense> : null}
      </div>
      <StatusBar connection={connection} projectName={projectName} counts={counts} pending={pending} onReview={() => navigate("review")} scanning={scanning} scanStatus={transport?.scanStatus} onCancelScan={typeof transport?.cancelScan === "function" ? () => transport.cancelScan().catch(() => {}) : undefined} lastScan={lastScan} notice={notice} noticeFailed={failedNotice} theme={theme} onTheme={toggleTheme} onShortcuts={() => setShortcutsOpen(true)} onScan={runScan} />
      <ShortcutsDialog open={shortcutsOpen} onOpenChange={setShortcutsOpen} />
      <CommandPalette
        open={paletteOpen}
        onOpenChange={setPaletteOpen}
        onNavigate={navigate}
        onSelectObject={(id) => {
          setInspectorOrigin("search");
          selectNode(id);
        }}
        overview={overview}
        colors={graphColors}
        transport={transport}
        recentObjects={recentObjects}
        onScan={runScan}
        onReload={commands.current.reload}
        onTheme={toggleTheme}
        theme={theme}
        onChat={commands.current.chat}
        onShortcuts={() => setShortcutsOpen(true)}
        onExportDocumentation={() => {
          setExportTab("documentation");
          setExportOpen(true);
        }}
        onExportSummary={() => {
          setExportTab("summary");
          setExportOpen(true);
        }}
        activeSession={devCenterShared.store?.getState?.()?.session ?? null}
      />
      <ExportDialog
        open={exportOpen}
        onOpenChange={setExportOpen}
        defaultTab={exportTab}
        overview={overview}
        transport={transport}
        scanning={scanning}
      />
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
  return <main className="onboarding-shell"><Card className="onboarding-card connecting-card" aria-live="polite"><BrandMark size={44} className="onboarding-mark" /><h1>{error ? "Desktop connection needed" : "Opening PBIBrain"}</h1><p className="onboarding-copy">{error || "Preparing your private project workspace."}</p>{error ? <Button onClick={onRetry}><RefreshCw />Retry connection</Button> : <span className="connecting-indicator"><i /><i /><i /><span>Connecting</span></span>}<p className="brand-credit">by {MAKER_NAME}</p></Card></main>;
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
      <p className="brand-credit">by {MAKER_NAME}</p>
      <p className="onboarding-note">Your Power BI files are only read, never changed.</p>
    </Card>
  </main>;
}

/** Found or not, and what the last scan did, for each saved source. Read again while a scan runs and when it ends. */
function useSourceStatus(transport, sources, scanning) {
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

function DesktopProjectView({ api, project, overview, config, transport, scanning, onScan, onChange, onRefresh, onSaved }) {
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
      <div className="desktop-sources"><div className="panel-heading"><div><h2>Power BI source files</h2></div><Button variant="outline" onClick={addSources} disabled={sourceWorking || scanning} tooltip={scanning ? "Cannot add sources while scan is in progress" : sourceWorking ? "Adding sources…" : undefined}><Plus />{sourceWorking ? "Adding…" : "Add source files"}</Button></div>{sources.length ? <div className="source-list">{sources.map((source) => { const state = sourceState(sourceStatus[source]); return <div className={`desktop-source-row source-${state.tone}`} key={source}><span className="source-state" role="img" aria-label={state.label} title={state.label} /><FileText className="source-icon" aria-hidden="true" /><span title={source}>{source}</span>{state.text ? <small className="source-scan" title={state.label}>{state.text}</small> : null}<Button variant="ghost" size="icon-sm" onClick={() => removeSource(source)} disabled={sourceWorking || scanning} aria-label={`Remove ${source}`}><X /></Button></div>; })}</div> : <EmptyState icon={<FileText />} title="No source files yet" detail="Add PBIP projects or model JSON files to scan them with this project." />}{sourceError ? <p className="onboarding-error" role="alert">{sourceError}</p> : null}</div>
      {typeof api?.add_cloud_source === "function" || cloudSources.length ? <div className="desktop-sources cloud-sources"><div className="panel-heading"><div><h2>Power BI service items</h2><p className="muted">Cloud semantic models and reports, read with your Microsoft sign-in.</p></div>{typeof api?.add_cloud_source === "function" ? <Button variant="outline" onClick={() => setCloudOpen(true)} disabled={sourceWorking || scanning || cloudOpen}><Cloud />Add cloud item</Button> : null}</div>
        {cloudOpen ? <CloudSourcePicker api={api} onClose={() => setCloudOpen(false)} onAdded={async () => { setCloudOpen(false); await onRefresh(); }} /> : null}
        {cloudSources.length ? <div className="source-list">{cloudSources.map((item) => <div className="desktop-source-row" key={item.item_id}><Cloud className="source-icon" aria-hidden="true" /><span title={`${item.workspace_name} · ${item.name}`}>{item.workspace_name} · {item.name} <span className="muted">({item.kind === "cloud_model" ? "semantic model" : "report"}, {item.access_type})</span></span><Button variant="ghost" size="icon-sm" onClick={() => removeCloudSource(item)} disabled={sourceWorking || scanning} aria-label={`Remove ${item.name}`}><X /></Button></div>)}</div> : null}
      </div> : null}
      <div className="config-actions" data-ui-actions=""><Button onClick={onScan} disabled={scanning} tooltip={scanning ? "Scan in progress" : undefined}><ScanLine />{scanning ? "Scanning…" : "Scan project"}</Button></div>
    </Card>
  </>;
}

/** The last part of a path: the file or folder name, which is what tells sources apart. */
function sourceName(path) {
  return String(path || "").replace(/[\\/]+$/, "").split(/[\\/]/).pop() || "";
}
function pathExample() {
  return /win/i.test(globalThis.navigator?.platform || "") ? "C:\\Reports\\Finance\\Finance.pbip" : "/home/me/reports/Finance/Finance.pbip";
}

function Overview({ overview, config, counts, colors, loading, projectName, onView, onBrowseType, onSources, onSample, onSummary, onScan, onReview, onSelect, onMerge, transport, scanning, scanLabel, error, onRetry, snapshot, auditTrail }) {
  // The seven model and report types show at once; meanings (aliases, roles, concepts…) open on demand.
  const [allTypes, setAllTypes] = useState(false);
  const hasObjects = counts.objects > 0;
  if (isBackendUnreachableError(error) && !hasObjects) {
    return (
      <div className="page page-overview" data-ui-stack="">
        <header className="overview-hero">
          <h1>{projectName}</h1>
          <p className="hero-meta muted">Service offline</p>
        </header>
        <Card className="panel" role="region" aria-label="PBIBrain service unreachable">
          <div className="empty-state tone-bad">
            <span className="empty-icon" aria-hidden="true"><TriangleAlert /></span>
            <h2>Can't reach the PBIBrain service</h2>
            <p>Make sure the PBIBrain backend service is running, then retry.</p>
            <div className="status-actions" data-ui-actions="">
              <Button onClick={onRetry}><RefreshCw />Retry connection</Button>
            </div>
          </div>
        </Card>
      </div>
    );
  }
  const hasSources = Boolean(config?.sources?.length || config?.cloud_sources?.length);
  const sourceCount = config?.sources ? config.sources.length + (config.cloud_sources?.length || 0) : undefined;
  const notChecked = Array.isArray(overview.not_checked) ? overview.not_checked : [];
  const lastScan = overview.last_scan;
  const validationState = overview.validation_state || "not_run";
  const validationLabel = { valid: "Graph validation passed", invalid: "Graph validation failed", warning: "Graph validation warnings", not_run: "Graph validation not run" }[validationState] || "Graph validation unavailable";
  // Notes at INFO level (for example an object type the validator only passes through) are not issues to act on.
  const issues = (overview.validation_issues || []).filter((item) => String(item.severity || "").toUpperCase() !== "INFO");
  // The overview lists the first issues and counts the rest.
  const issueTotal = Math.max(Number(overview.validation_issue_count) || 0, issues.length);
  const pending = counts.review;
  const ValidationIcon = validationState === "valid" ? ShieldCheck : ShieldAlert;
  const validationTone = { valid: "ok", invalid: "bad", warning: "warn" }[validationState] || "idle";

  const nodes = snapshot?.nodes || [];
  const edges = snapshot?.edges || [];
  const candidates = snapshot?.semantic_candidates || [];
  const conflicts = snapshot?.conflicts || [];

  const mostUsedMeasures = useMemo(() => {
    // The server counts over the whole graph. The browser estimate below is only for a server that does not send it.
    if (Array.isArray(overview?.top_measures)) return overview.top_measures.map((item) => ({ node: item, count: item.count || 0 }));
    const measures = nodes.filter((node) => node.type === "MEASURE" || node.type === "CALCULATION_ITEM");
    if (!measures.length) return [];
    const usageCounts = new Map();
    for (const edge of edges) {
      if (edge.type !== "CONTAINS" && edge.to_id) {
        usageCounts.set(edge.to_id, (usageCounts.get(edge.to_id) || 0) + 1);
      }
    }
    return measures
      .map((m) => ({ node: m, count: usageCounts.get(m.id) || 0 }))
      .sort((a, b) => b.count - a.count || a.node.name.localeCompare(b.node.name))
      .slice(0, 5);
  }, [nodes, edges, overview?.top_measures]);

  const unreviewedOnHot = useMemo(() => {
    if (Array.isArray(overview?.hot_unreviewed)) {
      return overview.hot_unreviewed.map((item) => ({
        item: { id: item.id, kind: item.kind, meaning: item.label, scope: item.scope }, targetId: item.target_id, degree: item.degree || 0,
        targetNode: { id: item.target_id, name: item.name, type: item.type },
      }));
    }
    const unreviewed = [
      ...candidates.filter((c) => !["approved", "rejected", "overridden"].includes(c.status)).map((c) => ({ ...c, kind: "candidate" })),
      ...conflicts.map((c) => ({ ...c, kind: "conflict" })),
    ];
    if (!unreviewed.length) return [];
    const degreeMap = new Map();
    for (const edge of edges) {
      if (edge.from_id) degreeMap.set(edge.from_id, (degreeMap.get(edge.from_id) || 0) + 1);
      if (edge.to_id) degreeMap.set(edge.to_id, (degreeMap.get(edge.to_id) || 0) + 1);
    }
    const nodeMap = new Map(nodes.map((n) => [n.id, n]));
    const scored = unreviewed.map((item) => {
      const targetId = itemTarget(item);
      const targetNode = nodeMap.get(targetId);
      const degree = degreeMap.get(targetId) || 0;
      return { item, targetNode, targetId, degree };
    });
    scored.sort((a, b) => b.degree - a.degree);
    return scored.slice(0, 5);
  }, [candidates, conflicts, edges, nodes, overview?.hot_unreviewed]);

  const recentChanges = useMemo(() => {
    const list = [];
    const seen = new Set();
    const nodeMap = new Map(nodes.map((n) => [n.id, n]));
    if (Array.isArray(auditTrail)) {
      for (const entry of auditTrail) {
        const id = entry.targetId || entry.reviewId || entry.id;
        if (id && !seen.has(id)) {
          seen.add(id);
          const targetNode = nodeMap.get(entry.targetId);
          list.push({
            id,
            targetId: entry.targetId,
            name: targetNode ? targetNode.name : entry.targetId || "Item",
            type: targetNode?.type || "OBJECT",
            action: entry.action || "reviewed",
            actor: entry.actor || "User",
          });
        }
      }
    }
    if (list.length < 5 && Array.isArray(snapshot?.overrides)) {
      for (const ov of snapshot.overrides) {
        const id = ov.target_id || ov.id;
        if (id && !seen.has(id)) {
          seen.add(id);
          const targetNode = nodeMap.get(ov.target_id);
          list.push({
            id,
            targetId: ov.target_id,
            name: targetNode ? targetNode.name : ov.target_id || "Item",
            type: targetNode?.type || "OBJECT",
            action: ov.status || "override",
            actor: "Reviewer",
          });
        }
      }
    }
    return list.slice(0, 5);
  }, [auditTrail, snapshot?.overrides, nodes]);

  const validationWidget = (
    <Card className="overview-widget" role="region" aria-label="Validation summary">
      <div className="widget-head">
        <div className="widget-title">
          <ValidationIcon className={`status-icon tone-${validationTone}`} aria-hidden="true" />
          <h3>Validation summary</h3>
        </div>
        <span className={`status-badge-inline tone-${validationTone}`}>{validationLabel}</span>
      </div>
      <p className="widget-description">
        {validationState === "not_run" ? "Scan sources to check graph validity." : validationState === "invalid" ? "Sources were extracted, but graph issues need attention." : "Graph validity is checked separately from source extraction and review decisions."}
      </p>
      {issues.length ? (
        <div className="widget-issues-list">
          {issues.slice(0, 3).map((item, index) => (
            <div key={`${item.code}-${index}`} className="widget-issue-item">
              <span className={`severity severity-${String(item.severity).toLowerCase()}`}>{item.severity}</span>
              <span className="widget-issue-text" title={item.message}>{item.message}</span>
              {item.object_id || item.from_id || item.to_id ? (
                <Button variant="ghost" size="sm" onClick={() => onSelect(item.object_id || item.from_id || item.to_id, "inspector")}>
                  Inspect
                </Button>
              ) : null}
            </div>
          ))}
          {issues.length > 3 ? (
            <Disclosure title={`View ${formatCount(issueTotal - 3)} more issues`} className="validation-issues">
              <ul>
                {issues.slice(3).map((item, index) => (
                  <li key={`${item.code}-${index}`}>
                    <span className={`severity severity-${String(item.severity).toLowerCase()}`}>{item.severity}</span>
                    <span className="issue-message">{item.message}</span>
                    {item.object_id || item.from_id || item.to_id ? (
                      <Button variant="link" size="sm" onClick={() => onSelect(item.object_id || item.from_id || item.to_id, "inspector")}>
                        Inspect affected object
                      </Button>
                    ) : null}
                  </li>
                ))}
              </ul>
              {issueTotal > issues.length ? <p className="footnote">The first {formatCount(issues.length)} of {formatCount(issueTotal)} issues are listed.</p> : null}
            </Disclosure>
          ) : null}
        </div>
      ) : validationState === "not_run" ? null : (
        <p className="widget-empty muted">No schema or dependency issues detected.</p>
      )}
      {validationState === "not_run" && onScan ? (
        <div className="widget-foot">
          <Button variant="ghost" size="sm" onClick={onScan} disabled={scanning} tooltip={!hasSources ? "Add sources before running validation" : undefined}>
            <ShieldCheck />Run validation
          </Button>
        </div>
      ) : null}
    </Card>
  );

  const sourcesRow = <div className="status-row tone-idle">
    <Database className="status-icon" aria-hidden="true" />
    <div className="status-copy">
      <h2>{scanning ? "Scanning sources…" : hasObjects ? "Sources indexed" : "Sources"}</h2>
      <p className="scan-meta">{sourceCount === undefined ? "Source settings unavailable" : `${sourceCount} ${sourceCount === 1 ? "source" : "sources"}`}{hasObjects ? ` · ${lastScan ? `Last scan ${formatDate(lastScan)}` : "Last scan time unavailable"}` : ""}</p>
    </div>
    <div className="status-actions" data-ui-actions="">
      {(!lastScan || !hasObjects) && onScan ? (
        <Button variant="ghost" size="sm" onClick={onScan} disabled={scanning || !hasSources} tooltip={!hasSources ? "Add sources before scanning" : undefined}>
          <ScanLine />Scan now
        </Button>
      ) : null}
      <Button variant="ghost" size="sm" onClick={onSources}>Manage sources</Button>
    </div>
  </div>;

  const notCheckedRow = notChecked.length ? <div className="status-row tone-warn" role="status">
    <TriangleAlert className="status-icon" aria-hidden="true" />
    <div className="status-copy">
      <h2>{notChecked.length} {notChecked.length === 1 ? "item" : "items"} not checked</h2>
      <ul className="not-checked-list">{notChecked.map((item) => { const note = originNote(item); return <li key={item.id}><Button variant="link" size="sm" onClick={() => onSelect(item.id, "inspector")}>{item.name}</Button> <span className="muted">{note?.title || "Not checked"}</span></li>; })}</ul>
    </div>
  </div> : null;

  const PRIMARY = ["MODEL", "TABLE", "COLUMN", "MEASURE", "REPORT", "PAGE", "VISUAL"];
  const typeCounts = Object.entries(overview.object_counts || {}).filter(([, count]) => count > 0).sort(([a], [b]) => { const ia = PRIMARY.indexOf(a), ib = PRIMARY.indexOf(b); return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib) || a.localeCompare(b); });

  const otherTypes = typeCounts.filter(([type]) => !PRIMARY.includes(type)).length;

  return <div className="page page-overview" data-ui-stack="">
    <header className={`overview-hero ${hasObjects && !loading ? "is-quiet" : ""}`}>
      <div className="overview-hero-copy">
        <h1 className={hasObjects && !loading ? "sr-only" : undefined} tabIndex={-1}>Overview</h1>
        {loading ? (
          <p className="hero-meta muted">{scanning ? "Scanning project…" : "Loading project…"}</p>
        ) : hasObjects ? (
          <p className="hero-meta muted sr-only">{lastScan ? `Last scan ${formatDate(lastScan)}` : "Project indexed"}</p>
        ) : (
          <p className="hero-meta">Connect your Power BI sources to build the project brain.</p>
        )}
      </div>
    </header>
    {hasObjects && typeCounts.length ? <nav className="type-strip" aria-label="Objects by type">
      {typeCounts.filter(([type]) => allTypes || PRIMARY.includes(type)).map(([type, count]) => <Tooltip key={type} content={`Browse ${formatCount(count)} ${pluralType(type, count).toLowerCase()}`}><button type="button" className="type-strip-item" onClick={() => onBrowseType(type)}><TypeGlyph type={type} colors={colors} size="sm" /><span className="type-strip-count" data-ui-number="">{formatCount(count)}</span><span className="type-strip-label">{pluralType(type, count)}</span></button></Tooltip>)}
      {otherTypes ? <button type="button" className="type-strip-item type-strip-more" aria-expanded={allTypes} onClick={() => setAllTypes((open) => !open)}>{allTypes ? "Fewer" : `+${otherTypes} more`}</button> : null}
    </nav> : null}
    {loading && !hasObjects ? <div className="overview-loading"><Skeleton className="skeleton-search" /><Skeleton className="skeleton-panel" /><p role="status" className="sr-only">{scanning ? "Scanning sources…" : "Loading project…"}</p></div> : !hasObjects ?
      <div className="overview-grid">
        <Card className="project-start" role="region" aria-labelledby="project-start-title">
          <h2 id="project-start-title">{hasSources ? "Ready for the first scan" : "Add your project sources"}</h2>
          <p>{hasSources ? "Scan your files to find models, reports, and their dependencies." : "Choose your PBIP project or exported model and report files."}</p>
          <Button
            size="lg"
            onClick={hasSources ? onScan : onSources}
            disabled={!config || scanning}
            tooltip={!config ? "Project settings unavailable. Connect to the PBIBrain service first." : scanning ? "Scan in progress" : undefined}
          >
            {hasSources ? <ScanLine /> : <Plus />}
            {hasSources ? scanLabel : "Add sources"}
          </Button>
          {!hasSources && onSample && config ? <Button variant="outline" size="lg" className="project-start-sample" onClick={onSample} disabled={scanning}><Boxes />Open sample project</Button> : null}
        </Card>
        <Card className="status-panel" role="region" aria-label="Project status">{sourcesRow}{notCheckedRow}</Card>
      </div> : <>
        <Card className="status-panel" role="region" aria-label="Project status">
          <div className={`status-row ${pending ? "tone-brand" : "tone-ok"}`}>
            {pending ? <span className="status-icon status-icon-count" aria-hidden="true"><Inbox /></span> : <CircleCheck className="status-icon" aria-hidden="true" />}
            <div className="status-copy">
              <h2>{validationState === "invalid" ? "Resolve graph issues before review" : pending ? "Ready for review" : "No pending reviews"}</h2>
              <p>{pending ? <><span className="sr-only">{pending} {pending === 1 ? "open item" : "open items"}. </span><span className="review-card-split"><span data-ui-number="">{formatCount(counts.candidates)} {counts.candidates === 1 ? "suggestion" : "suggestions"}</span>{counts.warnings ? <span data-ui-number="">{formatCount(counts.warnings)} conflicts</span> : null}{counts.stale ? <span data-ui-number="">{formatCount(counts.stale)} outdated decisions</span> : null}</span></> : "All suggestions have been reviewed."}</p>
            </div>
            <div className="status-actions"><Button variant={pending ? "default" : "outline"} size="sm" onClick={onReview}>Open review queue <ArrowRight aria-hidden="true" /></Button></div>
          </div>
          {sourcesRow}
          {notCheckedRow}
        </Card>

        <div className="overview-widgets-grid">
          {validationWidget}

          <Card className="overview-widget" role="region" aria-label="Most-used measures">
            <div className="widget-head">
              <div className="widget-title">
                <Calculator className="status-icon" aria-hidden="true" />
                <h3>Most-used measures</h3>
              </div>
              {mostUsedMeasures.length ? <span className="widget-badge muted">Top {mostUsedMeasures.length}</span> : null}
            </div>
            {mostUsedMeasures.length ? (
              <ul className="widget-list">
                {mostUsedMeasures.map(({ node, count }) => (
                  <li key={node.id} className="widget-list-row">
                    <div className="widget-list-name">
                      <TypeGlyph type="MEASURE" colors={colors} size="xs" />
                      <Button variant="link" size="sm" className="widget-link" onClick={() => onSelect(node.id, "inspector")} tooltip={node.name}>
                        {node.name}
                      </Button>
                      {node.scope ? <span className="widget-scope muted">{node.scope}</span> : null}
                    </div>
                    <span className="widget-metric" data-ui-number="">{formatCount(count)} {count === 1 ? "use" : "uses"}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="widget-empty muted">{overview?.measure_count === 0 ? "No measures in the scanned models." : "Not available until the project is scanned."}</p>
            )}
          </Card>

          <Card className="overview-widget" role="region" aria-label="Unreviewed on hot objects">
            <div className="widget-head">
              <div className="widget-title">
                <Flame className="status-icon tone-warn" aria-hidden="true" />
                <h3>Unreviewed on hot objects</h3>
              </div>
              {unreviewedOnHot.length ? <span className="widget-badge muted">Top {unreviewedOnHot.length}</span> : pending === 0 ? <span className="widget-badge muted">Clean</span> : null}
            </div>
            {unreviewedOnHot.length ? (
              <ul className="widget-list">
                {unreviewedOnHot.map(({ item, targetNode, targetId, degree }, idx) => (
                  <li key={item.id || `${targetId}-${idx}`} className="widget-list-row">
                    <div className="widget-list-name">
                      <TypeGlyph type={targetNode?.type || "OBJECT"} colors={colors} size="xs" />
                      <Button variant="link" size="sm" className="widget-link" onClick={() => onSelect(targetId, "inspector")} tooltip={targetNode ? targetNode.name : targetId}>
                        {targetNode ? targetNode.name : targetId}
                      </Button>
                      {item.scope ? <span className="widget-scope muted">{item.scope}</span> : null}
                      {item.kind === "conflict" ? <span className="badge-tag">conflict</span> : null}
                    </div>
                    <div className="widget-row-actions">
                      <span className="widget-metric" data-ui-number="">{formatCount(degree)} links</span>
                      <Button variant="ghost" size="sm" onClick={onReview}>Review</Button>
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="widget-empty muted">{pending === 0 ? "No pending suggestions or conflicts." : "Open the review queue to see them."}</p>
            )}
          </Card>

          {recentChanges.length ? <Card className="overview-widget" role="region" aria-label="Recently changed">
            <div className="widget-head">
              <div className="widget-title">
                <Clock className="status-icon" aria-hidden="true" />
                <h3>Recently changed</h3>
              </div>
              <span className="widget-badge muted">{recentChanges.length ? "Recent decisions" : "Idle"}</span>
            </div>
            {recentChanges.length ? (
              <ul className="widget-list">
                {recentChanges.map((entry) => (
                  <li key={entry.id} className="widget-list-row">
                    <div className="widget-list-name">
                      <TypeGlyph type={entry.type} colors={colors} size="xs" />
                      <Button variant="link" size="sm" className="widget-link" onClick={() => onSelect(entry.targetId, "inspector")} tooltip={entry.name}>
                        {entry.name}
                      </Button>
                      <span className={`badge-tag badge-status-${entry.action}`}>{entry.action}</span>
                    </div>
                    <span className="widget-metric muted">{entry.actor}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="widget-empty muted">No recent changes or review actions yet. Decisions will appear here as items are reviewed.</p>
            )}
          </Card> : null}
        </div>

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
  const [unfolded, setUnfolded] = useState(() => new Set());
  const folded = useMemo(() => foldSearchResults(result?.items || [], searchObject), [result]);
  return <div ref={panel}>
    <PageHeading quiet title={browse ? "Browse objects" : "Search"} />
    <Card className="panel search-panel" aria-busy={loading}>
      <div className="search-toolbar" data-ui-actions="">
        <Label htmlFor={inputId} className="sr-only">{browse ? "Filter by name or formula" : "Name or formula"}</Label>
        <div className="search-field"><NavIcon name="search" size={18} /><Input id={inputId} type="search" value={query} onChange={(event) => change({ query: event.target.value })} onKeyDown={(event) => { if (event.key === "Escape") { event.preventDefault(); if (query) change({ query: "" }); else event.target.blur(); } else if (event.key === "Enter") runSearch(); else if (event.key === "ArrowDown" && moveInList(panel.current?.querySelector(".search-results"), "first")) event.preventDefault(); }} placeholder={browse ? "Filter objects by name…" : "Measure, table, column, or visual…"} aria-label="Search objects" />{loading && active ? <RefreshCw className="search-spinner spin" aria-hidden="true" /> : null}</div>
        <div className="search-filters">
          <Label className="select-field"><span className="sr-only">Model</span><NativeSelect aria-label="Model" value={modelId} onChange={(event) => change({ modelId: event.target.value, reportId: "" })}><option value="">All models</option>{models.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</NativeSelect></Label>
          <Label className="select-field"><span className="sr-only">Report</span><NativeSelect aria-label="Report" value={reportId} onChange={(event) => change({ reportId: event.target.value, modelId: "" })}><option value="">All reports</option>{reports.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</NativeSelect></Label>
          <Label className="select-field"><span className="sr-only">Type</span><NativeSelect aria-label="Search object type" value={objectType} onChange={(event) => change({ objectType: event.target.value })}><option value="">All types</option>{Object.keys(overview.object_counts || {}).filter((type) => !new Set(["ALIAS", "BUSINESS_CONCEPT", "ROLE", "BEHAVIOR", "CONFLICT", "SELECTOR", "SELECTOR_OPTION", "SEMANTIC_ASSERTION"]).has(type)).sort().map((type) => <option key={type} value={type}>{typeLabel(type)}</option>)}</NativeSelect></Label>
          {modelId || reportId || objectType ? <Button variant="ghost" size="sm" className="clear-filters" onClick={() => change({ modelId: "", reportId: "", objectType: "" })}><X />Clear filters</Button> : null}
        </div>
        <div className="search-status" role="status" aria-live="polite">
          {active ? loading ? "Searching…" : result ? (
            (result.total === 0 || result.items.length === 0)
              ? (!query.trim() ? "No objects" : "No matches")
              : `${result.items.length} of ${formatCount(result.total)} ${!query.trim() ? (result.total === 1 ? "object" : "objects") : (result.total === 1 ? "match" : "matches")}`
          ) : "" : ""}
        </div>
      </div>
      {error ? <div className="search-error" role="alert"><TriangleAlert aria-hidden="true" /><span>{readableText(error.message)}</span><Button variant="outline" size="sm" onClick={() => runSearch(error.offset)}>Retry search</Button></div> : null}
      {!active ? <EmptyState icon={<NavIcon name="search" size={20} />} title="What are you looking for?" detail="Find a measure to inspect its formula and dependencies." action={<p className="empty-hint"><kbd>Ctrl</kbd><kbd>K</kbd> jumps here from anywhere</p>} /> : null}
      {active && !loading && !result?.items?.length && !error ? <EmptyState icon={<NavIcon name="search" size={20} />} title="No matches" detail="Try a shorter name or clear the filters." /> : null}
      {active && result?.items?.length ? <div className="search-results" onKeyDown={(event) => listKeys(event, () => panel.current?.querySelector(".search-field input")?.focus())}>{folded.map(({ item, copies }) => {
        const first = searchObject(item);
        const open = copies.length > 1 && unfolded.has(first.id);
        const shown = copies.length > 1 && !open ? [item] : copies;
        return shown.map((entry, index) => {
          const object = searchObject(entry);
          const color = artifactColor(object, colors);
          const snippet = browse && !query.trim() ? null : searchSnippet(entry, query);
          const lead = copies.length > 1 && index === 0;
          const where = lead && !open ? `${copies.length} ${first.report_id ? "reports" : "models"}` : scopeName(object) || readableText(object.description) || "";
          return <Button variant="ghost" key={object.id} data-result-id={object.id} className={`search-result ${copies.length > 1 && index ? "is-copy" : ""}`} style={{ "--artifact-color": color }} onClick={() => { onSession((current) => ({ ...current, selectedId: object.id, scrollY: contentScroller().scrollTop })); onSelect(object.id, "inspector"); }}>
            <TypeGlyph node={object} colors={colors} size="sm" />
            <span className="result-type sr-only">{typeLabel(object.type)}</span>
            <span className="result-copy"><strong><Marked text={labelFor(object)} query={query.trim()} /></strong>{where ? <small>{where}</small> : null}{snippet ? <code className={`result-snippet ${snippet.formula ? "is-formula" : ""}`}>{snippet.parts[0]}<mark>{snippet.parts[1]}</mark>{snippet.parts[2]}</code> : null}</span>
            {lead ? <span role="button" tabIndex={-1} className="result-fold" aria-label={open ? "Show one row" : `Show all ${copies.length}`} title={open ? "Show one row" : `Show all ${copies.length}`} onClick={(event) => { event.stopPropagation(); setUnfolded((current) => { const next = new Set(current); if (next.has(first.id)) next.delete(first.id); else next.add(first.id); return next; }); }}>×{copies.length}<ChevronDown className={open ? "is-open" : ""} aria-hidden="true" /></span> : <span />}
            <ChevronRight className="result-chevron" aria-hidden="true" />
          </Button>;
        });
      })}</div> : null}
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

function Inspector({ node, details, loading, error, snapshot, snapshotLoaded, snapshotError, overview, onSelect, onRetry, onEvidenceRetry, onReview, onGraph, colors, scanning, transport }) {
  const [activeEditId, setActiveEditId] = useState(null);
  if (error) return <Card className="panel inspector-state"><div className="empty-state tone-bad"><span className="empty-icon" aria-hidden="true"><TriangleAlert /></span><h2>Object unavailable</h2><p>{readableText(error)}</p><Button variant="outline" onClick={onRetry}><RefreshCw />Retry object</Button></div></Card>;
  if (loading) return <div className="inspector-loading"><Skeleton className="skeleton-title" /><div className="skeleton-grid"><Skeleton className="skeleton-block" /><Skeleton className="skeleton-block" /></div><p role="status" className="loading-label">Loading object details…</p></div>;
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
    <PageHeading title={labelFor(node)} description={scopeTrail.join(" · ")} action={<span className="object-actions"><CopyLinkButton /><Button variant="outline" onClick={onGraph}><Waypoints />Show in graph</Button></span>}>
      <div className="object-summary-state" style={{ "--artifact-color": color }}><span className="type-chip" style={artifactStyle(node, colors)}><TypeIcon type={node.type} />{typeLabel(node.type)}</span><StatusBadge value={node.status} /></div>
    </PageHeading>
    <div className="object-workspace">
      <div className="object-main">
        <Card className="panel object-summary">
          <h2 className="panel-title">Definition</h2>
          {node.description ? <p className="description-copy">{formatValue(node.description)}</p> : (!fields.length && !expression ? <p className="muted-copy">No description recorded.</p> : null)}
          {fields.length ? <dl className="metadata-grid">{fields.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl> : null}
        </Card>
        {expression ? <ExpressionBlock expression={formatValue(expression)} /> : null}
        <ObjectContents groups={details?.contents} colors={colors} onSelect={(id) => onSelect(id, "inspector")} />
        <UsageRoles profile={details?.usage_roles} />
        {candidates.length || warnings.length ? <Disclosure title="Review & evidence" badge={`${formatPlural(candidates.length, "suggestion")}${warnings.length ? ` · ${formatPlural(warnings.length, "warning")}` : ""}`} className="object-metadata object-review panel" defaultOpen>{candidates.map((item) => { const itemId = item.id || item.target || itemTarget(item); return <div className="object-review-item" key={itemId}><CandidateActions item={item} node={node} onReview={onReview} disabled={scanning} isEditing={activeEditId === itemId} onStartEdit={() => setActiveEditId(itemId)} onCancelEdit={() => setActiveEditId(null)} /><EvidenceCard item={item} /></div>; })}{warnings.map((warning) => <div className="warning-card" key={warning.id || formatEvidence(warning.reason)}><strong><TriangleAlert aria-hidden="true" />Conflict</strong><p>{formatEvidence(warning.reason || warning.message || warning.description || "Conflicting evidence needs review.")}</p></div>)}</Disclosure> : null}
        {snapshotError ? <div className="inline-error" role="alert"><p>{snapshotLoaded ? "Review evidence could not be refreshed. Showing last loaded evidence." : "Review evidence unavailable."} {readableText(snapshotError)}</p><Button variant="outline" size="sm" onClick={onEvidenceRetry}>Retry evidence</Button></div> : !snapshotLoaded ? <p className="muted-copy object-review" role="status">Loading review evidence…</p> : null}
        {connected.some((edge) => !usageTypes.has(edge.type) && edge.type !== "OBSERVED_WITH") ? <Disclosure title="Other relationships" className="object-metadata object-other panel"><RelationshipGroup title="Connected objects" nodeId={node.id} edges={connected.filter((edge) => !usageTypes.has(edge.type) && edge.type !== "OBSERVED_WITH")} nodes={relatedNodes} onSelect={onSelect} empty="No other relationships." colors={colors} /></Disclosure> : null}
        {observations.length ? <Disclosure title="Observed report usage" badge={observations.length} className="object-metadata object-observed panel">{observations.map((edge) => <div className="usage-row" key={edge.id}><span>{scopeName(edge.from_id === node.id ? edge.to_id : edge.from_id)}</span><strong>{formatValue(edge.properties?.count || edge.count || "observed")}</strong></div>)}<p className="footnote">Co-occurrence does not establish compatibility.</p></Disclosure> : null}
      </div>
      <Card className="panel object-lineage">
        <h2 className="panel-title">Lineage &amp; usage</h2>
        <VisualBindings bindings={details?.visual_bindings} wells={details?.field_wells} onSelect={(item) => onSelect(item.id, "inspector")} />
        <RelationshipGroup title="Used by" nodeId={node.id} edges={incoming.filter((edge) => usageTypes.has(edge.type))} nodes={relatedNodes} onSelect={onSelect} empty="No direct uses recorded." colors={colors} />
        {(() => {
          // A visual's fields and filters are already listed above by where they sit; Dependencies holds only the rest.
          const listed = new Set([...Object.values(details?.visual_bindings || {}).flat(), ...(details?.field_wells || []).flatMap((well) => well.fields || [])].map((item) => item?.id).filter(Boolean));
          const dependencies = outgoing.filter((edge) => usageTypes.has(edge.type) && !listed.has(edge.to_id));
          return listed.size && !dependencies.length ? null : <RelationshipGroup title={listed.size ? "Other dependencies" : "Dependencies"} nodeId={node.id} edges={dependencies} nodes={relatedNodes} onSelect={onSelect} empty="No direct dependencies recorded." colors={colors} />;
        })()}
        <p className="footnote">Direct links from the latest scan.</p>
        <Suspense fallback={null}><ImpactExplorer node={node} nodes={relatedNodes} onSelect={onSelect} transport={transport} /></Suspense>
      </Card>
    </div>
  </>;
}

/** How the object is used in reports: INFERRED summary of the USES roles (issue #11). */
function UsageRoles({ profile }) {
  const facts = profile?.facts || [];
  if (!facts.length) return null;
  return <Disclosure title="How it is used" badge={facts.length} className="object-metadata object-usage-roles panel" defaultOpen>
    {facts.map((fact) => <div className="usage-row" key={`${fact.code}-${fact.text}`}><span>{fact.text}</span></div>)}
    <p className="footnote">{readableText(profile.basis)}</p>
  </Disclosure>;
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

function RelationshipGroup({ title, nodeId, edges, nodes, onSelect, empty, colors }) {
  const [expanded, setExpanded] = useState(false);
  const unique = [...new Map(edges.map((edge) => [edge.from_id === nodeId ? edge.to_id : edge.from_id, edge])).values()];
  const shown = expanded ? unique : unique.slice(0, 10);
  return <section className="relationship-group" aria-label={title}><h3 className="relationship-title">{title}<span className="count-pill">{unique.length}</span></h3>{unique.length ? <div className="relationship-list" onKeyDown={(event) => listKeys(event)}>{shown.map((edge) => { const targetId = edge.from_id === nodeId ? edge.to_id : edge.from_id; const resolved = nodes.find((node) => node.id === targetId); return <Button variant="ghost" className="relationship-row" key={targetId} onClick={() => onSelect(targetId, "inspector")}><TypeGlyph node={resolved} type={resolved?.type || edge.type} colors={colors} size="xs" /><span className="relationship-copy"><strong>{resolved ? labelFor(resolved) : "Related object"}</strong><small>{typeLabel(resolved?.type || edge.type)}</small></span><ChevronRight className="row-chevron" aria-hidden="true" /></Button>; })}</div> : <p className="muted-copy compact">{empty}</p>}{unique.length > 10 ? <Button variant="link" size="sm" className="relationship-more" onClick={() => setExpanded((current) => !current)}>{expanded ? "Show fewer" : `Show all ${unique.length}`}</Button> : null}</section>;
}

/** Copies the address of the current place; the hash route opens the same object for a colleague on the same project. */
function CopyLinkButton() {
  const toast = useToast();
  const copy = async () => {
    try { await navigator.clipboard.writeText(globalThis.location.href); toast.show({ tone: "ok", text: "Link copied" }); }
    catch { toast.show({ tone: "warn", text: "The link could not be copied" }); }
  };
  return <Button variant="ghost" size="icon" className="copy-link" aria-label="Copy link to this object" title="Copy link to this object" onClick={copy}><Link2 /></Button>;
}

function CandidateActions({ item, node, onReview, disabled = false, isEditing = false, onStartEdit, onCancelEdit }) {
  const [exiting, setExiting] = useState(false);
  const decide = async (action, candidateItem, valueOverride) => {
    const isReduced = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    setExiting(true);
    if (!isReduced) {
      await new Promise((resolve) => setTimeout(resolve, 180));
    }
    try {
      const ok = await onReview(action, candidateItem, valueOverride);
      if (!ok) setExiting(false);
      return ok;
    } catch (err) {
      setExiting(false);
      throw err;
    }
  };
  const score = confidence(item.confidence ?? item.properties?.confidence);
  return (
    <fieldset className={`candidate-actions ${exiting ? "is-exiting" : ""}`} data-ui-actions="" disabled={disabled || exiting}>
      <div className="candidate-action-title">
        <span>{suggestionLabel(item)}</span>
        <Tooltip content={explainConfidence(item, node)}>
          <span className="count-pill" tabIndex={0} role="group" aria-label={`Confidence ${score}%`}>
            {score === null ? "" : `${score}%`}
          </span>
        </Tooltip>
      </div>
      <ReviewDecision
        item={item}
        onReview={onReview}
        onDecide={decide}
        disabled={disabled || exiting}
        isEditing={isEditing}
        onStartEdit={onStartEdit}
        onCancelEdit={onCancelEdit}
        compact={false}
      />
    </fieldset>
  );
}

function EvidenceCard({ item }) {
  return <div className="evidence-card"><p>{readableText(item.evidence?.length ? item.evidence : item.reason) || "No explanation recorded."}</p></div>;
}

export default function App(props) {
  return (
    <ToastProvider>
      <AppInner {...props} />
    </ToastProvider>
  );
}

export { isBackendUnreachableError, Overview };
