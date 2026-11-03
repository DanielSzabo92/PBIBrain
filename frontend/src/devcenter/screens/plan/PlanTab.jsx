// Plan tab without Apply (UI design 4.6, 5.5, 8, step U7).
import React, { useEffect, useMemo, useRef, useState } from "react";
import { ChevronRight, CircleX, TriangleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Notice } from "@/components/ui/notice";
import { EmptyState, Skeleton } from "@/components/ui/result-panel";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { StatusBadge } from "@/components/ui/status-badge";
import { errorCopy, t } from "../../copy.js";
import { normalizeError } from "../../errors.js";
import { createDevCenterHttp } from "../../httpClient.js";
import { slashGoesToSearch } from "../../preferences.js";
import { useAction, useDevCenterStore, useResource } from "../../useDevCenter.js";
import { targetNames } from "../sessionModel.js";
import {
  buildBlockList,
  formatCheckTime,
  formatWarningText,
  planPhaseGroups,
  planStripState,
  planSummaryGroups,
} from "./planModel.js";

const DOMAIN_OPTIONS = [
  { value: "all", label: "All" },
  { value: "model", label: "Model" },
  { value: "report", label: "Report" },
];

export default function PlanTab({ session, changeDisabled, reasonId, onTabs, onChangeTarget }) {
  const store = useDevCenterStore();
  const http = useMemo(() => createDevCenterHttp(), []);
  const planResource = useResource("plan");
  const formatOnlyAction = useAction("format_only_apply");

  const [checking, setChecking] = useState(false);
  const [checkTime, setCheckTime] = useState(() => formatCheckTime(session?.checked_at));
  const [validationOverride, setValidationOverride] = useState(null);
  const [checkError, setCheckError] = useState(null);
  const [announcement, setAnnouncement] = useState("");
  const [domainFilter, setDomainFilter] = useState("all");
  const [query, setQuery] = useState("");
  const [expandedIds, setExpandedIds] = useState(() => new Set());

  const searchRef = useRef(null);
  const defaultExpandedRef = useRef(false);

  useEffect(() => {
    if (session?.checked_at) {
      setCheckTime(formatCheckTime(session.checked_at));
    }
  }, [session?.checked_at]);

  useEffect(() => {
    const onKeyDown = (event) => {
      if (slashGoesToSearch(event)) {
        event.preventDefault();
        event.stopImmediatePropagation();
        searchRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKeyDown, true);
    return () => window.removeEventListener("keydown", onKeyDown, true);
  }, []);

  const effectivePlan = useMemo(() => {
    if (!planResource.data) return null;
    if (!validationOverride) return planResource.data;
    return {
      ...planResource.data,
      status: validationOverride.status ?? planResource.data.status,
      blocking: validationOverride.blocking ?? planResource.data.blocking,
      warnings: validationOverride.warnings ?? planResource.data.warnings,
    };
  }, [planResource.data, validationOverride]);

  const { model: targetModelName } = targetNames(session);

  const blocks = useMemo(
    () => buildBlockList({
      plan: effectivePlan,
      session,
      targetModelName,
    }),
    [effectivePlan, session, targetModelName],
  );

  const isChecking = checking || session?.plan_state === "checking";
  const strip = useMemo(
    () => planStripState({
      plan: effectivePlan,
      blocks,
      checking: isChecking,
      checkTime,
    }),
    [effectivePlan, blocks, isChecking, checkTime],
  );

  const summary = useMemo(() => planSummaryGroups(effectivePlan), [effectivePlan]);
  const phases = useMemo(
    () => planPhaseGroups(effectivePlan, { domainFilter, query }),
    [effectivePlan, domainFilter, query],
  );

  useEffect(() => {
    if (!defaultExpandedRef.current && phases.length > 0) {
      defaultExpandedRef.current = true;
      const changesPhase = phases.find((p) => p.phase === "changes") || phases[0];
      const firstItem = changesPhase?.items?.[0];
      if (firstItem) {
        setExpandedIds(new Set([firstItem.id]));
      }
    }
  }, [phases]);

  const toggleStep = (id) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleCheckPlan = async () => {
    if (checking) return;
    setChecking(true);
    setCheckError(null);
    setAnnouncement(t("plan.check.loading"));
    try {
      const reply = await http.validatePlan("full");
      await store.load("plan");
      const nowTime = "14:22";
      setCheckTime(nowTime);
      setValidationOverride({
        status: reply.status,
        blocking: reply.blocking,
        warnings: reply.warnings,
      });
      const nextStrip = planStripState({
        plan: { ...(effectivePlan || {}), ...reply },
        blocks: buildBlockList({
          plan: { ...(effectivePlan || {}), ...reply },
          session,
          targetModelName,
        }),
        checking: false,
        checkTime: nowTime,
      });
      setAnnouncement(`${nextStrip.badgeLabel}. ${nextStrip.body}`);
    } catch (raw) {
      setCheckError(normalizeError(raw));
    } finally {
      setChecking(false);
    }
  };

  const handleBlockAction = async (block) => {
    const action = block.action;
    if (!action) return;
    if (action.type === "compare_marks") {
      onTabs({ tab: "compare", marks: true, rowKey: null });
    } else if (action.type === "show_row") {
      onTabs({ tab: "compare", rowKey: action.rowKey, marks: false });
    } else if (action.type === "show_impact") {
      onTabs({ tab: "impact", impactRowKey: action.rowKey, impactItemId: action.itemId });
    } else if (action.type === "change_target") {
      if (onChangeTarget) onChangeTarget();
      else onTabs({ tab: "sources" });
    } else if (action.type === "check_plan") {
      await handleCheckPlan();
    } else if (action.type === "format_files") {
      await formatOnlyAction.run({});
      await store.load("applyPreview");
      await store.load("plan");
    }
  };

  if (planResource.error && !effectivePlan) {
    const copy = errorCopy(planResource.error);
    return (
      <div className="dc-plan-view">
        <Notice
          tone="bad"
          title={copy.title}
          actions={<Button variant="outline" size="sm" onClick={planResource.reload}>{t("shared.try_again")}</Button>}>
          {copy.body}
        </Notice>
      </div>
    );
  }

  if (!effectivePlan && planResource.loading) {
    return (
      <div className="dc-plan-view">
        <Skeleton lines={4} label={t("plan.check.loading")} />
      </div>
    );
  }

  const applyDisabled = strip.applyDisabled || changeDisabled;
  const applyDescId = strip.reason ? "dc-plan-apply-reason" : (changeDisabled ? reasonId : undefined);
  const stepCount = effectivePlan?.steps?.length ?? 0;
  const warnings = effectivePlan?.warnings ?? [];
  const openProposalsCount = session?.proposals?.open?.length ?? 0;
  const activeError = checkError || formatOnlyAction.error;
  const activeErrorCopy = activeError ? errorCopy(activeError) : null;

  return (
    <div className="dc-plan-view">
      <div className="sr-only" role="status" aria-live="polite">{announcement}</div>

      {activeErrorCopy ? (
        <Notice tone="bad" title={activeErrorCopy.title}>{activeErrorCopy.body}</Notice>
      ) : null}

      <section className="dc-plan-strip" aria-label="Plan status">
        <div className="dc-plan-strip-main">
          <StatusBadge tone={strip.badgeTone} label={strip.badgeLabel} />
          <span className="dc-plan-strip-body">{strip.body}</span>
        </div>
        <div className="dc-plan-strip-actions">
          {strip.reason ? (
            <span id="dc-plan-apply-reason" className="dc-plan-strip-reason">{strip.reason}</span>
          ) : null}
          <Button
            variant="outline"
            loading={isChecking}
            loadingText={t("plan.check.loading")}
            onClick={handleCheckPlan}>
            {t("plan.check")}
          </Button>
          <Button
            variant={strip.applyVariant}
            disabled={applyDisabled}
            aria-describedby={applyDescId}>
            {t("apply.action")}
          </Button>
        </div>
      </section>

      {blocks.length > 0 ? (
        <section className="dc-card dc-plan-blocks" aria-labelledby="dc-plan-blocks-title">
          <div className="dc-plan-blocks-head">
            <h2 id="dc-plan-blocks-title" className="dc-section-title">{t("plan.before_apply")}</h2>
            <span className="dc-plan-blocks-count dc-num">
              {blocks.length === 1
                ? "1 item stops the apply"
                : t("plan.before_apply.count", { n: blocks.length })}
            </span>
          </div>
          <ul className="dc-plan-block-list">
            {blocks.map((block) => {
              const Icon = block.icon === "warn" ? TriangleAlert : CircleX;
              return (
                <li key={block.id} className="dc-plan-block-row" data-block-kind={block.kind} data-block-category={block.category}>
                  <Icon
                    className={block.icon === "warn" ? "dc-plan-block-icon dc-tone-warn" : "dc-plan-block-icon dc-tone-bad"}
                    aria-hidden="true"
                  />
                  <div className="dc-plan-block-body">
                    <p className="dc-plan-block-text">{block.text}</p>
                    <p className="dc-plan-block-fix">{block.fix}</p>
                    {block.files?.length > 0 ? (
                      <ul className="dc-plan-block-files">
                        {block.files.map((file) => (
                          <li key={file} className="dc-mono">{file}</li>
                        ))}
                      </ul>
                    ) : null}
                  </div>
                  <div className="dc-plan-block-action">
                    <Button variant="outline" size="sm" onClick={() => handleBlockAction(block)}>
                      {block.actionLabel}
                    </Button>
                  </div>
                </li>
              );
            })}
          </ul>
        </section>
      ) : null}

      {stepCount === 0 && blocks.length === 0 ? (
        <EmptyState
          headingLevel={2}
          title={t("plan.empty.title")}
          action={<Button onClick={() => onTabs({ tab: "compare" })}>{t("plan.empty.action")}</Button>}>
          {t("plan.empty.body")}
        </EmptyState>
      ) : (
        <div className="dc-plan-grid">
          <div className="dc-plan-left">
            <section className="dc-card dc-plan-card" aria-labelledby="dc-plan-summary-title">
              <div className="dc-plan-card-head">
                <h2 id="dc-plan-summary-title" className="dc-section-title">{t("plan.summary")}</h2>
              </div>
              <table className="dc-table dc-plan-summary-table">
                <thead>
                  <tr>
                    <th scope="col">Type</th>
                    <th scope="col" className="dc-num">Created</th>
                    <th scope="col" className="dc-num">Deleted</th>
                    <th scope="col" className="dc-num">Modified</th>
                    <th scope="col" className="dc-num">Renamed</th>
                  </tr>
                </thead>
                <tbody>
                  <tr className="dc-plan-group-row">
                    <th colSpan={5} scope="colgroup">Model</th>
                  </tr>
                  {summary.modelRows.map((row) => (
                    <tr key={`model-${row.key}`}>
                      <td>{row.label}</td>
                      <td className={row.created === 0 ? "dc-num dc-plan-zero" : "dc-num"}>{row.created}</td>
                      <td className={row.deleted > 0 ? "dc-num dc-plan-del" : "dc-num dc-plan-zero"}>{row.deleted}</td>
                      <td className={row.modified === 0 ? "dc-num dc-plan-zero" : "dc-num"}>{row.modified}</td>
                      <td className={row.renamed === 0 ? "dc-num dc-plan-zero" : "dc-num"}>{row.renamed}</td>
                    </tr>
                  ))}
                  <tr className="dc-plan-group-row">
                    <th colSpan={5} scope="colgroup">Report</th>
                  </tr>
                  {summary.reportRows.map((row) => (
                    <tr key={`report-${row.key}`}>
                      <td>{row.label}</td>
                      <td className={row.created === 0 ? "dc-num dc-plan-zero" : "dc-num"}>{row.created}</td>
                      <td className={row.deleted > 0 ? "dc-num dc-plan-del" : "dc-num dc-plan-zero"}>{row.deleted}</td>
                      <td className={row.modified === 0 ? "dc-num dc-plan-zero" : "dc-num"}>{row.modified}</td>
                      <td className={row.renamed === 0 ? "dc-num dc-plan-zero" : "dc-num"}>{row.renamed}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>

            <section className="dc-card dc-plan-card" aria-labelledby="dc-plan-warnings-title">
              <div className="dc-plan-card-head">
                <h2 id="dc-plan-warnings-title" className="dc-section-title">{t("plan.warnings")}</h2>
                <span className="dc-muted dc-num">{warnings.length}</span>
              </div>
              {warnings.length === 0 ? (
                <p className="dc-muted dc-plan-card-empty">No warnings.</p>
              ) : (
                <ul className="dc-plan-warning-list">
                  {warnings.map((warning) => (
                    <li key={warning.item_id || warning.row_key} className="dc-plan-warning-row">
                      <TriangleAlert className="dc-plan-warning-icon dc-tone-warn" aria-hidden="true" />
                      <span>{formatWarningText(warning)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>

          <section className="dc-card dc-plan-card dc-plan-steps-card" aria-labelledby="dc-plan-steps-title">
            <div className="dc-plan-card-head dc-plan-steps-bar">
              <h2 id="dc-plan-steps-title" className="dc-section-title">{t("plan.steps")}</h2>
              <div className="dc-plan-steps-controls">
                <SegmentedControl
                  mode="radio"
                  aria-label="Filter steps by domain"
                  options={DOMAIN_OPTIONS}
                  value={domainFilter}
                  onValueChange={setDomainFilter}
                />
                <input
                  ref={searchRef}
                  type="search"
                  data-slot="input"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Filter steps by name"
                  aria-label="Filter steps by name"
                  aria-keyshortcuts="/"
                  className="ui-input h-8 w-full min-w-0 rounded-md px-2.5 text-[13px] outline-none placeholder:text-[var(--text-3)] disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-destructive dc-plan-search"
                />
              </div>
            </div>

            <div className="dc-plan-steps-scroll">
              {phases.length === 0 ? (
                <p className="dc-muted dc-plan-card-empty">No plan steps match this filter.</p>
              ) : (
                phases.map((phaseGroup) => (
                  <div key={phaseGroup.phase} className="dc-plan-phase" data-phase={phaseGroup.phase}>
                    <h3 className="dc-plan-phase-head">{phaseGroup.label}</h3>
                    <div className="dc-plan-phase-list">
                      {phaseGroup.items.map((item) => {
                        const isExpanded = expandedIds.has(item.id);
                        return (
                          <div key={item.id} className="dc-plan-step-row" data-step-id={item.stepId}>
                            <button
                              type="button"
                              className="dc-plan-step-btn"
                              aria-expanded={isExpanded}
                              onClick={() => toggleStep(item.id)}>
                              <ChevronRight
                                className={isExpanded ? "dc-plan-chev dc-plan-chev-open" : "dc-plan-chev"}
                                aria-hidden="true"
                              />
                              <span className="dc-plan-step-type">{item.typeLabel}</span>
                              <span className="dc-plan-step-name">{item.displayTitle}</span>
                              <span className="dc-plan-step-ops-count dc-num">
                                {item.opCount === 1 ? "1 op" : `${item.opCount} ops`}
                              </span>
                            </button>
                            {isExpanded ? (
                              <div className="dc-plan-step-ops">
                                {item.operations.map((op) => (
                                  <div key={op.opId} className="dc-plan-op">
                                    <div className="dc-plan-op-head">
                                      <span className="dc-mono dc-plan-op-kind">{op.op}</span>
                                      <span className="dc-mono dc-plan-op-target">{op.target}</span>
                                    </div>
                                    {op.oldLine !== null || op.newLine !== null ? (
                                      <pre className="dc-plan-op-diff dc-mono">
                                        {op.oldLine !== null ? (
                                          <span className="dc-plan-diff-old">{`- ${op.oldLine}\n`}</span>
                                        ) : null}
                                        {op.newLine !== null ? (
                                          <span className="dc-plan-diff-new">{`+ ${op.newLine}`}</span>
                                        ) : null}
                                      </pre>
                                    ) : null}
                                  </div>
                                ))}
                              </div>
                            ) : null}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ))
              )}
            </div>
          </section>
        </div>
      )}

      {openProposalsCount > 0 ? (
        <Notice
          tone="info"
          className="dc-plan-proposals-info"
          actions={
            <Button variant="outline" size="sm" onClick={() => onTabs({ tab: "agent" })}>
              {t("plan.proposals.action")}
            </Button>
          }>
          {openProposalsCount === 1
            ? "This plan uses accepted choices only. 1 agent proposal is open and is not in it."
            : t("plan.proposals", { n: openProposalsCount })}
        </Notice>
      ) : null}
    </div>
  );
}
