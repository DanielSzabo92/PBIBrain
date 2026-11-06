// Create flow (UI design 4.1, 5.1): a draft in three steps. The UI calls the JS API only at "Create session".
import React, { useRef, useState } from "react";
import { ArrowLeft, ArrowRight, Plus, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Menu } from "@/components/ui/menu";
import { Notice } from "@/components/ui/notice";
import { Input } from "@/components/ui/input";
import { Field, useFieldIds } from "@/components/ui/field";
import { ProgressList, StepIndicator } from "@/components/ui/progress";
import { desktopRequest } from "../../desktop.js";
import { errorCopy, t, tn } from "../copy.js";
import { useDevCenterState, useDevCenterStore } from "../useDevCenter.js";
import TargetChoice from "./TargetChoice.jsx";
import { defaultSessionName, draftHasModel, draftSource, runCreateFlow } from "./sessionModel.js";

// Local source kinds of the "Add source" menu and the native picker of each one.
// The cloud items are not in this version (user scope cut 2026-11-01: cloud UI is a future feature).
const ADD_ITEMS = [
  { kind: "pbip", label: "create.add_source.pbip", picker: "choose_sources" },
  { kind: "tmdl_folder", label: "create.add_source.tmdl", picker: "choose_folder" },
  { kind: "model_bim", label: "create.add_source.bim", picker: "choose_sources" },
  { kind: "pbir_report", label: "create.add_source.pbir", picker: "choose_folder" },
];

const STEP_KEYS = ["create.step.sources", "create.step.target", "create.step.name"];

function desktopApi() {
  return globalThis.pywebview?.api ?? null;
}

async function pick(picker) {
  const reply = await desktopRequest(desktopApi(), picker);
  if (picker === "choose_folder") return reply.folder ? [reply.folder] : [];
  return reply.sources ?? [];
}

