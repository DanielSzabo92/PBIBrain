# How does the user add cloud sources and manage naming rules?

Type: grilling
Status: resolved
Blocked by: 02

## Question

Design the cloud connect dialog (sign-in, access type, connect test result), the "Pull to local PBIP" flow, and the naming rules screen.

## Context

- Cloud (version 1 read only, technical design section 10): interactive Microsoft sign-in (`cloud_sign_in`), connect (`cloud_connect`) with access type `Read` (default) or `Read/Write` (spec 4.2; `Read/Write` is recorded in version 1 but no cloud source is a write target until 1.1). `pull_to_local` exports a cloud model as TMDL into a local folder with a PBIP skeleton.
- Connect test result: show the conditions that the app can check, and say what it cannot check. Reports that the app cannot read show as "not checked: report not readable" with the fix "export the report to a local PBIP" (section 10.3). Reports in other workspaces are "not checked".
- No XMLA write warning dialog in version 1 (out of scope, map).
- Naming rules (section 5): rules with status (proposed, confirmed, rejected), origin (detected, user), support ("37 of 40 measures"), break counts. Actions: `naming_rule_confirm`, `naming_rule_reject`, `naming_rule_edit`, `naming_rules_copy`. User rules include a regular expression kind.
- Skills: `design-doctrine`, `design-component` for the dialog parts.

## Done when

The answer gives: the connect dialog steps and states (signed out, signing in, sign-in failed, connected, test result), the access type control and its copy, the Pull to local flow, the naming rules screen layout and its actions, the rule editor, and the copy for each error and refusal.

## Answer

Resolved on 2026-10-31. The orchestrator accepted all 16 recommendations of round 1 (one round). Prototype: `.scratch/dev-center-ui/prototypes/07/` (`index.html`, `tokens.css`, `measure.mjs`, `snap.mjs`, screenshots in `shots/`). The prototype is never shipped. Open a screen with `index.html?screen=<id>&theme=dark|light`.

### Brief Inference

- Domain: dev-tool (Power BI model merge). Audience: expert BI developer. Tone: calm, utilitarian. Mood: precise.
- Motion depth: subtle feedback only (a spinner on async steps; no motion with `prefers-reduced-motion`).
- Layout family: the Sources tab of ticket 02 (section cards, dense table), a modal dialog with a step list, and the side pane of ticket 02 for the rule editor.
- Reference anchor: the ticket 02 prototype and the existing PBIBrain shell.

### Decisions of round 1

1. Cloud item picker: a list from a new JS API read call `cloud_items_list` (main path), plus "Paste a workspace connection" as a fallback. JS API only: the HTTP API has no authentication and must not show tenant data to a local agent. Backend change request.
2. One modal dialog (Radix Dialog) from "Add source > Cloud model" or "Cloud report". Steps: 1 Sign in, 2 Select model (or Select report), 3 Access type, 4 Test. The dialog skips step 1 when a silent token works.
3. The dialog shows "Signed in as <account>". No "Sign out" in version 1. "Use a different account" calls `cloud_sign_in` with an account prompt. Backend change request (`prompt`, account display name). No file stores the account name.
4. Access type: a radio group, "Read" (default, selected) and "Read/Write" (selectable, with the version 1 note). The same control is in the cloud report flow.
5. The test result for a cloud model shows only what the app can check, and a "Not checked" group with a reason for each item that it cannot check.
6. A cloud report that fails `getDefinition` is not added. The not-readable reports that a cloud model finds in its workspace show a line in the test result and in the impact completeness block, but they do not stop the add.
7. A cloud model cannot be a write target in version 1. On the Target step it is disabled with "Pull to local PBIP first." and a "Pull to local PBIP" button.
8. Pull to local: the entry points are the Target step button and a row action on each cloud model source. The new local PBIP becomes a local source. The cloud source stays. From the Target step, the new source becomes the selected target.
9. Pull into a folder that is not empty: refused inline. No overwrite.
10. Naming rules: a section of the Sources tab, below Sources and Target. One dense table, grouped by object type, with a status filter.
11. Row actions by status (see the table below). Delete of a user rule uses `naming_rule_reject`, the destructive style and a confirm dialog. Multi-select with "Confirm selected". Clarification request to the backend.
12. Add rule: `naming_rule_edit` with no rule ID creates a user rule. Contract clarification.
13. Rule editor: the side pane of ticket 02 (360 px column at 1280 px and wider, sheet below). The backend validates on save. No live match count.
14. Breaks: count only, no name list, in version 1.
15. "Copy rules from": a dialog with the session source models that have a rule file, and their rule counts. Copied rules arrive as "Proposed".
16. Read-only, no target, empty and detection states as in the copy table.

