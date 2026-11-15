// The Review queue: suggestions to decide, by row, by selection or by pattern, and the list of reviewed decisions.
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { groupReviewItems, GROUP_ABOVE } from "../reviewGroups.js";
import { Activity, Calculator, Check, ChevronRight, CircleCheck, FileText, Filter, Lightbulb, RefreshCw, RotateCcw, ShieldAlert, ShieldCheck, Table2, Tag, TriangleAlert, Type, Workflow, X, Zap } from "lucide-react";
import { useToast } from "../components/ui/toast";
import { SegmentedControl } from "../components/ui/segmented-control";
import { Tooltip } from "../components/ui/tooltip";
import ReviewDecision from "../components/ReviewDecision";
import ObjectContextPreview from "../components/ObjectContextPreview";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent } from "../components/ui/dialog";
import { isLowEvidence, explainConfidence } from "../reviewEvidence";
import { TypeGlyph } from "../components/TypeGlyph";
import { highlightDax } from "../dax";
import { byId, formatCount, objectScope, readableText, scopeChoices, suggestionLabel, suggestionParts, sanitizeDoublePunctuation } from "../presentation";
import { Button } from "../components/ui/button";
import { NativeSelect } from "../components/ui/native-select";
import { Badge } from "../components/ui/badge";
import { Card } from "../components/ui/card";
import { Label } from "../components/ui/label";
import { Skeleton } from "../components/ui/skeleton";
import { Checkbox } from "../components/ui/checkbox";
import { typeLabel } from "../graphPresentation";
import { confidence, labelFor, itemTarget, safeJson, itemConfidence, itemImpact, contentScroller, PageHeading, StatusBadge, EmptyState, formatDate, formatValue } from "./shared";

// Above this many suggestions a bulk approve or reject asks for confirmation.
const BULK_CONFIRM_ABOVE = 50;

export function reviewIssue(item) {
  const value = String(item?.issue || item?.issue_type || item?.kind || item?.type || "candidate").toLowerCase();
  if (value.includes("conflict")) return "conflict";
  if (value.includes("stale") || value.includes("override")) return "stale";
  return "candidate";
}

export function mergeReviewItems(items) {
  const merged = new Map();
  items.filter(Boolean).forEach((item, index) => {
    const issue = reviewIssue(item);
    const semanticKey = `${issue}:${itemTarget(item) || "unknown"}:${safeJson(item.value ?? item.meaning ?? item.reason ?? item.message ?? index)}`;
    const candidateId = item.candidate_id || item.properties?.candidate_id || item.item?.candidate_id || item.item?.properties?.candidate_id;
    const key = issue === "conflict" ? semanticKey : candidateId || item.id || semanticKey;
    merged.set(key, { ...merged.get(key), ...item, issue });
  });
  return [...merged.values()];
}

export function itemScopeValue(item, node, key) {
  return item?.[key] ?? item?.properties?.[key] ?? node?.[key] ?? node?.properties?.[key] ?? "";
}

// Keyboard triage (visual contract §9): J/K or ↓/↑ move between items, A approves, R rejects, X selects the focused item.
// Esc cancels any active inline edit.
function reviewKeys(event, onCancelEdit) {
  if (event.altKey || event.ctrlKey || event.metaKey) return;
  if (event.key === "Escape") {
    onCancelEdit?.();
    return;
  }
  if (event.target.closest("input, select, textarea")) return;
  const key = event.key.toLowerCase();
  const item = event.target.closest(".review-item");
  if (!item) return;
  if (key === "j" || key === "k" || event.key === "ArrowDown" || event.key === "ArrowUp") {
    const targets = [...event.currentTarget.querySelectorAll(".review-target:not(:disabled)")];
    const index = targets.indexOf(item.querySelector(".review-target"));
    const next = targets[index + (key === "j" || event.key === "ArrowDown" ? 1 : -1)];
    if (next) { next.focus(); next.scrollIntoView({ block: "nearest" }); event.preventDefault(); }
  } else if (key === "x") {
    const box = item.querySelector(".review-select");
    if (box && !box.disabled) { box.click(); event.preventDefault(); }
  } else if (key === "a" || key === "r") {
    const button = item.querySelector(key === "a" ? ".approve-button" : ".reject-button");
    if (button && !button.disabled) { button.click(); event.preventDefault(); }
  }
}

const REVIEW_PAGE = 50;
const reviewItemKey = (item) => item.id || `${item.issue}-${itemTarget(item)}`;

