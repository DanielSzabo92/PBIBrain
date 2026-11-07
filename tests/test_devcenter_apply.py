"""Build step S9: local apply (technical design sections 13 and 16 S9).

Acceptance tests (each test name gives its number):
1. End to end on a temp copy of the merge lab: apply, rescan, and the rescan matches the plan.
2. A failure in the report write leaves the model files unchanged (all or nothing).
3. Undo restores all files byte-equal to the backup.
4. A fake Desktop bridge with "unsaved changes" blocks; "open, saved" warns; "not reachable" warns.
5. Unconfirmed source marks block.
6. Agent proposals that are not accepted have no effect on the written files.
7. After apply, no row shows "source changed".
8. The change report has the plan summary.
9. End-to-end budget: the full apply of the merge lab in a fixed time (APPLY_BUDGET_SECONDS).
10. UC5 apply progress, UC6 apply preview, UC7 last apply, UC32 guard check of each rejection kind.

The real change guard needs the TOM bridge (Windows). On other systems the tests use
``FakePipeline``: the real app write step (``write_merge_files`` with the real PBIR
writer and a small Python model writer) and the real journaled promotion
(``LocalPromotion``). ``GuardPipelineEndToEndTests`` runs the real guard when the
bridge is built.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from types import SimpleNamespace
import unittest

from backend.api.app import create_app
from backend.devcenter import contracts, http_routes, jsapi
from backend.devcenter.agent_tools import AgentTools
from backend.devcenter.apply import desktop as desktop_states
from backend.devcenter.apply import rescan
from backend.devcenter.apply.desktop import DesktopBridge, state_of
from backend.devcenter.apply.pipeline import GuardPipeline, PromotionJournal
from backend.devcenter.apply.service import APPLY_BUDGET_SECONDS, GUARD_FOLDER, ApplyService
from backend.devcenter.apply.steps import CHECKS, GUARD, PROMOTION, STEPS_BY_KIND, ApplyFailure, check_of, guard_failure
from backend.devcenter.plan.compiler import GUARD_OPERATIONS, plan_hash, summary
from backend.devcenter.session.manager import DevCenterSessions
from backend.snapshots.manifest import content_hash, source_manifest
from change_guard.audit import AuditStore
from change_guard.merge import write_merge_files
from change_guard.promotion.local import LocalPromotion

REPOSITORY = Path(__file__).resolve().parents[1]
LAB = REPOSITORY / "tests" / "fixtures" / "merge_lab"
BRIDGE = REPOSITORY / "backend/adapters/tabular_metadata/dotnet/bin/Release/net8.0/TabularMetadata.dll"
SALES = "SalesA.SemanticModel/definition/tables/Sales.tmdl"
SUMMARY_PAGE = "SalesA.Report/definition/pages/summary/page.json"
MARGIN = "measure:Sales/Margin"
PAGE = "page:summary"
OLD_MARGIN = "[Total Sales] - [Total Cost]"
NEW_MARGIN = "DIVIDE([Total Sales] - [Total Cost], [Total Sales])"
TAKE_B = {"kind": "take", "source_id": "src-2"}
# The fake pipeline runs in well under a second. The limit of the real guard is APPLY_BUDGET_SECONDS.
FAKE_BUDGET_SECONDS = 10.0


# Fakes ------------------------------------------------------------------------------------

def fake_plan(devcenter, document, **_):
    """A Change Plan from the accepted Merge Choices of two rows (the compare needs the TOM bridge)."""

    choices = document.get("merge_choices") or {}
    operations, steps = [], []
    if MARGIN in choices:
        operations.append({"op_id": "op-0001", "op": "REWRITE_EXPRESSION", "guard_op": GUARD_OPERATIONS["REWRITE_EXPRESSION"], "domain": "model",
                           "object_type": "measure", "row_key": MARGIN, "table": "Sales", "name": "Margin", "property": "expression",
                           "old_text": OLD_MARGIN, "new_text": NEW_MARGIN, "order": 1, "needs": []})
        steps.append({"step_id": "step-margin", "kind": "merge_choice", "row_key": MARGIN, "row_id": "row-margin", "choice": "take",
                      "source_id": "src-2", "domain": "model", "object_type": "measure", "name": "Margin", "change": "modified",
                      "operation_ids": ["op-0001"]})
    if PAGE in choices:
        operations.append({"op_id": "op-0002", "op": "COPY_PAGE", "guard_op": GUARD_OPERATIONS["COPY_PAGE"], "domain": "report",
                           "object_type": "page", "row_key": PAGE + "@src-2", "source_id": "src-2", "source_key": PAGE,
                           "page_id": "summary", "name": "Summary", "replace": False, "order": 2, "needs": []})
        steps.append({"step_id": "step-summary", "kind": "merge_choice", "row_key": PAGE, "row_id": "row-summary", "choice": "take",
                      "source_id": "src-2", "domain": "report", "object_type": "page", "name": "Summary", "change": "created",
                      "operation_ids": ["op-0002"]})
    blocking = list(document.get("t23_blocking") or [])
    warnings = list(document.get("t23_warnings") or [])
    plan = {"status": "invalid" if blocking else "valid_with_warnings" if warnings else "valid", "summary": summary(steps), "steps": steps,
            "operations": operations, "blocking": blocking, "warnings": warnings, "sources": ["src-1", "src-2"]}
    plan["plan_hash"] = plan_hash(plan)
    return plan


class FakeModelWriter:
    """The model writer part of the bridge in Python: REWRITE_EXPRESSION and the format only rewrite."""

    def __init__(self, pipeline: "FakePipeline") -> None:
        self.pipeline = pipeline

    def write_model(self, model_path, output, operations):
        model, output = Path(model_path), Path(output)
        changed = []
        for operation in operations:
            if operation["op"] != "REWRITE_EXPRESSION":
                raise ValueError("The fake model writer knows REWRITE_EXPRESSION only")
            name = f"tables/{operation['table']}.tmdl"
            source = output / name if (output / name).is_file() else model / name
            text = source.read_text(encoding="utf-8")
            if not self.pipeline.broken_model_writer:
                text = text.replace(operation["old_text"], operation["new_text"])
            else:
                text = text.replace("measure 'Total Cost'", "measure 'Total Cost Changed'").replace("measure Total Cost", "measure 'Total Cost Changed'")
            (output / name).parent.mkdir(parents=True, exist_ok=True)
            (output / name).write_text(text, encoding="utf-8", newline="")
            changed.append(name)
        if not operations:
            for relative in self.pipeline.non_canonical:
                name = relative.split("definition/", 1)[1]
                text = (model / name).read_text(encoding="utf-8")
                (output / name).parent.mkdir(parents=True, exist_ok=True)
                (output / name).write_text("\n".join(line.rstrip() for line in text.split("\n")), encoding="utf-8", newline="")
                changed.append(name)
        return {"changed_files": sorted(set(changed)), "added_files": [], "removed_files": []}


class FakePipeline(PromotionJournal):
    """The app write step and the journaled promotion for real. The guard check is a switch."""

    def __init__(self) -> None:
        self.non_canonical: list[str] = []
        self.reject: list[dict] | None = None
        self.report_failure = False
        self.promotion_fault: int | None = None
        self.broken_model_writer = False
        self.hooks: list = []

    def _hook(self, step: str) -> None:
        for hook in self.hooks:
            hook(step)

    def canonical_files(self, job):
        return list(self.non_canonical)

    def write(self, job):
        self._hook("write")
        operation = "00000000-0000-4000-8000-" + job.apply_id[-12:]
        candidate = job.state_root / operation / "candidate"
        shutil.copytree(job.target_root, candidate, ignore=shutil.ignore_patterns(".pbi", ".pbibrain"))
        merge = {"operations": list(job.plan["operations"]), "model_path": job.model_path, "report_path": job.report_path,
                 "donor_paths": dict(job.donor_paths), "format_only": job.format_only}

        def failing_report_writer(*_args, **_kwargs):
            raise RuntimeError("report write failed")

        try:
            with tempfile.TemporaryDirectory(prefix="t23-write-") as work:
                write_merge_files(job.target_root, candidate, merge, FakeModelWriter(self), Path(work),
                                  report_writer=failing_report_writer if self.report_failure else None)
        except Exception as exc:
            raise ApplyFailure("write", "write_failed", "The app could not write the changed files.", check="write") from exc
        job.operation_id = operation
        job.context["candidate"] = candidate

    def guard(self, job):
        self._hook("guard")
        if self.reject is not None:
            raise guard_failure(GUARD, self.reject, "The guard did not accept the changed files.")

    def promote(self, job):
        self._hook("promotion")
        store = AuditStore(job.state_root)
        candidate = job.context["candidate"]
        baseline, proposed = source_manifest(job.target_root), source_manifest(candidate)
        permit = {"operation_id": job.operation_id, "source_root": str(job.target_root), "candidate_root": str(candidate),
                  "baseline_manifest": baseline, "candidate_manifest": proposed, "candidate_hash": content_hash(proposed),
                  "baseline_snapshot_id": "fake", "contract_hash": "fake", "policy_hash": "fake", "evidence_hash": "fake",
                  "principal": "test", "authorized_operation": "PROMOTE"}
        promotion = LocalPromotion(store)

        def fault(index):
            if index == self.promotion_fault:
                raise OSError("disk full")

        try:
            promotion.promote(job.operation_id, store.sign(permit), fault=fault)
        except Exception as exc:
            promotion.recover(job.operation_id)
            raise ApplyFailure(PROMOTION, "promotion_failed", "The app could not write the files to the target. No file changed.",
                               check="write", recovered=True) from exc
        job.files = self.files_of(job.state_root, job.operation_id)
        return job.files


class FakeDesktop:
    def __init__(self, state: str = desktop_states.NOT_OPEN) -> None:
        self.value = state
        self.hooks: list = []

    def state(self, target_root):
        for hook in self.hooks:
            hook("desktop_check")
        return self.value


# Test frame ---------------------------------------------------------------------------------

def route_of(method: str, path: str) -> http_routes.Route:
    parts = tuple(path.split("/"))
    return next(item for item in http_routes.ROUTES if item.method == method and item.path == parts)


class ApplyTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="t23-apply-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "project"
        for name in ("SalesA", "SalesB"):
            shutil.copytree(LAB / name, self.root / name)
        self.target = self.root / "SalesA"
        self.devcenter = DevCenterSessions(app_data_dir=None)
        self.devcenter.attach_project(self.root)
        self.app = create_app(use_native=False)
        self.app.devcenter = self.devcenter
        self.addCleanup(self.app.close)
        self.addCleanup(self.devcenter.close)
        self.pipeline = FakePipeline()
        self.desktop = FakeDesktop()
        self.builder_hooks: list = []
        self.service = ApplyService(self.devcenter, pipeline=self.pipeline, desktop=self.desktop, plan_builder=self.plan)
        self.devcenter.apply_service = self.service
        self.ok("session_create", {"display_name": "Apply"})
        for name in ("SalesA", "SalesB"):
            self.ok("source_add", {"base_revision": self.rev, "path": str(self.root / name / f"{name}.pbip")})
        self.ok("target_set", {"base_revision": self.rev, "model": {"mode": "existing", "source_id": "src-1"},
                               "report": {"mode": "existing", "source_id": "src-1"}})
        self.original = {item["path"]: (self.target / item["path"]).read_bytes() for item in source_manifest(self.target)}

    def plan(self, devcenter, document, **values):
        for hook in self.builder_hooks:
            hook("plan_status")
        return fake_plan(devcenter, document, **values)

    @property
    def rev(self) -> int:
        return self.devcenter.revision

    def ok(self, method: str, request: dict) -> dict:
        reply = jsapi.call(self.devcenter, method, request)
        self.assertNotIn("error", reply, reply)
        self.assertEqual([], contracts.errors(contracts.jsapi_reply(method), reply), reply)
        return reply

    def failed(self, method: str, request: dict) -> dict:
        reply = jsapi.call(self.devcenter, method, request)
        self.assertIn("error", reply, reply)
        self.assertEqual([], contracts.errors(contracts.ERROR, reply), reply)
        return reply["error"]

    def get(self, path: str) -> dict:
        status, payload = self.app.handle("GET", "/api/devcenter/" + path)
        self.assertEqual(200, status, payload)
        self.assertEqual([], contracts.errors(route_of("GET", path).contract, payload), payload)
        return payload

    def choose(self, *row_keys: str) -> None:
        for key in row_keys:
            self.ok("merge_choice_set", {"base_revision": self.rev, "row_key": key, "choice": TAKE_B})

    def apply(self, **extra) -> dict:
        preview = self.get("apply/preview")
        request = {"base_revision": self.rev, "plan_hash": preview["plan_hash"],
                   "approvals": sorted(item["purpose"] for item in preview["approvals_needed"]), **extra}
        return jsapi.call(self.devcenter, "apply", request)

    def applied(self, **extra) -> dict:
        reply = self.apply(**extra)
        self.assertNotIn("error", reply, reply)
        self.assertEqual([], contracts.errors(contracts.jsapi_reply("apply"), reply), reply)
        return reply

    def target_bytes(self) -> dict[str, bytes]:
        return {item["path"]: (self.target / item["path"]).read_bytes() for item in source_manifest(self.target)}

    def set_document(self, **values) -> None:
        """Put test-only plan inputs into the open session (the fake plan reads them)."""
        with self.devcenter._lock:
            self.devcenter._open.document.update(values)


# Acceptance tests ----------------------------------------------------------------------------

class ApplySequenceTests(ApplyTestCase):
    def test_01_end_to_end_apply_rescan_matches_the_plan(self) -> None:
        self.choose(MARGIN, PAGE)
        preview = self.get("apply/preview")
        self.assertTrue(preview["ready"], preview)
        reply = self.applied()
        self.assertEqual([], reply["rescan_differences"])
        self.assertIn(SALES, reply["files"])
        self.assertIn(SUMMARY_PAGE, reply["files"])
        self.assertIn(NEW_MARGIN, (self.target / SALES).read_text(encoding="utf-8"))
        self.assertTrue((self.target / SUMMARY_PAGE).is_file())
        last = self.get("apply/last")
        self.assertEqual((last["apply_id"], last["kind"], last["file_count"]), (reply["apply_id"], "apply", len(reply["files"])))
        self.assertTrue(last["backup_present"])
        self.assertFalse(last["target_changed"])
        self.assertEqual([], last["rescan_differences"])
        log = self.get("log")
        self.assertIn("apply", [entry["action"] for entry in log["entries"]])

    def test_02_report_write_failure_leaves_the_model_files_unchanged(self) -> None:
        self.choose(MARGIN, PAGE)
        self.pipeline.report_failure = True
        error = self.apply()["error"]
        self.assertEqual(("write", "write"), (error["details"]["step"], error["details"]["check"]))
        self.assertEqual(self.original, self.target_bytes())
        # A failure in the middle of the promotion restores the files that it wrote already.
        self.pipeline.report_failure = False
        self.pipeline.promotion_fault = 0
        error = self.apply()["error"]
        self.assertEqual(("promotion", "write", True), (error["details"]["step"], error["details"]["check"], error["details"]["recovered"]))
        self.assertEqual(self.original, self.target_bytes())
        self.assertEqual("failed", self.get("apply/progress")["state"])

    def test_03_undo_restores_all_files_byte_equal_to_the_backup(self) -> None:
        self.choose(MARGIN, PAGE)
        reply = self.applied()
        store = AuditStore(self.devcenter.session_folder() / GUARD_FOLDER)
        operation = self.service._load_last()["operation_id"]
        journal = store.load(operation + "/promotion.json")
        backups = {item["path"]: (store.root / item["backup"]).read_bytes() for item in journal["replacements"] if item["before_hash"]}
        undo = self.ok("undo_apply", {"base_revision": self.rev, "apply_id": reply["apply_id"]})
        self.assertEqual(sorted(reply["files"]), undo["files"])
        self.assertEqual([], undo["rescan_differences"])
        for path, data in backups.items():
            self.assertEqual(data, (self.target / path).read_bytes(), path)
        self.assertEqual(self.original, self.target_bytes())
        last = self.get("apply/last")
        self.assertTrue(last["undone"])
        self.assertFalse(last["backup_present"])
        self.assertEqual("not_found", self.failed("undo_apply", {"base_revision": self.rev})["code"])

    def test_04_desktop_bridge_states(self) -> None:
        self.choose(MARGIN)
        self.desktop.value = desktop_states.OPEN_UNSAVED
        self.assertEqual("open_unsaved", self.get("apply/preview")["desktop_state"])
        self.assertFalse(self.get("apply/preview")["ready"])
        error = self.apply()["error"]
        self.assertEqual(("desktop_check", "desktop_unsaved_changes"), (error["details"]["step"], error["details"]["reason"]))
        self.assertEqual(self.original, self.target_bytes())
        for state, notice in ((desktop_states.OPEN_SAVED, "apply_external_changes"), (desktop_states.NOT_REACHABLE, "desktop_not_checked")):
            with self.subTest(state=state):
                self.desktop.value = state
                self.assertEqual(state, self.get("apply/preview")["desktop_state"])
                reply = self.applied()
                self.assertEqual((state, [notice]), (reply["desktop_state"], reply["notices"]))
                self.ok("undo_apply", {"base_revision": self.rev})

    def test_04_desktop_bridge_client(self) -> None:
        pbip = self.target / "SalesA.pbip"
        instances = [{"pid": 1, "currentFilePath": str(self.root / "SalesB" / "SalesB.pbip"), "hasUnsavedChanges": True}]
        self.assertEqual("not_open", state_of(instances, self.target))
        self.assertEqual("open_saved", state_of([*instances, {"currentFilePath": str(pbip), "hasUnsavedChanges": False}], self.target))
        self.assertEqual("open_unsaved", state_of([{"currentFilePath": str(pbip), "hasUnsavedChanges": True}], self.target))

        def runner(payload, code=0):
            return lambda command: subprocess.CompletedProcess(command, code, stdout=payload, stderr="")

        status = json.dumps({"status": "ok", "instances": [{"currentFilePath": str(pbip), "hasUnsavedChanges": True}]})
        self.assertEqual("open_unsaved", DesktopBridge("powerbi-desktop", runner(status)).state(self.target))
        self.assertEqual("not_reachable", DesktopBridge("powerbi-desktop", runner("not json")).state(self.target))
        self.assertEqual("not_reachable", DesktopBridge("powerbi-desktop", runner(status, 1)).state(self.target))

        def missing(command):
            raise FileNotFoundError(command[0])

        self.assertEqual("not_reachable", DesktopBridge("powerbi-desktop", missing).state(self.target))

    def mark_margin(self) -> None:
        path = self.root / "SalesB" / "SalesB.SemanticModel" / "definition" / "tables" / "Sales.tmdl"
        text = path.read_text(encoding="utf-8")
        path.write_text(text.replace("[Sales Amount] - [Total Cost]", "[Sales Amount] - [Total Cost] * 2"), encoding="utf-8")

    def test_05_unconfirmed_source_marks_block(self) -> None:
        self.choose(MARGIN)
        self.mark_margin()
        preview = self.get("apply/preview")
        self.assertEqual({"count": 1, "row_keys": [MARGIN]}, preview["unconfirmed_marks"])
        self.assertFalse(preview["ready"])
        error = self.apply()["error"]
        self.assertEqual(("source_check", "unconfirmed_marks", [MARGIN]),
                         (error["details"]["step"], error["details"]["reason"], error["details"]["row_keys"]))
        self.assertEqual(self.original, self.target_bytes())
        self.ok("row_confirm", {"base_revision": self.rev, "row_keys": [MARGIN]})
        self.applied()

    def test_06_agent_proposals_that_are_not_accepted_have_no_effect(self) -> None:
        self.choose(MARGIN)

        def send(method, path, query, body):
            status, payload = self.app.handle(method, "/api/devcenter/" + path, json.dumps(body).encode("utf-8") if body is not None else None)
            return payload

        proposal = AgentTools(send).proposal_submit(kind="merge_choice", target=PAGE, payload={"choice": TAKE_B}, confidence=0.95,
                                                    reason="The donor has a summary page.", base_revision=self.rev, client="Test agent")
        self.assertNotIn("error", proposal, proposal)
        reply = self.applied()
        self.assertNotIn(SUMMARY_PAGE, reply["files"])
        self.assertFalse((self.target / SUMMARY_PAGE).exists())
        self.assertEqual([SALES], reply["files"])

    def test_07_after_apply_no_row_shows_source_changed(self) -> None:
        self.choose(MARGIN, PAGE)
        self.applied()
        self.ok("sources_check", {"base_revision": self.rev})
        self.assertEqual([], self.devcenter.marks())
        target = next(item for item in self.get("session")["sources"] if item["source_id"] == "src-1")
        self.assertEqual("same", target["fingerprint_state"])

    def test_08_the_change_report_has_the_plan_summary(self) -> None:
        self.choose(MARGIN, PAGE)
        reply = self.applied()
        report = self.ok("change_report_write", {"base_revision": self.rev, "apply_id": reply["apply_id"]})
        text = report["markdown"]
        plan = fake_plan(self.devcenter, self.devcenter._open.document)
        for part in ("## Plan summary", plan["plan_hash"], "Plan steps: 2", "Model: Changed: 1 (1 measure)",
                     "Report: Added: 1 (1 page)", "`Margin` (from SalesB)", SALES, "agrees with the plan"):
            self.assertIn(part, text)
        self.assertEqual(text, (self.root / report["path"]).read_text(encoding="utf-8"))
        self.assertTrue(report["path"].startswith(".pbibrain/sessions/"))
        self.assertNotIn("—", text)

    def test_08b_the_change_report_uses_the_file_name_of_the_save_dialog(self) -> None:
        self.choose(MARGIN, PAGE)
        reply = self.applied()
        name = "Sales merge change report 2026-11-06.md"
        report = self.ok("change_report_write", {"base_revision": self.rev, "apply_id": reply["apply_id"], "file_name": name})
        self.assertTrue(report["path"].endswith("/" + name))
        self.assertTrue((self.root / report["path"]).is_file())
        for bad in ("../x.md", ".hidden.md", "a\\b.md"):
            error = self.failed("change_report_write", {"base_revision": self.rev, "file_name": bad})
            self.assertEqual("invalid_payload", error["code"])

    def test_09_apply_budget(self) -> None:
        self.choose(MARGIN, PAGE)
        started = time.monotonic()
        self.applied()
        seconds = time.monotonic() - started
        self.assertLess(seconds, FAKE_BUDGET_SECONDS)
        self.assertLessEqual(self.service._load_last()["seconds"], FAKE_BUDGET_SECONDS)

    def test_format_only_apply_and_the_canonical_block(self) -> None:
        sales = self.target / SALES
        sales.write_text(sales.read_text(encoding="utf-8").replace(OLD_MARGIN, OLD_MARGIN + "   "), encoding="utf-8", newline="")
        self.pipeline.non_canonical = [SALES]
        self.choose(MARGIN)
        preview = self.get("apply/preview")
        self.assertEqual([SALES], preview["non_canonical_files"])
        self.assertFalse(preview["ready"])
        error = self.apply()["error"]
        self.assertEqual(("canonical_check", "canonical", [SALES]), (error["details"]["step"], error["details"]["check"], error["details"]["files"]))
        reply = self.ok("format_only_apply", {"base_revision": self.rev})
        self.assertEqual(("format_only", [SALES], []), (reply["kind"], reply["files"], reply["rescan_differences"]))
        self.assertNotIn(OLD_MARGIN + "   ", sales.read_text(encoding="utf-8"))
        self.assertEqual("format_only", self.get("apply/last")["kind"])
        self.pipeline.non_canonical = []
        self.assertEqual("already_canonical", self.failed("format_only_apply", {"base_revision": self.rev})["details"]["reason"])

    def test_other_blocks_of_steps_1_to_6(self) -> None:
        self.assertEqual("plan_empty", self.apply()["error"]["details"]["reason"])
        self.choose(MARGIN)
        stale = jsapi.call(self.devcenter, "apply", {"base_revision": self.rev - 1, "plan_hash": "x", "approvals": []})["error"]
        self.assertEqual(("stale_revision", "source_check"), (stale["code"], stale["details"]["step"]))
        self.assertEqual("plan_changed", self.failed("apply", {"base_revision": self.rev, "plan_hash": "x", "approvals": []})["details"]["reason"])
        self.set_document(t23_warnings=[{"item_id": "not_checked:measure:Sales/Margin", "kind": "not_checked", "row_key": MARGIN,
                                         "object": {"name": "Margin"}, "message": "The app did not examine this area."}])
        preview = self.get("apply/preview")
        self.assertEqual([{"purpose": "UNCHECKED_IMPACT", "risk": None, "row_keys": [MARGIN]}], preview["approvals_needed"])
        self.assertEqual([{"object_id": MARGIN, "object_name": "Margin"}], preview["not_checked"])
        error = self.failed("apply", {"base_revision": self.rev, "plan_hash": preview["plan_hash"], "approvals": []})
        self.assertEqual(("approval", "approval"), (error["details"]["step"], error["details"]["check"]))
        self.set_document(t23_blocking=[{"item_id": "dax_parse:" + MARGIN, "kind": "dax_parse", "row_key": MARGIN,
                                         "message": "The DAX expression has a syntax error."}])
        preview = self.get("apply/preview")
        self.assertEqual("invalid", preview["validation"]["status"])
        self.assertEqual([{"check": "dax_parse", "object": MARGIN, "message": "The DAX expression has a syntax error."}],
                         preview["validation"]["failed_checks"])
        self.assertEqual("plan_invalid", self.apply()["error"]["details"]["reason"])
        self.assertEqual(self.original, self.target_bytes())


class ApplyContractTests(ApplyTestCase):
    """UC5, UC6, UC7, UC32."""

    def watch(self) -> list[dict]:
        seen: list[dict] = []

        def record(_step):
            progress = self.get("apply/progress")
            if progress["state"] == "running":  # A preview read also calls the hooks.
                seen.append(progress)

        self.builder_hooks.append(record)
        self.desktop.hooks.append(record)
        self.pipeline.hooks.append(record)
        return seen

    def assert_order(self, seen: list[dict], kind: str) -> None:
        steps = STEPS_BY_KIND[kind]
        self.assertTrue(seen)
        self.assertEqual(len({item["apply_id"] for item in seen}), 1)
        for item in seen:
            self.assertEqual(("running", len(steps)), (item["state"], item["step_count"]))
            self.assertEqual(steps.index(item["step"]) + 1, item["step_index"])
        indexes = [item["step_index"] for item in seen]
        self.assertEqual(sorted(indexes), indexes)

    def test_uc5_progress_of_apply_format_only_and_undo(self) -> None:
        self.assertEqual("done", self.get("apply/progress")["state"])
        self.choose(MARGIN)
        seen = self.watch()
        reply = self.applied()
        self.assert_order(seen, "apply")
        self.assertEqual(["plan_status", "desktop_check", "write", "guard", "promotion"], [item["step"] for item in seen][-5:])
        end = self.get("apply/progress")
        self.assertEqual((reply["apply_id"], "done", "change_report", 12, 12),
                         (end["apply_id"], end["state"], end["step"], end["step_index"], end["step_count"]))
        seen.clear()
        self.ok("undo_apply", {"base_revision": self.rev})
        self.assert_order(seen, "undo")
        self.assertEqual("done", self.get("apply/progress")["state"])
        seen.clear()
        self.pipeline.non_canonical = [SALES]
        self.ok("format_only_apply", {"base_revision": self.rev})
        self.assert_order(seen, "format_only")
        self.assertEqual(["desktop_check", "write", "guard", "promotion"], [item["step"] for item in seen])
        self.assertEqual(("done", 7), (self.get("apply/progress")["state"], self.get("apply/progress")["step_index"]))
        seen.clear()
        self.pipeline.reject = [{"code": "UNPLANNED_FILE_CHANGED", "gate": "source"}]
        self.pipeline.non_canonical = []
        self.apply()
        end = self.get("apply/progress")
        self.assertEqual(("failed", "guard"), (end["state"], end["step"]))

    def test_uc6_apply_preview(self) -> None:
        self.choose(MARGIN)
        self.mark_margin()
        self.pipeline.non_canonical = ["SalesA.SemanticModel/definition/tables/Date.tmdl"]
        preview = self.get("apply/preview")
        plan = fake_plan(self.devcenter, self.devcenter._open.document)
        self.assertEqual(plan["plan_hash"], preview["plan_hash"])
        self.assertEqual({"count": 1, "row_keys": [MARGIN]}, preview["unconfirmed_marks"])
        self.assertEqual(["SalesA.SemanticModel/definition/tables/Date.tmdl"], preview["non_canonical_files"])
        self.assertEqual({"status": "valid", "failed_checks": []}, preview["validation"])
        self.assertEqual({"add": 0, "change": 1, "remove": 0, "rename": 0}, preview["summary"])
        for state in desktop_states.STATES:
            self.desktop.value = state
            self.assertEqual(state, self.get("apply/preview")["desktop_state"])
        # The preview is a read: it does not change the session revision or the marks.
        revision = self.rev
        self.get("apply/preview")
        self.assertEqual((revision, []), (self.rev, self.devcenter.marks()))

    def mark_margin(self) -> None:
        ApplySequenceTests.mark_margin(self)

    def test_uc7_last_apply_target_change_and_rescan_differences(self) -> None:
        empty = self.get("apply/last")
        self.assertEqual((None, False, 0), (empty["apply_id"], empty["backup_present"], empty["file_count"]))
        self.choose(MARGIN)
        self.applied()
        sales = self.target / SALES
        sales.write_text(sales.read_text(encoding="utf-8") + "\n", encoding="utf-8", newline="")
        last = self.get("apply/last")
        self.assertEqual((True, [SALES]), (last["target_changed"], last["changed_files"]))
        error = self.failed("undo_apply", {"base_revision": self.rev})
        self.assertEqual(("backup_check", "target_changed", [SALES]), (error["details"]["step"], error["details"]["reason"], error["details"]["files"]))
        # A writer that changes another object than the plan names gives a rescan difference.
        shutil.rmtree(self.target)
        shutil.copytree(LAB / "SalesA", self.target)
        self.ok("sources_check", {"base_revision": self.rev})
        if self.devcenter.marks():
            self.ok("row_confirm", {"base_revision": self.rev, "row_keys": [mark["row_key"] for mark in self.devcenter.marks()]})
        self.pipeline.broken_model_writer = True
        reply = self.applied()
        expected = [{"object": "measure:Sales/Margin", "expected": "changed", "found": "unchanged"},
                    {"object": "measure:Sales/Total Cost", "expected": "present", "found": "absent"},
                    {"object": "measure:Sales/Total Cost Changed", "expected": "absent", "found": "present"}]
        self.assertEqual(expected, reply["rescan_differences"])
        self.assertEqual(expected, self.get("apply/last")["rescan_differences"])

    def test_uc32_each_guard_rejection_gives_the_step_and_the_check(self) -> None:
        self.choose(MARGIN)
        kinds = {"scope": "UNPLANNED_FILE_CHANGED", "canonical": "NON_CANONICAL_MODEL_FILE", "tree_compare": "UNPLANNED_MODEL_CHANGE",
                 "pbir": "UNPLANNED_REPORT_PROPERTY", "policy": "STRUCTURAL_VALIDATION_FAILURE", "approval": "MISSING_APPROVAL",
                 "write": "WRITE_RECORD_MISSING", "rescan": "POST_PROMOTION_MISMATCH"}
        self.assertEqual(set(CHECKS), set(kinds))
        for check, code in kinds.items():
            with self.subTest(check=check):
                self.pipeline.reject = [{"code": code, "gate": "static" if check == "policy" else None}]
                error = self.apply()["error"]
                self.assertEqual(("action_not_allowed", "guard", check, [code]),
                                 (error["code"], error["details"]["step"], error["details"]["check"], error["details"]["guard_codes"]))
                self.assertEqual(self.original, self.target_bytes())

    def test_uc32_the_real_guard_pipeline_maps_the_guard_result(self) -> None:
        """``GuardPipeline.guard`` with a stand-in for ``ChangeGuard``: each result gives its step and check."""

        def run(decision, verification=None, accept_error=None, approvals=()):
            guard = SimpleNamespace(validate_candidate=lambda op: {"decision": decision},
                                    review=lambda op: {"verification": verification or {}, "review_binding": {}},
                                    accept_candidate=lambda *args: (_ for _ in ()).throw(accept_error) if accept_error else None)
            job = SimpleNamespace(context={"guard": guard}, operation_id="op", approvals=list(approvals))
            try:
                GuardPipeline(adapter=object()).guard(job)
            except ApplyFailure as failure:
                return failure.step, failure.check, failure.details
            return None

        reject = {"decision": "REJECT", "blocking_reasons": [{"code": "UNAUTHORIZED_MUTATION", "gate": "scope"}]}
        cases = [
            ({"scope": {"violations": [{"code": "UNPLANNED_MODEL_CHANGE"}]}}, "tree_compare"),
            ({"scope": {"violations": [{"code": "UNPLANNED_REPORT_PROPERTY"}]}}, "pbir"),
            ({"source": {"violations": [{"code": "NON_CANONICAL_MODEL_FILE"}]}}, "canonical"),
            ({"security": {"violations": [{"code": "WRITE_RECORD_HASH_MISMATCH"}]}}, "write"),
            ({"scope": {"violations": [{"code": "UNPLANNED_FILE_CREATED"}]}}, "scope"),
        ]
        for verification, check in cases:
            with self.subTest(check=check):
                self.assertEqual(("guard", check), run(reject, verification)[:2])
        static = {"decision": "REJECT", "blocking_reasons": [{"code": "STRUCTURAL_VALIDATION_FAILURE", "gate": "static"}]}
        self.assertEqual(("guard", "policy"), run(static)[:2])
        needs = {"decision": "APPROVAL_REQUIRED", "approval_reasons": ["HIGH_RISK_PROMOTION"]}
        self.assertEqual(("guard", "approval"), run(needs)[:2])
        self.assertIsNone(run(needs, approvals=["HIGH_RISK_PROMOTION"]))
        error = type("GuardError", (Exception,), {"code": "MISSING_APPROVAL"})()
        self.assertEqual(("guard", "approval"), run({"decision": "ALLOW"}, accept_error=error)[:2])
        self.assertEqual("rescan", check_of("POST_PROMOTION_MISMATCH"))

    def test_no_http_route_and_no_agent_tool_writes_an_apply(self) -> None:
        for method in ("POST", "PUT", "DELETE"):
            for path in ("apply", "apply/preview", "apply/last", "undo_apply", "format_only_apply", "change_report_write"):
                status, _ = self.app.handle(method, "/api/devcenter/" + path, b"{}")
                self.assertIn(status, {404, 405}, (method, path))
        self.assertEqual(200, self.app.handle("GET", "/api/devcenter/apply/progress")[0])


class RescanTests(unittest.TestCase):
    def test_a_full_match_and_each_kind_of_difference(self) -> None:
        before = {"measure:Sales/A": "1", "measure:Sales/B": "2", "table:Sales": "3", "measure:Sales/Old": "4", "page:p1": "5"}
        after = {"measure:Sales/A": "9", "table:Sales": "3", "measure:Sales/New": "4", "page:p1": "5", "page:p2": "6",
                 "measure:Sales/C": "7", "measure:Sales/B": "2"}
        operations = [
            {"op": "REWRITE_EXPRESSION", "domain": "model", "object_type": "measure", "row_key": "measure:Sales/A"},
            {"op": "RENAME", "domain": "model", "object_type": "measure", "table": "Sales", "old_name": "Old", "new_name": "New"},
            {"op": "CREATE", "domain": "model", "object_type": "measure", "table": "Sales", "name": "C"},
            {"op": "COPY_PAGE", "domain": "report", "object_type": "page", "row_key": "page:p2@src-2"},
        ]
        self.assertEqual([], rescan.differences(operations, before, after))
        broken = {**after, "measure:Sales/A": "1", "measure:Sales/Extra": "8"}
        broken.pop("page:p2")
        self.assertEqual([
            {"object": "measure:Sales/A", "expected": "changed", "found": "unchanged"},
            {"object": "measure:Sales/Extra", "expected": "absent", "found": "present"},
            {"object": "page", "expected": "1 present", "found": "0 present"},
        ], rescan.differences(operations, before, broken))

    def test_a_table_rename_moves_the_child_keys(self) -> None:
        before = {"table:Store": "1", "column:Store/Key": "2"}
        after = {"table:Shop": "1", "column:Shop/Key": "2"}
        operations = [{"op": "RENAME", "domain": "model", "object_type": "table", "old_name": "Store", "new_name": "Shop"}]
        self.assertEqual([], rescan.differences(operations, before, after))


class PromotionUndoTests(unittest.TestCase):
    def test_undo_refuses_a_changed_target_and_an_uncommitted_journal(self) -> None:
        with tempfile.TemporaryDirectory(prefix="t23-undo-") as work:
            root = Path(work)
            source = shutil.copytree(LAB / "Finance", root / "Finance")
            candidate = shutil.copytree(source, root / "candidate")
            path = next(candidate.rglob("*.tmdl"))
            path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            store = AuditStore(root / "state")
            operation = "00000000-0000-4000-8000-000000000001"
            baseline, proposed = source_manifest(source), source_manifest(candidate)
            permit = {"operation_id": operation, "source_root": str(source), "candidate_root": str(candidate), "baseline_manifest": baseline,
                      "candidate_manifest": proposed, "candidate_hash": content_hash(proposed), "baseline_snapshot_id": "b", "contract_hash": "c",
                      "policy_hash": "p", "evidence_hash": "e", "principal": "t", "authorized_operation": "PROMOTE"}
            promotion = LocalPromotion(store)
            promotion.promote(operation, store.sign(permit))
            changed = source / path.relative_to(candidate)
            data = changed.read_bytes()
            changed.write_bytes(data + b"\n")
            with self.assertRaises(Exception):
                promotion.undo(operation)
            changed.write_bytes(data)
            self.assertEqual("UNDONE", promotion.undo(operation)["status"])
            self.assertEqual(baseline, source_manifest(source))
            with self.assertRaises(Exception):
                promotion.undo(operation)


@unittest.skipUnless(BRIDGE.is_file(), "Build the TOM bridge first (Windows)")
class GuardPipelineEndToEndTests(unittest.TestCase):
    """The real plan, the real guard, and the real promotion on a temp copy of the merge lab."""

    def test_apply_rescan_undo_and_budget(self) -> None:
        with tempfile.TemporaryDirectory(prefix="t23-guard-") as work:
            root = Path(work) / "project"
            for name in ("SalesA", "SalesB"):
                shutil.copytree(LAB / name, root / name)
            devcenter = DevCenterSessions(app_data_dir=None)
            devcenter.attach_project(root)
            devcenter.apply_service = ApplyService(devcenter, desktop=FakeDesktop())
            app = create_app(use_native=False)
            app.devcenter = devcenter
            try:
                def ok(method, request):
                    reply = jsapi.call(devcenter, method, request)
                    self.assertNotIn("error", reply, reply)
                    return reply

                ok("session_create", {"display_name": "Guard"})
                for name in ("SalesA", "SalesB"):
                    ok("source_add", {"base_revision": devcenter.revision, "path": str(root / name / f"{name}.pbip")})
                ok("target_set", {"base_revision": devcenter.revision, "model": {"mode": "existing", "source_id": "src-1"},
                                  "report": {"mode": "existing", "source_id": "src-1"}})
                for key in (MARGIN, PAGE):
                    ok("merge_choice_set", {"base_revision": devcenter.revision, "row_key": key, "choice": TAKE_B})
                original = source_manifest(root / "SalesA")
                status, preview = app.handle("GET", "/api/devcenter/apply/preview")
                self.assertTrue(preview["ready"], preview)
                started = time.monotonic()
                reply = ok("apply", {"base_revision": devcenter.revision, "plan_hash": preview["plan_hash"],
                                     "approvals": sorted(item["purpose"] for item in preview["approvals_needed"])})
                self.assertLess(time.monotonic() - started, APPLY_BUDGET_SECONDS)
                self.assertEqual([], reply["rescan_differences"])
                ok("undo_apply", {"base_revision": devcenter.revision})
                self.assertEqual(original, source_manifest(root / "SalesA"))
            finally:
                devcenter.close()
                app.close()


if __name__ == "__main__":
    unittest.main()
