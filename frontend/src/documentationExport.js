/** Documentation export choices and the file the browser saves (issue #15). */

export const DOC_SECTIONS = [
  ["overview", "Overview and scope"],
  ["models", "Model diagram, relationships and tables"],
  ["measures", "Measure catalogue with DAX"],
  ["reports", "Report pages and visual fields"],
  ["lineage", "Lineage summary"],
  ["not_checked", "Not checked and unresolved"],
];

/**
 * The request for the chosen scope. Everything chosen means "all", sent as null, so objects
 * added by a later scan are included without the user ticking them.
 */
export function exportRequest({ format, models, reports, sections }, overview) {
  const allModels = (overview?.model_objects || []).map((item) => item.id);
  const allReports = (overview?.report_objects || []).map((item) => item.id);
  const pick = (chosen, all) => (all.length && all.every((id) => chosen.has(id)) ? null : all.filter((id) => chosen.has(id)));
  const allSections = DOC_SECTIONS.map(([key]) => key);
  return {
    format: format === "markdown" ? "markdown" : "pdf",
    modelIds: pick(models, allModels),
    reportIds: pick(reports, allReports),
    sections: allSections.every((key) => sections.has(key)) ? null : allSections.filter((key) => sections.has(key)),
  };
}

/** Why the export button is off, or "" when the scope can be exported. */
export function exportBlocker({ models, reports, sections }) {
  if (!sections.size) return "Choose at least one section.";
  if (!models.size && !reports.size) return "Choose at least one model or report.";
  return "";
}

/** Bytes of the server reply, decoded from base64. */
export function replyBytes(reply) {
  const text = atob(reply.content_base64 || "");
  const bytes = new Uint8Array(text.length);
  for (let index = 0; index < text.length; index += 1) bytes[index] = text.charCodeAt(index);
  return bytes;
}

export function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
