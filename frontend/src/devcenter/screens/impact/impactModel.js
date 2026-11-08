// Pure helpers of the Impact tab (UI design 4.5, 5.3, 7.3, step U8). No React here.
import { t, tn } from "../../copy.js";
import { formatObjectRef } from "../../phrases.js";

export const PAGE_SIZE = 500;
export const GRAPH_LIMIT = 150;
export const AREA_STEP = 20;
export const GROUPS = ["breaks", "needs", "offers"];
export const VIEWS = ["table", "graph", "wireframe"];

// Sort order of severities: blocking, severity, name (UI design 4.5).
export const SEVERITY_ORDER = [
  "breaks", "missing", "name_clash", "changes_value", "needs_review", "will_be_added", "mapped", "not_changed_by_this_plan",
];
const INFORMATION_SEVERITIES = new Set(["mapped", "not_changed_by_this_plan"]);

// The primary action is the first allowed action of this list. All other allowed actions go in the row menu.
export const PRIMARY_ORDER = ["include_in_rewrite", "set_policy_repoint", "set_policy_cascade", "map_to_target", "add_from_donor"];
export const BULK_ACTIONS = ["include_in_rewrite", "add_from_donor"];
export const POLICY_ACTIONS = new Set(["set_policy_block", "set_policy_cascade", "set_policy_repoint"]);

const ACTION_KEYS = {
  include_in_rewrite: "impact.action.include",
  set_policy_repoint: "impact.action.repoint",
  set_policy_cascade: "impact.action.cascade",
  set_policy_block: "impact.action.keep_blocked",
  add_from_donor: "impact.action.add_from_donor",
  map_to_target: "impact.action.map",
  drop_added_object: "impact.action.drop_added",
  remove_field: "impact.action.remove_field",
};

export function actionLabel(action) {
  return ACTION_KEYS[action] ? t(ACTION_KEYS[action]) : action;
}

// Status rule: Blocking = blocking flag (a possible item never blocks);
// Information = severity "mapped" or "not changed by this plan"; Warning = all others.
export function itemStatus(item) {
  if (item?.blocking && item.certainty !== "possible") return "blocking";
  if (INFORMATION_SEVERITIES.has(item?.severity)) return "information";
  return "warning";
}

export const STATUS_TONE = { blocking: "bad", warning: "warn", information: "info" };

export function statusLabel(status) {
  return t(`impact.status.${status}`);
}

export function severityLabel(severity) {
  if (severity === "not_changed_by_this_plan") return t("impact.tag.not_changed");
  const text = t(`impact.severity.${severity}`);
  return text.startsWith("impact.") ? severity : text;
}

function severityRank(severity) {
  const index = SEVERITY_ORDER.indexOf(severity);
  return index < 0 ? SEVERITY_ORDER.length : index;
}

export function compareItems(a, b) {
  const blocking = Number(itemStatus(b) === "blocking") - Number(itemStatus(a) === "blocking");
  if (blocking) return blocking;
  const severity = severityRank(a.severity) - severityRank(b.severity);
  if (severity) return severity;
  return String(a.impacted_object?.name ?? "").localeCompare(String(b.impacted_object?.name ?? ""), undefined, { sensitivity: "base", numeric: true });
}

export function sortItems(items) {
  return [...(items ?? [])].sort(compareItems);
}

export function primaryAction(item) {
  const allowed = item?.allowed_actions ?? [];
  return PRIMARY_ORDER.find((action) => allowed.includes(action)) ?? null;
}

export function menuActions(item) {
  const primary = primaryAction(item);
  return (item?.allowed_actions ?? []).filter((action) => action !== primary);
}

// Group control: the default is the first group with blocking items, else Breaks.
export function defaultGroup(blockingByDirection) {
  if ((blockingByDirection?.breaks ?? 0) > 0) return "breaks";
  if ((blockingByDirection?.needs ?? 0) > 0) return "needs";
  return "breaks";
}

export function groupOptions({ totals = {}, blocking = {}, offers = 0 }) {
  return GROUPS.map((group) => {
    const n = group === "offers" ? offers : totals[group] ?? 0;
    const m = group === "offers" ? 0 : blocking[group] ?? 0;
    return { value: group, label: `${t(`impact.group.${group}`)} (${n})`, blocking: m };
  });
}

