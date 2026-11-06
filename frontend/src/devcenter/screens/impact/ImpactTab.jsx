// Impact tab (UI design 4.5, 5.3, 9.3, 11, step U8): scope, group, and view controls, filters,
// the proposals switch and banner, the completeness strip, the Table, Graph, and Wireframe views,
// Offers, the item pane, bulk actions, and the removal policy dialog.
// The view switch keeps scope, filters, and selection, because all of them live in this component.
import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { LoaderCircle, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Banner } from "@/components/ui/notice";
import { EmptyState, Skeleton } from "@/components/ui/result-panel";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { Select } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { useToast } from "@/components/ui/toast";
import { t, tn } from "../../copy.js";
import { createDevCenterHttp } from "../../httpClient.js";
import { slashGoesToSearch } from "../../preferences.js";
import { useAction, useDevCenterState } from "../../useDevCenter.js";
import { targetNames } from "../sessionModel.js";
import CompletenessStrip from "../../components/CompletenessStrip.jsx";
import ImpactItemRow, { IMPACT_ROW_HEIGHT } from "../../components/ImpactItemRow.jsx";
import RemovalPolicyDialog from "../../components/RemovalPolicyDialog.jsx";
import ImpactGraph from "./ImpactGraph.jsx";
import ImpactOffers from "./ImpactOffers.jsx";
import ImpactPane from "./ImpactPane.jsx";
import ImpactWireframe from "./ImpactWireframe.jsx";
import {
  BULK_ACTIONS,
  EMPTY_FILTERS,
  PAGE_SIZE,
  SEVERITY_ORDER,
  VIEWS,
  actionLabel,
  completenessDefaultOpen,
  defaultGroup,
  groupOptions,
  hasFilters,
  impactQuery,
  isProposed,
  pageToggleTargets,
  pagesFor,
  placeText,
  policyFromAction,
  proposalTargets,
  reportOptions,
  resolvedText,
  severityLabel,
  sortItems,
  virtualWindow,
} from "./impactModel.js";
import "./impact.css";

// The session IDs where the user closed the completeness areas (default open stays closed after that).
const closedAreas = new Set();
const VIEW_HEIGHT = 520;
const mark = (name) => globalThis.performance?.mark?.(name);

