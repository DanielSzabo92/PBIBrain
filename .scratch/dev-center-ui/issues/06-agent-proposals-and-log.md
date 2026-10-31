# How does the user see, accept, and reject agent proposals and answer agent questions?

Type: grilling
Status: resolved
Blocked by: 02

## Question

Design how agent proposals and agent questions show in the work area, how the user accepts, rejects, or accepts all, how the user answers a question, and how the user reads the session log.

## Context

- ADR 0003 and learnings: accept, reject, accept all, and answer go only through the JS API (`proposal_accept`, `proposal_reject`, `proposal_accept_all`, `question_answer`). The agent never applies.
- Proposal kinds (technical design section 12): `merge_choice`, `alignment`, `removal_policy`, `impact_action`, `need_mapping`, `name`. Each has confidence (0.9 or higher) and a reason. A proposal shows as "proposed by agent" until the user acts. A marked row gives `source_changed` on a proposal.
- Questions: target, text, 2 to 5 options (each with an optional proposal payload), recommended option, reason.
- `include_proposals`: plan and impact can show the effect with or without open proposals. Decide where the user switches this.
- Log (`GET log`): time, author (user or agent), MCP client name, action, target, before and after, reason, proposal ID.
- Error codes to show in plain words: `stale_revision`, `user_choice_exists`, `source_changed`.
- "Accept all" needs a summary before it acts. Decide what the summary shows.
- The UI gets no push from the backend in version 1. Decide how new proposals appear (refresh action, poll, or both) together with ticket 10.
- Skills: `design-doctrine`, `ux-writing`.

## Done when

The answer gives: the proposal mark on a row and in the row detail, the proposals list and its filters, the accept all flow with its summary, the question card, the log view, the copy for each error code, and how new proposals appear.

## Answer

Resolved on 2026-10-31. Round 1 had 14 questions. The orchestrator accepted all 14, with these changes:
- Q2: the grid cell shows only the badge. The proposed choice is in the tooltip.
- Q12: the UI does not retry after `stale_revision`. It uses the shared toast of ticket 10.
- Q6 and Q9: the technical design sections 12 and 14 do not state this behavior, so backend change requests follow.

Prototype: `.scratch/dev-center-ui/prototypes/06/` (`index.html`, `light.html` for the light state gate, `tokens.css`, `measure.mjs`, `status_contrast.mjs`, screenshots in `shots/`). The prototype is never shipped. The repo `.gitignore` excludes `*.png`. To make the screenshots again, run `node measure.mjs shots` in `prototypes/06/`.

### Brief Inference

- Domain: dev-tool (Power BI model merge).
- Audience and tone: expert BI developer who examines the work of an agent. The tone is calm and exact, not urgent.
- Mood: trustworthy. The user must always see what the agent wants, why, and what the user already chose.
- Motion depth: subtle feedback only.
- Layout family: the work area of ticket 02. The Agent tab has a question stack first (one thing leads), then a dense table.
- Reference anchor: the existing PBIBrain Review queue (Approve and Reject in a dense list).

### Decisions

