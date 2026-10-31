# Power BI Development Center: functional specification

Status: ACCEPTED (functions). This document gives functions only. A separate round will define the UI.

Date: 2026-10-30.

## 1. Goal

The Development Center lets a developer (and an agent) build one "master" semantic model and report from many sources. The developer loads many models and reports, compares them, selects changes, examines the impact, and applies the changes to a target.

The app must show clearly what it will create, delete, and modify before it writes a file.

## 2. What exists now (baseline)

| Capability | Current state | Gap for the Development Center |
|---|---|---|
| Multi-source scan | `project-scan` loads many PBIP sources into one graph. | No cloud (XMLA) source. No source "role" (target or donor). |
| Object graph | 23 object types (model, table, column, measure, relationship, field parameter, UDF, calculation group and item, report, page, visual, visual calculation, filters). | No role (RLS), OLS, hierarchy, perspective, culture, partition, bookmark, theme, report-level measure nodes. |
| Compare | `brain_compare` compares two trusted snapshots of the same project. | No N-way compare across different models. No object alignment between models. |
| Impact | Conservative downstream impact (`brain_impact`), report usage included. | No "requirements" direction (what a new object needs). No page wireframe. |
| Write path | `change_guard` applies property edits only. Create and delete fail closed. | Merge needs create, delete, rename, and reference rewrite. |
| Agent access | Read-only MCP tools. | No tools to propose decisions or ask questions. |

## 3. Core concepts

| Term | Meaning |
|---|---|
| Merge Session | One saved work unit. It holds the sources, the target, the alignment, the merge choices, and the plan. |
| Source | One loaded model or report. Kinds: local PBIP (TMDL or TMSL), local PBIR report, cloud model (XMLA), cloud report (Fabric REST definition). |
| Target | The model and the report that receive the changes. A target is an existing source, or a new empty item, or a copy of a source. |
| Donor | A source that is not the target. Donors are read-only. |
| Alignment | The link between "the same object" in different sources (for example, `[Total Sales]` in Model A and in Model B). |
| Merge Choice | The choice for one aligned row (for example, "take from Model B"). |
| Change Plan | The ordered list of operations that the merge choices produce, with the prerequisites added. |
| Impact | The objects that a change breaks, changes, or needs. |

## 4. Sources and connections

### 4.1 Local sources

- The app MUST load PBIP projects with TMDL or TMSL models and PBIR reports.
- The app MUST load a standalone model folder (TMDL) or `model.bim` file.
- The app MUST load a standalone PBIR report with a `byPath` or `byConnection` dataset reference.
- The app SHOULD read PBIR-Legacy reports for compare and impact. It MUST NOT write PBIR-Legacy. The user must convert to PBIR first.
- The app MUST NOT read PBIX files directly. Tell the user to save as PBIP in Power BI Desktop.

### 4.2 Cloud sources (XMLA)

- The user MUST specify the access type when the user adds a connection: `Read` (default) or `Read/Write`.
- A `Read` connection can be a donor or a compare source. It can never be a write target.
- A `Read/Write` connection can be a target. The app MUST still write to it only after the final confirmation in section 9.
- The app SHOULD offer "Pull to local PBIP": export the cloud model as TMDL into a local folder. Then the user can merge locally and deploy later.
- The app SHOULD read cloud reports through the Fabric REST API (report definition) so that impact includes reports that use the cloud model.
- Cloud reports use the same access types: `Read` (default) or `Read/Write`. A `Read/Write` cloud report can be a target. The app writes it through the Fabric REST API (update report definition), only after the final confirmation in section 9.

> WARNING: Do not write through XMLA to a model that Power BI Desktop authored, unless the user accepts the result. After an XMLA write, the service can no longer download the model as a PBIX file (Microsoft documentation). The app MUST show this warning before the first XMLA write.

- XMLA write needs enhanced metadata and a capacity with XMLA read/write enabled. The app MUST test these conditions when it connects and show the result.
- Credentials stay in the Windows credential store. The app MUST NOT keep tokens in session files.

## 5. Target selection

- The user marks one model as the target model and zero or one report as the target report. Example: Model A [x], Model B [ ], Report A [x], Report B [ ].
- If the user marks no target model, the app creates a new empty model. If the user marks no target report, the app creates a new empty report bound (`byPath`) to the target model.
- The user can select "new target" also when a baseline exists. Options:
  - "Empty": start with nothing.
  - "Copy of <source>": start from a full copy of one source. The original source stays unchanged.
- A target report MUST bind to the target model. If a selected target report binds to a different model, the app MUST show the rebind impact (fields that do not exist in the target model).
- A session has one target report (decision Q1).

## 6. Alignment and compare

### 6.1 Object coverage

Model objects:
tables (import, DirectQuery, calculated), columns (data, calculated), measures, relationships, hierarchies and levels, calculation groups and items, field parameters, user-defined functions, RLS roles and filters, OLS permissions, perspectives, cultures and translations, shared expressions and parameters, partitions (M text), format string expressions, KPIs, detail rows expressions, annotations, sort-by column, data category, summarize-by.

