import PendingChanges from "./components/PendingChanges";
import React, { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft, PanelLeft, ScanSearch, Bot, FolderOpen, RefreshCw, ScanLine, TriangleAlert } from "lucide-react";
import { ToastProvider, useToast } from "./components/ui/toast";
import { brainTransport, normalizeSnapshot } from "./transport";
import { desktopRequest, subscribeToDesktopBridge } from "./desktop";
import NavIcon from "./NavIcon";
import { PRODUCT_CREDIT, PRODUCT_NAME } from "./brand";
import { parseRoute, routeHash } from "./routes";
import { compactCount, formatCount, objectName, readableText, suggestionLabel, isBackendUnreachableError } from "./presentation";
import { Button } from "./components/ui/button";
import { Card } from "./components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "./components/ui/tabs";
import { Breadcrumb, BreadcrumbList, BreadcrumbItem, BreadcrumbLink, BreadcrumbPage, BreadcrumbSeparator } from "./components/ui/breadcrumb";
import { shared as devCenterShared } from "./devcenter/sharedStore.js";
import { slashGoesToSearch } from "./devcenter/preferences.js";
import { normalizeColors } from "./graphPresentation";
import { AppMenuBar, ShortcutsDialog, StatusBar } from "./components/AppShell";
import { commandFor, displayKeys, shortcutKeys } from "./shortcuts";
import CommandPalette from "./components/CommandPalette";
import InspectorEmpty from "./components/InspectorEmpty";
import ExportDialog from "./components/ExportDialog";
import { DesktopConnecting, DesktopOnboarding, useRecentProjects } from "./views/DesktopStart";
import { Inspector } from "./views/Inspector";
import { Overview } from "./views/Overview";
import { SearchView } from "./views/SearchView";
import { ConfigView, DesktopProjectView, KeyboardSettings } from "./views/Settings";
import { EmptyState, PageHeading, dataCounts, formatDate, itemTarget, labelFor, numberOr } from "./views/shared";
const GraphView = lazy(() => import("./components/GraphView"));
const GraphColors = lazy(() => import("./components/GraphColors"));
const ModelSummary = lazy(() => import("./components/ModelSummary"));
const DocumentationExport = lazy(() => import("./components/DocumentationExport"));
const ChatPanel = lazy(() => import("./components/ChatPanel"));
const AISettings = lazy(() => import("./components/AISettings"));
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

  const [recentProjects, reloadRecent] = useRecentProjects(desktopApi, desktopSession?.project?.folder);
  const switchDesktopProject = useCallback(async (entry) => {
    if (scanInFlight.current) { setDesktopError("Wait for the project scan to finish before changing projects."); return; }
    invalidateProjectRequests();
    try { await openDesktopProject(entry.name, entry.folder); }
    catch (cause) { setDesktopError(cause.message || "Project could not be opened"); }
  }, [invalidateProjectRequests, openDesktopProject]);

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
      // A view that already put focus somewhere inside it (a restored row or result) keeps it.
      const main = document.querySelector("#main-content");
      const active = document.activeElement;
      if (main && active && active !== main && main.contains(active)) return;
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
    return <DesktopOnboarding api={desktopApi} error={desktopError} onOpen={openDesktopProject} recent={recentProjects} />;
  }

  const activeProject = desktopSession?.project;
  const projectName = activeProject?.name || config?.name || PRODUCT_NAME;
  const otherRecent = recentProjects.filter((entry) => entry.folder !== activeProject?.folder);
  const projectMenu = activeProject ? [
    ...(otherRecent.length ? [{ label: "Recent projects", items: otherRecent.map((entry) => ({ label: entry.name, onSelect: () => switchDesktopProject(entry), disabled: scanning })) }] : []),
    { items: [{ label: "Open another project…", icon: FolderOpen, onSelect: closeDesktopProject, disabled: scanning }] },
  ] : null;
  const pending = counts.review;
  const connection = loading ? "loading" : error ? "error" : "ready";
  const reloadBrain = () => {
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
      <AppMenuBar menus={menus} projectName={projectName} projectMenu={projectMenu} onProjectMenu={reloadRecent}>
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

function ViewLoading() {
  return <div className="view-loading" role="status"><RefreshCw className="spin" aria-hidden="true" />Loading view…</div>;
}

export default function App(props) {
  return (
    <ToastProvider>
      <AppInner {...props} />
    </ToastProvider>
  );
}

export { isBackendUnreachableError, Overview };