### Screen list

Screenshots: `prototypes/07/shots/<screen>-<theme>-<width>.png`, dark and light, at 1440 and 1024 wide (31 screens, 124 files). Dialog screens are viewport screenshots; the other screens are full-page. The repo `.gitignore` excludes `*.png`. To make them again, run `node measure.mjs shots` in `prototypes/07/`.

| Screen ID | What it shows |
|---|---|
| `sign-out` | Dialog step 1, signed out |
| `signing` | Dialog step 1, sign-in window open |
| `sign-fail`, `sign-fail&why=consent`, `sign-fail&why=network` | Sign-in failed: closed window, admin consent, no network |
| `select` | Step 2: account line, workspace combobox, model radio list with a disabled Excel model |
| `select-nocap` | Step 2: workspace with no XMLA capacity |
| `select-none` | Step 2: no workspaces |
| `select-paste` | Step 2 fallback: paste a workspace connection, with a field error |
| `access` | Step 3: access type |
| `testing` | Step 4: test in progress |
| `result` | Step 4: test result, "Checked" and "Not checked" groups |
| `test-fail` | Step 4: test failed (no Build permission) |
| `report-refused` | Cloud report not readable, not added |
| `pull-confirm`, `pull-notempty`, `pull-running`, `pull-done`, `pull-fail` | Pull to local PBIP |
| `rules` | Sources tab: Sources section and Naming rules section |
| `rules-select` | Two proposed rules selected, "Confirm selected (2)" |
| `rules-menu` | Row "More actions" menu open |
| `rules-editor` | Edit rule pane (unit word rule) |
| `rules-editor-error` | Add rule pane, regular expression with a backend error |
| `rules-empty`, `rules-notarget`, `rules-detecting` | Empty, no target, detection running |
| `rules-locked` | Locked session: all actions disabled |
| `rules-stale` | Toast after `stale_revision` |
| `rules-copy` | Copy rules dialog |
| `rules-delete` | Delete user rule confirm dialog |

### Cloud connect dialog

```
+ Add cloud model ------------------------------------------ [x] +
| (1) Sign in  (2) Select model  (3) Access type  (4) Test        |
|-----------------------------------------------------------------|
| [user] Signed in as daniel@contoso.com  Use a different account |
| Workspace  [Sales Analytics                               v]    |
| Semantic model                                                  |
|  (o) Sales Cloud           Updated 28 Oct 2026                  |
|  ( ) Sales Forecast        Updated 12 Oct 2026                  |
|  (-) Sales Excel           Excel model                          |
|      i PBIBrain cannot read Excel, push or live connected ...   |
| Not in the list? Paste a workspace connection                   |
|-----------------------------------------------------------------|
| [Back]                                     Cancel  [Next]       |
+-----------------------------------------------------------------+
```

Steps and states:

| Step | State | Content | Buttons |
|---|---|---|---|
| 1 Sign in | Signed out | Cloud icon, title, text | Cancel, "Sign in with Microsoft" (primary) |
| 1 Sign in | Signing in | Spinner, `role="status"` | Cancel, primary in the loading state (`aria-busy`) |
| 1 Sign in | Sign-in failed | `bad` banner, `role="alert"` | Cancel, "Try again" |
| 1 Sign in | Silent token works | Step 1 shows as done; the dialog opens on step 2 | none |
| 2 Select | Connected (signed in) | Account line, workspace combobox, model or report radio list | Back, Cancel, Next (disabled until the user selects one item) |
| 2 Select | Fallback | Workspace connection field, model name field | Back, Cancel, Next |
| 3 Access type | Default Read | Radio group | Back, Cancel, "Test connection" |
| 4 Test | Running | Check list in an `aria-live="polite"` region, one line for each check | Back, Cancel, "Add source" (disabled) |
| 4 Test | Result | "Checked" group, "Not checked" group | Back, Cancel, "Add source" |
| 4 Test | Failed | The failed check with the fix | Back, Cancel, "Test again" |

