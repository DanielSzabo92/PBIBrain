// Agent tab (UI design 4.7, 5.4, 9, step U9): questions, the proposals table, and the accept flows.
// The first open question leads. The 5 s session poll updates the counts, but the list does not
// change by itself: a notice loads the new proposals (A19). All text follows ASD-STE100 rules.
import React, { useEffect, useMemo, useState } from "react";
import { ChevronDown, ChevronRight, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Notice } from "@/components/ui/notice";
import { EmptyState } from "@/components/ui/result-panel";
import { Select } from "@/components/ui/select";
import { StatusBadge } from "@/components/ui/status-badge";
import { useToast } from "@/components/ui/toast";
import { errorCopy, t } from "../../copy.js";
import { normalizeError } from "../../errors.js";
import { useAction, useDevCenterStore } from "../../useDevCenter.js";
import QuestionCard from "../../components/QuestionCard.jsx";
import AcceptAllDialog from "./AcceptAllDialog.jsx";
import {
  acceptSelectedToast,
  confidenceText,
  filterProposals,
  fromText,
  kindText,
  newNoticeText,
  newProposalCount,
  PROPOSAL_KINDS,
  PROPOSAL_STATUSES,
  proposalAction,
  proposalStatus,
  questionSections,
  readyProposals,
  statusText,
  statusTone,
  timeText,
  visibleProposals,
} from "./agentModel.js";
import "./agent.css";

const SEARCH_ID = "dc-agent-search";

