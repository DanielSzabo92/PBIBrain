// BulkEditDialog (issue #12, operation source "Edit target"): rename by text or pattern, set a property,
// move to a display folder, apply the confirmed Naming Rules, or delete, on the selected rows or on all
// rows that match the filters. "Show preview" is a read (POST edit-preview). "Add to plan" is the only
// write, through the JS API (target_edit_apply). The Apply screen writes the files.
import React, { useState } from "react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { ChoiceRadio } from "@/components/ui/choice-radio";
import { Dialog, DialogClose, DialogContent } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { Notice } from "@/components/ui/notice";
import { Skeleton } from "@/components/ui/result-panel";
import { t, tn } from "../copy.js";
import { useAction } from "../useDevCenter.js";
import { EDIT_KINDS, EDIT_PROPERTIES, changeRows, editRequest, referenceRows, skippedCounts } from "./bulkEditModel.js";

export default function BulkEditDialog({ open, onOpenChange, ...props }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {open ? <EditContent {...props} onOpenChange={onOpenChange} /> : null}
    </Dialog>
  );
}

function CheckField({ id, checked, onChange, label }) {
  return (
    <div className="dc-edit-check">
      <Checkbox id={id} checked={checked} onCheckedChange={(value) => onChange(value === true)} />
      <Label htmlFor={id}>{label}</Label>
    </div>
  );
}

function TextField({ id, label, value, onChange, help }) {
  return (
    <div className="dc-edit-field">
      <Label htmlFor={id}>{label}</Label>
      <Input id={id} value={value} onChange={(event) => onChange(event.target.value)} aria-describedby={help ? `${id}-help` : undefined} />
      {help ? <p id={`${id}-help`} className="dc-policy-help">{help}</p> : null}
    </div>
  );
}

