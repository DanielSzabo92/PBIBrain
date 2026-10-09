from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Mapping

from backend.diff.snapshots import MISSING
from backend.snapshots.manifest import canonical_json, content_hash, utc_now

OPERATIONS = {"SET_PROPERTY", "CREATE_OBJECT", "DELETE_OBJECT", "RENAME_OBJECT", "REPLACE_EXPRESSION", "ADD_REFERENCE", "REMOVE_REFERENCE", "CHANGE_BINDING"}


class ContractError(ValueError):
    code = "INVALID_CONTRACT"


def _object(value: Any, required: set[str], optional: set[str] = frozenset()) -> dict[str, Any]:
    if not isinstance(value, dict) or not required.issubset(value) or set(value) - required - optional:
        raise ContractError("Missing or unknown schema fields")
    return value


def _text(value: Any) -> None:
    if not isinstance(value, str) or not value.strip() or any(character in value for character in "*?[]{}"):
        raise ContractError("Exact non-empty identifiers required; wildcards disabled")


def validate_contract(payload: Mapping[str, Any], objects: Mapping[str, Any] | None = None) -> dict[str, Any]:
    value = json.loads(canonical_json(dict(payload)))
    _object(value, {"contract_version", "task_id", "project_id", "baseline", "intent", "targets", "allowed_mutations", "forbidden", "behavior", "validation", "approval"})
    if type(value["contract_version"]) is not int or value["contract_version"] < 1:
        raise ContractError("Contract version must be a positive integer")
    for key in ("task_id", "project_id"):
        _text(value[key])
    baseline = _object(value["baseline"], {"snapshot_id", "source_revision"})
    _text(baseline["snapshot_id"])
    if baseline["source_revision"] is not None:
        _text(baseline["source_revision"])
    intent = _object(value["intent"], {"description", "category"})
    if not isinstance(intent["description"], str) or not intent["description"].strip():
        raise ContractError("Intent description required")
    _text(intent["category"])
    targets = value["targets"]
    if not isinstance(targets, list) or not targets:
        raise ContractError("Targets required")
    indexed = {}
    for target in targets:
        _object(target, {"object_id", "object_type"})
        _text(target["object_id"])
        _text(target["object_type"])
        if target["object_id"] in indexed:
            raise ContractError("Duplicate target")
        indexed[target["object_id"]] = target
    mutations = value["allowed_mutations"]
    if not isinstance(mutations, list) or not mutations:
        raise ContractError("Exact mutations required")
    keys = set()
    for mutation in mutations:
        _object(mutation, {"object_id", "operation", "property", "expected_before", "expected_after"})
        _text(mutation["property"])
        if mutation["object_id"] not in indexed or mutation["operation"] not in OPERATIONS:
            raise ContractError("Mutation target/operation invalid")
        marker = (mutation["object_id"], mutation["property"])
        if marker in keys:
            raise ContractError("Duplicate mutation")
        keys.add(marker)
        if mutation["operation"] in {"CREATE_OBJECT", "DELETE_OBJECT"} and mutation["property"] != "$object":
            raise ContractError("Object operations require an exact $object definition")
        if mutation["operation"] == "RENAME_OBJECT" and mutation["property"] != "name":
            raise ContractError("Rename may only change name")
        if mutation["operation"] == "REPLACE_EXPRESSION" and "expression" not in mutation["property"].casefold():
            raise ContractError("Expression operation requires an expression property")
        if objects is not None:
            obj = objects.get(mutation["object_id"])
            if mutation["operation"] == "CREATE_OBJECT":
                if obj is not None or mutation["expected_before"] != MISSING:
                    raise ContractError("Creation precondition invalid")
            else:
                if obj is None or obj["object_type"] != indexed[mutation["object_id"]]["object_type"]:
                    raise ContractError("Target is unresolved, ambiguous or wrong type")
                current: Any = dict(obj) if mutation["property"] == "$object" else obj["properties"]
                if mutation["property"] != "$object":
                    for part in mutation["property"].split("."):
                        if not isinstance(current, dict) or part not in current:
                            raise ContractError("Existing property value is unknown")
                        current = current[part]
                if canonical_json(current) != canonical_json(mutation["expected_before"]):
                    raise ContractError("Expected-before precondition mismatch")
    forbidden = _object(value["forbidden"], {"allow_unlisted_mutations", "allow_object_creation", "allow_object_deletion", "allow_identity_changes"})
    if any(type(item) is not bool for item in forbidden.values()) or forbidden["allow_unlisted_mutations"]:
        raise ContractError("Unlisted mutations are always forbidden")
    for operation, key in (("CREATE_OBJECT", "allow_object_creation"), ("DELETE_OBJECT", "allow_object_deletion")):
        if any(item["operation"] == operation for item in mutations) and not forbidden[key]:
            raise ContractError("Object operation contradicts forbidden policy")
    behavior = _object(value["behavior"], {"permitted_effects", "invariants"})
    for key in behavior:
        if not isinstance(behavior[key], list):
            raise ContractError("Behavior fields must be arrays")
    for effect in behavior["permitted_effects"]:
        _object(effect, {"category", "targets"})
        _text(effect["category"])
        if not isinstance(effect["targets"], list) or not effect["targets"]:
            raise ContractError("Effect requires explicit targets")
        for target in effect["targets"]:
            _text(target)
            if objects is not None and target not in objects and not any(item["object_id"] == target and item["operation"] == "CREATE_OBJECT" for item in mutations):
                raise ContractError("Behavior target is unresolved")
    for invariant in behavior["invariants"]:
        _object(invariant, {"id", "assertion"})
        _text(invariant["id"])
        if invariant["assertion"] != "PRESERVE":
            raise ContractError("Unsupported invariant assertion")
    validation = _object(value["validation"], {"require_static_validation", "require_runtime_validation", "require_impact_analysis", "require_complete_dependency_coverage"})
    if any(type(item) is not bool for item in validation.values()) or not validation["require_static_validation"]:
        raise ContractError("Static validation is mandatory")
    approval = _object(value["approval"], {"scope_expansion", "unexpected_behavior", "high_risk_promotion"})
    if any(item != "EXPLICIT" for item in approval.values()):
        raise ContractError("Approvals must be explicit")
    return value