// Each changed filter value goes into the GET impact query (UC29). "all" means no filter.
export function impactQuery({ scope, group, includeProposals, filters }) {
  const query = { target: scope || "plan" };
  if (includeProposals) query.includeProposals = true;
  if (group === "breaks" || group === "needs") query.direction = group;
  if (filters?.blockingOnly) query.blocking = true;
  for (const [name, param] of [["severity", "severity"], ["certainty", "certainty"], ["source", "source"], ["type", "objectType"]]) {
    const value = filters?.[name];
    if (value && value !== "all") query[param] = value;
  }
  if (filters?.q) query.q = filters.q;
  return query;
}

export const EMPTY_FILTERS = Object.freeze({ blockingOnly: false, severity: "all", certainty: "all", source: "all", type: "all", q: "" });

export function hasFilters(filters) {
  return Boolean(filters && (filters.blockingOnly || filters.q || ["severity", "certainty", "source", "type"].some((name) => filters[name] && filters[name] !== "all")));
}

// The toast after an action: "1 item resolved. <n> blocking left."
export function resolvedText(applied, blockingLeft, failed = 0) {
  const text = tn("impact.toast", applied, { m: blockingLeft });
  return failed > 0 ? `${text} ${tn("impact.bulk.failed", failed)}` : text;
}

// An item that comes only from an open proposal: the switch is on and its cause row has an open proposal.
export function proposalTargets(session) {
  return new Set((session?.proposals?.open ?? []).map((proposal) => proposal.target_id).filter(Boolean));
}

export function isProposed(item, includeProposals, targets) {
  return Boolean(includeProposals && targets?.has(item?.cause));
}

export function placeText(item, session) {
  const sourceId = item?.impacted_object?.source_id;
  if (!sourceId) return t("impact.place.other");
  return (session?.sources ?? []).find((source) => source.source_id === sourceId)?.display_name ?? sourceId;
}

export function otherPathsText(n) {
  return n > 0 ? tn("impact.other_paths", n) : "";
}

export function shortestPathText(item) {
  return (item?.path ?? []).map((step) => formatObjectRef(step.name || step.object_id)).join(" > ");
}

// Completeness strip (UI design 4.5): the entries of each area, 20 at a time.
const AREAS = [
  ["not_checked_object_types", "impact.area.object_types"],
  ["unresolved_bindings", "impact.area.bindings"],
  ["unreadable_reports", "impact.area.remote_reports"],
  ["bookmarks", "impact.area.bookmarks"],
  ["possible_only_areas", "impact.area.possible"],
];

function entryText(entry) {
  if (entry === null || entry === undefined) return "";
  if (typeof entry === "string") return formatObjectRef(entry);
  return formatObjectRef(entry.name ?? entry.title ?? entry.object_id ?? entry.id ?? JSON.stringify(entry));
}

export function completenessEntries(completeness) {
  const entries = [];
  for (const [field, labelKey] of AREAS) {
    for (const entry of completeness?.[field] ?? []) entries.push({ area: field, label: t(labelKey), text: entryText(entry) });
  }
  return entries;
}

export function completenessState(completeness) {
  const entries = completenessEntries(completeness);
  const complete = completeness?.status !== "incomplete";
  return {
    complete,
    tone: complete ? "ok" : "warn",
    label: complete ? t("impact.completeness.complete") : tn("impact.completeness.incomplete", entries.length),
    help: complete ? t("impact.completeness.complete.help") : t("impact.completeness.incomplete.help"),
    entries,
  };
}

// Default closed, but open when incomplete and the user did not close it in this session.
export function completenessDefaultOpen(completeness, closedByUser) {
  return completeness?.status === "incomplete" && !closedByUser;
}

export function visibleEntries(entries, shown) {
  return { list: entries.slice(0, shown), more: entries.length > shown };
}

