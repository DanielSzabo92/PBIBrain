// ProposalCard part for Row detail and Agent tab (UI design 4.4, 4.7, 6.2, step U6).
// All text follows ASD-STE100 rules.
import React from "react";
import { Sparkles, TriangleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/status-badge";
import { errorCopy, t } from "../copy.js";
import { useAction } from "../useDevCenter.js";
import { formatMergeChoiceLabel } from "./rowDetailModel.js";

export default function ProposalCard({
  proposal,
  row,
  donors = [],
  disabled = false,
  reasonId,
}) {
  const acceptAction = useAction("proposal_accept");
  const rejectAction = useAction("proposal_reject");

  if (!proposal) return null;

  const isMarked = (row?.marks?.length ?? 0) > 0 || proposal.blocked === "source_changed";
  const hasUserChoice = Boolean(row?.merge_choice);
  const clientName = proposal.mcp_client || "Agent";
  const confidenceValue =
    typeof proposal.confidence === "number"
      ? `${Math.round(proposal.confidence * 100)}%`
      : "95%";
  const summaryText =
    proposal.summary || formatMergeChoiceLabel(proposal.payload, donors);
  const acceptLabel = hasUserChoice
    ? t("agent.accept.replace")
    : t("agent.accept");

  const handleAccept = async () => {
    await acceptAction.run({ proposal_id: proposal.id });
  };

  const handleReject = async () => {
    await rejectAction.run({ proposal_id: proposal.id });
  };

  const actionError = acceptAction.error || rejectAction.error;
  const errText = actionError ? errorCopy(actionError).body : null;

  return (
    <section
      className="dc-proposal-card"
      data-slot="proposal-card"
      aria-label={t("agent.card.title")}
    >
      <div className="dc-proposal-head">
        <StatusBadge
          tone="proposal"
          icon={Sparkles}
          label={t("agent.card.title")}
        />
        <span className="dc-proposal-meta">
          {clientName} ({confidenceValue})
        </span>
      </div>
      <p className="dc-proposal-summary">{summaryText}</p>
      {proposal.reason ? (
        <p className="dc-proposal-reason">{proposal.reason}</p>
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
      <div className="dc-proposal-actions">
        <Button
          type="button"
          size="sm"
          loading={acceptAction.pending}
          disabled={disabled || isMarked || rejectAction.pending}
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
          disabled={disabled || acceptAction.pending}
          aria-describedby={reasonId}
          onClick={handleReject}
        >
          {t("agent.reject")}
        </Button>
      </div>
    </section>
  );
}
