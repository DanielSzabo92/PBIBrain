// The reads that each JS API call makes stale (UI design section 10, "Refresh").
// After a call, the store fetches the visible reads of INVALIDATES[method] at once
// and marks the other cached reads stale. Each method of jsapi-methods.json must have an entry.
// To add a method: add one line to INVALIDATES. Keep the lines in the order of jsapi-methods.json.

export const RESOURCE_KEYS = Object.freeze([
  "session",
  "sessions",
  "compareRows",
  "rowDiff",
  "displayFolders",
  "plan",
  "impact",
  "impactPaths",
  "removal",
  "wireframe",
  "namingRules",
  "applyPreview",
  "applyLast",
  "log",
]);

const ALL = RESOURCE_KEYS;

// Each change of the session changes its revision, the session list (updated time), and the log.
const change = (...keys) => Object.freeze(["session", "sessions", "log", ...keys]);

const CHOICE = ["compareRows", "plan", "impact", "impactPaths", "removal", "wireframe", "applyPreview"];
const RULES = ["namingRules", "compareRows", "plan", "applyPreview"];

export const INVALIDATES = Object.freeze({
  session_create: ALL,
  session_open: ALL,
  session_close: ALL,
  source_add: ALL,
  source_remove: ALL,
  source_relink: ALL,
  target_set: ALL,
  compare_mode_set: change("compareRows", "rowDiff", "plan", "impact", "impactPaths", "applyPreview"),
  alignment_override: change("rowDiff", ...CHOICE),
  merge_choice_set: change(...CHOICE),
  merge_choice_bulk_set: change(...CHOICE),
  target_edit_apply: change(...CHOICE),
  removal_policy_set: change(...CHOICE),
  need_mapping_set: change("compareRows", "plan", "impact", "impactPaths", "wireframe", "applyPreview"),
  impact_action_apply: change("compareRows", "plan", "impact", "impactPaths", "removal", "wireframe", "applyPreview"),
  offer_select: change("plan", "impact", "impactPaths", "wireframe", "applyPreview"),
  row_confirm: change("compareRows", "plan", "impact", "applyPreview"),
  sources_check: ALL,
  naming_rule_confirm: change(...RULES),
  naming_rule_reject: change(...RULES),
  naming_rule_edit: change(...RULES),
  naming_rules_copy: change(...RULES),
  proposal_accept: change(...CHOICE, "namingRules"),
  proposal_reject: change("compareRows", "plan", "impact", "impactPaths"),
  proposal_accept_all: change(...CHOICE, "namingRules"),
  question_answer: change(...CHOICE),
  format_only_apply: ALL,
  apply: ALL,
  undo_apply: ALL,
  change_report_write: change("applyLast"),
  cloud_sign_in: Object.freeze([]),
  cloud_connect: ALL,
  pull_to_local: ALL,
  cloud_items_list: Object.freeze([]),
});

// The reads that the method makes stale. An unknown method is a programming error.
export function invalidatedBy(method) {
  const keys = INVALIDATES[method];
  if (!keys) throw new Error(`invalidation.js has no entry for the JS API method ${method}.`);
  return keys;
}
