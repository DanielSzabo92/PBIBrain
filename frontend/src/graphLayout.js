import dagre from "@dagrejs/dagre";
import { ARTIFACT_GROUPS, artifactGroup } from "./graphPresentation.js";
import { objectName } from "./presentation.js";

export const NODE_WIDTH = 224;
export const NODE_HEIGHT = 88;

function idKey(value) {
  return value == null ? "" : String(value);
}

function compareText(left, right) {
  return String(left ?? "").localeCompare(String(right ?? ""), undefined, { numeric: true, sensitivity: "base" });
}

function compareNodes(left, right) {
  return compareText(objectName(left), objectName(right))
    || compareText(left?.type, right?.type)
    || compareText(idKey(left?.id), idKey(right?.id));
}

function compareEdges(left, right) {
  return compareText(idKey(left?.id), idKey(right?.id))
    || compareText(left?.type, right?.type)
    || compareText(idKey(left?.from_id), idKey(right?.from_id))
    || compareText(idKey(left?.to_id), idKey(right?.to_id));
}

function orderedNodes(nodes) {
  const byId = new Map();
  for (const node of [...(nodes || [])].filter(Boolean).sort(compareNodes)) {
    const id = idKey(node.id);
    if (id && !byId.has(id)) byId.set(id, node);
  }
  return [...byId.values()].sort(compareNodes);
}

function validEdges(edges, ids) {
  return [...(edges || [])]
    .filter((edge) => edge && ids.has(idKey(edge.from_id)) && ids.has(idKey(edge.to_id)))
    .sort(compareEdges);
}

function createsParentCycle(parent, child, parentOf) {
  const seen = new Set();
  let current = parent;
  while (current && !seen.has(current)) {
    if (current === child) return true;
    seen.add(current);
    current = parentOf.get(current);
  }
  return false;
}

// Pick one canonical CONTAINS owner per child for presentation. Facts remain
// untouched: the complete edge list is still returned for visible endpoints.
function presentationForest(nodes, edges) {
  const ids = new Set(nodes.map((node) => idKey(node.id)));
  const byId = new Map(nodes.map((node) => [idKey(node.id), node]));
  const candidates = validEdges(edges, ids)
    .filter((edge) => edge.type === "CONTAINS" && idKey(edge.from_id) !== idKey(edge.to_id))
    .sort((left, right) => {
      const childOrder = compareNodes(byId.get(idKey(left.to_id)), byId.get(idKey(right.to_id)));
      const parentOrder = compareNodes(byId.get(idKey(left.from_id)), byId.get(idKey(right.from_id)));
      return childOrder || parentOrder || compareEdges(left, right);
    });
  const parentOf = new Map();
  const edgeByChild = new Map();
  for (const edge of candidates) {
    const parent = idKey(edge.from_id);
    const child = idKey(edge.to_id);
    if (parentOf.has(child) || createsParentCycle(parent, child, parentOf)) continue;
    parentOf.set(child, parent);
    edgeByChild.set(child, edge);
  }
  const childrenById = new Map(nodes.map((node) => [idKey(node.id), []]));
  for (const [child, parent] of parentOf) childrenById.get(parent)?.push(child);
  for (const children of childrenById.values()) children.sort((left, right) => compareNodes(byId.get(left), byId.get(right)));
  return { parentOf, edgeByChild, childrenById };
}

function descendantCount(id, childrenById, memo) {
  if (memo.has(id)) return memo.get(id);
  const seen = new Set();
  const visit = (parent) => {
    for (const child of childrenById.get(parent) || []) {
      if (seen.has(child)) continue;
      seen.add(child);
      visit(child);
    }
  };
  visit(id);
  memo.set(id, seen.size);
  return seen.size;
}

function expansionSet(expandedIds, nodes) {
  if (expandedIds == null) return new Set(nodes.filter((node) => node.type === "MODEL").map((node) => idKey(node.id)));
  if (expandedIds instanceof Set) return new Set([...expandedIds].map(idKey));
  if (typeof expandedIds[Symbol.iterator] === "function") return new Set([...expandedIds].map(idKey));
  return new Set();
}

