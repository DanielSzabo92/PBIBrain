# Handoff: state after the adversarial product review work

Branch: `claude/vibrant-franklin-h8aafq` (the review branch `claude/product-adversarial-review-wid901` merged in; everything below is pushed; no PR is open).

The review is in `docs/adversarial-review/`: one file per finding (01–22) with evidence, solution and
acceptance criteria. The fix-status table in `docs/adversarial-review/README.md` says what was done for
each finding and what each fix measured; its last rows are this branch's work.

## What this branch did

| Area | What was done |
|---|---|
| Review queue | Row selection, server-side bulk decisions with undo, auto-accept (off by default), skeleton rows while loading. Returning from an object puts focus back on the row you left. |
| Scan | Background job with Cancel; Cancel lands at once, also inside formula analysis; a full scan of the 13,731-object project takes 11.7 s (was 23.0 s); each source's scan state survives a restart. |
| Inspector and graph | Version corrections, readable visual types, report measures in a card's bindings; zoom control in the graph toolbar. |
| Merge models | Session switcher instead of the breadcrumb, numbered process steps, only the choices that apply, one filter line. The copy target says "Recommended" once. The grid has one tab stop; focus returns to a source's actions button after its dialog; the missing-source header meets 4.5:1. |
| Desktop | Recent projects on the empty start screen and in the title-bar switcher. |
| Code structure | `App.jsx` split by view into `frontend/src/views/`; `app.css` is an ordered list of per-view imports; one list behaviour (`frontend/src/listNavigation.js`). |
| Toasts and notices | Sonner toasts take the app's colours and have a close button. The status-bar notice (scan result) is `.statusbar-notice`; review decisions report in toasts. |
| Chat settings | Turning the chat on no longer resets a provider picked while that save was in flight. |
| Gates | Large-project budgets (`tools/large_project.py`, `tests/test_scale_budgets_large.py`); screenshot comparison of seven views (`frontend/e2e/visual.spec.js`) on its own server; every browser spec updated to the current UI and passing. |
| Cleanup | Dead CSS and imports, the placeholder "tab not ready" screen of Merge, unused copy keys it and the old remove button used, the review's one-off large-project server (superseded by `tools/large_project.py`). |

## Decisions a reader may question

- **No server paging of the review view.** The slim snapshot opens in about 1 s on the large project, and grouping by pattern needs every item on the page. A bulk decision sends the chosen identifiers in one write, so a server-side filter would save nothing.
- **No lineage layout worker or scroll scrubber.** Folded lineage opens in about 1 s on the large project; a worker would not be felt.
- **No drop zone.** A browser cannot read a dropped file's path. It needs the desktop window's own drop event; Browse ("Add sources") covers the need today.
- **Auto-accept is off by default.** It changes what "reviewed" means, so a project opts in.
- **Version corrections live in the project file**, not the override file: an override on a model marks it "Edited" everywhere.
- **Expanding a group refits the picture when it fits** (deliberate since commit 2a73b29).
- **The chat shares the merge session only from the Merge view**, and only then offers the merge tools (`frontend/src/chat.js`).
- **Apply is always styled destructive** (it writes files); Format is the only plain confirm.

## Still open

- Drop zone for sources (desktop shell, see above).
- The "Open" notes in the fix-status table that no later row closes (for example a path list in the graph pane, a split search preview, per-type object pages for tables and models).
- Merge copy keys that look unused (about 180, mostly the cloud and pull flows) were left alone: many are built at run time from codes, so they need checking one by one.

## Test suites

| Suite | Command | State |
|---|---|---|
| Frontend unit | `cd frontend && npm test` | 338 pass. |
| Backend | `python -m unittest discover -s tests` | 895 tests, all pass. |
| Browser | `cd frontend && npm run build && npx playwright test` | 272 tests, all pass on fresh servers (about 6 minutes). |

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