@dataclass(frozen=True)
class ChangeContract:
    document: str
    authorization: str

    def to_dict(self) -> dict[str, Any]:
        return json.loads(self.document)

    @property
    def contract_hash(self) -> str:
        return content_hash(self.to_dict())

    def authorization_record(self) -> dict[str, Any]:
        record = json.loads(self.authorization)
        if record["contract_hash"] != self.contract_hash:
            raise ContractError("Authorized contract was altered")
        return record


def authorize_contract(payload: Mapping[str, Any], principal: str, policy_version: str, *, objects: Mapping[str, Any]) -> ChangeContract:
    _text(principal)
    _text(policy_version)
    contract = validate_contract(payload, objects)
    digest = content_hash(contract)
    authorization = {"contract_id": digest, "version": contract["contract_version"], "contract_hash": digest,
                     "baseline_snapshot_id": contract["baseline"]["snapshot_id"], "principal": principal, "authorized_at": utc_now(), "policy_version": policy_version}
    return ChangeContract(canonical_json(contract), canonical_json(authorization))


def enforce_scope(contract: ChangeContract, comparison: Mapping[str, Any]) -> dict[str, Any]:
    contract.authorization_record()
    payload = contract.to_dict()
    violations = []
    matched = set()
    for change in comparison.get("object_changes", []):
        key = (change["object_id"], change["property_path"])
        mutations = [item for item in payload["allowed_mutations"] if (item["object_id"], item["property"]) == key]
        target = next((item for item in payload["targets"] if item["object_id"] == change["object_id"]), None)
        allowed = len(mutations) == 1 and target is not None and target["object_type"] == change["object_type"]
        if allowed:
            mutation = mutations[0]
            expected_operation = {"OBJECT_CREATED": {"CREATE_OBJECT"}, "OBJECT_DELETED": {"DELETE_OBJECT"}, "OBJECT_RENAMED": {"RENAME_OBJECT", "SET_PROPERTY"},
                                  "REFERENCE_CHANGED": {"SET_PROPERTY", "ADD_REFERENCE", "REMOVE_REFERENCE", "CHANGE_BINDING"},
                                  "PROPERTY_CHANGED": {"SET_PROPERTY", "REPLACE_EXPRESSION"}, "IDENTITY_CHANGED": {"SET_PROPERTY"}}.get(change["classification"], set())
            allowed = mutation["operation"] in expected_operation and canonical_json(mutation["expected_before"]) == canonical_json(change["previous_value"]) and canonical_json(mutation["expected_after"]) == canonical_json(change["new_value"])
            if change["classification"] == "IDENTITY_CHANGED" and not payload["forbidden"]["allow_identity_changes"]:
                allowed = False
        if allowed:
            matched.add(key)
        else:
            violations.append({"code": "UNAUTHORIZED_MUTATION", "change": dict(change)})
    for mutation in payload["allowed_mutations"]:
        if (mutation["object_id"], mutation["property"]) not in matched and mutation["expected_before"] != mutation["expected_after"]:
            violations.append({"code": "REQUIRED_MUTATION_MISSING", "mutation": mutation})
    for unknown in comparison.get("unknown_differences", []):
        violations.append({"code": "UNINSPECTED_SOURCE_CHANGE", "change": dict(unknown)})
    if comparison.get("before_snapshot_id") != payload["baseline"]["snapshot_id"]:
        violations.append({"code": "BASELINE_MISMATCH"})
    if comparison.get("completeness", {}).get("status") != "COMPLETE":
        violations.append({"code": "COMPARISON_INCOMPLETE"})
    return {"scope_compliant": not violations, "status": "PASSED" if not violations else "REJECTED_SCOPE", "violations": violations}