export default function CreateSession({ onCancel, onDone, onOpenPartial }) {
  const store = useDevCenterStore();
  const busy = useDevCenterState((state) => state.busy);
  const [step, setStep] = useState(0);
  const [draft, setDraft] = useState({ sources: [], targetModel: null, targetReport: "new_empty", copyFolder: null, name: "" });
  const [nameTouched, setNameTouched] = useState(false);
  const [message, setMessage] = useState(null);
  const [stepError, setStepError] = useState(null);
  const [running, setRunning] = useState(false);
  const [lines, setLines] = useState(null);
  const [result, setResult] = useState(null);
  const nextKey = useRef(1);
  const headingRef = useRef(null);
  const nameIds = useFieldIds("dc-create-name");

  const update = (patch) => setDraft((current) => ({ ...current, ...patch }));
  const sessionName = nameTouched ? draft.name : draft.name || defaultSessionName(draft);

  const addSource = async (item) => {
    setMessage(null);
    let paths;
    try {
      paths = await pick(item.picker);
    } catch (cause) {
      setMessage({ tone: "bad", text: cause.message });
      return;
    }
    const added = [];
    for (const path of paths) {
      const value = draftSource(path, item.kind);
      if (value.refused) {
        setMessage({ tone: "bad", text: value.refused });
        continue;
      }
      if ([...draft.sources, ...added].some((source) => source.path === value.path)) {
        setMessage({ tone: "warn", text: t("create.sources.duplicate", { source: value.name }) });
        continue;
      }
      added.push({ ...value, key: String(nextKey.current++) });
    }
    if (added.length > 0) update({ sources: [...draft.sources, ...added] });
  };

  const removeSource = (key) => {
    const sources = draft.sources.filter((source) => source.key !== key);
    const patch = { sources };
    if (draft.targetModel?.endsWith(`:${key}`)) Object.assign(patch, { targetModel: null, copyFolder: null });
    if (draft.targetReport?.endsWith(`:${key}`)) patch.targetReport = "new_empty";
    update(patch);
  };

  const goTo = (index) => {
    setStepError(null);
    setStep(index);
    requestAnimationFrame(() => headingRef.current?.focus());
  };

  const next = () => {
    if (step === 0 && !draftHasModel(draft.sources)) return setStepError(t("create.sources.need_model"));
    if (step === 1 && !draft.targetModel) return setStepError(t("create.target.need_model"));
    if (step === 1 && !draft.targetModel.startsWith("existing:") && !draft.copyFolder) return setStepError(t("create.target.folder_needed"));
    goTo(step + 1);
  };

  const create = async () => {
    const name = sessionName.trim();
    setNameTouched(true);
    if (!name) {
      update({ name: "" });
      setStepError(t("create.name.required"));
      return;
    }
    setStepError(null);
    setRunning(true);
    const outcome = await runCreateFlow({
      draft: { ...draft, name },
      run: (method, payload) => store.run(method, payload),
      onStep: setLines,
      describe: (error) => errorCopy(error).body,
    });
    setRunning(false);
    setResult(outcome);
    if (outcome.created && outcome.failed.length === 0 && outcome.targetSet) onDone();
  };

  const steps = STEP_KEYS.map((key, index) => ({ label: t(key), state: index < step ? "done" : index === step ? "current" : "todo" }));
  const partial = result?.created && (result.failed.length > 0 || !result.targetSet);
  const locked = running || busy === "long";

  return (
    <div className="dc-page dc-create">
      <header className="dc-page-head">
        <div>
          <h1 className="dc-title">{t("create.title")}</h1>
        </div>
      </header>
      <StepIndicator steps={steps} label={t("create.title")} />
      <section className="dc-create-body" aria-labelledby="dc-create-step">
        <h2 id="dc-create-step" ref={headingRef} tabIndex={-1} className="dc-section-title">{t(STEP_KEYS[step])}</h2>

        {step === 0 ? (
          <>
            <p className="dc-subtitle">{t("create.sources.body")}</p>
            <div className="dc-toolbar" data-ui-actions="">
              <Menu
                label={t("create.add_source")}
                trigger={<Button variant="outline"><Plus aria-hidden="true" />{t("create.add_source")}</Button>}
                groups={[{ items: ADD_ITEMS.map((item) => ({ label: t(item.label), onSelect: () => addSource(item) })) }]}
              />
            </div>
            {message ? <Notice tone={message.tone}>{message.text}</Notice> : null}
            {draft.sources.length === 0 ? <p className="dc-muted">{t("create.sources.empty")}</p> : (
              <ul className="dc-draft-list" aria-label={t("create.sources.caption")}>
                {draft.sources.map((source) => (
                  <li key={source.key} className="dc-draft-item">
                    <span className="dc-draft-name">{source.name}</span>
                    <span className="dc-draft-kind">{t(`sources.kind.${source.kind}`)}</span>
                    <span className="dc-draft-path">{source.path}</span>
                    <Button variant="ghost" size="icon-sm" aria-label={t("create.remove.label", { source: source.name })} onClick={() => removeSource(source.key)}><X /></Button>
                  </li>
                ))}
              </ul>
            )}
          </>
        ) : null}

        {step === 1 ? (
          <TargetChoice
            sources={draft.sources}
            model={draft.targetModel}
            report={draft.targetReport}
            folder={draft.copyFolder}
            onModel={(value, folder) => update({ targetModel: value, copyFolder: folder })}
            onReport={(value) => update({ targetReport: value })}
            pickFolder={async () => (await pick("choose_folder"))[0] ?? null}
          />
        ) : null}

        {step === 2 ? (
          <>
            <Field ids={nameIds} label={t("create.name.label")} error={stepError && !sessionName.trim() ? stepError : null}>
              <Input id={nameIds.control} value={sessionName} maxLength={200} disabled={running || Boolean(result?.created)}
                aria-invalid={stepError && !sessionName.trim() ? "true" : undefined}
                aria-describedby={stepError && !sessionName.trim() ? nameIds.hint : undefined}
                onChange={(event) => { setNameTouched(true); update({ name: event.target.value }); }} />
            </Field>
            <dl className="dc-summary">
              <div><dt>{t("create.summary.sources")}</dt><dd>{draft.sources.map((source) => source.name).join(", ")}</dd></div>
              <div><dt>{t("create.summary.target_model")}</dt><dd>{summaryModel(draft)}</dd></div>
              <div><dt>{t("create.summary.target_report")}</dt><dd>{summaryReport(draft)}</dd></div>
            </dl>
            {lines ? <ProgressList lines={lines} label={t("create.progress.label")} /> : null}
            {result && !result.created ? <Notice tone="bad">{t("create.failed")}</Notice> : null}
            {partial ? (
              <Notice tone="warn" actions={<Button onClick={onOpenPartial}>{t("create.partial.action")}</Button>}>
                {result.failed.length > 0 ? tn("create.partial", result.failed.length) : `${t("create.progress.target")}: ${t("create.progress.not_run")}`}
              </Notice>
            ) : null}
          </>
        ) : null}

        {stepError && step !== 2 ? <p className="dc-step-error" role="alert">{stepError}</p> : null}
        {stepError && step === 2 && sessionName.trim() ? <p className="dc-step-error" role="alert">{stepError}</p> : null}
      </section>

      <footer className="dc-create-foot">
        <Button variant="ghost" onClick={onCancel} disabled={running || Boolean(result?.created)}>{t("shared.cancel")}</Button>
        <div className="dc-create-nav">
          {step > 0 ? <Button variant="outline" onClick={() => goTo(step - 1)} disabled={running || Boolean(result?.created)}><ArrowLeft aria-hidden="true" />{t("create.back")}</Button> : null}
          {step < 2 ? <Button onClick={next}>{t("create.next")}<ArrowRight aria-hidden="true" /></Button> : null}
          {step === 2 && !result?.created ? <Button onClick={create} loading={running} loadingText={t("work.long.session_create")} disabled={locked && !running}>{t("create.run")}</Button> : null}
        </div>
      </footer>
    </div>
  );
}

function draftName(draft, key) {
  return draft.sources.find((source) => source.key === key)?.name ?? t("shared.not_known");
}

function summaryModel(draft) {
  const [mode, key] = String(draft.targetModel ?? "").split(":");
  if (mode === "existing") return draftName(draft, key);
  if (mode === "copy") return `${t("create.target.copy", { source: draftName(draft, key) })}. ${t("create.target.copy.folder", { path: draft.copyFolder })}`;
  if (mode === "empty") return `${t("create.target.empty")}. ${t("create.target.copy.folder", { path: draft.copyFolder })}`;
  return t("shared.not_set");
}

function summaryReport(draft) {
  const [mode, key] = String(draft.targetReport ?? "new_empty").split(":");
  return mode === "existing" ? draftName(draft, key) : t("create.target.new_report");
}