On "Add source" the UI calls `cloud_connect` (with the access type), then `source_add`. In the create flow of ticket 02, the dialog only adds the item to the draft; the calls run at "Create session". The token refresh on expiry is silent and has no UI (technical design 10.1).

Test result lines for a cloud model (each line: icon plus text):

| Group | Line | Icon |
|---|---|---|
| Checked | Signed in as <account> | check, `ok` |
| Checked | Connected through XMLA | check, `ok` |
| Checked | Model read: <n> tables, <n> measures | check, `ok` |
| Checked | Capacity: <type> | check, `ok` |
| Checked | Your role: <role> (only where an API gives it) | check, `ok` |
| Checked | Reports in <workspace>: <n> found, <n> readable. If some are not readable: "Not checked: report not readable (<names>). Export the report to a local PBIP, then add the PBIP folder." | check `ok`, or warning `warn` |
| Not checked | "Not checked: reports in other workspaces" / "PBIBrain reads reports only in the workspace of the model." | minus circle, `text-2` |
| Not checked | "Not checked: write conditions" / "PBIBrain 1.0 does not write to cloud models." | minus circle, `text-2` |

### Access type control

A radio group (Radix RadioGroup in the build), legend "Access type".

- "Read" (default, with the label "Default" at the right): "PBIBrain only reads <model>. It can be a donor or a compare source. It cannot be a target."
- "Read/Write": "PBIBrain saves this choice for a later version. PBIBrain 1.0 does not write to cloud models, so the model stays read-only now."
- Under the group: no "change later" line. Version 1 has no call that changes the access type after the add (orchestrator answer 6).

The cloud report flow uses the same control with "report" in place of "model". The Sources row shows "Access: Read" or "Access: Read/Write". No XMLA write warning in version 1.

Caution: keep the line "You can change the access type later" only if the backend gives a call for it. Section 14.2 has no such call (clarification 6 below).

### Pull to local PBIP flow

1. The user clicks "Pull to local PBIP" on a cloud model row (Sources tab) or on the Target step.
2. The dialog "Pull to local PBIP" shows the default folder `models/<model name>` (relative to the project root) and "Change folder" (native folder picker).
3. If the folder is not empty, the dialog shows an inline error and disables "Pull model".
4. The user clicks "Pull model". The UI calls `pull_to_local`. A progress list shows: Read the model, Export as TMDL, Write the PBIP files, Add as local source (`aria-live="polite"`).
5. Success: "<model> is now a local PBIP" / "Folder: <path>. PBIBrain added it as a local source." Button "Close". From the Target step, the new source is the selected target model.
6. Failure: the failed step with the fix, and "Try again".

With no open project (cloud-only session), the folder picker opens with no default. The local source path rule (POSIX path relative to the project root, technical design 11) then has no root (clarification 7 below).

### Naming rules screen

Place: the third section of the Sources tab (after Sources and Target, ticket 02).

```
| Naming rules for Sales Master                                              |
| These rules belong to the target model. Other merge sessions with this     |
| target use the same rules. Only confirmed rules and user rules mark a name.|
|----------------------------------------------------------------------------|
| [Proposed (3)|Confirmed (4)|Rejected (1)|All (8)]                          |
|                       [Confirm selected (2)] [+ Add rule] [Copy rules from] |
| Breaks: the count of existing names in Sales Master that do not obey the rule. |
| [ ] Rule                           Scope        Origin   Support      Breaks Status      Actions        |
| Measures                                                                   |
| [x] Measures with currency ... Amt All tables   Detected 37 of 40 m.  ! 3  o Proposed  [Confirm] [...] |
|     Measure names use Title Case   All tables   Detected 38 of 40 m.  ! 2  v Confirmed  Edit     [...] |
|     Measure names match ^[A-Z]...  Folder: KPIs User     Not detected ! 1  v Confirmed  Edit     [...] |
| Columns                                                                    |
|     Key columns end with Key       Table: Dim*  Detected 6 of 7 col.    1  x Rejected  [Confirm]       |
```

