// Small helpers and parts that more than one view uses: how a suggestion's target, confidence and status are read,
// the page heading, the empty state and the status badge. Moved out of App.jsx when the views were split.
import React from "react";
import { objectName, readableText, statusLabel } from "../presentation";
import { Badge } from "../components/ui/badge";

export function confidence(value) {
  if (value == null || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? Math.round(number * 100) : null;
}

export function statusClass(value) {
  return String(value || "factual").toLowerCase().replace(/[^a-z]+/g, "-");
}

export function labelFor(node) {
  return objectName(node);
}

export function itemTarget(item) {
  const value = item?.target || item?.target_id || item?.object || item?.object_id || item?.source_object;
  return value && typeof value === "object" ? value.id || value.object_id : value;
}

export function safeJson(value) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

export function formatEvidence(value) {
  return readableText(value) || "No explanation recorded.";
}

export function numberOr(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

export function itemConfidence(item) {
  return numberOr(item?.confidence ?? item?.properties?.confidence, 0);
}

export function itemImpact(item) {
  const raw = item?.impact ?? item?.impact_score ?? item?.properties?.impact ?? item?.properties?.impact_score;
  const value = raw && typeof raw === "object" ? raw.score ?? raw.value : raw;
  if (typeof value === "string") {
    const rank = { critical: 4, high: 3, medium: 2, normal: 2, low: 1, none: 0 }[value.trim().toLowerCase()];
    if (rank !== undefined) return rank;
  }
  return numberOr(value, 0);
}

// Only the content pane scrolls (desktop shell); views save and restore its position, not the window's.
export function contentScroller() {
  return document.getElementById("main-content") || document.scrollingElement || document.documentElement;
}

// `quiet`: the view header bar already names the view, so the page keeps its h1 for structure and
// assistive tech only and spends no space on a second title or a sentence that restates it.
export function PageHeading({ kicker, title, description, action, children, quiet = false }) {
  if (quiet) return <h1 className="sr-only" tabIndex={-1}>{title}</h1>;
  return (
    <div className="page-heading">
      <div className="page-heading-copy">
        {kicker ? <p className="eyebrow">{kicker}</p> : null}
        {children}
        <h1>{title}</h1>
        {description ? <p className="page-description">{description}</p> : null}
      </div>
      {action ? <div className="page-heading-action">{action}</div> : null}
    </div>
  );
}

export function StatusBadge({ value, large = false }) { return <Badge variant="outline" className={`status-badge ${large ? "large" : ""} ${statusClass(value)}`}><i />{statusLabel(value)}</Badge>; }
export function EmptyState({ title, detail, action, icon, tone }) { return <div className={`empty-state ${tone ? `tone-${tone}` : ""}`}>{icon ? <span className="empty-icon" aria-hidden="true">{icon}</span> : null}<h2>{title}</h2><p>{detail}</p>{action}</div>; }
export function formatDate(value) { if (!value || value === "Not scanned") return value || "Not scanned"; const date = new Date(value); return Number.isNaN(date.valueOf()) ? String(value) : date.toLocaleString([], { dateStyle: "medium", timeStyle: "short" }); }
export function formatValue(value) { return readableText(value) || "—"; }

export function dataCounts(nodes, edges, candidates, conflicts) {
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
