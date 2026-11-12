/**
 * Pending changes (issue #17): project files that changed outside PBIBrain since the last
 * scan. The backend compares the files with the last scan and lists the objects each change
 * breaks or needs; this module only turns that reply into what the warning shows.
 */

import { formatPlural as plural } from "./presentation.js";

export const PENDING_POLL_MS = 5000;
const SHOWN_STATUSES = new Set(["BREAKS", "NEEDS", "CHANGED", "UNREADABLE"]);
const MAX_ITEMS = 5;

function objectLabel(item) {
  if (!item) return "";
  return item.table && item.object_type !== "TABLE" ? `${item.table}[${item.name}]` : item.name;
}

/** Whether the reply needs a warning at all. */
export function showsPending(reply) {
  return Boolean(reply && SHOWN_STATUSES.has(reply.status));
}

/** Tone of the warning: "bad" when something breaks, "warn" otherwise. */
export function pendingTone(reply) {
  return reply?.status === "BREAKS" ? "bad" : "warn";
}

/** One-line headline for the warning. */
export function pendingHeadline(reply) {
  if (!showsPending(reply)) return "";
  const files = plural(reply.file_count || 0, "file");
  if (reply.status === "UNREADABLE") return `${files} changed outside PBIBrain and cannot be read yet.`;
  const summary = reply.safety?.summary || {};
  const parts = [];
  if (summary.breaks) parts.push(`breaks ${plural(summary.breaks, "object")}`);
  if (summary.needs) parts.push(`needs ${plural(summary.needs, "missing object")}`);
  const changed = summary.changes ? plural(summary.changes, "object") : "no objects";
  return `${files} changed outside PBIBrain since the last scan: ${changed} changed${parts.length ? `, ${parts.join(", ")}` : ""}.`;
}

/** Up to five readable lines: the breaks first, then the needs. */
export function pendingLines(reply) {
  const safety = reply?.safety || {};
  const lines = [];
  for (const item of safety.breaks || []) {
    const used = objectLabel(item.uses);
    lines.push(item.reason === "uses_old_name"
      ? `${objectLabel(item)} still uses the old name of ${used} (now ${item.uses?.new_name || "renamed"})`
      : `${objectLabel(item)} uses ${used}, which was deleted`);
  }
  for (const item of safety.needs || []) {
    const missing = (item.missing || []).map((entry) => (entry.table ? `${entry.table}[${entry.name}]` : entry.kind === "table" ? `'${entry.name}'` : `[${entry.name}]`));
    lines.push(`${objectLabel(item)} needs ${missing.join(", ")}, which the model does not have`);
  }
  const total = lines.length;
  return { lines: lines.slice(0, MAX_ITEMS), more: Math.max(0, total - MAX_ITEMS) };
}

/** A key that changes only when the warning would change, so a dismissed warning stays dismissed. */
export function pendingKey(reply) {
  if (!showsPending(reply)) return "";
  return JSON.stringify([reply.status, reply.scanned_at, (reply.files || []).map((item) => `${item.change}:${item.file}`)]);
}
