# 21: S10 agent mcp tools

Status: open. Lane: backend. Design step: S10 (docs/DEV_CENTER_TECHNICAL_DESIGN.md section 16).

Depends on (tickets): [15](15-s6-impact-data.md), [16](16-s7a-model-writer.md).

The goal, the code areas, and the acceptance tests are the design text below. Each acceptance test must be an automated test, except the items that the design marks as manual.

### Design text: S10. Agent MCP tools

- Goal: the eight tools and the proposal endpoints.
- Code areas: `backend/mcp_server.py`, `backend/api/app.py` (proposal endpoints and reads), `backend/devcenter/session/` (proposals, questions, log).
- Depends on: S6 (S7 for `plan_validate` full mode).
- Acceptance tests:
  - Each tool returns the contract shape (JSON Schema).
  - Allowlist test: no tool maps to a route outside the read and proposal set; no HTTP route for an accepted-state write or Apply exists.
  - Confidence 0.89 gives `confidence_below_threshold`; an empty reason gives `reason_required`; a confirmed-rule break gives `naming_rule_violation` with rule IDs.
  - `stale_revision`, `user_choice_exists`, `source_changed`, and replacement of an older agent proposal.
  - `include_proposals` true and false give different plans; Apply ignores proposals.
  - Each proposal and question writes a log entry with the MCP client name.
  - Paging with `has_more`.
  - UC8: `GET log` filters by `author`, `action`, `target`, and `proposal_id` over all pages.
  - UC9: `GET session` gives each field of each open proposal and question, the blocked state, and the selected option and time of answered questions.
  - UC10: `proposal_accept_all` accepts the ready proposals, skips a proposal on an unconfirmed marked row and one in conflict with a user choice (with reason codes), returns one revision, and writes one log entry for each proposal.
  - UC11: `include_proposals=ready` on `GET plan` and `GET impact` includes only the proposals that `proposal_accept_all` would accept.
  - UC12: `proposal_accept` replaces a user choice and logs before and after; on an unconfirmed marked row it returns `source_changed`.

## Build record

Built (build step S10, ticket 21):
- `backend/devcenter/session/proposals.py`: agent proposals (six kinds), agent questions, blocked state (`source_changed`, `user_choice_conflict`), `include_proposals` overlay (`true` and `ready`), user decisions, and the `GET log` read with filters and paging.
- `backend/devcenter/session/http_routes.py`: `POST proposals`, `POST questions` (kind proposal), `GET log` (UC8). One import line in `backend/devcenter/http_routes.py`.
- `backend/devcenter/session/proposal_jsapi_methods.py`: JS API `proposal_accept` (UC12), `proposal_reject`, `proposal_accept_all` (UC10), `question_answer`. Removed from `HOST_PENDING`.
- `backend/devcenter/agent_tools.py`: the eight MCP tools and the fixed endpoint allowlist `TOOL_ROUTES`. `backend/mcp_server.py` registers them and refuses a route outside the allowlist.
- `GET session` (UC9): each field of each open proposal and question, the blocked state, and `selected_option` and `answered_utc` of answered questions.
- `GET plan`, `GET impact`, `POST plan-validate`: `include_proposals` (`true`, `false`, `ready`, UC11). The HTTP default stays accepted state only; the MCP tools send `true` by default. Apply and the session plan cache use accepted state only.
- `DevCenterSessions._change` and `_commit` take optional log entries (author, MCP client name, reason, proposal ID); one revision can write many log entries.
- Contracts: `agent.json`, `http/proposals.*`, `http/questions.*`, `http/log.reply.json`, `jsapi/{proposal_accept, proposal_reject, proposal_accept_all, question_answer}.{request,reply}.json`, and the proposal and question items of `http/session.reply.json`.

Tests: `tests/test_devcenter_agent_tools.py` (18 tests, all acceptance items of S10, UC8 to UC12). `tests/test_mcp_adapter.py` now expects the eight new tools.

Commands and counts:
- `python -m unittest tests.test_devcenter_agent_tools tests.test_mcp_adapter tests.test_devcenter_ui_contract tests.test_devcenter_http_routes tests.test_devcenter_route_list tests.test_devcenter_plan tests.test_devcenter_impact tests.test_devcenter_session_store tests.test_devcenter_naming`: 144 tests, OK.
- Full suite and e2e: not run by the worker (the orchestrator runs them).

Open items:
- `plan_validate` `full` mode gives the same checks as `quick` (the TMDL round trip needs S7 and S9 wiring).
- `GET compare-rows` still gives `proposal_status: null` for each row.
- No kit gates: this step has no screen.