1. The Agent tab is the main place for proposals and questions. Compare rows and the row detail also show proposals. Accept and Reject are in the Agent tab and in the row detail. They are never in the grid row.
2. Grid cell: one badge in the Merge Choice cell. The badge has the "bot" icon and the text "Proposed". The proposed choice shows only in the tooltip, for example "Agent proposes: Keep from Sales B". The real Merge Choice text does not change. The cell shows a maximum of one badge, because ticket 03 fixes the row height at 36 px. The priority is: "Confirm row first" (warn, alert icon), then "Question" (proposal tint, message icon), then "Proposed". When the cell shows "Confirm row first" and the row has a proposal, the tooltip also gives the proposal.
3. Row detail card: ticket 04 uses this specification at the top of the pane. See "Proposal mark" below.
4. Proposals list: one dense table with filters for Kind and Status, and a text search. See below.
5. A check box is on each row that is ready to accept. The buttons are "Accept selected (N)" and "Accept all". "Accept selected" calls `proposal_accept` for each item in sequence.
6. "Accept all" acts on all open proposals that are ready to accept, not on the filter. It skips blocked proposals and lists them as skipped.
7. A summary dialog shows before "Accept all" acts. See below.
8. Reject is one click, with no confirm and no reason field. The log records it. A rejected proposal does not come back. The agent can submit a new one.
9. When the row has a user Merge Choice, the accept is the user's own act. The card shows "Your choice" and the agent change together. The button text is "Replace with agent choice".
10. Question cards are above the proposals list. See below.
11. A switch "Include open proposals" is in the Plan and Impact toolbars. It is off by default. When it is on, an info banner shows.
12. Error copy: see the table below. After `stale_revision` the UI gets the data again and shows the shared toast. It does not retry automatically.
13. New proposals: the UI polls the session revision and shows a notice. The list on screen does not change by itself.
14. Log tab: one table, filters, and "Show more" paging.

### Proposal mark on a row and in the row detail

Grid (prototype screen `compare-card`):

```
| Object            | ... | Merge Choice                                |
| [Total Sales]     | ... | Not set  [msg Question]                     |
| [Net Margin]      | ... | Not set  [bot Proposed]  tooltip: "Agent proposes: Keep from Sales B" |
| [YoY %]           | ... | Keep from Sales A  [! Confirm row first]    |
| Product[Category] | ... | Keep from Sales A  [bot Proposed]           |
```

- The badge is focusable (`tabindex="0"`). The tooltip opens on focus and on hover. The badge uses the new tokens `proposal` and `proposal-soft`.
- Filter support for ticket 03: the compare-rows filter needs "Has proposal" and "Has question". The data is already in `GET compare-rows` (proposal status).

Row detail card (prototype screens `compare-card`, `compare-conflict`, `compare-source`):

```
+ [bot Proposed by agent]  Cursor, today 10:33 -----------+
| Keep from Finance (cloud)                (15px, 500)    |
| Your choice   Keep from Sales A   (only if one is set)  |
| Confidence    90%                                       |
| Reason        Finance has the full category list.       |
| [Replace with agent choice] (primary)  [Reject]         |
+---------------------------------------------------------+
```

- The card has a full hairline border (`line-strong`) on `surface-2`. It has no one-sided bar.
- The change is in plain words from the payload summary (backend change request 2). Examples by kind:
  - `merge_choice`: "Keep from Sales B".
  - `name`: "Rename to Net Amount".
  - `alignment`: "Match as one row".
  - `removal_policy`: "Repoint to Customer[Region]".
  - `need_mapping`: "Map to Date in Sales Master".
  - `impact_action`: the action label of the Impact item.
- The confidence shows as a whole percent (0.96 shows as "96%").
- A row with an unconfirmed source mark shows this note in the card: "A source of this row changed after the agent made this proposal. Confirm the row first, then accept or reject the proposal." The card also shows "Confirm row" (`row_confirm`). Accept is disabled. Reject stays available.
- When the row has an open question, the row detail shows the question card (below) in the same place.

### Proposals list and filters (prototype screens `agent`, `agent-selected`, `agent-empty`)

```
| Questions (2)                                     Last check 10:44 [Refresh] |
|   [question card]                                                            |
|   1 more open question. Show it                                              |
|   > Answered (3)                                                             |
| Proposals (7) [Kind: All v] [Status: All v] [Search target]                  |
|                                     [Accept selected (3)] [Accept all]       |
| [ ] | Target (kind above) | Proposed change | Confidence | Reason | From | Status | (sticky) Accept Reject |
```

- Columns: check box, Target, Proposed change, Confidence, Reason, From, Status, and Actions.
  - Target: the kind is small text above the target link. The link opens the row in Compare.
  - Proposed change: plus "Your choice: ..." when the user set one.
  - Reason: one line. The full text expands in the row.
  - From: the MCP client name and the time.
  - Actions: the column is sticky on the right, so Accept and Reject stay visible when the table scrolls inside its region.
