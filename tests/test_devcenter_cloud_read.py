"""Build step S11: cloud read with fakes only (technical design section 16, S11).

No test makes a network call. Fakes replace the token provider, the Power BI
and Fabric REST APIs, and the XMLA reader. The bridge tests run ``cloud-read``
with requests that fail before the connect step.
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import shutil
import tempfile
import time
import unittest
from unittest.mock import patch

from backend.adapters.tabular_metadata import TabularMetadataAdapter
from backend.devcenter import contracts, http_routes, jsapi
from backend.devcenter.session.manager import DevCenterSessions
from backend.devcenter.session.secrets import find_secrets
from backend.devcenter.sources import cloud_auth
from backend.devcenter.sources.cloud import (
    FABRIC_API,
    NOT_CHECKED_TEXT,
    POWER_BI_API,
    REASON_OTHER_WORKSPACES,
    REASON_REPORT_NOT_READABLE,
    BridgeCloudModelReader,
    CloudReadFailed,
    CloudService,
    HttpReply,
    ModelExport,
    parse_workspace_connection,
)
from backend.devcenter.sources.cloud_auth import AccessToken, Account, MsalTokenProvider, SignInRequired
from backend.devcenter.sources.cloud_jsapi_methods import S11_METHODS
from backend.devcenter.sources.kinds import PBIP, PBIR_REPORT, detect_local_source, require_model_target
from backend.devcenter.sources.objects import object_index

REPOSITORY = Path(__file__).resolve().parents[1]
LAB = REPOSITORY / "tests" / "fixtures" / "merge_lab"
RECORDED = REPOSITORY / "tests" / "fixtures" / "devcenter_cloud"
BRIDGE = REPOSITORY / "backend/adapters/tabular_metadata/dotnet/bin/Release/net8.0/TabularMetadata.dll"

TENANT = "0b9e7f4e-1d1c-4c55-9a51-3c1f1b9a7d01"
OBJECT_ID = "6f2d0c1a-7e7b-4f0e-8c3b-2a9d5e4f1b02"
WS_SALES = "11111111-2222-4333-8444-555555555501"
WS_SHARED = "11111111-2222-4333-8444-555555555502"
CAPACITY = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeee01"
MODEL = "22222222-3333-4444-8555-666666666601"
PUSH_MODEL = "22222222-3333-4444-8555-666666666602"
REPORT_OK = "33333333-4444-4555-8666-777777777701"
REPORT_LOCKED = "33333333-4444-4555-8666-777777777702"
REPORT_RECORDED = "33333333-4444-4555-8666-777777777703"
REPORT_OTHER_MODEL = "33333333-4444-4555-8666-777777777704"
ACCOUNT_NAME = "Avery Quinn Contoso"
LSU_1 = "2026-10-28T09:12:33Z"
LSU_2 = "2026-10-30T14:00:00Z"


def fake_token(number: int) -> str:
    """A token-like value that the secret check finds when it leaks into a file."""

    body = base64.urlsafe_b64encode(json.dumps({"n": number, "kind": "fakeAccessToken"}).encode()).decode().rstrip("=")
    return f"eyJhbGciOiJub25lIn0.{body}.ZmFrZVNpZ25hdHVyZTEyMzQ{number}"


class FakeTokens:
    """A fake ``TokenProvider``: it counts silent and interactive calls."""

    def __init__(self, *, signed_in: bool = True) -> None:
        self.signed_in = signed_in
        self.calls: list[tuple[str, str | None]] = []
        self.issued: list[str] = []
        self._account = Account(ACCOUNT_NAME, TENANT, OBJECT_ID) if signed_in else None
        self.current: AccessToken | None = None

    def sign_in(self, scopes, *, prompt=None) -> Account:
        if prompt != "select_account":
            self.calls.append(("silent", None))
            if self.signed_in:
                return self._account
            if prompt == "none":
                raise SignInRequired()
        self.calls.append(("interactive", prompt))
        self.signed_in = True
        self._account = Account(ACCOUNT_NAME, TENANT, OBJECT_ID)
        return self._account

    def token(self, scopes, *, force_refresh=False) -> AccessToken:
        if not self.signed_in:
            raise SignInRequired()
        self.calls.append(("refresh" if force_refresh else "token", None))
        if force_refresh or self.current is None:
            self.issued.append(fake_token(len(self.issued) + 1))
            self.current = AccessToken(self.issued[-1], int(time.time()) + 3600)
        return self.current

    def account(self) -> Account | None:
        return self._account


def report_parts(report_dir: Path) -> list[dict]:
    """The parts of a cloud report: the fixture files, with ``definition.pbir`` bound byConnection."""

    parts = []
    for path in sorted(report_dir.rglob("*")):
        if path.is_file() and path.name not in {".platform", "definition.pbir"}:
            parts.append({"path": path.relative_to(report_dir).as_posix(), "payload": base64.b64encode(path.read_bytes()).decode(),
                          "payloadType": "InlineBase64"})
    pbir = {"version": "4.0", "datasetReference": {"byConnection": {"connectionString": "Data Source=powerbi://api.powerbi.com/v1.0/myorg/Sales Analytics"}}}
    parts.append({"path": "definition.pbir", "payload": base64.b64encode(json.dumps(pbir).encode()).decode(), "payloadType": "InlineBase64"})
    return parts


class FakeCloud:
    """Fake Power BI and Fabric REST APIs (``CloudHttp``)."""

    def __init__(self, report_dir: Path) -> None:
        self.parts = report_parts(report_dir)
        self.requests: list[tuple[str, str, str]] = []
        self.expired: set[str] = set()
        self.always_expired = False
        self.queue: list[dict] = []
        self.groups = [
            {"id": WS_SALES, "name": "Sales Analytics", "isOnDedicatedCapacity": True, "capacityId": CAPACITY.upper()},
            {"id": WS_SHARED, "name": "My shared space", "isOnDedicatedCapacity": False},
        ]
        self.capacities = [{"id": CAPACITY, "displayName": "Capacity one", "sku": "F64", "state": "Active"}]
        self.datasets = {
            WS_SALES: [
                {"id": MODEL, "name": "Sales Cloud", "configuredBy": "owner", "addRowsAPIEnabled": False, "createdDate": "2026-10-28T09:12:33.123Z"},
                {"id": PUSH_MODEL, "name": "Sales Push", "addRowsAPIEnabled": True, "createdDate": "2026-10-12T08:00:00.000Z"},
            ],
            WS_SHARED: [{"id": "22222222-3333-4444-8555-666666666609", "name": "Small model", "addRowsAPIEnabled": False}],
        }
        self.reports = {
            WS_SALES: [
                {"id": REPORT_OK, "name": "Sales Overview", "datasetId": MODEL, "reportType": "PowerBIReport", "format": "PBIR"},
                {"id": REPORT_LOCKED, "name": "Sales Board", "datasetId": MODEL, "reportType": "PowerBIReport", "format": "PBIR"},
                {"id": REPORT_RECORDED, "name": "Sales Detail", "datasetId": "22222222-3333-4444-8555-666666666699", "reportType": "PowerBIReport"},
                {"id": REPORT_OTHER_MODEL, "name": "Push Board", "datasetId": PUSH_MODEL, "reportType": "PowerBIReport", "format": "PBIRLegacy"},
                {"id": "33333333-4444-4555-8666-777777777709", "name": "Paginated", "datasetId": MODEL, "reportType": "PaginatedReport"},
            ],
            WS_SHARED: [],
        }
        self.definitions = {REPORT_OK: "ok", REPORT_LOCKED: "get_definition_403.json", REPORT_RECORDED: "get_definition_202.json",
                            REPORT_OTHER_MODEL: "ok"}
        self.roles = {WS_SALES: [{"principal": {"id": OBJECT_ID, "type": "User"}, "role": "Contributor"}]}

    def _recorded(self, name: str) -> list[dict]:
        replies = json.loads((RECORDED / name).read_text(encoding="utf-8"))["replies"]
        for reply in replies:
            body = reply.get("body")
            if isinstance(body, dict) and (body.get("definition") or {}).get("parts") == "@report":
                body["definition"]["parts"] = self.parts
        return replies

    def send(self, method: str, url: str, token: AccessToken, body=None) -> HttpReply:
        self.requests.append((method, url, token.value))
        if self.always_expired or token.value in self.expired:
            return HttpReply(401, {}, {"error": {"code": "TokenExpired"}})
        if self.queue and self.queue[0].get("url") == url and self.queue[0]["method"] == method:
            reply = self.queue.pop(0)
            return HttpReply(reply["status"], reply.get("headers") or {}, reply.get("body"))
        value = lambda items: HttpReply(200, {}, {"value": items})  # noqa: E731
        if method == "GET" and url == f"{POWER_BI_API}/groups":
            return value(self.groups)
        if method == "GET" and url == f"{POWER_BI_API}/capacities":
            return value(self.capacities)
        for workspace in self.datasets:
            if method == "GET" and url == f"{POWER_BI_API}/groups/{workspace}/datasets":
                return value(self.datasets[workspace])
            if method == "GET" and url == f"{POWER_BI_API}/groups/{workspace}/reports":
                return value(self.reports[workspace])
            if method == "GET" and url == f"{FABRIC_API}/workspaces/{workspace}/roleAssignments":
                return value(self.roles[workspace]) if workspace in self.roles else HttpReply(403, {}, None)
            for report, script in self.definitions.items():
                if method == "POST" and url == f"{FABRIC_API}/workspaces/{workspace}/reports/{report}/getDefinition":
                    if script == "ok":
                        return HttpReply(200, {}, {"definition": {"parts": self.parts}})
                    replies = self._recorded(script)
                    self.queue = replies[1:]
                    first = replies[0]
                    return HttpReply(first["status"], first.get("headers") or {}, first.get("body"))
        return HttpReply(404, {}, {"error": {"code": "NotFound"}})


class FakeReader:
    """A fake XMLA server: ``cloud-read`` gives the TMDL of a local folder."""

    def __init__(self, model_dir: Path) -> None:
        self.model_dir = model_dir
        self.last_schema_update = LSU_1
        self.calls: list[tuple[str, str, str]] = []
        self.expire_next = False
        self.fail_code: str | None = None

    def read(self, server: str, database: str, token: AccessToken, folder: Path) -> ModelExport:
        self.calls.append((server, database, token.value))
        if self.expire_next:
            self.expire_next = False
            raise CloudReadFailed("token_expired")
        if self.fail_code:
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "partial.tmdl").write_text("partial", encoding="utf-8")
            raise CloudReadFailed(self.fail_code)
        if database != MODEL:
            raise CloudReadFailed("not_found")
        shutil.copytree(self.model_dir / "definition", folder)
        text = "".join(path.read_text(encoding="utf-8") for path in folder.rglob("*.tmdl"))
        return ModelExport("Sales Cloud", self.last_schema_update, len(list((folder / "tables").glob("*.tmdl"))),
                           text.count("\tmeasure "))


class CloudTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.root = self.base / "project"
        self.app_data = self.base / "appdata"
        shutil.copytree(LAB / "SalesA", self.root / "SalesA")
        # The fake server has its own copy of the model, so that a test can change it.
        self.server_model = self.base / "server" / "SalesCloud.SemanticModel"
        shutil.copytree(LAB / "SalesA" / "SalesA.SemanticModel", self.server_model)
        self.tokens = FakeTokens()
        self.http = FakeCloud(LAB / "SalesA" / "SalesA.Report")
        self.reader = FakeReader(self.server_model)
        self.sleeps: list[float] = []
        self.service = CloudService(self.tokens, self.http, self.reader, sleep=self.sleeps.append)
        self.devcenter = DevCenterSessions(app_data_dir=self.app_data, cloud=self.service)
        self.devcenter.attach_project(self.root)

    def tearDown(self) -> None:
        self.devcenter.close()
        self.temporary.cleanup()

    def call(self, method: str, request: dict | None = None) -> dict:
        reply = jsapi.call(self.devcenter, method, request)
        name = contracts.ERROR if "error" in reply else contracts.jsapi_reply(method)
        self.assertEqual([], contracts.errors(name, reply), reply)
        return reply

    def ok(self, method: str, request: dict | None = None) -> dict:
        reply = self.call(method, request)
        self.assertNotIn("error", reply, reply)
        return reply

    def failed(self, method: str, request: dict | None = None, *, code: str) -> dict:
        reply = self.call(method, request)
        self.assertIn("error", reply, reply)
        self.assertEqual(code, reply["error"]["code"], reply)
        return reply["error"]

    def create(self) -> dict:
        return self.ok("session_create", {"display_name": "Cloud merge"})

    def connect_model(self, **extra) -> dict:
        return self.ok("cloud_connect", {"base_revision": self.devcenter.revision, "kind": "model", "workspace_id": WS_SALES,
                                         "item_id": MODEL, **extra})

    def session_file(self) -> dict:
        return json.loads((self.devcenter.session_folder() / "session.json").read_text(encoding="utf-8"))

    def assert_no_secret_files(self) -> None:
        """Scan test: no file under the project or the app data holds a token or the account name."""

        files = [path for folder in (self.root, self.app_data) for path in folder.rglob("*") if path.is_file()]
        self.assertTrue(any(path.name == "session.json" for path in files))
        self.assertTrue(any(path.name == "connection.json" for path in files))
        for path in files:
            text = path.read_bytes().decode("utf-8", errors="replace")
            for token in self.tokens.issued:
                self.assertNotIn(token, text, path)
            self.assertNotIn(ACCOUNT_NAME, text, path)
            if path.name in {"session.json", "log.jsonl", "connection.json"}:
                for line in text.splitlines() if path.suffix == ".jsonl" else [text]:
                    self.assertEqual([], find_secrets(json.loads(line)), path)


class TokenFlowTests(CloudTestCase):
    def test_msal_provider_tries_silent_first_then_interactive(self):
        events: list[str] = []

        class FakeMsal:
            CONSOLE_WINDOW_HANDLE = object()

            def __init__(self) -> None:
                self.accounts: list[dict] = []

            def get_accounts(self):
                events.append("get_accounts")
                return list(self.accounts)

            def acquire_token_silent(self, scopes, account, force_refresh=False):
                events.append("silent_refresh" if force_refresh else "silent")
                return {"access_token": fake_token(9), "expires_in": 3600}

            def acquire_token_interactive(self, scopes, prompt=None, parent_window_handle=None):
                events.append(f"interactive:{prompt}")
                self.accounts = [{"username": "user", "home_account_id": f"{OBJECT_ID}.{TENANT}", "realm": TENANT}]
                return {"access_token": fake_token(8), "expires_in": 3600,
                        "id_token_claims": {"name": ACCOUNT_NAME, "tid": TENANT, "oid": OBJECT_ID}}

        provider = MsalTokenProvider(cloud_auth.CloudSettings("app-id-from-settings", "https://login.microsoftonline.com/organizations"))
        provider._application = FakeMsal()
        with self.assertRaises(SignInRequired):
            provider.sign_in(cloud_auth.POWER_BI_SCOPES, prompt="none")
        self.assertNotIn("interactive:None", events)
        account = provider.sign_in(cloud_auth.POWER_BI_SCOPES)
        self.assertEqual(ACCOUNT_NAME, account.display_name)
        self.assertEqual(["get_accounts", "get_accounts", "interactive:None", "get_accounts"], events)
        events.clear()
        token = provider.token(cloud_auth.POWER_BI_SCOPES)
        self.assertEqual(["silent"], events)
        self.assertNotIn(token.value, repr(token))
        provider.token(cloud_auth.POWER_BI_SCOPES, force_refresh=True)
        self.assertEqual(["silent", "silent_refresh"], events)
        events.clear()
        provider.sign_in(cloud_auth.POWER_BI_SCOPES, prompt="select_account")
        self.assertEqual(["interactive:select_account", "get_accounts"], events)

    def test_sign_in_needs_a_client_id_from_the_settings(self):
        with patch.dict(os.environ, {cloud_auth.SETTINGS_ENV: ""}):
            with self.assertRaises(Exception) as caught:
                cloud_auth.cloud_settings(self.base / "missing.json")
            self.assertEqual("client_id_missing", caught.exception.details["reason"])
            settings = self.base / "settings.json"
            settings.write_text(json.dumps({"cloud": {"client_id": "app-id-from-settings"}}), encoding="utf-8")
            self.assertEqual("app-id-from-settings", cloud_auth.cloud_settings(settings).client_id)

    def test_sign_in_reply_silent_then_interactive(self):
        self.tokens = FakeTokens(signed_in=False)
        self.service._tokens = self.tokens
        reply = self.ok("cloud_sign_in", {"prompt": "none"})
        self.assertEqual({"revision": None, "signed_in": False, "account_name": None, "reason": "interaction_required"}, reply)
        reply = self.ok("cloud_sign_in", {})
        self.assertTrue(reply["signed_in"])
        self.assertEqual([("silent", None), ("silent", None), ("interactive", None)], self.tokens.calls)
        self.assertEqual(ACCOUNT_NAME, reply["account_name"])

    def test_no_token_and_no_account_name_in_any_file(self):
        self.ok("cloud_sign_in", {})
        self.create()
        (self.root / ".pbibrain" / "connection.json").write_text(json.dumps({"connection_id": "c-1"}), encoding="utf-8")
        self.connect_model()
        self.ok("cloud_connect", {"base_revision": self.devcenter.revision, "kind": "report", "workspace_id": WS_SALES, "item_id": REPORT_OK})
        self.ok("sources_check", {"base_revision": self.devcenter.revision})
        model = self.session_file()["sources"][0]
        self.ok("pull_to_local", {"base_revision": self.devcenter.revision, "source_id": model["source_id"],
                                  "path": str(self.root / "models" / "Sales Cloud")})
        self.assertTrue(self.tokens.issued)
        self.assert_no_secret_files()


class ExpiredTokenTests(CloudTestCase):
    def test_http_401_gives_one_silent_refresh_and_one_retry(self):
        self.tokens.token(cloud_auth.POWER_BI_SCOPES)
        self.http.expired.add(self.tokens.current.value)
        self.tokens.calls.clear()
        self.ok("cloud_items_list", {"kind": "workspaces"})
        self.assertEqual([("token", None), ("refresh", None), ("token", None)], self.tokens.calls)
        self.assertEqual(2, len([item for item in self.http.requests if item[1] == f"{POWER_BI_API}/groups"]))

    def test_a_second_401_stops_after_one_refresh(self):
        self.http.always_expired = True
        error = self.failed("cloud_items_list", {"kind": "workspaces"}, code="action_not_allowed")
        self.assertEqual("sign_in_required", error["details"]["reason"])
        self.assertEqual(1, sum(1 for call in self.tokens.calls if call[0] == "refresh"))
        self.assertEqual(2, len(self.http.requests))

    def test_bridge_token_expired_gives_one_refresh_and_a_retry(self):
        self.create()
        self.reader.expire_next = True
        reply = self.connect_model()
        self.assertTrue(reply["added"])
        self.assertEqual(2, len(self.reader.calls))
        self.assertNotEqual(self.reader.calls[0][2], self.reader.calls[1][2])
        self.assertEqual(1, sum(1 for call in self.tokens.calls if call[0] == "refresh"))


class CloudModelDonorTests(CloudTestCase):
    def test_cloud_read_gives_a_tmdl_donor_that_scans(self):
        self.create()
        reply = self.connect_model()
        source = reply["source"]
        self.assertEqual(("cloud_model", "donor", "Read", None), (source["kind"], source["role"], source["access_type"], source["path"]))
        self.assertEqual({"tenant_id": TENANT, "workspace_id": WS_SALES, "workspace_name": "Sales Analytics", "item_id": MODEL,
                          "dataset_id": None, "last_schema_update": LSU_1}, source["cloud"])
        self.assertEqual("powerbi://api.powerbi.com/v1.0/myorg/Sales Analytics", self.reader.calls[0][0])
        cache = self.devcenter.session_folder() / "tmp" / "cloud" / MODEL
        loaded = detect_local_source(cache)
        index = object_index(loaded)
        self.assertIn("measure:Sales/Total Sales", index)
        self.assertEqual(index, self.session_file()["row_hashes"][source["source_id"]])
        if BRIDGE.is_file():
            self.assertEqual("PASSED", TabularMetadataAdapter(BRIDGE).read(cache)["status"])
        summary = self.devcenter.session_summary()
        self.assertEqual([], contracts.errors("http/session.reply.json", summary))

    def test_a_cloud_model_cannot_be_a_target(self):
        self.create()
        source = self.connect_model()["source"]
        error = self.failed("target_set", {"base_revision": self.devcenter.revision,
                                           "model": {"mode": "existing", "source_id": source["source_id"]}}, code="action_not_allowed")
        self.assertEqual(("Pull to local PBIP first.", "cloud_target"), (error["message"], error["details"]["reason"]))

    def test_the_same_cloud_item_two_times_is_refused(self):
        self.create()
        self.connect_model()
        error = self.failed("cloud_connect", {"base_revision": self.devcenter.revision, "kind": "model", "workspace_id": WS_SALES,
                                              "item_id": MODEL}, code="action_not_allowed")
        self.assertEqual("duplicate_source", error["details"]["reason"])

    def test_paste_a_workspace_connection(self):
        self.create()
        self.assertEqual("Sales Analytics", parse_workspace_connection("powerbi://api.powerbi.com/v1.0/myorg/Sales%20Analytics"))
        error = self.failed("cloud_connect", {"base_revision": self.devcenter.revision, "kind": "model",
                                              "workspace_connection": "https://app.powerbi.com/groups/x", "item_name": "Sales Cloud"},
                            code="invalid_payload")
        self.assertEqual("bad_connection", error["details"]["reason"])
        error = self.failed("cloud_connect", {"base_revision": self.devcenter.revision, "kind": "model",
                                              "workspace_connection": "powerbi://api.powerbi.com/v1.0/myorg/Sales Analytics",
                                              "item_name": "No such model"}, code="not_found")
        self.assertEqual("model_not_found", error["details"]["reason"])
        reply = self.ok("cloud_connect", {"base_revision": self.devcenter.revision, "kind": "model",
                                          "workspace_connection": "powerbi://api.powerbi.com/v1.0/myorg/Sales Analytics",
                                          "item_name": "sales cloud", "access_type": "Read/Write"})
        self.assertEqual("Read/Write", reply["source"]["access_type"])


class PullToLocalTests(CloudTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.create()
        self.model = self.connect_model()["source"]

    def pull(self, folder: Path, **extra) -> dict:
        return self.call("pull_to_local", {"base_revision": self.devcenter.revision, "source_id": self.model["source_id"],
                                           "path": str(folder), **extra})

    def test_pull_writes_a_pbip_that_the_local_loader_opens_as_a_target(self):
        folder = self.root / "models" / "Sales Cloud"
        reply = self.pull(folder, as_target=True)
        self.assertNotIn("error", reply, reply)
        source = reply["source"]
        self.assertEqual(("pbip", "models/Sales Cloud/Sales Cloud.pbip"), (source["kind"], source["path"]))
        self.assertEqual({"model": {"mode": "existing", "source_id": source["source_id"]},
                          "report": {"mode": "existing", "source_id": source["source_id"]}}, reply["target"])
        local = detect_local_source(folder / "Sales Cloud.pbip")
        self.assertEqual(PBIP, local.kind)
        require_model_target(local)
        self.assertIn("measure:Sales/Total Sales", object_index(local))
        if BRIDGE.is_file():
            self.assertEqual("PASSED", TabularMetadataAdapter(BRIDGE).read(local.model_dir / "definition")["status"])
        cloud = [item for item in self.session_file()["sources"] if item["kind"] == "cloud_model"]
        self.assertEqual(1, len(cloud), "The cloud source stays in the session")

    def test_a_failed_pull_leaves_no_partial_folder(self):
        new_folder = self.root / "models" / "New"
        self.reader.fail_code = "read_failed"
        revision = self.devcenter.revision
        self.assertEqual("model_not_readable", self.pull(new_folder)["error"]["details"]["reason"])
        self.assertFalse(new_folder.exists())
        self.assertEqual([], [path.name for path in (self.root / "models").iterdir()])
        empty = self.root / "models" / "Empty"
        empty.mkdir()
        self.assertIn("error", self.pull(empty))
        self.assertTrue(empty.is_dir())
        self.assertEqual([], list(empty.iterdir()))
        self.assertEqual(revision, self.devcenter.revision)

    def test_a_folder_that_is_not_empty_is_refused(self):
        folder = self.root / "models" / "Busy"
        folder.mkdir(parents=True)
        (folder / "note.txt").write_text("keep", encoding="utf-8")
        reply = self.pull(folder)
        self.assertEqual("folder_not_empty", reply["error"]["details"]["reason"])
        self.assertEqual(["note.txt"], [path.name for path in folder.iterdir()])
        self.assertEqual([], self.reader.calls[1:])

    def test_only_a_cloud_model_can_be_pulled(self):
        local = self.ok("source_add", {"base_revision": self.devcenter.revision, "path": str(self.root / "SalesA/SalesA.pbip")})["source"]
        reply = self.call("pull_to_local", {"base_revision": self.devcenter.revision, "source_id": local["source_id"],
                                            "path": str(self.root / "models" / "X")})
        self.assertEqual("not_cloud_model", reply["error"]["details"]["reason"])


class CloudReportTests(CloudTestCase):
    def test_get_definition_202_polls_the_recorded_operation(self):
        parts = self.service.definition(WS_SALES, REPORT_RECORDED)
        self.assertEqual([2.0, 1.0], self.sleeps)
        self.assertEqual(len(self.http.parts), len(parts))
        urls = [url for _method, url, _token in self.http.requests]
        self.assertEqual([f"{FABRIC_API}/workspaces/{WS_SALES}/reports/{REPORT_RECORDED}/getDefinition",
                          f"{FABRIC_API}/operations/op-0001", f"{FABRIC_API}/operations/op-0001",
                          f"{FABRIC_API}/operations/op-0001/result"], urls)

    def test_a_cloud_report_with_202_is_added_as_a_pbir_source(self):
        self.create()
        reply = self.ok("cloud_connect", {"base_revision": self.devcenter.revision, "kind": "report", "workspace_id": WS_SALES,
                                          "item_id": REPORT_RECORDED})
        self.assertTrue(reply["added"])
        self.assertEqual(("cloud_report", "pbir"), (reply["source"]["kind"], reply["source"]["report_format"]))
        loaded = detect_local_source(self.devcenter.session_folder() / "tmp" / "cloud" / REPORT_RECORDED)
        self.assertEqual(PBIR_REPORT, loaded.kind)
        self.assertTrue(any(key.startswith("visual:") for key in object_index(loaded)))

    def test_403_gives_not_checked_report_not_readable_and_no_add(self):
        self.create()
        revision = self.devcenter.revision
        reply = self.ok("cloud_connect", {"base_revision": revision, "kind": "report", "workspace_id": WS_SALES, "item_id": REPORT_LOCKED})
        self.assertFalse(reply["added"])
        self.assertIsNone(reply["source"])
        self.assertEqual(revision, reply["revision"])
        line = next(item for item in reply["checks"] if item["check_id"] == "report_definition")
        self.assertEqual(("failed", REASON_REPORT_NOT_READABLE, "export the report to a local PBIP"),
                         (line["result"], line["reason"], line["values"]["fix"]))
        self.assertEqual("not checked: report not readable", NOT_CHECKED_TEXT[REASON_REPORT_NOT_READABLE])
        self.assertEqual([], [path for path in (self.devcenter.session_folder() / "tmp" / "cloud").iterdir()])

    def test_reports_in_group_filter_by_dataset_id(self):
        coverage = self.service.report_coverage(WS_SALES, MODEL)
        self.assertEqual([("Sales Board", False), ("Sales Overview", True)],
                         [(item["name"], item["readable"]) for item in coverage["reports"]])
        self.assertEqual([(REASON_REPORT_NOT_READABLE, "Sales Board", "not checked: report not readable"),
                          (REASON_OTHER_WORKSPACES, None, "not checked: reports in other workspaces")],
                         [(item["reason"], item["name"], item["text"]) for item in coverage["not_checked"]])
        requested = {url for _method, url, _token in self.http.requests}
        self.assertNotIn(f"{FABRIC_API}/workspaces/{WS_SALES}/reports/{REPORT_OTHER_MODEL}/getDefinition", requested)


class FingerprintTests(CloudTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.create()
        self.source = self.connect_model()["source"]

    def change_server_model(self) -> None:
        path = self.server_model / "definition" / "tables" / "Sales.tmdl"
        text = path.read_text(encoding="utf-8")
        path.write_text(text.replace("measure 'Total Sales' = SUM(Sales[Amount])", "measure 'Total Sales' = SUM(Sales[Amount]) * 2"),
                        encoding="utf-8")

    def test_last_schema_update_change_marks_the_source(self):
        self.change_server_model()
        self.reader.last_schema_update = LSU_2
        reply = self.ok("sources_check", {"base_revision": self.devcenter.revision})
        self.assertEqual(1, reply["mark_count"])
        self.assertEqual([{"source_id": self.source["source_id"], "row_key": "measure:Sales/Total Sales", "mark": "source_changed"}],
                         self.devcenter.marks())
        view = self.devcenter.session_summary()["sources"][0]
        self.assertEqual(("ok", "changed"), (view["status"], view["fingerprint_state"]))
        self.assertEqual(LSU_2, self.session_file()["sources"][0]["cloud"]["last_schema_update"])
        self.ok("row_confirm", {"base_revision": self.devcenter.revision, "row_keys": ["measure:Sales/Total Sales"]})
        self.assertEqual([], self.devcenter.marks())

    def test_the_same_last_schema_update_gives_no_mark(self):
        self.change_server_model()
        reply = self.ok("sources_check", {"base_revision": self.devcenter.revision})
        self.assertEqual(0, reply["mark_count"])
        self.assertEqual("same", self.devcenter.session_summary()["sources"][0]["fingerprint_state"])

    def test_a_failed_read_makes_the_cloud_source_unreadable(self):
        self.reader.fail_code = "connect_failed"
        reply = self.ok("sources_check", {"base_revision": self.devcenter.revision})
        self.assertEqual("unreadable", reply["sources"][0]["status"])
        names = [path.name for path in (self.devcenter.session_folder() / "tmp" / "cloud").iterdir()]
        self.assertIn(MODEL, names, "The old export stays")
        self.assertEqual([], [name for name in names if name.endswith(".tmp")], "No partial folder stays")

    def test_no_token_makes_the_cloud_source_unreadable_with_no_window(self):
        self.tokens.signed_in = False
        reply = self.ok("sources_check", {"base_revision": self.devcenter.revision})
        self.assertEqual("unreadable", reply["sources"][0]["status"])
        self.assertNotIn("interactive", [call[0] for call in self.tokens.calls])
        self.assertEqual("not_checked", self.devcenter.session_summary()["sources"][0]["fingerprint_state"])


class ItemsAndConnectTests(CloudTestCase):
    def test_cloud_items_list_gives_the_fields_of_each_kind(self):
        workspaces = self.ok("cloud_items_list", {"kind": "workspaces"})
        self.assertEqual([
            {"id": WS_SHARED, "name": "My shared space", "capacity_type": "shared", "xmla_available": False},
            {"id": WS_SALES, "name": "Sales Analytics", "capacity_type": "fabric", "xmla_available": True},
        ], workspaces["items"])
        models = self.ok("cloud_items_list", {"kind": "models", "workspace_id": WS_SALES})
        self.assertEqual([
            {"id": MODEL, "name": "Sales Cloud", "updated_at": "2026-10-28T09:12:33Z", "model_type": "semantic_model",
             "xmla_readable": True, "reason": None},
            {"id": PUSH_MODEL, "name": "Sales Push", "updated_at": "2026-10-12T08:00:00Z", "model_type": "push",
             "xmla_readable": False, "reason": "push_model"},
        ], models["items"])
        shared = self.ok("cloud_items_list", {"kind": "models", "workspace_id": WS_SHARED})
        self.assertEqual(["workspace_not_on_capacity"], [item["reason"] for item in shared["items"]])
        reports = self.ok("cloud_items_list", {"kind": "reports", "workspace_id": WS_SALES})
        self.assertEqual([("Push Board", "pbir_legacy", PUSH_MODEL), ("Sales Board", "pbir", MODEL), ("Sales Detail", None, reports["items"][2]["dataset_id"]),
                          ("Sales Overview", "pbir", MODEL)], [(item["name"], item["format"], item["dataset_id"]) for item in reports["items"]])
        self.assertIsNone(reports["revision"])
        self.create()
        self.assertEqual(self.devcenter.revision, self.ok("cloud_items_list", {"kind": "workspaces"})["revision"])
        self.failed("cloud_items_list", {"kind": "models"}, code="invalid_payload")

    def test_no_http_route_gives_cloud_data(self):
        for route in http_routes.ROUTES:
            self.assertFalse(any("cloud" in part for part in route.path), route.path)
        for parts in (["cloud-items"], ["cloud_items_list"], ["cloud", "workspaces"]):
            status, _payload = http_routes.dispatch(object(), "GET", parts, {}, None)
            self.assertEqual(404, status)
        for method in S11_METHODS:
            self.assertIn(method, jsapi.METHODS)

    def test_sign_in_with_select_account_returns_the_display_name(self):
        reply = self.ok("cloud_sign_in", {"prompt": "select_account"})
        self.assertEqual({"revision": None, "signed_in": True, "account_name": ACCOUNT_NAME, "reason": None}, reply)
        self.assertEqual([("interactive", "select_account")], self.tokens.calls)
        self.create()
        (self.root / ".pbibrain" / "connection.json").write_text(json.dumps({"connection_id": "c-1"}), encoding="utf-8")
        self.connect_model()
        self.assert_no_secret_files()

    def test_connect_reply_has_the_test_lines(self):
        self.create()
        revision = self.devcenter.revision
        test = self.ok("cloud_connect", {"kind": "model", "workspace_id": WS_SALES, "item_id": MODEL, "add": False})
        self.assertEqual((False, None, revision), (test["added"], test["source"], test["revision"]))
        self.assertEqual(revision, self.devcenter.revision)
        reply = self.connect_model()
        lines = {item["check_id"]: (item["result"], item["reason"], item["values"]) for item in reply["checks"]}
        self.assertEqual([item["check_id"] for item in test["checks"]], [item["check_id"] for item in reply["checks"]])
        self.assertEqual(("ok", None, {"account_name": ACCOUNT_NAME}), lines["sign_in"])
        self.assertEqual(("ok", None, {"capacity_type": "fabric"}), lines["capacity"])
        self.assertEqual(("ok", None, {}), lines["xmla_connect"])
        self.assertEqual("ok", lines["model_read"][0])
        self.assertEqual({"table_count": 5, "measure_count": lines["model_read"][2]["measure_count"]}, lines["model_read"][2])
        self.assertGreater(lines["model_read"][2]["measure_count"], 3)
        self.assertEqual(("ok", None, {"role": "Contributor"}), lines["role"])
        self.assertEqual(("ok", REASON_REPORT_NOT_READABLE, {"report_count": 2, "readable_count": 1, "unreadable_names": ["Sales Board"]}),
                         lines["reports_in_workspace"])
        self.assertEqual(("not_checked", REASON_OTHER_WORKSPACES, {}), lines["reports_other_workspaces"])
        self.assertEqual(("not_checked", "write_not_in_version_1", {}), lines["write_conditions"])

    def test_connect_failures_give_failed_lines_and_no_add(self):
        self.create()
        revision = self.devcenter.revision
        shared = self.ok("cloud_connect", {"base_revision": revision, "kind": "model", "workspace_id": WS_SHARED,
                                           "item_id": "22222222-3333-4444-8555-666666666609"})
        self.assertFalse(shared["added"])
        self.assertIn(("capacity", "failed", "workspace_not_on_capacity"),
                      [(item["check_id"], item["result"], item["reason"]) for item in shared["checks"]])
        push = self.ok("cloud_connect", {"base_revision": revision, "kind": "model", "workspace_id": WS_SALES, "item_id": PUSH_MODEL})
        self.assertIn(("model_read", "failed", "push_model"), [(item["check_id"], item["result"], item["reason"]) for item in push["checks"]])
        self.reader.fail_code = "connect_failed"
        xmla = self.ok("cloud_connect", {"base_revision": revision, "kind": "model", "workspace_id": WS_SALES, "item_id": MODEL})
        self.assertIn(("xmla_connect", "failed", "xmla_not_available"),
                      [(item["check_id"], item["result"], item["reason"]) for item in xmla["checks"]])
        self.assertEqual(revision, self.devcenter.revision)
        self.assertEqual([], self.session_file()["sources"])
        self.failed("cloud_connect", {"base_revision": revision + 5, "kind": "model", "workspace_id": WS_SALES, "item_id": MODEL},
                    code="stale_revision")


class ContractTests(CloudTestCase):
    def test_each_s11_method_has_a_request_and_a_reply_schema(self):
        names = set(contracts.names())
        for method in S11_METHODS:
            with self.subTest(method=method):
                self.assertIn(contracts.jsapi_request(method), names)
                self.assertIn(contracts.jsapi_reply(method), names)

    def test_each_error_reply_validates_against_the_error_shape(self):
        requests = {
            "cloud_sign_in": {"prompt": "never"},
            "cloud_items_list": {"kind": "models"},
            "cloud_connect": {"base_revision": 1, "kind": "model", "workspace_id": WS_SALES, "item_id": MODEL},
            "pull_to_local": {"base_revision": 1, "source_id": "src-9", "path": str(self.root / "x")},
        }
        self.assertEqual(set(S11_METHODS), set(requests))
        for method, request in requests.items():
            with self.subTest(method=method):
                reply = jsapi.call(self.devcenter, method, request)
                self.assertIn("error", reply)
                self.assertEqual([], contracts.errors(contracts.ERROR, reply), reply)


@unittest.skipUnless(BRIDGE.is_file(), "Build the TOM bridge first")
class BridgeCloudReadTests(unittest.TestCase):
    """The bridge command ``cloud-read`` with requests that stop before the connect step (no network)."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.folder = Path(self.temporary.name) / "out"
        self.reader = BridgeCloudModelReader(BRIDGE)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_an_expired_token_gives_the_fixed_code(self):
        token = AccessToken(fake_token(1), int(time.time()) - 10)
        with self.assertRaises(CloudReadFailed) as caught:
            self.reader.read("powerbi://api.powerbi.com/v1.0/myorg/Sales Analytics", MODEL, token, self.folder)
        self.assertEqual("token_expired", caught.exception.code)
        self.assertNotIn(token.value, str(caught.exception))
        self.assertFalse(self.folder.exists())

    def test_a_server_that_is_not_a_workspace_connection_is_refused(self):
        token = AccessToken(fake_token(2), int(time.time()) + 3600)
        for server in ("Data Source=localhost", "powerbi://api.powerbi.com/v1.0/myorg/X;Password=y"):
            with self.subTest(server=server), self.assertRaises(CloudReadFailed) as caught:
                self.reader.read(server, MODEL, token, self.folder)
            self.assertEqual("invalid_request", caught.exception.code)


if __name__ == "__main__":
    unittest.main()
