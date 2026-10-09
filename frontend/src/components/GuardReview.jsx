import React, { useEffect, useRef, useState } from "react";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Card } from "./ui/card";
import "../guard.css";

const explain = (value) => String(value || "Not run").replaceAll("_", " ").toLowerCase();
const valueText = (value, names) => typeof value === "string" ? names.get(value) || value : value == null ? "Blank" : typeof value === "object" ? JSON.stringify(value) : String(value);

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
  const mutate = async (action, purpose) => {
    setWorking(true); setError("");
    try { await request(action, purpose ? { purpose } : {}); setReview(await request("review")); }
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
  const canApprove = review && !working && blocking.length === 0 && Boolean(verification.candidate_hash) && ["APPROVAL_REQUIRED", "ELIGIBLE_FOR_PROMOTION"].includes(operation.state);
  return <main className="guard-review page page-wide">
    <header><p className="eyebrow">Independent Change Guard</p><h1>Candidate review</h1><p>Mutation permission, behavior acceptance, and promotion are separate decisions.</p></header>
    <form className="guard-fields" onSubmit={(event) => { event.preventDefault(); load(); }}><label>Operation reference<Input value={operationId} onChange={(event) => { version.current += 1; setOperationId(event.target.value); setReview(null); }} required /></label><Button type="submit" disabled={working || !operationId}>{working ? "Loading…" : "Load candidate"}</Button></form>
    {error ? <p role="alert" className="inline-error">{error}</p> : null}
    {review ? <div className="guard-stack">
      <Card className="panel"><h2>{operation.state === "POST_PROMOTION_VERIFIED" ? "Promoted and verified" : decision.eligible_for_promotion ? "Verified candidate requires promotion authorization" : "Promotion blocked"}</h2><p>{explain(operation.state)}</p>{blocking.length ? <ul role="alert">{blocking.map((item, i) => <li key={i}>{blockerLabel(item)} · {explain(item.status)}</li>)}</ul> : null}</Card>
      <Card className="panel"><h2>Mutation contract</h2><p>{contract.intent?.description || "Contract pending authorization"}</p><ul>{contract.allowed_mutations?.map((item, i) => <li key={i}>{names.get(item.object_id) || "Resolved target"} · {propertyLabel(item.property)} · {valueText(item.expected_before, names)} → {valueText(item.expected_after, names)}</li>)}</ul><Button disabled={working || operation.state !== "PREFLIGHT"} onClick={() => mutate("authorize", "CONTRACT")}>Authorize listed mutations</Button></Card>
      <Card className="panel"><h2>Semantic differences</h2><div className="guard-table-wrap"><table><thead><tr><th>Object</th><th>Property</th><th>Original</th><th>Candidate</th><th>Permission</th></tr></thead><tbody>{verification.comparison?.object_changes?.map((item, i) => <tr key={i}><td>{names.get(item.object_id) || explain(item.object_type)}</td><td>{propertyLabel(item.property_path)}<small>{explain(item.classification)}</small></td><td>{valueText(item.previous_value, names)}</td><td>{valueText(item.new_value, names)}</td><td>{violations.has(`${item.object_id}:${item.property_path}`) ? "Unauthorized" : verification.scope?.status === "PASSED" ? "Authorized" : "Unverified"}</td></tr>)}</tbody></table></div><details><summary>Source coverage</summary><ul>{verification.comparison?.source_changes?.map((item) => <li key={item.source_file}>{item.source_file} · {explain(item.classification)}</li>)}</ul><ul>{verification.comparison?.unknown_differences?.map((item, i) => <li key={i}>{item.source_file} · {item.reason}</li>)}</ul></details></Card>
      <Card className="panel"><h2>Regression results</h2><p>{explain(verification.runtime?.status)} · {verification.runtime?.certified ? "Runtime evidence certified" : "Runtime evidence incomplete"}</p><p>{verification.runtime?.tested_objects?.length || 0} objects tested · {verification.runtime?.uncovered_impact_paths?.length ?? "Unknown"} uncovered paths</p><ul>{verification.runtime?.results?.map((test) => <li key={test.test_id}><strong>{test.test_id} · {explain(test.status)}</strong>{test.error ? <p>{explain(test.error)}</p> : null}<ul>{test.assertions?.map((item, i) => <li key={i}>{explain(item.code)}{item.before !== undefined ? ` · ${valueText(item.before, names)} → ${valueText(item.after, names)}` : ""}{item.delta ? ` · delta ${item.delta}` : ""}</li>)}</ul></li>)}</ul><p>Untested contexts remain unverified.</p></Card>
      <Card className="panel"><h2>Impact coverage</h2><p>{explain(verification.impact?.completeness?.status || review.preflight?.completeness?.status)}</p><ul>{[...new Set((verification.impact?.unknown_impacts || review.preflight?.unknown_impacts || []).map((item) => item.reason))].map((reason) => <li key={reason}>{explain(reason)}</li>)}</ul></Card>
      <Card className="panel"><h2>Separate approvals</h2><p>These actions do not approve semantic assertions in PBIBrain’s Review Queue.</p><div className="guard-fields"><Button disabled={!canApprove || !decision.approval_reasons?.includes("UNEXPECTED_BEHAVIOR")} onClick={() => mutate("authorize", "UNEXPECTED_BEHAVIOR")}>Accept disclosed behavior differences</Button><Button disabled={!canApprove || !decision.approval_reasons?.includes("HIGH_RISK_PROMOTION")} onClick={() => mutate("authorize", "HIGH_RISK_PROMOTION")}>Approve high risk change</Button><Button disabled={!canApprove || decision.approval_reasons?.length > 0} onClick={() => mutate("authorize", "PROMOTE")}>Authorize verified promotion</Button><Button disabled={working || operation.state !== "ELIGIBLE_FOR_PROMOTION" || !operation.promotion_authorized} onClick={() => mutate("promote")}>Promote verified candidate</Button></div><p>Approvals bind this candidate, baseline, contract, policy, and evidence.</p></Card>
      <Card className="panel"><h2>Audit history</h2><ol>{review.audit?.map((item) => <li key={item.sequence}>{explain(item.event)} · {new Date(item.timestamp).toLocaleString()}</li>)}</ol></Card>
    </div> : null}
  </main>;
}
