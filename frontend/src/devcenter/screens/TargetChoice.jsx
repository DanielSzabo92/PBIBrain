// Target model and target report radio lists (UI design 4.1 step 2, 4.8 "Change target").
// "Copy of <source>" and "Empty" open the native folder picker. A cancel of the picker keeps the old choice.
import React from "react";
import { Button } from "@/components/ui/button";
import { ChoiceRadio } from "@/components/ui/choice-radio";
import { t } from "../copy.js";
import { targetModelItems, targetReportItems } from "./sessionModel.js";

export default function TargetChoice({ sources, model, report, folder, onModel, onReport, pickFolder, disabled = false }) {
  const [picking, setPicking] = React.useState(false);

  const chooseModel = async (value, force = false) => {
    if (value.startsWith("existing:")) {
      onModel(value, null);
      return;
    }
    if (!force && value === model && folder) return;
    setPicking(true);
    try {
      const picked = await pickFolder();
      if (picked) onModel(value, picked);
    } finally {
      setPicking(false);
    }
  };

  const folderLine = folder ? (
    <div className="dc-folder-line">
      <span>{t("create.target.copy.folder", { path: folder })}</span>
      <Button variant="outline" size="sm" disabled={disabled || picking} onClick={() => chooseModel(model, true)}>{t("create.target.copy.change")}</Button>
    </div>
  ) : null;

  const modelItems = targetModelItems(sources).map((item) => ({
    value: item.value,
    label: item.label,
    disabled: item.disabled,
    reason: item.reason ?? item.help,
    children: item.value.startsWith("existing:") ? null : folderLine,
  }));
  const reportItems = targetReportItems(sources).map((item) => ({
    value: item.value,
    label: item.label,
    disabled: item.disabled,
    reason: item.reason ?? item.help,
  }));

  return (
    <div className="dc-target-choice">
      <ChoiceRadio legend={t("create.target.model")} items={modelItems} value={model ?? ""} onValueChange={(value) => chooseModel(value)} disabled={disabled || picking} />
      <ChoiceRadio legend={t("create.target.report")} items={reportItems} value={report ?? "new_empty"} onValueChange={onReport} disabled={disabled} />
    </div>
  );
}
