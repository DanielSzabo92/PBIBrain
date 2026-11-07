// Pure helpers of the session list, the create flow, and the work area frame (UI design 4.1, 4.2, 4.8, 5.1).
// No React here, so that the node unit tests can import this module.
import { t, tn } from "../copy.js";

// A source that holds a model. A report source has no model.
const MODEL_KINDS = new Set(["pbip", "tmdl_folder", "model_bim", "cloud_model"]);
const REPORT_KINDS = new Set(["pbir_report", "pbir_legacy_report", "cloud_report"]);

export function isModelSource(source) {
  return MODEL_KINDS.has(source?.kind);
}

export function isReportSource(source) {
  return REPORT_KINDS.has(source?.kind) || (source?.kind === "pbip" && Boolean(source?.report_path));
}

// GET session has no name fields for the target: the names come from the source list (S2).
export function sourceName(session, sourceId) {
  if (!sourceId) return null;
  return (session?.sources ?? []).find((source) => source.source_id === sourceId)?.display_name ?? null;
}

export function targetNames(session) {
  const target = session?.target ?? {};
  const model = sourceName(session, target.model?.source_id);
  const reportNew = !target.report || target.report.mode === "new_empty";
  const report = reportNew ? null : sourceName(session, target.report?.source_id);
  return { model, report, reportNew };
}

export function targetLine(session) {
  const names = targetNames(session);
  const model = t("work.target_model", { name: names.model ?? t("shared.not_set") });
  const report = names.reportNew ? t("work.target_report.new") : t("work.target_report", { name: names.report ?? t("shared.not_known") });
  return `${model}. ${report}.`;
}

// The plan status button (UI design 4.2). GET session gives only plan_status. The counts come from GET plan (S5).
export function planStatus(planStatusValue, plan = null, checking = false) {
  if (checking) return { tone: "plain", text: t("work.plan.checking"), checking: true };
  const blocking = Array.isArray(plan?.blocking) ? plan.blocking.length : null;
  const warnings = Array.isArray(plan?.warnings) ? plan.warnings.length : null;
  if (planStatusValue === "valid") return { tone: "ok", text: t("work.plan.valid") };
  if (planStatusValue === "valid_with_warnings") {
    return { tone: "warn", text: warnings === null ? t("work.plan.warnings.unknown") : tn("work.plan.warnings", warnings) };
  }
  if (planStatusValue === "invalid") {
    return { tone: "bad", text: blocking === null ? t("work.plan.invalid.unknown") : t("work.plan.invalid", { n: blocking }), blocking };
  }
  return { tone: "plain", text: t("work.plan.none") };
}

// The Agent tab count: open proposals plus open questions (UI design 2).
export function agentCount(session) {
  return (session?.proposals?.open?.length ?? 0) + (session?.questions?.open?.length ?? 0);
}

// The banner stack of the work area, in the order of UI design 3: locked, source missing, sources changed.
export function banners(session) {
  if (!session) return [];
  const list = [];
  const sources = session.sources ?? [];
  if (session.read_only) list.push({ id: "locked", tone: "info", text: t("shared.locked.banner") });
  const missing = sources.filter((source) => source.status !== "ok");
  if (missing.length > 0) {
    list.push({
      id: "missing",
      tone: "bad",
      text: tn("work.banner.missing", missing.length, { name: missing.map((source) => source.display_name).join(", ") }),
    });
  }
  const changed = sources.filter((source) => source.fingerprint_state === "changed");
  const marks = session.counts?.marks ?? 0;
  if (changed.length > 0 || marks > 0) {
    const parts = [];
    if (changed.length > 0) parts.push(tn("work.banner.changed", changed.length));
    if (marks > 0) parts.push(tn("work.banner.changed.rows", marks));
    list.push({ id: "changed", tone: "warn", text: parts.join(" ") });
  }
  return list;
}

// The status of a row of GET sessions (UI design 4.1).
export function listRowState(row) {
  if (row.schema_state === "newer") return { openable: false, tone: "warn", label: t("list.status.newer"), reason: t("list.status.newer.help") };
  if (row.schema_state !== "ok") return { openable: false, tone: "bad", label: t("list.status.damaged"), reason: t("list.status.damaged.help") };
  if (row.lock_state === "locked") return { openable: true, tone: "info", label: t("shared.locked.row"), reason: t("shared.locked.row_help") };
  return { openable: true, tone: "ok", label: t("list.status.ready"), reason: null };
}

export function listPlanLabel(value) {
  if (value === "valid") return { tone: "ok", label: t("list.plan.valid") };
  if (value === "valid_with_warnings") return { tone: "warn", label: t("list.plan.valid_with_warnings") };
  if (value === "invalid") return { tone: "bad", label: t("list.plan.invalid") };
  return { tone: "plain", label: t("list.plan.unknown") };
}

// Newest first. A row with no time goes last.
export function sortSessions(rows = []) {
  return [...rows].sort((a, b) => String(b.updated_at ?? "").localeCompare(String(a.updated_at ?? "")));
}

