// Impact graph view (UI design 4.5, A12, A22): the union of the shortest paths of the filtered items.
// Reuses layoutGraph and routePath. Solid edge = certain, dashed = possible. Limit 150 nodes, else "Open table".
import React, { useLayoutEffect, useMemo, useRef, useState } from "react";
import { Maximize2, Table2, ZoomIn, ZoomOut } from "lucide-react";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/result-panel";
import { NODE_HEIGHT, layoutGraph, routePath } from "../../../graphLayout.js";
import { t } from "../../copy.js";
import ImpactNode, { IMPACT_NODE_HEIGHT } from "../../components/ImpactNode.jsx";
import { GRAPH_LIMIT, buildImpactGraph, graphKeyTarget, graphTabOrder } from "./impactModel.js";
import ProvenanceLegend from "@/components/ProvenanceLegend";


const ZOOMS = [0.5, 0.67, 0.8, 1, 1.25];

export default function ImpactGraph({ items, total, selectedItemId, onOpenItem, onShowTable }) {
  const tooMany = total > GRAPH_LIMIT;
  const graph = useMemo(() => (tooMany ? { nodes: [], edges: [] } : buildImpactGraph(items)), [items, tooMany]);
  const overLimit = tooMany || graph.nodes.length > GRAPH_LIMIT;
  const layout = useMemo(
    () => (overLimit ? null : layoutGraph(graph.nodes, graph.edges, "LR", { width: IMPACT_NODE_WIDTH, height: IMPACT_NODE_HEIGHT, nodeHeight: IMPACT_NODE_HEIGHT })),
    [graph, overLimit]
  );
  const ordered = useMemo(() => (layout ? graphTabOrder(layout.nodes) : []), [layout]);
  const [zoom, setZoom] = useState(1);
  const viewRef = useRef(null);
  const refs = useRef(new Map());

  const size = useMemo(() => {
    if (!layout) return { width: 0, height: 0 };
    let width = 0;
    let height = 0;
    for (const entry of layout.nodes) {
      width = Math.max(width, entry.position.x + (entry.width || IMPACT_NODE_WIDTH) + 32);
      height = Math.max(height, entry.position.y + (entry.height || IMPACT_NODE_HEIGHT) + 32);
    }
    return { width, height };
  }, [layout]);

  // Budget P5: the reply to layout and paint.
  useLayoutEffect(() => {
    if (!layout) return undefined;
    const frame = requestAnimationFrame(() => globalThis.performance?.mark?.("dc-impact-graph-painted"));
    return () => cancelAnimationFrame(frame);
  }, [layout]);

  if (overLimit) {
    return (
      <EmptyState
        headingLevel={2}
        title={t("impact.graph.too_many.title")}
        action={<Button variant="outline" onClick={onShowTable}>{t("impact.graph.too_many.action")}</Button>}>
        {t("impact.graph.too_many.body", { n: tooMany ? total : graph.nodes.length })}
      </EmptyState>
    );
  }

  const selectedNodes = new Set(graph.nodes.filter((node) => node.itemIds.includes(selectedItemId)).map((node) => node.id));
  const itemFor = (node) => {
    const id = node.itemIds[0] ?? items.find((item) => (item.path ?? []).some((step) => step.object_id === node.id))?.id;
    return items.find((item) => item.id === id) ?? null;
  };
  const open = (node) => {
    const item = itemFor(node);
    if (item) onOpenItem(item, refs.current.get(node.id));
  };
  const onKeyDown = (event, node) => {
    const next = graphKeyTarget(graph, ordered, node.id, event.key);
    if (next) {
      event.preventDefault();
      refs.current.get(next)?.focus();
    } else if (event.key.startsWith("Arrow")) {
      event.preventDefault();
    }
  };
  const fit = () => {
    const width = viewRef.current?.clientWidth || size.width;
    const fitted = Math.min(1, width / Math.max(1, size.width));
    setZoom(Math.max(ZOOMS[0], Number(fitted.toFixed(2))));
  };
  const step = (direction) => {
    const index = ZOOMS.findIndex((value) => value >= zoom - 0.001);
    const next = ZOOMS[Math.min(ZOOMS.length - 1, Math.max(0, (index < 0 ? ZOOMS.length - 1 : index) + direction))];
    setZoom(next);
  };
  const offsetY = 0;

  return (
    <div className="dc-impact-graph">
      <div className="dc-impact-graph-bar">
        <span className="dc-impact-graph-count">{t("impact.graph.count", { n: graph.nodes.length, m: graph.edges.length })}</span>
        <ProvenanceLegend className="dc-impact-legend" />
        <span className="dc-impact-graph-zoom">
          <Button variant="ghost" size="icon-sm" aria-label={t("impact.graph.zoom_in")} onClick={() => step(1)}><ZoomIn /></Button>
          <span className="dc-impact-zoom-value" aria-label={t("impact.graph.zoom", { n: Math.round(zoom * 100) })}>{Math.round(zoom * 100)}%</span>
          <Button variant="ghost" size="icon-sm" aria-label={t("impact.graph.zoom_out")} onClick={() => step(-1)}><ZoomOut /></Button>
          <Button variant="ghost" size="icon-sm" aria-label={t("impact.graph.fit")} onClick={fit}><Maximize2 /></Button>
        </span>
        <Button variant="outline" size="sm" onClick={onShowTable}><Table2 aria-hidden="true" />{t("impact.graph.table")}</Button>
      </div>
      <div ref={viewRef} className="dc-impact-graph-view" role="group" aria-label={t("impact.graph.label")}>
        <div className="dc-impact-graph-canvas" style={{ width: size.width * zoom, height: size.height * zoom }}>
          <div className="dc-impact-graph-plane" style={{ width: size.width, height: size.height, transform: `scale(${zoom})` }}>
            <svg className="dc-impact-edges" width={size.width} height={size.height} aria-hidden="true">
              {layout.edges.map(({ edge, points }) => (
                <path key={edge.id} d={routePath(points)} className="dc-impact-edge" data-certain={edge.certain ? "true" : "false"} />
              ))}
            </svg>
            {ordered.map(({ node, position }) => (
              <ImpactNode
                key={node.id}
                ref={(element) => {
                  if (element) refs.current.set(node.id, element);
                  else refs.current.delete(node.id);
                }}
                node={node}
                x={position.x}
                y={position.y + offsetY}
                selected={selectedNodes.has(node.id)}
                onOpen={open}
                onKeyDown={onKeyDown}
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
