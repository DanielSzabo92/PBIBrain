// One dialog for the Apply, format only, and Undo flows (UI design 5.5, 5.6, 8.4, step U10).
// Phases: confirm, then the progress list, then the result panel. The parent mounts it on each open.
// While the call runs, the dialog has no close button and Escape does nothing.
// Initial focus: the approval checkbox, else Cancel. Focus goes to the result title when the result shows.
import React, { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { AlertDialog, AlertDialogCancel, AlertDialogContent } from "@/components/ui/dialog";
import { t } from "../../copy.js";
import { normalizeError } from "../../errors.js";
import { useDevCenterState, useDevCenterStore } from "../../useDevCenter.js";
import ApplyProgressList from "./ApplyProgressList.jsx";
import ApplyResultPanel from "./ApplyResultPanel.jsx";
import "./apply.css";
import {
  approvalItems,
  approvalPurposes,
  clockTime,
  deletedNames,
  desktopLine,
  FLOW_METHOD,
  flowResult,
  needsDesktopBanner,
  progressLine,
  progressRows,
} from "./applyModel.js";

const APPROVE_ID = "dc-apply-approve";

function ApplyConfirmBody({ preview, plan, approvals, approved, onApproved }) {
  const summary = preview?.summary ?? {};
  const deletes = deletedNames(plan);
  const desktop = desktopLine(preview?.desktop_state, "apply");
  return (
    <>
      <ul className="dc-apply-counts" aria-label={t("plan.summary")}>
        <li className="dc-num">{t("apply.summary.created", { n: summary.add ?? 0 })}</li>
        <li className="dc-num">{t("apply.summary.deleted", { n: summary.remove ?? 0 })}</li>
        <li className="dc-num">{t("apply.summary.modified", { n: summary.change ?? 0 })}</li>
        <li className="dc-num">{t("apply.summary.renamed", { n: summary.rename ?? 0 })}</li>
      </ul>
      {deletes.length > 0 ? <p className="dc-apply-deletes" data-apply="deletes">{t("apply.deletes", { n: deletes.length, list: deletes.join(", ") })}</p> : null}
      {approvals.length > 0 ? (
        <>
          <h3 className="dc-apply-h3">{t("apply.approvals", { n: approvals.length })}</h3>
          <ul className="dc-apply-approvals">
            {approvals.map((item) => (
              <li key={item.id} data-severity={item.severity}>
                <span className="dc-apply-severity" data-severity={item.severity}>{t(`apply.severity.${item.severity}`)}</span>
                <span>{item.name}</span>
              </li>
            ))}
          </ul>
        </>
      ) : null}
      {desktop ? <p className="dc-apply-desktop" data-desktop="before">{desktop}</p> : null}
      {approvals.length > 0 ? (
        <div className="dc-apply-approve">
          <Checkbox id={APPROVE_ID} size="target" checked={approved} onCheckedChange={(value) => onApproved(value === true)} />
          <label htmlFor={APPROVE_ID}>{t("apply.approve")}</label>
        </div>
      ) : null}
    </>
  );
}

// kind: apply, format, or undo. preview: GET apply/preview (apply and format). last: GET apply/last (undo).
// onDone(reply) runs after a successful call. onCheckPlan runs for "Check plan" (stale plan).
export default function ApplyFlowDialog({ kind, preview, plan, last, targetName, onClose, onDone, onCheckPlan, onOpenLog, onWriteReport }) {
  const store = useDevCenterStore();
  const progress = useDevCenterState((state) => state.progress);
  // The dialog binds the preview (and its plan hash) of the open.
  const [bound] = useState(() => ({ preview, plan, last }));
  // Undo is refused when the target files changed after the apply (GET apply/last). No "Undo anyway".
  const refusedAtOpen = kind === "undo" && Boolean(last?.target_changed);
  const [phase, setPhase] = useState(refusedAtOpen ? "result" : "confirm");
  const [approved, setApproved] = useState(false);
  const [result, setResult] = useState(() => (refusedAtOpen
    ? flowResult("undo", { error: { code: "action_not_allowed", details: { reason: "target_changed", files: last.changed_files ?? [] } } })
    : null));
  const [failedStep, setFailedStep] = useState(null);
  const [desktopState, setDesktopState] = useState(null);
  const [elapsed, setElapsed] = useState(0);
  const startedRef = useRef(0);
  const titleRef = useRef(null);

  const approvals = kind === "apply" ? approvalItems(bound.preview, bound.plan) : [];
  const deletes = kind === "apply" ? deletedNames(bound.plan).length : 0;
  const running = phase === "running";
  const fileCount = bound.preview?.non_canonical_files?.length ?? 0;

  useEffect(() => {
    if (!running) return undefined;
    const timer = setInterval(() => setElapsed(Date.now() - startedRef.current), 1000);
    return () => clearInterval(timer);
  }, [running]);

  useEffect(() => {
    if (phase === "result") titleRef.current?.focus();
  }, [phase]);

  const confirm = async () => {
    startedRef.current = Date.now();
    setElapsed(0);
    setPhase("running");
    let payload = {};
    if (kind === "apply") payload = { plan_hash: bound.preview?.plan_hash ?? "", approvals: approvalPurposes(bound.preview) };
    if (kind === "undo" && bound.last?.apply_id) payload = { apply_id: bound.last.apply_id };
    const time = clockTime();
    try {
      const reply = await store.run(FLOW_METHOD[kind], payload);
      setDesktopState(needsDesktopBanner(reply) ? "after" : null);
      setResult(flowResult(kind, { reply, planSteps: bound.plan?.steps?.length ?? 0, time: kind === "undo" ? clockTime(new Date(bound.last?.finished_utc ?? Date.now())) : time }));
      onDone?.(reply);
    } catch (raw) {
      const error = normalizeError(raw);
      setFailedStep(error.details?.step ?? null);
      setResult(flowResult(kind, { error }));
    }
    setPhase("result");
  };

  let title;
  if (phase === "confirm") {
    if (kind === "apply") title = t("apply.title", { target: targetName || "the target" });
    else if (kind === "format") title = t("format.title", { n: fileCount });
    else title = t("undo.title", { time: bound.last?.finished_utc ? clockTime(new Date(bound.last.finished_utc)) : "" });
  } else if (phase === "running") {
    title = kind === "apply" ? t("apply.progress.title") : t(`${kind}.progress.title`);
  } else {
    title = t(`${kind}.result.heading`);
  }

  let description;
  if (phase === "confirm") description = kind === "apply" ? t("apply.body") : kind === "format" ? t("format.body", { n: fileCount }) : t("undo.body", { n: bound.last?.file_count ?? 0 });
  else if (phase === "running") description = kind === "undo" ? t("undo.progress.body") : t("apply.progress.body");

  const rows = progressRows(kind, progress, {
    approvalCount: approvals.length,
    failedStep: phase === "result" && result?.type === "failure" ? failedStep : null,
    finished: phase === "result" && result && result.type !== "failure" && result.type !== "refused" && result.type !== "stale",
  });

  const confirmLabel = kind === "apply" ? t("apply.confirm") : kind === "format" ? t("format.confirm") : t("undo.confirm");
  const confirmVariant = kind === "undo" || (kind === "apply" && deletes > 0) ? "destructive" : "default";
  const confirmDisabled = kind === "apply" && approvals.length > 0 && !approved;

  const onOpenAutoFocus = (event) => {
    // A refused Undo opens on its result: the focus goes to the result title.
    if (refusedAtOpen) {
      event.preventDefault();
      titleRef.current?.focus();
    } else if (kind === "apply" && approvals.length > 0) {
      event.preventDefault();
      document.getElementById(APPROVE_ID)?.focus();
    }
  };

  let footer = null;
  if (phase === "confirm") {
    footer = (
      <>
        <AlertDialogCancel asChild><Button variant="outline">{t("shared.cancel")}</Button></AlertDialogCancel>
        <Button variant={confirmVariant} onClick={confirm} disabled={confirmDisabled} data-confirm={kind}>{confirmLabel}</Button>
      </>
    );
  } else if (phase === "result") {
    footer = (
      <>
        {result?.type === "stale" ? <Button variant="outline" onClick={() => { onClose(); onCheckPlan?.(); }}>{t("apply.stale.action")}</Button> : null}
        {result?.type === "failure" && onOpenLog ? <Button variant="outline" onClick={() => { onClose(); onOpenLog(); }}>{t("apply.open_log")}</Button> : null}
        {kind === "apply" && (result?.type === "success" || result?.type === "differences") && onWriteReport ? (
          <Button variant="outline" onClick={() => { onClose(); onWriteReport(); }}>{t("apply.write_report")}</Button>
        ) : null}
        <AlertDialogCancel asChild><Button>{t("apply.result.close")}</Button></AlertDialogCancel>
      </>
    );
  }

  return (
    <AlertDialog open onOpenChange={(value) => { if (!value && !running) onClose(); }}>
      <AlertDialogContent
        className="dc-apply-dialog"
        data-flow={kind}
        data-phase={phase}
        title={title}
        description={description}
        progress={running}
        onOpenAutoFocus={onOpenAutoFocus}
        footer={footer}>
        {phase === "confirm" && kind === "apply" ? (
          <ApplyConfirmBody preview={bound.preview} plan={bound.plan} approvals={approvals} approved={approved} onApproved={setApproved} />
        ) : null}
        {phase === "confirm" && kind === "format" ? (
          <>
            <p className="dc-apply-note">{t("format.note")}</p>
            {fileCount > 0 ? <ul className="dc-apply-files">{bound.preview.non_canonical_files.map((file) => <li key={file} className="dc-mono">{file}</li>)}</ul> : null}
          </>
        ) : null}
        {phase === "confirm" && kind === "undo" && desktopLine(bound.preview?.desktop_state, "undo") ? (
          <p className="dc-apply-desktop" data-desktop="before">{desktopLine(bound.preview?.desktop_state, "undo")}</p>
        ) : null}
        {phase === "running" ? <ApplyProgressList rows={rows} line={progressLine(kind, rows, progress, elapsed)} /> : null}
        {phase === "result" && result ? (
          <>
            {result.type === "failure" || result.type === "success" || result.type === "differences" ? <ApplyProgressList rows={rows} line={null} /> : null}
            <ApplyResultPanel ref={titleRef} result={result} desktopAfter={desktopState === "after" ? t("apply.desktop_after") : null} />
          </>
        ) : null}
      </AlertDialogContent>
    </AlertDialog>
  );
}
