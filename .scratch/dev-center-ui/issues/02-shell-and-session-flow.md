# How does the user get into a merge session, and how is the work area laid out?

Type: grilling
Status: resolved
Blocked by: 01

## Question

Design the entry and the frame of the Development Center: the sidebar item, the "Merge sessions" list, the create-session flow, and the layout of the work area of an open session. Which sub-views does the work area have, how does the user move between them, and what does each session state look like?

## Context

- Charting decisions 2 and 5 (map): one sidebar item "Development Center" in `frontend/src/App.jsx` (`VIEWS`); session list as its landing; target 1440 x 900, minimum 1024 x 640; below 1280 wide, side panes become sheets.
- Session data: technical design section 11 and section 14.1 `GET session` (sources with kind, role, access type, status, fingerprint state; target; compare mode; plan status; counts; open questions; open proposals).
- JS API calls in scope: `session_create`, `session_open`, `session_close`, `source_add`, `source_remove`, `source_relink`, `target_set`, `compare_mode_set`, `sources_check`, `row_confirm`.
- Create flow: sources (local kinds of section 2.1; cloud sources are in ticket 07), target model and target report selection (spec section 5), target kinds "existing", "Empty", "Copy of <local source>" (section 2.2), the fixed refusal messages for TMSL, PBIR-Legacy, and PBIX targets.
- States to design: no sessions, session locked by another process (read-only), session with newer schema (refused), source changed marks and the confirm flow (section 11), source missing and relink, plan Invalid / Valid with warnings / Valid in the header.
- Existing parts to reuse: `PageHeading`, `EmptyState`, `Card`, `Tabs`, `Sheet`, toast in `App.jsx`.
- Skills: `design-doctrine`, `design-screen` (run its taste preflight and Brief Inference).

## Done when

The answer gives: the screen list with a wireframe (ASCII or prototype screenshot) for each, the sub-view list of the work area and the navigation between them, the create flow steps, each session state with its look and copy draft, and the responsive rule for each pane. All layout claims are measured (ticket 01) or marked UNMEASURED.

## Answer

Resolved on 2026-10-31. The orchestrator accepted all 17 recommendations of round 1 (one round). Prototype: `.scratch/dev-center-ui/prototypes/02/` (`index.html`, `tokens.css`, `measure.mjs`, screenshots in `shots/`). The prototype is never shipped.

### Brief Inference

- Domain: dev-tool (Power BI model merge).
- Audience and tone: expert BI developer. Calm, utilitarian.
- Mood: precise.
- Motion depth: subtle feedback only.
- Layout family: list landing, then a work area: header strip, banner stack, tab row, main region, optional side pane.
- Reference anchor: the existing PBIBrain shell (dense tool, one accent, flat surfaces).

### Decisions of round 1

1. Session list data comes from a new read endpoint `GET /api/devcenter/sessions`. This is a backend change request (see the map list "Backend change requests").
2. With no open project: empty state "Open a project to start a merge session" and the button "Open project".
3. Session list: one dense table (Name, Target, Sources, Plan, Last change, Status). One primary button "New merge session" in the page heading. No cards, no hero row. A click on a row opens the session.
4. No delete and no rename of sessions in version 1. No UI, no change request.
5. Create flow: full page in the main column, 3 steps (Sources, Target, Name and create), step indicator, Back and Next.
6. Create calls run only at "Create session": `session_create`, then `source_add` for each source, then `target_set`, with a progress list. If one call fails, the session exists and opens on the Sources tab with the failed item marked. Cancel before "Create session" leaves nothing on disk.
7. "Add source" menu: PBIP project, Model folder (TMDL), model.bim file, PBIR report, separator, Cloud model, Cloud report (the cloud items open the ticket 07 dialog). PBIX is refused inline.
8. Target step: two radio lists (model, report) with disabled items and their fixed messages.
9. Work area: 6 tabs. Naming rules are a section of the Sources tab.
10. Session header: name, target, plan status button, "Check sources", "More" menu. Apply is only in the Plan tab (ticket 08).
11. The open session stays open across sidebar items. "Close session" calls `session_close`. A session opened from the list closes the current one first.
12. Locked session: read-only banner with "Try again". No force unlock.
13. Newer schema or damaged session: list row with no open action and a reason line.
14. `sources_check` runs automatically on open. Marks show a banner with "Show these rows".
15. Missing source: status "Not found", "Find source" (`source_relink`) and "Remove" (destructive, confirm dialog).
16. `compare_mode_set`: only in the Compare toolbar, as "Default | Strict" (ticket 03 places it exactly).
17. Responsive rule: see "Responsive rule for each pane" below.

### Screen list and wireframes

Screenshots are in `prototypes/02/shots/<screen>-<theme>-<width>.png`, dark and light, at 1440 and 1024 wide. The repo `.gitignore` excludes `*.png`, so git does not keep them. To make them again, run `node measure.mjs shots` in `prototypes/02/`.

