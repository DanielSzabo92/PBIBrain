# Power BI Development Center: technical design

Status: ACCEPTED (baseline for the frontend design and for the build). Date: 2026-10-31.

This document tells how the app does each function of the [functional specification](DEV_CENTER_FUNCTIONAL_SPEC.md). It collects the decisions of the wayfinder map `.scratch/dev-center/map.md` (tickets 01 to 14). Each decision has one home ticket. This document gives the decision; the ticket gives the reasons and the facts that were found first.

The words in this document have the meanings in [CONTEXT.md](../CONTEXT.md). Use "Merge Choice" for the choice on one row. The word "decision" means the review decisions of the change guard.

UI look and layout are out of scope. Section 14 gives only the backend data contracts that the UI uses.

## Contents

1. Architecture
2. Sources and connections
3. Graph coverage
4. Alignment and compare
5. Naming rules
6. Change Plan
7. Impact data
8. Change guard for merge
9. TMDL and PBIR write
10. XMLA and Fabric (cloud)
11. Session storage
12. Agent MCP tools
13. Apply
14. Backend data contracts for the UI
15. First-version scope
16. Build steps
17. Open risks
18. Decision records and sources

## 1. Architecture

### 1.1 Processes

| Process | Role in the Development Center |
|---|---|
| Desktop host (`backend/desktop/host.py`, pywebview) | Runs the UI. Owns the in-process JS API. All accepted-state writes and Apply go through this API only. |
| Local HTTP API (`backend/api/app.py`) | Read endpoints for the UI and for the MCP adapter. Agent proposal endpoints. No accepted-state write. Checks host and origin only; it has no authentication. |
| MCP adapter (`backend/mcp_server.py`, stdio, "PBIBrain") | Read tools (`brain_*`) and the agent tools. Calls the local HTTP API through a fixed endpoint allowlist. |
| .NET bridge (`backend/adapters/tabular_metadata/dotnet/`, .NET 8, TOM) | Reads models now. Gets new commands: model write (TOM operations to a temporary TMDL folder), canonical serialization, TOM tree compare, and (cloud) XMLA read and deploy. One exe, no second project. |
| Change guard (`change_guard/`) | Checks each apply: scope, source coverage, static checks, policy, approvals, backup, undo. No Docker or AppContainer isolation for merge. |

### 1.2 New code location

New package `backend/devcenter/`:

| Module | Content |
|---|---|
| `sources` | Source kinds, local loaders, cloud source records, target kinds. |
| `session` | Session folder, `session.json`, `log.jsonl`, lock, migration, secret check, Source Fingerprints. |
| `alignment` | Alignment keys, alignment steps, overrides. |
| `compare` | Property lists, normalization, compare rows. |
| `naming` | Tokenizer, detector, checker, proposer, rule files. |
| `plan` | Plan steps, operations, compiler, sort, removal policies, rewrite, lineageTags. |
| `impact` | Impact items, Breaks and Needs walks, Offers, wireframe, completeness. |
| `apply` | Validation, Desktop-open check, write orchestration, guard contract, verify, change report. |
| `contracts` | One JSON Schema file for each UI and MCP data shape. Contract tests check each shape. |

The repo uses `jsonschema` for contracts (no pydantic). The new code does the same.

### 1.3 Derived and stored data

The session stores only user state (section 11). The engine computes the alignment, the compare rows, the plan, and the impact again from the session state and the sources. Each derived result carries the plan hash (where it applies) and the source snapshot IDs. The same state always gives the same result (deterministic sort, UUIDv5 lineageTags).

## 2. Sources and connections

Home tickets: functional spec section 4, ticket 14.

### 2.1 Source kinds

| Kind | Read (donor, compare, impact) | Write target |
|---|---|---|
| PBIP with TMDL model | Yes | Yes |
| PBIP with TMSL model (`model.bim`) | Yes | No. Message: "Save as TMDL in Power BI Desktop first." |
| Standalone TMDL folder | Yes | Yes |
| Standalone `model.bim` | Yes | No (same message) |
| PBIR report (`byPath` or `byConnection`) | Yes | Yes |
| PBIR-Legacy report | Yes | No. Message: "Convert to PBIR in Power BI Desktop first." |
| PBIX | No. Message: "Save as PBIP in Power BI Desktop." | No |
| Cloud model (XMLA) | Version 1: yes | Version 1.1 (section 10.4) |
| Cloud report (Fabric REST) | Version 1: yes | Version 1.1 (section 10.4) |

### 2.2 Target kinds (version 1)

1. An existing local source.
2. "Empty": the app writes a minimal PBIP skeleton: `.pbism`, `definition/database.tmdl`, `definition/model.tmdl`, and an empty PBIR report bound `byPath` to that model.
3. "Copy of <local source>": the app copies the source folder to a new path that the user selects. The original source stays unchanged.

A session has one target model and zero or one target report. With no target report, the app creates an empty PBIR report bound `byPath` to the target model. A selected target report that binds to a different model shows the rebind impact.

### 2.3 Access types

A cloud connection has the access type `Read` (default) or `Read/Write`. A `Read` source is never a write target. In version 1 no cloud source is a write target; the `Read/Write` type is recorded now, so that version 1.1 needs no session migration.

## 3. Graph coverage

Home ticket: [Which new object types must the graph learn first?](../.scratch/dev-center/issues/06-object-coverage.md).

### 3.1 New object types in version 1

- Hierarchies and levels.
- RLS roles with their table filters. OLS (table and column permissions) as part of a role.
- Report-level measures (`reportExtensions.json`).
- Partitions (M text) and shared expressions.
- Bookmarks: read only (impact, no copy).
- PBIR visual positions (`x`, `y`, `z`, `width`, `height`), groups (`parentGroupName`), page size, page and visual filters.

Later: perspectives, cultures and translations, themes, KPIs, detail rows expressions, mobile layout.

### 3.2 New impact links

| From | To |
|---|---|
| Hierarchy level | Column |
| Visual | Hierarchy |
| Role filter (DAX) | Columns, measures, tables |
| OLS permission | Table or column |
| Report measure (DAX) | Model objects |
| Visual or filter | Report measure |
| Bookmark | Page, visuals, filter fields |
| Partition (M) | Shared expression |