- Columns: select box (proposed rows only), Rule (plain phrase, code values in the code font), Scope, Origin (Detected, User), Support ("37 of 40 measures"; user rules show "Not detected"), Breaks (count, with a warning icon when more than 0 and the rule is not rejected), Status, Actions.
- Status badges (icon plus text): Proposed = `info` tint, dashed circle. Confirmed = `ok` tint, check circle. Rejected = plain, x circle, rule text in `text-2`.
- Groups: Tables, Columns (data and calculated), Measures (and report measures), Hierarchies, Calculation groups. An empty group does not show.
- Default filter: "Proposed" when proposed rules exist, otherwise "All". The prototype shows "All".
- The table scrolls inside its own wrapper. The Actions column is sticky at the right edge, so the actions stay visible at all widths.

Actions:

| Rule | Primary button | "More actions" menu | JS API call |
|---|---|---|---|
| Proposed (detected or copied) | Confirm | Edit, Reject | `naming_rule_confirm`, `naming_rule_edit`, `naming_rule_reject` |
| Confirmed, detected | Edit | Reject | `naming_rule_edit`, `naming_rule_reject` |
| User rule | Edit | Delete (destructive, confirm dialog) | `naming_rule_edit`, `naming_rule_reject` |
| Rejected | Confirm (undo icon) | none | `naming_rule_confirm` |
| Selected proposed rows | "Confirm selected (n)" in the toolbar | none | sequential `naming_rule_confirm`, each with the new `base_revision` |
| Toolbar | "Add rule" | none | opens the editor; save calls `naming_rule_edit` with no rule ID |
| Toolbar | "Copy rules from" | none | dialog, then `naming_rules_copy` |

Reject has no confirm dialog, because the Rejected filter and "Confirm" undo it. Each icon-only button has an `aria-label` with the rule phrase, for example "More actions: Measure names use Title Case".

### Rule editor

The side pane of ticket 02. Title "Add rule" or "Edit rule". Fields, in this order:

1. Object type: Select (Tables, Data columns, Calculated columns, Calculated tables, Measures, Hierarchies, Calculation groups).
2. Scope: Select (All tables, Table, Display folder). For Table or Display folder, a Combobox with the names in the target model. The user can type a pattern such as `Dim*`.
3. Check kind: Select (Prefix, Suffix, Letter case, Separator, Unit word, Folder by type, Regular expression). "Regular expression" shows only for user rules. "Folder by type" does not show for columns.
4. Fields for the kind:
   - Prefix, Suffix: text field "Prefix" or "Suffix".
   - Letter case: Select (Title Case, camelCase, PascalCase, snake_case, UPPER, lower).
   - Separator: Select (Space, Underscore, None).
   - Unit word: text field "Unit word", Select "Format kind" (Currency, Percent, Whole number, Decimal number, Date), Select "Position" (End of the name, Start of the name).
   - Folder by type: Select "Place" (Table, Display folder), then a Combobox for the table or folder name. Optional text field "Only names with the prefix".
   - Regular expression: text field "Pattern" (code font). Help: "Python regular expression. PBIBrain checks the full name."
5. Rule: a read-only preview of the plain phrase.
6. For a detected rule: "Support in <model>: <n> of <n> <type>. Breaks: <n>."
7. Footer: "Cancel", "Save rule" (primary).

The backend validates on save. A field error shows under the field (`aria-invalid`, `aria-describedby`) with the backend message. All selects are the new Radix Select and Combobox parts (map decision 4). No native select.

### Copy rules from

