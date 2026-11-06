// Log tab (UI design 4.7, step U9): one table of the session log, newest first.
// Filters Author, Action, target search, and a proposal chip. "Show more" while has_more.
// No edit and no delete. All text follows ASD-STE100 rules.
import React, { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { FilterChip } from "@/components/ui/filter";
import { Input } from "@/components/ui/input";
import { Banner } from "@/components/ui/notice";
import { EmptyState } from "@/components/ui/result-panel";
import { Select } from "@/components/ui/select";
import { errorCopy, t } from "../../copy.js";
import { useResource } from "../../useDevCenter.js";
import {
  actionText,
  authorText,
  LOG_ACTIONS,
  logParams,
  targetRowKey,
  targetText,
  timeText,
  valueText,
} from "./logModel.js";
import "../agent/agent.css";

const SEARCH_ID = "dc-log-search";

export default function LogTab({ onTabs, proposalId: initialProposal = null }) {
  const [author, setAuthor] = useState("all");
  const [action, setAction] = useState("all");
  const [text, setText] = useState("");
  const [target, setTarget] = useState("");
  const [proposalId, setProposalId] = useState(initialProposal);
  const [pages, setPages] = useState(1);
  const log = useResource("log", logParams({ author, action, target, proposalId, pages }));
  const [shown, setShown] = useState(null);

  // The target search waits 150 ms after the last key.
  useEffect(() => {
    const timer = setTimeout(() => setTarget(text), 150);
    return () => clearTimeout(timer);
  }, [text]);

  // A change of a filter loads the first page again.
  useEffect(() => setPages(1), [author, action, target, proposalId]);

  // Keep the last data while a larger page loads, so that "Show more" keeps the rows on screen.
  useEffect(() => {
    if (log.data) setShown(log.data);
  }, [log.data]);

  const data = log.data ?? shown;
  const entries = data?.entries ?? [];
  const filtered = author !== "all" || action !== "all" || target !== "" || proposalId !== null;
  const openRow = (rowKey) => onTabs?.({ tab: "compare", rowKey });

  return (
    <div className="dc-log" data-slot="log-tab">
      <h2 className="dc-agent-h2">{t("log.title")}</h2>
      <div className="dc-log-filters">
        <Select
          label={t("log.filter.author")}
          value={author}
          onValueChange={setAuthor}
          options={[
            { value: "all", label: t("log.filter.all") },
            { value: "user", label: t("log.author.user") },
            { value: "agent", label: t("log.author.agent_any") },
          ]}
        />
        <Select
          label={t("log.filter.action")}
          value={action}
          onValueChange={setAction}
          options={[{ value: "all", label: t("log.filter.all") }, ...LOG_ACTIONS.map((value) => ({ value, label: actionText({ action: value }) }))]}
        />
        <div className="dc-log-search">
          <label htmlFor={SEARCH_ID} className="ui-field-label">{t("log.filter.target")}</label>
          <Input id={SEARCH_ID} type="search" value={text} onChange={(event) => setText(event.target.value)} />
        </div>
      </div>
      {proposalId ? (
        <div className="dc-log-chips">
          <FilterChip label={t("log.filter.proposal", { id: proposalId })} onRemove={() => setProposalId(null)} />
        </div>
      ) : null}
      {log.error ? (
        <Banner tone="bad" actions={<Button variant="outline" size="sm" onClick={log.reload}>{t("shared.try_again")}</Button>}>
          {errorCopy(log.error).body}
        </Banner>
      ) : null}
      {data && entries.length === 0 ? (
        filtered ? (
          <EmptyState headingLevel={3} title={t("log.empty.title")}>
            <Button variant="outline" size="sm" onClick={() => { setAuthor("all"); setAction("all"); setText(""); setTarget(""); setProposalId(null); }}>
              {t("shared.clear_filters")}
            </Button>
          </EmptyState>
        ) : (
          <EmptyState headingLevel={3} title={t("log.empty.title")}>{t("log.empty.body")}</EmptyState>
        )
      ) : null}
      {entries.length > 0 ? (
        <div className="dc-log-scroll" aria-busy={log.status === "loading" || undefined}>
          <table className="dc-log-table">
            <thead>
              <tr>
                <th scope="col">{t("log.column.time")}</th>
                <th scope="col">{t("log.column.author")}</th>
                <th scope="col">{t("log.column.action")}</th>
                <th scope="col">{t("log.column.target")}</th>
                <th scope="col">{t("log.column.before")}</th>
                <th scope="col">{t("log.column.after")}</th>
                <th scope="col">{t("log.column.reason")}</th>
                <th scope="col">{t("log.column.proposal")}</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((entry, index) => {
                const rowKey = targetRowKey(entry.target);
                return (
                  <tr key={`${entry.revision_after ?? "x"}-${index}`} className="dc-log-row" data-action={entry.action}>
                    <td className="dc-log-time">{timeText(entry.time_utc)}</td>
                    <td>{authorText(entry)}</td>
                    <td>{actionText(entry)}</td>
                    <td>
                      {rowKey ? (
                        <button type="button" className="dc-agent-link" onClick={() => openRow(rowKey)}>{rowKey}</button>
                      ) : targetText(entry.target)}
                    </td>
                    <td className="dc-log-code" data-col="before">{valueText(entry.before)}</td>
                    <td className="dc-log-code" data-col="after">{valueText(entry.after)}</td>
                    <td>{entry.reason || t("shared.empty_value")}</td>
                    <td>
                      {entry.proposal_id ? (
                        <button type="button" className="dc-agent-link" onClick={() => setProposalId(entry.proposal_id)}>{entry.proposal_id}</button>
                      ) : t("shared.empty_value")}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : null}
      {entries.length > 0 ? (
        <div className="dc-log-more">
          <span>{t("log.more.count", { n: entries.length })}</span>
          {data?.has_more ? (
            <Button variant="outline" size="sm" loading={log.status === "loading"} onClick={() => setPages((value) => value + 1)}>
              {t("log.more")}
            </Button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