export default function AgentTab({ session, changeDisabled = false, reasonId, onTabs }) {
  const store = useDevCenterStore();
  const toast = useToast();
  const donors = (session?.sources ?? []).filter((source) => source.role === "donor");
  const open = useMemo(() => session?.proposals?.open ?? [], [session]);
  const questions = questionSections(session?.questions);
  const [shownIds, setShownIds] = useState(() => new Set(open.map((item) => item.id)));
  const [showMore, setShowMore] = useState(false);
  const [showAnswered, setShowAnswered] = useState(false);
  const [lastCheck, setLastCheck] = useState(() => new Date().toISOString());
  const [refreshing, setRefreshing] = useState(false);
  const [kind, setKind] = useState("all");
  const [status, setStatus] = useState("all");
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState(() => new Set());
  const [progress, setProgress] = useState(null);
  const [failed, setFailed] = useState(() => new Map());
  const [acceptAllOpen, setAcceptAllOpen] = useState(false);

  // Each new session read is one check for new proposals and questions.
  useEffect(() => {
    setLastCheck(new Date().toISOString());
  }, [session]);

  const visible = visibleProposals(open, shownIds);
  const newCount = newProposalCount(open, shownIds);
  const rows = filterProposals(visible, { kind, status, q });
  const readyIds = new Set(readyProposals(visible).map((item) => item.id));
  const selectedReady = [...selected].filter((id) => readyIds.has(id));
  const readyRows = rows.filter((item) => readyIds.has(item.id));
  const allChecked = readyRows.length > 0 && readyRows.every((item) => selected.has(item.id));
  const someChecked = readyRows.some((item) => selected.has(item.id));
  const openRow = (rowKey) => onTabs?.({ tab: "compare", rowKey });

  const showNew = () => setShownIds(new Set(open.map((item) => item.id)));

  const refresh = async () => {
    setRefreshing(true);
    try {
      await store.load("session");
    } finally {
      setRefreshing(false);
    }
  };

  const toggle = (id, checked) => {
    setSelected((current) => {
      const next = new Set(current);
      if (checked) next.add(id);
      else next.delete(id);
      return next;
    });
  };

  const toggleAll = (checked) => {
    setSelected(checked ? new Set(readyRows.map((item) => item.id)) : new Set());
  };

  // "Accept selected": one proposal_accept call for each item, in sequence (UI design 5.4).
  const acceptSelected = async () => {
    const ids = selectedReady;
    const errors = new Map();
    let accepted = 0;
    for (let index = 0; index < ids.length; index += 1) {
      setProgress({ i: index + 1, n: ids.length });
      try {
        await store.run("proposal_accept", { proposal_id: ids[index] });
        accepted += 1;
      } catch (raw) {
        errors.set(ids[index], normalizeError(raw));
      }
    }
    setProgress(null);
    setFailed(errors);
    setSelected(new Set(errors.keys()));
    toast.show(acceptSelectedToast(accepted, ids.length));
  };

  const empty = open.length === 0 && questions.first === null;

  return (
    <div className="dc-agent" data-slot="agent-tab">
      <div className="dc-agent-check">
        <span className="dc-agent-last">{t("agent.refresh.last", { time: timeText(lastCheck) })}</span>
        <Button variant="outline" size="sm" onClick={refresh} loading={refreshing} loadingText={t("agent.refresh.loading")}>
          <RefreshCw aria-hidden="true" />
          {t("agent.refresh")}
        </Button>
      </div>

      {questions.first ? (
        <section className="dc-agent-section" aria-labelledby="dc-agent-questions">
          <h2 id="dc-agent-questions" className="dc-agent-h2">{t("agent.questions", { n: questions.more.length + 1 })}</h2>
          <QuestionCard
            key={questions.first.id}
            question={questions.first}
            donors={donors}
            disabled={changeDisabled}
            reasonId={reasonId}
            onOpenRow={openRow}
          />
          {questions.more.length > 0 && !showMore ? (
            <Button variant="link" className="dc-agent-more" onClick={() => setShowMore(true)}>
              {t("agent.questions.more", { n: questions.more.length })}
            </Button>
          ) : null}
          {showMore
            ? questions.more.map((question) => (
                <QuestionCard key={question.id} question={question} donors={donors} disabled={changeDisabled} reasonId={reasonId} onOpenRow={openRow} />
              ))
            : null}
        </section>
      ) : null}

      {questions.answered.length > 0 ? (
        <section className="dc-agent-section" aria-label={t("agent.questions.answered", { n: questions.answered.length })}>
          <Button
            variant="ghost"
            size="sm"
            className="dc-agent-disclosure"
            aria-expanded={showAnswered}
            aria-controls="dc-agent-answered"
            onClick={() => setShowAnswered((value) => !value)}>
            {showAnswered ? <ChevronDown aria-hidden="true" /> : <ChevronRight aria-hidden="true" />}
            {t("agent.questions.answered", { n: questions.answered.length })}
          </Button>
          {showAnswered ? (
            <ul id="dc-agent-answered" className="dc-agent-answered">
              {questions.answered.map((question) => {
                const option = (question.options ?? []).find((item) => item.id === question.selected_option);
                return (
                  <li key={question.id} data-question={question.id}>
                    <span className="dc-agent-answered-text">{question.text}</span>
                    <span className="dc-agent-answered-option">{t("agent.question.answered_with", { option: option?.label ?? question.selected_option ?? t("shared.empty_value") })}</span>
                  </li>
                );
              })}
            </ul>
          ) : null}
        </section>
      ) : null}

      {newCount > 0 ? (
        <div role="status" className="dc-agent-new">
          <Button variant="link" onClick={showNew}>{newNoticeText(newCount)}</Button>
        </div>
      ) : null}

      {empty ? (
        <EmptyState headingLevel={2} title={t("agent.empty.title")}>{t("agent.empty.body")}</EmptyState>
      ) : visible.length > 0 ? (
        <section className="dc-agent-section" aria-labelledby="dc-agent-proposals">
          <div className="dc-agent-head">
            <h2 id="dc-agent-proposals" className="dc-agent-h2">{t("agent.proposals", { n: visible.length })}</h2>
            <div className="dc-agent-bulk">
              <Button
                variant="outline"
                size="sm"
                disabled={changeDisabled || selectedReady.length === 0 || progress !== null}
                aria-describedby={reasonId}
                loading={progress !== null}
                loadingText={progress ? t("agent.accept_selected.loading", progress) : undefined}
                onClick={acceptSelected}>
                {t("agent.accept_selected", { n: selectedReady.length })}
              </Button>
              <Button
                size="sm"
                disabled={changeDisabled || readyIds.size === 0 || progress !== null}
                aria-describedby={readyIds.size === 0 ? "dc-agent-all-reason" : reasonId}
                onClick={() => setAcceptAllOpen(true)}>
                {t("agent.accept_all")}
              </Button>
              {readyIds.size === 0 ? <span id="dc-agent-all-reason" className="dc-agent-reason-text">{t("agent.accept_all.disabled")}</span> : null}
            </div>
          </div>
          <div className="dc-agent-filters">
            <Select
              label={t("agent.filter.kind")}
              value={kind}
              onValueChange={setKind}
              options={[{ value: "all", label: t("agent.filter.all") }, ...PROPOSAL_KINDS.map((value) => ({ value, label: kindText(value) }))]}
            />
            <Select
              label={t("agent.filter.status")}
              value={status}
              onValueChange={setStatus}
              options={[{ value: "all", label: t("agent.filter.all") }, ...PROPOSAL_STATUSES.map((value) => ({ value, label: statusText(value) }))]}
            />
            <div className="dc-agent-search">
              <label htmlFor={SEARCH_ID} className="ui-field-label">{t("agent.filter.search")}</label>
              <Input id={SEARCH_ID} type="search" value={q} onChange={(event) => setQ(event.target.value)} />
            </div>
          </div>
          <div className="dc-agent-scroll">
            <table className="dc-agent-table">
              <thead>
                <tr>
                  <th scope="col" className="dc-agent-col-check">
                    <Checkbox
                      size="target"
                      aria-label={t("agent.select_all")}
                      checked={allChecked ? true : someChecked ? "indeterminate" : false}
                      disabled={readyRows.length === 0 || changeDisabled}
                      onCheckedChange={(checked) => toggleAll(checked === true)}
                    />
                  </th>
                  <th scope="col">{t("agent.column.target")}</th>
                  <th scope="col">{t("agent.column.change")}</th>
                  <th scope="col" className="dc-agent-col-conf">{t("agent.column.confidence")}</th>
                  <th scope="col">{t("agent.column.reason")}</th>
                  <th scope="col">{t("agent.column.from")}</th>
                  <th scope="col">{t("agent.column.status")}</th>
                  <th scope="col" className="dc-agent-col-actions" data-ui-actions="">{t("agent.column.actions")}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((proposal) => (
                  <ProposalRow
                    key={proposal.id}
                    proposal={proposal}
                    checked={selected.has(proposal.id)}
                    onCheck={(checked) => toggle(proposal.id, checked)}
                    failedError={failed.get(proposal.id) ?? null}
                    disabled={changeDisabled || progress !== null}
                    reasonId={reasonId}
                    onOpenRow={openRow}
                  />
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      {acceptAllOpen ? (
        <AcceptAllDialog open={open} onClose={() => setAcceptAllOpen(false)} />
      ) : null}
    </div>
  );
}

function ProposalRow({ proposal, checked, onCheck, failedError, disabled, reasonId, onOpenRow }) {
  const toast = useToast();
  const accept = useAction("proposal_accept");
  const reject = useAction("proposal_reject");
  const [expanded, setExpanded] = useState(false);
  const status = proposalStatus(proposal);
  const action = proposalAction(proposal);
  const name = proposal.target_name || proposal.target_id;
  const error = accept.error || reject.error || failedError;
  const errorId = `dc-agent-err-${proposal.id}`;

  const runAccept = async () => {
    const reply = await accept.run({ proposal_id: proposal.id });
    if (reply) toast.show({ tone: "ok", text: t("agent.toast.accepted") });
  };
  const runReject = async () => {
    const reply = await reject.run({ proposal_id: proposal.id });
    if (reply) toast.show({ tone: "ok", text: t("agent.toast.rejected") });
  };

  return (
    <tr className="dc-agent-row" data-proposal={proposal.id} data-status={status} data-failed={error ? "true" : undefined}>
      <td className="dc-agent-col-check">
        {status === "ready" ? (
          <Checkbox size="target" aria-label={t("agent.select", { name })} checked={checked} disabled={disabled} onCheckedChange={(value) => onCheck(value === true)} />
        ) : null}
      </td>
      <td>
        <span className="dc-agent-kind">{kindText(proposal.kind)}</span>
        <button type="button" className="dc-agent-link" onClick={() => onOpenRow(proposal.target_id)}>{name}</button>
      </td>
      <td className="dc-agent-change">{proposal.summary}</td>
      <td className="dc-agent-col-conf">{confidenceText(proposal.confidence)}</td>
      <td>
        <button
          type="button"
          className="dc-agent-reason"
          data-expanded={expanded || undefined}
          aria-expanded={expanded}
          title={expanded ? undefined : t("agent.reason.show")}
          onClick={() => setExpanded((value) => !value)}>
          {proposal.reason}
        </button>
      </td>
      <td className="dc-agent-from">{fromText(proposal)}</td>
      <td>
        <StatusBadge tone={statusTone(status)} label={statusText(status)} />
        {error ? (
          <p id={errorId} className="dc-agent-error" role="alert">{errorCopy(error).body}</p>
        ) : null}
      </td>
      <td className="dc-agent-col-actions" data-ui-actions="">
        <div className="dc-agent-actions" data-ui-actions="">
          {action === "open_row" || error?.code === "source_changed" ? (
            <Button size="sm" variant="outline" onClick={() => onOpenRow(proposal.target_id)}>{t("agent.open_row")}</Button>
          ) : (
            <Button
              size="sm"
              loading={accept.pending}
              loadingText={t("agent.accept.loading")}
              disabled={disabled || reject.pending}
              aria-describedby={reasonId}
              onClick={runAccept}>
              {action === "replace" ? t("agent.accept.replace") : t("agent.accept")}
            </Button>
          )}
          <Button
            size="sm"
            variant="outline"
            loading={reject.pending}
            loadingText={t("agent.reject.loading")}
            disabled={disabled || accept.pending}
            aria-describedby={reasonId}
            onClick={runReject}>
            {t("agent.reject")}
          </Button>
        </div>
      </td>
    </tr>
  );
}