/**
 * Build the readable, progressively expanded graph view.
 *
 * CONTAINS edges define presentation ownership. Other edge types remain
 * factual relationships and are only filtered when an endpoint is hidden.
 */
export function buildExplorerGraph(nodes, edges, expandedIds = []) {
  const ordered = orderedNodes(nodes);
  if (!ordered.length) return { nodes: [], edges: [], childrenById: new Map(), hiddenCount: 0, collapsedCount: 0 };
  const forest = presentationForest(ordered, edges);
  const expanded = expansionSet(expandedIds, ordered);
  const roots = ordered.filter((node) => !forest.parentOf.has(idKey(node.id)));
  const visible = new Set();
  const visit = (id) => {
    if (visible.has(id)) return;
    visible.add(id);
    if (!expanded.has(id)) return;
    for (const child of forest.childrenById.get(id) || []) visit(child);
  };
  roots.forEach((node) => visit(idKey(node.id)));
  // Defensive fallback for malformed data; presentationForest normally makes
  // every connected component have a root even when source facts cycle.
  ordered.filter((node) => !forest.parentOf.has(idKey(node.id))).forEach((node) => visit(idKey(node.id)));

  const descendantMemo = new Map();
  const visibleNodes = ordered.filter((node) => visible.has(idKey(node.id))).map((node) => {
    const id = idKey(node.id);
    const children = forest.childrenById.get(id) || [];
    return {
      ...node,
      explorerParentId: forest.parentOf.get(id) ?? null,
      explorerChildCount: children.length,
      explorerDescendantCount: descendantCount(id, forest.childrenById, descendantMemo),
      explorerExpanded: expanded.has(id),
    };
  });
  const visibleEdges = validEdges(edges, new Set(visible));
  const collapsedCount = visibleNodes.filter((node) => node.explorerChildCount > 0 && !node.explorerExpanded).length;
  return {
    nodes: visibleNodes,
    edges: visibleEdges,
    childrenById: forest.childrenById,
    hiddenCount: ordered.length - visibleNodes.length,
    collapsedCount,
  };
}

// Reports use a model, but sit after that model in the containment hierarchy.
// Reverse only the layout constraint; the canonical arrow still points back.
function layoutEndpoints(edge) {
  return edge.type === "USES_MODEL" ? { v: edge.to_id, w: edge.from_id, name: edge.id } : { v: edge.from_id, w: edge.to_id, name: edge.id };
}
function edgePoints(graph, edge) {
  const points = graph.edge(layoutEndpoints(edge)).points;
  return edge.type === "USES_MODEL" ? [...points].reverse() : points;
}

// Stable ordering keeps refreshes predictable. Canonical edge direction is preserved,
// including cycles and parallel relationships; Dagre only chooses visual positions.
export function layoutGraph(nodes, edges, direction = "LR") {
  const graph = new dagre.graphlib.Graph({ multigraph: true });
  graph.setGraph({ rankdir: direction, ranksep: 56, nodesep: 24, edgesep: 16, marginx: 32, marginy: 32 });
  graph.setDefaultEdgeLabel(() => ({}));
  const ordered = [...nodes].sort((a, b) => a.id.localeCompare(b.id));
  const ids = new Set(ordered.map((node) => node.id));
  ordered.forEach((node) => graph.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT }));
  const validEdges = edges.filter((edge) => ids.has(edge.from_id) && ids.has(edge.to_id)).sort((a, b) => a.id.localeCompare(b.id));
  validEdges.forEach((edge) => graph.setEdge(layoutEndpoints(edge), { weight: edge.type === "CONTAINS" ? 4 : 1 }));
  if (ordered.length) dagre.layout(graph);
  return {
    nodes: ordered.map((node) => {
      const { x, y } = graph.node(node.id);
      return { node, position: { x: x - NODE_WIDTH / 2, y: y - NODE_HEIGHT / 2 } };
    }),
    edges: validEdges.map((edge) => ({ edge, points: edgePoints(graph, edge) })),
  };
}

