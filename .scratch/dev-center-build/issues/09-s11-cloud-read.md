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
