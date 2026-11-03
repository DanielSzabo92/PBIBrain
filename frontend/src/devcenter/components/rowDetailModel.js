// Pure model and helpers for RowDetail, NameField, and ProposalCard (UI design 4.4, 5.3, 6.2, 8, step U6).
// All text follows ASD-STE100 rules. No React import, so node --test can test this module directly.
import { t } from "../copy.js";
import { phraseText } from "../phrases.js";

export const PICKER_PROPERTIES = Object.freeze({
  measure: [
    { id: "expression", label: "Expression" },
    { id: "format_string", label: "Format string" },
    { id: "display_folder", label: "Display folder" },
    { id: "description", label: "Description" },
    { id: "hidden", label: "Hidden" },
  ],
  column: [
    { id: "expression", label: "Expression" },
    { id: "data_type", label: "Data type" },
    { id: "format_string", label: "Format string" },
    { id: "display_folder", label: "Display folder" },
    { id: "description", label: "Description" },
    { id: "summarize_by", label: "Summarize by" },
    { id: "sort_by_column", label: "Sort-by column" },
    { id: "data_category", label: "Data category" },
    { id: "hidden", label: "Hidden" },
  ],
  relationship: [
    { id: "cardinality", label: "Cardinality" },
    { id: "cross_filter_direction", label: "Cross-filter direction" },
    { id: "active", label: "Active" },
    { id: "security_filter_direction", label: "Security filter direction" },
    { id: "referential_integrity", label: "Assume referential integrity" },
  ],
});

export function pickerTypeKey(objectType, subtype) {
  const raw = subtype || objectType || "";
  if (raw === "measure" || objectType === "measure") return "measure";
  if (raw === "data_column" || raw === "calculated_column" || objectType === "column") return "column";
  if (raw === "relationship" || objectType === "relationship") return "relationship";
  return null;
}

export function normalizeChoiceKind(kind) {
  if (!kind) return "";
  if (kind === "take_from") return "take";
  if (kind === "keep_target") return "keep";
  if (kind === "take_selected_properties") return "take_properties";
  if (kind === "add_as_new_name") return "add_new_name";
  if (kind === "promote_to_model") return "promote";
  if (kind === "copy_to_target_report") return "copy_to_report";
  return kind;
}

export function getRowCell(row, sourceId) {
  if (!row || !sourceId) return null;
  if (Array.isArray(row.cells)) {
    return row.cells.find((c) => c.source_id === sourceId) || null;
  }
  return row.cells?.[sourceId] || null;
}

export function getTargetCell(row, targetModelId, targetReportId) {
  if (!row) return null;
  if (Array.isArray(row.cells)) {
    return (
      row.cells.find((c) => c.role === "target") ||
      (targetModelId ? row.cells.find((c) => c.source_id === targetModelId) : null) ||
      (targetReportId ? row.cells.find((c) => c.source_id === targetReportId) : null) ||
      null
    );
  }
  if (!row.cells) return null;
  if (row.cells.s0) return row.cells.s0;
  if (targetModelId && row.cells[targetModelId]) return row.cells[targetModelId];
  if (targetReportId && row.cells[targetReportId]) return row.cells[targetReportId];
  if (row.cells["src-3"]) return row.cells["src-3"];
  if (row.cells["src-1"]) return row.cells["src-1"];
  const firstKey = Object.keys(row.cells)[0];
  return firstKey ? row.cells[firstKey] : null;
}

export function isCellPresent(cell) {
  if (!cell) return false;
  if (typeof cell.present === "boolean") return cell.present;
  return cell.state !== "missing";
}

export function getPresentDonors(row, donors = []) {
  return donors.filter((donor) => isCellPresent(getRowCell(row, donor.source_id)));
}

export function getRowPropertiesForDonor(row, donorId) {
  const cell = getRowCell(row, donorId);
  const cellProps = cell?.phrases || cell?.properties;
  if (Array.isArray(cellProps) && cellProps.length > 0) {
    return cellProps.map((p) =>
      typeof p === "string" ? { phrase_id: p, property: extractPropertyId({ phrase_id: p }) } : p
    );
  }
  if (Array.isArray(row?.properties)) {
    return donorId
      ? row.properties.filter((p) => !p.source_id || p.source_id === donorId)
      : row.properties;
  }
  return [];
}

export function extractPropertyId(propItem) {
  if (!propItem) return "";
  if (propItem.property) return propItem.property;
  const raw = String(propItem.phrase_id || "");
  return raw
    .replace(/^compare\.property\./, "")
    .replace(/_changed$/, "");
}

