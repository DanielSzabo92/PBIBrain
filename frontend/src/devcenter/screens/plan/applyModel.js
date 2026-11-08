// Pure logic of the Apply, Undo, format only, and change report flows (UI design 5.5, 5.6, step U10).
// Plain JS with no React import, so that node --test can test it.
import { t } from "../../copy.js";

export const KINDS = Object.freeze(["apply", "format", "undo"]);

// The JS API method of each flow kind.
export const FLOW_METHOD = Object.freeze({ apply: "apply", format: "format_only_apply", undo: "undo_apply" });

// The rows of each progress list. Each row has the backend step IDs (apply/steps.py) that it shows.
// The copy keys use the names of the UI design; the backend step IDs are different for some rows.
const APPLY_ROWS = [
  { id: "source_check", group: "checks", steps: ["source_check"] },
  { id: "plan_status", group: "checks", steps: ["plan_status"] },
  { id: "desktop_check", group: "checks", steps: ["desktop_check"] },
  { id: "canonical_check", group: "checks", steps: ["canonical_check"] },
  { id: "full_validation", group: "checks", steps: ["validation"] },
  { id: "approval", group: "checks", steps: ["approval"] },
  { id: "candidate_write", group: "write", steps: ["write"] },
  { id: "guard", group: "write", steps: ["guard"] },
  { id: "promotion", group: "write", steps: ["promotion"] },
  { id: "rescan", group: "write", steps: ["rescan"] },
  { id: "fingerprints", group: "write", steps: ["fingerprint", "change_report"] },
];
const FORMAT_ROWS = [
  { id: "desktop_check", group: "checks", steps: ["desktop_check"] },
  { id: "canonical_check", group: "checks", steps: ["canonical_check"] },
  { id: "candidate_write", group: "write", steps: ["write"] },
  { id: "guard", group: "write", steps: ["guard"] },
  { id: "promotion", group: "write", steps: ["promotion"] },
  { id: "rescan", group: "write", steps: ["rescan"] },
  { id: "fingerprints", group: "write", steps: ["fingerprint"] },
];
const UNDO_ROWS = [
  { id: "restore", group: "write", steps: ["desktop_check", "backup_check", "promotion"] },
  { id: "rescan", group: "write", steps: ["rescan"] },
  { id: "fingerprints", group: "write", steps: ["fingerprint"] },
];
const ROWS = { apply: APPLY_ROWS, format: FORMAT_ROWS, undo: UNDO_ROWS };

// The backend step IDs in order (apply/steps.py STEPS_BY_KIND).
const STEP_ORDER = {
  apply: ["source_check", "plan_status", "desktop_check", "canonical_check", "validation", "approval",
    "write", "guard", "promotion", "rescan", "fingerprint", "change_report"],
  format: ["desktop_check", "canonical_check", "write", "guard", "promotion", "rescan", "fingerprint"],
  undo: ["desktop_check", "backup_check", "promotion", "rescan", "fingerprint"],
};

// The copy key of a details.step value (UI design 8, ticket 09 section 3.11).
const STEP_COPY = { validation: "full_validation", write: "candidate_write", fingerprint: "fingerprints", change_report: "fingerprints" };

function rowLabel(kind, row, approvalCount) {
  if (kind === "undo") return t(`undo.step.${row.id}`);
  if (row.id === "approval") return t("apply.step.approval", { n: approvalCount });
  return t(`apply.step.${row.id}`);
}

// The index (1 based) of a backend step in its flow. 0 when it is not known.
function stepIndexOf(kind, step) {
  const index = STEP_ORDER[kind]?.indexOf(step) ?? -1;
  return index + 1;
}

