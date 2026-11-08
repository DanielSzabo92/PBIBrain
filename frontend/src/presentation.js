// UI boundaries: names and readable evidence, never storage identities or payloads.
const identity = /\b(?:model|report|table|column|measure|page|visual|workspace|semantic|edge|override|relationship|selector|conflict):[^\s,;"{}]+|\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b|\b[0-9a-f]{32,64}\b/gi;

export function formatDaxName(table, name) {
  if (!table && !name) return "";
  if (table && !name) {
    const match = String(table).match(/^(?:'([^']+)'|([A-Za-z0-9_ ]+))\[(.*)\]$/);
    if (match) {
      const tbl = match[1] || match[2];
      const col = match[3];
      return `'${tbl}'[${col}]`;
    }
    const clean = String(table).replace(/^'+|'+$/g, "");
    return `'${clean}'`;
  }
  if (!table && name) {
    const match = String(name).match(/^(?:'([^']+)'|([A-Za-z0-9_ ]+))\[(.*)\]$/);
    if (match) {
      const tbl = match[1] || match[2];
      const col = match[3];
      return `'${tbl}'[${col}]`;
    }
    return `[${name}]`;
  }
  const cleanTable = String(table).replace(/^'+|'+$/g, "");
  return `'${cleanTable}'[${name}]`;
}

export function formatObjectRef(ref) {
  if (ref == null || ref === "") return "";
  if (typeof ref !== "string") {
    if (typeof ref === "object") {
      if (ref.table && ref.name && ref.object_type !== "table") {
        return formatDaxName(ref.table, ref.name);
      }
      if (ref.name) {
        return ref.object_type === "table" ? `'${ref.name}'` : ref.name;
      }
    }
    return String(ref);
  }

  const str = ref.trim();

  // Pattern 1: URI/prefix style: measure:Sales/Net Sales, column:Sales/Amount, table:Sales
  const uriMatch = str.match(/^(?:model:[^/]+\/)?(table|column|measure|hierarchy|partition|calculation_item|calculation_group|relationship):([^/]+)(?:\/(.+))?$/i);
  if (uriMatch) {
    const [, kind, part1, part2] = uriMatch;
    const lowerKind = kind.toLowerCase();
    if (lowerKind === "table" || lowerKind === "calculation_group") {
      return `'${part1}'`;
    }
    if (part2) {
      return formatDaxName(part1, part2);
    }
    return `'${part1}'`;
  }

  // Pattern 2: Table[Measure] without single quotes
  const daxMatch = str.match(/^([A-Za-z0-9_ ]+)\[(.*)\]$/);
  if (daxMatch) {
    return `'${daxMatch[1]}'[` + daxMatch[2] + `]`;
  }
  if (/^'[^']+'\[.*\]$/.test(str)) {
    return str;
  }

  // Pattern 3: row-* slug from Dev Center compare rows (e.g. row-gross-margin, row-net-sales, row-customer)
  const rowMatch = str.match(/^row-(.+)$/);
  if (rowMatch) {
    return rowMatch[1]
      .split("-")
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
      .join(" ");
  }

  // Pattern 4: relationship-*
  const relMatch = str.match(/^relationship-(.+)$/i);
  if (relMatch) {
    const label = relMatch[1]
      .split("-")
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
      .join(" ");
    return `Relationship (${label})`;
  }

  return str;
}

const PHRASE_MAPPINGS = [
  [/Report bindings of the scanned reports \(USES, FILTERS and page bindings\)\.?/gi, "Field usage and visual filters across scanned reports."],
  [/USES, FILTERS and page bindings/gi, "field usage and visual filters"],
  [/SCANNER_COVERAGE_UNKNOWN/gi, "Scanner coverage unknown: metadata incomplete for this source"],
  [/Explicit modification target/gi, "Directly modified object"],
  [/Consumes potentially affected object/gi, "Uses an object affected by this change"],
];

function sanitizePhrases(text) {
  let cleaned = text;
  for (const [regex, replacement] of PHRASE_MAPPINGS) {
    cleaned = cleaned.replace(regex, replacement);
  }
  return cleaned;
}

export function readableText(value, nodes = []) {
  if (value == null || value === "") return "";
  if (typeof value === "string") {
    if (/^[\[{]/.test(value.trim())) {
      try { return readableText(JSON.parse(value), nodes); } catch { /* A formula can start with [. */ }
    }
    const named = nodes.find((node) => node.id === value);
    if (named?.name && named.name !== value) return readableText(named.name);
    const replaced = value.replace(identity, (id) => nodes.find((node) => node.id === id)?.name || "Referenced object");
    return sanitizePhrases(replaced);
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
export const statusLabel = (status) => ({ factual: "Factual", candidate: "Inferred", approved: "Approved", rejected: "Rejected", overridden: "Edited", stale: "Needs attention" }[status] || "Factual");

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
  // Issue #10: data sources and the queries that read them.
  connector: "Connector", server: "Server", database: "Database", schema: "Schema", object: "Source object",
  path: "Path", url: "URL", workspace_id: "Workspace ID", lakehouse_id: "Lakehouse ID", dataflow_id: "Dataflow ID",
  source_parameters: "Parameters", parameter_value: "Parameter value", not_checked_detail: "Not read because",
};
export function publicProperties(node) {
  return Object.entries(propertyLabels).flatMap(([key, label]) => {
    const value = node?.[key] ?? node?.properties?.[key];
    return value == null || value === "" ? [] : [[label, readableText(value)]];
  }).filter(([label], index, list) => list.findIndex(([name]) => name === label) === index);
}

export function suggestionLabel(item) {
  const kind = item.assertion_type || item.properties?.assertion_type || item.item?.assertion_type || item.item?.properties?.assertion_type || item.type;
  const label = { ROLE: "Table role", BUSINESS_CONCEPT: "Meaning", BEHAVIOR: "Behavior", ALIAS: "Alias", SELECTOR: "Selector" }[kind] || "Suggestion";
  const rawValue = item.value ?? item.meaning ?? item.properties?.meaning ?? item.item?.meaning ?? item.item?.properties?.meaning;
  const value = kind === "ROLE" && String(rawValue).toLowerCase() === "fact" ? "Fact table" : readableText(rawValue);
  return `${label}: ${value || "Needs review"}`;
}


const NOT_CHECKED_REASONS = {
  model_not_in_project: "the semantic model is not a source of this project",
  m_not_read: "the Power Query (M) source was not read",
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
    const detail = node.not_checked_detail || properties.not_checked_detail;
    return { kind: "not_checked", label: "Not checked", title: `Not checked: ${reason}${detail ? ` (${detail})` : ""}${workspace ? ` (workspace ${workspace})` : ""}` };
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

/** Detects whether an error indicates the backend service is offline or unreachable. */
export function isBackendUnreachableError(err) {
  if (!err) return false;
  if (err?.status === 502 || err?.status === 503 || err?.status === 504) return true;
  const msg = typeof err === "string" ? err : err?.message || String(err);
  return /failed to fetch|fetch failed|networkerror|network request failed|econnrefused|connection refused|load failed|could not connect|cannot connect|unreachable/i.test(msg);
}
