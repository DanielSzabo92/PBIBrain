import React, { useEffect, useRef, useState } from "react";
import { ArrowUpRight, LoaderCircle } from "lucide-react";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Separator } from "./ui/separator";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "./ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "./ui/tabs";
import { ARTIFACT_GROUPS, artifactColor, artifactGroup, typeLabel } from "../graphPresentation";

const valueText = (value) => value == null ? "—" : typeof value === "object" ? JSON.stringify(value, null, 2) : String(value);

function RelatedObjects({ title, nodes = [], onSelect, colors }) {
  return <section className="detail-section"><h3>{title} <span>{nodes.length}</span></h3>
    {nodes.length ? nodes.map((node) => <Button variant="ghost" className="detail-related" key={node.id} onClick={() => onSelect(node)}>
      <span className="artifact-dot" style={{ backgroundColor: artifactColor(node, colors) }} />
      <span><strong>{node.name || node.id}</strong><small>{typeLabel(node.type)}</small></span><ArrowUpRight />
    </Button>) : <p className="text-sm text-muted-foreground">None recorded.</p>}
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
  const properties = Object.entries(current?.properties || {}).filter(([key]) => !["raw_source", "raw_metadata", "source_fingerprint", "source_hash", "dax_ast", "daxAst", "evidence", "dax_evidence", "dax_behaviors"].includes(key));
  return <Sheet modal={false} open={Boolean(node)} onOpenChange={(open) => { if (!open) onClose(); }}>
    <SheetContent side="right" className="graph-detail-sheet" onInteractOutside={(event) => event.preventDefault()}
      onOpenAutoFocus={() => { returnFocus.current = document.activeElement; }}
      onCloseAutoFocus={(event) => { event.preventDefault(); if (returnFocus.current?.isConnected) returnFocus.current.focus(); }}>
      <SheetHeader className="graph-detail-header">
        <div className="flex items-center gap-2 pr-8"><span className="artifact-dot" style={{ backgroundColor: color }} /><Badge variant="outline">{typeLabel(current?.type)}</Badge><Badge variant="secondary">{current?.status || "factual"}</Badge></div>
        <SheetTitle className="graph-detail-title">{current?.name || current?.id || "Object details"}</SheetTitle>
        <SheetDescription>{current ? ARTIFACT_GROUPS[artifactGroup(current)].label : "Object details"}</SheetDescription>
      </SheetHeader>
      <Separator />
      <div className="graph-detail-body" aria-busy={Boolean(node && !details && !error)}>
        {node && !details && !error ? <p role="status" className="detail-loading"><LoaderCircle className="size-4 animate-spin" />Loading details…</p> : null}
        {error ? <div role="alert" className="detail-error">{error}<Button variant="outline" size="sm" onClick={() => setAttempt((value) => value + 1)}>Retry details</Button></div> : null}
        <Tabs key={displayedNode?.id} defaultValue="properties">
          <TabsList aria-label="Object details"><TabsTrigger value="properties">Properties</TabsTrigger><TabsTrigger value="lineage">Lineage</TabsTrigger><TabsTrigger value="evidence">Evidence</TabsTrigger></TabsList>
          <TabsContent value="properties">
            <p className="detail-description">{valueText(current?.description || "No description available.")}</p>
            <dl className="detail-fields">
              {[["Canonical ID", current?.id], ["Model", current?.model_id], ["Report", current?.report_id], ["Source ID", current?.source_id]].filter(([, value]) => value).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{valueText(value)}</dd></div>)}
              {properties.map(([key, value]) => <div key={key}><dt>{typeLabel(key)}</dt><dd className={key === "expression" ? "detail-expression" : ""}>{valueText(value)}</dd></div>)}
            </dl>
            {details ? <details className="detail-raw"><summary>Raw metadata</summary><pre>{valueText(details.raw_metadata ?? current.properties?.raw_source ?? current)}</pre></details> : null}
          </TabsContent>
          <TabsContent value="lineage">
            {details ? <>
              <RelatedObjects title="Dependencies" nodes={details.dependencies} colors={colors} onSelect={onSelect} />
              <RelatedObjects title="Dependents" nodes={details.dependents} colors={colors} onSelect={onSelect} />
              <RelatedObjects title="Report usage" nodes={details.usage} colors={colors} onSelect={onSelect} />
              <RelatedObjects title="Related objects" nodes={details.relationships?.nodes} colors={colors} onSelect={onSelect} />
              <section className="detail-section"><h3>Relationships <span>{details.edges?.length || 0}</span></h3>{(details.edges || []).map((edge) => <div className="detail-edge" key={edge.id}><span>{typeLabel(edge.type)}</span><small>{edge.from_id} → {edge.to_id}</small><Badge variant="outline">{edge.evidence_class || "FACT"}</Badge></div>)}</section>
            </> : <p className="text-sm text-muted-foreground">{error ? "Details unavailable." : "Loading lineage…"}</p>}
          </TabsContent>
          <TabsContent value="evidence">
            {details ? <>{["warnings", "semantics", "evidence"].map((key) => <section className="detail-section" key={key}><h3>{typeLabel(key)}</h3>{details[key]?.length ? details[key].map((value, index) => <pre className="detail-evidence" key={index}>{valueText(value)}</pre>) : <p className="text-sm text-muted-foreground">None recorded.</p>}</section>)}</> : <p className="text-sm text-muted-foreground">{error ? "Details unavailable." : "Loading evidence…"}</p>}
          </TabsContent>
        </Tabs>
      </div>
      <div className="graph-detail-actions"><Button variant="outline" onClick={() => onCenter(current)}>Center graph here</Button><Button onClick={() => onInspect(current.id)}>Full inspector <ArrowUpRight /></Button></div>
    </SheetContent>
  </Sheet>;
}
