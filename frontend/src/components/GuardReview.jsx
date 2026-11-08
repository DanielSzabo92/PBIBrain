import React, { useEffect, useRef, useState } from "react";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Card } from "./ui/card";
import { formatObjectRef } from "../presentation.js";
import "../guard.css";

const GUARD_PHRASES = {
  PBIR_SCHEMA_UNSUPPORTED: "Unsupported report schema",
  PBIR_REQUIRED_ARTIFACT_MISSING: "Required report file missing",
  PBIR_PAGE_COVERAGE_MISMATCH: "Report page mismatch",
  PBIR_ACTIVE_PAGE_UNRESOLVED: "Active page not found",
  PBIR_PAGE_ID_PATH_MISMATCH: "Page ID path mismatch",
  PBIR_UNSUPPORTED_ARTIFACT: "Unsupported report item",
  PBIR_DYNAMIC_CONTEXT_UNSUPPORTED: "Dynamic report feature not supported",
  SCANNER_COVERAGE_UNKNOWN: "Scanner coverage unknown: metadata incomplete for this source",
  APPROVAL_REQUIRED: "Ready for your decision",
  ELIGIBLE_FOR_PROMOTION: "Eligible for promotion",
  POST_PROMOTION_VERIFIED: "Changes applied and verified",
  PREFLIGHT: "Proposal awaiting your decision",
  REQUIRED_RUNTIME_NOT_VERIFIED: "Required model tests incomplete",
  MANDATORY_IMPACT_INCOMPLETE: "Impact coverage incomplete",
  SECURITY_VIOLATION: "Security violation",
  REFERENCE_CHANGED: "Reference changed",
  PASSED: "Passed",
  FAILED: "Failed",
  NOT_RUN: "Not run",
  CONTRACT: "Contract",
};

const explain = (value) => {
  if (!value) return "Not run";
  const str = String(value).trim();
  const upper = str.toUpperCase();
  if (GUARD_PHRASES[upper]) return GUARD_PHRASES[upper];
  const pbirMatch = str.match(/^pbir[ _]schema[ _]unsupported(?::\s*(.*))?$/i);
  if (pbirMatch) {
    const reportPath = pbirMatch[1];
    if (reportPath) {
      const reportName = reportPath.split("/")[0] || reportPath;
      return `Unsupported report schema in ${reportName}`;
    }
    return "Unsupported report schema";
  }
  return str.replaceAll("_", " ").toLowerCase();
};

const formatGuardObjectName = (id, names) => {
  if (!id) return "Resolved target";
  const raw = names?.get(id) || id;
  if (typeof raw === "string") {
    if (raw.startsWith("relationship-")) {
      const clean = raw.slice("relationship-".length);
      const title = clean.charAt(0).toUpperCase() + clean.slice(1);
      return `Relationship: ${title} (${raw})`;
    }
    return formatObjectRef(raw);
  }
  return String(raw);
};

const valueText = (value, names) => typeof value === "string" ? (names?.get(value) || formatGuardObjectName(value, names)) : value == null ? "Blank" : typeof value === "object" ? JSON.stringify(value) : String(value);

