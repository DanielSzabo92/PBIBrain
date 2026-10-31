# Power BI Development Center: UI design

Status: ACCEPTED (baseline for the UI build). Date: 2026-10-31.

This document tells how the UI of the Development Center looks and works in version 1. It collects the decisions of the wayfinder map `.scratch/dev-center-ui/map.md` (tickets 01 to 11). Each decision has one home ticket. This document gives the decision; the ticket gives the reasons, the prototype, the screenshots, and the full measurement output.

The baselines are the [functional specification](DEV_CENTER_FUNCTIONAL_SPEC.md), the [technical design](DEV_CENTER_TECHNICAL_DESIGN.md) (section 14 data contracts, section 16 backend build steps S0 to S13), the ADRs in `docs/adr/`, and the word list [CONTEXT.md](../CONTEXT.md). Use "Merge Choice" for the choice on one row. The UI does not change a backend contract: each UI need that section 14 did not cover is a backend change request in technical design section 14.4.

Measurement rule: each contrast, a11y, state, and layout value in this document comes from a gate run (ticket 01 setup, Chrome 156.0.8078.49, playwright 1.63.0, axe-core 4.10.2, kit 3.0.0) on a prototype, or it has the mark UNMEASURED. A prototype value is not a value of the built app. Section 12 lists what the build must measure again.

## Contents

1. Scope and design direction
2. Place in the app and navigation
3. Layout and responsive rule
4. Screens
5. Flows
6. Components and their 8 states
7. Tokens
8. Copy
9. Accessibility contract
10. Data layer, errors, and refresh
11. Performance budgets
12. Measurement status
13. UI build steps
14. Out of scope
15. Open risks
16. Home tickets

## 1. Scope and design direction

### 1.1 Scope

Version 1 only: local merge plus cloud read. The UI has no cloud write (XMLA deploy, Fabric `updateDefinition`, PBIX warning dialog): these are version 1.1 (technical design section 10.4). Section 14 lists the other items that are out of scope.

### 1.2 Brief inference

| Item | Decision |
|---|---|
| Domain | Dev-tool (Power BI model and report merge) |
| Audience and tone | Expert BI developer. Calm, utilitarian. The apply copy is the plainest copy, because the apply is the highest-risk moment. |
| Mood | Precise. In the Agent tab: trustworthy (the user always sees what the agent wants, why, and what the user already chose). |
| Motion depth | Subtle feedback only: spinner, 2 px load bar, chevron turn, sheet slide. All motion stops with `prefers-reduced-motion: reduce`. |
| Layout family | List landing, then a work area: header strip, banner stack, tab row, main region, optional side pane. |
| Reference anchor | The existing PBIBrain shell (`frontend/src/App.jsx`, `theme.css`, `components/ui/`): dense, one accent (`brand`), flat surfaces, shadows only on overlays. |

### 1.3 House rules (from `design-doctrine`, binding for each U-step)

1. One thing leads on each screen. Section 4 names it for each screen.
2. One design system: `frontend/src/theme.css` tokens and `frontend/src/components/ui/` parts. New semantic tokens only for new meanings (section 7).
3. Each status shows an icon plus a word, never color only. Wireframe statuses add a pattern.
4. No native `<select>` in new screens. Use the new Select and Combobox parts.
5. No colored border on one side only of a card, notice, toast, row, node, or tab. Use a full hairline border or a surface fill.
6. Token by intent: a destructive action wears the destructive token on the trigger and on the confirm button.
7. Each interactive part has the 8 states (section 6.2).
8. No emoji, no em dash, no en dash, and no ellipsis character in UI copy or in new code.

## 2. Place in the app and navigation

Home ticket: 02.

- The existing shell gets one sidebar item, "Development Center". With no open session it shows the session list ("Merge sessions"). With an open session it shows the work area of that session. No second window, no second app.
- One open session at a time. The open session stays open while the user goes to other sidebar items. "Close session" (in the "More" menu) calls `session_close` and shows the list. A click on a session in the list when another session is open calls `session_close`, then `session_open`.
- Breadcrumb: "Development Center > <session name> > <tab>". The first part shows the list. The session stays open.
- Work area tabs (Radix Tabs, automatic mode): Compare (default), Impact, Plan, Agent, Sources, Log. Labels with a count: Plan (blocking items, `bad` tone), Agent (open proposals plus open questions). The app keeps the last tab, the Impact view, the selected item, and the "Include open proposals" switch for each session in memory, not on disk.
- Deep links between tabs (in memory, no URL routing): "Show these rows" opens Compare with the marks filter. "Show row" opens Compare with that row active. "Show impact" opens Impact on that object. "Show impact of this row" opens Impact with the row scope. "Open Sources", "Open Agent", "Open Compare", "Open Log" open that tab. The plan status button in the header opens the Plan tab.

## 3. Layout and responsive rule

Home tickets: 02 (rule), 03 to 08 (measured on each prototype).

- Design target 1440 x 900. Minimum supported window 1024 x 640. No phone layout. The kit rule "mobile is the base" does not apply (map decision 5); CSS uses `min-width: 1280px` and `max-width: 1279.98px` queries.
- No page-level horizontal overflow at any width from 1024 to 1440. Wide grids and tables scroll inside their own region. A scroll region that holds visually hidden text is `position: relative`. Each child of a flex column has `min-width: 0`.

| Pane | 1280 px and wider | Below 1280 px (to 1024 x 640) |
|---|---|---|
| App sidebar | 236 px | 236 px |
| Work header | One row. "Check sources" is a button. | "Check sources" moves into the "More" menu. The header wraps. |
| Banner stack | Full width. Order: locked, source missing, sources changed, Desktop after apply. | The same. Text and actions wrap. |
| Tab row | One row | Scrolls inside its own row if necessary |
| Main region | Fills the space left of the side pane | Full width |
| Side pane (row detail, impact item, rule editor) | Fixed right column, 360 px (`--pane-w`) | Modal sheet `min(400px, 92vw)` (`--sheet-w`), full height, Escape closes |
| Compare sticky columns | Checkbox, Object, Row state, Target | Checkbox, Object |
| Plan body | Two columns (5fr and 7fr) | One column |
| Code diff | Side by side | Unified |
| Dialogs | Max width of each dialog (640 px removal policy, 600 px apply); body scrolls; footer stays in view | The same; measured inside the window at 1024 x 640 |
| Menus | Align to the trigger edge that keeps them on screen | The same |

Measured on the prototypes: page overflow 0 px in 1,464 measurements (tickets 02 to 08: 6 sizes, 2 themes). Pane mode: column 360 px at 1280, 1366, 1440; sheet 400 px at 1024, 1152, 1279. The built app: UNMEASURED until U3 (section 13).

## 4. Screens

Each screen row names the element that leads. Copy keys refer to section 8.

### 4.1 Session list and create flow

Home ticket: 02.

| Screen | Leads | Content |
|---|---|---|
| No project | Empty state | Folder icon, "Open a project to start a merge session", "Open project" (primary). A session always has a project root. |
| No sessions | Empty state | "No merge sessions yet", "New merge session" (primary). |
| Session list | The table | One dense table: Name, Target, Sources, Plan, Last change, Status. Newest first. "New merge session" (primary) in the page heading. The name is a link and the full row is clickable. Rows with "Needs a newer PBIBrain" or "Cannot read" have no link and show a reason line. Locked rows show "Open in another window" / "Opens read-only.". No delete and no rename in version 1. Data: `GET sessions`. |
| Create, step 1 Sources | The source list | "Add source" menu: PBIP project, Model folder (TMDL), model.bim file, PBIR report, separator, Cloud model, Cloud report. PBIX is refused inline (`refuse.pbix`). "Next" needs at least one model source. |
| Create, step 2 Target | The target model radio list | Two radio lists (model, report). Disabled items show the fixed refusal (`refuse.*`). "Copy of <source>" opens the native folder picker. Default target model: none. Default target report: "New empty report". A cloud model shows "Pull to local PBIP first." with the button "Pull to local PBIP". |
| Create, step 3 Name and create | "Create session" | Name field (default "<target model name> merge"), summary, progress list (`aria-live="polite"`). |

The create page is a full page in the main column (max 880 px) with a step indicator, Back and Next. The UI keeps a draft only and calls the JS API only at "Create session" (section 5.1).

### 4.2 Work area frame

Home ticket: 02.

- Header: h1 session name; target model and target report line; plan status button (`ok` "Valid", `warn` "Valid with <n> warnings", `bad` "Plan not valid: <n> blocking", plain "Checking plan" with spinner); "Check sources"; "More" menu.
- Banners (Notice part, full hairline border): locked (`info`, "Try again"; all change controls disabled), source missing (`bad`, "Open Sources", hidden on the Sources tab), sources changed (`warn`, "Show these rows"), Desktop after apply (`warn`, closable).
- `sources_check` runs automatically on open.

### 4.3 Compare tab

Home ticket: 03. Leads: the grid.

