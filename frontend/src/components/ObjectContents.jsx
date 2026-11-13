import React, { useState } from "react";
import { TypeGlyph } from "./TypeGlyph";
import { Card } from "./ui/card";
import { pluralType } from "../graphPresentation";
import { formatCount } from "../presentation";

const FIRST = 12;

/**
 * What a model, table, report or page holds, by kind. The page of a container is its table of
 * contents: a model lists its tables with their size, a table its measures and columns with data types.
 */
export default function ObjectContents({ groups, colors, onSelect }) {
  const [open, setOpen] = useState(() => new Set());
  if (!Array.isArray(groups) || !groups.length) return null;
  return <Card className="panel object-contents" aria-label="Contents">
    <h2 className="panel-title">Contents</h2>
    {groups.map((group) => {
      const all = open.has(group.type);
      const rows = all ? group.items : group.items.slice(0, FIRST);
      const label = pluralType(group.type, group.count);
      return <div className="contents-group" key={group.type}>
        <h3 className="relationship-title">{label}<span className="count-pill" data-ui-number="">{formatCount(group.count)}</span></h3>
        <ul className="contents-list">
          {rows.map((row) => <li key={row.id}>
            <button type="button" className={`contents-row${row.hidden ? " is-hidden-object" : ""}`} onClick={() => onSelect(row.id)}>
              <TypeGlyph type={row.type} colors={colors} size="xs" />
              <span className="contents-name">{row.name}</span>
              {row.hidden ? <span className="contents-tag">Hidden</span> : null}
              <span className="contents-meta" data-ui-number="">{row.data_type || row.visual_type || (row.holds ? formatCount(row.holds) : "")}</span>
            </button>
          </li>)}
        </ul>
        {group.items.length > FIRST ? <button type="button" className="contents-more" onClick={() => setOpen((current) => { const next = new Set(current); if (all) next.delete(group.type); else next.add(group.type); return next; })}>
          {all ? "Show fewer" : `Show all ${formatCount(group.count)}`}
        </button> : null}
        {all && group.count > group.items.length ? <p className="footnote">The first {formatCount(group.items.length)} are listed; use the tree filter for the rest.</p> : null}
      </div>;
    })}
  </Card>;
}