### 3.3 Unknown object types

The write path loads the full model and changes only the planned objects. Unknown objects stay unchanged. The impact completeness block lists the object types that the app could not examine ("not checked").

M text is never parsed, except to find references to shared expressions. A copied table brings the shared expressions that it needs.

## 4. Alignment and compare

Home ticket: [What are the match and compare rules?](../.scratch/dev-center/issues/07-compare-rules.md).

### 4.1 Alignment

- Steps, in this sequence: same lineageTag; same qualified name and type; same name in a different table ("Moved", measures and report measures only); same expression with a different name ("possible rename", user confirms); manual alignment.
- An object that aligns at a step leaves the pool. The lineageTag always wins. A lineageTag that occurs two times in one source is ignored for those objects, with a warning.
- One to one. A row starts from the target object. A donor object with no target object gets its own row (target = Missing).
- A possible rename is proposed only when exactly one candidate exists on each side.
- Alignment keys for objects with no lineageTag:

| Object type | Alignment key |
|---|---|
| Relationship | The two columns at its ends, in any order |
| Calculation item | Calculation group + item name |
| RLS role | Role name |
| OLS permission | Role + table (+ column) |
| Partition | Table + partition name; the table alone when each side has one partition |
| Report page | Page ID, then page display name |
| Visual | Visual ID only (no approximate visual alignment in version 1) |
| Report measure | Home table + name |

- A target object that a donor lineageTag aligns to a different name, while the donor also has an object with the target name, gives a "Renamed" row plus a "name clash" row.
- User overrides (confirmed matches, broken matches, rejected renames) are session state. The computed alignment is not stored.

### 4.2 Compare

- One state for each cell, plus a "changed" mark. Precedence: Type conflict, Missing, Renamed, Moved, Different, Same.
- A table row is "Different" only for its own properties. Columns, measures, hierarchies, and partitions are separate rows.
- Properties that count:

| Object type | Properties that count |
|---|---|
| Measure | expression, format string (or format string expression), display folder, description, hidden, data category |
| Data column | data type, source column, format string, display folder, description, hidden, summarize-by, sort-by column, data category, key |
| Calculated column | the data column list + expression |
| Table | description, hidden, data category; calculated table: + expression |
| Relationship | cardinality, cross-filter direction, active, security filter direction, assume referential integrity |
| Hierarchy | levels (order and columns), display folder, description, hidden |
| RLS role | model permission, filter expression for each table, OLS for each table and column (not members) |
| Partition | mode, M text |
| Calculation item | expression, order, format string expression |
| Shared expression | M text, kind |
| Report measure | expression, format string, display folder |
| Report page, visual | full JSON without key order; plain words name the area: position, visual type, fields, filters, formatting |

- Default compare ignores lineageTag, sourceLineageTag, annotations, `changedProperty` lines, line ending style, and JSON key order. Strict compare also compares annotations and exact text; it ignores only line ending style and JSON key order.
- DAX normalization (default): ignore whitespace, comments, keyword and function name case, name case in references, and quotes on table names. Keep a table prefix on a measure reference.
- The default compare reads references through the alignment ("same after rename"). Strict compare does not.
- M text, descriptions, and format strings: exact text, but ignore line ending style and trailing spaces.
- Plain words: one fixed phrase ID for each property ("expression changed"). Short values also show old and new value ("hidden: No → Yes"). The code diff opens on request.

## 5. Naming rules

Home ticket: [How does the app find and store naming rules?](../.scratch/dev-center/issues/11-naming-rules.md).

- Rule shape: rule ID, scope (object type + optional table or display folder filter), one check kind (prefix, suffix, letter case, separator, unit word, folder by type, regular expression for user rules only), origin (detected or user), status (proposed, confirmed, rejected).
- In scope: tables, data columns, calculated columns, calculated tables, measures, hierarchies, calculation groups, report measures (they use the measure rules).
- Detection from the target model only, when the rules screen opens or the first session for the target starts. Offer a rule at 5 or more objects and 80% or more support (both are settings). Show the support ("37 of 40 measures"). A rejected rule is not offered again.
- Only a confirmed rule or a user rule marks a name. The app checks only names that the plan creates or changes. A rule break is a warning. The name clash check is built in, case-insensitive, and blocking.
- Storage: `<project root>/.pbibrain/naming-rules/<model folder name>.json`; cloud-only target: `%APPDATA%/PBIBrain/naming-rules/<workspace ID>/<model ID>.json`. Not a model annotation. Outside the guard scope.
- Deterministic name proposer: letter case, separator, prefix, suffix and unit word, folder. For a clash, it adds the donor source name in parentheses. Output: name + rule IDs.
- The user can copy the rule set of a different model; the copied rules arrive as "proposed".

## 6. Change Plan

Home ticket: [How does the Change Plan engine work?](../.scratch/dev-center/issues/09-change-plan.md).

### 6.1 Shape

- The plan is derived from the session state each time. Nobody edits it by hand.
- Two levels: a plan step (one Merge Choice or one prerequisite) compiles to one or more operations. Each operation keeps a link to its plan step. The summary counts plan steps: created, deleted, modified, renamed, for each object type, for model and report separately.
- Status: Invalid (blocking items), Valid with warnings, Valid.

### 6.2 Operations

| Level | Operations | Guard contract operation |
|---|---|---|
| Model | `CREATE`, `DELETE`, `REPLACE`, `SET_PROPERTIES`, `RENAME` | `CREATE_OBJECT`, `DELETE_OBJECT`, `SET_PROPERTY`, `RENAME_OBJECT` |
| Model | `RENAME_PAIR` (object with no lineageTag) | linked delete-and-create pair |
| Model | `REWRITE_EXPRESSION` (exact old text, exact new text) | `REPLACE_EXPRESSION` |
| Report | `COPY_PAGE`, `COPY_VISUAL`, `DELETE_PAGE`, `DELETE_VISUAL`, create, delete, replace report measure | `CREATE_OBJECT`, `DELETE_OBJECT` |
| Report | `REBIND_FIELD` (one for each field location) | `CHANGE_BINDING` |

"Promote report measure" is a plan step: create the model measure, rebind the fields, delete the report measure. "Format only" is a separate plan of its own.

