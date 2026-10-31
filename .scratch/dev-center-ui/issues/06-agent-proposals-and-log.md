# How does the user see, accept, and reject agent proposals and answer agent questions?

Type: grilling
Status: open
Blocked by: 02

## Question

Design how agent proposals and agent questions show in the work area, how the user accepts, rejects, or accepts all, how the user answers a question, and how the user reads the session log.

## Context

- ADR 0003 and learnings: accept, reject, accept all, and answer go only through the JS API (`proposal_accept`, `proposal_reject`, `proposal_accept_all`, `question_answer`). The agent never applies.
- Proposal kinds (technical design section 12): `merge_choice`, `alignment`, `removal_policy`, `impact_action`, `need_mapping`, `name`. Each has confidence (0.9 or higher) and a reason. A proposal shows as "proposed by agent" until the user acts. A marked row gives `source_changed` on a proposal.
- Questions: target, text, 2 to 5 options (each with an optional proposal payload), recommended option, reason.
- `include_proposals`: plan and impact can show the effect with or without open proposals. Decide where the user switches this.
- Log (`GET log`): time, author (user or agent), MCP client name, action, target, before and after, reason, proposal ID.
- Error codes to show in plain words: `stale_revision`, `user_choice_exists`, `source_changed`.
- "Accept all" needs a summary before it acts. Decide what the summary shows.
- The UI gets no push from the backend in version 1. Decide how new proposals appear (refresh action, poll, or both) together with ticket 10.
- Skills: `design-doctrine`, `ux-writing`.

## Done when

The answer gives: the proposal mark on a row and in the row detail, the proposals list and its filters, the accept all flow with its summary, the question card, the log view, the copy for each error code, and how new proposals appear.