export function buildPropertyPickerItems(row, donorId) {
  const typeKey = pickerTypeKey(row?.object_type, row?.subtype);
  const catalog = PICKER_PROPERTIES[typeKey] || [];
  if (catalog.length === 0) return [];
  const diffItems = getRowPropertiesForDonor(row, donorId);
  const diffByProp = new Map();
  for (const item of diffItems) {
    const propId = extractPropertyId(item);
    if (propId) diffByProp.set(propId, item);
  }

  return catalog.map((entry) => {
    const diff = diffByProp.get(entry.id) || null;
    if (diff) {
      const phrase = phraseText(diff.phrase_id || `${entry.id}_changed`);
      let summary = t("row.props.different", { phrase });
      if (diff.old !== undefined && diff.old !== null && diff.new !== undefined && diff.new !== null) {
        summary = `${diff.old} -> ${diff.new}`;
      } else if (diff.new !== undefined && diff.new !== null) {
        summary = String(diff.new);
      }
      return {
        id: entry.id,
        label: entry.label,
        different: true,
        disabled: false,
        summary,
      };
    }
    return {
      id: entry.id,
      label: entry.label,
      different: false,
      disabled: true,
      summary: t("row.props.same"),
    };
  });
}

// Compute the 8 choices of section 4.4 with their disabled state and disabled reason (A17).
export function buildMergeChoiceSpec({ row, session, donors = [], selectedDonorId = null }) {
  const targetModel = session?.target?.model || null;
  const targetReport = session?.target?.report || null;
  const targetCell = getTargetCell(row, targetModel?.source_id, targetReport?.source_id);
  const inTarget = isCellPresent(targetCell);
  const presentDonors = getPresentDonors(row, donors);
  const hasDonor = presentDonors.length > 0;
  const defaultDonor =
    (selectedDonorId && presentDonors.find((d) => d.source_id === selectedDonorId)) ||
    presentDonors[0] ||
    donors[0] ||
    null;
  const defaultDonorId = defaultDonor?.source_id || null;
  const defaultDonorName =
    defaultDonor?.display_name || defaultDonor?.name || defaultDonorId || "source";

  const pickerKey = pickerTypeKey(row?.object_type, row?.subtype);
  const pickerSupported = Boolean(pickerKey);
  const isReportMeasure = row?.object_type === "report_measure" || row?.subtype === "report_measure";

  const mainChoices = [
    {
      value: "keep",
      label: inTarget ? t("row.choice.keep") : t("row.choice.keep.missing"),
      disabled: false,
      reason: !inTarget ? t("row.choice.keep.missing.help") : null,
    },
    {
      value: "take",
      label: hasDonor
        ? t("row.choice.take", { source: defaultDonorName })
        : t("row.choice.take.any"),
      disabled: !hasDonor,
      reason: !hasDonor ? t("row.choice.take.disabled") : null,
    },
    {
      value: "take_properties",
      label: hasDonor
        ? t("row.choice.props", { source: defaultDonorName })
        : t("row.choice.props.any"),
      disabled: !pickerSupported || !inTarget || !hasDonor,
      reason: !pickerSupported
        ? t("row.choice.props.wrong_type")
        : !inTarget
          ? t("row.choice.props.no_target")
          : !hasDonor
            ? t("row.choice.take.disabled")
            : null,
    },
    {
      value: "add_new_name",
      label: t("row.choice.new_name"),
      disabled: !hasDonor,
      reason: !hasDonor ? t("row.choice.new_name.disabled") : null,
    },
    {
      value: "remove",
      label: t("row.choice.remove"),
      disabled: !inTarget,
      reason: !inTarget ? t("row.choice.remove.disabled") : null,
    },
    {
      value: "skip",
      label: t("row.choice.skip"),
      disabled: false,
      reason: t("row.choice.skip.help"),
    },
  ];

  const reportMeasureChoices = isReportMeasure
    ? [
        {
          value: "promote",
          label: t("row.choice.promote"),
          disabled: false,
          reason: t("row.choice.promote.help"),
        },
        {
          value: "copy_to_report",
          label: t("row.choice.copy"),
          disabled: inTarget,
          reason: inTarget
            ? t("row.choice.copy.disabled")
            : t("row.choice.copy.help"),
        },
      ]
    : [];

  return {
    inTarget,
    presentDonors,
    defaultDonorId,
    defaultDonorName,
    isReportMeasure,
    mainChoices,
    reportMeasureChoices,
  };
}

