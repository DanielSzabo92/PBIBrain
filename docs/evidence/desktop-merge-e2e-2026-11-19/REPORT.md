# Desktop merge end-to-end test: three PBIP sources into a new model and a new report

Date: 2026-11-19
Branch: `test/desktop-merge-e2e` (worktree `PBIBrain-wt/desktop-merge-test`), from `origin/main` at `2b56733`.
App: the desktop app (`python -m backend.desktop`, pywebview). The web GUI was not tested.
Power BI Desktop: opened through the `powerbi-desktop` CLI and through the Desktop start page.

## 1. Summary

| Requirement | Unpatched app | With the test-only patches |
|---|---|---|
| R1. Models load from PBIP files | PASS | PASS |
| R2. A new model and a new report give one PBIP with a report folder and a model folder | Not reached (apply cannot run) | PASS for the structure |
| R3. The merge session is clear, easy to manage, and the backend builds the model and report correctly | FAIL | FAIL (output is not correct) |
| R4a. The output opens in Power BI Desktop | Not reached | PASS, with a "not upgraded to the enhanced metadata format" banner |
| R4b. The output loads data (refresh) | Not reached | FAIL |

The unpatched app cannot finish a merge into a new empty target. I found 3 blocking defects before the apply starts and 3 more in the write step.
With 5 test-only patches, the apply passes. The output opens in Power BI Desktop, but the data refresh fails.
Two hand edits of copies of the output (the model header and the CSV paths) do not make the data load. A third error ("cyclic reference") stays. The untouched Sales source refreshes without an error, so the merge causes this error.

The defects with the highest impact:
1. The frontend sends the Merge Choice in a shape that the backend contract refuses. No choice can be saved from the grid.
2. The plan and the model writer use different property names. The write fails, and without the fix hidden flags and the `SourceFolder` body are lost.
3. Compare sorts the relationship ends by name. The writer takes the first end as the "many" side. Every relationship where the dimension name sorts first comes out reversed.
4. The empty-target skeleton `model.tmdl` deadlocks the format check and the guard.
5. Model-level properties (`culture`, `defaultPowerBIDataSourceVersion: powerBI_V3`, `dataAccessOptions`) are not in the output.
6. "Skip" on a visual has no effect. The whole page is copied.

On 2026-11-20, an independent code review of the Merge tab was compared with this test (section 13). Most of its claims hold in the code. It adds these high-impact defects, which this run did not exercise:
7. Bulk Undo with "all matching rows" erases the Merge Choices of rows that are not loaded in the grid (data loss).
8. Repoint policies, Need mappings and "include in rewrite" actions never reach the plan compiler. The writers and the compiler use different keys and field names.
9. An existing report as the target fails the PBIR check when its root `definition.pbir` has no `$schema`. This applies to 5 of the 7 mock reports.
The independent review did not examine the write step and the output. Items 2 to 6 above are found only by this run.

## 2. Scope and reading of the request

- "Use three tops to check": I read this as "use the first three source projects". These are `1_finance_Aevum`, `2_sales_Veloce` and `3_ecommerce_NexusCohort` in `C:\Users\Daniel\Desktop\Mock data`.
- I used copies of the sources in `.scratch/e2e-run/sources/`. The originals did not change.
- Target: model target mode "Empty" and report target mode "New empty", in a new folder.
- Only the desktop layout was tested.

## 3. Setup

1. Pulled `origin/main`. Made the worktree and the branch.
2. Ran `npm ci` and `npm run build` in `frontend/`. Built the TOM bridge (`TabularMetadata.csproj`).
3. Started the app with `PBIBRAIN_HOME=.scratch/e2e-run/home`.
4. Opened `.scratch/e2e-run/sources` as the project.

### 3.1 Source problems found before the merge

