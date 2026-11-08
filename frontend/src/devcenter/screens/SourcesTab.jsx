// Sources tab (UI design 4.8): the source list with "Find source" and "Remove", and the Target section.
// Naming rules (U5) and the cloud dialogs (U11) come in later steps.
import React, { useRef, useState } from "react";
import { FolderSearch, MoreHorizontal, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, Dialog, DialogContent, DialogTrigger } from "@/components/ui/dialog";
import { Menu } from "@/components/ui/menu";
import { Notice } from "@/components/ui/notice";
import { StatusBadge } from "@/components/ui/status-badge";
import { useToast } from "@/components/ui/toast";
import { desktopRequest } from "../../desktop.js";
import { errorCopy, t, tn } from "../copy.js";
import { useAction } from "../useDevCenter.js";
import TargetChoice from "./TargetChoice.jsx";
import { targetNames, targetPayload } from "./sessionModel.js";
import NamingRules from "./sources/NamingRules.jsx";

const STATUS = {
  ok: { tone: "ok", key: "sources.status.ok" },
  missing: { tone: "bad", key: "sources.status.missing" },
  unreadable: { tone: "bad", key: "sources.status.unreadable" },
};

function sourceStatus(source) {
  if (source.status === "ok" && source.fingerprint_state === "changed") return { tone: "warn", label: t("sources.status.changed") };
  const value = STATUS[source.status] ?? STATUS.unreadable;
  return { tone: value.tone, label: t(value.key) };
}

