// Pure helpers for the Plan view (UI design 4.6, 5.5, 8, step U7).
import { t } from "../../copy.js";

const MODEL_TYPES = [
  ["table", "Tables"],
  ["column", "Columns"],
  ["measure", "Measures"],
  ["relationship", "Relationships"],
  ["calculation_group", "Calculation groups"],
  ["hierarchy", "Hierarchies"],
  ["function", "Functions"],
  ["role", "Roles"],
];

const REPORT_TYPES = [
  ["page", "Pages"],
  ["visual", "Visuals"],
  ["report_measure", "Report measures"],
  ["field_binding", "Field bindings"],
];

const STEP_TYPE_LABELS = {
  table: "Table",
  column: "Column",
  measure: "Measure",
  relationship: "Relationship",
  calculation_group: "Calculation group",
  hierarchy: "Hierarchy",
  function: "Function",
  role: "Role",
  page: "Page",
  visual: "Visual",
  report_measure: "Report measure",
  field_binding: "Field binding",
};

const PHASE_ORDER = [
  ["deletes", "plan.phase.deletes", "Deletes"],
  ["renames", "plan.phase.renames", "Renames"],
  ["creates", "plan.phase.creates", "Creates"],
  ["changes", "plan.phase.changes", "Changes"],
  ["rewrites", "plan.phase.rewrites", "Expression rewrites"],
  ["report", "plan.phase.report", "Report changes"],
];

const CHANGE_TO_PHASE = {
  deleted: "deletes",
  renamed: "renames",
  created: "creates",
  modified: "changes",
};

const IMPACT_BLOCK_KINDS = new Set(["removed", "renamed", "need_missing", "need_clash"]);

const BLOCK_KEY_MAP = {
  removed: "plan.block.removed",
  renamed: "plan.block.renamed",
  need_missing: "plan.block.need",
  need_clash: "plan.block.need",
  name_clash: "plan.block.clash",
  choice_source_removed: "plan.block.choice_source_removed",
};

export function formatCheckTime(value) {
  if (!value) return "09:30";
  if (typeof value === "string") {
    if (/^\d{2}:\d{2}$/.test(value.trim())) return value.trim();
    const match = value.match(/T(\d{2}:\d{2})/);
    if (match) return match[1];
  }
  if (value instanceof Date && !Number.isNaN(value.getTime())) {
    const hh = String(value.getHours()).padStart(2, "0");
    const mm = String(value.getMinutes()).padStart(2, "0");
    return `${hh}:${mm}`;
  }
  return "09:30";
}

export function planDeletesCount(plan) {
  if (!plan) return 0;
  const modelDeleted = plan.summary?.model?.deleted?.total;
  const reportDeleted = plan.summary?.report?.deleted?.total;
  if (typeof modelDeleted === "number" || typeof reportDeleted === "number") {
    return (modelDeleted ?? 0) + (reportDeleted ?? 0);
  }
  const steps = plan.steps ?? [];
  return steps.filter((step) => step.change === "deleted").length;
}

function blockParams(item) {
  const params = item?.params ?? {};
  const objName = item?.object?.name || params.object || params.name || item?.row_key || "Object";
  const removedName = typeof params.removed === "object" && params.removed ? params.removed.name : params.removed;
  const renamedName = typeof params.renamed === "object" && params.renamed ? params.renamed.name : params.renamed;
  const neededName = typeof params.needed === "object" && params.needed ? params.needed.name : params.needed;
  const replacementName = typeof params.replacement === "object" && params.replacement ? params.replacement.name : params.replacement;
  const clashType = params.clash?.object_type || item?.object?.object_type || "object";
  const ops = Array.isArray(params.operations) ? params.operations : [];
  return {
    object: objName,
    dependent: objName,
    removed: removedName || "removed object",
    renamed: renamedName || "renamed object",
    old: renamedName || "old name",
    new: params.new_name || "new name",
    needed: neededName || "needed object",
    name: params.name || objName,
    type: clashType,
    source: params.source_name || params.source_id || "removed source",
    source_a: params.source_a || "target",
    source_b: params.source_b || "donor",
    replacement: replacementName || "replacement",
    a: params.a || ops[0] || "first object",
    b: params.b || ops[1] || ops[0] || "second object",
    line: params.line ?? 1,
    col: params.column ?? params.col ?? 1,
  };
}

