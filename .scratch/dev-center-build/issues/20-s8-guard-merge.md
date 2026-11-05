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

## Build record

What I built:
- `change_guard/merge.py` (new): the merge guard.
  - `build_merge_proposal` compiles a Change Plan into an exact contract with a `merge` section: the ordered plan operations, the model and report paths, and the report file expectations from a trial write (new file content, deleted files, and the listed JSON property changes of each changed file).
  - `write_merge_files` is the app write step: it runs the S7 writers (`write-model`, PBIR writer) and copies only the changed, added, and removed files into the candidate.
  - `write_record` makes the app write record (files and hashes, bound by hash to the contract and to the baseline manifest). It replaces the isolation receipt.
  - `verify_merge_candidate` gives the gates: security (write record), source (canonical TMDL proof, byte-equal regeneration of the model files from the plan, no unplanned file), and scope (each TOM tree compare difference matches a plan operation, identity map, rename pair, report properties, format only).
- Reject codes: `WRITE_RECORD_MISSING`, `WRITE_RECORD_HASH_MISMATCH`, `WRITE_RECORD_FILE_MISMATCH`, `NON_CANONICAL_BASELINE_FILE`, `NON_CANONICAL_MODEL_FILE`, `MODEL_NOT_PLAN_OUTPUT`, `MODEL_LOAD_FAILED`, `UNPLANNED_FILE_CREATED`, `UNPLANNED_FILE_DELETED`, `UNPLANNED_FILE_CHANGED`, `UNPLANNED_MODEL_CHANGE`, `REQUIRED_MODEL_CHANGE_MISSING`, `UNPLANNED_IDENTITY_ENTRY`, `UNPLANNED_IDENTITY_REMOVAL`, `RENAME_PAIR_PROPERTY_CHANGED`, `FORMAT_ONLY_MODEL_CHANGED`, `UNPLANNED_REPORT_PROPERTY`, `REQUIRED_REPORT_CHANGE_MISSING`, `REPORT_FILE_CONTENT_MISMATCH`.
- `change_guard/policy/engine.py`: `Policy.profile` and `merge_policy()`. The merge profile has no runtime value test. HIGH and CRITICAL risk need `HIGH_RISK_PROMOTION`; unchecked items need `UNCHECKED_IMPACT`. A gate that is not PASSED rejects. The standard profile keeps its old policy hash.
- `change_guard/contracts/schema.py` and `contract-v1.schema.json`: the `RENAME_PAIR` operation (merge only), the optional `merge` section, and the `write_record` definition.
- `backend/diff/snapshots.py`: `compare_snapshots(..., proven_sources=...)`. The line accounting skips a file that the merge proof covers. `tmdl_source.py` has no change (ADR 0001: no extension of the line check).
- `change_guard/orchestrator.py`: `write_merge_candidate` (app write step and write record), the merge branch of `validate_candidate`, a merge impact record, and the `UNCHECKED_IMPACT` approval purpose. `run_agent` refuses a merge contract. A merge contract and a standard policy (or the opposite) give `PROFILE_MISMATCH`.

Tests (`tests/test_change_guard_merge.py`, 16 tests):
- Fixture plans: (1) the compiled merge of SalesB into SalesA (model create, rename, rewrite, field parameter rewrite, page copy, rebind, report measure promote); (2) model operations on SalesA (create, delete, rename, rewrite, set properties, table rename, role rename pair); (3) format only on Finance. Each gets PASS.
- Mutations: each gives its code (extra property, extra file, removed file, non-canonical changed file, unplanned identity entry, rename pair with a second change, extra PBIR property, changed perspective).
- Write record: missing, tampered, wrong contract, and a file change after the write step reject.
- HIGH risk: the orchestrator does not promote without the approval record; with it the promotion completes and the post-promotion check passes.
- Format only: passes with an empty tree compare, rejects a model change. A plan on a non-canonical baseline names `tables/Budget.tmdl`.

Test commands and results:
- `python -m unittest tests.test_change_guard_merge`: 16 tests, OK (about 100 s, because each check calls the TOM bridge 6 times).
- `python -m unittest tests.test_guarded_development tests.test_guard_user_decisions tests.test_guard_coverage_expansion tests.test_git_guard_promotion tests.test_pbir_coverage`: 75 tests, OK (old profiles unchanged).
- No kit gates: this step has no screen.

Notes:
- SalesB has duplicate lineageTags, so `write-model` refuses SalesB as a target. The guard fixtures use SalesA and Finance as targets.
- The TOM tree compare keys objects by name. A rename shows as DELETED and ADDED. A relationship of a renamed table or column shows as DELETED and ADDED with the same name. A table expression rewrite (calculated table, field parameter) shows as a partition expression change. The guard accepts these only when a planned rename or rewrite explains them, and the byte-equal regeneration proves the rest.
