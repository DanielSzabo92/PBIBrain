# How does the user review the plan, apply it, and undo it?

Type: grilling
Status: resolved
Blocked by: 02

## Question

Design the plan view, the Apply dialog, the apply progress, the result after verify, undo, the "format only" apply, and the change report.

## Context

- Apply sequence: technical design section 13 (12 steps). The dialog data is `GET apply/preview`: summary, approvals needed (HIGH and CRITICAL items, "not checked" items), Desktop status. One approval records all approval purposes.
- Plan: `GET plan` (status Invalid / Valid with warnings / Valid, summary counts for each object type and for model and report, plan steps with their operations, blocking items, warnings, plan hash). `POST plan-validate` with `quick` or `full` mode.
- Blocks before the dialog: unconfirmed source marks, plan Invalid, Desktop open with unsaved changes, non-canonical target file (offers "format only" apply: `format_only_apply`).
- Warnings: Desktop open and saved (after apply, tell the user to select "Apply external changes" in Power BI Desktop), Desktop bridge not reachable ("could not check").
- After apply: rescan and compare with the plan, report each difference. Undo: `undo_apply` restores all files from the backup. `change_report_write` writes a Markdown report. The app never commits or pushes.
- Apply uses accepted state only. Open agent proposals have no effect (ADR 0003).
- Existing screen to compare with: `frontend/src/components/GuardReview.jsx`.
- Destructive actions (Apply that deletes, Undo) wear the destructive token in the trigger and in the confirm dialog.
- Skills: `design-doctrine`, `design-screen`, `ux-writing`.

## Done when

The answer gives: the plan view layout, the pre-apply block list and how each block leads to its fix, the Apply dialog content and its one approval control, the progress view for the 12 steps, the result view (success, verify differences, failure with "nothing written"), the undo flow, the format-only flow, the change report action, and the copy for each state.

## Answer

Resolved on 2026-10-31. The orchestrator accepted all 16 recommendations of round 1 (one round), with one change to Q8 (the progress source, see "Backend change requests"). Prototype: `.scratch/dev-center-ui/prototypes/08/` (`index.html`, `light.html` for the light state gate, `tokens.css` copied from 02, `measure.mjs`, screenshots in `shots/`). Open with `index.html?screen=<id>&theme=dark|light`. The prototype is never shipped.

### Brief Inference

- Domain: dev-tool (Power BI model merge). Audience: expert BI developer. Tone: calm, utilitarian. The apply is the highest-stakes moment of the session, so the copy is plainer here than elsewhere.
- Mood: precise and safe. The user must see what changes, what is at risk, and how to go back.
- Motion depth: subtle feedback only (spinner on the running step).
- Layout family: status strip, then the block list, then a two-column body (summary and warnings left, plan steps right), then the proposals line. Result panels go above the strip.
- One thing leads: the status strip with "Apply plan". The status text is 18 px, the h1 is 28 px.
- Reference anchor: the shell of ticket 02. No new tokens: the destructive token is the existing `bad` token.

### Decisions of round 1 (all accepted)