| Source | Opens in Power BI Desktop | Problem |
|---|---|---|
| Finance | Yes, with data | The `TMDLScripts\` folder holds a TMDL view script. Desktop ignores it. The app gives the `.SemanticModel` folder (not `definition\`) to the bridge read, so TOM reads the script as model definition and fails (`createOrReplace`). Checked on 2026-11-20: the bridge read of `Finance.SemanticModel` fails, and the read of `Finance.SemanticModel/definition` passes. Thus the app is at fault, not the source. |
| Sales | Yes, with data | None. A fresh refresh also passes (screenshot 15). |
| Ecommerce | No | `expression SourceFolder` is in `model.tmdl` and in `expressions.tmdl`. Desktop shows "TMDL objects cannot be merged because both declare the same property". The `SourceFolder` path also points to `...\3_ecommerce`, a folder that does not exist. |

Microsoft Learn confirms that `TMDLScripts\` holds TMDL view scripts and is not part of the semantic model definition.

Workarounds in the copies only:
- Finance: moved `TMDLScripts` to `.scratch/e2e-run/removed/`.
- Ecommerce: removed the duplicate `expression SourceFolder` from `model.tmdl`. Changed the path to `...\3_ecommerce_NexusCohort`.

The app scan did not report either problem. It showed "Graph validation passed" for the Ecommerce model that Desktop refuses.

## 4. R1: models load from PBIP files: PASS

- Overview counts match the TMDL files: 3 models, 20 tables, 105 columns, 22 measures, 3 reports, 3 pages, 22 visuals.
- Minor findings:
  - 16 warnings "M source not read" for `#"SourceFolder" & "\x.csv"`. This pattern is the most common CSV pattern in Power BI Desktop. The scanner cannot read a parameter concatenation.
  - The status bar shows "No data yet" next to "Scanned".
  - After an apply, the Overview says "3 files changed outside PBIBrain since the last scan". The app itself made these changes.

## 5. R3: the merge session in the unpatched app (Run A): FAIL

### 5.1 Blocking defects

| ID | Defect | Effect |
|---|---|---|
| A1 | The compare grid drops a source when its model read fails. `compare/service.py` `_sources` catches `DevCenterError` and sets the objects to `None`. For Finance, the read fails because `compare/extract.py` `_read_model` reads the `.SemanticModel` folder and not `definition/` (see 3.1). The bridge `write_model` already selects `definition/`. | Finance and Ecommerce were silently absent. Sources showed "Found". The plan showed "Valid". The cells said "Not checked" and gave no reason. |
| A2 | The grid sends `{choice, source}` for bulk, inline (Keep/Take/Skip) and keyboard choices. The JS API contract requires `{kind, source_id, ...}` with `additionalProperties: false`. | No Merge Choice can be saved. No error message shows. The inline button shows "Saved" before the reply comes back. |
| A3 | The empty-target skeleton writes `model.tmdl`. The TOM canonical serialization of an empty model has no `model.tmdl`. | The format check marks the skeleton as non-canonical. "Format TMDL" then DELETES `model.tmdl` and reports "model did not change". Apply then blocks with "TMDL format only". The session deadlocks. |

### 5.2 Other defects (UI and copy)

