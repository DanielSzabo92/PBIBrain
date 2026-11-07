"""Cloud read: cloud model donor, cloud report read, "Pull to local PBIP" (technical design section 10).

Three interfaces hold the parts that touch the network. The tests replace each
of them with a fake, so that no test makes a network call:

- ``TokenProvider`` (``cloud_auth``): sign-in and silent tokens.
- ``CloudHttp``: the Power BI REST API and the Fabric REST API.
- ``CloudModelReader``: the XMLA read. The real reader runs the bridge command
  ``cloud-read``, which exports the model as TMDL into a folder.

The session stores a cloud source as tenant ID, workspace ID, item ID, display
names, and access type (section 11). The TMDL export and the report definition
go into ``<session folder>/tmp/cloud/<item ID>/``. ``.pbibrain/.gitignore``
excludes ``tmp/``. The session never stores a token or an account name.
"""

from __future__ import annotations

import base64
import copy
from dataclasses import dataclass
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import time
from typing import Any, Callable, Mapping, Protocol, Sequence
from urllib.parse import quote, unquote, urlsplit
import uuid

from backend.devcenter.errors import DevCenterError, not_allowed
from backend.devcenter.sources.cloud_auth import (
    FABRIC_SCOPES,
    POWER_BI_SCOPES,
    PROMPT_NONE,
    REASON_NETWORK,
    AccessToken,
    MsalTokenProvider,
    SignInRequired,
    TokenProvider,
)
from backend.devcenter.sources.kinds import (
    CLOUD_MODEL,
    CLOUD_REPORT,
    MODEL_TMDL,
    REPORT_PBIR,
    REPORT_PBIR_LEGACY,
    LocalSource,
    detect_local_source,
)
from backend.devcenter.sources.targets import prepare_empty_folder, skeleton_files

POWER_BI_API = "https://api.powerbi.com/v1.0/myorg"
FABRIC_API = "https://api.fabric.microsoft.com/v1"
XMLA_HOST = "api.powerbi.com"

CLOUD_KINDS = (CLOUD_MODEL, CLOUD_REPORT)
ACCESS_READ = "Read"
ACCESS_READ_WRITE = "Read/Write"

RESULT_OK = "ok"
RESULT_FAILED = "failed"
RESULT_NOT_CHECKED = "not_checked"

# Reason codes of the completeness block and of the connect test lines.
REASON_REPORT_NOT_READABLE = "report_not_readable"
REASON_OTHER_WORKSPACES = "reports_in_other_workspaces"
REASON_NOT_ON_CAPACITY = "workspace_not_on_capacity"
REASON_XMLA_NOT_AVAILABLE = "xmla_not_available"
REASON_MODEL_NOT_FOUND = "model_not_found"
REASON_PUSH_MODEL = "push_model"
REASON_ROLE_NOT_READABLE = "role_not_readable"
REASON_WRITE_LATER = "write_not_in_version_1"
REASON_PBIR_LEGACY = "pbir_legacy_read_only"
REASON_SIGN_IN_REQUIRED = "sign_in_required"
# Write conditions of a cloud target (issue #16).
REASON_READ_ONLY_ACCESS = "read_only_access"
REASON_ROLE_CANNOT_WRITE = "role_cannot_write"
REASON_WRITE_DENIED = "cloud_write_denied"
WRITE_ROLES = frozenset({"Admin", "Member", "Contributor"})

# The STE text of the "not checked" items (technical design section 10.3).
NOT_CHECKED_TEXT = {
    REASON_REPORT_NOT_READABLE: "not checked: report not readable",
    REASON_OTHER_WORKSPACES: "not checked: reports in other workspaces",
}
FIX_REPORT_NOT_READABLE = "export the report to a local PBIP"

_POLL_LIMIT = 60
_INVALID_NAME_CHARACTERS = set('<>:"/\\|?*')


# Network interfaces --------------------------------------------------------------


@dataclass(frozen=True)
class HttpReply:
    status: int
    headers: Mapping[str, str]
    body: Any


class CloudHttp(Protocol):
    def send(self, method: str, url: str, token: AccessToken, body: Any = None) -> HttpReply:
        """Send one request with the bearer token. Give the status, the headers (lowercase names), and the JSON body."""


class UrllibHttp:
    """The real HTTP client (standard library only)."""

    def __init__(self, timeout: int = 60) -> None:
        self.timeout = timeout

    def send(self, method: str, url: str, token: AccessToken, body: Any = None) -> HttpReply:
        import urllib.error
        import urllib.request

        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(url, data=data, method=method)
        request.add_header("Authorization", "Bearer " + token.value)
        if data is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return HttpReply(response.status, {k.lower(): v for k, v in response.headers.items()}, _parse(response.read()))
        except urllib.error.HTTPError as error:
            return HttpReply(error.code, {k.lower(): v for k, v in (error.headers or {}).items()}, _parse(error.read()))
        except (urllib.error.URLError, OSError) as exc:
            raise not_allowed("PBIBrain did not get a reply from the Power BI service.", REASON_NETWORK) from exc


def _parse(data: bytes) -> Any:
    if not data:
        return None
    try:
        return json.loads(data.decode("utf-8-sig"))
    except ValueError:
        return None


@dataclass(frozen=True)
class ModelExport:
    database_name: str
    last_schema_update: str
    table_count: int
    measure_count: int


