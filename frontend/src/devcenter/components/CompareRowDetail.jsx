// Row detail side pane and Merge Choice controls (UI design 4.4, 5.3, 6.2, 8, step U6).
// All text follows ASD-STE100 rules.
import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Circle,
  LoaderCircle,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Combobox } from "@/components/ui/combobox";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  Dialog,
  DialogClose,
  DialogContent,
} from "@/components/ui/dialog";
import { Notice } from "@/components/ui/notice";
import { Select } from "@/components/ui/select";
import { StatusBadge } from "@/components/ui/status-badge";
import { useToast } from "@/components/ui/toast";
import { errorCopy, t } from "../copy.js";
import { phraseText } from "../phrases.js";
import { formatBlockingFix, formatBlockingText } from "../screens/plan/planModel.js";
import { useAction, useResource } from "../useDevCenter.js";
import NameField from "./NameField.jsx";
import ProposalCard from "./ProposalCard.jsx";
import QuestionCard from "./QuestionCard.jsx";
import { STATE_ICONS, normalizeState, stateWord } from "./StateCell.jsx";
import {
  buildMergeChoiceSpec,
  buildPropertyPickerItems,
  formatRemovalPolicySummary,
  getAlignmentStepText,
  getJoinCandidateRows,
  getPossibleRenameInfo,
  getRowCell,
  getRowPropertiesForDonor,
  getTargetCell,
  isCellPresent,
  normalizeChoiceKind,
} from "./rowDetailModel.js";

function FolderPicker({
  donorId,
  donorName,
  objectType,
  value,
  disabled,
  onCommit,
}) {
  const targetFolders = useResource(
    "displayFolders",
    objectType ? { objectType } : {}
  );
  const donorFolders = useResource(
    "displayFolders",
    donorId ? { source: donorId, objectType } : {}
  );

  const groups = useMemo(() => {
    const tList = Array.isArray(targetFolders.data?.folders)
      ? targetFolders.data.folders
      : [];
    const dList = Array.isArray(donorFolders.data?.folders)
      ? donorFolders.data.folders
      : [];
    const tSet = new Set(tList);
    const out = [];
    if (tList.length > 0) {
      out.push({
        label: t("row.folder.group.target"),
        options: tList.map((f) => ({ value: f, label: f })),
      });
    }
    const donorOnly = dList.filter((f) => !tSet.has(f));
    if (donorOnly.length > 0) {
      out.push({
        label: t("row.folder.group.source", { source: donorName || "donor" }),
        options: donorOnly.map((f) => ({
          value: f,
          label: f,
        })),
      });
    }
    return out;
  }, [targetFolders.data, donorFolders.data, donorName]);

  const listError =
    targetFolders.error || donorFolders.error
      ? t("row.folder.fail")
      : undefined;
  const loading =
    targetFolders.status === "loading" && !targetFolders.data;

  return (
    <Combobox
      label={t("row.folder.label")}
      value={value || ""}
      disabled={disabled}
      groups={groups}
      loading={loading}
      loadingText={t("row.folder.loading")}
      listError={listError}
      placeholder="Type a folder"
      createLabel={(text) => t("row.folder.new", { text })}
      onValueChange={(next) => onCommit(next)}
    />
  );
}

// Make a value safe for an HTML id that is also used in a CSS selector.
function domId(value) {
  return String(value ?? "").replace(/[^A-Za-z0-9_-]/g, "-");
}