// Format Merge Choice label for the Compare grid column and the Row detail pane.
export function formatMergeChoiceLabel(mc, donors = []) {
  if (!mc) return t("shared.not_set");
  const rawKind = typeof mc === "string" ? mc : mc.kind || mc.choice;
  const kind = normalizeChoiceKind(rawKind);
  const sourceId = typeof mc === "object" ? mc.source_id || mc.source : null;
  const donor = donors.find((d) => d.source_id === sourceId);
  const sourceName =
    (typeof mc === "object" && mc.source_name) ||
    donor?.display_name ||
    donor?.name ||
    sourceId ||
    "source";

  if (kind === "keep") return t("row.choice.keep");
  if (kind === "take") {
    return sourceId
      ? t("row.choice.take", { source: sourceName })
      : t("row.choice.take.any");
  }
  if (kind === "take_properties") {
    const label = sourceId
      ? t("row.choice.props", { source: sourceName })
      : t("row.choice.props.any");
    const count = Array.isArray(mc.properties) ? mc.properties.length : 0;
    return count > 0 ? `${label} (${count})` : label;
  }
  if (kind === "add_new_name") {
    return mc.new_name
      ? `${t("row.choice.new_name")}: ${mc.new_name}`
      : t("row.choice.new_name");
  }
  if (kind === "remove") return t("row.choice.remove");
  if (kind === "skip") return t("row.choice.skip");
  if (kind === "promote") return t("row.choice.promote");
  if (kind === "copy_to_report") return t("row.choice.copy");
  return String(rawKind || t("shared.not_set"));
}

export function getPossibleRenameInfo(row, allRows = [], donors = []) {
  if (!row) return null;
  const checkNotes = (notes, fallbackSourceId) => {
    for (const note of notes || []) {
      const noteId = typeof note === "string" ? note : note.note_id || note.phrase_id;
      if (noteId === "possible_rename" || noteId === "compare.note.possible_rename") {
        const sourceId = note.source_id || fallbackSourceId || donors[0]?.source_id || "src-2";
        const donor = donors.find((d) => d.source_id === sourceId);
        const sourceName = donor?.display_name || donor?.name || sourceId;
        const otherRowKey = note.other_row_key || null;
        const otherRow = otherRowKey ? allRows.find((r) => r.row_key === otherRowKey) : null;
        const donorCell = getRowCell(row, sourceId);
        const otherName = note.other_name || otherRow?.name || donorCell?.name || "renamed object";
        return {
          sourceId,
          sourceName,
          otherRowKey: otherRowKey || `${row.row_key}@${sourceId}`,
          otherName,
        };
      }
    }
    return null;
  };

  const fromRow = checkNotes(row.notes, null);
  if (fromRow) return fromRow;
  if (Array.isArray(row.cells)) {
    for (const cell of row.cells) {
      const found = checkNotes(cell.notes, cell.source_id);
      if (found) return found;
    }
  } else if (row.cells && typeof row.cells === "object") {
    for (const [sourceId, cell] of Object.entries(row.cells)) {
      const found = checkNotes(cell?.notes, sourceId);
      if (found) return found;
    }
  }
  return null;
}

export function getAlignmentStepText(row, donors = []) {
  if (!row) return t("row.alignment.name_type");
  let step = row.alignment_step || null;
  if (!step) {
    for (const donor of donors) {
      const cell = getRowCell(row, donor.source_id);
      if (cell?.step) {
        step = cell.step;
        break;
      }
    }
  }
  if (step === "manual") return t("row.alignment.user");
  if (step === "joined") return t("row.alignment.joined");
  if (step === "lineage_tag") return t("row.alignment.lineage_tag");
  if (step === "moved" || step === "name_table") return t("row.alignment.name_table");
  if (step === "expression") return t("row.alignment.expression");
  return t("row.alignment.name_type");
}

export function getJoinCandidateRows(row, allRows = [], donors = [], targetModelId = null, targetReportId = null) {
  if (!row || !Array.isArray(allRows)) return [];
  const candidates = [];
  for (const candidate of allRows) {
    if (!candidate || candidate.row_key === row.row_key) continue;
    if (candidate.object_type !== row.object_type) continue;
    const tCell = getTargetCell(candidate, targetModelId, targetReportId);
    if (isCellPresent(tCell)) continue;
    const pDonors = getPresentDonors(candidate, donors);
    if (pDonors.length === 0) continue;
    const donor = pDonors[0];
    const donorName = donor.display_name || donor.name || donor.source_id;
    const tablePart = candidate.table ? ` (${candidate.table})` : "";
    candidates.push({
      rowKey: candidate.row_key,
      sourceId: donor.source_id,
      value: candidate.row_key,
      label: `${candidate.name}${tablePart} in ${donorName}`,
    });
  }
  return candidates;
}

export function formatRemovalPolicySummary(policy, repointTarget, removalData, objectType = "measure") {
  const depCount = Array.isArray(removalData?.dependents) ? removalData.dependents.length : 0;
  const cascadeCount =
    typeof removalData?.cascade?.count === "number" ? removalData.cascade.count : depCount;
  if (!policy || policy === "block") {
    if (depCount === 0) return t("row.removal.none");
    return t("row.removal.block", { n: depCount, type: objectType });
  }
  if (policy === "repoint") {
    return t("row.removal.repoint", {
      n: depCount,
      object: repointTarget || t("shared.not_set"),
    });
  }
  if (policy === "cascade") {
    return t("row.removal.cascade", { n: cascadeCount });
  }
  return policy;
}
