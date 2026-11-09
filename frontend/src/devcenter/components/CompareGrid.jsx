// Compare grid component for N-way compare (UI design 4.3, 9.3, step U4, U6).
// All text follows ASD-STE100 rules.
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowUpDown,
  Calculator,
  Circle,
  CircleDashed,
  Columns2,
  Flag,
  Keyboard,
  Layers,
  Link2,
  Network,
  Search,
  Table as TableIcon,
  Target,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { FilterButton, FilterChip, Popover } from "@/components/ui/filter";
import { EmptyState } from "@/components/ui/result-panel";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { Tooltip } from "@/components/ui/tooltip";
import { useToast } from "@/components/ui/toast";
import { t, tn } from "../copy.js";
import { createDevCenterHttp } from "../httpClient.js";
import { slashGoesToSearch } from "../preferences.js";
import { useAction, useDevCenterState, useDevCenterStore } from "../useDevCenter.js";
import BulkEditDialog from "./BulkEditDialog.jsx";
import { editScope } from "./bulkEditModel.js";
import BulkBar from "./BulkBar.jsx";
import CodeDiff from "./CodeDiff.jsx";
import CompareRowDetail from "./CompareRowDetail.jsx";
import StateCell, { normalizeState, STATE_ICONS, stateWord } from "./StateCell.jsx";
import { formatMergeChoiceLabel, normalizeChoiceKind } from "./rowDetailModel.js";
import { formatDaxName, formatObjectRef } from "../phrases.js";
import "./compare.css";

const PAGE_SIZE = 200;
const ROW_HEIGHT = 36;
const OVERSCAN = 10;
const MAX_CACHED_PAGES = 25;

export const TYPE_ICONS = {
  measure: Calculator,
  calculation_item: Calculator,
  report_measure: Calculator,
  column: Columns2,
  data_column: Columns2,
  calculated_column: Columns2,
  table: TableIcon,
  relationship: Link2,
  hierarchy: Network,
  partition: Layers,
};

const STATE_PRECEDENCE = [
  "conflict",
  "type_conflict",
  "missing",
  "renamed",
  "moved",
  "different",
  "same",
];

export function objectTypeIcon(type) {
  const key = String(type || "").toLowerCase().replace(/\s+/g, "_");
  return TYPE_ICONS[key] || TableIcon;
}

export function choiceText(choice, donors = []) {
  return formatMergeChoiceLabel(choice, donors);
}

// The Merge Choice badge (UI design 4.3): at most one, in the priority "Confirm row first",
// "Question", "Proposed". The proposed choice shows only in the tooltip.
export function mergeChoiceBadge(row, session, donors = []) {
  if ((row?.marks?.length ?? 0) > 0) {
    return { kind: "mark", className: "dc-badge-mark", label: t("compare.badge.confirm_first"), tooltip: t("compare.badge.confirm_first") };
  }
  const question = (session?.questions?.open ?? []).find((item) => item.target_id === row?.row_key);
  if (question) return { kind: "question", className: "dc-badge-question", label: t("compare.badge.question"), tooltip: question.text };
  const proposal = (session?.proposals?.open ?? []).find((item) => item.target_id === row?.row_key);
  if (proposal || row?.proposal_status === "proposed" || row?.proposal) {
    const choice = proposal?.summary || choiceText(proposal?.payload?.choice ?? row?.proposal?.choice ?? row?.merge_choice, donors);
    return { kind: "proposal", className: "dc-badge-prop", label: t("compare.badge.proposed"), tooltip: t("shared.proposed.tooltip", { choice }) };
  }
  return null;
}

export function GridShortcutsHelp() {
  const [open, setOpen] = useState(false);
  const shortcuts = [
    { key: "D", desc: "Open code diff for selected cell (or double-click cell)" },
    { key: "M", desc: "Open bulk merge choices menu" },
    { key: "Space", desc: "Toggle row selection (Shift for range)" },
    { key: "Enter", desc: "Open row details pane" },
    { key: "/", desc: "Focus search filter" },
    { key: "Esc", desc: "Clear selection, close pane, or clear search" },
    { key: "Ctrl+A", desc: "Select or deselect all loaded rows" },
    { key: "K / T / S", desc: "Quick-set Keep, Take, or Skip on active row" },
    { key: "Arrows", desc: "Navigate between rows and columns" },
    { key: "F5", desc: "Reload project data" },
  ];

  return (
    <Popover
      open={open}
      onOpenChange={setOpen}
      label="Compare grid keyboard shortcuts"
      trigger={
        <Button
          variant="outline"
          size="sm"
          aria-label="Grid keyboard shortcuts"
          tooltip="Keyboard shortcuts"
          className="dc-shortcuts-help-btn"
        >
          <Keyboard className="dc-search-icon" aria-hidden="true" />
          <span className="sr-only">Keyboard shortcuts</span>
        </Button>
      }
      className="dc-shortcuts-popover p-3 text-xs"
    >
      <div className="dc-shortcuts-content">
        <div className="font-semibold text-sm mb-2" style={{ color: "var(--text)" }}>Grid keyboard shortcuts</div>
        <dl className="dc-shortcuts-list">
          {shortcuts.map(({ key, desc }) => (
            <React.Fragment key={key}>
              <dt><kbd>{key}</kbd></dt>
              <dd>{desc}</dd>
            </React.Fragment>
          ))}
        </dl>
      </div>
    </Popover>
  );
}

