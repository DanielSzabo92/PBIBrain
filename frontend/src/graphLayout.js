import dagre from "@dagrejs/dagre";
import { ARTIFACT_GROUPS, artifactGroup } from "./graphPresentation.js";

export const NODE_WIDTH = 224;
export const NODE_HEIGHT = 84;

// Stable ordering keeps refreshes predictable. Canonical edge direction is preserved,
// including cycles and parallel relationships; Dagre only chooses visual positions.
export function layoutGraph(nodes, edges, direction = "LR") {
  const graph = new dagre.graphlib.Graph({ multigraph: true });
  graph.setGraph({ rankdir: direction, ranksep: 100, nodesep: 36, edgesep: 20, marginx: 32, marginy: 32 });
  graph.setDefaultEdgeLabel(() => ({}));
  const ordered = [...nodes].sort((a, b) => a.id.localeCompare(b.id));
  const ids = new Set(ordered.map((node) => node.id));
  ordered.forEach((node) => graph.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT }));
  const validEdges = edges.filter((edge) => ids.has(edge.from_id) && ids.has(edge.to_id)).sort((a, b) => a.id.localeCompare(b.id));
  validEdges.forEach((edge) => graph.setEdge(edge.from_id, edge.to_id, {}, edge.id));
  if (ordered.length) dagre.layout(graph);
  return {
    nodes: ordered.map((node) => {
      const { x, y } = graph.node(node.id);
      return { node, position: { x: x - NODE_WIDTH / 2, y: y - NODE_HEIGHT / 2 } };
    }),
    edges: validEdges.map((edge) => ({ edge, points: graph.edge({ v: edge.from_id, w: edge.to_id, name: edge.id }).points })),
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
  graph.setGraph({ rankdir: direction, ranksep: 100, nodesep: 72, edgesep: 24, marginx: 40, marginy: 60 });
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
  validEdges.forEach((edge) => graph.setEdge(edge.from_id, edge.to_id, {}, edge.id));
  dagre.layout(graph);
  return {
    nodes: ordered.map((node) => {
      const { x, y } = graph.node(node.id);
      return { node, position: { x: x - NODE_WIDTH / 2, y: y - NODE_HEIGHT / 2 } };
    }),
    edges: validEdges.map((edge) => ({ edge, points: graph.edge({ v: edge.from_id, w: edge.to_id, name: edge.id }).points })),
    groups: groups.map((key) => {
      const { x, y, width, height } = graph.node(groupIds.get(key));
      return { id: groupIds.get(key), key, position: { x: x - width / 2, y: y - height / 2 }, width, height, count: ordered.filter((node) => artifactGroup(node) === key).length };
    }),
  };
}