- Filter bar: "Search names" (200 px, `q`, 150 ms debounce), filter buttons Type, Table, Display folder, State, Source, Page, Changed since, Marks, Has proposal, Has question, then "Compare" with the segmented radio group "Default | Strict". Table and Display folder use the Combobox. Active filters show as chips with "Clear filters". Default filter: "State: not same", as a removable chip.
- Grid columns: checkbox (40 px), Object (260 px: type icon, name, "<type>, <table>"), Row state (116 px: highest-precedence state plus "+N"), Target (132 px), one column for each donor in session order (132 px: StateCell), Merge Choice (228 px: text or "Not set", plus at most one badge in the priority "Confirm row first", "Question", "Proposed"), Marks (112 px). The proposed choice shows only in the badge tooltip.
- Fixed row height 36 px, header 34 px. Property phrases show in the tooltip and in the row detail.
- Footer: row count and state counts (below 1280 px: row count and mode only).
- Row backgrounds: hover `--row-hover`, bulk-selected `--row-selected`, active `--row-active`.
- Click or Enter sets the active row and opens the row detail. Checkbox or Space sets the bulk selection. These are two separate states.
- Bulk bar replaces the filter bar while rows are selected: "<n> selected", "Set Merge Choice" (Menu, key M), "Confirm <n> rows" (only with the Marks filter, `row_confirm` with a key list), "Clear selection". The header checkbox selects the loaded rows; then the link "Select all <N> rows that match the filters" collects the keys by paging (max 5,000) and sends explicit keys to `merge_choice_bulk_set`.
- Code diff: modal dialog 92 vw x 86 vh, from "Show code diff" or key D on a donor cell that is not Same. Radio group "Compare target with". Lines have numbers, a "-" or "+" mark, the `--bad-tint` or `--ok-tint` fill, and sr-only "Removed: " or "Added: ".
- Compare mode switch keeps the filters, clears the bulk selection, and keeps the active row if it still exists.
- No grouping by table in version 1. Columns sort by state, name, type, or table.
- States: loading (30 skeleton rows, 2 px load bar, `aria-busy`), later page (skeleton rows in the gap), compare read longer than 1 s ("Comparing sources"), empty (`compare.empty`), error (`compare.error`, "Try again"), no match (`compare.no_match`, "Clear filters").

### 4.4 Row detail pane

Home ticket: 04 (with the ticket 09 words). Leads: the Merge Choice group.

Section order: header (h2 name, type, table, row state, "Previous row", "Next row", Close); row notices (source mark, then blocking items, then warnings); agent proposal card or question card; Merge Choice group with the fields of the selected choice; Alignment (collapsible); Sources (collapsible, with "Show code diff"); "Show impact of this row".

| Choice | Fields when selected | Disabled when (reason text) |
|---|---|---|
| Keep target ("Do not add (keep target)" on a target-missing row) | none | never |
| Take from <source> | Source Select (2 or more donors), "Change name", Display folder | no donor has the object |
| Take properties from <source> | Source Select, property picker (different properties preselected, at least one) | target missing; type is not a measure, column, or relationship |
| Add as new name | New name (required, from `POST name-propose`), Display folder | no donor has the object |
| Remove from target | Removal policy summary and "Select removal policy" | target missing |
| Skip ("No change now. The row stays open.") | none | never |
| Promote to target model (report measure rows) | Name, Display folder | never; a clash shows as the clash error |
| Copy into target report (report measure rows) | Name | the source report is the target report |

- Save is immediate: each commit calls `merge_choice_set` with `base_revision`. Radio and Select commit on change; text fields commit on Enter or blur; Escape puts back the last saved value. The selected radio shows "Saving" with `aria-busy`. No undo button in the pane.
- Name check: 300 ms after the last key, `POST name-propose` with `candidate`. A rule break is a warning (save permitted). A clash is an error that makes the plan blocking, with "Use proposed name". "Propose name" is an icon button next to the field.
- Display folder: Combobox with the groups "In target" and "In <source>" and `Use new folder "<text>"`. Data: `GET display-folders`. On a load failure the field still accepts free text.
- Alignment: "Confirm rename", "Reject rename", "Split row" (confirm dialog; the Merge Choice of the row is removed; the selection moves to the row that keeps the target object), "Join with a row" (dialog with a search Combobox). All call `alignment_override`.
- Removal policy: the pane calls `GET impact/removal/{object}`. With dependents the policy dialog opens only on "Select removal policy" (section 5.3).
- Source mark notice with "Confirm row". A change of the Merge Choice does not confirm the row.
- Many selected rows: "<N> rows selected" and a pointer to the bulk bar. Read-only session: all change controls disabled, one info notice; code diff and impact links stay active.

### 4.5 Impact tab

Home ticket: 05. Leads: the view region (table by default).

- Toolbar row 1: scope Select ("Whole plan" or "Row: <name>"), group control "Breaks (n) | Needs (n) | Offers (n)" (blocking count in the `bad` tone; default: the first group with blocking items, else Breaks), view control "Table | Graph | Wireframe". Row 2: "Blocking only", Severity, Certainty, Model or report, Type, "Find object or reason", the switch "Include open proposals" (off by default). Row 2 is hidden in Offers.
- Proposals banner when the switch is on: "This view includes <n> open agent proposals. Apply uses only accepted choices." Items that come only from a proposal show the "Proposed" tag (bot icon).
- Completeness strip above each view: "Complete" (`ok`) or "Incomplete: <n> areas" (`warn`), one sentence, "Show areas". Areas list each entry, 20 at a time ("Show 20 more"). Default closed, but open when incomplete and the user did not close it in this session.
- Table: real `<table>`, two-line item rows (status chip, type icon, name button, place, severity, tags; line 2 reason phrase, shortest path, "<n> other paths"). Status rule: Blocking = blocking flag; Information = severity "mapped" or "not changed by this plan"; Warning = all others; Possible items never block. Sort: blocking, severity, name. One primary button (first allowed of `include_in_rewrite`, `set_policy_repoint`, `set_policy_cascade`, `map_to_target`, `add_from_donor`), other actions in a row menu. Bulk only for "Include in rewrite" and "Add from donor". Pages of 500, virtual scroll.
- Item pane: status, h2 name, full reason, blocking sentence, shortest path (PathStepList), "Show other paths" (`GET impact/{item}/paths`), Cause link, Certainty, Policy, actions with one line each. Cascade, Repoint, and Map to target take their input in the pane.
- Graph: reuse `layoutGraph`, `routePath`, `RoutedEdge`, and the zoom and fit pattern. New ImpactNode 224 x 76 px. Only the union of the shortest paths of the filtered items. Solid edge = certain, dashed = possible. Limit 150 nodes, else "Too many items for the graph" with "Open table". Text alternative: the table, with "Show as table".
- Wireframe: report trigger (target after apply, donors now, other reports "not changed by this plan"), page list (200 px), scaled canvas, "Drawing | Visual list". Each visual shows one status in the order removed, breaks, changes, new, not checked, unchanged, with pattern, icon, and word (section 7.3). Offer visuals in a donor report have a checkbox.
- Offers: tree by donor report, page, visual and filter; page checkbox with the mixed state; each change calls `offer_select`; bookmarks are "Information only". Selected visuals that need missing fields add Needs and the banner "<n> fields need an action before the copy can work." with "Open Needs".
- After each action: the list keeps scroll and selection, shows "Updating", and the toast "1 item resolved. <n> blocking left."

### 4.6 Plan tab

Home ticket: 08. Leads: the status strip with "Apply plan" (status text 18 px).

- Strip: status, one line ("41 plan steps, 2 warnings. Full check 10:58."), "Check plan" (full mode), "Apply plan". With blocks, "Apply plan" is disabled with the visible reason "Fix <n> items before you apply." (`aria-describedby`). "Apply plan" wears the destructive token when the plan deletes 1 or more objects.
- Block list "Before you apply" (only with blocks). Order: source marks, plan blocking items, Desktop, non-canonical files, full validation failures. Each block has one fix action: "Show these rows", "Show impact", "Show row", "Check again", "Format files first".
- Summary table (plan step counts by object type: Create, Delete, Modify, Rename; deletes in `bad` and bold, zero in `text-3`), Warnings, Plan steps (phases Deletes, Renames, Creates, Changes, Expression rewrites, Report changes; "All | Model | Report"; text filter; expand to operations with exact old and new text; list max 440 px high).
- Proposals line: "This plan uses accepted choices only. <n> agent proposals are open and are not in it." with "Open Agent". The Plan tab has no proposals switch.
- Result panel above the strip after an apply (section 5.6). Empty plan: "Nothing to apply" with "Open Compare".

### 4.7 Agent tab and Log tab

Home ticket: 06. Agent leads: the first open question card.

