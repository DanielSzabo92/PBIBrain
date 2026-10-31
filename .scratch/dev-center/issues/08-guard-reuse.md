# What must change so that the change guard accepts create, delete, and rename?

Type: grilling
Status: resolved
Blocked by: 01

## Question

The guard now accepts only property edits and fails closed on create and delete. The merge reuses only its safety checks (no Docker). What must the contract, the scope check, and the file coverage check learn so that they accept a Change Plan with create, delete, rename, and reference rewrite, and still reject changes outside the plan?

## Answer

Resolved with the user on 2026-10-31. The user accepted all proposed defaults.

### Facts found first

- The contract schema already lists `CREATE_OBJECT`, `DELETE_OBJECT`, `RENAME_OBJECT`, `REPLACE_EXPRESSION`, and the reference operations (`change_guard/contracts/contract-v1.schema.json`, `change_guard/contracts/schema.py`). Create and delete use the property `$object`. The scope check (`enforce_scope`) already maps `OBJECT_CREATED` and `OBJECT_DELETED` to these operations.
- The fail-closed behavior comes from two other gates:
  - Raw source coverage (`backend/diff/snapshots.py`, `_raw_coverage`; `backend/diff/tmdl_source.py`, `account_tmdl`). It accepts only `SOURCE_CHANGED` files, and in TMDL only line replacements of the same length. A new file, a removed file, an added line, or a removed line gives `UNKNOWN_DIFFERENCE`.
  - The security gate (`change_guard/orchestrator.py`, `validate_candidate`). It requires a Docker or AppContainer isolation receipt. Without a receipt, the status is `NOT_RUN` and the policy gives `INCONCLUSIVE`.
- The scope check compares a created object with `expected_after` as the full scanned object, also with `source_file` and `source_location`.
- Object IDs come from the lineageTag. With no lineageTag, the ID comes from the name (`StableIdentity`). Thus a rename of an object with no lineageTag shows as one delete plus one create. A rename without an authoritative identity gives `UNKNOWN_DIFFERENCE`.
- A change of the identity map gives `IDENTITY_CHANGED` on `$identity`. This object is not a contract target, so each new object would fail the scope check.
- The policy (`change_guard/policy/engine.py`) requires a certified runtime test for HIGH and CRITICAL risk. Relationships, tables, columns, and security objects are HIGH or CRITICAL.
- Promotion (`change_guard/promotion/local.py`) already backs up, writes, and deletes files, and recovery restores them. Backups and undo need no change for create and delete.

### Decisions

1. Model file proof: "canonical TMDL" proof. Do not extend the line-by-line accounting. For each changed `.tmdl` file, the candidate bytes must be equal to the TOM serialization of the candidate model. Then the guard compares the baseline model and the candidate model object by object. Each difference must match a plan operation.
2. Non-canonical baseline file (comments, hand edits, other order or indentation): a TOM rewrite of that file changes text outside the plan. The guard blocks the apply and names the file. The app offers a separate "format only" apply first. The guard accepts a format-only apply only when the model comparison is empty.
3. Compare scope: the guard compares the full TOM tree, also object types that the graph does not model yet (for example perspectives). A difference outside the plan in any object rejects the apply.
4. Created object: the guard compares the full object definition. It ignores only scanner location fields (`source_file`, `source_location`). The app produces the object, so an exact match is possible.
5. lineageTag: the Change Plan sets the new lineageTag of each created object before the write. Thus the contract knows the object IDs of new objects. The guard accepts new identity-map entries only for planned creates, and removed entries only for planned deletes.
6. Rename of an object with no lineageTag (roles, partitions, calculation items, report pages, and others): the contract states the rename as one linked delete-and-create pair. The guard accepts the pair only when all properties except the name are equal.
7. Reference rewrite: each changed expression is a separate `REPLACE_EXPRESSION` operation with the exact old text and the exact new text. The contract has no wildcard and no "update all references" operation.
8. Security gate without isolation: an "app write record" replaces the isolation receipt. The candidate folder must be exactly the baseline files plus the files that the app's write step produced. A hash binds the record to the contract (the compiled Change Plan).
9. Policy: a separate "merge" policy profile. It does not require a runtime value test. HIGH and CRITICAL risk require the explicit approval of the user in the apply dialog. A failed scope gate, source gate, or static gate always blocks.
10. Incomplete impact (for example calculation groups and field parameters): the guard does not block. The apply dialog shows the items that the app did not check, and the user must give an explicit approval.
11. Report files (PBIR): a new file must be equal to the planned object content (normalized JSON compare). A removed file needs a planned delete. A changed file must have only its listed property changes. This is the same rule as for the model.
12. Approvals: one "Apply" dialog after the preview. It lists the high-risk items and the items that the app did not check. One click records all necessary approvals. The guard keeps a separate signed record for each approval purpose.
13. Cloud targets: the guard always checks a local copy. A cloud deploy (XMLA or Fabric REST) starts only after the guard accepts that local copy.

### Consequences

- The work is in the guard gates (raw coverage, security gate, policy profile, identity map), not in the contract schema. The schema needs only the linked rename pair (decision 6) and the app write record (decision 8).
- ADR candidate for the technical design: decision 1 (canonical TMDL proof instead of line accounting). It is hard to reverse, and a reader can ask why the line check was not extended.