export default function CompareRowDetail({
  row,
  allRows = [],
  donors: allDonors = [],
  targetName = "Target",
  session,
  selectedCount = 0,
  onClearSelection,
  onClose,
  onEscape,
  onOpenDiff,
  onConfirmRow,
  onPreviousRow,
  onNextRow,
  canPrevious = false,
  canNext = false,
  onSelectRowKey,
  onNavigateImpact,
  http,
  changeDisabled = false,
  reasonId,
  autoFocusHeading = 0,
}) {
  const toast = useToast();
  const headingRef = useRef(null);

  // A target made as a copy of a source holds that source: it is the target column, not a donor.
  const copyOfId = session?.target?.model?.copy_of || null;
  const donors = useMemo(
    () => (copyOfId ? allDonors.filter((d) => d.source_id !== copyOfId) : allDonors),
    [allDonors, copyOfId]
  );

  const mergeChoiceAction = useAction("merge_choice_set");
  const alignmentAction = useAction("alignment_override");
  const confirmRowAction = useAction("row_confirm");

  const planRes = useResource("plan");
  const rulesRes = useResource("namingRules");

  const isRemoving =
    normalizeChoiceKind(
      typeof row?.merge_choice === "string"
        ? row.merge_choice
        : row?.merge_choice?.kind || row?.merge_choice?.choice
    ) === "remove";
  const removalRes = useResource(
    "removal",
    row && isRemoving ? { object: row.row_key } : { object: row?.row_key || "none" }
  );

  const readOnly = Boolean(session?.read_only);
  const disabled = Boolean(changeDisabled || readOnly);
  const effectiveReasonId = reasonId || (readOnly ? "dc-row-readonly-reason" : undefined);

  useEffect(() => {
    if (autoFocusHeading) {
      headingRef.current?.focus();
    }
  }, [autoFocusHeading, row?.row_key]);

  const savedMc = row?.merge_choice;
  const savedKind = useMemo(() => {
    if (!savedMc) return "";
    const raw = typeof savedMc === "string" ? savedMc : savedMc.kind || savedMc.choice;
    return normalizeChoiceKind(raw);
  }, [savedMc]);

  const baseSpec = useMemo(
    () => buildMergeChoiceSpec({ row, session, donors }),
    [row, session, donors]
  );

  const savedSourceId = useMemo(() => {
    if (savedMc && typeof savedMc === "object") {
      return savedMc.source_id || savedMc.source || baseSpec.defaultDonorId;
    }
    return baseSpec.defaultDonorId;
  }, [savedMc, baseSpec.defaultDonorId]);

  const [choiceKind, setChoiceKind] = useState(savedKind);
  const [donorId, setDonorId] = useState(savedSourceId);
  const spec = useMemo(
    () => buildMergeChoiceSpec({ row, session, donors, selectedDonorId: donorId }),
    [row, session, donors, donorId]
  );

  const [selectedProps, setSelectedProps] = useState(() => {
    if (savedMc && typeof savedMc === "object" && Array.isArray(savedMc.properties)) {
      return savedMc.properties;
    }
    return buildPropertyPickerItems(row, savedSourceId)
      .filter((p) => p.different)
      .map((p) => p.id);
  });
  const [propsError, setPropsError] = useState(null);
  const [showChangeName, setShowChangeName] = useState(false);
  const [newName, setNewName] = useState(
    (savedMc && typeof savedMc === "object" && savedMc.new_name) || ""
  );
  const [displayFolder, setDisplayFolder] = useState(
    (savedMc && typeof savedMc === "object" && savedMc.display_folder) ||
      row?.display_folder ||
      ""
  );
  const [alignmentOpen, setAlignmentOpen] = useState(false);
  const [splitDialogOpen, setSplitDialogOpen] = useState(false);
  const [joinDialogOpen, setJoinDialogOpen] = useState(false);
  const [joinCandidateKey, setJoinCandidateKey] = useState("");
  const [unfilteredRows, setUnfilteredRows] = useState([]);
  const splitCancelRef = useRef(null);

  useEffect(() => {
    setChoiceKind(savedKind);
    const nextDonor =
      (savedMc && typeof savedMc === "object" && (savedMc.source_id || savedMc.source)) ||
      baseSpec.defaultDonorId;
    setDonorId(nextDonor);
    if (savedMc && typeof savedMc === "object" && Array.isArray(savedMc.properties)) {
      setSelectedProps(savedMc.properties);
    } else {
      setSelectedProps(
        buildPropertyPickerItems(row, nextDonor)
          .filter((p) => p.different)
          .map((p) => p.id)
      );
    }
    setPropsError(null);
    const savedNewName = (savedMc && typeof savedMc === "object" && savedMc.new_name) || "";
    setNewName(savedNewName);
    setShowChangeName(Boolean(savedNewName && savedKind === "take"));
    setDisplayFolder(
      (savedMc && typeof savedMc === "object" && savedMc.display_folder) ||
        row?.display_folder ||
        ""
    );
  }, [row?.row_key, savedKind, savedMc, baseSpec.defaultDonorId, row]);

  useEffect(() => {
    if (!joinDialogOpen || !http?.getCompareRows) return undefined;
    let active = true;
    http
      .getCompareRows({ state: "all", limit: 200 })
      .then((res) => {
        if (active && Array.isArray(res?.rows)) {
          setUnfilteredRows(res.rows);
        }
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, [joinDialogOpen, http]);

  const handlePaneKeyDown = (event) => {
    if (event.key === "Escape" && !event.defaultPrevented) {
      if (splitDialogOpen || joinDialogOpen) return;
      if (onEscape) {
        onEscape(event);
      } else {
        event.preventDefault();
        onClose?.();
      }
    }
  };

  if (!row) return null;

  // Multi-row selection view (section 4.4 "Many rows selected").
  if (selectedCount > 1) {
    return (
      <aside
        className="dc-row-pane"
        aria-labelledby="dc-row-pane-title"
        onKeyDown={handlePaneKeyDown}
      >
        <div className="dc-row-pane-head">
          <div className="min-w-0">
            <h2
              id="dc-row-pane-title"
              ref={headingRef}
              tabIndex={-1}
              className="text-[14px] font-semibold m-0 truncate outline-none"
            >
              {t("row.multi.title", { n: selectedCount })}
            </h2>
          </div>
          <Button
            id="closepane"
            variant="ghost"
            size="icon"
            onClick={onClose}
            aria-label={t("row.close")}
            title={t("row.close")}
          >
            <X className="w-4 h-4" />
          </Button>
        </div>
        <p className="text-xs text-[var(--text-2)] m-0">{t("row.multi.bulk")}</p>
        <p className="text-xs text-[var(--text-2)] m-0">{t("row.multi.single")}</p>
        <div>
          <Button variant="outline" size="sm" onClick={onClearSelection}>
            {t("row.multi.action")}
          </Button>
        </div>
      </aside>
    );
  }

  const targetModelId = session?.target?.model?.source_id || null;
  const targetReportId = session?.target?.report?.source_id || null;
  const targetCell = getTargetCell(row, targetModelId, targetReportId);
  const inTarget = isCellPresent(targetCell);

  const activeDonor =
    donors.find((d) => d.source_id === donorId) ||
    spec.presentDonors[0] ||
    donors[0] ||
    null;
  const activeDonorId = activeDonor?.source_id || null;
  const activeDonorName =
    activeDonor?.display_name || activeDonor?.name || activeDonorId || "donor";

  const pickerItems = buildPropertyPickerItems(row, activeDonorId);
  const allChoices = [...spec.mainChoices, ...spec.reportMeasureChoices];

  const commitMergeChoice = async (nextChoiceObj) => {
    if (!row || disabled) return;
    await mergeChoiceAction.run({
      row_key: row.row_key,
      choice: nextChoiceObj,
    });
  };

  const handleSelectChoice = async (nextKind) => {
    const found = allChoices.find((c) => c.value === nextKind);
    if (!found || found.disabled || disabled) return;
    setChoiceKind(nextKind);
    setPropsError(null);

    if (nextKind === "keep" || nextKind === "remove" || nextKind === "skip") {
      await commitMergeChoice({ kind: nextKind });
      return;
    }

    if (nextKind === "take") {
      const payload = {
        kind: "take",
        source_id: activeDonorId,
        ...(newName.trim() ? { new_name: newName.trim() } : {}),
        ...(displayFolder ? { display_folder: displayFolder } : {}),
      };
      await commitMergeChoice(payload);
      return;
    }

    if (nextKind === "take_properties") {
      const defaultChecked = buildPropertyPickerItems(row, activeDonorId)
        .filter((p) => p.different)
        .map((p) => p.id);
      setSelectedProps(defaultChecked);
      if (defaultChecked.length === 0) {
        setPropsError(t("row.props.none"));
        return;
      }
      await commitMergeChoice({
        kind: "take_properties",
        source_id: activeDonorId,
        properties: defaultChecked,
        ...(defaultChecked.includes("display_folder") && displayFolder
          ? { display_folder: displayFolder }
          : {}),
      });
      return;
    }

    if (nextKind === "add_new_name") {
      if (newName.trim()) {
        await commitMergeChoice({
          kind: "add_new_name",
          source_id: activeDonorId,
          new_name: newName.trim(),
          ...(displayFolder ? { display_folder: displayFolder } : {}),
        });
      }
      return;
    }

    if (nextKind === "promote" || nextKind === "copy_to_report") {
      await commitMergeChoice({
        kind: nextKind,
        source_id: activeDonorId,
        ...(newName.trim() ? { new_name: newName.trim() } : {}),
        ...(displayFolder ? { display_folder: displayFolder } : {}),
      });
    }
  };

  const handleDonorChange = async (nextSourceId) => {
    setDonorId(nextSourceId);
    setPropsError(null);
    if (choiceKind === "take") {
      await commitMergeChoice({
        kind: "take",
        source_id: nextSourceId,
        ...(newName.trim() ? { new_name: newName.trim() } : {}),
        ...(displayFolder ? { display_folder: displayFolder } : {}),
      });
    } else if (choiceKind === "take_properties") {
      const nextChecked = buildPropertyPickerItems(row, nextSourceId)
        .filter((p) => p.different)
        .map((p) => p.id);
      setSelectedProps(nextChecked);
      if (nextChecked.length === 0) {
        setPropsError(t("row.props.none"));
        return;
      }
      await commitMergeChoice({
        kind: "take_properties",
        source_id: nextSourceId,
        properties: nextChecked,
      });
    } else if (choiceKind === "add_new_name" && newName.trim()) {
      await commitMergeChoice({
        kind: "add_new_name",
        source_id: nextSourceId,
        new_name: newName.trim(),
        ...(displayFolder ? { display_folder: displayFolder } : {}),
      });
    }
  };

  const handleToggleProperty = async (propId, checked) => {
    const next = checked
      ? [...new Set([...selectedProps, propId])]
      : selectedProps.filter((p) => p !== propId);
    setSelectedProps(next);
    if (next.length === 0) {
      setPropsError(t("row.props.none"));
      return;
    }
    setPropsError(null);
    await commitMergeChoice({
      kind: "take_properties",
      source_id: activeDonorId,
      properties: next,
      ...(next.includes("display_folder") && displayFolder
        ? { display_folder: displayFolder }
        : {}),
    });
  };

  const handleCommitName = async (committedName, { valid } = { valid: true }) => {
    if (!valid) return;
    setNewName(committedName);
    if (!choiceKind) return;
    if (choiceKind === "add_new_name" && !committedName.trim()) return;
    await commitMergeChoice({
      kind: choiceKind,
      source_id: activeDonorId,
      ...(committedName.trim() ? { new_name: committedName.trim() } : {}),
      ...(choiceKind === "take_properties" ? { properties: selectedProps } : {}),
      ...(displayFolder ? { display_folder: displayFolder } : {}),
    });
  };

  const handleCommitFolder = async (nextFolder) => {
    setDisplayFolder(nextFolder);
    if (!choiceKind) return;
    await commitMergeChoice({
      kind: choiceKind,
      source_id: activeDonorId,
      ...(newName.trim() ? { new_name: newName.trim() } : {}),
      ...(choiceKind === "take_properties" ? { properties: selectedProps } : {}),
      display_folder: nextFolder || null,
    });
  };

  const handleConfirmRowClick = async () => {
    if (onConfirmRow) {
      await onConfirmRow(row.row_key);
      return;
    }
    const reply = await confirmRowAction.run({ row_keys: [row.row_key] });
    if (reply) {
      toast.show({ tone: "ok", text: t("row.confirm.toast") });
    }
  };

  const candidatePool = unfilteredRows.length > 0 ? unfilteredRows : allRows;
  const possibleRename = getPossibleRenameInfo(row, candidatePool, donors);

  const handleConfirmRename = async () => {
    if (!possibleRename) return;
    await alignmentAction.run({
      action: "confirm",
      source_id: possibleRename.sourceId,
      row_key: row.row_key,
      other_row_key: possibleRename.otherRowKey,
    });
  };

  const handleRejectRename = async () => {
    if (!possibleRename) return;
    await alignmentAction.run({
      action: "reject_rename",
      source_id: possibleRename.sourceId,
      row_key: row.row_key,
      other_row_key: possibleRename.otherRowKey,
    });
  };

  const handleConfirmSplit = async () => {
    const splitDonorId = activeDonorId || donors[0]?.source_id || "src-2";
    const reply = await alignmentAction.run({
      action: "break",
      source_id: splitDonorId,
      row_key: row.row_key,
    });
    setSplitDialogOpen(false);
    if (reply && Array.isArray(reply.row_keys) && reply.row_keys.length > 0) {
      onSelectRowKey?.(reply.row_keys[0]);
    }
    setTimeout(() => {
      headingRef.current?.focus();
    }, 0);
  };

  const joinCandidates = getJoinCandidateRows(
    row,
    candidatePool,
    donors,
    targetModelId,
    targetReportId
  );

  const handleConfirmJoin = async () => {
    const picked = joinCandidates.find(
      (c) => c.value === joinCandidateKey || c.label === joinCandidateKey
    );
    const otherKey = picked?.rowKey || joinCandidateKey;
    const srcId = picked?.sourceId || activeDonorId || donors[0]?.source_id || "src-2";
    if (!otherKey) return;
    const reply = await alignmentAction.run({
      action: "confirm",
      source_id: srcId,
      row_key: row.row_key,
      other_row_key: otherKey,
    });
    setJoinDialogOpen(false);
    setJoinCandidateKey("");
    if (reply && Array.isArray(reply.row_keys) && reply.row_keys.length > 0) {
      onSelectRowKey?.(reply.row_keys[0]);
    }
    setTimeout(() => {
      headingRef.current?.focus();
    }, 0);
  };

  const hasMarks = (row.marks?.length ?? 0) > 0;
  const markSourceName = activeDonorName;

  // No hooks below the early returns above: plain values only.
  const rowBlocking = (planRes.data?.blocking || []).filter(
    (item) => item.row_key === row.row_key
  );
  const rowWarnings = (planRes.data?.warnings || []).filter(
    (item) => item.row_key === row.row_key
  );
  const openProposal =
    (session?.proposals?.open || []).find((p) => p.target_id === row.row_key) || null;
  const openQuestion =
    (session?.questions?.open || []).find((q) => q.target_id === row.row_key) || null;
  const confirmedRules = Array.isArray(rulesRes.data?.rules) ? rulesRes.data.rules : [];

  const donorOptions = (
    spec.presentDonors.length > 0 ? spec.presentDonors : donors
  ).map((d) => ({
    value: d.source_id,
    label: d.display_name || d.name,
  }));

  const showDonorSelect = spec.presentDonors.length > 1;
  const supportsFolder = [
    "measure",
    "column",
    "data_column",
    "calculated_column",
    "hierarchy",
    "report_measure",
  ].includes(row.subtype || row.object_type);

  const inlineError =
    mergeChoiceAction.error || alignmentAction.error || confirmRowAction.error;
  const inlineErrorCopy = inlineError ? errorCopy(inlineError) : null;

  const canSplit = inTarget && spec.presentDonors.length > 0;
  const displayTypeText =
    row.subtype === "report_measure" ? t("row.choice.report_group") : row.object_type;

  const renderChoiceSubfields = (itemValue) => {
    if (choiceKind !== itemValue) return null;

    if (itemValue === "take") {
      return (
        <div className="ui-choice-sub" data-slot="choice-sub">
          {showDonorSelect ? (
            <Select
              label={t("row.source")}
              value={activeDonorId || ""}
              options={donorOptions}
              disabled={disabled}
              onValueChange={handleDonorChange}
            />
          ) : null}

          {!showChangeName ? (
            <div>
              <Button
                type="button"
                variant="outline"
                size="xs"
                disabled={disabled}
                aria-describedby={disabled ? effectiveReasonId : undefined}
                onClick={() => setShowChangeName(true)}
              >
                {t("row.name.change")}
              </Button>
            </div>
          ) : (
            <NameField
              label={t("row.name.label")}
              value={newName}
              savedValue={savedMc?.new_name || ""}
              required={false}
              disabled={disabled}
              reasonId={effectiveReasonId}
              row={row}
              sourceId={activeDonorId}
              displayFolder={displayFolder}
              http={http}
              rules={confirmedRules}
              onChange={setNewName}
              onCommit={handleCommitName}
            />
          )}

          {supportsFolder ? (
            <FolderPicker
              donorId={activeDonorId}
              donorName={activeDonorName}
              objectType={row.object_type}
              value={displayFolder}
              disabled={disabled}
              onCommit={handleCommitFolder}
            />
          ) : null}
        </div>
      );
    }

    if (itemValue === "take_properties") {
      return (
        <div className="ui-choice-sub" data-slot="choice-sub">
          {showDonorSelect ? (
            <Select
              label={t("row.source")}
              value={activeDonorId || ""}
              options={donorOptions}
              disabled={disabled}
              onValueChange={handleDonorChange}
            />
          ) : null}

          <fieldset
            className="dc-props-fieldset"
            aria-invalid={Boolean(propsError) || undefined}
            aria-describedby={propsError ? "dc-props-err" : undefined}
          >
            <legend className="ui-field-label">
              {t("row.props.legend", { source: activeDonorName })}
            </legend>
            <div className="dc-props-list">
              {pickerItems.map((prop) => {
                const checked = selectedProps.includes(prop.id);
                const propSummaryId = `dc-prop-${domId(row.row_key)}-${prop.id}-sum`;
                return (
                  <label
                    key={prop.id}
                    className={`dc-prop-check-row ${prop.disabled ? "is-disabled" : ""}`}
                  >
                    <Checkbox
                      size="target"
                      checked={checked}
                      disabled={disabled || prop.disabled}
                      aria-describedby={propSummaryId}
                      onCheckedChange={(val) =>
                        handleToggleProperty(prop.id, Boolean(val))
                      }
                    />
                    <span className="dc-prop-check-text">
                      <span className="dc-prop-check-label">{prop.label}</span>
                      <span id={propSummaryId} className="dc-prop-check-summary">
                        {prop.summary}
                      </span>
                    </span>
                  </label>
                );
              })}
            </div>
            {propsError ? (
              <p id="dc-props-err" className="ui-field-hint is-error" role="alert">
                <span>{propsError}</span>
              </p>
            ) : null}
          </fieldset>

          {selectedProps.includes("display_folder") && supportsFolder ? (
            <FolderPicker
              donorId={activeDonorId}
              donorName={activeDonorName}
              objectType={row.object_type}
              value={displayFolder}
              disabled={disabled}
              onCommit={handleCommitFolder}
            />
          ) : null}
        </div>
      );
    }

    if (itemValue === "add_new_name") {
      return (
        <div className="ui-choice-sub" data-slot="choice-sub">
          {showDonorSelect ? (
            <Select
              label={t("row.source")}
              value={activeDonorId || ""}
              options={donorOptions}
              disabled={disabled}
              onValueChange={handleDonorChange}
            />
          ) : null}

          <NameField
            label={t("row.name.label")}
            value={newName}
            savedValue={savedMc?.new_name || ""}
            required={true}
            autoProposeOnMount={!newName}
            disabled={disabled}
            reasonId={effectiveReasonId}
            row={row}
            sourceId={activeDonorId}
            displayFolder={displayFolder}
            http={http}
            rules={confirmedRules}
            onChange={setNewName}
            onCommit={handleCommitName}
          />

          {supportsFolder ? (
            <FolderPicker
              donorId={activeDonorId}
              donorName={activeDonorName}
              objectType={row.object_type}
              value={displayFolder}
              disabled={disabled}
              onCommit={handleCommitFolder}
            />
          ) : null}
        </div>
      );
    }

    if (itemValue === "remove") {
      const policy = row.removal_policy?.policy || "block";
      const repointTarget = row.removal_policy?.repoint_target || null;
      return (
        <div className="ui-choice-sub" data-slot="choice-sub">
          <div className="dc-removal-summary">
            <span className="ui-field-label">{t("row.policy.legend")}</span>
            <p className="text-xs text-[var(--text-2)] m-0">
              {formatRemovalPolicySummary(
                policy,
                repointTarget,
                removalRes.data,
                row.object_type
              )}
            </p>
            <div>
              <Button
                type="button"
                variant="outline"
                size="xs"
                onClick={() => onNavigateImpact?.(row.row_key, row.name)}
              >
                {t("row.removal.change")}
              </Button>
            </div>
          </div>
        </div>
      );
    }

    if (itemValue === "promote" || itemValue === "copy_to_report") {
      return (
        <div className="ui-choice-sub" data-slot="choice-sub">
          {showDonorSelect ? (
            <Select
              label={t("row.source")}
              value={activeDonorId || ""}
              options={donorOptions}
              disabled={disabled}
              onValueChange={handleDonorChange}
            />
          ) : null}

          {!showChangeName ? (
            <div>
              <Button
                type="button"
                variant="outline"
                size="xs"
                disabled={disabled}
                aria-describedby={disabled ? effectiveReasonId : undefined}
                onClick={() => setShowChangeName(true)}
              >
                {t("row.name.change")}
              </Button>
            </div>
          ) : (
            <NameField
              label={t("row.name.label")}
              value={newName}
              savedValue={savedMc?.new_name || ""}
              required={false}
              disabled={disabled}
              reasonId={effectiveReasonId}
              row={row}
              sourceId={activeDonorId}
              displayFolder={displayFolder}
              http={http}
              rules={confirmedRules}
              onChange={setNewName}
              onCommit={handleCommitName}
            />
          )}

          {itemValue === "promote" && supportsFolder ? (
            <FolderPicker
              donorId={activeDonorId}
              donorName={activeDonorName}
              objectType="measure"
              value={displayFolder}
              disabled={disabled}
              onCommit={handleCommitFolder}
            />
          ) : null}
        </div>
      );
    }

    return null;
  };

  return (
    <aside
      className="dc-row-pane"
      aria-labelledby="dc-row-pane-title"
      onKeyDown={handlePaneKeyDown}
    >
      {/* 1. Header */}
      <div className="dc-row-pane-head">
        <div className="min-w-0 flex-1">
          <h2
            id="dc-row-pane-title"
            ref={headingRef}
            tabIndex={-1}
            className="text-[14px] font-semibold m-0 truncate outline-none"
          >
            {row.name}
          </h2>
          <div className="text-xs text-[var(--text-2)] mt-0.5 flex flex-wrap items-center gap-1.5">
            <span>
              {row.table
                ? t("row.meta", { type: displayTypeText, table: row.table })
                : displayTypeText}
            </span>
            {row.display_folder ? <span>({row.display_folder})</span> : null}
            <StatusBadge
              tone={
                row.row_state === "conflict" || row.row_state === "type_conflict"
                  ? "bad"
                  : row.row_state === "same"
                    ? "ok"
                    : "warn"
              }
              label={stateWord(row.row_state)}
            />
          </div>
        </div>
        <div className="ui-pane-nav">
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            disabled={!canPrevious}
            aria-label={t("row.previous")}
            title={t("row.previous")}
            onClick={onPreviousRow}
          >
            <ChevronLeft className="w-4 h-4" />
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            disabled={!canNext}
            aria-label={t("row.next")}
            title={t("row.next")}
            onClick={onNextRow}
          >
            <ChevronRight className="w-4 h-4" />
          </Button>
          <Button
            id="closepane"
            type="button"
            variant="ghost"
            size="icon-sm"
            onClick={onClose}
            aria-label={t("row.close")}
            title={t("row.close")}
          >
            <X className="w-4 h-4" />
          </Button>
        </div>
      </div>

      {/* Read-only notice */}
      {readOnly ? (
        <Notice tone="info">
          <span id="dc-row-readonly-reason">{t("shared.read_only.notice")}</span>
        </Notice>
      ) : null}

      {/* Inline error notice */}
      {inlineErrorCopy ? (
        <Notice tone="bad" title={inlineErrorCopy.title}>
          {inlineErrorCopy.body}
        </Notice>
      ) : null}

      {/* 2. Row notices: source mark, possible rename, plan blocking/warnings */}
      {hasMarks ? (
        <Notice
          tone="warn"
          title={t("compare.badge.confirm_first")}
          actions={
            <Button
              type="button"
              variant="outline"
              size="sm"
              loading={confirmRowAction.pending}
              disabled={disabled}
              aria-describedby={disabled ? effectiveReasonId : undefined}
              onClick={handleConfirmRowClick}
            >
              <Check className="w-3.5 h-3.5" aria-hidden="true" />
              {t("row.confirm")}
            </Button>
          }
        >
          {t("row.marks.changed", { source: markSourceName })}
        </Notice>
      ) : null}

      {possibleRename ? (
        <Notice
          tone="info"
          title={t("row.rename", {
            old: possibleRename.otherName,
            source: possibleRename.sourceName,
            new: row.name,
          })}
          actions={
            <>
              <Button
                type="button"
                size="sm"
                loading={alignmentAction.pending}
                disabled={disabled}
                aria-describedby={disabled ? effectiveReasonId : undefined}
                onClick={handleConfirmRename}
              >
                {t("row.rename.confirm")}
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={disabled || alignmentAction.pending}
                aria-describedby={disabled ? effectiveReasonId : undefined}
                onClick={handleRejectRename}
              >
                {t("row.rename.reject")}
              </Button>
            </>
          }
        />
      ) : null}

      {rowBlocking.map((item) => (
        <Notice key={item.item_id || item.kind} tone="bad" title={formatBlockingText(item)}>
          {formatBlockingFix(item)}
        </Notice>
      ))}

      {rowWarnings.map((item) => (
        <Notice key={item.item_id || item.kind} tone="warn">
          {item.message || item.kind}
        </Notice>
      ))}

      {/* 3. Open agent proposal card */}
      {openProposal ? (
        <ProposalCard
          key={row.row_key}
          proposal={openProposal}
          row={row}
          donors={donors}
          disabled={disabled}
          reasonId={effectiveReasonId}
        />
      ) : openQuestion ? (
        <QuestionCard
          key={openQuestion.id}
          question={openQuestion}
          donors={donors}
          disabled={disabled}
          reasonId={effectiveReasonId}
        />
      ) : null}

      {/* 4. Merge Choice fieldset */}
      <fieldset
        className="ui-choice dc-merge-choice-box"
        aria-busy={mergeChoiceAction.pending ? "true" : undefined}
      >
        <legend className="ui-choice-legend">{t("row.choice.legend")}</legend>
        <div
          className="ui-choice-list"
          role="radiogroup"
          aria-label={t("row.choice.legend")}
          aria-busy={mergeChoiceAction.pending ? "true" : undefined}
        >
          {spec.mainChoices.map((item) => {
            const selected = choiceKind === item.value;
            const itemId = `mc-${domId(row.row_key)}-${item.value}`;
            const reasonIdAttr = item.reason ? `${itemId}-reason` : undefined;
            const descIds = [
              reasonIdAttr,
              disabled ? effectiveReasonId : null,
            ]
              .filter(Boolean)
              .join(" ");
            return (
              <div
                key={item.value}
                className="ui-choice-item"
                data-selected={selected || undefined}
                data-disabled={item.disabled || disabled || undefined}
              >
                <div className="ui-choice-row">
                  <button
                    type="button"
                    role="radio"
                    id={itemId}
                    aria-checked={selected}
                    aria-busy={
                      selected && mergeChoiceAction.pending ? "true" : undefined
                    }
                    aria-describedby={descIds || undefined}
                    disabled={item.disabled || disabled}
                    className="ui-radio"
                    data-state={selected ? "checked" : "unchecked"}
                    onClick={() => handleSelectChoice(item.value)}
                  >
                    {selected ? <span className="ui-radio-dot" /> : null}
                  </button>
                  <label className="ui-choice-label" htmlFor={itemId}>
                    {item.label}
                  </label>
                </div>
                {item.reason ? (
                  <p id={reasonIdAttr} className="ui-choice-reason">
                    {item.reason}
                  </p>
                ) : null}
                {renderChoiceSubfields(item.value)}
              </div>
            );
          })}

          {spec.reportMeasureChoices.length > 0 ? (
            <div className="dc-choice-group">
              <div className="dc-choice-group-label">{t("row.choice.report_group")}</div>
              {spec.reportMeasureChoices.map((item) => {
                const selected = choiceKind === item.value;
                const itemId = `mc-${domId(row.row_key)}-${item.value}`;
                const reasonIdAttr = item.reason ? `${itemId}-reason` : undefined;
                const descIds = [
                  reasonIdAttr,
                  disabled ? effectiveReasonId : null,
                ]
                  .filter(Boolean)
                  .join(" ");
                return (
                  <div
                    key={item.value}
                    className="ui-choice-item"
                    data-selected={selected || undefined}
                    data-disabled={item.disabled || disabled || undefined}
                  >
                    <div className="ui-choice-row">
                      <button
                        type="button"
                        role="radio"
                        id={itemId}
                        aria-checked={selected}
                        aria-busy={
                          selected && mergeChoiceAction.pending ? "true" : undefined
                        }
                        aria-describedby={descIds || undefined}
                        disabled={item.disabled || disabled}
                        className="ui-radio"
                        data-state={selected ? "checked" : "unchecked"}
                        onClick={() => handleSelectChoice(item.value)}
                      >
                        {selected ? <span className="ui-radio-dot" /> : null}
                      </button>
                      <label className="ui-choice-label" htmlFor={itemId}>
                        {item.label}
                      </label>
                    </div>
                    {item.reason ? (
                      <p id={reasonIdAttr} className="ui-choice-reason">
                        {item.reason}
                      </p>
                    ) : null}
                    {renderChoiceSubfields(item.value)}
                  </div>
                );
              })}
            </div>
          ) : null}
        </div>
        {mergeChoiceAction.pending ? (
          <p className="ui-choice-status" role="status">
            <LoaderCircle className="spin" aria-hidden="true" />
            <span>{t("row.saving")}</span>
          </p>
        ) : null}
      </fieldset>

      {/* 5. Alignment section (collapsed by default) */}
      <section className="dc-pane-section" aria-labelledby="dc-pane-align-btn">
        <button
          id="dc-pane-align-btn"
          type="button"
          className="dc-align-toggle"
          aria-expanded={alignmentOpen}
          onClick={() => setAlignmentOpen((prev) => !prev)}
        >
          <ChevronDown
            className={`w-4 h-4 transition-transform ${alignmentOpen ? "rotate-180" : ""}`}
            aria-hidden="true"
          />
          <span>{t("row.alignment.title")}</span>
        </button>

        {alignmentOpen ? (
          <div className="dc-align-body">
            <div className="dc-align-meta">
              <span className="text-[var(--text-2)]">{t("row.alignment.by")}: </span>
              <span className="font-medium">{getAlignmentStepText(row, donors)}</span>
            </div>

            {donors.map((d) => {
              const c = getRowCell(row, d.source_id);
              if (c?.name && c.name !== row.name) {
                return (
                  <div key={d.source_id} className="text-xs text-[var(--text-2)]">
                    {d.display_name || d.name}: {c.name}
                  </div>
                );
              }
              return null;
            })}

            <div className="dc-align-actions">
              {possibleRename ? (
                <>
                  <Button
                    type="button"
                    size="xs"
                    disabled={disabled || alignmentAction.pending}
                    aria-describedby={disabled ? effectiveReasonId : undefined}
                    onClick={handleConfirmRename}
                  >
                    {t("row.rename.confirm")}
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="xs"
                    disabled={disabled || alignmentAction.pending}
                    aria-describedby={disabled ? effectiveReasonId : undefined}
                    onClick={handleRejectRename}
                  >
                    {t("row.rename.reject")}
                  </Button>
                </>
              ) : null}

              {canSplit ? (
                <Button
                  type="button"
                  variant="outline"
                  size="xs"
                  disabled={disabled}
                  aria-describedby={disabled ? effectiveReasonId : undefined}
                  onClick={() => setSplitDialogOpen(true)}
                >
                  {t("row.split")}
                </Button>
              ) : null}

              <Button
                type="button"
                variant="outline"
                size="xs"
                disabled={disabled}
                aria-describedby={disabled ? effectiveReasonId : undefined}
                onClick={() => setJoinDialogOpen(true)}
              >
                {t("row.join")}
              </Button>
            </div>
          </div>
        ) : null}
      </section>

      {/* 6. Sources / Differences by source */}
      <section className="dc-pane-section" aria-labelledby="dc-pane-diffs-title">
        <h3 id="dc-pane-diffs-title" className="dc-pane-sec-title">
          {t("sources.title")}
        </h3>

        {/* Target card */}
        <div className="dc-source-diff-card">
          <div className="dc-source-diff-head">
            <span className="font-medium text-xs">
              {targetName} ({t("compare.state.target")})
            </span>
            <span className="text-xs text-[var(--text-2)]">
              {inTarget ? t("compare.state.target") : t("compare.state.missing")}
            </span>
          </div>
        </div>

        {/* Donor cards */}
        {donors.map((donor) => {
          const cell = getRowCell(row, donor.source_id);
          const rawState = cell?.state || "same";
          const normState = normalizeState(rawState);
          const Icon = STATE_ICONS[normState] || STATE_ICONS.same;
          const word = stateWord(rawState);
          const propsList = getRowPropertiesForDonor(row, donor.source_id);
          const cellNotes = cell?.notes || [];

          return (
            <div key={donor.source_id} className="dc-source-diff-card">
              <div className="dc-source-diff-head">
                <span className="font-medium text-xs">
                  {donor.display_name || donor.name}
                </span>
                <span className={`dc-st dc-st-${normState} text-xs`}>
                  <Icon aria-hidden="true" />
                  <span>{word}</span>
                  {cell?.changed ? (
                    <span className="dc-st-changed" title={t("compare.changed.title")}>
                      <Circle aria-hidden="true" />
                      <span className="sr-only">{t("compare.changed")}</span>
                    </span>
                  ) : null}
                </span>
              </div>

              {propsList.length > 0 ? (
                <ul className="dc-source-diff-list">
                  {propsList.map((p, idx) => {
                    const phrase = phraseText(p.phrase_id || p.property);
                    const hasValues =
                      p.old !== undefined &&
                      p.old !== null &&
                      p.new !== undefined &&
                      p.new !== null;
                    return (
                      <li key={idx}>
                        <span>{phrase}</span>
                        {hasValues ? (
                          <span className="text-[var(--text-2)]">
                            {`: ${p.old} -> ${p.new}`}
                          </span>
                        ) : null}
                      </li>
                    );
                  })}
                </ul>
              ) : null}

              {cellNotes.length > 0 ? (
                <ul className="dc-source-diff-list">
                  {cellNotes.map((n, idx) => {
                    const nid = typeof n === "string" ? n : n.note_id || n.phrase_id;
                    return <li key={idx}>{phraseText(nid)}</li>;
                  })}
                </ul>
              ) : null}

              {normState !== "same" ? (
                <div className="mt-1.5">
                  <Button
                    type="button"
                    variant="outline"
                    size="xs"
                    onClick={(e) => onOpenDiff?.(donor, e.currentTarget)}
                  >
                    {t("row.diff")}
                  </Button>
                </div>
              ) : null}
            </div>
          );
        })}
      </section>

      {/* 7. Impact link */}
      <div className="pt-1">
        <button
          type="button"
          className="dc-link text-xs"
          onClick={() => onNavigateImpact?.(row.row_key, row.name)}
        >
          {t("row.impact_link")}
        </button>
      </div>

      {/* Split Row AlertDialog */}
      <AlertDialog open={splitDialogOpen} onOpenChange={setSplitDialogOpen}>
        <AlertDialogContent
          title={t("row.split.title", { object: row.name })}
          description={t("row.split.body")}
          onOpenAutoFocus={(e) => {
            e.preventDefault();
            splitCancelRef.current?.focus();
          }}
          onCloseAutoFocus={(e) => {
            e.preventDefault();
            headingRef.current?.focus();
          }}
          footer={
            <>
              <AlertDialogCancel asChild>
                <Button ref={splitCancelRef} variant="outline">
                  {t("shared.cancel")}
                </Button>
              </AlertDialogCancel>
              <AlertDialogAction asChild>
                <Button
                  loading={alignmentAction.pending}
                  onClick={handleConfirmSplit}
                >
                  {t("row.split.confirm")}
                </Button>
              </AlertDialogAction>
            </>
          }
        />
      </AlertDialog>

      {/* Join with a row Dialog */}
      <Dialog open={joinDialogOpen} onOpenChange={setJoinDialogOpen}>
        <DialogContent
          title={t("row.join.title", { object: row.name })}
          onCloseAutoFocus={(e) => {
            e.preventDefault();
            headingRef.current?.focus();
          }}
          footer={
            <>
              <DialogClose asChild>
                <Button variant="outline">{t("shared.cancel")}</Button>
              </DialogClose>
              <Button
                disabled={!joinCandidateKey || alignmentAction.pending}
                loading={alignmentAction.pending}
                onClick={handleConfirmJoin}
              >
                {t("row.join.confirm")}
              </Button>
            </>
          }
        >
          <Combobox
            label={t("row.join.search")}
            value={joinCandidateKey}
            onValueChange={setJoinCandidateKey}
            placeholder={t("row.join.search")}
            groups={[
              {
                label: displayTypeText,
                options: joinCandidates.map((c) => ({
                  value: c.value,
                  label: c.label,
                })),
              },
            ]}
          />
        </DialogContent>
      </Dialog>
    </aside>
  );
}
