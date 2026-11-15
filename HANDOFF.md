# Handoff: remaining work from the adversarial product review

Branch: `claude/product-adversarial-review-wid901` (everything below is pushed; no PR is open).

The review is in `docs/adversarial-review/`: one file per finding (01–22) with evidence, solution and
acceptance criteria. The fix-status table in `docs/adversarial-review/README.md` says what was done for
each finding and what each fix measured. This file lists only what is still open.

## Remaining tasks

Ordered by value to a user of a large project. Sizes are rough: S = hours, M = a day or two, L = several days.

### Review queue (findings 01, 11)

| Task | Size | Notes |
|---|---|---|
| Auto-accept suggestions that need no judgement | M | Suggestions derived from the object's own name or description above a threshold (default 90 %) are stored as accepted automatically, reversible, and never enter the queue. Changes what "reviewed" means, so it needs a setting (Settings › Review) and its own provenance mark. Start in `backend/api/review.py` (`get_review_queue`) and the scanner's `preserve_review_statuses`. |
| Row selection | S | Header checkbox and "Approve N selected" next to the per-pattern buttons. `ReviewQueue` in `frontend/src/App.jsx`. |
| Server paging of the review snapshot | L | Deliberately not done. The snapshot is 42 MB on the 13,731-object project but opens in about 1 s, and grouping by pattern counts every item on the client. Only worth doing if pattern counts move to the server first. See the learning "A long review queue opens grouped by pattern". |
| Bulk decisions on the server | M | A bulk approve still posts from the client. One request with a filter and one undo token would be faster and atomic. |

### Merge models (finding 19)

| Task | Size | Notes |
|---|---|---|
| One filter line | S | The chip row ("State: not same ×", "Clear filters") repeats the State select. Five browser tests in `frontend/e2e/devcenter-*.spec.js` use the chips; change them together. |
| Offer only the choices that apply | M | The row detail lists six options, two disabled with a reason. `e2e/devcenter-row.spec.js` asserts the disabled radios exist (lines ~203–225, 511, 606), so this is a contract change, not a style change. |
| Process stepper | M | Sources → Compare → Impact → Plan → Apply as a progress strip with counts. Today the step tabs are only set apart from the tool tabs by a divider (`TOOL_TABS` in `frontend/src/devcenter/screens/WorkArea.jsx`). |
| Header action | S | Merge shows "Change project" where every other view shows "Scan sources". |
| Breadcrumb | S | "Merge models › session › tab" repeats the sidebar, the title and the tab. The first crumb is the only way back to the session list, so replace it with a session switcher before removing it. |

### Inspector and graph (findings 13, 17, 15, 07)

| Task | Size | Notes |
|---|---|---|
| "Not versions" correction | M | Let the user say two models are not versions of each other (or are), stored in the project overrides. Folding is in `frontend/src/versions.js` (`versionFamilies`); the chip is in `frontend/src/components/LaneChips.jsx`. |
| Folded group title | S | A folded model is titled by its first member. Use the common stem ("Sales Analytics · 2 versions"). |
| Dependencies repeat the field wells | S | On a visual's page the fields appear under Axis / Values and again under Dependencies. |
| Readable visual type | S | "barChart" is shown raw in Definition and in the Contents rows. |
| Field wells on a real report | S | `field_wells` was checked with unit tests and stubbed data only; the bundled sample records no roles. Check it on a real PBIR report. |
| Lineage layout in a worker, scroll scrubber | M | Open items of finding 07. |
| Zoom control in the toolbar, project switcher, skeletons | S each | Leftovers of finding 15. |

### First run, settings, scan (findings 20, 18, 04)

| Task | Size | Notes |
|---|---|---|
| Drop zone and Browse | M | Needs the desktop shell: a browser cannot read the path of a dropped file. `DesktopProjectView` already has `addSources`. |
| Recent projects | S | On the empty Overview and in the title bar. Desktop shell only. |
| Per-source scan state | S | The sources list shows found / not found but not "scanned" or "failed". The phases are already reported by `GET /api/scan/status`. |
| Scan as a background job | M | The scan is still one request that holds the request lock; reads of cached answers go through, anything else waits. Phases and seconds are shown, but there is no Cancel. |

### Code structure and gates (findings 16, 21, 22)

| Task | Size | Notes |
|---|---|---|
| Split `frontend/src/App.jsx` | L | About 2,500 lines: Overview, Search, Inspector, ReviewQueue and Settings in one file. Split by view; no behaviour change. |
| CSS ownership | M | `frontend/src/app.css` is one file with appended blocks; move each view's rules beside its component. |
| One list behaviour | M | Search results, the object tree, the review queue and relationship lists each have their own keyboard handling and row markup. |
| Large fixture in CI | M | Scale budgets run on the 660-object fixture only. The 13,731-object project used for measurements was generated in a scratch folder and is not in the repository; add a generator under `tools/` and a budget test. |
| Screenshot comparison | M | None yet. |

## Known state of the test suites

Failures listed here were present before this work started and are unchanged, unless stated.

| Suite | Command | State |
|---|---|---|
| Frontend unit | `cd frontend && npm test` | 330 pass, 0 fail. |
| Backend | `python -m unittest discover -s tests` | 40 failures and 1 error before this work. Last full run: 41 failures; the extra one was the Inspector contract test, since fixed. Not re-run in full after that fix or after the later commits. |
| Browser, core specs | chat, desktopAudit, graph, graphExplorer, graphSession, modelSummary, overhaul, palette, product, productRefinement, sharedFixes | 39 of 56 fail, same as before. Not re-run after the Contents card and Merge commits. |
| Browser, Merge | devcenter-row, -compare, -a11y, -shell | 48 of 97 fail, all in the baseline (51 before; three now pass). The other `devcenter-*` specs (agent, apply, impact, plan, rules, harness, parts) were not re-run after the Merge changes. |
| Browser, new specs | a11yViews, reviewGroups, reviewLayout, routes | All pass. |

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