1. The default filter "Not same" is always empty in the real app. The grid sends `state=not_same`. The backend `filter_rows` has no such state; only the mock server knows it. "Show these rows" opens the same empty grid (screenshot 01).
2. The detail panel says "Finance changed" when Ecommerce changed.
3. The row state "Missing" (the target is empty) hides conflicts between donors. Example: `SourceFolder` is different in all three donors.
4. Bulk Set Merge Choice (after the A2 fix) sets the choice on all selected rows. This includes the rows that the dialog says it skips. The dialog count "1 row already has a different choice" was stale.
5. Name clash ("Gross Revenue" in Finance and Ecommerce): the guard catches it. But the message names no object, says "in use in the target" for an empty target, and suggests "Keep target", which cannot apply. The naming rule proposed the same clashing name.
6. Skip of "Win Rate" is blocked because a Sales visual needs it. This is correct. The message ("An object that this object needs…") names no objects.
7. Plan and Impact give no warning that one `SourceFolder` (from the first donor) breaks the CSV paths of the other donors.
8. Visuals show as hex IDs. Relationships show as GUIDs.
9. "Full check" times mix UTC and local time.
10. "Sources 4" in the list counts the target as a source.
11. "Empty" target opens a native folder picker at once. There is no field for the model name. The session name becomes the model name.
12. "Duplicate session" makes an empty session with no sources.
13. The Apply dialog lists about 140 to 170 items, all "Critical" (screenshot 04). A user cannot examine these items in a useful way.
14. Undo of "Format TMDL" failed with "Power BI Desktop has unsaved changes". No Desktop instance was open. The copy comes from `failureReason` in `applyModel.js`, which maps the step to a fixed message. The real error is hidden.
15. After a hand restore of `model.tmdl`, an orphan mark `new_since_start` on `model:Model` showed. No UI control can confirm it. The session stayed blocked.

## 6. R3: the write step (Run B, with patches 1 and 2): FAIL

Session `MergedThreeB`, target `.scratch/e2e-run/target2`.
Choices: take the first donor for each row. "Gross Revenue" (Ecommerce) renamed to "Gross Revenue (Ecommerce)". Skip two visuals and "Win Rate".
Plan: valid, 191 operations.

| ID | Defect | Evidence |
|---|---|---|
| B1 | `pipeline.write` catches every exception and raises `write_failed`. The UI says "The write record does not match the candidate files". The real cause is not logged. | Found with a scratch reproduction (`.scratch/repro_write.py`). |
| B2 | Property names in the plan do not match `ModelWriter.cs`. The plan sends `hidden`, `m_text`, `active`, `cross_filter_direction`. The writer reads `is_hidden`, `expression` / `partition_expression`, `is_active`, `cross_filtering_behavior`. | Hidden flags are lost. The expression `SourceFolder` gets an empty body. Partitions get a placeholder `#table` query. |
| B3 | A table create in `ModelWriter.cs` also adds a partition with the table name. The plan then creates the same partition. | `ModelWriteFailed: Item 'Dim_Accounts' already exists in the collection.` |
| B4 | The guard source gate has the same problem as A3. The skeleton `model.tmdl` gives `NON_CANONICAL_BASELINE_FILE`. | Guard rejects the candidate. |
| B5 | Skip on a visual has no effect. `COPY_PAGE` copies all visuals of the page. | `v10000000000000000004` and `1cc390d6804c07583e99` are in the candidate. The guard static check then fails: "Visual binding could not resolve object reference 'Win Rate'". |

To continue, I changed "Win Rate" from Skip to Take. Thus the user choice "Skip Win Rate" could not be kept.

## 7. R2 and the apply result (Run B, with all 5 patches)

Apply: all checks and write steps "Done" (screenshot 05). The result says "Plan applied with 5 differences":
- `page`: expected 3, found 2.
- 4 partitions of calculated tables (`DateTableTemplate_*`, `LocalDateTable_*`): expected absent, found present. The plan did not include these partitions. TOM adds them.

Output on disk (`target2`):

```
MergedThreeB.pbip
MergedThreeB.Report/        definition.pbir -> byPath ../MergedThreeB.SemanticModel
  definition/pages/         page1 (0 visuals), ReportSectionf4214… (16), a0884120… (6)
MergedThreeB.SemanticModel/
  definition/               database.tmdl, model.tmdl, expressions.tmdl, relationships.tmdl, tables/ (18)
```

