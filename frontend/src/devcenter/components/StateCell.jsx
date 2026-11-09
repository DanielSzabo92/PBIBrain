// Cell that shows the compare state of one object in one source (UI design 4.3).
// All text follows ASD-STE100 rules.
import React from "react";
import { ArrowRightLeft, Circle, CircleDashed, Equal, EqualNot, OctagonAlert, PenLine, Target } from "lucide-react";
import { t } from "../copy.js";
import { phraseText } from "../phrases.js";
import { Tooltip } from "../../components/ui/tooltip.jsx";

export const STATE_ICONS = {
  conflict: OctagonAlert,
  type_conflict: OctagonAlert,
  missing: CircleDashed,
  not_checked: CircleDashed,
  renamed: PenLine,
  moved: ArrowRightLeft,
  different: EqualNot,
  same: Equal,
  target: Target,
};

// Normalize backend state names to copy keys.
export function normalizeState(state) {
  if (state === "conflict") return "type_conflict";
  if (state === "not_checked") return "not_checked";
  return state || "same";
}

export function stateWord(state) {
  const key = normalizeState(state);
  return t(`compare.state.${key}`) || (key === "not_checked" ? "Not checked" : key);
}

// Consistent tone mapping across grid and row pane (UI design 7.2)
export function stateTone(state) {
  const key = normalizeState(state);
  if (key === "conflict" || key === "type_conflict") return "bad";
  if (key === "same") return "ok";
  if (key === "renamed" || key === "moved") return "info";
  if (key === "different") return "warn";
  if (key === "missing" || key === "not_checked") return "plain";
  return "warn";
}

export default function StateCell({ cell, sourceName, onOpenDiff, loading = false }) {
  if (loading) {
    return <span className="dc-skel-line" aria-hidden="true" />;
  }

  if (!cell) {
    const word = stateWord("not_checked");
    const Icon = STATE_ICONS.not_checked || CircleDashed;
    return (
      <Tooltip content={sourceName ? `${sourceName}: ${word}` : word}>
        <span className="dc-st dc-st-not-checked">
          <Icon aria-hidden="true" />
          <span>{word}</span>
        </span>
      </Tooltip>
    );
  }

  const rawState = cell.state || "same";
  const state = normalizeState(rawState);
  const Icon = STATE_ICONS[state] || Equal;
  const word = stateWord(state);

  const properties = cell.properties || cell.phrases || [];
  const notes = cell.notes || [];
  const propertyCount = properties.length;
  const hasChanged = Boolean(cell.changed) && state !== "same";

  const tooltipLines = [];
  if (sourceName) {
    tooltipLines.push(`${sourceName}: ${word}`);
  }
  if (state === "type_conflict") {
    tooltipLines.push(t("compare.state.type_conflict.help"));
  }
  for (const item of properties) {
    const text = phraseText(item.phrase_id || item.property);
    const detail = item.old !== undefined && item.new !== undefined ? `: ${item.old} to ${item.new}` : "";
    tooltipLines.push(`${text}${detail}`);
  }
  for (const note of notes) {
    const noteId = typeof note === "string" ? note : note.note_id || note.phrase_id;
    tooltipLines.push(phraseText(noteId));
  }
  if (state !== "same" && onOpenDiff) {
    tooltipLines.push("Press D for the code diff.");
  }
  const tooltipText = tooltipLines.join("\n");

  const cellContent = (
    <span
      className={`dc-st dc-st-${state}`}
      onDoubleClick={state !== "same" && onOpenDiff ? onOpenDiff : undefined}
    >
      <Icon aria-hidden="true" />
      {state === "target" ? <span className="sr-only">{word}</span> : <span>{word}</span>}
      {propertyCount > 0 ? (
        <Tooltip content={`${propertyCount} differences`}>
          <span className="dc-st-count">
            ({propertyCount})
          </span>
        </Tooltip>
      ) : null}
      {hasChanged ? (
        <Tooltip content={t("compare.changed.title")}>
          <span className="dc-st-changed">
            <Circle aria-hidden="true" />
            <span className="sr-only">{t("compare.changed")}</span>
          </span>
        </Tooltip>
      ) : null}
    </span>
  );

  if (tooltipText) {
    return <Tooltip content={<span style={{ whiteSpace: "pre-line" }}>{tooltipText}</span>}>{cellContent}</Tooltip>;
  }
  return cellContent;
}