Dialog "Copy rules from a different model". A radio list of the session source models (local and cloud) with their rule counts. A model with 0 rules is disabled ("This model has no naming rules."). Note: "Copied rules arrive as Proposed in <target>. Confirm each rule to use it." Button: "Copy <n> rules". After the copy, the filter changes to "Proposed".

### Copy for each state, error and refusal

| Where | When | Copy |
|---|---|---|
| Sign in | Signed out | Title "Sign in to Power BI". Text "PBIBrain reads models from your Power BI and Fabric workspaces. Sign in with your work account. Windows keeps the sign-in. PBIBrain does not save it in the project." Button "Sign in with Microsoft" |
| Sign in | Window open | "Complete the sign-in in the Microsoft window" / "This dialog continues when the sign-in is complete. If you do not see the window, look for it in the taskbar." |
| Sign in | User closed the window | "Sign-in stopped" / "You closed the Microsoft window before the sign-in was complete. Sign in again to continue." / "Try again" |
| Sign in | Admin consent needed | "Your organization must approve PBIBrain" / "An admin must give consent to the PBIBrain app in Microsoft Entra ID. Send this message to your admin, then sign in again." |
| Sign in | No network | "Cannot connect to Microsoft" / "PBIBrain did not get a reply from the Microsoft sign-in service. Check your network connection, then try again." |
| Sign in | Other MSAL error | "Sign-in failed" / "Microsoft did not accept the sign-in. Try again, or use a different account." |
| Select | Account line | "Signed in as <account>" / link "Use a different account" |
| Select | No workspaces | "No workspaces found" / "This account has no workspace that PBIBrain can read. Ask a workspace admin for access, or use a different account." |
| Select | Workspace not on a capacity | "XMLA is not available in this workspace" / "The workspace must use Premium, Premium Per User, Fabric or Embedded capacity. Select a different workspace, or ask the workspace admin to move it to a capacity." |
| Select | No models in the workspace | "This workspace has no semantic models. Select a different workspace." |
| Select | Unsupported model type (disabled item) | "PBIBrain cannot read Excel, push or live connected models through XMLA." |
| Select | Fallback link | "Not in the list? Paste a workspace connection" / back link "Select from the list" |
| Select | Fallback field help | "Copy it in Power BI: workspace settings, then License info, then Connection link. Example: powerbi://api.powerbi.com/v1.0/myorg/Sales Analytics" |
| Select | Bad connection text | "This is not a workspace connection. It must start with powerbi://. Copy the connection link again." |
| Select | Model name not found | "No model with this name in the workspace. Check the name, then try again." |
| Access type | Read | "PBIBrain only reads <model>. It can be a donor or a compare source. It cannot be a target." |
| Access type | Read/Write | "PBIBrain saves this choice for a later version. PBIBrain 1.0 does not write to cloud models, so the model stays read-only now." |
| Test | Header | "PBIBrain checked these conditions for <model>." |
| Test | XMLA connect failed | "Cannot connect through XMLA" / "XMLA read is off for this capacity. Ask your capacity admin to turn on XMLA read, then test again." |
| Test | No Build permission | "Cannot read the model" / "You do not have Build permission on <model>. Ask the model owner for Build permission, then test again." |
| Test | Model not found any more | "Cannot find the model" / "<model> is not in <workspace> now. Select the model again." |
| Test | Report not readable (model source) | "Not checked: report not readable (<names>). Export the report to a local PBIP, then add the PBIP folder." |
| Test | Other workspaces | "Not checked: reports in other workspaces" / "PBIBrain reads reports only in the workspace of the model." |
| Test | Write conditions | "Not checked: write conditions" / "PBIBrain 1.0 does not write to cloud models." |
| Cloud report | Not readable (refused) | "Not checked: report not readable" / "PBIBrain cannot read the definition of <report>. Power BI gives the definition only to users with write permission on the report. Export the report to a local PBIP, then add the PBIP folder." / "PBIBrain did not add this report." / "Close", "Select a different report" |
| Cloud report | PBIR-Legacy definition | "<report> uses the PBIR-Legacy format. PBIBrain reads it for compare and impact only." (line in the test result) |
| Sources row | Added | Toast "<model> added as a read-only source." |
| Target step | Cloud model item (disabled) | "Pull to local PBIP first." with the button "Pull to local PBIP" |
| Pull | Confirm | "PBIBrain exports <model> as TMDL into a new local PBIP folder. The cloud model does not change." / "The folder must be empty or new." / "After the pull, PBIBrain adds the folder as a local source. The cloud source stays in the session." / "Pull model" |
| Pull | Folder not empty | "This folder is not empty. Select an empty folder or a new folder." |
| Pull | Done | "<model> is now a local PBIP" / "Folder: <path>. PBIBrain added it as a local source." / "Close" |
| Pull | Write failed | "Cannot write the folder" / "PBIBrain cannot write to <path>. Make sure that you can write to this folder, then try again." |
| Pull | Read failed | The same lines as the test failures above |
| Rules | Section note | "These rules belong to the target model. Other merge sessions with this target use the same rules. Only confirmed rules and user rules mark a name." |
| Rules | Breaks caption | "Breaks: the count of existing names in <model> that do not obey the rule." |
| Rules | No target | "No target model" / "Set a target model to see its naming rules." / "Change target" |
| Rules | Detection running | "Finding naming patterns" / "PBIBrain reads the names in <model>." |
| Rules | Empty | "No naming patterns found" / "<model> has too few objects with the same pattern. Add a rule or copy rules from a different model." / "Add rule", "Copy rules from" |
| Rules | Filter with 0 rows | "No proposed rules." (or "No confirmed rules.", "No rejected rules.") / "Show all rules" |
| Rules | Locked session | The ticket 02 banner; every rule and cloud button is disabled |
| Rules | `stale_revision` | Toast "The session changed in a different place. PBIBrain loaded the new state. Do the action again." |
| Rules | "Confirm selected" stopped at a failure | "<n> of <m> rules confirmed. <rule> was not confirmed: <backend message>." |
| Editor | Bad pattern | "This pattern is not a valid regular expression: <backend detail>. Fix the pattern, then save the rule." |
| Editor | Required field empty | "Enter a <field name>." |
| Editor | Same rule exists | "A rule with this scope and check kind exists: <rule>. Edit that rule." |
| Copy | Note | "Copied rules arrive as Proposed in <target>. Confirm each rule to use it." / "Copy <n> rules" |
| Copy | Model with no rules (disabled) | "This model has no naming rules." |
| Delete | Confirm dialog | Title "Delete this rule?" / the rule phrase / "PBIBrain stops checking names against this rule. Plan warnings for this rule go away." / "Cancel", "Delete rule" (destructive fill, trash icon) |