### 6.3 Sort

Fixed phases: deletes (dependents first), renames, creates (needs first: table, column, relationship, hierarchy, measure, calculation group, role), replaces and property sets, expression rewrites, report operations in the same phase order. In each phase, a dependency sort. Ties sort by object type, then name. A dependency cycle makes the plan Invalid.

### 6.4 Removal policies

The user sets a policy for each removed object. Default: Block.

- Block: the plan stays Invalid until each dependent is resolved.
- Cascade: remove the dependents transitively. In a visual, remove the field and its filters; remove the visual only when no field stays. A dependent with its own Merge Choice keeps that choice.
- Repoint: one replacement object of the same kind; a warning when the data type is different. Each changed expression is one `REWRITE_EXPRESSION`; each changed field location is one `REBIND_FIELD`.

### 6.5 Rewrite and carry-over

- Token-exact rewrite: change only the reference tokens at the parser positions (`backend/dax/parser.py`). Keep all other text. Scope: measures, calculated columns and tables, calculation items, format string expressions, RLS filters, UDFs, field parameter DAX, report field bindings, `queryRef`, filters, conditional formatting.
- TOM moves relationships, hierarchy levels, sort-by, perspectives, and translations by itself.
- Unselected target dependents of a renamed object: blocking "Breaks" items with the action `include_in_rewrite`.
- Field parameters: rewrite only the DAX. Change `nativeQueryRef` only when it is equal to the old name. Bookmarks that refer to a changed object are "not checked".
- Donor DAX goes through the alignment: each donor reference becomes the aligned target name. A reference with no aligned target object becomes a Need.
- Model changes compile to report operations only for the session's target report. Other reports of the target model show as impact ("not changed by this plan").

### 6.6 lineageTags

- "Take from" on an existing target object: keep the target tag.
- "Take from" for a new object: keep the donor tag when the target does not have it; else a new tag and a warning.
- "Add as new name", or a donor tag that occurs two times in one source: a new tag.
- New tags are UUIDv5 from the session ID and the row key ([ADR 0002](adr/0002-deterministic-lineage-tags.md)).

### 6.7 Needs and clashes

- Each Need is a prerequisite plan step with the default "add from donor" (plan "Valid with warnings").
- A Need mapped to a target object adds rewrite operations.
- A Need with a name clash, or a Need that no donor has, is blocking.
- A name clash row is blocking until the user gives a new name or selects "Keep target". The proposer gives a name.

### 6.8 Where it runs

The Python backend computes and validates the plan and applies the report operations to the PBIR JSON. The .NET bridge applies the model operations to TOM. One guard contract covers the model files and the report files.

## 7. Impact data

Home ticket: [Which impact data does the backend give to the UI?](../.scratch/dev-center/issues/10-impact-data.md).

- One record, the Impact item: stable item ID (hash), direction (breaks or needs), cause (plan step or row), impacted object (source, object ID, type, name, model or report), severity, certainty, reason (phrase ID + text), shortest path (+ count of other paths), blocking flag, allowed actions.
- Severity. Breaks: breaks, changes value, needs review. Needs: will be added, mapped, missing, name clash.
- Certain: analyzer category DIRECT or STRUCTURAL and FACT edges only. Possible: all other items. Possible items never block.
- Blocking: a certain "breaks" item with policy Block and no resolving Merge Choice; an unselected dependent of a renamed target object; a Need with "missing" or "name clash".
- Actions: `include_in_rewrite`, `set_policy_block`, `set_policy_cascade`, `set_policy_repoint`, `add_from_donor`, `map_to_target`, `drop_added_object`, `remove_field`. An action changes only session state.
- Breaks walk: the existing analyzer (`backend/impact/analyzer.py`) on the target graph, extended with the new links. Seeds: each object that the plan deletes, renames, replaces, or changes. Other reports of the target model join as report-only graphs.
- Needs walk (new): upstream in the donor graph from each added object, translated through the alignment, transitive.
- Removal policy data: certain dependents with the Cascade effect for each; Repoint candidates with a data type warning flag.
- Completeness block: status, not-checked object types, unresolved bindings, unreadable remote reports, bookmarks that refer to a changed object, possible-only areas. The backend never truncates the item list.
- Wireframe data: page (ID, name, width, height, hidden, filters), visual (ID, type, title, x, y, z, width, height, group, hidden, status, cause item IDs, filters), report filters. Statuses in priority order: removed, breaks, changes, new, not checked, unchanged. Wireframes: target report after apply, donor reports now, other reports of the target model.
- Offer records (separate from Impact items): donor pages, visuals, and filters that use an added model object. Donor bookmarks show as information only.
- Derived, not stored. `required_tests` stays out of the UI in version 1.

## 8. Change guard for merge

Home ticket: [What must change so that the change guard accepts create, delete, and rename?](../.scratch/dev-center/issues/08-guard-reuse.md).

- Reuse for safety checks only: scope check, file coverage check, backups, undo. No Docker isolation, because the app writes and the agent only proposes.
- Canonical TMDL proof ([ADR 0001](adr/0001-canonical-tmdl-proof.md)): each changed `.tmdl` file must be byte-equal to the TOM serialization of the candidate model. Then the guard compares the full baseline TOM tree with the candidate tree. Each difference must match a plan operation. A difference in any object type, also types that the graph does not model, rejects the apply.
- A non-canonical baseline file blocks the apply and names the file. The app offers a "format only" apply first. The guard accepts it only when the model compare is empty.
- A created object must equal the planned full definition; only `source_file` and `source_location` are ignored.
- Identity map: new entries only for planned creates, removed entries only for planned deletes. The plan sets new lineageTags before the write.
- A rename with no lineageTag is a linked delete-and-create pair; all properties except the name must be equal.
- Each reference rewrite is its own `REPLACE_EXPRESSION` with exact old and new text. No wildcard.
- PBIR: a new file equals the planned content (normalized JSON); a removed file needs a planned delete; a changed file has only its listed property changes.
- App write record replaces the isolation receipt: the candidate folder is exactly the baseline files plus the files of the app's write step, bound by hash to the compiled contract.
- "merge" policy profile: no runtime value test. HIGH and CRITICAL risk, and "not checked" items, need the explicit user approval in the one Apply dialog. One click records all approvals; the guard keeps a separate signed record for each approval purpose. A failed scope, source, or static gate always blocks.
- Cloud targets: the guard checks a local copy first; the deploy runs only after the guard accepts it.