- Questions section (only with open questions): one full question card, then "<n> more open questions. Show them", then "Answered (<n>)" collapsed. "Last check <time>" and "Refresh".
- Proposals table: checkbox (only "Ready to accept" rows), Target (kind above the link), Proposed change (plus "Your choice"), Confidence (whole percent), Reason (one line, expands), From (MCP client and time), Status ("Ready to accept", "Confirm row first", "Conflicts with your choice"), sticky Actions (Accept or "Replace with agent choice" or "Open row"; Reject). Filters Kind, Status, target search. Newest first. "Accept selected (<n>)" and "Accept all".
- Reject is one click with no confirm. A rejected proposal does not come back.
- New proposals: the 5 s poll updates the counts; the list does not change by itself; the notice "<n> new proposals. Show them" (`role="status"`) loads it again.
- Proposal card (also at the top of the row detail): badge "Proposed by agent", client and time, the change in plain words (15 px, 500), "Your choice", Confidence, Reason (full), actions. Full `line-strong` border on `surface-2`. On a marked row: note, "Confirm row", Accept disabled.
- Question card: question text, radio options with effect lines, the recommended option preselected with "Recommended", Reason, "Answer", "Open row". No free text and no dismiss in version 1.
- Log tab: one table (Time, Author "You" or "Agent: <client>", Action label, Target link, Before, After (code font, empty = "None"), Reason, Proposal link). Filters Author, Action, target search, proposal chip. "Show more" while `has_more`. No edit, no delete.

### 4.8 Sources tab, cloud sources, naming rules

Home tickets: 02 (sources, target), 07 (cloud, naming rules).

- Sections: Sources (rows: kind, role, access type, status, actions "Find source", "Remove", "Pull to local PBIP" on cloud models), Target ("Change target"), Naming rules.
- Remove source: the confirm dialog cannot know the count before the call, because no read gives the Merge Choices for each source. The dialog text is "Remove <source> from this session?" / "Merge Choices that take from <source> stay, but the plan is not valid until you change them." The toast after the call gives the count from the `source_remove` reply (UC33): "<source> removed. <n> Merge Choices need a new source." This replaces the ticket 09 text with a count in the dialog.
- Cloud connect dialog (Radix Dialog): steps 1 Sign in, 2 Select model or report (from `cloud_items_list`; fallback "Paste a workspace connection"), 3 Access type ("Read" default; "Read/Write" saved for a later version; no change after the add), 4 Test ("Checked" and "Not checked" groups). Step 1 is skipped when a silent token works. "Signed in as <account>" with "Use a different account". No sign-out in version 1. A cloud report that is not readable is not added.
- Pull to local PBIP dialog: default folder `models/<model name>` relative to the project root, "Change folder", refusal of a folder that is not empty, progress list, result. The new folder becomes a local source; from the Target step it becomes the target.
- Naming rules: status filter "Proposed | Confirmed | Rejected | All" (default Proposed when proposed rules exist), table grouped by object type (Rule, Scope, Origin, Support, Breaks, Status, sticky Actions), "Confirm selected (<n>)", "Add rule", "Copy rules from". Rule editor in the side pane; the backend validates on save. Delete of a user rule has a destructive confirm dialog. Reject has no confirm.

## 5. Flows

### 5.1 Create a session

1. The user clicks "New merge session".
2. Step 1: the user adds sources. Local items open the native picker. Cloud items open the cloud dialog in draft mode (no call).
3. Step 2: the user selects the target model and the target report.
4. Step 3: the user clicks "Create session".
5. The UI calls `session_create`, then `source_add` for each source in list order, then `target_set`. Each call sends the `base_revision` of the previous reply.
6. Success opens the work area on Compare. A failure leaves the session, marks the failed item, and offers "Open session" (Sources tab). Cancel before step 5 leaves nothing on disk.

### 5.2 Set Merge Choices in bulk

1. The user selects rows (checkbox, Space, Shift ranges, Ctrl+A, or "Select all <N> rows").
2. The user selects a choice in "Set Merge Choice".
3. A confirm dialog shows only for "Remove from target" or when selected rows have a different Merge Choice. It counts replaced rows and skipped rows. Initial focus: Cancel.
4. The UI calls `merge_choice_bulk_set` with the possible row keys, clears the selection, and fetches the visible pages again.
5. Toast: "Merge Choice set for <n> rows. <n> rows skipped."

### 5.3 Set a removal policy

1. The user selects "Remove from target" (row detail) or a policy action (Impact).
2. The UI reads `GET impact/removal/{object}`. With 0 dependents the pane says "No object uses this. It is removed with no other change."
3. With dependents the pane shows "Removal policy: Block" and "Select removal policy".
4. The dialog offers Block ("Use Block"), Cascade (table of effects; "Use Cascade (remove <n> objects)", destructive), and Repoint (Combobox of same-kind candidates with a data type warning; "Use Repoint" disabled until a candidate is selected).
5. Confirm calls `removal_policy_set`. Cancel keeps the old policy.

### 5.4 Accept agent proposals

1. "Accept" or "Replace with agent choice" calls `proposal_accept`. "Accept selected" calls it for each item in sequence.
2. "Accept all" opens the summary dialog. The UI reads `GET plan` (accepted state) and `GET plan?include_proposals=ready`. The dialog shows the kinds, the plan now and after, the change, and the skipped items with their reasons. Initial focus: Cancel.
3. "Accept <n> proposals" calls `proposal_accept_all`. Toast: "<n> proposals accepted. <n> skipped."

### 5.5 Apply the plan

1. "Apply plan" calls `GET apply/preview` ("Checking before apply"). Blocks go to the block list, and the dialog does not open.
2. The dialog "Apply the plan to <target>?" shows the counts, the delete line, the approval items (Critical, High, Not checked), and the Desktop line. One approval checkbox shows only when approval items exist; the confirm stays disabled until it is checked. Initial focus: the checkbox, else Cancel. The dialog binds the plan hash.
3. Confirm calls `apply`. The dialog changes to the progress list (steps 1 to 6 done; steps 7 to 11 from `GET apply/progress`, polled every 500 ms; fallback "Applying plan. <time> elapsed."). No close button; Escape does nothing.
4. The result panel shows success, differences, or failure ("Nothing was written"). Focus goes to the panel title.
5. `stale_revision` from `apply`: "The plan changed after you opened this dialog. Check it again." with "Check plan".

### 5.6 Undo, format only, change report

- Undo: only the last apply of the session while its backup exists (`GET apply/last`). Confirm dialog (destructive "Undo apply", focus on Cancel), progress (Restore the files, Rescan, Save the fingerprints), toast. Refused when target files changed after the apply, with the file list. No "Undo anyway".
- Format only: "Format files first" opens "Format <n> target files?" (primary, not destructive). Same progress and result pattern. After success the app runs "Check plan" (full) automatically.
- Change report: native save dialog (project root, "<session name> change report <yyyy-mm-dd>.md"), `change_report_write`, toast "Change report saved" with "Show in folder". The app never commits or pushes.

### 5.7 Pull a cloud model to local PBIP

1. The user clicks "Pull to local PBIP" (Sources row or Target step).
2. The dialog shows the folder. A folder that is not empty disables "Pull model".
3. "Pull model" calls `pull_to_local`. The progress list shows Read the model, Export as TMDL, Write the PBIP files, Add as local source.
4. Success adds the local source. A failure shows the failed step with the fix and "Try again". The backend removes a partial folder.

## 6. Components and their 8 states

Home ticket: 09 (sections 1.1 to 1.5 give the anatomy, ARIA, and the full state table of each part).

### 6.1 Inventory

- Reused with no change: Card, Label, Separator, Input, Badge. Sheet and NativeSelect are not used in new screens (the Sheet has a one-sided top bar).
- Changed (also on old screens): Button (destructive uses `--bad-ink` on `bad`, hover `--bad-strong`; new `destructive-outline` and `status` variants; `loading` prop), Tabs (each panel stays in the DOM with `forceMount` and `hidden`; active tab = fill, never an underline), Checkbox (24 x 24 px target, indeterminate state, error state), `theme.css` (section 7).
- New generic parts in `frontend/src/components/ui/`: Select, Combobox, Menu, FilterButton with Popover, FilterChip, SegmentedControl, Switch, ChoiceRadio group, StatusBadge, Tooltip, Notice and Banner, Toast, Dialog and AlertDialog (with progress mode), SidePane, StepIndicator, ProgressList, ResultPanel, EmptyState, Skeleton, DataTable.
- New Development Center parts in `frontend/src/devcenter/components/`: BulkBar, NameField, StateCell, CompareGrid, CodeDiff, ProposalCard, QuestionCard, ImpactItemRow, CompletenessStrip, ImpactNode, WireframeBox, PathStepList, plus the screen parts of section 4.

### 6.2 Shared state rules