- Status values, each with an icon and text:
  - "Ready to accept" (proposal tint, bot icon).
  - "Confirm row first" (warn, alert icon). The action is "Open row" in place of Accept.
  - "Conflicts with your choice" (warn, swap icon). The action is "Replace with agent choice".
- Filters: Kind (All and the 6 kinds), Status (All and the 3 values above), and text search on the target name. The filters use the new Select of ticket 09 (no native select). The sort is newest first.
- The check box is enabled only for "Ready to accept" rows. The header check box selects all rows that are shown and enabled.
- Only one question card shows fully. More open questions show as "N more open questions. Show them". Thus the first open question leads the screen. The Questions section is not shown when no question is open.
- Empty state (no open proposal and no open question): bot icon, the title "No open proposals or questions", and the text "When an agent connected through MCP proposes a change or asks a question, it shows here. Nothing changes until you accept it." The Refresh button stays.
- The Agent tab count is open proposals plus open questions (ticket 02).

States of the controls (the prototype shows default, hover, focus, disabled, loading and selected; measured below):

| Control | default | hover | focus | active | disabled | loading | error | selected |
|---|---|---|---|---|---|---|---|---|
| Accept / Replace with agent choice | primary | `brand-strong` | ring | `surface-3` press | session locked, or row needs confirm | "Accepting", disabled | inline row alert (copy table) | not applicable |
| Reject | secondary | `surface-hover` | ring | press | session locked | "Rejecting", disabled | inline row alert | not applicable |
| Accept selected | secondary | `surface-hover` | ring | press | 0 selected | "Accepting 2 of 3" | toast with the failed count | not applicable |
| Accept all | primary | `brand-strong` | ring | press | 0 ready proposals, or locked | dialog button "Accepting" | dialog alert | not applicable |
| Row check box | box | `surface-hover` row | ring | press | not ready | not applicable | not applicable | checked, row `brand-soft` |
| Answer | primary | `brand-strong` | ring | press | locked | "Saving answer" | inline card alert | not applicable |
| Option radio | radio | row `surface-hover` | ring | press | locked | not applicable | not applicable | checked |
| Refresh | secondary | `surface-hover` | ring | press | not applicable | spinner, "Checking" | inline line (copy below) | not applicable |

In a locked session (ticket 02 banner), each Accept, Reject, Answer and check box is disabled.

### Accept all flow and its summary (prototype screen `accept-all`)

1. The user clicks "Accept all".
2. The UI gets `GET plan` with accepted state only, and the plan with only the ready proposals (backend change request 3). The dialog shows the loading line "Calculating the effect on the plan" until both are back.
3. The dialog shows the summary.
4. The user clicks "Accept N proposals". The UI calls `proposal_accept_all` with the `base_revision`.
5. On success, the dialog closes. A toast says "5 proposals accepted. 2 skipped." The UI gets the session, the plan, and the list again.
6. On `stale_revision`, the dialog closes. The UI gets the data again and shows the shared toast. The user opens the dialog again and sees new numbers.

```
Accept 5 agent proposals?
Each proposal becomes your Merge Choice, name, or mapping. Apply then uses them.
Nothing is written to the files until you apply the plan.
Proposals to accept   Merge Choice 1 | Name 1 | Alignment 1 | Removal policy 1 | Need mapping 1
Effect on the plan    Now: [x Not valid: 2 blocking]
                      After accept: [! Valid with 3 warnings]
                      Change: 2 fewer blocking items, 1 more warning
Skipped (2)           [!] [YoY %]: a source changed. Confirm the row first.
                      [swap] Product[Category]: you already set a Merge Choice. Decide in the row detail.
                                                  [Cancel] [Accept 5 proposals]
```

