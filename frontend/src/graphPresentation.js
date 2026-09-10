export const ARTIFACT_GROUPS = {
  report: { label: "Report artifacts", color: "#a78bfa", types: ["REPORT", "PAGE", "VISUAL", "VISUAL_FILTER", "PAGE_FILTER", "REPORT_FILTER"] },
  model: { label: "Model artifacts", color: "#60a5fa", types: ["MODEL", "TABLE", "COLUMN", "MEASURE", "RELATIONSHIP", "FIELD_PARAMETER", "SHARED_EXPRESSION", "USER_DEFINED_FUNCTION", "CALCULATION_GROUP", "CALCULATION_ITEM"] },
  other: { label: "Other artifacts", color: "#94a3b8", types: ["WORKSPACE", "BUSINESS_CONCEPT", "SELECTOR", "SELECTOR_OPTION", "CONFLICT", "SEMANTIC_ASSERTION", "ALIAS", "ROLE", "BEHAVIOR"] },
};

export const OBJECT_TYPES = Object.values(ARTIFACT_GROUPS).flatMap((group) => group.types);
export const EDGE_TYPES = ["CONTAINS", "BELONGS_TO", "DEPENDS_ON", "REFERENCES", "MODIFIES_FILTER", "ACTIVATES_RELATIONSHIP", "MODIFIES_RELATIONSHIP", "USES", "RELATES_TO", "FILTERS", "USES_MODEL", "CONTROLLED_BY", "HAS_OPTION", "DEFAULTS_TO", "SEMANTICALLY_MAPS_TO", "SIMILAR_TO", "OBSERVED_WITH", "CONFLICTS_WITH", "ALIAS_OF", "HAS_ROLE", "HAS_BEHAVIOR"];

export function artifactGroup(node) {
  if (Object.hasOwn(ARTIFACT_GROUPS, node.artifact_group)) return node.artifact_group;
  if (ARTIFACT_GROUPS.report.types.includes(node.type)) return "report";
  if (ARTIFACT_GROUPS.model.types.includes(node.type)) return "model";
  if (ARTIFACT_GROUPS.other.types.includes(node.type)) return "other";
  if (node.report_id || node.source === "report_metadata") return "report";
  if (node.model_id) return "model";
  return "other";
}

export function normalizeColors(value) {
  const groups = Object.fromEntries(Object.entries(ARTIFACT_GROUPS).map(([key, group]) => [key, group.color]));
  const types = {};
  for (const [section, target] of [["groups", groups], ["types", types]]) {
    for (const [key, color] of Object.entries(value?.[section] || {})) {
      if (section === "groups" && !Object.hasOwn(groups, key)) continue;
      if (section === "types" && !/^[A-Z][A-Z0-9_]{0,79}$/.test(key)) continue;
      if (typeof color === "string" && /^#[0-9a-f]{6}$/i.test(color)) target[key] = color.toLowerCase();
    }
  }
  return { groups, types };
}

export function artifactColor(node, colors) {
  const palette = colors || normalizeColors();
  return palette.types[node.type] || palette.groups[artifactGroup(node)];
}

export function typeLabel(type) {
  return String(type || "Object").toLowerCase().replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase());
}