Checks:
- PASS: one `.pbip`, one report folder, one model folder, `byPath` is correct.
- PASS: `Net Revenue = [Gross Revenue (Ecommerce)] - …`. The rename updated the reference.
- PASS: no duplicate `lineageTag`.
- PASS: the guard graph check resolved all visual fields.
- FAIL: the skipped visuals are present (B5).
- FAIL: `model.tmdl` has no `culture`, no `defaultPowerBIDataSourceVersion: powerBI_V3`, no `sourceQueryCulture`, no `dataAccessOptions`. The skeleton does not set them, and the merge does not copy them from a donor.
- FAIL: one `SourceFolder` (Finance). 9 Sales and Ecommerce tables point to the Finance folder.
- FAIL: table annotations (`PBI_ResultType`, `PBI_NavigationStepName`, `SummarizationSetBy`) are lost. Column order in a table changes.
- FAIL (before patch 5): all 17 relationships were reversed (see B6).
- Note: the Ecommerce page (0 visuals) was merged into the skeleton `page1`. Its name is lost.

| ID | Defect |
|---|---|
| B6 | `compare/extract.py` `_relationship` sorts the two ends by name and reverses the cardinality text (`one:many`). `ModelWriter.cs` ignores the cardinality and uses `ends[0]` as `fromColumn`. Result: `fromColumn: Dim_Customers.Customer_Key`, `toColumn: Fact_Orders.Customer_Key`. Refresh fails: "Column 'Channel_Key' in Table 'Fact_Orders' contains a duplicate value" (screenshot 10). |
| B7 | After a successful apply, the Plan tab still shows 69 operations: 29 columns, 1 measure, 18 relationships, 3 pages, 20 visuals (screenshot 11). The apply does not settle. |
| B8 | Undo restores all files (screenshot 13), but it leaves 26 empty folders (pages, visuals, `tables/`). |

## 8. R4: the output in Power BI Desktop

| Copy | Change by hand | Opens | Loads data |
|---|---|---|---|
| `target2` (app output, before patch 5) | None | Yes. Banner: "This report has not been upgraded to use the enhanced metadata format" (screenshot 06). Visuals show with "--" (screenshot 08). One visual shows "Something's wrong with one or more fields". | No. "Value cannot be null. Parameter name: Non-null assertion failure: query" (screenshot 07). |
| `fixcheck` | Model header added | Yes. The metadata banner is gone. | No. Sales and Ecommerce CSV files are not in the Finance folder (screenshot 09). |
| `fixcheck2` | Header and CSV paths | Yes | No. Reversed relationships (screenshot 10). |
| `fixcheck3` (app output after patch 5) | Header and CSV paths | Yes | No. "Dim_Stages: A cyclic reference was encountered during evaluation" (screenshot 14). |

The `Dim_Stages` table text is the same as the source, except for the lost annotations and the column order. The untouched Sales source refreshes without an error (screenshot 15). I did not find the cause of the cyclic reference. Likely causes: the lost annotations, or the auto date tables (`LocalDateTable_*`, `DateTableTemplate_*`) copied as normal calculated tables.

The `fixcheck*` copies are a diagnosis aid only. They are not the app output.

## 9. Test-only patches

All patches are in `test-only-patches-final.patch` (this folder). Each patch has a `TEST-ONLY PATCH` comment. Do not merge them.

1. `frontend/src/devcenter/components/CompareGrid.jsx`: map `{choice, source}` to `{kind, source_id}` (A2).
2. `backend/devcenter/apply/pipeline.py` `canonical_files`: ignore "model.tmdl missing in canonical serialization" (A3).
3. `backend/adapters/tabular_metadata/bridge.py` `_test_only_writer_ops`: map the property names. Fold the same-name partition into the table create (B2, B3).
4. Same function: put the "many" end first when the cardinality is `one:many` (B6).
5. `bridge.py` `canonical_check`: ignore the same skeleton `model.tmdl` item, also for the guard (B4).

## 10. Root cause of the late discovery

The frontend tests run against `tests/devcenter_ui_server.py`. This mock server accepts payloads that the real backend refuses (A2) and knows filter states that the backend does not have (`not_same`). Thus the UI tests pass, and the real app fails on the first choice.

## 11. Recommendations

