import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Background, Controls, Handle, MarkerType, MiniMap, Position, ReactFlow } from "@xyflow/react";
import { brainTransport, normalizeSnapshot } from "./transport";
import "@xyflow/react/dist/style.css";

const VIEWS = [
  ["overview", "Overview"],
  ["graph", "Graph"],
  ["inspector", "Inspector"],
  ["review", "Review queue"],
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

function relatedNodeIds(nodes, edges) {
  const preferred = nodes.filter((node) => node.type === "MODEL" || node.type === "REPORT");
  const roots = (preferred.length ? preferred : nodes).slice(0, 2);
  const ids = new Set(roots.map((node) => node.id));
  let frontier = [...ids];
  for (let depth = 0; depth < 2 && frontier.length; depth += 1) {
    const next = [];
    edges.forEach((edge) => {
      if (frontier.includes(edge.from_id) && !ids.has(edge.to_id)) {
        ids.add(edge.to_id);
        next.push(edge.to_id);
      }
      if (frontier.includes(edge.to_id) && !ids.has(edge.from_id)) {
        ids.add(edge.from_id);
        next.push(edge.from_id);
      }
    });
    frontier = next;
  }
  // ponytail: cap the initial view; search and explicit "show all" expose the rest.
  return new Set(nodes.filter((node) => ids.has(node.id)).slice(0, 60).map((node) => node.id));
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

function App({ transport = brainTransport }) {
  const [snapshot, setSnapshot] = useState(() => normalizeSnapshot(null));
  const [view, setView] = useState("overview");
  const [selectedId, setSelectedId] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setSnapshot(normalizeSnapshot(await transport.getSnapshot()));
    } catch (cause) {
      setError(cause.message || "Brain could not be loaded");
    } finally {
      setLoading(false);
    }
  }, [transport]);

  useEffect(() => {
    load();
  }, [load]);

  const nodes = snapshot.nodes;
  const edges = snapshot.edges;
  const candidates = snapshot.semantic_candidates;
  const conflicts = snapshot.conflicts;
  const selected = nodes.find((node) => node.id === selectedId) || null;
  const counts = useMemo(
    () => dataCounts(nodes, edges, candidates, conflicts),
    [nodes, edges, candidates, conflicts],
  );

  const selectNode = useCallback((id, nextView = "inspector") => {
    setSelectedId(id);
    if (nextView) setView(nextView);
  }, []);

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

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand-mark" aria-hidden="true">PB</div>
        <div>
          <p className="eyebrow">POWER BI BRAIN</p>
          <h1>Inspector</h1>
        </div>
        <div className="topbar-spacer" />
        <span className={`connection-dot ${loading ? "is-loading" : error ? "is-error" : "is-ready"}`} />
        <span className="connection-label">{loading ? "Loading" : error ? "Offline" : "Connected"}</span>
        <button className="icon-button" onClick={load} title="Reload Brain" aria-label="Reload Brain">↻</button>
      </header>

      <div className="workspace">
        <aside className="sidebar">
          <p className="nav-label">Workspace</p>
          <nav aria-label="Main navigation">
            {VIEWS.map(([key, label]) => (
              <button key={key} className={`nav-button ${view === key ? "active" : ""}`} onClick={() => setView(key)}>
                <span className="nav-icon">{key === "overview" ? "▦" : key === "graph" ? "⌘" : key === "inspector" ? "◉" : "✓"}</span>
                {label}
                {key === "review" && counts.candidates + counts.warnings > 0 ? <span className="nav-count">{counts.candidates + counts.warnings}</span> : null}
              </button>
            ))}
          </nav>
          <div className="sidebar-footer">
            <p className="nav-label">Store</p>
            <span className="store-pill">LadybugDB</span>
            <span className="store-detail">Canonical graph</span>
          </div>
        </aside>

        <main className="content">
          {notice ? <div className="toast" role="status">{notice}</div> : null}
          {error ? (
            <div className="error-banner" role="alert">
              <span>{error}</span>
              <button className="text-button" onClick={load}>Retry</button>
            </div>
          ) : null}
          {view === "overview" ? <Overview snapshot={snapshot} counts={counts} onView={setView} onSelect={selectNode} /> : null}
          {view === "graph" ? <GraphView snapshot={snapshot} selectedId={selectedId} onSelect={selectNode} /> : null}
          {view === "inspector" ? <Inspector node={selected} snapshot={snapshot} onSelect={selectNode} onReview={review} onGraph={() => setView("graph")} /> : null}
          {view === "review" ? <ReviewQueue snapshot={snapshot} onSelect={selectNode} onReview={review} /> : null}
        </main>
      </div>
    </div>
  );
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

