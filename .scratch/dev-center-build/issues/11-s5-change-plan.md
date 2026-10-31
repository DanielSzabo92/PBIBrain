# 11: S5 change plan

Status: open. Lane: backend. Design step: S5 (docs/DEV_CENTER_TECHNICAL_DESIGN.md section 16).

Depends on (tickets): [07](07-s3-alignment-compare.md), [08](08-s4-naming-rules.md).

The goal, the code areas, and the acceptance tests are the design text below. Each acceptance test must be an automated test, except the items that the design marks as manual.

### Design text: S5. Change Plan engine

- Goal: derive a deterministic, sorted plan of plan steps and operations from session state.
- Code areas: `backend/devcenter/plan/`, `backend/dax/parser.py`, `backend/dax/visitors.py`, `backend/api/app.py` (`plan`).
- Depends on: S3, S4.
- Acceptance tests:
  - Each Merge Choice type compiles to the expected operations for a fixture row (golden file).
  - Phase order and dependency order: a column create comes before the measure that uses it; a cycle gives Invalid.
  - Same state twice gives the same plan and the same plan hash.
  - Block, Cascade, and Repoint give the expected operations and statuses; Cascade removes a visual only when no field stays.
  - Token-exact rewrite: only reference tokens change; comments, whitespace, and other text stay byte-equal (property test over the DAX golden corpus).
  - Donor DAX is translated through the alignment; an unaligned reference becomes a Need.
  - lineageTag rules of section 6.6, with UUIDv5 values that equal fixed expected values.
  - A UDF below compatibility level 1702 is blocking.
  - "Promote report measure" gives create, rebind, delete.
  - A name clash row and an unselected rename dependent are blocking.
  - UC3: `GET session` returns the cached plan status, or null with `plan_state: "computing"`, and never starts a plan compute (spy test).
  - UC22: `merge_choice_set` accepts `promote` and `copy_to_report` on a report measure row, and the plan compiles them.
  - UC33: `source_remove` keeps the Merge Choices of that source, adds one `choice_source_removed` blocking item for each, and returns the count.
