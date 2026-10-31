# 20: S8 guard merge

Status: open. Lane: backend. Design step: S8 (docs/DEV_CENTER_TECHNICAL_DESIGN.md section 16).

Depends on (tickets): [16](16-s7a-model-writer.md), [17](17-s7b-pbir-writer.md).

The goal, the code areas, and the acceptance tests are the design text below. Each acceptance test must be an automated test, except the items that the design marks as manual.

### Design text: S8. Guard for merge

- Goal: the guard accepts a correct merge candidate and rejects each change outside the plan.
- Code areas: `backend/diff/snapshots.py`, `backend/diff/tmdl_source.py`, `change_guard/orchestrator.py`, `change_guard/policy/engine.py`, `change_guard/contracts/schema.py`, `change_guard/contracts/contract-v1.schema.json`.
- Depends on: S7.
- Acceptance tests:
  - A candidate from S7 for each fixture plan gets PASS.
  - Mutation tests: one extra changed property, one extra file, one removed file, a non-canonical changed file, an unplanned identity-map entry, a rename pair with a second property change, an extra PBIR property, and a changed perspective each give a reject with the expected code.
  - A missing or wrong write record hash rejects.
  - HIGH risk without approval rejects; with the approval record it passes.
  - "Format only" passes only with an empty tree compare.
  - The existing guard tests pass (old profiles unchanged).
