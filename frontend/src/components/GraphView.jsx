import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Background, BaseEdge, Handle, MarkerType, MiniMap, Panel, Position, ReactFlow } from "@xyflow/react";
import { ChevronDown, ChevronRight, Crosshair, FilterX, LocateFixed, Maximize2, Minus, Plus, RefreshCw, Search, SlidersHorizontal, TriangleAlert } from "lucide-react";
import "@xyflow/react/dist/style.css";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Card } from "./ui/card";
import { Checkbox } from "./ui/checkbox";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { NativeSelect } from "./ui/native-select";
import { Tabs, TabsList, TabsTrigger } from "./ui/tabs";
import GraphDetails from "./GraphDetails";
import { ARTIFACT_GROUPS, EDGE_TYPES, OBJECT_TYPES, artifactColor, artifactGroup, typeLabel } from "../graphPresentation";
import { buildExplorerGraph, layoutExplorerGraph, layoutArtifactGraph, layoutGraph, routePath, NODE_WIDTH, NODE_HEIGHT } from "../graphLayout";

const EMPTY_FILTERS = { modelId: "", reportId: "", query: "", artifact: "", objectType: "", status: "factual", edgeType: "" };
import { objectName, scopeChoices, statusLabel, visualType } from "../presentation";
const scopeOptions = scopeChoices;
const DEFAULT_LIMIT = 80;

function defaultDirection() {
  return globalThis.matchMedia?.("(max-width: 760px)").matches ? "TB" : "LR";
}

export function createGraphSession(selectedId = "") {
  const centerId = selectedId || "";
  return {
    revision: 0,
    filters: { ...EMPTY_FILTERS, status: centerId ? "" : "factual" },
    query: "",
    centerId,
    depth: 1,
    limit: DEFAULT_LIMIT,
    result: null,
    grouped: false,
    viewMode: "overview",
    expandedIds: null,
    viewports: {},
    placements: {},
    showLabels: false,
    direction: defaultDirection(),
    // Tracks the App selection consumed by the graph.  A manual graph reset
    // can clear centerId without being immediately re-centered on remount.
    selectionId: centerId,
  };
}

function normalizeGraphSession(value, selectedId) {
  const defaults = createGraphSession(selectedId);
  const incoming = value && typeof value === "object" ? value : {};
  const centerId = typeof incoming.centerId === "string" ? incoming.centerId : defaults.centerId;
  const selectionId = typeof incoming.selectionId === "string"
    ? incoming.selectionId
    : typeof incoming.centerId === "string" ? incoming.centerId : "";
  const filters = incoming.filters && typeof incoming.filters === "object"
    ? { ...defaults.filters, ...incoming.filters }
    : { ...defaults.filters };
  return {
    ...defaults,
    ...incoming,
    filters,
    query: typeof incoming.query === "string" ? incoming.query : defaults.query,
    centerId,
    depth: typeof incoming.depth === "number" ? incoming.depth : defaults.depth,
    limit: typeof incoming.limit === "number" ? incoming.limit : defaults.limit,
    revision: typeof incoming.revision === "number" ? incoming.revision : defaults.revision,
    result: incoming.result || null,
    grouped: typeof incoming.grouped === "boolean" ? incoming.grouped : defaults.grouped,
    viewMode: incoming.viewMode === "full" ? "full" : "overview",
    expandedIds: Array.isArray(incoming.expandedIds) ? incoming.expandedIds.filter((id) => typeof id === "string") : null,
    viewports: incoming.viewports && typeof incoming.viewports === "object" ? incoming.viewports : {},
    placements: incoming.placements && typeof incoming.placements === "object" ? incoming.placements : {},
    showLabels: typeof incoming.showLabels === "boolean" ? incoming.showLabels : defaults.showLabels,
    direction: incoming.direction === "TB" || incoming.direction === "LR" ? incoming.direction : defaults.direction,
    selectionId,
  };
}

function graphRequestKey(session) {
  return JSON.stringify([session.revision || 0, session.filters, session.centerId, session.depth, session.limit]);
}

