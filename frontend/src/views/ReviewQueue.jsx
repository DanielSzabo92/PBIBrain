// The Review queue: suggestions to decide, by row, by selection or by pattern, and the list of reviewed decisions.
// Rows, counts, filter choices and patterns come a page at a time from the server (finding 01): the page never
// holds the whole queue, and a decision over a pattern or the filters is chosen on the server.
import React, { startTransition, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Activity, Calculator, Check, ChevronRight, CircleCheck, FileText, Filter, Lightbulb, RefreshCw, RotateCcw, ShieldAlert, ShieldCheck, Table2, Tag, TriangleAlert, Type, Workflow, X, Zap } from "lucide-react";
import { listMove, moveInList } from "../listNavigation";
import { SegmentedControl } from "../components/ui/segmented-control";
import { Tooltip } from "../components/ui/tooltip";
import ReviewDecision from "../components/ReviewDecision";
import ObjectContextPreview from "../components/ObjectContextPreview";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent } from "../components/ui/dialog";
import { explainConfidence } from "../reviewEvidence";
import { TypeGlyph } from "../components/TypeGlyph";
import { highlightDax } from "../dax";
import { byId, formatCount, objectScope, readableText, scopeChoices, suggestionLabel, suggestionParts, sanitizeDoublePunctuation } from "../presentation";
import { Button } from "../components/ui/button";
import { NativeSelect } from "../components/ui/native-select";
import { Badge } from "../components/ui/badge";
import { Card } from "../components/ui/card";
import { Label } from "../components/ui/label";
import { Checkbox } from "../components/ui/checkbox";
import { typeLabel } from "../graphPresentation";
import { confidence, labelFor, itemTarget, itemConfidence, contentScroller, PageHeading, StatusBadge, EmptyState, formatDate, formatValue } from "./shared";

// Above this many suggestions a bulk approve or reject asks for confirmation.
const BULK_CONFIRM_ABOVE = 50;
// A queue longer than this opens as patterns (one rule, one basis, one object type), decided once each.
const GROUP_ABOVE = 200;
// Rows per request; a refresh after a decision asks again for every row loaded, up to the server's limit.
const REVIEW_PAGE = 25;
const MAX_ROWS = 500;

// Keyboard triage (visual contract §9): the shared list keys (↓/↑, Home/End) and J/K move between items, A approves, R rejects, X selects the focused item.
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
  const where = key === "j" ? "next" : key === "k" ? "previous" : listMove(event);
  if (where && !where.startsWith("page")) {
    event.preventDefault();
    moveInList(event.currentTarget, where, item.querySelector(".review-target"), ".review-target:not(:disabled)");
  } else if (key === "x") {
    const box = item.querySelector(".review-select");
    if (box && !box.disabled) { box.click(); event.preventDefault(); }
  } else if (key === "a" || key === "r") {
    const button = item.querySelector(key === "a" ? ".approve-button" : ".reject-button");
    if (button && !button.disabled) { button.click(); event.preventDefault(); }
  }
}

const reviewItemKey = (item) => item.key || item.id || `${item.issue}-${itemTarget(item)}`;
const mergeById = (current, added) => {
  if (!added?.length) return current;
  const merged = new Map(current.map((entry) => [entry.id, entry]));
  for (const entry of added) if (entry?.id && !merged.has(entry.id)) merged.set(entry.id, entry);
  return [...merged.values()];
};
const EMPTY_PAGE = { key: "", page: null, items: [], nodes: [], loading: false, error: "" };
// The context nodes of the page a row came with. A row reads these instead of the list's merged nodes, so
// loading another page leaves the rows already shown untouched (finding 01: scrolling holds the frame rate).
const PAGE_NODES = new WeakMap();
const rememberNodes = (page) => {
  const nodes = page?.nodes || [];
  for (const item of page?.items || []) PAGE_NODES.set(item, nodes);
  return page;
};

/**
 * Rows of one query, a page at a time. ``more`` adds the next page; a new ``revision`` (a decision, a scan)
 * asks again for as many rows as are loaded, so the list keeps its length and the reviewer their place.
 */