function Overview({ snapshot, counts, onView, onSelect }) {
  const scan = snapshot.scan || {};
  const validation = snapshot.validation || {};
  const lastScan = scan.last_scan || scan.lastScan || scan.timestamp || scan.completed_at || "Not scanned";
  const scanState = scan.state || scan.status || (counts.objects ? "ready" : "awaiting scan");
  const candidates = snapshot.semantic_candidates.filter((item) => item.status !== "rejected");
  const recent = [...candidates].sort((a, b) => Number(b.confidence || 0) - Number(a.confidence || 0)).slice(0, 4);

  return (
    <>
      <PageHeading kicker="Workspace overview" title="The Brain at a glance" description="Canonical structure, semantic review, and source health in one place." action={<button className="primary-button" onClick={() => onView("graph")}>Explore graph <span>→</span></button>} />
      <section className="stat-grid" aria-label="Brain counts">
        <StatCard label="Models" value={counts.models} detail="Semantic models" tone="blue" />
        <StatCard label="Reports" value={counts.reports} detail="Connected reports" tone="purple" />
        <StatCard label="Objects" value={counts.objects} detail="Canonical nodes" tone="green" />
        <StatCard label="Edges" value={counts.edges} detail="Known relationships" tone="amber" />
      </section>
      <section className="overview-grid">
        <div className="panel scan-panel">
          <div className="panel-heading"><div><p className="eyebrow">Source state</p><h3>Last scan</h3></div><StatusBadge value={scanState} /></div>
          <div className="scan-value">{formatDate(lastScan)}</div>
          <div className="scan-meta"><span>Graph storage</span><strong>LadybugDB</strong></div>
          <div className="scan-meta"><span>Validation</span><strong className={validation.valid === false ? "danger-text" : "success-text"}>{validation.valid === false ? "Needs attention" : validation.state || "Not run"}</strong></div>
          <button className="secondary-button full-width" onClick={() => onView("graph")}>Open graph</button>
        </div>
        <div className="panel review-panel">
          <div className="panel-heading"><div><p className="eyebrow">Human review</p><h3>Needs attention</h3></div><button className="text-button" onClick={() => onView("review")}>View all →</button></div>
          <div className="attention-row"><span className="attention-icon candidate">◌</span><span>Semantic candidates</span><strong>{counts.candidates}</strong></div>
          <div className="attention-row"><span className="attention-icon warning">!</span><span>Conflicts &amp; warnings</span><strong>{counts.warnings}</strong></div>
          <div className="attention-row"><span className="attention-icon approved">✓</span><span>Approved semantics</span><strong>{snapshot.semantic_candidates.filter((item) => item.status === "approved").length}</strong></div>
        </div>
      </section>
      <section className="panel candidate-panel">
        <div className="panel-heading"><div><p className="eyebrow">Semantic layer</p><h3>Review candidates</h3></div><span className="muted-label">Description-first inference</span></div>
        {recent.length ? <div className="candidate-list">{recent.map((item) => <CandidateRow key={item.id || `${item.target}-${item.value}`} item={item} onSelect={onSelect} onReview={() => onView("review")} />)}</div> : <EmptyState title="No semantic candidates" detail="Run a scan to populate reviewable semantic meaning." />}
      </section>
    </>
  );
}

function StatCard({ label, value, detail, tone }) {
  return <div className={`stat-card ${tone}`}><div className="stat-top"><span>{label}</span><span className="stat-glyph">◆</span></div><strong>{value}</strong><small>{detail}</small></div>;
}

