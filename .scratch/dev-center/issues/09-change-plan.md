# How does the Change Plan engine work?

Type: grilling
Status: resolved
Blocked by: 01, 04, 07

## Question

Which operation types exist? How does the engine sort them by dependency? How do the removal policies (block, cascade, repoint) behave? How does the engine rewrite references after a rename (DAX, field parameters, RLS, report bindings)? When does a copied object get a new lineageTag? How does a model change carry over to report operations?

## Context

- From "What are the match and compare rules?": the alignment can hold a "name clash" row (a donor object with the same name as a renamed target object). The plan must solve the name before it adds that object.
- From "What are the match and compare rules?": the compare reads references through the alignment. The reference rewrite after a rename must use the same alignment map.
- From "What must change so that the change guard accepts create, delete, and rename?": the plan must set the new lineageTag of each created object before the write, so that the guard contract knows the new object IDs.
- From the same ticket: write each reference rewrite as a separate expression operation with the exact old text and the exact new text. The guard accepts no wildcard and no "update all references" operation.
- From the same ticket: write the rename of an object with no lineageTag (role, partition, calculation item, report page) as one linked delete-and-create pair. The guard accepts the pair only when all properties except the name are equal.
- From the same ticket: the write step must produce TMDL files that are byte-equal to the TOM serialization. If a target file is not in that format, the plan needs a separate "format only" apply first.

## Answer

Resolved with the user on 2026-10-31. The user accepted all proposed defaults.

### Facts found first

- The guard contract already lists `SET_PROPERTY`, `CREATE_OBJECT`, `DELETE_OBJECT`, `RENAME_OBJECT`, `REPLACE_EXPRESSION`, `ADD_REFERENCE`, `REMOVE_REFERENCE`, and `CHANGE_BINDING` (`change_guard/contracts/schema.py`).
- The DAX parser is ANTLR based and keeps token positions (`backend/dax/parser.py`, `backend/dax/visitors.py`). Thus a token-exact reference rewrite is possible.
- TOM `RequestRename` changes only the name. Relationships, hierarchy levels, sort-by, perspectives, translations, and role table permissions follow the new name. DAX text does not (branch `research/tmdl-write`).
- The field parameter metadata (`ParameterMetadata`) and the `nativeQueryRef` rule after a rebind are not documented (branches `research/tmdl-write` and `research/pbir-copy`).
- Bookmarks are read only in the first version ("Which new object types must the graph learn first?").

### Decisions

1. The plan is derived. The engine computes it again from the session state (sources, alignment, Merge Choices, removal policies) each time. Nobody edits the plan by hand.
2. Two levels. A "plan step" comes from one Merge Choice or one prerequisite. The plan summary counts plan steps. Each plan step compiles to one or more atomic "operations" for the bridge and the guard. Each operation keeps a link to its plan step.
3. Operation types:
   - Model: `CREATE`, `DELETE`, `REPLACE` (full object), `SET_PROPERTIES`, `RENAME` (object with a lineageTag), `RENAME_PAIR` (linked delete-and-create for an object with no lineageTag), `REWRITE_EXPRESSION` (one for each changed expression, with the exact old text and the exact new text).
   - Report: `COPY_PAGE`, `COPY_VISUAL`, `DELETE_PAGE`, `DELETE_VISUAL`, `REBIND_FIELD` (one for each changed field location), and create, delete, or replace of a report measure.
   - "Promote report measure" is a plan step. It compiles to: create the model measure, rebind the fields, delete the report measure.
   - "Format only" is not an operation. It is a separate plan of its own (see "What must change so that the change guard accepts create, delete, and rename?").
4. Sort order: fixed phases, then a dependency sort in each phase.
   1. Deletes, dependents first.
   2. Renames.
   3. Creates, needs first (table, column, relationship, hierarchy, measure, calculation group, role).
   4. Replaces and property sets.
   5. Expression rewrites.
   6. Report operations, in the same phase order.

   Ties sort by object type, then by name. Thus the same session state always gives the same plan. A dependency cycle makes the plan Invalid.
5. Removal policy: the user sets it for each removed object, not for the full session. The default is Block.
   - Block: the plan stays Invalid until the user resolves each dependent.
   - Cascade: remove the dependents transitively. The app lists them first. In a visual, cascade removes the field and its filters. It removes the visual only when no field stays. A dependent with its own explicit Merge Choice keeps that choice, and the engine checks the new version.
   - Repoint: the user selects one replacement object of the same kind (measure for measure, column for column). The app gives a warning when the data type is different. Each changed expression is one `REWRITE_EXPRESSION`. Each changed field location is one `REBIND_FIELD`.
6. Rename rewrite method: change only the reference tokens at the exact parser positions. Do not use text search and replace. Keep all other text exactly. Scope: measures, calculated columns and tables, calculation items, format string expressions, RLS filters, UDFs, field parameter DAX; report field bindings, `queryRef`, filters, and conditional formatting expressions. TOM moves relationships, hierarchy levels, sort-by, perspectives, and translations.
7. Rename of a target object with unselected dependents: the app does not change unselected target objects (spec 7.2). Each unselected dependent is a blocking "Breaks" item. One click "include in rewrite" selects it.
8. Undocumented areas: rewrite only the DAX of a field parameter. Change `nativeQueryRef` only when it is equal to the old name. A bookmark that refers to a renamed or removed object is "not checked" and shows in the apply dialog.
9. Donor DAX goes through the alignment. When the plan copies donor DAX ("Take from", "Take properties", "Add as new name"), the engine changes each donor reference to the aligned target name. A reference with no aligned target object becomes a Need.
10. lineageTag rules:
    - "Take from" on an existing target object: keep the target tag.
    - "Take from" for a new object: keep the donor tag when the target does not have it. Otherwise make a new tag and give a warning.
    - "Add as new name": always a new tag.
    - A donor tag that occurs two times in one source: a new tag.
    - New tags are deterministic: UUIDv5 from the session ID and the row key. The same state gives the same plan and the same contract hash.
11. Needs (prerequisites): the engine adds each Need as a prerequisite plan step with the default "add from donor". The plan is then "Valid with warnings" and lists them. When the user maps a Need to an existing target object, the engine adds rewrite operations. A Need with a name clash, or a Need that no donor has, is a blocking item.
12. Name clash row: a blocking item. The user gives a new name or selects "Keep target". The app proposes a name from the naming rules.
13. Model to report carry-over: a rename, repoint, or cascade in the model compiles to report operations only for the session's target report. Other reports that use the target model show as impact ("not changed by this plan"). They get no operations.
14. Where the engine runs: the Python backend computes and validates the plan, and applies the report operations to the PBIR JSON. The .NET bridge applies the model operations to TOM. One guard contract covers the model files and the report files together.
15. All or nothing: a local apply writes the model and the report together, or nothing. Cloud: deploy the model first, then the report. When the report write fails, the app offers to restore the model from the backup.

### Consequences

- The plan operations map to the guard contract operations: `REWRITE_EXPRESSION` to `REPLACE_EXPRESSION`, `REBIND_FIELD` to `CHANGE_BINDING`, `RENAME_PAIR` to the linked rename pair of the guard ticket.
- ADR candidate: decision 10 (deterministic UUIDv5 lineageTags). A reader can ask why the tags are not random.
- ADR candidate: decision 6 (token-exact rewrite, not text replace).
