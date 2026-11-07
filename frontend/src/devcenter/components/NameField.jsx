// NameField part for Row detail Merge Choice sub-fields (UI design 4.4, 5.3, 6.2, step U6).
// All text follows ASD-STE100 rules.
import React, { useCallback, useEffect, useId, useRef, useState } from "react";
import { CircleDashed, CircleX, LoaderCircle, TriangleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { t, tn } from "../copy.js";

export const NAME_CHECK_DEBOUNCE_MS = 300;

export default function NameField({
  label = t("row.name.label"),
  value = "",
  savedValue = "",
  required = false,
  disabled = false,
  reasonId,
  row,
  sourceId,
  displayFolder,
  http,
  rules = [],
  autoProposeOnMount = false,
  onChange,
  onCommit,
}) {
  const inputId = useId();
  const statusId = `${inputId}-status`;
  const [draft, setDraft] = useState(value || "");
  const [checking, setChecking] = useState(false);
  const [proposing, setProposing] = useState(false);
  const [proposedRulesText, setProposedRulesText] = useState(null);
  const [breaks, setBreaks] = useState([]);
  const [clash, setClash] = useState(null);
  const [proposedName, setProposedName] = useState(null);
  const [emptyError, setEmptyError] = useState(false);

  const timerRef = useRef(null);
  const seqRef = useRef(0);
  const autoProposedRef = useRef(false);

  useEffect(() => {
    setDraft(value || "");
  }, [value]);

  const formatRuleNames = useCallback(
    (ruleIds = []) => {
      if (!Array.isArray(ruleIds) || ruleIds.length === 0) return "Naming rules";
      const labels = ruleIds.map((rid) => {
        const found = rules.find((r) => r.rule_id === rid);
        if (found?.text) return found.text.replace(/\.$/, "");
        return rid;
      });
      return labels.join(", ");
    },
    [rules]
  );

  const runCheck = useCallback(
    async (candidateText, { isPropose = false } = {}) => {
      if (!http || !row) return null;
      const trimmed = String(candidateText ?? "").trim();
      if (!isPropose && !trimmed) {
        setChecking(false);
        setBreaks([]);
        setClash(null);
        return null;
      }
      const token = ++seqRef.current;
      if (isPropose) setProposing(true);
      else setChecking(true);

      try {
        const objectType =
          row.object_type === "column" ? row.subtype || "data_column" : row.object_type || "measure";
        const body = {
          name: row.name || trimmed || "New measure",
          object_type: objectType,
          table: row.table || null,
          display_folder: displayFolder || row.display_folder || null,
          source_id: sourceId || null,
          ...(isPropose ? {} : { candidate: trimmed }),
        };
        const reply = await http.proposeName(body);
        if (seqRef.current !== token) return null;

        if (isPropose) {
          const nextName = reply.name || trimmed || row.name;
          setDraft(nextName);
          onChange?.(nextName);
          setEmptyError(false);
          setBreaks(Array.isArray(reply.breaks) ? reply.breaks : []);
          setClash(reply.clash || null);
          setProposedName(reply.name || null);
          setProposedRulesText(
            t("row.name.proposed", { rules: formatRuleNames(reply.rule_ids) })
          );
          onCommit?.(nextName, { valid: !reply.clash });
        } else {
          setBreaks(Array.isArray(reply.breaks) ? reply.breaks : []);
          setClash(reply.clash || null);
          setProposedName(reply.name || null);
        }
        return reply;
      } catch {
        if (seqRef.current === token) {
          setBreaks([]);
          setClash(null);
        }
        return null;
      } finally {
        if (seqRef.current === token) {
          setChecking(false);
          setProposing(false);
        }
      }
    },
    [http, row, displayFolder, sourceId, formatRuleNames, onChange, onCommit]
  );

  useEffect(() => {
    if (autoProposeOnMount && !autoProposedRef.current && !value) {
      autoProposedRef.current = true;
      runCheck(row?.name || "", { isPropose: true });
    }
  }, [autoProposeOnMount, value, row?.name, runCheck]);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  const handleInputChange = (event) => {
    const next = event.target.value;
    setDraft(next);
    setProposedRulesText(null);
    onChange?.(next);

    if (timerRef.current) clearTimeout(timerRef.current);

    if (!next.trim()) {
      setChecking(false);
      setBreaks([]);
      setClash(null);
      if (required) setEmptyError(true);
      return;
    }

    setEmptyError(false);
    timerRef.current = setTimeout(() => {
      runCheck(next, { isPropose: false });
    }, NAME_CHECK_DEBOUNCE_MS);
  };

  const commitCurrent = async () => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    const trimmed = draft.trim();
    if (required && !trimmed) {
      setEmptyError(true);
      return;
    }
    setEmptyError(false);
    if (!trimmed) {
      onCommit?.("", { valid: true });
      return;
    }
    const reply = await runCheck(trimmed, { isPropose: false });
    const hasClash = Boolean(reply ? reply.clash : clash);
    if (!hasClash) {
      onCommit?.(trimmed, { valid: true });
    }
  };

  const handleKeyDown = (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      commitCurrent();
    } else if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      if (timerRef.current) clearTimeout(timerRef.current);
      const restored = savedValue || "";
      setDraft(restored);
      onChange?.(restored);
      setEmptyError(false);
      setClash(null);
      setBreaks([]);
    }
  };

  const handleProposeClick = () => {
    if (timerRef.current) clearTimeout(timerRef.current);
    runCheck(draft.trim() || row?.name || "", { isPropose: true });
  };

  const handleUseProposed = () => {
    if (!proposedName) return;
    if (timerRef.current) clearTimeout(timerRef.current);
    setDraft(proposedName);
    onChange?.(proposedName);
    setClash(null);
    setEmptyError(false);
    onCommit?.(proposedName, { valid: true });
  };

  const isInvalid = Boolean(emptyError || clash);

  return (
    <div className="ui-field dc-name-field" data-slot="name-field">
      <label className="ui-field-label" htmlFor={inputId}>
        {label}
      </label>
      <div className="dc-name-input-row">
        <Input
          id={inputId}
          value={draft}
          disabled={disabled}
          aria-invalid={isInvalid || undefined}
          aria-describedby={
            [statusId, reasonId].filter(Boolean).join(" ") || undefined
          }
          onChange={handleInputChange}
          onBlur={commitCurrent}
          onKeyDown={handleKeyDown}
        />
        <Button
          type="button"
          variant="outline"
          size="icon"
          disabled={disabled || proposing}
          aria-label={t("row.name.propose")}
          title={t("row.name.propose")}
          onClick={handleProposeClick}
        >
          {proposing ? <LoaderCircle className="spin" aria-hidden="true" /> : <CircleDashed aria-hidden="true" />}
        </Button>
      </div>

      <div id={statusId} className="dc-name-feedback" aria-live="polite">
        {checking ? (
          <p className="ui-field-hint" role="status">
            <LoaderCircle className="spin" aria-hidden="true" />
            <span>{t("row.name.checking")}</span>
          </p>
        ) : null}

        {emptyError ? (
          <p className="ui-field-hint is-error" role="alert">
            <CircleX aria-hidden="true" />
            <span>{t("row.name.empty")}</span>
          </p>
        ) : null}

        {!emptyError && clash ? (
          <div className="dc-name-clash" role="alert">
            <p className="ui-field-hint is-error">
              <CircleX aria-hidden="true" />
              <span>
                {t("row.name.clash", {
                  type: clash.object_type || row?.object_type || "object",
                  name: draft.trim(),
                  table: clash.table || row?.table || "model",
                })}
              </span>
            </p>
            {proposedName && proposedName !== draft.trim() ? (
              <Button
                type="button"
                variant="outline"
                size="xs"
                disabled={disabled}
                // Keep focus in the input: a blur check moves this button before the click ends.
                onMouseDown={(event) => event.preventDefault()}
                onClick={handleUseProposed}
              >
                {t("row.name.clash.action", { proposed: proposedName })}
              </Button>
            ) : null}
          </div>
        ) : null}

        {!emptyError && breaks.length > 0 ? (
          <p className="ui-field-hint dc-name-warn" role="status">
            <TriangleAlert aria-hidden="true" />
            <span>
              {breaks.length === 1
                ? t("row.name.break.one", { rule: breaks[0].text })
                : `${tn("row.name.break", breaks.length)} ${breaks.map((b) => b.text).join(" ")}`}
            </span>
          </p>
        ) : null}

        {!emptyError && !clash && proposedRulesText ? (
          <p className="ui-field-hint">
            <span>{proposedRulesText}</span>
          </p>
        ) : null}
      </div>
    </div>
  );
}