// Graph (UI design 4.5): only the union of the shortest paths of the filtered items.
// The rank of a node is its smallest step index on a path. The impacted object is the last node of its path.
export function buildImpactGraph(items) {
  const nodes = new Map();
  const edges = new Map();
  const addNode = (step, rank) => {
    const current = nodes.get(step.object_id);
    if (current) {
      current.rank = Math.min(current.rank, rank);
      return current;
    }
    const node = { id: step.object_id, name: step.name, type: step.type, rank, itemIds: [], status: "path" };
    nodes.set(step.object_id, node);
    return node;
  };
  for (const item of items ?? []) {
    const path = [...(item.path ?? [])];
    const target = item.impacted_object;
    if (target && (!path.length || path[path.length - 1].object_id !== target.object_id)) {
      path.push({ object_id: target.object_id, name: target.name, type: target.object_type, edge_phrase: "uses" });
    }
    path.forEach((step, index) => addNode(step, index));
    for (let index = 1; index < path.length; index += 1) {
      const from = path[index - 1].object_id;
      const to = path[index].object_id;
      if (from === to) continue;
      const id = `${from}->${to}`;
      const edge = edges.get(id) ?? { id, from_id: from, to_id: to, type: "IMPACT", certain: false };
      edge.certain = edge.certain || item.certainty === "certain";
      edges.set(id, edge);
    }
    if (target) {
      const node = nodes.get(target.object_id);
      node.itemIds.push(item.id);
      const status = itemStatus(item);
      const order = ["path", "information", "warning", "blocking"];
      if (order.indexOf(status) > order.indexOf(node.status)) node.status = status;
    }
  }
  return { nodes: [...nodes.values()], edges: [...edges.values()] };
}

// Tab order of the graph: rank order, then top to bottom, then name.
export function graphTabOrder(placed) {
  return [...placed].sort((a, b) => a.node.rank - b.node.rank || a.position.y - b.position.y || a.node.name.localeCompare(b.node.name));
}

// Arrow keys along edges: Right next step, Left previous step, Up and Down the same rank.
export function graphKeyTarget(graph, ordered, nodeId, key) {
  const position = (id) => ordered.findIndex((entry) => entry.node.id === id);
  const sorted = (ids) => ids.sort((a, b) => position(a) - position(b));
  if (key === "ArrowRight") return sorted(graph.edges.filter((edge) => edge.from_id === nodeId).map((edge) => edge.to_id))[0] ?? null;
  if (key === "ArrowLeft") return sorted(graph.edges.filter((edge) => edge.to_id === nodeId).map((edge) => edge.from_id))[0] ?? null;
  if (key === "ArrowUp" || key === "ArrowDown") {
    const rank = ordered.find((entry) => entry.node.id === nodeId)?.node.rank;
    const same = ordered.filter((entry) => entry.node.rank === rank).map((entry) => entry.node.id);
    const index = same.indexOf(nodeId);
    const next = key === "ArrowDown" ? index + 1 : index - 1;
    return same[next] ?? null;
  }
  return null;
}

export function graphNodeLabel(node) {
  const status = node.status === "blocking" ? t("impact.graph.node.blocking")
    : node.status === "warning" ? t("impact.graph.node.warning")
      : node.status === "information" ? t("impact.graph.node.information")
        : t("impact.graph.node.path");
  return t("impact.graph.node", { type: node.type, name: node.name, status, n: node.rank });
}

// Wireframe (UI design 4.5, 7.3): each visual shows one status, in this order.
export const WIRE_STATUS_ORDER = ["removed", "breaks", "changes", "new", "not_checked", "unchanged"];

export function wireStatusWord(status) {
  return t(`impact.wireframe.status.${status}`);
}

// Reading order: rows from top to bottom (a visual that starts within 24 px of the row top is in the row), then left to right.
export function readingOrder(visuals) {
  const byTop = [...(visuals ?? [])].sort((a, b) => a.y - b.y || a.x - b.x);
  const rows = [];
  for (const visual of byTop) {
    const row = rows[rows.length - 1];
    if (row && visual.y - row.top < 24) row.list.push(visual);
    else rows.push({ top: visual.y, list: [visual] });
  }
  return rows.flatMap((row) => row.list.sort((a, b) => a.x - b.x));
}

export function wireVisualLabel(visual) {
  return t("impact.wireframe.visual", { type: visual.type, title: visual.title, status: wireStatusWord(visual.status) });
}

