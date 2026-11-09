// Bulk actions toolbar for selected rows in Compare grid (UI design 4.3).
// All text follows ASD-STE100 rules.
import React, { useState } from "react";
import { Check, ChevronDown, PencilLine, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Menu } from "@/components/ui/menu";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
} from "@/components/ui/dialog";
import { t, tn } from "../copy.js";

export function choiceDisplayName(choice, donors = []) {
  if (!choice) return t("shared.not_set");
  const kind = choice.kind || choice.choice;
  if (kind === "keep" || kind === "keep_target") return t("compare.bulk.keep");
  if (kind === "skip") return t("compare.bulk.skip");
  if (kind === "remove") return t("compare.bulk.remove");
  if (kind === "take_from") {
    const sourceId = choice.source_id || choice.source;
    const donor = donors.find((d) => d.source_id === sourceId);
    const sourceName = choice.source_name || donor?.display_name || donor?.name || sourceId;
    return `${t("compare.bulk.take_group")} ${sourceName}`;
  }
  return kind;
}

export default function BulkBar({
  selectedCount,
  allMatching,
  totalMatching,
  loadedCount,
  marksFilterActive,
  donors = [],
  onApplyChoice,
  onEditTarget,
  onConfirmRows,
  onClearSelection,
  onSelectAllMatching,
  disabled = false,
  reasonId,
  selectedRows = [],
  setMenuRef,
  menuOpen,
  onMenuOpenChange,
}) {
  const [pendingChoice, setPendingChoice] = useState(null);
  const [removalPolicy, setRemovalPolicy] = useState("block");

  const displayCount = allMatching ? totalMatching : selectedCount;

  // Calculate replacement count and skipped count.
  const checkChoiceImpact = (choice) => {
    const isRemove = choice.kind === "remove";
    let replaceCount = 0;
    let skippedCount = 0;

    for (const row of selectedRows) {
      if (row.merge_choice && row.merge_choice.choice !== choice.kind) {
        replaceCount += 1;
      }
      if (isRemove) {
        // Skipped if target is missing
        const targetCell = row.cells?.s0 || (Array.isArray(row.cells) ? row.cells.find((c) => c.role === "target") : null);
        if (targetCell?.state === "missing") skippedCount += 1;
      } else if (choice.kind === "take_from") {
        const donorCell = Array.isArray(row.cells)
          ? row.cells.find((c) => c.source_id === choice.source_id)
          : row.cells?.[choice.source_id];
        if (donorCell?.state === "missing") skippedCount += 1;
      }
    }
    return { replaceCount, skippedCount };
  };

  const handleSelectMenuChoice = (choice) => {
    const { replaceCount, skippedCount } = checkChoiceImpact(choice);
    if (choice.kind === "remove" || replaceCount > 0) {
      setRemovalPolicy("block");
      setPendingChoice({ ...choice, replaceCount, skippedCount });
      return;
    }
    onApplyChoice(choice, { skippedCount: 0 });
  };

  const confirmBulkChoice = () => {
    if (!pendingChoice) return;
    const choice = { ...pendingChoice };
    if (choice.kind === "remove") {
      choice.policy = removalPolicy;
    }
    setPendingChoice(null);
    onApplyChoice(choice, { skippedCount: choice.skippedCount });
  };

  const menuGroups = [
    {
      items: [
        {
          label: t("compare.bulk.keep"),
          onSelect: () => handleSelectMenuChoice({ kind: "keep" }),
        },
      ],
    },
    ...(donors.length > 0
      ? [
          {
            label: t("compare.bulk.take_group"),
            items: donors.map((donor) => ({
              label: `${t("compare.bulk.take_group")} ${donor.display_name || donor.name}`,
              onSelect: () =>
                handleSelectMenuChoice({
                  kind: "take_from",
                  source_id: donor.source_id,
                  source_name: donor.display_name || donor.name,
                }),
            })),
          },
        ]
      : []),
    {
      items: [
        {
          label: t("compare.bulk.skip"),
          onSelect: () => handleSelectMenuChoice({ kind: "skip" }),
        },
      ],
    },
    {
      items: [
        {
          label: t("compare.bulk.remove"),
          destructive: true,
          onSelect: () => handleSelectMenuChoice({ kind: "remove" }),
        },
      ],
    },
  ];

  const choiceLabel = pendingChoice ? choiceDisplayName(pendingChoice, donors) : "";
  const isRemove = pendingChoice?.kind === "remove";
  const affectedCount = Math.max(0, displayCount - (pendingChoice?.skippedCount || 0));

  return (
    <>
      <div className="dc-bulkbar" role="toolbar" aria-label="Bulk actions">
        <span className="dc-bulkbar-count">
          {displayCount === 1 ? "1 selected" : `${displayCount} selected`}
        </span>

        <Menu
          align="start"
          label={t("compare.bulk.set")}
          open={menuOpen}
          onOpenChange={onMenuOpenChange}
          trigger={
            <Button
              id="mcbtn"
              ref={setMenuRef}
              variant="outline"
              size="sm"
              disabled={disabled}
              aria-describedby={reasonId}
              aria-keyshortcuts="M"
              title='Set Merge Choice (M)'
            >
              {t("compare.bulk.set")}
              <ChevronDown className="dc-search-icon" aria-hidden="true" />
            </Button>
          }
          groups={menuGroups}
        />

        {onEditTarget ? (
          <Button
            id="edittarget"
            variant="outline"
            size="sm"
            onClick={onEditTarget}
            disabled={disabled}
            aria-describedby={reasonId}
          >
            <PencilLine className="dc-search-icon" aria-hidden="true" />
            {t("edit.open")}
          </Button>
        ) : null}

        {marksFilterActive ? (
          <Button
            id="confirmrows"
            variant="outline"
            size="sm"
            onClick={onConfirmRows}
            disabled={disabled}
            aria-describedby={reasonId}
          >
            <Check className="dc-search-icon" aria-hidden="true" />
            {tn("compare.bulk.confirm_rows", displayCount)}
          </Button>
        ) : null}

        <span className="dc-spacer" />

        <Button
          id="clearsel"
          variant="ghost"
          size="sm"
          onClick={onClearSelection}
          aria-label={t("shared.clear_selection")}
          aria-keyshortcuts="Escape"
          tooltip={`${t("shared.clear_selection")} (Esc)`}
        >
          <X className="dc-search-icon" aria-hidden="true" />
          {t("shared.clear_selection")}
        </Button>
      </div>

      {selectedCount === loadedCount && loadedCount < totalMatching && !allMatching ? (
        <div className="dc-selall" role="status">
          <span>All {loadedCount} loaded rows are selected.</span>
          <button
            type="button"
            className="dc-link"
            id="selallbtn"
            onClick={onSelectAllMatching}
          >
            {totalMatching > 5000
              ? `Select all 5,000 rows that match the filters (capped at 5,000)`
              : `Select all ${totalMatching} rows that match the filters`}
          </button>
        </div>
      ) : null}

      {allMatching ? (
        <div className="dc-selall" role="status">
          {totalMatching > 5000
            ? `All 5,000 rows that match the filters are selected (capped at 5,000).`
            : `All ${totalMatching} rows that match the filters are selected.`}
        </div>
      ) : null}

      {pendingChoice ? (
        <AlertDialog open={true} onOpenChange={(open) => !open && setPendingChoice(null)}>
          <AlertDialogContent
            title={
              isRemove
                ? tn("compare.bulk.dialog.remove.title", affectedCount)
                : tn("compare.bulk.dialog.set.title", affectedCount, { choice: choiceLabel })
            }
            footer={
              <>
                <AlertDialogCancel asChild>
                  <Button variant="outline" onClick={() => setPendingChoice(null)}>
                    {t("shared.cancel")}
                  </Button>
                </AlertDialogCancel>
                <AlertDialogAction asChild>
                  <Button
                    id="dok"
                    variant={isRemove ? "destructive" : "default"}
                    onClick={confirmBulkChoice}
                  >
                    {isRemove
                      ? t("compare.bulk.dialog.remove.confirm")
                      : t("compare.bulk.dialog.set.confirm")}
                  </Button>
                </AlertDialogAction>
              </>
            }
          >
            <ul>
              {isRemove ? (
                <>
                  <li>{t("compare.bulk.dialog.remove.body")}</li>
                  <li className="mt-2 list-none">
                    <fieldset className="ui-choice border border-[var(--line)] rounded-md p-3">
                      <legend className="ui-choice-legend font-medium text-xs px-1">Removal policy</legend>
                      <div className="flex flex-col gap-2 mt-1">
                        <label className="flex items-start gap-2 cursor-pointer text-sm">
                          <input
                            type="radio"
                            name="bulk-remove-policy"
                            value="block"
                            checked={removalPolicy === "block"}
                            onChange={() => setRemovalPolicy("block")}
                          />
                          <div>
                            <strong>Block</strong>
                            <p className="text-xs text-[var(--text-2)] m-0">
                              Keep references. The plan is not valid until you resolve them.
                            </p>
                          </div>
                        </label>
                        <label className="flex items-start gap-2 cursor-pointer text-sm">
                          <input
                            type="radio"
                            name="bulk-remove-policy"
                            value="cascade"
                            checked={removalPolicy === "cascade"}
                            onChange={() => setRemovalPolicy("cascade")}
                          />
                          <div>
                            <strong>Cascade</strong>
                            <p className="text-xs text-[var(--text-2)] m-0">
                              Also delete objects that use these objects.
                            </p>
                          </div>
                        </label>
                      </div>
                    </fieldset>
                  </li>
                </>
              ) : null}
              {pendingChoice.replaceCount > 0 ? (
                <li>{tn("compare.bulk.dialog.set.replace", pendingChoice.replaceCount)}</li>
              ) : null}
              {pendingChoice.skippedCount > 0 ? (
                <li>
                  {tn("compare.bulk.dialog.set.skipped", pendingChoice.skippedCount, {
                    source: pendingChoice.source_name || "target",
                  })}
                </li>
              ) : null}
            </ul>
          </AlertDialogContent>
        </AlertDialog>
      ) : null}
    </>
  );
}
