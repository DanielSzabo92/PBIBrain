// Progress list of the Apply, format only, and Undo flows (UI design 5.5 step 3, 5.6, step U10).
// Each row shows its state with an icon and a visible status word.
import React from "react";
import { Check, CircleX, LoaderCircle } from "lucide-react";
import { t } from "../../copy.js";

const STATE_WORD = { done: "Done", running: "Running", waiting: "Waiting", failed: "Failed" };

function RowIcon({ state }) {
  if (state === "done") return <Check className="dc-apply-step-icon dc-tone-ok" aria-hidden="true" />;
  if (state === "running") return <LoaderCircle className="dc-apply-step-icon spin" aria-hidden="true" />;
  if (state === "failed") return <CircleX className="dc-apply-step-icon dc-tone-bad" aria-hidden="true" />;
  return <span className="dc-apply-step-icon dc-apply-step-wait" aria-hidden="true" />;
}

export default function ApplyProgressList({ rows, line }) {
  const groups = [];
  for (const row of rows) {
    const last = groups[groups.length - 1];
    if (last && last.group === row.group) last.rows.push(row);
    else groups.push({ group: row.group, rows: [row] });
  }
  return (
    <div className="dc-apply-progress">
      {groups.map((group) => (
        <div key={group.group} className="dc-apply-progress-group">
          <h3 className="dc-apply-h3">{t(`apply.progress.${group.group}`)}</h3>
          <ol className="dc-apply-steps">
            {group.rows.map((row) => (
              <li key={row.id} className="dc-apply-step" data-step={row.id} data-state={row.state}>
                <RowIcon state={row.state} />
                <span className="dc-apply-step-label">{row.label}</span>
                <span className="dc-apply-step-state">{STATE_WORD[row.state]}</span>
              </li>
            ))}
          </ol>
        </div>
      ))}
      {line ? <p className="dc-apply-progress-line dc-num" role="status" aria-live="polite">{line}</p> : null}
    </div>
  );
}
