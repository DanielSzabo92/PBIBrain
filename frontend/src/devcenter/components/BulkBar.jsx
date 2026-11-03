// Bulk actions toolbar for selected rows in Compare grid (UI design 4.3).
// All text follows ASD-STE100 rules.
import React, { useState } from "react";
import { Check, ChevronDown, X } from "lucide-react";
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
  onConfirmRows,
  onClearSelection,
  onSelectAllMatching,
  disabled = false,
  reasonId,
  selectedRows = [],
  setMenuRef,
  modeControl,
  menuOpen,
  onMenuOpenChange,
}) {
  const [pendingChoice, setPendingChoice] = useState(null);

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
      setPendingChoice({ ...choice, replaceCount, skippedCount });
      return;
    }
    onApplyChoice(choice, { skippedCount: 0 });
  };

  const confirmBulkChoice = () => {
    if (!pendingChoice) return;
    const choice = { ...pendingChoice };
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

        {modeControl}

        <Button
          id="clearsel"
          variant="ghost"
          size="sm"
          onClick={onClearSelection}
          aria-label={t("shared.clear_selection")}
        >
          <X className="dc-search-icon" aria-hidden="true" />
          {t("shared.clear_selection")}
        </Button>
      </div>

      {loadedCount < totalMatching && !allMatching ? (
        <div className="dc-selall" role="status">
          <span>All {loadedCount} loaded rows are selected.</span>
          <button
            type="button"
            className="dc-link"
            id="selallbtn"
            onClick={onSelectAllMatching}
          >
            Select all {totalMatching} rows that match the filters
          </button>
        </div>
      ) : null}

      {allMatching ? (
        <div className="dc-selall" role="status">
          All {totalMatching} rows that match the filters are selected.
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
                  <li>{t("compare.bulk.dialog.remove.policy")}</li>
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
