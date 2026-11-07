---
title: "Agent object edits are proposals that become issue 12's edit and remove choices, new objects are synthetic compare rows, and each submit is checked against the…"
author: Claude
date: 2026-11-07
branch: claude/confident-meitner-xfnnqb
cost: { minutes: 10, tokens: 223567 }
id: l-ad497b31
scope: repo
status: active
src: agent
touches:
  - tests/test_devcenter_bulk_edits.py
  - tests/test_agent_object_edits.py
  - backend/devcenter/session/proposals.py
  - backend/devcenter/plan/compiler.py
  - backend/devcenter/contracts/agent.json
---

## Decided
- No new route, tool or JS API method for issue #13: four proposal kinds (`object_edit`, `object_rename`, `object_delete`, `object_create`) on the existing `proposal_submit` tool. Accepting one writes the `edit` / `remove` Merge Choice of issue #12 or a `created_objects` entry, so plan, guard, apply, rescan and undo are reused.
- A created object (no donor) is a synthetic compare row (`new:<type>:<table>/<name>`, no cells, `created: True`) that the plan compiler adds itself; it compiles to one CREATE. Its DAX, and a new `expression` set by an edit, go through the compiler's `translate` with the target model as the "donor": missing names block `need_missing`, deleted ones `removed`, renamed ones are written with the plan's names.
- Submit check = build the plan with the proposal applied on top of accepted state. Blocking kinds the agent can fix (`choice_not_valid`, `dax_parse`, `need_missing`, `name_clash`, ...) refuse the submit as `invalid_payload` with reason `proposal_not_valid` (no new error code: five lists pin the codes). `removed` / `renamed` are kept as impact so a delete of a used measure can still be proposed and stays plan-blocked until a Removal Policy other than block.
- `needs_review` (delete; rename or expression change with Breaks) is skipped by Accept all with reason `needs_review`, but `include_proposals=ready` reads still include it.

## Watch out
- An `object_edit` and an `object_rename` on the same row both merge into one edit choice; the "user choice" check only blocks when the existing choice is not `edit` or sets the same property.
- `rewrite_dependents` skips an object whose edit sets `expression`, or two REWRITE_EXPRESSION ops would fight.

In the code: backend/devcenter/session/proposals.py (OBJECT_KINDS, _object_check, _needs_review, _skip_reason), backend/devcenter/plan/compiler.py (created_row, register_authored, build_authored, build_edit), backend/devcenter/contracts/agent.json, tests/test_agent_object_edits.py.
