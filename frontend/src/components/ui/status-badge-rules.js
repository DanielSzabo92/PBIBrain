// StatusBadge rules (UI design 1.3 house rule 3, A4): each status shows an icon plus a word.
// This module has no JSX, so that the node unit tests can import it.

export const STATUS_TONES = Object.freeze(["ok", "warn", "bad", "info", "plain", "proposal"]);

// Return the checked tone and label. Throw when the tone is not known or when the label is empty,
// because a tone with no word is a color-only status.
export function statusBadgeProps({ tone = "plain", label } = {}) {
  if (!STATUS_TONES.includes(tone)) {
    throw new Error(`StatusBadge: the tone "${tone}" is not known. Use one of: ${STATUS_TONES.join(", ")}.`);
  }
  const text = typeof label === "string" ? label.trim() : "";
  if (!text) {
    throw new Error(`StatusBadge: the tone "${tone}" has no label. Give each status a word, not only a color.`);
  }
  return { tone, label: text };
}