- The count of a kind shows only when it is 1 or more.
- If 0 proposals are ready, the "Accept all" button is disabled. Its tooltip is "No proposal is ready to accept."
- Focus starts on "Cancel", because the action changes many choices. Escape closes the dialog.
- The dialog is the only guard. No type-to-confirm is necessary, because nothing is written to the files, and the user can change each choice again.

### Question card (prototype screen `agent`)

```
+ [msg Question from agent]  Claude Desktop, 10:42   Row: [Total Sales] -----+
| Sales B and Finance (cloud) have different [Total Sales]. Sales B uses    |
| Sales[Net]. Finance uses Sales[Gross]. Which one do you keep? (15px, 500)  |
| (o) Keep from Sales B (Sales[Net])  [check Recommended]                   |
|     Sets Merge Choice: Keep from Sales B                                   |
| ( ) Keep from Finance (cloud) (Sales[Gross])                              |
|     Sets Merge Choice: Keep from Finance (cloud)                           |
| ( ) Keep both, rename the Finance version to [Total Sales Gross]          |
| Reason: The target report labels the visual "Net sales", but ...           |
| [Answer] (primary)   [Open row] (ghost)                                    |
+---------------------------------------------------------------------------+
```

- The radio list is a `fieldset`. The recommended option is selected first and has the label "Recommended" (icon plus text).
- Under each option, a line gives its effect from the payload. An option with no payload has no effect line. Its answer goes only to the log.
- "Answer" calls `question_answer` with the option and the `base_revision`. After the call, the card moves to "Answered (N)", with the selected option and the time. A payload becomes an accepted choice (backend ticket 12, decision 9).
- Version 1 has no free-text answer and no dismiss. The question stays open until the user answers it. For a manual choice, the user clicks "Open row" and sets the Merge Choice in the row detail. The question then stays open, and the user can answer it later.
- A target that is an Impact item opens the Impact tab on that item (ticket 05).

### The include_proposals switch (prototype screen `plan-include`)

- A switch "Include open proposals" is in the toolbar of the Plan tab and of the Impact tab. Tickets 05 and 08 place it in the toolbar.
- The default is off, so the tabs show what Apply will do. The app keeps the switch state for each session in memory only.
- When it is on, an info banner shows above the content: "This view includes 7 open agent proposals. Apply uses only accepted choices."
- The Apply dialog (ticket 08) always uses accepted state, whatever the switch state is.

### Log view (prototype screens `log`, `log-proposal`)

```
| Session log         [Author: All v] [Action: All v] [Search target] [Proposal P-0007 x] |
| Time           | Author                      | Action                | Target       | Before  | After             | Reason       | Proposal |
| Today 10:44:12 | (user) You                  | Accepted proposal     | [Net Margin] | Not set | Keep from Sales B | Accepted ... | P-0007   |
| Today 10:41:30 | (bot) Agent: Claude Desktop | Proposed Merge Choice | [Net Margin] | Not set | Keep from Sales B | Sales B ...  | P-0007   |
| Showing 8 entries.                                                            [Show more] |
```

- Newest first. The Author column has an icon and text: "You" or "Agent: <MCP client name>".
- Action shows a plain label for each backend action. For example, `proposal_accept` shows as "Accepted proposal". Ticket 09 owns the full label list.
- Target is a link that opens the row in Compare or the item in Impact.
- Before and After show in the code font. An empty value shows as "None" (no dash). A long value expands in the row.
- The Proposal link filters the log to that proposal (backend change request 1). The filter shows as a chip with a clear button.
- Filters: Author (All, You, Agent), Action (All and the action labels), and target search.
- Paging: "Show more" loads the next page while `has_more` is true.
- The log has no edit and no delete.
- Empty state: the title "No changes yet" and the text "Each change to this session, by you or by an agent, shows here with its reason."

### Copy for each error code