function GraphView({ snapshot, selectedId, onSelect }) {
  const [query, setQuery] = useState("");
  const [nodeType, setNodeType] = useState("ALL");
  const [edgeType, setEdgeType] = useState("ALL");
  const [showAll, setShowAll] = useState(false);
  const graphSource = snapshot.graph && typeof snapshot.graph === "object" ? snapshot.graph : {};
  const graphIsScoped = Boolean(graphSource.scoped || graphSource.is_scoped || graphSource.scope || graphSource.target);
  const graphNodes = Array.isArray(graphSource.nodes) ? graphSource.nodes : snapshot.nodes;
  const graphEdges = Array.isArray(graphSource.edges) ? graphSource.edges : snapshot.edges;
  const types = useMemo(() => [...new Set(graphNodes.map((node) => node.type).filter(Boolean))].sort(), [graphNodes]);
  const edgeTypes = useMemo(() => [...new Set(graphEdges.map((edge) => edge.type).filter(Boolean))].sort(), [graphEdges]);
  const warningIds = useMemo(() => new Set(snapshot.conflicts.flatMap((item) => {
    const target = itemTarget(item);
    return [target, item.id, item.conflict_id].filter(Boolean);
  })), [snapshot.conflicts]);
  const relevantIds = useMemo(() => relatedNodeIds(graphNodes, graphEdges), [graphNodes, graphEdges]);
  const needle = query.trim().toLowerCase();
  const matching = useMemo(() => graphNodes.filter((node) => {
    const matchesText = !needle || [node.id, node.name, node.description].some((value) => String(value || "").toLowerCase().includes(needle));
    return matchesText && (nodeType === "ALL" || node.type === nodeType);
  }), [graphNodes, needle, nodeType]);
  const scopeIds = useMemo(() => {
    if (showAll || graphIsScoped || needle) return new Set(matching.map((node) => node.id));
    if (!selectedId) return new Set(matching.filter((node) => relevantIds.has(node.id)).map((node) => node.id));
    const ids = new Set([selectedId]);
    graphEdges.forEach((edge) => {
      if (edge.from_id === selectedId) ids.add(edge.to_id);
      if (edge.to_id === selectedId) ids.add(edge.from_id);
    });
    return new Set(matching.filter((node) => ids.has(node.id)).map((node) => node.id));
  }, [showAll, graphIsScoped, needle, selectedId, matching, graphEdges, relevantIds]);
  const visibleNodes = graphNodes.filter((node) => scopeIds.has(node.id));
  const visibleEdges = graphEdges.filter((edge) => scopeIds.has(edge.from_id) && scopeIds.has(edge.to_id) && (edgeType === "ALL" || edge.type === edgeType));

  return (
    <>
      <PageHeading kicker="Canonical graph" title="Follow the meaning" description="Scoped view of factual structure, inferred semantics, and observed usage." action={<button className="secondary-button" onClick={() => setShowAll((value) => !value)}>{showAll ? "Show relevant objects" : "Show all objects"}</button>} />
      <div className="graph-toolbar panel">
        <label className="search-field"><span>⌕</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search objects…" aria-label="Search objects" /></label>
        <label className="select-field"><span>Object</span><select value={nodeType} onChange={(event) => setNodeType(event.target.value)}><option value="ALL">All types</option>{types.map((type) => <option key={type} value={type}>{type}</option>)}</select></label>
        <label className="select-field"><span>Edge</span><select value={edgeType} onChange={(event) => setEdgeType(event.target.value)}><option value="ALL">All edges</option>{edgeTypes.map((type) => <option key={type} value={type}>{type}</option>)}</select></label>
        <span className="toolbar-count">{visibleNodes.length} of {graphNodes.length} nodes · {visibleEdges.length} edges</span>
      </div>
      <section className="graph-panel panel">
        <GraphCanvas nodes={visibleNodes} edges={visibleEdges} selectedId={selectedId} warningIds={warningIds} onSelect={(id) => onSelect(id, "inspector")} />
        <div className="graph-legend"><LegendDot className="fact" label="Fact" /><LegendDot className="candidate" label="Candidate" /><LegendDot className="approved" label="Approved" /><LegendDot className="warning" label="Warning" /><LegendLine className="fact" label="Fact edge" /><LegendLine className="inferred" label="Inferred" /><LegendLine className="observed" label="Observed" /></div>
      </section>
    </>
  );
}

