# Map: Power BI Development Center UI

Label: wayfinder:map

## Destination

A UI design document (`docs/DEV_CENTER_UI_DESIGN.md`) for version 1 of the Development Center. It gives the screens, flows, layout, components with the 8 states, copy, the a11y contract, and the UI build steps (U0, U1, ...) with automated tests (unit, contract against the section 14 JSON Schemas, Playwright e2e). It is complete enough to split into UI build tickets.

## Notes

- Baselines (accepted, do not reopen without the user): [Functional specification](../../docs/DEV_CENTER_FUNCTIONAL_SPEC.md), [Technical design](../../docs/DEV_CENTER_TECHNICAL_DESIGN.md) (mainly section 13 Apply, section 14 UI data contracts, section 15 scope, section 16 build steps), ADRs in `docs/adr/`, word list `CONTEXT.md`, learnings in `.trail/learnings/`. The backend map is `.scratch/dev-center/map.md`.
- Scope: version 1 only. Local merge plus cloud read. No cloud write UI (version 1.1).
- Word list: use "Merge Choice" for the choice on one row (not "Decision").
- Language: ASD-STE100 for all text. UI copy also obeys the `ux-writing` skill. No emoji. No em dash or en dash in UI copy.
- Skills for each ticket session: call `ux-ui-agent-skills:design-doctrine` first. Then, where they fit: `design-screen` (02, 03, 05, 08), `data-dashboard` (03, 05), `design-component` (04, 09), `ux-writing` (06, 08, 09), `a11y-audit` (09), `design-review` (11). Conversation tickets also call "grilling" and "domain-modeling". Prototype tickets call "prototype".
- HITL tickets: the ticket session asks the orchestrator session in rounds, with a recommended answer for each question. The orchestrator answers for the user. Put the full text of each round in the message (the orchestrator cannot read a scratchpad file).
- Prototypes go in `.scratch/dev-center-ui/prototypes/<ticket>/`. They are never shipped. Give screenshots in both themes.
- Render gates: until ticket 01 runs `npm install && npx playwright install chrome`, mark each contrast, a11y, state, and layout claim UNMEASURED. A gate that prints SKIPPED is not a pass.
- Standing decisions from charting (2026-10-31, round 1, all accepted):
  1. Destination and paths as above.
  2. Place in the app: one new sidebar item "Development Center" in the existing shell (`frontend/src/App.jsx`). It opens a session list ("Merge sessions"). An open session gets its own work area with sub-views. No second window, no second app.
  3. One design system: reuse `frontend/src/theme.css` tokens and `frontend/src/components/ui/`. Add only semantic tokens for new meanings (compare states, impact severities, proposal status) in `theme.css`, in both themes. Each status shows icon + text, never color only.
  4. No native select in new screens: new Radix-based Select and Combobox parts in `components/ui/`. Old screens keep `NativeSelect` in version 1; their migration is a later task.
  5. Window size: design target 1440 x 900. Minimum supported window 1024 x 640. Below 1280 wide, side panes become sheets (overlay). No phone layout. No page-level horizontal overflow at any width; wide grids scroll inside their own region.
  6. Data seam: an HTTP read client (`/api/devcenter/...`) and a JS API client (section 14.2). Browser dev mode and Playwright e2e use one JS API mock plus a fake HTTP server with fixture JSON from the "merge lab". Contract tests validate each fixture and each mock reply against the section 14 JSON Schemas. A UI build step that needs a schema waits for the backend step that creates it.
  7. Ticket list and blocking as on this map.
  8. HITL answers come from the orchestrator (see above).
  9. Skills as in the list above.

## Decisions so far

<!-- one line per closed ticket -->
- 01 (2026-10-31): Render gates work after `npm install` in the kit folder. Theme text and status tokens pass AA in both themes. `line`, `line-strong` (`input`) and `line-focus` are below 3:1, so new controls use `control-border`. axe fails on Graph (2 rules) and on the light Inspector type chip (4.15:1). No page overflow from 1024 to 1440. Full values: [01-render-gates](issues/01-render-gates.md).
- 02 (2026-10-31): The sidebar item opens a "Merge sessions" table. A 3-step create page (Sources, Target, Name and create) calls the JS API only at the end. The work area has a header (plan status, Check sources, More), banners, and 6 tabs (Compare, Impact, Plan, Agent, Sources, Log). Side panes are a 360 px column at 1280 px and wider, and a sheet below. Measured: 0 overflow in 120 runs, 0 axe violations. Full answer: [02-shell-and-session-flow](issues/02-shell-and-session-flow.md).
- 10 (2026-10-31): Data seam in `frontend/src/devcenter/`: HTTP read client, queued JS API client with revision, no state library (`useSyncExternalStore` store). Mock state lives in a new fake server (port 8766), and a test shim forwards the JS API calls to it. `stale_revision`: no retry, refetch, toast. Poll `GET session` every 5 s. Unit, contract and e2e tests run in a new CI workflow. Full answer: [10-data-layer-and-tests](issues/10-data-layer-and-tests.md).
- 08 (2026-10-31): The Plan tab has a status strip with "Apply plan", a block list (one fix action for each block), then the summary, plan steps, and warnings. The Apply dialog has one approval checkbox and uses the destructive token when the plan deletes objects. Progress comes from polling. A result panel gives Undo and the change report. Measured: 0 overflow, 0 axe violations, state gate passes in both themes. Full answer: [08-plan-apply-undo](issues/08-plan-apply-undo.md).
- 06 (2026-10-31): The Agent tab shows one leading question card, then a proposals table (Kind, Status, search, sticky Accept and Reject, Accept selected, Accept all). Accept all shows a summary: kinds, plan now and after, skipped items. The grid cell has one "bot" badge with a tooltip. Revision poll every 5 s with a notice. Log table with filters. Measured: 0 overflow, 0 axe violations, states pass in both themes. Full answer: [06-agent-proposals-and-log](issues/06-agent-proposals-and-log.md).

