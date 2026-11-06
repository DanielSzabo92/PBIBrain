// QuestionCard part for the Agent tab and Row detail (UI design 4.4, 4.7, step U9).
// Radio options with effect lines, the recommended option preselected, Reason, "Answer", "Open row".
// No free text and no dismiss in version 1. All text follows ASD-STE100 rules.
import React, { useState } from "react";
import { CircleHelp } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ChoiceRadio } from "@/components/ui/choice-radio";
import { StatusBadge } from "@/components/ui/status-badge";
import { useToast } from "@/components/ui/toast";
import { errorCopy, t } from "../copy.js";
import { useAction } from "../useDevCenter.js";
import { fromText, optionEffect } from "../screens/agent/agentModel.js";
import { formatMergeChoiceLabel } from "./rowDetailModel.js";

export default function QuestionCard({ question, donors = [], disabled = false, reasonId, onOpenRow, headingLevel = 3 }) {
  const toast = useToast();
  const answer = useAction("question_answer");
  const [value, setValue] = useState(question?.recommended_option || question?.options?.[0]?.id || "");
  if (!question) return null;
  const Heading = `h${headingLevel}`;
  const formatChoice = (choice) => formatMergeChoiceLabel(choice, donors);
  const items = (question.options ?? []).map((option) => ({
    value: option.id,
    label: option.label,
    badge: option.id === question.recommended_option ? <span className="dc-question-rec">{t("agent.question.recommended")}</span> : null,
    reason: optionEffect(option, formatChoice) || undefined,
  }));
  const blocked = question.blocked === "source_changed";

  const submit = async () => {
    const reply = await answer.run({ question_id: question.id, option_id: value });
    if (reply) toast.show({ tone: "ok", text: t("agent.toast.answered") });
  };

  return (
    <section className="dc-question-card" data-slot="question-card" data-question={question.id} aria-labelledby={`q-title-${question.id}`}>
      <div className="dc-proposal-head">
        <StatusBadge tone="info" icon={CircleHelp} label={t("agent.question.title")} />
        <span className="dc-proposal-meta">{fromText(question)}</span>
      </div>
      <Heading id={`q-title-${question.id}`} className="dc-question-text">{question.text}</Heading>
      <p className="dc-question-row">{t("agent.question.row", { name: question.target_name || question.target_id })}</p>
      <ChoiceRadio
        legend={question.text}
        className="dc-question-options"
        items={items}
        value={value}
        onValueChange={setValue}
        disabled={disabled || answer.pending}
        loading={answer.pending}
        loadingText={t("agent.question.saving")}
      />
      {question.reason ? (
        <p className="dc-proposal-reason"><span className="dc-proposal-label">{t("agent.card.reason")}: </span>{question.reason}</p>
      ) : null}
      {blocked ? <p className="dc-proposal-blocked">{t("agent.card.marked")}</p> : null}
      {answer.error ? (
        <p className="ui-field-hint is-error" role="alert"><span>{errorCopy(answer.error).body}</span></p>
      ) : null}
      <div className="dc-proposal-actions">
        <Button type="button" size="sm" loading={answer.pending} disabled={disabled || blocked || !value} aria-describedby={reasonId} onClick={submit}>
          {t("agent.question.answer")}
        </Button>
        {onOpenRow ? (
          <Button type="button" variant="outline" size="sm" onClick={() => onOpenRow(question.target_id)}>
            {t("agent.question.open_row")}
          </Button>
        ) : null}
      </div>
    </section>
  );
}
