# 07: S3 alignment compare

Status: open. Lane: backend. Design step: S3 (docs/DEV_CENTER_TECHNICAL_DESIGN.md section 16).

Depends on (tickets): [03](03-s1-scanner-coverage.md), [04](04-s2-session-store.md).

The goal, the code areas, and the acceptance tests are the design text below. Each acceptance test must be an automated test, except the items that the design marks as manual.

### Design text: S3. Alignment and compare

- Goal: N-way compare rows with states, marks, and plain-word phrases.
- Code areas: `backend/devcenter/alignment/`, `backend/devcenter/compare/`, `backend/dax/parser.py` (normalization tokens), `backend/diff/snapshots.py` (reuse `compare_properties` where it fits), `backend/api/app.py` (`compare-rows`, `diff`).
- Depends on: S1, S2.
- Acceptance tests:
  - For the merge lab, the full compare row set equals a golden file (states, marks, notes, phrases).
  - lineageTag wins over name: the "Renamed" plus "name clash" case.
  - A duplicate lineageTag is ignored with a warning.
  - Each alignment key of section 4.1 aligns its fixture case.
  - A possible rename appears only with one candidate on each side.
  - Default DAX normalization: each rule of section 4.2 has a pass and a fail case; `[Total]` is not equal to `Sales[Total]`.
  - "Same after rename" in default mode; "Different" in strict mode.
  - Alignment overrides from the session change the rows.
  - Same input twice gives the same row order and IDs.
  - UC20: `GET display-folders?source=<id>` returns the display folder paths of a merge lab source; the object type filter limits them.
  - UC21: `alignment_override` break removes the Merge Choice of the row and returns the new row keys.
  - UC23: `q` filters compare rows by name, case-insensitive.
  - UC24: `total` and `state_counts` equal the counts of the full filtered row set.
  - UC25: `sort` by state, name, type, and table, asc and desc, gives a stable order.
  - UC26: `row_state` is the highest-precedence cell state, and the `state` filter uses it.
  - UC31: `phrases.json` holds each compare phrase ID that the engine uses; the contract test refuses an em or en dash, an emoji, and text over 60 characters.