S1. No project (`no-project`)

```
| sidebar | Development Center                                   |
|         | Merge sessions (h1)                                  |
|         |        [folder icon]                                 |
|         |  Open a project to start a merge session             |
|         |  Merge sessions are saved in the project folder.     |
|         |  Open a PBIP project first.                          |
|         |        [Open project] (primary)                      |
```

S2. No sessions (`list-empty`): the same frame. Title "No merge sessions yet". Text "A merge session loads many models and reports, compares them, and builds one target. Nothing changes until you apply a plan." Button "New merge session" (primary).

S3. Session list (`list`)

```
| Development Center                                                         |
| Merge sessions (h1)                                  [+ New merge session] |
| Combine many models and reports into one target. ...                       |
| +-----------------------------------------------------------------------+ |
| | Name           | Target   | Sources | Plan          | Last change | Status                     | |
| | Sales master.. | Sales .. | 4       | ! Valid w. 5  | Today 10:42 | ok Ready                   | |
| | Finance cons.. | Finance  | 3       | x Not valid 3 | Yesterday   | lock Open in another window | |
| |   Opens read-only.                                                     | |
| | Ops pilot      | Ops ..   | 2       | Not known     | 20 Oct 2026 | x Needs a newer PBIBrain   | |
| |   This session was saved by a newer PBIBrain version. Update ...       | |
| | Marketing test | Not known| 0       | Not known     | 12 Oct 2026 | x Cannot read              | |
| +-----------------------------------------------------------------------+ |
```

The name is a link, and the full row is also clickable. Rows with "Needs a newer PBIBrain" or "Cannot read" have no link. Sort: last change, newest first. The table scrolls inside its own wrapper if it does not fit.

S4. Create, step 1 Sources (`create-1-sources`, menu open)

```
| Development Center > New merge session                                     |
| New merge session (h1)                                                     |
| (1) Sources   (2) Target   (3) Name and create                             |
| +------------------------------------------------------------------------+ |
| | Sources                                              [+ Add source v]  | |
| | Add each model and report to compare. Sources stay read-only.          | |
| | [file] Sales A  PBIP project, TMDL  models/SalesA/...   ok Read  Remove | |
| | ...                                                                    | |
| | [!] Cannot add "Budget.pbix". Save as PBIP in Power BI Desktop.        | |
| +------------------------------------------------------------------------+ |
| [Cancel]                                                          [Next]   |
```

"Next" is disabled until the list has at least one model source. A source that fails to read shows its error in its row.

S5. Create, step 2 Target (`create-2-target`)

```
| Target model                                                               |
|  ( ) Sales A  PBIP project, TMDL                                           |
|  (-) Sales B  PBIP project, TMSL   i Save as TMDL in Power BI Desktop first. |
|  ( ) Empty    A new model with no objects                                  |
|  (o) Copy of Sales A   Copies the folder. Sales A stays the same.          |
|      New folder: models/SalesMaster  [Change]                              |
| Target report                                                              |
|  (o) New empty report   Bound to the target model                          |
|  ( ) Sales Overview  PBIR report                                           |
|      ! Rebind needed. Bound to Sales B. 12 fields are not in the target model. |
|  (-) Old KPIs  PBIR-Legacy report  i Convert to PBIR in Power BI Desktop first. |
| [Back]                                                            [Next]   |
```

"Copy of <source>" shows one item for each local model source that can be a write target. The selection of this item opens the native folder picker for the new path. Default target model: none. "Next" stays disabled until the user selects one. Default target report: "New empty report". Before create, the session does not exist, so the rebind count may not be known. Then the text is only "Rebind needed. Bound to <model>." The count shows after create (from `GET impact`).

S6. Create, step 3 Name and create (`create-3-fail`)

```
| Session name [Sales Master merge        ]                                  |
| Sources        4 (2 models, 2 reports)                                     |
| Target model   Copy of Sales A in models/SalesMaster                       |
| Target report  New empty report                                            |
| (after Create session:)                                                    |
|  ok Session created                                                        |
|  ok Sales A added                                                          |
|  x  Sales B not added: the folder was not found.                           |
|  >  Sales Overview, Old KPIs, Set target (not run)                         |
| [!] The session exists, but 1 source was not added.                        |
|     Open the session to add it again.                      [Open session]  |
| [Back] (disabled while it runs)                       [Create session]     |
```

Default name: "<target model name> merge". The progress list is `aria-live="polite"`.

S7. Work area (`work-compare-pane`, `work-locked`, `work-sources-missing`, `work-more-menu`)

