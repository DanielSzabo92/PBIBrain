"""Issue #16: cloud model and cloud report targets of a merge apply, with fakes only.

Acceptance: two local donors and a cloud model target. Apply, the rescan from the
service matches the plan, and the undo restores the backup in the service.

No test makes a network call. The fake XMLA server is a folder: the fake reader
exports it, the fake writer replaces it (the bridge ``cloud-deploy`` in production).
The apply uses the fake pipeline of the S9 tests (the real app write and the real
journaled promotion on the working copy).
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from backend.api.app import create_app
from backend.devcenter import contracts, jsapi
from backend.devcenter.apply.cloud_target import CLOUD_WRITE, WARNING_PBIX
from backend.devcenter.apply.service import ApplyService
from backend.devcenter.session.manager import DevCenterSessions
from backend.devcenter.sources.cloud import (
    FABRIC_API,
    CloudReadFailed,
    CloudService,
    HttpReply,
    ModelDeploy,
    definition_parts,
    deploy_from_bridge,
)
from tests.test_devcenter_apply import MARGIN, NEW_MARGIN, OLD_MARGIN, PAGE, TAKE_B, FakeDesktop, FakePipeline, fake_plan, route_of
from tests.test_devcenter_cloud_read import LSU_1, MODEL, REPORT_OK, WS_SALES, FakeCloud, FakeReader, FakeTokens

REPOSITORY = Path(__file__).resolve().parents[1]
LAB = REPOSITORY / "tests" / "fixtures" / "merge_lab"
BRIDGE = REPOSITORY / "backend/adapters/tabular_metadata/dotnet/bin/Release/net8.0/TabularMetadata.dll"
LSU_DEPLOY = "2026-11-07T10:00:00Z"


class FakeWriter:
    """A fake XMLA write: the TMDL folder replaces the definition of the fake server model."""

    def __init__(self, reader: FakeReader) -> None:
        self.reader = reader
        self.calls: list[tuple[str, str, str | None]] = []
        self.fail_code: str | None = None
        self.count = 0

    def deploy(self, server, database, token, folder, expected):
        self.calls.append((server, database, expected))
        if self.fail_code:
            raise CloudReadFailed(self.fail_code)
        before = self.reader.last_schema_update
        if expected is not None and expected != before:
            raise CloudReadFailed("target_changed")
        definition = self.reader.model_dir / "definition"
        shutil.rmtree(definition)
        shutil.copytree(folder, definition)
        self.count += 1
        self.reader.last_schema_update = f"2026-11-07T10:00:0{self.count}Z"
        return ModelDeploy(before, self.reader.last_schema_update)


class WritableCloud(FakeCloud):
    """The fake REST APIs with Fabric ``updateDefinition`` (it replaces the parts of the report)."""

    def __init__(self, report_dir: Path) -> None:
        super().__init__(report_dir)
        # The service gives definition.pbir with its schema and a byConnection reference.
        pbir = {"$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
                "version": "4.0", "datasetReference": {"byConnection": {
                    "connectionString": "Data Source=powerbi://api.powerbi.com/v1.0/myorg/Sales Analytics;Initial Catalog=Sales Cloud"}}}
        self.parts = [part for part in self.parts if part["path"] != "definition.pbir"]
        self.parts.append({"path": "definition.pbir", "payload": base64.b64encode(json.dumps(pbir).encode()).decode(),
                           "payloadType": "InlineBase64"})
        self.updates: list[str] = []
        self.update_status = 200

    def send(self, method, url, token, body=None):
        prefix = f"{FABRIC_API}/workspaces/{WS_SALES}/reports/"
        if method == "POST" and url.startswith(prefix) and url.endswith("/updateDefinition"):
            self.requests.append((method, url, token.value))
            if self.update_status != 200:
                return HttpReply(self.update_status, {}, None)
            self.updates.append(url[len(prefix):].split("/")[0])
            self.parts = list(body["definition"]["parts"])
            return HttpReply(200, {}, None)
        return super().send(method, url, token, body)


class CloudTargetTestCase(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="cloud-target-")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.root = self.base / "project"
        for name in ("SalesA", "SalesB"):
            shutil.copytree(LAB / name, self.root / name)
        self.server_model = self.base / "server" / "SalesCloud.SemanticModel"
        shutil.copytree(LAB / "SalesA" / "SalesA.SemanticModel", self.server_model)
        self.tokens = FakeTokens()
        self.http = WritableCloud(LAB / "SalesA" / "SalesA.Report")
        self.reader = FakeReader(self.server_model)
        self.writer = FakeWriter(self.reader)
        self.cloud = CloudService(self.tokens, self.http, self.reader, sleep=lambda _: None, writer=self.writer)
        self.devcenter = DevCenterSessions(app_data_dir=self.base / "appdata", cloud=self.cloud)
        self.devcenter.attach_project(self.root)
        self.addCleanup(self.devcenter.close)
        self.app = create_app(use_native=False)
        self.app.devcenter = self.devcenter
        self.addCleanup(self.app.close)
        self.pipeline = FakePipeline()
        self.service = ApplyService(self.devcenter, pipeline=self.pipeline, desktop=FakeDesktop(), plan_builder=fake_plan)
        self.devcenter.apply_service = self.service
        self.ok("session_create", {"display_name": "Cloud target"})
        for name in ("SalesA", "SalesB"):
            self.ok("source_add", {"base_revision": self.rev, "path": str(self.root / name / f"{name}.pbip")})
        self.model_id = self.ok("cloud_connect", {"base_revision": self.rev, "kind": "model", "workspace_id": WS_SALES,
                                                  "item_id": MODEL, "access_type": "Read/Write"})["source"]["source_id"]

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

    def target(self, report: dict | None = None) -> None:
        self.ok("target_set", {"base_revision": self.rev, "model": {"mode": "existing", "source_id": self.model_id},
                               "report": report or {"mode": "new_empty"}})

    def choose(self, *row_keys: str) -> None:
        for key in row_keys:
            self.ok("merge_choice_set", {"base_revision": self.rev, "row_key": key, "choice": TAKE_B})

    def apply(self) -> dict:
        preview = self.get("apply/preview")
        return jsapi.call(self.devcenter, "apply", {"base_revision": self.rev, "plan_hash": preview["plan_hash"],
                                                    "approvals": sorted(item["purpose"] for item in preview["approvals_needed"])})

    def server_sales(self) -> str:
        return (self.server_model / "definition" / "tables" / "Sales.tmdl").read_text(encoding="utf-8")


class CloudModelTargetTests(CloudTargetTestCase):
    def test_acceptance_two_local_donors_to_a_cloud_model_apply_rescan_and_undo(self) -> None:
        self.target()
        self.choose(MARGIN)
        original = self.server_sales()
        preview = self.get("apply/preview")
        self.assertTrue(preview["ready"], preview)
        self.assertIn(CLOUD_WRITE, [item["purpose"] for item in preview["approvals_needed"]])
        cloud = preview["cloud_target"]
        self.assertEqual(("Sales Analytics", "Sales Cloud", None), (cloud["workspace_name"], cloud["model_name"], cloud["report_name"]))
        self.assertIn(WARNING_PBIX, cloud["warnings"])
        self.assertTrue(all(item["result"] != "failed" for item in cloud["checks"]), cloud["checks"])

        reply = self.apply()
        self.assertNotIn("error", reply, reply)
        self.assertEqual([], contracts.errors(contracts.jsapi_reply("apply"), reply), reply)
        self.assertEqual([], reply["rescan_differences"])
        self.assertIn("cloud_written", reply["notices"])
        self.assertIn(NEW_MARGIN, self.server_sales())
        # The deploy carried the LastSchemaUpdate of the fresh read, so a concurrent change stops it.
        self.assertEqual([("powerbi://api.powerbi.com/v1.0/myorg/Sales Analytics", MODEL, LSU_1)], self.writer.calls)
        last = self.get("apply/last")
        self.assertTrue(last["backup_present"])
        self.assertEqual([], last["rescan_differences"])
        # After the apply the target baseline is the service model: no row is marked "source changed".
        self.ok("sources_check", {"base_revision": self.rev})
        self.assertEqual([], self.devcenter._open.document["source_marks"])

        undo = self.ok("undo_apply", {"base_revision": self.rev, "apply_id": reply["apply_id"]})
        self.assertEqual([], undo["rescan_differences"])
        self.assertEqual(original, self.server_sales())
        self.assertIn(OLD_MARGIN, self.server_sales())
        self.assertTrue(self.get("apply/last")["undone"])

    def test_a_read_only_cloud_model_cannot_be_a_target(self) -> None:
        with self.devcenter._lock:
            self.devcenter._source(self.devcenter._open.document, self.model_id)["access_type"] = "Read"
        error = self.failed("target_set", {"base_revision": self.rev, "model": {"mode": "existing", "source_id": self.model_id}})
        self.assertEqual("cloud_target", error["details"]["reason"])
        # A copy only reads the cloud model, so it is allowed with Read access.
        reply = self.ok("target_set", {"base_revision": self.rev, "model": {"mode": "copy_of", "source_id": self.model_id,
                                                                             "path": str(self.root / "Merged")}})
        self.assertEqual(1, len(reply["sources_added"]))

    def test_the_cloud_write_needs_its_approval(self) -> None:
        self.target()
        self.choose(MARGIN)
        preview = self.get("apply/preview")
        error = jsapi.call(self.devcenter, "apply", {"base_revision": self.rev, "plan_hash": preview["plan_hash"], "approvals": []})["error"]
        self.assertEqual(("approval", "approval_missing"), (error["details"]["step"], error["details"]["reason"]))
        self.assertEqual([], self.writer.calls)

    def test_a_change_in_the_service_after_the_read_stops_the_deploy(self) -> None:
        self.target()
        self.choose(MARGIN)
        original = self.server_sales()
        real = self.writer.deploy

        def concurrent(server, database, token, folder, expected):
            self.reader.last_schema_update = "2026-11-07T09:59:59Z"  # Someone saved the model in the meantime.
            return real(server, database, token, folder, expected)

        self.writer.deploy = concurrent
        error = self.apply()["error"]
        self.assertEqual(("promotion", "target_changed_in_service"), (error["details"]["step"], error["details"]["reason"]))
        self.assertEqual(original, self.server_sales())

    def test_write_conditions_block_a_shared_capacity_and_a_viewer(self) -> None:
        self.target()
        self.choose(MARGIN)
        self.http.roles[WS_SALES][0]["role"] = "Viewer"
        preview = self.get("apply/preview")
        self.assertFalse(preview["ready"])
        role = next(item for item in preview["cloud_target"]["checks"] if item["check_id"] == "role")
        self.assertEqual(("failed", "role_cannot_write"), (role["result"], role["reason"]))
        error = self.apply()["error"]
        self.assertEqual(("plan_status", "cloud_write_not_possible", "role"),
                         (error["details"]["step"], error["details"]["reason"], error["details"]["check_id"]))
        self.http.roles[WS_SALES][0]["role"] = "Contributor"
        self.http.groups[0]["isOnDedicatedCapacity"] = False
        capacity = next(item for item in self.get("apply/preview")["cloud_target"]["checks"] if item["check_id"] == "capacity")
        self.assertEqual(("failed", "workspace_not_on_capacity"), (capacity["result"], capacity["reason"]))
        self.assertEqual([], self.writer.calls)

    def test_a_cloud_report_target_needs_a_cloud_model_target(self) -> None:
        report = self.ok("cloud_connect", {"base_revision": self.rev, "kind": "report", "workspace_id": WS_SALES, "item_id": REPORT_OK,
                                           "access_type": "Read/Write"})["source"]["source_id"]
        self.ok("target_set", {"base_revision": self.rev, "model": {"mode": "existing", "source_id": "src-1"},
                               "report": {"mode": "existing", "source_id": report}})
        self.choose(MARGIN)
        failed = self.get("apply/preview")["validation"]["failed_checks"]
        self.assertIn("mixed_target", [item["check"] for item in failed])


class CloudReportTargetTests(CloudTargetTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.report_id = self.ok("cloud_connect", {"base_revision": self.rev, "kind": "report", "workspace_id": WS_SALES,
                                                   "item_id": REPORT_OK, "access_type": "Read/Write"})["source"]["source_id"]
        self.original_parts = list(self.http.parts)
        self.target({"mode": "existing", "source_id": self.report_id})

    def paths(self) -> set[str]:
        return {part["path"] for part in self.http.parts}

    def test_model_and_report_go_to_the_service_and_undo_restores_both(self) -> None:
        self.choose(MARGIN, PAGE)
        preview = self.get("apply/preview")
        self.assertTrue(preview["ready"], preview)
        self.assertEqual("Sales Overview", preview["cloud_target"]["report_name"])
        reply = self.apply()
        self.assertNotIn("error", reply, reply)
        self.assertEqual([], reply["rescan_differences"])
        self.assertEqual([REPORT_OK], self.http.updates)
        self.assertIn("definition/pages/summary/page.json", self.paths())
        self.assertIn(NEW_MARGIN, self.server_sales())
        # The upload keeps the byConnection binding of the service (the working copy binds byPath for the guard).
        pbir = next(part for part in self.http.parts if part["path"] == "definition.pbir")
        self.assertIn("byConnection", json.loads(base64.b64decode(pbir["payload"]))["datasetReference"])
        self.ok("sources_check", {"base_revision": self.rev})
        self.assertEqual([], self.devcenter._open.document["source_marks"])

        self.ok("undo_apply", {"base_revision": self.rev})
        self.assertNotIn("definition/pages/summary/page.json", self.paths())
        self.assertEqual(sorted(part["path"] for part in self.original_parts), sorted(self.paths()))
        self.assertIn(OLD_MARGIN, self.server_sales())

    def test_a_refused_report_write_restores_the_model(self) -> None:
        self.choose(MARGIN, PAGE)
        original = self.server_sales()
        self.http.update_status = 403
        error = self.apply()["error"]
        self.assertEqual(("promotion", "cloud_report_write_failed", True),
                         (error["details"]["step"], error["details"]["reason"], error["details"]["recovered"]))
        self.assertEqual(original, self.server_sales())
        self.assertEqual(2, len(self.writer.calls))  # The deploy and the restore of the backup.


@unittest.skipUnless(BRIDGE.is_file(), "TOM bridge not built")
class CloudTargetRealGuardTests(CloudTargetTestCase):
    """The acceptance case with the real plan, the real guard and the real promotion on the working copy."""

    def setUp(self) -> None:
        super().setUp()
        self.service = ApplyService(self.devcenter, desktop=FakeDesktop())
        self.devcenter.apply_service = self.service

    def test_real_guard_two_local_donors_to_a_cloud_model(self) -> None:
        self.target()
        self.choose(MARGIN)
        original = self.server_sales()
        preview = self.get("apply/preview")
        self.assertTrue(preview["ready"], preview)
        reply = self.apply()
        self.assertNotIn("error", reply, reply)
        self.assertEqual([], reply["rescan_differences"])
        self.assertIn(NEW_MARGIN, self.server_sales())
        self.ok("undo_apply", {"base_revision": self.rev})
        self.assertEqual(original, self.server_sales())

    def test_real_guard_cloud_model_and_cloud_report(self) -> None:
        report = self.ok("cloud_connect", {"base_revision": self.rev, "kind": "report", "workspace_id": WS_SALES, "item_id": REPORT_OK,
                                           "access_type": "Read/Write"})["source"]["source_id"]
        self.target({"mode": "existing", "source_id": report})
        self.choose(MARGIN, PAGE)
        preview = self.get("apply/preview")
        self.assertTrue(preview["ready"], preview)
        reply = self.apply()
        self.assertNotIn("error", reply, reply)
        self.assertEqual([], reply["rescan_differences"])
        self.assertIn("definition/pages/summary/page.json", {part["path"] for part in self.http.parts})


class CloudWriteHelperTests(unittest.TestCase):
    def test_definition_parts_are_the_inverse_of_the_folder(self) -> None:
        parts = definition_parts(LAB / "SalesA" / "SalesA.Report")
        self.assertNotIn(".platform", [part["path"] for part in parts])
        page = next(part for part in parts if part["path"] == "definition.pbir")
        self.assertEqual((LAB / "SalesA" / "SalesA.Report" / "definition.pbir").read_bytes(), base64.b64decode(page["payload"]))

    def test_deploy_reply_of_the_bridge(self) -> None:
        self.assertEqual(ModelDeploy(LSU_1, LSU_DEPLOY), deploy_from_bridge(
            {"adapter_version": 1, "command": "cloud-deploy", "status": "PASSED", "last_schema_update_before": LSU_1,
             "last_schema_update": LSU_DEPLOY}))
        with self.assertRaises(CloudReadFailed) as caught:
            deploy_from_bridge({"adapter_version": 1, "command": "cloud-deploy", "status": "FAILED", "code": "target_changed"})
        self.assertEqual("target_changed", caught.exception.code)

    @unittest.skipUnless(BRIDGE.is_file(), "TOM bridge not built")
    def test_bridge_cloud_deploy_refuses_a_server_that_is_not_a_workspace(self) -> None:
        request = {"server": "localhost", "database": MODEL, "access_token": "x", "expires_on": 4102444800, "folder": str(LAB)}
        result = subprocess.run(["dotnet", str(BRIDGE), "cloud-deploy"], input=json.dumps(request), capture_output=True, text=True,
                                encoding="utf-8", timeout=120, check=False)
        payload = json.loads(result.stdout)
        self.assertEqual(("FAILED", "invalid_request"), (payload["status"], payload["code"]))
        self.assertNotIn("x", payload.get("error", "").split())


if __name__ == "__main__":
    unittest.main()
