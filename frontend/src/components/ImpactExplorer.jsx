import React, { useEffect, useMemo, useRef, useState } from "react";
import { ReactFlow, Background, Controls } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { GitFork, Maximize2, RefreshCw } from "lucide-react";
import { brainTransport } from "../transport";
import { Button } from "./ui/button";
import { NativeSelect } from "./ui/native-select";
import { Input } from "./ui/input";
import { Card } from "./ui/card";
import { Dialog, DialogContent } from "./ui/dialog";
import { Disclosure } from "./ui/collapsible";
import { formatDaxName, formatObjectRef } from "../presentation.js";
import ProvenanceLegend from "./ProvenanceLegend";
import "../guard.css";

const LABELS = { from_column_id: "Source column", to_column_id: "Target column", active: "Active relationship", cross_filter_direction: "Filter direction" };
const CATEGORY = { DIRECT: "Direct change", STRUCTURAL: "Factual reference", POTENTIAL_BEHAVIORAL: "Inferred effect", CONDITIONAL: "Depends on context", UNKNOWN: "Unknown impact" };

const REASON_PHRASES = {
  SCANNER_COVERAGE_UNKNOWN: "Scanner coverage unknown: metadata incomplete for this source",
  "Explicit modification target": "Directly modified object",
  "Consumes potentially affected object": "Uses an object affected by this change",
};

const formatReason = (reason) => {
  if (!reason) return "";
  const str = String(reason).trim();
  const upper = str.toUpperCase();
  if (REASON_PHRASES[upper]) return REASON_PHRASES[upper];
  if (REASON_PHRASES[str]) return REASON_PHRASES[str];
  return str.replaceAll("_", " ");
};

