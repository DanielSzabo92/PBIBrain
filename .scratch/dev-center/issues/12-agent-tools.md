# What are the exact agent tools?

Type: grilling
Status: resolved
Blocked by: 07, 10

## Question

Define each MCP tool (inputs, outputs, errors): session read, compare rows, impact, naming rules, propose a merge choice with confidence and reason, ask a question, validate. Do they live in the existing Brain MCP server or in a new server? How does the design make sure that the agent never reaches the write path?

## Context

- From "What are the match and compare rules?": a compare row has one state for each source (Type conflict, Missing, Renamed, Moved, Different, Same), a "changed" mark, notes such as "same after rename" or "name clash", and a list of property phrases. The compare tool returns this shape.
- From "What are the match and compare rules?": a "possible rename" and an agent alignment are proposals only. The user must confirm them.
- From "How does the Change Plan engine work?": the engine derives the plan from the session state, and nobody edits it by hand. Thus the agent changes the plan only through proposed Merge Choices and removal policies that the user accepts. The validate tool returns the plan status, the blocking items, and the warnings.
- From "Which impact data does the backend give to the UI?": the impact tool returns Impact items (direction, severity, certain or possible, reason phrase ID and text, shortest path with path count, blocking flag, allowed action IDs), a completeness block, and Offer records. The agent can propose an action ID. The action changes the session state only after the user accepts it.
- From "How does the app find and store naming rules?": `naming_rules_get` returns the Naming Rules of the target (ID, scope, check kind, origin, status, support). Add a name-proposal tool: input a candidate name and the object type; output the proposed name and the rule IDs that it used (deterministic). When the agent proposes a name in a Merge Choice, the tool checks it and rejects a name that breaks a confirmed rule, with the rule ID. The agent cannot override a confirmed rule; it must ask the user a question.

## Answer

Resolved on 2026-10-31. The user (through the orchestrator session) accepted all 13 proposed defaults.

### Facts found first

- `backend/mcp_server.py` is a read-only stdio adapter ("PBIBrain"). It calls the local API through `BrainClient`. It allows POST only to `impact` and `compare`. Tools: `brain_overview`, `brain_search`, `brain_object`, `brain_context`, `brain_graph`, `brain_impact`, `brain_compare`.
- The local API (`backend/api/app.py`) checks only the host and the origin. It has no authentication. Thus each local HTTP client can call each endpoint, for example `POST /api/review/...`.
- The `X-PBIBrain-Session` header (`backend/desktop/host.py:397`) is a stale-connection check, not a secret. The session ID is in `.pbibrain/connection.json` on disk.
- The desktop app uses a pywebview JS API (`backend/desktop/host.py:95`). This API runs inside the app process and has no HTTP route.

### Decisions

1. **Server.** The agent tools go into the existing "PBIBrain" MCP server as a new tool group. They use the same stdio adapter and the same local API. The `brain_*` read tools stay as they are.
2. **Tool names.** `session_get`, `compare_rows_list`, `impact_get`, `naming_rules_get`, `name_propose`, `proposal_submit`, `question_ask`, `plan_validate`. The spec name `decision_propose` changes to `proposal_submit`, because "decision" means review decisions.
3. **No write path for the agent: three layers.**
   - (a) Accept, reject, accept-all, and Apply exist only in the pywebview JS API, inside the app process. They are never HTTP endpoints. Thus no HTTP client can call them: not the MCP adapter, not curl, not an agent shell.
   - (b) The HTTP API gets only proposal endpoints. They write agent proposals with the status "proposed". They never change accepted state.
   - (c) The MCP adapter keeps a fixed endpoint allowlist. A test makes sure that no tool maps to a write endpoint and that no HTTP route for accept or apply exists.
4. **Stated limit.** An agent with shell access as the same Windows user can still edit project files directly. The design does not try to block this. The technical design states it as a limit and points to the permissions of the agent host. The agent setup notes show it as a warning.
5. **One proposal tool.** `proposal_submit` inputs: `kind`, `target` (row ID or Impact item ID), `payload`, `confidence`, `reason`, `base_revision`. Kinds: `merge_choice`, `alignment` (manual match or rename confirm), `removal_policy`, `impact_action` (an allowed action ID of the item), `need_mapping`, `name`. All kinds go through one check and one log. Output: proposal ID, status "proposed", new session revision.
6. **The server enforces the 0.9 rule.** Confidence below 0.9 gives `confidence_below_threshold`, and the message tells the agent to use `question_ask`. An empty reason gives `reason_required`. A `name` proposal (or a name in a `merge_choice` payload) goes through the naming rule check. A break of a confirmed rule gives `naming_rule_violation` with the rule IDs.
7. **Conflicts.** Each read returns the session `revision`. A proposal with an old `base_revision` gets `stale_revision`. A new agent proposal for the same target and kind replaces the older agent proposal. An agent proposal never replaces a user choice (`user_choice_exists`).
8. **Preview.** `impact_get` and `plan_validate` take `include_proposals` (default true). With true, they show the plan as if the user accepted all open proposals. Apply always uses accepted state only.
9. **Questions.** `question_ask` inputs: target, text, 2 to 5 options (each with an optional proposal payload of the same shape as `proposal_submit`), the recommended option, and a reason. When the user selects an option with a payload, the payload becomes an accepted choice. `session_get` returns the open questions and the answered questions with the answers. No separate list tool.
10. **Session scope.** The tools act only on the merge session that is open in the app. The agent cannot open, create, or close a session. It cannot add sources, sign in, or change access types.
11. **Validation.** `plan_validate` takes `mode: quick | full`. Quick: DAX parse, reference resolution, impact blocking rules, duplicate lineageTag check. Full: quick plus the TMDL round trip through the bridge in a temp folder and the PBIR schema check. Output: plan status, plan step counts, blocking Impact items, warnings, and the list of checks that ran.
12. **Errors and paging.** One error shape: `{error: {code, message, details}}`. Codes: `not_found`, `session_not_open`, `stale_revision`, `confidence_below_threshold`, `reason_required`, `user_choice_exists`, `naming_rule_violation` (with rule IDs), `invalid_payload`, `action_not_allowed`, `source_changed`. All list tools page with `limit`, `offset`, and `has_more`.
13. **Audit log.** Each proposal and each question goes into the session log: author "agent", MCP client name, time, confidence, reason, base revision. User accept and reject entries link to the proposal.

### Tool summary

| Tool | Inputs | Output |
|---|---|---|
| `session_get` | none | session ID, revision, sources and access types, target, compare mode, plan status, counts, open and answered questions, open proposals |
| `compare_rows_list` | filters (state, changed, type, source), limit, offset | compare rows (state for each source, changed mark, notes, property phrases, Merge Choice, proposal status), `has_more` |
| `impact_get` | row ID or "plan", `include_proposals`, limit, offset | Impact items, completeness block, Offer records |
| `naming_rules_get` | none | Naming Rules (ID, scope, check kind, origin, status, support) |
| `name_propose` | candidate name, object type | proposed name, rule IDs used |
| `proposal_submit` | see decision 5 | proposal ID, status, revision |
| `question_ask` | see decision 9 | question ID, revision |
| `plan_validate` | `mode`, `include_proposals` | see decision 11 |

### Glossary

Added "Agent Proposal" and "Agent Question" to `CONTEXT.md`.
