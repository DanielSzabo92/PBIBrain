from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping
from backend.snapshots.manifest import canonical_json, content_hash
from change_guard.contracts import ChangeContract


@dataclass(frozen=True)
class Policy:
    version: str = "guard-policy-1"
    # Serialized trusted configuration, never supplied from candidate artifacts.
    risk_overrides: str = "{}"
    retry_limit: int = 3
    retain_results: bool = False

    @property
    def policy_hash(self) -> str:
        return content_hash({"version": self.version, "risk_overrides": self.risk_overrides, "retry_limit": self.retry_limit, "retain_results": self.retain_results})


def classify_risk(contract: ChangeContract, policy: Policy) -> str:
    import json
    ranks = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
    overrides = json.loads(policy.risk_overrides)
    levels = []
    targets = {item["object_id"]: item["object_type"] for item in contract.to_dict()["targets"]}
    for mutation in contract.to_dict()["allowed_mutations"]:
        kind, prop = targets[mutation["object_id"]], mutation["property"]
        level = "MEDIUM"
        if prop in {"description", "display_folder"}:
            level = "LOW"
        if kind in {"RELATIONSHIP", "CALCULATION_GROUP", "CALCULATION_ITEM", "COLUMN", "TABLE"} and prop not in {"description", "display_folder"}:
            level = "HIGH"
        if kind in {"ROLE", "TABLE_PERMISSION", "OBJECT_LEVEL_SECURITY", "ROW_LEVEL_SECURITY"} or any(item in prop.casefold() for item in ("roles", "permission", "partition", "source", "storage", "security")):
            level = "CRITICAL"
        override = overrides.get(kind + ":" + prop, level)
        if override not in ranks:
            raise ValueError("Invalid risk policy")
        levels.append(override)
    return max(levels, key=ranks.get)


def evaluate_candidate(contract: ChangeContract, evidence: Mapping[str, Any], policy: Policy) -> dict[str, Any]:
    """Blocking precedence is independent of human/agent explanations."""
    payload = contract.to_dict()
    risk = classify_risk(contract, policy)
    reasons, approval_reasons = [], []
    gates = [("security", "SECURITY_VIOLATION"), ("scope", "UNAUTHORIZED_MUTATION"), ("baseline", "BASELINE_MISMATCH"),
             ("source", "SOURCE_INTEGRITY_FAILURE"), ("static", "STRUCTURAL_VALIDATION_FAILURE")]
    inconclusive = False
    for name, reason in gates:
        status = evidence.get(name, {}).get("status", "NOT_RUN")
        if status != "PASSED":
            reasons.append({"code": reason, "gate": name, "status": status})
            inconclusive |= status in {"NOT_RUN", "INCONCLUSIVE", "UNKNOWN"}
    runtime_required = payload["validation"]["require_runtime_validation"] or risk in {"HIGH", "CRITICAL"} or bool(payload["behavior"]["invariants"])
    runtime = evidence.get("runtime", {})
    if runtime_required and (runtime.get("status") != "PASSED" or not runtime.get("certified", False)):
        status = runtime.get("status", "NOT_RUN")
        reasons.append({"code": "REQUIRED_RUNTIME_NOT_VERIFIED", "gate": "runtime", "status": status})
        inconclusive |= status in {"NOT_RUN", "INCONCLUSIVE"} or not runtime.get("certified", False)
    if runtime.get("violated_invariants"):
        reasons.append({"code": "BEHAVIORAL_INVARIANT_VIOLATED", "gate": "regression", "status": "FAILED"})
    impact_required = payload["validation"]["require_impact_analysis"] or risk != "LOW"
    completeness_required = payload["validation"]["require_complete_dependency_coverage"] or risk in {"HIGH", "CRITICAL"}
    impact = evidence.get("impact", {})
    if impact_required and not impact.get("impact_report_id"):
        reasons.append({"code": "IMPACT_NOT_RUN", "gate": "impact", "status": "NOT_RUN"})
        inconclusive = True
    if completeness_required and (impact.get("completeness", {}).get("status") != "COMPLETE" or impact.get("completeness", {}).get("analysis_truncated") or impact.get("completeness", {}).get("output_truncated")):
        reasons.append({"code": "MANDATORY_IMPACT_INCOMPLETE", "gate": "impact", "status": "INCONCLUSIVE"})
        inconclusive = True
    if runtime_required and (runtime.get("uncovered_impact_paths") or runtime.get("missing_required_tests")):
        reasons.append({"code": "REGRESSION_COVERAGE_INCOMPLETE", "gate": "regression", "status": "INCONCLUSIVE"})
        inconclusive = True
    invariant_ids = {item["id"] for item in payload["behavior"]["invariants"]}
    if invariant_ids - set(runtime.get("verified_invariants", [])):
        reasons.append({"code": "INVARIANT_NOT_VERIFIED", "gate": "regression", "status": "INCONCLUSIVE"})
        inconclusive = True
    if risk in {"HIGH", "CRITICAL"}:
        approval_reasons.append("HIGH_RISK_PROMOTION")
    permitted_targets = {target for effect in payload["behavior"]["permitted_effects"] for target in effect["targets"]}
    undisclosed_changes = [item["test_id"] for item in runtime.get("results", []) if item.get("changed")
                           and not set(item.get("target_objects", [])).issubset(permitted_targets)]
    if runtime.get("unexplained_differences") or undisclosed_changes:
        approval_reasons.append("UNEXPECTED_BEHAVIOR")
    approved = set(evidence.get("valid_approval_operations", []))
    missing_approval = [item for item in approval_reasons if item not in approved]
    # Unknown gates never override an actual scope, security or invariant failure.
    hard_rejection = any(item["status"] in {"FAILED", "REJECTED_SCOPE"} for item in reasons)
    decision = "REJECT" if hard_rejection else "INCONCLUSIVE" if reasons else "APPROVAL_REQUIRED" if missing_approval else "ALLOW"
    return {"decision": decision, "scope_compliant": evidence.get("scope", {}).get("status") == "PASSED", "static_valid": evidence.get("static", {}).get("status") == "PASSED",
            "runtime_valid": runtime.get("status") == "PASSED" and runtime.get("certified", False), "regression_status": runtime.get("status", "NOT_RUN"),
            "impact_coverage": impact.get("completeness", {}).get("status", "UNKNOWN"), "risk": risk,
            "blocking_reasons": reasons, "approval_reasons": missing_approval, "eligible_for_promotion": decision == "ALLOW", "policy_version": policy.version, "policy_hash": policy.policy_hash}
