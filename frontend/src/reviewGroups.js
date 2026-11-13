// Review suggestions grouped by pattern: one rule, one evidence basis, one object type.
// A project of 2,400 measures yields 2,400 "meaning from the description" suggestions that
// differ only in the object; a reviewer decides the pattern once and opens the rows for exceptions.

const KIND_NAMES = { ALIAS: "Other name", ROLE: "Table role", BUSINESS_CONCEPT: "Meaning", SEMANTICALLY_MAPS_TO: "Meaning", BEHAVIOR: "Behaviour", SELECTOR: "Selector" };
const BASIS_NAMES = { object_name: "from the name", name: "from the name", description: "from the description", dax_ast: "from the formula", dax_analysis: "from the formula" };
const TYPE_PLURALS = { MEASURE: "measures", COLUMN: "columns", TABLE: "tables", VISUAL: "visuals", PAGE: "pages", REPORT: "reports", SEMANTIC_MODEL: "models", RELATIONSHIP: "relationships" };

export function reviewKind(item) {
  return item.assertion_type || item.properties?.assertion_type || item.item?.assertion_type || item.item?.properties?.assertion_type || item.type || "";
}

export function reviewBasis(item) {
  return item.item?.properties?.candidate_source || item.properties?.candidate_source || item.source || "";
}

function plural(type) {
  return TYPE_PLURALS[type] || `${String(type || "object").toLowerCase().replaceAll("_", " ")}s`;
}

/**
 * Groups for the queue, largest first. Conflicts and removed-target decisions are each one
 * group that cannot be decided in bulk (`bulk: false`): every one of them needs a look.
 */
export function groupReviewItems(items, targetOf) {
  const groups = new Map();
  for (const item of items) {
    const node = targetOf(item);
    const special = item.issue === "conflict" || item.issue === "stale" ? item.issue : "";
    const kind = special || reviewKind(item);
    const basis = special ? "" : BASIS_NAMES[reviewBasis(item)] || "from a rule";
    const type = node?.type || "";
    const key = `${kind}|${basis}|${type}`;
    let group = groups.get(key);
    if (!group) {
      const title = special === "conflict" ? "Conflicts" : special === "stale" ? "Decisions whose object is gone" : `${KIND_NAMES[kind] || "Suggestion"} ${basis}`;
      group = { key, kind, basis, type, title, scope: type ? plural(type) : "", bulk: !special, items: [], low: 1, high: 0, names: new Set() };
      groups.set(key, group);
    }
    group.items.push(item);
    const score = Number(item.confidence ?? item.properties?.confidence ?? 0) || 0;
    if (score < group.low) group.low = score;
    if (score > group.high) group.high = score;
    if (node?.name) group.names.add(node.name);
  }
  return [...groups.values()]
    .map((group) => ({ ...group, names: group.names.size }))
    .sort((a, b) => Number(a.bulk) - Number(b.bulk) || b.items.length - a.items.length || a.key.localeCompare(b.key));
}

/** Rows are grouped by default once the queue is too long to read as a list. */
export const GROUP_ABOVE = 200;
