// Save dialog of the change report (UI design 5.6, step U10). The parent mounts it on each open.
// It shows the default file name "<session name> change report <yyyy-mm-dd>.md" and the folder.
// Confirm calls change_report_write. A toast tells the result. The app never commits or pushes.
import React, { useState } from "react";
import { Button } from "@/components/ui/button";
import { AlertDialog, AlertDialogCancel, AlertDialogContent } from "@/components/ui/dialog";
import { useToast } from "@/components/ui/toast";
import { errorCopy, t } from "../../copy.js";
import { normalizeError } from "../../errors.js";
import { useDevCenterStore } from "../../useDevCenter.js";
import { changeReportName } from "./applyModel.js";

// The desktop host opens the folder of a file. A host with no such method shows no action.
function showInFolder(path) {
  const api = globalThis.pywebview?.api;
  if (typeof api?.show_in_folder === "function") api.show_in_folder(path);
}

export default function ApplyReportDialog({ sessionName, applyId, onClose }) {
  const store = useDevCenterStore();
  const toast = useToast();
  const [name] = useState(() => changeReportName(sessionName));
  const [pending, setPending] = useState(false);

  const save = async () => {
    setPending(true);
    try {
      const reply = await store.run("change_report_write", applyId ? { apply_id: applyId, file_name: name } : { file_name: name });
      toast.show({ tone: "ok", text: t("report.toast"), action: { label: t("report.toast.action"), onClick: () => showInFolder(reply.path) } });
    } catch (raw) {
      const error = normalizeError(raw);
      if (error.code !== "stale_revision") toast.show({ tone: "warn", text: t("report.fail", { reason: errorCopy(error).body }) });
    } finally {
      setPending(false);
      onClose();
    }
  };

  return (
    <AlertDialog open onOpenChange={(value) => { if (!value && !pending) onClose(); }}>
      <AlertDialogContent
        className="dc-report-dialog"
        title={t("report.dialog.title")}
        description={t("report.dialog.body")}
        progress={pending}
        footer={
          <>
            <AlertDialogCancel asChild><Button variant="outline" disabled={pending}>{t("shared.cancel")}</Button></AlertDialogCancel>
            <Button onClick={save} loading={pending}>{t("report.confirm")}</Button>
          </>
        }>
        <dl className="dc-report-fields">
          <dt>{t("report.dialog.name")}</dt>
          <dd className="dc-mono" data-report="name">{name}</dd>
          <dt>{t("report.dialog.folder")}</dt>
          <dd data-report="folder">{t("report.dialog.folder.value")}</dd>
        </dl>
      </AlertDialogContent>
    </AlertDialog>
  );
}