function GraphCanvas({ nodes, edges, selectedId, warningIds, onSelect }) {
  const center = nodes.findIndex((node) => node.id === selectedId);
  const ordered = center > 0 ? [nodes[center], ...nodes.slice(0, center), ...nodes.slice(center + 1)] : nodes;
  const columns = Math.max(1, Math.ceil(Math.sqrt(ordered.length)));
  const positions = new Map(ordered.map((node, index) => [node.id, {
    x: 90 + (index % columns) * 235,
    y: 45 + Math.floor(index / columns) * 125,
  }]));
  const flowNodes = ordered.map((node) => ({
    id: node.id,
    type: "brain",
    position: positions.get(node.id),
    data: { node, warning: warningIds.has(node.id), color: nodeColor(node, warningIds.has(node.id)), onSelect },
  }));
  const flowEdges = edges.map((edge) => {
    const evidenceClass = String(edge.evidence_class || edge.evidenceClass || "FACT").toUpperCase();
    const warning = warningIds.has(edge.from_id) || warningIds.has(edge.to_id) || edge.type === "CONFLICTS_WITH";
    const color = warning ? "#f1c27f" : EDGE_COLORS[edge.type] || "#738294";
    return {
      id: edge.id,
      source: edge.from_id,
      target: edge.to_id,
      label: edge.type,
      className: `flow-edge ${evidenceClass.toLowerCase()} ${warning ? "warning" : ""}`,
      markerEnd: { type: MarkerType.ArrowClosed, color },
      style: { stroke: color, strokeWidth: warning ? 2 : 1.5, strokeDasharray: evidenceClass === "INFERRED" ? "6 4" : evidenceClass === "OBSERVED" ? "2 5" : undefined },
      labelStyle: { fill: "#8b9aa8", fontSize: 8, fontWeight: 600 },
      labelBgStyle: { fill: "#171e25", fillOpacity: 0.9 },
      data: { evidenceClass, warning },
    };
  });
  const nodeTypes = useMemo(() => ({ brain: BrainFlowNode }), []);

  if (!nodes.length) return <EmptyState title="No matching objects" detail="Change the filters or run a scan." />;
  return (
    <div className="flow-wrap" role="img" aria-label="Scoped Brain graph">
      <ReactFlow
        nodes={flowNodes}
        edges={flowEdges}
        nodeTypes={nodeTypes}
        onNodeClick={(_, node) => onSelect(node.id)}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        minZoom={0.35}
        maxZoom={1.8}
        nodesConnectable={false}
        edgesFocusable={false}
        proOptions={{ hideAttribution: true }}
      >
        <Background gap={22} size={1} color="#ffffff16" />
        <Controls showInteractive={false} />
        <MiniMap nodeColor={(node) => node.data?.color || "#83b7ff"} maskColor="#10151acc" />
      </ReactFlow>
    </div>
  );
}

function BrainFlowNode({ data, selected }) {
  const node = data.node;
  const onKeyDown = (event) => {
    if (event.key !== "Enter" && event.key !== " " && event.key !== "Spacebar") return;
    event.preventDefault();
    data.onSelect?.(node.id);
  };
  return <div className={`flow-node ${statusClass(node.status)} ${data.warning ? "warning" : ""} ${selected ? "selected" : ""}`} role="button" tabIndex="0" onKeyDown={onKeyDown} aria-label={`Inspect ${labelFor(node)}`}>
    <Handle type="target" position={Position.Left} className="flow-handle" />
    <span className="flow-node-type">{data.warning ? "⚠ " : ""}{node.type}</span>
    <span className="flow-node-name">{truncate(labelFor(node), 22)}</span>
    <span className="flow-node-id">{truncate(shortId(node.id), 24)}</span>
    <Handle type="source" position={Position.Right} className="flow-handle" />
  </div>;
}

function nodeColor(node, warning = false) {
  if (warning) return "#f1c27f";
  if (node.status === "candidate") return "#d093ff";
  if (node.status === "approved" || node.status === "overridden") return "#6ee7bd";
  if (node.status === "rejected") return "#ff8d8d";
  return "#83b7ff";
}