export default function ImpactTab({ session, tabState, onTabs, changeDisabled, reasonId }) {
  const http = useMemo(() => createDevCenterHttp(), []);
  const toast = useToast();
  const revision = useDevCenterState((state) => state.revision);
  const applyAction = useAction("impact_action_apply");
  const offerAction = useAction("offer_select");

  const rowKey = tabState?.impactRowKey || null;
  const rowName = tabState?.impactRowName || rowKey;
  const [scope, setScope] = useState(rowKey || "plan");
  const [group, setGroup] = useState(null);
  const [view, setView] = useState("table");
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [searchText, setSearchText] = useState("");
  const [includeProposals, setIncludeProposals] = useState(false);

  const [pages, setPages] = useState(() => new Map());
  const [total, setTotal] = useState(null);
  const [listStatus, setListStatus] = useState("loading");
  const [summary, setSummary] = useState(null);
  const [blockingSummary, setBlockingSummary] = useState(null);
  const [updating, setUpdating] = useState(false);
  const [scrollTop, setScrollTop] = useState(0);

  const [checked, setChecked] = useState(() => new Set());
  const [activeId, setActiveId] = useState(null);
  const [activeSnapshot, setActiveSnapshot] = useState(null);
  const [pending, setPending] = useState(null);
  const [actionError, setActionError] = useState(null);
  const [mapFocusSeq, setMapFocusSeq] = useState(0);
  const [dialog, setDialog] = useState(null);
  const [policies, setPolicies] = useState({});
  const [wire, setWire] = useState({ report: "target", pageId: null, mode: "drawing", visualId: null });
  const [areasOpen, setAreasOpen] = useState(false);

  const scrollRef = useRef(null);
  const generationRef = useRef(0);
  const loadingPages = useRef(new Set());
  const paneOpenerRef = useRef(null);
  const dialogTriggerRef = useRef(null);
  const areasInitRef = useRef(false);
  const groupInitRef = useRef(false);
  const paintPending = useRef(false);

  // A move from Compare or Plan with a row sets the scope to that row.
  useEffect(() => {
    if (rowKey) setScope(rowKey);
  }, [rowKey]);

  // Debounced search.
  useEffect(() => {
    const timer = setTimeout(() => {
      setFilters((current) => (current.q === searchText ? current : { ...current, q: searchText }));
      if (searchText !== filters.q) mark("dc-impact-input");
    }, 200);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchText]);

  // "/" goes to "Find object or reason" while the Impact tab shows (UI design 9.3).
  useEffect(() => {
    const onKeyDown = (event) => {
      const field = document.getElementById("dc-impact-search");
      if (!field || field.offsetParent === null) return;
      if (slashGoesToSearch(event)) {
        event.preventDefault();
        event.stopImmediatePropagation();
        field.focus();
      }
    };
    window.addEventListener("keydown", onKeyDown, true);
    return () => window.removeEventListener("keydown", onKeyDown, true);
  }, []);

  const baseQuery = useMemo(() => ({ target: scope, ...(includeProposals ? { includeProposals: true } : {}) }), [scope, includeProposals]);
  const listQuery = useMemo(
    () => (group && group !== "offers" ? impactQuery({ scope, group, includeProposals, filters }) : null),
    [scope, group, includeProposals, filters],
  );

  // Summary reads: the group counts, offers, and completeness (no filter), and the blocking counts.
  const loadSummary = useCallback(async () => {
    const [all, blocking] = await Promise.all([
      http.getImpact({ ...baseQuery, limit: 1 }),
      http.getImpact({ ...baseQuery, blocking: true, limit: 1 }),
    ]);
    setSummary(all);
    setBlockingSummary(blocking);
    return blocking.total ?? 0;
  }, [http, baseQuery]);

  useEffect(() => {
    loadSummary().catch(() => setListStatus("error"));
  }, [loadSummary]);

  // The default group: the first group with blocking items, else Breaks.
  useEffect(() => {
    if (groupInitRef.current || !blockingSummary) return;
    groupInitRef.current = true;
    setGroup(defaultGroup(blockingSummary.facets?.direction));
  }, [blockingSummary]);

  // The completeness areas: open when incomplete and the user did not close them in this session.
  useEffect(() => {
    if (areasInitRef.current || !summary) return;
    areasInitRef.current = true;
    setAreasOpen(completenessDefaultOpen(summary.completeness, closedAreas.has(session.session_id)));
  }, [summary, session.session_id]);

  const fetchPage = useCallback(
    async (index, generation) => {
      if (!listQuery) return;
      loadingPages.current.add(index);
      try {
        const reply = await http.getImpact({ ...listQuery, limit: PAGE_SIZE, offset: index * PAGE_SIZE });
        if (generation !== generationRef.current) return;
        mark("dc-impact-reply");
        paintPending.current = true;
        setPages((current) => new Map(current).set(index, sortItems(reply.items)));
        setTotal(reply.total ?? 0);
        setListStatus("ready");
      } catch {
        if (generation === generationRef.current) setListStatus("error");
      } finally {
        loadingPages.current.delete(index);
      }
    },
    [http, listQuery],
  );

  // A new query starts again at the top. The selection of the bulk checkboxes stays.
  useEffect(() => {
    if (!listQuery) return;
    generationRef.current += 1;
    loadingPages.current = new Set();
    setPages(new Map());
    setTotal(null);
    setListStatus("loading");
    setScrollTop(0);
    if (scrollRef.current) scrollRef.current.scrollTop = 0;
    fetchPage(0, generationRef.current);
  }, [listQuery, fetchPage]);

  // Budget P1 and P2: the first rows painted after the reply.
  useLayoutEffect(() => {
    if (!paintPending.current) return undefined;
    paintPending.current = false;
    const frame = requestAnimationFrame(() => mark("dc-impact-painted"));
    return () => cancelAnimationFrame(frame);
  }, [pages]);

  // Reload all loaded pages in place: the list keeps scroll and selection.
  const reloadAll = useCallback(async () => {
    const generation = generationRef.current;
    const indexes = pages.size ? [...pages.keys()] : [0];
    const blockingLeft = await loadSummary().catch(() => null);
    if (listQuery) {
      const replies = await Promise.all(
        indexes.map((index) => http.getImpact({ ...listQuery, limit: PAGE_SIZE, offset: index * PAGE_SIZE }).then((reply) => [index, reply]).catch(() => null)),
      );
      if (generation === generationRef.current) {
        setPages((current) => {
          const next = new Map(current);
          for (const entry of replies) if (entry) next.set(entry[0], sortItems(entry[1].items));
          return next;
        });
        const last = replies.filter(Boolean).at(-1);
        if (last) setTotal(last[1].total ?? 0);
      }
    }
    return blockingLeft;
  }, [pages, loadSummary, listQuery, http]);

  // A change in another place (poll, agent, other tab) gives a new revision: refresh in place.
  const lastRevision = useRef(revision);
  const ownChange = useRef(false);
  useEffect(() => {
    if (lastRevision.current !== null && revision !== null && revision !== lastRevision.current && !ownChange.current) {
      setUpdating(true);
      reloadAll().finally(() => setUpdating(false));
    }
    lastRevision.current = revision;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [revision]);

  const loaded = useMemo(() => {
    const list = [];
    for (const index of [...pages.keys()].sort((a, b) => a - b)) list.push(...pages.get(index));
    return list;
  }, [pages]);
  const itemById = useMemo(() => new Map(loaded.map((item) => [item.id, item])), [loaded]);
  const activeItem = (activeId && itemById.get(activeId)) || (activeSnapshot?.id === activeId ? activeSnapshot : null);
  const targets = useMemo(() => proposalTargets(session), [session]);
  const proposalCount = session?.proposals?.open?.length ?? 0;

  // Open an item from a Plan link.
  useEffect(() => {
    const wanted = tabState?.impactItemId;
    if (wanted && itemById.has(wanted) && activeId !== wanted) {
      setActiveId(wanted);
      setActiveSnapshot(itemById.get(wanted));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tabState?.impactItemId, itemById]);

  // Virtual window (budget P4) and page loading.
  const rowsTotal = total ?? 0;
  const { first, last } = virtualWindow({ scrollTop, height: VIEW_HEIGHT, rowHeight: IMPACT_ROW_HEIGHT, total: rowsTotal });
  useEffect(() => {
    if (!listQuery || total === null) return;
    for (const index of pagesFor({ first, last })) {
      if (!pages.has(index) && !loadingPages.current.has(index)) fetchPage(index, generationRef.current);
    }
  }, [first, last, pages, total, listQuery, fetchPage]);

  const visibleRows = [];
  for (let index = first; index < last; index += 1) {
    const pageItems = pages.get(Math.floor(index / PAGE_SIZE));
    const item = pageItems?.[index % PAGE_SIZE];
    visibleRows.push({ index, item });
  }

  const blockingByGroup = blockingSummary?.facets?.direction ?? {};
  const totalsByGroup = summary?.facets?.direction ?? {};
  const groups = groupOptions({ totals: totalsByGroup, blocking: blockingByGroup, offers: summary?.offers?.length ?? 0 });

  const setFilter = (name, value) => {
    mark("dc-impact-input");
    setFilters((current) => ({ ...current, [name]: value }));
  };
  const clearFilters = () => {
    mark("dc-impact-input");
    setSearchText("");
    setFilters(EMPTY_FILTERS);
  };

  const openItem = (item, opener) => {
    if (opener) paneOpenerRef.current = opener;
    setActiveId(item.id);
    setActiveSnapshot(item);
    setActionError(null);
  };
  const closePane = () => {
    setActiveId(null);
    setActiveSnapshot(null);
  };

  const finish = async (reply, countBefore) => {
    const blockingLeft = await reloadAll();
    const applied = reply?.applied?.length ?? countBefore;
    const failed = reply?.failed?.length ?? 0;
    toast.show({ tone: failed ? "warn" : "ok", text: resolvedText(applied, blockingLeft ?? 0, failed) });
  };

  const runAction = async (item, action, trigger, payload) => {
    const policy = policyFromAction(action);
    if (policy && policy !== "block") {
      dialogTriggerRef.current = trigger || document.activeElement;
      setDialog({ object: item.cause, name: item.path?.[0]?.name ?? item.cause, type: item.path?.[0]?.type, policy });
      return;
    }
    if (action === "map_to_target" && !payload) {
      openItem(item, trigger);
      setMapFocusSeq((value) => value + 1);
      return;
    }
    setPending({ itemId: item.id, action });
    setActionError(null);
    setUpdating(true);
    ownChange.current = true;
    try {
      const reply = await applyAction.run({ item_ids: [item.id], action, ...(payload ? { payload } : {}) });
      if (!reply) {
        setActionError(action);
        return;
      }
      if (policy) setPolicies((current) => ({ ...current, [item.cause]: policy }));
      await finish(reply, 1);
    } finally {
      ownChange.current = false;
      setPending(null);
      setUpdating(false);
    }
  };

  const openPolicy = (item, policy, trigger) => {
    dialogTriggerRef.current = trigger;
    setDialog({ object: item.cause, name: item.path?.[0]?.name ?? item.cause, type: item.path?.[0]?.type, policy: policy || policies[item.cause] || "block" });
  };

  const policySaved = async (reply) => {
    setPolicies((current) => ({ ...current, [reply.row_key]: reply.policy }));
    setUpdating(true);
    ownChange.current = true;
    const blockingBefore = blockingSummary?.total ?? 0;
    try {
      // One policy can resolve many items: the resolved count is the drop of the blocking count.
      const blockingLeft = (await reloadAll()) ?? 0;
      toast.show({ tone: "ok", text: resolvedText(Math.max(0, blockingBefore - blockingLeft), blockingLeft) });
    } finally {
      ownChange.current = false;
      setUpdating(false);
    }
  };

  const bulk = async (action) => {
    const ids = [...checked];
    if (!ids.length) return;
    setPending({ itemId: null, action });
    setUpdating(true);
    ownChange.current = true;
    try {
      const reply = await applyAction.run({ item_ids: ids, action });
      if (reply) {
        setChecked(new Set(reply.failed.map((entry) => entry.item_id)));
        await finish(reply, ids.length);
      }
    } finally {
      ownChange.current = false;
      setPending(null);
      setUpdating(false);
    }
  };

  const toggleCheck = (item, value) => {
    setChecked((current) => {
      const next = new Set(current);
      if (value) next.add(item.id);
      else next.delete(item.id);
      return next;
    });
  };

  const toggleOffers = async (list, selected) => {
    if (!list.length) return;
    setUpdating(true);
    ownChange.current = true;
    try {
      for (const offer of list) {
        const reply = await offerAction.run({ offer_id: offer.id, selected });
        if (!reply) break;
      }
      await loadSummary().catch(() => null);
    } finally {
      ownChange.current = false;
      setUpdating(false);
    }
  };

  const openVisual = (visual) => {
    setWire((current) => ({ ...current, visualId: visual.id }));
    const itemId = (visual.cause_item_ids ?? []).find((id) => itemById.has(id));
    if (itemId) openItem(itemById.get(itemId), document.activeElement);
  };

  const { report: targetReport } = targetNames(session);
  const reports = useMemo(() => reportOptions(session, targetReport), [session, targetReport]);
  const sourceOptions = [
    { value: "all", label: t("impact.filter.all") },
    ...(session?.sources ?? []).filter((source) => source.role === "target" || source.role === "donor").map((source) => ({ value: source.source_id, label: source.display_name })),
  ];
  const severityOptions = [
    { value: "all", label: t("impact.filter.all") },
    ...SEVERITY_ORDER.filter((severity) => (summary?.facets?.severity?.[severity] ?? 0) > 0 || filters.severity === severity).map((severity) => ({ value: severity, label: severityLabel(severity) })),
  ];
  const typeOptions = [
    { value: "all", label: t("impact.filter.all") },
    ...Object.keys(summary?.facets?.object_type ?? {}).sort().map((type) => ({ value: type, label: type })),
  ];
  const scopeOptions = [{ value: "plan", label: t("impact.scope.plan") }, ...(rowKey ? [{ value: rowKey, label: t("impact.scope.row", { name: rowName }) }] : [])];

  const filtered = hasFilters(filters);
  const disabled = Boolean(changeDisabled);
  const showRow2 = group !== "offers";

  let region;
  if (!group || (listStatus === "loading" && group !== "offers" && !loaded.length)) {
    region = <Skeleton lines={4} label={scope === "plan" ? t("impact.loading.plan") : t("impact.loading.row", { name: rowName })} />;
  } else if (listStatus === "error" && group !== "offers") {
    region = (
      <EmptyState
        variant="error"
        headingLevel={2}
        title={t("impact.error.title")}
        action={<Button variant="outline" onClick={() => { setListStatus("loading"); reloadAll().then(() => setListStatus("ready")).catch(() => setListStatus("error")); }}>{t("impact.error.retry")}</Button>}>
        {t("impact.error.body", { message: t("shared.not_current") })}
      </EmptyState>
    );
  } else if (group === "offers") {
    region = (
      <ImpactOffers
        offers={summary?.offers ?? []}
        disabled={disabled || offerAction.pending}
        reasonId={reasonId}
        onToggle={(offer, selected) => toggleOffers([offer], selected)}
        onTogglePage={(items, selected) => toggleOffers(pageToggleTargets(items, selected), selected)}
        onOpenNeeds={() => setGroup("needs")}
      />
    );
  } else if (rowsTotal === 0 && view !== "wireframe") {
    region = filtered ? (
      <EmptyState headingLevel={2} title={t("impact.empty.filter")} action={<Button variant="outline" onClick={clearFilters}>{t("impact.empty.filter.action")}</Button>} />
    ) : scope !== "plan" ? (
      <EmptyState headingLevel={2} title={t("impact.empty.row.title")} action={<Button variant="outline" onClick={() => setScope("plan")}>{t("impact.empty.row.action")}</Button>}>
        {t("impact.empty.row.body", { name: rowName })}
      </EmptyState>
    ) : group === "needs" ? (
      <EmptyState headingLevel={2} title={t("impact.empty.needs")} />
    ) : (
      <EmptyState headingLevel={2} title={t("impact.empty.plan.title")}>{t("impact.empty.plan.body")}</EmptyState>
    );
  } else if (view === "graph") {
    region = <ImpactGraph items={loaded} total={rowsTotal} selectedItemId={activeId} onOpenItem={openItem} onShowTable={() => setView("table")} />;
  } else if (view === "wireframe") {
    region = (
      <ImpactWireframe
        reports={reports}
        report={wire.report}
        onReport={(report) => setWire((current) => ({ ...current, report, pageId: null }))}
        pageId={wire.pageId}
        onPage={(pageId) => setWire((current) => ({ ...current, pageId }))}
        mode={wire.mode}
        onMode={(mode) => setWire((current) => ({ ...current, mode }))}
        selectedVisualId={wire.visualId}
        onOpenVisual={openVisual}
        offers={summary?.offers ?? []}
        onOffer={(offer, selected) => toggleOffers([offer], selected)}
        offerDisabled={disabled || offerAction.pending}
      />
    );
  } else {
    const topPad = first * IMPACT_ROW_HEIGHT;
    const bottomPad = Math.max(0, (rowsTotal - last) * IMPACT_ROW_HEIGHT);
    region = (
      <div
        ref={scrollRef}
        className="dc-impact-scroll"
        style={{ height: VIEW_HEIGHT }}
        onScroll={(event) => setScrollTop(event.currentTarget.scrollTop)}>
        <table className="dc-impact-table" aria-label={t("impact.table.label")} aria-rowcount={rowsTotal + 1}>
          <thead>
            <tr aria-rowindex={1}>
              <th scope="col" className="dc-impact-cell-check"><span className="sr-only">{t("impact.col.select")}</span></th>
              <th scope="col">{t("impact.col.item")}</th>
              <th scope="col">{t("impact.col.place")}</th>
              <th scope="col">{t("impact.col.severity")}</th>
              <th scope="col">{t("impact.col.action")}</th>
            </tr>
          </thead>
          <tbody>
            {topPad > 0 ? <tr aria-hidden="true" className="dc-impact-pad" style={{ height: topPad }}><td colSpan={5} /></tr> : null}
            {visibleRows.map(({ index, item }) =>
              item ? (
                <ImpactItemRow
                  key={item.id}
                  item={item}
                  rowIndex={index}
                  place={placeText(item, session)}
                  proposed={isProposed(item, includeProposals, targets)}
                  checked={checked.has(item.id)}
                  active={item.id === activeId}
                  disabled={disabled}
                  reasonId={reasonId}
                  pendingAction={pending?.itemId === item.id ? pending.action : null}
                  onCheck={toggleCheck}
                  onOpen={openItem}
                  onAction={runAction}
                />
              ) : (
                <tr key={`wait-${index}`} className="dc-impact-row dc-impact-row-wait" aria-rowindex={index + 2} style={{ height: IMPACT_ROW_HEIGHT }}>
                  <td colSpan={5}><span className="dc-impact-wait">{t("shared.updating")}</span></td>
                </tr>
              ),
            )}
            {bottomPad > 0 ? <tr aria-hidden="true" className="dc-impact-pad" style={{ height: bottomPad }}><td colSpan={5} /></tr> : null}
          </tbody>
        </table>
      </div>
    );
  }

  return (
    <div className="dc-impact" data-view={view} data-group={group || undefined} data-impact-row={scope !== "plan" ? scope : undefined} data-impact-item={tabState?.impactItemId || undefined}>
      <div className="dc-impact-toolbar">
        <Select label={t("impact.scope.label")} value={scope} onValueChange={(value) => setScope(value)} options={scopeOptions} className="dc-impact-scope" />
        <div className="dc-impact-field">
          <span className="ui-field-label" id="dc-impact-group-label">{t("impact.group.label")}</span>
          <div role="radiogroup" aria-labelledby="dc-impact-group-label" className="ui-segmented dc-impact-groups">
            {groups.map((option) => (
              <button
                key={option.value}
                type="button"
                role="radio"
                aria-checked={group === option.value}
                data-state={group === option.value ? "on" : "off"}
                className="ui-segment"
                data-group-value={option.value}
                onClick={() => setGroup(option.value)}>
                <span>{option.label}</span>
                {option.blocking > 0 ? <span className="dc-impact-group-blocking" data-tone="bad">{t("impact.group.blocking", { n: option.blocking })}</span> : null}
              </button>
            ))}
          </div>
        </div>
        <div className="dc-impact-field">
          <span className="ui-field-label">{t("impact.view.label")}</span>
          <SegmentedControl
            mode="radio"
            aria-label={t("impact.view.label")}
            value={view}
            onValueChange={setView}
            options={VIEWS.map((value) => ({ value, label: t(`impact.view.${value}`) }))}
          />
        </div>
        {updating ? (
          <span className="dc-impact-updating" role="status">
            <LoaderCircle className="spin" aria-hidden="true" />
            {t("shared.updating")}
          </span>
        ) : null}
      </div>
      {showRow2 ? (
        <div className="dc-impact-filters" role="group" aria-label={t("impact.filters.label")}>
          <Switch label={t("impact.filter.blocking")} checked={filters.blockingOnly} onCheckedChange={(value) => setFilter("blockingOnly", value === true)} />
          <Select label={t("impact.filter.severity")} value={filters.severity} onValueChange={(value) => setFilter("severity", value)} options={severityOptions} />
          <Select
            label={t("impact.filter.certainty")}
            value={filters.certainty}
            onValueChange={(value) => setFilter("certainty", value)}
            options={[{ value: "all", label: t("impact.filter.all") }, { value: "certain", label: t("impact.certainty.certain") }, { value: "possible", label: t("impact.certainty.possible") }]}
          />
          <Select label={t("impact.filter.side")} value={filters.source} onValueChange={(value) => setFilter("source", value)} options={sourceOptions} />
          <Select label={t("impact.filter.type")} value={filters.type} onValueChange={(value) => setFilter("type", value)} options={typeOptions} />
          <div className="dc-impact-search">
            <label className="ui-field-label" htmlFor="dc-impact-search">{t("impact.filter.search")}</label>
            <Input id="dc-impact-search" type="search" value={searchText} aria-keyshortcuts="/" onChange={(event) => setSearchText(event.target.value)} />
          </div>
          <Switch label={t("shared.include_proposals.switch")} checked={includeProposals} onCheckedChange={(value) => setIncludeProposals(value === true)} />
        </div>
      ) : null}
      {includeProposals ? (
        <Banner tone="info" data-banner="proposals">{tn("shared.include_proposals.banner", proposalCount)}</Banner>
      ) : null}
      {summary ? (
        <CompletenessStrip
          completeness={summary.completeness}
          open={areasOpen}
          onOpenChange={(open) => {
            setAreasOpen(open);
            if (!open) closedAreas.add(session.session_id);
          }}
        />
      ) : null}
      {checked.size > 0 && group !== "offers" ? (
        <div className="dc-impact-bulk" role="group" aria-label={t("impact.bulk.label")}>
          <span className="dc-impact-bulk-count">{t("impact.bulk.count", { n: checked.size })}</span>
          {BULK_ACTIONS.map((action) => (
            <Button
              key={action}
              variant="outline"
              size="sm"
              disabled={disabled}
              aria-describedby={disabled ? reasonId : undefined}
              loading={pending?.itemId === null && pending?.action === action}
              loadingText={t("shared.updating")}
              onClick={() => bulk(action)}>
              {actionLabel(action)}
            </Button>
          ))}
          <Button variant="ghost" size="sm" onClick={() => setChecked(new Set())}><X aria-hidden="true" />{t("shared.clear_selection")}</Button>
        </div>
      ) : null}
      {rowsTotal > PAGE_SIZE && view === "table" && group !== "offers" ? (
        <p className="dc-impact-large">{t("impact.large", { a: first + 1, b: Math.min(rowsTotal, last), total: rowsTotal })}</p>
      ) : null}
      <div className="dc-impact-body">
        <div className="dc-impact-region">{region}</div>
        {activeItem ? (
          <ImpactPane
            item={activeItem}
            http={http}
            policy={policies[activeItem.cause] || (activeItem.blocking && (activeItem.allowed_actions ?? []).includes("set_policy_block") ? "block" : null)}
            disabled={disabled}
            reasonId={reasonId}
            pendingAction={pending?.itemId === activeItem.id ? pending.action : null}
            actionError={actionError}
            mapFocusSeq={mapFocusSeq}
            returnFocusRef={paneOpenerRef}
            onClose={closePane}
            onAction={runAction}
            onPolicy={openPolicy}
            onCause={(item) => onTabs?.({ tab: "compare", rowKey: item.cause })}
          />
        ) : null}
      </div>
      <RemovalPolicyDialog
        open={Boolean(dialog)}
        onOpenChange={(open) => { if (!open) setDialog(null); }}
        object={dialog?.object}
        objectName={dialog?.name}
        objectType={dialog?.type}
        initialPolicy={dialog?.policy}
        returnFocusRef={dialogTriggerRef}
        onSaved={policySaved}
      />
    </div>
  );
}
