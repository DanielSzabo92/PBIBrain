"""User-decision integration: real TOM snapshots; unavailable proof stays blocked."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend.adapters.tabular_metadata import TabularMetadataAdapter
from backend.snapshots import source_manifest
from change_guard.orchestrator import ChangeGuard, GuardError
from change_guard.service import GuardService
from tests.guarded_fixture import reference_project
from tests.test_guarded_development import proposal, modify_bim


class UserDecisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not TabularMetadataAdapter().bridge.is_file():
            raise unittest.SkipTest("Build trusted TOM bridge for user-decision integration")

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.source = root / "source"
        reference_project(self.source)
        self.guard = ChangeGuard(self.source, root / "trusted", "user-review")
        self.before = source_manifest(self.source)
        baseline = self.guard.capture_baseline()
        self.state = self.guard.prepare_change(proposal(baseline))
        self.operation = self.state["operation_id"]
        self.service = GuardService(self.guard, "human-session", "http://127.0.0.1:8051")

    def candidate(self):
        state = self.guard.authorize(self.operation, "CONTRACT")
        candidate = Path(state["candidate_root"])
        modify_bim(candidate, lambda model: model["relationships"][0].update(fromColumn="ShipDateKey"))
        self.guard.validate_candidate(self.operation)
        return candidate

    def test_preflight_is_reviewable_and_reject_changes_no_sources(self):
        review = self.guard.review(self.operation)
        self.assertEqual("PREFLIGHT", review["operation"]["state"])
        self.assertTrue(review["contract"]["allowed_mutations"])
        self.assertEqual(self.before, source_manifest(self.source))
        status, result = self.service.handle("POST", "/guard/reject/" + self.operation,
                                            {"binding": review["review_binding"]}, token="human-session")
        self.assertEqual(200, status, result)
        self.assertEqual("REJECTED", result["result"]["user_decision"])
        self.assertEqual("CANCELLED", result["result"]["state"])
        self.assertFalse(result["result"]["promotion_authorized"])
        self.assertEqual(self.before, source_manifest(self.source))
        self.assertTrue(self.guard.store.verify_integrity(self.operation)["integrity_verified"])

    def test_rejection_cannot_be_revived_by_old_mutating_methods(self):
        self.candidate()
        review = self.guard.review(self.operation)
        self.guard.reject_change(self.operation, review["review_binding"])
        actions = [lambda: self.guard.authorize(self.operation, "PROMOTE"),
                   lambda: self.guard.authorize(self.operation, "CONTRACT"),
                   lambda: self.guard.validate_candidate(self.operation), lambda: self.guard.retry(self.operation),
                   lambda: self.guard.execute_regression_plan(self.operation, [], None, None, None, None),
                   lambda: self.guard.promote_candidate(self.operation),
                   lambda: self.guard.accept_candidate(self.operation, review["review_binding"], ["HIGH_RISK_PROMOTION", "PROMOTE"])]
        for action in actions:
            with self.subTest(action=action), self.assertRaises(GuardError): action()
        self.assertEqual("CANCELLED", self.guard.review(self.operation)["operation"]["state"])
        self.assertEqual(self.before, source_manifest(self.source))

    def test_changed_review_binding_cannot_accept_or_reject(self):
        self.candidate()
        binding = self.guard.review(self.operation)["review_binding"]
        for field in binding:
            changed = deepcopy(binding); changed[field] = "different"
            for decide in (lambda: self.guard.reject_change(self.operation, changed),
                           lambda: self.guard.accept_candidate(self.operation, changed, ["HIGH_RISK_PROMOTION", "PROMOTE"])):
                with self.subTest(field=field), self.assertRaises(GuardError) as error: decide()
                self.assertEqual("REVIEW_STALE", error.exception.code)
        self.assertEqual(self.before, source_manifest(self.source))

    def test_accept_does_not_bypass_missing_runtime_or_isolation(self):
        self.candidate()
        review = self.guard.review(self.operation)
        status, result = self.service.handle("POST", "/guard/accept/" + self.operation,
            {"binding": review["review_binding"], "approval_operations": ["HIGH_RISK_PROMOTION", "PROMOTE"]}, token="human-session")
        self.assertEqual(409, status, result)
        self.assertEqual("INVALID_STAGE", result["error"]["code"])
        self.assertFalse(self.guard.candidate_status(self.operation).get("promotion_authorized"))
        self.assertEqual(self.before, source_manifest(self.source))

    def test_reject_stays_terminal_even_after_sources_change(self):
        self.candidate()
        review = self.guard.review(self.operation)
        self.guard.reject_change(self.operation, review["review_binding"])
        modify_bim(self.source, lambda model: model["tables"][0].update(description="User's later edit"))
        latest = self.guard.review(self.operation)
        self.assertEqual("CANCELLED", latest["operation"]["state"])
        self.assertEqual("REJECTED", latest["operation"]["user_decision"])
        self.assertFalse(latest["operation"]["promotion_authorized"])

    def test_rejection_survives_interrupted_state_update(self):
        review = self.guard.review(self.operation)
        with patch.object(self.guard, "_save", side_effect=RuntimeError("Interrupted state write")):
            with self.assertRaises(RuntimeError): self.guard.reject_change(self.operation, review["review_binding"])
        restarted = ChangeGuard(self.source, self.guard.store.root, "user-review")
        self.assertEqual("CANCELLED", restarted.review(self.operation)["operation"]["state"])
        with self.assertRaises(GuardError): restarted.authorize(self.operation, "CONTRACT")
        self.assertEqual(self.before, source_manifest(self.source))

    def test_cached_promotion_permission_is_revoked_by_rejection(self):
        from change_guard.promotion.local import LocalPromotion, PromotionError
        from change_guard.promotion.git import GitPromotion
        self.candidate()
        state = self.guard.candidate_status(self.operation)
        review = self.guard.review(self.operation)
        # A cached permit is a test double for authorization previously issued
        # by the trusted controller. This test certifies only revocation.
        permit = self.guard.store.sign({"operation_id": self.operation, "authorized_operation": "PROMOTE"})
        self.guard.reject_change(self.operation, review["review_binding"])
        for controller in (LocalPromotion(self.guard.store), GitPromotion(self.guard.store)):
            with self.subTest(controller=type(controller).__name__), self.assertRaises(PromotionError) as error:
                if isinstance(controller, GitPromotion): controller.promote(self.operation, permit, "0" * 40)
                else: controller.promote(self.operation, permit)
            self.assertIn("revoked", str(error.exception))
        self.assertFalse((self.guard.store.root / self.operation / "promotion.json").exists())
        self.assertFalse((self.guard.store.root / self.operation / "git-promotion.json").exists())
        self.assertEqual(self.before, source_manifest(self.source))

    def test_decision_routes_require_guard_access_and_exact_input(self):
        binding = self.guard.review(self.operation)["review_binding"]
        for action in ("accept", "reject"):
            route = "/guard/" + action + "/" + self.operation
            self.assertEqual(403, self.service.handle("POST", route, {"binding": binding}, token="brain-session")[0])
            self.assertEqual(403, self.service.handle("POST", route, {"binding": binding}, token="human-session", origin="https://untrusted.invalid")[0])
            self.assertEqual(409, self.service.handle("POST", route, {"binding": binding, "skip_checks": True}, token="human-session")[0])
        self.guard.allowed_principals = ("unauthorized-principal",)
        with self.assertRaises(GuardError) as error: self.guard.reject_change(self.operation, binding)
        self.assertEqual("PRINCIPAL_NOT_AUTHORIZED", error.exception.code)


if __name__ == "__main__": unittest.main()