export function ReviewQueue({ session, onSession, snapshot, loaded, loading, error, onRetry, overview, onSelect, onReview, onBulkReview, scanning, colors, auditTrail = [], onUndoReview }) {
  const { issue = "ALL", objectType = "ALL", modelId = "ALL", reportId = "ALL", sort = "confidence-high", tab = "queue", group = "" } = session;
  const change = (values) => onSession((current) => ({ ...current, ...values }));
  const panel = useRef(null);
  const toast = useToast();
  const [activeEditId, setActiveEditId] = useState(null);
  const [bulkBusy, setBulkBusy] = useState(false);

  useEffect(() => {
    const frame = requestAnimationFrame(() => {
      const selected = [...(panel.current?.querySelectorAll("[data-review-id]") || [])].find((element) => element.dataset.reviewId === session.selectedId);
      if (selected) { selected.focus({ preventScroll: true }); contentScroller().scrollTop = session.scrollY || 0; }
    });
    return () => cancelAnimationFrame(frame);
  }, []);
  // Derived once per snapshot and filter, not on every render: the queue can hold more than 10,000 suggestions.
  const { all, types, models, reports, filtered, lowEvidenceItems, standardItems } = useMemo(() => {
    const external = snapshot.review_items.map((item) => ({ ...item, issue: reviewIssue(item) }));
    const candidates = snapshot.semantic_candidates.map((item) => ({ ...item, issue: "candidate" }));
    const conflicts = snapshot.conflicts.map((item) => ({ ...item, issue: "conflict", status: item.status || "candidate", confidence: item.confidence ?? 0 }));
    const staleRecords = [...snapshot.stale_overrides, ...snapshot.overrides.filter((item) => item.status === "stale"), ...external.filter((item) => item.issue === "stale")];
    const stale = staleRecords.map((item) => ({ ...item, issue: "stale", status: item.status || "candidate", confidence: item.confidence ?? 0 }));
    const all = mergeReviewItems(external.length ? external : [...candidates, ...conflicts, ...stale]).filter((item) => !["rejected", "approved", "overridden"].includes(item.status));
    const types = [...new Set(all.map((item) => byId(snapshot.nodes, itemTarget(item))?.type).filter(Boolean))].sort();
    const models = [...new Set(all.map((item) => itemScopeValue(item, byId(snapshot.nodes, itemTarget(item)), "model_id")).filter(Boolean))].sort();
    const reports = [...new Set(all.map((item) => itemScopeValue(item, byId(snapshot.nodes, itemTarget(item)), "report_id")).filter(Boolean))].sort();
    const filtered = all.filter((item) => {
      const targetNode = byId(snapshot.nodes, itemTarget(item));
      const isLow = isLowEvidence(item, snapshot.nodes);
      const matchesIssue = issue === "ALL" ? true : issue === "low-evidence" ? isLow : item.issue === issue;
      return matchesIssue
        && (objectType === "ALL" || targetNode?.type === objectType)
        && (modelId === "ALL" || itemScopeValue(item, targetNode, "model_id") === modelId)
        && (reportId === "ALL" || itemScopeValue(item, targetNode, "report_id") === reportId);
    }).sort((a, b) => {
      if (sort === "confidence-low") return itemConfidence(a) - itemConfidence(b);
      if (sort === "impact-high") return itemImpact(b) - itemImpact(a);
      if (sort === "impact-low") return itemImpact(a) - itemImpact(b);
      return itemConfidence(b) - itemConfidence(a);
    });

    const lowEvidenceItems = [];
    const standardItems = [];
    for (const item of filtered) (isLowEvidence(item, snapshot.nodes) ? lowEvidenceItems : standardItems).push(item);
    return { all, types, models, reports, filtered, lowEvidenceItems, standardItems };
  }, [snapshot, issue, objectType, modelId, reportId, sort]);
  // Rows are mounted in steps as the list is scrolled; a queue of 11,000 suggestions must not build 11,000 rows at once.
  const [shown, setShown] = useState(REVIEW_PAGE);
  const filterKey = `${issue}|${objectType}|${modelId}|${reportId}|${sort}|${tab}`;
  useEffect(() => { setShown(REVIEW_PAGE); }, [filterKey]);
  const more = useRef(null);
  const longest = Math.max(standardItems.length, lowEvidenceItems.length);
  useEffect(() => {
    const sentinel = more.current;
    if (!sentinel || shown >= longest || typeof IntersectionObserver !== "function") return undefined;
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) setShown((count) => count + REVIEW_PAGE);
    }, { rootMargin: "600px" });
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [shown, longest]);
  const moreRows = shown < longest
    ? <div ref={more} className="queue-more"><Button variant="ghost" size="sm" onClick={() => setShown((count) => count + REVIEW_PAGE)}>Show more ({(longest - shown).toLocaleString()} left)</Button></div>
    : null;
  const approvableItems = useMemo(() => filtered.filter((item) => item.issue !== "conflict" && item.issue !== "stale"), [filtered]);
  // Row selection: a decision over the rows the reviewer ticked. Conflicts and outdated decisions are decided one at a time.
  const [selected, setSelected] = useState(() => new Set());
  useEffect(() => { setSelected(new Set()); }, [filterKey]);
  const selectedItems = useMemo(() => selected.size ? approvableItems.filter((item) => selected.has(reviewItemKey(item))) : [], [selected, approvableItems]);
  const toggleSelected = useCallback((item, on) => setSelected((current) => {
    const next = new Set(current);
    if (on) next.add(reviewItemKey(item)); else next.delete(reviewItemKey(item));
    return next;
  }), []);
  const selectAll = (items, on) => setSelected((current) => {
    const next = new Set(current);
    for (const item of items) { if (on) next.add(reviewItemKey(item)); else next.delete(reviewItemKey(item)); }
    return next;
  });
  const selectionOf = (items) => {
    const count = items.reduce((total, item) => total + (selected.has(reviewItemKey(item)) ? 1 : 0), 0);
    return count === 0 ? false : count === items.length ? true : "indeterminate";
  };
  // A long queue opens as patterns (one rule, one basis, one object type), decided once each.
  const grouping = issue === "low-evidence" ? "none" : group || (filtered.length > GROUP_ABOVE ? "pattern" : "none");
  const groups = useMemo(() => grouping === "pattern" ? groupReviewItems(filtered, (item) => byId(snapshot.nodes, itemTarget(item))) : [], [grouping, filtered, snapshot.nodes]);
  const [openGroup, setOpenGroup] = useState({ key: "", shown: REVIEW_PAGE });

  // A bulk decision over many suggestions is asked for once more, with its scope named:
  // "Approve all" and "Reject all" sit next to each other and one click decided thousands.
  const [bulkConfirm, setBulkConfirm] = useState(null);
  const handleBulkAction = async (action, items, confirmed = false, scope = "") => {
    if (bulkBusy || scanning || !items?.length) return;
    if (!confirmed && items.length > BULK_CONFIRM_ABOVE) { setBulkConfirm({ action, items, scope }); return; }
    setBulkConfirm(null);
    setBulkBusy(true);
    try {
      if (onBulkReview) {
        await onBulkReview(action, items);
      } else {
        let count = 0;
        for (const item of items) {
          try {
            const ok = await onReview(action, item);
            if (ok !== false) count++;
          } catch {}
        }
        toast.show({
          tone: "ok",
          text: `${action === "approve" ? "Approved" : "Rejected"} ${count} ${count === 1 ? "suggestion" : "suggestions"}`,
        });
      }
      setSelected(new Set());
    } finally {
      setBulkBusy(false);
    }
  };

  const candidatesReviewed = (snapshot?.semantic_candidates || []).filter(
    (item) => ["approved", "rejected", "overridden"].includes(item.status)
  );
  const overridesReviewed = (snapshot?.overrides || []).filter((item) => item.status !== "stale");
  const seenReviewed = new Set();
  const allReviewed = [];
  for (const entry of auditTrail) {
    const key = entry.reviewId || entry.candidateId || entry.targetId;
    if (key && !seenReviewed.has(key)) {
      seenReviewed.add(key);
      allReviewed.push(entry);
    }
  }
  for (const item of candidatesReviewed) {
    const key = item.candidate_id || item.id;
    if (key && !seenReviewed.has(key)) {
      seenReviewed.add(key);
      allReviewed.push({
        id: `snap-${key}`,
        reviewId: key,
        candidateId: key,
        targetId: itemTarget(item),
        action: item.status,
        actor: item.decided_by === "auto" ? "Auto" : "Reviewer",
        auto: item.decided_by === "auto",
        timestamp: snapshot?.scan?.last_scan || new Date().toISOString(),
        label: suggestionLabel(item),
        value: item.value,
        property: item.property,
        item,
        confidence: itemConfidence(item),
      });
    }
  }
  for (const item of overridesReviewed) {
    const key = `override:${item.target}:${item.property}`;
    if (!seenReviewed.has(key)) {
      seenReviewed.add(key);
      allReviewed.push({
        id: `snap-${key}`,
        reviewId: key,
        candidateId: key,
        targetId: item.target,
        action: "overridden",
        actor: "Reviewer",
        timestamp: snapshot?.scan?.last_scan || new Date().toISOString(),
        label: suggestionLabel(item),
        value: item.value,
        property: item.property,
        item,
        confidence: itemConfidence(item),
      });
    }
  }

  const reviewRow = (item) => (
    <ReviewItem
      colors={colors}
      key={reviewItemKey(item)}
      item={item}
      nodes={snapshot.nodes}
      edges={snapshot.edges}
      disabled={scanning}
      selectable={item.issue !== "conflict" && item.issue !== "stale"}
      selected={selected.has(reviewItemKey(item))}
      onSelected={toggleSelected}
      isEditing={activeEditId === (item.id || itemTarget(item))}
      onStartEdit={() => setActiveEditId(item.id || itemTarget(item))}
      onCancelEdit={() => setActiveEditId(null)}
      onSelect={(id, nextView) => {
        change({ selectedId: item.id || itemTarget(item), scrollY: contentScroller().scrollTop });
        onSelect(id, nextView);
      }}
      onReview={onReview}
    />
  );
  const percent = (value) => `${Math.round(value * 100)} %`;
  const groupList = grouping === "pattern" ? <div className="review-groups">
    <div className="review-group-columns" aria-hidden="true"><span>Pattern</span><span>Suggestions</span><span>Confidence</span><span>Decision</span></div>
    {groups.map((entry) => {
      const open = openGroup.key === entry.key;
      const count = entry.items.length;
      const label = `${entry.title}${entry.scope ? ` · ${entry.scope}` : ""}`;
      return <section className={`review-group${open ? " is-open" : ""}`} key={entry.key} aria-label={label}>
        <div className="review-group-head">
          <button type="button" className="review-group-toggle" aria-expanded={open} onClick={() => setOpenGroup(open ? { key: "", shown: REVIEW_PAGE } : { key: entry.key, shown: REVIEW_PAGE })}>
            <ChevronRight className={open ? "is-open" : ""} aria-hidden="true" />
            <span className="review-group-title">{entry.title}</span>
            {entry.scope ? <span className="review-group-scope">{entry.scope}</span> : null}
          </button>
          <span className="review-group-count" data-ui-number="">{formatCount(count)}{entry.names && entry.names < count ? <small> · {formatCount(entry.names)} names</small> : null}</span>
          <span className="review-group-confidence" data-ui-number="">{entry.bulk ? (entry.low === entry.high ? percent(entry.high) : `${percent(entry.low)} – ${percent(entry.high)}`) : "—"}</span>
          <span className="review-group-actions" data-ui-actions="">
            {entry.bulk ? <>
              <Button variant="outline" size="sm" className="group-approve" disabled={bulkBusy || scanning} aria-label={`Approve ${formatCount(count)}: ${label}`} onClick={() => handleBulkAction("approve", entry.items, false, label)}><Check aria-hidden="true" />Approve</Button>
              <Button variant="ghost" size="sm" className="group-reject" disabled={bulkBusy || scanning} aria-label={`Reject ${formatCount(count)}: ${label}`} onClick={() => handleBulkAction("reject", entry.items, false, label)}><X aria-hidden="true" />Reject</Button>
            </> : <small>One at a time</small>}
          </span>
        </div>
        {open ? <>
          {entry.bulk ? <div className="review-group-select"><Checkbox className="review-select-all" checked={selectionOf(entry.items)} disabled={bulkBusy || scanning} aria-label={`Select all ${formatCount(count)}: ${label}`} onCheckedChange={(value) => selectAll(entry.items, value === true)} /><span aria-hidden="true">Select all {formatCount(count)}</span></div> : null}
          <div className="queue-list" onKeyDown={(e) => reviewKeys(e, () => setActiveEditId(null))}>{entry.items.slice(0, openGroup.shown).map(reviewRow)}</div>
          {count > openGroup.shown ? <div className="queue-more"><Button variant="ghost" size="sm" onClick={() => setOpenGroup((current) => ({ ...current, shown: current.shown + REVIEW_PAGE }))}>Show more ({formatCount(count - openGroup.shown)} left)</Button></div> : null}
        </> : null}
      </section>;
    })}
  </div> : null;
  const scopes = [...scopeChoices(overview, "model"), ...scopeChoices(overview, "report"), ...snapshot.nodes];
  const scopeName = (id, kind, index) => scopes.find((node) => node.id === id)?.name || `${kind} ${index + 1}`;
  const hasFilters = issue !== "ALL" || objectType !== "ALL" || modelId !== "ALL" || reportId !== "ALL";
  return <div ref={panel}>
    <div className="queue-header-row">
      <PageHeading quiet title="Review queue" />
      <SegmentedControl
        options={[
          { value: "queue", label: `To review (${formatCount(filtered.length)})` },
          { value: "reviewed", label: `Reviewed (${formatCount(allReviewed.length)})` },
        ]}
        value={tab}
        onValueChange={(val) => change({ tab: val })}
        aria-label="Review views"
      />
    </div>
    {error && !loaded ? <Card className="panel" role="alert"><EmptyState icon={<TriangleAlert />} tone="bad" title="Review queue unavailable" detail={readableText(error)} action={<Button variant="outline" onClick={onRetry}><RefreshCw />Retry review queue</Button>} /></Card> : <>
    {error ? <Card className="panel" role="alert"><EmptyState icon={<TriangleAlert />} tone="bad" title="Review refresh failed" detail={`Showing last loaded reviews. ${readableText(error)}`} action={<Button variant="outline" onClick={onRetry}><RefreshCw />Retry review queue</Button>} /></Card> : null}
    {tab === "reviewed" ? (
      <>
        <p className="review-purpose">
          <span className="queue-count"><strong data-ui-number="">{allReviewed.length}</strong> reviewed</span>
          <span className="review-purpose-copy">Audit trail of reviewed decisions. Use Reopen to return a suggestion to the queue.</span>
        </p>
        <Card className="panel queue-panel">
          {allReviewed.length ? (
            <>
              <div className="review-columns" aria-hidden="true">
                <span>Object &amp; suggestion</span>
                <span>Decision &amp; reviewer</span>
                <span>Status</span>
                <span>Action</span>
              </div>
              <div className="queue-list">
                {allReviewed.slice(0, shown).map((entry) => (
                  <ReviewedItem
                    colors={colors}
                    key={entry.id || entry.reviewId}
                    entry={entry}
                    nodes={snapshot.nodes}
                    disabled={scanning}
                    onSelect={onSelect}
                    onUndo={onUndoReview}
                  />
                ))}
              </div>
              {allReviewed.length > shown ? <div className="queue-more"><Button variant="ghost" size="sm" onClick={() => setShown((count) => count + REVIEW_PAGE)}>Show more ({formatCount(allReviewed.length - shown)} left)</Button></div> : null}
            </>
          ) : (
            <EmptyState
              icon={<CircleCheck />}
              tone="ok"
              title="No reviewed items yet"
              detail="Suggestions you approve or reject will appear here as an audit trail."
            />
          )}
        </Card>
      </>
    ) : (
      <>
        <p className="review-purpose"><span className="queue-count"><strong data-ui-number="">{loading ? "…" : formatCount(filtered.length)}</strong>{loading ? "Loading…" : " to review"}</span><span className="review-purpose-copy" /><span className="review-keys" aria-hidden="true"><kbd>J</kbd><kbd>K</kbd> move <kbd>A</kbd> approve <kbd>R</kbd> reject <kbd>X</kbd> select</span></p>
        <div className="queue-toolbar" data-ui-actions="">
          <Label className="select-field"><span>Issue</span><NativeSelect aria-label="Issue" value={issue} onChange={(event) => change({ issue: event.target.value })}><option value="ALL">All issues</option><option value="candidate">Suggestions</option><option value="low-evidence">Low evidence</option><option value="conflict">Conflicts</option><option value="stale">Outdated decisions</option></NativeSelect></Label>
          <Label className="select-field"><span>Object</span><NativeSelect aria-label="Object" value={objectType} onChange={(event) => change({ objectType: event.target.value })}><option value="ALL">All types</option>{types.map((type) => <option key={type} value={type}>{typeLabel(type)}</option>)}</NativeSelect></Label>
          {models.length > 1 ? <Label className="select-field"><span>Model</span><NativeSelect aria-label="Model" value={modelId} onChange={(event) => change({ modelId: event.target.value, reportId: "ALL" })}><option value="ALL">All models</option>{models.map((value, index) => <option key={value} value={value}>{scopeName(value, "Model", index)}</option>)}</NativeSelect></Label> : null}
          {reports.length > 1 ? <Label className="select-field"><span>Report</span><NativeSelect aria-label="Report" value={reportId} onChange={(event) => change({ reportId: event.target.value, modelId: "ALL" })}><option value="ALL">All reports</option>{reports.map((value, index) => <option key={value} value={value}>{scopeName(value, "Report", index)}</option>)}</NativeSelect></Label> : null}
          {hasFilters ? <Button variant="ghost" size="sm" onClick={() => change({ issue: "ALL", objectType: "ALL", modelId: "ALL", reportId: "ALL" })}><X />Clear filters</Button> : null}
          {issue !== "low-evidence" && filtered.length > 1 ? <Label className="select-field select-group"><span>Group</span><NativeSelect aria-label="Group" value={grouping} onChange={(event) => change({ group: event.target.value })}><option value="pattern">By pattern</option><option value="none">No grouping</option></NativeSelect></Label> : null}
          <Label className="select-field select-sort"><span>Sort</span><NativeSelect aria-label="Sort" value={sort} onChange={(event) => change({ sort: event.target.value })}><option value="confidence-high">Most certain first</option><option value="confidence-low">Least certain first</option><option value="impact-high">Highest impact first</option><option value="impact-low">Lowest impact first</option></NativeSelect></Label>
          {selectedItems.length > 0 ? (
            <div className="queue-bulk-actions is-selection" data-ui-actions="" role="group" aria-label="Selected suggestions">
              <Button variant="outline" size="sm" className="selected-approve" disabled={bulkBusy || scanning} onClick={() => handleBulkAction("approve", selectedItems)}>
                <Check className="size-4" aria-hidden="true" />Approve {formatCount(selectedItems.length)} selected
              </Button>
              <Button variant="ghost" size="sm" className="selected-reject" disabled={bulkBusy || scanning} onClick={() => handleBulkAction("reject", selectedItems)}>
                <X className="size-4" aria-hidden="true" />Reject {formatCount(selectedItems.length)} selected
              </Button>
              <Button variant="ghost" size="icon-sm" className="selected-clear" aria-label="Clear selection" title="Clear selection" onClick={() => setSelected(new Set())}><X aria-hidden="true" /></Button>
            </div>
          ) : null}
          {selectedItems.length === 0 && approvableItems.length > 0 && grouping !== "pattern" ? (
            <div className="queue-bulk-actions" data-ui-actions="">
              <Button variant="outline" size="sm" className="bulk-approve" disabled={bulkBusy || scanning} onClick={() => handleBulkAction("approve", approvableItems)}>
                <Check className="size-4" aria-hidden="true" />
                {hasFilters ? `Approve filtered (${formatCount(approvableItems.length)})` : `Approve all (${formatCount(approvableItems.length)})`}
              </Button>
              <Button variant="ghost" size="sm" className="bulk-reject" disabled={bulkBusy || scanning} onClick={() => handleBulkAction("reject", approvableItems)}>
                <X className="size-4" aria-hidden="true" />
                {hasFilters ? `Reject filtered (${formatCount(approvableItems.length)})` : `Reject all (${formatCount(approvableItems.length)})`}
              </Button>
            </div>
          ) : null}
        </div>
        <AlertDialog open={Boolean(bulkConfirm)} onOpenChange={(open) => { if (!open) setBulkConfirm(null); }}>
          {bulkConfirm ? <AlertDialogContent
            title={`${bulkConfirm.action === "approve" ? "Approve" : "Reject"} ${formatCount(bulkConfirm.items.length)} suggestions?`}
            description={`${bulkConfirm.scope ? `Every suggestion in “${bulkConfirm.scope}”` : bulkConfirm.items.length === approvableItems.length ? (hasFilters ? "Every suggestion that matches the current filters" : "Every open suggestion in the project") : "The selected suggestions"} will be ${bulkConfirm.action === "approve" ? "approved" : "rejected"}. Each decision can be changed later under Reviewed.`}
            footer={<><AlertDialogCancel asChild><Button variant="outline">Cancel</Button></AlertDialogCancel><AlertDialogAction asChild><Button variant={bulkConfirm.action === "approve" ? "default" : "destructive"} onClick={() => handleBulkAction(bulkConfirm.action, bulkConfirm.items, true)}>{bulkConfirm.action === "approve" ? "Approve" : "Reject"} {formatCount(bulkConfirm.items.length)}</Button></AlertDialogAction></>}
          /> : null}
        </AlertDialog>
        <Card className="panel queue-panel" aria-busy={loading}>
          {loading ? <div className="queue-loading">{[0, 1, 2].map((index) => <Skeleton className="skeleton-row-item" key={index} />)}<p className="sr-only" role="status">Loading suggestions…</p></div> : filtered.length && groupList ? groupList : filtered.length ? <>
            <div className="review-columns is-pending has-select">
              <span>{approvableItems.length ? <Checkbox className="review-select-all" checked={selectionOf(approvableItems)} disabled={bulkBusy || scanning} aria-label={`Select all ${formatCount(approvableItems.length)} suggestions`} onCheckedChange={(value) => selectAll(approvableItems, value === true)} /> : null}<span aria-hidden="true">Object</span></span>
              <span aria-hidden="true">Suggestion</span><span aria-hidden="true">Based on</span><span aria-hidden="true">Confidence</span><span aria-hidden="true">Decision</span>
            </div>
            {issue === "low-evidence" ? (
              <div className="low-evidence-group" role="region" aria-label="Low evidence suggestions">
                <div className="low-evidence-header">
                  <div className="low-evidence-title">
                    <ShieldAlert className="size-4" aria-hidden="true" />
                    <div>
                      <h3>Low-evidence suggestions ({lowEvidenceItems.length})</h3>
                      <p>Name-only tautologies and weak proposals with no supporting description or formula.</p>
                    </div>
                  </div>
                  <div className="low-evidence-actions" data-ui-actions="">
                    <Button variant="outline" size="sm" className="bulk-approve-low" disabled={bulkBusy || scanning} onClick={() => handleBulkAction("approve", lowEvidenceItems)}><Check className="size-4" aria-hidden="true" />Approve all low-evidence ({lowEvidenceItems.length})</Button>
                    <Button variant="ghost" size="sm" className="bulk-reject-low" disabled={bulkBusy || scanning} onClick={() => handleBulkAction("reject", lowEvidenceItems)}><X className="size-4" aria-hidden="true" />Reject all low-evidence ({lowEvidenceItems.length})</Button>
                  </div>
                </div>
                <div className="queue-list" onKeyDown={(e) => reviewKeys(e, () => setActiveEditId(null))}>
                  {lowEvidenceItems.slice(0, shown).map(reviewRow)}
                </div>
              </div>
            ) : (
              <>
                {standardItems.length ? (
                  <div className="queue-list" onKeyDown={(e) => reviewKeys(e, () => setActiveEditId(null))}>
                    {standardItems.slice(0, shown).map(reviewRow)}
                  </div>
                ) : null}

                {lowEvidenceItems.length ? (
                  <div className="low-evidence-group" role="region" aria-label="Low evidence suggestions">
                    <div className="low-evidence-header">
                      <div className="low-evidence-title">
                        <ShieldAlert className="size-4" aria-hidden="true" />
                        <div>
                          <h3>Low-evidence suggestions ({lowEvidenceItems.length})</h3>
                          <p>Name-only tautologies and weak proposals with no supporting description or formula.</p>
                        </div>
                      </div>
                      <div className="low-evidence-actions" data-ui-actions="">
                        <Button variant="outline" size="sm" className="bulk-approve-low" disabled={bulkBusy || scanning} onClick={() => handleBulkAction("approve", lowEvidenceItems)}><Check className="size-4" aria-hidden="true" />Approve all low-evidence ({lowEvidenceItems.length})</Button>
                        <Button variant="ghost" size="sm" className="bulk-reject-low" disabled={bulkBusy || scanning} onClick={() => handleBulkAction("reject", lowEvidenceItems)}><X className="size-4" aria-hidden="true" />Reject all low-evidence ({lowEvidenceItems.length})</Button>
                      </div>
                    </div>
                    <div className="queue-list" onKeyDown={(e) => reviewKeys(e, () => setActiveEditId(null))}>
                      {lowEvidenceItems.slice(0, shown).map(reviewRow)}
                    </div>
                  </div>
                ) : null}
              </>
            )}
            {moreRows}
          </> : <EmptyState icon={hasFilters ? <ShieldCheck /> : <CircleCheck />} tone={hasFilters || !overview?.counts?.nodes ? undefined : "ok"} title={hasFilters ? "No matching reviews" : overview?.counts?.nodes ? "Queue is clear" : "Nothing to review yet"} detail={hasFilters ? "Choose different filters to see the remaining reviews." : overview?.counts?.nodes ? "All suggestions have been reviewed." : "Suggestions appear after the first scan."} action={hasFilters ? <Button variant="outline" onClick={() => change({ issue: "ALL", objectType: "ALL", modelId: "ALL", reportId: "ALL" })}>Clear filters</Button> : null} />}
        </Card>
      </>
    )}
    </>}
  </div>;
}

