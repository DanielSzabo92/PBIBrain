// Lineage: the project read left to right, the way data flows into a report.
//
//   Model › Tables › Columns › Calculations (measures, field parameters, calculation groups, UDFs)
//   › Visuals › Visual filters › Pages › Page filters › Reports › Report filters
//
// Every object sits in the lane of its type; lanes with nothing in them are skipped. Within a lane, objects
// stay together with their owner (columns by table, visuals by page) and owners are ordered to follow the
// lane before them, so links run mostly straight. Pure functions: positions, lanes, flow-oriented edges.

import { NODE_WIDTH, NODE_HEIGHT } from "./graphLayout.js";
import { objectName } from "./presentation.js";

export const LANES = [
  { key: "model", label: "Models", types: ["MODEL", "WORKSPACE"] },
  { key: "table", label: "Tables", types: ["TABLE", "SHARED_EXPRESSION"] },
  { key: "column", label: "Columns", types: ["COLUMN", "RELATIONSHIP"] },
  { key: "calc", label: "Calculations", types: ["MEASURE", "FIELD_PARAMETER", "CALCULATION_GROUP", "CALCULATION_ITEM", "USER_DEFINED_FUNCTION"] },
  { key: "visual", label: "Visuals", types: ["VISUAL", "VISUAL_CALCULATION"] },
  { key: "visualFilter", label: "Visual filters", types: ["VISUAL_FILTER"] },
  { key: "page", label: "Pages", types: ["PAGE"] },
  { key: "pageFilter", label: "Page filters", types: ["PAGE_FILTER"] },
  { key: "report", label: "Reports", types: ["REPORT"] },
  { key: "reportFilter", label: "Report filters", types: ["REPORT_FILTER"] },
  { key: "meaning", label: "Meaning", types: [] },
];
const LANE_OF_TYPE = new Map(LANES.flatMap((lane, index) => lane.types.map((type) => [type, index])));
const MEANING_LANE = LANES.length - 1;

/** Lane index of a node type; anything unlisted (concepts, aliases, roles, selectors…) goes to "Meaning". */
export function laneOf(node) {
  return LANE_OF_TYPE.get(node?.type) ?? MEANING_LANE;
}

// Edges whose canonical direction is "dependent → dependency": data flows the other way.
const DEPENDENCY = new Set(["DEPENDS_ON", "REFERENCES", "USES", "USES_MODEL", "FILTERS", "MODIFIES_FILTER", "CONTROLLED_BY", "ACTIVATES_RELATIONSHIP", "MODIFIES_RELATIONSHIP"]);
const OWNERSHIP = new Set(["CONTAINS", "BELONGS_TO", "HAS_OPTION"]);

/**
 * The flow orientation of an edge: `{ from, to }` so that data runs from `from` into `to`.
 * Between lanes that is always left → right; inside one lane a dependency flows from what is used to its user.
 */
export function flowEnds(edge, laneById) {
  const a = laneById.get(edge.from_id);
  const b = laneById.get(edge.to_id);
  if (a !== undefined && b !== undefined && a !== b) return a < b ? { from: edge.from_id, to: edge.to_id } : { from: edge.to_id, to: edge.from_id };
  return DEPENDENCY.has(edge.type) ? { from: edge.to_id, to: edge.from_id } : { from: edge.from_id, to: edge.to_id };
}

const compareName = (left, right) => objectName(left).localeCompare(objectName(right), undefined, { numeric: true, sensitivity: "base" }) || left.id.localeCompare(right.id);

/**
 * Lay nodes out in lineage lanes.
 * @returns {{ nodes: {node, position, width, height}[], edges: {edge, from, to}[], lanes: {key,label,count,x,y,width}[] }}
 */
