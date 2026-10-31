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