```
| Development Center > Sales master merge > Compare                           |
| Sales master merge (h1)       [! Valid with 5 warnings] [Check sources] [...] |
| [db] Target model: Sales Master   [file] Target report: new empty report     |
| [banner stack: locked / source missing / sources changed]                    |
| Compare | Impact | Plan (3) | Agent (4) | Sources | Log                       |
| +-------------------------------------------+ +---------------------------+ |
| | toolbar: Compare mode [Default | Strict]  | | Row detail (ticket 04)    | |
| | grid (ticket 03), scrolls in its region   | | 360 px column at >= 1280  | |
| +-------------------------------------------+ +---------------------------+ |
```

The Sources tab has three sections: Sources (rows with kind, role, access type, status, actions), Target (model, report, "Change target"), and Naming rules (ticket 07).

### Sub-views of the work area and the navigation

| Tab | Content | Count on the label | Owner ticket |
|---|---|---|---|
| Compare (default) | Compare grid, compare mode | none | 03, 04 |
| Impact | Impact views | none | 05 |
| Plan | Plan, Apply, undo, change report | blocking items (bad tint) | 08 |
| Agent | Proposals and questions | open proposals plus open questions | 06 |
| Sources | Sources, target, naming rules | none | 02, 07 |
| Log | Session log | none | 06 |

Navigation rules:

- The sidebar has one item, "Development Center". It shows the list when no session is open. It shows the work area of the open session when one is open.
- The breadcrumb is "Development Center > <session name> > <tab>". The first part goes back to the list. The session stays open.
- The tab row is a Radix Tabs list (arrow keys, Home, End). The app keeps the last tab of each session in memory, not on disk.
- The plan status button opens the Plan tab. "Show these rows" opens Compare with the marks filter. "Open Sources" opens the Sources tab. Hide "Open Sources" when the Sources tab is active (the prototype still shows it).
- "More" menu: "Check sources" (below 1280 wide only) and "Close session". "Close session" calls `session_close` and shows the list.
- When the user opens a session from the list and another session is open, the app calls `session_close` on the current session, then `session_open`.

### Create flow steps

1. The user clicks "New merge session" (list heading or empty state).
2. Step 1 Sources: the user adds sources with "Add source". Each local item opens the native picker. Each cloud item opens the ticket 07 dialog. The UI refuses a PBIX file inline. The UI keeps a draft only.
3. Step 2 Target: the user selects the target model and the target report. Disabled items show the fixed refusal messages.
4. Step 3 Name and create: the user examines the name and clicks "Create session".
5. The UI calls `session_create`, then `source_add` for each source in list order, then `target_set`. Each call sends the `base_revision` from the previous reply.
6. On success, the work area opens on the Compare tab. On failure, the progress list shows the failed call. "Open session" opens the Sources tab with the failed item marked.

If the user clicks "Cancel" or goes to another sidebar item before step 5, the UI drops the draft.

### Session states: look and copy draft

Each status uses icon plus text, never color only. Banners use a full hairline border on all sides (no one-sided color bar).

| State | Where | Look | Copy draft |
|---|---|---|---|
| No project | List page | Empty state, folder icon, primary button | "Open a project to start a merge session" / "Merge sessions are saved in the project folder. Open a PBIP project first." / "Open project" |
| No sessions | List page | Empty state, merge icon, primary button | "No merge sessions yet" / "A merge session loads many models and reports, compares them, and builds one target. Nothing changes until you apply a plan." / "New merge session" |
| Ready | List row | `ok` badge, check icon | "Ready" |
| Locked by another process | List row | `info` badge, lock icon, reason line | "Open in another window" / "Opens read-only." |
| Locked by another process | Work area | `info` banner (lock icon); each change control disabled | "Another PBIBrain window has this session open. You can read it, but you cannot change it." / "Try again" |
| Newer schema | List row, no link | `bad` badge, x icon, reason line | "Needs a newer PBIBrain" / "This session was saved by a newer PBIBrain version. Update PBIBrain to open it." |
| Damaged file | List row, no link | `bad` badge, x icon, reason line | "Cannot read" / "The session file is not valid JSON or has merge conflict marks. Fix the file, then try again." |
| Sources changed | Work area banner; Sources row | `warn` banner; `warn` badge "Changed" | "2 sources changed since the last check. 14 rows need your confirm." / "Show these rows" |
| Source missing | Work area banner; Sources row | `bad` banner; `bad` badge "Not found"; "Find source", "Remove" | "1 source was not found: Sales B. Find it again or remove it." / "Open Sources" |
| Remove source confirm | Dialog | Destructive confirm button | "Remove Sales B from this session?" / "Merge Choices that use Sales B stay in the session, but they have no source." / "Remove source" / "Cancel" |
| Check sources running | Header button | Loading state, spinner icon | "Checking sources" |
| Check sources, no change | Toast | Existing app toast | "All sources are the same as at the last check." |
| Plan Invalid | Header | `bad` status button | "Plan not valid: 3 blocking" |
| Plan Valid with warnings | Header | `warn` status button | "Valid with 5 warnings" |
| Plan Valid | Header | `ok` status button | "Valid" |
| Plan not computed yet | Header | Plain status, spinner | "Checking plan" |
| Create partly failed | Create step 3 | `bad` banner, progress list | "The session exists, but 1 source was not added. Open the session to add it again." / "Open session" |
| PBIX refused | Create step 1 | `bad` inline banner | "Cannot add "<file>". Save as PBIP in Power BI Desktop." |