Code areas: `backend/diff/snapshots.py` (`_raw_coverage`, `compare_objects`), `backend/diff/tmdl_source.py` (`account_tmdl`), `change_guard/orchestrator.py` (`validate_candidate`), `change_guard/policy/engine.py`, `change_guard/contracts/schema.py` and `contract-v1.schema.json` (rename pair, write record only), `change_guard/promotion/local.py` (no change).

## 9. TMDL and PBIR write

Home tickets: [How can the app write TMDL safely?](../.scratch/dev-center/issues/01-tmdl-write.md), [Which PBIR versions must the app support?](../.scratch/dev-center/issues/04-pbir-copy.md), [What happens when the app changes files while Power BI Desktop has the project open?](../.scratch/dev-center/issues/05-desktop-open.md).

### 9.1 Model write (bridge)

- New bridge command `write-model`. Input: the model folder path and the ordered operation list (JSON). Steps: read the model with TOM, apply the operations to the TOM tree, serialize TMDL to a temporary folder, read it again to verify, compare it with the plan. Output: the list of changed, added, and removed `.tmdl` files and their bytes in the temporary folder.
- WARNING: Never serialize into the user's `definition` folder. The TOM folder write rewrites every file and deletes each `.tmdl` file that it did not write. Copy only the changed files, through the guard promotion.
- New bridge command `canonical-check`: serialize a model and report each file whose bytes are not canonical (input for "format only").
- New bridge command `tree-compare`: compare two models object by object over the full TOM tree (guard input).
- `RequestRename` changes only the name. The app rewrites DAX itself (section 6.5).
- TOM gives a new object no lineageTag and rejects duplicates only inside one collection. The plan sets the tags; the app checks duplicates over the full model.
- TOM blocks a UDF below compatibility level 1702. The plan makes this a blocking item.
- TOM does not check DAX. The app validates before it writes.
- Output bytes: tabs, CRLF, no BOM (deterministic).
- Update the TOM package from 19.114.12 to the current version in S0, and run the determinism test again.

### 9.2 Report write (Python)

- Update the vendored PBIR schemas first (`backend/adapters/pbir/schemas/`, `tools/vendor_pbir_schemas.py`): report 3.3.0, page 2.1.0, visualContainer 2.13.0, pagesMetadata 1.1.0, bookmark 2.1.0, bookmarksMetadata 1.0.0, reportExtension 1.0.0, versionMetadata 1.0.0. The validator fails closed on an unknown `$schema`.
- Version policy: read all versions; write a changed file in its own version.
- Names: letters, digits, underscore, hyphen. A visual name is unique in its page. Bookmark and report-measure names are unique in the report. On a clash, rename and keep an old-to-new name map.
- Reference fix-ups after copy or rename: page order (`pages.json`), visual group parent, drillthrough binding, visual interactions, report-measure DAX.
- Rebind: replace Entity and Property in each field location (query state, sort, filters, page binding, report-measure DAX). Report rebind: `datasetReference` in `definition.pbir`.
- Refuse in version 1, with a reason: bookmark copy, sync slicer groups, custom visuals, visuals that use static resources. The theme is not copied.
- Do not write `report.json` (PBIR-Legacy), `mobileState.json`, diagram layout files, or `definition.pbir` except for the planned rebind.
- Write UTF-8 without BOM.

## 10. XMLA and Fabric (cloud)

Home tickets: [How does the app read and write cloud models through XMLA?](../.scratch/dev-center/issues/02-xmla-access.md), [How does the app read and write cloud reports through the Fabric REST API?](../.scratch/dev-center/issues/03-fabric-report-api.md).

### 10.1 Sign-in (version 1)

- Interactive Microsoft account sign-in only. MSAL public client with a dedicated Entra app registration. Silent token first, then interactive. Use the Windows broker (WAM).
- Persistent MSAL token cache, protected by Windows. Never in session files or `connection.json`.
- Python gets the token and gives it to the bridge for each call (`Server.AccessToken`). The bridge never stores it. The bridge reports token expiry as a fixed error code; Python gets a new token silently and calls again.
- Service principal sign-in: later.

### 10.2 Cloud model read (version 1)

- New bridge command `cloud-read`: connect through XMLA with TOM, read the full model, export TMDL to a temporary folder. The graph loads it as a donor source.
- "Pull to local PBIP": export the cloud model as TMDL into a local folder that the user selects, with a PBIP skeleton. This is the default flow for a cloud target.
- Source Fingerprint: `Database.LastSchemaUpdate` plus a hash of the canonical model export.

### 10.3 Cloud report read (version 1)

- `POST /v1/workspaces/{workspaceId}/reports/{reportId}/getDefinition`, scope `Report.ReadWrite.All` or `Item.ReadWrite.All`. Handle 202: poll `GET /v1/operations/{id}`, then get the result.
- `getDefinition` can need write permission. A report that the app cannot read shows in the completeness block as "not checked: report not readable", with the fix "export the report to a local PBIP".
- Reports of a cloud model: Power BI "Reports In Group" in the workspace of the model only. Reports in other workspaces show as "not checked: reports in other workspaces". No admin scanner API.
- Source Fingerprint: a hash of the definition parts.

### 10.4 Cloud write (version 1.1)

This design is fixed now so that its build steps (S12, S13) need no new map.

- Only a `Read/Write` connection can be a target. The connect step records the access type.
- Before the first XMLA write, the app shows the warning: after an XMLA write, the service can no longer download the model as a PBIX file. The user must accept it for each model.
- Model deploy: the guard checks the local copy first. Then the bridge command `cloud-deploy` reads the live model, takes a TMDL backup into the session backup folder, applies the same operation list to the live TOM tree, and calls `Model.SaveChanges()` (sends only the changed objects). A metadata-only deploy keeps the partitions and does not refresh data.
- Write conditions (capacity, XMLA read/write setting, enhanced metadata, Contributor role or higher) have no documented test call. The connect step checks the capacity and the role where an API exists. The deploy error is the final signal. The app explains each known error code in plain words.
- Known limits shown before the deploy: a later PBIX republish overwrites the incremental refresh policy; XMLA cannot set data source credentials; live-connected, push, and Excel models are not supported.
- Report write: download the current definition as a backup, then `POST .../updateDefinition` with all parts as InlineBase64 (full replace, PBIR only). The deployed `definition.pbir` must use `byConnection`.
- Order: model first, then report. When the report write fails, the app offers to restore the model from the backup.

