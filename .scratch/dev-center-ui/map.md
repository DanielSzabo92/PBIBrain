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
- 07 (2026-10-31): Cloud sources use one dialog: Sign in, Select (list from `cloud_items_list`, paste fallback), Access type (Read default; Read/Write saved, no write in 1.0, no later change), Test (Checked and Not checked groups). Unreadable cloud reports are not added. Pull to local adds a local source (path relative to the project root). Naming rules: Sources tab table, status filter, side-pane editor. Measured: 0 overflow, 0 axe, states pass. Full answer: [07-sources-connect-naming](issues/07-sources-connect-naming.md).
- 04 (2026-10-31): The row detail pane shows notices, the agent card, then one Merge Choice radio group. Source Select, name field with the proposer, folder Combobox and property picker show inside the selected choice. A modal dialog sets the removal policy (Block, Cascade, Repoint). Save is immediate. Measured: 0 overflow, 0 axe violations, states pass. Full answer: [04-row-detail-and-merge-choice](issues/04-row-detail-and-merge-choice.md).
- 03 (2026-10-31): The compare grid is an ARIA grid with 36 px virtual rows and pages of 200. Sticky parts are the header, Object and Target columns. Each state shows icon plus word. Default filter is "not same". A bulk bar sets Merge Choices with explicit row keys. The code diff opens in a modal. Measured: 0 overflow, 0 axe violations, states pass. Jump scroll fails the 50 ms budget in the prototype; build rule: light rows during a fast scroll. Full answer: [03-compare-grid](issues/03-compare-grid.md).
- 05 (2026-10-31): The Impact tab has a scope (whole plan or row), Breaks, Needs and Offers groups, and Table, Graph and Wireframe views. Items use two-line rows with one primary action. The graph reuses the dagre layout with a new impact node. The wireframe shows status as pattern, icon and text. A completeness strip shows in all views. Measured: 0 overflow, 0 axe, states pass. Full answer: [05-impact-views](issues/05-impact-views.md).
- 09 (2026-10-31): One unified token set: opaque hex tints (`--ok-tint` to `--brand-tint`), `--bad-ink`, `--bad-strong`, and aliases `--cmp-*`, `--impact-*`, `--proposal` (= `brand-strong`). 31 new parts with 8 states, a keyed copy catalog, and a 21-rule a11y contract with one test each. Found: the current destructive Button is 2.61:1 in dark (UI build item U-fix-1); the Tabs fix is U-fix-2. "Match" words become "Split row" and "Join with a row". Specimen: 177 element-states pass in both themes, 0 axe. Full answer: [09-components-tokens-copy-a11y](issues/09-components-tokens-copy-a11y.md).

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
- JS API `cloud_items_list` (read, JS API only). Input: kind (workspaces, models, reports), workspace_id. Output: workspaces (ID, name, capacity type, XMLA available); models (ID, name, updated time, model type, XMLA readable plus reason code); reports (ID, name, PBIR or PBIR-Legacy, dataset ID). Reason: no call lists cloud items. HTTP has no authentication, so this must not be an HTTP call. Ticket 07.
- JS API `cloud_sign_in`: add input `prompt` (none, select_account) and return the account display name. No file stores the name. Reason: "Use a different account" and the "Signed in as" line. Ticket 07.
- JS API `cloud_connect` reply: test lines with check ID, result (ok, failed, not_checked), reason code, and values (capacity type, role, table and measure counts, report counts, names of unreadable reports). Reason: the Test step. Ticket 07.
- JS API `naming_rule_reject` on a user rule removes the rule; on a detected rule it keeps it as rejected. `naming_rule_edit` with no rule ID creates a user rule (origin user, status confirmed); an edit of a proposed rule sets it to confirmed. Reason: the naming rules screen. Ticket 07.
- JS API `pull_to_local`: store the new source path relative to the project root; a failed pull removes the partial folder. Ticket 07.
- `GET /api/devcenter/naming-rules`: add the rule count for each session source model. Reason: the "Copy rules from" dialog. Ticket 07.
- `POST /api/devcenter/name-propose`: add optional input `candidate`; the reply adds `breaks` (rule ID, rule text) and `clash` (object or null). Reason: no contract checks a name that the user types. Ticket 04.
- `GET /api/devcenter/display-folders?source=<id>` (new, optional object type filter): returns display folder paths. Reason: the folder Combobox needs the folders of the target and the selected source (spec 7.2). Ticket 04.
- JS API `alignment_override` (break): remove the Merge Choice of the row and return the new row keys. Reason: the UI moves the selection and tells the user. Ticket 04.
- JS API `merge_choice_set`: accept the values `promote` and `copy_to_report` (with new name and display folder) for report measure rows. Reason: spec 7.4 makes them plan steps, but section 14.2 has no call for them. Ticket 04.
- `GET /api/devcenter/compare-rows`: add `q` (name contains, case-insensitive). Reason: name search in the filter bar. Ticket 03.
- `GET /api/devcenter/compare-rows`: add `total` and `state_counts` for the current filter. Reason: `aria-rowcount`, scroll height, "Select all N rows", footer counts. Ticket 03.
- `GET /api/devcenter/compare-rows`: add `sort` (state, name, type, table; asc or desc). Reason: sortable columns, in place of grouping by table. Ticket 03.
- `GET /api/devcenter/compare-rows`: add `row_state` for each row (highest precedence over all cells), and use it for the `state` filter. Reason: the Row state column and the filter must agree. Ticket 03.
- JS API `row_confirm`: accept a list of row keys. Reason: "Confirm N rows" in the bulk bar. Ticket 03.
- JS API `impact_action_apply` for many items: `item_ids` (array), `action`, `base_revision`; one revision step, all or nothing; the reply lists the items it could not change. Reason: bulk "Include in rewrite" and "Add from donor". Ticket 05.
- `GET /api/devcenter/impact` filters and totals: parameters `direction`, `blocking`, `severity`, `certainty`, `source`, `object_type`, `q`, with `limit` and `offset`; the reply adds `total` and facet counts for the full result before paging. Reason: filters and counts on large lists without a download of all pages. Ticket 05.
- `GET /api/devcenter/impact/{item}/paths` (new): all paths of one Impact item, paged; each step has object ID, name, type, and edge phrase. Reason: "Show other paths" in the item pane. Ticket 05.
- `backend/devcenter/contracts/phrases.json` (new): each phrase ID (compare properties, compare notes, impact reasons, edge phrases) with its STE text; a contract test checks no em or en dash, no emoji, max 60 characters, and that each engine ID is in the file. Reason: one owner of phrase text; the UI shows `text` only. Ticket 09.
- `apply`, `format_only_apply`, `undo_apply` errors: add `details.step` (section 13 step ID) and `details.check` for the guard (scope, canonical, tree_compare, pbir, policy, approval, write, rescan). Reason: one plain sentence for each failure; section 12 has no guard codes. Ticket 09.
- JS API `source_remove`: keep the Merge Choices that take from the removed source, add one blocking plan item for each (kind `choice_source_removed`), and return the count. Reason: the remove confirm text and the block list. Ticket 09.
- JS API `naming_rule_edit`: refuse a rule with the same object type, scope and check kind with `action_not_allowed` and `details.existing_rule_id`. Reason: the "Same rule exists" error. Ticket 09.

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
