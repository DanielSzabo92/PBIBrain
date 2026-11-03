// Naming rules section of the Sources tab (UI design 4.8 and 13, U5).
import React, { useEffect, useRef, useState } from "react";
import { Check, LoaderCircle, MoreHorizontal, Pencil, Plus, RotateCcw, Tag, Trash2, TriangleAlert, X } from "lucide-react";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Menu } from "@/components/ui/menu";
import { Notice } from "@/components/ui/notice";
import { EmptyState } from "@/components/ui/result-panel";
import { StatusBadge } from "@/components/ui/status-badge";
import { useToast } from "@/components/ui/toast";
import { errorCopy, t } from "../../copy.js";
import { normalizeError } from "../../errors.js";
import { useAction, useDevCenterStore, useResource } from "../../useDevCenter.js";
import NamingRuleEditor from "./NamingRuleEditor.jsx";
import NamingRulesCopyDialog from "./NamingRulesCopyDialog.jsx";
import { formatScope, formatSupport, groupRulesByType, ruleCounts, ruleStatusProps } from "./namingRulesModel.js";

export default function NamingRules({ session, changeDisabled, reasonId, onChangeTarget }) {
  const toast = useToast();
  const store = useDevCenterStore();
  const namingRules = useResource("namingRules");

  const confirmAction = useAction("naming_rule_confirm");
  const rejectAction = useAction("naming_rule_reject");

  const [filter, setFilter] = useState("all");
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [editingRule, setEditingRule] = useState(null);
  const [editorOpen, setEditorOpen] = useState(false);
  const [copyDialogOpen, setCopyDialogOpen] = useState(false);
  const [deletingRule, setDeletingRule] = useState(null);

  const titleRef = useRef(null);
  const initializedRef = useRef(false);

  const targetSourceId = session.target?.model?.source_id;
  const targetSource = session.sources?.find((s) => s.source_id === targetSourceId);
  const targetModelName = targetSource?.display_name || namingRules.data?.target?.model_name || "target";

  const allRules = namingRules.data?.rules ?? [];
  const counts = ruleCounts(allRules);

  useEffect(() => {
    // Default filter: Proposed when proposed rules exist on initial load.
    if (!initializedRef.current && namingRules.data) {
      initializedRef.current = true;
      if (counts.proposed > 0) {
        setFilter("proposed");
      } else {
        setFilter("all");
      }
    }
  }, [namingRules.data, counts.proposed]);

  const toggleSelect = (ruleId) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(ruleId)) next.delete(ruleId);
      else next.add(ruleId);
      return next;
    });
  };

  const openAddRule = () => {
    setEditingRule(null);
    setEditorOpen(true);
  };

  const openEditRule = (rule) => {
    setEditingRule(rule);
    setEditorOpen(true);
  };

  const onSelectRuleFromDuplicate = (ruleId) => {
    const existing = allRules.find((r) => r.rule_id === ruleId);
    if (existing) {
      setEditingRule(existing);
    }
  };

  const handleConfirm = async (rule) => {
    const reply = await confirmAction.run({ rule_id: rule.rule_id });
    if (reply) {
      toast.show({ tone: "ok", text: `Rule confirmed: ${rule.text}` });
    }
  };

  const handleReject = async (rule) => {
    const reply = await rejectAction.run({ rule_id: rule.rule_id });
    if (reply) {
      toast.show({ tone: "ok", text: `Rule rejected: ${rule.text}` });
    }
  };

  const handleConfirmSelected = async () => {
    const ids = Array.from(selectedIds);
    let confirmedCount = 0;
    const total = ids.length;

    for (const id of ids) {
      const rule = allRules.find((r) => r.rule_id === id);
      try {
        await store.run("naming_rule_confirm", { rule_id: id });
        confirmedCount += 1;
        setSelectedIds((prev) => {
          const next = new Set(prev);
          next.delete(id);
          return next;
        });
      } catch (raw) {
        const error = normalizeError(raw);
        const cleanMsg = (error?.message || "Failed to confirm rule.").replace(/\.+$/, "");
        toast.show({
          tone: "bad",
          text: t("rules.confirm_selected.stopped", {
            n: confirmedCount,
            m: total,
            rule: rule?.text || id,
            message: cleanMsg,
          }),
        });
        return;
      }
    }

    setSelectedIds(new Set());
    toast.show({ tone: "ok", text: `${confirmedCount} rules confirmed.` });
  };

  const confirmDelete = async () => {
    const rule = deletingRule;
    setDeletingRule(null);
    if (!rule) return;
    const reply = await rejectAction.run({ rule_id: rule.rule_id });
    if (reply) {
      toast.show({ tone: "ok", text: "Rule deleted." });
    }
  };

  // State: No target model set
  if (!session.target?.model || !targetSourceId || (namingRules.data && namingRules.data.target === null)) {
    return (
      <section className="dc-section" aria-labelledby="dc-rules-title">
        <div className="dc-section-head">
          <h2 id="dc-rules-title" className="dc-section-title">Naming rules</h2>
        </div>
        <EmptyState headingLevel={3} title={t("rules.no_target.title")}>
          <p className="dc-muted">{t("rules.no_target.body")}</p>
          {onChangeTarget ? (
            <Button variant="outline" onClick={onChangeTarget}>
              {t("rules.no_target.action")}
            </Button>
          ) : null}
        </EmptyState>
      </section>
    );
  }

  // State: Detecting rules
  if (namingRules.status === "loading" && !namingRules.data) {
    return (
      <section className="dc-section" aria-labelledby="dc-rules-title" aria-busy="true">
        <div className="dc-section-head">
          <div className="dc-section-title-wrap">
            <h2 id="dc-rules-title" className="dc-section-title">
              Naming rules for {targetModelName}
            </h2>
            <p className="dc-muted">{t("rules.note")}</p>
          </div>
        </div>
        <div className="dc-empty-box" role="status">
          <LoaderCircle className="spin" aria-hidden="true" />
          <h3>{t("rules.detecting.title")}</h3>
          <p className="dc-muted">{t("rules.detecting.body", { model: targetModelName })}</p>
        </div>
      </section>
    );
  }

  // State: Empty rules in target model
  if (namingRules.data && allRules.length === 0) {
    return (
      <section className="dc-section" aria-labelledby="dc-rules-title">
        <div className="dc-section-head">
          <div className="dc-section-title-wrap">
            <h2 id="dc-rules-title" className="dc-section-title">
              Naming rules for {targetModelName}
            </h2>
            <p className="dc-muted">{t("rules.note")}</p>
          </div>
        </div>
        <EmptyState headingLevel={3} title={t("rules.empty.title")}>
          <p className="dc-muted">{t("rules.empty.body", { model: targetModelName })}</p>
          <div className="dc-empty-actions">
            <Button
              variant="default"
              disabled={changeDisabled}
              aria-describedby={reasonId}
              onClick={openAddRule}>
              <Plus aria-hidden="true" />
              {t("rules.add")}
            </Button>
            <Button
              variant="outline"
              disabled={changeDisabled}
              aria-describedby={reasonId}
              onClick={() => setCopyDialogOpen(true)}>
              {t("rules.copy_from")}
            </Button>
          </div>
        </EmptyState>

        <NamingRuleEditor
          open={editorOpen}
          onClose={() => setEditorOpen(false)}
          rule={editingRule}
          targetModelName={targetModelName}
          onSelectRule={onSelectRuleFromDuplicate}
        />

        <NamingRulesCopyDialog
          open={copyDialogOpen}
          onOpenChange={setCopyDialogOpen}
          session={session}
          sourceRuleCounts={namingRules.data?.source_rule_counts}
          targetModelName={targetModelName}
        />
      </section>
    );
  }

  // Filter rules
  const visibleRules = filter === "all" ? allRules : allRules.filter((r) => r.status === filter);
  const groups = groupRulesByType(visibleRules);

  const actionError = confirmAction.error ?? rejectAction.error;

  return (
    <section className="dc-section" aria-labelledby="dc-rules-title">
      <div className="dc-section-head">
        <div className="dc-section-title-wrap">
          <h2 id="dc-rules-title" ref={titleRef} tabIndex={-1} className="dc-section-title">
            Naming rules for {targetModelName}
          </h2>
          <p className="dc-muted">{t("rules.note")}</p>
        </div>
      </div>

      {actionError ? (
        <Notice tone="bad">{errorCopy(actionError).body}</Notice>
      ) : null}

      <div className="dc-rules-toolbar">
        <div className="dc-seg-control" role="group" aria-label="Show rules by status">
          <Button
            variant={filter === "proposed" ? "default" : "outline"}
            size="sm"
            aria-pressed={filter === "proposed"}
            onClick={() => setFilter("proposed")}>
            Proposed ({counts.proposed})
          </Button>
          <Button
            variant={filter === "confirmed" ? "default" : "outline"}
            size="sm"
            aria-pressed={filter === "confirmed"}
            onClick={() => setFilter("confirmed")}>
            Confirmed ({counts.confirmed})
          </Button>
          <Button
            variant={filter === "rejected" ? "default" : "outline"}
            size="sm"
            aria-pressed={filter === "rejected"}
            onClick={() => setFilter("rejected")}>
            Rejected ({counts.rejected})
          </Button>
          <Button
            variant={filter === "all" ? "default" : "outline"}
            size="sm"
            aria-pressed={filter === "all"}
            onClick={() => setFilter("all")}>
            All ({counts.all})
          </Button>
        </div>

        <span className="dc-grow" />

        {selectedIds.size > 0 ? (
          <Button
            variant="default"
            size="sm"
            disabled={changeDisabled || confirmAction.pending}
            aria-describedby={reasonId}
            onClick={handleConfirmSelected}>
            <Check aria-hidden="true" />
            {t("rules.confirm_selected", { n: selectedIds.size })}
          </Button>
        ) : null}

        <Button
          variant="outline"
          size="sm"
          disabled={changeDisabled}
          aria-describedby={reasonId}
          onClick={openAddRule}>
          <Plus aria-hidden="true" />
          {t("rules.add")}
        </Button>

        <Button
          variant="outline"
          size="sm"
          disabled={changeDisabled}
          aria-describedby={reasonId}
          onClick={() => setCopyDialogOpen(true)}>
          {t("rules.copy_from")}
        </Button>
      </div>

      {visibleRules.length === 0 ? (
        <div className="dc-rules-filter-empty">
          <p className="dc-muted">{t(`rules.filter_empty.${filter}`)}</p>
          <Button variant="outline" size="sm" onClick={() => setFilter("all")}>
            {t("rules.filter_empty.action")}
          </Button>
        </div>
      ) : (
        <div className="ui-table-scroll">
          <table className="ui-table dc-rules-table">
            <caption className="dc-caption">
              {t("rules.breaks_caption", { model: targetModelName })}
            </caption>
            <thead>
              <tr>
                <th scope="col" className="dc-col-check">
                  <span className="sr-only">Select</span>
                </th>
                <th scope="col">Rule</th>
                <th scope="col">Scope</th>
                <th scope="col">Origin</th>
                <th scope="col">Support</th>
                <th scope="col">Breaks</th>
                <th scope="col">Status</th>
                <th scope="col" className="dc-sticky-actions">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {groups.map((group) => (
                <React.Fragment key={group.objectType}>
                  <tr className="dc-rule-group-row">
                    <td colSpan={8} className="dc-rule-group-title">
                      {group.label}
                    </td>
                  </tr>
                  {group.rules.map((rule) => {
                    const statusProps = ruleStatusProps(rule.status);
                    const isProposed = rule.status === "proposed";
                    const isRejected = rule.status === "rejected";
                    const isConfirmed = rule.status === "confirmed";
                    const isUser = rule.origin === "user";
                    const isSelected = selectedIds.has(rule.rule_id);

                    const moreItems = [];
                    if (isProposed) {
                      moreItems.push(
                        {
                          label: "Edit",
                          icon: Pencil,
                          disabled: changeDisabled,
                          onSelect: () => openEditRule(rule),
                        },
                        {
                          label: "Reject",
                          icon: X,
                          disabled: changeDisabled,
                          onSelect: () => handleReject(rule),
                        },
                      );
                    } else if (isConfirmed) {
                      if (isUser) {
                        moreItems.push({
                          label: "Delete",
                          icon: Trash2,
                          destructive: true,
                          disabled: changeDisabled,
                          onSelect: () => setDeletingRule(rule),
                        });
                      } else {
                        moreItems.push({
                          label: "Reject",
                          icon: X,
                          disabled: changeDisabled,
                          onSelect: () => handleReject(rule),
                        });
                      }
                    }

                    return (
                      <tr
                        key={rule.rule_id}
                        data-rule={rule.rule_id}
                        className={`${isSelected ? "dc-row-selected" : ""} ${isRejected ? "dc-rule-rejected" : ""}`}>
                        <td className="dc-col-check">
                          {isProposed ? (
                            <Checkbox
                              size="target"
                              aria-label={`Select rule ${rule.text}`}
                              checked={isSelected}
                              disabled={changeDisabled}
                              aria-describedby={reasonId}
                              onCheckedChange={() => toggleSelect(rule.rule_id)}
                            />
                          ) : null}
                        </td>
                        <td className="dc-rule-text">{rule.text}</td>
                        <td>{formatScope(rule.scope)}</td>
                        <td>{rule.origin === "user" ? t("rules.origin.user") : t("rules.origin.detected")}</td>
                        <td className="dc-num">{formatSupport(rule)}</td>
                        <td className="dc-num">
                          {rule.breaks > 0 && !isRejected ? (
                            <span className="dc-breaks-warn">
                              <TriangleAlert className="dc-icon-sm" aria-hidden="true" />
                              {rule.breaks}
                            </span>
                          ) : (
                            rule.breaks ?? 0
                          )}
                        </td>
                        <td>
                          <StatusBadge tone={statusProps.tone} label={statusProps.label} />
                        </td>
                        <td className="dc-sticky-actions">
                          <div className="dc-row-actions">
                            {isProposed ? (
                              <>
                                <Button
                                  variant="outline"
                                  size="sm"
                                  disabled={changeDisabled}
                                  aria-describedby={reasonId}
                                  aria-label={`Confirm: ${rule.text}`}
                                  onClick={() => handleConfirm(rule)}>
                                  <Check aria-hidden="true" />
                                  {t("rules.confirm")}
                                </Button>
                                <Menu
                                  align="end"
                                  label={t("rules.more", { rule: rule.text })}
                                  trigger={
                                    <Button
                                      variant="ghost"
                                      size="icon-sm"
                                      disabled={changeDisabled}
                                      aria-describedby={reasonId}
                                      aria-label={t("rules.more", { rule: rule.text })}>
                                      <MoreHorizontal aria-hidden="true" />
                                    </Button>
                                  }
                                  groups={[{ items: moreItems }]}
                                />
                              </>
                            ) : null}

                            {isConfirmed ? (
                              <>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  disabled={changeDisabled}
                                  aria-describedby={reasonId}
                                  aria-label={`Edit: ${rule.text}`}
                                  onClick={() => openEditRule(rule)}>
                                  <Pencil aria-hidden="true" />
                                  Edit
                                </Button>
                                <Menu
                                  align="end"
                                  label={t("rules.more", { rule: rule.text })}
                                  trigger={
                                    <Button
                                      variant="ghost"
                                      size="icon-sm"
                                      disabled={changeDisabled}
                                      aria-describedby={reasonId}
                                      aria-label={t("rules.more", { rule: rule.text })}>
                                      <MoreHorizontal aria-hidden="true" />
                                    </Button>
                                  }
                                  groups={[{ items: moreItems }]}
                                />
                              </>
                            ) : null}

                            {isRejected ? (
                              <Button
                                variant="outline"
                                size="sm"
                                disabled={changeDisabled}
                                aria-describedby={reasonId}
                                aria-label={`Confirm again: ${rule.text}`}
                                onClick={() => handleConfirm(rule)}>
                                <RotateCcw aria-hidden="true" />
                                {t("rules.confirm")}
                              </Button>
                            ) : null}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </React.Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Side Pane Rule Editor */}
      <NamingRuleEditor
        open={editorOpen}
        onClose={() => setEditorOpen(false)}
        rule={editingRule}
        targetModelName={targetModelName}
        onSelectRule={onSelectRuleFromDuplicate}
      />

      {/* Copy Rules Dialog */}
      <NamingRulesCopyDialog
        open={copyDialogOpen}
        onOpenChange={setCopyDialogOpen}
        session={session}
        sourceRuleCounts={namingRules.data?.source_rule_counts}
        targetModelName={targetModelName}
      />

      {/* Delete User Rule Confirmation Dialog */}
      <AlertDialog
        open={Boolean(deletingRule)}
        onOpenChange={(open) => {
          if (!open) setDeletingRule(null);
        }}>
        {deletingRule ? (
          <AlertDialogContent
            title={t("rules.delete.title")}
            description={
              <>
                <p className="dc-cell-line">{deletingRule.text}</p>
                <p className="dc-muted">{t("rules.delete.body")}</p>
              </>
            }
            footer={<>
              <AlertDialogCancel asChild>
                <Button variant="outline">{t("shared.cancel")}</Button>
              </AlertDialogCancel>
              <AlertDialogAction asChild>
                <Button variant="destructive" onClick={confirmDelete}>
                  {t("rules.delete.confirm")}
                </Button>
              </AlertDialogAction>
            </>}
          />
        ) : null}
      </AlertDialog>
    </section>
  );
}
