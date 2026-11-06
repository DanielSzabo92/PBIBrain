// ImpactNode (UI design 4.5): one graph object, 224 x 76 px. A button: Tab in rank order, arrows along edges, Enter or Space opens.
import React from "react";
import { CircleX, Info, TriangleAlert } from "lucide-react";
import { graphNodeLabel } from "../screens/impact/impactModel.js";
import { t } from "../copy.js";

export const IMPACT_NODE_WIDTH = 224;
export const IMPACT_NODE_HEIGHT = 76;

const ICONS = { blocking: CircleX, warning: TriangleAlert, information: Info };

const ImpactNode = React.forwardRef(function ImpactNode({ node, x, y, selected, onOpen, onKeyDown }, ref) {
  const Icon = ICONS[node.status];
  const word = node.status === "path" ? t("impact.graph.node.path") : t(`impact.status.${node.status}`);
  return (
    <button
      ref={ref}
      type="button"
      className="dc-impact-node"
      data-status={node.status}
      data-node-id={node.id}
      data-selected={selected || undefined}
      aria-pressed={selected}
      aria-label={graphNodeLabel(node)}
      style={{ left: x, top: y, width: IMPACT_NODE_WIDTH, height: IMPACT_NODE_HEIGHT }}
      onClick={() => onOpen(node)}
      onKeyDown={(event) => onKeyDown(event, node)}>
      <span className="dc-impact-node-type">{node.type}</span>
      <span className="dc-impact-node-name">{node.name}</span>
      <span className="dc-impact-node-status">
        {Icon ? <Icon aria-hidden="true" /> : null}
        {word}
      </span>
    </button>
  );
});

export default ImpactNode;
