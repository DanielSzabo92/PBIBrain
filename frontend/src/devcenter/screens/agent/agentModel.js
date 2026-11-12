// Pure helpers of the Agent tab (UI design 4.7, 5.4, step U9).
// No React here, so that the node unit tests can import this module.
import { t, tn } from "../../copy.js";
import { planStatus } from "../sessionModel.js";

export const PROPOSAL_STATUSES = Object.freeze(["ready", "needs_review", "source_changed", "user_choice_conflict"]);
export const PROPOSAL_KINDS = Object.freeze([
  "merge_choice", "name", "alignment", "removal_policy", "need_mapping", "impact_action",
  "object_edit", "object_rename", "object_delete", "object_create",
]);

// The status of an open proposal comes from its blocked field (S10, UC9). A destructive
// object proposal (issue #13) is "needs_review": the user accepts it one by one, never in "Accept all".
export function proposalStatus(proposal) {
  const blocked = proposal?.blocked;
  if (blocked === "source_changed" || blocked === "user_choice_conflict") return blocked;
  return proposal?.needs_review ? "needs_review" : "ready";
}

// The safety check of an object proposal (issue #13): plan blocking items and Breaks/Needs counts.
export function checkText(proposal) {
  const check = proposal?.check;
  if (!check) return null;
  return t("agent.card.check", { breaks: check.breaks ?? 0, needs: check.needs ?? 0, blocking: check.blocking?.length ?? 0 });
}

export function statusText(status) {
  return t(`agent.status.${status}`);
}

export function statusTone(status) {
  if (status === "ready") return "ok";
  return "warn";
}

// The row action of a proposal: Accept, Replace with agent choice, or Open row (UI design 4.7).
export function proposalAction(proposal) {
  const status = proposalStatus(proposal);
  if (status === "source_changed") return "open_row";
  if (status === "user_choice_conflict") return "replace";
  return "accept";
}

export function confidenceText(confidence) {
  return typeof confidence === "number" ? `${Math.round(confidence * 100)}%` : t("shared.not_known");
}

export function kindText(kind) {
  const key = `agent.kind.${kind}`;
  const text = t(key);
  return text === key ? String(kind ?? "") : text;
}

// HH:MM of a UTC time text. The UI shows the local time of the user.
export function timeText(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return `${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
}

export function fromText(proposal) {
  return t("agent.card.from", { client: proposal?.mcp_client || "Agent", time: timeText(proposal?.created_utc) });
}

// Newest first. Filters: kind, status, and a target search on the target name or ID.
export function filterProposals(proposals, { kind = "all", status = "all", q = "" } = {}) {
  const query = String(q || "").trim().toLowerCase();
  return [...(proposals ?? [])]
    .filter((item) => kind === "all" || item.kind === kind)
    .filter((item) => status === "all" || proposalStatus(item) === status)
    .filter((item) => !query || `${item.target_name ?? ""} ${item.target_id ?? ""}`.toLowerCase().includes(query))
    .sort((a, b) => String(b.created_utc ?? "").localeCompare(String(a.created_utc ?? "")));
}

// A19: the list shows only the proposals that the user saw. New IDs make the notice count.
export function visibleProposals(open, shownIds) {
  return (open ?? []).filter((item) => shownIds.has(item.id));
}

export function newProposalCount(open, shownIds) {
  return (open ?? []).filter((item) => !shownIds.has(item.id)).length;
}

export function newNoticeText(n) {
  return tn("agent.new", n);
}

// The ready proposals. Only these have a checkbox and go into "Accept all".
export function readyProposals(open) {
  return (open ?? []).filter((item) => proposalStatus(item) === "ready");
}

function kindCounts(proposals) {
  const counts = new Map();
  for (const item of proposals ?? []) counts.set(item.kind, (counts.get(item.kind) ?? 0) + 1);
  return [...counts.entries()].map(([kind, n]) => ({ kind, n, text: `${kindText(kind)}: ${n}` }));
}

function planCounts(plan) {
  return {
    blocking: Array.isArray(plan?.blocking) ? plan.blocking.length : 0,
    warnings: Array.isArray(plan?.warnings) ? plan.warnings.length : 0,
  };
}

// The "Accept all" summary (UI design 5.4): kinds, plan now and after, change, and skipped items.
export function acceptAllSummary({ open, planNow, planAfter }) {
  const ready = readyProposals(open);
  const skippedKeys = {
    source_changed: "agent.accept_all.skipped.source_changed",
    needs_review: "agent.accept_all.skipped.needs_review",
  };
  const skipped = (open ?? []).filter((item) => proposalStatus(item) !== "ready").map((item) => ({
    id: item.id,
    reason: proposalStatus(item),
    text: t(skippedKeys[proposalStatus(item)] ?? "agent.accept_all.skipped.user_choice", {
      object: item.target_name || item.target_id,
    }),
  }));
  const now = planCounts(planNow);
  const after = planCounts(planAfter);
  return {
    ready,
    n: ready.length,
    kinds: kindCounts(ready),
    skipped,
    nowText: planNow ? planStatus(planNow.status, planNow).text : null,
    afterText: planAfter ? planStatus(planAfter.status, planAfter).text : null,
    changeText: planNow && planAfter ? t("agent.accept_all.change", { n: now.blocking - after.blocking, m: after.warnings - now.warnings }) : null,
  };
}

// The toast after "Accept selected" (UI design 5.4).
export function acceptSelectedToast(accepted, total) {
  const failed = total - accepted;
  if (failed === 0) return { tone: "ok", text: t("agent.toast.accept_all", { n: accepted, m: 0 }) };
  return { tone: "warn", text: t("agent.toast.accept_selected", { a: accepted, n: total, m: failed }) };
}

// The option lines of a question card. A merge_choice option shows the choice that it sets.
export function optionEffect(option, formatChoice) {
  const proposal = option?.proposal;
  if (!proposal) return null;
  if (proposal.kind === "merge_choice") return t("agent.question.sets", { choice: formatChoice(proposal.payload?.choice ?? proposal.payload) });
  return kindText(proposal.kind);
}

export function questionSections(questions) {
  const open = questions?.open ?? [];
  const answered = questions?.answered ?? [];
  return { first: open[0] ?? null, more: open.slice(1), answered };
}