1. Plan tab layout: one column (strip, block list, summary, plan steps, warnings). No side pane.
2. Quick validation runs automatically after each state change. "Check plan" runs `plan-validate` full mode and shows the time of the last full check. Apply runs full mode again.
3. With blocks, "Apply plan" is disabled with a visible reason ("Fix 5 items before you apply."), linked with `aria-describedby`.
4. "Apply plan" first calls `GET apply/preview` (loading state "Checking before apply"). Blocks in the reply go to the block list, and the dialog does not open. Change request: the preview returns the blocks.
5. Each block has one fix action (table below).
6. One approval checkbox, only when HIGH, CRITICAL, or "not checked" items exist. No type-to-confirm, because Undo restores the files.
7. Destructive token on "Apply plan" (trigger and dialog) when the plan deletes 1 or more objects. Undo always wears the destructive token.
8. Progress in the dialog. The user cannot close it while it runs. Source: `GET /api/devcenter/apply/progress`, polled every 500 ms. Fallback: "Applying plan" plus the elapsed time.
9. Result panel at the top of the Plan tab: success, differences, failure ("Nothing was written").
10. Undo for the last apply of the session only, while its backup exists. Refused when the target files changed after the apply. Change request: a read for the last apply.
11. Format-only flow: own dialog (brand button), the same progress and result pattern, undo works, then the plan is checked again.
12. "Write change report": native save dialog, default folder the project root, default name "<session name> change report <date>.md", toast with "Show in folder".
13. Desktop open and saved: warn line in the dialog, then a warn banner after the apply until the user closes it. "Could not check Power BI Desktop" is a dialog line only.
14. Plan steps: plan order with phase headings, "All | Model | Report" filter, text filter, expand to operations, exact old and new text for rewrites, scroll inside the list.
15. Open agent proposals: one info line with "Open Agent". No preview switch in version 1.
16. The dialog binds the plan hash. `stale_revision` from `apply` shows "The plan changed after you opened this dialog. Check it again." with "Check plan".

### Plan view layout

Screens: `ready`, `blocked`, `checking`. Screenshots `shots/<screen>-<theme>-<1440|1024>.png`.

```
| Development Center > Sales master merge > Plan                                   |
| Sales master merge (h1)            [! Valid with 2 warnings] [Check sources] [...] |
| Compare | Impact | Plan (2) | Agent (4) | Sources | Log                          |
| +------------------------------------------------------------------------------+ |
| | ! Valid with 2 warnings (18 px)        Fix 5 items before you apply.          | |
| | 41 plan steps, 2 warnings. Full check 10:58.     [Check plan] [-> Apply plan] | |
| +------------------------------------------------------------------------------+ |
| | Before you apply                               5 items stop the apply        | |   (only with blocks)
| |  ! 14 rows changed in their source ...                    [Show these rows]  | |
| |  x [Net Margin] uses [Gross Profit] ...                   [Show impact]      | |
| +------------------------------------------------------------------------------+ |
| +-- Summary ---------------------+ +-- Plan steps ---- [All|Model|Report] [Filter] + |
| | Object type  Cre Del Mod Ren   | | Deletes (4)                                  | |
| | Model                          | |  > [Gross Profit] Measure       1 operation  | |
| |  Table        1   0   2   0    | | Renames (3)                                  | |
| |  Measure      9   2   5   2    | |  v [Sales Amt] to [Total Sales]  4 operations | |
| | Report                         | |    RENAME ...                                | |
| |  Visual       5   1   0   0    | |    REWRITE_EXPRESSION [Net Margin]           | |
| +--------------------------------+ |    - DIVIDE([Sales Amt] ...)                 | |
| +-- Warnings --------------------+ |    + DIVIDE([Total Sales] ...)               | |
| | ! [Budget Variance] needs ...  | |  (scrolls inside, max 440 px)                | |
| +--------------------------------+ +----------------------------------------------+ |
| i This plan uses accepted choices only. 4 agent proposals are open ... [Open Agent] |
```

- At 1280 px and wider the body has two columns (5fr and 7fr). Below 1280 px it is one column: summary, warnings, then plan steps.
- The summary counts plan steps, not operations (technical design 6.1). Delete counts show in the `bad` color and with bold weight; zero shows in `text-3`.
- Phases in the step list follow technical design 6.3: Deletes, Renames, Creates, Changes, Expression rewrites, Report changes.
- The Plan tab count is the number of blocking items in the plan (bad tint), from `GET plan`.
- When the plan has no steps: empty state "Nothing to apply" in place of the summary and steps, and "Apply plan" is disabled with the reason "Nothing to apply.".
- A locked session (ticket 02) disables "Check plan", "Apply plan", Undo, and "Format files first".

### Pre-apply block list and the fix for each block

The list combines the blocks of `GET plan` (blocking items) and of `GET apply/preview` (marks, Desktop, files). Order: source marks, plan blocking items, Desktop, non-canonical files. Each line has an icon, a text, a sub-line with the fix, and one action.

