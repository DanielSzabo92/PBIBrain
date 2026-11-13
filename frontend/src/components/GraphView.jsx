import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Background, BaseEdge, Handle, MarkerType, MiniMap, Position, ReactFlow, getSmoothStepPath, useViewport } from "@xyflow/react";
import { BadgeCheck, ChevronDown, ChevronRight, ChevronsDownUp, CircleX, Code, Copy, Crosshair, FilterX, ListFilter, Maximize, Minus, PenLine, Plus, Search, Shapes, SlidersHorizontal, TriangleAlert } from "lucide-react";
import "@xyflow/react/dist/style.css";
import { Button } from "./ui/button";
import { ContextMenu, ContextMenuTrigger, ContextMenuContent, ContextMenuItem, ContextMenuSeparator } from "./ui/context-menu";
import { toast } from "./ui/toast";
import { Checkbox } from "./ui/checkbox";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { NativeSelect } from "./ui/native-select";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "./ui/tabs";
import { Tooltip } from "./ui/tooltip";
import { Popover } from "./ui/filter";
import GraphDetails from "./GraphDetails";
import ProvenanceLegend from "./ProvenanceLegend";
import { TypeGlyph, TypeIcon } from "./TypeGlyph";
import { ARTIFACT_GROUPS, EDGE_TYPES, artifactColor, artifactGroup, middleEllipsis, typeLabel } from "../graphPresentation";
import { buildExplorerGraph, bundleExplorerEdges, layoutExplorerGraph, layoutArtifactGraph, layoutGraph, NODE_WIDTH, NODE_HEIGHT, GROUP_WIDTH, GROUP_HEIGHT } from "../graphLayout";
import { formatCount, objectName, scopeChoices, statusLabel, visualType } from "../presentation";
import { foldLineage, hideLanes, layoutLineage, lineageOf, TWO_LINE_HEIGHT } from "../lineage";
import { groupVersions, versionNote } from "../versions";
import ImpactMatrix from "./ImpactMatrix";
import LaneChips from "./LaneChips";
import { VersionBadge } from "./VersionBadge";
import { OriginBadge } from "./OriginBadge";
import { isTextEntry } from "../shortcuts";

const EMPTY_FILTERS = { modelId: "", reportId: "", query: "", artifact: "", objectType: "", status: "", edgeType: "" };
const scopeOptions = scopeChoices;
const DEFAULT_LIMIT = 80;
// Density rules (visual contract §11.8).
const AUTO_COLLAPSE_ABOVE = 40;
const MINIMAP_ABOVE = 30;
// Semantic zoom (visual contract §11.9). Names are 13px, so below READABLE_ZOOM they would render under
// 11px: from there down to GLYPH_ZOOM a name is counter-scaled to stay 11px on screen (and shortened to fit);
// below GLYPH_ZOOM a node shows only its type glyph. Edge labels (12px) hide below LABEL_ZOOM.
const READABLE_ZOOM = 0.85;
const GLYPH_ZOOM = 0.55;
const LABEL_ZOOM = 0.92;
/** Zoom tier as a stable key: "full", a 0.05-wide band ("0.6"), or "far". Bands round down, so text never drops under 11px. */
function zoomTier(zoom) {
  if (zoom >= READABLE_ZOOM - 0.001) return "full";
  if (zoom < GLYPH_ZOOM) return "far";
  return (Math.floor(zoom * 20 + 1e-6) / 20).toFixed(2);
}
const nameScale = (tier) => tier === "full" || tier === "far" ? 1 : 11 / (13 * Number(tier));
// Lineage fits no further out than the smallest zoom that still shows names (see GLYPH_ZOOM).
const FULL_GRAPH_MIN_ZOOM = 0.55;
const DETAIL_PANE_WIDTH = 360;
const NAME_WIDTH_MAX = 320;
// Room for a name and three inside counts.
const GROUP_COUNTS_WIDTH = 224;
// Large pictures render only what is in view (the whole project stays laid out and searchable).
const VIEWPORT_ONLY_ABOVE = 400;
// The pane overlays the canvas for one double-click window before it docks, so the second click of a
// double-click still lands on the node that the first click selected.
const DOCK_DELAY = 350;
// Links between collapsed owners are all drawn up to this many; above it, only those of the selection.
const BUNDLES_ALWAYS = 40;
// Their counts are written out up to this many; above it, on the selection's links only.
const BUNDLE_LABELS = 40;
// Inside counts shown on an owner, in reading order.
const COUNT_TYPES = ["TABLE", "COLUMN", "MEASURE", "PAGE", "VISUAL"];
// Lanes with more objects than this pack the selection's chain together instead of dimming the rest.
const TRACE_ABOVE = 80;
const DEPENDENCY_EDGES = new Set(["DEPENDS_ON", "REFERENCES", "USES", "USES_MODEL"]);
const STRUCTURE_EDGES = new Set(["CONTAINS", "BELONGS_TO"]);
const STATUS_GLYPHS = { approved: BadgeCheck, rejected: CircleX, overridden: PenLine };

function defaultDirection() {
  return globalThis.matchMedia?.("(max-width: 760px)").matches ? "TB" : "LR";
}

// Viewport travel (motion tokens: --ease-move). Linear interpolation pans and zooms directly instead of
// d3's default "fly" curve, which zooms out mid-way.
const easeMove = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
const travel = (duration) => ({ duration, ease: easeMove, interpolate: "linear" });

function prefersReducedMotion() {
  return Boolean(globalThis.matchMedia?.("(prefers-reduced-motion: reduce)").matches);
}

export function createGraphSession(selectedId = "") {
  const centerId = selectedId || "";
  return {
    revision: 0,
    filters: { ...EMPTY_FILTERS },
    query: "",
    centerId,
    depth: 1,
    limit: DEFAULT_LIMIT,
    result: null,
    grouped: false,
    viewMode: "overview",
    expandedIds: null,
    hiddenTypes: [],
    // Lineage lanes switched off with the lane chips (shared by Lineage and Matrix).
    hiddenLanes: [],
    // Lineage folds opened by the person (large pictures fold long lanes by owner).
    unfolded: [],
    groupVersions: true,
    // Selecting an object hides what is not related to it. null: automatic, on for large pictures (issue #53).
    relatedOnly: null,
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
    viewMode: ["full", "matrix"].includes(incoming.viewMode) ? incoming.viewMode : "overview",
    expandedIds: Array.isArray(incoming.expandedIds) ? incoming.expandedIds.filter((id) => typeof id === "string") : null,
    hiddenTypes: Array.isArray(incoming.hiddenTypes) ? incoming.hiddenTypes.filter((type) => typeof type === "string") : [],
    hiddenLanes: Array.isArray(incoming.hiddenLanes) ? incoming.hiddenLanes.filter((lane) => typeof lane === "string") : [],
    unfolded: Array.isArray(incoming.unfolded) ? incoming.unfolded.filter((id) => typeof id === "string") : [],
    groupVersions: typeof incoming.groupVersions === "boolean" ? incoming.groupVersions : defaults.groupVersions,
    relatedOnly: typeof incoming.relatedOnly === "boolean" ? incoming.relatedOnly : null,
    viewports: incoming.viewports && typeof incoming.viewports === "object" ? incoming.viewports : {},
    placements: incoming.placements && typeof incoming.placements === "object" ? incoming.placements : {},
    showLabels: typeof incoming.showLabels === "boolean" ? incoming.showLabels : defaults.showLabels,
    direction: incoming.direction === "TB" || incoming.direction === "LR" ? incoming.direction : defaults.direction,
    selectionId,
  };
}

/**
 * Containers, Lineage and Matrix read the whole factual structure of the scope (getLineage: compact, no
 * object limit), so the default picture is the whole project and never a sample of it.
 * Suggestions, artifact/type/link filters and Neighbourhood use the scoped, limited getGraph slice.
 */
function wholeScope(session) {
  const { filters } = session;
  return !session.centerId && ["overview", "full", "matrix"].includes(session.viewMode) && !filters.artifact && !filters.objectType && !filters.edgeType && (filters.status === "" || filters.status === "factual");
}


function graphRequestKey(session) {
  return wholeScope(session)
    ? JSON.stringify([session.revision || 0, "lineage", session.filters.modelId, session.filters.reportId])
    : JSON.stringify([session.revision || 0, session.filters, session.centerId, session.depth, session.limit]);
}

/** The type a person reads first: the visual kind for visuals, else the object type. */
function kindLabel(node) {
  return node?.type === "VISUAL" ? visualType(node) : typeLabel(node?.type);
}

/** Accessible name of a graph node, e.g. "Measure Net Sales" or "Table Sales, 5 inside, needs review". */
function nodeLabel(node, warning, isGroup) {
  const count = node?.explorerDescendantCount || node?.explorerChildCount || 0;
  const inside = isGroup && count ? `, ${count} inside` : "";
  const state = warning ? ", needs review" : node.status && node.status !== "factual" ? `, ${statusLabel(node.status).toLowerCase()}` : "";
  if (node?.fold) return `${node.foldCount} ${typeLabel(node.type)} objects of ${objectName(node)}, folded. Press Enter to show them`;
  return `${kindLabel(node)} ${objectName(node)}${inside}${state}`;
}

function SelectField({ label, value, onChange, children, disabled }) {
  return <Label className="graph-filter-field"><span>{label}</span><NativeSelect aria-label={label} value={value} onChange={(event) => onChange(event.target.value)} disabled={disabled}>{children}</NativeSelect></Label>;
}

// Popover triggers need the DOM node (Radix measures it to place the popover).
const ToolbarTrigger = React.forwardRef(function ToolbarTrigger({ icon: Icon, label, count, countLabel, active, ...props }, ref) {
  return <button ref={ref} type="button" className="graph-tool-trigger" data-active={active || undefined} {...props}>
    <Icon aria-hidden="true" /><span>{label}</span>
    {count ? <span className="graph-tool-count" data-ui-number="" aria-label={countLabel}>{count}</span> : null}
    <ChevronDown aria-hidden="true" className="graph-tool-chevron" />
  </button>;
});