export function routePath(points) {
  if (!points?.length) return "";
  // Round each bend while retaining the layout engine's obstacle-aware route.
  let path = `M ${points[0].x} ${points[0].y}`;
  for (let i = 1; i < points.length - 1; i += 1) {
    const previous = points[i - 1], point = points[i], next = points[i + 1];
    const incoming = Math.hypot(point.x - previous.x, point.y - previous.y);
    const outgoing = Math.hypot(next.x - point.x, next.y - point.y);
    const radius = Math.min(12, incoming / 2, outgoing / 2);
    if (!radius) continue;
    const start = { x: point.x + (previous.x - point.x) * radius / incoming, y: point.y + (previous.y - point.y) * radius / incoming };
    const end = { x: point.x + (next.x - point.x) * radius / outgoing, y: point.y + (next.y - point.y) * radius / outgoing };
    path += ` L ${start.x} ${start.y} Q ${point.x} ${point.y} ${end.x} ${end.y}`;
  }
  const last = points.at(-1);
  return `${path} L ${last.x} ${last.y}`;
}

// Compound Dagre groups reserve separate regions while routing the original
// cross-group relationships around objects. Presentation groups are not facts.
export function layoutArtifactGraph(nodes, edges, direction = "LR") {
  if (!nodes.length) return { nodes: [], edges: [], groups: [] };
  const graph = new dagre.graphlib.Graph({ multigraph: true, compound: true });
  graph.setGraph({ rankdir: direction, ranksep: 64, nodesep: 60, edgesep: 16, marginx: 40, marginy: 60 });
  graph.setDefaultEdgeLabel(() => ({}));
  const ordered = [...nodes].sort((a, b) => a.id.localeCompare(b.id));
  const ids = new Set(ordered.map((node) => node.id));
  const groups = Object.keys(ARTIFACT_GROUPS).filter((key) => ordered.some((node) => artifactGroup(node) === key));
  const groupIds = new Map();
  groups.forEach((key) => {
    let id = `__pbibrain_group_${key}`;
    while (ids.has(id)) id += "_";
    groupIds.set(key, id);
    graph.setNode(id, {});
  });
  ordered.forEach((node) => {
    graph.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
    graph.setParent(node.id, groupIds.get(artifactGroup(node)));
  });
  const validEdges = edges.filter((edge) => ids.has(edge.from_id) && ids.has(edge.to_id)).sort((a, b) => a.id.localeCompare(b.id));
  validEdges.forEach((edge) => graph.setEdge(layoutEndpoints(edge), { weight: edge.type === "CONTAINS" ? 4 : 1 }));
  dagre.layout(graph);
  return {
    nodes: ordered.map((node) => {
      const { x, y } = graph.node(node.id);
      return { node, position: { x: x - NODE_WIDTH / 2, y: y - NODE_HEIGHT / 2 } };
    }),
    edges: validEdges.map((edge) => ({ edge, points: edgePoints(graph, edge) })),
    groups: groups.map((key) => {
      const { x, y, width, height } = graph.node(groupIds.get(key));
      return { id: groupIds.get(key), key, position: { x: x - width / 2, y: y - height / 2 }, width, height, count: ordered.filter((node) => artifactGroup(node) === key).length };
    }),
  };
}

function endpointOnRect(rect, other, horizontalPreferred) {
  const dx = other.x - rect.x;
  const dy = other.y - rect.y;
  if (horizontalPreferred && Math.abs(dx) >= 1) {
    const side = dx >= 0 ? 1 : -1;
    return { x: rect.x + side * NODE_WIDTH / 2, y: rect.y };
  }
  if (!horizontalPreferred && Math.abs(dy) >= 1) {
    const side = dy >= 0 ? 1 : -1;
    return { x: rect.x, y: rect.y + side * NODE_HEIGHT / 2 };
  }
  if (Math.abs(dx) >= Math.abs(dy)) {
    const side = dx >= 0 ? 1 : -1;
    return { x: rect.x + side * NODE_WIDTH / 2, y: rect.y };
  }
  const side = dy >= 0 ? 1 : -1;
  return { x: rect.x, y: rect.y + side * NODE_HEIGHT / 2 };
}