Report objects:
pages (including tooltip and drillthrough pages), visuals, visual calculations, report, page, and visual filters, bookmarks, report-level measures (`reportExtensions.json`), slicer sync groups, visual interactions, theme, static resources, conditional formatting field references.

### 6.2 Alignment rules

The app aligns objects across sources in this sequence:

1. Same `lineageTag` (TMDL). This finds copies of the same object, also after a rename.
2. Same qualified name (`'Table'[Object]`) and same object type.
3. Same name in a different table (for measures). Show as "moved".
4. Same expression with a different name. Show as "possible rename". The user must confirm.
5. Manual alignment by the user or by the agent (the agent proposal needs user confirmation).

The user can break or change any alignment.

### 6.3 Compare states

For each aligned row and each source, the app shows one state:

| State | Meaning |
|---|---|
| Same | The object is equal to the target after normalization. |
| Different | The object exists, and one or more properties are not equal. |
| Missing | The object does not exist in this source. |
| Renamed | The object aligns by `lineageTag` or confirmation, but the name is not equal. |
| Moved | The object is in a different home table (measures and report measures). A different display folder is a property difference ("Different"). Changed 2026-10-31 by the ticket "What are the match and compare rules?". |
| Type conflict | The same name has a different object type (for example, a column and a measure). |

Example row: `[Total Sales]`: Model A = target, Model B = Missing, Model C = Different, Report A = Same (report measure), Report B = Missing.

### 6.4 Normalization

- Default normalization ignores DAX whitespace, DAX comments, letter case of DAX keywords, and JSON key order.
- The user can select "strict" to compare the exact text.
- For "Different", the app MUST tell which properties are different in plain words (for example, "expression changed", "format string changed", "display folder changed").
- The code diff (DAX, M, TMDL, JSON) is an extra view. The user opens it on request. It is not the default view.

### 6.5 Bulk scope

The user can filter and select rows by: object type, table, display folder, state, source, page, and "changed since <snapshot>".

## 7. Merge Choices

### 7.1 Merge Choice types

| Merge Choice | Result in the target |
|---|---|
| Keep target | No change. |
| Take from <source> | Add the object, or replace the target version. |
| Take properties from <source> | Replace only the selected properties (for example, expression only). |
| Add as new name | Add a copy with a new name. The target version stays. |
| Remove from target | Delete the object. |
| Skip | No change. The row stays open. |

### 7.2 New name and display folder

- "Add as new name" and "Take from" MUST let the user set a new name and a display folder.
- The display folder field MUST offer a list of the display folders that exist in the target and in the selected source. The user can also type a new folder.
- When the user renames an object, the app MUST update all references in the objects that the plan carries over: DAX expressions, calculation items, field parameters, RLS filters, report field bindings, filters, bookmarks, and conditional formatting.
- The app MUST NOT change references in target objects that the user did not select. It MUST show them as impact.

### 7.3 Naming conventions

- The app SHOULD detect naming patterns from the target model: prefixes, suffixes, letter case, separators, unit words, and folder-by-type rules.
- The user can confirm, edit, or delete a detected pattern. The user can also write rules by hand.
- The app MUST mark a new name that does not obey the rules.
- The agent (section 10) SHOULD propose a name that obeys the rules. It MUST give the rule that it used.
- The app stores naming rules for each target model (decision Q2).

### 7.4 Report-level measures

- The user can move a report-level measure to the target model ("promote").
- The user can copy a report-level measure to another report.
- The user can copy a model measure into a report as a report-level measure only when that report uses a live connection (`byConnection`).
- The app MUST mark a name conflict between a report-level measure and a model object.
- After "promote", the app MUST rebind the visuals of the target report from the report measure to the model measure.

## 8. Impact and requirements

### 8.1 Two directions

- Breaks (downstream): what stops to work or changes value when the plan removes, renames, or changes an object. Scope: measures, calculated columns and tables, relationships, hierarchies, sort-by, calculation items, field parameters, UDFs, RLS and OLS, perspectives, visuals, visual calculations, filters at all levels, bookmarks, conditional formatting, drillthrough fields, report-level measures, and other reports that use the target model.
- Needs (upstream): what the target must have before an added object works. Example: a measure needs column `Sales[Amount]` and the relationship `Sales`-`Date`. The app MUST add each need to the plan as a "prerequisite" row. The user can accept it, map it to an existing target object, or drop the added object.

### 8.2 Carry-over offers

- When the user adds a model object, the app SHOULD list the donor report items that use it: pages, visuals, filters, bookmarks. The user can select them to copy into the target report.
- When the user copies a page or a visual, the app MUST list each field that the target model does not have. For each field, the user selects: add from donor, map to an existing target field, or remove the field from the visual.

### 8.3 Removal policy

When the user removes an object that other objects use, the user selects one policy:
- Block (default): the plan stays invalid until the user resolves each dependent.
- Cascade: remove the dependents also. The app lists them first.
- Repoint: replace the reference with a different object.

### 8.4 Representations

- Table (default): one row for each impacted object, with the reason in plain words, the severity (breaks, changes value, needs review), and the path.
- Graph: the dependency path from the change to each impacted object.
- Page wireframe: each page drawn from the visual positions in PBIR. Each visual and filter has a color for its status (breaks, changes, new, removed, unchanged).

