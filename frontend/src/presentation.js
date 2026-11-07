// UI boundaries: names and readable evidence, never storage identities or payloads.
const identity = /\b(?:model|report|table|column|measure|page|visual|workspace|semantic|edge|override|relationship|selector|conflict):[^\s,;"{}]+|\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b|\b[0-9a-f]{32,64}\b/gi;

export function readableText(value, nodes = []) {
  if (value == null || value === "") return "";
  if (typeof value === "string") {
    if (/^[\[{]/.test(value.trim())) {
      try { return readableText(JSON.parse(value), nodes); } catch { /* A formula can start with [. */ }
    }
    const named = nodes.find((node) => node.id === value);
    if (named?.name && named.name !== value) return readableText(named.name);
    return value.replace(identity, (id) => nodes.find((node) => node.id === id)?.name || "Referenced object");
  }
  if (Array.isArray(value)) return [...new Set(value.map((item) => readableText(item, nodes)).filter(Boolean))].join(" · ");
  if (typeof value === "object") {
    // Evidence comes from several extractors. Keep their explanation, not transport metadata.
    for (const key of ["evidence", "reason", "message", "description", "text", "expression", "meaning", "value", "name"]) {
      const text = readableText(value[key], nodes);
      if (text) return text;
    }
    return Object.entries(value).filter(([key]) => /^(behavior|operation|function|column|table|label|role|concept|detail|summary)$/.test(key))
      .map(([key, item]) => `${key[0].toUpperCase()}${key.slice(1)}: ${readableText(item, nodes)}`).join(" · ");
  }
  return typeof value === "boolean" ? value ? "Yes" : "No" : String(value);
}

export function objectName(node) {
  if (node?.type === "VISUAL") {
    const properties = node.properties || {};
    const title = node.title || properties.title;
    if (title) return String(title);
    const display = node.displayName || properties.display_name || properties.displayName;
    if (display) return String(display);
    const name = node.name;
    if (name && name !== node.source_id && !/^(?:visual[_:]|[0-9a-f]{16,}$)/i.test(name)) return String(name);
    const kind = visualType(node);
    if (kind !== "Visual") return kind;
    return String(name || node.source_id || node.id || "Unnamed visual");
  }
  return readableText(node?.name) || "Unnamed object";
}

export function visualType(node) {
  const value = node?.visual_type || node?.properties?.visual_type || node?.visualType || node?.properties?.visualType;
  return value ? String(value).replace(/([a-z\d])([A-Z])/g, "$1 $2").replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase()) : "Visual";
}
export const statusLabel = (status) => ({ factual: "From source", candidate: "Suggested", approved: "Approved", rejected: "Rejected", overridden: "Edited", stale: "Needs attention" }[status] || "From source");

export function objectScope(node, nodes = []) {
  if (!node) return "Source object unavailable";
  const byId = new Map(nodes.map((item) => [item.id, item]));
  const parents = [];
  const visited = new Set([node.id]);
  let parentId = node.properties?.table_id || node.properties?.parent_id || node.properties?.calculation_group_id;
  while (parentId && !visited.has(parentId)) {
    visited.add(parentId);
    const parent = byId.get(parentId);
    if (!parent) break;
    parents.unshift(objectName(parent));
    parentId = parent.properties?.parent_id;
  }
  const roots = [node.model_id, node.report_id].filter((id) => id && !visited.has(id));
  return [...roots.map((id) => byId.has(id) ? objectName(byId.get(id)) : "Scope unavailable"), ...parents].join(" / ") || (node.type === "MODEL" ? "Project model" : "Scope unavailable");
}

export function scopeChoices(overview, kind) {
  return (overview?.[`${kind}_objects`] || overview?.[`${kind}_ids`] || []).map((item, index) => {
    const id = typeof item === "string" ? item : item.id;
    return { id, name: typeof item === "object" && item.name ? objectName(item) : `${kind === "model" ? "Model" : "Report"} ${index + 1}` };
  }).filter((item) => item.id);
}

const propertyLabels = {
  data_type: "Data type", dataType: "Data type", format_string: "Format", formatString: "Format",
  display_folder: "Display folder", displayFolder: "Display folder", is_hidden: "Hidden", isHidden: "Hidden",
  summarize_by: "Summarize by", summarizeBy: "Summarize by", visual_type: "Visual type", visualType: "Visual type",
  cardinality: "Cardinality", cross_filtering_behavior: "Filter direction", is_active: "Active",
};
export function publicProperties(node) {
  return Object.entries(propertyLabels).flatMap(([key, label]) => {
    const value = node?.[key] ?? node?.properties?.[key];
    return value == null || value === "" ? [] : [[label, readableText(value)]];
  }).filter(([label], index, list) => list.findIndex(([name]) => name === label) === index);
}

export function suggestionLabel(item) {
  const kind = item.assertion_type || item.properties?.assertion_type || item.item?.assertion_type || item.item?.properties?.assertion_type || item.type;
  const label = { ROLE: "Role", BUSINESS_CONCEPT: "Meaning", BEHAVIOR: "Behavior", ALIAS: "Alias", SELECTOR: "Selector" }[kind] || "Suggestion";
  return `${label}: ${readableText(item.value ?? item.meaning ?? item.properties?.meaning ?? item.item?.meaning ?? item.item?.properties?.meaning) || "Needs review"}`;
}

const NOT_CHECKED_REASONS = {
  model_not_in_project: "the semantic model is not a source of this project",
  cloud_service_not_available: "the cloud item was not read; open the project in the app and sign in",
  sign_in_required: "sign in with Microsoft to read the cloud item",
  cloud_read_failed: "the Power BI service did not give the item",
  report_not_readable: "the report definition is not readable",
};

/**
 * Where a model or report comes from (issue #9): a cloud workspace, or "not checked" when the project scan
 * could not read it. Null for local objects, so local projects look as before.
 */
export function originNote(node) {
  if (!node) return null;
  const properties = node.properties || {};
  const status = node.check_status || properties.check_status;
  const workspace = node.workspace_name || properties.workspace_name || properties.connection_workspace;
  if (status === "not_checked") {
    const reason = NOT_CHECKED_REASONS[node.not_checked_reason || properties.not_checked_reason] || "the item was not read";
    return { kind: "not_checked", label: "Not checked", title: `Not checked: ${reason}${workspace ? ` (workspace ${workspace})` : ""}` };
  }
  if ((node.origin || properties.origin) === "cloud") {
    return { kind: "cloud", label: workspace || "Cloud", title: `Cloud${workspace ? ` · workspace ${workspace}` : ""}` };
  }
  return null;
}

/** Sort key that keeps local roots first, then each cloud workspace together. */
export function workspaceKey(node) {
  const properties = node?.properties || {};
  return String(node?.workspace_name || properties.workspace_name || "");
}
