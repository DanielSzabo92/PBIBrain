import React, { useMemo, useState } from "react";
import { ChevronDown, ChevronRight, TriangleAlert } from "lucide-react";
import { Button } from "./ui/button";
import { Checkbox } from "./ui/checkbox";
import { Label } from "./ui/label";
import { TypeGlyph } from "./TypeGlyph";
import { VersionBadge } from "./VersionBadge";
import { OriginBadge } from "./OriginBadge";
import { buildImpactMatrix } from "../matrix";
import { LANES, laneOf } from "../lineage";
import { groupVersions, versionNote } from "../versions";
import { formatPlural as plural, objectName } from "../presentation";
import { typeLabel } from "../graphPresentation";

// Large projects open with tables and pages folded, so the first view is a readable summary.
const FOLD_TABLES_ABOVE = 160;
const FOLD_PAGES_ABOVE = 48;

const toggle = (set, id) => { const next = new Set(set); if (next.has(id)) next.delete(id); else next.add(id); return next; };

const laneKey = (node) => LANES[laneOf(node)].key;

/**
 * Impact matrix (graph view "Matrix"): model objects down, report visuals across. Solid cells are direct use,
 * outlined cells are use through a calculation, hatched blocks are a report that is not bound to that model.
 * Folded groups show how many of their pairs are used, as a heat value.
 *
 * It reads the same whole-scope payload as Lineage and follows the same lane chips: Tables off flattens the
 * rows, Columns/Calculations off hide those rows, Visuals off folds pages, Pages off drops the page row, and
 * filter lanes off stop counting what those filters use. With "Group versions", twins share a row or column
 * and a half mark says only some versions use the pair.
 */
