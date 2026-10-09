"""Real Git/filesystem fault injection, with no external repositories."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import os
import sys
from backend.snapshots import source_manifest, content_hash
from change_guard.audit.records import AuditStore
from change_guard.audit.records import AuditIntegrityError
from change_guard.promotion.git import GitPromotion
from change_guard.promotion.local import PromotionError


class GitGuardPromotionTests(unittest.TestCase):
    def test_integrity_report_checks_signatures_chain_and_signed_head(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = AuditStore(Path(temporary) / "trusted")
            store.append("proof", "START", {"snapshot": "baseline"})
            store.append("proof", "FINISH", {"snapshot": "candidate"})
            verified = store.verify_integrity("proof")
            self.assertTrue(verified["integrity_verified"])
            self.assertEqual(verified["computed_tail_hash"], verified["head"]["last_hash"])
            self.assertEqual("FINISH", verified["terminal_event"])
            head = store.load("proof/audit-head.json")
            head["last_hash"] = "sha256:" + "0" * 64
            store.save("proof/audit-head.json", head)
            with self.assertRaises(AuditIntegrityError): store.verify_integrity("proof")

    def setup_operation(self, temporary):
        root = Path(temporary); source, candidate = root / "source", root / "candidate"
        source.mkdir(); candidate.mkdir()
        (source / "model.json").write_text('{"before":true}', encoding="utf-8")
        (candidate / "model.json").write_text('{"after":true}', encoding="utf-8")
        def git(*args): return subprocess.run(["git", "-C", str(source), *args], capture_output=True, text=True, check=True).stdout.strip()
        git("init"); git("config", "user.name", "Guard proof"); git("config", "user.email", "guard@localhost"); git("add", "."); git("commit", "-m", "Baseline")
        before = git("rev-parse", "HEAD")
        store = AuditStore(root / "trusted")
        manifest = source_manifest(candidate)
        permit = {"operation_id": "git-proof", "source_root": str(source), "candidate_root": str(candidate), "baseline_manifest": source_manifest(source), "candidate_manifest": manifest,
                  "candidate_hash": content_hash(manifest), "baseline_snapshot_id": "baseline", "contract_hash": "contract", "policy_hash": "policy", "evidence_hash": "evidence", "principal": "proof-controller", "authorized_operation": "PROMOTE"}
        return store, permit, before, git

    def test_verified_git_promotion_is_clean_and_preserves_parent_revision(self):
        with tempfile.TemporaryDirectory() as temporary:
            store, permit, before, git = self.setup_operation(temporary)
            result = GitPromotion(store).promote("git-proof", store.sign(permit), before)
            self.assertEqual("COMMITTED", result["status"])
            self.assertEqual(result["candidate_revision"], git("rev-parse", "HEAD"))
            self.assertEqual(before, git("rev-parse", "HEAD^"))
            self.assertEqual("", git("status", "--porcelain"))

    def test_recovery_after_each_git_write_survives_restart(self):
        for stage in ("SOURCES_APPLIED", "INDEX_APPLIED", "REF_APPLIED"):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as temporary:
                store, permit, before, git = self.setup_operation(temporary)
                def fault(point):
                    if point == stage: raise RuntimeError("Simulated interruption")
                with self.assertRaises(PromotionError): GitPromotion(store).promote("git-proof", store.sign(permit), before, fault=fault)
                restarted = AuditStore(store.root)
                result = GitPromotion(restarted).recover("git-proof")
                self.assertEqual("RECOVERED", result["status"])
                self.assertEqual(before, git("rev-parse", "HEAD"))
                self.assertEqual(permit["baseline_manifest"], source_manifest(permit["source_root"]))
                self.assertEqual("", git("status", "--porcelain"))

    def test_concurrent_staged_edit_blocks_recovery(self):
        with tempfile.TemporaryDirectory() as temporary:
            store, permit, before, git = self.setup_operation(temporary)
            def fault(stage):
                if stage == "INDEX_APPLIED": raise RuntimeError("Interruption")
            with self.assertRaises(PromotionError): GitPromotion(store).promote("git-proof", store.sign(permit), before, fault=fault)
            source = Path(permit["source_root"])
            (source / "human.json").write_text("{}", encoding="utf-8"); git("add", "human.json")
            with self.assertRaises(PromotionError): GitPromotion(store).recover("git-proof")
            self.assertTrue((source / "human.json").exists())

    @unittest.skipUnless(os.name == "nt", "Windows delete-on-close index lock proof")
    def test_abrupt_process_exit_releases_git_lock_and_recovers(self):
        for stage in ("SOURCES_APPLIED", "INDEX_APPLIED", "REF_APPLIED"):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as temporary:
                script = "from tests.test_git_guard_promotion import GitGuardPromotionTests; from change_guard.promotion.git import GitPromotion; import sys,os; store,permit,before,git=GitGuardPromotionTests().setup_operation(sys.argv[1]); GitPromotion(store).promote('git-proof',store.sign(permit),before,fault=lambda point: os._exit(99) if point==sys.argv[2] else None)"
                child = subprocess.run([sys.executable, "-I", "-c", script, temporary, stage], capture_output=True, text=True)
                # -I intentionally omits the checkout; use a trusted module
                # invocation with cwd instead, keeping the test data argument.
                if child.returncode != 99 and "ModuleNotFoundError" in child.stderr:
                    child = subprocess.run([sys.executable, "-c", script, temporary, stage], cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
                self.assertEqual(99, child.returncode, child.stderr)
                root = Path(temporary)
                self.assertFalse((root / "source/.git/index.lock").exists())
                store = AuditStore(root / "trusted")
                journal = store.load("git-proof/git-promotion.json")
                result = GitPromotion(store).recover("git-proof")
                self.assertEqual("RECOVERED", result["status"])
                current = subprocess.run(["git", "-C", str(root / "source"), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
                self.assertEqual(journal["baseline_revision"], current)
                self.assertTrue(store.verify_integrity("git-proof")["integrity_verified"])


if __name__ == "__main__": unittest.main()