The "Same rule exists" line needs a backend check that section 5 does not state. Ticket 09 must confirm it. All copy uses `<placeholders>` as whole values, not sentence parts, for translation.

### Measurements (2026-10-31, Chrome 156.0.8078.49, playwright 1.63.0, axe-core 4.10.2)

- Page overflow (`measure.mjs`): 31 screens x 6 sizes (1024 x 640, then 1152, 1279, 1280, 1366, 1440 at 900 high) x 2 themes = 372 measurements. Page-level horizontal overflow 0 px, 0 elements past the right edge outside a scroll container, and 0 dialogs past the viewport edge, on all 372.
- Rule editor pane: column 360 px at 1280, 1366, 1440; sheet 400 px at 1024, 1152, 1279.
- axe (the rule tags of ticket 01), 31 screens at 1440 x 900, dark and light: 0 violations on all 62. The first run found `listitem` (serious) on `testing` and `pull-running`, because `role="status"` was on the `ul`. Fixed: the live region is now a wrapper `div`.
- Kit `verify_states.mjs` (default, hover, focus) through the gate wrapper, with `DS_REQUIRE_BROWSER=1`, on static snapshots (`snap.mjs`) of all 31 screens in both themes: 62 of 62 pass (5964 element-states). The first runs found two failures, now fixed. (a) "Delete rule" hover at 1.17:1 (dark) and 1.13:1 (light): the generic `.btn:hover` background replaced the destructive fill. Fixed with a destructive hover color. (b) `rules-select` dark: "More actions" on a selected row at 2.24:1. This is the known gate error: the gate dropped the alpha of `brand-soft`. Fixed with an opaque tint that renders the same color: `color-mix(in srgb, var(--brand) 12%, var(--surface))` (light: 9%). Ticket 09: give the selected-row tint as an opaque semantic token.
- Kit `verify_target_size.mjs` on `rules`, `rules-editor`, `result`, `rules-delete` (dark): 70, 84, 78, 76 targets, all at least 24 x 24. Pass.
- Kit `slop_tells.mjs --strict`: `rules` and `rules-editor`: no tells. `result` and `rules-delete`: MED "Only one distinct shadow". This is the intended design: surfaces are flat, and only the overlay has a shadow (ticket 02 anchor).
- Kit `check_no_emoji.py`: no emoji, no em dash or en dash. Kit `lint_native_select.py`: no native select.
- Raw results: `prototypes/07/shots/result.json`, `prototypes/07/shots/states.txt`.