export default function GuardReview({ fetcher = globalThis.fetch }) {
  const token = useRef(new URLSearchParams(globalThis.location?.hash?.slice(1) || "").get("session") || "");
  const [operationId, setOperationId] = useState("");
  const [review, setReview] = useState(null);
  const [error, setError] = useState("");
  const [working, setWorking] = useState(false);
  const version = useRef(0);
  useEffect(() => { if (globalThis.location?.hash) globalThis.history.replaceState(null, "", globalThis.location.pathname); }, []);
  const request = async (action, payload) => {
    const response = await fetcher(`/guard/${action}/${encodeURIComponent(operationId)}`, { method: payload ? "POST" : "GET", headers: { "Content-Type": "application/json", "X-PBI-Guard-Session": token.current }, body: payload ? JSON.stringify(payload) : undefined });
    const value = await response.json();
    if (!response.ok || value.guard_api_version !== 1 || !value.ok) throw new Error(value.error?.message || explain(value.error?.code));
    return value.result;
  };
  const load = async () => {
    const current = ++version.current; setWorking(true); setError(""); setReview(null);
    try { const result = await request("review"); if (current === version.current) setReview(result); }
    catch (cause) { if (current === version.current) setError(cause.message); }
    finally { if (current === version.current) setWorking(false); }
  };
  const mutate = async (action, payload = {}) => {
    setWorking(true); setError("");
    try {
      await request(action, typeof payload === "string" ? { purpose: payload } : payload);
      if (action === "accept") await request("promote", { binding: payload.binding });
      setReview(await request("review"));
    }
    catch (cause) { setReview(null); setError(cause.message); }
    finally { setWorking(false); }
  };
  const operation = review?.operation || {};
  const verification = review?.verification || {};
  const decision = operation.decision || {};
  const contract = review?.contract || {};
  const records = [...(review?.preflight?.direct_impacts || []), ...(review?.preflight?.potential_impacts || [])];
  const names = new Map(records.map((item) => [item.object_id, item.name]));
  const violations = new Set((verification.scope?.violations || []).map((item) => `${item.change?.object_id}:${item.change?.property_path}`));
  const blocking = decision.blocking_reasons || [];
  const propertyLabel = (value) => ({ from_column_id: "Source column", to_column_id: "Target column", active: "Active relationship", cross_filter_direction: "Filter direction", from_cardinality: "Source cardinality", to_cardinality: "Target cardinality", security_filter_behavior: "Security filter direction" }[value] || explain(value));
  const blockerLabel = (item) => item.code === "SECURITY_VIOLATION" && item.status === "NOT_RUN" ? "Sandbox verification missing" : ({ REQUIRED_RUNTIME_NOT_VERIFIED: "Required model tests incomplete", MANDATORY_IMPACT_INCOMPLETE: "Impact coverage incomplete" }[item.code] || explain(item.code));
  const canApprove = review?.review_binding && !working && blocking.length === 0 && Boolean(verification.candidate_hash) && ["APPROVAL_REQUIRED", "ELIGIBLE_FOR_PROMOTION"].includes(operation.state);
  const canReject = review?.review_binding && !working && !["CANCELLED", "PROMOTING", "PROMOTED", "POST_PROMOTION_VERIFIED", "PROMOTION_RECOVERY_REQUIRED"].includes(operation.state);
  const rejected = operation.user_decision === "REJECTED";
  return <main className="guard-review page page-wide">
    <header><h1>Review proposed Power BI changes</h1><p>Review the edits and their effects. You choose whether to accept or reject them.</p></header>
    <form className="guard-fields" onSubmit={(event) => { event.preventDefault(); load(); }}><label>Operation reference<Input value={operationId} disabled={working} onChange={(event) => { version.current += 1; setOperationId(event.target.value); setReview(null); }} required /></label><Button type="submit" disabled={working || !operationId}>{working ? "Loading…" : "Load candidate"}</Button></form>
    {error ? <p role="alert" className="inline-error">{error}</p> : null}
    {review ? <div className="guard-stack">
      <Card className="panel"><h2>{rejected ? "Changes rejected" : operation.state === "POST_PROMOTION_VERIFIED" ? "Changes applied and verified" : canApprove ? "Ready for your decision" : operation.state === "PREFLIGHT" ? "Proposal awaiting your decision" : "Checks incomplete"}</h2><p>{rejected ? "Your project remains unchanged." : explain(operation.state)}</p>{blocking.length && !rejected ? <ul role="alert">{blocking.map((item, i) => <li key={i}>{blockerLabel(item)} · {explain(item.status)}</li>)}</ul> : null}</Card>
      <Card className="panel"><h2>Proposed edits</h2><p>{contract.intent?.description || "Proposal pending"}</p><ul>{contract.allowed_mutations?.map((item, i) => <li key={i}>{formatGuardObjectName(item.object_id, names)} · {propertyLabel(item.property)} · {valueText(item.expected_before, names)} → {valueText(item.expected_after, names)}</li>)}</ul>{operation.state === "PREFLIGHT" ? <><p>Accepting this proposal allows work on a separate copy. Your project changes only after you accept the verified edits.</p><Button disabled={working} onClick={() => mutate("authorize", "CONTRACT")}>Accept proposal</Button></> : null}</Card>
      <Card className="panel"><h2>Semantic differences</h2><div className="guard-table-wrap"><table><thead><tr><th>Object</th><th>Property</th><th>Original</th><th>Candidate</th><th>Permission</th></tr></thead><tbody>{verification.comparison?.object_changes?.map((item, i) => <tr key={i}><td>{formatGuardObjectName(item.object_id, names)}</td><td>{propertyLabel(item.property_path)}<small>{explain(item.classification)}</small></td><td>{valueText(item.previous_value, names)}</td><td>{valueText(item.new_value, names)}</td><td>{violations.has(`${item.object_id}:${item.property_path}`) ? "Unauthorized" : verification.scope?.status === "PASSED" ? "Authorized" : "Unverified"}</td></tr>)}</tbody></table></div><details><summary>Source coverage</summary><ul>{verification.comparison?.source_changes?.map((item) => <li key={item.source_file}>{item.source_file} · {explain(item.classification)}</li>)}</ul><ul>{verification.comparison?.unknown_differences?.map((item, i) => <li key={i}>{item.source_file} · {explain(item.reason)}</li>)}</ul></details></Card>
      <Card className="panel"><h2>Regression results</h2><p>{explain(verification.runtime?.status)} · {verification.runtime?.certified ? "Runtime evidence certified" : "Runtime evidence incomplete"}</p><p>{verification.runtime?.tested_objects?.length || 0} objects tested · {verification.runtime?.uncovered_impact_paths?.length ?? "Unknown"} uncovered paths</p><ul>{verification.runtime?.results?.map((test) => <li key={test.test_id}><strong>{test.test_id} · {explain(test.status)}</strong>{test.error ? <p>{explain(test.error)}</p> : null}<ul>{test.assertions?.map((item, i) => <li key={i}>{explain(item.code)}{item.before !== undefined ? ` · ${valueText(item.before, names)} → ${valueText(item.after, names)}` : ""}{item.delta ? ` · delta ${item.delta}` : ""}</li>)}</ul></li>)}</ul><p>Untested contexts remain unverified.</p></Card>
      <Card className="panel"><h2>Impact coverage</h2><p>{explain(verification.impact?.completeness?.status || review.preflight?.completeness?.status)}</p><ul>{[...new Set((verification.impact?.unknown_impacts || review.preflight?.unknown_impacts || []).map((item) => item.reason))].map((reason) => <li key={reason}>{explain(reason)}</li>)}</ul></Card>
      <Card className="panel"><h2>Your decision</h2><p>Accept applies the exact verified changes shown above. Reject keeps your project unchanged.</p>{decision.approval_reasons?.includes("HIGH_RISK_PROMOTION") ? <p>This change affects model behavior. Accept also approves this disclosed risk.</p> : null}{decision.approval_reasons?.includes("UNEXPECTED_BEHAVIOR") ? <p>Accept also approves the behavior differences shown in the regression results.</p> : null}{!canApprove && !rejected && operation.state !== "POST_PROMOTION_VERIFIED" ? <p>Accept becomes available when all required checks pass.</p> : null}<div className="guard-fields">{operation.state !== "PREFLIGHT" ? <Button disabled={!canApprove} onClick={() => mutate("accept", { binding: review.review_binding, approval_operations: [...(decision.approval_reasons || []), "PROMOTE"] })}>Accept changes</Button> : null}<Button variant="outline" disabled={!canReject} onClick={() => mutate("reject", { binding: review.review_binding })}>{operation.state === "PREFLIGHT" ? "Reject proposal" : "Reject changes"}</Button></div></Card>
      <Card className="panel"><h2>Audit history</h2><ol>{review.audit?.map((item) => <li key={item.sequence}>{explain(item.event)} · {new Date(item.timestamp).toLocaleString()}</li>)}</ol></Card>
    </div> : null}
  </main>;
}
