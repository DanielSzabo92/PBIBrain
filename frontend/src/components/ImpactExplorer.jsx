import React, { useMemo, useRef, useState } from "react";
import { ReactFlow, Background, Controls } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { brainTransport } from "../transport";
import { Button } from "./ui/button";
import { NativeSelect } from "./ui/native-select";
import { Input } from "./ui/input";
import { Card } from "./ui/card";
import "../guard.css";

const LABELS = { from_column_id: "Source column", to_column_id: "Target column", active: "Active relationship", cross_filter_direction: "Filter direction" };
const CATEGORY = { DIRECT: "Direct change", STRUCTURAL: "Known reference", POTENTIAL_BEHAVIORAL: "Possible behavior change", CONDITIONAL: "Depends on context", UNKNOWN: "Unknown impact" };

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
  const name = (id) => nodes.find((item) => item.id === id)?.name || allRecords.find((item) => item.object_id === id)?.name || "Related object";
  const graph = useMemo(() => {
    const ids = new Map(); const edges = new Map();
    records.forEach((item) => {
      ids.set(item.object_id, { label: item.name || name(item.object_id), level: item.path.length });
      item.path.forEach((step, index) => {
        if (!ids.has(step.from_id)) ids.set(step.from_id, { label: name(step.from_id), level: index });
        if (!ids.has(step.to_id)) ids.set(step.to_id, { label: name(step.to_id), level: index + 1 });
        const key = `${step.from_id}:${step.to_id}:${step.edge_type}`;
        edges.set(key, { id: key, source: step.from_id, target: step.to_id, label: step.direction === "analytical" ? "Possible effect" : "Known reference", style: { strokeDasharray: step.direction === "analytical" ? "5 4" : undefined } });
      });
    });
    const counts = new Map();
    const flowNodes = [...ids.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([id, item]) => {
      const index = counts.get(item.level) || 0; counts.set(item.level, index + 1);
      return { id, position: { x: item.level * 240, y: index * 90 }, data: { label: item.label } };
    });
    return { nodes: flowNodes, edges: [...edges.values()] };
  }, [report, category, scope]);
  const analyze = async () => {
    const request = ++sequence.current; setWorking(true); setError(""); setReport(null);
    try {
      const proposal = node.type === "RELATIONSHIP" && newValue !== "" ? [{ property, new_value: property === "active" ? newValue === "true" : newValue }] : [];
      const value = await transport.getImpact(node.id, proposal);
      if (request === sequence.current) setReport(value);
    } catch (cause) { if (request === sequence.current) setError(cause.message || "Impact analysis unavailable"); }
    finally { if (request === sequence.current) setWorking(false); }
  };
  const findColumns = async () => {
    setError("");
    try {
      const response = await transport.search({ query, modelId: node.model_id, objectType: "COLUMN", limit: 100 });
      setColumns(response.items || response.objects || []);
      if (response.has_more) setError("More columns exist. Narrow the search.");
    } catch (cause) { setError(cause.message || "Columns unavailable"); }
  };
  const invalidate = () => { sequence.current += 1; setReport(null); setWorking(false); };
  return <Card className="panel impact-explorer">
    <Button variant="ghost" aria-expanded={open} onClick={() => setOpen(!open)}>Impact Explorer</Button>
    {open ? <div className="guard-stack">
      <p className="muted-copy">Possible downstream effects. This view grants no edit permission.</p>
      {node.type === "RELATIONSHIP" ? <div className="guard-fields">
        <label>Proposed property<NativeSelect value={property} onChange={(event) => { invalidate(); setProperty(event.target.value); setNewValue(""); }}>{Object.entries(LABELS).map(([key, value]) => <option key={key} value={key}>{value}</option>)}</NativeSelect></label>
        <p>Current value: {node.properties?.[property] === undefined ? "Unknown" : property.endsWith("column_id") ? name(node.properties[property]) : String(node.properties[property])}</p>
        {property.endsWith("column_id") ? <><label>Find column<Input value={query} onChange={(event) => setQuery(event.target.value)} /></label><Button variant="outline" onClick={findColumns}>Find columns</Button><label>New column<NativeSelect value={newValue} onChange={(event) => { invalidate(); setNewValue(event.target.value); }}><option value="">Use current endpoint</option>{columns.map((column) => <option key={column.id} value={column.id}>{column.name}</option>)}</NativeSelect></label></> : <label>New value<NativeSelect value={newValue} onChange={(event) => { invalidate(); setNewValue(event.target.value); }}><option value="">Use current value</option>{(property === "active" ? [["true", "Active"], ["false", "Inactive"]] : [["oneDirection", "Single direction"], ["bothDirections", "Both directions"]]).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</NativeSelect></label>}
      </div> : null}
      <Button onClick={analyze} disabled={working}>{working ? "Analyzing…" : "Analyze impact"}</Button>
      {error ? <p role="alert" className="inline-error">{error}</p> : null}
      {report ? <>
        <div className="guard-warning" role="status"><strong>{report.completeness?.status === "COMPLETE" ? "Static impact coverage complete" : "Impact coverage incomplete"}</strong><p>Runtime behavior has not been verified.</p>{report.completeness?.output_truncated ? <p>Displayed paths are truncated. Full impact remains in the analysis.</p> : null}</div>
        <div className="guard-fields"><label>Impact category<NativeSelect value={category} onChange={(event) => setCategory(event.target.value)}><option value="">All categories</option>{Object.entries(CATEGORY).map(([key, value]) => <option key={key} value={key}>{value}</option>)}</NativeSelect></label><label>Model or report<NativeSelect value={scope} onChange={(event) => setScope(event.target.value)}><option value="">All models and reports</option>{scopes.map((id) => <option key={id} value={id}>{name(id)}</option>)}</NativeSelect></label></div>
        {graph.nodes.length ? <div className="impact-flow" aria-label="Impact paths"><ReactFlow nodes={graph.nodes} edges={graph.edges} fitView nodesDraggable={false} onNodeClick={(_, item) => onSelect?.(item.id, "inspector")}><Background /><Controls showInteractive={false} /></ReactFlow></div> : <p>No displayed impacts match these filters.</p>}
        <p>Solid lines: known references. Dashed lines: possible effects.</p>
        <ul className="guard-records">{records.map((item, index) => <li key={`${item.object_id}:${item.analyzer_rule_id}:${index}`}><Button variant="link" onClick={() => onSelect?.(item.object_id, "inspector")}>{item.name || name(item.object_id)}</Button><span>{CATEGORY[item.impact_category]}</span><p>{item.reason}</p>{item.conditions?.length ? <p>{item.conditions.join(" · ")}</p> : null}<details><summary>Evidence path</summary><ol>{item.path.map((step, i) => <li key={i}>{name(step.from_id)} → {name(step.to_id)} · {step.edge_type.replaceAll("_", " ").toLowerCase()} · {step.direction === "analytical" ? "Possible influence" : "Source reference"}</li>)}</ol></details></li>)}</ul>
        {report.unknown_impacts?.length ? <div role="alert"><h4>Unresolved impact</h4><ul>{report.unknown_impacts.map((item, i) => <li key={i}>{item.reason.replaceAll("_", " ")}</li>)}</ul></div> : null}
        <details><summary>Required regression contexts ({report.required_tests?.length || 0})</summary><ul>{report.required_tests?.map((item) => <li key={item.test_id}>{item.category.replaceAll("_", " ")} · Query required</li>)}</ul></details>
      </> : null}
    </div> : null}
  </Card>;
}
