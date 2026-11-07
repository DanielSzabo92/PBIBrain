from __future__ import annotations

from dataclasses import asdict
from copy import deepcopy
from functools import wraps
import getpass
import json
from pathlib import Path
import tempfile
import uuid
from typing import Any

from backend.adapters.tabular_metadata import TabularMetadataAdapter
from backend.diff import compare_snapshots
from backend.impact import analyze_impact
from backend.impact.cache import SnapshotImpactCache
from backend.safety import assess_change
from backend.snapshots import Snapshot, capture_snapshot, source_manifest, content_hash
from backend.snapshots.manifest import safe_path, utc_now, SourceIntegrityError
from backend.snapshots.scan import scan_snapshot
from change_guard.audit import AuditStore
from change_guard.audit.records import exclusive_lock
from change_guard.contracts import ChangeContract, authorize_contract, validate_contract, enforce_scope
from change_guard.coverage import prove_tmdl_changes
from change_guard.merge import is_merge_contract, merge_impact, verify_merge_candidate, write_merge_files, write_record
from change_guard.policy import Policy, evaluate_candidate
from change_guard.promotion import LocalPromotion
from change_guard.regression import execute_regression_plan
from change_guard.workspace import create_candidate, assert_candidate_integrity, DockerIsolation, LocalCopyIsolation, LOCAL_COPY_BACKEND


class GuardError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def operation_locked(method):
    @wraps(method)
    def locked(self, operation_id, *args, **kwargs):
        uuid.UUID(operation_id)
        with exclusive_lock(safe_path(self.store.root, operation_id + "/operation.lock")):
            return method(self, operation_id, *args, **kwargs)
    return locked


def _empty_impact(snapshot: dict) -> dict:
    """Impact over no surviving targets: every target is new (preflight) or deleted (candidate).

    The analyzer needs at least one resolved object. A deletion's dependents are found by the
    baseline impact and by the safety report; there is nothing left to walk in the candidate.
    """
    completeness = dict(snapshot.get("completeness") or {"status": "UNKNOWN"})
    report = {"impact_report_version": 1, "baseline_snapshot_id": snapshot["snapshot_id"], "target_ids": [], "changed_properties": [],
              "direct_impacts": [], "potential_impacts": [], "conditional_impacts": [], "unknown_impacts": [], "affected_model_ids": [],
              "affected_report_ids": [], "impacted_objects": [], "impact_paths": [], "required_tests": [], "warnings": [], "evidence": [],
              "completeness": {**completeness, "status": "COMPLETE" if completeness.get("status") == "COMPLETE" else "INCOMPLETE",
                               "analysis_truncated": False, "output_truncated": False, "total_impact_records": 0}}
    report["impact_report_id"] = content_hash(report)
    return report