Banner order when more than one shows: locked, source missing, sources changed. The remove-confirm text about Merge Choices is a draft. Ticket 09 must confirm it against the backend behavior of `source_remove`.

### Responsive rule for each pane

| Pane | 1280 px wide and more | Below 1280 px (down to 1024 x 640) | Measured |
|---|---|---|---|
| App sidebar | 236 px, no change | 236 px, no change | yes (ticket 01 and this prototype) |
| Work header | One row; "Check sources" is a button | "Check sources" moves into the "More" menu; the header wraps | yes: button visible at 1280, 1366, 1440; hidden at 1024, 1152, 1279 |
| Banner stack | Full width | Full width; text wraps; the action wraps below | yes (no overflow) |
| Tab row | One row | Scrolls inside its own row if it does not fit | yes: the 6 tabs fit at all measured widths, no tab scroll |
| Main region (grid) | Fills the space left of the side pane | Full width | yes: the grid scrolls inside its own region; no page overflow |
| Side pane (row detail and later panes) | Fixed right column, 360 px | Sheet over the content, `min(400px, 92vw)` wide; Escape closes it | yes: column 360 px at 1280 to 1440; sheet 400 px at 1024 to 1279 |
| List table | Fits | Scrolls inside its own wrapper if necessary | yes (no overflow) |
| Create panel | Max 880 px wide | Fills the main column | yes (no overflow) |
| Menus | Align to the trigger edge that keeps them on screen | The same | yes, after a fix: the "Add source" menu first went 58 px past the right edge at 1024 and 1152. Aligned to the right edge of its trigger: 0 px |

The kit rule "mobile is the base" does not apply, because the app has no phone layout (map decision 5). The prototype uses `min-width: 1280px` and `max-width: 1279.98px` queries.

### Measurements (2026-10-31, Chrome 156.0.8078.49, playwright 1.63.0, axe-core 4.10.2)

- Page overflow (`measure.mjs`): 10 screens x 6 sizes (1024 x 640, then 1152, 1279, 1280, 1366, 1440 at 900 high) x 2 themes = 120 measurements. Page-level horizontal overflow 0 px, and 0 elements past the right edge outside a scroll container, on all 120 (after the menu fix above).
- axe (the rule tags of ticket 01), 10 screens at 1440 x 900, dark and light: 0 violations on all 20.
- Kit `verify_states.mjs` (default, hover, focus) on the list screen: 33 element-states, pass in dark and in light.
- Kit `verify_target_size.mjs` on the list screen: 22 targets, all at least 24 x 24. Pass.
- Kit `slop_tells.mjs --strict` on the list screen: no tells.
- Kit `check_no_emoji.py` on the prototype: no emoji, no em dash or en dash.
- Raw results: `prototypes/02/shots/result.json`.

UNMEASURED: the state gate, target size and slop tells on the screens other than the list (the kit gates take a file path, not a query string). The real Radix Menu, Tabs and Sheet focus behavior (the prototype uses static markup). The rendered contrast of the disabled radio text (`text-3`); ticket 01 measured `text-3` on all surfaces at 5.56 or more (dark) and 4.71 or more (light).

### Backend change request

`GET /api/devcenter/sessions`: for each session in `<project root>/.pbibrain/sessions/` (and in `%APPDATA%/PBIBrain/sessions/` for cloud-only targets): ID, display name, updated time (UTC), target model name, target report name, source count, plan status (null when it is not known without a compute), lock state (`free`, `locked`), schema state (`ok`, `newer`, `damaged`). Reason: `GET session` returns only the open session, so the list screen has no data. The map list "Backend change requests" has this item. Open point for the backend: a plan status can need a compute. Null is permitted; the list then shows "Not known".

### Inputs for later tickets

- 03: put the "Default | Strict" control in the Compare toolbar. Support the marks filter that "Show these rows" sets. Give a bulk confirm for marked rows.
- 04: the row detail renders in the 360 px column or in the 400 px sheet.
- 06, 08: the Agent and Plan tab counts come from `GET session` (open proposals, open questions) and `GET plan` (blocking items).
- 09: new parts: a Menu (Radix DropdownMenu), a Steps indicator, a Banner, a status badge with icon, and a radio list with a disabled reason. Each control border uses `control-border`.