| State | Rule |
|---|---|
| default | Control border `control-border` (never `line`, `line-strong`, or `input`). Fill `surface` or `surface-2`. |
| hover | `surface-hover` (rows `--row-hover`). A destructive fill keeps `bad` and goes to `--bad-strong`. |
| focus | 2 px `ring` outline, 2 px offset, never hidden under a sticky part, bulk bar, toast, or sheet. |
| active | `surface-3` while pressed. An open Select, Combobox, or Menu has `aria-expanded="true"` and a `brand` border. |
| disabled | Opacity 0.5 (`--disabled-opacity`; Button keeps 0.45), `cursor: not-allowed`, and a visible reason where a ticket gives one (`aria-describedby`). A locked session disables each change control. |
| loading | The control shows a spinner and its loading text, `aria-busy="true"`, `aria-disabled="true"`. A region shows skeleton bars, `aria-busy`, and a visible status text. |
| error | `aria-invalid`, `bad` border, hint with an x icon and the fix, `aria-describedby`. Region errors use the EmptyState error variant or a `bad` Notice with "Try again". |
| selected | Bulk row `--row-selected`, active row `--row-active` with `aria-selected="true"`, checked table row `--brand-tint`, selected option a `brand` check, pressed segment `surface-3`. |

Specimen measurement (ticket 09, static markup): 177 element-states pass `verify_states` in both themes, 0 axe violations, 215 text elements meet AA, 138 targets pass target size. The real Radix behavior: UNMEASURED until U1.

## 7. Tokens

Home ticket: 09 (section 2). Values are in `.scratch/dev-center-ui/prototypes/09/tokens.css`.

### 7.1 New values in `theme.css` (both themes)

| Token | Dark | Light | Meaning |
|---|---|---|---|
| `--ok-tint` | `#1c2b28` | `#e9f5f0` | `ok-soft` over `surface`, opaque |
| `--warn-tint` | `#2d2921` | `#f8f1e7` | `warn-soft` over `surface`, opaque |
| `--bad-tint` | `#2e2225` | `#fbefef` | `bad-soft` over `surface`, opaque |
| `--info-tint` | `#1e2833` | `#eaf2f9` | `info-soft` over `surface`, opaque |
| `--brand-tint` | `#222535` | `#eff0fc` | `brand-soft` over `surface`, opaque |
| `--bad-ink` | `#0b0c0f` | `#ffffff` | text and icon on a `bad` fill |
| `--bad-strong` | `#f49a9a` | `#9f2626` | hover of a `bad` fill |

New screens use the opaque `-tint` tokens for each fill under text, because the kit state gate drops alpha. Old screens keep `-soft`.

### 7.2 Semantic aliases

`--cmp-conflict` = `bad`; `--cmp-missing` = `text-2`; `--cmp-renamed` and `--cmp-moved` = `info`; `--cmp-different` = `warn`; `--cmp-same` = `text-3`; `--cmp-changed` = `brand`; `--proposal` = `brand-strong`, `--proposal-tint` = `--brand-tint`; `--impact-removed` and `--impact-breaks` = `bad`; `--impact-changes` = `warn`; `--impact-new` = `ok`; `--impact-unchecked` = `info`; `--impact-unchanged` = `control-border`; each `--cmp-*` and `--impact-*` color that fills has a `-tint` alias; `--row-hover` = `surface-hover`, `--row-selected` = `surface-3`, `--row-active` = `--brand-tint`.

Other statuses use the existing tones through StatusBadge: severity Critical `bad`, High `warn`, Not checked plain; certainty Possible plain with the help icon; plan status Valid `ok`, Valid with warnings `warn`, Not valid `bad`, Checking plain; source marks `warn`; naming rule Proposed `info`, Confirmed `ok`, Rejected plain.

Layout tokens (no color) go into a `devcenter.css` block: `--pane-w: 360px`, `--sheet-w: min(400px, 92vw)`, `--row-h: 36px`, `--target-min: 24px`, `--control-h: 32px`, `--space-1` to `--space-6` (4 px steps), `--disabled-opacity: 0.5`.

### 7.3 Wireframe status patterns

| Status | Border | Fill | Icon and word |
|---|---|---|---|
| Removed | 1 px solid `--impact-removed` | 45 degree hatch of `--impact-removed-tint` and `surface`; title struck through | trash, "Removed" |
| Breaks | 3 px solid `--impact-breaks` | `surface` | circle-x, "Breaks" |
| Changes | 2 px dashed `--impact-changes` | `surface` | triangle-alert, "Changes" |
| New | 2 px dotted `--impact-new` | `--impact-new-tint` | plus, "New" |
| Not checked | 1 px dashed `--impact-unchecked` | `surface` | circle-help, "Not checked" |
| Unchanged | 1 px solid `--impact-unchanged` | `surface` | no status line |

### 7.4 Measured contrast (kit `contrast.py`, ticket 09 section 2.4, 61 pairs)

All new pairs pass. Lowest values: `brand` on `--brand-tint` 5.80 dark, 4.87 light; `text-3` on `--row-active` 5.24 dark, 4.79 light; `control-border` on `--row-active` 3.11 both; `control-border` on `--row-selected` 3.30 dark, 3.08 light; wireframe borders on `surface` 3.74 dark, 3.52 light; `--bad-ink` on `bad` 7.49 dark, 5.79 light. The only failure is the existing destructive Button text `#fff` on `bad` in dark (2.61:1), fixed in U1.

Caution: do not change `--row-active` or `--row-selected` without a new measurement, because two pairs have little margin (4.79 and 3.08 in light).

UNMEASURED: the struck "Removed" title on the hatch (no gate samples a gradient).

## 8. Copy

Home ticket: 09 (section 3, the full catalog with keys). U2 moves the catalog into `frontend/src/devcenter/copy.js`. After U2, `copy.js` is the source of truth; ticket 09 section 3 is the history.

### 8.1 Rules

- ASD-STE100 and the `ux-writing` skill. Sentence case. Buttons start with a verb and name the object ("Apply plan", "Undo apply", "Remove source").
- Errors give what happened, why, and how to fix it.
- No em dash, no en dash, no emoji, no ellipsis character, no "(s)" plural form. Numerals for counts.
- A `<placeholder>` is always a whole value (name, count, path, time), never a part of a sentence.
- Empty values: "None" for an empty value, "Not set" for a Merge Choice that is not set, "Not known" for data that the app does not have.
- Words from ticket 09: "Split row", "Join with a row", "Aligned by", section "Alignment", "Take from <source>".
- Phrase text (compare properties and notes, impact reasons, edge phrases) comes from the backend file `backend/devcenter/contracts/phrases.json`. The UI shows `text` only.

### 8.2 Key families

`shared.*` (stale toast, network, unknown, locked, read-only, not current, session not open, include proposals), error code texts (one for each code of technical design section 12 plus `network` and `unknown`), `refuse.*` (fixed refusals), `list.*`, `create.*`, `work.*`, `sources.*`, `compare.*`, `row.*`, `impact.*`, `agent.*`, `log.*`, `rules.*`, `cloud.*`, `plan.*`, `apply.*`, `undo.*`, `format.*`, `report.*`, `details.*` (one sentence for each apply `details.step` and `details.check`).

### 8.3 Shared texts that each tab uses

| Key | Text |
|---|---|
| `shared.stale` | "This session changed in another place. The view shows the latest state. Do the action again." |
| `shared.network.title` / `.body` | "Cannot reach PBIBrain" / "The local API did not answer. Make sure PBIBrain is running, then try again." |
| `shared.unknown.title` / `.body` | "Something stopped this action" / "<backend message> Try again. If it fails again, open the Log tab and copy the details." |
| `shared.locked.banner` | "Another PBIBrain window has this session open. You can read it, but you cannot change it." / "Try again" |
| `shared.not_current` | "This data is not current. Try again to load it." |
| `shared.session_not_open` | "This session is not open now. Open it again from the list." |

### 8.4 Confirm dialogs

The title asks. The confirm button restates the action and the object. Cancel stays "Cancel". No type-to-confirm, because each action can be undone (Merge Choices change again; Apply has Undo).

| Dialog | Confirm (token) | Initial focus |
|---|---|---|
| Remove source | "Remove source" (destructive) | Cancel |
| Bulk set Merge Choice | "Set Merge Choice" (primary) | Cancel |
| Bulk remove | "Remove from target" (destructive) | Cancel |
| Split row | "Split row" (primary) | Cancel |
| Removal policy | "Use Block" (primary), "Use Cascade (remove <n> objects)" (destructive), "Use Repoint" (primary) | the policy radio group |
| Accept all | "Accept <n> proposals" (primary) | Cancel |
| Delete rule | "Delete rule" (destructive, trash icon) | Cancel |
| Pull to local | "Pull model" (primary) | the folder field |
| Apply | "Apply plan" (destructive when the plan deletes objects, else primary) | the approval checkbox, else Cancel |
| Format files | "Format files" (primary) | Cancel |
| Undo | "Undo apply" (destructive) | Cancel |

## 9. Accessibility contract

Home ticket: 09 (section 4). Target: WCAG 2.2 AA, plus reduced motion as a house rule. Each rule has one test. "e2e" = Playwright on the fake server, "unit" = `node --test`, "kit" = manual kit gate with `DS_REQUIRE_BROWSER=1`, "SR" = manual NVDA and Narrator pass.

### 9.1 Rules and tests