export function formatBlockingText(item) {
  if (!item) return "";
  const values = blockParams(item);
  if (typeof item.message === "string" && item.message.trim() && !item.message.includes("{")) {
    return item.message;
  }
  const copyKey = BLOCK_KEY_MAP[item.kind];
  if (copyKey) {
    const translated = t(copyKey, values);
    if (translated !== copyKey) return translated;
  }
  if (item.kind === "dax_parse") {
    return `The expression of ${values.object} has a syntax error at line ${values.line}, column ${values.col}.`;
  }
  if (typeof item.message === "string" && item.message.trim()) {
    return item.message.replace(/\{([a-z_]+)\}/g, (full, name) => (values[name] !== undefined ? String(values[name]) : full));
  }
  return item.kind || "";
}

export function formatBlockingFix(item) {
  if (!item) return "";
  if (typeof item.fix === "string" && item.fix.trim() && !item.fix.includes("{")) {
    return item.fix;
  }
  const values = blockParams(item);
  if (item.kind === "dax_parse" || item.kind === "udf_compatibility" || item.kind === "dependency_cycle") {
    return t("plan.block.validation.fix");
  }
  const baseKey = BLOCK_KEY_MAP[item.kind];
  if (baseKey) {
    const fixKey = `${baseKey}.fix`;
    const translated = t(fixKey, values);
    if (translated !== fixKey) return translated;
  }
  return item.fix || t("plan.block.validation.fix");
}

export function formatWarningText(item) {
  if (!item) return "";
  if (typeof item.message === "string" && item.message.trim() && !item.message.includes("{")) {
    return item.message;
  }
  const objName = item.object?.table && item.object?.name
    ? `${item.object.table}[${item.object.name}]`
    : (item.object?.name || item.row_key || "Object");
  const source = item.params?.source_name || item.params?.source_id || "donor";
  return `${objName} (${source}): ${item.message || item.kind}`;
}

