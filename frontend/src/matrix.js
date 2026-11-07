// Impact matrix: model objects (rows) against report visuals (columns).
//
// A cell says whether a visual uses a model object directly (bound to a field well, a visual filter…) or
// indirectly (through a measure, field parameter or calculation that depends on it). Rows are grouped by
// model › table and columns by report › page, so several models and reports read as blocks: a block of a
// model against a report that is not bound to it cannot have usage and is shown as not connected.

import { flowEnds, laneOf, LANES } from "./lineage.js";
import { objectName, workspaceKey } from "./presentation.js";

const ROW_LANES = new Set(LANES.flatMap((lane, index) => (lane.key === "column" || lane.key === "calc" ? [index] : [])));
const VISUAL_LANE = LANES.findIndex((lane) => lane.key === "visual");
const FLOW = new Set(["DEPENDS_ON", "REFERENCES", "USES", "FILTERS", "MODIFIES_FILTER", "CONTROLLED_BY", "HAS_OPTION"]);
const OWNERSHIP = new Set(["CONTAINS", "BELONGS_TO"]);
const FILTER_TYPES = new Set(["PAGE_FILTER", "REPORT_FILTER"]);

// Local roots first, then each cloud workspace as one block (issue #9).
const byWorkspace = (left, right) => workspaceKey(left).localeCompare(workspaceKey(right), undefined, { sensitivity: "base" });
const byName = (left, right) => objectName(left).localeCompare(objectName(right), undefined, { numeric: true, sensitivity: "base" }) || left.id.localeCompare(right.id);

function owners(nodes, edges) {
  const owner = new Map();
  edges.forEach((edge) => {
    if (!OWNERSHIP.has(edge.type)) return;
    const [parent, child] = edge.type === "BELONGS_TO" ? [edge.to_id, edge.from_id] : [edge.from_id, edge.to_id];
    if (!owner.has(child)) owner.set(child, parent);
  });
  return owner;
}

/** Walk owners up until a node of one of `types` is found. */
function ancestor(id, types, owner, byId) {
  let current = owner.get(id), guard = 0;
  while (current && guard++ < 8) {
    if (types.includes(byId.get(current)?.type)) return current;
    current = owner.get(current);
  }
  return "";
}

/**
 * @returns {{
 *   rowGroups: { model, tables: { table, rows: node[] }[] }[],
 *   colGroups: { report, pages: { page, visuals: node[] }[] }[],
 *   cell: (rowId, visualId) => 0 | 1 | 2,
 *   usage: Map<rowId, { direct: number, indirect: number }>,
 *   bound: (modelId, reportId) => boolean,
 *   rows: node[], visuals: node[],
 *   modelOf: (node) => modelId, reportOf: (node) => reportId,
 * }}
 * Options switch off what filters count: visual filters (direct use), page and report filters (indirect use).
 */