class CloudReadFailed(Exception):
    """A fixed error code of the bridge command ``cloud-read``."""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


class CloudModelReader(Protocol):
    def read(self, server: str, database: str, token: AccessToken, folder: Path) -> ModelExport:
        """Export the model as TMDL into ``folder``. Raise ``CloudReadFailed`` with the bridge code."""


class BridgeCloudModelReader:
    """The real XMLA reader: the bridge command ``cloud-read``. The token goes on stdin only."""

    def __init__(self, bridge: str | Path | None = None, *, timeout: int = 600) -> None:
        default = Path(__file__).resolve().parents[2] / "adapters/tabular_metadata/dotnet/bin/Release/net8.0/TabularMetadata.dll"
        self.bridge = Path(bridge) if bridge else default
        self.timeout = timeout

    def read(self, server: str, database: str, token: AccessToken, folder: Path) -> ModelExport:
        if not self.bridge.is_file():
            raise CloudReadFailed("bridge_missing", "Build the trusted TOM bridge first")
        request = {"server": server, "database": database, "access_token": token.value,
                   "expires_on": token.expires_on, "out": str(folder)}
        try:
            result = subprocess.run(["dotnet", str(self.bridge), "cloud-read"], input=json.dumps(request), capture_output=True,
                                    text=True, encoding="utf-8", timeout=self.timeout, check=False)
            payload = json.loads(result.stdout)
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            raise CloudReadFailed("read_failed", "The bridge failed or timed out") from exc
        return export_from_bridge(payload)


@dataclass(frozen=True)
class ModelDeploy:
    last_schema_update_before: str
    last_schema_update: str


class CloudModelWriter(Protocol):
    def deploy(self, server: str, database: str, token: AccessToken, folder: Path,
               expected_last_schema_update: str | None) -> ModelDeploy:
        """Write the TMDL folder to the model (delta deploy). Raise ``CloudReadFailed`` with the bridge code."""


class BridgeCloudModelWriter:
    """The real XMLA writer: the bridge command ``cloud-deploy`` (issue #16). The token goes on stdin only."""

    def __init__(self, bridge: str | Path | None = None, *, timeout: int = 900) -> None:
        default = Path(__file__).resolve().parents[2] / "adapters/tabular_metadata/dotnet/bin/Release/net8.0/TabularMetadata.dll"
        self.bridge = Path(bridge) if bridge else default
        self.timeout = timeout

    def deploy(self, server: str, database: str, token: AccessToken, folder: Path,
               expected_last_schema_update: str | None) -> ModelDeploy:
        if not self.bridge.is_file():
            raise CloudReadFailed("bridge_missing", "Build the trusted TOM bridge first")
        request = {"server": server, "database": database, "access_token": token.value, "expires_on": token.expires_on,
                   "folder": str(folder), "expected_last_schema_update": expected_last_schema_update}
        try:
            result = subprocess.run(["dotnet", str(self.bridge), "cloud-deploy"], input=json.dumps(request), capture_output=True,
                                    text=True, encoding="utf-8", timeout=self.timeout, check=False)
            payload = json.loads(result.stdout)
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            raise CloudReadFailed("write_failed", "The bridge failed or timed out") from exc
        return deploy_from_bridge(payload)


def deploy_from_bridge(payload: Mapping[str, Any]) -> ModelDeploy:
    """Read the stdout object of ``cloud-deploy``, or raise ``CloudReadFailed`` with its code."""

    if payload.get("adapter_version") != 1 or payload.get("command") != "cloud-deploy":
        raise CloudReadFailed("write_failed", "The bridge reply is not a cloud-deploy reply")
    if payload.get("status") != "PASSED":
        raise CloudReadFailed(str(payload.get("code") or "write_failed"), str(payload.get("error") or ""))
    return ModelDeploy(str(payload["last_schema_update_before"]), str(payload["last_schema_update"]))


def definition_parts(folder: Path) -> list[dict[str, Any]]:
    """The parts of a report folder for Fabric ``updateDefinition`` (the inverse of ``write_definition``)."""

    parts = []
    for path in sorted(Path(folder).rglob("*")):
        if path.is_file() and path.name != ".platform":
            parts.append({"path": path.relative_to(folder).as_posix(), "payload": base64.b64encode(path.read_bytes()).decode("ascii"),
                          "payloadType": "InlineBase64"})
    return parts


def export_from_bridge(payload: Mapping[str, Any]) -> ModelExport:
    """Read the stdout object of ``cloud-read``, or raise ``CloudReadFailed`` with its code."""

    if payload.get("adapter_version") != 1 or payload.get("command") != "cloud-read":
        raise CloudReadFailed("read_failed", "The bridge reply is not a cloud-read reply")
    if payload.get("status") != "PASSED":
        raise CloudReadFailed(str(payload.get("code") or "read_failed"), str(payload.get("error") or ""))
    return ModelExport(str(payload["database_name"]), str(payload["last_schema_update"]),
                       int(payload["table_count"]), int(payload["measure_count"]))


# Small helpers -------------------------------------------------------------------


def xmla_server(workspace_name: str) -> str:
    return f"powerbi://{XMLA_HOST}/v1.0/myorg/{workspace_name}"