| ID | Rule | Test |
|---|---|---|
| A1 | Zero axe violations (wcag2a, wcag2aa, wcag21a, wcag21aa, wcag22aa) on each screen and state, both themes. | e2e, `axe-core@4.10.2` |
| A2 | Text contrast 4.5:1 (large 3:1) in each state. | CI `tests/test_theme_contrast.py`; kit `verify_states` |
| A3 | Control boundaries, focus rings, status borders, graph and wireframe marks 3:1. New controls use `control-border`. | CI contrast test; CI lint (no `border-input` or `line-strong` border on a control in `frontend/src/devcenter/**`) |
| A4 | No color-only status: icon plus word; wireframe adds a pattern. | e2e (`[data-status]` has an svg and text); unit (StatusBadge refuses a tone with no label) |
| A5 | No one-sided colored border. | CI lint; kit `slop_tells --strict` |
| A6 | Each action works with the keyboard only (section 9.3). No trap outside modal dialogs. | e2e keyboard specs; kit `verify_keyboard` |
| A7 | Focus always visible and never hidden. | e2e (outline 2 px; `elementFromPoint` at the center is the element) |
| A8 | Focus order = visual order: header, banners, tabs, toolbar, main region, side pane. | e2e Tab order snapshot (Compare, Impact, Plan, Agent) |
| A9 | Dialog focus: initial focus as in section 8.4, trap, Escape (not in progress mode), return to the trigger, else to the h1 of the tab. | e2e for each dialog; kit `verify_focustrap` |
| A10 | SidePane: keyboard open puts focus on the h2; the sheet traps focus; close returns focus to the opener. | e2e at 1440 x 900 and 1024 x 640 |
| A11 | One polite live region for toasts and counts; async results announced (validate, apply progress, apply result, sources check, new proposals, bulk count); blocking errors `role="alert"`; no repeat within 1 s. | e2e with injected delays and faults |
| A12 | Screen reader names for cells, row headers, graph nodes, wireframe boxes, badge triggers, icon buttons (ticket 09 gives each pattern). | e2e `getByRole` with exact names; SR |
| A13 | Grid semantics (`role="grid"`, `aria-rowcount`, `aria-rowindex`, `aria-selected`, `aria-multiselectable`); graph and wireframe have a full text alternative with the same selection. | e2e after scroll and filter |
| A14 | Each target at least 24 x 24 px or covered by the spacing exception. | kit `verify_target_size`; e2e bounding boxes |
| A15 | Reduced motion: no spin, slide, or fade; status text stays. | e2e with `reducedMotion: 'reduce'` |
| A16 | Errors are text, linked to the field, with the fix. | e2e (name clash, empty name, no property, bad pattern, bad connection text) |
| A17 | Each field has a visible label; disabled options show the reason as text. | axe plus e2e (`aria-describedby` not empty) |
| A18 | No page overflow from 1024 x 640 to 1440 x 900 (the supported window range). | e2e at 1024 x 640, 1280 x 900, 1440 x 900, both themes |
| A19 | Poll results do not move focus or change the list under the user. | e2e with `/__test__/agent-proposal` |
| A20 | No native `<select>`, no emoji, no em or en dash in copy. | CI lint; kit `lint_native_select`, `check_no_emoji` |
| A21 | Zoom 200% at 1440 x 900 (720 CSS px wide) keeps all content and each action reachable (WCAG 1.4.4). Side panes become sheets. Page-level horizontal scroll is permitted at this zoom. | e2e page zoom 2 on Compare, Impact, and Plan: each toolbar control, tab, and dialog button can get focus and shows in view after a scroll |
| A22 | No action needs a drag (WCAG 2.5.7). Graph pan and zoom have buttons (zoom in, zoom out, fit) and keys; the grid scrolls with keys and the wheel. | e2e: graph zoom and fit buttons work; each graph node can get focus with Tab |
| A23 | A toast stays at least 8 s, stays while the pointer is on it or it has focus, and has a close button. A toast never holds the only copy of a needed action or a blocking error (WCAG 2.2.1, 4.1.3). | e2e with a fake clock: the toast stays 8 s, and stays while hovered |
| A24 | The "/" key can be turned off (WCAG 2.1.4, section 9.3). | e2e: with the Settings switch off, "/" in the Compare tab does not move focus |

Stated limit: WCAG 1.4.10 (reflow to 320 CSS px) is not met. The app is a desktop app with a minimum window of 1024 x 640 (charting decision 5), and the compare grid is two-dimensional data, which 1.4.10 permits to scroll in two directions. A21 covers 1.4.4 at 200% zoom. Risk UR7 records this limit.

### 9.2 Focus return

| From | Action | Focus goes to |
|---|---|---|
| Grid cell | Enter | the pane h2 |
| Pane | Close or Escape | the grid cell that opened it |
| Pane | Previous row, Next row | the same button; the live region says the row name |
| Any dialog | Cancel, Escape, confirm | the trigger; if the trigger is gone, the new active grid cell |
| Apply dialog | success | the ResultPanel title (`tabindex="-1"`) |
| Bulk action | done | the first selected row cell, or the grid |
| `stale_revision` | refetch | the control that failed (it leaves its loading state) |
| Toast | any | the toast never takes focus by itself |

### 9.3 Keyboard shortcut map

Home tickets: 03 (grid keys), 09 (global rule), 11 (additions).

- Global: no global letter keys, no tab-switch keys, and no shortcut help dialog in version 1. "/" moves focus to the search field of the active tab (Compare "Search names", Impact "Find object or reason", Agent "Search target", Log "Search target", Sources rules search). "/" acts only when focus is not in a text field and no dialog is open. Escape closes the top overlay (menu, popover, tooltip, dialog, sheet), one at a time.
- "/" is a single-character key that acts outside the focused part, so WCAG 2.1.4 needs a way to turn it off. The app Settings get the switch "Use the / key to go to search" (on by default), stored in `localStorage` as the theme is. When it is off, "/" types a slash as usual. D and M need no switch, because they act only when focus is in the grid (2.1.4 exception).
- Controls with a key have `aria-keyshortcuts` and show the key in their tooltip: the search fields ("/"), "Set Merge Choice" ("M"), "Show code diff" ("D").

| Region | Keys |
|---|---|
| Tabs | Left, Right, Home, End (move and select) |
| Compare grid | Tab in and out (last focused cell); arrows (one cell); Home, End (row); Ctrl+Home, Ctrl+End (first, last row); Page Up, Page Down; Enter (row detail); Space (bulk checkbox); Shift+Space, Shift+Up, Shift+Down (range); Ctrl+A (loaded rows); D (code diff, focus in the grid only); M (Set Merge Choice, rows selected, focus in the grid only); Escape (clear the selection, then close the row detail) |
| Impact table | Tab between rows and controls; Space toggles the row checkbox; Enter on the name opens the pane |
| Impact graph | Tab in rank order; Right next step, Left previous step, Up and Down same rank; Enter or Space opens the item |
| Wireframe | Tab in reading order; Enter or Space opens the visual |
| Select | Enter, Space, Up, Down open; typeahead; Home, End; Enter selects; Escape closes |
| Combobox | type to filter; Down opens; Up, Down move; Enter selects; Escape closes, a second Escape clears |
| Menu | Enter, Space, Down open; arrows; Home, End; typeahead; Escape closes |
| SegmentedControl | toggle mode: Tab and Space; radio mode: arrows |
| Dialog | Tab cycles inside; Escape closes (not in progress mode) |

Measured on the ticket 03 prototype (Playwright): arrows, Space, Shift+Arrow, Escape, Enter, End, Ctrl+End, and D work. UNMEASURED: Tab out of the grid, the Radix parts, and screen reader output.

## 10. Data layer, errors, and refresh

Home ticket: 10.

