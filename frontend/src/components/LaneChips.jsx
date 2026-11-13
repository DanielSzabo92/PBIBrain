import React, { useMemo } from "react";
import { ChevronRight, Layers } from "lucide-react";
import { TypeGlyph } from "./TypeGlyph";
import { LANES, laneOf } from "../lineage";
import { formatCount } from "../presentation";

// What each lane does in the Matrix when it is switched off (Models and Reports are its axes).
const MATRIX_ROLE = {
  source: { fixed: "Not part of the matrix" },
  query: { fixed: "Not part of the matrix" },
  model: { fixed: "Models are the rows of the matrix" },
  table: { off: "Rows are not grouped by table" },
  column: { off: "Column rows are hidden" },
  calc: { off: "Calculation rows are hidden" },
  visual: { off: "Visuals are folded into their pages" },
  visualFilter: { off: "What visual filters use is not counted" },
  page: { off: "Pages are not shown; with Visuals off, reports are folded" },
  pageFilter: { off: "What page filters use is not counted" },
  report: { fixed: "Reports are the columns of the matrix" },
  reportFilter: { off: "What report filters use is not counted" },
  meaning: { fixed: "Not part of the matrix" },
};

/**
 * Lane chips: the lineage lanes in dependency order (Models › Sources › Queries › Tables › … › Report filters), each a toggle.
 * Shared by Lineage and Matrix, so switching off Columns hides them in both. Counts are the loaded objects.
 * The last chip says whether versions of a model or report are folded into one, and how many such groups exist.
 */
export default function LaneChips({ nodes, hidden, matrix, colors, onChange, versionGroups = [], versionsFolded = false, onVersions }) {
  const counts = useMemo(() => {
    const result = new Map();
    nodes.forEach((node) => { const lane = LANES[laneOf(node)].key; result.set(lane, (result.get(lane) || 0) + 1); });
    return result;
  }, [nodes]);
  const off = new Set(hidden);
  const lanes = LANES.filter((lane) => counts.get(lane.key) || off.has(lane.key));
  if (!lanes.length) return null;
  const toggle = (key) => onChange(off.has(key) ? hidden.filter((item) => item !== key) : [...hidden, key]);
  return <div className="lane-chips" role="toolbar" aria-label="Lanes, in dependency order">
    {lanes.map((lane, index) => {
      const role = matrix ? MATRIX_ROLE[lane.key] || {} : {};
      const fixed = Boolean(role.fixed);
      const shown = fixed || !off.has(lane.key);
      const count = counts.get(lane.key) || 0;
      const hint = fixed ? role.fixed : shown ? `Hide ${lane.label.toLowerCase()}${role.off ? ` (${role.off.toLowerCase()})` : ""}` : `Show ${lane.label.toLowerCase()}`;
      return <React.Fragment key={lane.key}>
        {index ? <ChevronRight className="lane-chip-sep" aria-hidden="true" /> : null}
        <button type="button" className="lane-chip" aria-pressed={shown} disabled={fixed} title={hint} onClick={() => toggle(lane.key)}>
          {lane.types[0] ? <TypeGlyph type={lane.types[0]} colors={colors} size="xs" /> : null}
          <span>{lane.label}</span>
          <span className="lane-chip-count" data-ui-number="">{formatCount(count)}</span>
        </button>
      </React.Fragment>;
    })}
    {versionGroups.length && onVersions ? <button type="button" className="lane-chip version-chip" aria-pressed={versionsFolded}
      title={`${versionsFolded ? "Shown once" : "Shown separately"}: ${versionGroups.map((names) => names.join(" = ")).join("; ")}. Click to ${versionsFolded ? "show every version" : "fold versions into one"}.`}
      onClick={() => onVersions(!versionsFolded)}>
      <Layers aria-hidden="true" />
      <span>{versionsFolded ? "Versions folded" : "Fold versions"}</span>
      <span className="lane-chip-count" data-ui-number="">{formatCount(versionGroups.length)}</span>
    </button> : null}
  </div>;
}