function routeExplorerEdge(edge, positions, direction, offset = 0) {
  const source = positions.get(idKey(edge.from_id));
  const target = positions.get(idKey(edge.to_id));
  if (!source || !target) return [];
  if (source.id === target.id) {
    const horizontal = direction === "LR" || direction === "RL";
    const outward = direction === "RL" || direction === "BT" ? -1 : 1;
    if (horizontal) {
      const x = source.x + outward * NODE_WIDTH / 2;
      const outer = x + outward * (48 + Math.abs(offset));
      return [
        { x, y: source.y - NODE_HEIGHT * 0.2 },
        { x: outer, y: source.y - NODE_HEIGHT * 0.35 + offset },
        { x: outer, y: source.y + NODE_HEIGHT * 0.35 + offset },
        { x, y: source.y + NODE_HEIGHT * 0.2 },
      ];
    }
    const y = source.y + outward * NODE_HEIGHT / 2;
    const outer = y + outward * (48 + Math.abs(offset));
    return [
      { x: source.x - NODE_WIDTH * 0.2, y },
      { x: source.x - NODE_WIDTH * 0.35 + offset, y: outer },
      { x: source.x + NODE_WIDTH * 0.35 + offset, y: outer },
      { x: source.x + NODE_WIDTH * 0.2, y },
    ];
  }
  const dx = target.x - source.x;
  const dy = target.y - source.y;
  const horizontal = (direction === "LR" || direction === "RL") && Math.abs(dx) >= 1;
  const start = endpointOnRect(source, target, horizontal);
  const end = endpointOnRect(target, source, horizontal);
  if (horizontal) {
    const middleX = (start.x + end.x) / 2;
    return [start, { x: middleX, y: start.y + offset }, { x: middleX, y: end.y + offset }, end];
  }
  const middleY = (start.y + end.y) / 2;
  return [start, { x: start.x + offset, y: middleY }, { x: end.x + offset, y: middleY }, end];
}

function previousPositionMap(previousPositions) {
  if (!previousPositions) return new Map();
  const entries = previousPositions instanceof Map
    ? [...previousPositions.entries()]
    : Array.isArray(previousPositions)
      ? previousPositions.map((item) => [item?.node?.id ?? item?.id, item?.position ?? item])
      : Array.isArray(previousPositions.nodes)
        ? previousPositions.nodes.map((item) => [item?.node?.id ?? item?.id, item?.position ?? item])
        : [];
  return new Map(entries
    .map(([id, position]) => [idKey(id), position?.position ?? position])
    .filter(([id, position]) => id && Number.isFinite(position?.x) && Number.isFinite(position?.y))
    .map(([id, position]) => [id, { x: position.x, y: position.y }]));
}

function positionOverlap(left, right) {
  return Math.abs(left.x - right.x) < NODE_WIDTH && Math.abs(left.y - right.y) < NODE_HEIGHT;
}

function anchoredExplorerPositions(ordered, forest, rawPositions, previousPositions, direction) {
  const previous = previousPositionMap(previousPositions);
  const anchored = new Map(ordered
    .filter((node) => previous.has(idKey(node.id)))
    .map((node) => [idKey(node.id), previous.get(idKey(node.id))]));
  if (!anchored.size) return rawPositions;

  const horizontal = direction === "LR" || direction === "RL";
  const rankKey = horizontal ? "x" : "y";
  const laneKey = horizontal ? "y" : "x";
  const laneStep = horizontal ? NODE_HEIGHT + 36 : NODE_WIDTH + 36;
  const depthMemo = new Map();
  const depthOf = (id, path = new Set()) => {
    if (depthMemo.has(id)) return depthMemo.get(id);
    if (path.has(id)) return 0;
    const parent = forest.parentOf.get(id);
    if (!parent) {
      depthMemo.set(id, 0);
      return 0;
    }
    const nextPath = new Set(path);
    nextPath.add(id);
    const depth = depthOf(parent, nextPath) + 1;
    depthMemo.set(id, depth);
    return depth;
  };
  const fresh = ordered
    .filter((node) => !anchored.has(idKey(node.id)))
    .sort((left, right) => depthOf(idKey(left.id)) - depthOf(idKey(right.id)) || compareNodes(left, right));
  for (const node of fresh) {
    const id = idKey(node.id);
    const raw = rawPositions.get(id);
    if (!raw) continue;
    let rank = raw[rankKey];
    let lane = raw[laneKey];
    const parent = forest.parentOf.get(id);
    const rawParent = rawPositions.get(parent);
    const placedParent = anchored.get(parent);
    if (rawParent && placedParent) {
      lane = placedParent[laneKey] + raw[laneKey] - rawParent[laneKey];
    }
    let candidate = { x: horizontal ? rank : lane, y: horizontal ? lane : rank };
    let laneOffset = 0;
    while ([...anchored.values()].some((placed) => positionOverlap(candidate, placed))) {
      laneOffset += laneStep;
      const nextLane = lane + laneOffset;
      candidate = { x: horizontal ? rank : nextLane, y: horizontal ? nextLane : rank };
    }
    anchored.set(id, candidate);
  }
  return anchored;
}

