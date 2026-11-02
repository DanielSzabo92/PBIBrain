// Session list and its empty states (UI design 4.1). Data: GET sessions.
import React from "react";
import { FolderOpen, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { EmptyState, Skeleton } from "@/components/ui/result-panel";
import { Notice } from "@/components/ui/notice";
import { StatusBadge } from "@/components/ui/status-badge";
import { errorCopy, t } from "../copy.js";
import { useAction, useDevCenterState, useDevCenterStore, useResource } from "../useDevCenter.js";
import { formatTime, listPlanLabel, listRowState, sortSessions } from "./sessionModel.js";

export default function SessionList({ banner, onDismissBanner, onNew, onOpened, onOpenProject }) {
  const store = useDevCenterStore();
  const sessions = useResource("sessions");
  const openSession = useAction("session_open");
  const closeSession = useAction("session_close");
  const current = useDevCenterState((state) => state.session);
  const busy = useDevCenterState((state) => state.busy);
  const [opening, setOpening] = React.useState(null);

  const open = async (row) => {
    if (current && current.session_id === row.session_id) {
      onOpened();
      return;
    }
    setOpening(row.session_id);
    try {
      // One open session at a time (UI design 2): close the open session first.
      if (current) {
        const closed = await closeSession.run({});
        if (!closed) return;
      }
      const reply = await openSession.run({ session_id: row.session_id });
      if (reply) {
        await store.load("session");
        onOpened();
      }
    } finally {
      setOpening(null);
    }
  };

  const error = sessions.error;
  const noProject = error?.code === "action_not_allowed" && error?.details?.reason === "no_project";
  const rows = sortSessions(sessions.data?.sessions ?? []);
  const actionError = openSession.error ?? closeSession.error;

  const sessionBanner = banner ? (
    <Notice tone="warn" actions={<Button variant="outline" size="sm" onClick={onDismissBanner}>{t("shared.close")}</Button>}>{t(banner.key)}</Notice>
  ) : null;

  if (noProject) {
    return (
      <div className="dc-page">
        <h1 className="sr-only">{t("list.title")}</h1>
        <EmptyState icon={FolderOpen} headingLevel={2} title={t("list.no_project.title")} action={<Button onClick={onOpenProject}><FolderOpen aria-hidden="true" />{t("list.no_project.action")}</Button>}>
          {t("list.no_project.body")}
        </EmptyState>
      </div>
    );
  }

  if (error && !sessions.data) {
    const copy = errorCopy(error);
    return (
      <div className="dc-page">
        <h1 className="sr-only">{t("list.title")}</h1>
        <EmptyState variant="error" headingLevel={2} title={copy.title ?? t("list.error.title")} action={<Button variant="outline" onClick={sessions.reload}>{t("shared.try_again")}</Button>}>
          {copy.body}
        </EmptyState>
      </div>
    );
  }

  if (!sessions.data) {
    return <div className="dc-page"><h1 className="sr-only">{t("list.title")}</h1><Skeleton label={t("list.loading")} /></div>;
  }

  if (rows.length === 0) {
    return (
      <div className="dc-page">
        <h1 className="sr-only">{t("list.title")}</h1>
        {sessionBanner}
        <EmptyState headingLevel={2} title={t("list.empty.title")} action={<Button onClick={onNew}><Plus aria-hidden="true" />{t("list.empty.action")}</Button>}>
          {t("list.empty.body")}
        </EmptyState>
      </div>
    );
  }

  return (
    <div className="dc-page">
      <header className="dc-page-head">
        <div>
          <h1 className="dc-title">{t("list.title")}</h1>
          <p className="dc-subtitle">{t("list.description")}</p>
        </div>
        <Button onClick={onNew} disabled={busy === "long"}><Plus aria-hidden="true" />{t("list.new")}</Button>
      </header>
      {sessionBanner}
      {actionError ? <Notice tone="bad">{errorCopy(actionError).body}</Notice> : null}
      {sessions.error ? <Notice tone="warn" actions={<Button variant="outline" size="sm" onClick={sessions.reload}>{t("shared.try_again")}</Button>}>{t("shared.not_current")}</Notice> : null}
      <div className="ui-table-scroll dc-list-scroll">
        <table className="ui-table dc-list">
          <caption className="sr-only">{t("list.caption")}</caption>
          <thead>
            <tr>
              <th scope="col">{t("list.column.name")}</th>
              <th scope="col">{t("list.column.target")}</th>
              <th scope="col" className="dc-num">{t("list.column.sources")}</th>
              <th scope="col">{t("list.column.plan")}</th>
              <th scope="col">{t("list.column.updated")}</th>
              <th scope="col">{t("list.column.status")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const state = listRowState(row);
              const plan = listPlanLabel(row.plan_status);
              const name = row.display_name || t("list.unnamed");
              const reasonId = `dc-row-reason-${row.session_id}`;
              const loading = opening === row.session_id;
              return (
                <tr key={row.session_id} data-openable={state.openable || undefined} onClick={state.openable && !opening ? () => open(row) : undefined}>
                  <th scope="row">
                    {state.openable ? (
                      <Button variant="link" className="dc-row-link" loading={loading} loadingText={name} disabled={Boolean(opening) && !loading} aria-describedby={state.reason ? reasonId : undefined}
                        onClick={(event) => { event.stopPropagation(); open(row); }}>
                        {name}
                      </Button>
                    ) : <span className="dc-row-name">{name}</span>}
                    {state.reason ? <p id={reasonId} className="dc-row-reason">{state.reason}</p> : null}
                    {row.is_open ? <p className="dc-row-reason">{t("list.open.current")}</p> : null}
                  </th>
                  <td>
                    <span className="dc-cell-line">{row.target_model_name ?? t("shared.empty_value")}</span>
                    {row.target_report_name ? <span className="dc-cell-sub">{row.target_report_name}</span> : null}
                  </td>
                  <td className="dc-num">{row.source_count}</td>
                  <td><StatusBadge tone={plan.tone} label={plan.label} /></td>
                  <td>{formatTime(row.updated_at)}</td>
                  <td><StatusBadge tone={state.tone} label={state.label} /></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