export default function SourcesTab({ session, changeDisabled, reasonId, onTabs }) {
  const toast = useToast();
  const remove = useAction("source_remove");
  const relink = useAction("source_relink");
  const [removing, setRemoving] = useState(null);
  const [findError, setFindError] = useState(null);
  const trigger = useRef(null);
  const titleRef = useRef(null);
  const changeTargetRef = useRef(null);
  const sources = session.sources ?? [];
  const names = targetNames(session);

  const confirmRemove = async () => {
    const source = removing;
    setRemoving(null);
    const reply = await remove.run({ source_id: source.source_id });
    if (reply) toast.show({ tone: reply.choice_count > 0 ? "warn" : "ok", text: tn("sources.remove.toast", reply.choice_count, { source: source.display_name }) });
  };

  const find = async (source) => {
    setFindError(null);
    let folder;
    try {
      folder = (await desktopRequest(globalThis.pywebview?.api, "choose_folder")).folder;
    } catch (cause) {
      setFindError(cause.message);
      return;
    }
    if (!folder) return;
    const reply = await relink.run({ source_id: source.source_id, path: folder });
    if (reply) toast.show({ tone: "ok", text: t("sources.find.done", { source: source.display_name }) });
  };

  const actionError = remove.error ?? relink.error;

  return (
    <div className="dc-sources">
      <section className="dc-section" aria-labelledby="dc-sources-title">
        <h2 id="dc-sources-title" ref={titleRef} tabIndex={-1} className="dc-section-title">{t("sources.title")}</h2>
        {actionError ? <Notice tone="bad">{errorCopy(actionError).body}</Notice> : null}
        {findError ? <Notice tone="bad">{findError}</Notice> : null}
        {sources.length === 0 ? <p className="dc-muted">{t("sources.empty")}</p> : (
          <div className="ui-table-scroll">
            <table className="ui-table dc-source-table">
              <caption className="sr-only">{t("sources.caption")}</caption>
              <thead>
                <tr>
                  <th scope="col">{t("sources.column.name")}</th>
                  <th scope="col">{t("sources.column.kind")}</th>
                  <th scope="col">{t("sources.column.role")}</th>
                  <th scope="col">{t("sources.column.access")}</th>
                  <th scope="col">{t("sources.column.status")}</th>
                  <th scope="col" className="ui-table-actions" data-ui-actions="">Actions</th>
                </tr>
              </thead>
              <tbody>
                {sources.map((source) => {
                  const state = sourceStatus(source);
                  return (
                    <tr key={source.source_id} data-source={source.source_id}>
                      <th scope="row">
                        <span className="dc-cell-line">{source.display_name}</span>
                        {source.cloud ? (
                          <>
                            <span className="dc-cell-sub">{t("sources.cloud.workspace", { name: source.cloud.workspace_name })}</span>
                            <span className="dc-cell-sub">{t("sources.cloud.ids", { workspace: source.cloud.workspace_id, item: source.cloud.item_id })}</span>
                          </>
                        ) : <span className="dc-cell-sub">{source.path}</span>}
                      </th>
                      <td>{t(`sources.kind.${source.kind}`)}</td>
                      <td>{t(`sources.role.${source.role}`)}</td>
                      <td>{source.access_type ?? t("sources.access.local")}</td>
                      <td><StatusBadge tone={state.tone} label={state.label} /></td>
                      <td className="ui-table-actions" data-ui-actions="">
                        <div className="dc-row-actions" data-ui-actions="">
                          {(() => {
                            const items = [];
                            if (source.status !== "ok" && !source.cloud) {
                              items.push({
                                label: t("sources.status.missing.find"),
                                icon: FolderSearch,
                                onSelect: () => find(source),
                              });
                            }
                            if (source.role !== "target") {
                              items.push({
                                label: t("create.remove"),
                                icon: Trash2,
                                destructive: true,
                                onSelect: () => { setRemoving(source); },
                              });
                            }
                            if (!items.length) return null;
                            return (
                              <Menu
                                label={`Actions for ${source.display_name}`}
                                align="end"
                                trigger={
                                  <Button
                                    variant="ghost"
                                    size="icon-sm"
                                    disabled={changeDisabled}
                                    aria-describedby={reasonId}
                                    aria-label={`Actions for ${source.display_name}`}
                                  >
                                    <MoreHorizontal className="size-4" aria-hidden="true" />
                                  </Button>
                                }
                                groups={[{ items }]}
                              />
                            );
                          })()}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="dc-section" aria-labelledby="dc-target-title">
        <div className="dc-section-head">
          <h2 id="dc-target-title" className="dc-section-title">{t("sources.target.title")}</h2>
          <ChangeTarget session={session} disabled={changeDisabled} reasonId={reasonId} triggerRef={changeTargetRef} />
        </div>
        <dl className="dc-summary">
          <div><dt>{t("sources.target.model")}</dt><dd>{names.model ?? t("shared.not_set")}</dd></div>
          <div><dt>{t("sources.target.report")}</dt><dd>{names.reportNew ? t("create.target.new_report") : names.report ?? t("shared.not_known")}</dd></div>
        </dl>
      </section>

      <section className="dc-section" aria-labelledby="dc-rules-section-title">
        <div className="dc-section-head">
          <h2 id="dc-rules-section-title" className="dc-section-title">Naming rules</h2>
          {onTabs ? (
            <Button variant="outline" size="sm" onClick={() => onTabs({ tab: "rules" })}>
              Open Naming rules tab →
            </Button>
          ) : null}
        </div>
        <p className="dc-muted">Rules for renaming and conflict resolution live in their own tab.</p>
      </section>

      <AlertDialog open={Boolean(removing)} onOpenChange={(open) => { if (!open) setRemoving(null); }}>
        {removing ? (
          <AlertDialogContent
            title={t("sources.remove.title", { source: removing.display_name })}
            description={t("sources.remove.body", { source: removing.display_name })}
            onCloseAutoFocus={(event) => {
              // Focus goes back to the trigger. When the source is gone, it goes to the section heading (UI design 9.2).
              event.preventDefault();
              const target = trigger.current?.isConnected ? trigger.current : titleRef.current;
              target?.focus();
            }}
            footer={<>
              <AlertDialogCancel asChild><Button variant="outline">{t("shared.cancel")}</Button></AlertDialogCancel>
              <AlertDialogAction asChild><Button variant="destructive" onClick={confirmRemove}>{t("sources.remove.confirm")}</Button></AlertDialogAction>
            </>}
          />
        ) : null}
      </AlertDialog>
    </div>
  );
}

function initialChoice(session) {
  const model = session.target?.model;
  const report = session.target?.report;
  return {
    model: model?.source_id ? `existing:${model.source_id}` : null,
    report: report?.mode === "existing" ? `existing:${report.source_id}` : "new_empty",
  };
}

function ChangeTarget({ session, disabled, reasonId, triggerRef }) {
  const setTarget = useAction("target_set");
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [choice, setChoice] = useState(() => ({ ...initialChoice(session), folder: null }));
  const [error, setError] = useState(null);
  const sources = (session.sources ?? []).map((source) => ({ key: source.source_id, name: source.display_name, kind: source.kind }));

  const start = (value) => {
    setOpen(value);
    if (value) {
      setChoice({ ...initialChoice(session), folder: null });
      setError(null);
      setTarget.reset();
    }
  };

  const save = async () => {
    if (!choice.model) return setError(t("create.target.need_model"));
    if (!choice.model.startsWith("existing:") && !choice.folder) return setError(t("create.target.folder_needed"));
    const ids = new Map(sources.map((source) => [source.key, source.key]));
    const payload = targetPayload({ targetModel: choice.model, targetReport: choice.report, copyFolder: choice.folder, name: session.display_name }, ids);
    const reply = await setTarget.run(payload);
    if (reply) {
      setOpen(false);
      toast.show({ tone: "ok", text: t("sources.target.done") });
    }
  };

  return (
    <Dialog open={open} onOpenChange={start}>
      <DialogTrigger asChild><Button ref={triggerRef} variant="outline" size="sm" disabled={disabled} aria-describedby={reasonId}>{t("sources.target.change")}</Button></DialogTrigger>
      {/* Radix mounts the content only while the dialog is open, and returns focus to the trigger on close. */}
      <DialogContent
          title={t("sources.target.change")}
          footer={<>
            <Button variant="outline" onClick={() => setOpen(false)}>{t("shared.cancel")}</Button>
            <Button onClick={save} loading={setTarget.pending} loadingText={t("shared.updating")}>{t("sources.target.save")}</Button>
          </>}>
          <TargetChoice
            sources={sources}
            model={choice.model}
            report={choice.report}
            folder={choice.folder}
            onModel={(model, folder) => setChoice((current) => ({ ...current, model, folder }))}
            onReport={(report) => setChoice((current) => ({ ...current, report }))}
            pickFolder={async () => (await desktopRequest(globalThis.pywebview?.api, "choose_folder")).folder ?? null}
            disabled={setTarget.pending}
          />
          {error || setTarget.error ? <p className="dc-step-error" role="alert">{error ?? errorCopy(setTarget.error).body}</p> : null}
        </DialogContent>
    </Dialog>
  );
}
