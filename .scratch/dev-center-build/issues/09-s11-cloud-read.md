# 09: S11 cloud read

Status: open. Lane: cloud. Design step: S11 (docs/DEV_CENTER_TECHNICAL_DESIGN.md section 16).

Depends on (tickets): [04](04-s2-session-store.md).

The goal, the code areas, and the acceptance tests are the design text below. Each acceptance test must be an automated test, except the items that the design marks as manual.

## Lead notes

- Register new JS API methods in `backend/devcenter/jsapi.py` (`AREA_MODULES`) and new reads in `backend/devcenter/http_routes.py`. Put schemas in `backend/devcenter/contracts/` (validator by `$id`).

Fakes only. HITL item T1: the user must register the Entra app (public client, WAM redirect, Power BI and Fabric scopes) before a real-tenant run. Do not add a real client ID; read it from settings, with no default value in the repo. `msal` is an optional dependency: import it lazily, and the tests use a fake token provider.

### Design text: S11. Cloud read

- Goal: sign-in, cloud model donor, "Pull to local PBIP", cloud report impact.
- Code areas: new `backend/devcenter/sources/cloud.py`, the bridge (`cloud-read`), MSAL token cache setup.
- Depends on: S2. Real-tenant checklist depends on task T1 (section 17).
- Acceptance tests (offline, fakes):
  - Token flow: silent first, then interactive; no token in any session file or `connection.json` (scan test).
  - Expired token: one silent refresh and a retry.
  - `cloud-read` against the fake server interface gives a TMDL donor that scans.
  - "Pull to local PBIP" writes a folder that the local loader opens as a target.
  - `getDefinition` 202 polling with recorded responses; a 403 gives "not checked: report not readable".
  - "Reports In Group" filters by dataset ID; other workspaces show as "not checked".
  - Fingerprints: `LastSchemaUpdate` change marks the source.
  - UC13: `cloud_items_list` returns workspaces, models, and reports with their fields from the fake server; no HTTP route gives these data.
  - UC14: `cloud_sign_in` with `prompt: select_account` asks for an account and returns the display name; no session file or `connection.json` holds the name (scan test).
  - UC15: the `cloud_connect` reply lists test lines with check ID, result, reason code, and values for the recorded cases.
  - UC17: `pull_to_local` stores a path relative to the project root; a failed pull leaves no partial folder.
- Manual: the real-tenant checklist (T1) before release.

## Build record

What the worker built (fakes only, no real tenant, no network call in a test):

- `backend/devcenter/sources/cloud_auth.py`: MSAL public client with the Windows broker, silent first, then interactive. `prompt` `none` (silent only) and `select_account` (account picker). `msal` and `msal-extensions` are optional (`pip install .[cloud]`) and load at sign-in only. The token cache is the DPAPI cache of `msal-extensions` in `%LOCALAPPDATA%/PBIBrain/`; without that package the cache is in memory only. The Entra app ID comes from `PBIBRAIN_CLOUD_CLIENT_ID` or `%APPDATA%/PBIBrain/settings.json` (`cloud.client_id`, optional `cloud.tenant`). There is no default value (task T1).
- `backend/devcenter/sources/cloud.py`: three interfaces that the tests replace with fakes (`TokenProvider`, `CloudHttp`, `CloudModelReader`). Power BI lists (groups, capacities, datasets, reports), Fabric `getDefinition` with 202 polling, "Reports In Group" filtered by dataset ID, role check, connect test lines (UC15), "Pull to local PBIP" (UC17), cloud source check with `LastSchemaUpdate` as the change signal. One silent refresh and one retry on HTTP 401 and on the bridge code `token_expired`.
- `backend/devcenter/sources/cloud_jsapi_methods.py`: `cloud_sign_in`, `cloud_items_list`, `cloud_connect`, `pull_to_local`, registered with one line in `jsapi.AREA_MODULES`. No HTTP route.
- Bridge: new file `CloudRead.cs` and one dispatch line in `Program.cs`. Command `cloud-read` reads a JSON request on stdin (the token is never in the process arguments), connects with `Server.AccessToken`, exports TMDL to an empty folder, and gives `last_schema_update`, table and measure counts. Fixed codes: `invalid_request`, `token_expired`, `connect_failed`, `not_found`, `read_failed`.
- Session manager: small hooks only. A cloud source record has `path: null` and a `cloud` block (tenant ID, workspace ID and name, item ID, dataset ID, `last_schema_update`). The export cache is `<session folder>/tmp/cloud/<item ID>/` (git ignores `tmp/`). A cloud source is refused as a target with "Pull to local PBIP first." The cloud check is silent; no token gives `unreadable`.
- Contracts: 8 new JS API schemas; `defs.json` source: `path` can be null, new `cloud_reference`.
- `HOST_PENDING` in `tests/test_devcenter_ui_contract.py`: the four S11 methods are removed.

Design choices for the UI ticket (14):

- `cloud_connect` adds the cloud source itself. `add: false` runs the test only (no revision step, no session needed). The UI must not call `source_add` after `cloud_connect`.
- `pull_to_local` takes `as_target: true` for the Target step flow (one more revision step for `target_set`).
- Check IDs: `sign_in`, `capacity`, `xmla_connect`, `model_read`, `role`, `reports_in_workspace`, `reports_other_workspaces`, `write_conditions`, `report_definition`.

Open items for the real-tenant checklist (T1):

- The model `updated_at` uses the dataset `createdDate`, because the Power BI dataset list has no modified time. Excel and live-connected models are not found from the list fields (only push models are).
- The report `format` field of "Reports In Group" and the role assignment read for a Viewer are not confirmed.
- The bridge `cloud-read` tests stop before the connect step (expired token, bad server). The XMLA connect and the export run only against a real tenant.

Tests:

- `python -m unittest tests.test_devcenter_cloud_read`: 32 tests, OK.
- `python -m unittest discover -s tests`: see the commit message.
- `npm test` in `frontend/`: 99 pass, 0 fail.
- `dotnet build -c Release backend/adapters/tabular_metadata/dotnet/TabularMetadata.csproj`: 0 warnings, 0 errors.