function ReviewedItem({ entry, nodes, colors, onSelect, onUndo, disabled = false }) {
  const targetNode = byId(nodes, entry.targetId);
  const [pending, setPending] = useState(false);
  const status = entry.action === "approve" ? "approved" : entry.action === "reject" ? "rejected" : entry.action === "remove" ? "stale" : entry.action || "approved";
  const actionText = entry.auto ? "Accepted by the auto-accept setting" : status === "approved" ? "Approved" : status === "rejected" ? "Rejected" : status === "overridden" ? "Edited" : "Decision removed";
  const score = confidence(entry.confidence);
  const dateStr = formatDate(entry.timestamp);

  const handleReopen = async () => {
    if (pending || disabled) return;
    setPending(true);
    try {
      await onUndo(entry);
    } finally {
      setPending(false);
    }
  };

  return (
    <div className={`review-item issue-${status}`} aria-busy={pending}>
      <Button
        variant="ghost"
        className="review-target"
        data-review-id={entry.reviewId || entry.targetId}
        disabled={!targetNode}
        onClick={() => targetNode && onSelect(targetNode.id, "inspector")}>
        {targetNode ? <TypeGlyph node={targetNode} colors={colors} size="sm" /> : <span className={`review-dot ${status}`} />}
        <span className="review-target-copy">
          <strong>{targetNode ? labelFor(targetNode) : "Source object"}</strong>
          <small className="review-scope">{objectScope(targetNode, nodes)}</small>
          <small className={`review-suggestion issue-${status}`}>{entry.label || formatValue(entry.value)}</small>
          {targetNode ? <small className="review-type">{typeLabel(targetNode.type)}</small> : null}
        </span>
      </Button>
      <div className="review-evidence">
        <p className="reviewed-actor-line">
          {entry.auto ? <Badge variant="outline" className="auto-mark" title="Accepted by the auto-accept setting (Settings › Review)"><Zap aria-hidden="true" />Auto</Badge> : <strong>{entry.actor || "You"}</strong>} &bull; <span>{actionText}</span>
        </p>
        <small className="reviewed-timestamp">{dateStr}</small>
      </div>
      <div className="review-score">
        <StatusBadge value={status} />
        {score !== null ? <strong data-ui-number="">{score}%</strong> : null}
      </div>
      <div className="review-actions" data-ui-actions="">
        <Button
          variant="outline"
          size="sm"
          className="reopen-button"
          disabled={pending || disabled}
          onClick={handleReopen}>
          <RotateCcw aria-hidden="true" />
          Reopen
        </Button>
      </div>
    </div>
  );
}

