"""Reviewable candidate revision, using a temporary index. No push/deployment."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
from contextlib import contextmanager
from backend.snapshots.manifest import safe_path, source_manifest, content_hash
from .local import PromotionError
from .local import LocalPromotion
from change_guard.audit.records import exclusive_lock


def create_review_revision(repository: str | Path, candidate: str | Path, baseline_revision: str,
                           baseline_manifest: list[dict], candidate_manifest: list[dict], operation_id: str) -> dict:
    repository, candidate = Path(repository).resolve(), Path(candidate).resolve()
    if source_manifest(repository) != baseline_manifest or source_manifest(candidate) != candidate_manifest:
        raise PromotionError("Pinned sources changed")
    if len(baseline_revision) != 40 or any(item not in "0123456789abcdef" for item in baseline_revision):
        raise PromotionError("Exact baseline revision required")
    with tempfile.TemporaryDirectory(prefix="pbi-guard-index-") as temporary:
        environment = dict(os.environ)
        environment["GIT_INDEX_FILE"] = str(Path(temporary) / "index")
        def git(*arguments: str, data: bytes | None = None) -> str:
            result = subprocess.run(["git", "-C", str(repository), *arguments], input=data, capture_output=True, env=environment, check=False)
            if result.returncode:
                raise PromotionError("Git candidate revision failed")
            return result.stdout.decode("utf-8").strip()
        if git("rev-parse", "HEAD") != baseline_revision:
            raise PromotionError("BASELINE_STALE")
        status = subprocess.run(["git", "-C", str(repository), "status", "--porcelain", "--untracked-files=all"], capture_output=True, check=True)
        if status.stdout.strip():
            raise PromotionError("Git promotion requires a clean authoritative project")
        git("read-tree", baseline_revision)
        before, after = {item["path"]: item for item in baseline_manifest}, {item["path"]: item for item in candidate_manifest}
        for relative in sorted(set(before) | set(after)):
            if before.get(relative) == after.get(relative):
                continue
            if relative not in after:
                git("update-index", "--force-remove", "--", relative)
            else:
                data = safe_path(candidate, relative, must_exist=True).read_bytes()
                if content_hash(data) != after[relative]["hash"]:
                    raise PromotionError("CANDIDATE_STALE")
                blob = git("hash-object", "-w", "--stdin", data=data)
                git("update-index", "--add", "--cacheinfo", "100644", blob, relative)
        tree = git("write-tree")
        revision = git("commit-tree", tree, "-p", baseline_revision, data=("Verified Power BI candidate " + operation_id + "\n").encode("utf-8"))
        reference = "refs/pbi-guard/" + operation_id
        git("update-ref", reference, revision, "0" * 40)
        if git("rev-parse", reference) != revision or git("rev-parse", "HEAD") != baseline_revision:
            raise PromotionError("Git reference verification failed")
        return {"status": "REVIEW_REVISION_CREATED", "baseline_revision": baseline_revision, "candidate_revision": revision, "reference": reference, "authoritative_promoted": False}


class GitPromotion:
    """Verified source replacement plus compare-and-swap of a pinned Git ref.