// Build the "Before you apply" block list in the fixed order of section 4.6:
// (1) unconfirmed source marks, (2) plan blocking items, (3) Desktop unsaved changes,
// (4) non-canonical target files, (5) full validation failures.
export function buildBlockList({ plan, session, applyPreview, targetModelName } = {}) {
  const blocks = [];
  const rawBlocking = Array.isArray(plan?.blocking) ? plan.blocking : [];
  const preview = applyPreview ?? plan?.apply_preview ?? null;

  // (1) Unconfirmed source marks.
  const marksBlocking = rawBlocking.find((item) => item.kind === "source_marks");
  const marksCount = marksBlocking?.params?.count
    ?? preview?.unconfirmed_marks?.count
    ?? session?.counts?.marks
    ?? 0;
  if (marksCount > 0) {
    blocks.push({
      id: marksBlocking?.item_id || "block-marks",
      category: "marks",
      kind: "source_marks",
      icon: "warn",
      text: marksCount === 1
        ? "1 row changed in its source, and you did not confirm it."
        : t("plan.block.marks", { n: marksCount }),
      fix: t("plan.block.marks.fix"),
      files: [],
      actionLabel: t("plan.block.marks.action"),
      action: { type: "compare_marks" },
    });
  }

  // (2) Plan blocking items (excluding source_marks and full-validation dax_parse).
  for (const item of rawBlocking) {
    if (item.kind === "source_marks" || item.kind === "dax_parse") continue;
    const isImpact = IMPACT_BLOCK_KINDS.has(item.kind);
    const isNoTarget = item.kind === "no_target_model";
    blocks.push({
      id: item.item_id || `block-${item.kind}-${item.row_key || blocks.length}`,
      category: "plan",
      kind: item.kind,
      icon: "bad",
      text: formatBlockingText(item),
      fix: formatBlockingFix(item),
      files: [],
      actionLabel: isNoTarget
        ? t("work.change_target")
        : isImpact
          ? t("plan.block.show_impact")
          : t("plan.block.show_row"),
      action: isNoTarget
        ? { type: "change_target" }
        : isImpact
          ? { type: "show_impact", rowKey: item.row_key, itemId: item.item_id }
          : { type: "show_row", rowKey: item.row_key },
    });
  }

  // (3) Desktop unsaved changes.
  if (preview?.desktop_state === "open_unsaved") {
    blocks.push({
      id: "block-desktop",
      category: "desktop",
      kind: "desktop",
      icon: "bad",
      text: t("plan.block.desktop", { target: targetModelName || "target model" }),
      fix: t("plan.block.desktop.fix"),
      files: [],
      actionLabel: t("plan.block.desktop.action"),
      action: { type: "check_plan" },
    });
  }

  // (4) Non-canonical target files.
  const nonCanonical = Array.isArray(preview?.non_canonical_files) ? preview.non_canonical_files : [];
  if (nonCanonical.length > 0) {
    blocks.push({
      id: "block-files",
      category: "files",
      kind: "files",
      icon: "warn",
      text: nonCanonical.length === 1
        ? "1 target file is not in the Power BI Desktop format."
        : t("plan.block.files", { n: nonCanonical.length }),
      fix: t("plan.block.files.fix"),
      files: nonCanonical,
      actionLabel: t("plan.block.files.action"),
      action: { type: "format_files" },
    });
  }

  // (5) Full validation failures (dax_parse items and preview.validation.failed_checks).
  for (const item of rawBlocking) {
    if (item.kind !== "dax_parse") continue;
    blocks.push({
      id: item.item_id || `block-dax-${item.row_key || blocks.length}`,
      category: "validation",
      kind: "dax_parse",
      icon: "bad",
      text: formatBlockingText(item),
      fix: formatBlockingFix(item),
      files: [],
      actionLabel: t("plan.block.show_row"),
      action: { type: "show_row", rowKey: item.row_key },
    });
  }
  const failedChecks = Array.isArray(preview?.validation?.failed_checks)
    ? preview.validation.failed_checks
    : [];
  for (const check of failedChecks) {
    const id = check.item_id || `block-validation-${check.row_key || blocks.length}`;
    if (blocks.some((existing) => existing.id === id)) continue;
    blocks.push({
      id,
      category: "validation",
      kind: check.kind || "dax_parse",
      icon: "bad",
      text: formatBlockingText({ kind: "dax_parse", ...check }),
      fix: formatBlockingFix({ kind: "dax_parse", ...check }),
      files: [],
      actionLabel: t("plan.block.show_row"),
      action: { type: "show_row", rowKey: check.row_key },
    });
  }

  return blocks;
}

