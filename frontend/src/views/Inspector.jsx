// Inspector: one object with its definition, lineage, usage, evidence and review actions, beside the object tree.
import VisualBindings from "../components/VisualBindings";
import ObjectContents from "../components/ObjectContents";
import React, { lazy, Suspense, useEffect, useState } from "react";
import { Check, ChevronRight, Copy, Link2, RefreshCw, TriangleAlert, Waypoints } from "lucide-react";
import { useToast } from "../components/ui/toast";
import { Tooltip } from "../components/ui/tooltip";
import ReviewDecision from "../components/ReviewDecision";
import { explainConfidence } from "../reviewEvidence";
import { TypeGlyph, TypeIcon } from "../components/TypeGlyph";
import { highlightDax } from "../dax";
import { formatPlural, readableText, publicProperties, scopeChoices, suggestionLabel } from "../presentation";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { Disclosure } from "../components/ui/collapsible";
import { Skeleton } from "../components/ui/skeleton";
import { artifactColor, artifactStyle, typeLabel } from "../graphPresentation";
import { PageHeading, StatusBadge, confidence, formatEvidence, formatValue, itemTarget, labelFor } from "./shared";
import { listKeys } from "../listNavigation";
// It draws with the graph library, which the first screen does not need.
const ImpactExplorer = lazy(() => import("../components/ImpactExplorer"));

const NO_REVIEW = { items: [], nodes: [], loaded: false, error: "" };

/** One object's open suggestions and conflicts, asked of the server (finding 01): not the whole project's. */
function useObjectReview(transport, id, revision) {
  const [state, setState] = useState({ id: null, ...NO_REVIEW });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (!id || typeof transport?.getReviewPage !== "function") return undefined;
    let active = true;
    setState((current) => current.id === id ? { ...current, error: "" } : { id, ...NO_REVIEW });
    transport.getReviewPage({ target: id, limit: 100 }).then((page) => {
      if (active) setState({ id, items: page.items || [], nodes: page.nodes || [], loaded: true, error: "" });
    }).catch((cause) => {
      if (active) setState((current) => ({ ...current, id, error: cause?.message || "Review evidence could not be loaded" }));
    });
    return () => { active = false; };
  }, [transport, id, revision, attempt]);
  const current = state.id === id ? state : { id, ...NO_REVIEW };
  return { ...current, retry: () => setAttempt((value) => value + 1) };
}