| Code | Where | Text | Action |
|---|---|---|---|
| `stale_revision` | Shared toast (ticket 10). The UI gets the data again first. No automatic retry. | "This session changed in another place. The view shows the latest state. Do the action again." | none |
| `user_choice_exists` | Inline alert under the row in the list, or in the row detail card | "You already set a Merge Choice on this row. Change the choice in the row detail, or reject the proposal." | none |
| `source_changed` | Inline alert under the row in the list, or in the row detail card | "A source of this row changed after the agent made this proposal. Confirm the row first, then accept or reject the proposal." | "Open row" |

Other texts:
- Success toasts: "Proposal accepted.", "Proposal rejected.", "Answer saved."
- Accept selected with failures: "2 of 3 proposals accepted. 1 was not accepted. See the marked row."
- Poll failure (after 3 failures in sequence): an inline line in the Agent tab, "Could not check for new proposals. Try again." with "Refresh".
- Replaced proposal in an open card: "The agent replaced this proposal." The card then shows the new proposal.
- An inline alert uses `role="alert"`, a full hairline border, and an icon. The icon is `bad` for `user_choice_exists` and `warn` for `source_changed`.

### How new proposals appear (with ticket 10)

1. While the app window has focus and a session is open, the UI polls `GET session` every 5 s and compares `revision`. Ticket 10 sets the final interval and the shared poll.
2. When the revision changes, the UI updates the tab counts and the header plan status.
3. The UI does not add new rows to a list that the user examines. In the Agent tab, a notice shows at the top: "3 new proposals. Show them." The notice is `role="status"`. "Show them" loads the list again and keeps the filters.
4. The Agent tab has a "Refresh" button and the text "Last check 10:44".
5. When a change affects the open row detail, the card shows the new data after the next read. If the shown proposal ID is gone because the agent replaced it, the card shows "The agent replaced this proposal." and the new card.
6. While the window does not have focus, the poll stops. It runs one time when the window gets focus again.

### New tokens (for ticket 09)

- `proposal` and `proposal-soft` in `theme.css`, in both themes. In the prototype they are aliases of `info` and `info-soft`, so the measured contrast is the `info` contrast of ticket 01. Ticket 09 can give them their own values.

### Measurements (2026-10-31, Chrome 156.0.8078.49, playwright 1.63.0, axe-core 4.10.2)

- Page overflow (`measure.mjs`): 13 screens x 6 sizes (1024 x 640, then 1152, 1279, 1280, 1366, 1440 at 900 high) x 2 themes = 156 measurements. Page-level horizontal overflow is 0 px, and 0 elements are past the right edge outside a scroll container, on all 156. Two fixes were necessary first:
  - A section in the flex column took the width of the wide table. The fix was `min-width: 0` on each child of the region.
  - Hidden screen-reader text (`position: absolute`) inside the table scroll region made the page wider. The fix was `position: relative` on the scroll container. Fact for ticket 09: each scroll region that contains visually hidden text needs a positioned container.
- axe (the rule tags of ticket 01), 13 screens at 1440 x 900, dark and light: 0 violations on all 26.
- Kit `verify_states.mjs` (default, hover, focus) on the Agent screen, run through the gate wrapper with `DS_REQUIRE_BROWSER=1`: 144 element-states, pass in dark (`index.html --dark`), and pass in light (`light.html`, the same page with light as the default theme). The first run failed 3 states: the header plan status button "Plan not valid: 2 blocking" at 1.00:1. Cause: the gate reads the soft tint background without its alpha (the ticket 01 gate error). Fix (the same as ticket 08): the button uses an opaque tint `--bad-soft-solid`, the `bad-soft` token composited over `bg` with `color-mix`, with one value for each theme. The rendered color stays the same: the live text contrast on the tint is 6.45:1 dark and 4.79:1 light, before and after the fix.
- Live composited contrast of each badge (`status_contrast.mjs`, the minimum over 5 screens):
  - Dark: from 5.54 ("Proposed" on a selected grid row) to 8.05.
  - Light: from 4.56 ("Proposed" on a selected grid row) to 5.59.
  - All pass 4.5:1. The light "Proposed" badge on a selected row (4.56) has very little margin. Ticket 09 must examine this pair when it sets the `proposal` values.
