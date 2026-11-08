// CompletenessStrip (UI design 4.5): "Complete" or "Incomplete: <n> areas", one sentence, and "Show areas".
// The areas list shows 20 entries at a time ("Show 20 more").
import React, { useState } from "react";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/status-badge";
import { t } from "../copy.js";
import { AREA_STEP, completenessState, visibleEntries } from "../screens/impact/impactModel.js";

export default function CompletenessStrip({ completeness, open, onOpenChange }) {
  const [shown, setShown] = useState(AREA_STEP);
  const state = completenessState(completeness);
  const { list, more } = visibleEntries(state.entries, shown);
  const listId = "dc-impact-areas";
  return (
    <section className="dc-complete" data-complete={state.complete ? "true" : "false"} aria-label={state.label}>
      <div className="dc-complete-main">
        <StatusBadge tone={state.tone} label={state.label} />
        <p className="dc-complete-help" title={t("impact.completeness.safe_superset.tooltip")}>{state.help}</p>
        {state.entries.length > 0 ? (
          <Button variant="outline" size="sm" aria-expanded={open} aria-controls={listId} onClick={() => onOpenChange(!open)}>
            {open ? t("impact.completeness.hide") : t("impact.completeness.show")}
          </Button>
        ) : null}
      </div>
      {open && state.entries.length > 0 ? (
        <div id={listId} className="dc-complete-areas">
          <ul className="dc-complete-list">
            {list.map((entry, index) => (
              <li key={`${entry.area}-${index}`} className="dc-complete-entry">
                <span className="dc-complete-area">{entry.label}</span>
                <span>{entry.text}</span>
              </li>
            ))}
          </ul>
          {more ? (
            <Button variant="ghost" size="sm" onClick={() => setShown((value) => value + AREA_STEP)}>
              {t("impact.completeness.more")}
            </Button>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