/**
 * Lay out only the visible ownership forest. Dependency and evidence links
 * are routed after placement, so they cannot force ownership ranks apart.
 */
export function layoutExplorerGraph(nodes, edges, direction = "LR", previousPositions = null) {
  const ordered = orderedNodes(nodes);
  if (!ordered.length) return { nodes: [], edges: [] };
  const ids = new Set(ordered.map((node) => idKey(node.id)));
  const valid = validEdges(edges, ids);
  const forest = presentationForest(ordered, valid);
  const byId = new Map(ordered.map((node) => [idKey(node.id), node]));
  const graph = new dagre.graphlib.Graph({ multigraph: true });
  graph.setGraph({ rankdir: direction, ranksep: 72, nodesep: 36, edgesep: 24, marginx: 40, marginy: 40 });
  graph.setDefaultEdgeLabel(() => ({}));
  ordered.forEach((node) => graph.setNode(idKey(node.id), { width: NODE_WIDTH, height: NODE_HEIGHT }));
  for (const [child, parent] of forest.parentOf) {
    graph.setEdge({ v: parent, w: child, name: `explorer:${child}` }, { weight: 4, minlen: 1 });
  }
  // A report uses its model, but that relationship is not ownership. Keep
  // CONTAINS as the explorer forest and add this reversed layout constraint so
  // the model still precedes the report without rewriting the factual arrow.
  valid.filter((edge) => edge.type === "USES_MODEL"
    && byId.get(idKey(edge.from_id))?.type === "REPORT"
    && byId.get(idKey(edge.to_id))?.type === "MODEL")
    .forEach((edge) => {
      const endpoints = layoutEndpoints(edge);
      graph.setEdge({ ...endpoints, name: `explorer:scope:${idKey(edge.id)}:${idKey(edge.from_id)}:${idKey(edge.to_id)}` }, { weight: 3, minlen: 1 });
    });
  dagre.layout(graph);
  const rawLaidOut = ordered.map((node) => {
    const placed = graph.node(idKey(node.id));
    return {
      node,
      position: { x: placed.x - NODE_WIDTH / 2, y: placed.y - NODE_HEIGHT / 2 },
    };
  });
  const rawPositions = new Map(rawLaidOut.map(({ node, position }) => [idKey(node.id), position]));
  const finalPositions = anchoredExplorerPositions(ordered, forest, rawPositions, previousPositions, direction);
  const laidOut = ordered.map((node) => ({ node, position: finalPositions.get(idKey(node.id)) }));
  const positions = new Map(laidOut.map(({ node, position }) => [idKey(node.id), {
    id: idKey(node.id),
    x: position.x + NODE_WIDTH / 2,
    y: position.y + NODE_HEIGHT / 2,
  }]));
  const parallelOffsets = new Map();
  const byEndpoints = new Map();
  valid.forEach((edge) => {
    const key = `${idKey(edge.from_id)}\u0000${idKey(edge.to_id)}`;
    if (!byEndpoints.has(key)) byEndpoints.set(key, []);
    byEndpoints.get(key).push(edge);
  });
  for (const group of byEndpoints.values()) {
    group.forEach((edge, index) => parallelOffsets.set(edge, (index - (group.length - 1) / 2) * 16));
  }
  return {
    nodes: laidOut,
    edges: valid.map((edge) => ({ edge, points: routeExplorerEdge(edge, positions, direction, parallelOffsets.get(edge) || 0) })),
  };
}