export function planStripState({ plan, blocks = [], checking = false, checkTime = "09:30" } = {}) {
  const time = formatCheckTime(checkTime);
  const deletesCount = planDeletesCount(plan);
  const applyVariant = deletesCount > 0 ? "destructive" : "default";

  if (checking) {
    return {
      state: "checking",
      badgeTone: "plain",
      badgeLabel: t("plan.check.loading"),
      body: "Validating expressions and dependencies.",
      reason: "Wait for the plan check.",
      applyDisabled: true,
      applyVariant,
    };
  }

  const blockCount = Math.max(blocks.length, Array.isArray(plan?.blocking) ? plan.blocking.length : 0);
  if (blockCount > 0 || plan?.status === "invalid") {
    const n = Math.max(blockCount, 1);
    return {
      state: "invalid",
      badgeTone: "bad",
      badgeLabel: t("plan.strip.invalid", { n }),
      body: n === 1
        ? `1 blocking item in the plan. Full check ${time}.`
        : t("plan.strip.invalid.body", { n, time }),
      reason: n === 1
        ? "Fix 1 item before you apply."
        : t("plan.strip.invalid.fix", { n }),
      applyDisabled: true,
      applyVariant,
    };
  }

  const stepCount = plan?.steps?.length ?? plan?.summary?.steps ?? 0;
  if (stepCount === 0) {
    return {
      state: "empty",
      badgeTone: "ok",
      badgeLabel: t("plan.strip.valid"),
      body: t("plan.strip.empty.body", { time }),
      reason: t("plan.strip.empty.note"),
      applyDisabled: true,
      applyVariant,
    };
  }

  const warnCount = plan?.warnings?.length ?? 0;
  if (warnCount > 0 || plan?.status === "valid_with_warnings") {
    const w = Math.max(warnCount, 1);
    const badgeLabel = w === 1 ? "Valid with 1 warning" : t("plan.strip.warnings", { n: w });
    const body = stepCount === 1 && w === 1
      ? `1 plan step, 1 warning. Full check ${time}.`
      : w === 1
        ? `${stepCount} plan steps, 1 warning. Full check ${time}.`
        : t("plan.strip.warnings.body", { steps: stepCount, n: w, time });
    return {
      state: "valid_with_warnings",
      badgeTone: "warn",
      badgeLabel,
      body,
      reason: null,
      applyDisabled: false,
      applyVariant,
    };
  }

  const body = stepCount === 1
    ? `1 plan step. Full check ${time}.`
    : t("plan.strip.valid.body", { steps: stepCount, time });
  return {
    state: "valid",
    badgeTone: "ok",
    badgeLabel: t("plan.strip.valid"),
    body,
    reason: null,
    applyDisabled: false,
    applyVariant,
  };
}

function countForType(domainSummary, change, typeKey) {
  return domainSummary?.[change]?.by_type?.[typeKey] ?? 0;
}

export function planSummaryGroups(plan) {
  const modelSummary = plan?.summary?.model ?? {};
  const reportSummary = plan?.summary?.report ?? {};
  const operations = Array.isArray(plan?.operations) ? plan.operations : [];
  const rebindCount = operations.filter((op) => op.op === "REBIND_FIELD").length;

  const buildRows = (types, summaryObj, defaultKeys, extraCounts = {}) => {
    const rows = [];
    for (const [key, label] of types) {
      const created = countForType(summaryObj, "created", key) + (extraCounts[key]?.created ?? 0);
      const deleted = countForType(summaryObj, "deleted", key) + (extraCounts[key]?.deleted ?? 0);
      const modified = countForType(summaryObj, "modified", key) + (extraCounts[key]?.modified ?? 0);
      const renamed = countForType(summaryObj, "renamed", key) + (extraCounts[key]?.renamed ?? 0);
      const total = created + deleted + modified + renamed;
      if (defaultKeys.has(key) || total > 0) {
        rows.push({ key, label, created, deleted, modified, renamed });
      }
    }
    return rows;
  };

  const modelDefaults = new Set(["table", "column", "measure", "relationship"]);
  const reportDefaults = new Set(["page", "visual", "field_binding"]);
  const extraReport = rebindCount > 0 ? { field_binding: { modified: rebindCount } } : {};

  return {
    modelRows: buildRows(MODEL_TYPES, modelSummary, modelDefaults),
    reportRows: buildRows(REPORT_TYPES, reportSummary, reportDefaults, extraReport),
  };
}

function formatOperationTarget(op) {
  if (op.table && op.name && op.object_type !== "table") {
    return `${op.table}[${op.name}]`;
  }
  return op.name || op.row_key || "";
}

