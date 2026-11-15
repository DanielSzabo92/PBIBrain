// Overview: the project at a glance (counts, what needs attention, top measures, sources and versions).
import CommonObjects from "../components/CommonObjects";
import { hasComparableSources } from "../commonality";
import React, { useMemo, useState } from "react";
import { ArrowRight, Boxes, Calculator, CircleCheck, Clock, Flame, Inbox, Database, Plus, RefreshCw, ScanLine, ShieldAlert, ShieldCheck, TriangleAlert } from "lucide-react";
import { Tooltip } from "../components/ui/tooltip";
import { TypeGlyph } from "../components/TypeGlyph";
import { formatCount, originNote, isBackendUnreachableError } from "../presentation";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { Disclosure } from "../components/ui/collapsible";
import { Skeleton } from "../components/ui/skeleton";
import { pluralType } from "../graphPresentation";
import { formatDate, itemTarget } from "./shared";

export function Overview({ overview, config, counts, colors, loading, projectName, onView, onBrowseType, onSources, onSample, onSummary, onScan, onReview, onSelect, onMerge, transport, scanning, scanLabel, error, onRetry, snapshot, auditTrail }) {
  // The seven model and report types show at once; meanings (aliases, roles, concepts…) open on demand.
  const [allTypes, setAllTypes] = useState(false);
  const hasObjects = counts.objects > 0;
  if (isBackendUnreachableError(error) && !hasObjects) {
    return (
      <div className="page page-overview" data-ui-stack="">
        <header className="overview-hero">
          <h1>{projectName}</h1>
          <p className="hero-meta muted">Service offline</p>
        </header>
        <Card className="panel" role="region" aria-label="PBIBrain service unreachable">
          <div className="empty-state tone-bad">
            <span className="empty-icon" aria-hidden="true"><TriangleAlert /></span>
            <h2>Can't reach the PBIBrain service</h2>
            <p>Make sure the PBIBrain backend service is running, then retry.</p>
            <div className="status-actions" data-ui-actions="">
              <Button onClick={onRetry}><RefreshCw />Retry connection</Button>
            </div>
          </div>
        </Card>
      </div>
    );
  }
  const hasSources = Boolean(config?.sources?.length || config?.cloud_sources?.length);
  const sourceCount = config?.sources ? config.sources.length + (config.cloud_sources?.length || 0) : undefined;
  const notChecked = Array.isArray(overview.not_checked) ? overview.not_checked : [];
  const lastScan = overview.last_scan;
  const validationState = overview.validation_state || "not_run";
  const validationLabel = { valid: "Graph validation passed", invalid: "Graph validation failed", warning: "Graph validation warnings", not_run: "Graph validation not run" }[validationState] || "Graph validation unavailable";
  // Notes at INFO level (for example an object type the validator only passes through) are not issues to act on.
  const issues = (overview.validation_issues || []).filter((item) => String(item.severity || "").toUpperCase() !== "INFO");
  // The overview lists the first issues and counts the rest.
  const issueTotal = Math.max(Number(overview.validation_issue_count) || 0, issues.length);
  const pending = counts.review;
  const ValidationIcon = validationState === "valid" ? ShieldCheck : ShieldAlert;
  const validationTone = { valid: "ok", invalid: "bad", warning: "warn" }[validationState] || "idle";

  const nodes = snapshot?.nodes || [];
  const edges = snapshot?.edges || [];
  const candidates = snapshot?.semantic_candidates || [];
  const conflicts = snapshot?.conflicts || [];

  const mostUsedMeasures = useMemo(() => {
    // The server counts over the whole graph. The browser estimate below is only for a server that does not send it.
    if (Array.isArray(overview?.top_measures)) return overview.top_measures.map((item) => ({ node: item, count: item.count || 0 }));
    const measures = nodes.filter((node) => node.type === "MEASURE" || node.type === "CALCULATION_ITEM");
    if (!measures.length) return [];
    const usageCounts = new Map();
    for (const edge of edges) {
      if (edge.type !== "CONTAINS" && edge.to_id) {
        usageCounts.set(edge.to_id, (usageCounts.get(edge.to_id) || 0) + 1);
      }
    }
    return measures
      .map((m) => ({ node: m, count: usageCounts.get(m.id) || 0 }))
      .sort((a, b) => b.count - a.count || a.node.name.localeCompare(b.node.name))
      .slice(0, 5);
  }, [nodes, edges, overview?.top_measures]);

  const unreviewedOnHot = useMemo(() => {
    if (Array.isArray(overview?.hot_unreviewed)) {
      return overview.hot_unreviewed.map((item) => ({
        item: { id: item.id, kind: item.kind, meaning: item.label, scope: item.scope }, targetId: item.target_id, degree: item.degree || 0,
        targetNode: { id: item.target_id, name: item.name, type: item.type },
      }));
    }
    const unreviewed = [
      ...candidates.filter((c) => !["approved", "rejected", "overridden"].includes(c.status)).map((c) => ({ ...c, kind: "candidate" })),
      ...conflicts.map((c) => ({ ...c, kind: "conflict" })),
    ];
    if (!unreviewed.length) return [];
    const degreeMap = new Map();
    for (const edge of edges) {
      if (edge.from_id) degreeMap.set(edge.from_id, (degreeMap.get(edge.from_id) || 0) + 1);
      if (edge.to_id) degreeMap.set(edge.to_id, (degreeMap.get(edge.to_id) || 0) + 1);
    }
    const nodeMap = new Map(nodes.map((n) => [n.id, n]));
    const scored = unreviewed.map((item) => {
      const targetId = itemTarget(item);
      const targetNode = nodeMap.get(targetId);
      const degree = degreeMap.get(targetId) || 0;
      return { item, targetNode, targetId, degree };
    });
    scored.sort((a, b) => b.degree - a.degree);
    return scored.slice(0, 5);
  }, [candidates, conflicts, edges, nodes, overview?.hot_unreviewed]);

  const recentChanges = useMemo(() => {
    const list = [];
    const seen = new Set();
    const nodeMap = new Map(nodes.map((n) => [n.id, n]));
    if (Array.isArray(auditTrail)) {
      for (const entry of auditTrail) {
        const id = entry.targetId || entry.reviewId || entry.id;
        if (id && !seen.has(id)) {
          seen.add(id);
          const targetNode = nodeMap.get(entry.targetId);
          list.push({
            id,
            targetId: entry.targetId,
            name: targetNode ? targetNode.name : entry.targetId || "Item",
            type: targetNode?.type || "OBJECT",
            action: entry.action || "reviewed",
            actor: entry.actor || "User",
          });
        }
      }
    }
    if (list.length < 5 && Array.isArray(snapshot?.overrides)) {
      for (const ov of snapshot.overrides) {
        const id = ov.target_id || ov.id;
        if (id && !seen.has(id)) {
          seen.add(id);
          const targetNode = nodeMap.get(ov.target_id);
          list.push({
            id,
            targetId: ov.target_id,
            name: targetNode ? targetNode.name : ov.target_id || "Item",
            type: targetNode?.type || "OBJECT",
            action: ov.status || "override",
            actor: "Reviewer",
          });
        }
      }
    }
    return list.slice(0, 5);
  }, [auditTrail, snapshot?.overrides, nodes]);

  const validationWidget = (
    <Card className="overview-widget" role="region" aria-label="Validation summary">
      <div className="widget-head">
        <div className="widget-title">
          <ValidationIcon className={`status-icon tone-${validationTone}`} aria-hidden="true" />
          <h3>Validation summary</h3>
        </div>
        <span className={`status-badge-inline tone-${validationTone}`}>{validationLabel}</span>
      </div>
      <p className="widget-description">
        {validationState === "not_run" ? "Scan sources to check graph validity." : validationState === "invalid" ? "Sources were extracted, but graph issues need attention." : "Graph validity is checked separately from source extraction and review decisions."}
      </p>
      {issues.length ? (
        <div className="widget-issues-list">
          {issues.slice(0, 3).map((item, index) => (
            <div key={`${item.code}-${index}`} className="widget-issue-item">
              <span className={`severity severity-${String(item.severity).toLowerCase()}`}>{item.severity}</span>
              <span className="widget-issue-text" title={item.message}>{item.message}</span>
              {item.object_id || item.from_id || item.to_id ? (
                <Button variant="ghost" size="sm" onClick={() => onSelect(item.object_id || item.from_id || item.to_id, "inspector")}>
                  Inspect
                </Button>
              ) : null}
            </div>
          ))}
          {issues.length > 3 ? (
            <Disclosure title={`View ${formatCount(issueTotal - 3)} more issues`} className="validation-issues">
              <ul>
                {issues.slice(3).map((item, index) => (
                  <li key={`${item.code}-${index}`}>
                    <span className={`severity severity-${String(item.severity).toLowerCase()}`}>{item.severity}</span>
                    <span className="issue-message">{item.message}</span>
                    {item.object_id || item.from_id || item.to_id ? (
                      <Button variant="link" size="sm" onClick={() => onSelect(item.object_id || item.from_id || item.to_id, "inspector")}>
                        Inspect affected object
                      </Button>
                    ) : null}
                  </li>
                ))}
              </ul>
              {issueTotal > issues.length ? <p className="footnote">The first {formatCount(issues.length)} of {formatCount(issueTotal)} issues are listed.</p> : null}
            </Disclosure>
          ) : null}
        </div>
      ) : validationState === "not_run" ? null : (
        <p className="widget-empty muted">No schema or dependency issues detected.</p>
      )}
      {validationState === "not_run" && onScan ? (
        <div className="widget-foot">
          <Button variant="ghost" size="sm" onClick={onScan} disabled={scanning} tooltip={!hasSources ? "Add sources before running validation" : undefined}>
            <ShieldCheck />Run validation
          </Button>
        </div>
      ) : null}
    </Card>
  );

  const sourcesRow = <div className="status-row tone-idle">
    <Database className="status-icon" aria-hidden="true" />
    <div className="status-copy">
      <h2>{scanning ? "Scanning sources…" : hasObjects ? "Sources indexed" : "Sources"}</h2>
      <p className="scan-meta">{sourceCount === undefined ? "Source settings unavailable" : `${sourceCount} ${sourceCount === 1 ? "source" : "sources"}`}{hasObjects ? ` · ${lastScan ? `Last scan ${formatDate(lastScan)}` : "Last scan time unavailable"}` : ""}</p>
    </div>
    <div className="status-actions" data-ui-actions="">
      {(!lastScan || !hasObjects) && onScan ? (
        <Button variant="ghost" size="sm" onClick={onScan} disabled={scanning || !hasSources} tooltip={!hasSources ? "Add sources before scanning" : undefined}>
          <ScanLine />Scan now
        </Button>
      ) : null}
      <Button variant="ghost" size="sm" onClick={onSources}>Manage sources</Button>
    </div>
  </div>;

  const notCheckedRow = notChecked.length ? <div className="status-row tone-warn" role="status">
    <TriangleAlert className="status-icon" aria-hidden="true" />
    <div className="status-copy">
      <h2>{notChecked.length} {notChecked.length === 1 ? "item" : "items"} not checked</h2>
      <ul className="not-checked-list">{notChecked.map((item) => { const note = originNote(item); return <li key={item.id}><Button variant="link" size="sm" onClick={() => onSelect(item.id, "inspector")}>{item.name}</Button> <span className="muted">{note?.title || "Not checked"}</span></li>; })}</ul>
    </div>
  </div> : null;

  const PRIMARY = ["MODEL", "TABLE", "COLUMN", "MEASURE", "REPORT", "PAGE", "VISUAL"];
  const typeCounts = Object.entries(overview.object_counts || {}).filter(([, count]) => count > 0).sort(([a], [b]) => { const ia = PRIMARY.indexOf(a), ib = PRIMARY.indexOf(b); return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib) || a.localeCompare(b); });

  const otherTypes = typeCounts.filter(([type]) => !PRIMARY.includes(type)).length;

  return <div className="page page-overview" data-ui-stack="">
    <header className={`overview-hero ${hasObjects && !loading ? "is-quiet" : ""}`}>
      <div className="overview-hero-copy">
        <h1 className={hasObjects && !loading ? "sr-only" : undefined} tabIndex={-1}>Overview</h1>
        {loading ? (
          <p className="hero-meta muted">{scanning ? "Scanning project…" : "Loading project…"}</p>
        ) : hasObjects ? (
          <p className="hero-meta muted sr-only">{lastScan ? `Last scan ${formatDate(lastScan)}` : "Project indexed"}</p>
        ) : (
          <p className="hero-meta">Connect your Power BI sources to build the project brain.</p>
        )}
      </div>
    </header>
    {hasObjects && typeCounts.length ? <nav className="type-strip" aria-label="Objects by type">
      {typeCounts.filter(([type]) => allTypes || PRIMARY.includes(type)).map(([type, count]) => <Tooltip key={type} content={`Browse ${formatCount(count)} ${pluralType(type, count).toLowerCase()}`}><button type="button" className="type-strip-item" onClick={() => onBrowseType(type)}><TypeGlyph type={type} colors={colors} size="sm" /><span className="type-strip-count" data-ui-number="">{formatCount(count)}</span><span className="type-strip-label">{pluralType(type, count)}</span></button></Tooltip>)}
      {otherTypes ? <button type="button" className="type-strip-item type-strip-more" aria-expanded={allTypes} onClick={() => setAllTypes((open) => !open)}>{allTypes ? "Fewer" : `+${otherTypes} more`}</button> : null}
    </nav> : null}
    {loading && !hasObjects ? <div className="overview-loading"><Skeleton className="skeleton-search" /><Skeleton className="skeleton-panel" /><p role="status" className="sr-only">{scanning ? "Scanning sources…" : "Loading project…"}</p></div> : !hasObjects ?
      <div className="overview-grid">
        <Card className="project-start" role="region" aria-labelledby="project-start-title">
          <h2 id="project-start-title">{hasSources ? "Ready for the first scan" : "Add your project sources"}</h2>
          <p>{hasSources ? "Scan your files to find models, reports, and their dependencies." : "Choose your PBIP project or exported model and report files."}</p>
          <Button
            size="lg"
            onClick={hasSources ? onScan : onSources}
            disabled={!config || scanning}
            tooltip={!config ? "Project settings unavailable. Connect to the PBIBrain service first." : scanning ? "Scan in progress" : undefined}
          >
            {hasSources ? <ScanLine /> : <Plus />}
            {hasSources ? scanLabel : "Add sources"}
          </Button>
          {!hasSources && onSample && config ? <Button variant="outline" size="lg" className="project-start-sample" onClick={onSample} disabled={scanning}><Boxes />Open sample project</Button> : null}
        </Card>
        <Card className="status-panel" role="region" aria-label="Project status">{sourcesRow}{notCheckedRow}</Card>
      </div> : <>
        <Card className="status-panel" role="region" aria-label="Project status">
          <div className={`status-row ${pending ? "tone-brand" : "tone-ok"}`}>
            {pending ? <span className="status-icon status-icon-count" aria-hidden="true"><Inbox /></span> : <CircleCheck className="status-icon" aria-hidden="true" />}
            <div className="status-copy">
              <h2>{validationState === "invalid" ? "Resolve graph issues before review" : pending ? "Ready for review" : "No pending reviews"}</h2>
              <p>{pending ? <><span className="sr-only">{pending} {pending === 1 ? "open item" : "open items"}. </span><span className="review-card-split"><span data-ui-number="">{formatCount(counts.candidates)} {counts.candidates === 1 ? "suggestion" : "suggestions"}</span>{counts.warnings ? <span data-ui-number="">{formatCount(counts.warnings)} conflicts</span> : null}{counts.stale ? <span data-ui-number="">{formatCount(counts.stale)} outdated decisions</span> : null}</span></> : "All suggestions have been reviewed."}</p>
            </div>
            <div className="status-actions"><Button variant={pending ? "default" : "outline"} size="sm" onClick={onReview}>Open review queue <ArrowRight aria-hidden="true" /></Button></div>
          </div>
          {sourcesRow}
          {notCheckedRow}
        </Card>

        <div className="overview-widgets-grid">
          {validationWidget}

          <Card className="overview-widget" role="region" aria-label="Most-used measures">
            <div className="widget-head">
              <div className="widget-title">
                <Calculator className="status-icon" aria-hidden="true" />
                <h3>Most-used measures</h3>
              </div>
              {mostUsedMeasures.length ? <span className="widget-badge muted">Top {mostUsedMeasures.length}</span> : null}
            </div>
            {mostUsedMeasures.length ? (
              <ul className="widget-list">
                {mostUsedMeasures.map(({ node, count }) => (
                  <li key={node.id} className="widget-list-row">
                    <div className="widget-list-name">
                      <TypeGlyph type="MEASURE" colors={colors} size="xs" />
                      <Button variant="link" size="sm" className="widget-link" onClick={() => onSelect(node.id, "inspector")} tooltip={node.name}>
                        {node.name}
                      </Button>
                      {node.scope ? <span className="widget-scope muted">{node.scope}</span> : null}
                    </div>
                    <span className="widget-metric" data-ui-number="">{formatCount(count)} {count === 1 ? "use" : "uses"}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="widget-empty muted">{overview?.measure_count === 0 ? "No measures in the scanned models." : "Not available until the project is scanned."}</p>
            )}
          </Card>

          <Card className="overview-widget" role="region" aria-label="Unreviewed on hot objects">
            <div className="widget-head">
              <div className="widget-title">
                <Flame className="status-icon tone-warn" aria-hidden="true" />
                <h3>Unreviewed on hot objects</h3>
              </div>
              {unreviewedOnHot.length ? <span className="widget-badge muted">Top {unreviewedOnHot.length}</span> : pending === 0 ? <span className="widget-badge muted">Clean</span> : null}
            </div>
            {unreviewedOnHot.length ? (
              <ul className="widget-list">
                {unreviewedOnHot.map(({ item, targetNode, targetId, degree }, idx) => (
                  <li key={item.id || `${targetId}-${idx}`} className="widget-list-row">
                    <div className="widget-list-name">
                      <TypeGlyph type={targetNode?.type || "OBJECT"} colors={colors} size="xs" />
                      <Button variant="link" size="sm" className="widget-link" onClick={() => onSelect(targetId, "inspector")} tooltip={targetNode ? targetNode.name : targetId}>
                        {targetNode ? targetNode.name : targetId}
                      </Button>
                      {item.scope ? <span className="widget-scope muted">{item.scope}</span> : null}
                      {item.kind === "conflict" ? <span className="badge-tag">conflict</span> : null}
                    </div>
                    <div className="widget-row-actions">
                      <span className="widget-metric" data-ui-number="">{formatCount(degree)} links</span>
                      <Button variant="ghost" size="sm" onClick={onReview}>Review</Button>
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="widget-empty muted">{pending === 0 ? "No pending suggestions or conflicts." : "Open the review queue to see them."}</p>
            )}
          </Card>

          {recentChanges.length ? <Card className="overview-widget" role="region" aria-label="Recently changed">
            <div className="widget-head">
              <div className="widget-title">
                <Clock className="status-icon" aria-hidden="true" />
                <h3>Recently changed</h3>
              </div>
              <span className="widget-badge muted">{recentChanges.length ? "Recent decisions" : "Idle"}</span>
            </div>
            {recentChanges.length ? (
              <ul className="widget-list">
                {recentChanges.map((entry) => (
                  <li key={entry.id} className="widget-list-row">
                    <div className="widget-list-name">
                      <TypeGlyph type={entry.type} colors={colors} size="xs" />
                      <Button variant="link" size="sm" className="widget-link" onClick={() => onSelect(entry.targetId, "inspector")} tooltip={entry.name}>
                        {entry.name}
                      </Button>
                      <span className={`badge-tag badge-status-${entry.action}`}>{entry.action}</span>
                    </div>
                    <span className="widget-metric muted">{entry.actor}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="widget-empty muted">No recent changes or review actions yet. Decisions will appear here as items are reviewed.</p>
            )}
          </Card> : null}
        </div>

        {transport && hasComparableSources(overview) && !scanning ? <CommonObjects transport={transport} colors={colors} onSelect={onSelect} onMerge={onMerge} refreshKey={overview.last_scan} /> : null}
      </>}
  </div>;
}