export function layoutLineage(nodes, edges, direction = "LR", { laneGap = 64, rowGap = 8, ownerGap = 16 } = {}) {
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const laneById = new Map(nodes.map((node) => [node.id, laneOf(node)]));
  const valid = edges.filter((edge) => byId.has(edge.from_id) && byId.has(edge.to_id) && edge.from_id !== edge.to_id);

  // Owner of each object (table for a column, page for a visual…), from ownership edges.
  const owner = new Map();
  valid.forEach((edge) => {
    if (!OWNERSHIP.has(edge.type)) return;
    const [parent, child] = edge.type === "BELONGS_TO" ? [edge.to_id, edge.from_id] : [edge.from_id, edge.to_id];
    if (!owner.has(child)) owner.set(child, parent);
  });
  const ownerKey = (node) => owner.get(node.id) || node.table_id || node.properties?.table_id || node.page_id || node.report_id || node.model_id || "";
  // The model or report an object belongs to: lanes keep each model's (and each report's) objects in one block.
  const rootOf = (node) => {
    let current = node.id, guard = 0;
    while (guard++ < 8) {
      const type = byId.get(current)?.type;
      if (type === "MODEL" || type === "REPORT") return current;
      const next = owner.get(current);
      if (!next) break;
      current = next;
    }
    return node.model_id || node.report_id || "";
  };
  const roots = new Map(nodes.map((node) => [node.id, rootOf(node)]));

  // Neighbours along flow, for the ordering sweeps.
  const neighbours = new Map(nodes.map((node) => [node.id, []]));
  valid.forEach((edge) => { neighbours.get(edge.from_id).push(edge.to_id); neighbours.get(edge.to_id).push(edge.from_id); });

  const laneNodes = LANES.map(() => []);
  nodes.forEach((node) => laneNodes[laneById.get(node.id)].push(node));
  const used = laneNodes.map((list, index) => (list.length ? index : -1)).filter((index) => index >= 0);

  // Initial order: by owner name, then by name.
  const order = new Map();
  used.forEach((lane) => {
    laneNodes[lane].sort((left, right) => {
      const lo = byId.get(ownerKey(left)), ro = byId.get(ownerKey(right));
      return (lo && ro ? compareName(lo, ro) : String(ownerKey(left)).localeCompare(String(ownerKey(right)))) || compareName(left, right);
    });
    laneNodes[lane].forEach((node, index) => order.set(node.id, index));
  });

  // Barycentre sweeps: order owners, then members, by the mean position of their neighbours in other lanes.
  const sweep = (lanes) => lanes.forEach((lane) => {
    const list = laneNodes[lane];
    const centre = (node) => {
      const others = neighbours.get(node.id).filter((id) => laneById.get(id) !== lane);
      if (!others.length) return order.get(node.id);
      return others.reduce((sum, id) => sum + order.get(id) / Math.max(1, laneNodes[laneById.get(id)].length), 0) / others.length * list.length;
    };
    const groups = new Map();
    list.forEach((node) => { const key = ownerKey(node); if (!groups.has(key)) groups.set(key, []); groups.get(key).push(node); });
    const scored = [...groups.values()].map((members) => ({ members: members.map((node) => ({ node, c: centre(node) })), }));
    scored.forEach((group) => { group.c = group.members.reduce((sum, item) => sum + item.c, 0) / group.members.length; });
    const rootRank = (group) => { const root = roots.get(group.members[0].node.id); return order.has(root) ? order.get(root) / Math.max(1, laneNodes[laneById.get(root)].length) : 0; };
    scored.forEach((group) => { group.r = rootRank(group); });
    scored.sort((a, b) => a.r - b.r || a.c - b.c);
    const next = scored.flatMap((group) => group.members.sort((a, b) => a.c - b.c || compareName(a.node, b.node)).map((item) => item.node));
    laneNodes[lane] = next;
    next.forEach((node, index) => order.set(node.id, index));
  });
  for (let pass = 0; pass < 3; pass += 1) { sweep(used.slice(1)); sweep([...used].reverse().slice(1)); }

  // Positions: each lane is a column (LR) or a row (TB), top-aligned under one row of lane headers, with a small gap between owners.
  const horizontal = direction !== "TB";
  const along = horizontal ? NODE_HEIGHT : NODE_WIDTH;
  const extents = used.map((lane) => {
    let size = 0, previous = null;
    laneNodes[lane].forEach((node, index) => { const key = ownerKey(node); size += (index ? rowGap : 0) + (index && key !== previous ? ownerGap : 0) + along; previous = key; });
    return size;
  });
  const tallest = Math.max(0, ...extents);
  const placed = [];
  const lanes = [];
  used.forEach((lane, column) => {
    const cross = column * ((horizontal ? NODE_WIDTH : NODE_HEIGHT) + laneGap);
    let cursor = 0, previous = null;
    laneNodes[lane].forEach((node, index) => {
      const key = ownerKey(node);
      if (index) cursor += rowGap + (key !== previous ? ownerGap : 0);
      previous = key;
      placed.push({ node, position: horizontal ? { x: cross, y: cursor } : { x: cursor, y: cross }, width: NODE_WIDTH, height: NODE_HEIGHT });
      cursor += along;
    });
    lanes.push({ key: LANES[lane].key, label: LANES[lane].label, count: laneNodes[lane].length, index: lane, x: horizontal ? cross : -NODE_WIDTH - 40, y: horizontal ? -40 : cross, width: horizontal ? NODE_WIDTH : NODE_WIDTH });
  });

  return {
    nodes: placed,
    edges: valid.map((edge) => ({ edge, ...flowEnds(edge, laneById) })),
    lanes,
  };
}

/**
 * Everything upstream (feeds into) and downstream (is fed by) of one object, following flow-oriented edges
 * transitively. Upstream follows only incoming flow and downstream only outgoing flow, so selecting a
 * column lights its table and model, the measures and visuals it feeds, but never its sibling columns.
 */
export function lineageOf(id, flowEdges) {
  const into = new Map(), out = new Map();
  flowEdges.forEach(({ edge, from, to }) => {
    // Only real data flow: "observed with", semantic and similarity links are context, not lineage.
    if (!DEPENDENCY.has(edge.type) && !OWNERSHIP.has(edge.type)) return;
    if (!into.has(to)) into.set(to, []);
    if (!out.has(from)) out.set(from, []);
    into.get(to).push({ id: from, edge });
    out.get(from).push({ id: to, edge });
  });
  const walk = (start, links) => {
    const seen = new Set([start]);
    const edgeIds = new Set();
    const queue = [start];
    while (queue.length) {
      const current = queue.shift();
      (links.get(current) || []).forEach(({ id: next, edge }) => {
        edgeIds.add(edge.id);
        if (!seen.has(next)) { seen.add(next); queue.push(next); }
      });
    }
    return { ids: seen, edgeIds };
  };
  const up = walk(id, into);
  const down = walk(id, out);
  return { ids: new Set([...up.ids, ...down.ids]), edgeIds: new Set([...up.edgeIds, ...down.edgeIds]), upstream: up.ids, downstream: down.ids };
}