const SUGGESTION_ICONS = { ROLE: Table2, BUSINESS_CONCEPT: Lightbulb, BEHAVIOR: Activity, ALIAS: Tag, SELECTOR: Filter };
const REVIEW_SOURCES = { object_name: [Type, "From the name"], name: [Type, "From the name"], description: [FileText, "From the description"], dax_ast: [Calculator, "From the formula"], dax_analysis: [Calculator, "From the formula"], rule: [Workflow, "From a rule"] };

function ReviewItem({
  item,
  nodes,
  edges = [],
  onSelect,
  onReview,
  colors,
  disabled = false,
  selectable = false,
  selected = false,
  onSelected,
  isEditing = false,
  onStartEdit,
  onCancelEdit,
}) {
  const targetNode = byId(nodes, itemTarget(item));
  const [pending, setPending] = useState(false);
  const [exiting, setExiting] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [error, setError] = useState("");
  const rowRef = useRef(null);

  const decide = async (action, reviewItem, valueOverride) => {
    if (pending || disabled || exiting) return;
    setError("");

    const currentRow = rowRef.current;
    const parentList = currentRow?.closest(".queue-list");
    const allRows = parentList ? [...parentList.querySelectorAll(".review-item:not(.is-exiting)")] : [];
    const currentIndex = allRows.indexOf(currentRow);
    const nextRow = allRows[currentIndex + 1] || allRows[currentIndex - 1];
    const nextNameTarget = nextRow?.querySelector(".review-target:not(:disabled)");

    setExiting(true);
    if (nextNameTarget) {
      nextNameTarget.focus({ preventScroll: true });
    }

    setPending(true);
    const isReduced = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (!isReduced) {
      await new Promise((resolve) => setTimeout(resolve, 180));
    }
    try {
      if (!await onReview(action, item, valueOverride)) {
        setExiting(false);
        setError("Decision could not be saved. Try again.");
      }
    } catch {
      setExiting(false);
      setError("Decision could not be saved. Try again.");
    } finally {
      setPending(false);
    }
  };

  const evidence = readableText(item.evidence?.length ? item.evidence : item.item?.evidence, nodes);
  const rawReason = item.reason || (item.source === "object_name" ? "Only the object name supports this meaning; no description confirms it." : item.source === "description" ? "The source description suggests this meaning. Confirm that the label fits." : "An inference rule proposed this meaning. Confirm it using the recorded evidence.");
  const reason = sanitizeDoublePunctuation(rawReason);
  const score = confidence(item.confidence ?? item.properties?.confidence);
  const level = score === null ? "none" : score >= 80 ? "high" : score >= 50 ? "mid" : "low";
  const confidenceTip = explainConfidence(item, targetNode);
  const expression = targetNode?.expression ?? targetNode?.properties?.expression;
  const parts = suggestionParts(item);
  const chipKind = item.issue === "conflict" ? "Conflict" : item.issue === "stale" ? "Outdated" : parts.label;
  const chipText = item.issue === "conflict" ? "Conflicting suggestions" : item.issue === "stale" ? "Outdated saved decision" : parts.value;
  const chipTitle = item.issue === "conflict" || item.issue === "stale" ? chipText : `${parts.label}: ${parts.value}`;
  const ChipIcon = item.issue === "conflict" || item.issue === "stale" ? TriangleAlert : SUGGESTION_ICONS[parts.kind] || Lightbulb;
  const [SourceIcon, sourceText] = REVIEW_SOURCES[item.item?.properties?.candidate_source || item.properties?.candidate_source || item.source] || REVIEW_SOURCES.rule;

  return (
    <div
      ref={rowRef}
      className={`review-item compact-row issue-${item.issue} ${exiting ? "is-exiting" : ""} ${expanded ? "is-expanded" : ""} ${selected ? "is-selected" : ""}`}
      aria-busy={pending}
    >
      <div className="review-main-cell">
        {onSelected ? (selectable
          ? <Checkbox className="review-select" checked={selected} disabled={disabled || pending || exiting} aria-label={`Select ${targetNode ? labelFor(targetNode) : "suggestion"}`} onCheckedChange={(value) => onSelected(item, value === true)} />
          : <span className="review-select-gap" aria-hidden="true" />) : null}
        <Button
          variant="ghost"
          size="icon-xs"
          className="row-expand-button"
          aria-expanded={expanded}
          aria-label={expanded ? "Hide evidence" : "Show evidence"}
          onClick={() => setExpanded((prev) => !prev)}
        >
          <ChevronRight className={`size-3.5 transition-transform ${expanded ? "rotate-90" : ""}`} aria-hidden="true" />
        </Button>
        <ObjectContextPreview node={targetNode} nodes={nodes} edges={edges} colors={colors} onSelect={onSelect}>
          <Button
            variant="ghost"
            className="review-target"
            data-review-id={item.id || itemTarget(item)}
            disabled={!targetNode}
            onClick={() => targetNode && onSelect(targetNode.id, "inspector")}
          >
            {targetNode ? <TypeGlyph node={targetNode} colors={colors} size="sm" /> : <span className={`review-dot ${item.issue}`} />}
            <span className="review-target-copy">
              <strong>{targetNode ? labelFor(targetNode) : "Source object unavailable"}</strong>
              <small className="review-scope">{objectScope(targetNode, nodes)}</small>
            </span>
          </Button>
        </ObjectContextPreview>
      </div>

      <div className="review-suggestion-cell">
        <span className={`review-suggestion-chip review-suggestion issue-${item.issue}`} title={chipTitle}>
          <ChipIcon className="size-3.5" aria-hidden="true" />
          <span className="sr-only">{chipKind}: </span>
          <span className="review-suggestion-value">{chipText}</span>
        </span>
      </div>

      <div className="review-evidence-summary" title={readableText(reason, nodes)}>
        <SourceIcon className="size-3.5" aria-hidden="true" />
        <span>{sourceText}</span>
      </div>

      <Tooltip content={confidenceTip}>
        <div className={`review-score level-${level}`} tabIndex={0} role="group" aria-label={`Confidence ${score}%`}>
          <strong data-ui-number="">{score === null ? "-" : `${confidence(itemConfidence(item))}%`}</strong>
          <span className="meter" aria-hidden="true"><i style={{ transform: `scaleX(${(score ?? 0) / 100})` }} /></span>
        </div>
      </Tooltip>

      <ReviewDecision
        item={item}
        onReview={onReview}
        onDecide={decide}
        disabled={disabled || pending || exiting}
        isEditing={isEditing}
        onStartEdit={onStartEdit}
        onCancelEdit={onCancelEdit}
        compact={true}
        iconOnly={true}
      />

      {error ? <p className="review-decision-error" role="alert">{error}</p> : null}

      {expanded ? (
        <div className="review-evidence-expanded" id={`evidence-${item.id || itemTarget(item)}`}>
          <div className="evidence-reason">
            <p>{readableText(reason, nodes)}</p>
            {evidence ? <small className="evidence-detail">{evidence}</small> : null}
          </div>
          {expression ? (
            <div className="evidence-formula">
              <span className="code-lang">DAX</span>
              <pre><code>{highlightDax(expression)}</code></pre>
            </div>
          ) : null}
          {targetNode ? (
            <div className="evidence-actions">
              <Button variant="link" size="sm" onClick={() => onSelect(targetNode.id, "inspector")}>
                View details in Inspector →
              </Button>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}



export default ReviewQueue;