- Code in `frontend/src/devcenter/`: `httpClient.js` (section 14.1 reads and the change request reads, each with an optional `signal`), `errors.js` (`DevCenterError`, `normalizeError` for the new and the old shape), `jsapi-methods.json` (method list with `short` or `long`), `jsapiClient.js` (one FIFO queue, `base_revision` from the store), `invalidation.js`, `store.js` (`useSyncExternalStore`, no state library), `poller.js`, `useDevCenter.js` (the only React module), `copy.js`, `mock/pywebviewShim.js` (test only).
- Revision: each call sends the last known revision. A read reply with a lower `revision` than the store is dropped and fetched again.
- `stale_revision`: no automatic retry. The store fetches `GET session` and the visible reads, shows `shared.stale`, and drops the queued calls with no second toast. The failed control leaves its loading state.
- Other codes: `session_not_open` shows the list with a banner; `source_changed` opens Compare with the marks filter (an accept shows the inline alert); `action_not_allowed`, `invalid_payload`, `not_found`, `user_choice_exists` show an inline error at the control; `network`, `unknown`, and HTTP 5xx show a region banner with "Try again", and the region keeps its old data marked not current. Agent submit codes show only in the Agent tab and the Log.
- Refresh: after each call, the reads in `INVALIDATES[method]` that are visible fetch at once; others become stale. Poll `GET session` every 5 s while a session is open, the window is visible, and no call runs; one poll on window focus. `GET apply/progress` every 500 ms only during `apply`, `format_only_apply`, `undo_apply`. No push from the backend.
- Busy: short calls queue, and only the changed control shows loading. Long calls (`session_create`, `session_open`, `sources_check`, `apply`, `format_only_apply`, `undo_apply`, `pull_to_local`, `cloud_connect`, `cloud_sign_in`, `merge_choice_bulk_set`, `proposal_accept_all`) disable each change control until the reply. HTTP reads abort on filter change, page change, or view close. JS API calls have no Cancel. While a long call runs, the work header shows a status line with a spinner, for example "Checking sources. Changes wait until this ends.", so that each disabled control has a visible reason.
- Fake server `tests/devcenter_ui_server.py` (port 8766): all reads, `POST /__test__/jsapi/<method>`, test controls (`scenario`, `fault`, `delay`, `agent-proposal`), scenarios `default`, `no-project`, `no-sessions`, `locked`, `newer-schema`, `damaged`, `sources-changed`, `source-missing`, `plan-invalid`, `apply-ready`, `large-5000-rows`. The shim and `/__test__` routes never go into `backend/api/app.py` or `backend/desktop/host.py`.
- Fixtures in `tests/fixtures/devcenter_ui/<scenario>/`: hand-written first, recorded from the merge lab in U12. Each fixture passes the contract test.
- CI `.github/workflows/ci.yml` (Windows runner, each push and pull request): Python `unittest` (with the contract test and `tests/test_theme_contrast.py`), `npm test`, `npm run build`, Playwright e2e with axe and the overflow check, and the lint test for `frontend/src/devcenter/**` (no native select, hex color, emoji, em or en dash, one-sided colored border).

## 11. Performance budgets

Home tickets: 03 (measured prototype), 10 (method), 11 (final values). These values replace the ticket 10 target "first 200 rows within 1.5 s".

Measured in e2e with `performance.mark` on the fake server, scenario `large-5000-rows` (5 sources, 5,000 rows; Impact: 5,000 items).

| ID | Item | Budget |
|---|---|---|
| P1 | Compare and Impact lists: first page reply to first rows painted | 300 ms or less |
| P2 | Filter change (user input) to new rows painted, fetch included | 500 ms or less |
| P3 | Wheel scroll and jump scroll (more than one view in each frame) | no long task over 50 ms |
| P4 | Row elements in the DOM | 80 or fewer |
| P5 | Graph (150 nodes): reply to layout and paint | 500 ms or less |
| P6 | Click to the loading state of the control (INP) | 100 ms or less (INP 200 ms or less) |
| P7 | Tab switch and side pane open with cached data | 200 ms or less |

- CI rule: each budget is the median of 5 runs. CI fails at 2 times the budget, because a CI runner is slow and noisy. U12 checks the real budget (1 times) on a development PC.
- Build rule for the grid (ticket 03): during a fast scroll (more than one view in each frame), render light rows (name and row state only) and fill the cells when the scroll stops. Keyed row reuse.
- Backend budgets stay in technical design R6 (compare under 10 s, plan and impact under 5 s). Above a budget the UI works and shows the elapsed time.

Prototype values (ticket 03, headless Chrome with software raster): P1 60 to 197 ms, P2 76 to 171 ms, wheel scroll 0 long tasks, P4 max 40. Jump scroll FAILED (11 to 44 long tasks, max 71 to 100 ms) before the light-row rule. All values in the built app: UNMEASURED until U4, U8, and U12.

## 12. Measurement status

| Area | Measured on prototypes (tickets 01 to 09) | Must be measured in the build |
|---|---|---|
| Page overflow | 0 px in 1,464 runs (tickets 02 to 08) | U3 to U11 e2e (A18) |
| axe | 0 violations on all prototype screens, both themes | U1 to U11 e2e (A1) |
| States | `verify_states` pass on the list, grid toolbar, row detail (44 snapshots), impact (32 pages), agent, plan, sources (62 snapshots), specimen | Each U-step with a screen (kit, section 13 rule) |
| Token contrast | ticket 01 table and ticket 09 61 pairs | U0 and U1 CI test |
| Target size | pass on the checked snapshots | Each U-step with a screen (kit) |
| Keyboard | grid keys (ticket 03) | U4, U8, U1 e2e |
| Focus trap and return | UNMEASURED (static markup) | U1 and each dialog U-step (A9, A10) |
| Screen reader output | UNMEASURED | U12 SR pass |
| Live region timing, reduced motion | UNMEASURED | U3 and later e2e (A11, A15) |
| Performance | prototype only, jump scroll failed | U4, U8, U12 |
| Struck title on the hatch | UNMEASURED | U12 (manual sample on a screenshot) |
| Copy against real MSAL, XMLA, and Fabric errors | UNMEASURED (risk R1) | Real-tenant checklist T1 |

A gate that prints SKIPPED is not a pass.

## 13. UI build steps

Each U-step ends with green automated tests in CI (section 10). All tests run offline on the fake server, with no Power BI Desktop and no cloud.

Rules for each U-step:

- A U-step that needs a schema waits for the backend S-step that creates it (map decision 6). "Depends on" names these S-steps.
- Each U-step adds its fixtures to `tests/fixtures/devcenter_ui/` and to the contract test, and its methods to `jsapi-methods.json` and `invalidation.js`.
- Each U-step that adds a screen runs the e2e checks A1 (axe, both themes), A18 (overflow at 1024 x 640, 1280 x 900, 1440 x 900), and the keyboard and focus specs of its parts.
- Each U-step that adds a screen also runs the kit gates `verify_states` (light and `--dark`), `verify_target_size`, `slop_tells --strict`, and `verify_focustrap` on a snapshot of that screen (inline CSS, as `.scratch/dev-center-ui/gates/snap.mjs` does). The build worker runs them through the kit `gate.mjs` wrapper with `DS_REQUIRE_BROWSER=1` (on Windows, with the fake `argv[1]` of the ticket 09 setup). The worker records the results in its build ticket file and in its commit message. There are no pull requests: commits only, no push. U12 runs the full sweep.
- After U1, the existing e2e suite must stay green, because U1 changes old screens.

UI lanes: U1 and U2 in parallel after U0. After U3: U4, U5, U7, and U11 in parallel, as their S-steps permit.

| Step | Depends on (U) | Depends on (S) |
|---|---|---|
| U0 Test harness and CI | none | none |
| U1 Shared fixes, tokens, parts | U0 | none |
| U2 Data layer and copy | U0 | none |
| U3 Shell, session list, create, work area frame, Sources and Target | U1, U2 | S2 |
| U4 Compare grid | U3 | S3 |
| U5 Naming rules | U3 | S4 |
| U6 Row detail and Merge Choice | U4 | S3, S4, S5 |
| U7 Plan view | U3 | S5 |
| U8 Impact views and removal policy | U6 | S6 |
| U9 Agent and Log | U6, U8 | S10 |
| U10 Apply, Undo, format only, change report | U7 | S9 |
| U11 Cloud sources and Pull to local | U3 | S11 |
| U12 Release checks | all | S3, S5, S6, S9 |

### U0. Test harness and CI

- Goal: the fake server, the shim, and CI exist before the first screen.
- Code areas: `tests/devcenter_ui_server.py`, `tests/fixtures/devcenter_ui/`, `frontend/src/devcenter/mock/pywebviewShim.js`, `frontend/vite.config.js` (plugin with `DEVCENTER_FAKE=1` and the proxy), `frontend/playwright.config.js` (second `webServer`, port 8766), `.github/workflows/ci.yml`, `frontend/test/devcenter-lint.test.js`, `tests/test_theme_contrast.py`.
- Depends on: nothing.
- Acceptance tests:
  - `GET /__test__/health` answers on port 8766. `POST /__test__/scenario` loads each scenario of section 10 and resets the state.
  - `POST /__test__/jsapi/<method>` with a wrong `base_revision` returns `stale_revision`. `fault`, `delay`, and `agent-proposal` change the next reply as stated.
  - The production `npm run build` output has no shim tag. The dev build with `DEVCENTER_FAKE=1` has it.
  - The lint test fails on test inputs with a native `<select>`, a hex color, an emoji, an em dash, and a one-sided colored border, and passes on `frontend/src/devcenter/**`.
  - `tests/test_theme_contrast.py` gives the ticket 01 values for the existing tokens (`line`, `line-strong`, `line-focus` are listed as decorative only).
  - The CI workflow runs the 5 gates on a Windows runner. The existing Python tests and e2e suite pass.
  - The S2 route list test ("no HTTP route changes session state") still passes, because it reads the real app only.

### U1. Shared fixes, tokens, parts

