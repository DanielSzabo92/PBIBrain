// RemovalPolicyDialog (UI design 5.3, 8.4, A9): Block, Cascade (destructive), or Repoint for a removed object.
// Initial focus: the policy radio group. Escape and Cancel keep the old policy. Focus goes back to the trigger,
// else to the h1 of the tab.
import React, { useState } from "react";
import { TriangleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ChoiceRadio } from "@/components/ui/choice-radio";
import { Combobox } from "@/components/ui/combobox";
import { Dialog, DialogClose, DialogContent } from "@/components/ui/dialog";
import { Notice } from "@/components/ui/notice";
import { Skeleton } from "@/components/ui/result-panel";
import { t } from "../copy.js";
import { useAction, useResource } from "../useDevCenter.js";
import { canConfirmPolicy, effectText, policyConfirm } from "../screens/impact/impactModel.js";

export default function RemovalPolicyDialog({ open, onOpenChange, ...props }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {open ? <PolicyContent {...props} onOpenChange={onOpenChange} /> : null}
    </Dialog>
  );
}

// The content mounts on each open, so the policy state starts from initialPolicy before the initial focus.
function PolicyContent({ onOpenChange, object, objectName, objectType, effectName, initialPolicy = "block", returnFocusRef, onSaved }) {
  const removal = useResource("removal", { object: object || "none" });
  const save = useAction("removal_policy_set");
  const [policy, setPolicy] = useState(initialPolicy || "block");
  const [target, setTarget] = useState("");

  const data = removal.data;
  const dependents = data?.dependents ?? [];
  const effects = data?.cascade?.effects ?? [];
  const cascadeCount = data?.cascade?.count ?? effects.length;
  const candidates = data?.repoint_candidates ?? [];
  const chosen = candidates.find((candidate) => candidate.object_id === target);
  const confirm = policyConfirm(policy, cascadeCount);
  const type = (objectType || "measure").toLowerCase();

  const submit = async () => {
    const reply = await save.run({ row_key: object, policy, repoint_target: policy === "repoint" ? target : null });
    if (reply) {
      onOpenChange(false);
      onSaved?.(reply);
    }
  };

  const cascadeTable = (
    <div className="dc-policy-effects">
      <p className="dc-policy-help">{t("row.policy.cascade.effects")}</p>
      <table className="dc-policy-table">
        <thead>
          <tr>
            <th scope="col">{t("impact.policy.col.object")}</th>
            <th scope="col">{t("impact.policy.col.effect")}</th>
          </tr>
        </thead>
        <tbody>
          {effects.map((effect) => (
            <tr key={`${effect.object_id}-${effect.effect}`}>
              <th scope="row">{effect.name || effect.object_id}</th>
              <td>{effectText(effect.effect)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

  const repointField = (
    <div className="dc-policy-repoint">
      <Combobox
        label={t("row.policy.repoint.with")}
        value={target}
        onValueChange={(value) => setTarget(candidates.some((candidate) => candidate.object_id === value) ? value : "")}
        groups={[{ label: t("impact.policy.candidates"), options: candidates.map((candidate) => ({ value: candidate.object_id, label: candidate.name, description: candidate.type })) }]}
      />
      {chosen?.type_warning ? (
        <p className="dc-policy-warning" data-tone="warn">
          <TriangleAlert aria-hidden="true" />
          {t("row.policy.repoint.type", { candidate_type: chosen.data_type || t("shared.not_known"), object_type: type })}
        </p>
      ) : null}
    </div>
  );

  return (
    <DialogContent
      title={effectName ? t("row.policy.title.effect", { object: objectName || object, effect: effectName }) : t("row.policy.title", { object: objectName || object })}
      className="dc-policy-dialog"
      onOpenAutoFocus={(event) => {
        event.preventDefault();
        const root = event.currentTarget;
        const radio = root?.querySelector('[role="radio"][data-state="checked"]') || root?.querySelector('[role="radio"]');
        radio?.focus();
      }}
      onCloseAutoFocus={(event) => {
        event.preventDefault();
        const trigger = returnFocusRef?.current;
        if (trigger?.isConnected) trigger.focus();
        else document.querySelector(".dc-work-head h1")?.focus();
      }}
      footer={
        <>
          <DialogClose asChild>
            <Button variant="outline">{t("shared.cancel")}</Button>
          </DialogClose>
          <Button
            variant={confirm.variant}
            disabled={!canConfirmPolicy(policy, target) || removal.status === "loading"}
            loading={save.pending}
            loadingText={t("shared.updating")}
            onClick={submit}>
            {confirm.text}
          </Button>
        </>
      }>
      {removal.status === "loading" && !data ? <Skeleton lines={2} label={t("row.removal.loading")} /> : null}
      {removal.status === "error" ? <Notice tone="bad">{t("row.removal.fail")}</Notice> : null}
      {data ? (
        <p className="dc-policy-body">
          {dependents.length === 0 ? t("row.removal.none") : t("row.policy.body", { n: dependents.length, type })}
        </p>
      ) : null}
      <ChoiceRadio
        legend={t("row.policy.legend")}
        value={policy}
        onValueChange={setPolicy}
        items={[
          { value: "block", label: t("row.policy.block"), reason: t("row.policy.block.help") },
          { value: "cascade", label: t("row.policy.cascade"), reason: t("row.policy.cascade.help"), children: cascadeTable },
          { value: "repoint", label: t("row.policy.repoint"), reason: t("row.policy.repoint.help", { type }), children: repointField },
        ]}
      />
      {save.error ? <Notice tone="bad" role="alert">{t("row.policy.fail")}</Notice> : null}
    </DialogContent>
  );
}