| Block | Text | Sub-line | Action and effect |
|---|---|---|---|
| Unconfirmed source marks (step 1) | "14 rows changed in their source, and you did not confirm them." | "Examine each row, then confirm its Merge Choice." | "Show these rows": Compare tab with the marks filter (ticket 03). |
| Plan blocking item: Breaks or removal | "[Net Margin] uses [Gross Profit], which this plan deletes." | "Blocking. Set a removal policy for [Gross Profit], or keep it." | "Show impact": Impact tab on that object (ticket 05). |
| Plan blocking item: name clash or Need | "Name clash: Customer[Region] exists in Sales A and in Sales B." | "Blocking. Give a new name or select "Keep target"." | "Show row": Compare tab with that row selected (ticket 04). |
| Desktop unsaved changes (step 3) | "Power BI Desktop has unsaved changes in Sales Master." | "Save or close the target in Power BI Desktop. Then check again." | "Check again": calls `GET apply/preview` again. |
| Non-canonical target files (step 4) | "3 target files are not in the Power BI Desktop format." | "The app must format them first. The model does not change." plus the file list | "Format files first": opens the format-only dialog. |
| Full validation failure (step 5) | The failed check, for example "DAX parse error in [Net Margin]: ..." | "Blocking. Fix the expression in its source, or change the Merge Choice." | "Show row". |

Which plan items go to Impact and which go to Compare depends on the blocking item kind in `GET plan`. Ticket 09 fixes the exact kind-to-action map against the section 14 schema.

### Apply dialog and its one approval control

Screens: `dialog`, `dialog-unchecked`, `stale`. Modal, `role="dialog"`, `aria-modal`, title and text linked. Width `min(600px, 100%)`, height `calc(100vh - 32px)` maximum; the body scrolls, the footer stays visible (measured, see below).

```
Apply the plan to Sales Master?
The app writes the model and report files together, or writes nothing. You can undo the full apply.
[27 Created] [4 Deleted] [25 Modified] [3 Renamed]
! Deletes 4 objects: 2 measures, 1 column, 1 visual.          (only with deletes, bad color)
Needs your approval (3)                                         (only with approvals)
  [! Critical]    Delete [Gross Profit]
                  2 report visuals outside the target report use it.
  [! High]        Rename [Sales Amt] to [Total Sales]
  [i Not checked] Bookmarks on Overview
! Power BI Desktop has the target open. After the apply, select "Apply external changes" in Power BI Desktop.
[ ] I examined the high-risk and not-checked items. I approve them.
                                              [Cancel] [-> Apply plan]
```

- Data: `GET apply/preview` (summary, approvals needed, not-checked items, Desktop status) and the plan hash.
- The checkbox is the only approval control. One selection records all approval purposes (technical design section 8). The confirm button is disabled until the user selects it. With no approval items, the dialog has no checkbox and the confirm button is enabled.
- Confirm button: "Apply plan". It wears the destructive token when the plan deletes 1 or more objects, else brand primary. The trigger in the strip uses the same rule.
- Desktop lines: open and saved: "Power BI Desktop has the target open. After the apply, select "Apply external changes" in Power BI Desktop." Bridge not reachable: "Could not check Power BI Desktop. Save and close the target in Power BI Desktop before you apply."
- Severity badges use icon plus text: Critical (`bad`), High (`warn`), Not checked (plain).
- Initial focus: the checkbox when it exists, else "Cancel". Escape and "Cancel" close the dialog and change nothing.
- Stale plan: if `apply` returns `stale_revision`, the dialog body shows "The plan changed after you opened this dialog. Check it again." The footer has "Cancel" and "Check plan" (runs full check, closes the dialog).

### Progress view for the 12 steps

Screens: `progress`, `progress-fallback`. The confirm changes the dialog content into a progress list. The dialog has no close button and ignores Escape while it runs.

