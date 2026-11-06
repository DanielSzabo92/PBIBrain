// WireframeBox (UI design 4.5, 7.3): one visual of a wireframe page with pattern, icon, and word (A4).
// The Unchanged status has no status line. An offer visual of a donor report has a checkbox.
import React from "react";
import { CircleHelp, CircleX, Plus, Trash2, TriangleAlert } from "lucide-react";
import { Checkbox } from "@/components/ui/checkbox";
import { t } from "../copy.js";
import { wireStatusWord, wireVisualLabel } from "../screens/impact/impactModel.js";

export const WIRE_ICONS = { removed: Trash2, breaks: CircleX, changes: TriangleAlert, new: Plus, not_checked: CircleHelp };

export function WireStatus({ status }) {
  const Icon = WIRE_ICONS[status];
  if (!Icon) return null;
  return (
    <span className="dc-wire-status" data-status-line={status}>
      <Icon aria-hidden="true" />
      {wireStatusWord(status)}
    </span>
  );
}

export default function WireframeBox({ visual, scale, selected, offer, offerDisabled, onOpen, onOffer }) {
  return (
    <div
      className="dc-wire-box"
      data-status={visual.status}
      data-selected={selected || undefined}
      style={{
        left: Math.round(visual.x * scale),
        top: Math.round(visual.y * scale),
        width: Math.max(48, Math.round(visual.width * scale)),
        height: Math.max(40, Math.round(visual.height * scale)),
      }}>
      <button type="button" className="dc-wire-open" aria-label={wireVisualLabel(visual)} aria-pressed={selected} onClick={() => onOpen(visual)}>
        <span className="dc-wire-title">{visual.title}</span>
        <WireStatus status={visual.status} />
      </button>
      {offer ? (
        <Checkbox
          size="target"
          className="dc-wire-offer"
          checked={Boolean(offer.selected)}
          disabled={offerDisabled}
          aria-label={t("impact.wireframe.offer", { title: visual.title })}
          onCheckedChange={(checked) => onOffer(offer, checked === true)}
        />
      ) : null}
    </div>
  );
}