export default function ImpactExplorer({ node, nodes = [], onSelect, transport = brainTransport }) {
  const [open, setOpen] = useState(false);
  const [property, setProperty] = useState("from_column_id");
  const [newValue, setNewValue] = useState("");
  const [columns, setColumns] = useState([]);
  const [query, setQuery] = useState("");
  const [report, setReport] = useState(null);
  const [category, setCategory] = useState("");
  const [scope, setScope] = useState("");
  const [error, setError] = useState("");
  const [working, setWorking] = useState(false);
  const sequence = useRef(0);

  const allRecords = [...(report?.direct_impacts || []), ...(report?.potential_impacts || []), ...(report?.conditional_impacts || [])];
  const records = allRecords.filter((item) => (!category || item.impact_category === category) && (!scope || item.model_id === scope || item.report_id === scope));
  const scopes = [...new Set(allRecords.flatMap((item) => [item.model_id, item.report_id]).filter(Boolean))];
  const formatNodeName = (raw) => (raw ? formatObjectRef(raw) : "Related object");
  const name = (id) => formatNodeName(nodes.find((item) => item.id === id)?.name || allRecords.find((item) => item.object_id === id)?.name);

  const graph = useMemo(() => {
    const ids = new Map();
    const edges = new Map();
    records.forEach((item) => {
      ids.set(item.object_id, { label: item.name || name(item.object_id), level: item.path.length });
      item.path.forEach((step, index) => {
        if (!ids.has(step.from_id)) ids.set(step.from_id, { label: name(step.from_id), level: index });
        if (!ids.has(step.to_id)) ids.set(step.to_id, { label: name(step.to_id), level: index + 1 });
        const key = `${step.from_id}:${step.to_id}:${step.edge_type}`;
        edges.set(key, { id: key, source: step.from_id, target: step.to_id, label: step.direction === "analytical" ? "Inferred" : "Factual", style: { strokeDasharray: step.direction === "analytical" ? "6 4" : undefined } });
      });
    });
    const counts = new Map();
    const flowNodes = [...ids.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([id, item]) => {
      const index = counts.get(item.level) || 0;
      counts.set(item.level, index + 1);
      return { id, position: { x: item.level * 260, y: index * 96 }, data: { label: item.label } };
    });
    return { nodes: flowNodes, edges: [...edges.values()] };
  }, [report, category, scope]);

  const analyze = async () => {
    const request = ++sequence.current;
    setWorking(true);
    setError("");
    try {
      const proposal = node.type === "RELATIONSHIP" && newValue !== "" ? [{ property, new_value: property === "active" ? newValue === "true" : newValue }] : [];
      const value = await transport.getImpact(node.id, proposal);
      if (request === sequence.current) setReport(value);
    } catch (cause) {
      if (request === sequence.current) setError(cause.message || "Impact analysis unavailable");
    } finally {
      if (request === sequence.current) setWorking(false);
    }
  };

  // Analyze on open so impact analysis is immediately visible without an extra click.
  useEffect(() => {
    if (open && !report && !working && !error) {
      analyze();
    }
  }, [open, node.id]);

  const findColumns = async () => {
    setError("");
    try {
      const response = await transport.search({ query, modelId: node.model_id, objectType: "COLUMN", limit: 100 });
      setColumns(response.items || response.objects || []);
      if (response.has_more) setError("More columns exist. Narrow the search.");
    } catch (cause) {
      setError(cause.message || "Columns unavailable");
    }
  };

  const invalidate = () => {
    sequence.current += 1;
    setReport(null);
    setWorking(false);
  };

  return (
    <>
      <div className="impact-explorer-section">
        <div className="impact-explorer-summary">
          <div className="impact-explorer-head">
            <GitFork className="size-4 text-primary shrink-0" aria-hidden="true" />
            <h3 className="panel-title font-semibold text-sm">Impact Explorer</h3>
          </div>
          <p className="muted-copy compact">What breaks if I change this object? Explore downstream blast radius.</p>
          <Button
            variant="outline"
            className="w-full justify-between mt-2"
            aria-expanded={open}
            onClick={() => setOpen(true)}>
            <span>Impact Explorer</span>
            <Maximize2 className="size-3.5 opacity-70" aria-hidden="true" />
          </Button>
        </div>
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent
          title="Impact Explorer"
          description={`Downstream impact analysis for ${node.name || formatNodeName(node.id)}. Inspect affected objects, evidence chains, and verification queries.`}
          className="impact-explorer-dialog">
          <div className="impact-explorer-content">
            <div className="impact-explorer-toolbar">
              {node.type === "RELATIONSHIP" ? (
                <div className="guard-fields impact-proposal-fields">
                  <label className="text-xs font-medium">
                    Proposed property
                    <NativeSelect value={property} onChange={(event) => { invalidate(); setProperty(event.target.value); setNewValue(""); }}>
                      {Object.entries(LABELS).map(([key, value]) => <option key={key} value={key}>{value}</option>)}
                    </NativeSelect>
                  </label>
                  <p className="text-xs text-muted-foreground self-center">
                    Current: {node.properties?.[property] === undefined ? "Unknown" : property.endsWith("column_id") ? name(node.properties[property]) : String(node.properties[property])}
                  </p>
                  {property.endsWith("column_id") ? (
                    <>
                      <label className="text-xs font-medium">
                        Find column
                        <Input value={query} onChange={(event) => setQuery(event.target.value)} />
                      </label>
                      <Button variant="outline" size="sm" onClick={findColumns}>Find columns</Button>
                      <label className="text-xs font-medium">
                        New column
                        <NativeSelect value={newValue} onChange={(event) => { invalidate(); setNewValue(event.target.value); }}>
                          <option value="">Use current endpoint</option>
                          {columns.map((column) => <option key={column.id} value={column.id}>{column.name}</option>)}
                        </NativeSelect>
                      </label>
                    </>
                  ) : (
                    <label className="text-xs font-medium">
                      New value
                      <NativeSelect value={newValue} onChange={(event) => { invalidate(); setNewValue(event.target.value); }}>
                        <option value="">Use current value</option>
                        {(property === "active" ? [["true", "Active"], ["false", "Inactive"]] : [["oneDirection", "Single direction"], ["bothDirections", "Both directions"]]).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                      </NativeSelect>
                    </label>
                  )}
                </div>
              ) : null}

              <div className="impact-action-bar">
                <Button onClick={analyze} disabled={working}>
                  <RefreshCw className={working ? "size-3.5 spin" : "size-3.5"} aria-hidden="true" />
                  {working ? "Analyzing…" : "Analyze impact"}
                </Button>
                {report ? (
                  <div className="guard-fields impact-filter-row">
                    <label className="text-xs font-medium flex items-center gap-1.5">
                      <span>Impact category</span>
                      <NativeSelect value={category} aria-label="Impact category" onChange={(event) => setCategory(event.target.value)}>
                        <option value="">All categories</option>
                        {Object.entries(CATEGORY).map(([key, value]) => <option key={key} value={key}>{value}</option>)}
                      </NativeSelect>
                    </label>
                    <label className="text-xs font-medium flex items-center gap-1.5">
                      <span>Model or report</span>
                      <NativeSelect value={scope} aria-label="Model or report" onChange={(event) => setScope(event.target.value)}>
                        <option value="">All models and reports</option>
                        {scopes.map((id) => <option key={id} value={id}>{name(id)}</option>)}
                      </NativeSelect>
                    </label>
                  </div>
                ) : null}
              </div>
            </div>

            {error ? <p role="alert" className="inline-error text-xs">{error}</p> : null}

            {report ? (
              <div className="impact-report-body">
                <div className="guard-warning" role="status">
                  <strong>{report.completeness?.status === "COMPLETE" ? "Static impact coverage complete" : "Impact coverage incomplete"}</strong>
                  <p>Runtime behavior has not been verified.</p>
                  {report.completeness?.output_truncated ? <p>Displayed paths are truncated. Full impact remains in the analysis.</p> : null}
                </div>

                <div className="impact-flow-container">
                  {graph.nodes.length ? (
                    <div className="impact-flow" aria-label="Impact paths">
                      <ReactFlow
                        nodes={graph.nodes}
                        edges={graph.edges}
                        fitView
                        nodesDraggable={false}
                        proOptions={{ hideAttribution: true }}
                        onNodeClick={(_, item) => onSelect?.(item.id, "inspector")}>
                        <Background />
                        <Controls showInteractive={false} className="impact-flow-controls" />
                      </ReactFlow>
                    </div>
                  ) : (
                    <p className="text-sm text-muted-foreground p-4 text-center">No displayed impacts match these filters.</p>
                  )}
                  <ProvenanceLegend className="impact-explorer-legend mt-2" />
                </div>

                <div className="impact-records-section">
                  <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">Affected Objects ({records.length})</h4>
                  <ul className="guard-records">
                    {records.map((item, index) => (
                      <li key={`${item.object_id}:${item.analyzer_rule_id}:${index}`} className="guard-record-item">
                        <div className="flex items-center justify-between gap-2 mb-1">
                          <Button variant="link" className="p-0 h-auto font-medium" onClick={() => onSelect?.(item.object_id, "inspector")}>
                            {formatNodeName(item.name) || name(item.object_id)}
                          </Button>
                          <span className="type-chip text-2xs">{CATEGORY[item.impact_category]}</span>
                        </div>
                        <p className="text-xs text-foreground mb-1">{formatReason(item.reason)}</p>
                        {item.conditions?.length ? <p className="text-2xs text-muted-foreground mb-1.5">{item.conditions.join(" · ")}</p> : null}
                        <Disclosure title="Evidence path" defaultOpen={false} className="mt-1">
                          <ol className="text-xs space-y-1 pl-4 list-decimal text-muted-foreground">
                            {item.path.map((step, i) => (
                              <li key={i}>
                                {name(step.from_id)} → {name(step.to_id)} · {step.edge_type.replaceAll("_", " ").toLowerCase()} · {step.direction === "analytical" ? "Inferred" : "Factual"}
                              </li>
                            ))}
                          </ol>
                        </Disclosure>
                      </li>
                    ))}
                  </ul>
                </div>

                {report.unknown_impacts?.length ? (
                  <div role="alert" className="inline-error p-3 rounded-md">
                    <h4 className="font-semibold text-xs mb-1">Unresolved impact</h4>
                    <ul className="text-xs space-y-1 list-disc pl-4">
                      {report.unknown_impacts.map((item, i) => <li key={i}>{formatReason(item.reason)}</li>)}
                    </ul>
                  </div>
                ) : null}

                <Disclosure
                  title={`Required verification queries (${report.required_tests?.length || 0})`}
                  defaultOpen={false}
                  className="mt-2">
                  <ul className="text-xs space-y-1 list-disc pl-4 text-muted-foreground">
                    {report.required_tests?.map((item) => (
                      <li key={item.test_id}>{item.category.replaceAll("_", " ")} · Query required</li>
                    ))}
                  </ul>
                </Disclosure>
              </div>
            ) : null}
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
