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