- Goal: the shared parts and tokens exist and pass their gates on a specimen.
- Code areas: `frontend/src/theme.css`, `frontend/src/devcenter/devcenter.css`, `frontend/src/components/ui/` (button, tabs, checkbox, and the new generic parts of section 6.1), a dev-only specimen route, `tests/test_theme_contrast.py`.
- Depends on: U0.
- Acceptance tests:
  - U-fix-1: the contrast test passes `--bad-ink` on `bad` and on `--bad-strong` at 4.5:1 or more in both themes. e2e axe on an old screen with a destructive button has no `color-contrast` violation.
  - U-fix-2: e2e axe on Graph has no `aria-valid-attr-value` violation. The active tab is a fill, not an underline (the ticket 08 prototype still shows an underline; this document wins). The existing e2e suite passes.
  - The contrast test passes each new pair of section 7.4 in both themes.
  - The specimen route (only with `DEVCENTER_FAKE=1`) renders each part in each of its states. e2e axe: 0 violations in both themes. Click test: checkbox, switch, radio, and segmented control change state.
  - e2e keyboard specs for Select, Combobox, Menu, SegmentedControl, Tabs, Dialog, and SidePane (A6, A9, A10).
  - Unit: StatusBadge refuses a tone with no label (A4).
  - Kit gates on the specimen snapshot (section 13 rule), recorded.

### U2. Data layer and copy

- Goal: the client modules and the copy catalog, tested without a browser.
- Code areas: `frontend/src/devcenter/` (`httpClient.js`, `errors.js`, `jsapi-methods.json`, `jsapiClient.js`, `invalidation.js`, `store.js`, `poller.js`, `useDevCenter.js`, `copy.js`), `frontend/test/devcenter*.test.js`, `tests/test_devcenter_ui_contract.py`.
- Depends on: U0.
- Acceptance tests:
  - Unit: URL and filter params, paging, error normalization (new shape, old shape, thrown error), queue order and revision handoff, drop of an old read reply, `stale_revision` drops the queued calls, each method has an invalidation entry, poll rules with a fake clock (visible, hidden, busy, focus).
  - Unit: each `copy.js` key has text; no em dash, en dash, emoji, ellipsis character, or "(s)".
  - Contract: `jsapi-methods.json` equals the section 14.2 list plus the change request calls of technical design section 14.4. The error shape fixture validates against its schema when S2 provides it.

### U3. Shell, session list, create flow, work area frame, Sources and Target

- Goal: the user can open, create, and close a session and see the work area frame.
- Code areas: `frontend/src/App.jsx` (sidebar item), `frontend/src/devcenter/screens/` (list, create, work area, sources), `frontend/e2e/devcenter-shell.spec.js`.
- Depends on: U1, U2; S2 (`GET sessions`, `GET session`, session and source JS API schemas, `revision` on reads).
- Acceptance tests:
  - e2e on `no-project`, `no-sessions`, `default`, `locked`, `newer-schema`, `damaged`, `sources-changed`, `source-missing`: each screen and banner of sections 4.1 and 4.2 with its copy.
  - Create flow: success opens Compare; a `fault` on `source_add` shows the partial failure and "Open session"; Cancel sends no JS API call.
  - The locked scenario disables each change control.
  - "Check sources" is a button at 1280 px and in "More" at 1279 px. The side pane is a 360 px column at 1280 px and a 400 px sheet at 1279 px.
  - Remove source: destructive confirm (text with no count, section 4.8), then the reply count in the toast.
  - The Settings switch "Use the / key to go to search" turns the "/" key off and on (A24).
  - `stale_revision` (injected) gives `shared.stale` and the refreshed view. A slow long call disables the change controls. A new revision from the poll updates the tab counts within 6 s.
  - A1, A8, A11, A15, A18 on these screens. Kit gates (section 13 rule).

### U4. Compare grid

- Goal: the N-way compare grid with filters, bulk actions, and code diff.
- Code areas: `frontend/src/devcenter/components/CompareGrid*`, `StateCell`, `BulkBar`, `CodeDiff`, `frontend/e2e/devcenter-compare.spec.js`.
- Depends on: U3; S3 (`GET compare-rows` with `q`, `total`, `state_counts`, `sort`, `row_state`; `GET compare-rows/{row}/diff`; `phrases.json`); S2 (`row_confirm` with a key list, `merge_choice_bulk_set`).
- Acceptance tests:
  - The full grid keyboard map of section 9.3 (e2e).
  - The default chip "State: not same"; each filter, search (debounce 150 ms), sort, and "Clear filters".
  - "Select all <N> rows" collects the keys by paging (max 5,000) and sends explicit keys. The bulk confirm shows only for remove or replace, with the counts. "Confirm <n> rows" only with the Marks filter.
  - Compare mode switch keeps the filters, clears the selection, keeps the active row.
  - Code diff opens from D and from the row detail link; Escape closes it; focus returns.
  - A13 attributes after a scroll and a filter change.
  - States: loading, later page, empty, error, no match.
  - Budgets P1 to P4 and P6 on `large-5000-rows`, with the light-row rule.
  - Kit gates (section 13 rule).

### U5. Naming rules

- Goal: the naming rules section and the rule editor.
- Code areas: `frontend/src/devcenter/screens/sources/NamingRules*`, `frontend/e2e/devcenter-rules.spec.js`.
- Depends on: U3; S4 (`GET naming-rules` with rule counts, rule JS API calls, duplicate refusal).
- Acceptance tests:
  - Status filter and its default; groups by object type; sticky actions.
  - Actions by status (ticket 07 table); "Confirm selected" calls in sequence and stops at a failure with the copy.
  - Add rule and Edit rule in the side pane; the backend error shows under the field (A16); the duplicate rule error shows "Edit that rule".
  - Delete user rule: destructive confirm, focus on Cancel.
  - "Copy rules from" lists the models with their counts; a model with 0 rules is disabled.
  - Empty, no target, detection running, and locked states.
  - Kit gates (section 13 rule).

### U6. Row detail and Merge Choice

- Goal: the row detail pane with all Merge Choices, names, folders, and alignment actions.
- Code areas: `frontend/src/devcenter/components/RowDetail*`, `NameField`, `ProposalCard` (display only until U9), `frontend/e2e/devcenter-row.spec.js`.
- Depends on: U4; S3 (`GET display-folders`, `alignment_override` break), S4 (`POST name-propose` with `candidate`), S5 (`merge_choice_set` with `promote` and `copy_to_report`, plan items for each row).
- Acceptance tests:
  - Enter opens the pane with focus on the h2; Close and Escape return focus (A10). Previous and Next follow the grid order and the filter.
  - Each choice of section 4.4 with its fields and its disabled reason (A17). Report measure rows show the two extra choices.
  - Save is immediate; the radio shows "Saving"; a second commit waits for the first.
  - Property picker: zero checked gives the error and no call.
  - Name check after 300 ms: rule break warning, clash error, "Use proposed name", empty required name error.
  - Display folder Combobox groups, new folder option, and the load failure fallback.
  - Split row (confirm, the choice is removed, the selection moves), Join with a row, Confirm and Reject rename.
  - Source mark "Confirm row"; many rows selected; read-only session.
  - Kit gates (section 13 rule).

### U7. Plan view

- Goal: the Plan tab without Apply.
- Code areas: `frontend/src/devcenter/screens/plan/`, `frontend/e2e/devcenter-plan.spec.js`.
- Depends on: U3; S5 (`GET plan`, `POST plan-validate`, cheap `GET session` with cached plan status, `choice_source_removed` items).
- Acceptance tests:
  - Strip states (Invalid, Valid with warnings, Valid, empty, checking) with their copy; header status button and Plan tab count agree with `GET plan`.
  - "Apply plan" is disabled with the visible reason when blocks exist (`aria-describedby`).
  - Block list order and each fix action opens the right tab and filter.
  - Summary counts, phases, "All | Model | Report", text filter, expand to operations with old and new text.
  - "Check plan" runs full mode and shows the time. Empty plan state. Proposals info line with "Open Agent".
  - Kit gates (section 13 rule).

### U8. Impact views and removal policy

- Goal: the Impact tab in all three views, Offers, completeness, and the removal policy dialog.
- Code areas: `frontend/src/devcenter/screens/impact/`, `ImpactItemRow`, `ImpactNode`, `WireframeBox`, `CompletenessStrip`, `PathStepList`, `RemovalPolicyDialog`, `frontend/src/graphLayout.js` (reuse only), `frontend/e2e/devcenter-impact.spec.js`.
- Depends on: U6; S6 (`GET impact` with filters, totals, and facets; `GET impact/{item}/paths`; `GET impact/removal/{object}`; `GET wireframe/{report}`; bulk `impact_action_apply`).
- Acceptance tests:
  - Scope, group, and view switches; the view switch keeps scope, filters, and selection.
  - Status rule and primary action order; row menu; pane actions; bulk "Include in rewrite" and "Add from donor"; the toast gives the blocking count.
  - Completeness strip default rule and "Show 20 more".
  - Graph: 150 nodes limit with "Open table"; Tab in rank order and arrow keys along edges; node names (A12); "Show as table" keeps the selection.
  - Wireframe: each status has pattern, icon, and word (A4); "Visual list" in reading order; Offer checkboxes.
  - Offers: page checkbox mixed state; Needs banner with "Open Needs".
  - "Include open proposals" switch and banner.
  - Removal policy dialog: Block, Cascade (destructive), Repoint (disabled until a candidate); focus rules (A9).
  - Budgets P1 to P5 on the 5,000-item scenario.
  - Kit gates (section 13 rule).