## 11. Session storage

Home ticket: [How does the app store a merge session?](../.scratch/dev-center/issues/13-session-storage.md).

- Folder `<project root>/.pbibrain/sessions/<session ID>/`; cloud-only target: `%APPDATA%/PBIBrain/sessions/<session ID>/` (no git).
- `session.json`: canonical JSON (sorted keys, 2-space indent, LF), atomic save on each state change. Content: `schema_version`, session ID, display name, created and updated time (UTC), `revision`, sources, target, compare mode, alignment overrides, Merge Choices by row key, removal policies, prerequisite and Need mappings, item action results, selected Offers, naming rule file path and hash, agent proposals, agent questions with answers, Source Fingerprints, row hashes.
- Not stored: alignment, plan, impact, graph.
- Source references: local = POSIX path relative to the project root, kind, role; cloud = tenant ID, workspace ID, item ID, display names, access type. No absolute paths, user names, e-mail addresses, or tokens.
- `log.jsonl`: append-only; time, author (user or agent), MCP client name, action, target, value before and after, reason, proposal ID, revision after. No hash chain.
- Source Fingerprints and row hashes: checked when a session opens, on "Check sources", and before Apply (blocking). Marks: "source changed", "source object missing", "new since start". A marked row keeps its Merge Choice and needs a user confirm. Agent proposals on a marked row get `source_changed`. No file watcher in version 1.
- After the app's own Apply, the app writes the new target fingerprint and row hashes from its write record.
- `.pbibrain/.gitignore` excludes `connection.json`, the graph database, locks, backups, and temp files. Secret check before each save.
- One open session at a time. A lock file (process ID) makes a second open read-only.
- Integer `schema_version`, forward migration with a backup, refusal of a newer version, refusal of conflict markers and invalid JSON.
- `connection.json`: rename `session_id` to `connection_id`. The app still reads the old key and writes the new key on the next save.

## 12. Agent MCP tools

Home ticket: [What are the exact agent tools?](../.scratch/dev-center/issues/12-agent-tools.md).

- Eight tools in the existing "PBIBrain" MCP server: `session_get`, `compare_rows_list`, `impact_get`, `naming_rules_get`, `name_propose`, `proposal_submit`, `question_ask`, `plan_validate`. The `brain_*` tools stay.
- No write path for the agent ([ADR 0003](adr/0003-accepted-state-only-in-process.md)):
  - Accepted-state writes (section 14.2) and Apply exist only in the pywebview JS API.
  - HTTP has proposal endpoints only. They write proposals with status "proposed".
  - The MCP adapter keeps a fixed endpoint allowlist. A test makes sure that no tool maps to a write endpoint and that no HTTP route for an accepted-state write or Apply exists.
- Stated limit: an agent with shell access as the same Windows user can edit project files directly. The design does not block this. The agent setup notes show it as a warning, and point to the permissions of the agent host.
- `proposal_submit`: `kind` (`merge_choice`, `alignment`, `removal_policy`, `impact_action`, `need_mapping`, `name`), `target`, `payload`, `confidence`, `reason`, `base_revision`. The server rejects confidence below 0.9 (`confidence_below_threshold`), an empty reason (`reason_required`), and a name that breaks a confirmed rule (`naming_rule_violation` with rule IDs).
- Conflicts: `stale_revision`; a new agent proposal for the same target and kind replaces the older agent proposal; an agent proposal never replaces a user choice (`user_choice_exists`).
- `impact_get` and `plan_validate` take `include_proposals` (default true). Apply uses accepted state only.
- `question_ask`: target, text, 2 to 5 options (each with an optional proposal payload), recommended option, reason.
- The tools act only on the session that is open in the app.
- `plan_validate` `mode`: `quick` (DAX parse, reference resolution, blocking rules, duplicate lineageTag check) or `full` (quick + TMDL round trip in a temp folder + PBIR schema check).
- One error shape `{error: {code, message, details}}`. Codes: `not_found`, `session_not_open`, `stale_revision`, `confidence_below_threshold`, `reason_required`, `user_choice_exists`, `naming_rule_violation`, `invalid_payload`, `action_not_allowed`, `source_changed`. Lists page with `limit`, `offset`, `has_more`.

## 13. Apply

Home tickets: 08, 09, 05, 13, and this ticket.

Sequence of a local apply:

1. Source check (fingerprints). A marked row that the user did not confirm blocks.
2. Plan status. Invalid blocks.
3. Desktop-open check through the Desktop bridge:
   - Target open with unsaved changes: blocking item.
   - Target open with no unsaved changes: warning. After the apply, tell the user to select "Apply external changes".
   - Bridge not available: warning "could not check".
4. Canonical check. A non-canonical target file blocks and offers the "format only" apply.
5. Full validation (`plan_validate` full mode).
6. Apply dialog data: plan summary, HIGH and CRITICAL items, "not checked" items, Desktop warning. One approval.
7. Write to a candidate folder: bridge `write-model` for model operations, Python PBIR writer for report operations. App write record.
8. Guard: contract from the compiled plan, scope check, canonical proof, tree compare, PBIR rules, policy "merge", approvals.
9. Promotion: backup, write model and report files together, or nothing (all or nothing).
10. Rescan the target and compare with the plan. Report each difference.
11. Write the new target fingerprint and row hashes. Append the log entry.
12. Optional Markdown change report (for a commit message or a pull request). The app never commits or pushes.

Undo: the user can undo the full apply from the guard backup (`change_guard/promotion/local.py` recovery).

## 14. Backend data contracts for the UI

Each shape has a JSON Schema file in `backend/devcenter/contracts/`. The frontend design uses these shapes and names only. The UI look is a separate round.