export default function ImpactMatrix({ graph, error, onRetry, query, hiddenLanes = [], groupVersions: versionsOn = true, colors, selectedId, onSelect }) {
  const [hideUnused, setHideUnused] = useState(false);
  const [userFold, setFolded] = useState(null);
  const [hoverCol, setHoverCol] = useState(-1);
  const off = useMemo(() => new Set(hiddenLanes), [hiddenLanes]);
  const options = useMemo(() => ({ visualFilters: !off.has("visualFilter"), pageFilters: !off.has("pageFilter"), reportFilters: !off.has("reportFilter") }), [off]);

  const raw = useMemo(() => graph ? buildImpactMatrix(graph.nodes || [], graph.edges || [], options) : null, [graph, options]);
  const versions = useMemo(() => graph && versionsOn ? groupVersions(graph.nodes || [], graph.edges || []) : null, [graph, versionsOn]);
  const grouped = Boolean(versions?.grouped);
  const matrix = useMemo(() => grouped ? buildImpactMatrix(versions.nodes, versions.edges, options) : raw, [grouped, versions, options, raw]);
  const rawById = useMemo(() => new Map((graph?.nodes || []).map((node) => [node.id, node])), [graph]);

  // Lane chips: which row kinds take part, and which levels are shown or folded for good.
  const rowLaneOn = (node) => !off.has(laneKey(node));
  const noObjects = off.has("column") && off.has("calc");
  const flatTables = off.has("table");
  const noPages = off.has("page");
  const noVisuals = off.has("visual");
  const fold = useMemo(() => {
    if (!matrix) return null;
    const base = userFold || {
      tables: new Set(matrix.rows.length > FOLD_TABLES_ABOVE ? matrix.rowGroups.flatMap((group) => group.tables.map((table) => table.table.id)) : []),
      pages: new Set(matrix.visuals.length > FOLD_PAGES_ABOVE ? matrix.colGroups.flatMap((group) => group.pages.map((page) => page.page.id)) : []),
      models: new Set(), reports: new Set(),
    };
    const all = (list) => new Set(list);
    return {
      tables: noObjects ? all(matrix.rowGroups.flatMap((group) => group.tables.map((table) => table.table.id))) : base.tables,
      models: noObjects && flatTables ? all(matrix.rowGroups.map((group) => group.model.id)) : base.models,
      pages: noVisuals ? all(matrix.colGroups.flatMap((group) => group.pages.map((page) => page.page.id))) : base.pages,
      reports: noVisuals && noPages ? all(matrix.colGroups.map((group) => group.report.id)) : base.reports,
    };
  }, [matrix, userFold, noObjects, flatTables, noVisuals, noPages]);
  const setFold = (key, id) => setFolded({ ...fold, [key]: toggle(fold[key], id) });

  // A pair of (possibly grouped) objects: its mark, and in how many of the bound version pairs it is used.
  const pair = (rowNode, visualNode) => {
    const value = matrix.cell(rowNode.id, visualNode.id);
    if (!grouped || !value) return { value, partial: false };
    const rows = versions.membersOf.get(rowNode.id) || [rowNode];
    const visuals = versions.membersOf.get(visualNode.id) || [visualNode];
    let pairs = 0, used = 0;
    rows.forEach((row) => visuals.forEach((visual) => {
      if (!raw.bound(raw.modelOf(row), raw.reportOf(visual))) return;
      pairs += 1;
      if (raw.cell(row.id, visual.id)) used += 1;
    }));
    return { value, partial: pairs > 1 && used < pairs, used, pairs };
  };

  const needle = query.trim().toLowerCase();
  const matches = (node) => !needle || objectName(node).toLowerCase().includes(needle);

  // Visible columns: a visual, or a folded page / report standing for all its visuals.
  const columns = useMemo(() => {
    if (!matrix) return [];
    return matrix.colGroups.flatMap(({ report, pages }) => fold.reports.has(report.id)
      ? [{ key: report.id, kind: "report", node: report, reportId: report.id, ids: pages.flatMap((page) => page.visuals.map((visual) => visual.id)) }]
      : pages.flatMap(({ page, visuals }) => fold.pages.has(page.id)
        ? [{ key: page.id, kind: "page", node: page, reportId: report.id, ids: visuals.map((visual) => visual.id) }]
        : visuals.map((visual) => ({ key: visual.id, kind: "visual", node: visual, reportId: report.id, ids: [visual.id] }))));
  }, [matrix, fold]);

  // Visible rows: model header, table header (or folded table), objects.
  const rows = useMemo(() => {
    if (!matrix) return [];
    const used = (id) => { const entry = matrix.usage.get(id); return entry.direct + entry.indirect > 0; };
    return matrix.rowGroups.flatMap(({ model, tables }) => {
      // With Columns and Calculations both off, tables (or models) stand for all their objects.
      const tableRows = tables.map(({ table, rows: members }) => {
        const shown = members.filter((node) => (noObjects || rowLaneOn(node)) && matches(node) && (!hideUnused || used(node.id)));
        return { table, members, shown };
      }).filter((entry) => entry.shown.length || (!needle && !hideUnused && !hiddenLanes.length));
      if (!tableRows.length) return [];
      const head = { kind: "model", key: model.id, node: model, modelId: model.id, ids: tableRows.flatMap((entry) => entry.shown.map((node) => node.id)), count: tableRows.reduce((sum, entry) => sum + entry.shown.length, 0) };
      if (fold.models.has(model.id)) return [{ ...head, folded: true }];
      if (flatTables) return [head, ...tableRows.flatMap(({ shown }) => shown.map((node) => ({ kind: "object", key: node.id, node, modelId: model.id, ids: [node.id] })))];
      return [head, ...tableRows.flatMap(({ table, shown }) => fold.tables.has(table.id)
        ? [{ kind: "table", key: table.id, node: table, modelId: model.id, ids: shown.map((node) => node.id), count: shown.length, folded: true }]
        : [{ kind: "table", key: table.id, node: table, modelId: model.id, ids: shown.map((node) => node.id), count: shown.length, folded: false },
          ...shown.map((node) => ({ kind: "object", key: node.id, node, modelId: model.id, ids: [node.id] }))])];
    });
    // rowLaneOn reads `off`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [matrix, fold, hideUnused, needle, off, noObjects, flatTables]);

  // Folded aggregates: share of used pairs, scaled against the busiest aggregate on screen.
  const aggregate = useMemo(() => {
    if (!matrix) return () => null;
    const cache = new Map();
    let max = 1;
    const count = (row, column) => {
      const key = `${row.key}\u0000${column.key}`;
      if (cache.has(key)) return cache.get(key);
      let used = 0, direct = 0;
      row.ids.forEach((rowId) => column.ids.forEach((visualId) => { const value = matrix.cell(rowId, visualId); if (value) used += 1; if (value === 2) direct += 1; }));
      const result = { used, direct };
      cache.set(key, result);
      max = Math.max(max, used);
      return result;
    };
    rows.forEach((row) => { if (row.kind !== "object" && row.folded) columns.forEach((column) => count(row, column)); });
    rows.forEach((row) => { if (row.kind === "object") columns.forEach((column) => { if (column.kind !== "visual") count(row, column); }); });
    return (row, column) => { const value = count(row, column); return { ...value, heat: value.used / max }; };
  }, [matrix, rows, columns]);

  if (error) return <div className="graph-empty" role="alert"><span className="empty-icon tone-bad" aria-hidden="true"><TriangleAlert /></span><h3>Matrix unavailable</h3><p>{error}</p>{onRetry ? <Button variant="outline" onClick={onRetry}>Retry</Button> : null}</div>;
  if (!matrix) return <div className="graph-empty graph-loading" role="status"><p>Loading matrix…</p></div>;
  if (!matrix.rows.length || !matrix.visuals.length) {
    return <div className="graph-empty"><h3>Nothing to compare yet</h3><p>{!matrix.visuals.length ? "No report visuals are loaded. Scan a report that uses this model." : "No columns or calculations are loaded for this scope."}</p></div>;
  }

  const headRows = noPages ? 2 : 3;
  const unused = matrix.rows.filter((node) => { const entry = matrix.usage.get(node.id); return entry.direct + entry.indirect === 0; }).length;
  const reportSpan = (group) => columns.filter((column) => column.reportId === group.report.id).length;
  const describe = (row, column, value) => {
    const rowName = objectName(row.node), colName = objectName(column.node);
    if (row.kind === "object" && column.kind === "visual" && value?.partial) return `${colName} uses ${rowName} in ${value.used} of ${value.pairs} versions`;
    if (row.kind === "object" && column.kind === "visual") value = value?.value ?? value;
    if (row.kind === "object" && column.kind === "visual") return value === 2 ? `${colName} uses ${rowName} directly` : value === 1 ? `${colName} uses ${rowName} through a calculation or a page/report filter` : `${colName} does not use ${rowName}`;
    return `${rowName} × ${colName}`;
  };

  const renderCell = (row, column, index) => {
    const off = !matrix.bound(row.modelId, column.reportId);
    const common = { key: column.key, "data-c": index };
    if (off) return <td {...common} className="mx-off" title={`${objectName(column.node)} is not bound to ${objectName(matrix.rowGroups.find((group) => group.model.id === row.modelId)?.model)}`} />;
    if (row.kind === "object" && column.kind === "visual") {
      const result = pair(row.node, column.node);
      const value = result.value;
      return <td {...common} title={describe(row, column, result)}>{value ? <span className={`mx-mark ${value === 2 ? "is-direct" : "is-indirect"} ${result.partial ? "is-partial" : ""}`} aria-label={`${value === 2 ? "Direct" : "Indirect"}${result.partial ? `, in ${result.used} of ${result.pairs} versions` : ""}`} /> : null}</td>;
    }
    if (row.kind !== "object" && !row.folded) return <td {...common} className="mx-band" />;
    const { used, direct, heat } = aggregate(row, column);
    return <td {...common} title={`${describe(row, column)}: ${used} of ${row.ids.length * column.ids.length} pairs used${direct ? `, ${direct} directly` : ""}`}>
      {used ? <span className="mx-heat" style={{ "--heat": Math.max(0.18, heat) }} data-ui-number="">{used}</span> : null}
    </td>;
  };

  return <div className="impact-matrix-view">
    <div className="mx-bar" data-ui-actions="">
      <span className="mx-legend" aria-label="Legend">
        <span><i className="mx-mark is-direct" aria-hidden="true" />Used directly</span>
        <span><i className="mx-mark is-indirect" aria-hidden="true" />Through a calculation or filter</span>
        <span><i className="mx-swatch-off" aria-hidden="true" />Report not bound to this model</span>
        {grouped ? <span><i className="mx-mark is-direct is-partial" aria-hidden="true" />Only in some versions</span> : null}
      </span>
      <span className="graph-toolbar-spacer" />
      <span className="mx-summary" data-ui-number="">{plural(matrix.rows.length, "model object")} · {plural(matrix.visuals.length, "visual")}{unused ? <> · <strong>{unused} unused</strong></> : null}</span>
      <Label className="mx-toggle"><Checkbox checked={hideUnused} onCheckedChange={(value) => setHideUnused(Boolean(value))} />Hide unused</Label>
    </div>
    {graph?.truncated ? <p className="mx-notice">Showing the first {graph.nodes.length} of {graph.total_nodes} objects. Choose a model or report in Filters to see all of it.</p> : null}
    <div className="mx-scroll">
      {hoverCol >= 0 ? <style>{`.impact-matrix [data-c="${hoverCol}"] { background: var(--surface-hover); }`}</style> : null}
      <table className="impact-matrix" onMouseLeave={() => setHoverCol(-1)} onMouseOver={(event) => { const c = event.target.closest?.("[data-c]")?.dataset.c; setHoverCol(c === undefined ? -1 : Number(c)); }}>
        <thead>
          <tr>
            <th className="mx-corner" rowSpan={headRows} scope="col"><span>Model objects</span><span className="mx-corner-x">Visuals →</span></th>
            {matrix.colGroups.map((group) => <th key={group.report.id} colSpan={reportSpan(group)} scope="colgroup" className="mx-report">
              <button type="button" className="mx-fold" aria-expanded={!fold.reports.has(group.report.id)} onClick={() => setFold("reports", group.report.id)} title={objectName(group.report)}>
                {fold.reports.has(group.report.id) ? <ChevronRight aria-hidden="true" /> : <ChevronDown aria-hidden="true" />}<TypeGlyph node={group.report} colors={colors} size="xs" /><span translate="no">{objectName(group.report)}</span><VersionBadge node={group.report} note={versionNote(group.report, rawById)} /><OriginBadge node={group.report} />
              </button>
            </th>)}
            <th className="mx-total-head" rowSpan={headRows} scope="col">Used by</th>
          </tr>
          {noPages ? null : <tr>
            {matrix.colGroups.flatMap((group) => fold.reports.has(group.report.id)
              ? [<th key={`${group.report.id}:all`} className="mx-page mx-page-folded" scope="col"><span className="mx-dim">{plural(group.pages.length, "page")}</span></th>]
              : group.pages.map(({ page, visuals }) => <th key={page.id} colSpan={fold.pages.has(page.id) ? 1 : visuals.length} scope="colgroup" className="mx-page">
                <button type="button" className="mx-fold" aria-expanded={!fold.pages.has(page.id)} onClick={() => setFold("pages", page.id)} title={objectName(page)}>
                  {fold.pages.has(page.id) ? <ChevronRight aria-hidden="true" /> : <ChevronDown aria-hidden="true" />}<span translate="no">{objectName(page)}</span>
                </button>
              </th>))}
          </tr>}
          <tr>
            {columns.map((column, index) => <th key={column.key} data-c={index} scope="col" className={`mx-col ${column.kind !== "visual" ? "is-folded" : ""} ${column.node.id === selectedId ? "is-selected" : ""}`}>
              {column.kind === "visual"
                ? <button type="button" className="mx-col-label" onClick={() => onSelect(column.node)} aria-label={`${typeLabel(column.node.type)} ${objectName(column.node)}`} title={objectName(column.node)}><TypeGlyph node={column.node} colors={colors} size="xs" /><span translate="no">{objectName(column.node)}</span><VersionBadge node={column.node} note={versionNote(column.node, rawById)} /></button>
                : <span className="mx-col-label mx-dim" title={`${column.ids.length} visuals`} data-ui-number="">{column.ids.length}</span>}
            </th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            if (row.kind === "model") return <tr key={`m:${row.key}`} className="mx-model-row">
              <th scope="rowgroup" colSpan={row.folded ? 1 : columns.length + 2}>
                <button type="button" className="mx-fold" aria-expanded={!row.folded} onClick={() => setFold("models", row.key)}>
                  {row.folded ? <ChevronRight aria-hidden="true" /> : <ChevronDown aria-hidden="true" />}<TypeGlyph node={row.node} colors={colors} size="xs" /><span translate="no">{objectName(row.node)}</span><VersionBadge node={row.node} note={versionNote(row.node, rawById)} /><OriginBadge node={row.node} /><span className="mx-dim" data-ui-number="">{row.count}</span>
                </button>
              </th>
              {row.folded ? <>{columns.map((column, index) => renderCell(row, column, index))}<td /></> : null}
            </tr>;
            if (row.kind === "table") return <tr key={`t:${row.key}`} className={`mx-table-row ${row.folded ? "is-folded" : ""}`}>
              <th scope="rowgroup">
                <button type="button" className="mx-fold" aria-expanded={!row.folded} onClick={() => setFold("tables", row.key)} title={objectName(row.node)}>
                  {row.folded ? <ChevronRight aria-hidden="true" /> : <ChevronDown aria-hidden="true" />}<TypeGlyph node={row.node} colors={colors} size="xs" /><span translate="no">{objectName(row.node)}</span><span className="mx-dim" data-ui-number="">{row.count}</span>
                </button>
              </th>
              {columns.map((column, index) => row.folded ? renderCell(row, column, index) : <td key={column.key} data-c={index} className="mx-band" />)}
              <td className="mx-band" />
            </tr>;
            const entry = matrix.usage.get(row.node.id);
            const total = entry.direct + entry.indirect;
            return <tr key={row.key} className={`mx-object-row ${total ? "" : "is-unused"} ${row.node.id === selectedId ? "is-selected" : ""}`}>
              <th scope="row">
                <button type="button" className="mx-row-label" onClick={() => onSelect(row.node)} aria-label={`${typeLabel(row.node.type)} ${objectName(row.node)}`} title={objectName(row.node)}>
                  <TypeGlyph node={row.node} colors={colors} size="xs" /><span translate="no">{objectName(row.node)}</span><VersionBadge node={row.node} note={versionNote(row.node, rawById)} />
                </button>
              </th>
              {columns.map((column, index) => renderCell(row, column, index))}
              <td className="mx-total" title={total ? `${entry.direct} direct, ${entry.indirect} through a calculation or filter` : "No visual uses this object"}>
                {total ? <><span className="mx-total-bar" style={{ "--share": total / matrix.visuals.length }} aria-hidden="true" /><span data-ui-number="">{total}</span></> : <span className="mx-unused">Unused</span>}
              </td>
            </tr>;
          })}
        </tbody>
      </table>
    </div>
  </div>;
}