function SelectField({ label, value, onChange, children, disabled }) {
  return <Label className="graph-filter-field"><span>{label}</span><NativeSelect aria-label={label} value={value} onChange={(event) => onChange(event.target.value)} disabled={disabled}>{children}</NativeSelect></Label>;
}

export default function GraphView({ transport, overview, snapshot, selectedId, colors, onSelect, session = null, onSession }) {
  const [uncontrolledSession, setUncontrolledSession] = useState(() => createGraphSession(selectedId));
  const [graphError, setGraphError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [focusedNode, setFocusedNode] = useState(null);
  const request = useRef(0);
  const controlled = typeof onSession === "function";
  const rawSession = controlled ? session : uncontrolledSession;
  const normalizedSession = useMemo(() => normalizeGraphSession(rawSession, selectedId), [rawSession, selectedId]);
  const selectionChanged = Boolean(selectedId) && normalizedSession.selectionId !== selectedId;
  const selectionNeedsRecenter = selectionChanged && normalizedSession.centerId !== selectedId;
  const graphSession = useMemo(() => selectionNeedsRecenter
    ? {
        ...normalizedSession,
        centerId: selectedId,
        selectionId: selectedId,
        filters: { ...normalizedSession.filters, status: "" },
        result: null,
      }
    : normalizedSession, [normalizedSession, selectedId, selectionNeedsRecenter]);
  const { filters, query, centerId, depth, limit, grouped, showLabels, direction } = graphSession;
  const graphKey = graphRequestKey(graphSession);
  const requestedKey = useRef(graphKey);
  requestedKey.current = graphKey;
  const updateSession = useCallback((change) => {
    const apply = (current) => {
      const base = normalizeGraphSession(current, selectedId);
      return typeof change === "function" ? change(base) : { ...base, ...change };
    };
    if (controlled) onSession?.(apply);
    else setUncontrolledSession((current) => apply(current));
  }, [controlled, onSession, selectedId]);
  // The parent owns the session in production.  Initialize it lazily so a
  // first visit can still preserve filters before the first graph response.
  useEffect(() => {
    if (controlled && session == null) {
      onSession?.((current) => current || createGraphSession(selectedId));
    }
  }, [controlled, onSession, selectedId, session]);
  useEffect(() => {
    if (!selectionChanged) return;
    updateSession((current) => {
      const next = normalizeGraphSession(current, selectedId);
      if (!selectedId || next.selectionId === selectedId) return next;
      if (next.centerId === selectedId) return { ...next, selectionId: selectedId };
      return {
        ...next,
        centerId: selectedId,
        selectionId: selectedId,
        filters: { ...next.filters, status: "" },
        result: null,
      };
    });
  }, [selectedId, selectionChanged, updateSession]);
  const updateFilters = (change) => { updateSession((current) => ({ ...current, filters: { ...current.filters, ...change } })); setFocusedNode(null); };
  useEffect(() => {
    const timer = setTimeout(() => updateSession((current) => current.filters.query === query.trim() ? current : { ...current, filters: { ...current.filters, query: query.trim() } }), 220);
    return () => clearTimeout(timer);
  }, [query, updateSession]);
  const loadGraph = useCallback(async () => {
    const requestId = ++request.current;
    setLoading(true); setGraphError(null);
    try {
      const data = await transport.getGraph({ ...filters, centerId, depth, limit });
      if (requestId === request.current && requestedKey.current === graphKey) {
        updateSession((current) => graphRequestKey(current) === graphKey ? { ...current, result: { key: graphKey, data } } : current);
      }
    } catch (error) {
      if (requestId === request.current && requestedKey.current === graphKey) {
        setGraphError({ key: graphKey, message: error.message || "Graph could not be loaded" });
        updateSession((current) => current.result?.key === graphKey ? { ...current, result: null } : current);
      }
    } finally {
      if (requestId === request.current && requestedKey.current === graphKey) setLoading(false);
    }
  }, [graphKey, transport, updateSession]);
  useEffect(() => { loadGraph(); return () => { request.current += 1; }; }, [loadGraph]);
  const graph = graphSession.result?.key === graphKey ? graphSession.result.data : null;
  const nodes = graph?.nodes || [];
  const edges = graph?.edges || [];
  const viewMode = centerId ? "connections" : graphSession.viewMode;
  const expandedIds = graphSession.expandedIds ?? nodes.filter((node) => node.type === "MODEL").map((node) => node.id);
  const explorer = useMemo(() => buildExplorerGraph(nodes, edges, expandedIds), [nodes, edges, graphSession.expandedIds]);
  const canvasNodes = viewMode === "overview" ? explorer.nodes : nodes;
  const canvasEdges = viewMode === "overview" ? explorer.edges.filter((edge) => filters.edgeType || edge.type === "CONTAINS" || edge.type === "USES_MODEL" || edge.from_id === focusedNode?.id || edge.to_id === focusedNode?.id) : edges;
  const canvasKey = JSON.stringify([graphKey, viewMode, direction, viewMode !== "overview" && grouped]);
  const saveViewport = useCallback((viewport) => updateSession((current) => {
    const previous = current.viewports?.[canvasKey];
    if (previous && previous.x === viewport.x && previous.y === viewport.y && previous.zoom === viewport.zoom) return current;
    // Keep recent scopes without accumulating every search entered in a session.
    const entries = Object.entries(current.viewports || {}).filter(([key]) => key !== canvasKey).slice(-11);
    return { ...current, viewports: { ...Object.fromEntries(entries), [canvasKey]: viewport } };
  }), [canvasKey, updateSession]);
  const savePlacements = useCallback((positions) => updateSession((current) => {
    const previous = current.placements?.[canvasKey];
    const entries = Object.entries(positions);
    if (previous && Object.keys(previous).length === entries.length && entries.every(([id, position]) => previous[id]?.x === position.x && previous[id]?.y === position.y)) return current;
    const recent = Object.entries(current.placements || {}).filter(([key]) => key !== canvasKey).slice(-11);
    return { ...current, placements: { ...Object.fromEntries(recent), [canvasKey]: positions } };
  }), [canvasKey, updateSession]);
  const toggleGroup = (id) => updateSession((current) => {
    const expanded = new Set(current.expandedIds ?? nodes.filter((node) => node.type === "MODEL").map((node) => node.id));
    if (expanded.has(id)) expanded.delete(id); else expanded.add(id);
    return { ...current, expandedIds: [...expanded] };
  });
  const error = graphError?.key === graphKey ? graphError.message : "";
  const objectTypes = [...new Set([...OBJECT_TYPES, ...Object.keys(overview?.object_counts || {})])].sort();
  const edgeTypes = [...new Set([...EDGE_TYPES, ...edges.map((edge) => edge.type)])].sort();
  const warningIds = useMemo(() => new Set((snapshot.conflicts || []).flatMap((item) => [item.target?.id || item.target || item.target_id || item.object_id, item.id, item.conflict_id].filter(Boolean))), [snapshot.conflicts]);
  const legendNodes = [...new Map(nodes.map((node) => [`${artifactGroup(node)}:${node.type}`, node])).values()].sort((a, b) => a.type.localeCompare(b.type));
  const hasFilters = Object.entries(filters).some(([key, value]) => value !== EMPTY_FILTERS[key]) || Boolean(query) || Boolean(centerId);
  const activeFilters = Object.entries(filters).filter(([key, value]) => value !== EMPTY_FILTERS[key]).length;
  const reset = () => { updateSession((current) => ({ ...current, filters: { ...EMPTY_FILTERS }, query: "", centerId: "", depth: 1, limit: DEFAULT_LIMIT, result: null, expandedIds: null })); setFocusedNode(null); };
  const center = (node) => { updateSession((current) => ({ ...current, filters: { ...EMPTY_FILTERS, status: node.status === "factual" ? "factual" : "" }, query: "", centerId: node.id })); setFocusedNode(node); };
  const changeView = (mode) => {
    if (mode === "connections") { if (focusedNode) center(focusedNode); return; }
    updateSession({ viewMode: mode, centerId: "" });
    setFocusedNode(null);
  };

  return <div className="graph-page">
    <Card className="graph-filter-card">
      <div className="graph-filter-top">
        <div className="graph-search"><Search aria-hidden="true" /><Input type="search" aria-label="Filter graph objects" value={query} onChange={(event) => { updateSession({ query: event.target.value }); setFocusedNode(null); }} placeholder="Find an object…" /></div>
        <Tabs value={filters.artifact || "all"} onValueChange={(value) => updateFilters({ artifact: value === "all" ? "" : value })}>
          <TabsList aria-label="Artifact groups"><TabsTrigger value="all">All objects</TabsTrigger>{Object.entries(ARTIFACT_GROUPS).map(([key, group]) => <TabsTrigger value={key} key={key}><span className="artifact-dot" style={{ backgroundColor: colors.groups[key] }} />{group.label.replace(" artifacts", "")}</TabsTrigger>)}</TabsList>
        </Tabs>
        <div className="graph-filter-actions">
          <Button variant="ghost" size="sm" disabled={!hasFilters} onClick={reset}><FilterX />Clear filters</Button>
          <Button variant="outline" size="sm" onClick={loadGraph} disabled={loading}><RefreshCw className={loading ? "spin" : ""} />Refresh</Button>
        </div>
      </div>
      <details className="graph-filter-details"><summary><SlidersHorizontal aria-hidden="true" />More filters{activeFilters ? <span className="count-pill">{activeFilters} active</span> : ""}</summary><div className="graph-filters">
        <SelectField label="Model" value={filters.modelId} onChange={(modelId) => { updateSession((current) => ({ ...current, centerId: "", filters: { ...current.filters, modelId, reportId: "" } })); setFocusedNode(null); }}><option value="">All models</option>{scopeOptions(overview, "model").map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</SelectField>
        <SelectField label="Report" value={filters.reportId} onChange={(reportId) => { updateSession((current) => ({ ...current, centerId: "", filters: { ...current.filters, reportId, modelId: "" } })); setFocusedNode(null); }}><option value="">All reports</option>{scopeOptions(overview, "report").map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</SelectField>
        <SelectField label="Object type" value={filters.objectType} onChange={(objectType) => updateFilters({ objectType })}><option value="">All types</option>{objectTypes.map((type) => <option key={type} value={type}>{typeLabel(type)}</option>)}</SelectField>
        <SelectField label="Status" value={filters.status} onChange={(status) => updateFilters({ status })}><option value="">All statuses</option>{["factual", "candidate", "approved", "rejected", "overridden"].map((status) => <option key={status} value={status}>{statusLabel(status)}</option>)}</SelectField>
        <SelectField label="Relationship" value={filters.edgeType} onChange={(edgeType) => updateFilters({ edgeType })}><option value="">All relationships</option>{edgeTypes.map((type) => <option key={type} value={type}>{typeLabel(type)}</option>)}</SelectField>
        <SelectField label="Distance" value={depth} disabled={!centerId} onChange={(value) => { updateSession({ depth: Number(value) }); setFocusedNode(null); }}>{[1, 2, 3, 4].map((value) => <option key={value} value={value}>{value} {value === 1 ? "connection away" : "connections away"}</option>)}</SelectField>
      </div>
      </details>
    </Card>
    <div className="graph-meta">
      <div className="graph-summary" role="status" aria-live="polite"><span>{loading ? "Loading graph…" : viewMode === "overview" ? `${canvasNodes.length} visible · ${explorer.hiddenCount} in collapsed groups · ${nodes.length} of ${graph?.total_nodes ?? 0} matching objects loaded` : `${nodes.length} of ${graph?.total_nodes ?? 0} matching objects · ${edges.length} relationships`}</span></div>
      {centerId ? <div className="graph-center"><Badge variant="default"><Crosshair />Focused view</Badge><span>{objectName(nodes.find((node) => node.id === centerId))}</span><Button variant="ghost" size="xs" onClick={() => { updateSession({ centerId: "" }); setFocusedNode(null); }}>Back to project</Button>{filters.objectType ? <small>The center stays visible for context.</small> : null}</div> : null}
      {graph?.truncated ? <div className="scope-notice">Showing {nodes.length} of {graph.total_nodes} objects. Filter by name or double-click an object to explore its connections{limit < 1000 ? <> or <Button variant="link" size="xs" onClick={() => updateSession({ limit: Math.min(limit * 2, 1000) })}>Show more</Button></> : "."}</div> : null}
    </div>
    <Card className="graph-canvas-card" aria-busy={loading}>
      <div className="graph-view-toolbar">
        <Tabs value={viewMode} onValueChange={changeView}><TabsList aria-label="Graph view"><TabsTrigger value="overview">Overview</TabsTrigger><TabsTrigger value="connections" disabled={!centerId && !focusedNode}>Connections</TabsTrigger><TabsTrigger value="full">Full graph</TabsTrigger></TabsList></Tabs>
        <p>{viewMode === "overview" ? "Expand a group. Select an object to see its connections." : viewMode === "connections" ? "Follow an object’s connections, one step at a time." : "All loaded objects and relationships."}</p>
        {viewMode === "overview" ? <Button variant="ghost" size="sm" disabled={graphSession.expandedIds == null} onClick={() => updateSession({ expandedIds: null })}>Collapse groups</Button> : centerId ? <Button variant="outline" size="sm" disabled={loading || depth >= 4} onClick={() => updateSession({ depth: Math.min(depth + 1, 4) })}><Plus />Expand connections</Button> : null}
      </div>
      <div className="graph-canvas-toolbar"><SelectField label="Layout" value={direction} onChange={(value) => updateSession({ direction: value })}><option value="LR">Left to right</option><option value="TB">Top to bottom</option></SelectField><span className="toolbar-divider" aria-hidden="true" /><Label className="graph-label-control"><Checkbox checked={showLabels} onCheckedChange={(checked) => updateSession({ showLabels: checked === true })} />Relationship labels</Label><Label className="graph-label-control"><Checkbox checked={filters.status !== "factual"} onCheckedChange={(checked) => updateFilters({ status: checked ? "" : "factual" })} />Include suggestions</Label>{viewMode !== "overview" ? <Label className="graph-label-control"><Checkbox checked={grouped} onCheckedChange={(checked) => updateSession({ grouped: checked === true })} />Group by ownership</Label> : null}<span className="graph-hint">Scroll to zoom · Drag to pan · Double-click to focus</span></div>
      {error ? <div className="graph-empty" role="alert"><span className="empty-icon tone-bad" aria-hidden="true"><TriangleAlert /></span><h3>Graph unavailable</h3><p>{error}</p><Button variant="outline" onClick={loadGraph}>Retry graph</Button></div> : !graph ? <div className="graph-empty graph-loading" role="status"><span className="graph-loader" aria-hidden="true"><i /><i /><i /></span><p>Loading graph…</p></div> : nodes.length ? <GraphCanvas key={canvasKey} overview={viewMode === "overview"} grouped={viewMode !== "overview" && grouped} onCenter={center} nodes={canvasNodes} edges={canvasEdges} selectedId={focusedNode?.id || centerId} detailsOpen={Boolean(focusedNode)} warningIds={warningIds} direction={direction} showLabels={showLabels} colors={colors} onSelect={setFocusedNode} onToggleGroup={toggleGroup} viewport={graphSession.viewports[canvasKey]} onViewportChange={saveViewport} placements={graphSession.placements[canvasKey]} onPlacementsChange={savePlacements} /> : <div className="graph-empty"><span className="empty-icon" aria-hidden="true"><Search /></span><h3>No matching objects</h3><p>{hasFilters ? "Try another filter or clear the filters." : "Scan project sources to see their relationships."}</p>{hasFilters ? <Button variant="outline" onClick={reset}>Clear filters</Button> : null}</div>}
      <div className="artifact-legend" aria-label="Graph color legend">{legendNodes.map((node) => <span key={`${artifactGroup(node)}:${node.type}`}><span className="artifact-dot" style={{ backgroundColor: artifactColor(node, colors) }} />{typeLabel(node.type)}{legendNodes.filter((item) => item.type === node.type).length > 1 ? ` · ${typeLabel(artifactGroup(node))}` : ""}</span>)}<span className="legend-spacer" aria-hidden="true" /><span className="legend-evidence"><i className="legend-line fact" />Fact</span><span className="legend-evidence"><i className="legend-line inferred" />Inferred</span><span className="legend-evidence"><i className="legend-line observed" />Observed</span></div>
    </Card>
    <GraphDetails node={focusedNode} colors={colors} transport={transport} onClose={() => setFocusedNode(null)} onSelect={setFocusedNode} onCenter={center} onInspect={(id) => { updateSession({ selectionId: id }); onSelect(id, "inspector"); }} />
  </div>;
}

function GraphCanvas({ overview, grouped, onCenter, nodes, edges, selectedId, detailsOpen, warningIds, direction, showLabels, colors, onSelect, onToggleGroup, viewport, onViewportChange, placements, onPlacementsChange }) {
  const [flow, setFlow] = useState(null);
  const [zoom, setZoom] = useState(viewport?.zoom || 1);
  const wrapper = useRef(null);
  const initialViewport = useRef(viewport);
  const previousPositions = useRef(new Map(Object.entries(placements || {})));
  const layout = useMemo(() => {
    if (!overview) return grouped ? layoutArtifactGraph(nodes, edges, direction) : { ...layoutGraph(nodes, edges, direction), groups: [] };
    const next = layoutExplorerGraph(nodes, edges, direction, previousPositions.current);
    previousPositions.current = new Map(next.nodes.map(({ node, position }) => [node.id, position]));
    return { ...next, groups: [] };
  }, [nodes, edges, direction, grouped, overview]);
  useEffect(() => {
    if (overview) onPlacementsChange(Object.fromEntries(previousPositions.current));
  }, [layout, overview, onPlacementsChange]);
  const duration = globalThis.matchMedia?.("(prefers-reduced-motion: reduce)").matches ? 0 : 180;
  // Keep a newly selected node clear of the floating details sheet.
  useEffect(() => {
    const placed = layout.nodes.find(({ node }) => node.id === selectedId);
    if (!detailsOpen || !flow || !placed || !wrapper.current || window.innerWidth <= 760) return undefined;
    // Wait out the double-click window so panning never moves a node mid-gesture.
    const timer = setTimeout(() => {
      if (!wrapper.current) return;
      const bounds = wrapper.current.getBoundingClientRect();
      const sheetLeft = window.innerWidth - 14 - Math.min(420, window.innerWidth - 28) - 16;
      const { x, y, zoom } = flow.getViewport();
      if ((placed.position.x + NODE_WIDTH) * zoom + x + bounds.left < sheetLeft) return;
      const visibleMiddle = (bounds.left + Math.min(bounds.right, sheetLeft)) / 2;
      flow.setViewport({ x: visibleMiddle - bounds.left - (placed.position.x + NODE_WIDTH / 2) * zoom, y, zoom }, { duration });
    }, 450);
    return () => clearTimeout(timer);
  }, [flow, layout, selectedId, detailsOpen, duration]);
  const connected = new Set([selectedId]);
  edges.forEach((edge) => {
    if (edge.from_id === selectedId || edge.to_id === selectedId) { connected.add(edge.from_id); connected.add(edge.to_id); }
  });
  const flowNodes = [
    ...layout.groups.map((group) => ({ id: group.id, type: "artifactGroup", position: group.position, width: group.width, height: group.height, measured: { width: group.width, height: group.height }, zIndex: -1, selectable: false, focusable: false, draggable: false, style: { width: group.width, height: group.height, pointerEvents: "none" }, data: { ...group, color: colors.groups[group.key] } })),
    ...layout.nodes.map(({ node, position }) => ({
      id: node.id, type: "brain", position, selected: node.id === selectedId,
      width: NODE_WIDTH, height: NODE_HEIGHT, ariaRole: "button", ariaLabel: `Select ${objectName(node)}`,
      // Cards have fixed dimensions. Preserve React Flow's measured/handle
      // state when controlled nodes are replaced after saving the session.
      measured: { width: NODE_WIDTH, height: NODE_HEIGHT },
      className: !overview && selectedId && !connected.has(node.id) ? "is-dimmed" : "",
      data: { node, direction, overview, onToggleGroup, warning: warningIds.has(node.id) || node.type === "CONFLICT", color: artifactColor(node, colors) },
    })),
  ];
  const flowEdges = layout.edges.map(({ edge, points }) => {
    const evidenceClass = String(edge.evidence_class || "FACT").toUpperCase();
    const highlighted = edge.from_id === selectedId || edge.to_id === selectedId;
    const warning = edge.type === "CONFLICTS_WITH" || warningIds.has(edge.from_id) || warningIds.has(edge.to_id);
    const source = nodes.find((node) => node.id === edge.from_id);
    const color = artifactColor(source, colors);
    return {
      id: edge.id, source: edge.from_id, target: edge.to_id, type: "routed",
      label: showLabels || highlighted || warning || overview && edge.type === "USES_MODEL" ? `${warning ? "Warning · " : ""}${typeLabel(edge.type)}` : undefined,
      ariaLabel: `${objectName(source)} ${typeLabel(edge.type)} ${objectName(nodes.find((node) => node.id === edge.to_id))}`,
      className: `flow-edge ${evidenceClass.toLowerCase()} ${warning ? "warning" : ""} ${highlighted ? "highlighted" : ""}`,
      markerEnd: { type: MarkerType.ArrowClosed, color, width: 16, height: 16 },
      style: { stroke: color, opacity: overview ? highlighted ? 1 : 0.7 : selectedId && !highlighted ? 0.1 : highlighted ? 1 : 0.55, strokeWidth: highlighted || warning ? 2.2 : 1.4, strokeDasharray: evidenceClass === "INFERRED" ? "6 4" : evidenceClass === "OBSERVED" ? "2 5" : undefined },
      labelStyle: { fill: "var(--text)", fontSize: 11, fontWeight: 500 }, labelBgStyle: { fill: "var(--surface-2)", fillOpacity: 0.98 }, labelBgPadding: [6, 3], labelBgBorderRadius: 4, data: { points },
    };
  });
  const fit = () => flow?.fitView({ padding: 0.16, minZoom: overview ? 0.8 : 0.08, maxZoom: 1, duration });
  return <div ref={wrapper} className={`flow-wrap artifact-flow ${overview ? "explorer-flow" : ""}`} role="region" aria-label="Directed project graph">
    <ReactFlow onInit={(instance) => { setFlow(instance); setZoom(instance.getZoom()); }} nodes={flowNodes} edges={flowEdges} nodeTypes={NODE_RENDERERS} edgeTypes={EDGE_RENDERERS}
      onNodeDoubleClick={(_, node) => { if (node.type === "brain") onCenter(node.data.node); }} onNodeClick={(_, node) => { if (node.type === "brain") onSelect(node.data.node); }} onPaneClick={() => onSelect(null)}
      onNodesChange={(changes) => { const selection = changes.find((change) => change.type === "select" && change.selected); if (selection) { const node = nodes.find((item) => item.id === selection.id); if (node) onSelect(node); } }}
      onMoveEnd={(_, nextViewport) => { setZoom(nextViewport.zoom); onViewportChange(nextViewport); }}
      defaultViewport={initialViewport.current} zoomOnDoubleClick={false} fitView={!initialViewport.current} fitViewOptions={{ padding: 0.16, minZoom: overview ? 0.8 : 0.08, maxZoom: 1 }} minZoom={0.08} maxZoom={2}
      nodesDraggable={false} nodesConnectable={false} edgesFocusable={false} proOptions={{ hideAttribution: true }}>
      <Panel position="top-left" className="graph-canvas-actions">{nodes.some((node) => node.id === selectedId) ? <><Button variant="outline" size="sm" className="canvas-button" onClick={() => flow?.fitView({ nodes: [{ id: selectedId }], padding: 0.6, minZoom: 0.8, maxZoom: 1, duration })}><LocateFixed />Focus selected</Button>{overview ? <Button variant="outline" size="sm" className="canvas-button" onClick={() => onCenter(nodes.find((node) => node.id === selectedId))}><Crosshair />Explore connections</Button> : null}</> : null}</Panel>
      <Background gap={22} size={1.2} color="var(--grid-dot)" />
      <Panel position="bottom-left" className="graph-zoom-controls"><Button variant="ghost" size="icon-sm" aria-label="Zoom in" onClick={() => flow?.zoomIn({ duration })}><Plus /></Button><span className="graph-zoom-value" aria-label={`Zoom ${Math.round(zoom * 100)} percent`}>{Math.round(zoom * 100)}%</span><Button variant="ghost" size="icon-sm" aria-label="Zoom out" onClick={() => flow?.zoomOut({ duration })}><Minus /></Button><span className="zoom-divider" aria-hidden="true" /><Button variant="ghost" size="icon-sm" aria-label="Fit view" title={overview ? "Fit visible groups at readable size" : "Fit view"} onClick={fit}><Maximize2 /></Button></Panel>
      <MiniMap pannable zoomable bgColor="var(--surface)" nodeColor={(node) => node.data?.color || "#94a3b8"} nodeStrokeColor={(node) => node.data?.color || "#94a3b8"} nodeBorderRadius={4} nodeClassName={(node) => node.type === "artifactGroup" ? "minimap-artifact-group" : ""} maskColor="var(--minimap-mask)" style={{ width: 176, height: 116 }} />
    </ReactFlow>
  </div>;
}

function ArtifactGroup({ data }) {
  return <div className="artifact-group" style={{ "--artifact-color": data.color }}><span className="artifact-group-title"><span className="artifact-dot" />{ARTIFACT_GROUPS[data.key].label}<span>{data.count}</span></span></div>;
}

function BrainFlowNode({ data, selected }) {
  const node = data.node;
  const flagged = node.status && node.status !== "factual" || data.warning;
  const isGroup = data.overview && node.explorerChildCount > 0;
  return <div className={`flow-node artifact-node ${isGroup ? "explorer-group-node" : ""} ${selected ? "selected" : ""} ${data.warning ? "has-warning" : ""}`} style={{ "--artifact-color": data.color }} title={objectName(node)}>
    <Handle type="target" position={data.direction === "TB" ? Position.Top : Position.Left} className="flow-handle" />
    <span className="flow-node-type"><span className="artifact-dot" />{node.type === "VISUAL" ? visualType(node) : typeLabel(node.type)}</span>
    <span className="flow-node-name">{objectName(node)}</span>
    {isGroup ? <button type="button" className="graph-group-toggle nodrag nopan" aria-label={`${node.explorerExpanded ? "Collapse" : "Expand"} ${objectName(node)}`} aria-expanded={node.explorerExpanded} title={`${node.explorerDescendantCount} loaded objects inside`} onMouseDown={(event) => event.stopPropagation()} onDoubleClick={(event) => event.stopPropagation()} onKeyDown={(event) => event.stopPropagation()} onClick={(event) => { event.stopPropagation(); data.onToggleGroup(node.id); }}>{node.explorerExpanded ? <ChevronDown /> : <ChevronRight />}<span>{node.explorerDescendantCount} inside</span></button> : null}
    {flagged ? <span className={`flow-node-status ${data.warning ? "warning" : ""}`}>{data.warning ? "Needs review" : statusLabel(node.status)}</span> : null}
    <Handle type="source" position={data.direction === "TB" ? Position.Bottom : Position.Right} className="flow-handle" />
  </div>;
}

function RoutedEdge({ id, data, markerEnd, style, label, labelStyle, labelBgStyle, labelBgPadding, labelBgBorderRadius }) {
  const middle = data.points[Math.floor(data.points.length / 2)];
  return <BaseEdge id={id} path={routePath(data.points)} markerEnd={markerEnd} style={style} label={label} labelX={middle.x} labelY={middle.y} labelStyle={labelStyle} labelBgStyle={labelBgStyle} labelBgPadding={labelBgPadding} labelBgBorderRadius={labelBgBorderRadius} />;
}

const NODE_RENDERERS = { brain: BrainFlowNode, artifactGroup: ArtifactGroup };
const EDGE_RENDERERS = { routed: RoutedEdge };