### 14.1 Read endpoints (HTTP, `/api/devcenter/...`)

| Endpoint | Returns |
|---|---|
| `GET session` | Session summary: ID, revision, sources (kind, role, access type, status, fingerprint state), target, compare mode, plan status, counts, open and answered questions, open proposals. |
| `GET compare-rows` (filters: type, table, display folder, state, source, page, changed, marks; `limit`, `offset`) | Compare rows: row key, object type, name, state and changed mark for each source, notes ("same after rename"), property phrases with short old and new values, Merge Choice, proposal status, source marks, `has_more`. |
| `GET compare-rows/{row}/diff` | Code diff for one row and one source (DAX, M, TMDL, JSON). |
| `GET plan` (`include_proposals`) | Plan status, summary counts, plan steps with their operations, blocking items, warnings, plan hash. |
| `GET impact` (row ID or "plan"; `include_proposals`; paging) | Impact items, completeness block, Offer records. |
| `GET impact/removal/{object}` | Certain dependents with the Cascade effect; Repoint candidates with type warning flags. |
| `GET wireframe/{report}` | Wireframe data (section 7). |
| `GET naming-rules` | Rules with status, origin, support, break counts. |
| `POST name-propose` | Proposed name and rule IDs (read-only calculation). |
| `POST plan-validate` (`mode`) | Validation result. |
| `GET apply/preview` | Apply dialog data: summary, approvals needed, not-checked items, Desktop status. |
| `GET log` (paging) | Log entries. |

### 14.2 State changes (pywebview JS API only)

`session_create`, `session_open`, `session_close`, `source_add`, `source_remove`, `source_relink`, `target_set`, `compare_mode_set`, `alignment_override`, `merge_choice_set`, `merge_choice_bulk_set`, `removal_policy_set`, `need_mapping_set`, `impact_action_apply`, `offer_select`, `row_confirm` (after a source change), `sources_check`, `naming_rule_confirm`, `naming_rule_reject`, `naming_rule_edit`, `naming_rules_copy`, `proposal_accept`, `proposal_reject`, `proposal_accept_all`, `question_answer`, `format_only_apply`, `apply`, `undo_apply`, `change_report_write`, `cloud_sign_in`, `cloud_connect`, `pull_to_local`.

Each call takes the `base_revision` and returns the new `revision`, or the error shape of section 12. Browser dev mode uses a mock of this API.

### 14.3 Agent proposal endpoints (HTTP)

`POST /api/devcenter/proposals` and `POST /api/devcenter/questions`. They write only proposals and questions.

## 15. First-version scope

### 15.1 Version 1

- Local sources of all kinds in section 2.1 for read. Local TMDL and PBIR as write target.
- Target kinds: existing local source, "Empty", "Copy of <local source>".
- N-way alignment and compare (no fixed limit on donors).
- All six Merge Choices. "Take properties" for measures, columns, relationships.
- Report measures: promote to the model; copy into the target report.
- Model create and copy: tables, columns, measures, relationships, hierarchies, calculation groups and items, UDFs (compatibility level 1702+), RLS roles with OLS, partitions and shared expressions. Field parameters: table copy with DAX rewrite only, shown as "not checked".
- Report carry-over: pages (with drillthrough, tooltip, groups, interactions fix-ups), visuals, page, visual, and report filters.
- Bookmarks: read only for impact.
- Naming rules, impact, wireframes, Offers, removal policies, the full local apply with guard, undo, and change report.
- Agent MCP tools.
- Cloud read: sign-in, cloud model as donor, "Pull to local PBIP", cloud reports of the model's workspace for impact.

### 15.2 Version 1.1

- Cloud write: XMLA delta deploy and Fabric `updateDefinition` (section 10.4).

### 15.3 Later

- Optional value check (live query in donor and target). The analyzer `required_tests` list stays for it.
- Service principal sign-in.
- File watcher for source changes.
- Perspectives, cultures and translations, themes, KPIs, detail rows expressions.
- Bookmark copy, sync slicer groups, custom visuals, static resources, mobile layout.
- Approximate visual alignment.
- Copy a model measure into a `byConnection` report as a report measure.
- Reports in other workspaces and the admin scanner API.
- The features of section 13 of the functional spec (out of scope of this design).

## 16. Build steps

Each build step ends with green automated tests in CI. All acceptance tests run offline, with no Power BI Desktop and no cloud. Bridge tests need the .NET 8 SDK (as the existing native tests). Cloud tests use recorded fake HTTP responses and a fake TOM server interface.

Parallel lanes: S3 and S4 after S2. S5 and S6 after S3 (S6 needs S5 only for plan-seeded Breaks; S6 starts with row-seeded impact). S10 after S6, in parallel with S7 to S9. S11 after S2, in parallel with all others. S12 and S13 after S9 and S11.

### S0. Foundations

- Goal: remove the blockers that all later steps share.
- Code areas: `backend/adapters/pbir/schemas/`, `tools/vendor_pbir_schemas.py`, `backend/desktop/host.py`, `backend/agent.py`, `backend/adapters/tabular_metadata/dotnet/TabularMetadata.csproj`, `tests/fixtures/`.
- Work: update the vendored PBIR schemas (section 9.2); rename `session_id` to `connection_id` with old-key read; update the TOM package; create the "merge lab" fixture set: 3 TMDL models, 2 PBIR reports, 1 TMSL model, 1 PBIR-Legacy report, with known renames, name clashes, moved measures, possible renames, duplicate lineageTags, objects with no lineageTag, a field parameter, a calculation group, a UDF, RLS and OLS, a hierarchy, bookmarks, and a non-canonical TMDL file.
- Depends on: nothing.
- Acceptance tests:
  - A PBIR report with each current schema version validates. An unknown `$schema` still fails closed.
  - An old `connection.json` with `session_id` loads; the next save writes `connection_id` only.
  - The existing native bridge tests pass with the new TOM version. TMDL serialization of the same model twice gives equal bytes.
  - The merge lab fixtures scan without errors.

### S1. Scanner coverage