export function buildImpactMatrix(nodes, edges, { visualFilters = true, pageFilters = true, reportFilters = true } = {}) {
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const valid = edges.filter((edge) => byId.has(edge.from_id) && byId.has(edge.to_id));
  const owner = owners(nodes, valid);
  const laneById = new Map(nodes.map((node) => [node.id, laneOf(node)]));

  // Upstream adjacency along data flow, dependency links only.
  const feeders = new Map();
  valid.forEach((edge) => {
    if (!FLOW.has(edge.type)) return;
    const { from, to } = flowEnds(edge, laneById);
    if (!feeders.has(to)) feeders.set(to, new Set());
    feeders.get(to).add(from);
  });

  const reportOf = (node) => node.report_id || ancestor(node.id, ["REPORT"], owner, byId);
  const pageOf = (node) => node.page_id || node.properties?.page_id || ancestor(node.id, ["PAGE"], owner, byId);
  const children = new Map();
  owner.forEach((parent, child) => { if (!children.has(parent)) children.set(parent, []); children.get(parent).push(child); });

  const rows = nodes.filter((node) => ROW_LANES.has(laneById.get(node.id)));
  const visuals = nodes.filter((node) => laneById.get(node.id) === VISUAL_LANE);
  const rowIds = new Set(rows.map((node) => node.id));

  // Per visual: model objects it reaches directly, and through dependencies.
  const cells = new Map();
  const usage = new Map(rows.map((node) => [node.id, { direct: 0, indirect: 0 }]));
  visuals.forEach((visual) => {
    const marks = new Map();
    const direct = [...(feeders.get(visual.id) || [])];
    // A visual filter or visual calculation of this visual counts as the visual using what it uses.
    (children.get(visual.id) || []).forEach((child) => {
      if (!visualFilters && byId.get(child)?.type === "VISUAL_FILTER") return;
      direct.push(...(feeders.get(child) || []));
    });
    direct.forEach((id) => { if (rowIds.has(id)) marks.set(id, 2); });
    // Page and report filters act on every visual below them: what they use counts as indirect use.
    const filtering = [pageFilters ? pageOf(visual) : "", reportFilters ? reportOf(visual) : ""].filter(Boolean).flatMap((scope) => (children.get(scope) || []).filter((child) => FILTER_TYPES.has(byId.get(child)?.type)));
    const viaFilters = filtering.flatMap((filter) => [...(feeders.get(filter) || [])]);
    const queue = [...direct, ...viaFilters], seen = new Set(queue);
    viaFilters.forEach((id) => { if (rowIds.has(id) && !marks.has(id)) marks.set(id, 1); });
    while (queue.length) {
      const current = queue.shift();
      (feeders.get(current) || new Set()).forEach((next) => {
        if (seen.has(next)) return;
        seen.add(next); queue.push(next);
        if (rowIds.has(next) && !marks.has(next)) marks.set(next, 1);
      });
    }
    marks.forEach((value, id) => { const entry = usage.get(id); if (value === 2) entry.direct += 1; else entry.indirect += 1; });
    cells.set(visual.id, marks);
  });

  // Row groups: model › table.
  const modelOf = (node) => node.model_id || ancestor(node.id, ["MODEL"], owner, byId);
  const tableOf = (node) => node.properties?.table_id || node.table_id || ancestor(node.id, ["TABLE", "CALCULATION_GROUP"], owner, byId);
  const rowTree = new Map();
  rows.forEach((node) => {
    const model = modelOf(node), table = tableOf(node);
    if (!rowTree.has(model)) rowTree.set(model, new Map());
    const tables = rowTree.get(model);
    if (!tables.has(table)) tables.set(table, []);
    tables.get(table).push(node);
  });
  const nodeOrStub = (id, type, fallback) => byId.get(id) || { id: id || `none:${type}`, type, name: fallback };
  const rowGroups = [...rowTree].map(([model, tables]) => ({
    model: nodeOrStub(model, "MODEL", "Model"),
    tables: [...tables].map(([table, list]) => ({ table: nodeOrStub(table, "TABLE", "Model-level objects"), rows: list.sort((a, b) => (a.type === b.type ? 0 : a.type === "COLUMN" ? -1 : b.type === "COLUMN" ? 1 : a.type.localeCompare(b.type)) || byName(a, b)) })).sort((a, b) => byName(a.table, b.table)),
  })).sort((a, b) => byWorkspace(a.model, b.model) || byName(a.model, b.model));

  // Column groups: report › page.
  const colTree = new Map();
  visuals.forEach((node) => {
    const report = reportOf(node), page = pageOf(node);
    if (!colTree.has(report)) colTree.set(report, new Map());
    const pages = colTree.get(report);
    if (!pages.has(page)) pages.set(page, []);
    pages.get(page).push(node);
  });
  const colGroups = [...colTree].map(([report, pages]) => ({
    report: nodeOrStub(report, "REPORT", "Report"),
    pages: [...pages].map(([page, list]) => ({ page: nodeOrStub(page, "PAGE", "Page"), visuals: list.sort(byName) })).sort((a, b) => byName(a.page, b.page)),
  })).sort((a, b) => byWorkspace(a.report, b.report) || byName(a.report, b.report));

  // Which models each report is bound to (USES_MODEL). Unknown bindings count as bound, so nothing is hidden.
  const bindings = new Map();
  valid.forEach((edge) => {
    if (edge.type !== "USES_MODEL") return;
    const [report, model] = byId.get(edge.from_id)?.type === "REPORT" ? [edge.from_id, edge.to_id] : [edge.to_id, edge.from_id];
    if (!bindings.has(report)) bindings.set(report, new Set());
    bindings.get(report).add(model);
  });
  const bound = (modelId, reportId) => !bindings.has(reportId) || bindings.get(reportId).has(modelId);

  // Reports follow the order of the model they are bound to, so model/report blocks run down the diagonal.
  const modelRank = new Map(rowGroups.map((group, index) => [group.model.id, index]));
  const reportRank = (group) => Math.min(rowGroups.length, ...[...(bindings.get(group.report.id) || [])].map((id) => modelRank.get(id) ?? rowGroups.length));
  colGroups.sort((a, b) => reportRank(a) - reportRank(b) || byWorkspace(a.report, b.report) || byName(a.report, b.report));

  return {
    rowGroups, colGroups, rows, visuals, usage, bound, modelOf, reportOf,
    cell: (rowId, visualId) => cells.get(visualId)?.get(rowId) || 0,
  };
}
