import assert from "node:assert/strict";
import test from "node:test";
import {
  explain,
  formatGuardObjectName,
  valueText,
  blockerLabel,
  propertyLabel,
  getVerdictMeta,
  GUARD_PHRASES,
} from "../src/components/guard-review-rules.js";
import { statusBadgeProps } from "../src/components/ui/status-badge-rules.js";

test("explain formats raw states into human readable phrases", () => {
  assert.equal(explain("REJECTED"), "Rejected");
  assert.equal(explain("rejected"), "Rejected");
  assert.equal(explain("NOT_RUN"), "Not run");
  assert.equal(explain("not_run"), "Not run");
  assert.equal(explain("PASSED"), "Passed");
  assert.equal(explain("passed"), "Passed");
  assert.equal(explain("FAILED"), "Failed");
  assert.equal(explain("failed"), "Failed");
  assert.equal(explain("APPROVAL_REQUIRED"), "Ready for your decision");
  assert.equal(explain("POST_PROMOTION_VERIFIED"), "Changes applied and verified");
  assert.equal(explain("PREFLIGHT"), "Proposal awaiting your decision");
  assert.equal(explain("ELIGIBLE_FOR_PROMOTION"), "Eligible for promotion");
  assert.equal(explain("REQUIRED_RUNTIME_NOT_VERIFIED"), "Required model tests incomplete");
  assert.equal(explain("MANDATORY_IMPACT_INCOMPLETE"), "Impact coverage incomplete");
  assert.equal(explain("SECURITY_VIOLATION"), "Security violation");
  assert.equal(explain("REFERENCE_CHANGED"), "Reference changed");
  assert.equal(explain("CONTRACT"), "Contract");
  assert.equal(explain("ALLOW"), "Allowed");
  assert.equal(explain("BLOCK"), "Blocked");
  assert.equal(explain("HIGH_RISK_PROMOTION"), "High risk promotion");
  assert.equal(explain("UNEXPECTED_BEHAVIOR"), "Behavior differences disclosed");
  assert.equal(explain("BREAKS_DEPENDENTS"), "Breaks dependent objects");
  assert.equal(explain("PROMOTE"), "Promotion");
  assert.equal(explain("CANDIDATE_READY"), "candidate ready");
});

test("explain sanitizes pbir schema unsupported strings", () => {
  assert.equal(explain("pbir_schema_unsupported"), "Unsupported report schema");
  assert.equal(explain("pbir schema unsupported"), "Unsupported report schema");
  assert.equal(
    explain("pbir schema unsupported: Sales Report/definition.pbir"),
    "Unsupported report schema in Sales Report"
  );
  assert.equal(
    explain("pbir_schema_unsupported: CustomerModel/page.json"),
    "Unsupported report schema in CustomerModel"
  );
});

test("explain formats relationship identifiers into clean human phrases", () => {
  assert.equal(explain("relationship-sales"), "Relationship (Sales)");
  assert.equal(explain("relationship-order-dates"), "Relationship (Order dates)");
});

test("explain capitalizes generic snake_case identifiers instead of raw lowercase", () => {
  assert.equal(explain("unauthorized_change"), "Unauthorized change");
  assert.equal(explain("uncovered_impact_path"), "Uncovered impact path");
  assert.equal(explain("runtime_error"), "Runtime error");
  assert.equal(explain(""), "Not run");
  assert.equal(explain(null), "Not run");
  assert.equal(explain(undefined), "Not run");
});

test("formatGuardObjectName formats relationship and object identifiers cleanly", () => {
  assert.equal(formatGuardObjectName("relationship-sales"), "Relationship (Sales)");
  assert.equal(formatGuardObjectName("table:Sales"), "'Sales'");
  assert.equal(formatGuardObjectName("measure:Sales/Amount"), "'Sales'[Amount]");
  assert.equal(formatGuardObjectName("column:Sales/Key"), "'Sales'[Key]");
  assert.equal(formatGuardObjectName(null), "Resolved target");
  assert.equal(formatGuardObjectName(""), "Resolved target");

  const names = new Map([["obj-1", "Total Revenue"]]);
  assert.equal(formatGuardObjectName("obj-1", names), "Total Revenue");
});

