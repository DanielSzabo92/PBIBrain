// "Accept all" summary dialog (UI design 5.4, step U9). The parent mounts it on each open.
// It reads GET plan (accepted state) and GET plan?include_proposals=ready, and shows the kinds,
// the plan now and after, the change, and the skipped items with their reasons. Initial focus: Cancel.
import React, { useState } from "react";
import { LoaderCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { AlertDialog, AlertDialogCancel, AlertDialogContent } from "@/components/ui/dialog";
import { useToast } from "@/components/ui/toast";
import { errorCopy, t, tn } from "../../copy.js";
import { useAction, useResource } from "../../useDevCenter.js";
import { acceptAllSummary } from "./agentModel.js";

export default function AcceptAllDialog({ open, onClose }) {
  const toast = useToast();
  const planNow = useResource("plan", {});
  const planAfter = useResource("plan", { includeProposals: "ready" });
  const acceptAll = useAction("proposal_accept_all");
  // The summary uses the list at the time of the open, so the poll does not change it.
  const [items] = useState(open);
  const summary = acceptAllSummary({ open: items, planNow: planNow.data, planAfter: planAfter.data });
  const loading = !planNow.data || !planAfter.data;

  const confirm = async () => {
    const reply = await acceptAll.run({});
    if (!reply) return;
    toast.show({ tone: "ok", text: t("agent.toast.accept_all", { n: reply.accepted_ids?.length ?? 0, m: reply.skipped?.length ?? 0 }) });
    onClose();
  };

  return (
    <AlertDialog open onOpenChange={(value) => { if (!value && !acceptAll.pending) onClose(); }}>
      <AlertDialogContent
        className="dc-accept-all"
        title={tn("agent.accept_all.title", summary.n)}
        description={t("agent.accept_all.body")}
        progress={acceptAll.pending}
        footer={
          <>
            <AlertDialogCancel asChild>
              <Button variant="outline" disabled={acceptAll.pending}>{t("shared.cancel")}</Button>
            </AlertDialogCancel>
            <Button onClick={confirm} loading={acceptAll.pending} disabled={summary.n === 0}>
              {tn("agent.accept_all.confirm", summary.n)}
            </Button>
          </>
        }>
        <p className="dc-accept-files">{t("agent.accept_all.files")}</p>
        <h3 className="dc-accept-h3">{t("agent.accept_all.kinds")}</h3>
        <ul className="dc-accept-list" aria-label={t("agent.accept_all.list")}>
          {summary.kinds.map((item) => <li key={item.kind}>{item.text}</li>)}
        </ul>
        <h3 className="dc-accept-h3">{t("agent.accept_all.effect")}</h3>
        {loading ? (
          <p className="dc-accept-loading" role="status"><LoaderCircle className="spin" aria-hidden="true" />{t("agent.accept_all.loading")}</p>
        ) : (
          <>
            <dl className="dc-accept-effect">
              <dt>{t("agent.accept_all.now")}</dt>
              <dd data-plan="now">{summary.nowText}</dd>
              <dt>{t("agent.accept_all.after")}</dt>
              <dd data-plan="after">{summary.afterText}</dd>
            </dl>
            <p className="dc-accept-change" data-plan="change">{summary.changeText}</p>
          </>
        )}
        {summary.skipped.length > 0 ? (
          <>
            <h3 className="dc-accept-h3">{t("agent.accept_all.skipped", { n: summary.skipped.length })}</h3>
            <ul className="dc-accept-list dc-accept-skipped">
              {summary.skipped.map((item) => <li key={item.id} data-reason={item.reason}>{item.text}</li>)}
            </ul>
          </>
        ) : null}
        {acceptAll.error ? <p className="ui-field-hint is-error" role="alert"><span>{errorCopy(acceptAll.error).body}</span></p> : null}
      </AlertDialogContent>
    </AlertDialog>
  );
}
