// Helper functions for naming rules (UI design section 4.8 and 13).
import { t } from "../../copy.js";

export const OBJECT_TYPE_LABELS = Object.freeze({
  measure: "Measures",
  data_column: "Columns",
  calculated_column: "Calculated columns",
  calculated_table: "Calculated tables",
  table: "Tables",
  hierarchy: "Hierarchies",
  calculation_group: "Calculation groups",
});

const STATUS_BADGE = Object.freeze({
  proposed: { tone: "info", key: "rules.status.proposed" },
  confirmed: { tone: "ok", key: "rules.status.confirmed" },
  rejected: { tone: "plain", key: "rules.status.rejected" },
});

export function ruleStatusProps(status) {
  const item = STATUS_BADGE[status] ?? STATUS_BADGE.rejected;
  return { tone: item.tone, label: t(item.key) };
}

export function formatScope(scope) {
  if (!scope) return "All tables";
  const parts = [];
  if (scope.table) parts.push(`Table: ${scope.table}`);
  if (scope.display_folder) parts.push(`Display folder: ${scope.display_folder}`);
  if (scope.format_kind) parts.push(`Format: ${scope.format_kind}`);
  if (scope.name_prefix) parts.push(`Prefix: ${scope.name_prefix}`);
  return parts.length > 0 ? parts.join(", ") : "All tables";
}

export function formatSupport(rule) {
  if (rule.origin === "user" || !rule.support || rule.support.total === 0) {
    return t("rules.support.none");
  }
  const typeLabel = (OBJECT_TYPE_LABELS[rule.object_type] ?? "objects").toLowerCase();
  return t("rules.support", {
    n: rule.support.count,
    m: rule.support.total,
    type: typeLabel,
  });
}

export function formatPreviewText(objectType, scope, check) {
  const typeLabel = OBJECT_TYPE_LABELS[objectType] ?? "Objects";
  const kind = check?.kind;
  const value = check?.value || "...";
  let checkText = "";
  if (kind === "prefix") checkText = `start with "${value}"`;
  else if (kind === "suffix") checkText = `end with "${value}"`;
  else if (kind === "unit_word") checkText = `end with the unit word "${value}"`;
  else if (kind === "letter_case") checkText = `use ${value} case`;
  else if (kind === "separator") checkText = `use ${value} separator`;
  else if (kind === "folder_by_type") checkText = `live in ${check.folder || "display folder"} "${value}"`;
  else if (kind === "regex") checkText = `match the pattern "${value}"`;
  else checkText = `follow ${kind || "rule"}`;

  const scopeText = formatScope(scope);
  return `${typeLabel} (${scopeText}) ${checkText}.`;
}

export function groupRulesByType(rules) {
  const groups = new Map();
  for (const rule of rules) {
    const key = rule.object_type;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(rule);
  }
  return Array.from(groups.entries()).map(([objectType, items]) => ({
    objectType,
    label: OBJECT_TYPE_LABELS[objectType] ?? objectType,
    rules: items,
  }));
}

export function ruleCounts(rules) {
  let proposed = 0;
  let confirmed = 0;
  let rejected = 0;
  for (const rule of rules) {
    if (rule.status === "proposed") proposed += 1;
    else if (rule.status === "confirmed") confirmed += 1;
    else if (rule.status === "rejected") rejected += 1;
  }
  return { proposed, confirmed, rejected, all: rules.length };
}
