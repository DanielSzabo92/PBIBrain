// Lineage: the project read left to right, the way data flows into a report.
//
//   Model › Sources › Queries › Tables › Columns › Calculations (measures, field parameters, calculation groups, UDFs)
//   › Visuals › Visual filters › Pages › Page filters › Reports › Report filters
//
// Every object sits in the lane of its type; lanes with nothing in them are skipped. Within a lane, objects
// stay together with their owner (columns by table, visuals by page) and owners are ordered to follow the
// lane before them, so links run mostly straight. Pure functions: positions, lanes, flow-oriented edges.

import { NODE_WIDTH, NODE_HEIGHT } from "./graphLayout.js";
import { objectName } from "./presentation.js";

export const LANES = [
  { key: "model", label: "Models", types: ["MODEL", "WORKSPACE"] },
  // Issue #10: data sources and the Power Query that reads them (partitions, shared expressions) feed the tables.
  // They sit after Models, so "model contains shared expression" still flows left to right and a model does
  // not pass the sources of its shared expressions on to every table.
  { key: "source", label: "Sources", types: ["DATA_SOURCE"] },
  { key: "query", label: "Queries", types: ["PARTITION", "SHARED_EXPRESSION"] },
  { key: "table", label: "Tables", types: ["TABLE"] },
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
const DEPENDENCY = new Set(["SOURCES_FROM", "DEPENDS_ON", "REFERENCES", "USES", "USES_MODEL", "FILTERS", "MODIFIES_FILTER", "CONTROLLED_BY", "ACTIVATES_RELATIONSHIP", "MODIFIES_RELATIONSHIP"]);
const OWNERSHIP = new Set(["CONTAINS", "BELONGS_TO", "HAS_OPTION"]);
/** A link drawn across lanes that are switched off: it stands for a chain through hidden objects. */
export const THROUGH = "THROUGH_HIDDEN";
const LINEAGE_LINKS = new Set([...DEPENDENCY, ...OWNERSHIP, THROUGH]);

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

// One shared collator: localeCompare with options builds a new one on every call.
const NAME_ORDER = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });
const compareName = (left, right) => NAME_ORDER.compare(objectName(left), objectName(right)) || left.id.localeCompare(right.id);

// Lane widths follow their longest name (LR): never narrower than a node, never wider than MAX_LANE_WIDTH.
// A name that still does not fit wraps to a second line (TWO_LINE_HEIGHT) before it is shortened.
export const MAX_LANE_WIDTH = 280;
export const TWO_LINE_HEIGHT = 48;
// Node chrome around the name (app.css .flow-node): border, padding, type chip and gaps, room for a badge.
const NAME_CHROME = 2 + 3 + 24 + 8 + 10;
const ZOOM_SLACK = 1.3;
const estimate = (text) => String(text).length * 7;

/**
 * Lay nodes out in lineage lanes.
 * `measure(text)` gives the rendered width of a name; lanes widen to fit names and long names take two lines.
 * @returns {{ nodes: {node, position, width, height, lines}[], edges: {edge, from, to}[], lanes: {key,label,count,x,y,width}[] }}
 */