1. Add a contract test: for each JS API call in the frontend, check the payload against `backend/devcenter/contracts/jsapi/*.request.json`. Run the same check in the mock server.
2. Add one end-to-end test with the real bridge: merge two small PBIP sources into an empty target, then open the result with TOM and compare it to the sources (relationship direction, hidden flags, partition queries, model properties).
3. Make one shared property map for the plan and `ModelWriter.cs`, or make the writer refuse unknown property names.
4. Keep the relationship direction in the compare object. Sort the ends only for the row key.
5. Write `culture`, `defaultPowerBIDataSourceVersion` and `dataAccessOptions` in the empty-target skeleton, or copy them from the first donor. Make the skeleton canonical, or exclude it from the canonical check.
6. Remove skipped visuals from a copied page, or block the skip with a clear message.
7. Show a plan warning when donors have different values for one shared parameter (`SourceFolder`).
8. Log the real exception in `pipeline.write` and show its code in the UI.
9. Remove empty folders on undo.

## 12. Files

- `screenshots/`: 01 to 15 from this run, `baseline/` from Desktop before the merge.
- `.scratch/e2e-run/` (not committed): sources, targets, `fixcheck*` copies, logs, `repro_write.py`, `repro_plan.py`.

## 13. Comparison with the independent code review (2026-11-20)

### 13.1 Method

The user supplied an independent review of the Merge tab: "Merge Tab (Development Center): Technical Defect & Collateral Damage Report", items M-01 to M-19, on the same base (`origin/main` at `2b56733`). That review reads code. This report comes from a live run. I examined each claim in the code of this worktree. Where the cost was low, I ran the code.

The P0/P1/P2 levels of the independent review are predictions from the code. This run did not trigger those failures, unless the evidence label is "Live". The two methods give different information:
- A run also shows the behavior of code that is not in this repo: TOM, Power BI Desktop and the real PBIP files. A code read cannot show this.
- A code read is a prediction by the reader and can be wrong. Both reviews had such errors (M-01 "all"; the first Finance cause in 3.1).
- Severity also depends on whether and how often a normal user reaches the path. A code read does not show this.
- A run covers only the paths that were clicked. A code read also covers other paths. Thus the code review found real defects that this run did not reach.

Evidence labels:
- **Live**: seen in the live run of this report.
- **Code**: confirmed in the code (and run, where the text says so).
- **Partly**: the main claim is confirmed; one or more sub-items are not checked or do not hold.
- **Not checked**: not examined.
- **Does not hold**: the claim is false as stated.

### 13.2 Claims and evidence