UNMEASURED: the real Radix Dialog, RadioGroup, Select, Combobox and DropdownMenu focus behavior (the prototype uses static markup); focus return to the trigger after the dialog closes; the copy against real MSAL, XMLA and Fabric error codes (no real tenant, risk R1).

### Backend change requests and clarifications

1. Change request `cloud_items_list` (JS API, read only). Input: `kind` (`workspaces`, `models`, `reports`), `workspace_id` for models and reports. Output: workspaces (ID, name, capacity type, XMLA available yes or no); models (ID, name, updated time, model type, readable through XMLA yes or no with a reason code); reports (ID, name, format PBIR or PBIR-Legacy, dataset ID). Reason: section 14 has no call that lists cloud items, so the dialog cannot show a picker. JS API only, because the HTTP API has no authentication.
2. Change request `cloud_sign_in`: add the input `prompt` (`none`, `select_account`) and return the account display name. Reason: "Use a different account" and the "Signed in as" line. The UI only shows the account name; no file stores it.
3. Clarification, `naming_rule_reject` on a user rule: does it remove the rule, or keep it as "rejected"? The UI calls it "Delete". If the rule stays as rejected, the UI shows it in the Rejected filter.
4. Clarification, `naming_rule_edit` with no rule ID creates a user rule (origin `user`, status `confirmed`). Also: which status does a proposed rule get after `naming_rule_edit`? The UI expects "confirmed".
5. Clarification, `cloud_connect` result shape: the UI needs the test lines (check ID; result `ok`, `failed` or `not_checked`; a reason code; values such as capacity type, role, table and measure counts, report counts, and the names of not-readable reports).
6. Clarification, change of the access type after the add: section 14.2 has no call. Either `cloud_connect` again on an existing source, or the UI removes the line "You can change the access type later".
7. Clarification, `pull_to_local` in a cloud-only session (no project root): which path form does the session store for the new local source? Does a failed pull remove the partial folder?
8. Clarification, `naming_rules_copy` source list: the UI needs the rule count for each session source model (in `GET naming-rules` or `GET session`).

### Orchestrator answers to the clarifications (2026-10-31)

Numbers refer to the list above.

- 1 and 2: accepted as backend change requests.
- 3: `naming_rule_reject` on a user rule removes the rule. On a detected rule it keeps the rule as rejected.
- 4: `naming_rule_edit` with no rule ID creates a user rule (origin `user`, status `confirmed`). An edit of a proposed rule sets its status to `confirmed`.
- 5: accepted as a backend change request (the `cloud_connect` result shape above).
- 6: version 1 has no call that changes the access type after the add. The UI does not show the line "You can change the access type later".
- 7: a session always has a project root (ticket 02: no project, no session). `pull_to_local` stores the new local source path relative to the project root. A failed pull removes the partial folder.
- 8: `GET naming-rules` gives the rule count for each session source model.