- Kit `verify_target_size.mjs` (dark and light pages): 118 targets, all at least 24 x 24 or covered by an exception. A fix was necessary first: the row check boxes were 16 x 16 and are now 24 x 24.
- Kit `slop_tells.mjs --strict`: one MED tell, "Only one distinct shadow across the page". The prototype uses the theme shadows only for the dialog, the toast and the sheet. This agrees with the doctrine rule "most things are flat". On the light page: one LOW tell, two near-same neutrals (`rgb(239,239,236)` and `rgb(240,240,238)`), from the theme tokens of `theme.css`, not from new values.
- Kit `check_no_emoji.py` on the prototype: no emoji, no em dash or en dash.
- Screenshots: `shots/<screen>-<theme>-<1440|1024>.png`, 52 files. Raw results: `shots/result.json`. Screens examined by eye: Agent (dark 1440, light 1024 with an inline error), Accept all (light 1440), Compare with card (dark 1440, light 1024 sheet), Log (light 1440).

UNMEASURED:
- The state gate, target size and slop tells on the screens other than the default Agent screen (dark and light). The kit gates take a file path, not a query string.
- The real Radix Dialog focus trap, and the Tooltip, Select and Switch behavior. The prototype uses static markup.
- The poll cost, and the time to load the list again with many proposals (ticket 10).
- The full-page screenshot of the dialog shows the scrim only over the first viewport. This is a screenshot artifact of a fixed scrim, not a layout fault.

### Inputs for other tickets

- 03: the Merge Choice cell has a maximum of one badge (priority: Confirm row first, Question, Proposed). The proposed choice is in the tooltip. Add the filters "Has proposal" and "Has question".
- 04: put the proposal card (specification above) at the top of the row detail. Put the question card there when the row has an open question.
- 05 and 08: add the switch "Include open proposals" (off by default) and its info banner. Apply ignores the switch.
- 09: the tokens `proposal` and `proposal-soft`, an opaque tint token for each status badge that is a button (so that the state gate can measure it), the action labels of the log, the Switch, Tooltip and Dialog parts, and a check box with a 24 px target.
- 10: the 5 s revision poll while the window has focus, the "N new proposals" notice, the shared `stale_revision` toast, and no automatic retry.

### Backend change requests

1. `GET log`: add the filters `author` (user, agent), `action`, `target`, and `proposal_id`. Reason: a filter on loaded pages only gives wrong results, and the Proposal link needs all entries of one proposal.
2. `GET session`: for each open proposal and question, give: ID, kind, target ID, target display name, payload summary text, confidence, reason, MCP client name, created time, and blocked state (`source_changed`, `user_choice_conflict`). For answered questions, give the selected option and the time. Reason: the Agent tab and the row card need these fields without one read for each item.
3. `proposal_accept_all`: the technical design sections 12 and 14 do not state its behavior. Requested behavior:
   - Accept all open proposals that are not blocked.
   - Skip proposals on an unconfirmed marked row, and proposals that conflict with a user choice. Do not fail the full call because of them.
   - Return the accepted IDs, the skipped IDs with a reason code, and one new revision.
   - Write one log entry for each proposal.

   Also, `GET plan` and `GET impact` need `include_proposals=ready` (only the proposals that accept-all would accept). Reason: the summary dialog must show the real effect, and `true` also includes the skipped proposals.
4. `proposal_accept`: the technical design gives `user_choice_exists` only for agent submits. Requested behavior:
   - An accept by the user replaces the earlier user choice on that target. The log records the before and after values.
   - The accept refuses a proposal on an unconfirmed marked row with `source_changed`.

   Reason: the user accepts on purpose ("Replace with agent choice"), and a choice on a row that changed must not reach Apply without a confirm.
