# Handoff: remaining work from the adversarial product review

Branch: `claude/vibrant-franklin-h8aafq` (the review branch `claude/product-adversarial-review-wid901` merged in; everything below is pushed; no PR is open).

The review is in `docs/adversarial-review/`: one file per finding (01–22) with evidence, solution and
acceptance criteria. The fix-status table in `docs/adversarial-review/README.md` says what was done for
each finding and what each fix measured. This file lists only what is still open.

## Done since the first handoff

On branch `claude/vibrant-franklin-h8aafq` (the review branch merged in, plus the commits below it).

| Area | What was done |
|---|---|
| Review queue | Row selection (checkbox, X key, header checkbox, "Approve N selected"). Bulk decisions are one write on the server with an undo token (`POST /api/review` with `items` or `filter`, `reply: "summary"`; undo with `token`). Auto-accept: Settings › Review, off by default, threshold 90 %, marked "Auto" under Reviewed, marks in `review-marks.json` beside the override file. |
| Inspector and graph | "Versions" dialog on the Lineage toolbar: "Not a version" and "Is a version of", stored as `version_links` in `brain.json`. Folded title is the shared name ("Sales Analytics · 2 versions"). Visual types are readable. "Other dependencies" no longer repeats the field wells. Field wells checked on a real PBIR report. |
| Scan | Background job: `POST /api/scan {"background": true}`, status in `GET /api/scan/status` (`last` holds how it ended), `POST /api/scan/cancel`. The request lock is held only while the graph is published. Per-source state in `GET /api/config/sources` (`scan`), shown in Settings. |
| Gates | `tools/large_project.py` writes the 13,731-object project; `tests/test_scale_budgets_large.py` holds its first requests to budgets. The overview lists at most 50 validation issues and counts the rest (`validation_issue_count`). |
| Merge models | One filter line in Compare: the chip row is gone, "Clear filters" sits in the toolbar. |
| Code structure | The Review queue and the shared view helpers moved out of `App.jsx` into `frontend/src/views/`; no behaviour change. |

Decisions a reader may question:

- **Auto-accept is off by default.** It changes what "reviewed" means, so a project opts in.
- **Version corrections are in the project file, not the override file.** An override on a model marks the model itself as "Edited" in every view.
- **Cancel stops between scan steps.** Formula analysis is one step (15 of 18 s on the large project), so a cancel during it takes effect when it ends; the page is released at once and nothing is published.
- **"Header action" (Merge shows "Change project" where other views show "Scan sources") was not changed.** The header shows both buttons in every view; "Scan sources" is hidden while the project has no objects, which is the state of the fake server the review used for Merge.

## Remaining tasks

Ordered by value to a user of a large project. Sizes are rough: S = hours, M = a day or two, L = several days.

### Review queue (findings 01, 11)

| Task | Size | Notes |
|---|---|---|
| Server paging of the review snapshot | L | Deliberately not done. The snapshot is 42 MB on the 13,731-object project but opens in about 1 s, and grouping by pattern counts every item on the client. Only worth doing if pattern counts move to the server first. See the learning "A long review queue opens grouped by pattern". |
| Bulk decisions by filter from the page | S | The server accepts `filter`, but the page still sends identifiers: patterns and "low evidence" are computed in the browser. Use `filter` once those move to the server. |

### Merge models (finding 19)

| Task | Size | Notes |
|---|---|---|
| Offer only the choices that apply | M | The row detail lists six options, two disabled with a reason. `e2e/devcenter-row.spec.js` asserts the disabled radios exist (lines ~203–225, 511, 606), so this is a contract change, not a style change. |
| Process stepper | M | Sources → Compare → Impact → Plan → Apply as a progress strip with counts. Today the step tabs are only set apart from the tool tabs by a divider (`TOOL_TABS` in `frontend/src/devcenter/screens/WorkArea.jsx`). |
| Breadcrumb | S | "Merge models › session › tab" repeats the sidebar, the title and the tab. The first crumb is the only way back to the session list, so replace it with a session switcher before removing it. |

### Inspector and graph (findings 13, 15, 07)