- Goal: the graph knows the version 1 object types, the new links, and PBIR positions.
- Code areas: `backend/scanner/model_reader.py`, `backend/scanner/report_reader.py`, `backend/scanner/metadata_reader.py`, `backend/graph/schema.py`, `backend/graph/migrations.py`, `backend/adapters/tabular_metadata/dotnet/Program.cs`, `backend/impact/analyzer.py`.
- Depends on: S0.
- Acceptance tests:
  - Each new node type (hierarchy, level, role, role filter, OLS permission, report measure, partition, shared expression, bookmark) is in the graph for the merge lab, from TMDL and from TMSL.
  - Each link of section 3.2 exists for a fixture case.
  - Visual nodes carry x, y, z, width, height, `parentGroupName`; page nodes carry width and height.
  - An unknown object type gives a "not checked" entry, not an error.
  - Existing graph contract tests pass (schema migration forward).

### S2. Session store and local sources

- Goal: create, save, open, and lock a merge session with local sources and a target.
- Code areas: `backend/devcenter/session/`, `backend/devcenter/sources/`, `backend/snapshots/manifest.py` (reuse `source_manifest`, `content_hash`), `backend/desktop/host.py` (JS API methods of section 14.2 for sessions and sources), `backend/devcenter/contracts/`.
- Depends on: S0.
- Acceptance tests:
  - Round trip: create, change, save, open gives an equal `session.json`; the bytes are canonical.
  - An atomic save interrupted after the temp write leaves the old file valid.
  - The secret check refuses a token-like string and an absolute user path.
  - A second open of a locked session is read-only.
  - An older `schema_version` migrates with a backup; a newer one is refused; conflict markers are refused.
  - A changed source file marks the rows ("source changed", "source object missing", "new since start"); Apply-check reports a blocking state until each row is confirmed.
  - "Empty" target writes a skeleton that the bridge loads; "Copy of" leaves the original unchanged (hash compare).
  - A TMSL or PBIR-Legacy target is refused with the fixed message.
  - `.pbibrain/.gitignore` has the runtime entries.
  - No HTTP route changes session state (route list test).

### S3. Alignment and compare

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

### S4. Naming rules

- Goal: detect, store, check, and propose names.
- Code areas: `backend/devcenter/naming/`, `backend/api/app.py` (`naming-rules`, `name-propose`), JS API rule methods.
- Depends on: S2 (S3 for break counts on new names in the plan, later).
- Acceptance tests:
  - The tokenizer splits separators and case changes for a fixed name list.
  - Detection offers a rule at 5 objects and 80%, not at 4 objects or 79%; the limits come from settings.
  - A rejected rule is not offered again.
  - The proposer applies the fixed order and returns the rule IDs; a clash adds "(<donor source>)".
  - A user regular-expression rule checks a name.
  - The rule file is in `.pbibrain/naming-rules/` and outside `definition/`; a bridge TMDL write leaves it.
  - Copy of a rule set gives "proposed" rules.

### S5. Change Plan engine

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

### S6. Impact data

- Goal: Impact items, Needs, Offers, wireframes, completeness.
- Code areas: `backend/devcenter/impact/`, `backend/impact/analyzer.py`, `backend/api/app.py` (`impact`, `removal`, `wireframe`).
- Depends on: S3 (row seeds), S5 (plan seeds).
- Acceptance tests:
  - For fixture plans, the Impact item set equals a golden file (severity, certainty, reason ID, path, blocking, actions).
  - Item IDs are stable across runs.
  - A possible item never blocks.
  - The Needs walk is transitive and translates through the alignment.
  - Other reports of the target model carry "not changed by this plan".
  - Cascade preview lists the effect for each dependent; Repoint gives same-kind candidates with type warnings.
  - Wireframe data for the merge lab target equals a golden file; statuses follow the priority order.
  - Offers list donor pages, visuals, and filters; a bookmark shows as information only.
  - The completeness block lists not-checked types, unresolved bindings, and bookmarks.
  - Budget test (section 17, risk R6): plan and impact under 5 s on the generated large set.

### S7. Writers

- Goal: produce candidate model and report files from operations.
- Code areas: `backend/adapters/tabular_metadata/dotnet/Program.cs` (`write-model`, `canonical-check`, `tree-compare`), `backend/adapters/tabular_metadata/bridge.py`, new `backend/adapters/pbir/writer.py`.
- Depends on: S5.
- Acceptance tests:
  - Each model operation type applied by `write-model` to a fixture gives the expected TMDL (golden), and the temp folder reloads.
  - The user `definition` folder is never a write destination (test that the command refuses it).
  - Non-`.tmdl` files near the model stay.
  - `canonical-check` finds the non-canonical fixture file; "format only" makes it canonical with an empty tree compare.
  - `tree-compare` reports a change in an object type that the graph does not model (perspective).
  - The PBIR writer: page copy with a name clash keeps the old-to-new map and fixes `pages.json`, groups, drillthrough, and interactions; `REBIND_FIELD` changes each field location; a changed file keeps its schema version; output validates against the vendored schemas; no BOM.
  - Refused items (bookmark copy, sync slicer groups, custom visuals, static resources) give fixed reasons.

### S8. Guard for merge

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

### S9. Local apply

- Goal: the full apply sequence of section 13, with undo.
- Code areas: `backend/devcenter/apply/`, `backend/desktop/host.py` (`apply`, `format_only_apply`, `undo_apply`, `change_report_write`), `change_guard/promotion/local.py`, the Desktop bridge client.
- Depends on: S6, S8.
- Acceptance tests:
  - End to end on a temp copy of the merge lab: apply, rescan, and the rescan matches the plan with no difference.
  - A failure in the report write leaves the model files unchanged (all or nothing).
  - Undo restores all files byte-equal to the backup.
  - A fake Desktop bridge with "unsaved changes" blocks; "open, saved" warns; "not reachable" warns.
  - Unconfirmed source marks block.
  - Agent proposals that are not accepted have no effect on the written files.
  - After apply, no row shows "source changed".
  - The change report has the plan summary.
  - End-to-end budget: the full apply of the merge lab in a fixed time (record the value in S9 and keep it as a regression limit).

### S10. Agent MCP tools

