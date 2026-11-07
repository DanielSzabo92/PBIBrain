// Common / divergent / unique objects across the project (issue #14).
// Pure functions over the /api/commonality payload, used by the Overview panel.

export const BUCKETS = ["identical", "differs", "renamed", "unique"];

export const BUCKET_LABELS = {
  identical: "Identical",
  differs: "Differs",
  renamed: "Renamed",
  unique: "Unique",
};

const TYPE_ORDER = ["TABLE", "COLUMN", "MEASURE", "CALCULATION_ITEM", "HIERARCHY", "PARTITION", "SHARED_EXPRESSION", "RELATIONSHIP", "SECURITY_ROLE", "PAGE", "VISUAL"];

const PROPERTY_LABELS = {
  expression: "expression",
  format_string: "format",
  display_folder: "display folder",
  datatype: "data type",
  data_type: "data type",
  description: "description",
  hidden: "hidden",
  name: "name",
  visual_type: "visual type",
  field_refs: "fields",
  display_name: "display name",
};

export function propertyLabel(key) {
  return PROPERTY_LABELS[key] || String(key).replaceAll("_", " ");
}

/** Rows of the counts table: one per type, in model-first order, with the row total. */
export function countRows(counts = {}) {
  return Object.entries(counts)
    .map(([type, byBucket]) => ({ type, ...Object.fromEntries(BUCKETS.map((bucket) => [bucket, byBucket?.[bucket] || 0])), total: BUCKETS.reduce((sum, bucket) => sum + (byBucket?.[bucket] || 0), 0) }))
    .filter((row) => row.total > 0)
    .sort((a, b) => {
      const ia = TYPE_ORDER.indexOf(a.type), ib = TYPE_ORDER.indexOf(b.type);
      return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib) || a.type.localeCompare(b.type);
    });
}

export function sourceName(ref, sources = []) {
  return sources.find((source) => source.ref === ref)?.name || ref;
}

/** One line that says where the group lives and how it differs. */
export function groupSummary(group, sources = []) {
  const names = (refs) => refs.map((ref) => sourceName(ref, sources)).join(", ");
  const present = group.in || [];
  const of = group.of || present.length;
  const differs = (group.differs || []).filter((key) => key !== "name").map(propertyLabel);
  if (group.bucket === "unique") return `Only in ${names(present)}`;
  if (group.bucket === "identical") return `Identical in ${present.length} of ${of}: ${names(present)}`;
  if (group.bucket === "renamed") {
    const byName = new Map();
    for (const ref of present) {
      const name = group.names?.[ref] || group.name;
      byName.set(name, [...(byName.get(name) || []), ref]);
    }
    const parts = [...byName].map(([name, refs]) => `${name} (${names(refs)})`);
    return `Same logic under ${byName.size} names: ${parts.join(" · ")}${differs.length ? `; also differs in ${differs.join(", ")}` : ""}`;
  }
  return `Differs in ${present.length} of ${of}${differs.length ? `: ${differs.join(", ")}` : ""}${group.variants ? ` (${group.variants} variants)` : ""}`;
}

/** The members of a group as rows: source, object name, object id. */
export function groupMembers(group, sources = []) {
  return (group.in || []).map((ref) => ({
    ref,
    source: sourceName(ref, sources),
    name: group.names?.[ref] || group.name,
    objectId: group.objects?.[ref] || null,
  }));
}

/** Model ids of a group, for starting a merge session from it (models only, two or more). */
export function mergeCandidates(group, sources = []) {
  if (!group || group.domain === "report") return [];
  const ids = (group.in || []).map((ref) => sources.find((source) => source.ref === ref)).filter((source) => source && source.domain !== "report").map((source) => source.id);
  return ids.length >= 2 ? ids : [];
}

/** The panel is worth showing when there are two models or two reports to compare. */
export function hasComparableSources(overview = {}) {
  return (overview.models || 0) >= 2 || (overview.reports || 0) >= 2;
}
