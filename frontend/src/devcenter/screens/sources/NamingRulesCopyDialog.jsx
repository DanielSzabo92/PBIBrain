// Copy rules dialog (UI design 4.8 and 13, U5).
import React, { useState } from "react";
import { Info } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { useToast } from "@/components/ui/toast";
import { errorCopy, t } from "../../copy.js";
import { useAction } from "../../useDevCenter.js";

export default function NamingRulesCopyDialog({
  open,
  onOpenChange,
  session,
  sourceRuleCounts = {},
  targetModelName,
  onCopied,
}) {
  const toast = useToast();
  const copyAction = useAction("naming_rules_copy");
  const [selectedSourceId, setSelectedSourceId] = useState(null);

  const targetSourceId = session.target?.model?.source_id;
  const sources = (session.sources ?? []).filter((s) => {
    // Only models, and exclude the target model.
    if (s.source_id === targetSourceId) return false;
    const kind = s.kind;
    return kind === "pbip" || kind === "tmdl_folder" || kind === "model_bim" || kind === "cloud_model";
  });

  const selectedCount = selectedSourceId ? (sourceRuleCounts[selectedSourceId] ?? 0) : 0;

  const handleCopy = async () => {
    if (!selectedSourceId || selectedCount === 0) return;
    const reply = await copyAction.run({ source_id: selectedSourceId });
    if (reply) {
      toast.show({
        tone: "ok",
        text: `Copied ${reply.copied?.length ?? selectedCount} rules.`,
      });
      onCopied?.();
      onOpenChange(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        title="Copy rules from a different model"
        footer={<>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t("shared.cancel")}
          </Button>
          <Button
            onClick={handleCopy}
            disabled={!selectedSourceId || selectedCount === 0}
            loading={copyAction.pending}
            loadingText={t("shared.updating")}>
            {t("rules.copy.confirm", { n: selectedCount })}
          </Button>
        </>}>
        <div className="dc-copy-rules-body">
          <fieldset className="dc-radio-group">
            <legend className="dc-muted dc-legend">
              Models in this session that have naming rules
            </legend>
            <div className="dc-radio-list">
              {sources.map((source) => {
                const count = sourceRuleCounts[source.source_id] ?? 0;
                const disabled = count === 0;
                const isSelected = selectedSourceId === source.source_id;
                return (
                  <label
                    key={source.source_id}
                    className={`dc-radio-card ${isSelected ? "selected" : ""} ${disabled ? "disabled" : ""}`}>
                    <input
                      type="radio"
                      name="copy_source"
                      value={source.source_id}
                      checked={isSelected}
                      disabled={disabled}
                      onChange={() => setSelectedSourceId(source.source_id)}
                      className="dc-radio-input"
                    />
                    <div className="dc-radio-content">
                      <div className="dc-radio-header">
                        <span className="dc-radio-title">{source.display_name}</span>
                        <span className="dc-radio-count">{count} rules</span>
                      </div>
                      <span className="dc-radio-desc">{t(`sources.kind.${source.kind}`)}</span>
                      {disabled ? (
                        <span className="dc-radio-reason">
                          <Info className="dc-icon-sm" aria-hidden="true" />
                          {t("rules.copy.no_rules")}
                        </span>
                      ) : null}
                    </div>
                  </label>
                );
              })}
            </div>
          </fieldset>

          <p className="dc-muted dc-small">
            {t("rules.copy.note", { target: targetModelName || "target model" })}
          </p>

          {copyAction.error ? (
            <p className="dc-step-error" role="alert">
              {errorCopy(copyAction.error).body}
            </p>
          ) : null}
        </div>
      </DialogContent>
    </Dialog>
  );
}