| Outside ID | Claim (short) | Evidence | Notes and corrections | This report |
|---|---|---|---|---|
| M-01 | The grid filter states `not_same` and `conflict`, and the row detail state `all`, match 0 rows in `filter_rows`. | Live + Code | `compare/rows.py:229` compares `row_state` literally. The backend has no translation for these values. Correction: the grid does not send `state=all`; it leaves out `state` for "All" (`CompareGrid.jsx:304`). Only `CompareRowDetail.jsx:268` sends `state: "all"`. `plan/edits.py:125` (Bulk Edit) calls the same function. | 5.2 item 1 |
| M-02 | The bulk Merge Choice payload breaks the JS API schema. | Live + Code | The grid sends `{choice: "take_from", source}`. The schema allows only `kind` and `source_id`, and the `kind` enum has `take`, not `take_from`. `BulkBar.jsx` compares `merge_choice.choice` with `choice.kind`, so the "replace" count is wrong (this explains the stale count in 5.2 item 4). Correction: "Confirm N rows" shows only with the marks filter; this is probably the design, not a defect. | A2, 5.2 item 4 |
| M-03 | Bulk Undo with "all matching rows" erases choices on rows that are not loaded. | Code | `previousMap` uses only `allLoadedRows`. Keys outside the loaded pages get `null`. `merge_choice_bulk_set` (`session/manager.py`) removes the choice for `null`. The mock server refuses `{items}`, and the undo `catch` ignores the error. Not run live. | New |
| M-04 | Grid filter, race and display defects. | Partly | Confirmed: only the first Type and Source value is sent (`CompareGrid.jsx:305,308`); `loadPage` ignores its `generation` argument (`CompareGrid.jsx:387`), thus a late reply can overwrite a newer filter; `p.proposal` is never sent by `httpClient.getCompareRows`; static `ArrowUpDown` icons; `"s0"` fallback. Not checked: the 60 ms blank cells, "= Same" text, the 6 of 13 types. | New |
| M-05 | Every Repoint policy fails in the compiler. | Code | Writers store `repoint_target` (`impact/service.py:354,396`, `session/proposals.py:227`). `plan/compiler.py:1031` reads only `replacement_row_key`. Extra find: `impact_action_apply` can key `removal_policies` by the `imp-` item ID when no `row_key` is given (`impact/service.py:352`). | New |
| M-06 | Need mappings: key and field mismatch. | Code | `impact_action_apply` keys by `imp-<16 hex>` (`impact/service.py:357`, `impact/engine.py:64`). The engine reads by the donor `source_key` (`impact/engine.py:580`). The compiler reads by `row["row_key"]` and the field `row_key`, not `target_object` (`plan/compiler.py:449-451`). | New |
| M-07 | "Include in rewrite" item actions: key mismatch. | Code | Stored by `imp-` ID (`impact/service.py:348`). The compiler reads `renamed:{dependent}:{cause}` (`plan/compiler.py:1238`). | New |
| M-08 | The impact cache has no session ID. | Code | Cache key is `(revision, target_param, mode)` (`impact/service.py:88`). `_commit` and `_close` do not clear it. Two sessions at the same revision can share a cached result. Not run live. | New |
| M-09 | Removal policies are not in the HTTP read contracts. | Code | `session.reply.json` and `compare-rows.reply.json` have no `removal_polic*`. `CompareRowDetail.jsx:812` reads `row.removal_policy`, which only the mock server sets. | New |
| M-10 | The model read uses the wrong folder; `TMDLScripts/` breaks it. | Live + Code (run) | See 3.1 and A1. Bridge read of `Finance.SemanticModel` fails; read of `definition/` passes. | A1, 3.1 |
| M-11 | The PBIR writer refuses an untouched root `definition.pbir` (v4, no `$schema`). | Code (run) | `validate_report_documents` gives `PBIR_SCHEMA_UNSUPPORTED` for `Sales.Report/definition.pbir` (`schema: null`). Root files without `$schema`: Finance, Sales, HR, Manufacturing, Healthcare (5 of 7). Finance has 3 more issues on extra files (`definition/definition.pbir`, `definition/pages.json`, `version.json`). Scope: the candidate holds the target report, thus this fails only when one of these reports is the TARGET. It did not block this run (new empty report). Sales opens in Desktop, so the check is too strict. | New |
| M-12 | Plan tab state and placeholder defects. | Partly | Confirmed: fixed time `"14:22"` (`PlanTab.jsx:183`) and `"09:30"` (`planModel.js:66,77,359`); `planResource.loading` (`PlanTab.jsx:170,283`); `plan_state === "checking"` while the backend sets `"computing"` (`session/manager.py:346`); copy key `work.change_target` is missing in `copy.js`; classes `dc-card`, `dc-table`, `dc-mono` are used. Not checked: the CSS rules of these classes, the `validationOverride` reset. | New |
| M-13 | Naming engine defects. | Partly | Confirmed (run): `is_case(..., "title")` returns true for `ALL CAPS` and `PascalCase`. The other sub-items are not checked. The clash name in 5.2 item 5 agrees with this item. | 5.2 item 5 |
| M-14 | Naming Rules UI defects. | Not checked | | |
| M-15 | No "Add source" in the work area; the target choice opens the folder picker at once. | Partly | Confirmed: `TargetChoice.jsx` calls `pickFolder()` on selection, with `try/finally` and no `catch`. "Add source" not checked. | 5.2 item 11 |
| M-16 | Rename and Delete only write `localStorage`; Duplicate makes an empty session. | Live + Code | `DevCenter.jsx:65-112`. | 5.2 item 12 |
| M-17 | Shell leaks: project switch, `key={view}`, the `/` key. | Partly | Confirmed: `resetProjectView` (`App.jsx:260`) does not reset the DevCenter shared store. Correction: `key={view}` alone is probably the design. The `/` key priority is not checked. | New |
| M-18 | Row detail, CodeDiff and NameField defects. | Partly | Confirmed: marks use `activeDonorName` (`CompareRowDetail.jsx:606`), which explains "Finance changed" when Ecommerce changed; `CodeDiff` compares line by line by index. The other sub-items are not checked. | 5.2 item 2 |
| M-19 | CSS and shared primitives. | Partly | Confirmed: `var(--brand-text)` is used and not defined. The other sub-items are not checked. | New |

