import React, { useEffect, useState } from "react";
import { Check } from "lucide-react";
import { Button } from "./ui/button";
import { Card } from "./ui/card";
import { NativeSelect } from "./ui/native-select";
import { Label } from "./ui/label";
import { Switch } from "./ui/switch";

export const AUTO_ACCEPT_DEFAULT = 0.9;
const THRESHOLDS = [1, 0.95, 0.9, 0.85, 0.8, 0.7];

/** The review settings stored in the project file, with their defaults. */
export function reviewSettings(config) {
  const saved = config?.review || {};
  return { auto_accept: saved.auto_accept === true, auto_accept_threshold: Number(saved.auto_accept_threshold) || AUTO_ACCEPT_DEFAULT };
}

/**
 * Settings › Review. Auto-accept changes what "reviewed" means, so it is off until chosen here,
 * and every decision it makes is marked "Auto" under Reviewed and can be reopened.
 */
export default function ReviewSettings({ transport, config, onSaved, onChanged, scanning = false }) {
  const [draft, setDraft] = useState(() => reviewSettings(config));
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  useEffect(() => { setDraft(reviewSettings(config)); }, [config]);
  const saved = reviewSettings(config);
  const dirty = draft.auto_accept !== saved.auto_accept || (draft.auto_accept && draft.auto_accept_threshold !== saved.auto_accept_threshold);
  const save = async () => {
    setSaving(true); setMessage("");
    try {
      const next = await transport.saveConfig({ ...config, review: draft });
      onSaved?.(next);
      await onChanged?.();
      setMessage("Saved");
    } catch (cause) { setMessage(cause?.message || "Could not save the review settings"); }
    finally { setSaving(false); }
  };
  if (!config) return <Card className="panel config-panel"><p className="muted-copy" role="status">Open a project to change its review settings.</p></Card>;
  return <Card className="panel config-panel review-settings">
    <div className="settings-section">
      <div className="settings-section-copy"><h3>Auto-accept</h3><p>Suggestions that only restate the object’s own name or description.</p></div>
      <div className="review-settings-fields">
        <Switch
          checked={draft.auto_accept}
          onCheckedChange={(value) => setDraft((current) => ({ ...current, auto_accept: value === true }))}
          label="Accept these suggestions without review"
          description="They skip the queue, are marked “Auto” under Reviewed, and can be reopened there. A reopened suggestion is never accepted automatically again."
        />
        <Label className="config-field review-threshold"><span>Minimum confidence</span>
          <NativeSelect aria-label="Minimum confidence" value={String(draft.auto_accept_threshold)} disabled={!draft.auto_accept} onChange={(event) => setDraft((current) => ({ ...current, auto_accept_threshold: Number(event.target.value) }))}>
            {[...new Set([...THRESHOLDS, draft.auto_accept_threshold])].sort((a, b) => b - a).map((value) => <option key={value} value={String(value)}>{Math.round(value * 100)} %{value === AUTO_ACCEPT_DEFAULT ? " (default)" : ""}</option>)}
          </NativeSelect>
        </Label>
      </div>
    </div>
    <div className="config-actions" data-ui-actions="">
      <Button onClick={save} disabled={saving || scanning || !dirty} tooltip={scanning ? "Cannot save while a scan is in progress" : !dirty ? "No changes to save" : undefined}>{saving ? "Saving…" : "Save review settings"}</Button>
      {message ? <span role={message === "Saved" ? "status" : "alert"} className={message === "Saved" ? "success-text" : "error-copy"}>{message === "Saved" ? <Check aria-hidden="true" /> : null}{message}</span> : null}
    </div>
  </Card>;
}
