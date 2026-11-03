// Side pane for the active row detail (UI design 4.4, placeholder for U6).
// All text follows ASD-STE100 rules.
import React from "react";
import { Code, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { phraseText } from "../phrases.js";
import { STATE_ICONS, stateWord } from "./StateCell.jsx";

export default function CompareRowDetail({
  row,
  donors = [],
  onClose,
  onOpenDiff,
}) {
  if (!row) return null;

  const rawState = row.row_state || "same";
  const state = rawState === "conflict" ? "type_conflict" : rawState;
  const StateIcon = STATE_ICONS[state] || STATE_ICONS.same;
  const stateLabel = stateWord(state);

  const getCell = (sourceId) => {
    if (Array.isArray(row.cells)) {
      return row.cells.find((c) => c.source_id === sourceId) || null;
    }
    return row.cells?.[sourceId] || null;
  };

  const donorDiffs = donors
    .map((donor) => {
      const cell = getCell(donor.source_id);
      const properties = cell?.properties || cell?.phrases || [];
      const notes = cell?.notes || [];
      return {
        donor,
        cell,
        properties,
        notes,
        hasDiffs: properties.length > 0 || notes.length > 0 || cell?.state !== "same",
      };
    })
    .filter((item) => item.hasDiffs);

  return (
    <aside className="dc-row-pane" aria-label="Row detail">
      <div className="dc-row-pane-head">
        <div>
          <h2 className="text-base font-semibold m-0">{row.name}</h2>
          <div className="text-xs text-[var(--text-2)]">
            {row.object_type}
            {row.table ? `, ${row.table}` : ""}
          </div>
        </div>
        <Button
          id="closepane"
          variant="ghost"
          size="icon"
          onClick={onClose}
          aria-label="Close row detail"
        >
          <X className="w-4 h-4" />
        </Button>
      </div>

      <div>
        <span className={`dc-st dc-st-${state}`}>
          <StateIcon aria-hidden="true" />
          <span>{stateLabel}</span>
        </span>
      </div>

      {donorDiffs.map(({ donor, properties, notes }) => (
        <div key={donor.source_id} className="flex flex-col gap-1">
          <b className="text-xs">{donor.display_name || donor.name}</b>
          <ul className="text-xs m-0 pl-4 text-[var(--text-2)]">
            {properties.map((p, idx) => (
              <li key={`p-${idx}`}>
                {phraseText(p.phrase_id || p.property)}
                {p.old !== undefined && p.new !== undefined ? `: ${p.old} to ${p.new}` : ""}
              </li>
            ))}
            {notes.map((n, idx) => (
              <li key={`n-${idx}`}>{phraseText(n.phrase_id || n.note_id || n)}</li>
            ))}
          </ul>
        </div>
      ))}

      <Button
        id="opendiff"
        variant="outline"
        size="sm"
        disabled={donorDiffs.length === 0}
        onClick={() => onOpenDiff?.(donorDiffs[0]?.donor || donors[0])}
      >
        <Code className="w-4 h-4" aria-hidden="true" />
        <span>Show code diff</span>
      </Button>

      <div className="dc-row-pane-ph">
        Merge Choice editor, alignment and removal policy: ticket 19.
      </div>
    </aside>
  );
}
