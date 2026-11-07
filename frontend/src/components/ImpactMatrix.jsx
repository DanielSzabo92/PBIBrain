import React, { useEffect, useMemo, useState } from "react";
import { ChevronDown, ChevronRight, TriangleAlert } from "lucide-react";
import { Button } from "./ui/button";
import { Checkbox } from "./ui/checkbox";
import { Label } from "./ui/label";
import { TypeGlyph } from "./TypeGlyph";
import { buildImpactMatrix } from "../matrix";
import { objectName } from "../presentation";
import { typeLabel } from "../graphPresentation";

const LIMIT = 1000;
// Large projects open with tables and pages folded, so the first view is a readable summary.
const FOLD_TABLES_ABOVE = 160;
const FOLD_PAGES_ABOVE = 48;

const toggle = (set, id) => { const next = new Set(set); if (next.has(id)) next.delete(id); else next.add(id); return next; };
const plural = (count, one, many = `${one}s`) => `${count} ${count === 1 ? one : many}`;

/**
 * Impact matrix (graph view "Matrix"): model objects down, report visuals across. Solid cells are direct use,
 * outlined cells are use through a calculation, hatched blocks are a report that is not bound to that model.
 * Folded groups show how many of their pairs are used, as a heat value.
 */
export default function ImpactMatrix({ transport, filters, query, colors, selectedId, onSelect }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [hideUnused, setHideUnused] = useState(false);
  const [folded, setFolded] = useState(null);
  const [hoverCol, setHoverCol] = useState(-1);
  const { modelId = "", reportId = "" } = filters || {};

  useEffect(() => {
    let active = true;
    setError("");
    transport.getGraph({ modelId, reportId, limit: LIMIT, status: "factual" })
      .then((graph) => { if (active) { setData(graph); setFolded(null); } })
      .catch((failure) => { if (active) setError(failure.message || "Matrix could not be loaded"); });
    return () => { active = false; };
  }, [transport, modelId, reportId]);

  const matrix = useMemo(() => data ? buildImpactMatrix(data.nodes || [], data.edges || []) : null, [data]);
  const fold = useMemo(() => folded || (matrix ? {
    tables: new Set(matrix.rows.length > FOLD_TABLES_ABOVE ? matrix.rowGroups.flatMap((group) => group.tables.map((table) => table.table.id)) : []),
    pages: new Set(matrix.visuals.length > FOLD_PAGES_ABOVE ? matrix.colGroups.flatMap((group) => group.pages.map((page) => page.page.id)) : []),
    models: new Set(), reports: new Set(),
  } : null), [folded, matrix]);
  const setFold = (key, id) => setFolded({ ...fold, [key]: toggle(fold[key], id) });

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
      const tableRows = tables.map(({ table, rows: members }) => {
        const shown = members.filter((node) => matches(node) && (!hideUnused || used(node.id)));
        return { table, members, shown };
      }).filter((entry) => entry.shown.length || (!needle && !hideUnused));
      if (!tableRows.length) return [];
      const head = { kind: "model", key: model.id, node: model, modelId: model.id, ids: tableRows.flatMap((entry) => entry.shown.map((node) => node.id)), count: tableRows.reduce((sum, entry) => sum + entry.shown.length, 0) };
      if (fold.models.has(model.id)) return [{ ...head, folded: true }];
      return [head, ...tableRows.flatMap(({ table, shown }) => fold.tables.has(table.id)
        ? [{ kind: "table", key: table.id, node: table, modelId: model.id, ids: shown.map((node) => node.id), count: shown.length, folded: true }]
        : [{ kind: "table", key: table.id, node: table, modelId: model.id, ids: shown.map((node) => node.id), count: shown.length, folded: false },
          ...shown.map((node) => ({ kind: "object", key: node.id, node, modelId: model.id, ids: [node.id] }))])];
    });
  }, [matrix, fold, hideUnused, needle]);

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

  if (error) return <div className="graph-empty" role="alert"><span className="empty-icon tone-bad" aria-hidden="true"><TriangleAlert /></span><h3>Matrix unavailable</h3><p>{error}</p></div>;
  if (!matrix) return <div className="graph-empty graph-loading" role="status"><p>Loading matrix…</p></div>;
  if (!matrix.rows.length || !matrix.visuals.length) {
    return <div className="graph-empty"><h3>Nothing to compare yet</h3><p>{!matrix.visuals.length ? "No report visuals are loaded. Scan a report that uses this model." : "No columns or calculations are loaded for this scope."}</p></div>;
  }

  const unused = matrix.rows.filter((node) => { const entry = matrix.usage.get(node.id); return entry.direct + entry.indirect === 0; }).length;
  const reportSpan = (group) => columns.filter((column) => column.reportId === group.report.id).length;
  const describe = (row, column, value) => {
    const rowName = objectName(row.node), colName = objectName(column.node);
    if (row.kind === "object" && column.kind === "visual") return value === 2 ? `${colName} uses ${rowName} directly` : value === 1 ? `${colName} uses ${rowName} through a calculation or a page/report filter` : `${colName} does not use ${rowName}`;
    return `${rowName} × ${colName}`;
  };

  const renderCell = (row, column, index) => {
    const off = !matrix.bound(row.modelId, column.reportId);
    const common = { key: column.key, "data-c": index };
    if (off) return <td {...common} className="mx-off" title={`${objectName(column.node)} is not bound to ${objectName(matrix.rowGroups.find((group) => group.model.id === row.modelId)?.model)}`} />;
    if (row.kind === "object" && column.kind === "visual") {
      const value = matrix.cell(row.node.id, column.node.id);
      return <td {...common} title={describe(row, column, value)}>{value ? <span className={`mx-mark ${value === 2 ? "is-direct" : "is-indirect"}`} aria-label={value === 2 ? "Direct" : "Indirect"} /> : null}</td>;
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
      </span>
      <span className="graph-toolbar-spacer" />
      <span className="mx-summary" data-ui-number="">{plural(matrix.rows.length, "model object")} · {plural(matrix.visuals.length, "visual")}{unused ? <> · <strong>{unused} unused</strong></> : null}</span>
      <Label className="mx-toggle"><Checkbox checked={hideUnused} onCheckedChange={(value) => setHideUnused(Boolean(value))} />Hide unused</Label>
    </div>
    {data?.truncated ? <p className="mx-notice">Showing the first {LIMIT} of {data.total_nodes} objects. Choose a model or report in Filters to see all of it.</p> : null}
    <div className="mx-scroll">
      {hoverCol >= 0 ? <style>{`.impact-matrix [data-c="${hoverCol}"] { background: var(--surface-hover); }`}</style> : null}
      <table className="impact-matrix" onMouseLeave={() => setHoverCol(-1)} onMouseOver={(event) => { const c = event.target.closest?.("[data-c]")?.dataset.c; setHoverCol(c === undefined ? -1 : Number(c)); }}>
        <thead>
          <tr>
            <th className="mx-corner" rowSpan={3} scope="col"><span>Model objects</span><span className="mx-corner-x">Visuals →</span></th>
            {matrix.colGroups.map((group) => <th key={group.report.id} colSpan={reportSpan(group)} scope="colgroup" className="mx-report">
              <button type="button" className="mx-fold" aria-expanded={!fold.reports.has(group.report.id)} onClick={() => setFold("reports", group.report.id)} title={objectName(group.report)}>
                {fold.reports.has(group.report.id) ? <ChevronRight aria-hidden="true" /> : <ChevronDown aria-hidden="true" />}<TypeGlyph node={group.report} colors={colors} size="xs" /><span translate="no">{objectName(group.report)}</span>
              </button>
            </th>)}
            <th className="mx-total-head" rowSpan={3} scope="col">Used by</th>
          </tr>
          <tr>
            {matrix.colGroups.flatMap((group) => fold.reports.has(group.report.id)
              ? [<th key={`${group.report.id}:all`} className="mx-page mx-page-folded" scope="col"><span className="mx-dim">{plural(group.pages.length, "page")}</span></th>]
              : group.pages.map(({ page, visuals }) => <th key={page.id} colSpan={fold.pages.has(page.id) ? 1 : visuals.length} scope="colgroup" className="mx-page">
                <button type="button" className="mx-fold" aria-expanded={!fold.pages.has(page.id)} onClick={() => setFold("pages", page.id)} title={objectName(page)}>
                  {fold.pages.has(page.id) ? <ChevronRight aria-hidden="true" /> : <ChevronDown aria-hidden="true" />}<span translate="no">{objectName(page)}</span>
                </button>
              </th>))}
          </tr>
          <tr>
            {columns.map((column, index) => <th key={column.key} data-c={index} scope="col" className={`mx-col ${column.kind !== "visual" ? "is-folded" : ""} ${column.node.id === selectedId ? "is-selected" : ""}`}>
              {column.kind === "visual"
                ? <button type="button" className="mx-col-label" onClick={() => onSelect(column.node)} aria-label={`${typeLabel(column.node.type)} ${objectName(column.node)}`} title={objectName(column.node)}><TypeGlyph node={column.node} colors={colors} size="xs" /><span translate="no">{objectName(column.node)}</span></button>
                : <span className="mx-col-label mx-dim" title={`${column.ids.length} visuals`} data-ui-number="">{column.ids.length}</span>}
            </th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            if (row.kind === "model") return <tr key={`m:${row.key}`} className="mx-model-row">
              <th scope="rowgroup" colSpan={row.folded ? 1 : columns.length + 2}>
                <button type="button" className="mx-fold" aria-expanded={!row.folded} onClick={() => setFold("models", row.key)}>
                  {row.folded ? <ChevronRight aria-hidden="true" /> : <ChevronDown aria-hidden="true" />}<TypeGlyph node={row.node} colors={colors} size="xs" /><span translate="no">{objectName(row.node)}</span><span className="mx-dim" data-ui-number="">{row.count}</span>
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
                  <TypeGlyph node={row.node} colors={colors} size="xs" /><span translate="no">{objectName(row.node)}</span>
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
