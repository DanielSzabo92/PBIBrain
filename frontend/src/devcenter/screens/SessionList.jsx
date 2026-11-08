// Session list and its empty states (UI design 4.1). Data: GET sessions.
import React from "react";
import { ArrowRight, Copy, Edit3, FolderOpen, MoreHorizontal, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { EmptyState, Skeleton } from "@/components/ui/result-panel";
import { Notice } from "@/components/ui/notice";
import { StatusBadge } from "@/components/ui/status-badge";
import { Menu } from "@/components/ui/menu";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { errorCopy, t } from "../copy.js";
import { useAction, useDevCenterState, useDevCenterStore, useResource } from "../useDevCenter.js";
import { formatTime, listPlanLabel, listRowState, sortSessions } from "./sessionModel.js";

export default function SessionList({
  banner,
  onDismissBanner,
  onNew,
  onOpened,
  onOpenProject,
  sessionOverrides = {},
  deletedSessions = new Set(),
  onRenameSession,
  onDuplicateSession,
  onDeleteSession,
}) {
  const store = useDevCenterStore();
  const sessions = useResource("sessions");
  const openSession = useAction("session_open");
  const closeSession = useAction("session_close");
  const current = useDevCenterState((state) => state.session);
  const busy = useDevCenterState((state) => state.busy);
  const [opening, setOpening] = React.useState(null);
  const [renameTarget, setRenameTarget] = React.useState(null);
  const [deleteTarget, setDeleteTarget] = React.useState(null);
  const [renameDraft, setRenameDraft] = React.useState("");

  const startRename = (row) => {
    setRenameTarget(row);
    setRenameDraft(sessionOverrides[row.session_id]?.display_name || row.display_name || "");
  };

  const handleSaveRename = () => {
    if (!renameTarget) return;
    const trimmed = renameDraft.trim();
    if (!trimmed) return;
    onRenameSession?.(renameTarget.session_id, trimmed);
    setRenameTarget(null);
  };

  const handleSaveDelete = async () => {
    if (!deleteTarget) return;
    await onDeleteSession?.(deleteTarget.session_id);
    setDeleteTarget(null);
  };

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
  const rawRows = (sessions.data?.sessions ?? [])
    .filter((row) => !deletedSessions.has(row.session_id))
    .map((row) => (sessionOverrides[row.session_id] ? { ...row, ...sessionOverrides[row.session_id] } : row));
  const rows = sortSessions(rawRows);
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
      {current && !deletedSessions.has(current.session_id) ? (
        <div className="dc-active-session-banner">
          <div className="dc-active-session-copy">
            <span className="dc-active-session-label">{t("list.resume.title")}</span>
            <strong>{sessionOverrides[current.session_id]?.display_name || current.display_name}</strong>
          </div>
          <Button size="sm" onClick={onOpened}>
            {t("list.resume.action")}
            <ArrowRight aria-hidden="true" />
          </Button>
        </div>
      ) : null}
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
              <th scope="col"><span className="sr-only">Actions</span></th>
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
                  <td className="dc-cell-actions">
                    <Menu
                      align="end"
                      label={t("work.more")}
                      trigger={<Button variant="ghost" size="icon-sm" aria-label={`Actions for ${name}`} onClick={(e) => e.stopPropagation()}><MoreHorizontal /></Button>}
                      groups={[{
                        items: [
                          state.openable ? { label: t("list.row.open"), icon: FolderOpen, onSelect: () => open(row) } : null,
                          { label: t("list.row.rename"), icon: Edit3, onSelect: () => startRename(row) },
                          { label: t("list.row.duplicate"), icon: Copy, onSelect: () => onDuplicateSession?.(row.session_id) },
                          { label: t("list.row.delete"), icon: Trash2, onSelect: () => setDeleteTarget(row) },
                        ].filter(Boolean),
                      }]}
                    />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <Dialog open={Boolean(renameTarget)} onOpenChange={(open) => { if (!open) setRenameTarget(null); }}>
        <DialogContent
          title={t("work.rename.title")}
          footer={
            <>
              <Button variant="outline" onClick={() => setRenameTarget(null)}>
                {t("shared.cancel") || "Cancel"}
              </Button>
              <Button onClick={handleSaveRename} disabled={!renameDraft.trim()}>
                {t("work.rename.save")}
              </Button>
            </>
          }
        >
          <label className="dc-field">
            <span>{t("work.rename.label")}</span>
            <Input
              value={renameDraft}
              onChange={(e) => setRenameDraft(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") handleSaveRename(); }}
              autoFocus
            />
          </label>
        </DialogContent>
      </Dialog>
      <AlertDialog open={Boolean(deleteTarget)} onOpenChange={(open) => { if (!open) setDeleteTarget(null); }}>
        <AlertDialogContent
          title={t("work.delete.title")}
          description={t("work.delete.description")}
          footer={
            <>
              <AlertDialogCancel asChild>
                <Button variant="outline">{t("shared.cancel") || "Cancel"}</Button>
              </AlertDialogCancel>
              <AlertDialogAction asChild>
                <Button variant="destructive" onClick={handleSaveDelete}>
                  <Trash2 aria-hidden="true" />
                  {t("work.delete.confirm")}
                </Button>
              </AlertDialogAction>
            </>
          }
        />
      </AlertDialog>
    </div>
  );
}
