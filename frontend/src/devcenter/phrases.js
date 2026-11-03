// Phrases catalog from the backend contract (UC31).
// All text follows ASD-STE100 rules.
import PHRASES_CONTRACT from "../../../backend/devcenter/contracts/phrases.json" with { type: "json" };

export const PHRASES = Object.freeze(PHRASES_CONTRACT.phrases ?? {});

// Get the display text for a phrase identifier.
export function phraseText(phraseId) {
  if (!phraseId) return "";
  const cleanId = String(phraseId).replace(/^compare\.(property|note|warning)\./, "");
  const entry = PHRASES[cleanId] ?? PHRASES[phraseId];
  return entry?.text ?? cleanId;
}