function Inspector({ node, snapshot, onSelect, onReview, onGraph }) {
  if (!node) return <><PageHeading kicker="Object inspector" title="Select an object" description="Choose a node from the graph or a target from the review queue." action={<button className="primary-button" onClick={onGraph}>Open graph <span>→</span></button>} /><div className="panel empty-inspector"><EmptyState title="Nothing selected" detail="The inspector shows identity, lineage, evidence, and review actions." /></div></>;
  const outgoing = snapshot.edges.filter((edge) => edge.from_id === node.id);
  const incoming = snapshot.edges.filter((edge) => edge.to_id === node.id);
  const candidates = snapshot.semantic_candidates.filter((item) => itemTarget(item) === node.id);
  const warnings = snapshot.conflicts.filter((item) => itemTarget(item) === node.id);
  const fields = Object.entries(node.properties || {}).filter(([key]) => !["raw_source", "raw_metadata"].includes(key));
  const rawMetadata = node.raw_metadata ?? node.rawMetadata ?? node.properties?.raw_metadata ?? node.properties?.rawMetadata;
  const rawSource = node.raw_source ?? node.rawSource ?? node.properties?.raw_source ?? node.properties?.rawSource;
  return (
    <>
      <PageHeading kicker="Object inspector" title={labelFor(node)} description={`${node.type} · ${shortId(node.id)}`} action={<button className="secondary-button" onClick={onGraph}>Show in graph <span>↗</span></button>} />
      <div className="inspector-layout">
        <div className="inspector-main">
          <section className="panel identity-panel"><div className="object-heading"><span className={`object-icon ${statusClass(node.status)}`}>{node.type.slice(0, 2)}</span><div><p className="eyebrow">{node.type}</p><h3>{labelFor(node)}</h3></div><StatusBadge value={node.status} /></div><dl className="identity-grid"><div><dt>Canonical ID</dt><dd className="mono">{node.id}</dd></div><div><dt>Source ID</dt><dd className="mono">{node.source_id || "—"}</dd></div><div><dt>Model</dt><dd>{node.model_id || "—"}</dd></div><div><dt>Report</dt><dd>{node.report_id || "—"}</dd></div></dl></section>
          <section className="panel"><PanelTitle eyebrow="Meaning" title="Description & metadata" />{node.description ? <p className="description-copy">{formatValue(node.description)}</p> : <p className="muted-copy">No description available.</p>}{fields.length ? <div className="metadata-table">{fields.map(([key, value]) => <div key={key}><span>{key.replace(/_/g, " ")}</span><strong>{formatValue(value)}</strong></div>)}</div> : null}<RawDetails rawMetadata={rawMetadata} rawSource={rawSource} /></section>
          <section className="panel"><PanelTitle eyebrow="Lineage" title="Relationships" /><RelationshipGroup title="Dependencies" nodeId={node.id} edges={outgoing.filter((edge) => edge.type === "DEPENDS_ON")} nodes={snapshot.nodes} onSelect={onSelect} empty="No measure dependencies." /><RelationshipGroup title="Dependents" nodeId={node.id} edges={incoming.filter((edge) => edge.type === "DEPENDS_ON")} nodes={snapshot.nodes} onSelect={onSelect} empty="No dependents." /><RelationshipGroup title="All connected" nodeId={node.id} edges={[...outgoing, ...incoming].filter((edge) => edge.type !== "DEPENDS_ON")} nodes={snapshot.nodes} onSelect={onSelect} empty="No other relationships." /></section>
        </div>
        <aside className="inspector-side"><section className="panel action-panel"><PanelTitle eyebrow="Review state" title="Human decision" /><StatusBadge value={node.status} large />{candidates.length ? <div className="action-list">{candidates.map((item) => <CandidateActions key={item.id || item.target} item={item} onReview={onReview} />)}</div> : <p className="muted-copy">No semantic candidate targets this object.</p>}</section><section className="panel"><PanelTitle eyebrow="Evidence" title="Semantic signals" />{candidates.length ? <div className="evidence-list">{candidates.map((item) => <EvidenceCard key={item.id || item.target} item={item} />)}</div> : <p className="muted-copy">No inferred meaning recorded.</p>}{warnings.map((warning) => <div className="warning-card" key={warning.id || formatEvidence(warning.reason)}><strong>Conflict</strong><p>{formatEvidence(warning.reason || warning.message || warning.description || "Conflicting evidence needs review.")}</p></div>)}</section><section className="panel"><PanelTitle eyebrow="Usage" title="Observed report usage" />{snapshot.edges.filter((edge) => edge.type === "OBSERVED_WITH" && (edge.from_id === node.id || edge.to_id === node.id)).map((edge) => <div className="usage-row" key={edge.id}><span>{shortId(edge.from_id === node.id ? edge.to_id : edge.from_id)}</span><strong>{formatValue(edge.properties?.count || edge.count || "observed")}</strong></div>)}{!snapshot.edges.some((edge) => edge.type === "OBSERVED_WITH" && (edge.from_id === node.id || edge.to_id === node.id)) ? <p className="muted-copy">No observed co-occurrence.</p> : null}<p className="footnote">Observed usage is evidence, not compatibility.</p></section></aside>
      </div>
    </>
  );
}