function TypesPopoverContent({ nodes, hiddenTypes, colors, onChange }) {
  const hidden = new Set(hiddenTypes);
  const rows = useMemo(() => {
    const byType = new Map();
    for (const node of nodes) {
      const row = byType.get(node.type) || { type: node.type, node, count: 0 };
      row.count += 1;
      byType.set(node.type, row);
    }
    // A hidden type stays listed even when the current slice has none of it, so it can be shown again.
    for (const type of hiddenTypes) if (!byType.has(type)) byType.set(type, { type, node: { type }, count: 0 });
    const groupOrder = ["model", "report", "other"];
    return [...byType.values()].sort((left, right) => groupOrder.indexOf(artifactGroup(left.node)) - groupOrder.indexOf(artifactGroup(right.node)) || typeLabel(left.type).localeCompare(typeLabel(right.type)));
  }, [nodes, hiddenTypes]);
  const hiddenHere = rows.filter((row) => hidden.has(row.type)).length;
  const toggle = (type, visible) => onChange(visible ? hiddenTypes.filter((item) => item !== type) : [...new Set([...hiddenTypes, type])]);

  return <>
    <div role="group" aria-label="Graph color legend">
      <ul className="graph-type-list">
        {rows.map((row) => {
          const label = typeLabel(row.type);
          const id = `graph-type-${row.type}`;
          return <li key={row.type} className="graph-type-row">
            <Checkbox id={id} aria-label={label} checked={!hidden.has(row.type)} onCheckedChange={(checked) => toggle(row.type, checked === true)} />
            <TypeGlyph type={row.type} node={row.node} colors={colors} size="sm" />
            <label htmlFor={id} translate="no">{label}</label>
            <span className="graph-type-count" data-ui-number="">{row.count}</span>
            <button type="button" className="graph-type-only" aria-label={`Show only ${label}`} onClick={() => onChange(rows.map((item) => item.type).filter((type) => type !== row.type))}>Only</button>
          </li>;
        })}
      </ul>
    </div>
    {hiddenHere ? <Button variant="ghost" size="sm" className="graph-popover-reset" onClick={() => onChange([])}>Show all types</Button> : null}
    <div className="graph-popover-section"><span className="graph-popover-heading">Links</span><ProvenanceLegend /></div>
  </>;
}

function TypesPopover({ nodes, hiddenTypes, colors, onChange }) {
  const hidden = new Set(hiddenTypes);
  const hiddenHere = nodes.filter((node) => hidden.has(node.type)).length;
  return <Popover label="Object types" className="graph-popover graph-types-popover"
    trigger={<ToolbarTrigger icon={Shapes} label="Types" active={hiddenTypes.length > 0} count={hiddenTypes.length ? `${nodes.length - hiddenHere}/${nodes.length}` : ""} countLabel={`${nodes.length - hiddenHere} of ${nodes.length} types shown`} title="Object types: colour key and visibility" />}>
    <TypesPopoverContent nodes={nodes} hiddenTypes={hiddenTypes} colors={colors} onChange={onChange} />
  </Popover>;
}

function DisplayPopoverContent({ direction, showLabels, includeSuggestions, grouped, canGroup, versions, canVersion, relatedOnly, onChange }) {
  return <div className="graph-popover-stack">
    <SelectField label="Layout" value={direction} onChange={(value) => onChange({ direction: value })}><option value="LR">Left to right</option><option value="TB">Top to bottom</option></SelectField>
    <Label className="graph-label-control"><Checkbox checked={showLabels} onCheckedChange={(checked) => onChange({ showLabels: checked === true })} />Relationship labels</Label>
    <Label className="graph-label-control"><Checkbox checked={includeSuggestions} onCheckedChange={(checked) => onChange({ includeSuggestions: checked === true })} />Include suggestions</Label>
    {canGroup ? <Label className="graph-label-control"><Checkbox checked={grouped} onCheckedChange={(checked) => onChange({ grouped: checked === true })} />Group by ownership</Label> : null}
    {canVersion ? <Label className="graph-label-control" title="Show an object once when it is in several versions of a model or report (same table and name, same page and visual IDs)"><Checkbox checked={versions} onCheckedChange={(checked) => onChange({ groupVersions: checked === true })} />Group versions</Label> : null}
    <Label className="graph-label-control" title="When an object is selected, hide the objects it is not connected to instead of dimming them"><Checkbox checked={relatedOnly} onCheckedChange={(checked) => onChange({ relatedOnly: checked === true })} />Show only related on select</Label>
  </div>;
}

function DisplayPopover({ direction, showLabels, includeSuggestions, grouped, canGroup, versions, canVersion, relatedOnly, onChange }) {
  return <Popover label="Display options" className="graph-popover graph-display-popover"
    trigger={<ToolbarTrigger icon={SlidersHorizontal} label="Display" title="Layout direction and labels" />}>
    <DisplayPopoverContent direction={direction} showLabels={showLabels} includeSuggestions={includeSuggestions} grouped={grouped} canGroup={canGroup} versions={versions} canVersion={canVersion} relatedOnly={relatedOnly} onChange={onChange} />
  </Popover>;
}