### U9. Agent and Log

- Goal: proposals, questions, accept flows, and the session log.
- Code areas: `frontend/src/devcenter/screens/agent/`, `screens/log/`, `ProposalCard`, `QuestionCard`, grid badge in `CompareGrid`, `frontend/e2e/devcenter-agent.spec.js`.
- Depends on: U6, U8; S10 (proposal fields in `GET session`, `proposal_accept`, `proposal_reject`, `proposal_accept_all`, `include_proposals=ready`, `question_answer`, `GET log` filters).
- Acceptance tests:
  - The first open question leads; "Answer" moves it to "Answered".
  - Proposals table filters, status values, and sticky actions; Accept, Replace with agent choice, Reject; "Accept selected" in sequence with the partial failure toast.
  - "Accept all" summary with the plan now and after, the skipped list, focus on Cancel.
  - Error copy for `user_choice_exists` and `source_changed`.
  - A proposal added through `/__test__/agent-proposal` shows the notice after the poll, and focus and the list stay the same (A19). "The agent replaced this proposal." in an open card.
  - Grid badge priority and tooltip; the row detail card on a marked row disables Accept.
  - Log filters, proposal chip, "Show more", empty value "None".
  - Kit gates (section 13 rule).

### U10. Apply, Undo, format only, change report

- Goal: the full apply flow of section 5.5 and 5.6.
- Code areas: `frontend/src/devcenter/screens/plan/Apply*`, `ProgressList`, `ResultPanel`, `frontend/e2e/devcenter-apply.spec.js`.
- Depends on: U7; S9 (`GET apply/preview` with blocks, `GET apply/progress`, `GET apply/last`, `apply`, `format_only_apply`, `undo_apply`, `change_report_write`, error `details.step` and `details.check`).
- Acceptance tests:
  - Preview blocks go to the block list and the dialog does not open.
  - The approval checkbox shows only with approval items and gates the confirm. "Apply plan" is destructive when the plan deletes objects (trigger and confirm).
  - Progress maps `step_index` to the list (poll 500 ms); fallback with elapsed time when the endpoint fails; no close and no Escape while it runs.
  - Success, differences, and failure panels with their copy; focus on the panel title; one sentence for each `details.check`.
  - Stale plan copy with "Check plan".
  - Undo: available only with a backup; refused with the file list when the target changed; progress and toast.
  - Format only: dialog, progress, result, automatic "Check plan".
  - Change report: save dialog default name, toast with "Show in folder", failure toast.
  - Desktop lines in the dialog and the banner after the apply.
  - Kit gates (section 13 rule).

### U11. Cloud sources and Pull to local

- Goal: the cloud connect dialog and the pull flow.
- Code areas: `frontend/src/devcenter/screens/sources/Cloud*`, `PullToLocal*`, `frontend/e2e/devcenter-cloud.spec.js`.
- Depends on: U3; S11 (`cloud_items_list`, `cloud_sign_in` with `prompt`, `cloud_connect` test lines, `pull_to_local`).
- Acceptance tests:
  - Each step and state of the dialog (ticket 07 table), with a silent token that skips step 1.
  - Sign-in failure copies (closed window, admin consent, no network, other).
  - Workspace with no XMLA capacity; disabled unsupported model with its reason; paste fallback with the bad connection error (A16).
  - Access type default "Read"; no line about a later change.
  - Test result groups "Checked" and "Not checked"; a cloud report that is not readable is not added.
  - In the create flow the dialog adds a draft item only (no call).
  - Pull: folder not empty disables "Pull model"; progress; success adds a local source (and selects it as target from the Target step); failure with "Try again".
  - Kit gates (section 13 rule).

### U12. Release checks

- Goal: the build meets this document on real engine data.
- Code areas: `tools/record_devcenter_ui_fixtures.py`, `tests/fixtures/devcenter_ui/`, `frontend/e2e/devcenter-a11y.spec.js`.
- Depends on: U0 to U11; S3, S5, S6, S9 (merge lab engine output).
- Acceptance tests:
  - Recorded `default` and `large-5000-rows` fixtures from the merge lab replace the hand files and pass the contract test.
  - A1 to A24 pass on each screen in both themes (`devcenter-a11y.spec.js` holds A1, A7, A11, A15, A18, A21, A22, A23).
  - SR pass with NVDA and Narrator on Compare, row detail, Impact graph and wireframe, Apply dialog; findings recorded.
  - Kit full sweep (`verify_states`, `verify_target_size`, `slop_tells --strict`, `verify_focustrap`, `verify_keyboard`, `lint_hardcodes`, `lint_intent`) on snapshots of each screen; results recorded.
  - Budgets P1 to P7 at 1 times on a development PC, including the jump scroll in the real app.
  - Each UNMEASURED item of section 12 is measured or listed with its reason.

## 14. Out of scope

| Item | Reason |
|---|---|
| Cloud write UI (XMLA deploy, Fabric `updateDefinition`, PBIX warning dialog) | Version 1.1 (technical design 10.4). |
| Later features of technical design 15.3 | Not version 1. |
| Migration of old screens from `NativeSelect` | Charting decision 4: a later task. |
| Graph `nested-interactive` and the Inspector light type chip (4.15:1) on old screens | Ticket 09 decision 6: a later task. The Development Center does not use these parts. |
| Phone layout | Charting decision 5: desktop app. |
| Session delete and rename | Ticket 02: no UI and no change request in version 1. |
| Free-text answers and dismiss of agent questions | Ticket 06: version 1 has options only. |
| "Undo anyway" and undo of an older apply | Ticket 08: only the last apply with a backup. |
| Cloud sign-out and access type change after the add | Ticket 07: no backend call in version 1. |
| Tab-switch keys and a shortcut help dialog | Ticket 11: no global letter keys in version 1. |
| URL routing for tabs and deep links | Ticket 02: tab state is in memory. |
| Grouping of compare rows by table | Ticket 03: columns sort in its place. |
| Backend data contracts | Technical design section 14. A UI need goes to section 14.4 as a change request. |

## 15. Open risks

| ID | Risk | Effect | Mitigation |
|---|---|---|---|
| UR1 | The jump scroll of the grid failed the 50 ms budget in the prototype. | The grid can stutter on a scroll bar drag. | Light rows during a fast scroll (section 11); measure in U4 and U12. |
| UR2 | The kit state gate drops alpha and the kit gates cannot run in CI. | A hover failure can pass CI. | Opaque `-tint` tokens; kit gates by hand in each U-step (section 13 rule). |
| UR3 | Two token pairs have little margin in light (4.79, 3.08). | A small theme change can fail AA. | The CI contrast test holds each pair. |
| UR4 | Copy for MSAL, XMLA, and Fabric errors has no real-tenant test. | Wrong text for a real error. | Real-tenant checklist T1 (technical design R1). |
| UR5 | CI timing on a shared runner is noisy. | Flaky budget failures. | Median of 5, CI limit at 2 times the budget, real budget in U12. |
| UR6 | The UI waits for 34 backend change requests. | A late change request delays its U-step. | Technical design 14.4 names the owner S-step of each; section 13 names the dependencies. |
| UR7 | WCAG 1.4.10 reflow is not met below 1024 CSS px (section 9.1, stated limit). | A user who needs 400% zoom must scroll in two directions. | Desktop scope (charting decision 5); A21 holds 1.4.4 at 200%; a later layout task can lower the minimum width. |

## 16. Home tickets

| Area | Ticket |
|---|---|
| Render gates and baseline values | `.scratch/dev-center-ui/issues/01-render-gates.md` |
| Shell, session list, create flow, responsive rule | `.scratch/dev-center-ui/issues/02-shell-and-session-flow.md` |
| Compare grid, grid keys, prototype budgets | `.scratch/dev-center-ui/issues/03-compare-grid.md` |
| Row detail and Merge Choice | `.scratch/dev-center-ui/issues/04-row-detail-and-merge-choice.md` |
| Impact views | `.scratch/dev-center-ui/issues/05-impact-views.md` |
| Agent proposals, questions, Log | `.scratch/dev-center-ui/issues/06-agent-proposals-and-log.md` |
| Sources, cloud connect, naming rules | `.scratch/dev-center-ui/issues/07-sources-connect-naming.md` |
| Plan, Apply, Undo, format only | `.scratch/dev-center-ui/issues/08-plan-apply-undo.md` |
| Components, tokens, copy catalog, a11y contract | `.scratch/dev-center-ui/issues/09-components-tokens-copy-a11y.md` |
| Data layer, fake server, tests, CI | `.scratch/dev-center-ui/issues/10-data-layer-and-tests.md` |
| This document, budgets, shortcut map, U-steps | `.scratch/dev-center-ui/issues/11-ui-design-doc-and-build-steps.md` |

Prototypes (never shipped): `.scratch/dev-center-ui/prototypes/<ticket>/`. Screenshots are not in git (`*.png` in `.gitignore`); each prototype has `measure.mjs shots` to make them again.
