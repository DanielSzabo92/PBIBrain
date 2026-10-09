"""Journaled multi-file replacement. Explicitly not a crash-atomic transaction."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Callable
from backend.snapshots.manifest import source_manifest, safe_path, content_hash, utc_now
from change_guard.audit.records import AuditStore, durable_write, exclusive_lock


class PromotionError(RuntimeError):
    code = "PROMOTION_RECOVERY_REQUIRED"


def file_hash(path: Path) -> str | None:
    return content_hash(path.read_bytes()) if path.is_file() else None


def verified_promotion_permit(store: AuditStore, operation_id: str, authorization: dict) -> dict:
    permit = store.verify(authorization)
    rejection = operation_id + "/user_rejection.json"
    if safe_path(store.root, rejection).exists():
        store.load(rejection)  # An invalid signature fails closed too.
        raise PromotionError("User rejected this change; cached authorization is revoked")
    return permit


class LocalPromotion:
    def __init__(self, store: AuditStore) -> None:
        self.store = store

    def promote(self, operation_id: str, authorization: dict, *, fault: Callable[[int], None] | None = None) -> dict:
        # Only a controller-signed authorization can reach filesystem writes.
        permit = verified_promotion_permit(self.store, operation_id, authorization)
        required = {"operation_id", "source_root", "candidate_root", "baseline_manifest", "candidate_manifest", "candidate_hash", "baseline_snapshot_id", "contract_hash", "policy_hash", "evidence_hash", "principal", "authorized_operation"}
        if not required.issubset(permit) or permit["operation_id"] != operation_id or permit["authorized_operation"] != "PROMOTE":
            raise PromotionError("Invalid promotion authorization")
        source, candidate = Path(permit["source_root"]), Path(permit["candidate_root"])
        if source.resolve().anchor.casefold() != self.store.root.resolve().anchor.casefold():
            raise PromotionError("Local staging must share the destination volume")
        lock_id = content_hash(str(source.resolve())).split(":")[1]
        with exclusive_lock(self.store.root / "locks" / (lock_id + ".lock")):
            if source_manifest(source) != permit["baseline_manifest"]:
                raise PromotionError("BASELINE_STALE")
            if source_manifest(candidate) != permit["candidate_manifest"] or content_hash(permit["candidate_manifest"]) != permit["candidate_hash"]:
                raise PromotionError("CANDIDATE_STALE")
            journal_path = operation_id + "/promotion.json"
            if safe_path(self.store.root, journal_path).exists():
                raise PromotionError("Existing promotion requires inspection/recovery")
            old = {item["path"]: item for item in permit["baseline_manifest"]}
            new = {item["path"]: item for item in permit["candidate_manifest"]}
            replacements = []
            for relative in sorted(set(old) | set(new)):
                if old.get(relative) == new.get(relative):
                    continue
                destination = safe_path(source, relative)
                backup = operation_id + "/backups/" + relative
                if relative in old:
                    data = destination.read_bytes()
                    if content_hash(data) != old[relative]["hash"]:
                        raise PromotionError("BASELINE_STALE")
                    durable_write(safe_path(self.store.root, backup), data, exclusive=True)
                replacements.append({"path": relative, "before_hash": old.get(relative, {}).get("hash"), "after_hash": new.get(relative, {}).get("hash"), "backup": backup, "state": "PREPARED"})
            journal = {"journal_version": 1, "operation_id": operation_id, "status": "PREPARED", "source_root": str(source),
                       "candidate_root": str(candidate), "baseline_manifest": permit["baseline_manifest"], "candidate_manifest": permit["candidate_manifest"],
                       "replacements": replacements, "authorization_hash": content_hash(authorization), "created_at": utc_now()}
            self.store.save(journal_path, journal, exclusive=True)
            self.store.append(operation_id, "PROMOTION_PREPARED", {"journal_hash": content_hash(journal)})
            try:
                for index, replacement in enumerate(replacements):
                    journal["status"] = "APPLYING"
                    replacement["state"] = "APPLYING"
                    self.store.save(journal_path, journal)
                    destination = safe_path(source, replacement["path"])
                    if file_hash(destination) != replacement["before_hash"]:
                        raise PromotionError("Concurrent destination modification")
                    if replacement["after_hash"] is None:
                        destination.unlink()
                    else:
                        data = safe_path(candidate, replacement["path"], must_exist=True).read_bytes()
                        if content_hash(data) != replacement["after_hash"]:
                            raise PromotionError("Candidate changed during promotion")
                        staging = safe_path(self.store.root, operation_id + "/staging/" + replacement["path"])
                        durable_write(destination, data, temporary_path=staging)
                    replacement["state"] = "APPLIED"
                    self.store.save(journal_path, journal)
                    if fault:
                        fault(index)
                if source_manifest(source) != permit["candidate_manifest"]:
                    raise PromotionError("Post-promotion source verification failed")
                journal["status"] = "COMMITTED"
                journal["verified_at"] = utc_now()
                self.store.save(journal_path, journal)
                self.store.append(operation_id, "PROMOTION_COMMITTED", {"source_hash": content_hash(source_manifest(source)), "authorization_hash": content_hash(authorization)})
                return journal
            except Exception as error:
                journal["status"] = "PROMOTION_RECOVERY_REQUIRED"
                journal["error_type"] = type(error).__name__
                self.store.save(journal_path, journal)
                self.store.append(operation_id, "PROMOTION_FAILED", {"error_type": type(error).__name__, "status": journal["status"]})
                # No more writes to sources. A separate recovery call verifies
                # all inputs and refuses to overwrite concurrent human edits.
                raise PromotionError("Promotion interrupted; verified recovery required") from error

    def require_recovery(self, operation_id: str, reason: str) -> None:
        journal_path = operation_id + "/promotion.json"
        journal = self.store.load(journal_path)
        journal.update(status="PROMOTION_RECOVERY_REQUIRED", recovery_reason=reason)
        self.store.save(journal_path, journal)
        self.store.append(operation_id, "POST_PROMOTION_RECOVERY_REQUIRED", {"reason": reason})

    def recover(self, operation_id: str) -> dict:
        journal_path = operation_id + "/promotion.json"
        journal = self.store.load(journal_path)
        source = Path(journal["source_root"])
        lock_id = content_hash(str(source.resolve())).split(":")[1]
        with exclusive_lock(self.store.root / "locks" / (lock_id + ".lock")):
            if journal["status"] == "COMMITTED":
                if source_manifest(source) != journal["candidate_manifest"]:
                    raise PromotionError("Committed source changed; rollback requires fresh authorization")
                return journal
            # Verify every backup and every current target before any write.
            previous = {item["path"]: item for item in journal["baseline_manifest"]}
            proposed = {item["path"]: item for item in journal["candidate_manifest"]}
            actual = {item["path"]: item for item in source_manifest(source)}
            if any(actual.get(path) not in (previous.get(path), proposed.get(path)) for path in set(previous) | set(proposed) | set(actual)):
                raise PromotionError("Concurrent project modification prevents recovery")
            for replacement in journal["replacements"]:
                destination = safe_path(source, replacement["path"])
                if file_hash(destination) not in {replacement["before_hash"], replacement["after_hash"]}:
                    raise PromotionError("Concurrent source edit prevents recovery")
                if replacement["before_hash"] is not None and file_hash(safe_path(self.store.root, replacement["backup"], must_exist=True)) != replacement["before_hash"]:
                    raise PromotionError("Recovery backup corrupted")
            try:
                for replacement in reversed(journal["replacements"]):
                    destination = safe_path(source, replacement["path"])
                    if replacement["before_hash"] is None:
                        if destination.exists():
                            destination.unlink()
                    else:
                        staging = safe_path(self.store.root, operation_id + "/staging/" + replacement["path"])
                        durable_write(destination, safe_path(self.store.root, replacement["backup"], must_exist=True).read_bytes(), temporary_path=staging)
                if source_manifest(source) != journal["baseline_manifest"]:
                    raise PromotionError("Recovered project does not match baseline")
                journal["status"] = "RECOVERED"
                journal["recovered_at"] = utc_now()
                self.store.save(journal_path, journal)
                self.store.append(operation_id, "RECOVERY_VERIFIED", {"source_hash": content_hash(source_manifest(source))})
                return journal
            except Exception as error:
                journal["status"] = "PROMOTION_RECOVERY_REQUIRED"
                self.store.save(journal_path, journal)
                raise PromotionError("Recovery incomplete") from error