test("valueText formats blank, primitives, and objects without raw JSON leaking", () => {
  assert.equal(valueText(null), "Blank");
  assert.equal(valueText(undefined), "Blank");
  assert.equal(valueText(""), "Resolved target");
  assert.equal(valueText(42), "42");
  assert.equal(valueText(true), "true");
  assert.equal(valueText({ delta: 5 }), '{"delta":5}');

  const names = new Map([["key-1", "2026-01-01"]]);
  assert.equal(valueText("key-1", names), "2026-01-01");
});

test("blockerLabel provides humanized descriptions of guard blockers", () => {
  assert.equal(
    blockerLabel({ code: "SECURITY_VIOLATION", status: "NOT_RUN" }),
    "Sandbox verification missing"
  );
  assert.equal(
    blockerLabel({ code: "REQUIRED_RUNTIME_NOT_VERIFIED", status: "FAILED" }),
    "Required model tests incomplete"
  );
  assert.equal(
    blockerLabel({ code: "MANDATORY_IMPACT_INCOMPLETE", status: "FAILED" }),
    "Impact coverage incomplete"
  );
  assert.equal(
    blockerLabel({ code: "SECURITY_VIOLATION", status: "FAILED" }),
    "Security violation detected"
  );
  assert.equal(
    blockerLabel({ code: "CUSTOM_BLOCK", status: "FAILED" }),
    "Custom block"
  );
});

test("propertyLabel returns clean labels for Power BI relationship properties", () => {
  assert.equal(propertyLabel("from_column_id"), "Source column");
  assert.equal(propertyLabel("to_column_id"), "Target column");
  assert.equal(propertyLabel("active"), "Active relationship");
  assert.equal(propertyLabel("cross_filter_direction"), "Filter direction");
  assert.equal(propertyLabel("from_cardinality"), "Source cardinality");
  assert.equal(propertyLabel("to_cardinality"), "Target cardinality");
  assert.equal(propertyLabel("security_filter_behavior"), "Security filter direction");
  assert.equal(propertyLabel("custom_prop"), "Custom prop");
});

test("getVerdictMeta correctly resolves verdict heading, tone, and badge label", () => {
  // Rejected by user decision
  const v1 = getVerdictMeta({ operation: { user_decision: "REJECTED", state: "REJECTED" } });
  assert.equal(v1.heading, "Changes rejected");
  assert.equal(v1.tone, "bad");
  assert.equal(v1.label, "Rejected");
  assert.equal(v1.rejected, true);

  // Rejected by state alone
  const v2 = getVerdictMeta({ operation: { state: "REJECTED" } });
  assert.equal(v2.heading, "Changes rejected");
  assert.equal(v2.tone, "bad");
  assert.equal(v2.label, "Rejected");
  assert.equal(v2.rejected, true);

  // Post promotion verified
  const v3 = getVerdictMeta({ operation: { state: "POST_PROMOTION_VERIFIED" } });
  assert.equal(v3.heading, "Changes applied and verified");
  assert.equal(v3.tone, "ok");
  assert.equal(v3.label, "Verified and applied");

  // Ready for decision / canApprove
  const v4 = getVerdictMeta({ operation: { state: "ELIGIBLE_FOR_PROMOTION" }, canApprove: true });
  assert.equal(v4.heading, "Ready for your decision");
  assert.equal(v4.tone, "ok");
  assert.equal(v4.label, "Ready to accept");

  // Preflight proposal
  const v5 = getVerdictMeta({ operation: { state: "PREFLIGHT" } });
  assert.equal(v5.heading, "Proposal awaiting your decision");
  assert.equal(v5.tone, "proposal");
  assert.equal(v5.label, "Proposal awaiting decision");

  // Incomplete checks
  const v6 = getVerdictMeta({ operation: { state: "IMPLEMENTING" } });
  assert.equal(v6.heading, "Checks incomplete");
  assert.equal(v6.tone, "warn");
  assert.equal(v6.label, "Checks incomplete");
});

test("StatusBadge rules are satisfied by GuardReview verdict tones", () => {
  // All tones used in GuardReview must satisfy statusBadgeProps
  assert.doesNotThrow(() => statusBadgeProps({ tone: "ok", label: "Ready to accept" }));
  assert.doesNotThrow(() => statusBadgeProps({ tone: "bad", label: "Rejected" }));
  assert.doesNotThrow(() => statusBadgeProps({ tone: "warn", label: "Checks incomplete" }));
  assert.doesNotThrow(() => statusBadgeProps({ tone: "proposal", label: "Proposal awaiting decision" }));
  assert.doesNotThrow(() => statusBadgeProps({ tone: "ok", label: "Verified and applied" }));
});