export function Inspector({ node, details, loading, error, reviewRevision = 0, overview, onSelect, onRetry, onReview, onGraph, colors, scanning, transport }) {
  const [activeEditId, setActiveEditId] = useState(null);
  const review = useObjectReview(transport, node?.id, reviewRevision);
  if (error) return <Card className="panel inspector-state"><div className="empty-state tone-bad"><span className="empty-icon" aria-hidden="true"><TriangleAlert /></span><h2>Object unavailable</h2><p>{readableText(error)}</p><Button variant="outline" onClick={onRetry}><RefreshCw />Retry object</Button></div></Card>;
  if (loading) return <div className="inspector-loading"><Skeleton className="skeleton-title" /><div className="skeleton-grid"><Skeleton className="skeleton-block" /><Skeleton className="skeleton-block" /></div><p role="status" className="loading-label">Loading object details…</p></div>;
  if (!node) return <><PageHeading title="Select an object" description="Choose an object from Search or the graph." action={<Button onClick={onGraph}>Open graph</Button>} /></>;
  const connected = details?.edges || [];
  const outgoing = connected.filter((edge) => edge.from_id === node.id);
  const incoming = connected.filter((edge) => edge.to_id === node.id);
  const usageTypes = new Set(["DEPENDS_ON", "REFERENCES", "USES"]);
  const relatedNodes = [...new Map([...(details?.neighbors || []), ...review.nodes, ...(details?.dependencies || []), ...(details?.dependents || []), ...(details?.usage || []), ...(details?.relationships?.nodes || []), node].map((item) => [item.id, item])).values()];
  const scopes = [...scopeChoices(overview, "model"), ...scopeChoices(overview, "report"), ...relatedNodes];
  const scopeName = (id) => readableText(scopes.find((item) => item.id === id)?.name);
  const candidates = review.items.filter((item) => item.issue === "candidate");
  const warnings = review.items.filter((item) => item.issue === "conflict");
  const observations = connected.filter((edge) => edge.type === "OBSERVED_WITH");
  const properties = node.properties || {};
  const expression = node.expression ?? properties.expression;
  const fields = publicProperties(node);
  const color = artifactColor(node, colors);
  const scopeTrail = [node.model_id, node.report_id, properties.table_id].filter((id) => id && id !== node.id).map(scopeName).filter(Boolean);
  return <>
    <PageHeading title={labelFor(node)} description={scopeTrail.join(" · ")} action={<span className="object-actions"><CopyLinkButton /><Button variant="outline" onClick={onGraph}><Waypoints />Show in graph</Button></span>}>
      <div className="object-summary-state" style={{ "--artifact-color": color }}><span className="type-chip" style={artifactStyle(node, colors)}><TypeIcon type={node.type} />{typeLabel(node.type)}</span><StatusBadge value={node.status} /></div>
    </PageHeading>
    <div className="object-workspace">
      <div className="object-main">
        <Card className="panel object-summary">
          <h2 className="panel-title">Definition</h2>
          {node.description ? <p className="description-copy">{formatValue(node.description)}</p> : (!fields.length && !expression ? <p className="muted-copy">No description recorded.</p> : null)}
          {fields.length ? <dl className="metadata-grid">{fields.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl> : null}
        </Card>
        {expression ? <ExpressionBlock expression={formatValue(expression)} /> : null}
        <ObjectContents groups={details?.contents} colors={colors} onSelect={(id) => onSelect(id, "inspector")} />
        <UsageRoles profile={details?.usage_roles} />
        {candidates.length || warnings.length ? <Disclosure title="Review & evidence" badge={`${formatPlural(candidates.length, "suggestion")}${warnings.length ? ` · ${formatPlural(warnings.length, "warning")}` : ""}`} className="object-metadata object-review panel" defaultOpen>{candidates.map((item) => { const itemId = item.id || item.target || itemTarget(item); return <div className="object-review-item" key={itemId}><CandidateActions item={item} node={node} onReview={onReview} disabled={scanning} isEditing={activeEditId === itemId} onStartEdit={() => setActiveEditId(itemId)} onCancelEdit={() => setActiveEditId(null)} /><EvidenceCard item={item} /></div>; })}{warnings.map((warning) => <div className="warning-card" key={warning.id || formatEvidence(warning.reason)}><strong><TriangleAlert aria-hidden="true" />Conflict</strong><p>{formatEvidence(warning.reason || warning.message || warning.description || "Conflicting evidence needs review.")}</p></div>)}</Disclosure> : null}
        {review.error ? <div className="inline-error" role="alert"><p>{review.loaded ? "Review evidence could not be refreshed. Showing last loaded evidence." : "Review evidence unavailable."} {readableText(review.error)}</p><Button variant="outline" size="sm" onClick={review.retry}>Retry evidence</Button></div> : !review.loaded ? <p className="muted-copy object-review" role="status">Loading review evidence…</p> : null}
        {connected.some((edge) => !usageTypes.has(edge.type) && edge.type !== "OBSERVED_WITH") ? <Disclosure title="Other relationships" className="object-metadata object-other panel"><RelationshipGroup title="Connected objects" nodeId={node.id} edges={connected.filter((edge) => !usageTypes.has(edge.type) && edge.type !== "OBSERVED_WITH")} nodes={relatedNodes} onSelect={onSelect} empty="No other relationships." colors={colors} /></Disclosure> : null}
        {observations.length ? <Disclosure title="Observed report usage" badge={observations.length} className="object-metadata object-observed panel">{observations.map((edge) => <div className="usage-row" key={edge.id}><span>{scopeName(edge.from_id === node.id ? edge.to_id : edge.from_id)}</span><strong>{formatValue(edge.properties?.count || edge.count || "observed")}</strong></div>)}<p className="footnote">Co-occurrence does not establish compatibility.</p></Disclosure> : null}
      </div>
      <Card className="panel object-lineage">
        <h2 className="panel-title">Lineage &amp; usage</h2>
        <VisualBindings bindings={details?.visual_bindings} wells={details?.field_wells} onSelect={(item) => onSelect(item.id, "inspector")} />
        <RelationshipGroup title="Used by" nodeId={node.id} edges={incoming.filter((edge) => usageTypes.has(edge.type))} nodes={relatedNodes} onSelect={onSelect} empty="No direct uses recorded." colors={colors} />
        {(() => {
          // A visual's fields and filters are already listed above by where they sit; Dependencies holds only the rest.
          const listed = new Set([...Object.values(details?.visual_bindings || {}).flat(), ...(details?.field_wells || []).flatMap((well) => well.fields || [])].map((item) => item?.id).filter(Boolean));
          const dependencies = outgoing.filter((edge) => usageTypes.has(edge.type) && !listed.has(edge.to_id));
          return listed.size && !dependencies.length ? null : <RelationshipGroup title={listed.size ? "Other dependencies" : "Dependencies"} nodeId={node.id} edges={dependencies} nodes={relatedNodes} onSelect={onSelect} empty="No direct dependencies recorded." colors={colors} />;
        })()}
        <Suspense fallback={null}><ImpactExplorer node={node} nodes={relatedNodes} onSelect={onSelect} transport={transport} /></Suspense>
      </Card>
    </div>
  </>;
}

/** How the object is used in reports: INFERRED summary of the USES roles (issue #11). */
export function UsageRoles({ profile }) {
  const facts = profile?.facts || [];
  if (!facts.length) return null;
  return <Disclosure title="How it is used" badge={facts.length} className="object-metadata object-usage-roles panel" defaultOpen>
    {facts.map((fact) => <div className="usage-row" key={`${fact.code}-${fact.text}`}><span>{fact.text}</span></div>)}
    <p className="footnote" title={readableText(profile.basis)}>Inferred from report bindings</p>
  </Disclosure>;
}

export function ExpressionBlock({ expression }) {
  const [message, setMessage] = useState("");
  useEffect(() => {
    if (message !== "Copied") return undefined;
    const timer = setTimeout(() => setMessage(""), 1800);
    return () => clearTimeout(timer);
  }, [message]);
  const copy = async () => {
    try { await navigator.clipboard.writeText(expression); setMessage("Copied"); }
    catch { setMessage("Select the formula to copy it."); }
  };
  return <section className="object-expression" aria-label="DAX formula"><div className="code-head"><h3><span className="code-lang">DAX</span>formula</h3><Button variant="ghost" size="xs" onClick={copy} className={message === "Copied" ? "is-copied" : ""}>{message === "Copied" ? <Check /> : <Copy />}{message === "Copied" ? "Copied" : "Copy formula"}</Button></div><pre tabIndex={0}><code>{highlightDax(expression)}</code></pre>{message && message !== "Copied" ? <p role="status">{message}</p> : null}</section>;
}

export function RelationshipGroup({ title, nodeId, edges, nodes, onSelect, empty, colors }) {
  const [expanded, setExpanded] = useState(false);
  const unique = [...new Map(edges.map((edge) => [edge.from_id === nodeId ? edge.to_id : edge.from_id, edge])).values()];
  const shown = expanded ? unique : unique.slice(0, 10);
  return <section className="relationship-group" aria-label={title}><h3 className="relationship-title">{title}<span className="count-pill">{unique.length}</span></h3>{unique.length ? <div className="relationship-list" onKeyDown={(event) => listKeys(event)}>{shown.map((edge) => { const targetId = edge.from_id === nodeId ? edge.to_id : edge.from_id; const resolved = nodes.find((node) => node.id === targetId); return <Button variant="ghost" className="relationship-row" key={targetId} onClick={() => onSelect(targetId, "inspector")}><TypeGlyph node={resolved} type={resolved?.type || edge.type} colors={colors} size="xs" /><span className="relationship-copy"><strong>{resolved ? labelFor(resolved) : "Related object"}</strong><small>{typeLabel(resolved?.type || edge.type)}</small></span><ChevronRight className="row-chevron" aria-hidden="true" /></Button>; })}</div> : <p className="muted-copy compact">{empty}</p>}{unique.length > 10 ? <Button variant="link" size="sm" className="relationship-more" onClick={() => setExpanded((current) => !current)}>{expanded ? "Show fewer" : `Show all ${unique.length}`}</Button> : null}</section>;
}

/** Copies the address of the current place; the hash route opens the same object for a colleague on the same project. */
export function CopyLinkButton() {
  const toast = useToast();
  const copy = async () => {
    try { await navigator.clipboard.writeText(globalThis.location.href); toast.show({ tone: "ok", text: "Link copied" }); }
    catch { toast.show({ tone: "warn", text: "The link could not be copied" }); }
  };
  return <Button variant="ghost" size="icon" className="copy-link" aria-label="Copy link to this object" title="Copy link to this object" onClick={copy}><Link2 /></Button>;
}

export function CandidateActions({ item, node, onReview, disabled = false, isEditing = false, onStartEdit, onCancelEdit }) {
  const [exiting, setExiting] = useState(false);
  const decide = async (action, candidateItem, valueOverride) => {
    const isReduced = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    setExiting(true);
    if (!isReduced) {
      await new Promise((resolve) => setTimeout(resolve, 180));
    }
    try {
      const ok = await onReview(action, candidateItem, valueOverride, node);
      if (!ok) setExiting(false);
      return ok;
    } catch (err) {
      setExiting(false);
      throw err;
    }
  };
  const score = confidence(item.confidence ?? item.properties?.confidence);
  return (
    <fieldset className={`candidate-actions ${exiting ? "is-exiting" : ""}`} data-ui-actions="" disabled={disabled || exiting}>
      <div className="candidate-action-title">
        <span>{suggestionLabel(item)}</span>
        <Tooltip content={explainConfidence(item, node)}>
          <span className="count-pill" tabIndex={0} role="group" aria-label={`Confidence ${score}%`}>
            {score === null ? "" : `${score}%`}
          </span>
        </Tooltip>
      </div>
      <ReviewDecision
        item={item}
        onReview={onReview}
        onDecide={decide}
        disabled={disabled || exiting}
        isEditing={isEditing}
        onStartEdit={onStartEdit}
        onCancelEdit={onCancelEdit}
        compact={false}
      />
    </fieldset>
  );
}

export function EvidenceCard({ item }) {
  return <div className="evidence-card"><p>{readableText(item.evidence?.length ? item.evidence : item.reason) || "No explanation recorded."}</p></div>;
}
