import React, { useEffect, useRef, useState } from "react";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Card } from "./ui/card";
import { Badge } from "./ui/badge";
import { StatusBadge } from "./ui/status-badge";
import { Disclosure } from "./ui/collapsible";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogTrigger,
} from "./ui/dialog";
import BrandMark from "./BrandMark";
import { formatObjectRef } from "../presentation.js";
import { TriangleAlert } from "lucide-react";
import "../guard.css";

import {
  GUARD_PHRASES,
  explain,
  formatGuardObjectName,
  valueText,
  blockerLabel,
  propertyLabel,
  getVerdictMeta,
  getInitialOperationId,
} from "./guard-review-rules.js";

export default function GuardReview({ fetcher = globalThis.fetch }) {
  const token = useRef(new URLSearchParams(globalThis.location?.hash?.slice(1) || "").get("session") || "");
  const [operationId, setOperationId] = useState(getInitialOperationId);
  const [recentOperations, setRecentOperations] = useState(() => {
    try {
      const saved = localStorage.getItem("pbi-guard-recent-ops");
      return saved ? JSON.parse(saved) : [];
    } catch {
      return [];
    }
  });
  const [review, setReview] = useState(null);
  const [error, setError] = useState("");
  const [working, setWorking] = useState(false);
  const [acceptDialogOpen, setAcceptDialogOpen] = useState(false);
  const version = useRef(0);

  const request = async (action, payload, targetId) => {
    const op = targetId || operationId;
    const response = await fetcher(`/guard/${action}/${encodeURIComponent(op)}`, {
      method: payload ? "POST" : "GET",
      headers: {
        "Content-Type": "application/json",
        "X-PBI-Guard-Session": token.current,
      },
      body: payload ? JSON.stringify(payload) : undefined,
    });
    const value = await response.json();
    if (!response.ok || value.guard_api_version !== 1 || !value.ok) {
      throw new Error(value.error?.message || explain(value.error?.code));
    }
    return value.result;
  };

  const load = async (targetId) => {
    const op = targetId || operationId;
    if (!op) return;
    const current = ++version.current;
    setWorking(true);
    setError("");
    setReview(null);
    try {
      const result = await request("review", null, op);
      if (current === version.current) {
        setReview(result);
        setRecentOperations((prev) => {
          const next = [
            {
              id: op,
              timestamp: Date.now(),
              state: result?.operation?.state,
              summary: result?.contract?.intent?.description || "",
            },
            ...prev.filter((item) => item.id !== op),
          ].slice(0, 8);
          try {
            localStorage.setItem("pbi-guard-recent-ops", JSON.stringify(next));
          } catch {}
          return next;
        });
        try {
          const currentUrl = new URL(globalThis.location?.href || "");
          currentUrl.searchParams.set("op", op);
          globalThis.history.replaceState(null, "", currentUrl.toString());
        } catch {}
      }
    } catch (cause) {
      if (current === version.current) setError(cause.message);
    } finally {
      if (current === version.current) setWorking(false);
    }
  };

  const mutate = async (action, payload = {}) => {
    setWorking(true);
    setError("");
    try {
      await request(action, typeof payload === "string" ? { purpose: payload } : payload);
      if (action === "accept") await request("promote", { binding: payload.binding });
      const freshReview = await request("review");
      setReview(freshReview);
      setRecentOperations((prev) => {
        const next = prev.map((item) =>
          item.id === operationId
            ? { ...item, state: freshReview?.operation?.state }
            : item
        );
        try {
          localStorage.setItem("pbi-guard-recent-ops", JSON.stringify(next));
        } catch {}
        return next;
      });
    } catch (cause) {
      setReview(null);
      setError(cause.message);
    } finally {
      setWorking(false);
    }
  };

  useEffect(() => {
    const initialOp = getInitialOperationId();
    if (initialOp) {
      load(initialOp);
    }
    if (globalThis.location?.hash?.includes("session=")) {
      try {
        const cleanSearch = globalThis.location.search || "";
        globalThis.history.replaceState(null, "", globalThis.location.pathname + cleanSearch);
      } catch {}
    }
  }, []);

  const operation = review?.operation || {};
  const verification = review?.verification || {};
  const decision = operation.decision || {};
  const contract = review?.contract || {};
  const records = [...(review?.preflight?.direct_impacts || []), ...(review?.preflight?.potential_impacts || [])];
  const names = new Map(records.map((item) => [item.object_id, item.name]));
  const violations = new Set((verification.scope?.violations || []).map((item) => `${item.change?.object_id}:${item.change?.property_path}`));
  const blocking = decision.blocking_reasons || [];
  const canApprove =
    review?.review_binding &&
    !working &&
    blocking.length === 0 &&
    Boolean(verification.candidate_hash) &&
    ["APPROVAL_REQUIRED", "ELIGIBLE_FOR_PROMOTION"].includes(operation.state);
  const canReject =
    review?.review_binding &&
    !working &&
    !["CANCELLED", "PROMOTING", "PROMOTED", "POST_PROMOTION_VERIFIED", "PROMOTION_RECOVERY_REQUIRED"].includes(operation.state);
  const {
    heading: verdictHeading,
    tone: statusBadgeTone,
    label: statusBadgeLabel,
    rejected,
  } = getVerdictMeta({ operation, canApprove });

  const impactReasons = [
    ...new Set(
      (verification.impact?.unknown_impacts || review?.preflight?.unknown_impacts || []).map(
        (item) => item.reason
      )
    ),
  ];

  return (
    <div className="guard-shell app-shell">
      <header className="app-titlebar guard-titlebar">
        <span className="app-titlebar-brand" aria-hidden="true">
          <BrandMark size={18} />
        </span>
        <span className="guard-titlebar-title">PBIBrain Change Guard</span>
        <span className="app-titlebar-center">
          <span className="guard-titlebar-badge">Trusted Review</span>
        </span>
        <span className="app-titlebar-project" title="Operation Review">
          Guard Review
        </span>
      </header>
      <div className="guard-content-scroller" id="main-content">
        <main className="guard-review page page-wide">
          <header className="guard-header">
            <div className="guard-header-intro">
              <h1>Review proposed Power BI changes</h1>
              <p>Review the edits and their effects. You choose whether to accept or reject them.</p>
            </div>
            <form
              className="guard-fields guard-op-form"
              onSubmit={(event) => {
                event.preventDefault();
                load();
              }}
            >
              {recentOperations.length > 0 ? (
                <label className="guard-op-select-label">
                  <span>Recent operations</span>
                  <select
                    className="guard-select"
                    value={recentOperations.some((item) => item.id === operationId) ? operationId : ""}
                    disabled={working}
                    onChange={(event) => {
                      const next = event.target.value;
                      if (next) {
                        setOperationId(next);
                        load(next);
                      }
                    }}
                  >
                    <option value="" disabled>
                      Select recent operation…
                    </option>
                    {recentOperations.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.id.slice(0, 8)}… {item.summary ? `· ${item.summary}` : ""} {item.state ? `(${explain(item.state)})` : ""}
                      </option>
                    ))}
                  </select>
                </label>
              ) : null}
              <label className="guard-op-input-label">
                <span>Operation reference</span>
                <Input
                  value={operationId}
                  disabled={working}
                  onChange={(event) => {
                    version.current += 1;
                    setOperationId(event.target.value);
                    setReview(null);
                  }}
                  required
                />
              </label>
              <Button type="submit" disabled={working || !operationId}>
                {working ? "Loading…" : "Load candidate"}
              </Button>
            </form>
          </header>

          {error ? <p role="alert" className="inline-error">{error}</p> : null}

          {review ? (
            <div className="guard-stack">
              <Card className={`panel guard-verdict-card verdict-${statusBadgeTone}`}>
                <div className="guard-verdict-header">
                  <div className="guard-verdict-title-row">
                    <StatusBadge tone={statusBadgeTone} label={statusBadgeLabel} />
                    <h2>{verdictHeading}</h2>
                  </div>
                  <p className="guard-verdict-desc">
                    {rejected ? (
                      "Your project remains unchanged."
                    ) : (
                      <span className={operation.state === "CANDIDATE_READY" ? "guard-state-text capitalize" : "guard-state-text"}>
                        {explain(operation.state)}
                      </span>
                    )}
                  </p>
                </div>
                {blocking.length > 0 && !rejected ? (
                  <div className="guard-blockers-container">
                    <h3 className="guard-blockers-title">Required verification checks</h3>
                    <ul role="alert" className="guard-blockers-list">
                      {blocking.map((item, i) => (
                        <li key={i} className="guard-blocker-item">
                          <TriangleAlert className="guard-blocker-icon" aria-hidden="true" />
                          <span>
                            <strong>{blockerLabel(item)}</strong> · {explain(item.status)}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </Card>

              <Card className="panel">
                <div className="guard-card-header">
                  <h2>Proposed edits</h2>
                  {contract.intent?.type ? (
                    <Badge variant="outline">{explain(contract.intent?.type)}</Badge>
                  ) : null}
                </div>
                <p className="guard-panel-desc">{contract.intent?.description || "Proposal pending"}</p>
                <ul className="guard-edits-list">
                  {contract.allowed_mutations?.map((item, i) => (
                    <li key={i}>
                      <strong>{formatGuardObjectName(item.object_id, names)}</strong> · {propertyLabel(item.property)} · <span className="guard-diff-before">{valueText(item.expected_before, names)}</span> → <span className="guard-diff-after">{valueText(item.expected_after, names)}</span>
                    </li>
                  ))}
                </ul>
                {operation.state === "PREFLIGHT" ? (
                  <div className="guard-preflight-notice">
                    <p>Accepting this proposal allows work on a separate copy. Your project changes only after you accept the verified edits.</p>
                  </div>
                ) : null}
              </Card>

              <Card className="panel">
                <div className="guard-card-header">
                  <h2>Semantic differences</h2>
                  <span className="guard-meta-count">
                    {verification.comparison?.object_changes?.length || 0} {verification.comparison?.object_changes?.length === 1 ? "change" : "changes"}
                  </span>
                </div>
                <div className="guard-table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Object</th>
                        <th>Property</th>
                        <th>Original</th>
                        <th>Candidate</th>
                        <th>Permission</th>
                      </tr>
                    </thead>
                    <tbody>
                      {verification.comparison?.object_changes?.map((item, i) => (
                        <tr key={i}>
                          <td><strong>{formatGuardObjectName(item.object_id, names)}</strong></td>
                          <td>
                            {propertyLabel(item.property_path)}
                            <small>{explain(item.classification)}</small>
                          </td>
                          <td><span className="guard-diff-before">{valueText(item.previous_value, names)}</span></td>
                          <td><span className="guard-diff-after">{valueText(item.new_value, names)}</span></td>
                          <td>
                            <Badge variant={violations.has(`${item.object_id}:${item.property_path}`) ? "destructive" : verification.scope?.status === "PASSED" ? "secondary" : "outline"}>
                              {violations.has(`${item.object_id}:${item.property_path}`) ? "Unauthorized" : verification.scope?.status === "PASSED" ? "Authorized" : "Unverified"}
                            </Badge>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {((verification.comparison?.source_changes?.length || 0) > 0 || (verification.comparison?.unknown_differences?.length || 0) > 0) ? (
                  <Disclosure
                    title="Source coverage"
                    badge={`${(verification.comparison?.source_changes?.length || 0) + (verification.comparison?.unknown_differences?.length || 0)} files`}
                    className="guard-nested-disclosure"
                  >
                    <ul className="guard-disclosure-list">
                      {verification.comparison?.source_changes?.map((item) => (
                        <li key={item.source_file}>
                          <code>{item.source_file}</code> · {explain(item.classification)}
                        </li>
                      ))}
                    </ul>
                    {verification.comparison?.unknown_differences?.length ? (
                      <ul className="guard-disclosure-list">
                        {verification.comparison?.unknown_differences?.map((item, i) => (
                          <li key={i}>
                            <code>{item.source_file}</code> · {explain(item.reason)}
                          </li>
                        ))}
                      </ul>
                    ) : null}
                  </Disclosure>
                ) : null}
              </Card>

              <Card className="panel">
                <div className="guard-card-header">
                  <h2>Regression results</h2>
                  <StatusBadge
                    tone={verification.runtime?.certified ? "ok" : "warn"}
                    label={verification.runtime?.certified ? "Certified" : "Incomplete"}
                  />
                </div>
                <p className="guard-panel-desc">
                  {explain(verification.runtime?.status)} · {verification.runtime?.certified ? "Runtime evidence certified" : "Runtime evidence incomplete"}
                </p>
                <p className="guard-meta-info">
                  {verification.runtime?.tested_objects?.length || 0} objects tested · {verification.runtime?.uncovered_impact_paths?.length ?? "Unknown"} uncovered paths
                </p>
                <ul className="guard-regression-list">
                  {verification.runtime?.results?.map((test) => (
                    <li key={test.test_id} className="guard-regression-item">
                      <strong>{test.test_id} · {explain(test.status)}</strong>
                      {test.error ? <p className="guard-regression-error">{explain(test.error)}</p> : null}
                      {test.assertions?.length ? (
                        <ul>
                          {test.assertions.map((item, i) => (
                            <li key={i}>
                              {explain(item.code)}
                              {item.before !== undefined ? ` · ${valueText(item.before, names)} → ${valueText(item.after, names)}` : ""}
                              {item.delta ? ` · delta ${item.delta}` : ""}
                            </li>
                          ))}
                        </ul>
                      ) : null}
                    </li>
                  ))}
                </ul>
                <p className="guard-disclaimer">Untested contexts remain unverified.</p>
              </Card>

              <Card className="panel">
                <div className="guard-card-header">
                  <h2>Impact coverage</h2>
                  <StatusBadge
                    tone={verification.impact?.completeness?.status === "COMPLETE" ? "ok" : "warn"}
                    label={explain(verification.impact?.completeness?.status || review.preflight?.completeness?.status)}
                  />
                </div>
                <Disclosure
                  title="Impact coverage details"
                  badge={`${impactReasons.length} unknown`}
                  defaultOpen={impactReasons.length > 0}
                  className="guard-collapsible-card"
                >
                  <p className="guard-disclosure-status">
                    Status: <strong>{explain(verification.impact?.completeness?.status || review.preflight?.completeness?.status)}</strong>
                  </p>
                  {impactReasons.length > 0 ? (
                    <ul className="guard-disclosure-list">
                      {impactReasons.map((reason) => (
                        <li key={reason}>{explain(reason)}</li>
                      ))}
                    </ul>
                  ) : (
                    <p className="guard-disclosure-empty">No unverified impact paths recorded.</p>
                  )}
                </Disclosure>
              </Card>

              <Card className="panel">
                <h2>Your decision</h2>
                <p>Accept applies the exact verified changes shown above. Reject keeps your project unchanged.</p>
                {decision.approval_reasons?.includes("HIGH_RISK_PROMOTION") ? (
                  <p>This change affects model behavior. Accept also approves this disclosed risk.</p>
                ) : null}
                {decision.approval_reasons?.includes("UNEXPECTED_BEHAVIOR") ? (
                  <p>Accept also approves the behavior differences shown in the regression results.</p>
                ) : null}
                {!canApprove && !rejected && operation.state !== "POST_PROMOTION_VERIFIED" ? (
                  <p>Accept becomes available when all required checks pass.</p>
                ) : null}
              </Card>

              <Card className="panel">
                <div className="guard-card-header">
                  <h2>Audit history</h2>
                  <span className="guard-meta-count">{review.audit?.length || 0} events</span>
                </div>
                <Disclosure
                  title="Audit history details"
                  badge={`${review.audit?.length || 0} events`}
                  defaultOpen={false}
                  className="guard-collapsible-card"
                >
                  <ol className="guard-audit-list">
                    {review.audit?.map((item) => (
                      <li key={item.sequence}>
                        <span className="guard-audit-event">{explain(item.event)}</span>
                        <span className="guard-audit-time">{new Date(item.timestamp).toLocaleString()}</span>
                      </li>
                    ))}
                  </ol>
                </Disclosure>
              </Card>
            </div>
          ) : null}
        </main>
      </div>

      {review ? (
        <aside className="guard-sticky-bar" role="region" aria-label="Review actions">
          <div className="guard-sticky-content">
            <div className="guard-sticky-summary">
              <StatusBadge tone={statusBadgeTone} label={statusBadgeLabel} />
              <div className="guard-sticky-text">
                <strong>{verdictHeading}</strong>
                <span>
                  {rejected
                    ? "Your project remains unchanged."
                    : canApprove
                    ? "All automated checks passed · Ready to apply"
                    : operation.state === "POST_PROMOTION_VERIFIED"
                    ? "Changes verified in target model"
                    : operation.state === "PREFLIGHT"
                    ? "Proposal ready for workspace preparation"
                    : "Required checks incomplete"}
                </span>
              </div>
            </div>
            <div className="guard-sticky-actions guard-fields">
              {operation.state === "PREFLIGHT" ? (
                <>
                  <Button
                    disabled={working}
                    onClick={() => mutate("authorize", "CONTRACT")}
                  >
                    Accept proposal
                  </Button>
                  <Button
                    variant="outline"
                    disabled={!canReject}
                    onClick={() => mutate("reject", { binding: review.review_binding })}
                  >
                    Reject proposal
                  </Button>
                </>
              ) : (
                <>
                  <AlertDialog open={acceptDialogOpen} onOpenChange={setAcceptDialogOpen}>
                    <AlertDialogTrigger asChild>
                      <Button disabled={!canApprove}>Accept changes</Button>
                    </AlertDialogTrigger>
                    <AlertDialogContent
                      title="Accept and apply verified changes?"
                      description="Accepting applies the exact verified changes shown above directly to your Power BI project sources."
                      footer={
                        <>
                          <AlertDialogCancel>Cancel</AlertDialogCancel>
                          <AlertDialogAction asChild>
                            <Button
                              onClick={() => {
                                setAcceptDialogOpen(false);
                                mutate("accept", {
                                  binding: review.review_binding,
                                  approval_operations: [...(decision.approval_reasons || []), "PROMOTE"],
                                });
                              }}
                            >
                              Confirm and apply
                            </Button>
                          </AlertDialogAction>
                        </>
                      }
                    >
                      <div className="guard-dialog-details">
                        {decision.approval_reasons?.includes("HIGH_RISK_PROMOTION") ? (
                          <p className="guard-dialog-warning">
                            This change affects model behavior. Accept also approves this disclosed risk.
                          </p>
                        ) : null}
                        {decision.approval_reasons?.includes("UNEXPECTED_BEHAVIOR") ? (
                          <p className="guard-dialog-warning">
                            Accept also approves the behavior differences shown in the regression results.
                          </p>
                        ) : null}
                        <p>Once applied, your project sources will be updated with the verified candidate.</p>
                      </div>
                    </AlertDialogContent>
                  </AlertDialog>
                  <Button
                    variant="outline"
                    disabled={!canReject}
                    onClick={() => mutate("reject", { binding: review.review_binding })}
                  >
                    Reject changes
                  </Button>
                </>
              )}
            </div>
          </div>
        </aside>
      ) : null}
    </div>
  );
}