def parse_workspace_connection(text: Any) -> str:
    """Give the workspace name of a pasted connection ``powerbi://api.powerbi.com/v1.0/<tenant>/<workspace>``."""

    value = str(text or "").strip()
    parts = urlsplit(value)
    path = [part for part in parts.path.split("/") if part]
    if parts.scheme.casefold() != "powerbi" or not parts.netloc or len(path) != 3 or not path[0].startswith("v"):
        raise DevCenterError("invalid_payload", "This is not a workspace connection. It must start with powerbi://.",
                             {"reason": "bad_connection"})
    return unquote(path[2])


def _utc(value: Any) -> str | None:
    text = str(value or "")
    if len(text) < 19 or text[4] != "-" or text[10] != "T":
        return None
    return text[:19] + "Z"


def capacity_type(sku: Any, dedicated: bool) -> str:
    if not dedicated:
        return "shared"
    text = str(sku or "").upper()
    if text.startswith("PP"):
        return "premium_per_user"
    if text.startswith("P"):
        return "premium"
    if text.startswith("F"):
        return "fabric"
    if text.startswith(("A", "EM")):
        return "embedded"
    return "unknown"


def _file_name(name: str) -> str:
    value = "".join("_" if ord(c) < 32 or c in _INVALID_NAME_CHARACTERS else c for c in str(name)).strip().rstrip(". ")
    return value or "Model"