### 8.5 Accuracy rules

- Static impact is a conservative superset. The app MUST tell when a result is "possible" and not "certain" (for example, relationship direction effects).
- The app MUST show the completeness: unresolved bindings, unsupported objects, and remote reports that it could not read.
- Optional value check: with a live connection, the app SHOULD run the same measure in the donor and in the target for a sample of filters and show the difference. This is evidence, not proof.

## 9. Change Plan and apply

### 9.1 Plan

- The plan is an ordered list of operations: create, delete, replace, replace properties, rename, rewrite references, rebind visual, copy page, copy visual.
- The app MUST compute the sequence from the dependencies (for example, create the column before the measure that uses it).
- The plan has a status: Invalid (blocking items), Valid with warnings, Valid.
- The plan summary MUST give counts: created, deleted, modified, renamed, for each object type, and for model and report separately.

### 9.2 Validation before apply

- The app MUST validate the result before it writes: DAX parse of all new and changed expressions, reference resolution, TMDL round trip through the TOM bridge, PBIR JSON schema check, and duplicate `lineageTag` check.
- New objects copied from a donor MUST get new `lineageTag` values when the target already has that tag for a different object.

### 9.3 Apply

- Local target: the app writes TMDL and PBIR files. It takes a snapshot first. The user can undo the full apply from that snapshot.
- Cloud target (`Read/Write` only): the app deploys only the delta through XMLA. It takes a TMDL backup of the cloud model first. It shows the warning in section 4.2.
- Cloud report target (`Read/Write` only): the app downloads the current report definition as a backup. Then it writes the new definition through the Fabric REST API.
- The app MUST NOT apply a plan that has blocking items.
- The app MUST NOT apply agent-proposed decisions that the user did not accept.
- After apply, the app MUST rescan the target and compare the result with the plan. It MUST report each difference.
- The app SHOULD compile the plan into a `change_guard` contract. Then the guard checks the scope and the source coverage. This needs create, delete, and rename support in the guard.
- The app MUST NOT commit to Git or push. It CAN write a change report (Markdown) for a commit message or a pull request.

## 10. Agent through MCP

### 10.1 Tools (proposal)

| Tool | Purpose |
|---|---|
| `session_get` | Read sources, target, and plan status. |
| `alignment_list` | Read the compare rows with states and property differences. |
| `impact_get` | Read the impact and needs for a row or for the full plan. |
| `naming_rules_get` | Read the naming rules of the target. |
| `decision_propose` | Set a proposed decision with a confidence and a reason. |
| `question_ask` | Add a question for the user to a row (with options). |
| `plan_validate` | Run the validation. Return the blocking items. |

The agent MUST NOT have an apply tool.

### 10.2 Behavior

- The agent sets proposals that have a confidence at or above the threshold. Threshold: 0.9 (decision Q3).
- Below the threshold, the agent adds a question with options. Example: "Model B and Model C have different `[Total Sales]`. B uses `Sales[Net]`, C uses `Sales[Gross]`. Which one?"
- Each agent proposal shows as "proposed by agent" until the user accepts or rejects it. The user can accept all proposals in one action.
- The agent MUST give a reason for each proposal. The app MUST keep the reason in the session log.

## 11. Session and audit

- The app MUST save a session and open it again later.
- The app MUST detect a source that changed after the session started, and mark the rows that the change affects.
- The app MUST keep a log of each decision: who (user or agent), when, and the reason.

## 12. Out of scope (the app MUST NOT do these)

- Refresh or process data.
- Edit Power Query (M) logic. The app copies M text as it is.
- Write PBIX or PBIR-Legacy files.
- Publish reports or deploy to workspaces, except the XMLA model write in section 9.3.
- Apply changes without a user confirmation.
- Claim numerical correctness from static analysis.

## 13. Suggested later features

- Merge templates: save a set of decisions and run it again on a new version of the donors.
- Standard library: keep a "golden" set of measures and functions, and compare each model with it.
- Duplicate finder: find measures with the same logic and different names across all sources.
- Unused object finder: objects that no report and no measure use.
- Three-way merge with Git: compare target, donor, and their common ancestor commit.

## 14. Decisions (were open questions)

All questions are decided (2026-10-30). The user accepted the proposed defaults.

| ID | Question | Decision |
|---|---|---|
| Q1 | One target report or many target reports in one session? | DECIDED: one. |
| Q2 | Naming rules for each session or for each target model? | DECIDED: for each target model. |
| Q3 | Agent auto-select threshold? | DECIDED: 0.9. |
| Q4 | Write to a cloud model directly, or always pull to local first? | DECIDED: pull to local first. Direct XMLA write is an option. |
| Q5 | Read cloud reports (Fabric REST) for impact? | DECIDED: yes. Access type `Read` (default) or `Read/Write`. Write is optional. |
| Q6 | When an object is "Different", the user can take only some of its parts from a donor (for example, the DAX expression from Model B, but the target format string and display folder). Which object types get this "take only some parts" option? The other types are taken as one complete object. | DECIDED: measures, columns, and relationships first. |
