# Handoff: state after the adversarial product review work

Branch: `claude/vibrant-franklin-h8aafq` (the review branch `claude/product-adversarial-review-wid901` merged in; everything below is pushed; no PR is open).

The review is in `docs/adversarial-review/`: one file per finding (01–22) with evidence, solution and
acceptance criteria. The fix-status table in `docs/adversarial-review/README.md` says what was done for
each finding and what each fix measured; its last rows are this branch's work.

## What this branch did

| Area | What was done |
|---|---|
| Review queue | Paged by the server (`GET /api/review/page`, `backend/api/review_page.py`); the page never loads the graph snapshot. Row selection and "select all" by filter or pattern, decided on the server with undo; auto-accept (off by default); skeleton rows while loading. Rows load as the list's end comes into view, are memoised, mount a few per frame and are not laid out off screen. Returning from an object puts focus back on the row you left. |
| Server | Answers and UI files over 1 kB go gzipped; the lineage payload is a third of its size; reads during a scan stay under 50 ms (previous answers while the graph is published, garbage collection paused for the scan, file changes read without the request lock, the JSON store written a record at a time). |
| Scan | Background job with Cancel; Cancel lands at once, also inside formula analysis; a full scan of the 13,731-object project takes 11.7 s (was 23.0 s); each source's scan state survives a restart. |
| Inspector and graph | Version corrections, readable visual types, report measures in a card's bindings; zoom control in the graph toolbar; the selection's chain as a path list in the pane and a "Trace on select" toggle; a scroll scrubber for tall lineage; relationship lists named from the object answer (`neighbors`). |
| Search and chat | Preview beside the results from 1280 px; one search for the palette and the page; object names in chat answers are links. |
| Merge models | Session switcher instead of the breadcrumb, numbered process steps, only the choices that apply, one filter line. The copy target says "Recommended" once. The grid has one tab stop; focus returns to a source's actions button after its dialog; the missing-source header meets 4.5:1. |
| Desktop | Recent projects on the empty start screen and in the title-bar switcher; source files dropped on the window are added. |
| Code structure | `App.jsx` split by view into `frontend/src/views/`; `app.css` is an ordered list of per-view imports; one list behaviour (`frontend/src/listNavigation.js`). |
| Toasts and notices | Sonner toasts take the app's colours and have a close button. The status-bar notice (scan result) is `.statusbar-notice`; review decisions report in toasts. |
| Chat settings | Turning the chat on no longer resets a provider picked while that save was in flight. |
| Gates | Large-project budgets (`tools/large_project.py`, `tests/test_scale_budgets_large.py`); screenshot comparison of seven views (`frontend/e2e/visual.spec.js`) on its own server; every browser spec updated to the current UI and passing. |
| Copy | Inspector, Merge and Settings sentences removed; `frontend/e2e/copyBudget.spec.js` holds every view to at most two long text runs. |
| Cleanup | Dead CSS and imports; the placeholder "tab not ready" screen of Merge; 151 unused Merge copy keys (cloud sign-in, pull and test flows, `shared.network.*` duplicating `error.network.*`); the client's snapshot loading (`normalizeSnapshot`, `dataCounts`, `linksOf`, `reviewGroups.js`), replaced by server pages; `view=review` on `/api/brain`; the review's one-off large-project server (superseded by `tools/large_project.py`). |

## Decisions a reader may question

- **The lineage layout runs on the main thread.** Finding 07 suggested a worker. Copying the 30,000-object graph to a worker and back costs 30 + 40–60 ms of main-thread time, as much as the work it would move; the folded layout takes 3 ms and the longest task while Lineage opens is 144–173 ms, under the 200 ms budget.
- **Lineage edges have no id on the wire.** Every lineage edge is factual and unique by type and ends; the client names it `type|from|to` (`frontend/src/transport.js`). The random ids were a third of the gzipped transfer.
- **Garbage collection pauses during a background scan** and its last pass waits for 2 s without requests (`start_scan` in `backend/api/app.py`). Collection over the scan's objects stopped every thread for 0.2–0.7 s about 17 times per scan; memory grows 14 MB without it.
- **Auto-accept is off by default.** It changes what "reviewed" means, so a project opts in.
- **Version corrections live in the project file**, not the override file: an override on a model marks it "Edited" everywhere.
- **Expanding a group refits the picture when it fits** (deliberate since commit 2a73b29).
- **The chat shares the merge session only from the Merge view**, and only then offers the merge tools (`frontend/src/chat.js`).
- **Apply is always styled destructive** (it writes files); Format is the only plain confirm.

## Still open

Nothing. Every finding's last row in the fix-status table is Fixed, with the measurement against its acceptance criteria.

## Test suites

| Suite | Command | State |
|---|---|---|
| Frontend unit | `cd frontend && npm test` | 335 pass. |
| Backend | `python -m unittest discover -s tests` | 909 tests: 906 pass, 3 skipped. |
| Browser | `cd frontend && npm run build && npx playwright test` | 280 tests, all pass on fresh servers (about 6 minutes). |

## Working notes

- Browser tests serve `frontend/dist`. Rebuild before a run, never during one.
- Specs share the graph server on port 8765 and change its state (approvals, rescans, settings); an order problem shows as a test that passes alone. The screenshot spec has its own server (8768) for that reason, the chat spec has 8767, Merge specs use the fake on 8766.
- A locally reused server keeps the state of earlier runs; stop it (`pkill -f tests.graph_ui_server`) for a clean run.
- Sonner mounts a toast from a timer, so a test with a paused clock moves it on (`page.clock.runFor(1)`); the newest toast is `.first()`.
- Every view takes focus 40 ms after it opens, and the graph pans or refits 40 ms after a selection or a dock change; tests wait for that before the next key (`still()` in `e2e/graphExplorer.spec.js`).
- The reduced-motion rule sets durations to 0.001 ms; count a duration as motion only above that.
- xyflow's stylesheet loads with the graph chunk after the app CSS; theme it through its variables.
- After an intended visual change: `npx playwright test e2e/visual.spec.js --update-snapshots`, and look at the pictures before committing them.
- `trail check` reports word matches in this file and in backend code from earlier commits as conflicts; say so in the commit message.
