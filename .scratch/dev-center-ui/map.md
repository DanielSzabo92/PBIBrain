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
