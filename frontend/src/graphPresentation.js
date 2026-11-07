export const ARTIFACT_GROUPS = {
  report: { label: "Report artifacts", color: "#a78bfa", types: ["REPORT", "PAGE", "VISUAL", "VISUAL_CALCULATION", "VISUAL_FILTER", "PAGE_FILTER", "REPORT_FILTER"] },
  model: { label: "Model artifacts", color: "#60a5fa", types: ["MODEL", "TABLE", "COLUMN", "MEASURE", "RELATIONSHIP", "FIELD_PARAMETER", "SHARED_EXPRESSION", "USER_DEFINED_FUNCTION", "CALCULATION_GROUP", "CALCULATION_ITEM", "PARTITION"] },
  other: { label: "Other artifacts", color: "#94a3b8", types: ["DATA_SOURCE", "WORKSPACE", "BUSINESS_CONCEPT", "SELECTOR", "SELECTOR_OPTION", "CONFLICT", "SEMANTIC_ASSERTION", "ALIAS", "ROLE", "BEHAVIOR"] },
};


// Default object palette (docs/design/visual-contract.md §3). Each type has a dark-theme colour (stored,
// user-editable) and a hand-tuned light-theme variant. Every colour is ≥3:1 on its canvas and ≥ΔE 5 from
// every status colour, so a type never reads as ok/warn/bad. Violet (Page) is a data colour only.
export const DEFAULT_PALETTE = {
  name: "Default",
  description: "Distinct hue per object type",
  groups: { report: "#e68ac0", model: "#6ea8fe", other: "#b5ac9c" },
  types: { MODEL: "#6ea8fe", TABLE: "#4cc2b0", COLUMN: "#a2afc2", MEASURE: "#c6c95a", REPORT: "#e68ac0", PAGE: "#c49bf2", VISUAL: "#f0995e" },
};

const LIGHT_VARIANTS = {
  "#6ea8fe": "#2563c9", "#4cc2b0": "#0e8273", "#a2afc2": "#5d6b80", "#c6c95a": "#6b6d00",
  "#e68ac0": "#b83f86", "#c49bf2": "#7c4fc4", "#f0995e": "#b4561c", "#b5ac9c": "#7a7163",
};

export const PALETTES = [
  DEFAULT_PALETTE,
  { name: "High contrast", description: "Saturated, maximum separation", groups: { report: "#ff7ab8", model: "#5c9dff", other: "#c4bba9" }, types: { MODEL: "#5c9dff", TABLE: "#2fd1b8", COLUMN: "#b6c2d4", MEASURE: "#d9de4c", REPORT: "#ff7ab8", PAGE: "#c48dff", VISUAL: "#ff9150" } },
  { name: "Studio", description: "Balanced, muted tones", groups: { report: "#b4a0cd", model: "#8daec6", other: "#b8afa1" }, types: { TABLE: "#8daec6", COLUMN: "#9dafa5", MEASURE: "#d3bb8f", REPORT: "#b4a0cd", PAGE: "#99bcbc", VISUAL: "#c79da3" } },
  { name: "Coast", description: "Cool blue, sage, and sand", groups: { report: "#88b8b1", model: "#8daeca", other: "#b7b1a0" }, types: { TABLE: "#8daeca", COLUMN: "#a7bfbe", MEASURE: "#d0bf99", REPORT: "#88b8b1", PAGE: "#acb8d0", VISUAL: "#c1a7b7" } },
  { name: "Slate", description: "Quiet, neutral shades", groups: { report: "#bbb5c6", model: "#a1b2c1", other: "#b7b5ae" }, types: { TABLE: "#a1b2c1", COLUMN: "#9eaaa5", MEASURE: "#cac2b3", REPORT: "#bbb5c6", PAGE: "#9aadb5", VISUAL: "#c1adaf" } },
];

/** Light-theme variant of a stored (dark-theme) colour: the tuned value for defaults, else a darker mix. */
export function lightVariant(color) {
  return LIGHT_VARIANTS[String(color).toLowerCase()] || `color-mix(in oklch, ${color} 55%, #18181a)`;
}

/** CSS custom properties that let any element follow the object's colour in both themes. */
export function artifactStyle(node, colors) {
  const color = artifactColor(node, colors);
  return { "--artifact-color": color, "--artifact-color-light": lightVariant(color) };
}

export const OBJECT_TYPES = Object.values(ARTIFACT_GROUPS).flatMap((group) => group.types);
export const EDGE_TYPES = ["CONTAINS", "BELONGS_TO", "DEPENDS_ON", "REFERENCES", "MODIFIES_FILTER", "ACTIVATES_RELATIONSHIP", "MODIFIES_RELATIONSHIP", "USES", "RELATES_TO", "FILTERS", "USES_MODEL", "CONTROLLED_BY", "HAS_OPTION", "DEFAULTS_TO", "SEMANTICALLY_MAPS_TO", "SIMILAR_TO", "OBSERVED_WITH", "CONFLICTS_WITH", "ALIAS_OF", "HAS_ROLE", "HAS_BEHAVIOR", "DRILLS_THROUGH_TO", "TOOLTIP_PAGE", "INTERACTS_WITH", "SYNCED_WITH", "FORMATS_BY"];

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
  if ((!Object.keys(types).length && legacy)) return { groups: { ...DEFAULT_PALETTE.groups }, types: { ...DEFAULT_PALETTE.types } };
  return { groups, types };
}

export function artifactColor(node, colors) {
  const palette = colors || normalizeColors();
  return palette.types[node.type] || palette.groups[artifactGroup(node)];
}

export function typeLabel(type) {
  return String(type || "Object").toLowerCase().replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase());
}

/**
 * Shorten a name in the middle so both its start and its end stay readable ("Sales amount … (LY)").
 * `measure(text)` returns a width in the same unit as `maxWidth`; without it the name is returned unchanged.
 */
export function middleEllipsis(text, maxWidth, measure) {
  const value = String(text ?? "");
  if (typeof measure !== "function" || measure(value) <= maxWidth) return value;
  const build = (kept) => {
    if (kept <= 0) return "…";
    const head = value.slice(0, Math.ceil(kept / 2)).trimEnd();
    const tail = value.slice(value.length - Math.floor(kept / 2)).trimStart();
    return `${head}…${tail}`;
  };
  let low = 0;
  let high = value.length - 1;
  while (low < high) {
    const middle = (low + high + 1) >> 1;
    if (measure(build(middle)) <= maxWidth) low = middle; else high = middle - 1;
  }
  return build(low);
}