```
Applying the plan
Do not close PBIBrain. If a step fails, the app writes nothing.
Checks
  ok Sources are the same as at the last check        (step 1)
  ok Plan is valid                                    (step 2)
  ok Power BI Desktop has no unsaved changes          (step 3)
  ok Target files are in the Power BI Desktop format  (step 4)
  ok Full check passed                                (step 5)
  ok You approved 3 items                             (step 6)
Write
  ok Write a candidate copy                           (step 7)
  .. Guard check                                      (step 8, running)
  o  Write the files                                  (step 9)
  o  Rescan and compare                               (step 10)
  o  Save the new fingerprints                        (step 11)
                                  Step 8 of 11. 0:09 elapsed.
```

- Steps 1 to 6 are done before the dialog, so they show as done. Step 12 (change report) is not in the list: it is the "Write change report" action after the result.
- The UI polls `GET /api/devcenter/apply/progress` every 500 ms while `apply` runs. It maps `step_index` and `step` to the list and shows "Step <step_index> of <step_count>". The list is `aria-live="polite"`.
- Fallback when the progress endpoint is not available: one line "Applying plan. 0:14 elapsed." with a spinner.
- No Cancel. Reason: after step 9 starts, a stop can leave a half state; the steps before it are short.
- The format-only apply and the undo use the same dialog with their own step names (format: Write a candidate copy, Guard check, Write the files, Rescan and compare; undo: Restore the files, Rescan, Save the fingerprints).

### Result view

Screens: `success`, `diff`, `fail`. The dialog closes. The result panel shows above the strip until the user closes it or applies again. Full hairline border, icon plus text; no one-sided bar.

| Result | Look | Copy | Actions |
|---|---|---|---|
| Success | `ok` icon, `role="status"` | "Plan applied" / "The target matches the plan. 41 plan steps, 26 files written at 11:06. A backup is kept for undo." | "Write change report" (primary), "Undo apply" (destructive outline), close |
| Verify differences | `warn` icon, `role="status"`, table Object / Expected / Found | "Plan applied with 2 differences" / "The rescan of the target does not match the plan in 2 places. Examine them. If they are not correct, undo the apply." | "Undo apply" (destructive, first), "Write change report", close |
| Failure | `bad` icon, `role="alert"` | "Nothing was written" / "The <step> stopped the apply. <reason>. Your target files are the same as before." / "Failed step: <step>. Run "Check plan", then apply again. If it fails again, open the Log tab and copy the details." | "Check plan", "Open Log", close |

- After success, the plan derives again from the session. With no differences, the plan is empty ("Nothing to apply"), and the header status is "Valid". With differences, the plan shows only the steps that still differ (the prototype still shows the full old plan under the `diff` panel; this is a prototype short cut).
- Desktop banner after an apply to an open target: "In Power BI Desktop, select "Apply external changes" to load the new files." It stays in the work area banner stack (after the ticket 02 banners) until the user closes it.
- Failure reasons come from the error shape `{error: {code, message, details}}`. Ticket 09 writes one sentence for each guard failure code. No codes or stack text in the panel; the Log tab keeps the details.

### Undo flow

Screens: `undo`, `undo-refused`.

1. "Undo apply" shows in the result panel and in the Plan tab "More" menu while the last apply has a backup (from the last-apply read, see change requests).
2. The click opens the confirm dialog: "Undo the apply of 11:06?" / "The app restores all 26 target files from the backup. The Merge Choices stay in the session, so the plan shows the same steps again." Desktop line when the target is open: "Power BI Desktop has the target open. After the undo, select "Apply external changes" in Power BI Desktop." Buttons: "Cancel", "Undo apply" (destructive). Initial focus: "Cancel".
3. "Undo apply" calls `undo_apply` and shows the progress dialog (undo steps).
4. Success: toast "Apply undone. The target files are the same as before 11:06." The result panel closes, the plan derives again, and Undo goes away.
5. Refused (target files changed after the apply): the dialog does not run. The panel shows "Cannot undo this apply" / "2 target files changed after the apply. An undo would remove those changes. Undo them by hand, or keep the current files." plus the file list. No "Undo anyway" in version 1.
6. Undo failure: "Undo stopped. Nothing was restored." plus the reason and "Open Log".