function formatOperationView(op) {
  let oldLine = op.old_text ?? null;
  let newLine = op.new_text ?? null;
  if (oldLine === null && newLine === null && (op.old_name || op.new_name)) {
    oldLine = op.old_name ?? null;
    newLine = op.new_name ?? null;
  }
  return {
    opId: op.op_id,
    op: op.op,
    target: formatOperationTarget(op),
    property: op.property || null,
    oldLine,
    newLine,
  };
}

export function planPhaseGroups(plan, { domainFilter = "all", query = "" } = {}) {
  const steps = Array.isArray(plan?.steps) ? plan.steps : [];
  const operations = Array.isArray(plan?.operations) ? plan.operations : [];
  const opById = new Map(operations.map((op) => [op.op_id, op]));
  const buckets = new Map(PHASE_ORDER.map(([phase]) => [phase, []]));
  const q = (query || "").trim().toLowerCase();

  for (const step of steps) {
    const stepOps = (step.operation_ids ?? []).map((id) => opById.get(id)).filter(Boolean);
    const byUiPhase = new Map();

    if (stepOps.length === 0) {
      const fallbackPhase = step.domain === "report" ? "report" : (CHANGE_TO_PHASE[step.change] || "changes");
      byUiPhase.set(fallbackPhase, []);
    } else {
      for (const op of stepOps) {
        const uiPhase = op.domain === "report" ? "report" : (op.phase || "changes");
        if (!byUiPhase.has(uiPhase)) byUiPhase.set(uiPhase, []);
        byUiPhase.get(uiPhase).push(op);
      }
    }

    for (const [uiPhase, phaseOps] of byUiPhase.entries()) {
      const itemDomain = uiPhase === "report" ? "report" : "model";
      if (domainFilter === "model" && itemDomain !== "model") continue;
      if (domainFilter === "report" && itemDomain !== "report") continue;

      const firstOp = phaseOps[0];
      const useOpIdentity = (uiPhase === "rewrites" && step.change !== "modified")
        || (uiPhase === "report" && step.domain !== "report");
      const objectType = useOpIdentity && firstOp?.object_type ? firstOp.object_type : step.object_type;
      const typeLabel = STEP_TYPE_LABELS[objectType] || objectType || "Object";

      let displayTitle = useOpIdentity && firstOp?.name ? firstOp.name : step.name;
      if (uiPhase === "renames" && firstOp?.old_name && firstOp?.new_name && firstOp.old_name !== firstOp.new_name) {
        displayTitle = `${firstOp.old_name} -> ${firstOp.new_name}`;
      } else if (useOpIdentity && firstOp?.table && firstOp?.name && objectType !== "table") {
        displayTitle = `${firstOp.table}[${firstOp.name}]`;
      }

      const opViews = phaseOps.map(formatOperationView);
      if (q) {
        const haystack = [
          typeLabel,
          displayTitle,
          step.name,
          ...phaseOps.flatMap((op) => [op.name, op.table, op.old_name, op.new_name, op.op]),
        ]
          .filter(Boolean)
          .join(" ")
          .toLowerCase();
        if (!haystack.includes(q)) continue;
      }

      const bucket = buckets.get(uiPhase);
      if (bucket) {
        bucket.push({
          id: `${step.step_id}:${uiPhase}`,
          stepId: step.step_id,
          rowKey: (useOpIdentity && firstOp?.row_key) || step.row_key,
          domain: itemDomain,
          phase: uiPhase,
          objectType,
          typeLabel,
          name: step.name,
          displayTitle,
          opCount: opViews.length,
          operations: opViews,
        });
      }
    }
  }

  const result = [];
  for (const [phase, labelKey, baseName] of PHASE_ORDER) {
    const items = buckets.get(phase) ?? [];
    if (items.length > 0) {
      result.push({
        phase,
        baseName,
        label: t(labelKey, { n: items.length }),
        count: items.length,
        items,
      });
    }
  }
  return result;
}
