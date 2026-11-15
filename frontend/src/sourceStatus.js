// What a configured source looks like in Settings: found or not, and what the last scan did with it.
// `entry` is one row of GET /api/config/sources: { path, exists, kind, scan?: { state, detail, models, reports } }.

const plural = (count, word) => `${count} ${word}${count === 1 ? "" : "s"}`;

/** @returns {{ tone: "ok"|"bad"|"warn"|"busy"|"unknown", label: string, text: string }} label is the full sentence, text the short one. */
export function sourceState(entry) {
  if (!entry) return { tone: "unknown", label: "Not checked yet", text: "" };
  if (!entry.exists) return { tone: "bad", label: "Not found at this path", text: "Not found" };
  const scan = entry.scan;
  if (!scan) return { tone: "ok", label: "Found. Not scanned since the app started.", text: "Found" };
  if (scan.state === "scanned") {
    const holds = [scan.models ? plural(scan.models, "model") : "", scan.reports ? plural(scan.reports, "report") : ""].filter(Boolean).join(", ");
    return { tone: "ok", label: `Scanned${holds ? `: ${holds}` : ""}`, text: `Scanned${holds ? ` · ${holds}` : ""}` };
  }
  if (scan.state === "failed") return { tone: "bad", label: `Could not be read: ${scan.detail || "unknown error"}`, text: "Failed" };
  if (scan.state === "reading") return { tone: "busy", label: "Being read", text: "Reading…" };
  if (scan.state === "waiting") return { tone: "busy", label: "Waiting to be read", text: "Waiting" };
  if (scan.state === "read") return { tone: "busy", label: "Read; the scan is still running", text: "Read" };
  return { tone: "warn", label: `Not scanned. ${scan.detail || "The scan did not finish"}.`, text: "Not scanned" };
}

export function sourceStatusMap(result) {
  return Object.fromEntries((result?.sources || []).map((item) => [item.path, item]));
}