Undo applies only to the last apply of this session. A second apply replaces the undo target.

### Format-only flow

Screen: `format`.

1. The block "3 target files are not in the Power BI Desktop format." has "Format files first".
2. The dialog: "Format 3 target files?" / "Rewrites 3 files in the Power BI Desktop format. The model does not change. The guard stops the write if it finds a model change. You can undo it." File list in code type. Note: "Comments and hand-made line order in these files go away." Buttons: "Cancel", "Format files" (brand primary, not destructive: no object is deleted).
3. "Format files" calls `format_only_apply` and shows the progress dialog (format steps).
4. Success: result panel "Files formatted" / "3 files are now in the Power BI Desktop format. The model did not change." with "Undo format" (destructive outline). Then the app runs "Check plan" (full) automatically, and the block goes away.
5. Failure: "Nothing was written" / "The guard found a model change in the formatted files, so it stopped the write." with "Open Log".

### Change report action

Screen: `report`.

- "Write change report" is in the success and difference panels and in the Plan tab "More" menu after an apply.
- The click opens the native save dialog. Default folder: the project root. Default name: "<session name> change report <yyyy-mm-dd>.md". Then the UI calls `change_report_write` with the path.
- Success: toast "Change report saved" with "Show in folder".
- Failure: toast "Could not save the change report. <reason>. Select a different folder and try again."
- The app never commits or pushes. The panel copy does not offer Git actions.

### Copy for each state (summary list)

| State | Copy |
|---|---|
| Strip, Invalid | "Plan not valid: 2 blocking" / "2 blocking items in the plan. Full check 10:42." / "Fix 5 items before you apply." |
| Strip, Valid with warnings | "Valid with 2 warnings" / "41 plan steps, 2 warnings. Full check 10:58." |
| Strip, Valid | "Valid" / "41 plan steps. Full check 10:58." |
| Strip, empty | "Valid" / "The target matches your Merge Choices. Full check 11:07." / "Nothing to apply." |
| Strip, check running | "Check plan" in loading state: "Checking plan" |
| Apply preview running | "Checking before apply" |
| Empty plan | "Nothing to apply" / "The target matches your Merge Choices. Change a Merge Choice in Compare to build a new plan." / "Open Compare" |
| Proposals line | "This plan uses accepted choices only. 4 agent proposals are open and are not in it." / "Open Agent" |
| Dialog | see "Apply dialog" |
| Progress | "Applying the plan" / "Do not close PBIBrain. If a step fails, the app writes nothing." |
| Results, undo, format, report | see the sections above |
| Desktop after apply | "In Power BI Desktop, select "Apply external changes" to load the new files." |
| Stale | "The plan changed after you opened this dialog. Check it again." / "Check plan" |

All copy passed the kit `check_no_emoji.py` (no emoji, no em dash or en dash). Buttons start with a verb and name the object ("Apply plan", "Undo apply", "Format files", "Write change report").

### Comparison with `GuardReview.jsx`

The old screen puts the decision at the end of 7 cards and uses "Accept changes" for approval. The Plan tab puts the action first, shows only the risk items in the dialog, and uses one checkbox. The old screen has "Loading" text with an ellipsis character and arrow characters in data lines; the new copy uses neither.

### Measurements (2026-10-31, Chrome 156.0.8078.49, playwright 1.63.0, axe-core 4.10.2)