// The report trigger: the target after apply, donors now.
export function reportOptions(session, targetReportName) {
  const options = [];
  if (targetReportName) options.push({ value: "target", label: t("impact.wireframe.target", { report: targetReportName }) });
  for (const source of session?.sources ?? []) {
    if (source.role === "target") continue;
    if (!["pbip", "pbir_report", "pbix"].includes(source.kind)) continue;
    options.push({ value: source.source_id, label: t("impact.wireframe.donor", { report: source.display_name }) });
  }
  return options;
}

// Offers (UI design 4.5): a tree by donor report, page, visual and filter. Bookmarks are information only.
export function offerTree(offers) {
  const donors = new Map();
  for (const offer of offers ?? []) {
    const key = offer.source_id;
    if (!donors.has(key)) donors.set(key, { sourceId: key, sourceName: offer.source_name || key, pages: new Map(), bookmarks: [] });
    const donor = donors.get(key);
    if (offer.kind === "bookmark" || offer.information_only) {
      donor.bookmarks.push(offer);
      continue;
    }
    const pageName = offer.page_name || offer.name;
    if (!donor.pages.has(pageName)) donor.pages.set(pageName, { name: pageName, items: [] });
    donor.pages.get(pageName).items.push(offer);
  }
  return [...donors.values()].map((donor) => ({ ...donor, pages: [...donor.pages.values()] }));
}

// The page checkbox: checked, not checked, or mixed ("indeterminate").
export function pageCheckState(items) {
  const selectable = (items ?? []).filter((offer) => !offer.information_only);
  if (!selectable.length) return false;
  const selected = selectable.filter((offer) => offer.selected).length;
  if (selected === 0) return false;
  return selected === selectable.length ? true : "indeterminate";
}

// The offers that change when the user toggles a page checkbox.
export function pageToggleTargets(items, checked) {
  const want = checked === true;
  return (items ?? []).filter((offer) => !offer.information_only && Boolean(offer.selected) !== want);
}

// Selected visuals that need missing fields add Needs.
export function missingFieldCount(offers) {
  const fields = new Set();
  for (const offer of offers ?? []) if (offer.selected) for (const field of offer.missing_fields ?? []) fields.add(field);
  return fields.size;
}

export function offerLine(offer) {
  const ref = (offer.references ?? [])[0];
  const objName = ref ? formatObjectRef(ref) : t("shared.not_known");
  return t("impact.offers.item", { visual_type: t(`impact.offers.kind.${offer.kind}`), object: objName });
}

// Removal policy dialog (UI design 5.3, 8.4).
export function policyConfirm(policy, cascadeCount) {
  if (policy === "cascade") return { text: t("row.policy.cascade.confirm", { n: cascadeCount }), variant: "destructive" };
  if (policy === "repoint") return { text: t("row.policy.repoint.confirm"), variant: "default" };
  return { text: t("row.policy.block.confirm"), variant: "default" };
}

export function canConfirmPolicy(policy, repointTarget) {
  return policy !== "repoint" || Boolean(repointTarget);
}

const EFFECT_KEYS = {
  remove_object: "row.policy.cascade.removed",
  remove_field_from_visual: "row.policy.cascade.field_removed",
  remove_visual: "row.policy.cascade.visual_removed",
  remove_filter: "row.policy.cascade.filter_removed",
};

export function effectText(effect) {
  return EFFECT_KEYS[effect] ? t(EFFECT_KEYS[effect]) : effect;
}

export function policyFromAction(action) {
  return POLICY_ACTIONS.has(action) ? action.replace("set_policy_", "") : null;
}

// The virtual window of the table: rows in view plus an overscan on each side (budget P4: 80 rows or fewer).
export function virtualWindow({ scrollTop, height, rowHeight, total, overscan = 8 }) {
  const first = Math.max(0, Math.floor(scrollTop / rowHeight) - overscan);
  const last = Math.min(total, Math.ceil((scrollTop + height) / rowHeight) + overscan);
  return { first, last };
}

export function pagesFor({ first, last }) {
  const pages = new Set();
  if (last <= first) return [0];
  for (let page = Math.floor(first / PAGE_SIZE); page <= Math.floor((last - 1) / PAGE_SIZE); page += 1) pages.add(page);
  return [...pages];
}
