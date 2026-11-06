# 24: U9 agent log ui

Status: open. Lane: ui. Design step: U9 (docs/DEV_CENTER_UI_DESIGN.md section 13).

Depends on (tickets): [19](19-u6-row-detail.md), [22](22-u8-impact-ui.md), [21](21-s10-agent-mcp-tools.md).

The goal, the code areas, and the acceptance tests are the design text below. Each acceptance test must be an automated test, except the items that the design marks as manual.

### Design text: U9. Agent and Log

- Goal: proposals, questions, accept flows, and the session log.
- Code areas: `frontend/src/devcenter/screens/agent/`, `screens/log/`, `ProposalCard`, `QuestionCard`, grid badge in `CompareGrid`, `frontend/e2e/devcenter-agent.spec.js`.
- Depends on: U6, U8; S10 (proposal fields in `GET session`, `proposal_accept`, `proposal_reject`, `proposal_accept_all`, `include_proposals=ready`, `question_answer`, `GET log` filters).
- Acceptance tests:
  - The first open question leads; "Answer" moves it to "Answered".
  - Proposals table filters, status values, and sticky actions; Accept, Replace with agent choice, Reject; "Accept selected" in sequence with the partial failure toast.
  - "Accept all" summary with the plan now and after, the skipped list, focus on Cancel.
  - Error copy for `user_choice_exists` and `source_changed`.
  - A proposal added through `/__test__/agent-proposal` shows the notice after the poll, and focus and the list stay the same (A19). "The agent replaced this proposal." in an open card.
  - Grid badge priority and tooltip; the row detail card on a marked row disables Accept.
  - Log filters, proposal chip, "Show more", empty value "None".
  - Kit gates (section 13 rule).

## Build record

Built (branch `dc/24-u9-agent-log-ui`, base `dc/23-s9-local-apply`):
- `screens/agent/AgentTab.jsx`, `AcceptAllDialog.jsx`, `agentModel.js`, `agent.css`: questions section (first open question leads, "<n> more open questions", "Answered (<n>)", "Last check", "Refresh"), proposals table (Kind, Status, target search filters; newest first; checkbox only on ready rows; status values; sticky Actions with Accept, Replace with agent choice, Open row, Reject; expandable reason), "Accept selected" in sequence with the partial failure toast and the marked failed row, "Accept all" summary dialog (kinds, plan now and after, change, skipped list, focus on Cancel), A19 new proposal notice.
- `components/QuestionCard.jsx` (Agent tab and row detail), `ProposalCard.jsx` (client and time, confidence, reason, Your choice, Confirm row on a marked row, "The agent replaced this proposal.").
- `CompareGrid.jsx`: `mergeChoiceBadge` with the priority Confirm row first, Question, Proposed, and the tooltip.
- `screens/log/LogTab.jsx`, `logModel.js`: Author, Action, target filters, proposal chip, "Show more" (pages of 50), empty value "None", target link to the row.
- Fake server: `question_answer`, question shape of S10, GET log filters with `limit` and `offset`, GET plan with `include_proposals=ready` (file `plan-proposals`), `POST /__test__/agent-review` (data in `tests/fixtures/devcenter_ui/default/agent-review.json`, plus 60 generated log entries).

Tests:
- `python -m unittest tests.test_devcenter_ui_agent tests.test_devcenter_ui_contract tests.test_devcenter_ui_server tests.test_devcenter_ui_impact`: 57 OK (6 new).
- `npm test` (frontend): 151 pass (7 new in `test/devcenter-agent.test.js`).
- `npm run build`: OK.
- `npx playwright test e2e/devcenter-agent.spec.js`: 13 passed. Also `devcenter-row.spec.js -g "ProposalCard blocked"`: 1 passed (ProposalCard changed).

Not run (Linux cloud machine): the full Python suite, the full e2e suite, the TOM bridge, `lbug_shared.dll`, and Power BI Desktop tests.

Open kit gates (kit not on this machine): `verify_states` (light and `--dark`), `verify_target_size`, `slop_tells --strict`, `verify_focustrap` on the Agent tab, the Accept all dialog, and the Log tab.

Open items:
- The proposals table shows "Your choice" only in the card (GET session has no user choice text). The table status "Conflicts with your choice" tells it.
- `agent.toast.accept_all` has no one form ("1 proposals accepted").
- The Log target search is an exact match, as in S10 `log_page`.

Review: 1 review, PASS (Sonnet reviewer), no blocking findings.

Learning: Add agent fixture data as a file in `default/` with a `/__test__/` loader, not as a new scenario folder, because `test_devcenter_ui_server` pins the scenario list and the folder set.
Learning: The Log tab first entry after the open is "Checked sources", because WorkArea runs `sources_check` once on each page load of a session.
Learning: A Playwright locator on a card by `data-slot` matches the second card after "Show them", because locators are lazy; select the card by its `data-question` ID.
