export const ARTIFACT_GROUPS = {
  report: { label: "Report artifacts", color: "#a78bfa", types: ["REPORT", "PAGE", "VISUAL", "VISUAL_CALCULATION", "VISUAL_FILTER", "PAGE_FILTER", "REPORT_FILTER"] },
  model: { label: "Model artifacts", color: "#60a5fa", types: ["MODEL", "TABLE", "COLUMN", "MEASURE", "RELATIONSHIP", "FIELD_PARAMETER", "SHARED_EXPRESSION", "USER_DEFINED_FUNCTION", "CALCULATION_GROUP", "CALCULATION_ITEM"] },
  other: { label: "Other artifacts", color: "#94a3b8", types: ["WORKSPACE", "BUSINESS_CONCEPT", "SELECTOR", "SELECTOR_OPTION", "CONFLICT", "SEMANTIC_ASSERTION", "ALIAS", "ROLE", "BEHAVIOR"] },
};


export const PALETTES = [
  { name: "Studio", description: "Balanced, muted tones", groups: { report: "#b4a0cd", model: "#8daec6", other: "#b8afa1" }, types: { TABLE: "#8daec6", COLUMN: "#9dafa5", MEASURE: "#d3bb8f", REPORT: "#b4a0cd", PAGE: "#99bcbc", VISUAL: "#c79da3" } },
  { name: "Coast", description: "Cool blue, sage, and sand", groups: { report: "#88b8b1", model: "#8daeca", other: "#b7b1a0" }, types: { TABLE: "#8daeca", COLUMN: "#a7bfbe", MEASURE: "#d0bf99", REPORT: "#88b8b1", PAGE: "#acb8d0", VISUAL: "#c1a7b7" } },
  { name: "Ember", description: "Warm clay, olive, and rose", groups: { report: "#c49f9a", model: "#b9ad8b", other: "#aab2a0" }, types: { TABLE: "#b9ad8b", COLUMN: "#9cae9c", MEASURE: "#d0ae8e", REPORT: "#c49f9a", PAGE: "#aea4ba", VISUAL: "#a1b9bd" } },
  { name: "Slate", description: "Quiet, neutral shades", groups: { report: "#bbb5c6", model: "#a1b2c1", other: "#b7b5ae" }, types: { TABLE: "#a1b2c1", COLUMN: "#9eaaa5", MEASURE: "#cac2b3", REPORT: "#bbb5c6", PAGE: "#9aadb5", VISUAL: "#c1adaf" } },
];

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
  const legacy = ["#a78bfa", "#60a5fa", "#94a3b8"].every((color, index) => Object.values(groups)[index] === color);
  if (!Object.keys(types).length && legacy) return { groups: { ...PALETTES[0].groups }, types: { ...PALETTES[0].types } };
  return { groups, types };
}

export function artifactColor(node, colors) {
  const palette = colors || normalizeColors();
  return palette.types[node.type] || palette.groups[artifactGroup(node)];
}

export function typeLabel(type) {
  return String(type || "Object").toLowerCase().replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase());
}
