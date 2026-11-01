# 08: S4 naming rules

Status: open. Lane: backend. Design step: S4 (docs/DEV_CENTER_TECHNICAL_DESIGN.md section 16).

Depends on (tickets): [04](04-s2-session-store.md).

The goal, the code areas, and the acceptance tests are the design text below. Each acceptance test must be an automated test, except the items that the design marks as manual.

## Lead notes

- Register new JS API methods in `backend/devcenter/jsapi.py` (`AREA_MODULES`) and new reads in `backend/devcenter/http_routes.py`. Put schemas in `backend/devcenter/contracts/` (validator by `$id`).

### Design text: S4. Naming rules

- Goal: detect, store, check, and propose names.
- Code areas: `backend/devcenter/naming/`, `backend/api/app.py` (`naming-rules`, `name-propose`), JS API rule methods.
- Depends on: S2 (S3 for break counts on new names in the plan, later).
- Acceptance tests:
  - The tokenizer splits separators and case changes for a fixed name list.
  - Detection offers a rule at 5 objects and 80%, not at 4 objects or 79%; the limits come from settings.
  - A rejected rule is not offered again.
  - The proposer applies the fixed order and returns the rule IDs; a clash adds "(<donor source>)".
  - A user regular-expression rule checks a name.
  - The rule file is in `.pbibrain/naming-rules/` and outside `definition/`; a bridge TMDL write leaves it.
  - Copy of a rule set gives "proposed" rules.
  - UC16: reject of a user rule removes it; reject of a detected rule keeps it as rejected; edit with no rule ID creates a confirmed user rule; edit of a proposed rule confirms it.
  - UC18: `GET naming-rules` gives the rule count for each session source model.
  - UC19: `name-propose` with `candidate` returns `breaks` for a name that breaks a confirmed rule, and `clash` for a name that exists (case-insensitive).
  - UC34: `naming_rule_edit` of a duplicate rule returns `action_not_allowed` with `details.existing_rule_id`.

## Build record

Built (worker, branch `worktree-agent-a8b5b04ed9fccfcec`):

- New package `backend/devcenter/naming/`: `tokens` (tokenizer, letter case styles, render), `objects` (named objects of TMDL, TMSL, and report measures; format kind), `rules` (rule shape, identity key for UC34, signature, checker, rule text), `detector` (pure detection with `NamingSettings`; limits 5 objects and 80% by default), `proposer` (fixed order letter case, separator, prefix, suffix and unit word, folder; clash adds "(<donor source>)", then "(<donor source> 2)"), `store` (rule file at `.pbibrain/naming-rules/<model folder name>.json`, cloud path helper, canonical JSON, hash), `service` (session glue), `jsapi_methods`, `http_routes`.
- The rule file keeps only the rules that the user acted on (confirmed, rejected, user, copied). The detector gives the other proposed rules again on each read, with stable rule IDs (hash of the rule signature). Thus `GET naming-rules` writes no file. A rejected rule is matched by its signature and is not offered again.
- The detection limits are settings: the `settings` object of the rule file (`min_objects`, `min_support`), with the defaults in `NamingSettings`.
- JS API: `naming_rule_confirm`, `naming_rule_reject`, `naming_rule_edit`, `naming_rules_copy`. Each change writes the rule file, stores `naming_rules.path` and `naming_rules.hash` in the session, adds a revision, and adds one log entry.
- HTTP: `GET naming-rules` (rules with status, origin, support, break count, text; `source_rule_counts` for UC18) and `POST name-propose` (UC19: `candidate`, `breaks`, `clash`; also `resolved_clash` and `checked_name`).
- Contracts: `contracts/naming.json` (shared defs), 8 JS API request and reply schemas, `http/naming-rules.reply.json`, `http/name-propose.request.json`, `http/name-propose.reply.json`.
- Registration: one line in `jsapi.py` (`AREA_MODULES`), one import line at the end of `http_routes.py`. No edit in `host.py` or `app.py`.

Deviation (lead to decide): `POST name-propose` is a read in section 14.1, but the route guard allowed only GET reads and POST proposals. `http_routes.py` got `READ_POSTS = ("name-propose", "plan-validate")` and the guard accepts a POST read for these paths only. The S2 test `tests/test_devcenter_http_routes.py` got the same allowlist, and its loop of GET read checks now skips POST reads. My tests check that `POST name-propose` changes no revision and no file.

Other test change: `tests/test_devcenter_ui_contract.py` no longer lists the four S4 methods in `HOST_PENDING` (lead request).

Not in this step: the bridge has no TMDL write command yet (S7a). The test of "a bridge TMDL write leaves the rule file" simulates the TOM folder write (it deletes and writes again each `.tmdl` file of `definition/`).

Tests:

- `python -m unittest tests.test_devcenter_naming`: 23 tests, OK.
- `python -m unittest discover -s tests`: 459 tests, OK (after the merge of 354f742).
- `npm test` in `frontend/`: 99 pass, 0 fail.

Rework 1 (review FAIL):

1. A stored rule now also hides a detected rule with the same rule ID. An edited detected rule keeps its ID, so the detector does not offer the original rule again after an edit, or after an edit and a reject. New tests check that the read has no duplicate rule IDs.
2. A stored rule with a bad shape (no `check`, an unknown `status`, an unknown scope key) gives `action_not_allowed` with reason `rules_file_damaged`, not a KeyError.
3. The UC18 test checks the count values: 4 and 2 from detection, 3 with a user rule in the file, and 2 again with a rejected rule.

Tests after rework: `tests.test_devcenter_naming` 26 OK; full Python suite 462 OK.