function EditContent({ onOpenChange, http, scope, count, allMatching, onSaved }) {
  const save = useAction("target_edit_apply");
  const [form, setForm] = useState({ kind: "rename", find: "", replace: "", regex: false, matchCase: true,
                                     property: "format_string", value: "", folder: "", policy: "block" });
  const [preview, setPreview] = useState(null);
  const [state, setState] = useState("idle");
  const update = (values) => {
    setForm((old) => ({ ...old, ...values }));
    setPreview(null);
    setState("idle");
  };
  const request = editRequest(form, scope);
  const propertyKind = EDIT_PROPERTIES[form.property];

  const runPreview = async () => {
    if (!request) return;
    setState("loading");
    try {
      setPreview(await http.previewEdit(request));
      setState("ready");
    } catch {
      setState("error");
    }
  };

  const submit = async () => {
    if (!request) return;
    const reply = await save.run(request);
    if (reply) {
      onOpenChange(false);
      onSaved?.(reply);
    }
  };

  const changes = changeRows(preview);
  const references = referenceRows(preview);
  const skipped = Object.values(skippedCounts(preview)).reduce((sum, value) => sum + value, 0);
  const blocking = preview?.plan?.blocking?.length ?? 0;

  return (
    <DialogContent
      title={allMatching ? t("edit.title.all", { n: count }) : tn("edit.title", count)}
      className="dc-policy-dialog dc-edit-dialog"
      footer={
        <>
          <DialogClose asChild>
            <Button variant="outline">{t("shared.cancel")}</Button>
          </DialogClose>
          <Button variant="outline" id="editpreview" disabled={!request} loading={state === "loading"}
            loadingText={t("edit.preview.loading")} onClick={runPreview}>
            {t("edit.preview")}
          </Button>
          <Button id="editadd" variant={form.kind === "delete" ? "destructive" : "default"}
            disabled={!request || state !== "ready" || changes.length === 0}
            loading={save.pending} loadingText={t("shared.updating")} onClick={submit}>
            {t("edit.add")}
          </Button>
        </>
      }>
      <p className="dc-policy-body">{t("edit.help")}</p>
      <ChoiceRadio
        legend={t("edit.kind.legend")}
        value={form.kind}
        onValueChange={(kind) => update({ kind })}
        items={EDIT_KINDS.map((kind) => ({ value: kind, label: t(`edit.kind.${kind}`) }))}
      />
      {form.kind === "rename" ? (
        <div className="dc-edit-fields">
          <TextField id="editfind" label={t("edit.rename.find")} value={form.find} onChange={(find) => update({ find })} />
          <TextField id="editreplace" label={t("edit.rename.replace")} value={form.replace} onChange={(replace) => update({ replace })}
            help={form.regex ? t("edit.rename.regex.help") : null} />
          <CheckField id="editregex" checked={form.regex} onChange={(regex) => update({ regex })} label={t("edit.rename.regex")} />
          <CheckField id="editcase" checked={form.matchCase} onChange={(matchCase) => update({ matchCase })} label={t("edit.rename.match_case")} />
        </div>
      ) : null}
      {form.kind === "set_property" ? (
        <div className="dc-edit-fields">
          <div className="dc-edit-field">
            <Label htmlFor="editproperty">{t("edit.property")}</Label>
            <NativeSelect id="editproperty" value={form.property}
              onChange={(event) => update({ property: event.target.value, value: Array.isArray(EDIT_PROPERTIES[event.target.value]) ? "default" : "" })}>
              {Object.keys(EDIT_PROPERTIES).map((name) => <option key={name} value={name}>{name}</option>)}
            </NativeSelect>
          </div>
          {propertyKind === "text" ? (
            <TextField id="editvalue" label={t("edit.value")} value={form.value} onChange={(value) => update({ value })} />
          ) : (
            <div className="dc-edit-field">
              <Label htmlFor="editvalue">{t("edit.value")}</Label>
              <NativeSelect id="editvalue" value={String(form.value || (propertyKind === "bool" ? "false" : "default"))}
                onChange={(event) => update({ value: event.target.value })}>
                {(propertyKind === "bool" ? ["true", "false"] : propertyKind).map((value) => (
                  <option key={value} value={value}>{propertyKind === "bool" ? t(`edit.value.${value}`) : value}</option>
                ))}
              </NativeSelect>
            </div>
          )}
        </div>
      ) : null}
      {form.kind === "move_folder" ? (
        <TextField id="editfolder" label={t("edit.folder")} value={form.folder} onChange={(folder) => update({ folder })} help={t("edit.folder.help")} />
      ) : null}
      {form.kind === "apply_naming_rules" ? <p className="dc-policy-help">{t("edit.rules.help")}</p> : null}
      {form.kind === "delete" ? (
        <ChoiceRadio
          legend={t("edit.delete.help")}
          value={form.policy}
          onValueChange={(policy) => update({ policy })}
          items={[{ value: "block", label: t("edit.policy.block"), reason: t("row.policy.block.help") },
                  { value: "cascade", label: t("edit.policy.cascade"), reason: t("row.policy.cascade.help") }]}
        />
      ) : null}

      {state === "loading" && !preview ? <Skeleton lines={2} label={t("edit.preview.loading")} /> : null}
      {state === "error" ? <Notice tone="bad" role="alert">{t("edit.preview.fail")}</Notice> : null}
      {preview ? (
        <div className="dc-edit-preview" role="region" aria-label={t("edit.preview")}>
          <p className="dc-policy-help">
            {tn("edit.preview.changes", changes.length)}
            {skipped > 0 ? ` · ${tn("edit.preview.skipped", skipped)}` : ""}
            {` · ${tn("edit.preview.references", preview.references_total ?? references.length)}`}
          </p>
          {blocking > 0 ? <Notice tone="warn">{tn("edit.preview.blocking", blocking)}</Notice> : null}
          {changes.length > 0 ? (
            <table className="dc-policy-table">
              <thead>
                <tr>
                  <th scope="col">{t("edit.col.object")}</th>
                  <th scope="col">{t("edit.col.before")}</th>
                  <th scope="col">{t("edit.col.after")}</th>
                </tr>
              </thead>
              <tbody>
                {changes.map((row) => (
                  <tr key={row.key}>
                    <th scope="row">{row.object}</th>
                    <td>{row.before}</td>
                    <td>{row.after}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
          {references.length > 0 ? (
            <table className="dc-policy-table">
              <thead>
                <tr>
                  <th scope="col">{t("edit.col.where")}</th>
                  <th scope="col">{t("edit.col.before")}</th>
                  <th scope="col">{t("edit.col.after")}</th>
                </tr>
              </thead>
              <tbody>
                {references.map((row) => (
                  <tr key={row.key}>
                    <th scope="row">
                      {row.object}
                      <span className="dc-policy-help"> {t(`edit.domain.${row.domain}`)}, {t(`edit.ref.${row.kind}`)}</span>
                    </th>
                    <td><code>{row.before}</code></td>
                    <td><code>{row.after}</code></td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
        </div>
      ) : null}
      {save.error ? <Notice tone="bad" role="alert">{t("edit.fail")}</Notice> : null}
    </DialogContent>
  );
}