// The rows of the progress list. progress is the store value of GET apply/progress (or null).
// Apply: the checks (steps 1 to 6) show as done, because the preview did them (UI design 5.5 step 3).
// Each row before the current step is done, the current row runs, and the other rows wait.
// failedStep: the details.step of a failure; that row shows as failed.
export function progressRows(kind, progress, { approvalCount = 0, failedStep = null, finished = false } = {}) {
  const rows = ROWS[kind] ?? [];
  const order = STEP_ORDER[kind] ?? [];
  let current = 0;
  if (progress?.available && Number.isInteger(progress.step_index)) {
    current = progress.step ? stepIndexOf(kind, progress.step) || progress.step_index : progress.step_index;
  }
  if (kind === "apply") current = Math.max(current, stepIndexOf("apply", "write"));
  if (kind !== "apply" && current === 0) current = 1;
  const failedIndex = failedStep ? stepIndexOf(kind, failedStep) : 0;
  return rows.map((row) => {
    const first = Math.min(...row.steps.map((step) => order.indexOf(step) + 1).filter((value) => value > 0));
    const last = Math.max(...row.steps.map((step) => order.indexOf(step) + 1));
    let state = "waiting";
    if (finished) state = "done";
    else if (failedIndex > 0) {
      if (failedIndex >= first && failedIndex <= last) state = "failed";
      else if (last < failedIndex) state = "done";
    } else if (last < current) state = "done";
    else if (current >= first && current <= last) state = "running";
    return { id: row.id, group: row.group, label: rowLabel(kind, row, approvalCount), state };
  });
}

// The row number (1 based) and the count of the progress list, for "Step <i> of <n>".
export function progressCount(rows) {
  const running = rows.findIndex((row) => row.state === "running");
  const done = rows.filter((row) => row.state === "done").length;
  return { i: running >= 0 ? running + 1 : Math.min(done + 1, rows.length), n: rows.length };
}

// "12 s" or "1 min 5 s".
export function formatElapsed(ms) {
  const total = Math.max(0, Math.floor((Number(ms) || 0) / 1000));
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return minutes > 0 ? `${minutes} min ${seconds} s` : `${seconds} s`;
}

// The progress line: "Step <i> of <n>. <time> elapsed." or the fallback when GET apply/progress fails.
export function progressLine(kind, rows, progress, elapsedMs) {
  const elapsed = formatElapsed(elapsedMs);
  if (progress && progress.available === false) {
    if (kind === "apply") return t("apply.progress.fallback", { elapsed });
    return t("apply.progress.fallback.other", { action: t(`flow.${kind}.running`), elapsed });
  }
  const { i, n } = progressCount(rows);
  return t("apply.progress.count", { i, n, elapsed });
}

// The qualified name of an operation: Sales[Region] when table and name exist.
export function qualifiedOperationName(op) {
  if (!op) return "";
  if (op.table && op.name && op.object_type !== "table") {
    return `${op.table}[${op.name}]`;
  }
  return op.name || op.row_key || "";
}

// The approval items of the Apply dialog (UI design 5.5 step 2): Critical, High, Not checked.
// Each item links back to its row or impact item so the user can inspect it before committing.
export function approvalItems(preview, plan) {
  const names = new Map();
  for (const op of plan?.operations ?? []) {
    if (op?.row_key && op?.name && !names.has(op.row_key)) names.set(op.row_key, qualifiedOperationName(op));
  }
  const items = [];
  for (const need of preview?.approvals_needed ?? []) {
    if (need.purpose !== "HIGH_RISK_PROMOTION") continue;
    const severity = need.risk === "CRITICAL" ? "critical" : "high";
    for (const key of need.row_keys ?? []) {
      items.push({
        id: `${severity}-${key}`,
        severity,
        name: names.get(key) ?? key,
        rowKey: key,
        type: "row",
      });
    }
  }
  for (const item of preview?.not_checked ?? []) {
    items.push({
      id: `not_checked-${item.object_id}`,
      severity: "not_checked",
      name: item.object_name || item.object_id,
      rowKey: item.object_id,
      itemId: item.object_id,
      type: "impact",
    });
  }
  // Issue #16: the write to a cloud target is one approval item (the service then blocks the PBIX download).
  const cloud = preview?.cloud_target;
  if (cloud && (preview?.approvals_needed ?? []).some((need) => need.purpose === "CLOUD_WRITE")) {
    const name = cloud.report_name ? `${cloud.model_name} + ${cloud.report_name}` : cloud.model_name;
    items.push({ id: "cloud-write", severity: "cloud", name: t("apply.cloud.item", { name, workspace: cloud.workspace_name }) });
  }
  const rank = { critical: 0, high: 1, cloud: 2, not_checked: 3 };
  return items.sort((a, b) => rank[a.severity] - rank[b.severity]);
}