def _remove(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    elif path.exists():
        path.unlink(missing_ok=True)


def write_definition(parts: Sequence[Mapping[str, Any]], folder: Path) -> None:
    """Write the parts of a report definition (InlineBase64) into a new folder."""

    folder.mkdir(parents=True, exist_ok=False)
    root = folder.resolve()
    for part in parts:
        relative = PurePosixPath(str(part.get("path") or ""))
        if not relative.parts or relative.is_absolute() or ".." in relative.parts or ":" in str(relative):
            raise not_allowed("The report definition has a part with a path that is not valid.", "bad_definition")
        if part.get("payloadType") != "InlineBase64":
            raise not_allowed("The report definition has a part in a form that PBIBrain cannot read.", "bad_definition")
        target = (root / Path(*relative.parts)).resolve()
        if not target.is_relative_to(root):
            raise not_allowed("The report definition has a part with a path that is not valid.", "bad_definition")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(base64.b64decode(str(part.get("payload") or ""), validate=True))


def _check(check_id: str, result: str, reason: str | None = None, **values: Any) -> dict[str, Any]:
    return {"check_id": check_id, "result": result, "reason": reason, "values": values}


class ReportNotReadable(Exception):
    pass


def read_error(exc: CloudReadFailed) -> DevCenterError:
    """Give the plain error of a failed model read (the bridge code is the reason)."""

    if exc.code == "not_found":
        return DevCenterError("not_found", "The model is not in the workspace, or you cannot read it.", {"reason": REASON_MODEL_NOT_FOUND})
    if exc.code in {"connect_failed", "bridge_missing"}:
        return not_allowed("PBIBrain cannot connect to the workspace through XMLA.", REASON_XMLA_NOT_AVAILABLE)
    return not_allowed("PBIBrain cannot read the cloud model.", "model_not_readable", code=exc.code)


# The service ---------------------------------------------------------------------


class CloudService:
    """Cloud calls of one app process. Only memory holds the account and the tokens."""

    def __init__(self, tokens: TokenProvider | None = None, http: CloudHttp | None = None,
                 reader: CloudModelReader | None = None, *, sleep: Callable[[float], None] = time.sleep,
                 poll_limit: int = _POLL_LIMIT, writer: CloudModelWriter | None = None) -> None:
        self._tokens = tokens
        self.http: CloudHttp = http or UrllibHttp()
        self.reader: CloudModelReader = reader or BridgeCloudModelReader()
        self.writer: CloudModelWriter = writer or BridgeCloudModelWriter()
        self.sleep = sleep
        self.poll_limit = poll_limit

    @property
    def tokens(self) -> TokenProvider:
        if self._tokens is None:
            self._tokens = MsalTokenProvider()
        return self._tokens

    # Tokens and HTTP -------------------------------------------------------------

    def _with_token(self, scopes: Sequence[str], action: Callable[[AccessToken], Any], expired: Callable[[Any], bool]) -> Any:
        """Run the action with a silent token. On an expired token: one silent refresh and one retry."""

        result = action(self.tokens.token(scopes))
        if not expired(result):
            return result
        result = action(self.tokens.token(scopes, force_refresh=True))
        if expired(result):
            raise SignInRequired(REASON_SIGN_IN_REQUIRED)
        return result

    def _send(self, method: str, url: str, scopes: Sequence[str], body: Any = None) -> HttpReply:
        return self._with_token(scopes, lambda token: self.http.send(method, url, token, body), lambda reply: reply.status == 401)

    def _get(self, url: str, scopes: Sequence[str] = POWER_BI_SCOPES) -> Any:
        reply = self._send("GET", url, scopes)
        if reply.status == 403:
            raise not_allowed("You do not have permission to read this item.", "permission_denied")
        if reply.status == 404:
            raise DevCenterError("not_found", "The cloud item does not exist.", {"reason": "cloud_not_found"})
        if reply.status >= 400 or not isinstance(reply.body, Mapping):
            raise not_allowed("The Power BI service did not give a valid reply.", "cloud_error", status=reply.status)
        return reply.body

    def _values(self, url: str, scopes: Sequence[str] = POWER_BI_SCOPES) -> list[Mapping[str, Any]]:
        values = self._get(url, scopes).get("value")
        return [item for item in values if isinstance(item, Mapping)] if isinstance(values, list) else []

    # Sign-in (UC14) ----------------------------------------------------------------

    def sign_in(self, revision: int | None, request: Mapping[str, Any]) -> dict[str, Any]:
        prompt = request.get("prompt")
        try:
            account = self.tokens.sign_in(POWER_BI_SCOPES, prompt=prompt)
        except SignInRequired:
            if prompt != PROMPT_NONE:
                raise
            return {"revision": revision, "signed_in": False, "account_name": None, "reason": "interaction_required"}
        return {"revision": revision, "signed_in": True, "account_name": account.display_name, "reason": None}

    def _account_check(self) -> dict[str, Any]:
        account = self.tokens.account()
        if account is None:
            account = self.tokens.sign_in(POWER_BI_SCOPES, prompt=PROMPT_NONE)
        return _check("sign_in", RESULT_OK, None, account_name=account.display_name)

    # Item lists (UC13) -------------------------------------------------------------

    def _capacities(self) -> dict[str, Any]:
        try:
            return {str(item.get("id")).casefold(): item.get("sku") for item in self._values(f"{POWER_BI_API}/capacities")}
        except DevCenterError:
            return {}

    def workspaces(self) -> list[dict[str, Any]]:
        capacities: dict[str, Any] | None = None
        rows = []
        for item in self._values(f"{POWER_BI_API}/groups"):
            dedicated = bool(item.get("isOnDedicatedCapacity"))
            if dedicated and capacities is None:
                capacities = self._capacities()
            sku = (capacities or {}).get(str(item.get("capacityId") or "").casefold())
            kind = capacity_type(sku, dedicated)
            rows.append({"id": str(item.get("id")), "name": str(item.get("name") or ""), "capacity_type": kind,
                         "xmla_available": kind != "shared"})
        return sorted(rows, key=lambda row: (row["name"].casefold(), row["id"]))

    def _workspace(self, workspace_id: Any = None, name: str | None = None) -> dict[str, Any]:
        for row in self.workspaces():
            if (workspace_id and row["id"].casefold() == str(workspace_id).casefold()) or (name and row["name"].casefold() == name.casefold()):
                return row
        raise DevCenterError("not_found", "The workspace does not exist or you cannot read it.", {"reason": "workspace_not_found"})

    def models(self, workspace: Mapping[str, Any]) -> list[dict[str, Any]]:
        rows = []
        for item in self._values(f"{POWER_BI_API}/groups/{quote(workspace['id'])}/datasets"):
            push = bool(item.get("addRowsAPIEnabled"))
            reason = REASON_NOT_ON_CAPACITY if not workspace["xmla_available"] else REASON_PUSH_MODEL if push else None
            rows.append({"id": str(item.get("id")), "name": str(item.get("name") or ""),
                         "updated_at": _utc(item.get("lastSchemaUpdate") or item.get("createdDate")),
                         "model_type": "push" if push else "semantic_model",
                         "xmla_readable": reason is None, "reason": reason})
        return sorted(rows, key=lambda row: (row["name"].casefold(), row["id"]))

    def reports(self, workspace_id: str) -> list[dict[str, Any]]:
        rows = []
        for item in self._values(f"{POWER_BI_API}/groups/{quote(workspace_id)}/reports"):
            if item.get("reportType") not in (None, "PowerBIReport"):
                continue  # Paginated reports are not PBIR.
            report_format = {"PBIR": REPORT_PBIR, "PBIRLegacy": REPORT_PBIR_LEGACY}.get(str(item.get("format") or ""))
            rows.append({"id": str(item.get("id")), "name": str(item.get("name") or ""), "format": report_format,
                         "dataset_id": str(item["datasetId"]) if item.get("datasetId") else None})
        return sorted(rows, key=lambda row: (row["name"].casefold(), row["id"]))

    def items(self, revision: int | None, request: Mapping[str, Any]) -> dict[str, Any]:
        kind = request["kind"]
        if kind == "workspaces":
            items: list[dict[str, Any]] = self.workspaces()
        else:
            if not request.get("workspace_id"):
                raise DevCenterError("invalid_payload", "Select a workspace first.", {"reason": "workspace_required"})
            if kind == "models":
                items = self.models(self._workspace(request["workspace_id"]))
            else:
                items = self.reports(str(request["workspace_id"]))
        return {"revision": revision, "kind": kind, "items": items}

    # Model read (XMLA) -------------------------------------------------------------

    def read_model(self, workspace_name: str, database: str, folder: Path) -> ModelExport:
        """Export the model as TMDL into ``folder`` (new or empty). A failure removes the folder content."""

        def action(token: AccessToken) -> Any:
            try:
                return self.reader.read(xmla_server(workspace_name), database, token, folder)
            except CloudReadFailed as exc:
                if exc.code != "token_expired":
                    _remove(folder)
                return exc

        result = self._with_token(POWER_BI_SCOPES, action,
                                  lambda value: isinstance(value, CloudReadFailed) and value.code == "token_expired")
        if isinstance(result, CloudReadFailed):
            raise result
        return result

    # Report read (Fabric getDefinition) --------------------------------------------

    def definition(self, workspace_id: str, report_id: str) -> list[Mapping[str, Any]]:
        """Get the definition parts. Handle 202 with polling. Raise ``ReportNotReadable`` on 403."""

        url = f"{FABRIC_API}/workspaces/{quote(workspace_id)}/reports/{quote(report_id)}/getDefinition"
        reply = self._send("POST", url, FABRIC_SCOPES)
        if reply.status in (401, 403):
            raise ReportNotReadable()
        if reply.status == 202:
            reply = self._poll(reply)
        if reply.status != 200 or not isinstance(reply.body, Mapping):
            raise not_allowed("The Power BI service did not give the report definition.", "cloud_error", status=reply.status)
        parts = (reply.body.get("definition") or {}).get("parts")
        if not isinstance(parts, list):
            raise not_allowed("The report definition has no parts.", "bad_definition")
        return parts

    def _poll(self, accepted: HttpReply, *, result: bool = True) -> HttpReply:
        operation = accepted.headers.get("x-ms-operation-id")
        location = accepted.headers.get("location") or (f"{FABRIC_API}/operations/{operation}" if operation else None)
        if not location:
            raise not_allowed("The Power BI service did not give an operation to wait for.", "cloud_error", status=202)
        delay = float(accepted.headers.get("retry-after") or 1)
        for _ in range(self.poll_limit):
            self.sleep(delay)
            state = self._send("GET", location, FABRIC_SCOPES)
            if state.status == 403:
                raise ReportNotReadable()
            status = str((state.body or {}).get("status") or "") if isinstance(state.body, Mapping) else ""
            if state.status >= 400 or status == "Failed":
                raise not_allowed("The Power BI service could not prepare the report definition.", "cloud_error", status=state.status)
            if status == "Succeeded":
                if not result:
                    return state
                address = state.headers.get("location") or location.rstrip("/") + "/result"
                return self._send("GET", address, FABRIC_SCOPES)
            delay = float(state.headers.get("retry-after") or delay)
        raise not_allowed("The Power BI service did not prepare the report definition in time.", "cloud_timeout")

    # Writes (issue #16) --------------------------------------------------------------

    def deploy_model(self, workspace_name: str, database: str, folder: Path,
                     expected_last_schema_update: str | None) -> ModelDeploy:
        """Delta deploy of a TMDL ``definition`` folder to a cloud model through XMLA."""

        def action(token: AccessToken) -> Any:
            try:
                return self.writer.deploy(xmla_server(workspace_name), database, token, folder, expected_last_schema_update)
            except CloudReadFailed as exc:
                return exc

        result = self._with_token(POWER_BI_SCOPES, action,
                                  lambda value: isinstance(value, CloudReadFailed) and value.code == "token_expired")
        if isinstance(result, CloudReadFailed):
            raise result
        return result

    def update_report(self, workspace_id: str, report_id: str, folder: Path) -> None:
        """Replace the definition of a cloud report with the files of ``folder`` (Fabric ``updateDefinition``)."""

        url = f"{FABRIC_API}/workspaces/{quote(workspace_id)}/reports/{quote(report_id)}/updateDefinition"
        reply = self._send("POST", url, FABRIC_SCOPES, {"definition": {"parts": definition_parts(folder)}})
        if reply.status in (401, 403):
            raise not_allowed("You do not have permission to change this report.", REASON_WRITE_DENIED)
        if reply.status == 202:
            reply = self._poll(reply, result=False)
        if reply.status not in (200, 202):
            raise not_allowed("The Power BI service did not take the report definition.", "cloud_error", status=reply.status)

    def write_checks(self, record: Mapping[str, Any]) -> list[dict[str, Any]]:
        """The write conditions of a cloud target: access type, capacity (XMLA read/write), model type, role."""

        cloud = record["cloud"]
        checks = []
        if record.get("access_type") != ACCESS_READ_WRITE:
            checks.append(_check("access_type", RESULT_FAILED, REASON_READ_ONLY_ACCESS))
            return checks
        checks.append(_check("access_type", RESULT_OK))
        workspace = self._workspace(cloud["workspace_id"])
        if record["kind"] == CLOUD_MODEL:
            if not workspace["xmla_available"]:
                checks.append(_check("capacity", RESULT_FAILED, REASON_NOT_ON_CAPACITY, capacity_type=workspace["capacity_type"]))
                return checks
            checks.append(_check("capacity", RESULT_OK, None, capacity_type=workspace["capacity_type"]))
            model = next((row for row in self.models(workspace) if row["id"].casefold() == str(cloud["item_id"]).casefold()), None)
            if model is None:
                checks.append(_check("model_type", RESULT_FAILED, REASON_MODEL_NOT_FOUND))
                return checks
            checks.append(_check("model_type", RESULT_FAILED if model["reason"] else RESULT_OK, model["reason"]))
        role = self._role(cloud["workspace_id"])
        if role["result"] == RESULT_OK and role["values"].get("role") not in WRITE_ROLES:
            role = _check("role", RESULT_FAILED, REASON_ROLE_CANNOT_WRITE, **role["values"])
        checks.append(role)
        return checks

    def report_to_folder(self, workspace_id: str, report_id: str, folder: Path) -> LocalSource:
        parts = self.definition(workspace_id, report_id)
        try:
            write_definition(parts, folder)
            return detect_local_source(folder)
        except BaseException:
            _remove(folder)
            raise

    def report_coverage(self, workspace_id: str, dataset_id: str, cache: Path | None = None) -> dict[str, Any]:
        """Reports of a cloud model: "Reports In Group" of its own workspace, filtered by dataset ID (section 10.3).

        Give each report with its read state, and the "not checked" items of the completeness block.
        """

        reports = []
        not_checked: list[dict[str, Any]] = []
        for item in self.reports(workspace_id):
            if (item["dataset_id"] or "").casefold() != dataset_id.casefold():
                continue
            readable = True
            try:
                parts = self.definition(workspace_id, item["id"])
                if cache is not None:
                    # A folder of its own: a cloud report source of the session keeps its cache.
                    folder = cache / item["id"]
                    _remove(folder)
                    cache.mkdir(parents=True, exist_ok=True)
                    write_definition(parts, folder)
            except ReportNotReadable:
                readable = False
                not_checked.append({"reason": REASON_REPORT_NOT_READABLE, "text": NOT_CHECKED_TEXT[REASON_REPORT_NOT_READABLE],
                                    "fix": FIX_REPORT_NOT_READABLE, "report_id": item["id"], "name": item["name"]})
            reports.append({**item, "readable": readable})
        not_checked.append({"reason": REASON_OTHER_WORKSPACES, "text": NOT_CHECKED_TEXT[REASON_OTHER_WORKSPACES],
                            "fix": None, "report_id": None, "name": None})
        return {"reports": reports, "not_checked": not_checked}

    def _role(self, workspace_id: str) -> dict[str, Any]:
        account = self.tokens.account()
        try:
            values = self._values(f"{FABRIC_API}/workspaces/{quote(workspace_id)}/roleAssignments", FABRIC_SCOPES)
        except DevCenterError:
            return _check("role", RESULT_NOT_CHECKED, REASON_ROLE_NOT_READABLE)
        wanted = (account.object_id or "").casefold() if account else ""
        for item in values:
            principal = item.get("principal") or {}
            if wanted and str(principal.get("id") or "").casefold() == wanted:
                return _check("role", RESULT_OK, None, role=str(item.get("role") or ""))
        return _check("role", RESULT_NOT_CHECKED, REASON_ROLE_NOT_READABLE)

    # Cache of the session ----------------------------------------------------------

    @staticmethod
    def cache_dir(devcenter: Any) -> Path:
        return devcenter.session_folder() / "tmp" / "cloud"

    @staticmethod
    def _swap(staging: Path, folder: Path) -> Path:
        _remove(folder)
        os.replace(staging, folder)
        return folder

    def _fresh(self, devcenter: Any, record: Mapping[str, Any]) -> tuple[LocalSource, str | None]:
        """Read the cloud item again into the cache. Give the source and the LastSchemaUpdate (models only)."""

        cloud = record["cloud"]
        cache = self.cache_dir(devcenter)
        cache.mkdir(parents=True, exist_ok=True)
        staging = cache / f".{cloud['item_id']}.{uuid.uuid4().hex}.tmp"
        try:
            if record["kind"] == CLOUD_MODEL:
                try:
                    export = self.read_model(cloud["workspace_name"], cloud["item_id"], staging / "definition")
                except CloudReadFailed as exc:
                    raise read_error(exc) from exc
                stamp: str | None = export.last_schema_update
            else:
                try:
                    self.report_to_folder(cloud["workspace_id"], cloud["item_id"], staging)
                except ReportNotReadable as exc:
                    raise not_allowed("PBIBrain cannot read the definition of this report.", REASON_REPORT_NOT_READABLE) from exc
                stamp = None
            folder = self._swap(staging, cache / cloud["item_id"])
        finally:
            _remove(staging)
        return detect_local_source(folder), stamp

    def load(self, devcenter: Any, record: Mapping[str, Any]) -> LocalSource:
        """Give the cached export of a cloud source. Read it again when the cache is missing."""

        folder = self.cache_dir(devcenter) / record["cloud"]["item_id"]
        try:
            return detect_local_source(folder)
        except DevCenterError:
            return self._fresh(devcenter, record)[0]

    def check_source(self, devcenter: Any, record: dict[str, Any], has_marks: bool) -> LocalSource | None:
        """Source check of one cloud source (section 11).

        For a model, the ``LastSchemaUpdate`` value is the change signal: the
        same value and no marks give None (no change). A new value gives the new
        export, so that the caller compares the row hashes. A report gives its
        definition again each time.
        """

        cloud = record["cloud"]
        source, stamp = self._fresh(devcenter, record)
        if record["kind"] == CLOUD_MODEL:
            same = stamp == cloud.get("last_schema_update")
            cloud["last_schema_update"] = stamp
            if same and not has_marks:
                return None
        return source

    # Connect (UC15) ----------------------------------------------------------------

    def connect(self, devcenter: Any, request: Mapping[str, Any]) -> dict[str, Any]:
        add = request.get("add", True)
        revision = devcenter.revision
        if add and revision is None:
            raise DevCenterError("session_not_open", "No merge session is open.")
        if add and request.get("base_revision") != revision:
            raise DevCenterError("stale_revision", "The session changed. Load it again.", {"revision": revision})
        checks = [self._account_check()]
        kind = request["kind"]
        if kind == "model":
            record, source, more = self._connect_model(devcenter if add else None, request)
        else:
            record, source, more = self._connect_report(devcenter if add else None, request)
        checks.extend(more)
        staging = source
        blocked = record is None or any(item["result"] == RESULT_FAILED for item in checks if item["check_id"] in _BLOCKING)
        if not add or blocked:
            if staging is not None:
                _remove(staging)
            return {"revision": revision, "added": False, "source": None, "checks": checks}
        final = self.cache_dir(devcenter) / record["cloud"]["item_id"]
        prepared: list[bool] = []

        def prepare() -> LocalSource:
            # The manager calls this only after its duplicate check, so no source of the session uses ``final``.
            prepared.append(True)
            return detect_local_source(self._swap(staging, final))

        try:
            reply = devcenter.add_prepared_source(request, "cloud_connect", record, prepare)
        except BaseException:
            _remove(staging)
            if prepared:
                _remove(final)
            raise
        return {"revision": reply["revision"], "added": True, "source": reply["source"], "checks": checks}

    def _resolve_model(self, request: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        if request.get("workspace_connection"):
            workspace = self._workspace(name=parse_workspace_connection(request["workspace_connection"]))
            wanted = str(request.get("item_name") or "").casefold()
            match = lambda row: row["name"].casefold() == wanted  # noqa: E731
        else:
            if not request.get("workspace_id") or not request.get("item_id"):
                raise DevCenterError("invalid_payload", "Select a workspace and a model.", {"reason": "item_required"})
            workspace = self._workspace(request["workspace_id"])
            wanted = str(request["item_id"]).casefold()
            match = lambda row: row["id"].casefold() == wanted  # noqa: E731
        model = next((row for row in self.models(workspace) if match(row)), None)
        if model is None:
            raise DevCenterError("not_found", "No model with this name in the workspace.", {"reason": REASON_MODEL_NOT_FOUND})
        return workspace, model

    @staticmethod
    def _refuse_duplicate(devcenter: Any, item_id: str) -> None:
        if devcenter is None:
            return
        for item in devcenter.session_summary()["sources"]:
            if str((item.get("cloud") or {}).get("item_id") or "").casefold() == item_id.casefold():
                raise not_allowed("This source is already in the session.", "duplicate_source")

    def _connect_model(self, devcenter: Any, request: Mapping[str, Any]) -> tuple[Any, Any, list[dict[str, Any]]]:
        """Run the model checks. With a session, give the record and the staging folder of the export."""

        workspace, model = self._resolve_model(request)
        self._refuse_duplicate(devcenter, model["id"])
        checks = []
        if not workspace["xmla_available"]:
            checks.append(_check("capacity", RESULT_FAILED, REASON_NOT_ON_CAPACITY, capacity_type=workspace["capacity_type"]))
            return None, None, checks
        checks.append(_check("capacity", RESULT_OK, None, capacity_type=workspace["capacity_type"]))
        if model["reason"] is not None:
            checks.append(_check("model_read", RESULT_FAILED, model["reason"]))
            return None, None, checks
        cache = self.cache_dir(devcenter) if devcenter is not None else None
        temporary = None
        if cache is None:
            import tempfile

            temporary = Path(tempfile.mkdtemp(prefix="pbibrain-cloud-"))
            folder = temporary / model["id"]
        else:
            cache.mkdir(parents=True, exist_ok=True)
            folder = cache / f".{model['id']}.{uuid.uuid4().hex}.tmp"
        keep = False
        try:
            try:
                export = self.read_model(workspace["name"], model["id"], folder / "definition")
            except CloudReadFailed as exc:
                if exc.code in {"connect_failed", "bridge_missing"}:
                    checks.append(_check("xmla_connect", RESULT_FAILED, REASON_XMLA_NOT_AVAILABLE))
                else:
                    checks.append(_check("xmla_connect", RESULT_OK))
                    reason = REASON_MODEL_NOT_FOUND if exc.code == "not_found" else "model_not_readable"
                    checks.append(_check("model_read", RESULT_FAILED, reason))
                return None, None, checks
            checks.append(_check("xmla_connect", RESULT_OK))
            checks.append(_check("model_read", RESULT_OK, None, table_count=export.table_count, measure_count=export.measure_count))
            checks.append(self._role(workspace["id"]))
            coverage = self.report_coverage(workspace["id"], model["id"], cache / "coverage" / model["id"] if cache else None)
            names = [item["name"] for item in coverage["reports"] if not item["readable"]]
            checks.append(_check("reports_in_workspace", RESULT_OK, REASON_REPORT_NOT_READABLE if names else None,
                                 report_count=len(coverage["reports"]),
                                 readable_count=sum(1 for item in coverage["reports"] if item["readable"]),
                                 unreadable_names=names))
            checks.append(_check("reports_other_workspaces", RESULT_NOT_CHECKED, REASON_OTHER_WORKSPACES))
            checks.append(_check("write_conditions", RESULT_NOT_CHECKED, REASON_WRITE_LATER))
            if devcenter is None:
                return {}, None, checks  # A test only: no record.
            keep = True
        finally:
            if not keep:
                _remove(folder)
            if temporary is not None:
                shutil.rmtree(temporary, ignore_errors=True)
        record = self._record(CLOUD_MODEL, model["name"], workspace, model["id"], request, model_format=MODEL_TMDL,
                              last_schema_update=export.last_schema_update)
        return record, folder, checks

    def _connect_report(self, devcenter: Any, request: Mapping[str, Any]) -> tuple[Any, Any, list[dict[str, Any]]]:
        if not request.get("workspace_id") or not request.get("item_id"):
            raise DevCenterError("invalid_payload", "Select a workspace and a report.", {"reason": "item_required"})
        workspace = self._workspace(request["workspace_id"])
        wanted = str(request["item_id"]).casefold()
        report = next((row for row in self.reports(workspace["id"]) if row["id"].casefold() == wanted), None)
        if report is None:
            raise DevCenterError("not_found", "The report is not in the workspace.", {"reason": "report_not_found"})
        self._refuse_duplicate(devcenter, report["id"])
        cache = self.cache_dir(devcenter) if devcenter is not None else None
        import tempfile

        base = cache if cache is not None else Path(tempfile.mkdtemp(prefix="pbibrain-cloud-"))
        base.mkdir(parents=True, exist_ok=True)
        folder = base / f".{report['id']}.{uuid.uuid4().hex}.tmp"
        keep = False
        try:
            try:
                local = self.report_to_folder(workspace["id"], report["id"], folder)
            except ReportNotReadable:
                return None, None, [_check("report_definition", RESULT_FAILED, REASON_REPORT_NOT_READABLE,
                                           name=report["name"], fix=FIX_REPORT_NOT_READABLE),
                                    _check("write_conditions", RESULT_NOT_CHECKED, REASON_WRITE_LATER)]
            report_format = local.report_format
            checks = [_check("report_definition", RESULT_OK, REASON_PBIR_LEGACY if report_format == REPORT_PBIR_LEGACY else None,
                             name=report["name"], format=report_format),
                      _check("write_conditions", RESULT_NOT_CHECKED, REASON_WRITE_LATER)]
            if cache is None:
                return {}, None, checks
            keep = True
        finally:
            if not keep:
                _remove(folder)
            if cache is None:
                shutil.rmtree(base, ignore_errors=True)
        record = self._record(CLOUD_REPORT, report["name"], workspace, report["id"], request,
                              report_format=report_format, dataset_id=report["dataset_id"])
        return record, folder, checks

    def _record(self, kind: str, name: str, workspace: Mapping[str, Any], item_id: str, request: Mapping[str, Any], *,
                model_format: str | None = None, report_format: str | None = None, last_schema_update: str | None = None,
                dataset_id: str | None = None) -> dict[str, Any]:
        account = self.tokens.account()
        return {
            "kind": kind,
            "role": "donor",
            "display_name": name,
            "path": None,
            "model_path": None,
            "model_format": model_format,
            "report_path": None,
            "report_format": report_format,
            "access_type": request.get("access_type") or ACCESS_READ,
            "cloud": {
                "tenant_id": account.tenant_id if account else None,
                "workspace_id": workspace["id"],
                "workspace_name": workspace["name"],
                "item_id": item_id,
                "dataset_id": dataset_id,
                "last_schema_update": last_schema_update,
            },
        }

    # Pull to local PBIP (UC17) -----------------------------------------------------

    def pull_to_local(self, devcenter: Any, request: Mapping[str, Any]) -> dict[str, Any]:
        revision = devcenter.revision
        if revision is None:
            raise DevCenterError("session_not_open", "No merge session is open.")
        if request.get("base_revision") != revision:
            raise DevCenterError("stale_revision", "The session changed. Load it again.", {"revision": revision})
        record = copy.deepcopy(devcenter.source_record(request.get("source_id")))
        if record["kind"] != CLOUD_MODEL:
            raise not_allowed("Only a cloud model can be pulled to a local PBIP.", "not_cloud_model")
        folder = prepare_empty_folder(str(request.get("path") or ""))
        devcenter.relative_path(folder)  # Refuse a folder on a different drive before the read.
        name = _file_name(record["display_name"])
        model_folder = f"{name}.SemanticModel"
        existed = folder.exists()
        new_parent = next((parent for parent in reversed(folder.parents) if not parent.exists()), None)
        staging = folder.parent / f".{folder.name}.pull-{uuid.uuid4().hex}.tmp"
        moved = False
        try:
            for relative, data in skeleton_files(name).items():
                if relative.startswith(f"{model_folder}/definition/"):
                    continue  # The cloud export gives the model definition.
                path = staging / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            cloud = record["cloud"]
            try:
                self.read_model(cloud["workspace_name"], cloud["item_id"], staging / model_folder / "definition")
            except CloudReadFailed as exc:
                raise read_error(exc) from exc
            if existed:
                folder.rmdir()
            os.replace(staging, folder)
            moved = True
            added = devcenter.source_add({"base_revision": revision, "path": str(folder / f"{name}.pbip")})
        except BaseException:
            _remove(staging)
            if moved or not existed:
                _remove(folder)
            if existed and not folder.exists():
                folder.mkdir(parents=True)
            if new_parent is not None:
                _remove(new_parent)  # The pull made this folder; nothing else is in it.
            raise
        target = None
        if request.get("as_target"):
            new_id = added["source"]["source_id"]
            target = devcenter.target_set({"base_revision": added["revision"], "model": {"mode": "existing", "source_id": new_id},
                                           "report": {"mode": "existing", "source_id": new_id}})
        return {"revision": target["revision"] if target else added["revision"], "source": added["source"],
                "target": target["target"] if target else None}


_BLOCKING = frozenset({"sign_in", "capacity", "xmla_connect", "model_read", "report_definition"})