function RawDetails({ rawMetadata, rawSource }) {
  if (rawMetadata === undefined && rawSource === undefined) return null;
  return <details className="raw-details"><summary>Raw source payload</summary><div className="raw-blocks">{rawMetadata !== undefined ? <div><span>raw_metadata</span><pre>{safeJson(rawMetadata)}</pre></div> : null}{rawSource !== undefined ? <div><span>raw_source</span><pre>{safeJson(rawSource)}</pre></div> : null}</div></details>;
}

function RelationshipGroup({ title, nodeId, edges, nodes, onSelect, empty }) {
  return <div className="relationship-group"><div className="relationship-title">{title}<span>{edges.length}</span></div>{edges.length ? <div className="relationship-list">{edges.slice(0, 10).map((edge) => { const targetId = edge.from_id === nodeId ? edge.to_id : edge.from_id; const resolved = nodes.find((node) => node.id === targetId); return <button className="relationship-row" key={edge.id} onClick={() => resolved && onSelect(resolved.id, "inspector")}><span className="edge-chip" style={{ background: EDGE_COLORS[edge.type] || "#738294" }} /> <span>{edge.type}</span><strong>{resolved ? labelFor(resolved) : shortId(targetId)}</strong></button>; })}</div> : <p className="muted-copy compact">{empty}</p>}</div>;
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
  return <><PageHeading kicker="Human review" title="Review queue" description="Resolve semantic uncertainty and conflicts. Facts stay automatic." action={<span className="queue-count">{filtered.length} open items</span>} /><div className="queue-toolbar panel"><label className="select-field"><span>Issue</span><select value={issue} onChange={(event) => setIssue(event.target.value)}><option value="ALL">All issues</option><option value="candidate">Candidates</option><option value="conflict">Conflicts</option><option value="stale">Stale overrides</option></select></label><label className="select-field"><span>Object</span><select value={objectType} onChange={(event) => setObjectType(event.target.value)}><option value="ALL">All types</option>{types.map((type) => <option key={type} value={type}>{type}</option>)}</select></label><label className="select-field"><span>Model</span><select value={modelId} onChange={(event) => setModelId(event.target.value)}><option value="ALL">All models</option>{models.map((value) => <option key={value} value={value}>{shortId(value)}</option>)}</select></label><label className="select-field"><span>Report</span><select value={reportId} onChange={(event) => setReportId(event.target.value)}><option value="ALL">All reports</option>{reports.map((value) => <option key={value} value={value}>{shortId(value)}</option>)}</select></label><label className="select-field"><span>Sort</span><select value={sort} onChange={(event) => setSort(event.target.value)}><option value="confidence-high">Confidence ↓</option><option value="confidence-low">Confidence ↑</option><option value="impact-high">Impact ↓</option><option value="impact-low">Impact ↑</option></select></label></div><section className="panel queue-panel">{filtered.length ? <div className="queue-list">{filtered.map((item) => <ReviewItem key={item.id || `${item.issue}-${itemTarget(item)}`} item={item} nodes={snapshot.nodes} onSelect={onSelect} onReview={onReview} />)}</div> : <EmptyState title="Queue is clear" detail="No unresolved semantic items match these filters." />}</section></>;
}