// Format the combined target label: "Combined model and Combined report" or single target.
export function applyTargetLabel(targets) {
  if (typeof targets === "string") return targets;
  const model = targets?.model;
  const report = targets?.report;
  if (model && report) return `${model} and ${report}`;
  if (model) return model;
  if (report) return report;
  return "the target";
}

// Derive target files to be written from session and preview.
export function targetFiles(session, preview) {
  if (Array.isArray(preview?.target_files) && preview.target_files.length > 0) {
    return preview.target_files;
  }
  const files = [];
  const target = session?.target ?? {};
  const sources = session?.sources ?? [];
  const modelSource = sources.find((s) => s.source_id === target.model?.source_id || (s.role === "target" && (s.kind === "pbip" || s.kind === "tmdl_folder" || s.model_format)));
  const reportSource = sources.find((s) => s.source_id === target.report?.source_id || (s.role === "target" && (s.kind === "pbir_report" || s.report_format)));

  if (modelSource) {
    const p = modelSource.model_path || modelSource.path;
    if (p && !files.includes(p)) files.push(p);
  }
  if (reportSource) {
    const p = reportSource.report_path || reportSource.path;
    if (p && !files.includes(p)) files.push(p);
  }
  return files;
}

// Pre-checks evaluated before user confirms apply, displayed green/red inside confirmation.
export function applyPreChecks(preview, plan) {
  const checks = [];

  // 1. Desktop check
  const desktopState = preview?.desktop_state;
  const desktopOk = desktopState !== "open_unsaved";
  checks.push({
    id: "desktop_check",
    label: t("apply.step.desktop_check"),
    ok: desktopOk,
    detail: !desktopOk ? t("details.step.desktop_check") : null,
  });

  // 2. Source check
  const unconfirmed = preview?.unconfirmed_marks?.count ?? 0;
  const sourcesOk = unconfirmed === 0;
  checks.push({
    id: "source_check",
    label: t("apply.step.source_check"),
    ok: sourcesOk,
    detail: !sourcesOk ? t("details.step.source_check") : null,
  });

  // 3. Plan status
  const validationStatus = preview?.validation?.status ?? plan?.status;
  const failedChecks = preview?.validation?.failed_checks ?? [];
  const planOk = validationStatus !== "invalid" && failedChecks.length === 0 && plan?.status !== "invalid";
  checks.push({
    id: "plan_status",
    label: t("apply.step.plan_status"),
    ok: planOk,
    detail: !planOk ? t("details.step.plan_status") : null,
  });

  // 4. Canonical check
  const nonCanonical = preview?.non_canonical_files ?? [];
  const canonicalOk = nonCanonical.length === 0;
  checks.push({
    id: "canonical_check",
    label: t("apply.step.canonical_check"),
    ok: canonicalOk,
    detail: !canonicalOk ? t("details.step.canonical_check") : null,
  });

  return checks;
}

