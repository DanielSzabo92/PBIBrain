// Naming rule editor side pane (UI design 4.8 and 13, U5).
import React, { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Field, useFieldIds } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { SidePane } from "@/components/ui/side-pane";
import { useToast } from "@/components/ui/toast";
import { errorCopy, t } from "../../copy.js";
import { useAction } from "../../useDevCenter.js";
import { formatPreviewText, OBJECT_TYPE_LABELS } from "./namingRulesModel.js";

const OBJECT_TYPE_OPTIONS = Object.entries(OBJECT_TYPE_LABELS).map(([value, label]) => ({
  value,
  label,
}));

const SCOPE_OPTIONS = [
  { value: "all", label: "All tables" },
  { value: "table", label: "Table" },
  { value: "display_folder", label: "Display folder" },
];

const CHECK_KIND_OPTIONS = [
  { value: "letter_case", label: "Letter case" },
  { value: "separator", label: "Separator" },
  { value: "prefix", label: "Prefix" },
  { value: "suffix", label: "Suffix" },
  { value: "unit_word", label: "Unit word" },
  { value: "folder_by_type", label: "Folder by type" },
  { value: "regex", label: "Regular expression" },
];

const CASE_OPTIONS = [
  { value: "title", label: "Title Case" },
  { value: "pascal", label: "PascalCase" },
  { value: "camel", label: "camelCase" },
  { value: "snake", label: "snake_case" },
  { value: "upper", label: "UPPER CASE" },
  { value: "lower", label: "lower case" },
];

const SEPARATOR_OPTIONS = [
  { value: "space", label: "Space" },
  { value: "underscore", label: "Underscore" },
  { value: "none", label: "None" },
];

const FORMAT_OPTIONS = [
  { value: "none", label: "None" },
  { value: "currency", label: "Currency" },
  { value: "percent", label: "Percent" },
];

const FOLDER_TYPE_OPTIONS = [
  { value: "display_folder", label: "Display folder" },
  { value: "table", label: "Table" },
];

