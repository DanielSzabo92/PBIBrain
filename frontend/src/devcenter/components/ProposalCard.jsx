// ProposalCard part for Row detail and Agent tab (UI design 4.4, 4.7, 6.2, steps U6 and U9).
// All text follows ASD-STE100 rules.
import React, { useRef } from "react";
import { CircleDashed, TriangleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Notice } from "@/components/ui/notice";
import { StatusBadge } from "@/components/ui/status-badge";
import { useToast } from "@/components/ui/toast";
import { errorCopy, t } from "../copy.js";
import { useAction } from "../useDevCenter.js";
import { confidenceText, fromText } from "../screens/agent/agentModel.js";
import { formatMergeChoiceLabel } from "./rowDetailModel.js";

export default function ProposalCard({
  proposal,
  row,
  donors = [],
  disabled = false,
  reasonId,
}) {
  const toast = useToast();
  const acceptAction = useAction("proposal_accept");
  const rejectAction = useAction("proposal_reject");
  const confirmAction = useAction("row_confirm");
  // The card keeps the first proposal ID that it showed. A new ID for the same row means
  // that the agent replaced the proposal while the card was open (UI design 4.7).
  const firstId = useRef(proposal?.id ?? null);
  if (firstId.current === null && proposal) firstId.current = proposal.id;

  if (!proposal) return null;

  const replaced = firstId.current !== proposal.id;
  const isMarked = (row?.marks?.length ?? 0) > 0 || proposal.blocked === "source_changed";
  const hasUserChoice = Boolean(row?.merge_choice) || proposal.blocked === "user_choice_conflict";
  const summaryText =
    proposal.summary || formatMergeChoiceLabel(proposal.payload, donors);
  const acceptLabel = hasUserChoice
    ? t("agent.accept.replace")
    : t("agent.accept");

  const handleAccept = async () => {
    const reply = await acceptAction.run({ proposal_id: proposal.id });
    if (reply) toast.show({ tone: "ok", text: t("agent.toast.accepted") });
  };

  const handleReject = async () => {
    const reply = await rejectAction.run({ proposal_id: proposal.id });
    if (reply) toast.show({ tone: "ok", text: t("agent.toast.rejected") });
  };

  const handleConfirm = async () => {
    await confirmAction.run({ row_keys: [proposal.target_id] });
  };

  const actionError = acceptAction.error || rejectAction.error || confirmAction.error;
  const errText = actionError ? errorCopy(actionError).body : null;
  const busy = acceptAction.pending || rejectAction.pending || confirmAction.pending;

  return (
    <section
      className="dc-proposal-card"
      data-slot="proposal-card"
      data-proposal={proposal.id}
      aria-label={t("agent.card.title")}
    >
      <div className="dc-proposal-head">
        <StatusBadge
          tone="proposal"
          icon={CircleDashed}
          label={t("agent.card.title")}
        />
        <span className="dc-proposal-meta">{fromText(proposal)}</span>
      </div>
      {replaced ? <Notice tone="info" className="dc-proposal-replaced">{t("agent.replaced")}</Notice> : null}
      <p className="dc-proposal-summary">{summaryText}</p>
      {row?.merge_choice ? (
        <p className="dc-proposal-line">{t("agent.your_choice", { choice: formatMergeChoiceLabel(row.merge_choice, donors) })}</p>
      ) : null}
      <p className="dc-proposal-line">
        <span className="dc-proposal-label">{t("agent.card.confidence")}: </span>
        {confidenceText(proposal.confidence)}
      </p>
      {proposal.reason ? (
        <p className="dc-proposal-reason">
          <span className="dc-proposal-label">{t("agent.card.reason")}: </span>
          {proposal.reason}
        </p>
      ) : null}
      {isMarked ? (
        <p className="dc-proposal-blocked" id={`prop-blocked-${proposal.id}`}>
          <TriangleAlert aria-hidden="true" />
          <span>{t("agent.card.marked")}</span>
        </p>
      ) : null}
      {errText ? (
        <p className="ui-field-hint is-error" role="alert">
          <span>{errText}</span>
        </p>
      ) : null}
      <div className="dc-proposal-actions" data-ui-actions="">
        {isMarked ? (
          <Button
            type="button"
            size="sm"
            loading={confirmAction.pending}
            disabled={disabled || busy}
            aria-describedby={reasonId}
            onClick={handleConfirm}
          >
            {t("agent.card.confirm")}
          </Button>
        ) : null}
        <Button
          type="button"
          size="sm"
          variant={isMarked ? "outline" : "default"}
          loading={acceptAction.pending}
          disabled={disabled || isMarked || rejectAction.pending || confirmAction.pending}
          aria-describedby={
            isMarked ? `prop-blocked-${proposal.id}` : reasonId
          }
          onClick={handleAccept}
        >
          {acceptLabel}
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          loading={rejectAction.pending}
          disabled={disabled || acceptAction.pending || confirmAction.pending}
          aria-describedby={reasonId}
          onClick={handleReject}
        >
          {t("agent.reject")}
        </Button>
      </div>
    </section>
  );
}