// Build exportable Markdown report for leads before applying.
export function buildBeforeApplyReport({ plan, session, preview, targetName = "Target", targetFiles: files = [] } = {}) {
  const summary = applySummary(plan);
  const deletes = deletedNames(plan);
  const approvals = approvalItems(preview, plan);
  const prechecks = applyPreChecks(preview, plan);
  const stepCount = plan?.steps?.length ?? 0;
  const opCount = plan?.operations?.length ?? 0;

  const lines = [
    `# Before-Apply Report: ${targetName}`,
    "",
    `Generated at: ${new Date().toISOString()}`,
    "",
    "## Pre-checks",
    "",
    ...prechecks.map((c) => `- [${c.ok ? "x" : " "}] ${c.label}${c.detail ? `: ${c.detail}` : ""}`),
    "",
    "## Plan Summary",
    "",
    `- Plan steps: ${stepCount}`,
    `- Operations: ${opCount}`,
    `- Created: ${summary.add ?? 0}`,
    `- Deleted: ${summary.remove ?? 0}`,
    `- Modified: ${summary.change ?? 0}`,
    `- Renamed: ${summary.rename ?? 0}`,
    "",
  ];

  if (files.length > 0) {
    lines.push("## Files to Write", "");
    for (const f of files) lines.push(`- \`${f}\``);
    lines.push("");
  }

  if (deletes.length > 0) {
    lines.push("## Deletions", "");
    for (const d of deletes) lines.push(`- \`${d}\``);
    lines.push("");
  }

  if (approvals.length > 0) {
    lines.push("## Approvals Needed", "");
    for (const a of approvals) lines.push(`- [${a.severity.toUpperCase()}] ${a.name}`);
    lines.push("");
  }

  return lines.join("\n");
}

// The approval purposes that the apply request sends (apply.request.json).
export function approvalPurposes(preview) {
  const purposes = new Set();
  for (const need of preview?.approvals_needed ?? []) purposes.add(need.purpose);
  if ((preview?.not_checked ?? []).length > 0) purposes.add("UNCHECKED_IMPACT");
  return [...purposes].filter((value) => value === "HIGH_RISK_PROMOTION" || value === "UNCHECKED_IMPACT" || value === "CLOUD_WRITE").sort();
}

// The names of the objects that the plan deletes, using qualified names (e.g. Sales[Region]).
export function deletedNames(plan) {
  const names = [];
  for (const op of plan?.operations ?? []) {
    if (op?.op === "DELETE") {
      const name = qualifiedOperationName(op);
      if (name && !names.includes(name)) names.push(name);
    }
  }
  return names;
}

// Single data source for apply dialog counts: always reconciled with the deletedNames list.
export function applySummary(plan) {
  const deletes = deletedNames(plan);
  const remove = deletes.length;
  let add = 0;
  let change = 0;
  let rename = 0;

  if (plan?.summary) {
    const model = plan.summary.model ?? {};
    const report = plan.summary.report ?? {};
    add = (model.created?.total ?? 0) + (report.created?.total ?? 0);
    change = (model.modified?.total ?? 0) + (report.modified?.total ?? 0);
    rename = (model.renamed?.total ?? 0) + (report.renamed?.total ?? 0);
  } else if (Array.isArray(plan?.operations)) {
    for (const op of plan.operations) {
      if (op.op === "CREATE" || op.op === "COPY_PAGE" || op.op === "CREATE_REPORT_MEASURE") add += 1;
      else if (op.op === "RENAME" || op.op === "RENAME_PAIR") rename += 1;
      else if (op.op !== "DELETE") change += 1;
    }
  }

  return { add, remove, change, rename };
}

// The Desktop line of the dialog. null when Power BI Desktop does not have the target open.
export function desktopLine(state, kind = "apply") {
  if (state === "open_saved" || state === "open_unsaved") return kind === "undo" ? t("undo.desktop") : t("apply.desktop.open");
  if (state === "not_reachable") return t("apply.desktop.not_reachable");
  return null;
}

// True when the reply tells the user to select "Apply external changes" in Power BI Desktop.
export function needsDesktopBanner(reply) {
  return Array.isArray(reply?.notices) && reply.notices.includes("apply_external_changes");
}

function lowerFirst(text) {
  return text ? text.charAt(0).toLowerCase() + text.slice(1) : text;
}

// The one sentence for a failure: details.check first (guard checks), else details.step.
export function failureReason(error) {
  const details = error?.details ?? {};
  if (details.check && t(`details.check.${details.check}`) !== `details.check.${details.check}`) {
    return t(`details.check.${details.check}`);
  }
  const key = STEP_COPY[details.step] ?? details.step;
  if (key && t(`details.step.${key}`) !== `details.step.${key}`) {
    return t(`details.step.${key}`, { check: details.check ?? "not known" });
  }
  return error?.message ? String(error.message) : t("shared.unknown.title");
}