function ReviewItem({ item, nodes, onSelect, onReview }) {
  const target = itemTarget(item);
  const targetNode = nodes.find((node) => node.id === target);
  return <div className="review-item"><button className="review-target" onClick={() => targetNode && onSelect(targetNode.id, "inspector")}><span className={`review-dot ${item.issue}`} /> <span><strong>{formatValue(item.value || item.meaning || item.reason || item.message || item.issue)}</strong><small>{targetNode ? `${targetNode.type} · ${labelFor(targetNode)}` : shortId(target)}</small></span></button><div className="review-evidence">{formatEvidence(item.evidence?.[0] ?? item.reason)}</div><div className="review-score"><strong>{confidence(itemConfidence(item)) === null ? "—" : `${confidence(itemConfidence(item))}%`}</strong><small>impact {itemImpact(item)} · {item.status || "candidate"}</small></div><div className="review-actions"><button className="approve-button" onClick={() => onReview("approve", item)}>Approve</button><button className="reject-button" onClick={() => onReview("reject", item)}>Reject</button></div></div>;
}

function CandidateRow({ item, onSelect, onReview }) {
  const target = itemTarget(item);
  return <div className="candidate-row"><button onClick={() => onSelect(target)}><span className="candidate-symbol">◌</span><span><strong>{formatValue(item.value || item.meaning || "Semantic candidate")}</strong><small>{shortId(target)}</small></span></button><span className="confidence-pill">{confidence(itemConfidence(item)) ?? "—"}%</span><button className="text-button" onClick={onReview}>Review →</button></div>;
}

function CandidateActions({ item, onReview }) {
  const [editingAction, setEditingAction] = useState("");
  const [value, setValue] = useState(item.value || item.meaning || "");
  const beginEdit = (action) => { setValue(item.value || item.meaning || ""); setEditingAction(action); };
  return <div className="candidate-actions"><div className="candidate-action-title"><span>{formatValue(item.value || item.meaning || "Unlabeled candidate")}</span><span>{confidence(itemConfidence(item)) ?? "—"}%</span></div>{editingAction ? <div className="edit-row"><input value={value} onChange={(event) => setValue(event.target.value)} aria-label={`${editingAction} semantic value`} /><button className="approve-button" onClick={() => { onReview(editingAction, item, value); setEditingAction(""); }}>{editingAction === "edit" ? "Save edit" : "Save override"}</button><button className="text-button" onClick={() => setEditingAction("")}>Cancel</button></div> : <div className="action-buttons"><button className="approve-button" onClick={() => onReview("approve", item)}>Approve</button><button className="secondary-button" onClick={() => beginEdit("edit")}>Edit</button><button className="reject-button" onClick={() => onReview("reject", item)}>Reject</button><button className="text-button" onClick={() => beginEdit("override")}>Override</button></div>}</div>;
}

function EvidenceCard({ item }) {
  return <div className="evidence-card"><div><span className="evidence-source">{formatValue(item.source || "inference")}</span><StatusBadge value={item.status || "candidate"} /></div><p>{formatEvidence(item.evidence?.[0] ?? item.reason ?? "Evidence recorded by the inference engine.")}</p><small>{formatValue(item.evidence_class || "INFERRED")} · deterministic score</small></div>;
}

function PanelTitle({ eyebrow, title }) { return <div className="panel-heading"><div><p className="eyebrow">{eyebrow}</p><h3>{title}</h3></div></div>; }
function StatusBadge({ value, large = false }) { return <span className={`status-badge ${large ? "large" : ""} ${statusClass(value)}`}><i />{value || "factual"}</span>; }
function LegendDot({ className, label }) { return <span><i className={`legend-dot ${className}`} />{label}</span>; }
function LegendLine({ className, label }) { return <span><i className={`legend-line ${className}`} />{label}</span>; }
function EmptyState({ title, detail }) { return <div className="empty-state"><span className="empty-mark">○</span><strong>{title}</strong><p>{detail}</p></div>; }
function truncate(value, length) { const text = String(value || ""); return text.length > length ? `${text.slice(0, length - 1)}…` : text; }
function formatDate(value) { if (!value || value === "Not scanned") return value || "Not scanned"; const date = new Date(value); return Number.isNaN(date.valueOf()) ? String(value) : date.toLocaleString([], { dateStyle: "medium", timeStyle: "short" }); }
function formatValue(value) { return safeJson(value); }

export default App;