export default function NamingRuleEditor({
  open,
  onClose,
  rule,
  targetModelName,
  onSelectRule,
  onSaved,
}) {
  const toast = useToast();
  const editAction = useAction("naming_rule_edit");

  const [objectType, setObjectType] = useState("measure");
  const [scopeKind, setScopeKind] = useState("all");
  const [scopeValue, setScopeValue] = useState("");
  const [formatKind, setFormatKind] = useState("none");
  const [namePrefix, setNamePrefix] = useState("");
  const [checkKind, setCheckKind] = useState("letter_case");
  const [checkValue, setCheckValue] = useState("title");
  const [folderType, setFolderType] = useState("display_folder");
  const [inlineError, setInlineError] = useState(null);

  const patternIds = useFieldIds("dc-rule-pattern");
  const tableScopeIds = useFieldIds("dc-rule-scope-table");
  const folderScopeIds = useFieldIds("dc-rule-scope-folder");
  const prefixFilterIds = useFieldIds("dc-rule-prefix-filter");
  const folderValueIds = useFieldIds("dc-rule-folder-value");
  const checkValueIds = useFieldIds("dc-rule-check-value");

  useEffect(() => {
    editAction.reset();
    setInlineError(null);
    if (rule) {
      setObjectType(rule.object_type || "measure");
      const scope = rule.scope || {};
      if (scope.table) {
        setScopeKind("table");
        setScopeValue(scope.table);
      } else if (scope.display_folder) {
        setScopeKind("display_folder");
        setScopeValue(scope.display_folder);
      } else {
        setScopeKind("all");
        setScopeValue("");
      }
      setFormatKind(scope.format_kind || "none");
      setNamePrefix(scope.name_prefix || "");
      const check = rule.check || {};
      setCheckKind(check.kind || "letter_case");
      setCheckValue(check.value || (check.kind === "letter_case" ? "title" : ""));
      setFolderType(check.folder || "display_folder");
    } else {
      setObjectType("measure");
      setScopeKind("all");
      setScopeValue("");
      setFormatKind("none");
      setNamePrefix("");
      setCheckKind("letter_case");
      setCheckValue("title");
      setFolderType("display_folder");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rule, open]);

  const onCheckKindChange = (nextKind) => {
    setCheckKind(nextKind);
    if (nextKind === "letter_case") setCheckValue("title");
    else if (nextKind === "separator") setCheckValue("space");
    else if (nextKind === "regex") setCheckValue("^[A-Z][A-Za-z0-9 %]*$");
    else setCheckValue("");
  };

  const previewScope = {
    table: scopeKind === "table" ? scopeValue : null,
    display_folder: scopeKind === "display_folder" ? scopeValue : null,
    format_kind: formatKind !== "none" ? formatKind : null,
    name_prefix: namePrefix.trim() || null,
  };

  const previewCheck = {
    kind: checkKind,
    value: checkValue,
    folder: checkKind === "folder_by_type" ? folderType : undefined,
  };

  const save = async () => {
    setInlineError(null);
    if (!checkValue.trim()) {
      setInlineError(t("rules.editor.required", { field: "value" }));
      return;
    }

    const payload = {
      rule_id: rule?.rule_id || undefined,
      object_type: objectType,
      scope: previewScope,
      check: previewCheck,
    };

    const reply = await editAction.run(payload);
    if (reply) {
      toast.show({ tone: "ok", text: "Rule saved." });
      onSaved?.(reply.rule);
      onClose();
    }
  };

  const actionError = editAction.error;
  const isDuplicate = actionError?.details?.reason === "duplicate_rule";
  const duplicateRuleId = actionError?.details?.existing_rule_id;
  const isRegexError = actionError?.details?.reason === "invalid_regex";
  const regexErrorDetail = actionError?.details?.detail || actionError?.message;

  const title = rule ? "Edit rule" : "Add rule";

  return (
    <SidePane
      open={open}
      onClose={onClose}
      title={title}
      className="dc-rule-editor">
      <div className="dc-rule-editor-form">
        <Select
          id="dc-rule-object-type"
          label="Object type"
          value={objectType}
          onValueChange={setObjectType}
          options={OBJECT_TYPE_OPTIONS}
        />

        <Select
          id="dc-rule-scope-kind"
          label="Scope"
          value={scopeKind}
          onValueChange={(val) => {
            setScopeKind(val);
            if (val === "all") setScopeValue("");
          }}
          options={SCOPE_OPTIONS}
        />

        {scopeKind === "table" ? (
          <Field ids={tableScopeIds} label="Table name">
            <Input
              id={tableScopeIds.control}
              value={scopeValue}
              onChange={(e) => setScopeValue(e.target.value)}
              placeholder="Table name"
            />
          </Field>
        ) : null}

        {scopeKind === "display_folder" ? (
          <Field ids={folderScopeIds} label="Display folder">
            <Input
              id={folderScopeIds.control}
              value={scopeValue}
              onChange={(e) => setScopeValue(e.target.value)}
              placeholder="Folder name"
            />
          </Field>
        ) : null}

        {objectType === "measure" ? (
          <Select
            id="dc-rule-format-kind"
            label="Format kind"
            value={formatKind}
            onValueChange={setFormatKind}
            options={FORMAT_OPTIONS}
          />
        ) : null}

        <Field ids={prefixFilterIds} label="Name prefix filter (optional)">
          <Input
            id={prefixFilterIds.control}
            value={namePrefix}
            onChange={(e) => setNamePrefix(e.target.value)}
            placeholder="Filter prefix"
          />
        </Field>

        <Select
          id="dc-rule-check-kind"
          label="Check kind"
          value={checkKind}
          onValueChange={onCheckKindChange}
          options={CHECK_KIND_OPTIONS}
        />

        {checkKind === "letter_case" ? (
          <Select
            id="dc-rule-check-case"
            label="Letter case"
            value={checkValue}
            onValueChange={setCheckValue}
            options={CASE_OPTIONS}
          />
        ) : null}

        {checkKind === "separator" ? (
          <Select
            id="dc-rule-check-separator"
            label="Separator"
            value={checkValue}
            onValueChange={setCheckValue}
            options={SEPARATOR_OPTIONS}
          />
        ) : null}

        {checkKind === "folder_by_type" ? (
          <>
            <Select
              id="dc-rule-folder-type"
              label="Folder target"
              value={folderType}
              onValueChange={setFolderType}
              options={FOLDER_TYPE_OPTIONS}
            />
            <Field ids={folderValueIds} label="Folder name">
              <Input
                id={folderValueIds.control}
                value={checkValue}
                onChange={(e) => setCheckValue(e.target.value)}
                placeholder="Folder name"
              />
            </Field>
          </>
        ) : null}

        {["prefix", "suffix", "unit_word"].includes(checkKind) ? (
          <Field ids={checkValueIds} label="Value">
            <Input
              id={checkValueIds.control}
              value={checkValue}
              onChange={(e) => setCheckValue(e.target.value)}
              placeholder="Value"
            />
          </Field>
        ) : null}

        {checkKind === "regex" ? (
          <Field
            ids={patternIds}
            label="Pattern"
            hint="Python regular expression. PBIBrain checks the full name."
            error={isRegexError ? t("rules.editor.bad_pattern", { detail: regexErrorDetail }) : inlineError}>
            <Input
              id={patternIds.control}
              className="code font-mono"
              value={checkValue}
              onChange={(e) => {
                setCheckValue(e.target.value);
                setInlineError(null);
                editAction.reset();
              }}
              aria-invalid={isRegexError || Boolean(inlineError) || undefined}
              aria-describedby={patternIds.hint}
            />
          </Field>
        ) : null}

        <div className="dc-rule-preview">
          <span className="dc-rule-preview-label">Rule preview</span>
          <p className="dc-rule-preview-text">
            {formatPreviewText(objectType, previewScope, previewCheck)}
          </p>
        </div>

        {rule?.support ? (
          <p className="dc-muted">
            Support in {targetModelName || "target"}: {rule.support.count} of {rule.support.total}. Breaks: {rule.breaks ?? 0}.
          </p>
        ) : null}

        {isDuplicate ? (
          <div className="dc-duplicate-error" role="alert">
            <p className="dc-step-error">
              {t("rules.editor.same_rule", { rule: duplicateRuleId })}
            </p>
            {duplicateRuleId && onSelectRule ? (
              <Button
                variant="outline"
                size="sm"
                onClick={() => onSelectRule(duplicateRuleId)}>
                Edit that rule
              </Button>
            ) : null}
          </div>
        ) : actionError && !isRegexError ? (
          <p className="dc-step-error" role="alert">
            {errorCopy(actionError).body}
          </p>
        ) : null}
      </div>

      <div className="dc-pane-footer">
        <Button variant="outline" onClick={onClose}>
          {t("shared.cancel")}
        </Button>
        <Button
          onClick={save}
          loading={editAction.pending}
          loadingText={t("shared.updating")}>
          {t("rules.editor.save")}
        </Button>
      </div>
    </SidePane>
  );
}