- Goal: the eight tools and the proposal endpoints.
- Code areas: `backend/mcp_server.py`, `backend/api/app.py` (proposal endpoints and reads), `backend/devcenter/session/` (proposals, questions, log).
- Depends on: S6 (S7 for `plan_validate` full mode).
- Acceptance tests:
  - Each tool returns the contract shape (JSON Schema).
  - Allowlist test: no tool maps to a route outside the read and proposal set; no HTTP route for an accepted-state write or Apply exists.
  - Confidence 0.89 gives `confidence_below_threshold`; an empty reason gives `reason_required`; a confirmed-rule break gives `naming_rule_violation` with rule IDs.
  - `stale_revision`, `user_choice_exists`, `source_changed`, and replacement of an older agent proposal.
  - `include_proposals` true and false give different plans; Apply ignores proposals.
  - Each proposal and question writes a log entry with the MCP client name.
  - Paging with `has_more`.

### S11. Cloud read

- Goal: sign-in, cloud model donor, "Pull to local PBIP", cloud report impact.
- Code areas: new `backend/devcenter/sources/cloud.py`, the bridge (`cloud-read`), MSAL token cache setup.
- Depends on: S2. Real-tenant checklist depends on task T1 (section 17).
- Acceptance tests (offline, fakes):
  - Token flow: silent first, then interactive; no token in any session file or `connection.json` (scan test).
  - Expired token: one silent refresh and a retry.
  - `cloud-read` against the fake server interface gives a TMDL donor that scans.
  - "Pull to local PBIP" writes a folder that the local loader opens as a target.
  - `getDefinition` 202 polling with recorded responses; a 403 gives "not checked: report not readable".
  - "Reports In Group" filters by dataset ID; other workspaces show as "not checked".
  - Fingerprints: `LastSchemaUpdate` change marks the source.
- Manual: the real-tenant checklist (T1) before release.

### S12. Cloud model write (version 1.1)

- Goal: XMLA delta deploy after the guard accepts the local copy.
- Code areas: the bridge (`cloud-deploy`), `backend/devcenter/apply/`.
- Depends on: S9, S11.
- Acceptance tests (fakes): a `Read` connection is never a target; the PBIX warning shows once for each model and needs acceptance; the backup exists before `SaveChanges`; only planned objects change on the fake server; each known error code maps to a plain-word message.

### S13. Cloud report write (version 1.1)

- Goal: Fabric `updateDefinition` after the model deploy.
- Code areas: `backend/devcenter/sources/cloud.py`, `backend/devcenter/apply/`.
- Depends on: S12.
- Acceptance tests (recorded fakes): backup download first; all parts sent as InlineBase64; `definition.pbir` uses `byConnection`; a report write failure offers the model restore.

## 17. Open risks

| ID | Risk | Effect | Mitigation |
|---|---|---|---|
| R1 | No test against a real Fabric or Power BI workspace. | Cloud read can fail in ways that fakes do not show. | Task T1: the user registers the Entra app (public client, WAM redirect, Power BI and Fabric scopes) and runs the real-tenant checklist before release. Until then S11 uses fakes only. |
| R2 | `getDefinition` can need write permission. | A `Read` user cannot read a cloud report. | "Not checked" with the fix "export to a local PBIP". Confirm in T1. |
| R3 | Power BI Desktop can write TMDL bytes that are not TOM-canonical. | Many first applies need "format only". | "Format only" apply; measure the rate on real projects in S7. |
| R4 | The field parameter metadata and the `nativeQueryRef` rule are not documented. | A rename can break a field parameter silently. | DAX-only rewrite; "not checked" in the apply dialog. |
| R5 | The Desktop "Apply external changes" result with "Cancel" is not documented. | A later Desktop save can overwrite the apply. | Block on unsaved changes; tell the user to apply external changes at once. |
| R6 | Large models. | Slow compare and impact. | Budgets on a generated set (5 sources × 5,000 objects, 200 visuals): alignment and compare under 10 s, plan and impact under 5 s, quick validate under 5 s. Above a budget the app works and shows the elapsed time. |
| R7 | An agent with shell access can edit project files. | The proposal-only rule does not hold against shell writes. | Stated limit and setup warning (section 12). Guard source checks show unplanned file changes at the next apply. |
| R8 | The TOM package update can change the serialization bytes. | Golden files and canonical checks change. | Update in S0, before golden files exist. |
| R9 | Cloud write (1.1): write conditions have no test call; a later PBIX republish overwrites the refresh policy. | Deploy errors after the user approved. | Plain-word error mapping; warnings before deploy. |

## 18. Decision records and sources

### 18.1 ADRs

- [ADR 0001: The guard proves model writes by a canonical TMDL check and a full tree compare](adr/0001-canonical-tmdl-proof.md)
- [ADR 0002: Deterministic UUIDv5 lineageTags for new objects](adr/0002-deterministic-lineage-tags.md)
- [ADR 0003: Accepted-state changes and Apply only in the in-process JS API](adr/0003-accepted-state-only-in-process.md)

### 18.2 Home tickets

| Area | Ticket |
|---|---|
| TMDL write | `.scratch/dev-center/issues/01-tmdl-write.md` |
| XMLA | `.scratch/dev-center/issues/02-xmla-access.md` |
| Fabric reports | `.scratch/dev-center/issues/03-fabric-report-api.md` |
| PBIR copy | `.scratch/dev-center/issues/04-pbir-copy.md` |
| Desktop open | `.scratch/dev-center/issues/05-desktop-open.md` |
| Graph coverage | `.scratch/dev-center/issues/06-object-coverage.md` |
| Alignment and compare | `.scratch/dev-center/issues/07-compare-rules.md` |
| Guard | `.scratch/dev-center/issues/08-guard-reuse.md` |
| Change Plan | `.scratch/dev-center/issues/09-change-plan.md` |
| Impact | `.scratch/dev-center/issues/10-impact-data.md` |
| Naming rules | `.scratch/dev-center/issues/11-naming-rules.md` |
| Agent tools | `.scratch/dev-center/issues/12-agent-tools.md` |
| Session storage | `.scratch/dev-center/issues/13-session-storage.md` |
| Scope and build order | `.scratch/dev-center/issues/14-first-version.md` |

Research branches (not merged): `research/tmdl-write`, `research/xmla-access`, `research/fabric-report-api`, `research/pbir-copy`, `research/desktop-open`.