| Task | Size | Notes |
|---|---|---|
| A card visual's measure is missing from `visual_bindings` | S | On `tests/fixtures/merge_lab/SalesA` the card "target" has the well Values: Sales Target, but `visual_bindings.measures` is empty. The page lists by well, so it shows correctly; the bindings count is wrong. |
| Lineage layout in a worker, scroll scrubber | M | Open items of finding 07. |
| Zoom control in the toolbar, project switcher, skeletons | S each | Leftovers of finding 15. |

### First run, settings, scan (findings 20, 18, 04)

| Task | Size | Notes |
|---|---|---|
| Drop zone and Browse | M | Needs the desktop shell: a browser cannot read the path of a dropped file. `DesktopProjectView` already has `addSources`. |
| Recent projects | S | On the empty Overview and in the title bar. Desktop shell only. |
| Cancel inside formula analysis | M | `Scanner.scan` is one call. A cancel check per model in `build_fact_graph` would make Cancel take effect within a second or two. |
| Per-source state across restarts | S | `ProjectService.source_states` is kept in memory. |

### Code structure and gates (findings 16, 21, 22)

| Task | Size | Notes |
|---|---|---|
| Split `frontend/src/App.jsx`, the rest | L | Started: the Review queue is `frontend/src/views/ReviewQueue.jsx` (loaded on demand) and the helpers more than one view uses are `views/shared.jsx`; `App.jsx` went from 2,600 to 1,850 lines. Still inside: Overview, Search, Inspector and Settings. Unit tests read `App.jsx` as text for those views (`test/ux-states.test.js`, `navigation`, `issue45`, `issue46`, `issue48…`, `issue49…`) and must read the new files when they move. |
| CSS ownership | M | `frontend/src/app.css` is one file with appended blocks; move each view's rules beside its component. |
| One list behaviour | M | Search results, the object tree, the review queue and relationship lists each have their own keyboard handling and row markup. |
| Screenshot comparison | M | None yet. |

## Known state of the test suites

Failures listed here were present before this work started and are unchanged, unless stated.

| Suite | Command | State |
|---|---|---|
| Frontend unit | `cd frontend && npm test` | 334 pass, 0 fail. |
| Backend | `python -m unittest discover -s tests` | 892 tests, all pass (the 40 earlier failures were fixed on main before this work resumed). |
| Browser, core specs | chat, desktopAudit, graph, graphExplorer, graphSession, modelSummary, overhaul, palette, product, productRefinement, sharedFixes, a11yViews, reviewGroups, reviewLayout, routes | 42 of 83 fail in one combined run. See the note on order below. |
| Browser, Merge | devcenter-row, -compare, -a11y, -shell, -plan | The same 6 failures in compare and plan before and after the Clear filters change. Other `devcenter-*` specs were not re-run. |
| Browser, new specs | a11yViews, reviewGroups, reviewLayout, routes, reviewSelection, scanBackground | All pass when run together without the older specs. |

Order matters in the core run: two `overhaul.spec.js` tests swap in another project and restore the
fixture in a `finally`, but they time out at one minute, so the restore can be skipped. Specs after them
(`routes.spec.js`, the auto-accept test in `reviewSelection.spec.js`) then see the wrong project and fail,
though each passes on its own. Fixing those two time-outs, or restoring the fixture in an `afterEach`, fixes them.

The pre-existing failures have not been triaged. That is a task of its own: many look like tests that
were not updated after earlier redesigns (for example a tab renamed to "Lineage flow").

## Working notes

- Browser tests serve `frontend/dist`. Do not rebuild it while a run is in progress.
- A full Merge browser run takes 10–20 minutes because failing tests wait for their time-out.
- `trail check` reports the same false conflicts on every commit of this branch: rows of the fix-status
  table (finding numbers read as values), `GraphView.jsx` (the node list is not filtered on selection)
  and `tests/test_api_answer_cache.py` (it tests the answer cache, not gzip). Say so in the commit message.
- Review grouping switches on above 200 suggestions. A test that expects `.review-item` rows on a larger
  fixture must choose "No grouping" first.
- The Merge row detail is docked under the grid from 1100 × 720 px; below that it is still an overlay.