function FiltersPopoverContent({ filters, depth, centerId, overview, edgeTypes, hasFilters, onFilters, onScope, onDepth, onReset }) {
  return <>
    <div className="graph-popover-grid">
      <SelectField label="Objects" value={filters.artifact} onChange={(artifact) => onFilters({ artifact })}><option value="">All objects</option>{Object.entries(ARTIFACT_GROUPS).map(([key, group]) => <option key={key} value={key}>{group.label.replace(" artifacts", " objects")}</option>)}</SelectField>
      <SelectField label="Model" value={filters.modelId} onChange={(modelId) => onScope({ modelId, reportId: "" })}><option value="">All models</option>{scopeOptions(overview, "model").map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</SelectField>
      <SelectField label="Report" value={filters.reportId} onChange={(reportId) => onScope({ reportId, modelId: "" })}><option value="">All reports</option>{scopeOptions(overview, "report").map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</SelectField>
      <SelectField label="Status" value={filters.status} onChange={(status) => onFilters({ status })}><option value="">All statuses</option>{["factual", "candidate", "approved", "rejected", "overridden"].map((status) => <option key={status} value={status}>{statusLabel(status)}</option>)}</SelectField>
      <SelectField label="Relationship" value={filters.edgeType} onChange={(edgeType) => onFilters({ edgeType })}><option value="">All relationships</option>{edgeTypes.map((type) => <option key={type} value={type}>{typeLabel(type)}</option>)}</SelectField>
      <SelectField label="Distance" value={depth} disabled={!centerId} onChange={(value) => onDepth(Number(value))}>{[1, 2, 3, 4].map((value) => <option key={value} value={value}>{value} {value === 1 ? "connection away" : "connections away"}</option>)}</SelectField>
    </div>
    <Button variant="ghost" size="sm" className="graph-popover-reset" disabled={!hasFilters} onClick={onReset}><FilterX />Clear filters</Button>
  </>;
}

function FiltersPopover({ filters, depth, centerId, overview, edgeTypes, activeCount, hasFilters, onFilters, onScope, onDepth, onReset }) {
  return <Popover label="Graph filters" className="graph-popover graph-filters-popover"
    trigger={<ToolbarTrigger icon={ListFilter} label="Filters" active={activeCount > 0} count={activeCount || ""} countLabel={`${activeCount} active`} title="Filter by model, report, status or relationship" />}>
    <FiltersPopoverContent filters={filters} depth={depth} centerId={centerId} overview={overview} edgeTypes={edgeTypes} hasFilters={hasFilters} onFilters={onFilters} onScope={onScope} onDepth={onDepth} onReset={onReset} />
  </Popover>;
}

function ViewPopover({
  nodes, hiddenTypes, colors, onTypesChange,
  direction, showLabels, includeSuggestions, grouped, canGroup, versions, canVersion, relatedOnly, onDisplayChange,
  filters, depth, centerId, overview, edgeTypes, activeCount, hasFilters, onFilters, onScope, onDepth, onResetFilters
}) {
  const hiddenCount = hiddenTypes.length;
  const activeTotal = (activeCount || 0) + (hiddenCount ? 1 : 0);
  const [activeTab, setActiveTab] = useState("display");
  return <Popover label="View options and filters" className="graph-popover graph-view-popover"
    trigger={<ToolbarTrigger icon={SlidersHorizontal} label="View" active={activeTotal > 0} count={activeTotal ? String(activeTotal) : ""} countLabel={`${activeTotal} view options active`} title="View, display and filter options" />}>
    <Tabs value={activeTab} onValueChange={setActiveTab} className="graph-view-tabs">
      <TabsList aria-label="View options categories">
        <TabsTrigger value="display">Display</TabsTrigger>
        <TabsTrigger value="filters" count={activeCount ? activeCount : undefined}>Filters</TabsTrigger>
        <TabsTrigger value="types" count={hiddenCount ? `${nodes.length - hiddenCount}/${nodes.length}` : undefined}>Types</TabsTrigger>
      </TabsList>
      <TabsContent value="display">
        <DisplayPopoverContent direction={direction} showLabels={showLabels} includeSuggestions={includeSuggestions} grouped={grouped} canGroup={canGroup} versions={versions} canVersion={canVersion} relatedOnly={relatedOnly} onChange={onDisplayChange} />
      </TabsContent>
      <TabsContent value="filters">
        <FiltersPopoverContent filters={filters} depth={depth} centerId={centerId} overview={overview} edgeTypes={edgeTypes} hasFilters={hasFilters} onFilters={onFilters} onScope={onScope} onDepth={onDepth} onReset={onResetFilters} />
      </TabsContent>
      <TabsContent value="types">
        <TypesPopoverContent nodes={nodes} hiddenTypes={hiddenTypes} colors={colors} onChange={onTypesChange} />
      </TabsContent>
    </Tabs>
  </Popover>;
}

function useNarrowView(breakpoint = 1200) {
  const query = `(max-width: ${breakpoint}px)`;
  const [isNarrow, setIsNarrow] = useState(() => Boolean(globalThis.matchMedia?.(query).matches));
  useEffect(() => {
    const list = globalThis.matchMedia?.(query);
    if (!list) return undefined;
    const update = () => setIsNarrow(list.matches);
    list.addEventListener("change", update);
    return () => list.removeEventListener("change", update);
  }, [query]);
  return isNarrow;
}

export default function GraphView({ transport, overview, snapshot, selectedId, colors, onSelect, session = null, onSession }) {
  const isNarrow = useNarrowView(1200);
  const [uncontrolledSession, setUncontrolledSession] = useState(() => createGraphSession(selectedId));
  const [graphError, setGraphError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [focusedNode, setFocusedNode] = useState(null);
  const [paneSettled, setPaneSettled] = useState(false);
  const canvasApi = useRef(null);
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
  const { filters, query, centerId, depth, limit, grouped, showLabels, direction, hiddenTypes, hiddenLanes } = graphSession;
  const graphKey = graphRequestKey(graphSession);
  const requestedKey = useRef(graphKey);
  requestedKey.current = graphKey;
  const updateSession = useCallback((change) => {
    const apply = (current) => {
      const base = normalizeGraphSession(current, selectedId);
      const next = typeof change === "function" ? change(base) : { ...base, ...change };
      // A no-op update keeps the stored object, so the parent does not re-render for nothing.
      return next === base && current ? current : next;
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
      const data = wholeScope(graphSession) && typeof transport.getLineage === "function"
        ? await transport.getLineage({ modelId: filters.modelId, reportId: filters.reportId })
        : await transport.getGraph({ ...filters, centerId, depth, limit: wholeScope(graphSession) ? 1000 : limit });
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
    // graphKey covers every input of the request.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graphKey, transport, updateSession]);
  useEffect(() => { loadGraph(); return () => { request.current += 1; }; }, [loadGraph]);
  const graph = graphSession.result?.key === graphKey ? graphSession.result.data : null;
  const viewMode = centerId ? "connections" : graphSession.viewMode;
  const overviewMode = viewMode === "overview";
  const lanesView = viewMode === "full" || viewMode === "matrix";
  // The whole-scope payload is not searched by the server: the search box filters it here, by name.
  const searchHere = wholeScope(graphSession) && filters.query;
  const loadedNodes = graph?.nodes;
  const nodes = useMemo(() => {
    const list = loadedNodes || [];
    if (!searchHere) return list;
    const needle = filters.query.toLowerCase();
    return list.filter((node) => objectName(node).toLowerCase().includes(needle));
  }, [loadedNodes, searchHere, filters.query]);
  const edges = graph?.edges || [];
  // Lineage: versions folded into one node, then lanes that are switched off bridged over.
  const versioned = useMemo(() => lanesView && graphSession.groupVersions ? groupVersions(nodes, edges) : null, [lanesView, graphSession.groupVersions, nodes, edges]);
  const rawById = useMemo(() => new Map((loadedNodes || []).map((node) => [node.id, node])), [loadedNodes]);
  // Type visibility is a view choice on the loaded slice. The focused object always stays for context.
  const hiddenSet = useMemo(() => new Set(hiddenTypes), [hiddenTypes]);
  const typedNodes = useMemo(() => {
    const list = versioned ? versioned.nodes : nodes;
    return hiddenSet.size ? list.filter((node) => !hiddenSet.has(node.type) || node.id === centerId) : list;
  }, [nodes, versioned, hiddenSet, centerId]);
  const typedIds = useMemo(() => new Set(typedNodes.map((node) => node.id)), [typedNodes]);
  const typedEdges = useMemo(() => {
    const list = versioned ? versioned.edges : edges;
    return hiddenSet.size ? list.filter((edge) => typedIds.has(edge.from_id) && typedIds.has(edge.to_id)) : list;
  }, [edges, versioned, hiddenSet, typedIds]);
  const laned = useMemo(() => viewMode === "full" && hiddenLanes.length ? hideLanes(typedNodes, typedEdges, hiddenLanes) : null, [viewMode, hiddenLanes, typedNodes, typedEdges]);
  const lanedNodes = laned ? laned.nodes : typedNodes;
  const lanedEdges = laned ? laned.edges : typedEdges;
  // A large lineage shows one row per owner in its long lanes; a click on a row opens it.
  const folded = useMemo(() => viewMode === "full" ? foldLineage(lanedNodes, lanedEdges, graphSession.unfolded) : null, [viewMode, lanedNodes, lanedEdges, graphSession.unfolded]);
  const shownNodes = folded ? folded.nodes : lanedNodes;
  const shownEdges = folded ? folded.edges : lanedEdges;
  // Default expansion opens each model, unless that would show more than the readable budget.
  const defaultExpanded = useMemo(() => {
    const models = shownNodes.filter((node) => node.type === "MODEL").map((node) => node.id);
    if (shownNodes.length <= AUTO_COLLAPSE_ABOVE) return models;
    // A large project: count what the models own directly instead of building the whole picture twice.
    if (shownNodes.length > 2000) {
      const modelIds = new Set(models);
      const owned = shownEdges.reduce((count, edge) => count + (edge.type === "CONTAINS" && modelIds.has(edge.from_id) ? 1 : 0), 0);
      if (models.length + owned > AUTO_COLLAPSE_ABOVE) return [];
    }
    return buildExplorerGraph(shownNodes, shownEdges, models).nodes.length > AUTO_COLLAPSE_ABOVE ? [] : models;
  }, [shownNodes, shownEdges]);
  const expandedIds = graphSession.expandedIds ?? defaultExpanded;
  const explorer = useMemo(() => buildExplorerGraph(shownNodes, shownEdges, expandedIds), [shownNodes, shownEdges, expandedIds]);
  const canvasNodes = overviewMode ? explorer.nodes : shownNodes;
  const focusedId = focusedNode?.id;
  // Overview lays out its structural links only; the links a selection adds are drawn, not laid out,
  // so selecting an object never runs the layout again (issue #53).
  const layoutEdges = useMemo(() => overviewMode
    ? explorer.edges.filter((edge) => filters.edgeType || edge.type === "CONTAINS" || DEPENDENCY_EDGES.has(edge.type))
    : shownEdges, [overviewMode, explorer, filters.edgeType, shownEdges]);
  // What collapsed owners hide is still said: one counted link per pair of owners that are shown.
  const bundles = useMemo(() => overviewMode && !filters.edgeType ? bundleExplorerEdges(explorer, shownEdges) : [], [overviewMode, filters.edgeType, explorer, shownEdges]);
  const canvasEdges = useMemo(() => {
    if (!overviewMode || filters.edgeType) return layoutEdges;
    const ofSelection = (edge) => edge.from_id === focusedId || edge.to_id === focusedId;
    const drawnBundles = bundles.length <= BUNDLES_ALWAYS ? bundles : focusedId ? bundles.filter(ofSelection) : [];
    const selectionLinks = focusedId ? explorer.edges.filter((edge) => edge.type !== "CONTAINS" && !DEPENDENCY_EDGES.has(edge.type) && ofSelection(edge)) : [];
    return selectionLinks.length || drawnBundles.length ? [...layoutEdges, ...selectionLinks, ...drawnBundles] : layoutEdges;
  }, [overviewMode, focusedId, filters.edgeType, layoutEdges, explorer, bundles]);
  // An opened model says which of its tables each report uses, so its own "report uses model" line,
  // which would run through those tables, is laid out but not drawn.
  const undrawn = useMemo(() => {
    if (!overviewMode || !canvasEdges.some((edge) => edge.bundle)) return null;
    const open = new Set(explorer.nodes.filter((node) => node.type === "MODEL" && node.explorerExpanded).map((node) => node.id));
    const ids = new Set(layoutEdges.filter((edge) => edge.type === "USES_MODEL" && (open.has(edge.to_id) || open.has(edge.from_id))).map((edge) => edge.id));
    return ids.size ? ids : null;
  }, [overviewMode, canvasEdges, explorer, layoutEdges]);
  // Automatic: on when the picture is too large to read the selection's chain in place.
  const relatedOnly = graphSession.relatedOnly ?? canvasNodes.length > (lanesView ? TRACE_ABOVE : VIEWPORT_ONLY_ABOVE);
  // Lineage searches and lane choices are applied here, not by the request: they re-fit the canvas too.
  const canvasKey = JSON.stringify([graphKey, viewMode, direction, !overviewMode && grouped, searchHere ? filters.query : "", viewMode === "full" ? hiddenLanes : []]);
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
  const toggleGroup = useCallback((id) => {
    canvasApi.current?.pin(id);
    updateSession((current) => {
      const expanded = new Set(current.expandedIds ?? defaultExpanded);
      if (expanded.has(id)) expanded.delete(id); else expanded.add(id);
      return { ...current, expandedIds: [...expanded] };
    });
    // A picture that fits is fitted again; a larger one stays where it is and shows the owner that changed.
    setTimeout(() => {
      canvasApi.current?.settle(id);
    }, 60);
  }, [defaultExpanded, updateSession]);
  const error = graphError?.key === graphKey ? graphError.message : "";
  const edgeTypes = [...new Set([...EDGE_TYPES, ...edges.map((edge) => edge.type)])].sort();
  const warningIds = useMemo(() => new Set((snapshot.conflicts || []).flatMap((item) => [item.target?.id || item.target || item.target_id || item.object_id, item.id, item.conflict_id].filter(Boolean))), [snapshot.conflicts]);
  const activeFilters = ["artifact", "modelId", "reportId", "edgeType", "objectType", "status"].filter((key) => Boolean(filters[key])).length;
  const hasFilters = Boolean(activeFilters || query || centerId || hiddenTypes.length > 0 || hiddenLanes.length > 0);
  const reset = () => { updateSession((current) => ({ ...current, filters: { ...EMPTY_FILTERS }, query: "", centerId: "", depth: 1, limit: DEFAULT_LIMIT, result: null, expandedIds: null, hiddenTypes: [], hiddenLanes: [], unfolded: [] })); setFocusedNode(null); };
  const center = useCallback((node) => {
    if (!node) return;
    updateSession((current) => ({ ...current, filters: { ...EMPTY_FILTERS }, query: "", centerId: node.id }));
    setFocusedNode(node);
  }, [updateSession]);

  const changeView = (mode) => {
    if (mode === "connections") { if (focusedNode) center(focusedNode); return; }
    updateSession({ viewMode: mode, centerId: "" });
    setFocusedNode(null);
  };
  const inspect = useCallback((id) => { updateSession({ selectionId: id }); onSelect(id, "inspector"); }, [onSelect, updateSession]);
  const changeDisplay = (change) => {
    if ("includeSuggestions" in change) { updateFilters({ status: change.includeSuggestions ? "" : "factual" }); return; }
    updateSession(change);
  };

  // The pane docks next to the canvas once the double-click window has passed (see DOCK_DELAY).
  const paneOpen = Boolean(focusedNode);
  useEffect(() => {
    if (!paneOpen) { setPaneSettled(false); return undefined; }
    const timer = setTimeout(() => setPaneSettled(true), DOCK_DELAY);
    return () => clearTimeout(timer);
  }, [paneOpen]);
  // Narrow windows show the pane over the canvas instead of beside it.
  const docked = paneSettled && !globalThis.matchMedia?.("(max-width: 760px)").matches;
  const closeDetails = useCallback(() => {
    const id = focusedNode?.id;
    const returnToNode = document.activeElement?.closest?.(".graph-detail-pane") || document.activeElement === document.body;
    setFocusedNode(null);
    if (id && returnToNode) requestAnimationFrame(() => document.querySelector(`.react-flow__node[data-id="${globalThis.CSS?.escape ? CSS.escape(id) : id}"]`)?.focus());
  }, [focusedNode]);

  // Canvas keys (visual contract §11.10): + − 0 zoom, F fits, Esc clears the selection and closes the pane.
  useEffect(() => {
    const onKey = (event) => {
      if (event.defaultPrevented || event.ctrlKey || event.metaKey || event.altKey) return;
      const target = event.target;
      if (target?.closest?.("[role=dialog], [role=alertdialog], [role=menu], [role=listbox]")) return;
      if (isTextEntry(target)) return;
      const api = canvasApi.current;
      if (event.key === "Escape") {
        if (paneOpen) { event.preventDefault(); closeDetails(); }
        return;
      }
      if (!api) return;
      const action = { "+": api.zoomIn, "=": api.zoomIn, "-": api.zoomOut, "_": api.zoomOut, "0": api.zoomReset, f: api.fit, F: api.fit }[event.key];
      if (!action) return;
      event.preventDefault();
      action();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [paneOpen, closeDetails]);

  const centerNode = centerId ? nodes.find((node) => node.id === centerId) : null;
  const selectNode = useCallback((node) => {
    if (!node?.fold) { setFocusedNode(node); return; }
    setFocusedNode(null);
    updateSession((current) => ({ ...current, unfolded: [...new Set([...(current.unfolded || []), node.id])] }));
  }, [updateSession]);
  const inside = folded ? ` · ${formatCount(folded.folded)} folded` : overviewMode && explorer.hiddenCount ? ` · ${formatCount(explorer.hiddenCount)} inside` : "";
  const summary = loading && !graph ? "Loading graph…" : `${formatCount(canvasNodes.length)} ${canvasNodes.length === 1 ? "object" : "objects"}${inside} · ${formatCount(canvasEdges.length)} ${canvasEdges.length === 1 ? "link" : "links"}`;
  const summaryDetail = [
    overviewMode && explorer.hiddenCount ? `${explorer.hiddenCount} in collapsed groups` : "",
    hiddenTypes.length && typedNodes.length !== (versioned ? versioned.nodes : nodes).length ? `${(versioned ? versioned.nodes : nodes).length - typedNodes.length} hidden by type` : "",
    laned ? `${typedNodes.length - lanedNodes.length} in lanes switched off` : "",
    versioned?.grouped ? `${nodes.length - versioned.nodes.length} version copies folded` : "",
    `${nodes.length} of ${graph?.total_nodes ?? 0} matching objects loaded`,
  ].filter(Boolean).join(" · ");
  const evidenceShown = canvasEdges.some((edge) => String(edge.evidence_class || "FACT").toUpperCase() !== "FACT");

  return <div className="graph-page">
    <div className="graph-toolbar" data-ui-actions="">
      <div className="graph-search"><Search aria-hidden="true" /><Input type="search" aria-label="Filter graph objects" value={query} onChange={(event) => { updateSession({ query: event.target.value }); setFocusedNode(null); }} onKeyDown={(event) => { if (event.key === "Escape") { event.preventDefault(); if (query) { updateSession({ query: "" }); setFocusedNode(null); } else { event.target.blur(); } } }} placeholder="Find an object…" spellCheck={false} autoComplete="off" /></div>
      <Tabs controls="graph-canvas" value={viewMode} onValueChange={changeView}>
        <TabsList aria-label="Graph view">
          <TabsTrigger value="overview" title="Owners first: expand a group to see what is inside">Containers</TabsTrigger>
          <TabsTrigger value="connections" disabled={!centerId && !focusedNode} title="One object and what it connects to (double-click an object)">Neighbourhood</TabsTrigger>
          <TabsTrigger value="full" title="Every loaded object in lineage lanes: model › tables › columns › calculations › visuals › pages › reports">Lineage flow</TabsTrigger>
          <TabsTrigger value="matrix" title="Which model objects each visual uses, directly or through other calculations">Field usage</TabsTrigger>
        </TabsList>
      </Tabs>
      <span className="toolbar-divider" aria-hidden="true" />
      {isNarrow ? (
        <ViewPopover
          nodes={nodes} hiddenTypes={hiddenTypes} colors={colors} onTypesChange={(next) => updateSession({ hiddenTypes: next })}
          direction={direction} showLabels={showLabels} includeSuggestions={filters.status !== "factual"} grouped={grouped} canGroup={!overviewMode} versions={graphSession.groupVersions} canVersion={lanesView} relatedOnly={relatedOnly} onDisplayChange={changeDisplay}
          filters={filters} depth={depth} centerId={centerId} overview={overview} edgeTypes={edgeTypes} activeCount={activeFilters} hasFilters={hasFilters}
          onFilters={updateFilters}
          onScope={(change) => { updateSession((current) => ({ ...current, centerId: "", filters: { ...current.filters, ...change } })); setFocusedNode(null); }}
          onDepth={(value) => { updateSession({ depth: value }); setFocusedNode(null); }}
          onResetFilters={reset}
        />
      ) : (
        <>
          <TypesPopover nodes={nodes} hiddenTypes={hiddenTypes} colors={colors} onChange={(next) => { updateSession({ hiddenTypes: next }); }} />
          <DisplayPopover direction={direction} showLabels={showLabels} includeSuggestions={filters.status !== "factual"} grouped={grouped} canGroup={!overviewMode} versions={graphSession.groupVersions} canVersion={lanesView} relatedOnly={relatedOnly} onChange={changeDisplay} />
          <FiltersPopover filters={filters} depth={depth} centerId={centerId} overview={overview} edgeTypes={edgeTypes} activeCount={activeFilters} hasFilters={hasFilters}
            onFilters={updateFilters}
            onScope={(change) => { updateSession((current) => ({ ...current, centerId: "", filters: { ...current.filters, ...change } })); setFocusedNode(null); }}
            onDepth={(value) => { updateSession({ depth: value }); setFocusedNode(null); }}
            onReset={reset} />
        </>
      )}
      {centerNode ? <div className="graph-center" data-slot="focus-chip">
        <Crosshair aria-hidden="true" /><span className="graph-center-label">Focused view</span>
        <span className="graph-center-name" translate="no" title={objectName(centerNode)}>{objectName(centerNode)}</span>
        <span className="graph-center-actions">
          <Button variant="ghost" size="xs" disabled={loading || depth >= 4} onClick={() => updateSession({ depth: Math.min(depth + 1, 4) })} title={`Showing ${depth} ${depth === 1 ? "step" : "steps"} away`}><Plus />Expand connections</Button>
          <Button variant="ghost" size="xs" onClick={() => { updateSession({ centerId: "" }); setFocusedNode(null); }}>Back to project</Button>
        </span>
      </div> : null}
      <span className="graph-toolbar-spacer" />
      <span className="graph-summary" role="status" aria-live="polite" data-ui-number="" title={summaryDetail}>{summary}<span className="sr-only">{summaryDetail ? `. ${summaryDetail}` : ""}</span></span>
      <Button variant="ghost" size="sm" aria-label="Fit view" tooltip="Fit view (F)" disabled={!canvasNodes.length} onClick={() => canvasApi.current?.fit()}><Maximize />Fit</Button>
    </div>
    {lanesView ? <LaneChips nodes={versioned ? versioned.nodes : nodes} hidden={hiddenLanes} matrix={viewMode === "matrix"} colors={colors} onChange={(next) => { updateSession({ hiddenLanes: next }); setFocusedNode(null); }} /> : null}
    <div className="graph-body">
      <div id="graph-canvas" className="graph-canvas-card" data-slot="card" aria-busy={loading} style={docked ? { marginRight: DETAIL_PANE_WIDTH + 8 } : undefined}>
        {viewMode === "matrix" ? <ImpactMatrix graph={graph} error={error} onRetry={loadGraph} query={query} hiddenLanes={hiddenLanes} groupVersions={graphSession.groupVersions} colors={colors} selectedId={focusedNode?.id} onSelect={setFocusedNode} />
          : error ? <div className="graph-empty" role="alert"><span className="empty-icon tone-bad" aria-hidden="true"><TriangleAlert /></span><h3>Graph unavailable</h3><p>{error}</p><Button variant="outline" onClick={loadGraph}>Retry graph</Button></div>
          : !graph ? <div className="graph-empty graph-loading" role="status"><p>Loading graph…</p></div>
          : canvasNodes.length ? <GraphCanvas key={canvasKey} rawById={rawById} apiRef={canvasApi} overview={overviewMode} full={viewMode === "full"} grouped={!overviewMode && grouped} onCenter={center} onInspect={inspect} nodes={canvasNodes} edges={canvasEdges} layoutEdges={layoutEdges} undrawn={undrawn} relatedOnly={relatedOnly} selectedId={focusedNode?.id || centerId} docked={docked} warningIds={warningIds} direction={direction} showLabels={showLabels} colors={colors} onSelect={selectNode} onToggleGroup={toggleGroup} viewport={graphSession.viewports[canvasKey]} onViewportChange={saveViewport} placements={graphSession.placements[canvasKey]} onPlacementsChange={savePlacements} />
          : <div className="graph-empty"><span className="empty-icon" aria-hidden="true"><Search /></span><h3>{hasFilters || overview?.counts?.objects ? "No matching objects" : "No sources scanned yet"}</h3><p>{hasFilters ? "Try another filter or clear the filters." : "Scan project sources to see their relationships."}</p>{hasFilters ? <Button variant="outline" onClick={reset}>Clear filters</Button> : null}</div>}
        <div className="graph-overlay graph-overlay-top" data-ui-actions="">
          {overviewMode && graphSession.expandedIds != null && explorer.collapsedCount < explorer.nodes.filter((node) => node.explorerChildCount > 0).length ? <Button variant="outline" size="xs" className="graph-overlay-button" onClick={() => updateSession({ expandedIds: null })}><ChevronsDownUp />Collapse all</Button> : null}
          {viewMode === "full" && graphSession.unfolded.length ? <Button variant="outline" size="xs" className="graph-overlay-button" onClick={() => updateSession({ unfolded: [] })}><ChevronsDownUp />Fold all</Button> : null}
          {graph?.truncated && viewMode !== "matrix" && !wholeScope(graphSession) ? <div className="scope-notice">Showing {graph.nodes.length} of {graph.total_nodes} objects{limit < 1000 ? <> · <Button variant="link" size="xs" onClick={() => updateSession({ limit: Math.min(limit * 2, 1000) })}>Show more</Button></> : null}</div> : null}
        </div>
        {evidenceShown && viewMode !== "matrix" ? <div className="graph-overlay graph-overlay-key"><ProvenanceLegend /></div> : null}
      </div>
      <GraphDetails node={focusedNode} settled={paneSettled} colors={colors} transport={transport} onClose={closeDetails} onSelect={setFocusedNode} onCenter={center} onInspect={inspect} />
    </div>
  </div>;
}

// ---------- Canvas -----------------------------------------------------------

let measureContext = null;
let measureFamily = "";
function measureName(text) {
  if (typeof document === "undefined") return String(text).length * 7;
  if (!measureContext) {
    measureContext = document.createElement("canvas").getContext("2d");
    measureFamily = getComputedStyle(document.body).fontFamily || "sans-serif";
  }
  if (!measureContext) return String(text).length * 7;
  measureContext.font = `500 13px ${measureFamily}`;
  return measureContext.measureText(text).width;
}

// Room for the name inside a node (app.css .flow-node): border, padding, the 24px type chip and its gap,
// plus the 24px group toggle or the 16px status glyph with their gaps.
function nameRoom(width, isGroup, hasStatus) {
  const chrome = isGroup ? 2 + 11 + 24 + 8 + 8 + 24 + 8 : 2 + 3 + 24 + 8 + 10;
  return width - chrome - (hasStatus ? 24 : 0);
}

// Room for the "×2" / "1/2" version badge and its gap.
const versionRoom = (node) => (node?.familySize > 1 ? 34 : 0) + (node?.fold ? 14 + String(node.foldCount).length * 7 + 22 : 0);

const SIDES = {
  LR: { forward: [Position.Right, Position.Left], backward: [Position.Left, Position.Right], same: [Position.Right, Position.Right] },
  TB: { forward: [Position.Bottom, Position.Top], backward: [Position.Top, Position.Bottom], same: [Position.Bottom, Position.Bottom] },
};

function anchor(rect, side) {
  if (side === Position.Right) return { x: rect.x + rect.width, y: rect.y + rect.height / 2 };
  if (side === Position.Left) return { x: rect.x, y: rect.y + rect.height / 2 };
  if (side === Position.Bottom) return { x: rect.x + rect.width / 2, y: rect.y + rect.height };
  return { x: rect.x + rect.width / 2, y: rect.y };
}

// Orthogonal, rounded routing between two boxes. Forward links leave the trailing side, links that point
// back leave the leading side, and links within one rank loop outward instead of crossing their neighbours.
function edgeGeometry(source, target, direction, offset) {
  const horizontal = direction !== "TB";
  const sides = SIDES[horizontal ? "LR" : "TB"];
  if (source === target) {
    const out = anchor(source, sides.same[0]);
    const lift = horizontal ? { x: 0, y: source.height * 0.3 } : { x: source.width * 0.3, y: 0 };
    const reach = 28 + offset;
    const path = horizontal
      ? `M ${out.x} ${out.y - lift.y} h ${reach - 6} q 6 0 6 6 v ${2 * lift.y - 12} q 0 6 -6 6 h ${-(reach - 6)}`
      : `M ${out.x - lift.x} ${out.y} v ${reach - 6} q 0 6 6 6 h ${2 * lift.x - 12} q 6 0 6 -6 v ${-(reach - 6)}`;
    return { path, labelX: horizontal ? out.x + reach : out.x, labelY: horizontal ? out.y : out.y + reach };
  }
  const gap = 8;
  const ahead = horizontal ? target.x >= source.x + source.width + gap : target.y >= source.y + source.height + gap;
  const behind = horizontal ? target.x + target.width <= source.x - gap : target.y + target.height <= source.y - gap;
  const [sourcePosition, targetPosition] = ahead ? sides.forward : behind ? sides.backward : sides.same;
  const start = anchor(source, sourcePosition);
  const end = anchor(target, targetPosition);
  const [path, labelX, labelY] = getSmoothStepPath({ sourceX: start.x, sourceY: start.y, sourcePosition, targetX: end.x, targetY: end.y, targetPosition, borderRadius: 8, offset: 20 + offset });
  const shiftY = horizontal && offset ? (offset % 2 === 0 ? 1 : -1) * (14 + offset * 1.5) : 0;
  const shiftX = !horizontal && offset ? (offset % 2 === 0 ? 1 : -1) * (14 + offset * 1.5) : 0;
  return { path, labelX: labelX + shiftX, labelY: labelY + shiftY };
}

function GraphCanvas({ rawById, apiRef, overview, full, grouped, onCenter, onInspect, nodes, edges, layoutEdges = edges, undrawn = null, relatedOnly = false, selectedId, docked, warningIds, direction, showLabels, colors, onSelect, onToggleGroup, viewport, onViewportChange, placements, onPlacementsChange }) {
  const [flow, setFlow] = useState(null);
  const [zoom, setZoom] = useState(viewport?.zoom || 1);
  const [tier, setTier] = useState(() => zoomTier(viewport?.zoom || 1));
  const [labelsReadable, setLabelsReadable] = useState(() => (viewport?.zoom || 1) >= LABEL_ZOOM);
  const far = tier === "far";
  const scale = nameScale(tier);
  // Names are shortened by measured width, so measure again once the UI font has loaded.
  const [fontsReady, setFontsReady] = useState(() => typeof document === "undefined" || document.fonts?.status !== "loading");
  useEffect(() => {
    if (fontsReady || !document.fonts?.ready) return undefined;
    let active = true;
    document.fonts.ready.then(() => { if (active) setFontsReady(true); });
    return () => { active = false; };
  }, [fontsReady]);
  const wrapper = useRef(null);
  const initialViewport = useRef(viewport);
  const previousPositions = useRef(new Map(Object.entries(placements || {})));
  // Owners of one type share one width: the widest name of that type, up to NAME_WIDTH_MAX, so a name is
  // not cut while there is room and the columns stay aligned.
  const ownerWidths = useMemo(() => {
    const widths = new Map();
    if (!overview) return widths;
    nodes.forEach((node) => {
      const isGroup = node.explorerChildCount > 0;
      const base = isGroup ? GROUP_WIDTH : NODE_WIDTH;
      const wanted = Math.ceil(measureName(objectName(node)) + base - nameRoom(base, isGroup, false) + 12);
      const key = `${node.type}:${isGroup}`;
      widths.set(key, Math.min(NAME_WIDTH_MAX, Math.max(widths.get(key) || (isGroup ? GROUP_COUNTS_WIDTH : base), wanted)));
    });
    return widths;
    // fontsReady: names are measured again once the UI font has loaded.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [overview, nodes, fontsReady]);
  const sizeOf = useCallback((node) => {
    if (!overview) return { width: NODE_WIDTH, height: NODE_HEIGHT };
    const isGroup = node.explorerChildCount > 0;
    return { width: ownerWidths.get(`${node.type}:${isGroup}`) || (isGroup ? GROUP_WIDTH : NODE_WIDTH), height: isGroup ? GROUP_HEIGHT : NODE_HEIGHT };
  }, [overview, ownerWidths]);
  // Lineage lanes (Model › Tables › Columns › Calculations › Visuals › … › Reports) for every view except Overview.
  const lineage = !overview && !grouped;
  const layout = useMemo(() => {
    if (lineage) return { ...layoutLineage(nodes, edges, direction, { measure: measureName, badge: versionRoom }), groups: [] };
    if (!overview) return grouped ? layoutArtifactGraph(nodes, edges, direction, sizeOf) : { ...layoutGraph(nodes, edges, direction, sizeOf), groups: [] };
    // A small picture keeps every placed object where it was and adds new ones around them. A large one is
    // laid out afresh, in lineage order, and the viewport holds the opened owner still instead (see pin).
    const fresh = nodes.length > AUTO_COLLAPSE_ABOVE;
    const next = layoutExplorerGraph(nodes, layoutEdges, direction, fresh ? null : previousPositions.current, sizeOf, { reportsLast: fresh });
    previousPositions.current = new Map(next.nodes.map(({ node, position }) => [node.id, position]));
    return { ...next, groups: [] };
    // fontsReady: lane widths follow measured names.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes, layoutEdges, direction, grouped, overview, sizeOf, lineage, fontsReady]);
  useEffect(() => {
    if (overview) onPlacementsChange(Object.fromEntries(previousPositions.current));
  }, [layout, overview, onPlacementsChange]);
  const rects = useMemo(() => new Map(layout.nodes.map(({ node, position, width, height }) => [node.id, { x: position.x, y: position.y, width: width || NODE_WIDTH, height: height || NODE_HEIGHT }])), [layout]);
  // Links drawn: the laid-out ones, plus in Overview the links a selection brings in.
  const drawnEdges = useMemo(() => {
    if (edges === layoutEdges) return layout.edges;
    const laidOut = new Set(layoutEdges);
    const kept = undrawn ? layout.edges.filter(({ edge }) => !undrawn.has(edge.id)) : layout.edges;
    return [...kept, ...edges.filter((edge) => !laidOut.has(edge) && rects.has(edge.from_id) && rects.has(edge.to_id)).map((edge) => ({ edge }))];
  }, [edges, layoutEdges, layout, rects, undrawn]);
  const bundleLabels = useMemo(() => edges.reduce((count, edge) => count + (edge.bundle ? 1 : 0), 0) <= BUNDLE_LABELS, [edges]);
  const byId = useMemo(() => new Map(nodes.map((node) => [node.id, node])), [nodes]);
  const reduced = prefersReducedMotion();
  const fitDuration = reduced ? 0 : 320;
  const stepDuration = reduced ? 0 : 180;
  const nodeCount = layout.nodes?.length || nodes.length;
  const minFitZoom = nodeCount <= 6 ? 1.0 : nodeCount <= 20 ? 0.85 : (full ? 0.75 : READABLE_ZOOM);
  const fitOptions = useMemo(() => ({ padding: 0.15, minZoom: minFitZoom, maxZoom: 1 }), [minFitZoom]);

  // Pan just enough to bring a node into the visible canvas; zoom never changes.
  const reveal = useCallback((id, duration = fitDuration) => {
    const rect = rects.get(id);
    if (!flow || !rect || !wrapper.current) return;
    const bounds = wrapper.current.getBoundingClientRect();
    const { x, y, zoom: scale } = flow.getViewport();
    const left = rect.x * scale + x, top = rect.y * scale + y;
    const right = left + rect.width * scale, bottom = top + rect.height * scale;
    const margin = 48;
    // The smallest pan that brings the node inside the margin, so the rest of the picture moves as little as possible.
    const shift = (start, end, size) => start < margin ? margin - start : end > size - margin ? Math.max(size - margin - end, margin - start) : 0;
    const dx = shift(left, right, bounds.width);
    const dy = shift(top, bottom, bounds.height);
    if (!dx && !dy) return;
    flow.setViewport({ x: x + dx, y: y + dy, zoom: scale }, travel(duration));
  }, [flow, rects, fitDuration]);
  // The canvas re-fits only when the pane docks or closes, never on a plain selection: re-fitting a large
  // picture on every click moved everything under the pointer and made nodes flicker in and out (issue #53).
  // Large pictures keep their zoom and only pan the selection into view.
  const large = layout.nodes.length > VIEWPORT_ONLY_ABOVE;
  const latest = useRef(null);
  // Whether the whole picture is readable in the canvas as it is now.
  const fitsWhole = () => {
    const bounds = wrapper.current?.getBoundingClientRect();
    if (!bounds || !rects.size) return true;
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    rects.forEach((rect) => { minX = Math.min(minX, rect.x); minY = Math.min(minY, rect.y); maxX = Math.max(maxX, rect.x + rect.width); maxY = Math.max(maxY, rect.y + rect.height); });
    return (maxX - minX) * minFitZoom <= bounds.width * 0.9 && (maxY - minY) * minFitZoom <= bounds.height * 0.9;
  };
  latest.current = { flow, reveal, fitOptions, fitDuration, selectedId, large, fitsWhole, fit: () => flow?.fitView({ ...fitOptions, ...travel(fitDuration) }) };
  const wasDocked = useRef(docked);
  useEffect(() => {
    if (wasDocked.current === docked) return undefined;
    wasDocked.current = docked;
    const timer = setTimeout(() => {
      const current = latest.current;
      if (current.large || !current.fitsWhole()) { if (docked && current.selectedId) current.reveal(current.selectedId); }
      else current.fit();
    }, 40);
    return () => clearTimeout(timer);
  }, [docked]);
  // While docked, a newly selected object is panned into view if the pane covers it.
  useEffect(() => {
    if (!docked || !selectedId) return undefined;
    const timer = setTimeout(() => latest.current.reveal(selectedId), 40);
    return () => clearTimeout(timer);
  }, [docked, selectedId]);

  // Lineage and Containers read from the left: when the picture cannot fit at a readable zoom, open at Models (top-left)
  // instead of the middle of the picture. Estimated from the window, since the canvas is not measured yet.
  const leftAnchor = useMemo(() => {
    if ((!lineage && !overview) || initialViewport.current || !layout.nodes.length || typeof window === "undefined") return null;
    const xs = layout.nodes.map(({ position }) => position.x), ys = layout.nodes.map(({ position }) => position.y);
    const minX = Math.min(...xs), minY = Math.min(...ys) - 48;
    const spanX = Math.max(...layout.nodes.map(({ position, width }) => position.x + (width || NODE_WIDTH))) - minX;
    const spanY = Math.max(...layout.nodes.map(({ position, height }) => position.y + (height || NODE_HEIGHT))) - minY;
    const fitZoom = Math.min(1, (window.innerWidth - 300) / spanX, (window.innerHeight - 260) / spanY);
    return fitZoom < minFitZoom ? { x: 24 - minX * minFitZoom, y: 24 - minY * minFitZoom, zoom: minFitZoom } : null;
    // Only for the first paint of this canvas.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  // The owner being opened or closed stays under the pointer while the picture is laid out again.
  const pinned = useRef(null);
  useLayoutEffect(() => {
    const pin = pinned.current;
    pinned.current = null;
    const now = pin && rects.get(pin.id);
    if (!now || !flow) return;
    const { x, y, zoom: scale } = flow.getViewport();
    const dx = (now.x - pin.rect.x) * scale, dy = (now.y - pin.rect.y) * scale;
    if (dx || dy) flow.setViewport({ x: x - dx, y: y - dy, zoom: scale });
  }, [rects, flow]);
  // Fit: the whole picture when it is readable at that size; else fit the width and start at the top-left,
  // where the lanes begin. A tall picture is never centred on its middle.
  const fit = useCallback(() => {
    const bounds = wrapper.current?.getBoundingClientRect();
    if (!flow || !bounds || !rects.size) return;
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    rects.forEach((rect) => { minX = Math.min(minX, rect.x); minY = Math.min(minY, rect.y); maxX = Math.max(maxX, rect.x + rect.width); maxY = Math.max(maxY, rect.y + rect.height); });
    const header = lineage ? 48 : 0;
    const spanX = maxX - minX, spanY = maxY - minY + header;
    const whole = Math.min(1, bounds.width * 0.9 / spanX, bounds.height * 0.9 / spanY);
    if (whole >= minFitZoom || (!lineage && !overview)) { flow.fitView({ ...fitOptions, ...travel(fitDuration) }); return; }
    const scale = Math.max(minFitZoom, Math.min(1, (bounds.width - 48) / spanX));
    flow.setViewport({ x: 24 - minX * scale, y: 24 - (minY - header) * scale, zoom: scale }, travel(fitDuration));
  }, [flow, fitOptions, fitDuration, rects, lineage, overview, minFitZoom]);
  useEffect(() => {
    if (!apiRef) return undefined;
    apiRef.current = {
      fit,
      pin: (id) => { pinned.current = rects.has(id) ? { id, rect: rects.get(id) } : null; },
      settle: (id) => {
        const bounds = wrapper.current?.getBoundingClientRect();
        if (!flow || !bounds) return;
        let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
        rects.forEach((rect) => { minX = Math.min(minX, rect.x); minY = Math.min(minY, rect.y); maxX = Math.max(maxX, rect.x + rect.width); maxY = Math.max(maxY, rect.y + rect.height); });
        const fits = (maxX - minX) * minFitZoom <= bounds.width * 0.9 && (maxY - minY) * minFitZoom <= bounds.height * 0.9;
        if (fits) fit(); else reveal(id);
      },
      zoomIn: () => flow?.zoomIn(travel(stepDuration)),
      zoomOut: () => flow?.zoomOut(travel(stepDuration)),
      zoomReset: () => flow?.zoomTo(1, travel(stepDuration)),
    };
    return () => { apiRef.current = null; };
  }, [apiRef, fit, flow, stepDuration, rects, minFitZoom, reveal]);

  // In lineage lanes a selection lights its whole chain: what feeds it and everything it feeds, to the report.
  const trace = useMemo(() => lineage && selectedId ? lineageOf(selectedId, drawnEdges) : null, [lineage, selectedId, drawnEdges]);
  const connected = useMemo(() => {
    if (trace) return trace.ids;
    const ids = new Set([selectedId]);
    edges.forEach((edge) => {
      if (edge.from_id === selectedId || edge.to_id === selectedId) { ids.add(edge.from_id); ids.add(edge.to_id); }
    });
    return ids;
  }, [edges, selectedId, trace]);
  const focusing = Boolean(selectedId) && rects.has(selectedId);
  // Trace layout: when a selection hides everything unrelated, what is left is packed in its lanes around
  // the selected object, which keeps its exact place. The big layout is never recomputed (issue #53): this
  // is a second, small one shown over it, and clearing the selection puts everything back.
  const packed = useMemo(() => {
    if (!lineage || !relatedOnly || !focusing || !trace || connected.size >= layout.nodes.length) return null;
    const members = layout.nodes.filter(({ node }) => connected.has(node.id)).map(({ node }) => node);
    const links = edges.filter((edge) => connected.has(edge.from_id) && connected.has(edge.to_id));
    const small = layoutLineage(members, links, direction, { measure: measureName, badge: versionRoom });
    const own = small.nodes.find(({ node }) => node.id === selectedId);
    const home = rects.get(selectedId);
    if (!own || !home) return null;
    const horizontal = direction !== "TB";
    const shift = horizontal ? home.y - own.position.y : home.x - own.position.x;
    return new Map(small.nodes.map(({ node, position, height }) => {
      const rect = rects.get(node.id);
      return [node.id, horizontal ? { ...rect, y: position.y + shift, height: height || rect.height } : { ...rect, x: position.x + shift }];
    }));
    // fontsReady: names are measured again once the UI font has loaded.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lineage, relatedOnly, focusing, trace, connected, layout, edges, direction, rects, selectedId, fontsReady]);

  // Everything that does not depend on the selection is built once per layout; a selection only
  // re-decorates the nodes it changes, so a click on a large picture stays cheap (issue #53).
  const baseNodes = useMemo(() => [
    ...(layout.lanes || []).map((lane) => ({ id: `lane:${lane.key}`, type: "lane", position: { x: lane.x, y: lane.y }, width: lane.width, height: 28, measured: { width: lane.width, height: 28 }, selectable: false, focusable: false, draggable: false, style: { width: lane.width, pointerEvents: "none" }, data: lane })),
    ...layout.groups.map((group) => ({ id: group.id, type: "artifactGroup", position: group.position, width: group.width, height: group.height, measured: { width: group.width, height: group.height }, zIndex: -1, selectable: false, focusable: false, draggable: false, style: { width: group.width, height: group.height, pointerEvents: "none" }, data: { ...group, color: colors.groups[group.key] } })),
    ...layout.nodes.map(({ node, lines }) => {
      const rect = rects.get(node.id);
      const twoLine = lines === 2 && rect.height >= TWO_LINE_HEIGHT;
      const warning = warningIds.has(node.id) || node.type === "CONFLICT";
      const isGroup = overview && node.explorerChildCount > 0;
      const statusGlyph = warning || Boolean(STATUS_GLYPHS[node.status]);
      return {
        id: node.id, type: "brain", position: { x: rect.x, y: rect.y }, selected: false,
        width: rect.width, height: rect.height,
        // Default node ariaRole: "button"; group nodes use role="group" to avoid nested-interactive violations with toggle button.
        ariaRole: isGroup ? "group" : "button", ariaLabel: nodeLabel(node, warning, isGroup),
        // Cards have fixed dimensions. Preserve React Flow's measured/handle
        // state when controlled nodes are replaced after saving the session.
        measured: { width: rect.width, height: rect.height },
        className: "",
        // Two-line names are shortened to what two lines hold, with a little slack for word wrapping.
        data: { node, direction, isGroup, onToggleGroup, onCenter, onInspect, warning, twoLine, versions: versionNote(node, rawById), color: artifactColor(node, colors), colors, displayName: middleEllipsis(objectName(node), (twoLine ? 1.8 : 1) * (nameRoom(rect.width, isGroup, statusGlyph) - versionRoom(node)) / scale, measureName) },
      };
    }),
    // fontsReady: names are measured again once the UI font has loaded.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  ], [layout, rects, warningIds, overview, direction, onToggleGroup, onCenter, onInspect, colors, fontsReady, scale, rawById]);
  const flowNodes = useMemo(() => baseNodes.map((item) => {
    if (item.type !== "brain") return item;
    const selected = item.id === selectedId;
    const related = !focusing || connected.has(item.id);
    const place = related ? packed?.get(item.id) : null;
    if (!selected && related && !place) return item;
    return { ...item, selected, className: related ? "" : "is-dimmed", hidden: !related && relatedOnly, ...(place ? { position: { x: place.x, y: place.y } } : {}) };
  }), [baseNodes, selectedId, focusing, connected, relatedOnly, packed]);
  const laneCount = layout.lanes?.length || 0;

  const baseEdges = useMemo(() => {
    const pairCount = new Map();
    return drawnEdges.map(({ edge, from = edge.from_id, to = edge.to_id }) => {
      const pair = [edge.from_id, edge.to_id].sort().join("\u0000");
      const index = pairCount.get(pair) || 0;
      pairCount.set(pair, index + 1);
      const evidenceClass = String(edge.evidence_class || "FACT").toUpperCase();
      const warning = edge.type === "CONFLICTS_WITH";
      const structure = STRUCTURE_EDGES.has(edge.type);
      // Lineage draws every link in flow direction (left → right), so arrows read "flows into".
      const geometry = edgeGeometry(rects.get(from), rects.get(to), direction, index * 10);
      return {
        edge, structure, warning,
        classes: ["flow-edge", evidenceClass.toLowerCase(), structure ? "is-structure" : "", warning ? "warning" : "", edge.bundle ? "is-bundle" : ""].filter(Boolean),
        flow: {
          id: edge.id, source: from, target: to, type: "routed",
          label: edge.bundle ? formatCount(edge.count) : typeLabel(edge.type),
          ariaLabel: edge.bundle
            ? `${formatCount(edge.count)} links between ${objectName(byId.get(edge.from_id))} and ${objectName(byId.get(edge.to_id))}`
            : `${objectName(byId.get(edge.from_id))} ${typeLabel(edge.type)} ${objectName(byId.get(edge.to_id))}`,
          // A bundle is as heavy as what it stands for: 1 link is a hairline, thousands are a band.
          ...(edge.bundle ? { style: { strokeWidth: 1 + Math.min(3, Math.log10(edge.count)) } } : {}),
          data: geometry,
        },
      };
    });
  }, [drawnEdges, rects, byId, direction]);
  const flowEdges = useMemo(() => baseEdges.map(({ edge, structure, warning, classes, flow: base }) => {
    const onPath = trace ? trace.edgeIds.has(edge.id) : Boolean(selectedId) && (edge.from_id === selectedId || edge.to_id === selectedId);
    const tone = onPath ? "var(--brand)" : warning ? "var(--warn)" : "var(--graph-edge)";
    // A link is drawn only between two objects that are shown: no loose ends when a selection hides the rest.
    const loose = focusing && relatedOnly && !(connected.has(base.source) && connected.has(base.target));
    const moved = !loose && packed && packed.has(base.source) && packed.has(base.target);
    return {
      ...base,
      ...(loose ? { hidden: true } : {}),
      ...(moved ? { data: edgeGeometry(packed.get(base.source), packed.get(base.target), direction, 0) } : {}),
      className: [...classes, onPath ? "on-path" : "", focusing && !onPath ? "is-dimmed" : "", (showLabels || (edge.bundle && (bundleLabels || onPath)) || (onPath && !structure && drawnEdges.length <= 12)) ? "show-label" : ""].filter(Boolean).join(" "),
      markerEnd: edge.bundle || (structure && !onPath) ? undefined : { type: MarkerType.ArrowClosed, color: tone, width: onPath ? 4 : 5.5, height: onPath ? 4 : 5.5 },
      // A link passes behind the objects between its ends, never across their names. Links on the
      // selected path are listed last, so they are drawn over the other links.
      zIndex: 0,
      onPath,
    };
  }).sort((left, right) => Number(left.onPath) - Number(right.onPath)).map(({ onPath, ...flow }) => flow), [baseEdges, drawnEdges, selectedId, focusing, showLabels, trace, bundleLabels, relatedOnly, connected, packed, direction]);

  // Arrow keys move to the connected object that lies in that direction (else the nearest object there).
  const step = useCallback((fromId, key) => {
    const from = rects.get(fromId);
    if (!from) return null;
    const vector = { ArrowRight: [1, 0], ArrowLeft: [-1, 0], ArrowDown: [0, 1], ArrowUp: [0, -1] }[key];
    const origin = { x: from.x + from.width / 2, y: from.y + from.height / 2 };
    const score = (id) => {
      const rect = rects.get(id);
      if (!rect || id === fromId) return Infinity;
      const dx = rect.x + rect.width / 2 - origin.x;
      const dy = rect.y + rect.height / 2 - origin.y;
      const along = dx * vector[0] + dy * vector[1];
      if (along <= 1) return Infinity;
      return along + 2 * Math.abs(dx * vector[1] - dy * vector[0]);
    };
    const best = (ids) => ids.reduce((winner, id) => { const value = score(id); return value < winner.value ? { id, value } : winner; }, { id: null, value: Infinity }).id;
    const neighbours = [...new Set(edges.flatMap((edge) => edge.from_id === fromId ? [edge.to_id] : edge.to_id === fromId ? [edge.from_id] : []))];
    return best(neighbours) || best([...rects.keys()]);
  }, [rects, edges]);
  const focusNode = (id) => wrapper.current?.querySelector(`.react-flow__node[data-id="${globalThis.CSS?.escape ? CSS.escape(id) : id}"]`)?.focus({ preventScroll: true });
  const onKeyDown = (event) => {
    if (event.defaultPrevented || event.ctrlKey || event.metaKey || event.altKey) return;
    const element = event.target?.closest?.(".react-flow__node-brain");
    if (!element || event.target.closest(".graph-group-toggle")) return;
    const node = byId.get(element.dataset.id);
    if (!node) return;
    if (event.key.startsWith("Arrow")) {
      const next = step(node.id, event.key);
      event.preventDefault();
      if (!next) return;
      onSelect(byId.get(next));
      focusNode(next);
      reveal(next, stepDuration);
    } else if (event.key === "Enter") {
      event.preventDefault();
      if (node.id === selectedId) onInspect(node.id); else onSelect(node);
    } else if (event.key === " ") {
      event.preventDefault();
      if (overview && node.explorerChildCount > 0) onToggleGroup(node.id); else onSelect(node);
    }
  };

  const onMove = useCallback((_, next) => { setTier(zoomTier(next.zoom)); setLabelsReadable(next.zoom >= LABEL_ZOOM); }, []);
  const [hoverId, setHoverId] = useState(null);
  const farLabels = far ? [...new Set([selectedId, hoverId])].filter((id) => id && rects.has(id)).map((id) => ({ id, rect: rects.get(id), node: byId.get(id) })) : [];
  // A minimap of a tall strip of lanes is a line: it only helps when the picture has two real dimensions.
  const showMinimap = flowNodes.length - laneCount > MINIMAP_ABOVE && (!lineage || layout.nodes.length <= VIEWPORT_ONLY_ABOVE);
  return <div ref={wrapper} className={`flow-wrap artifact-flow ${overview ? "explorer-flow" : ""} ${far ? "is-far" : scale !== 1 ? "is-mid" : ""} ${labelsReadable ? "" : "labels-off"} ${focusing ? "is-focusing" : ""}`} style={{ "--name-scale": scale }} role="region" aria-label="Directed project graph" aria-roledescription="graph" onKeyDown={onKeyDown}>
    <ReactFlow onInit={(instance) => {
      setFlow(instance);
      const current = instance.getZoom(); setZoom(current); setTier(zoomTier(current)); setLabelsReadable(current >= LABEL_ZOOM);
    }} nodes={flowNodes} edges={flowEdges} nodeTypes={NODE_RENDERERS} edgeTypes={EDGE_RENDERERS}
      onNodeDoubleClick={(_, node) => { if (node.type === "brain") onCenter(node.data.node); }} onNodeClick={(_, node) => { if (node.type === "brain") onSelect(node.data.node); }} onPaneClick={() => onSelect(null)}
      onNodeMouseEnter={(_, node) => setHoverId(node.id)} onNodeMouseLeave={() => setHoverId(null)}
      onMove={onMove} onMoveEnd={(_, nextViewport) => { setZoom(nextViewport.zoom); onViewportChange(nextViewport); }}
      onlyRenderVisibleElements={flowNodes.length > VIEWPORT_ONLY_ABOVE}
      defaultViewport={initialViewport.current || leftAnchor || undefined} zoomOnDoubleClick={false} fitView={!initialViewport.current && !leftAnchor} fitViewOptions={fitOptions} minZoom={0.2} maxZoom={2}
      panOnScroll zoomOnPinch
      nodesDraggable={false} nodesConnectable={false} edgesFocusable={false} disableKeyboardA11y deleteKeyCode={null} selectionKeyCode={null} multiSelectionKeyCode={null} proOptions={{ hideAttribution: true }}>
      <Background gap={20} size={1.2} color="var(--grid-dot)" />
      {farLabels.length ? <FarLabels items={farLabels} /> : null}
      {laneCount ? <StickyLanes lanes={layout.lanes} /> : null}
      {showMinimap ? <MiniMap pannable zoomable bgColor="var(--surface)" nodeColor={(node) => node.type === "lane" ? "transparent" : node.data?.color || "var(--artifact-other, #94a3b8)"} nodeStrokeColor={(node) => node.type === "lane" ? "transparent" : node.data?.color || "var(--artifact-other, #94a3b8)"} nodeBorderRadius={4} nodeClassName={(node) => node.type === "artifactGroup" ? "minimap-artifact-group" : ""} maskColor="var(--minimap-mask)" style={{ width: 168, height: 112 }} /> : null}
    </ReactFlow>
    <div className="graph-zoom-controls" data-ui-actions="">
      <Button variant="ghost" size="icon-sm" aria-label="Zoom out" tooltip="Zoom out (−)" onClick={() => flow?.zoomOut(travel(stepDuration))}><Minus /></Button>
      <Tooltip content="Reset zoom (0)">
        <button type="button" className="graph-zoom-value" data-ui-number="" aria-label={`Zoom ${Math.round(zoom * 100)} percent. Reset to 100 percent`} onClick={() => flow?.zoomTo(1, travel(stepDuration))}>{Math.round(zoom * 100)}%</button>
      </Tooltip>
      <Button variant="ghost" size="icon-sm" aria-label="Zoom in" tooltip="Zoom in (+)" onClick={() => flow?.zoomIn(travel(stepDuration))}><Plus /></Button>
    </div>
  </div>;
}

// At glyph-only zoom, the hovered and the selected object still get a readable 12px name, in screen space.
function FarLabels({ items }) {
  const { x, y, zoom } = useViewport();
  return items.map(({ id, rect, node }) => <span key={id} className="graph-far-label" aria-hidden="true" translate="no"
    style={{ left: (rect.x + rect.width / 2) * zoom + x, top: rect.y * zoom + y }}>{objectName(node)}</span>);
}

function ArtifactGroup({ data }) {
  return <div className="artifact-group"><span className="artifact-group-title">{ARTIFACT_GROUPS[data.key].label}<span data-ui-number="">{data.count}</span></span></div>;
}

function BrainFlowNode({ data, selected }) {
  const node = data.node;
  const name = objectName(node);
  const suggested = node.status === "candidate" || String(node.evidence_class || "").toUpperCase() === "INFERRED";
  const StatusIcon = data.warning ? TriangleAlert : STATUS_GLYPHS[node.status];
  const vertical = data.direction === "TB";
  const count = node.explorerDescendantCount || 0;
  const stacked = node.familySize > 1 && node.versionCount > 1;
  const insideCounts = COUNT_TYPES.filter((type) => node.explorerTypeCounts?.[type]).slice(0, 3).map((type) => [type, node.explorerTypeCounts[type]]);

  const daxFormula = node.expression || node.properties?.expression || null;

  const handleCopyName = useCallback((event) => {
    event?.stopPropagation?.();
    if (navigator?.clipboard?.writeText) {
      navigator.clipboard.writeText(name);
      toast.success?.(`Copied name "${name}"`);
    }
  }, [name]);

  const handleCopyDax = useCallback((event) => {
    event?.stopPropagation?.();
    if (daxFormula && navigator?.clipboard?.writeText) {
      navigator.clipboard.writeText(daxFormula);
      toast.success?.(`Copied DAX formula for "${name}"`);
    }
  }, [daxFormula, name]);

  const handleInspect = useCallback((event) => {
    event?.stopPropagation?.();
    data.onInspect?.(node.id);
  }, [data, node.id]);

  const handleFocus = useCallback((event) => {
    event?.stopPropagation?.();
    data.onCenter?.(node);
  }, [data, node]);

  return (
    <ContextMenu>
      <ContextMenuTrigger asChild>
        <div className={`flow-node artifact-node ${node.fold ? "is-fold" : ""} ${data.isGroup ? "explorer-group-node" : ""} ${selected ? "selected" : ""} ${suggested ? "is-suggested" : ""} ${data.warning ? "has-warning" : ""} ${data.twoLine ? "is-two-line" : ""} ${stacked ? "is-stack" : ""}`} style={{ "--artifact-color": data.color }} title={node.fold ? `${formatCount(node.foldCount)} ${typeLabel(node.type)} of ${name}. Click to show them.` : `${kindLabel(node)} · ${name}${data.isGroup ? ` · ${count} inside` : ""}${data.versions ? `\n${data.versions}` : ""}`} data-type={node.type}>
          <Handle type="target" position={vertical ? Position.Top : Position.Left} className="flow-handle" isConnectable={false} />
          <TypeGlyph node={node} colors={data.colors} />
          <span className="flow-node-text">
            <span className="flow-node-name" translate="no" aria-hidden={data.displayName !== name || undefined}>{data.displayName}</span>
            {/* The shortened name is for the eye; the full name stays in the text for find-in-page and tests. */}
            {data.displayName !== name ? <span className="sr-only" translate="no">{name}</span> : null}
            {data.isGroup ? <span className="flow-node-meta" data-ui-number="">{insideCounts.length ? insideCounts.map(([type, value]) => <span key={type} className="flow-node-count" title={`${formatCount(value)} ${typeLabel(type)}`}><TypeIcon type={type} />{formatCount(value)}</span>) : `${count} inside`}</span> : null}
          </span>
          {node.fold ? <span className="fold-count" data-ui-number="" aria-hidden="true">{formatCount(node.foldCount)}<ChevronRight /></span> : null}
          <VersionBadge node={node} note={data.versions} />
          {node.type === "MODEL" || node.type === "REPORT" ? <OriginBadge node={node} /> : null}
          {StatusIcon ? <span className={`flow-node-status ${data.warning ? "warning" : node.status}`} aria-hidden="true"><StatusIcon /></span> : null}
          {data.isGroup ? (
            <Tooltip content={`${count} loaded objects inside`}>
              <button
                type="button"
                className="graph-group-toggle nodrag nopan"
                aria-label={`${node.explorerExpanded ? "Collapse" : "Expand"} ${name}`}
                aria-expanded={node.explorerExpanded}
                onMouseDown={(event) => event.stopPropagation()}
                onDoubleClick={(event) => event.stopPropagation()}
                onKeyDown={(event) => event.stopPropagation()}
                onClick={(event) => {
                  event.stopPropagation();
                  data.onToggleGroup(node.id);
                }}
              >
                <ChevronRight aria-hidden="true" />
              </button>
            </Tooltip>
          ) : null}
          <Handle type="source" position={vertical ? Position.Bottom : Position.Right} className="flow-handle" isConnectable={false} />
        </div>
      </ContextMenuTrigger>
      <ContextMenuContent>
        <ContextMenuItem onClick={handleInspect}>
          <Search className="size-3.5" aria-hidden="true" />
          <span>Open in Inspector</span>
        </ContextMenuItem>
        <ContextMenuItem onClick={handleFocus}>
          <Crosshair className="size-3.5" aria-hidden="true" />
          <span>Focus</span>
        </ContextMenuItem>
        <ContextMenuSeparator />
        <ContextMenuItem onClick={handleCopyName}>
          <Copy className="size-3.5" aria-hidden="true" />
          <span>Copy name</span>
        </ContextMenuItem>
        <ContextMenuItem disabled={!daxFormula} onClick={handleCopyDax}>
          <Code className="size-3.5" aria-hidden="true" />
          <span>Copy DAX</span>
        </ContextMenuItem>
      </ContextMenuContent>
    </ContextMenu>
  );
}

function RoutedEdge({ id, data, markerEnd, style, label, interactionWidth }) {
  return <BaseEdge id={id} path={data.path} markerEnd={markerEnd} style={style} label={label} labelX={data.labelX} labelY={data.labelY} labelBgPadding={[6, 3]} labelBgBorderRadius={4} interactionWidth={interactionWidth ?? 16} />;
}

// Lane names stay at the top edge of the canvas once their header has scrolled out of view.
function StickyLanes({ lanes }) {
  const { x, y, zoom } = useViewport();
  const gone = lanes.filter((lane) => lane.y * zoom + y < 4);
  if (!gone.length) return null;
  return <div className="sticky-lanes" aria-hidden="true">{gone.map((lane) => <span key={lane.key} className="sticky-lane" style={{ left: lane.x * zoom + x, width: Math.max(lane.width * zoom, 60) }}><span>{lane.label}</span><span className="lineage-lane-count" data-ui-number="">{formatCount(lane.count)}</span></span>)}</div>;
}

function LaneHeader({ data }) {
  return <div className="lineage-lane"><span>{data.label}</span><span className="lineage-lane-count" data-ui-number="">{formatCount(data.count)}</span></div>;
}

const NODE_RENDERERS = { brain: BrainFlowNode, artifactGroup: ArtifactGroup, lane: LaneHeader };
const EDGE_RENDERERS = { routed: RoutedEdge };
