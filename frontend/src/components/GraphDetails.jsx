import React, { useEffect, useState } from "react";
import { BadgeCheck, Check, ChevronRight, CircleDashed, CircleX, Crosshair, Eye, LoaderCircle, PanelRight, PenLine, TriangleAlert, X } from "lucide-react";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "./ui/tabs";
import VisualBindings from "./VisualBindings";
import { ARTIFACT_GROUPS, artifactGroup, typeLabel } from "../graphPresentation";
import { TypeGlyph } from "./TypeGlyph";
import { highlightDax } from "../dax";

import { objectName, readableText, publicProperties, statusLabel, visualType } from "../presentation";
const valueText = (value) => readableText(value) || "—";

// Provenance and decision glyphs (visual contract §4).
const STATUS_ICONS = { factual: Check, candidate: CircleDashed, approved: BadgeCheck, rejected: CircleX, overridden: PenLine, stale: TriangleAlert };
const EVIDENCE = { FACT: [Check, "Factual"], INFERRED: [CircleDashed, "Inferred"], OBSERVED: [Eye, "Observed"] };

function Provenance({ status }) {
  const Icon = STATUS_ICONS[status] || Check;
  return <span className={`graph-provenance ${status || "factual"}`}><Icon aria-hidden="true" />{statusLabel(status)}</span>;
}

function RelatedObjects({ title, nodes = [], onSelect, colors }) {
  return <section className="detail-section"><h3>{title} <span className="count-pill">{nodes.length}</span></h3>
    {nodes.length ? nodes.map((node) => <Button variant="ghost" className="detail-related" key={node.id} onClick={() => onSelect(node)}>
      <TypeGlyph node={node} colors={colors} size="sm" />
      <span><strong translate="no">{objectName(node)}</strong><small>{typeLabel(node.type)}</small></span><ChevronRight className="row-chevron" />
    </Button>) : <p className="muted-copy compact">None recorded.</p>}
  </section>;
}

/**
 * Object details, docked to the right of the graph canvas (visual contract §11.2).
 * It is a complementary region, not a dialog: the graph stays usable beside it.
 */
export default function GraphDetails({ node, settled = false, colors, transport, onClose, onSelect, onCenter, onInspect }) {
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const id = node?.id;
  useEffect(() => {
    if (!id) return undefined;
    let active = true;
    setResult(null); setError("");
    transport.getObject(id).then((data) => {
      if (active) setResult({ id, data });
    }).catch((cause) => { if (active) setError(cause.message || "Could not load object details"); });
    return () => { active = false; };
  }, [id, attempt, transport]);
  if (!node) return null;
  const details = result && result.id === node.id ? result.data : null;
  const current = details?.object || node;
  const properties = publicProperties(current);
  const expression = current?.expression || current?.properties?.expression;
  const related = [current, ...(details?.dependencies || []), ...(details?.dependents || []), ...(details?.usage || []), ...(details?.relationships?.nodes || [])].filter(Boolean);
  const name = (target) => objectName(related.find((item) => item.id === target));
  const kind = current.type === "VISUAL" ? visualType(current) : typeLabel(current.type);
  return <aside className={`graph-detail-sheet graph-detail-pane ${settled ? "is-settled" : "is-entering"}`} aria-label="Object details">
    <header className="graph-detail-header">
      <div className="graph-detail-kicker"><TypeGlyph node={current} colors={colors} size="sm" /><span>{kind}</span><Provenance status={current.status} /></div>
      <h2 className="graph-detail-title" translate="no">{objectName(current)}</h2>
      <p className="graph-detail-scope">{ARTIFACT_GROUPS[artifactGroup(current)].label}</p>
      <Button variant="ghost" size="icon-sm" className="graph-detail-close" aria-label="Close" tooltip="Close (Esc)" onClick={onClose}><X /></Button>
      <div className="graph-detail-actions" data-ui-actions="">
        <Button variant="outline" size="sm" onClick={() => onCenter(current)}><Crosshair />Show connections</Button>
        <Button size="sm" onClick={() => onInspect(current.id)}><PanelRight />Open in Inspector</Button>
      </div>
    </header>
    <div className="graph-detail-body" aria-busy={Boolean(!details && !error)}>
      {!details && !error ? <p role="status" className="detail-loading"><LoaderCircle className="size-4 spin" />Loading details…</p> : null}
      {error ? <div role="alert" className="detail-error">{error}<Button variant="outline" size="sm" onClick={() => setAttempt((value) => value + 1)}>Retry details</Button></div> : null}
      <Tabs key={node.id} defaultValue="properties">
        <TabsList aria-label="Object details"><TabsTrigger value="properties">Properties</TabsTrigger><TabsTrigger value="lineage">Lineage</TabsTrigger><TabsTrigger value="evidence">Evidence</TabsTrigger></TabsList>
        <TabsContent value="properties">
          <p className="detail-description">{valueText(current?.description || "No description available.")}</p>
          <dl className="detail-fields">
            {expression ? <div className="detail-field-code"><dt>DAX formula</dt><dd className="detail-expression">{highlightDax(expression)}</dd></div> : null}
            {properties.map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{value}</dd></div>)}
          </dl>
          <VisualBindings bindings={details?.visual_bindings} onSelect={onSelect} />
        </TabsContent>
        <TabsContent value="lineage">
          {details ? <>
            <RelatedObjects title="Dependencies" nodes={details.dependencies} colors={colors} onSelect={onSelect} />
            <RelatedObjects title="Dependents" nodes={details.dependents} colors={colors} onSelect={onSelect} />
            <RelatedObjects title="Report usage" nodes={details.usage} colors={colors} onSelect={onSelect} />
            <RelatedObjects title="Related objects" nodes={details.relationships?.nodes} colors={colors} onSelect={onSelect} />
            <section className="detail-section"><h3>Relationships <span className="count-pill">{details.edges?.length || 0}</span></h3>{(details.edges || []).map((edge) => {
              const [Icon, label] = EVIDENCE[String(edge.evidence_class || "FACT").toUpperCase()] || [Check, "Factual"];
              return <div className="detail-edge" key={edge.id}><div><span>{typeLabel(edge.type)}</span><Badge variant="outline"><Icon aria-hidden="true" />{label}</Badge></div><small>{name(edge.from_id)} → {name(edge.to_id)}</small></div>;
            })}</section>
          </> : <p className="muted-copy compact">{error ? "Details unavailable." : "Loading lineage…"}</p>}
        </TabsContent>
        <TabsContent value="evidence">
          {details ? <>{["warnings", "semantics", "evidence"].map((key) => <section className="detail-section" key={key}><h3>{typeLabel(key)}</h3>{details[key]?.length ? details[key].map((value, index) => <p className="detail-evidence" key={index}>{readableText(value, related) || "No explanation recorded."}</p>) : <p className="muted-copy compact">None recorded.</p>}</section>)}</> : <p className="muted-copy compact">{error ? "Details unavailable." : "Loading evidence…"}</p>}
        </TabsContent>
      </Tabs>
    </div>
  </aside>;
}
