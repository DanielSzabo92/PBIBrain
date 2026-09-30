import React, { useEffect, useLayoutEffect, useRef, useState } from "react";
import { ArrowUpRight, ChevronRight, Crosshair, LoaderCircle } from "lucide-react";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "./ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "./ui/tabs";
import VisualBindings from "./VisualBindings";
import { ARTIFACT_GROUPS, artifactColor, artifactGroup, typeLabel } from "../graphPresentation";
import { highlightDax } from "../dax";

import { objectName, readableText, publicProperties, statusLabel } from "../presentation";
const valueText = (value) => readableText(value) || "—";

function RelatedObjects({ title, nodes = [], onSelect, colors }) {
  return <section className="detail-section"><h3>{title} <span className="count-pill">{nodes.length}</span></h3>
    {nodes.length ? nodes.map((node) => <Button variant="ghost" className="detail-related" key={node.id} onClick={() => onSelect(node)}>
      <span className="artifact-dot" style={{ backgroundColor: artifactColor(node, colors) }} />
      <span><strong>{objectName(node)}</strong><small>{typeLabel(node.type)}</small></span><ChevronRight className="row-chevron" />
    </Button>) : <p className="muted-copy compact">None recorded.</p>}
  </section>;
}

export default function GraphDetails({ node, colors, transport, onClose, onSelect, onCenter, onInspect }) {
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const returnFocus = useRef(null);
  const lastNode = useRef(node);
  if (node) lastNode.current = node;
  const displayedNode = node || lastNode.current;
  const id = node?.id;
  const isOpen = Boolean(node);
  // While the sheet fades in it ignores the pointer, so the second click of a
  // double-click still reaches the graph node underneath.
  const [entering, setEntering] = useState(false);
  useLayoutEffect(() => {
    if (!isOpen) return undefined;
    setEntering(true);
    const timer = setTimeout(() => setEntering(false), 320);
    return () => clearTimeout(timer);
  }, [isOpen]);
  useEffect(() => {
    if (!id) return undefined;
    let active = true;
    setResult(null); setError("");
    transport.getObject(id).then((data) => {
      if (active) setResult({ id, data });
    }).catch((cause) => { if (active) setError(cause.message || "Could not load object details"); });
    return () => { active = false; };
  }, [id, attempt, transport]);
  const details = result && result.id === displayedNode?.id ? result.data : null;
  const current = details?.object || displayedNode;
  const color = current ? artifactColor(current, colors) : undefined;
  const properties = publicProperties(current);
  const expression = current?.expression || current?.properties?.expression;
  const related = [current, ...(details?.dependencies || []), ...(details?.dependents || []), ...(details?.usage || []), ...(details?.relationships?.nodes || [])].filter(Boolean);
  const name = (id) => objectName(related.find((item) => item.id === id));
  return <Sheet modal={false} open={Boolean(node)} onOpenChange={(open) => { if (!open) onClose(); }}>
    <SheetContent side="right" className={`graph-detail-sheet ${entering ? "is-entering" : ""}`} style={{ "--artifact-color": color }} onInteractOutside={(event) => event.preventDefault()}
      onOpenAutoFocus={() => { returnFocus.current = document.activeElement; }}
      onCloseAutoFocus={(event) => { event.preventDefault(); if (returnFocus.current?.isConnected) returnFocus.current.focus(); }}>
      <SheetHeader className="graph-detail-header">
        <div className="graph-detail-chips"><span className="type-chip"><span className="artifact-dot" />{typeLabel(current?.type)}</span><Badge variant="secondary">{statusLabel(current?.status)}</Badge></div>
        <SheetTitle className="graph-detail-title">{current ? objectName(current) : "Object details"}</SheetTitle>
        <SheetDescription>{current ? ARTIFACT_GROUPS[artifactGroup(current)].label : "Object details"}</SheetDescription>
      </SheetHeader>
      <div className="graph-detail-body" aria-busy={Boolean(node && !details && !error)}>
        {node && !details && !error ? <p role="status" className="detail-loading"><LoaderCircle className="size-4 spin" />Loading details…</p> : null}
        {error ? <div role="alert" className="detail-error">{error}<Button variant="outline" size="sm" onClick={() => setAttempt((value) => value + 1)}>Retry details</Button></div> : null}
        <Tabs key={displayedNode?.id} defaultValue="properties">
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
              <section className="detail-section"><h3>Relationships <span className="count-pill">{details.edges?.length || 0}</span></h3>{(details.edges || []).map((edge) => <div className="detail-edge" key={edge.id}><div><span>{typeLabel(edge.type)}</span><Badge variant="outline">{edge.evidence_class === "INFERRED" ? "Suggested" : edge.evidence_class === "OBSERVED" ? "Observed" : "From source"}</Badge></div><small>{name(edge.from_id)} → {name(edge.to_id)}</small></div>)}</section>
            </> : <p className="muted-copy compact">{error ? "Details unavailable." : "Loading lineage…"}</p>}
          </TabsContent>
          <TabsContent value="evidence">
            {details ? <>{["warnings", "semantics", "evidence"].map((key) => <section className="detail-section" key={key}><h3>{typeLabel(key)}</h3>{details[key]?.length ? details[key].map((value, index) => <p className="detail-evidence" key={index}>{readableText(value, related) || "No explanation recorded."}</p>) : <p className="muted-copy compact">None recorded.</p>}</section>)}</> : <p className="muted-copy compact">{error ? "Details unavailable." : "Loading evidence…"}</p>}
          </TabsContent>
        </Tabs>
      </div>
      <div className="graph-detail-actions"><Button variant="outline" onClick={() => { onCenter(current); onClose(); }}><Crosshair />Center graph here</Button><Button onClick={() => onInspect(current.id)}>Full inspector <ArrowUpRight /></Button></div>
    </SheetContent>
  </Sheet>;
}
