import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Background, BaseEdge, Handle, MarkerType, MiniMap, Panel, Position, ReactFlow } from "@xyflow/react";
import { Crosshair, FilterX, LocateFixed, Maximize2, Minus, Plus, RefreshCw, Search, SlidersHorizontal, TriangleAlert } from "lucide-react";
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
import { layoutArtifactGraph, layoutGraph, routePath, NODE_WIDTH, NODE_HEIGHT } from "../graphLayout";

const EMPTY_FILTERS = { modelId: "", reportId: "", query: "", artifact: "", objectType: "", status: "factual", edgeType: "" };
import { objectName, scopeChoices, statusLabel, visualType } from "../presentation";
const scopeOptions = scopeChoices;

function SelectField({ label, value, onChange, children, disabled }) {
  return <Label className="graph-filter-field"><span>{label}</span><NativeSelect aria-label={label} value={value} onChange={(event) => onChange(event.target.value)} disabled={disabled}>{children}</NativeSelect></Label>;
}

export default function GraphView({ transport, overview, snapshot, selectedId, colors, onSelect }) {
  const [filters, setFilters] = useState(() => ({ ...EMPTY_FILTERS, status: selectedId ? "" : "factual" }));
  const [query, setQuery] = useState("");
  const [centerId, setCenterId] = useState(selectedId || "");
  const [depth, setDepth] = useState(1);
  const [limit, setLimit] = useState(80);
  const [result, setResult] = useState(null);
  const [graphError, setGraphError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [focusedNode, setFocusedNode] = useState(null);
  const [grouped, setGrouped] = useState(false);
  const [showLabels, setShowLabels] = useState(false);
  const [direction, setDirection] = useState(() => globalThis.matchMedia?.("(max-width: 760px)").matches ? "TB" : "LR");
  const request = useRef(0);
  const graphKey = JSON.stringify([filters, centerId, depth, limit]);
  const requestedKey = useRef(graphKey);
  requestedKey.current = graphKey;
  const updateFilters = (change) => { setFilters((current) => ({ ...current, ...change })); setFocusedNode(null); };
  useEffect(() => { setCenterId(selectedId || ""); setFocusedNode(null); }, [selectedId]);
  useEffect(() => {
    const timer = setTimeout(() => setFilters((current) => current.query === query.trim() ? current : { ...current, query: query.trim() }), 220);
    return () => clearTimeout(timer);
  }, [query]);
  const loadGraph = useCallback(async () => {
    const requestId = ++request.current;
    setLoading(true); setGraphError(null);
    try {
      const data = await transport.getGraph({ ...filters, centerId, depth, limit });
      if (requestId === request.current && requestedKey.current === graphKey) setResult({ key: graphKey, data });
    } catch (error) {
      if (requestId === request.current && requestedKey.current === graphKey) {
        setGraphError({ key: graphKey, message: error.message || "Graph could not be loaded" });
        setResult(null);
      }
    } finally {
      if (requestId === request.current && requestedKey.current === graphKey) setLoading(false);
    }
  }, [filters, centerId, depth, limit, graphKey, transport]);
  useEffect(() => { loadGraph(); return () => { request.current += 1; }; }, [loadGraph]);
  const graph = result?.key === graphKey ? result.data : null;
  const nodes = graph?.nodes || [];
  const edges = graph?.edges || [];
  const error = graphError?.key === graphKey ? graphError.message : "";
  const objectTypes = [...new Set([...OBJECT_TYPES, ...Object.keys(overview?.object_counts || {})])].sort();
  const edgeTypes = [...new Set([...EDGE_TYPES, ...edges.map((edge) => edge.type)])].sort();
  const warningIds = useMemo(() => new Set((snapshot.conflicts || []).flatMap((item) => [item.target?.id || item.target || item.target_id || item.object_id, item.id, item.conflict_id].filter(Boolean))), [snapshot.conflicts]);
  const legendNodes = [...new Map(nodes.map((node) => [`${artifactGroup(node)}:${node.type}`, node])).values()].sort((a, b) => a.type.localeCompare(b.type));
  const hasFilters = Object.entries(filters).some(([key, value]) => value !== EMPTY_FILTERS[key]) || Boolean(query) || Boolean(centerId);
  const activeFilters = Object.entries(filters).filter(([key, value]) => value !== EMPTY_FILTERS[key]).length;
  const reset = () => { setFilters(EMPTY_FILTERS); setQuery(""); setCenterId(""); setDepth(1); setLimit(80); setFocusedNode(null); };
  const center = (node) => { setFilters({ ...EMPTY_FILTERS, status: node.status === "factual" ? "factual" : "" }); setQuery(""); setCenterId(node.id); setFocusedNode(node); };

  return <div className="graph-page">
    <Card className="graph-filter-card">
      <div className="graph-filter-top">
        <div className="graph-search"><Search aria-hidden="true" /><Input type="search" aria-label="Filter graph objects" value={query} onChange={(event) => { setQuery(event.target.value); setFocusedNode(null); }} placeholder="Find an object…" /></div>
        <Tabs value={filters.artifact || "all"} onValueChange={(value) => updateFilters({ artifact: value === "all" ? "" : value })}>
          <TabsList aria-label="Artifact groups"><TabsTrigger value="all">All objects</TabsTrigger>{Object.entries(ARTIFACT_GROUPS).map(([key, group]) => <TabsTrigger value={key} key={key}><span className="artifact-dot" style={{ backgroundColor: colors.groups[key] }} />{group.label.replace(" artifacts", "")}</TabsTrigger>)}</TabsList>
        </Tabs>
        <div className="graph-filter-actions">
          <Button variant="ghost" size="sm" disabled={!hasFilters} onClick={reset}><FilterX />Clear filters</Button>
          <Button variant="outline" size="sm" onClick={loadGraph} disabled={loading}><RefreshCw className={loading ? "spin" : ""} />Refresh</Button>
        </div>
      </div>
      <details className="graph-filter-details"><summary><SlidersHorizontal aria-hidden="true" />More filters{activeFilters ? <span className="count-pill">{activeFilters} active</span> : ""}</summary><div className="graph-filters">
        <SelectField label="Model" value={filters.modelId} onChange={(modelId) => { setCenterId(""); updateFilters({ modelId, reportId: "" }); }}><option value="">All models</option>{scopeOptions(overview, "model").map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</SelectField>
        <SelectField label="Report" value={filters.reportId} onChange={(reportId) => { setCenterId(""); updateFilters({ reportId, modelId: "" }); }}><option value="">All reports</option>{scopeOptions(overview, "report").map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</SelectField>
        <SelectField label="Object type" value={filters.objectType} onChange={(objectType) => updateFilters({ objectType })}><option value="">All types</option>{objectTypes.map((type) => <option key={type} value={type}>{typeLabel(type)}</option>)}</SelectField>
        <SelectField label="Status" value={filters.status} onChange={(status) => updateFilters({ status })}><option value="">All statuses</option>{["factual", "candidate", "approved", "rejected", "overridden"].map((status) => <option key={status} value={status}>{statusLabel(status)}</option>)}</SelectField>
        <SelectField label="Relationship" value={filters.edgeType} onChange={(edgeType) => updateFilters({ edgeType })}><option value="">All relationships</option>{edgeTypes.map((type) => <option key={type} value={type}>{typeLabel(type)}</option>)}</SelectField>
        <SelectField label="Distance" value={depth} disabled={!centerId} onChange={(value) => { setDepth(Number(value)); setFocusedNode(null); }}>{[1, 2, 3, 4].map((value) => <option key={value} value={value}>{value} {value === 1 ? "connection away" : "connections away"}</option>)}</SelectField>
      </div>
      </details>
    </Card>
    <div className="graph-meta">
      <div className="graph-summary" role="status" aria-live="polite"><span>{loading ? "Loading graph…" : `${nodes.length} of ${graph?.total_nodes ?? 0} matching objects · ${edges.length} relationships`}</span></div>
      {centerId ? <div className="graph-center"><Badge variant="default"><Crosshair />Focused view</Badge><span>{objectName(nodes.find((node) => node.id === centerId))}</span><Button variant="ghost" size="xs" onClick={() => { setCenterId(""); setFocusedNode(null); }}>Back to project</Button>{filters.objectType ? <small>The center stays visible for context.</small> : null}</div> : null}
      {graph?.truncated ? <div className="scope-notice">Showing {nodes.length} of {graph.total_nodes} objects. Filter by name or double-click an object to explore its connections{limit < 1000 ? <> or <Button variant="link" size="xs" onClick={() => setLimit(Math.min(limit * 2, 1000))}>Show more</Button></> : "."}</div> : null}
    </div>
    <Card className="graph-canvas-card" aria-busy={loading}>
      <div className="graph-canvas-toolbar"><SelectField label="Layout" value={direction} onChange={setDirection}><option value="LR">Left to right</option><option value="TB">Top to bottom</option></SelectField><span className="toolbar-divider" aria-hidden="true" /><Label className="graph-label-control"><Checkbox checked={showLabels} onCheckedChange={(checked) => setShowLabels(checked === true)} />Relationship labels</Label><Label className="graph-label-control"><Checkbox checked={filters.status !== "factual"} onCheckedChange={(checked) => updateFilters({ status: checked ? "" : "factual" })} />Include suggestions</Label><Label className="graph-label-control"><Checkbox checked={grouped} onCheckedChange={(checked) => setGrouped(checked === true)} />Group by ownership</Label><span className="graph-hint">Scroll to zoom · Drag to pan · Double-click to focus</span></div>
      {error ? <div className="graph-empty" role="alert"><span className="empty-icon tone-bad" aria-hidden="true"><TriangleAlert /></span><h3>Graph unavailable</h3><p>{error}</p><Button variant="outline" onClick={loadGraph}>Retry graph</Button></div> : !graph ? <div className="graph-empty graph-loading" role="status"><span className="graph-loader" aria-hidden="true"><i /><i /><i /></span><p>Loading graph…</p></div> : nodes.length ? <GraphCanvas grouped={grouped} onCenter={center} nodes={nodes} edges={edges} selectedId={focusedNode?.id} warningIds={warningIds} direction={direction} showLabels={showLabels} colors={colors} onSelect={setFocusedNode} /> : <div className="graph-empty"><span className="empty-icon" aria-hidden="true"><Search /></span><h3>No matching objects</h3><p>{hasFilters ? "Try another filter or clear the filters." : "Scan project sources to see their relationships."}</p>{hasFilters ? <Button variant="outline" onClick={reset}>Clear filters</Button> : null}</div>}
      <div className="artifact-legend" aria-label="Graph color legend">{legendNodes.map((node) => <span key={`${artifactGroup(node)}:${node.type}`}><span className="artifact-dot" style={{ backgroundColor: artifactColor(node, colors) }} />{typeLabel(node.type)}{legendNodes.filter((item) => item.type === node.type).length > 1 ? ` · ${typeLabel(artifactGroup(node))}` : ""}</span>)}<span className="legend-spacer" aria-hidden="true" /><span className="legend-evidence"><i className="legend-line fact" />Fact</span><span className="legend-evidence"><i className="legend-line inferred" />Inferred</span><span className="legend-evidence"><i className="legend-line observed" />Observed</span></div>
    </Card>
    <GraphDetails node={focusedNode} colors={colors} transport={transport} onClose={() => setFocusedNode(null)} onSelect={setFocusedNode} onCenter={center} onInspect={(id) => onSelect(id, "inspector")} />
  </div>;
}

function GraphCanvas({ grouped, onCenter, nodes, edges, selectedId, warningIds, direction, showLabels, colors, onSelect }) {
  const [flow, setFlow] = useState(null);
  const wrapper = useRef(null);
  const layout = useMemo(() => grouped ? layoutArtifactGraph(nodes, edges, direction) : { ...layoutGraph(nodes, edges, direction), groups: [] }, [nodes, edges, direction, grouped]);
  // Keep a newly selected node clear of the floating details sheet.
  useEffect(() => {
    const placed = layout.nodes.find(({ node }) => node.id === selectedId);
    if (!flow || !placed || !wrapper.current || window.innerWidth <= 760) return undefined;
    // Wait out the double-click window so panning never moves a node mid-gesture.
    const timer = setTimeout(() => {
      if (!wrapper.current) return;
      const bounds = wrapper.current.getBoundingClientRect();
      const sheetLeft = window.innerWidth - 14 - Math.min(420, window.innerWidth - 28) - 16;
      const { x, y, zoom } = flow.getViewport();
      if ((placed.position.x + NODE_WIDTH) * zoom + x + bounds.left < sheetLeft) return;
      const visibleMiddle = (bounds.left + Math.min(bounds.right, sheetLeft)) / 2;
      flow.setViewport({ x: visibleMiddle - bounds.left - (placed.position.x + NODE_WIDTH / 2) * zoom, y, zoom }, { duration: 360 });
    }, 450);
    return () => clearTimeout(timer);
  }, [flow, layout, selectedId]);
  const connected = new Set([selectedId]);
  edges.forEach((edge) => {
    if (edge.from_id === selectedId || edge.to_id === selectedId) { connected.add(edge.from_id); connected.add(edge.to_id); }
  });
  const flowNodes = [
    ...layout.groups.map((group) => ({ id: group.id, type: "artifactGroup", position: group.position, width: group.width, height: group.height, zIndex: -1, selectable: false, focusable: false, draggable: false, style: { width: group.width, height: group.height, pointerEvents: "none" }, data: { ...group, color: colors.groups[group.key] } })),
    ...layout.nodes.map(({ node, position }) => ({
      id: node.id, type: "brain", position, selected: node.id === selectedId,
      width: NODE_WIDTH, height: NODE_HEIGHT, ariaRole: "button", ariaLabel: `Select ${objectName(node)}`,
      className: selectedId && !connected.has(node.id) ? "is-dimmed" : "",
      data: { node, direction, warning: warningIds.has(node.id) || node.type === "CONFLICT", color: artifactColor(node, colors) },
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
      label: showLabels || highlighted || warning ? `${warning ? "Warning · " : ""}${typeLabel(edge.type)}` : undefined,
      ariaLabel: `${objectName(source)} ${typeLabel(edge.type)} ${objectName(nodes.find((node) => node.id === edge.to_id))}`,
      className: `flow-edge ${evidenceClass.toLowerCase()} ${warning ? "warning" : ""} ${highlighted ? "highlighted" : ""}`,
      markerEnd: { type: MarkerType.ArrowClosed, color, width: 16, height: 16 },
      style: { stroke: color, opacity: selectedId && !highlighted ? 0.1 : highlighted ? 1 : 0.55, strokeWidth: highlighted || warning ? 2.2 : 1.4, strokeDasharray: evidenceClass === "INFERRED" ? "6 4" : evidenceClass === "OBSERVED" ? "2 5" : undefined },
      labelStyle: { fill: "var(--text)", fontSize: 11, fontWeight: 500 }, labelBgStyle: { fill: "var(--surface-2)", fillOpacity: 0.98 }, labelBgPadding: [6, 3], labelBgBorderRadius: 4, data: { points },
    };
  });
  const layoutKey = JSON.stringify([direction, grouped, nodes.map((node) => [node.id, artifactGroup(node)]).sort(), edges.map((edge) => [edge.id, edge.from_id, edge.to_id]).sort()]);
  return <div ref={wrapper} className="flow-wrap artifact-flow" role="region" aria-label="Directed project graph">
    <ReactFlow key={layoutKey} onInit={setFlow} nodes={flowNodes} edges={flowEdges} nodeTypes={NODE_RENDERERS} edgeTypes={EDGE_RENDERERS}
      onNodeDoubleClick={(_, node) => { if (node.type === "brain") onCenter(node.data.node); }} onNodeClick={(_, node) => { if (node.type === "brain") onSelect(node.data.node); }} onPaneClick={() => onSelect(null)}
      onNodesChange={(changes) => { const selection = changes.find((change) => change.type === "select" && change.selected); if (selection) { const node = nodes.find((item) => item.id === selection.id); if (node) onSelect(node); } }}
      zoomOnDoubleClick={false} fitView fitViewOptions={{ padding: 0.16, maxZoom: 1 }} minZoom={0.08} maxZoom={2}
      nodesDraggable={false} nodesConnectable={false} edgesFocusable={false} proOptions={{ hideAttribution: true }}>
      <Panel position="top-left">{nodes.some((node) => node.id === selectedId) ? <Button variant="outline" size="sm" className="canvas-button" onClick={() => flow?.fitView({ nodes: [{ id: selectedId }], padding: 0.6, minZoom: 0.8, maxZoom: 1, duration: 360 })}><LocateFixed />Focus selected</Button> : null}</Panel>
      <Background gap={22} size={1.2} color="var(--grid-dot)" />
      <Panel position="bottom-left" className="graph-zoom-controls"><Button variant="ghost" size="icon-sm" aria-label="Zoom in" onClick={() => flow?.zoomIn({ duration: 200 })}><Plus /></Button><Button variant="ghost" size="icon-sm" aria-label="Zoom out" onClick={() => flow?.zoomOut({ duration: 200 })}><Minus /></Button><span className="zoom-divider" aria-hidden="true" /><Button variant="ghost" size="icon-sm" aria-label="Fit view" title="Fit view" onClick={() => flow?.fitView({ padding: 0.14, duration: 320 })}><Maximize2 /></Button></Panel>
      <MiniMap pannable zoomable nodeColor={(node) => node.data?.color || "#94a3b8"} nodeStrokeColor={(node) => node.data?.color || "#94a3b8"} nodeBorderRadius={4} nodeClassName={(node) => node.type === "artifactGroup" ? "minimap-artifact-group" : ""} maskColor="var(--minimap-mask)" style={{ width: 176, height: 116 }} />
    </ReactFlow>
  </div>;
}

function ArtifactGroup({ data }) {
  return <div className="artifact-group" style={{ "--artifact-color": data.color }}><span className="artifact-group-title"><span className="artifact-dot" />{ARTIFACT_GROUPS[data.key].label}<span>{data.count}</span></span></div>;
}

function BrainFlowNode({ data, selected }) {
  const node = data.node;
  const flagged = node.status && node.status !== "factual" || data.warning;
  return <div className={`flow-node artifact-node ${selected ? "selected" : ""} ${data.warning ? "has-warning" : ""}`} style={{ "--artifact-color": data.color }} title={objectName(node)}>
    <Handle type="target" position={data.direction === "TB" ? Position.Top : Position.Left} className="flow-handle" />
    <span className="flow-node-type"><span className="artifact-dot" />{node.type === "VISUAL" ? visualType(node) : typeLabel(node.type)}</span>
    <span className="flow-node-name">{objectName(node)}</span>
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