## Backend change requests

<!-- one line each: endpoint, fields, reason, ticket. Ticket 11 carries this list into the design. -->
- `GET /api/devcenter/sessions`. Fields for each session: ID, display name, updated time, target model and report names, source count, plan status (null permitted), lock state, schema state (ok, newer, damaged). Reason: `GET session` returns only the open session, so the session list has no data. Ticket 02.
- All `/api/devcenter/*` reads: add a `revision` field. Reason: the UI drops replies that are older than its last state change. Ticket 10.
- `GET /api/devcenter/session`: keep it cheap. Return the cached plan status, or null with `plan_state: "computing"`, and never run a plan compute. Reason: the UI polls it every 5 s. Ticket 10.
- `backend/devcenter/contracts/`: add one JSON Schema for each section 14.2 JS API call (request and reply), plus the error shape `{error:{code,message,details}}`. Reason: the contract test validates each mock reply. Ticket 10.
- `GET /api/devcenter/apply/progress`: fields `apply_id`, `step` (section 13 step ID), `step_index`, `step_count`, `state` (running, done, failed). Reason: the Apply dialog shows the current step, with a poll every 500 ms. Tickets 08 and 10.
- `GET /api/devcenter/apply/preview`: add the blocks (unconfirmed mark count and row keys, Desktop state not_open/open_saved/open_unsaved/not_reachable, list of non-canonical files, full validation result, plan hash). Reason: the UI shows the blocks of apply steps 1 to 5 before the dialog opens. Ticket 08.
- `GET /api/devcenter/apply/last`: fields apply_id, kind (apply, format_only), finished time UTC, file count, backup present, target changed since apply plus the list of changed files, rescan differences (object, expected, found). Reason: Undo availability and refusal, and the result panel after the session opens again. Ticket 08.
- `GET /api/devcenter/log`: add the filters author, action, target, proposal_id. Reason: a filter on loaded pages gives wrong results, and the Proposal link needs all entries of one proposal. Ticket 06.
- `GET /api/devcenter/session`: for each open proposal and question, give ID, kind, target ID, target display name, payload summary text, confidence, reason, MCP client, created time, and blocked state (source_changed, user_choice_conflict). For answered questions, give the selected option and the time. Reason: the Agent tab and the row card need these fields without one read for each item. Ticket 06.
- JS API `proposal_accept_all`: accept all proposals that are not blocked. Skip proposals on unconfirmed marked rows and proposals in conflict with a user choice, and do not fail the full call. Return the accepted IDs, the skipped IDs with a reason code, and one revision. Write one log entry for each proposal. Reason: technical design sections 12 and 14 do not state this. Ticket 06.
- `GET /api/devcenter/plan` and `GET /api/devcenter/impact`: add `include_proposals=ready` (only the proposals that accept-all would accept). Reason: the Accept all summary must show the real effect. Ticket 06.
- JS API `proposal_accept`: a user accept replaces the earlier user choice on that target, and the log records before and after. Refuse a proposal on an unconfirmed marked row with source_changed. Reason: sections 12 and 14 give user_choice_exists only for agent submits. Ticket 06.

## Not yet specified

- Keyboard shortcut map for the full work area (global keys versus grid keys). Probably settles in tickets 03 and 09.
- Performance budgets for the UI (first render of 5,000 compare rows, filter response time). Probably settles in tickets 03 and 10.
- The order of the UI build steps against the backend lanes (S2 to S11). Settles in ticket 11.

## Out of scope

- Cloud write UI: XMLA deploy, Fabric `updateDefinition`, the PBIX warning dialog for XMLA write (version 1.1, technical design section 10.4). Ruled out at charting: version 1 only.
- The later features (technical design section 15.3): value check, service principal sign-in, file watcher, perspectives, translations, themes, bookmark copy, merge templates, golden library, duplicate finder, unused object finder, three-way Git merge.
- Migration of the old screens from `NativeSelect` to the new Select. Ruled out at charting (decision 4): a later task.
- A phone layout. Ruled out at charting (decision 5): desktop app.
- Backend data contracts. They are fixed in the technical design section 14. A UI need that the contracts do not cover goes to the orchestrator as a backend change request, not into this map.