export function formatTime(value) {
  if (!value) return t("shared.not_known");
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return t("shared.not_known");
  return date.toLocaleString(undefined, { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

// The last part of a path, with no folder suffix.
export function pathName(path) {
  const name = String(path ?? "").replace(/\\/g, "/").replace(/\/+$/, "").split("/").pop() ?? "";
  return name.replace(/\.(SemanticModel|Report|pbip|bim)$/i, "") || name;
}

// The draft kind of a picked path. A PBIX file gives a refusal (refuse.pbix), not a source.
export function draftSource(path, menuKind) {
  const value = String(path ?? "");
  const file = value.replace(/\\/g, "/").split("/").pop() ?? value;
  if (/\.pbix$/i.test(value)) return { refused: t("refuse.pbix", { file }) };
  let kind = menuKind;
  if (/\.SemanticModel\/?$/i.test(value)) kind = "tmdl_folder";
  else if (/\.Report\/?$/i.test(value)) kind = "pbir_report";
  else if (/\.bim$/i.test(value)) kind = "model_bim";
  else if (/\.pbip$/i.test(value)) kind = "pbip";
  return { path: value, kind, name: pathName(value) };
}

export function draftHasModel(sources = []) {
  return sources.some((source) => MODEL_KINDS.has(source.kind));
}

// The target model choices of step 2 (UI design 4.1). value: "existing:<key>", "copy:<key>", or "empty".
export function targetModelItems(sources = []) {
  const items = [];
  for (const source of sources) {
    if (!MODEL_KINDS.has(source.kind)) continue;
    // Issue #16: a cloud model with Read/Write access is a target; the apply writes it through XMLA.
    const cloud = source.kind === "cloud_model" && source.access_type !== "Read/Write";
    const tmsl = source.kind === "model_bim";
    const reason = cloud ? t("refuse.cloud_target") : tmsl ? t("refuse.tmsl_target") : null;
    items.push({ value: `existing:${source.key}`, label: source.name, help: t("create.target.existing.help", { source: source.name }), disabled: Boolean(reason), reason });
    items.push({ value: `copy:${source.key}`, label: t("create.target.copy", { source: source.name }), help: t("create.target.copy.help", { source: source.name }) });
  }
  items.push({ value: "empty", label: t("create.target.empty"), help: t("create.target.empty.help") });
  return items;
}

export function targetReportItems(sources = []) {
  const items = [{ value: "new_empty", label: t("create.target.new_report"), help: t("create.target.new_report.help") }];
  for (const source of sources) {
    if (!REPORT_KINDS.has(source.kind)) continue;
    const legacy = source.kind === "pbir_legacy_report";
    const cloud = source.kind === "cloud_report" && source.access_type !== "Read/Write";
    const reason = legacy ? t("refuse.legacy_target") : cloud ? t("refuse.cloud_target") : null;
    items.push({ value: `existing:${source.key}`, label: source.name, disabled: Boolean(reason), reason });
  }
  return items;
}

export function defaultSessionName(draft) {
  const choice = draft?.targetModel ?? "";
  const key = choice.includes(":") ? choice.split(":")[1] : null;
  const source = (draft?.sources ?? []).find((item) => item.key === key);
  if (choice === "empty") return t("create.name.default", { model: t("create.target.empty") });
  return source ? t("create.name.default", { model: source.name }) : "";
}

// The target_set payload of a draft. sourceIds maps a draft key to the source_id of its source_add reply.
// Return null when the target model source was not added.
export function targetPayload(draft, sourceIds) {
  const [mode, key] = String(draft.targetModel ?? "").split(":");
  let model;
  if (mode === "existing" || mode === "copy") {
    const sourceId = sourceIds.get(key);
    if (!sourceId) return null;
    model = mode === "existing" ? { mode: "existing", source_id: sourceId } : { mode: "copy_of", source_id: sourceId, path: draft.copyFolder };
  } else if (mode === "empty") {
    model = { mode: "empty", path: draft.copyFolder, name: draft.name };
  } else {
    return null;
  }
  const [reportMode, reportKey] = String(draft.targetReport ?? "new_empty").split(":");
  let report = { mode: "new_empty" };
  if (reportMode === "existing") {
    const sourceId = sourceIds.get(reportKey);
    report = sourceId ? { mode: "existing", source_id: sourceId } : { mode: "new_empty" };
  }
  return { model, report };
}

// Run the create calls of UI design 5.1: session_create, source_add for each source in list order, then target_set.
// run(method, payload) rejects with a DevCenterError. onStep(lines) gets the progress after each step.
export async function runCreateFlow({ draft, run, onStep = () => {}, describe = (error) => error?.message ?? "" }) {
  const lines = [
    { id: "session", text: t("create.progress.created"), state: "pending" },
    ...draft.sources.map((source) => ({ id: source.key, text: t("create.progress.source_added", { source: source.name }), state: "pending" })),
    { id: "target", text: t("create.progress.target"), state: "pending" },
  ];
  const update = (id, patch) => {
    const line = lines.find((item) => item.id === id);
    Object.assign(line, patch);
    onStep(lines.map((item) => ({ ...item })));
  };
  update("session", { state: "running" });
  let created;
  try {
    created = await run("session_create", { display_name: draft.name.trim() });
  } catch (error) {
    update("session", { state: "failed", fix: describe(error) });
    return { created: false, failed: [], lines, error };
  }
  update("session", { state: "done" });
  const sourceIds = new Map();
  const failed = [];
  for (const source of draft.sources) {
    update(source.key, { state: "running" });
    try {
      const reply = await run("source_add", { path: source.path });
      sourceIds.set(source.key, reply.source.source_id);
      update(source.key, { state: "done" });
    } catch (error) {
      failed.push(source);
      update(source.key, { state: "failed", text: t("create.progress.source_failed", { source: source.name, reason: describe(error) }) });
    }
  }
  const target = targetPayload(draft, sourceIds);
  if (!target) {
    update("target", { state: "failed", text: `${t("create.progress.target")}: ${t("create.progress.not_run")}` });
    return { created: true, sessionId: created.session_id, failed, lines, targetSet: false };
  }
  update("target", { state: "running" });
  try {
    await run("target_set", target);
    update("target", { state: "done" });
  } catch (error) {
    update("target", { state: "failed", fix: describe(error) });
    return { created: true, sessionId: created.session_id, failed, lines, targetSet: false, error };
  }
  return { created: true, sessionId: created.session_id, failed, lines, targetSet: true };
}