- Page overflow (`measure.mjs`): 15 screens x 6 sizes (1024 x 640, then 1152, 1279, 1280, 1366, 1440 at 900 high) x 2 themes = 180 measurements. Page-level horizontal overflow 0 px and 0 elements past the right edge outside a scroll container, on all 180.
- Dialog fit: 84 dialog measurements. The dialog stays fully in view on all 84, also at 1024 x 640. The footer stays in view on all 72 dialogs that have a footer (the progress fallback has no footer by design; the script counted those 12 as "fails" because the footer value is null).
- axe (the rule tags of ticket 01), 15 screens at 1440 x 900, dark and light: 0 violations on all 30.
- Kit `verify_states.mjs` (default, hover, focus) on the `ready` screen, run through the gate wrapper with `DS_REQUIRE_BROWSER=1`: 101 element-states, pass in dark (`index.html`) and in light (`light.html`, the same page with light as the default theme). The first run failed 3 states: the header status button "Valid with 2 warnings" at 1.00:1. Cause: the gate reads the soft tint background without its alpha (the ticket 01 gate error). Fix: the header status button uses an opaque tint (`--ok-soft-solid`, `--warn-soft-solid`, `--bad-soft-solid`: the soft token composited over `bg` with `color-mix`, one value for each theme). The rendered colors stay the same. Measured in the live page, text on the tint: dark 8.89 (warn), 6.45 (bad), 8.36 (ok); light 5.19, 4.79, 4.88. All pass 4.5:1. Input for ticket 09: a status badge that is a button needs an opaque tint token in `theme.css`, so that the state gate can measure it.
- Kit `verify_target_size.mjs` on `ready`: 69 targets, all at least 24 x 24. Pass.
- Kit `slop_tells.mjs` on `ready`: no HIGH tells. LOW: two near-same neutrals `rgb(14,15,19)` and `rgb(15,16,20)` (`bg` and `bg-sidebar` of the existing theme, the same finding as ticket 01).
- Kit `check_no_emoji.py`: pass.
- Raw results: `prototypes/08/shots/result.json`. Screenshots: dark and light at 1440 and 1024 for each screen. The repo `.gitignore` excludes `*.png`; run `node measure.mjs shots` in `prototypes/08/` to make them again.

UNMEASURED: states, target size, and slop tells on the screens other than `ready`, and target size and slop tells on `ready` in light (the kit gates take a file path, not a query string). Focus trap and initial focus of the real Radix Dialog (the prototype is static markup). The destructive fill `text-inverse` on `bad` was not measured by a token gate; axe found no contrast failure on the "Apply plan" and "Undo apply" buttons in both themes, which covers the rendered pairs.

### Backend change requests

1. `GET /api/devcenter/apply/preview`: add the blocks. Fields: unconfirmed mark count (and the row keys or a filter token), Desktop state (`not_open`, `open_saved`, `open_unsaved`, `not_reachable`), non-canonical file list (paths relative to the target root), full validation result (status and failed checks with object and message), plan hash. Reason: the UI must show the step 1 to 5 blocks before the dialog (Q4).
2. `GET /api/devcenter/apply/progress`: fields `apply_id`, `step`, `step_index`, `step_count`, `state`. The UI polls it every 500 ms while `apply`, `format_only_apply`, or `undo_apply` runs. Reason: live progress list (Q8). Fallback: "Applying plan" plus elapsed time.
3. `GET /api/devcenter/apply/last`: fields `apply_id`, kind (`apply`, `format_only`), finished time (UTC), file count, backup present (bool), target changed since apply (bool) and the changed file list, differences from the rescan (object, expected, found). Reason: Undo availability and refusal, and the result panel after the session opens again (Q10).

### Inputs for later tickets

- 03: support a "Show row" deep link (row key) and the marks filter from the block list.
- 05: support a "Show impact" deep link (object ID).
- 06: the Log tab receives the apply, undo, and format entries; "Open Log" from a failure selects the last entry.
- 09: new parts: Dialog with a non-closable progress mode, progress list, result panel, destructive and destructive-outline button variants on `bad`, severity badge (Critical, High, Not checked). Exact copy for each guard failure code and each blocking item kind. Measure `text-inverse` on `bad` in both themes.
- 10: the poll loop for `apply/progress`, the mocks for the three endpoints above, and fixtures for each result state.