export default function CompareGrid({
  session,
  tabState = {},
  onTabs,
  changeDisabled = false,
  reasonId,
  http: propHttp,
}) {
  const http = useMemo(() => propHttp || createDevCenterHttp(), [propHttp]);
  const store = useDevCenterStore();
  const storeRevision = useDevCenterState((s) => s.revision);
  const toast = useToast();

  const setModeAction = useAction("compare_mode_set");
  const bulkSetAction = useAction("merge_choice_bulk_set");
  const singleChoiceAction = useAction("merge_choice_set");
  const confirmAction = useAction("row_confirm");
  const [editOpen, setEditOpen] = useState(false);

  // Sources identification.
  const sources = session?.sources || [];
  const targetSource =
    sources.find((s) => s.role === "target" || s.source_id === session?.target?.model?.source_id) ||
    sources[0] ||
    null;
  const donors = useMemo(() => sources.filter((s) => s.role === "donor"), [sources]);

  // Mode from session.
  const compareMode = session?.compare_mode || "default";

  // Filters state.
  const [q, setQ] = useState("");
  const [debouncedQ, setDebouncedQ] = useState("");
  const [stateFilter, setStateFilter] = useState("notsame"); // "notsame", specific state, or "all"
  const [typeFilters, setTypeFilters] = useState([]);
  const [tableFilter, setTableFilter] = useState("");
  const [folderFilter, setFolderFilter] = useState("");
  const [sourceFilters, setSourceFilters] = useState([]);
  const [changedFilter, setChangedFilter] = useState(false);
  const [marksFilter, setMarksFilter] = useState(Boolean(tabState?.marks));
  const [proposalFilter, setProposalFilter] = useState(false);
  const [sortField, setSortField] = useState("name");
  const [sortDir, setSortDir] = useState("asc");

  // Debounce search input.
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedQ(q);
    }, 150);
    return () => clearTimeout(timer);
  }, [q]);

  // Update marks filter if tabState requests it.
  useEffect(() => {
    if (tabState?.marks) setMarksFilter(true);
  }, [tabState?.marks]);

  // Data cache and paging.
  const [pages, setPages] = useState(new Map());
  const [pendingPages, setPendingPages] = useState(new Set());
  const [total, setTotal] = useState(null);
  const [stateCounts, setStateCounts] = useState({});
  const [loading, setLoading] = useState(true);
  const [slowLoading, setSlowLoading] = useState(false);
  const [error, setError] = useState(null);
  const [generation, setGeneration] = useState(0);

  // Selection and active row.
  const [selectedKeys, setSelectedKeys] = useState(new Set());
  const [allMatching, setAllMatching] = useState(false);
  const [, setAnchorRow] = useState(null);
  const [activeRowKey, setActiveRowKey] = useState(tabState?.rowKey || null);
  const [paneFocusSeq, setPaneFocusSeq] = useState(0);
  const [focusedCell, setFocusedCell] = useState({ r: 0, c: 1 });

  // Single row save visual feedback and undo state.
  const [lastSavedRowKey, setLastSavedRowKey] = useState(null);
  const [flashingRowKeys, setFlashingRowKeys] = useState(new Set());
  const [undoHistory, setUndoHistory] = useState([]);

  const triggerRowFlash = useCallback((key) => {
    setFlashingRowKeys((prev) => new Set(prev).add(key));
    const isReduced = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    setTimeout(() => {
      setFlashingRowKeys((prev) => {
        const next = new Set(prev);
        next.delete(key);
        return next;
      });
    }, isReduced ? 0 : 150);
  }, []);

  useEffect(() => {
    if (tabState?.rowKey) {
      setActiveRowKey(tabState.rowKey);
      setStateFilter("all");
      setMarksFilter(false);
    }
  }, [tabState?.rowKey]);

  // Refs for synchronous tracking to avoid stale closures during rapid keyboard actions.
  const focusedCellRef = useRef({ r: 0, c: 1 });
  const anchorRowRef = useRef(null);
  const selectedKeysRef = useRef(selectedKeys);
  selectedKeysRef.current = selectedKeys;
  const allMatchingRef = useRef(allMatching);
  allMatchingRef.current = allMatching;
  const activeRowKeyRef = useRef(activeRowKey);
  activeRowKeyRef.current = activeRowKey;
  const pagesRef = useRef(pages);
  pagesRef.current = pages;

  // Code Diff modal state.
  const [diffTarget, setDiffTarget] = useState(null); // { row, donor, triggerElement }
  const [bulkMenuOpen, setBulkMenuOpen] = useState(false);

  // Virtual scrolling refs.
  const scrollRef = useRef(null);
  const gridRef = useRef(null);
  const searchInputRef = useRef(null);
  const bulkMenuBtnRef = useRef(null);
  const [scrollTop, setScrollTop] = useState(0);
  const [clientHeight, setClientHeight] = useState(600);
  const [isFastScrolling, setIsFastScrolling] = useState(false);
  const fastScrollTimer = useRef(null);

  useEffect(() => {
    return () => clearTimeout(fastScrollTimer.current);
  }, []);

  // Columns definition.
  // Col 0: chk, Col 1: obj, Col 2: rs, Col 3: mc (pinned), Col 4: tg, Col 5..: donors, Col N-1: mk
  const totalCols = 6 + donors.length;
  const colWidths = useMemo(() => {
    const list = [40, 260, 136, 220, 132];
    for (let i = 0; i < donors.length; i++) list.push(132);
    list.push(112);
    return list;
  }, [donors.length]);
  const totalGridWidth = useMemo(() => colWidths.reduce((sum, w) => sum + w, 0), [colWidths]);
  const colsCss = useMemo(() => colWidths.map((w) => `${w}px`).join(" "), [colWidths]);

  // Filter params object for queries.
  const queryParams = useMemo(() => {
    const p = {};
    if (debouncedQ) p.q = debouncedQ;
    if (stateFilter === "notsame") p.state = "not_same";
    else if (stateFilter && stateFilter !== "all") p.state = stateFilter;
    if (typeFilters.length > 0) p.type = typeFilters[0];
    if (tableFilter) p.table = tableFilter;
    if (folderFilter) p.folder = folderFilter;
    if (sourceFilters.length > 0) p.source = sourceFilters[0];
    if (changedFilter) p.changed = "true";
    if (marksFilter) p.marks = "true";
    if (proposalFilter) p.proposal = "true";
    if (sortField) p.sort = `${sortField}:${sortDir}`;
    return p;
  }, [
    debouncedQ,
    stateFilter,
    typeFilters,
    tableFilter,
    folderFilter,
    sourceFilters,
    changedFilter,
    marksFilter,
    proposalFilter,
    sortField,
    sortDir,
  ]);

  // Reload currently loaded pages in place without unmounting the active row pane.
  const reloadLoadedPages = useCallback(async () => {
    const pageIndices = pagesRef.current.size > 0 ? [...pagesRef.current.keys()] : [0];
    await Promise.all(
      pageIndices.map(async (pageIndex) => {
        try {
          const reply = await http.getCompareRows({
            ...queryParams,
            offset: pageIndex * PAGE_SIZE,
            limit: PAGE_SIZE,
          });
          setPages((prev) => {
            const next = new Map(prev);
            next.set(pageIndex, reply.rows || []);
            return next;
          });
          setTotal(reply.total ?? 0);
          setStateCounts(reply.state_counts || {});
        } catch {
          // Ignore background refresh error.
        }
      })
    );
  }, [http, queryParams]);

  // Refresh loaded pages whenever a JS API mutation advances the store revision.
  const prevRevisionRef = useRef(storeRevision);
  useEffect(() => {
    if (
      prevRevisionRef.current !== null &&
      storeRevision !== null &&
      storeRevision !== prevRevisionRef.current
    ) {
      reloadLoadedPages();
    }
    prevRevisionRef.current = storeRevision;
  }, [storeRevision, reloadLoadedPages]);

  // Reset and reload on filter or sort change.
  useEffect(() => {
    setGeneration((g) => g + 1);
    setPages(new Map());
    setPendingPages(new Set());
    setTotal(null);
    setLoading(true);
    setError(null);
    setSelectedKeys(new Set());
    setAllMatching(false);
    selectedKeysRef.current = new Set();
    allMatchingRef.current = false;
    anchorRowRef.current = null;
    setAnchorRow(null);
    setScrollTop(0);
    if (scrollRef.current) {
      scrollRef.current.scrollTop = 0;
    }
  }, [queryParams, compareMode]);

  // Fetch page helper.
  const loadPage = useCallback(
    (pageIndex) => {
      if (pendingPages.has(pageIndex)) return;
      setPendingPages((prev) => new Set(prev).add(pageIndex));

      const params = {
        ...queryParams,
        offset: pageIndex * PAGE_SIZE,
        limit: PAGE_SIZE,
      };

      http
        .getCompareRows(params)
        .then((reply) => {
          setPendingPages((prev) => {
            const next = new Set(prev);
            next.delete(pageIndex);
            return next;
          });
          setPages((prev) => {
            const next = new Map(prev);
            next.set(pageIndex, reply.rows || []);
            if (next.size > MAX_CACHED_PAGES) {
              const keys = [...next.keys()].sort((a, b) => Math.abs(b - pageIndex) - Math.abs(a - pageIndex));
              next.delete(keys[0]);
            }
            return next;
          });
          setTotal(reply.total ?? 0);
          setStateCounts(reply.state_counts || {});
          setLoading(false);
        })
        .catch((err) => {
          setPendingPages((prev) => {
            const next = new Set(prev);
            next.delete(pageIndex);
            return next;
          });
          setLoading(false);
          setError(err);
        });
    },
    [http, queryParams, pendingPages]
  );

  // Initial page 0 load.
  useEffect(() => {
    loadPage(0, generation);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [generation]);

  // Slow loading indicator timer.
  useEffect(() => {
    if (!loading) {
      setSlowLoading(false);
      return;
    }
    const timer = setTimeout(() => {
      setSlowLoading(true);
    }, 1000);
    return () => clearTimeout(timer);
  }, [loading]);

  // Scroll listener for virtual rendering.
  const onScroll = useCallback((e) => {
    const el = e.currentTarget;
    setScrollTop(el.scrollTop);
    setClientHeight(el.clientHeight);

    setIsFastScrolling(true);
    clearTimeout(fastScrollTimer.current);
    fastScrollTimer.current = setTimeout(() => {
      setIsFastScrolling(false);
    }, 60);
  }, []);

  // Measure visible row range.
  const totalRows = total ?? 0;
  const startRow = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - OVERSCAN);
  const endRow = Math.min(totalRows, Math.ceil((scrollTop + clientHeight) / ROW_HEIGHT) + OVERSCAN);

  // Synchronize layout and dimension refs.
  const totalRowsRef = useRef(totalRows);
  totalRowsRef.current = totalRows;
  const totalColsRef = useRef(totalCols);
  totalColsRef.current = totalCols;
  const clientHeightRef = useRef(clientHeight);
  clientHeightRef.current = clientHeight;

  // Request visible pages if not in cache.
  useEffect(() => {
    if (total == null) return;
    const startPage = Math.floor(startRow / PAGE_SIZE);
    const endPage = Math.floor(Math.max(startRow, endRow - 1) / PAGE_SIZE);
    for (let p = startPage; p <= endPage; p++) {
      if (!pages.has(p) && !pendingPages.has(p)) {
        loadPage(p, generation);
      }
    }
  }, [startRow, endRow, total, pages, pendingPages, loadPage, generation]);

  // Retrieve row by index.
  const getRow = useCallback((rowIndex) => {
    const pageIndex = Math.floor(rowIndex / PAGE_SIZE);
    const page = pagesRef.current?.get(pageIndex);
    return page ? page[rowIndex % PAGE_SIZE] : null;
  }, []);

  // All loaded rows in page order.
  const allLoadedRows = useMemo(() => {
    const sortedEntries = [...pages.entries()].sort((a, b) => a[0] - b[0]);
    return sortedEntries.flatMap(([, list]) => list);
  }, [pages]);

  // Active row object.
  const activeRow = useMemo(() => {
    if (!activeRowKey) return null;
    return allLoadedRows.find((r) => r.row_key === activeRowKey) || null;
  }, [activeRowKey, allLoadedRows]);

  const activeRowIndex = useMemo(() => {
    if (!activeRowKey) return -1;
    return allLoadedRows.findIndex((r) => r.row_key === activeRowKey);
  }, [activeRowKey, allLoadedRows]);

  const canPrevious = activeRowIndex > 0;
  const canNext = activeRowIndex >= 0 && activeRowIndex < allLoadedRows.length - 1;

  const handlePreviousRow = useCallback(() => {
    if (activeRowIndex <= 0) return;
    const prevIdx = activeRowIndex - 1;
    const prevRow = allLoadedRows[prevIdx];
    if (!prevRow) return;
    activeRowKeyRef.current = prevRow.row_key;
    focusedCellRef.current = { r: prevIdx, c: focusedCellRef.current.c };
    setActiveRowKey(prevRow.row_key);
    if (prevIdx === 0) {
      setPaneFocusSeq((s) => s + 1);
    }
  }, [activeRowIndex, allLoadedRows]);

  const handleNextRow = useCallback(() => {
    if (activeRowIndex < 0 || activeRowIndex >= allLoadedRows.length - 1) return;
    const nextIdx = activeRowIndex + 1;
    const nextRow = allLoadedRows[nextIdx];
    if (!nextRow) return;
    activeRowKeyRef.current = nextRow.row_key;
    focusedCellRef.current = { r: nextIdx, c: focusedCellRef.current.c };
    setActiveRowKey(nextRow.row_key);
    if (nextIdx === allLoadedRows.length - 1) {
      setPaneFocusSeq((s) => s + 1);
    }
  }, [activeRowIndex, allLoadedRows]);

  const closePaneAndReturnFocus = useCallback(() => {
    activeRowKeyRef.current = null;
    setActiveRowKey(null);
    setPaneFocusSeq(0);
    const { r, c } = focusedCellRef.current;
    setFocusedCell({ r, c });
    setTimeout(() => {
      const cellNode = gridRef.current?.querySelector(`[data-r="${r}"][data-c="${c}"]`);
      if (cellNode) {
        cellNode.tabIndex = 0;
        cellNode.focus();
      }
    }, 0);
  }, []);

  const clearSelection = useCallback(() => {
    selectedKeysRef.current = new Set();
    setSelectedKeys(new Set());
    allMatchingRef.current = false;
    setAllMatching(false);
    anchorRowRef.current = null;
    setAnchorRow(null);
  }, []);

  const handleEscapeFromPane = useCallback(
    (e) => {
      if (selectedKeysRef.current.size > 0 || allMatchingRef.current) {
        e.preventDefault();
        clearSelection();
      } else {
        e.preventDefault();
        closePaneAndReturnFocus();
      }
    },
    [clearSelection, closePaneAndReturnFocus]
  );

  // Selected rows objects.
  const selectedRowsList = useMemo(() => {
    return allLoadedRows.filter((r) => selectedKeys.has(r.row_key));
  }, [allLoadedRows, selectedKeys]);

  // Row selection toggling.
  const toggleRowSelection = useCallback(
    (index, range = false) => {
      const row = getRow(index);
      if (!row) return;
      setAllMatching(false);
      allMatchingRef.current = false;

      let anchor = anchorRowRef.current;
      if (range) {
        if (anchor === null) {
          anchor = focusedCellRef.current.r;
          anchorRowRef.current = anchor;
          setAnchorRow(anchor);
        }
        const [a, b] = [Math.min(anchor, index), Math.max(anchor, index)];
        const next = new Set(selectedKeysRef.current);
        for (let k = a; k <= b; k++) {
          const r = getRow(k);
          if (r) next.add(r.row_key);
        }
        selectedKeysRef.current = next;
        setSelectedKeys(next);
      } else {
        const next = new Set(selectedKeysRef.current);
        if (next.has(row.row_key)) next.delete(row.row_key);
        else next.add(row.row_key);
        selectedKeysRef.current = next;
        anchorRowRef.current = index;
        setAnchorRow(index);
        setSelectedKeys(next);
      }
    },
    [getRow]
  );

  // Header checkbox toggle.
  const toggleSelectLoaded = useCallback(() => {
    if (selectedKeysRef.current.size > 0 || allMatchingRef.current) {
      clearSelection();
    } else {
      const next = new Set();
      for (const row of allLoadedRows) {
        next.add(row.row_key);
      }
      selectedKeysRef.current = next;
      setSelectedKeys(next);
      anchorRowRef.current = 0;
      setAnchorRow(0);
    }
  }, [allLoadedRows, clearSelection]);

  // Global search shortcut "/" handler.
  useEffect(() => {
    const onKeyDown = (e) => {
      if (slashGoesToSearch(e)) {
        e.preventDefault();
        searchInputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  // Cell focus helper for direct cell focus events.
  const handleCellFocus = useCallback((r, c) => {
    focusedCellRef.current = { r, c };
    setFocusedCell((prev) => {
      if (prev.r === r && prev.c === c) return prev;
      return { r, c };
    });
  }, []);

  // Cell focus helper.
  const moveFocus = useCallback((r, c) => {
    const maxR = Math.max(0, totalRowsRef.current - 1);
    const nextR = Math.max(0, Math.min(maxR, r));
    const nextC = Math.max(0, Math.min(totalColsRef.current - 1, c));
    focusedCellRef.current = { r: nextR, c: nextC };
    setFocusedCell({ r: nextR, c: nextC });

    // Scroll row into view if needed.
    const el = scrollRef.current;
    if (el) {
      const y = nextR * ROW_HEIGHT;
      if (y < el.scrollTop) el.scrollTop = y;
      else if (y + ROW_HEIGHT > el.scrollTop + el.clientHeight) {
        el.scrollTop = y + ROW_HEIGHT - el.clientHeight;
      }
    }

    // Synchronously focus cell element if present in DOM.
    const cellNode = gridRef.current?.querySelector(`[data-r="${nextR}"][data-c="${nextC}"]`);
    if (cellNode) {
      cellNode.tabIndex = 0;
      cellNode.focus();
    } else {
      setTimeout(() => {
        const node = gridRef.current?.querySelector(`[data-r="${nextR}"][data-c="${nextC}"]`);
        if (node) {
          node.tabIndex = 0;
          node.focus();
        }
      }, 0);
    }
  }, []);

  // Synchronize actual DOM element focus when focusedCell updates.
  useEffect(() => {
    const { r, c } = focusedCell;
    const cellNode = gridRef.current?.querySelector(`[data-r="${r}"][data-c="${c}"]`);
    if (cellNode && document.activeElement !== cellNode) {
      if (
        gridRef.current?.contains(document.activeElement) ||
        document.activeElement === scrollRef.current ||
        document.activeElement === document.body ||
        !document.activeElement
      ) {
        cellNode.focus();
      }
    }
  }, [focusedCell]);

  const handleUndoSingle = useCallback(
    async (rowKey, fallbackChoice) => {
      let prev = fallbackChoice;
      if (prev === undefined) {
        const item = [...undoHistory].reverse().find((h) => h.type === "single" && h.rowKey === rowKey);
        prev = item ? item.previousChoice : null;
      }
      const reply = await singleChoiceAction.run({
        row_key: rowKey,
        choice: prev || null,
      });
      if (reply) {
        setLastSavedRowKey(null);
        triggerRowFlash(rowKey);
        toast.show({ tone: "ok", text: "Merge choice undone" });
        reloadLoadedPages();
        store.load("session");
        store.load("plan");
      }
    },
    [singleChoiceAction, reloadLoadedPages, store, toast, triggerRowFlash, undoHistory]
  );

  const handleSingleRowChoice = useCallback(
    async (row, kind) => {
      if (!row || changeDisabled) return;
      const previousChoice = row.merge_choice ? { ...row.merge_choice } : null;
      let choicePayload = { choice: kind };
      if (kind === "take") {
        const availableDonor =
          donors.find((d) => {
            const cell = Array.isArray(row.cells)
              ? row.cells.find((c) => c.source_id === d.source_id)
              : row.cells?.[d.source_id];
            return cell && cell.state !== "missing";
          }) || donors[0];
        if (availableDonor) {
          choicePayload = { choice: "take", source: availableDonor.source_id };
        }
      }

      setUndoHistory((h) => [...h, { type: "single", rowKey: row.row_key, previousChoice }]);
      setLastSavedRowKey(row.row_key);
      triggerRowFlash(row.row_key);

      const reply = await singleChoiceAction.run({
        row_key: row.row_key,
        choice: choicePayload,
      });

      if (reply) {
        toast.show({
          tone: "ok",
          text: `Merge choice saved: ${kind}`,
          action: {
            label: "Undo",
            onClick: () => handleUndoSingle(row.row_key, previousChoice),
          },
        });
        reloadLoadedPages();
        store.load("session");
        store.load("plan");
      }
    },
    [changeDisabled, donors, singleChoiceAction, reloadLoadedPages, store, toast, triggerRowFlash, handleUndoSingle]
  );

  // Keyboard navigation on grid.
  const onGridKeyDown = useCallback(
    (e) => {
      const { r, c } = focusedCellRef.current;
      const totalR = totalRowsRef.current;
      const totalC = totalColsRef.current;
      const pageRows = Math.max(1, Math.floor(clientHeightRef.current / ROW_HEIGHT) - 1);
      const k = e.key;

      if (k === "ArrowDown") {
        e.preventDefault();
        const nextR = Math.min(Math.max(0, totalR - 1), r + 1);
        if (e.shiftKey) toggleRowSelection(nextR, true);
        moveFocus(nextR, c);
      } else if (k === "ArrowUp") {
        e.preventDefault();
        const nextR = Math.max(0, r - 1);
        if (e.shiftKey) toggleRowSelection(nextR, true);
        moveFocus(nextR, c);
      } else if (k === "ArrowRight") {
        e.preventDefault();
        moveFocus(r, Math.min(totalC - 1, c + 1));
      } else if (k === "ArrowLeft") {
        e.preventDefault();
        moveFocus(r, Math.max(0, c - 1));
      } else if (k === "Home") {
        e.preventDefault();
        if (e.ctrlKey) moveFocus(0, 0);
        else moveFocus(r, 0);
      } else if (k === "End") {
        e.preventDefault();
        if (e.ctrlKey) moveFocus(totalR - 1, totalC - 1);
        else moveFocus(r, totalC - 1);
      } else if (k === "PageDown") {
        e.preventDefault();
        moveFocus(Math.min(totalR - 1, r + pageRows), c);
      } else if (k === "PageUp") {
        e.preventDefault();
        moveFocus(Math.max(0, r - pageRows), c);
      } else if (k === "Enter") {
        e.preventDefault();
        const row = getRow(r);
        if (row) {
          activeRowKeyRef.current = row.row_key;
          setActiveRowKey(row.row_key);
          setPaneFocusSeq((s) => s + 1);
        }
      } else if (k === " ") {
        e.preventDefault();
        toggleRowSelection(r, e.shiftKey);
      } else if ((k === "a" || k === "A") && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        toggleSelectLoaded();
      } else if (k === "Escape") {
        if (selectedKeysRef.current.size > 0 || allMatchingRef.current) {
          e.preventDefault();
          clearSelection();
        } else if (activeRowKeyRef.current) {
          e.preventDefault();
          closePaneAndReturnFocus();
        }
      } else if ((k === "d" || k === "D") && !e.ctrlKey && !e.metaKey && !e.altKey) {
        if (c >= 5 && c < 5 + donors.length) {
          const row = getRow(r);
          const donor = donors[c - 5];
          if (row && donor) {
            const cell = Array.isArray(row.cells)
              ? row.cells.find((x) => x.source_id === donor.source_id)
              : row.cells?.[donor.source_id];
            if (cell && cell.state !== "same") {
              e.preventDefault();
              const triggerEl = gridRef.current?.querySelector(`[data-r="${r}"][data-c="${c}"]`);
              setDiffTarget({ row, donor, triggerElement: triggerEl });
            }
          }
        }
      } else if ((k === "m" || k === "M") && !e.ctrlKey && !e.metaKey && !e.altKey) {
        if (selectedKeysRef.current.size > 0 || allMatchingRef.current) {
          e.preventDefault();
          setBulkMenuOpen(true);
        }
      } else if ((k === "k" || k === "K") && !e.ctrlKey && !e.metaKey && !e.altKey) {
        e.preventDefault();
        const row = getRow(r);
        if (row) handleSingleRowChoice(row, "keep");
      } else if ((k === "t" || k === "T") && !e.ctrlKey && !e.metaKey && !e.altKey) {
        e.preventDefault();
        const row = getRow(r);
        if (row) handleSingleRowChoice(row, "take");
      } else if ((k === "s" || k === "S") && !e.ctrlKey && !e.metaKey && !e.altKey) {
        e.preventDefault();
        const row = getRow(r);
        if (row) handleSingleRowChoice(row, "skip");
      } else if ((k === "z" || k === "Z") && (e.ctrlKey || e.metaKey) && !e.altKey) {
        e.preventDefault();
        if (lastSavedRowKey) {
          handleUndoSingle(lastSavedRowKey);
        }
      } else if ((k === "u" || k === "U") && !e.ctrlKey && !e.metaKey && !e.altKey) {
        e.preventDefault();
        const dir = e.shiftKey ? -1 : 1;
        let targetR = -1;
        const start = r + dir;
        const end = dir === 1 ? totalR : -1;
        for (let i = start; i !== end; i += dir) {
          const row = getRow(i);
          if (row && !row.merge_choice) {
            targetR = i;
            break;
          }
        }
        if (targetR >= 0) {
          moveFocus(targetR, c);
        }
      } else if ((k === "b" || k === "B") && !e.ctrlKey && !e.metaKey && !e.altKey) {
        e.preventDefault();
        const dir = e.shiftKey ? -1 : 1;
        let targetR = -1;
        const start = r + dir;
        const end = dir === 1 ? totalR : -1;
        for (let i = start; i !== end; i += dir) {
          const row = getRow(i);
          if (
            row &&
            (row.row_state === "conflict" ||
              row.row_state === "missing" ||
              (row.marks && row.marks.length > 0))
          ) {
            targetR = i;
            break;
          }
        }
        if (targetR >= 0) {
          moveFocus(targetR, c);
        }
      }
    },
    [
      clearSelection,
      closePaneAndReturnFocus,
      donors,
      getRow,
      handleSingleRowChoice,
      handleUndoSingle,
      lastSavedRowKey,
      moveFocus,
      toggleRowSelection,
      toggleSelectLoaded,
    ]
  );

  // Compare mode toggle.
  const handleModeChange = async (newMode) => {
    if (newMode === compareMode) return;
    const reply = await setModeAction.run({ compare_mode: newMode });
    if (reply) {
      clearSelection();
      store.load("session");
    }
  };

  // Bulk Apply Choice.
  const handleApplyBulkChoice = async (choice, { skippedCount = 0 } = {}) => {
    let keys = [];
    if (allMatching) {
      const collected = [];
      let offset = 0;
      const limit = 200;
      let hasMore = true;

      while (hasMore && collected.length < 5000) {
        try {
          const res = await http.getCompareRows({ ...queryParams, offset, limit });
          const rows = res.rows || [];
          for (const row of rows) collected.push(row.row_key);
          offset += rows.length;
          hasMore = Boolean(res.has_more && rows.length > 0);
        } catch {
          break;
        }
      }
      keys = collected;
    } else {
      keys = Array.from(selectedKeys);
    }

    const previousMap = new Map();
    for (const key of keys) {
      const r = allLoadedRows.find((row) => row.row_key === key);
      previousMap.set(key, r?.merge_choice ? { ...r.merge_choice } : null);
    }

    const choicePayload = { choice: choice.kind };
    if (choice.kind === "take_from") choicePayload.source = choice.source_id;
    if (choice.kind === "remove" && choice.policy) choicePayload.policy = choice.policy;

    const reply = await bulkSetAction.run({ row_keys: keys, choice: choicePayload });
    if (reply) {
      clearSelection();
      const appliedCount = Math.max(0, keys.length - skippedCount);
      const isCapped = allMatching && total > 5000;
      const capSuffix = isCapped ? " (cap: 5,000)" : "";
      const toastText =
        (skippedCount > 0
          ? tn("compare.bulk.toast", appliedCount, { m: skippedCount })
          : tn("compare.bulk.toast.clean", appliedCount)) + capSuffix;

      const undoBulk = async () => {
        try {
          const items = Array.from(previousMap.entries()).map(([row_key, c]) => ({
            row_key,
            choice: c,
          }));
          await bulkSetAction.run({ items });
          toast.show({ tone: "ok", text: "Bulk choices undone" });
          reloadLoadedPages();
          store.load("session");
          store.load("plan");
        } catch {
          // ignore
        }
      };

      toast.show({
        tone: "ok",
        text: toastText,
        action: { label: "Undo", onClick: undoBulk },
      });
      reloadLoadedPages();
      store.load("compareRows", queryParams);
      store.load("session");
      store.load("plan");
    }
  };

  // Bulk Confirm Rows.
  const handleConfirmRows = async () => {
    let keys = [];
    if (allMatching) {
      const collected = [];
      let offset = 0;
      const limit = 200;
      let hasMore = true;

      while (hasMore && collected.length < 5000) {
        try {
          const res = await http.getCompareRows({ ...queryParams, offset, limit });
          const rows = res.rows || [];
          for (const row of rows) collected.push(row.row_key);
          offset += rows.length;
          hasMore = Boolean(res.has_more && rows.length > 0);
        } catch {
          break;
        }
      }
      keys = collected;
    } else {
      keys = Array.from(selectedKeys);
    }

    const reply = await confirmAction.run({ row_keys: keys });
    if (reply) {
      clearSelection();
      const confirmedCount = Array.isArray(reply.confirmed)
        ? reply.confirmed.length
        : (reply.confirmed ?? keys.length);
      toast.show({
        tone: "ok",
        text: tn("compare.bulk.confirm_rows", confirmedCount),
      });
      reloadLoadedPages();
      store.load("compareRows", queryParams);
    }
  };

  // Clear all filters.
  const clearAllFilters = () => {
    setQ("");
    setDebouncedQ("");
    setStateFilter("all");
    setTypeFilters([]);
    setTableFilter("");
    setFolderFilter("");
    setSourceFilters([]);
    setChangedFilter(false);
    setMarksFilter(false);
    setProposalFilter(false);
  };

  const hasActiveFilters =
    debouncedQ ||
    stateFilter !== "all" ||
    typeFilters.length > 0 ||
    tableFilter ||
    folderFilter ||
    sourceFilters.length > 0 ||
    changedFilter ||
    marksFilter ||
    proposalFilter;

  const openPaneByClick = (rowKey) => {
    activeRowKeyRef.current = rowKey;
    setPaneFocusSeq(0);
    setActiveRowKey(rowKey);
  };

  // Render cell helper.
  const renderCell = (row, rowIndex, colIndex, isFocused) => {
    const tabIndex = isFocused ? 0 : -1;
    const isSelected = allMatching || selectedKeys.has(row?.row_key);

    // Skeleton row if row is loading.
    if (!row) {
      return (
        <div
          key={`cell-${rowIndex}-${colIndex}`}
          className={`dc-cell ${colIndex < 4 ? `dc-stick dc-col-${["chk", "obj", "rs", "mc"][colIndex]}` : ""}`}
          role="gridcell"
          aria-colindex={colIndex + 1}
          tabIndex={tabIndex}
          data-r={rowIndex}
          data-c={colIndex}
        >
          {colIndex === 0 ? null : <span className="dc-skel-line" />}
        </div>
      );
    }

    // Light-row rule during fast scroll: render name (col 1) and state (col 2) only.
    if (isFastScrolling && colIndex !== 1 && colIndex !== 2) {
      return (
        <div
          key={`cell-${rowIndex}-${colIndex}`}
          className={`dc-cell ${colIndex < 4 ? `dc-stick dc-col-${["chk", "obj", "rs", "mc"][colIndex]}` : ""}`}
          role="gridcell"
          aria-colindex={colIndex + 1}
          tabIndex={tabIndex}
          data-r={rowIndex}
          data-c={colIndex}
        />
      );
    }

    const getCellData = (sourceId) => {
      if (Array.isArray(row.cells)) {
        return row.cells.find((c) => c.source_id === sourceId) || null;
      }
      return row.cells?.[sourceId] || null;
    };

    // Col 0: Checkbox
    if (colIndex === 0) {
      return (
        <div
          key={`cell-${rowIndex}-0`}
          className="dc-cell dc-stick dc-col-chk"
          role="gridcell"
          aria-colindex={1}
          tabIndex={tabIndex}
          data-r={rowIndex}
          data-c={0}
          onFocus={() => handleCellFocus(rowIndex, 0)}
          onClick={(e) => {
            e.stopPropagation();
            toggleRowSelection(rowIndex, e.shiftKey);
          }}
        >
          <input
            type="checkbox"
            tabIndex={0}
            checked={isSelected}
            aria-label={t("compare.select_row", { name: row.name })}
            aria-keyshortcuts="Space"
            onChange={() => {}}
          />
        </div>
      );
    }

    // Col 1: Object
    if (colIndex === 1) {
      const ObjIcon = objectTypeIcon(row.object_type);
      return (
        <div
          key={`cell-${rowIndex}-1`}
          className="dc-cell dc-stick dc-col-obj"
          role="gridcell"
          aria-colindex={2}
          tabIndex={tabIndex}
          data-r={rowIndex}
          data-c={1}
          onFocus={() => handleCellFocus(rowIndex, 1)}
          onClick={() => openPaneByClick(row.row_key)}
        >
          <ObjIcon className="dc-obj-icon" aria-hidden="true" />
          <div className="dc-obj-box">
            <span className="dc-obj-name">
              {row.table && row.object_type !== "table"
                ? formatDaxName(row.table, row.name)
                : row.object_type === "table"
                  ? `'${row.name}'`
                  : formatObjectRef(row.name)}
            </span>
            <span className="dc-obj-meta">
              {row.object_type}
            </span>
          </div>
        </div>
      );
    }

    // Col 2: Row state
    if (colIndex === 2) {
      const rawState = row.row_state || "same";
      const state = rawState === "conflict" ? "type_conflict" : rawState;
      const StateIcon = STATE_ICONS[state] || STATE_ICONS.same;
      const label = stateWord(state);

      // Distinct non-same states.
      const cellValues = Array.isArray(row.cells) ? row.cells : Object.values(row.cells || {});
      const otherStates = new Set(
        cellValues.map((c) => c.state).filter((s) => s && s !== "same" && s !== "target" && s !== row.row_state)
      );
      const extraCount = otherStates.size;

      return (
        <div
          key={`cell-${rowIndex}-2`}
          className="dc-cell dc-stick dc-col-rs"
          role="gridcell"
          aria-colindex={3}
          tabIndex={tabIndex}
          data-r={rowIndex}
          data-c={2}
          onFocus={() => handleCellFocus(rowIndex, 2)}
          onClick={() => openPaneByClick(row.row_key)}
        >
          <Tooltip content={state === "type_conflict" ? t("compare.state.type_conflict.help") : null}>
            <span className={`dc-st dc-st-${state}`}>
              <StateIcon aria-hidden="true" />
              <span>{label}</span>
            </span>
          </Tooltip>
          {extraCount > 0 ? (
            <Tooltip content="More states in this row">
              <span className="dc-st-count">
                +{extraCount}
              </span>
            </Tooltip>
          ) : null}
        </div>
      );
    }

    // Col 3: Merge Choice (pinned next to row state)
    if (colIndex === 3) {
      const mc = choiceText(row.merge_choice, donors);
      const badge = mergeChoiceBadge(row, session, donors);
      const rawKind = row.merge_choice ? (row.merge_choice.kind || row.merge_choice.choice) : null;
      const choiceKind = rawKind ? normalizeChoiceKind(rawKind) : null;
      const isSaved = lastSavedRowKey === row.row_key;

      const hasDonor = donors.some((d) => {
        const cell = getCellData(d.source_id);
        return cell && cell.state !== "missing";
      });

      return (
        <div
          key={`cell-${rowIndex}-3`}
          className="dc-cell dc-stick dc-col-mc"
          role="gridcell"
          aria-colindex={4}
          tabIndex={tabIndex}
          data-r={rowIndex}
          data-c={3}
          onFocus={() => handleCellFocus(rowIndex, 3)}
          onClick={(e) => {
            if (!e.target.closest("button")) {
              openPaneByClick(row.row_key);
            }
          }}
        >
          <div className="dc-mc-cell">
            <div className="dc-mc-toggle-group" role="group" aria-label={t("compare.column.choice")}>
              <button
                type="button"
                className={`dc-mc-btn ${choiceKind === "keep" ? "is-active" : ""}`}
                disabled={changeDisabled}
                onClick={(e) => {
                  e.stopPropagation();
                  handleSingleRowChoice(row, "keep");
                }}
                title="Keep target (K)"
                aria-keyshortcuts="k"
              >
                Keep
              </button>
              <button
                type="button"
                className={`dc-mc-btn ${choiceKind === "take" ? "is-active" : ""}`}
                disabled={changeDisabled || !hasDonor}
                onClick={(e) => {
                  e.stopPropagation();
                  handleSingleRowChoice(row, "take");
                }}
                title={hasDonor ? "Take from donor (T)" : "No donor available"}
                aria-keyshortcuts="t"
              >
                Take
              </button>
              <button
                type="button"
                className={`dc-mc-btn ${choiceKind === "skip" ? "is-active" : ""}`}
                disabled={changeDisabled}
                onClick={(e) => {
                  e.stopPropagation();
                  handleSingleRowChoice(row, "skip");
                }}
                title="Skip (S)"
                aria-keyshortcuts="s"
              >
                Skip
              </button>
            </div>
            {isSaved ? (
              <span className="dc-mc-saved">
                Saved · <button type="button" className="dc-link dc-mc-undo-btn" onClick={(e) => { e.stopPropagation(); handleUndoSingle(row.row_key); }}>Undo</button>
              </span>
            ) : choiceKind && !["keep", "take", "skip"].includes(choiceKind) ? (
              <Tooltip content={mc}>
                <span className="dc-mc-custom-label">{mc}</span>
              </Tooltip>
            ) : null}
            {badge ? (
              <Tooltip content={badge.tooltip}>
                <span className={`dc-badge ${badge.className}`} data-badge={badge.kind}>
                  {badge.kind === "mark" ? <Flag aria-hidden="true" /> : null}
                  <span>{badge.label}</span>
                </span>
              </Tooltip>
            ) : null}
          </div>
        </div>
      );
    }

    // Col 4: Target
    if (colIndex === 4) {
      const isMissing = targetSource?.status === "missing";
      const targetCell = isMissing ? null : (getCellData("s0") || getCellData(targetSource?.source_id) || {
        state: "target",
      });
      return (
        <div
          key={`cell-${rowIndex}-4`}
          className={`dc-cell dc-col-tg ${isMissing ? "dc-cell-missing" : ""}`}
          role="gridcell"
          aria-colindex={5}
          tabIndex={tabIndex}
          data-r={rowIndex}
          data-c={4}
          onFocus={() => handleCellFocus(rowIndex, 4)}
          onClick={isMissing ? undefined : () => openPaneByClick(row.row_key)}
        >
          {isMissing ? (
            <Tooltip content={`${targetSource?.display_name || "Target"}: Not found`}>
              <span className="dc-st dc-st-missing">
                <CircleDashed aria-hidden="true" />
                <span>Not found</span>
              </span>
            </Tooltip>
          ) : (
            <StateCell cell={targetCell} sourceName={targetSource?.display_name || "Target"} />
          )}
        </div>
      );
    }

    // Donor columns (5 .. 5 + donors.length - 1)
    if (colIndex >= 5 && colIndex < 5 + donors.length) {
      const donorIndex = colIndex - 5;
      const donor = donors[donorIndex];
      const isMissing = donor?.status === "missing";
      const cell = isMissing ? null : getCellData(donor.source_id);

      const openDiffForDonor = () => {
        if (isMissing) return;
        const triggerEl = gridRef.current?.querySelector(`[data-r="${rowIndex}"][data-c="${colIndex}"]`);
        setDiffTarget({ row, donor, triggerElement: triggerEl });
      };

      return (
        <div
          key={`cell-${rowIndex}-${colIndex}`}
          className={`dc-cell ${isMissing ? "dc-cell-missing" : ""}`}
          role="gridcell"
          aria-colindex={colIndex + 1}
          tabIndex={tabIndex}
          data-r={rowIndex}
          data-c={colIndex}
          onFocus={() => handleCellFocus(rowIndex, colIndex)}
          onClick={isMissing ? undefined : () => openPaneByClick(row.row_key)}
        >
          {isMissing ? (
            <Tooltip content={`${donor.display_name || donor.name}: Not found`}>
              <span className="dc-st dc-st-missing">
                <CircleDashed aria-hidden="true" />
                <span>Not found</span>
              </span>
            </Tooltip>
          ) : (
            <StateCell
              cell={cell}
              sourceName={donor.display_name || donor.name}
              onOpenDiff={openDiffForDonor}
            />
          )}
        </div>
      );
    }

    // Marks column: colIndex === totalCols - 1
    if (colIndex === totalCols - 1) {
      const hasMarks = row.marks && row.marks.length > 0;
      const cellValues = Array.isArray(row.cells) ? row.cells : Object.values(row.cells || {});
      const hasChanged = row.changed || cellValues.some((c) => c.changed);

      return (
        <div
          key={`cell-${rowIndex}-${colIndex}`}
          className="dc-cell"
          role="gridcell"
          aria-colindex={colIndex + 1}
          tabIndex={tabIndex}
          data-r={rowIndex}
          data-c={colIndex}
          onFocus={() => handleCellFocus(rowIndex, colIndex)}
          onClick={() => openPaneByClick(row.row_key)}
        >
          {hasMarks ? (
            <span className="dc-badge dc-badge-mark">
              <Flag aria-hidden="true" />
              <span>{t("compare.mark.confirm")}</span>
            </span>
          ) : null}
          {hasChanged ? (
            <span className="dc-badge dc-badge-changed">
              <Circle aria-hidden="true" />
              <span>{t("compare.mark.changed")}</span>
            </span>
          ) : null}
        </div>
      );
    }

    return null;
  };

  const handleHeaderSort = (field) => {
    if (sortField === field) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortField(field);
      setSortDir("asc");
    }
  };

  const totalLoaded = allLoadedRows.length;

  const modeControl = (
    <div className="flex items-center gap-2">
      <span className="text-xs text-[var(--text-2)]">{t("compare.mode")}</span>
      <SegmentedControl
        mode="radio"
        options={[
          { value: "default", label: t("compare.mode.default") },
          { value: "strict", label: t("compare.mode.strict") },
        ]}
        value={compareMode}
        onValueChange={handleModeChange}
        aria-label={t("compare.mode")}
      />
    </div>
  );

  return (
    <div className="dc-compare" data-tab="compare">
      {/* Bulk bar or Filter bar */}
      {selectedKeys.size > 0 || allMatching ? (
        <BulkBar
          selectedCount={selectedKeys.size}
          allMatching={allMatching}
          totalMatching={totalRows}
          loadedCount={totalLoaded}
          marksFilterActive={marksFilter}
          donors={donors}
          onApplyChoice={handleApplyBulkChoice}
          onEditTarget={targetSource ? () => setEditOpen(true) : undefined}
          onConfirmRows={handleConfirmRows}
          onClearSelection={clearSelection}
          onSelectAllMatching={() => {
            allMatchingRef.current = true;
            setAllMatching(true);
          }}
          disabled={changeDisabled}
          reasonId={reasonId}
          selectedRows={selectedRowsList}
          setMenuRef={bulkMenuBtnRef}
          menuOpen={bulkMenuOpen}
          onMenuOpenChange={setBulkMenuOpen}
        />
      ) : (
        <div className="dc-toolbar" data-ui-actions="" role="toolbar" aria-label="Filters">
          <Tooltip content="Search names (/)">
            <label className="dc-search">
              <Search className="dc-search-icon" aria-hidden="true" />
              <input
                ref={searchInputRef}
                id="q"
                type="search"
                className="dc-search-input"
                placeholder={t("compare.search")}
                value={q}
                onChange={(e) => setQ(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Escape") {
                    e.preventDefault();
                    e.stopPropagation();
                    if (q) {
                      setQ("");
                      setDebouncedQ("");
                    } else {
                      e.target.blur();
                    }
                  }
                }}
                aria-keyshortcuts="/"
                aria-label={t("compare.search")}
              />
            </label>
          </Tooltip>

          <FilterButton
            label={t("compare.filter.state")}
            selected={stateFilter === "all" ? [] : [stateFilter]}
            onSelectedChange={(vals) => setStateFilter(vals[0] || "all")}
            options={[
              { value: "notsame", label: "Not same (hide Same rows)" },
              { value: "conflict", label: "Type conflict" },
              { value: "missing", label: "Missing" },
              { value: "renamed", label: "Renamed" },
              { value: "moved", label: "Moved" },
              { value: "different", label: "Different" },
              { value: "same", label: "Same" },
            ]}
          />

          <FilterButton
            label={t("compare.filter.type")}
            selected={typeFilters}
            onSelectedChange={setTypeFilters}
            options={[
              { value: "measure", label: "Measure" },
              { value: "column", label: "Column" },
              { value: "table", label: "Table" },
              { value: "relationship", label: "Relationship" },
              { value: "hierarchy", label: "Hierarchy" },
              { value: "partition", label: "Partition" },
            ]}
          />

          <Button
            variant="outline"
            size="sm"
            data-active={marksFilter || undefined}
            onClick={() => setMarksFilter((v) => !v)}
            aria-pressed={marksFilter}
          >
            {t("compare.filter.marks")}
          </Button>

          <Button
            variant="outline"
            size="sm"
            data-active={changedFilter || undefined}
            onClick={() => setChangedFilter((v) => !v)}
            aria-pressed={changedFilter}
            tooltip={t("compare.filter.changed.help")}
          >
            {t("compare.filter.changed")}
          </Button>

          <span className="dc-spacer" />

          <GridShortcutsHelp />

          {modeControl}
        </div>
      )}

      {/* Active filter chips */}
      {hasActiveFilters ? (
        <div className="dc-chips">
          {stateFilter === "notsame" ? (
            <FilterChip
              label="State: not same"
              onRemove={() => setStateFilter("all")}
            />
          ) : stateFilter && stateFilter !== "all" ? (
            <FilterChip
              label={`State: ${stateWord(stateFilter)}`}
              onRemove={() => setStateFilter("all")}
            />
          ) : null}

          {typeFilters.map((tp) => (
            <FilterChip
              key={tp}
              label={`Type: ${tp}`}
              onRemove={() => setTypeFilters((list) => list.filter((x) => x !== tp))}
            />
          ))}

          {marksFilter ? (
            <FilterChip
              label={t("work.compare.marks")}
              onRemove={() => setMarksFilter(false)}
            />
          ) : null}

          {changedFilter ? (
            <FilterChip
              label="Changed since last check"
              onRemove={() => setChangedFilter(false)}
            />
          ) : null}

          {debouncedQ ? (
            <FilterChip
              label={`Name contains "${debouncedQ}"`}
              onRemove={() => {
                setQ("");
                setDebouncedQ("");
              }}
            />
          ) : null}

          <button
            type="button"
            className="dc-link text-xs"
            id="clearf"
            onClick={clearAllFilters}
          >
            {t("shared.clear_filters")}
          </button>
        </div>
      ) : null}

      {/* Main Area: Grid + Side Pane */}
      <div className={`dc-compare-area ${activeRow ? "with-pane" : ""}`}>
        <div className="dc-grid-frame">
          {loading ? <div className="dc-loadbar" aria-hidden="true" /> : null}

          {error ? (
            <div className="p-8">
              <EmptyState
                variant="error"
                title={t("compare.error.title")}
                action={
                  <Button variant="outline" onClick={() => loadPage(0, generation)}>
                    {t("compare.error.action")}
                  </Button>
                }
              >
                {t("compare.error.body", { message: error.message || "" })}
              </EmptyState>
            </div>
          ) : !loading && totalRows === 0 && !hasActiveFilters ? (
            <div className="p-8">
              <EmptyState
                title={t("compare.empty.title")}
                action={
                  <Button variant="outline" onClick={() => onTabs?.({ tab: "sources" })}>
                    {t("compare.empty.action")}
                  </Button>
                }
              >
                {t("compare.empty.body")}
              </EmptyState>
            </div>
          ) : !loading && totalRows === 0 && hasActiveFilters ? (
            <div className="p-8">
              <EmptyState
                title={t("compare.no_match.title")}
                action={
                  <Button variant="outline" id="clearf2" onClick={clearAllFilters}>
                    {t("compare.no_match.action")}
                  </Button>
                }
              >
                {tn("compare.no_match.body", allLoadedRows.length || 0)}
              </EmptyState>
            </div>
          ) : (
            <>
              <div
                ref={scrollRef}
                className="dc-grid-scroll"
                onScroll={onScroll}
                tabIndex={0}
                onKeyDown={onGridKeyDown}
              >
                <div
                  ref={gridRef}
                  className="dc-grid"
                  role="grid"
                  aria-label="Compare rows"
                  aria-multiselectable="true"
                  aria-rowcount={total == null ? -1 : total + 1}
                  aria-colcount={totalCols}
                  aria-busy={String(loading)}
                  style={{
                    "--cols": colsCss,
                    width: `${totalGridWidth}px`,
                  }}
                >
                  {/* Header Row */}
                  <div className="dc-row dc-hrow" role="row" aria-rowindex={1}>
                    <div className="dc-hcell dc-stick dc-col-chk" role="columnheader" aria-colindex={1}>
                      <input
                        id="hchk"
                        type="checkbox"
                        tabIndex={0}
                        aria-label={t("compare.select_loaded")}
                        aria-keyshortcuts="Control+A"
                        checked={selectedKeys.size > 0 || allMatching}
                        onChange={toggleSelectLoaded}
                      />
                    </div>

                    <div
                      className="dc-hcell dc-stick dc-col-obj"
                      role="columnheader"
                      aria-colindex={2}
                      aria-sort={sortField === "name" ? (sortDir === "asc" ? "ascending" : "descending") : "none"}
                      onClick={() => handleHeaderSort("name")}
                    >
                      <button
                        type="button"
                        className="dc-hcell-btn"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleHeaderSort("name");
                        }}
                      >
                        <span>{t("compare.column.object")}</span>
                        <ArrowUpDown className="w-3 h-3" aria-hidden="true" />
                      </button>
                    </div>

                    <div
                      className="dc-hcell dc-stick dc-col-rs"
                      role="columnheader"
                      aria-colindex={3}
                      aria-sort={sortField === "state" ? (sortDir === "asc" ? "ascending" : "descending") : "none"}
                      onClick={() => handleHeaderSort("state")}
                    >
                      <button
                        type="button"
                        className="dc-hcell-btn"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleHeaderSort("state");
                        }}
                      >
                        <span>{t("compare.column.state")}</span>
                        <ArrowUpDown className="w-3 h-3" aria-hidden="true" />
                      </button>
                    </div>

                    <div
                      className="dc-hcell dc-stick dc-col-mc"
                      role="columnheader"
                      aria-colindex={4}
                    >
                      <span>{t("compare.column.choice")}</span>
                    </div>

                    <div className={`dc-hcell dc-col-tg ${targetSource?.status === "missing" ? "dc-hcell-missing" : ""}`} role="columnheader" aria-colindex={5}>
                      <Target className="w-3.5 h-3.5" aria-hidden="true" />
                      <span>{targetSource?.display_name || "Target"}{targetSource?.status === "missing" ? " (Not found)" : ""}</span>
                      <span className="sr-only"> (target)</span>
                    </div>

                    {donors.map((donor, dIdx) => {
                      const isMissing = donor?.status === "missing";
                      return (
                        <Tooltip key={donor.source_id} content={isMissing ? `${donor.display_name || donor.name}: Not found` : null}>
                          <div
                            className={`dc-hcell ${isMissing ? "dc-hcell-missing" : ""}`}
                            role="columnheader"
                            aria-colindex={6 + dIdx}
                          >
                            <span>{donor.display_name || donor.name}{isMissing ? " (Not found)" : ""}</span>
                          </div>
                        </Tooltip>
                      );
                    })}

                    <div
                      className="dc-hcell"
                      role="columnheader"
                      aria-colindex={totalCols}
                    >
                      <span>{t("compare.column.marks")}</span>
                    </div>
                  </div>

                  {/* Virtualized Body Rows */}
                  <div
                    className="dc-grid-body"
                    role="rowgroup"
                    style={{
                      height: `${(loading && total == null ? 30 : totalRows) * ROW_HEIGHT}px`,
                    }}
                  >
                    {Array.from(
                      { length: Math.max(0, (loading && total == null ? 30 : endRow) - startRow) },
                      (_, i) => startRow + i
                    ).map((rIdx) => {
                      const row = getRow(rIdx);
                      const isSelected = allMatching || (row && selectedKeys.has(row.row_key));
                      const isActive = row && activeRowKey === row.row_key;
                      const isFlashing = row && flashingRowKeys.has(row.row_key);

                      return (
                        <div
                          key={`row-${rIdx}`}
                          className={`dc-row dc-body-row ${isActive ? "active" : ""} ${isSelected ? "is-selected" : ""} ${isFlashing ? "is-flashing" : ""}`}
                          role="row"
                          aria-rowindex={rIdx + 2}
                          aria-selected={Boolean(isSelected)}
                          aria-current={isActive ? "true" : undefined}
                          data-key={row?.row_key}
                          data-i={rIdx}
                          style={{
                            transform: `translateY(${rIdx * ROW_HEIGHT}px)`,
                          }}
                        >
                          {colWidths.map((_, cIdx) =>
                            renderCell(
                              row,
                              rIdx,
                              cIdx,
                              focusedCell.r === rIdx && focusedCell.c === cIdx
                            )
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>

              {/* Grid Footer */}
              <div className="dc-grid-foot" role="status">
                <span>
                  {loading && total == null
                    ? slowLoading
                      ? t("compare.loading.slow")
                      : t("compare.loading")
                    : tn("compare.footer.rows", totalRows)}
                </span>

                <div className="dc-foot-counts">
                  {STATE_PRECEDENCE.filter((st) => stateCounts[st] > 0).map((st) => {
                    const norm = normalizeState(st);
                    const StIcon = STATE_ICONS[norm] || STATE_ICONS.same;
                    return (
                      <span key={st} className={`dc-st dc-st-${norm}`}>
                        <StIcon aria-hidden="true" />
                        <span>{stateWord(norm)}</span>
                        <span>{stateCounts[st]}</span>
                      </span>
                    );
                  })}
                </div>

                <span className="dc-spacer" />

                <span>
                  {compareMode === "strict"
                    ? t("compare.footer.strict")
                    : t("compare.footer.default")}
                </span>
              </div>
            </>
          )}
        </div>

        {/* Side Pane (active row detail) */}
        {activeRow ? (
          <CompareRowDetail
            row={activeRow}
            allRows={allLoadedRows}
            donors={donors}
            targetName={targetSource?.display_name || "Target"}
            session={session}
            selectedCount={allMatching ? totalRows : selectedKeys.size}
            onClearSelection={clearSelection}
            onClose={closePaneAndReturnFocus}
            onEscape={handleEscapeFromPane}
            onOpenDiff={(donor, triggerEl) => {
              const fallbackEl = gridRef.current?.querySelector(".dc-body-row.active");
              setDiffTarget({
                row: activeRow,
                donor,
                triggerElement: triggerEl || fallbackEl,
              });
            }}
            onPreviousRow={handlePreviousRow}
            onNextRow={handleNextRow}
            canPrevious={canPrevious}
            canNext={canNext}
            onSelectRowKey={(key) => {
              activeRowKeyRef.current = key;
              setActiveRowKey(key);
            }}
            onNavigateImpact={(rowKey, rowName) => {
              onTabs?.({ tab: "impact", impactRowKey: rowKey, impactRowName: rowName });
            }}
            http={http}
            changeDisabled={changeDisabled}
            reasonId={reasonId}
            autoFocusHeading={paneFocusSeq}
          />
        ) : null}
      </div>

      {/* Code Diff Modal Dialog */}
      {diffTarget ? (
        <CodeDiff
          row={diffTarget.row}
          initialDonor={diffTarget.donor}
          donors={donors}
          targetName={targetSource?.display_name || "Target"}
          compareMode={compareMode}
          onClose={() => setDiffTarget(null)}
          http={http}
          triggerElement={diffTarget.triggerElement}
        />
      ) : null}

      {/* Edit target: in-place bulk edits with no donor (issue #12) */}
      <BulkEditDialog
        open={editOpen}
        onOpenChange={setEditOpen}
        http={http}
        scope={editScope({ allMatching, queryParams, selectedKeys })}
        count={allMatching ? totalRows : selectedKeys.size}
        allMatching={allMatching}
        onSaved={(reply) => {
          clearSelection();
          toast.show({ tone: "ok", text: tn("edit.toast", reply.count) });
          reloadLoadedPages();
          store.load("compareRows", queryParams);
        }}
      />
    </div>
  );
}