// The name of the failed step, for "Failed step: <step>."
export function failedStepLabel(kind, step) {
  if (!step) return t("shared.not_known");
  if (kind === "undo") {
    const row = UNDO_ROWS.find((item) => item.steps.includes(step));
    return row ? t(`undo.step.${row.id}`) : step;
  }
  const key = STEP_COPY[step] ?? step;
  if (key === "approval") return t("apply.step.approval.name");
  const text = t(`apply.step.${key}`);
  return text === `apply.step.${key}` ? step : text;
}

// "14:22" for a Date.
export function clockTime(date = new Date()) {
  const pad = (value) => String(value).padStart(2, "0");
  return `${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

// The result panel of a finished flow: success, differences, failure, refused, or stale.
// reply: the JS API reply. error: the DevCenterError. planSteps: the count of plan steps.
export function flowResult(kind, { reply = null, error = null, planSteps = 0, time = "" } = {}) {
  if (error) {
    if (error.code === "stale_revision" && kind === "apply") {
      return { type: "stale", tone: "warn", title: t("apply.stale"), body: null, action: "check_plan" };
    }
    if (kind === "undo" && error.details?.reason === "target_changed") {
      const files = Array.isArray(error.details.files) ? error.details.files : [];
      return { type: "refused", tone: "bad", title: t("undo.refused.title"), body: t("undo.refused.body", { n: files.length }), files };
    }
    const reason = failureReason(error);
    const step = failedStepLabel(kind, error.details?.step);
    if (kind === "undo") return { type: "failure", tone: "bad", title: t("undo.fail.title"), body: t("undo.fail", { reason }), step, files: [] };
    if (kind === "format") {
      const body = error.details?.step === "guard" ? t("format.fail.body") : t("apply.fail.body", { step: lowerFirst(step), reason });
      return { type: "failure", tone: "bad", title: t("format.fail.title"), body, step, help: t("apply.fail.help"), files: [] };
    }
    return {
      type: "failure", tone: "bad", title: t("apply.fail.title"),
      body: t("apply.fail.body", { step: lowerFirst(step), reason }), step, help: t("apply.fail.help"), files: [],
    };
  }
  const differences = Array.isArray(reply?.rescan_differences) ? reply.rescan_differences : [];
  const files = reply?.file_count ?? reply?.files?.length ?? 0;
  if (kind === "undo") return { type: "success", tone: "ok", title: t("undo.done.title"), body: t("undo.toast", { time }), differences };
  if (kind === "format") return { type: "success", tone: "ok", title: t("format.success.title"), body: t("format.success.body", { n: files }), differences };
  if (differences.length > 0) {
    return { type: "differences", tone: "warn", title: t("apply.diff.title", { n: differences.length }), body: t("apply.diff.body", { n: differences.length }), differences };
  }
  return { type: "success", tone: "ok", title: t("apply.success.title"), body: t("apply.success.body", { steps: planSteps, files, time }), differences };
}

// Undo is available only for the last apply of the session while its backup exists (GET apply/last).
export function undoState(last) {
  if (!last?.apply_id || last.undone || !last.backup_present) return { available: false, refused: false, files: [] };
  return { available: true, refused: Boolean(last.target_changed), files: Array.isArray(last.changed_files) ? last.changed_files : [] };
}

// "2026-11-06" for a Date (local time).
export function isoDate(date = new Date()) {
  const pad = (value) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

// The default file name of the change report (UI design 5.6).
// Characters that a Windows file name cannot have become a space (change_report_write.request.json).
export function changeReportName(sessionName, date = new Date()) {
  const session = String(sessionName || "").replace(/[\\/:*?"<>|]+/g, " ").replace(/^[\s.]+/, "").replace(/\s+/g, " ").trim();
  return t("report.file_name", { session: session || "Merge session", date: isoDate(date) });
}

// The time of an ISO UTC value as "14:22" in local time, for the Undo title.
export function timeOf(utc) {
  if (!utc) return "";
  const date = new Date(utc);
  return Number.isNaN(date.getTime()) ? "" : clockTime(date);
}