### 13.3 Collateral claims (section 3 of the independent review)

- Bulk Edit uses `filter_rows`: confirmed (`plan/edits.py:125`).
- Cloud targets: confirmed in the `apply/cloud_target.py` docstring. Cloud targets use the same guard and the same working-copy write. Thus the write-step defects of this report (B2, B3, B6, the model header) also apply to cloud targets. The independent review did not list them.
- Graph and Overview are stale after an apply: agrees with section 4 ("3 files changed outside PBIBrain since the last scan" after an apply). No `reloadBrain` or `applyScan` call in `frontend/src/devcenter`.
- `DesktopStart.jsx:71` says "Your Power BI files are only read, never changed": confirmed. This text is false when Merge Apply is available.
- The conflicting test schemas (`replacement_row_key` and `renamed:` in `test_devcenter_plan.py` and `test_change_guard_merge.py`; `repoint_target` and `target_object` in `test_devcenter_agent_tools.py`): confirmed.
- Part B (fix-time hazards) and the remediation order: not checked. The commits it names (`7006e5c`, `362c553`, `ad635c3`, `31a46de`) exist. Its learning IDs (`l-...`) are not examined here.

### 13.4 Found only by this run

The independent review did not examine `ModelWriter.cs`, the output files, or Power BI Desktop. These items are found only by this run:
- A3, B4: the empty-target skeleton `model.tmdl` deadlocks the format check and the guard.
- B1: `pipeline.write` hides the real exception.
- B2, B3: property names and the duplicate partition between the plan and `ModelWriter.cs`.
- B5: Skip on a visual has no effect.
- B6: all relationships are reversed.
- B7, B8: the plan does not settle after apply; undo leaves empty folders.
- The model header, the single `SourceFolder`, the lost table annotations, and the "cyclic reference" refresh error (sections 7 and 8).
- The Ecommerce source that Desktop refuses, while the app scan says "Graph validation passed" (3.1).
- The Apply dialog with about 140 to 170 "Critical" items, and the hidden real error on undo (5.2 items 13 and 14).

### 13.5 Changes to the recommendations

Add to section 11:
10. Read `definition/` in `compare/extract.py` `_read_model`, as `write_model` already does. Show a clear error when a source model cannot be read (A1).
11. Use one key and one field set for `removal_policies`, `need_mappings` and `item_actions` in all writers and the compiler. Read the old keys as a fallback for saved sessions.
12. Capture the previous choices of all affected rows before a bulk set, not only the loaded rows. Show bulk errors to the user.
13. Accept an untouched root `definition.pbir` (v4) with no `$schema` in the PBIR check. Keep the strict check for files that the writer changes.
14. Add the session ID to the impact cache key. Clear the cache on session close.
15. Validate every mock server payload against `backend/devcenter/contracts/**`. Both reviews show that the mock server hides contract defects.
