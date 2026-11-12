// Phrases catalog from the backend contract (UC31).
// All text follows ASD-STE100 rules.
import PHRASES_CONTRACT from "../../../backend/devcenter/contracts/phrases.json" with { type: "json" };
import { formatDaxName, formatObjectRef } from "../presentation.js";

export { formatDaxName, formatObjectRef };

const PHRASES = Object.freeze(PHRASES_CONTRACT.phrases ?? {});

const PLAN_OP_PHRASES = Object.freeze({
  SET_EXPRESSION: "Set expression",
  SET_PROPERTIES: "Set properties",
  SET_PROPERTY: "Set property",
  REPLACE: "Replace",
  CREATE: "Create",
  DELETE: "Delete",
  RENAME: "Rename",
  RENAME_PAIR: "Rename pair",
  REWRITE_EXPRESSION: "Rewrite expression",
  COPY_PAGE: "Copy page",
  COPY_VISUAL: "Copy visual",
  DELETE_PAGE: "Delete page",
  DELETE_VISUAL: "Delete visual",
  CREATE_REPORT_MEASURE: "Create report measure",
  DELETE_REPORT_MEASURE: "Delete report measure",
  REPLACE_REPORT_MEASURE: "Replace report measure",
  REBIND_FIELD: "Rebind field",
  REMOVE_FIELD: "Remove field",
  REBIND_REPORT: "Rebind report",
  SET_DATASET_REFERENCE: "Set dataset reference",
  APPLY_NAMING_RULES: "Apply naming rules",
  MOVE_FOLDER: "Move folder",
});

export function formatOperationKind(opKind) {
  if (!opKind) return "";
  const upper = String(opKind).toUpperCase();
  if (PLAN_OP_PHRASES[upper]) return PLAN_OP_PHRASES[upper];
  return String(opKind).replaceAll("_", " ").toLowerCase().replace(/^\w/, (c) => c.toUpperCase());
}

// Get the display text for a phrase identifier.
export function phraseText(phraseId) {
  if (!phraseId) return "";
  const cleanId = String(phraseId).replace(/^compare\.(property|note|warning)\./, "");
  const entry = PHRASES[cleanId] ?? PHRASES[phraseId];
  return entry?.text ?? cleanId;
}