function useReviewPages(transport, query, revision, enabled = true) {
  const key = enabled ? JSON.stringify(query) : "";
  const [state, setState] = useState(EMPTY_PAGE);
  const [attempt, setAttempt] = useState(0);
  const loaded = useRef({ key: "", count: 0 });
  const busy = useRef(false);
  useEffect(() => {
    if (!enabled) return undefined;
    let active = true;
    const again = loaded.current.key === key;
    const limit = again ? Math.min(MAX_ROWS, Math.max(REVIEW_PAGE, loaded.current.count)) : REVIEW_PAGE;
    setState((current) => current.key === key ? { ...current, error: "" } : { ...EMPTY_PAGE, key, loading: true });
    transport.getReviewPage({ ...query, offset: 0, limit }).then(rememberNodes).then((page) => {
      if (!active) return;
      loaded.current = { key, count: page.items?.length || 0 };
      setState({ key, page, items: page.items || [], nodes: page.nodes || [], loading: false, error: "" });
    }).catch((cause) => {
      if (active) setState((current) => ({ ...(current.key === key ? current : EMPTY_PAGE), key, loading: false, error: cause?.message || "Review data could not be loaded" }));
    });
    return () => { active = false; };
    // The query is in the key.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, revision, attempt, transport, enabled]);
  const current = state.key === key ? state : { ...EMPTY_PAGE, key, loading: enabled };
  const more = useCallback(async () => {
    if (busy.current || !current.page?.has_more) return;
    busy.current = true;
    try {
      const page = rememberNodes(await transport.getReviewPage({ ...query, offset: current.items.length, limit: REVIEW_PAGE }));
      setState((latest) => {
        if (latest.key !== key) return latest;
        const seen = new Set(latest.items.map(reviewItemKey));
        const items = [...latest.items, ...(page.items || []).filter((item) => !seen.has(reviewItemKey(item)))];
        loaded.current = { key, count: items.length };
        return { ...latest, page: { ...page, items: undefined }, items, nodes: mergeById(latest.nodes, page.nodes) };
      });
    } catch (cause) {
      setState((latest) => latest.key === key ? { ...latest, error: cause?.message || "Review data could not be loaded" } : latest);
    } finally {
      busy.current = false;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, current.page, current.items.length, transport]);
  // A decided row leaves at once; the refresh that follows confirms it (and keeps it gone if the refresh fails).
  const drop = useCallback((rowKey) => setState((latest) => {
    if (latest.key !== key || !latest.items.some((item) => reviewItemKey(item) === rowKey)) return latest;
    loaded.current = { key, count: Math.max(0, latest.items.length - 1) };
    return { ...latest, items: latest.items.filter((item) => reviewItemKey(item) !== rowKey), page: latest.page && { ...latest.page, total: Math.max(0, (latest.page.total || 0) - 1) } };
  }), [key]);
  const total = current.page?.total ?? 0;
  return { ...current, total, approvable: current.page?.approvable_total ?? 0, left: Math.max(0, total - current.items.length), more, drop, retry: () => setAttempt((value) => value + 1) };
}

/**
 * Rows a few per frame: a page that arrives while the reviewer scrolls is mounted over several frames
 * instead of in one long task, so scrolling holds the frame rate (finding 01).
 */
const ROWS_PER_FRAME = 5;
function useRevealed(items) {
  const [count, setCount] = useState(ROWS_PER_FRAME);
  const length = items.length;
  useEffect(() => {
    if (count >= length || typeof requestAnimationFrame !== "function") return undefined;
    // A transition: React renders the new rows in slices and lets each frame through.
    const frame = requestAnimationFrame(() => startTransition(() => setCount((current) => Math.min(length, current + ROWS_PER_FRAME))));
    return () => cancelAnimationFrame(frame);
  }, [count, length]);
  return typeof requestAnimationFrame === "function" && count < length ? items.slice(0, count) : items;
}

/** "Show more (N left)"; it also loads by itself when it scrolls near the window. */
function MoreRows({ pages, shown = pages.items.length }) {
  const button = useRef(null);
  const { left, more, items } = pages;
  // Only once the loaded rows are all on the page: while they mount the list is short and this would be in view.
  const mounted = shown >= items.length;
  useEffect(() => {
    const element = button.current;
    if (!element || !left || !mounted || typeof IntersectionObserver !== "function") return undefined;
    const observer = new IntersectionObserver((entries) => { if (entries.some((entry) => entry.isIntersecting)) more(); }, { rootMargin: "600px" });
    observer.observe(element);
    return () => observer.disconnect();
  }, [left, more, items.length, mounted]);
  if (!left) return null;
  return <div ref={button} className="queue-more"><Button variant="ghost" size="sm" onClick={more}>Show more ({formatCount(left)} left)</Button></div>;
}

// A reviewed entry from the server: a decided suggestion or a saved edit.
function reviewedEntry(item, lastScan) {
  if (item.reviewed_kind === "override") {
    const key = `override:${item.target}:${item.property}`;
    return { id: `snap-${key}`, reviewId: key, candidateId: key, targetId: item.target, action: "overridden", actor: "Reviewer", timestamp: lastScan, label: suggestionLabel(item), value: item.value, property: item.property, item, confidence: itemConfidence(item) };
  }
  const key = item.candidate_id || item.id;
  return { id: `snap-${key}`, reviewId: key, candidateId: key, targetId: itemTarget(item), action: item.status, actor: item.decided_by === "auto" ? "Auto" : "Reviewer", auto: item.decided_by === "auto", timestamp: lastScan, label: suggestionLabel(item), value: item.value, property: item.property, item, confidence: itemConfidence(item) };
}

export function ReviewQueue({ session, onSession, transport, revision = 0, overview, onSelect, onReview, onBulkReview, scanning, colors, auditTrail = [], onUndoReview }) {
  const { issue = "ALL", objectType = "ALL", modelId = "ALL", reportId = "ALL", sort = "confidence-high", tab = "queue", group = "" } = session;
  const change = (values) => onSession((current) => ({ ...current, ...values }));
  const panel = useRef(null);
  const [activeEditId, setActiveEditId] = useState(null);
  const [bulkBusy, setBulkBusy] = useState(false);


  // The filters as the server names them; a bulk decision "by view" sends exactly these.
  const view = useMemo(() => ({ issue, object_type: objectType, model_id: modelId, report_id: reportId }), [issue, objectType, modelId, reportId]);
  const queueTab = tab !== "reviewed";
  // Counts, filter choices and patterns: one request without rows.
  const summary = useReviewPages(transport, { ...view, sort, grouping: "pattern", rows: 0 }, revision);
  const facts = summary.page;
  const matching = facts?.matching ?? 0;
  const grouping = issue === "low-evidence" ? "none" : group || (matching > GROUP_ABOVE ? "pattern" : "none");
  const lists = queueTab && Boolean(facts) && grouping !== "pattern";
  const standard = useReviewPages(transport, { ...view, sort, section: "standard" }, revision, lists && issue !== "low-evidence" && facts.standard_total > 0);
  const low = useReviewPages(transport, { ...view, sort, section: "low" }, revision, lists && facts.low_total > 0);
  const [openGroup, setOpenGroup] = useState("");
  const groupRows = useReviewPages(transport, { ...view, sort, pattern: openGroup }, revision, queueTab && grouping === "pattern" && Boolean(openGroup));
  const standardRows = useRevealed(standard.items);
  const lowRows = useRevealed(low.items);
  const openGroupRows = useRevealed(groupRows.items);
  const reviewed = useReviewPages(transport, { tab: "reviewed" }, revision, !queueTab);
  // Back from an object: focus returns to the row that was left, once its page has arrived.
  const restored = useRef(!session.selectedId);
  const shownRows = standard.items.length + low.items.length + groupRows.items.length;
  useEffect(() => {
    if (restored.current || !shownRows) return undefined;
    const frame = requestAnimationFrame(() => {
      const selected = [...(panel.current?.querySelectorAll("[data-review-id]") || [])].find((element) => element.dataset.reviewId === session.selectedId);
      restored.current = true;
      if (selected) { selected.focus({ preventScroll: true }); contentScroller().scrollTop = session.scrollY || 0; }
    });
    return () => cancelAnimationFrame(frame);
  }, [shownRows, session.selectedId, session.scrollY]);
  const filterKey = `${issue}|${objectType}|${modelId}|${reportId}|${sort}|${tab}`;
  useEffect(() => { setOpenGroup(""); }, [filterKey]);

  // Row selection. Ticked rows are decided by identifier. "Select all" ticks a scope (the filters, or one pattern)
  // that the server resolves; rows unticked after it are sent as exceptions.
  const [selection, setSelection] = useState({ scope: null, rows: new Map() });
  useEffect(() => { setSelection({ scope: null, rows: new Map() }); }, [filterKey, revision]);
  const inScope = (scope, item) => !scope.pattern || item.pattern === scope.pattern;
  const isSelected = (item) => selection.scope ? inScope(selection.scope, item) && !selection.rows.has(reviewItemKey(item)) : selection.rows.has(reviewItemKey(item));
  const selectedCount = selection.scope ? Math.max(0, selection.scope.count - selection.rows.size) : selection.rows.size;
  const toggleSelected = useCallback((item, on) => setSelection((current) => {
    const rows = new Map(current.rows);
    const add = current.scope ? !on : on;
    if (add) rows.set(reviewItemKey(item), item); else rows.delete(reviewItemKey(item));
    if (current.scope && rows.size >= current.scope.count) return { scope: null, rows: new Map() };
    return { ...current, rows };
  }), []);
  const selectAll = (scope, on) => setSelection(on && scope.count ? { scope, rows: new Map() } : { scope: null, rows: new Map() });
  const selectionOf = (scope) => {
    if (selection.scope && (selection.scope.pattern || "") === (scope.pattern || "")) return selection.rows.size ? "indeterminate" : true;
    if (selection.scope) return false;
    const ticked = [...selection.rows.values()].filter((item) => inScope(scope, item)).length;
    return ticked === 0 ? false : ticked >= scope.count ? true : "indeterminate";
  };
  const selectionTarget = () => selection.scope
    ? { view: { ...view, ...(selection.scope.pattern ? { pattern: selection.scope.pattern } : {}) }, except: [...selection.rows.values()], count: selection.scope.count }
    : [...selection.rows.values()];

  // A bulk decision over many suggestions is asked for once more, with its scope named:
  // "Approve all" and "Reject all" sit next to each other and one click decided thousands.
  // ``target`` is ticked rows or { view, except, count }.
  const [bulkConfirm, setBulkConfirm] = useState(null);
  const countOf = (target) => Array.isArray(target) ? target.length : Math.max(0, (target?.count || 0) - (target?.except?.length || 0));
  const handleBulkAction = async (action, target, confirmed = false, scope = "") => {
    const count = countOf(target);
    if (bulkBusy || scanning || !count) return;
    if (!confirmed && count > BULK_CONFIRM_ABOVE) { setBulkConfirm({ action, target, count, scope }); return; }
    setBulkConfirm(null);
    setBulkBusy(true);
    try {
      await onBulkReview(action, target);
      setSelection({ scope: null, rows: new Map() });
    } finally {
      setBulkBusy(false);
    }
  };
  const confirmScope = (entry) => {
    if (entry.scope) return `Every suggestion in “${entry.scope}”`;
    if (Array.isArray(entry.target) || entry.target.except?.length) return "The selected suggestions";
    if (entry.target.view.section === "low") return "Every low-evidence suggestion that matches the current filters";
    return hasFilters ? "Every suggestion that matches the current filters" : "Every open suggestion in the project";
  };

  // This session's decisions first, then the decided suggestions and saved edits from the server.
  const lastScan = reviewed.page?.scan?.last_scan || new Date().toISOString();
  const allReviewed = [];
  const seenReviewed = new Set();
  for (const entry of [...auditTrail, ...reviewed.items.map((item) => reviewedEntry(item, lastScan))]) {
    const key = entry.reviewId || entry.candidateId || entry.targetId;
    if (key && !seenReviewed.has(key)) {
      seenReviewed.add(key);
      allReviewed.push(entry);
    }
  }
  const reviewedTotal = Math.max(facts?.facets?.reviewed ?? 0, reviewed.total, allReviewed.length);

  // Row handlers are made once and read the current state through a ref, so a memoised row is not drawn
  // again when the list around it changes.
  const latest = useRef(null);
  latest.current = { pagers: { standard, low, groupRows }, change, onSelect, onReview, setActiveEditId };
  const handlers = useMemo(() => ({
    toggle: (item, on) => toggleSelected(item, on),
    startEdit: (item) => latest.current.setActiveEditId(item.id || itemTarget(item)),
    cancelEdit: () => latest.current.setActiveEditId(null),
    select: (item, id, nextView) => {
      latest.current.change({ selectedId: item.id || itemTarget(item), scrollY: contentScroller().scrollTop });
      latest.current.onSelect(id, nextView);
    },
    review: async (pager, action, decided, value) => {
      const ok = await latest.current.onReview(action, decided, value, byId(latest.current.pagers[pager].nodes, itemTarget(decided)));
      if (ok && action !== "edit") latest.current.pagers[pager].drop(reviewItemKey(decided));
      return ok;
    },
  }), [toggleSelected]);
  const reviewRow = (pager, pages) => (item) => (
    <ReviewRow
      key={reviewItemKey(item)}
      item={item}
      nodes={PAGE_NODES.get(item) || pages.nodes}
      pager={pager}
      handlers={handlers}
      colors={colors}
      disabled={scanning}
      selected={isSelected(item)}
      isEditing={activeEditId === (item.id || itemTarget(item))}
    />
  );
  const percent = (value) => `${Math.round(value * 100)} %`;
  const groups = facts?.groups || [];
  const groupList = grouping === "pattern" ? <div className="review-groups">
    <div className="review-group-columns" aria-hidden="true"><span>Pattern</span><span>Suggestions</span><span>Confidence</span><span>Decision</span></div>
    {groups.map((entry) => {
      const open = openGroup === entry.key;
      const count = entry.count;
      const label = `${entry.title}${entry.scope ? ` · ${entry.scope}` : ""}`;
      const patternView = { view: { ...view, pattern: entry.key }, count };
      return <section className={`review-group${open ? " is-open" : ""}`} key={entry.key} aria-label={label}>
        <div className="review-group-head">
          <button type="button" className="review-group-toggle" aria-expanded={open} onClick={() => setOpenGroup(open ? "" : entry.key)}>
            <ChevronRight className={open ? "is-open" : ""} aria-hidden="true" />
            <span className="review-group-title">{entry.title}</span>
            {entry.scope ? <span className="review-group-scope">{entry.scope}</span> : null}
          </button>
          <span className="review-group-count" data-ui-number="">{formatCount(count)}{entry.names && entry.names < count ? <small> · {formatCount(entry.names)} names</small> : null}</span>
          <span className="review-group-confidence" data-ui-number="">{entry.bulk ? (entry.low === entry.high ? percent(entry.high) : `${percent(entry.low)} – ${percent(entry.high)}`) : "—"}</span>
          <span className="review-group-actions" data-ui-actions="">
            {entry.bulk ? <>
              <Button variant="outline" size="sm" className="group-approve" disabled={bulkBusy || scanning} aria-label={`Approve ${formatCount(count)}: ${label}`} onClick={() => handleBulkAction("approve", patternView, false, label)}><Check aria-hidden="true" />Approve</Button>
              <Button variant="ghost" size="sm" className="group-reject" disabled={bulkBusy || scanning} aria-label={`Reject ${formatCount(count)}: ${label}`} onClick={() => handleBulkAction("reject", patternView, false, label)}><X aria-hidden="true" />Reject</Button>
            </> : <small>One at a time</small>}
          </span>
        </div>
        {open ? <>
          {entry.bulk ? <div className="review-group-select"><Checkbox className="review-select-all" checked={selectionOf({ pattern: entry.key, count })} disabled={bulkBusy || scanning} aria-label={`Select all ${formatCount(count)}: ${label}`} onCheckedChange={(value) => selectAll({ pattern: entry.key, count }, value === true)} /><span aria-hidden="true">Select all {formatCount(count)}</span></div> : null}
          {groupRows.loading ? <ReviewSkeleton /> : <div className="queue-list" onKeyDown={(e) => reviewKeys(e, () => setActiveEditId(null))}>{openGroupRows.map(reviewRow("groupRows", groupRows))}</div>}
          <MoreRows pages={groupRows} shown={openGroupRows.length} />
        </> : null}
      </section>;
    })}
  </div> : null;
  const scopes = [...scopeChoices(overview, "model"), ...scopeChoices(overview, "report")];
  const scopeName = (id, kind, index) => scopes.find((node) => node.id === id)?.name || `${kind} ${index + 1}`;
  const hasFilters = issue !== "ALL" || objectType !== "ALL" || modelId !== "ALL" || reportId !== "ALL";
  const types = facts?.facets?.types || [];
  const models = facts?.facets?.models || [];
  const reports = facts?.facets?.reports || [];
  const approvable = facts?.approvable ?? 0;
  const allView = { view, count: approvable };
  const lowView = { view: { ...view, section: "low" }, count: low.approvable };
  const loading = summary.loading;
  const failed = summary.error || standard.error || low.error || groupRows.error || reviewed.error;
  const retry = () => { summary.retry(); standard.retry(); low.retry(); groupRows.retry(); reviewed.retry(); };
  const lowGroup = <div className="low-evidence-group" role="region" aria-label="Low evidence suggestions">
    <div className="low-evidence-header">
      <div className="low-evidence-title">
        <ShieldAlert className="size-4" aria-hidden="true" />
        <div>
          <h3>Low-evidence suggestions ({formatCount(facts?.low_total ?? 0)})</h3>
          <p>Name-only tautologies and weak proposals with no supporting description or formula.</p>
        </div>
      </div>
      <div className="low-evidence-actions" data-ui-actions="">
        <Button variant="outline" size="sm" className="bulk-approve-low" disabled={bulkBusy || scanning || !low.approvable} onClick={() => handleBulkAction("approve", lowView)}><Check className="size-4" aria-hidden="true" />Approve all low-evidence ({formatCount(low.approvable)})</Button>
        <Button variant="ghost" size="sm" className="bulk-reject-low" disabled={bulkBusy || scanning || !low.approvable} onClick={() => handleBulkAction("reject", lowView)}><X className="size-4" aria-hidden="true" />Reject all low-evidence ({formatCount(low.approvable)})</Button>
      </div>
    </div>
    <div className="queue-list" onKeyDown={(e) => reviewKeys(e, () => setActiveEditId(null))}>
      {lowRows.map(reviewRow("low", low))}
    </div>
    <MoreRows pages={low} shown={lowRows.length} />
  </div>;
  return <div ref={panel}>
    <div className="queue-header-row">
      <PageHeading quiet title="Review queue" />
      <SegmentedControl
        options={[
          { value: "queue", label: `To review (${formatCount(matching)})` },
          { value: "reviewed", label: `Reviewed (${formatCount(reviewedTotal)})` },
        ]}
        value={tab}
        onValueChange={(val) => change({ tab: val })}
        aria-label="Review views"
      />
    </div>
    {failed && !facts ? <Card className="panel" role="alert"><EmptyState icon={<TriangleAlert />} tone="bad" title="Review queue unavailable" detail={readableText(failed)} action={<Button variant="outline" onClick={retry}><RefreshCw />Retry review queue</Button>} /></Card> : <>
    {failed ? <Card className="panel" role="alert"><EmptyState icon={<TriangleAlert />} tone="bad" title="Review refresh failed" detail={`Showing last loaded reviews. ${readableText(failed)}`} action={<Button variant="outline" onClick={retry}><RefreshCw />Retry review queue</Button>} /></Card> : null}
    {tab === "reviewed" ? (
      <>
        <p className="review-purpose">
          <span className="queue-count"><strong data-ui-number="">{formatCount(reviewedTotal)}</strong> reviewed</span>
          <span className="review-purpose-copy">Audit trail of reviewed decisions. Use Reopen to return a suggestion to the queue.</span>
        </p>
        <Card className="panel queue-panel" aria-busy={reviewed.loading}>
          {reviewed.loading && !allReviewed.length ? <ReviewSkeleton /> : allReviewed.length ? (
            <>
              <div className="review-columns" aria-hidden="true">
                <span>Object &amp; suggestion</span>
                <span>Decision &amp; reviewer</span>
                <span>Status</span>
                <span>Action</span>
              </div>
              <div className="queue-list">
                {allReviewed.map((entry) => (
                  <ReviewedItem
                    colors={colors}
                    key={entry.id || entry.reviewId}
                    entry={entry}
                    nodes={reviewed.nodes}
                    disabled={scanning}
                    onSelect={onSelect}
                    onUndo={onUndoReview}
                  />
                ))}
              </div>
              <MoreRows pages={reviewed} />
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
        <p className="review-purpose"><span className="queue-count"><strong data-ui-number="">{loading ? "…" : formatCount(matching)}</strong>{loading ? "Loading…" : " to review"}</span><span className="review-purpose-copy" /><span className="review-keys" aria-hidden="true"><kbd>J</kbd><kbd>K</kbd> move <kbd>A</kbd> approve <kbd>R</kbd> reject <kbd>X</kbd> select</span></p>
        <div className="queue-toolbar" data-ui-actions="">
          <Label className="select-field"><span>Issue</span><NativeSelect aria-label="Issue" value={issue} onChange={(event) => change({ issue: event.target.value })}><option value="ALL">All issues</option><option value="candidate">Suggestions</option><option value="low-evidence">Low evidence</option><option value="conflict">Conflicts</option><option value="stale">Outdated decisions</option></NativeSelect></Label>
          <Label className="select-field"><span>Object</span><NativeSelect aria-label="Object" value={objectType} onChange={(event) => change({ objectType: event.target.value })}><option value="ALL">All types</option>{types.map((type) => <option key={type} value={type}>{typeLabel(type)}</option>)}</NativeSelect></Label>
          {models.length > 1 ? <Label className="select-field"><span>Model</span><NativeSelect aria-label="Model" value={modelId} onChange={(event) => change({ modelId: event.target.value, reportId: "ALL" })}><option value="ALL">All models</option>{models.map((value, index) => <option key={value} value={value}>{scopeName(value, "Model", index)}</option>)}</NativeSelect></Label> : null}
          {reports.length > 1 ? <Label className="select-field"><span>Report</span><NativeSelect aria-label="Report" value={reportId} onChange={(event) => change({ reportId: event.target.value, modelId: "ALL" })}><option value="ALL">All reports</option>{reports.map((value, index) => <option key={value} value={value}>{scopeName(value, "Report", index)}</option>)}</NativeSelect></Label> : null}
          {hasFilters ? <Button variant="ghost" size="sm" onClick={() => change({ issue: "ALL", objectType: "ALL", modelId: "ALL", reportId: "ALL" })}><X />Clear filters</Button> : null}
          {issue !== "low-evidence" && matching > 1 ? <Label className="select-field select-group"><span>Group</span><NativeSelect aria-label="Group" value={grouping} onChange={(event) => change({ group: event.target.value })}><option value="pattern">By pattern</option><option value="none">No grouping</option></NativeSelect></Label> : null}
          <Label className="select-field select-sort"><span>Sort</span><NativeSelect aria-label="Sort" value={sort} onChange={(event) => change({ sort: event.target.value })}><option value="confidence-high">Most certain first</option><option value="confidence-low">Least certain first</option><option value="impact-high">Highest impact first</option><option value="impact-low">Lowest impact first</option></NativeSelect></Label>
          {selectedCount > 0 ? (
            <div className="queue-bulk-actions is-selection" data-ui-actions="" role="group" aria-label="Selected suggestions">
              <Button variant="outline" size="sm" className="selected-approve" disabled={bulkBusy || scanning} onClick={() => handleBulkAction("approve", selectionTarget())}>
                <Check className="size-4" aria-hidden="true" />Approve {formatCount(selectedCount)} selected
              </Button>
              <Button variant="ghost" size="sm" className="selected-reject" disabled={bulkBusy || scanning} onClick={() => handleBulkAction("reject", selectionTarget())}>
                <X className="size-4" aria-hidden="true" />Reject {formatCount(selectedCount)} selected
              </Button>
              <Button variant="ghost" size="icon-sm" className="selected-clear" aria-label="Clear selection" title="Clear selection" onClick={() => setSelection({ scope: null, rows: new Map() })}><X aria-hidden="true" /></Button>
            </div>
          ) : null}
          {selectedCount === 0 && approvable > 0 && grouping !== "pattern" ? (
            <div className="queue-bulk-actions" data-ui-actions="">
              <Button variant="outline" size="sm" className="bulk-approve" disabled={bulkBusy || scanning} onClick={() => handleBulkAction("approve", allView)}>
                <Check className="size-4" aria-hidden="true" />
                {hasFilters ? `Approve filtered (${formatCount(approvable)})` : `Approve all (${formatCount(approvable)})`}
              </Button>
              <Button variant="ghost" size="sm" className="bulk-reject" disabled={bulkBusy || scanning} onClick={() => handleBulkAction("reject", allView)}>
                <X className="size-4" aria-hidden="true" />
                {hasFilters ? `Reject filtered (${formatCount(approvable)})` : `Reject all (${formatCount(approvable)})`}
              </Button>
            </div>
          ) : null}
        </div>
        <AlertDialog open={Boolean(bulkConfirm)} onOpenChange={(open) => { if (!open) setBulkConfirm(null); }}>
          {bulkConfirm ? <AlertDialogContent
            title={`${bulkConfirm.action === "approve" ? "Approve" : "Reject"} ${formatCount(bulkConfirm.count)} suggestions?`}
            description={`${confirmScope(bulkConfirm)} will be ${bulkConfirm.action === "approve" ? "approved" : "rejected"}. Each decision can be changed later under Reviewed.`}
            footer={<><AlertDialogCancel asChild><Button variant="outline">Cancel</Button></AlertDialogCancel><AlertDialogAction asChild><Button variant={bulkConfirm.action === "approve" ? "default" : "destructive"} onClick={() => handleBulkAction(bulkConfirm.action, bulkConfirm.target, true)}>{bulkConfirm.action === "approve" ? "Approve" : "Reject"} {formatCount(bulkConfirm.count)}</Button></AlertDialogAction></>}
          /> : null}
        </AlertDialog>
        <Card className="panel queue-panel" aria-busy={loading}>
          {loading || (lists && standard.loading && low.loading) ? <ReviewSkeleton /> : matching && groupList ? groupList : matching ? <>
            <div className="review-columns is-pending has-select">
              <span>{approvable ? <Checkbox className="review-select-all" checked={selectionOf({ count: approvable })} disabled={bulkBusy || scanning} aria-label={`Select all ${formatCount(approvable)} suggestions`} onCheckedChange={(value) => selectAll({ count: approvable }, value === true)} /> : null}<span aria-hidden="true">Object</span></span>
              <span aria-hidden="true">Suggestion</span><span aria-hidden="true">Based on</span><span aria-hidden="true">Confidence</span><span aria-hidden="true">Decision</span>
            </div>
            {issue !== "low-evidence" && standard.items.length ? <>
              <div className="queue-list" onKeyDown={(e) => reviewKeys(e, () => setActiveEditId(null))}>
                {standardRows.map(reviewRow("standard", standard))}
              </div>
              <MoreRows pages={standard} shown={standardRows.length} />
            </> : null}
            {facts.low_total ? lowGroup : null}
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

const ReviewRow = React.memo(function ReviewRow({ item, nodes, pager, handlers, colors, disabled, selected, isEditing }) {
  return (
    <ReviewItem
      colors={colors}
      item={item}
      nodes={nodes}
      disabled={disabled}
      selectable={item.issue === "candidate"}
      selected={selected}
      onSelected={handlers.toggle}
      isEditing={isEditing}
      onStartEdit={() => handlers.startEdit(item)}
      onCancelEdit={handlers.cancelEdit}
      onSelect={(id, nextView) => handlers.select(item, id, nextView)}
      onReview={(action, decided, value) => handlers.review(pager, action, decided, value)}
    />
  );
});

function ReviewItem({
  item,
  nodes,
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
        <ObjectContextPreview node={targetNode} nodes={nodes} links={item.links} colors={colors} onSelect={onSelect}>
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

const SLOW_LOAD_MS = 8000;

/** Placeholder rows shaped like a suggestion (type chip, name and suggestion, confidence); after 8 s it says why it waits. */
function ReviewSkeleton() {
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    const timer = setTimeout(() => setSlow(true), SLOW_LOAD_MS);
    return () => clearTimeout(timer);
  }, []);
  return <div className="queue-loading" aria-busy="true">
    {[0, 1, 2, 3, 4].map((index) => <div className="review-skeleton-row" key={index} aria-hidden="true">
      <span className="review-skeleton-chip" />
      <span className="review-skeleton-text"><span /><span /></span>
      <span className="review-skeleton-meter" />
    </div>)}
    <p className={slow ? "queue-loading-slow" : "sr-only"} role="status">{slow ? "Still reading the suggestions. A large project takes a few seconds more." : "Loading suggestions…"}</p>
  </div>;
}