Files, index and ref are separate crash points recorded before each write.
Recovery refuses foreign commits, staged edits and modified backup contents.
"""
    def __init__(self, store):
        self.store = store

    @staticmethod
    def _git(root, *arguments, index_file=None):
        environment = dict(os.environ, GIT_OPTIONAL_LOCKS="0")
        if index_file is not None: environment["GIT_INDEX_FILE"] = str(index_file)
        result = subprocess.run(["git", "-C", str(root), *arguments], capture_output=True, text=True, env=environment, check=False)
        if result.returncode: raise PromotionError("Controlled Git operation failed")
        return result.stdout.strip()

    @contextmanager
    def _index_guard(self, root):
        directory = Path(self._git(root, "rev-parse", "--absolute-git-dir")).resolve()
        index = directory / "index"
        lock = directory / "index.lock"
        if index.is_symlink() or lock.is_symlink(): raise PromotionError("Unsafe Git index path")
        if os.name == "nt":
            import ctypes as c
            kernel = c.WinDLL("kernel32", use_last_error=True)
            kernel.CreateFileW.argtypes = [c.c_wchar_p, c.c_ulong, c.c_ulong, c.c_void_p, c.c_ulong, c.c_ulong, c.c_void_p]
            kernel.CreateFileW.restype = c.c_void_p
            kernel.CloseHandle.argtypes = [c.c_void_p]
            # Git respects this existing lock. Windows deletes our marker when
            # its handle closes, including an abrupt controller termination.
            handle = kernel.CreateFileW(str(lock), 0x40000000, 1, None, 1, 0x04000080, None)
            if handle == c.c_void_p(-1).value: raise PromotionError("Git index already locked")
            try: yield index
            finally: kernel.CloseHandle(handle)
        else:
            try: descriptor = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError as error: raise PromotionError("Git index already locked; inspect stale locks before recovery") from error
            try: yield index
            finally: os.close(descriptor); lock.unlink()

    def _index_tree(self, root, index):
        with tempfile.TemporaryDirectory(prefix="guard-index-check-") as temporary:
            copied = Path(temporary) / "index"
            copied.write_bytes(index.read_bytes())
            return self._git(root, "write-tree", index_file=copied)

    def _replace_index(self, root, index, revision):
        staging = index.parent / ("guard-index-" + os.urandom(16).hex())
        try:
            self._git(root, "read-tree", revision, index_file=staging)
            with staging.open("r+b") as stream: os.fsync(stream.fileno())
            os.replace(staging, index)
        finally:
            staging.unlink(missing_ok=True)

    def promote(self, operation_id, authorization, baseline_revision, *, fault=None):
        permit = self.store.verify(authorization)
        if permit.get("authorized_operation") != "PROMOTE" or permit.get("operation_id") != operation_id:
            raise PromotionError("Invalid Git promotion authorization")
        root = Path(permit["source_root"]).resolve()
        lock = content_hash(str(root)).split(":")[1] + "-git.lock"
        path = operation_id + "/git-promotion.json"
        with exclusive_lock(self.store.root / "locks" / lock):
            if safe_path(self.store.root, path).exists(): raise PromotionError("Existing Git promotion requires recovery")
            if Path(self._git(root, "rev-parse", "--show-toplevel")).resolve() != root:
                raise PromotionError("Git promotion requires the project at the repository root")
            branch = self._git(root, "symbolic-ref", "HEAD")
            journal = {"operation_id": operation_id, "source_root": str(root), "branch": branch, "baseline_revision": baseline_revision,
                       "candidate_revision": None, "baseline_source_hash": content_hash(permit["baseline_manifest"]),
                       "authorization_hash": content_hash(authorization), "status": "PREPARING_REVISION"}
            self.store.save(path, journal, exclusive=True)
            self.store.append(operation_id, "GIT_REVISION_PREPARATION", journal)
            try:
                revision = create_review_revision(root, permit["candidate_root"], baseline_revision, permit["baseline_manifest"], permit["candidate_manifest"], operation_id)
                journal.update(revision, status="PREPARED")
                self.store.save(path, journal); self.store.append(operation_id, "GIT_PROMOTION_PREPARED", journal)
                with self._index_guard(root) as index:
                    if self._index_tree(root, index) != self._git(root, "rev-parse", baseline_revision + "^{tree}"):
                        raise PromotionError("Concurrent staged modification")
                    LocalPromotion(self.store).promote(operation_id, authorization, fault=fault)
                    journal["status"] = "SOURCES_APPLIED"; self.store.save(path, journal)
                    if fault: fault("SOURCES_APPLIED")
                    if self._git(root, "symbolic-ref", "HEAD") != branch or self._git(root, "rev-parse", "HEAD") != baseline_revision:
                        raise PromotionError("BASELINE_STALE")
                    if source_manifest(root) != permit["candidate_manifest"]: raise PromotionError("Concurrent source modification")
                    journal["status"] = "UPDATING_INDEX"; self.store.save(path, journal)
                    self._replace_index(root, index, revision["candidate_revision"])
                    if fault: fault("INDEX_APPLIED")
                    journal["status"] = "UPDATING_REF"; self.store.save(path, journal)
                    self._git(root, "update-ref", branch, revision["candidate_revision"], baseline_revision)
                    if fault: fault("REF_APPLIED")
                    if source_manifest(root) != permit["candidate_manifest"] or self._git(root, "rev-parse", "HEAD") != revision["candidate_revision"] or self._git(root, "status", "--porcelain", "--untracked-files=all"):
                        raise PromotionError("Git promotion verification failed")
                    journal.update(status="COMMITTED", authoritative_promoted=True)
                    self.store.save(path, journal); self.store.append(operation_id, "GIT_PROMOTION_COMMITTED", journal)
                    return journal
            except Exception as error:
                journal.update(status="PROMOTION_RECOVERY_REQUIRED", error_type=type(error).__name__)
                self.store.save(path, journal)
                if safe_path(self.store.root, operation_id + "/promotion.json").exists():
                    LocalPromotion(self.store).require_recovery(operation_id, type(error).__name__)
                self.store.append(operation_id, "GIT_PROMOTION_FAILED", {"status": journal["status"]})
                raise PromotionError("Git promotion interrupted; verified recovery required") from error

    def recover(self, operation_id):
        path = operation_id + "/git-promotion.json"
        journal = self.store.load(path)
        root = Path(journal["source_root"]).resolve()
        lock = content_hash(str(root)).split(":")[1] + "-git.lock"
        with exclusive_lock(self.store.root / "locks" / lock), self._index_guard(root) as root_index:
            before, after = journal["baseline_revision"], journal["candidate_revision"]
            head = self._git(root, "rev-parse", "HEAD")
            if self._git(root, "symbolic-ref", "HEAD") != journal["branch"] or head not in {before, after}:
                raise PromotionError("Concurrent Git change prevents recovery")
            trees = {self._git(root, "rev-parse", revision + "^{tree}") for revision in (before, after) if revision}
            if self._index_tree(root, root_index) not in trees: raise PromotionError("Concurrent index edit prevents recovery")
            if not safe_path(self.store.root, operation_id + "/promotion.json").exists():
                if head != before or content_hash(source_manifest(root)) != journal["baseline_source_hash"]:
                    raise PromotionError("Unwritten source baseline changed")
                journal.update(status="RECOVERED", authoritative_promoted=False)
                self.store.save(path, journal); self.store.append(operation_id, "GIT_RECOVERY_VERIFIED", journal)
                return journal
            local = self.store.load(operation_id + "/promotion.json")
            if journal["status"] == "COMMITTED" and local["status"] == "COMMITTED":
                if head != after or source_manifest(root) != local["candidate_manifest"]: raise PromotionError("Committed Git state changed")
                return journal
            if safe_path(self.store.root, operation_id + "/promotion.json").exists():
                LocalPromotion(self.store).require_recovery(operation_id, "Git recovery")
                LocalPromotion(self.store).recover(operation_id)
            else:
                raise PromotionError("Source recovery journal missing")
            self._git(root, "update-ref", journal["branch"], before, head)
            self._replace_index(root, root_index, before)
            if self._git(root, "rev-parse", "HEAD") != before or self._git(root, "status", "--porcelain", "--untracked-files=all"):
                raise PromotionError("Git recovery verification failed")
            journal.update(status="RECOVERED", authoritative_promoted=False)
            self.store.save(path, journal); self.store.append(operation_id, "GIT_RECOVERY_VERIFIED", journal)
            return journal
