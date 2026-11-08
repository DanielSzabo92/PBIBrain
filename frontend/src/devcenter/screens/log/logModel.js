// Pure helpers of the Log tab (UI design 4.7, step U9).
// No React here, so that the node unit tests can import this module.
import { COPY, t } from "../../copy.js";
import { formatObjectRef } from "../../phrases.js";
import { kindText, timeText } from "../agent/agentModel.js";

export const LOG_PAGE = 50;

// The actions of the Action filter: each top-level "log.action.<name>" key of the copy.
export const LOG_ACTIONS = Object.freeze(
  Object.keys(COPY)
    .filter((key) => /^log\.action\.[a-z_]+$/.test(key))
    .map((key) => key.slice("log.action.".length)),
);

export function authorText(entry) {
  if (entry?.author === "agent") return t("log.author.agent", { client: entry.mcp_client || "Agent" });
  return t("log.author.user");
}

export function actionText(entry) {
  const action = entry?.action ?? "";
  const key = `log.action.${action}`;
  if (COPY[key] === undefined) return action;
  if (action === "proposal_submit") {
    const kind = entry?.after?.kind ?? entry?.kind ?? "merge_choice";
    return t(key, { kind: kindText(kind) });
  }
  return t(key);
}

// Before and After formatted without raw JSON syntax. An empty value shows "None".
export function valueText(value) {
  if (value === null || value === undefined || value === "") return t("shared.empty_value");
  if (typeof value === "string") return formatObjectRef(value);
  if (typeof value === "boolean") return value ? "True" : "False";
  if (typeof value === "number") return String(value);
  if (Array.isArray(value)) {
    return value.map((item) => valueText(item)).join(", ");
  }
  if (typeof value === "object") {
    if ("choice" in value || "kind" in value) {
      const choice = value.choice || value.kind;
      if (choice === "donor") return value.source_id ? `Take from ${value.source_id}` : "Take donor";
      if (choice === "target" || choice === "keep") return "Keep target";
      if (choice === "both") return "Keep both";
      if (choice === "ignore") return "Do not copy";
      if (choice === "rename") return value.name ? `Rename to '${value.name}'` : "Rename";
      if (choice === "edit") return "Edit";
      if (choice === "delete") return "Delete";
      if (choice === "take_properties") return "Take properties";
      return String(choice).replace(/_/g, " ");
    }
    if ("policy" in value) {
      if (value.policy === "block") return "Block removal";
      if (value.policy === "cascade") return "Remove dependents";
      if (value.policy === "repoint") return value.repoint_target ? `Repoint to ${formatObjectRef(value.repoint_target)}` : "Repoint";
      return `Policy: ${value.policy}`;
    }
    if (value.expression !== undefined) return value.expression;
    const entries = Object.entries(value);
    if (entries.length === 0) return t("shared.empty_value");
    return entries
      .map(([k, v]) => `${k.replace(/_/g, " ")}: ${typeof v === "object" ? JSON.stringify(v) : formatObjectRef(String(v))}`)
      .join(", ");
  }
  return String(value);
}

export function targetText(target) {
  if (target === null || target === undefined || target === "") return t("shared.empty_value");
  return Array.isArray(target) ? target.map(formatObjectRef).join(", ") : formatObjectRef(String(target));
}

// One target link opens the row. A list of targets has no link.
export function targetRowKey(target) {
  return typeof target === "string" && target ? target : null;
}

export { timeText };

// The params of GET log for the filters and the number of loaded pages.
export function logParams({ author = "all", action = "all", target = "", proposalId = null, pages = 1 } = {}) {
  const params = { limit: LOG_PAGE * Math.max(1, pages) };
  if (author !== "all") params.author = author;
  if (action !== "all") params.action = action;
  if (String(target).trim()) params.target = String(target).trim();
  if (proposalId) params.proposalId = proposalId;
  return params;
}