class ChangeGuard:
    """Trusted controller. The agent receives a candidate mount only.

    Neither this controller nor its credentials are exposed by Brain API/MCP.
    Missing isolation proof blocks acceptance even if semantic scope is valid.
    A LOCAL_COPY receipt (the no-container tier, issue #17) is proof of the weaker kind:
    the agent was given a copy, and the sources are checked against the pinned baseline.
    """
    def __init__(self, source_root: str | Path, state_root: str | Path, project_id: str, *, policy: Policy | None = None,
                 identity_manifest: dict | None = None, adapter: TabularMetadataAdapter | None = None,
                 allowed_principals: tuple[str, ...] | None = None, identity_path: str | Path | None = None) -> None:
        self.source_root, state_root = Path(source_root).absolute(), Path(state_root).absolute()
        if self.source_root.resolve().is_relative_to(state_root.resolve()) or state_root.resolve().is_relative_to(self.source_root.resolve()):
            raise SourceIntegrityError("Controller state and sources must be disjoint")
        self.project_id = project_id
        self.policy = policy or Policy()
        self.identity_path = Path(identity_path).absolute() if identity_path else None
        self.identities = deepcopy(identity_manifest or {"version": 1, "mappings": {}})
        self.adapter = adapter or TabularMetadataAdapter()
        self.allowed_principals = allowed_principals or (getpass.getuser(),)
        self.store = AuditStore(state_root)
        self.impact_cache = SnapshotImpactCache()

    def _identity_seed(self) -> dict:
        if self.identity_path:
            path = safe_path(self.identity_path.parent, self.identity_path.name, must_exist=True)
            value = json.loads(path.read_text(encoding="utf-8-sig"))
        else:
            value = deepcopy(self.identities)
        if not isinstance(value, dict) or value.get("version") != 1 or not isinstance(value.get("mappings"), dict):
            raise SourceIntegrityError("Identity seed is invalid")
        values = list(value["mappings"].values())
        if any(not isinstance(item, str) or not item for item in values) or len(set(values)) != len(values):
            raise SourceIntegrityError("Identity seed is invalid or colliding")
        return value

    def _baseline_matches(self, baseline: dict) -> bool:
        return source_manifest(self.source_root) == baseline["source_manifest"] and content_hash(self._identity_seed()) == baseline["configuration"]["identity_source_hash"]

    def _operation(self, operation_id: str) -> dict:
        uuid.UUID(operation_id)
        state = self.store.load(operation_id + "/state.json")
        self.store.read(operation_id)
        if state["policy_hash"] != self.policy.policy_hash or state["source_root"] != str(self.source_root) or state["project_id"] != self.project_id:
            raise GuardError("TRUST_BINDING_CHANGED", "Controller configuration changed")
        rejection_path = operation_id + "/user_rejection.json"
        if safe_path(self.store.root, rejection_path).exists():
            rejection = self.store.load(rejection_path)
            if rejection.get("operation_id") != operation_id:
                raise GuardError("TRUST_BINDING_CHANGED", "Rejection belongs to another operation")
            state.update(state="CANCELLED", user_decision="REJECTED", promotion_authorized=False, approvals=[],
                         decision={"decision": "REJECT", "eligible_for_promotion": False,
                                   "blocking_reasons": [{"code": "USER_REJECTED", "status": "REJECTED"}]})
        return state

    def _save(self, state: dict, event: str, evidence: dict) -> dict:
        self.store.append(state["operation_id"], event, evidence)
        state["updated_at"] = utc_now()
        self.store.save(state["operation_id"] + "/state.json", state)
        return state

    def _contract(self, state: dict) -> ChangeContract:
        if state.get("user_decision") == "REJECTED":
            raise GuardError("USER_REJECTED", "User rejected this change; prepare a new proposal")
        authorized = self.store.load(state["operation_id"] + "/contract.json")
        contract = ChangeContract(authorized["document"], authorized["authorization"])
        contract.authorization_record()
        if contract.contract_hash != state["contract_hash"]:
            raise GuardError("CONTRACT_CHANGED", "Contract hash mismatch")
        return contract

    def capture_baseline(self) -> Snapshot:
        manifest = source_manifest(self.source_root)
        seed = self._identity_seed()
        analysis = scan_snapshot(self.source_root, identities=seed, adapter=self.adapter)
        snapshot = capture_snapshot(self.source_root, self.project_id, configuration={"policy_hash": self.policy.policy_hash, "identity_source_hash": content_hash(seed)},
                                    identity_manifest=analysis["identity_manifest"], analysis=analysis)
        if snapshot.to_dict()["source_manifest"] != manifest or not self._baseline_matches(snapshot.to_dict()):
            raise GuardError("BASELINE_STALE", "Source changed during baseline capture")
        return snapshot

    def prepare_change(self, proposal: dict) -> dict:
        baseline = self.capture_baseline()
        snapshot = baseline.to_dict()
        contract = validate_contract(proposal, snapshot["analysis"]["objects"])
        if contract["project_id"] != self.project_id or contract["baseline"]["snapshot_id"] != baseline.snapshot_id or contract["baseline"]["source_revision"] != snapshot["source_revision"]:
            raise GuardError("BASELINE_MISMATCH", "Contract baseline does not match current sources")
        operation_id = str(uuid.uuid4())
        state = {"operation_id": operation_id, "state": "CREATED", "source_root": str(self.source_root), "project_id": self.project_id,
                 "policy_hash": self.policy.policy_hash, "policy_version": self.policy.version, "baseline_snapshot_id": baseline.snapshot_id,
                 "contract_hash": content_hash(contract), "attempt": 0, "approvals": [], "created_at": utc_now()}
        self._save(state, "CREATED", {"request_reference": contract["task_id"], "proposal_hash": content_hash(contract)})
        state["state"] = "RESOLVING_TARGETS"
        self._save(state, "TARGETS_RESOLVED", {"targets": contract["targets"]})
        self.store.save(operation_id + "/proposal.json", contract, exclusive=True)
        self.store.save(operation_id + "/baseline.json", snapshot, exclusive=True)
        baseline_root = self.store.root / operation_id / "baseline_sources"
        create_candidate(self.source_root, baseline_root, snapshot["source_manifest"])
        if is_merge_contract(contract):
            impact = merge_impact(contract, baseline.snapshot_id)
        else:
            changes = [{"object_id": item["object_id"], "property": item["property"], "new_value": item["expected_after"]} for item in contract["allowed_mutations"] if item["operation"] not in {"CREATE_OBJECT", "DELETE_OBJECT"}]
            existing = [item["object_id"] for item in contract["targets"] if item["object_id"] in snapshot["analysis"]["objects"]]
            impact = analyze_impact(snapshot["analysis"]["graph"], existing, changes, baseline_snapshot_id=baseline.snapshot_id,
                                    completeness=snapshot["completeness"]) if existing else _empty_impact(snapshot)
        self.store.save(operation_id + "/preflight.json", impact, exclusive=True)
        state["state"] = "PREFLIGHT"
        state["baseline_root"] = str(baseline_root)
        return self._save(state, "PREFLIGHT_COMPLETE", {"baseline_snapshot_id": baseline.snapshot_id, "impact_report_id": impact["impact_report_id"], "completeness": impact["completeness"], "contract_authorized": False})

    def authorize(self, operation_id: str, purpose: str) -> dict:
        principal = getpass.getuser()
        if principal not in self.allowed_principals:
            raise GuardError("PRINCIPAL_NOT_AUTHORIZED", "Current OS principal cannot authorize changes")
        with exclusive_lock(self.store.root / operation_id / "operation.lock"):
            state = self._operation(operation_id)
            baseline = Snapshot.from_dict(self.store.load(operation_id + "/baseline.json"))
            if not self._baseline_matches(baseline.to_dict()):
                state["state"] = "BASELINE_STALE"
                self._save(state, "BASELINE_STALE", {})
                raise GuardError("BASELINE_STALE", "Sources changed after preflight")
            if purpose == "CONTRACT":
                if state["state"] != "PREFLIGHT":
                    raise GuardError("INVALID_STAGE", "Contract authorization requires completed preflight")
                proposal = self.store.load(operation_id + "/proposal.json")
                contract = authorize_contract(proposal, principal, self.policy.version, objects=baseline.to_dict()["analysis"]["objects"])
                self.store.save(operation_id + "/contract.json", {"document": contract.document, "authorization": contract.authorization}, exclusive=True)
                state["state"] = "CONTRACT_AUTHORIZED"
                self._save(state, "CONTRACT_AUTHORIZED", contract.authorization_record())
                state["state"] = "BASELINE_CAPTURED"
                self._save(state, "BASELINE_PINNED", {"baseline_snapshot_id": baseline.snapshot_id})
                return self._create_candidate(state, baseline)
            if purpose not in {"HIGH_RISK_PROMOTION", "UNEXPECTED_BEHAVIOR", "UNCHECKED_IMPACT", "BREAKS_DEPENDENTS", "PROMOTE"}:
                raise GuardError("INVALID_APPROVAL_OPERATION", "Explicit approval purpose required")
            evidence = self.store.load(operation_id + "/verification.json")
            candidate = Snapshot.from_dict(self.store.load(operation_id + "/candidate.json"))
            if content_hash(assert_candidate_integrity(state["candidate_root"])) != state.get("candidate_hash"):
                raise GuardError("CANDIDATE_STALE", "Candidate changed after verification")
            # Human approval cannot override fundamental gates or failed evidence.
            decision = evaluate_candidate(self._contract(state), evidence, self.policy)
            if decision["blocking_reasons"]:
                raise GuardError("APPROVAL_CANNOT_BYPASS_GATES", "Candidate has blocking validation conditions")
            binding = self._record_approval(state, evidence, principal, purpose)
            state["decision"] = evaluate_candidate(self._contract(state), self._evidence_with_approvals(state, evidence), self.policy)
            state["state"] = "ELIGIBLE_FOR_PROMOTION" if state["decision"]["eligible_for_promotion"] else "APPROVAL_REQUIRED"
            if purpose == "PROMOTE":
                refreshed = self._evidence_with_approvals(state, evidence)
                decision = evaluate_candidate(self._contract(state), refreshed, self.policy)
                if not decision["eligible_for_promotion"]:
                    raise GuardError("MISSING_APPROVAL", "Required purpose-specific approvals missing")
                permit = {**binding, "operation_id": operation_id, "source_root": str(self.source_root), "candidate_root": state["candidate_root"],
                          "baseline_manifest": baseline.to_dict()["source_manifest"], "candidate_manifest": candidate.to_dict()["source_manifest"]}
                self.store.save(operation_id + "/promotion_authorization.json", permit)
                state["state"] = "ELIGIBLE_FOR_PROMOTION"
                state["decision"] = decision
                state["promotion_authorized"] = True
                self._save(state, "PROMOTION_AUTHORIZED", binding)
            else:
                self._save(state, "APPROVAL_EVALUATED", {"decision": state["decision"]})
            return state

    def _record_approval(self, state: dict, evidence: dict, principal: str, purpose: str) -> dict:
        binding = {"candidate_hash": state["candidate_hash"], "baseline_snapshot_id": state["baseline_snapshot_id"], "contract_hash": state["contract_hash"],
                   "policy_hash": self.policy.policy_hash, "evidence_hash": content_hash(evidence), "principal": principal,
                   "authorized_at": utc_now(), "authorized_operation": purpose}
        state["approvals"].append(binding)
        self.store.save(state["operation_id"] + "/approval-" + str(len(state["approvals"])) + ".json", binding, exclusive=True)
        self._save(state, "HUMAN_APPROVAL", binding)
        return binding

    def _review_binding(self, state: dict, evidence: dict | None) -> dict:
        return {"operation_id": state["operation_id"], "candidate_hash": state.get("candidate_hash"),
                "baseline_snapshot_id": state["baseline_snapshot_id"], "contract_hash": state["contract_hash"],
                "policy_hash": self.policy.policy_hash, "evidence_hash": content_hash(evidence) if evidence is not None else None}

    def _check_user_binding(self, state: dict, binding: dict) -> tuple[str, dict | None]:
        principal = getpass.getuser()
        if principal not in self.allowed_principals:
            raise GuardError("PRINCIPAL_NOT_AUTHORIZED", "Current OS principal cannot decide changes")
        path = state["operation_id"] + "/verification.json"
        evidence = self.store.load(path) if safe_path(self.store.root, path).exists() else None
        if not isinstance(binding, dict) or binding != self._review_binding(state, evidence):
            raise GuardError("REVIEW_STALE", "Proposal or verification changed; review it again")
        return principal, evidence

    @operation_locked
    def accept_candidate(self, operation_id: str, binding: dict, approval_operations: list[str]) -> dict:
        """Explicit user decision bound to the displayed candidate and evidence."""
        state = self._operation(operation_id)
        principal, evidence = self._check_user_binding(state, binding)
        if state["state"] not in {"APPROVAL_REQUIRED", "ELIGIBLE_FOR_PROMOTION"} or evidence is None:
            raise GuardError("INVALID_STAGE", "Acceptance requires a verified candidate")
        contract = self._contract(state)
        baseline = self.store.load(operation_id + "/baseline.json")
        if not self._baseline_matches(baseline):
            raise GuardError("BASELINE_STALE", "Sources changed after review")
        if content_hash(assert_candidate_integrity(state["candidate_root"])) != state.get("candidate_hash"):
            raise GuardError("CANDIDATE_STALE", "Candidate changed after review")
        decision = evaluate_candidate(contract, self._evidence_with_approvals(state, evidence), self.policy)
        if decision["blocking_reasons"]:
            raise GuardError("APPROVAL_CANNOT_BYPASS_GATES", "Candidate has blocking validation conditions")
        required = [*decision["approval_reasons"], "PROMOTE"]
        if not isinstance(approval_operations, list) or any(not isinstance(item, str) for item in approval_operations) or len(approval_operations) != len(set(approval_operations)) or set(approval_operations) != set(required):
            raise GuardError("MISSING_APPROVAL", "Accept the exact disclosed approval purposes")
        candidate = self.store.load(operation_id + "/candidate.json")
        for purpose in required:
            approval = self._record_approval(state, evidence, principal, purpose)
        state["decision"] = evaluate_candidate(contract, self._evidence_with_approvals(state, evidence), self.policy)
        if not state["decision"]["eligible_for_promotion"]:
            raise GuardError("MISSING_APPROVAL", "Required approvals missing")
        permit = {**approval, "operation_id": operation_id, "source_root": str(self.source_root), "candidate_root": state["candidate_root"],
                  "baseline_manifest": baseline["source_manifest"], "candidate_manifest": candidate["source_manifest"]}
        self.store.save(operation_id + "/promotion_authorization.json", permit)
        state.update(state="ELIGIBLE_FOR_PROMOTION", promotion_authorized=True, user_decision="ACCEPTED")
        return self._save(state, "USER_ACCEPTED", {**binding, "principal": principal, "approval_operations": required})

    @operation_locked
    def reject_change(self, operation_id: str, binding: dict) -> dict:
        """Cancel the proposal without touching original or candidate artifacts."""
        state = self._operation(operation_id)
        principal, _ = self._check_user_binding(state, binding)
        if state["state"] in {"PROMOTING", "PROMOTED", "POST_PROMOTION_VERIFIED", "PROMOTION_RECOVERY_REQUIRED"}:
            raise GuardError("INVALID_STAGE", "Applied changes require the recovery workflow")
        if state.get("user_decision") == "REJECTED":
            return state
        self.store.save(operation_id + "/user_rejection.json", {**binding, "principal": principal,
                        "user_decision": "REJECTED", "decided_at": utc_now()}, exclusive=True)
        state.update(state="CANCELLED", user_decision="REJECTED", promotion_authorized=False, approvals=[])
        state["decision"] = {"decision": "REJECT", "eligible_for_promotion": False,
                             "blocking_reasons": [{"code": "USER_REJECTED", "status": "REJECTED"}]}
        return self._save(state, "USER_REJECTED", {**binding, "principal": principal})

    def _create_candidate(self, state: dict, baseline: Snapshot) -> dict:
        if state["attempt"] >= self.policy.retry_limit:
            raise GuardError("RETRY_LIMIT", "Implementation retry limit reached")
        state["attempt"] += 1
        candidate_root = self.store.root / state["operation_id"] / ("candidate-" + str(state["attempt"]))
        create_candidate(state["baseline_root"], candidate_root, baseline.to_dict()["source_manifest"])
        state.update(state="CANDIDATE_READY", candidate_root=str(candidate_root), approvals=[], candidate_hash=None, promotion_authorized=False)
        return self._save(state, "CANDIDATE_READY", {"attempt": state["attempt"], "source_hash": content_hash(baseline.to_dict()["source_manifest"])})

    @operation_locked
    def retry(self, operation_id: str) -> dict:
        state = self._operation(operation_id)
        if state["state"] not in {"REJECTED", "VALIDATION_INCONCLUSIVE", "CANDIDATE_READY", "FAILED"}:
            raise GuardError("INVALID_STAGE", "Candidate cannot be retried in this stage")
        self._contract(state)
        baseline = Snapshot.from_dict(self.store.load(operation_id + "/baseline.json"))
        if not self._baseline_matches(baseline.to_dict()):
            raise GuardError("BASELINE_STALE", "Cannot retry a stale baseline")
        return self._create_candidate(state, baseline)

    @operation_locked
    def write_merge_candidate(self, operation_id: str, *, report_writer=None) -> dict:
        """App write step for a merge Change Plan (technical design section 8).

        The app writers produce the candidate files. The guard keeps an app write
        record that replaces the isolation receipt. A hash binds it to the contract.
        """
        state = self._operation(operation_id)
        contract = self._contract(state)
        if not is_merge_contract(contract.to_dict()) or self.policy.profile != "merge":
            raise GuardError("PROFILE_MISMATCH", "The app write step needs a merge contract and the merge policy")
        if state["state"] != "CANDIDATE_READY":
            raise GuardError("INVALID_STAGE", "The app write step requires a fresh authorized candidate")
        baseline = self.store.load(operation_id + "/baseline.json")
        state["state"] = "IMPLEMENTING"
        self._save(state, "APP_WRITE_STARTED", {"attempt": state["attempt"]})
        try:
            with tempfile.TemporaryDirectory(prefix="merge-write-") as work:
                files = write_merge_files(Path(state["baseline_root"]), Path(state["candidate_root"]), contract.to_dict()["merge"], self.adapter,
                                          Path(work), report_writer=report_writer)
        except Exception as error:
            state["state"] = "FAILED"
            self._save(state, "APP_WRITE_FAILED", {"error_type": type(error).__name__, "code": getattr(error, "code", None)})
            raise
        record = write_record(contract.contract_hash, baseline["source_manifest"], files)
        self.store.save(operation_id + "/write-record-" + str(state["attempt"]) + ".json", record, exclusive=True)
        return self._save(state, "APP_WRITE_RECORDED", {"record_hash": record["record_hash"], "file_count": len(files)})

    @operation_locked
    def record_local_edit(self, operation_id: str) -> dict:
        """The no-container tier for an agent that edits the candidate copy with its own tools.

        The agent (or a person) changed files under ``candidate_root``; this records a
        LOCAL_COPY receipt bound to the candidate as it is now. Verification follows as usual.
        """
        state = self._operation(operation_id)
        if is_merge_contract(self._contract(state).to_dict()):
            raise GuardError("PROFILE_MISMATCH", "An agent never writes a merge candidate; the app write step does")
        if state["state"] != "CANDIDATE_READY":
            raise GuardError("INVALID_STAGE", "A local edit requires a fresh authorized candidate")
        if not self.policy.allow_local_copy:
            raise GuardError("LOCAL_COPY_DISABLED", "The guard policy requires container isolation")
        receipt = LocalCopyIsolation().record(state["candidate_root"])
        state["state"] = "IMPLEMENTING"
        self._save(state, "IMPLEMENTING", {"attempt": state["attempt"], "backend": LOCAL_COPY_BACKEND})
        self.store.save(operation_id + "/isolation-" + str(state["attempt"]) + ".json", receipt, exclusive=True)
        return self._save(state, "AGENT_EXITED", receipt)

    @operation_locked
    def run_agent(self, operation_id: str, isolation: DockerIsolation | LocalCopyIsolation, command: list[str]) -> dict:
        state = self._operation(operation_id)
        if is_merge_contract(self._contract(state).to_dict()):
            raise GuardError("PROFILE_MISMATCH", "An agent never writes a merge candidate; the app write step does")
        if state["state"] != "CANDIDATE_READY":
            raise GuardError("INVALID_STAGE", "Agent implementation requires a fresh authorized candidate")
        if isinstance(isolation, LocalCopyIsolation) and not self.policy.allow_local_copy:
            raise GuardError("LOCAL_COPY_DISABLED", "The guard policy requires container isolation")
        state["state"] = "IMPLEMENTING"
        self._save(state, "IMPLEMENTING", {"attempt": state["attempt"]})
        try:
            from .workspace.windows import WindowsAppContainer
            if isinstance(isolation, WindowsAppContainer):
                receipt = isolation.run(state["candidate_root"], command, protected_roots=(self.source_root, self.store.root))
            else:
                receipt = isolation.run(state["candidate_root"], command)
            self.store.save(operation_id + "/isolation-" + str(state["attempt"]) + ".json", receipt, exclusive=True)
            return self._save(state, "AGENT_EXITED", receipt)
        except Exception as error:
            state["state"] = "FAILED"
            self._save(state, "AGENT_ISOLATION_FAILED", {"error_type": type(error).__name__})
            raise

    def validate_candidate(self, operation_id: str) -> dict:
        with exclusive_lock(self.store.root / operation_id / "operation.lock"):
            state = self._operation(operation_id)
            if state["state"] not in {"IMPLEMENTING", "CANDIDATE_READY", "REJECTED", "VALIDATION_INCONCLUSIVE", "APPROVAL_REQUIRED", "ELIGIBLE_FOR_PROMOTION", "STATIC_VALIDATION", "RUNTIME_VALIDATION", "POLICY_EVALUATION"}:
                raise GuardError("INVALID_STAGE", "Candidate cannot be validated in this stage")
            contract = self._contract(state)
            merge = is_merge_contract(contract.to_dict())
            if merge != (self.policy.profile == "merge"):
                raise GuardError("PROFILE_MISMATCH", "A merge contract needs the merge policy, and the merge policy needs a merge contract")
            baseline = Snapshot.from_dict(self.store.load(operation_id + "/baseline.json"))
            baseline_value = baseline.to_dict()
            if not self._baseline_matches(baseline_value) or source_manifest(state["baseline_root"]) != baseline_value["source_manifest"]:
                state["state"] = "BASELINE_STALE"
                self._save(state, "BASELINE_STALE", {})
                raise GuardError("BASELINE_STALE", "Pinned baseline or authoritative source changed")
            manifest = assert_candidate_integrity(state["candidate_root"])
            state["state"] = "STATIC_VALIDATION"
            self._save(state, "STATIC_VALIDATION_STARTED", {"candidate_source_hash": content_hash(manifest)})
            try:
                analyzed = scan_snapshot(state["candidate_root"], identities=baseline_value["identity_manifest"], adapter=self.adapter)
                candidate = capture_snapshot(state["candidate_root"], self.project_id, configuration=baseline_value["configuration"],
                                             identity_manifest=analyzed["identity_manifest"], kind="CANDIDATE", analysis=analyzed)
            except Exception as error:
                state["state"] = "REJECTED"
                evidence = {"source": {"status": "FAILED", "code": getattr(error, "code", "SOURCE_PARSE_FAILURE")}, "static": {"status": "NOT_RUN"}}
                self.store.save(operation_id + "/verification.json", evidence)
                state["decision"] = {"decision": "REJECT", "eligible_for_promotion": False, "blocking_reasons": [{"code": "SOURCE_INTEGRITY_FAILURE", "status": "FAILED"}]}
                state.update(candidate_hash=content_hash(manifest), candidate_snapshot_id=None)
                state["promotion_authorized"] = False
                self._save(state, "SOURCE_VALIDATION_FAILED", evidence)
                raise GuardError("SOURCE_INTEGRITY_FAILURE", "Candidate metadata verification failed") from error
            if manifest != source_manifest(state["candidate_root"]):
                raise GuardError("CANDIDATE_STALE", "Candidate changed during verification")
            merge_result = None
            if merge:
                # Merge: the app write record replaces the isolation receipt, and the merge proof replaces the line accounting.
                record_path = operation_id + "/write-record-" + str(state["attempt"]) + ".json"
                record = self.store.load(record_path) if safe_path(self.store.root, record_path).exists() else None
                merge_result = verify_merge_candidate(contract.to_dict(), contract.contract_hash, state["baseline_root"], state["candidate_root"], record, self.adapter)
                comparison = compare_snapshots(baseline, candidate, before_root=state["baseline_root"], after_root=state["candidate_root"],
                                               proven_sources=merge_result["proven_sources"])
                scope = merge_result["scope"]
                security = merge_result["security"]
            else:
                # Created, deleted and renamed TMDL blocks are proven by TOM regeneration (issue #17);
                # anything that proof does not cover still goes through the line check.
                tmdl_coverage = prove_tmdl_changes(state["baseline_root"], state["candidate_root"], self.adapter)
                comparison = compare_snapshots(baseline, candidate, before_root=state["baseline_root"], after_root=state["candidate_root"],
                                               proven_sources=tmdl_coverage["proven_sources"])
                scope = enforce_scope(contract, comparison)
                receipt_path = operation_id + "/isolation-" + str(state["attempt"]) + ".json"
                receipt = self.store.load(receipt_path) if safe_path(self.store.root, receipt_path).exists() else {"status": "NOT_RUN"}
                container = receipt.get("backend") == "DOCKER" or (receipt.get("backend") == "WINDOWS_APPCONTAINER" and receipt.get("token_is_appcontainer") is True and receipt.get("capability_count") == 0 and receipt.get("descendants_exited") is True and receipt.get("inherited_handles") is False)
                local_copy = receipt.get("backend") == LOCAL_COPY_BACKEND and self.policy.allow_local_copy
                isolated = container or local_copy
                security = {"status": "PASSED" if receipt.get("status") == "PASSED" and isolated and receipt.get("candidate_source_hash") == content_hash(manifest) else "NOT_RUN", "receipt_hash": content_hash(receipt)}
                if local_copy:
                    security["isolation_strength"] = "WEAKER_NO_CONTAINER"
                    security["backend"] = LOCAL_COPY_BACKEND
            targets = [item["object_id"] for item in contract.to_dict()["targets"] if item["object_id"] in baseline_value["analysis"]["objects"]]
            changes = [{"object_id": item["object_id"], "property": item["property_path"], "new_value": item["new_value"]} for item in comparison["property_changes"] if item["object_id"] in targets]
            if merge:
                impact = post_impact = merge_impact(contract.to_dict(), baseline.snapshot_id)
            else:
                impact = self.impact_cache.analyze(baseline, targets, changes) if targets else _empty_impact(baseline_value)
                surviving = [item for item in targets if item in analyzed["objects"]]
                post_impact = self.impact_cache.analyze(candidate, surviving) if surviving else _empty_impact(candidate.to_dict())
            # Candidate uncertainty is mandatory even if baseline impact was complete.
            if not merge and post_impact["completeness"]["status"] != "COMPLETE":
                impact["completeness"]["status"] = "INCOMPLETE"
                impact["unknown_impacts"].extend(post_impact["unknown_impacts"])
                impact["impact_report_id"] = content_hash({key: value for key, value in impact.items() if key not in {"impact_report_id", "metrics"}})
            source_passed = not comparison["unknown_differences"] and (merge_result is None or merge_result["source"]["status"] == "PASSED")
            source = {"status": "PASSED" if source_passed else "FAILED", **({"violations": merge_result["source"]["violations"]} if merge_result else {})}
            if not merge and tmdl_coverage["changed"]:
                source["tmdl_coverage"] = tmdl_coverage
            # The one safety report every write path shows (issue #17): changes, Breaks, Needs.
            safety = assess_change(baseline_value["analysis"]["graph"], analyzed["graph"])
            evidence = {"verification_version": 1, "security": security, "scope": {"status": scope["status"], **scope}, "baseline": {"status": "PASSED"},
                        "source": source, "safety": safety,
                        "static": {"status": analyzed["validation_status"], "validation": analyzed["validation"]},
                        "impact": impact, "post_impact": post_impact, "runtime": {"status": "NOT_RUN", "certified": False}, "comparison": comparison,
                        "candidate_hash": content_hash(manifest), "candidate_snapshot_id": candidate.snapshot_id, "baseline_snapshot_id": baseline.snapshot_id, "contract_hash": contract.contract_hash,
                        "policy_hash": self.policy.policy_hash}
            state.update(candidate_hash=content_hash(manifest), candidate_snapshot_id=candidate.snapshot_id, approvals=[])
            self.store.save(operation_id + "/candidate.json", candidate.to_dict())
            return self._evaluate_and_save(state, evidence)

    def _evidence_with_approvals(self, state: dict, evidence: dict) -> dict:
        digest = content_hash(evidence)
        valid = [item["authorized_operation"] for item in state["approvals"] if all(item.get(key) == expected for key, expected in
            (("candidate_hash", state["candidate_hash"]), ("baseline_snapshot_id", state["baseline_snapshot_id"]), ("contract_hash", state["contract_hash"]), ("policy_hash", self.policy.policy_hash), ("evidence_hash", digest)))]
        return {**evidence, "valid_approval_operations": valid}

    def _evaluate_and_save(self, state: dict, evidence: dict) -> dict:
        state["state"] = "POLICY_EVALUATION"
        state["promotion_authorized"] = False
        state.pop("user_decision", None)
        self.store.save(state["operation_id"] + "/verification.json", evidence)
        decision = evaluate_candidate(self._contract(state), self._evidence_with_approvals(state, evidence), self.policy)
        state["decision"] = decision
        state["state"] = {"REJECT": "REJECTED", "INCONCLUSIVE": "VALIDATION_INCONCLUSIVE", "APPROVAL_REQUIRED": "APPROVAL_REQUIRED", "ALLOW": "ELIGIBLE_FOR_PROMOTION"}[decision["decision"]]
        return self._save(state, "POLICY_DECISION", {"decision": decision, "evidence_hash": content_hash(evidence)})

    @operation_locked
    def execute_regression_plan(self, operation_id: str, tests: list, before_adapter: Any, after_adapter: Any, before_context: Any, after_context: Any) -> dict:
        state = self._operation(operation_id)
        self._contract(state)
        evidence = self.store.load(operation_id + "/verification.json")
        baseline = self.store.load(operation_id + "/baseline.json")
        if not self._baseline_matches(baseline):
            raise GuardError("BASELINE_STALE", "Baseline changed before runtime validation")
        if evidence.get("scope", {}).get("status") != "PASSED" or evidence.get("static", {}).get("status") != "PASSED":
            raise GuardError("STATIC_GATES_NOT_PASSED", "Static and scope gates must pass before runtime queries")
        if content_hash(assert_candidate_integrity(state["candidate_root"])) != state.get("candidate_hash"):
            raise GuardError("CANDIDATE_STALE", "Candidate changed after static validation")
        state["state"] = "RUNTIME_VALIDATION"
        self._save(state, "RUNTIME_VALIDATION_STARTED", {"tests": [test.test_id for test in tests]})
        evidence["runtime"] = execute_regression_plan(tests, before_adapter, after_adapter, before_context, after_context,
                    baseline_snapshot_id=state["baseline_snapshot_id"], candidate_snapshot_id=state["candidate_snapshot_id"], impact=evidence["impact"], retain_results=self.policy.retain_results,
                    baseline_graph=baseline["analysis"]["graph"], candidate_graph=self.store.load(operation_id + "/candidate.json")["analysis"]["graph"], static_verified=evidence["source"]["status"] == "PASSED" and evidence["static"]["status"] == "PASSED")
        if content_hash(assert_candidate_integrity(state["candidate_root"])) != state.get("candidate_hash") or not self._baseline_matches(baseline):
            state["state"] = "VALIDATION_INCONCLUSIVE"
            self._save(state, "SOURCES_CHANGED_DURING_RUNTIME", {})
            raise GuardError("VALIDATION_INPUT_CHANGED", "Runtime results invalidated by changed source")
        state["approvals"] = []
        return self._evaluate_and_save(state, evidence)

    @operation_locked
    def promote_candidate(self, operation_id: str, *, mode: str = "local", binding: dict | None = None) -> dict:
        if mode not in {"local", "git"}: raise GuardError("INVALID_PROMOTION_MODE", "Supported modes: local, git")
        state = self._operation(operation_id)
        if binding is not None:
            self._check_user_binding(state, binding)
        if state["state"] != "ELIGIBLE_FOR_PROMOTION":
            raise GuardError("PROMOTION_NOT_AUTHORIZED", "Candidate is not eligible for promotion")
        self._contract(state)
        baseline = self.store.load(operation_id + "/baseline.json")
        if not self._baseline_matches(baseline):
            state["state"] = "BASELINE_STALE"
            self._save(state, "BASELINE_STALE", {})
            raise GuardError("BASELINE_STALE", "Baseline changed before promotion")
        if content_hash(assert_candidate_integrity(state["candidate_root"])) != state["candidate_hash"]:
            raise GuardError("CANDIDATE_STALE", "Candidate changed before promotion")
        evidence = self.store.load(operation_id + "/verification.json")
        if not evaluate_candidate(self._contract(state), self._evidence_with_approvals(state, evidence), self.policy)["eligible_for_promotion"]:
            raise GuardError("PROMOTION_NOT_AUTHORIZED", "Verification or approval changed")
        permit = self.store.load(operation_id + "/promotion_authorization.json")
        if permit["evidence_hash"] != content_hash(evidence) or permit["candidate_hash"] != state["candidate_hash"] or permit["contract_hash"] != state["contract_hash"] or permit["policy_hash"] != self.policy.policy_hash:
            raise GuardError("AUTHORIZATION_STALE", "Promotion authorization no longer matches")
        state["state"] = "PROMOTING"
        self._save(state, "PROMOTING", {"authorization_hash": content_hash(permit)})
        try:
            if mode == "git":
                from .promotion.git import GitPromotion
                result = GitPromotion(self.store).promote(operation_id, self.store.sign(permit), baseline["source_revision"])
            else:
                result = LocalPromotion(self.store).promote(operation_id, self.store.sign(permit))
            state["promotion_mode"] = mode
            state["state"] = "PROMOTED"
            self._save(state, "PROMOTED", {"journal_status": result["status"]})
            baseline = self.store.load(operation_id + "/baseline.json")
            analyzed = scan_snapshot(self.source_root, identities=self.store.load(operation_id + "/candidate.json")["identity_manifest"], adapter=self.adapter)
            promoted = capture_snapshot(self.source_root, self.project_id, configuration=baseline["configuration"], identity_manifest=analyzed["identity_manifest"], kind="PROMOTED", analysis=analyzed)
            if promoted.snapshot_id != state["candidate_snapshot_id"]:
                raise GuardError("POST_PROMOTION_MISMATCH", "Promoted source identity differs from verified candidate")
            self.store.save(operation_id + "/promoted.json", promoted.to_dict(), exclusive=True)
            state["state"] = "POST_PROMOTION_VERIFIED"
            return self._save(state, "POST_PROMOTION_VERIFIED", {"promoted_snapshot_id": promoted.snapshot_id})
        except Exception as error:
            state["promotion_mode"] = mode
            journal_path = operation_id + "/promotion.json"
            if safe_path(self.store.root, journal_path).exists():
                LocalPromotion(self.store).require_recovery(operation_id, type(error).__name__)
            state["state"] = "PROMOTION_RECOVERY_REQUIRED"
            self._save(state, "PROMOTION_RECOVERY_REQUIRED", {"error_type": type(error).__name__})
            raise

    @operation_locked
    def recover_promotion(self, operation_id: str) -> dict:
        state = self._operation(operation_id)
        if state.get("promotion_mode") == "git":
            from .promotion.git import GitPromotion
            result = GitPromotion(self.store).recover(operation_id)
        else:
            result = LocalPromotion(self.store).recover(operation_id)
        state["state"] = "FAILED" if result["status"] == "RECOVERED" else "PROMOTED"
        return self._save(state, "RECOVERY_RESULT", {"journal_status": result["status"]})

    def candidate_status(self, operation_id: str) -> dict:
        return self._operation(operation_id)

    def review(self, operation_id: str) -> dict:
        state = self._operation(operation_id)
        path = operation_id + "/verification.json"
        baseline = self.store.load(operation_id + "/baseline.json")
        if state["state"] not in {"POST_PROMOTION_VERIFIED", "CANCELLED"} and not self._baseline_matches(baseline):
            state.update(state="BASELINE_STALE", promotion_authorized=False,
                         decision={"decision": "REJECT", "eligible_for_promotion": False, "blocking_reasons": [{"code": "BASELINE_STALE", "status": "FAILED"}]})
        if state["state"] != "CANCELLED" and state.get("candidate_hash") and content_hash(assert_candidate_integrity(state["candidate_root"])) != state["candidate_hash"]:
            state.update(state="VALIDATION_INCONCLUSIVE", promotion_authorized=False,
                         decision={"decision": "INCONCLUSIVE", "eligible_for_promotion": False, "blocking_reasons": [{"code": "CANDIDATE_STALE", "status": "INCONCLUSIVE"}]})
        verification = self.store.load(path) if safe_path(self.store.root, path).exists() else None
        return {"guard_review_version": 1, "operation": state, "preflight": self.store.load(operation_id + "/preflight.json"),
                 "contract": self.store.load(operation_id + "/proposal.json"),
                 "verification": verification if verification is not None else {"status": "NOT_RUN"},
                 "review_binding": self._review_binding(state, verification), "audit": self.store.read(operation_id)}