export function layoutLineage(nodes, edges, direction = "LR", { laneGap = 64, rowGap = 8, ownerGap = 16, measure = estimate, badge = () => 0 } = {}) {
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

  // Sizes: a lane is as wide as its longest name allows (LR); names beyond that wrap to two lines.
  const horizontal = direction !== "TB";
  const widths = new Map(), lines = new Map();
  used.forEach((lane) => {
    const need = (node) => measure(objectName(node)) + badge(node);
    const longest = Math.max(0, ...laneNodes[lane].map(need));
    // Slack: names are counter-scaled to stay readable when zoomed out, so they need more room than at 100%.
    const width = horizontal ? Math.min(MAX_LANE_WIDTH, Math.max(NODE_WIDTH, Math.ceil(longest * ZOOM_SLACK + NAME_CHROME))) : NODE_WIDTH;
    widths.set(lane, width);
    laneNodes[lane].forEach((node) => lines.set(node.id, need(node) > width - NAME_CHROME ? 2 : 1));
  });
  const heightOf = (node) => (lines.get(node.id) === 2 ? TWO_LINE_HEIGHT : NODE_HEIGHT);
  const laneHeight = (lane) => Math.max(NODE_HEIGHT, ...laneNodes[lane].map(heightOf));

  // Positions: each lane is a column (LR) or a row (TB), top-aligned under one row of lane headers, with a small gap between owners.
  const placed = [];
  const lanes = [];
  let cross = 0;
  used.forEach((lane) => {
    const width = widths.get(lane);
    let cursor = 0, previous = null;
    laneNodes[lane].forEach((node, index) => {
      const key = ownerKey(node);
      if (index) cursor += rowGap + (key !== previous ? ownerGap : 0);
      previous = key;
      const height = horizontal ? heightOf(node) : laneHeight(lane);
      placed.push({ node, position: horizontal ? { x: cross, y: cursor } : { x: cursor, y: cross }, width, height, lines: lines.get(node.id) });
      cursor += horizontal ? height : width;
    });
    lanes.push({ key: LANES[lane].key, label: LANES[lane].label, count: laneNodes[lane].reduce((sum, node) => sum + (node.foldCount || 1), 0), index: lane, x: horizontal ? cross : -NODE_WIDTH - 40, y: horizontal ? -40 : cross, width: horizontal ? width : NODE_WIDTH });
    cross += (horizontal ? width : laneHeight(lane)) + laneGap;
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
    if (!LINEAGE_LINKS.has(edge.type)) return;
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

// Cap on the links drawn across hidden lanes, so switching off a busy lane never builds a hairball.
const MAX_THROUGH_LINKS = 20000;

/**
 * Switch lanes off without breaking the chains that run through them: objects in `hiddenLanes` (lane keys)
 * leave the picture, and every chain that passed through them becomes one THROUGH link from the last shown
 * object before them to the first shown object after them. With Columns off, a table links straight to the
 * measures and visuals that use its columns.
 */
export function hideLanes(nodes, edges, hiddenLanes) {
  const hidden = new Set(hiddenLanes || []);
  if (!hidden.size) return { nodes, edges };
  const laneById = new Map(nodes.map((node) => [node.id, laneOf(node)]));
  const isHidden = (id) => hidden.has(LANES[laneById.get(id)]?.key);
  const shownNodes = nodes.filter((node) => !isHidden(node.id));
  const out = new Map();
  edges.forEach((edge) => {
    if (!laneById.has(edge.from_id) || !laneById.has(edge.to_id) || !LINEAGE_LINKS.has(edge.type)) return;
    const { from, to } = flowEnds(edge, laneById);
    if (!out.has(from)) out.set(from, []);
    out.get(from).push(to);
  });
  const kept = edges.filter((edge) => laneById.has(edge.from_id) && laneById.has(edge.to_id) && !isHidden(edge.from_id) && !isHidden(edge.to_id));
  const direct = new Set(kept.map((edge) => { const { from, to } = flowEnds(edge, laneById); return `${from}\u0000${to}`; }));
  const through = [];
  for (const node of shownNodes) {
    // Walk forward through hidden objects only; every shown object reached that way gets one link.
    const starts = (out.get(node.id) || []).filter(isHidden);
    if (!starts.length) continue;
    const seen = new Set(starts), queue = [...starts], reached = new Set();
    while (queue.length) {
      const current = queue.pop();
      (out.get(current) || []).forEach((next) => {
        if (next === node.id) return;
        if (!isHidden(next)) { reached.add(next); return; }
        if (!seen.has(next)) { seen.add(next); queue.push(next); }
      });
    }
    for (const target of reached) {
      const key = `${node.id}\u0000${target}`;
      if (direct.has(key)) continue;
      direct.add(key);
      through.push({ id: `through:${node.id}>${target}`, type: THROUGH, from_id: node.id, to_id: target, status: "factual", evidence_class: "FACT" });
      if (through.length >= MAX_THROUGH_LINKS) return { nodes: shownNodes, edges: [...kept, ...through], capped: true };
    }
  }
  return { nodes: shownNodes, edges: [...kept, ...through] };
}

// Folding (large pictures): a lane of thousands of rows is unreadable, so above FOLD_ABOVE objects a long
// lane shows one row per owner ("Orders · 18 columns") and the links between rows are counted.
export const FOLD_ABOVE = 400;
const FOLD_LANE_ABOVE = 40;
const FOLD_ROWS_MAX = 60;
const NEVER_FOLDED = new Set(["model", "report"]);

/**
 * Fold the long lanes of a large lineage by owner. `unfolded` lists the fold ids the person opened.
 * Returns null when nothing folds, else `{ nodes, edges, folded }` where a fold is a node
 * `{ id: "fold:<lane>:<owner>", fold: true, foldCount, foldOwnerId, type, name }` and a link that stands
 * for several is `{ bundle: true, count }`.
 */
export function foldLineage(nodes, edges, unfolded = []) {
  if (nodes.length <= FOLD_ABOVE) return null;
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const owner = new Map();
  edges.forEach((edge) => {
    if (!OWNERSHIP.has(edge.type) || !byId.has(edge.from_id) || !byId.has(edge.to_id)) return;
    const [parent, child] = edge.type === "BELONGS_TO" ? [edge.to_id, edge.from_id] : [edge.from_id, edge.to_id];
    if (!owner.has(child)) owner.set(child, parent);
  });
  const rootOf = (id) => {
    let current = id, guard = 0;
    while (owner.has(current) && guard++ < 8) current = owner.get(current);
    return current === id ? "" : current;
  };
  const open = new Set(unfolded || []);
  const lanes = LANES.map(() => []);
  nodes.forEach((node) => lanes[laneOf(node)].push(node));
  const foldOf = new Map();
  const folds = [];
  lanes.forEach((list, index) => {
    const lane = LANES[index].key;
    if (list.length <= FOLD_LANE_ABOVE || NEVER_FOLDED.has(lane)) return;
    const groupBy = (keyOf) => {
      const groups = new Map();
      list.forEach((node) => { const key = keyOf(node); if (!groups.has(key)) groups.set(key, []); groups.get(key).push(node); });
      return groups;
    };
    let groups = groupBy((node) => owner.get(node.id) || "");
    // Still too many rows (a visual per page of every report): fold by the model or report instead.
    if (groups.size > FOLD_ROWS_MAX) groups = groupBy((node) => rootOf(node.id));
    groups.forEach((members, ownerId) => {
      if (!ownerId || members.length < 2) return;
      const id = `fold:${lane}:${ownerId}`;
      if (open.has(id)) return;
      const first = members[0];
      folds.push({ id, type: first.type, name: objectName(byId.get(ownerId)), status: "factual", fold: true, foldCount: members.length, foldOwnerId: ownerId, foldLane: lane, model_id: first.model_id, report_id: first.report_id });
      members.forEach((node) => foldOf.set(node.id, id));
    });
  });
  if (!folds.length) return null;
  const end = (id) => foldOf.get(id) || id;
  const kept = [];
  const counted = new Map();
  edges.forEach((edge) => {
    const from = end(edge.from_id), to = end(edge.to_id);
    if (from === edge.from_id && to === edge.to_id) { kept.push(edge); return; }
    if (from === to) return;
    const ownership = OWNERSHIP.has(edge.type);
    const key = `${ownership ? "own" : "use"}\u0000${from}\u0000${to}`;
    const bundle = counted.get(key);
    if (bundle) bundle.count += 1;
    else counted.set(key, { id: `fold-link:${edge.type}:${from}>${to}`, type: edge.type, from_id: from, to_id: to, status: "factual", evidence_class: "FACT", bundle: !ownership, count: 1 });
  });
  // A fold keeps its place under its owner even when the owner's own row is folded too.
  folds.forEach((fold) => {
    const parent = end(fold.foldOwnerId);
    const key = `own\u0000${parent}\u0000${fold.id}`;
    if (byId.has(fold.foldOwnerId) && !counted.has(key)) counted.set(key, { id: `fold-link:CONTAINS:${parent}>${fold.id}`, type: "CONTAINS", from_id: parent, to_id: fold.id, status: "factual", evidence_class: "FACT", count: 1 });
  });
  return { nodes: [...nodes.filter((node) => !foldOf.has(node.id)), ...folds], edges: [...kept, ...counted.values()], folded: foldOf.size };
}
