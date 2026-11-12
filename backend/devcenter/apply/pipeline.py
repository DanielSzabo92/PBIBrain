"""Write, guard, and promotion steps of a local apply (technical design section 13 steps 7 to 9).

``GuardPipeline`` runs the change guard for merge (section 8): the app write step
(bridge ``write-model`` and the PBIR writer) into a candidate folder, the guard
checks with the policy ``merge``, the approvals, and the journaled promotion with
a backup. Undo restores the backup of the promotion journal.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from collections.abc import Mapping, Sequence

from backend.devcenter.apply.steps import CANONICAL_CHECK, GUARD, PROMOTION, WRITE, ApplyFailure, guard_failure
from backend.snapshots.manifest import source_manifest
from change_guard.audit import AuditStore
from change_guard.promotion.local import LocalPromotion, PromotionError, file_hash


@dataclass
class ApplyJob:
    """The input of one apply run. The pipeline sets ``operation_id`` and ``files``."""

    apply_id: str
    kind: str
    project_id: str
    target_root: Path
    state_root: Path
    model_path: str | None
    report_path: str | None
    plan: Mapping[str, Any]
    donor_paths: Mapping[str, str] = field(default_factory=dict)
    unchecked_items: Sequence[Mapping[str, Any]] = ()
    approvals: Sequence[str] = ()
    operation_id: str | None = None
    files: list[str] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)

    @property
    def format_only(self) -> bool:
        return self.kind == "format_only"


class PromotionJournal:
    """Reads of the promotion journal and the undo. The same for each pipeline."""

    @staticmethod
    def _journal(state_root: Path, operation_id: str) -> dict[str, Any] | None:
        store = AuditStore(state_root)
        path = store.root / operation_id / "promotion.json"
        return store.load(operation_id + "/promotion.json") if path.is_file() else None

    def files_of(self, state_root: Path, operation_id: str) -> list[str]:
        journal = self._journal(state_root, operation_id)
        return sorted(item["path"] for item in journal["replacements"]) if journal else []

    def changed_files(self, state_root: Path, operation_id: str) -> list[str]:
        """Give each target file that is not as the apply (or the undo) left it."""

        journal = self._journal(state_root, operation_id)
        if journal is None:
            return []
        expected = {item["path"]: item["hash"] for item in journal["baseline_manifest" if journal.get("status") == "UNDONE" else "candidate_manifest"]}
        try:
            current = {item["path"]: item["hash"] for item in source_manifest(Path(journal["source_root"]))}
        except Exception:
            return sorted(expected)
        return sorted(path for path in set(expected) | set(current) if expected.get(path) != current.get(path))

    def backup_present(self, state_root: Path, operation_id: str) -> bool:
        try:
            journal = self._journal(state_root, operation_id)
        except Exception:
            return False
        if journal is None or journal.get("status") != "COMMITTED":
            return False
        root = Path(state_root)
        return all(item["before_hash"] is None or file_hash(root / item["backup"]) == item["before_hash"]
                   for item in journal["replacements"])

    def undo(self, state_root: Path, operation_id: str) -> list[str]:
        try:
            journal = LocalPromotion(AuditStore(state_root)).undo(operation_id)
        except PromotionError as exc:
            raise ApplyFailure(PROMOTION, "undo_failed", "The app could not restore the backup.", check="write") from exc
        return sorted(item["path"] for item in journal["replacements"])


def _names(items: Any) -> list[str]:
    names = []
    for item in items or []:
        value = item.get("path") or item.get("file") if isinstance(item, Mapping) else item
        if isinstance(value, str) and value:
            names.append(value.replace("\\", "/"))
    return names


def _violations(verification: Mapping[str, Any], decision: Mapping[str, Any]) -> list[dict[str, Any]]:
    found = []
    for gate in ("security", "source", "scope", "static"):
        block = verification.get(gate) if isinstance(verification, Mapping) else None
        for item in (block or {}).get("violations", []) if isinstance(block, Mapping) else []:
            if isinstance(item, Mapping):
                found.append({"code": item.get("code"), "gate": gate})
    for item in decision.get("blocking_reasons", []) or []:
        found.append({"code": item.get("code"), "gate": item.get("gate")})
    return found


class GuardPipeline(PromotionJournal):
    """The real pipeline: the change guard with the TOM bridge (Windows)."""

    def __init__(self, adapter: Any = None) -> None:
        self._adapter = adapter

    @property
    def adapter(self) -> Any:
        if self._adapter is None:
            from backend.adapters.tabular_metadata import TabularMetadataAdapter

            self._adapter = TabularMetadataAdapter()
        return self._adapter

    def canonical_files(self, job: ApplyJob) -> list[str]:
        """Step 4: each target model file that is not canonical TMDL, relative to the target root."""

        if not job.model_path:
            return []
        try:
            result = self.adapter.canonical_check(job.target_root / job.model_path)
        except Exception as exc:
            raise ApplyFailure(CANONICAL_CHECK, "canonical_check_failed", "The app could not check the format of the model files.",
                               check="canonical") from exc
        return sorted(job.model_path.rstrip("/") + "/" + name for name in _names(result.get("non_canonical_files")))

    def write(self, job: ApplyJob) -> None:
        """Step 7: the app write step into the guard candidate, with the app write record."""

        from change_guard.merge import build_merge_proposal
        from change_guard.orchestrator import ChangeGuard
        from change_guard.policy import merge_policy

        try:
            guard = ChangeGuard(job.target_root, job.state_root, job.project_id, policy=merge_policy(), adapter=self.adapter)
            baseline = guard.capture_baseline().to_dict()
            document = build_merge_proposal(
                job.target_root, job.plan, project_id=job.project_id, adapter=self.adapter,
                baseline={"snapshot_id": baseline["snapshot_id"], "source_revision": baseline["source_revision"]},
                model_path=job.model_path, report_path=job.report_path, donor_paths=dict(job.donor_paths),
                format_only=job.format_only, unchecked_items=list(job.unchecked_items), task_id="merge-" + job.apply_id)
            operation = guard.prepare_change(document)["operation_id"]
            guard.authorize(operation, "CONTRACT")
            guard.write_merge_candidate(operation)
        except Exception as exc:
            raise ApplyFailure(WRITE, "write_failed", "The app could not write the changed files.", check="write",
                               guard_codes=[str(getattr(exc, "code", None) or "APP_WRITE_FAILED")]) from exc
        job.context["guard"] = guard
        job.operation_id = operation

    def guard(self, job: ApplyJob) -> None:
        """Step 8: the guard checks, then the approvals of the one Apply dialog."""

        guard = job.context["guard"]
        operation = job.operation_id
        try:
            state = guard.validate_candidate(operation)
        except Exception as exc:
            raise guard_failure(GUARD, [{"code": getattr(exc, "code", None), "gate": "source"}],
                                "The guard did not accept the changed files.") from exc
        review = guard.review(operation)
        decision = state.get("decision") or {}
        if decision.get("decision") not in {"ALLOW", "APPROVAL_REQUIRED"}:
            raise guard_failure(GUARD, _violations(review.get("verification") or {}, decision),
                                "The guard did not accept the changed files.")
        required = list(decision.get("approval_reasons") or [])
        missing = sorted(set(required) - set(job.approvals))
        if missing:
            raise ApplyFailure(GUARD, "approval_missing", "The apply needs an approval that the user did not give.",
                               check="approval", purposes=missing)
        try:
            guard.accept_candidate(operation, review["review_binding"], [*required, "PROMOTE"])
        except Exception as exc:
            raise guard_failure(GUARD, [{"code": getattr(exc, "code", "MISSING_APPROVAL"), "gate": "policy"}],
                                "The guard did not accept the approval.") from exc

    def promote(self, job: ApplyJob) -> list[str]:
        """Step 9: backup, then all files or no file. A failure restores the backup."""

        guard = job.context["guard"]
        try:
            guard.promote_candidate(job.operation_id)
        except Exception as exc:
            code = str(getattr(exc, "code", None) or "PROMOTION_FAILED")
            try:
                guard.recover_promotion(job.operation_id)
                recovered = True
            except Exception:
                recovered = False
            raise ApplyFailure(PROMOTION, "promotion_failed", "The app could not write the files to the target. No file changed."
                               if recovered else "The app could not write the files to the target.",
                               check="rescan" if code == "POST_PROMOTION_MISMATCH" else "write",
                               recovered=recovered, guard_codes=[code]) from exc
        job.files = self.files_of(job.state_root, job.operation_id)
        return job.files
