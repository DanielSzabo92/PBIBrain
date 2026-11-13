# PBIBrain — adversarial product review

Date: 2026-11-12 · Reviewed: `main` at `57c06fb`, production build of `frontend/`, real backend.

## Verdict

PBIBrain is a careful product at demo size and **not usable at enterprise size**. With a few thousand objects the first screen takes 11–14 s, the Review queue freezes the window for about two minutes, the Graph opens on a meaningless sample, and the Overview states things that are false. Separately, the command palette ships unstyled. The visual system (tokens, contrast, type icons, provenance language) is a good base; what is missing is scale, truthfulness of status, an object tree, and restraint in copy.

Fix order: **01–05** (trust and speed), then **06–09** (the graph and review surfaces), then **22** so it stays fixed, then the rest.

## How it was tested

- **Large project:** 8 models, 24 reports, 240 tables, 4,320 columns, 2,400 measures, 144 pages, 1,440 visuals → 13,731 objects, 41,942 relationships, 11,528 review items. Generated and served by `evidence/large_project_server.py` through the real scanner, repository and API (scan time 21 s).
- **Empty project** through `brain serve` (first-run experience).
- **Merge models** on the e2e fake server (`tests/devcenter_ui_server.py`); the real merge engine needs the desktop shell and Microsoft's model library and was not exercised.
- Headless Chromium at 1440×900 and 1024×700, dark theme; timings from Playwright request timing and `PerformanceObserver("longtask")`.
- Not covered: light-theme visual pass, the packaged desktop app, cloud sources, the chat with a live provider, PBIP/TMDL input at scale (the large fixture uses the JSON source format), screen readers.

## Findings

| # | Problem | Severity | Criteria |
|---|---|---|---|
| [01](01-review-queue-freezes-on-large-projects.md) | Review queue downloads 163 MB and freezes for ~2 min | P0 | performance |
| [02](02-command-palette-renders-unstyled.md) | Command palette (Ctrl+K) renders unstyled, shows raw ids | P0 | look, ease |
| [03](03-first-load-takes-11-seconds.md) | First load 11–14 s; overview recomputed per request | P0 | performance |
| [04](04-single-threaded-server-blocks-the-ui.md) | Single-threaded server: one slow request blocks all | P0 | performance |
| [05](05-overview-states-things-that-are-false.md) | Overview claims "no measures", "clean", "no issues" when not loaded | P0 | goals, trust |
| [06](06-graph-opens-on-an-arbitrary-slice.md) | Graph opens on 80 arbitrary objects of 13,731 | P0 | goals, layout |
| [07](07-lineage-does-not-scale-past-a-few-hundred-objects.md) | Lineage is a 1,440-row strip; Fit and minimap fail | P1 | performance, navigation |
| [08](08-selecting-a-node-leaves-orphan-edges.md) | Selecting a node hides nodes but leaves loose edges | P1 | goals, look |
| [09](09-review-rows-overlap.md) | Review rows: chip overlaps text | P1 | look, layout |
| [10](10-no-deep-links-or-history.md) | No deep links, no Back, state lost on reload | P1 | navigation |
| [11](11-review-workflow-does-not-scale.md) | 11,528 one-by-one approvals; risky "Approve all" | P1 | goals |
| [12](12-search-results-are-noisy.md) | Search: duplicates first, no match context | P1 | goals, information yield |
| [13](13-inspector-needs-an-object-tree.md) | Inspector opens on a manual; no model tree | P1 | ease, information yield |
| [14](14-too-much-explanatory-text.md) | Sentences where icons, colour and layout should speak | P1 | self-explanatory UI |
| [15](15-visual-polish-gaps.md) | Polish gaps that keep it from looking premium | P2 | look |
| [16](16-bundle-and-code-structure.md) | 1.24 MB entry script; 2,277-line `App.jsx` | P2 | performance |
| [17](17-version-grouping-is-hidden-and-can-mislead.md) | Version folding merges different models silently | P2 | goals |
| [18](18-settings-and-sources.md) | Sources are truncated path inputs with no status | P2 | ease |
| [19](19-merge-models-usability.md) | Merge models: jargon, hidden columns, heavy chrome | P2 | ease, layout |
| [20](20-first-run-and-onboarding.md) | First run: empty shell, no sample, false "no issues" | P2 | ease |
| [21](21-accessibility-theme-and-window-sizes.md) | Ignores OS theme; narrow-window and keyboard gaps | P3 | ease, look |
| [22](22-no-scale-or-visual-regression-gates.md) | No scale, timing or visual tests would catch these | P1 | production readiness |

## Scorecard against the brief

| Question | Answer |
|---|---|
| Accomplishes its goals? | At demo size, yes. At thousands of objects, no: 01, 05, 06, 11. |
| Easy and obvious? | Partly. No object tree, no history, three search boxes: 10, 12, 13, 20. |
| Looks proficient, high-end, expensive? | Tidy, not premium; one broken dialog and overlapping rows: 02, 09, 15. |
| Performant with many files and thousands of objects? | No: 01, 03, 04, 07, 16. |
| Clean, navigable layout? | Shell yes; graph and lineage at scale no: 06, 07, 08, 19. |
| Self-explanatory UI with little text? | No; the UI leans on sentences: 14, 09, 18. |

## Fix status

Measured on the same 13,731-object project, before → after.

| # | State | What changed | Result |
|---|---|---|---|
| 02 | **Fixed** | Palette stylesheet matches the markup; scope shows names, not graph IDs; `e2e/palette.spec.js` guards it | Styled, one line per row |
| 03 | **Fixed** (first part) | Read-only answers kept until the graph or decisions change; overview built at server start; one shared store read per request; review-queue target lookup indexed | First content 14 s → 0.6 s; `/api/overview` 11 s → 2 ms warm; one object 1.9 s → 20 ms; graph slice 2.1 s → 0.2 s |
| 04 | **Partly** | `brain serve` answers each request on its own thread; cached answers and files skip the request lock | A cached read during a slow request: 24 s → 0.3 s. Open: the desktop host server is still serial; scan is still one blocking request; no compression (of little use on loopback, dropped from the plan) |
| 05 | **Mostly** | Most-used measures and hot unreviewed objects are computed by the server; no "None"/"Clean"/"no issues" claim without data; scan time is recorded and survives a restart | Widgets are correct on first paint. Open: "8 sources" vs "32 sources" wording, the "99+" badge |
| 01 | **Mostly** | Review screens load a slim snapshot (`/api/brain?view=review`); indexed lookups; rows mounted 50 at a time; derived lists memoised; a row no longer scans every link | 163 MB → 42 MB; ready in 137 s → ~2 s; longest freeze 99 s → 0.9 s; DOM 378k → 7k elements. Open: true server paging, bulk actions by filter on the server |
| 04 | **Fixed** (see above) | The desktop server is threaded too and builds the first answers while the window opens; `/api/health` answers without the request lock and the launchers wait for it | Open: scan is still one blocking request |
| 06 | **Fixed** | Containers reads the whole project: every model and report with counts by type, counted links between collapsed owners, expand in place with the opened owner held still; no "Showing 80 of N" | 32 owners of 13,731 objects in 0.4 s (was 80 arbitrary objects; the first version of this fix took 5 s until name ordering was fixed: 3.6 s → 60 ms) |
| 07 | **Mostly** | Lineage folds long lanes by owner above 400 objects; Fit fits the width and starts top-left; lane names stay at the top edge; wheel scrolls, Ctrl+wheel zooms; no minimap for a strip; zoom floor 20 % | 2,479 rows → 163; opens in ~1 s. Open: layout in a worker, scroll scrubber |
| 08 | **Fixed** | A link with a hidden end is hidden; on large lanes the selection's chain is packed around the selected object, which keeps its place; Esc puts everything back | Selecting a table: 76 objects and 148 links on screen, none loose. Open: path list in the pane, toolbar toggle |
| 09 | **Fixed** | Object, suggestion, source, confidence and actions each have a column; kind and source are glyphs; approve/reject are icon buttons with names and shortcuts | No two cells intersect at 1024, 1280, 1440 and 1920 px (`e2e/reviewLayout.spec.js`) |
| 05 | **Fixed** | Counts are formatted and exact ("11,528 suggestions", nav badge "11.5k"); no "99+"; hot objects and top measures name their model; "Recently changed" only when there is something | — |
| 14 | **Mostly** | View titles are in the header bar only (the h1 stays for screen readers); purpose sentences removed from Overview, Search, Review and Settings; type strip shows the main types with "+N more" | Overview content starts at 80 px instead of 240 px. Open: Inspector and Merge copy |
| 18 | **Partly** | Each source row shows a found / not found dot and the file name before the path (`GET /api/config/sources`); path example matches the platform | Eight sources are told apart at a glance; a wrong path shows before a scan. Open: browse button, per-source scan state |
| 12 | **Mostly** | Search lists project objects only (alias records left out, agents' API unchanged); copies across models fold into one row with ×N; the matching formula line is shown with the term marked; filters and count share one line with the query | "total orders": first row is the measure, once, ×8; 61 rows → 10. Open: split preview, shared engine with the palette |
| 13 | **Mostly** | The Inspector has an object tree (Model › Table › Measures, Columns; Report › Page › Visuals) with a filter, keyboard movement and windowed rows; the tutorial card is gone | 8,576 objects browsable; the selected object is revealed in the tree. Open: per-type object pages, field wells for visuals |
| 10 | **Mostly** | The view, object, search query, settings tab and graph focus live in the URL hash; Back/Forward and Alt+←/→ work; reload returns to the same place | `/#/inspector/<id>` opens that object. Open: copy-link button, links in chat answers |
| 16 | **Partly** | Merge models and the impact graph load on demand; React, Radix, icons and the graph library are separate cached files | Entry script 1,252 kB (365 kB gzip) → 341 kB (97 kB gzip). Open: splitting `App.jsx`, CSS ownership, budgets in CI |
| 17 | **Partly** | Models fold as versions only when their names agree apart from a version marker (v2, copy, DEV, a date) | Six template models are no longer "×8"; the two real v2 copies still fold. Open: honest group title, visible toggle, user correction |
| 20 | **Mostly** | "Open sample project" on the empty Overview adds a small retail model with its report and scans it; no validation claim, zero counts, "Queue is clear" or "No matching objects" before the first scan; launchers wait for the server | A populated graph in 2 clicks from a new project. Open: drop zone, scan progress by phase, recent projects |
| 11 | **Partly** | A bulk approve or reject over more than 50 suggestions asks once more and names its scope; counts are formatted | Open: auto-accept, grouping by pattern, selection model |
| 22 | **Partly** | Budget tests for overview, search and lineage on the 660-object fixture; browser tests for row overlap at four widths, deep links, the object tree and alias-free search | Open: the 13.7k fixture in CI, screenshot comparison |
| 21 | **Partly** | Theme follows the operating system until the user picks one; "Match system theme" in the View menu | A light-mode OS starts light. Open: one list behaviour |
| 21 | **Mostly** | axe runs on Overview, Search, Graph, Inspector, Review and Settings in both themes (`e2e/a11yViews.spec.js`) | 12 runs, no violations |
| 13 | **Mostly** | Object page: properties are a flat list, empty binding groups are not drawn; lane, type and group counts are formatted | No empty boxes on a visual or a measure page. Open: per-type pages, field wells |
| 11 | **Mostly** | Above 200 suggestions the queue opens grouped by pattern (rule, evidence basis, object type) with counts, distinct names and confidence; a group is approved or rejected once (asked again above 50, naming the pattern) or opened to decide rows one by one; "Approve all" is not offered beside pattern decisions (`e2e/reviewGroups.spec.js`) | 11,528 rows → 7 patterns on the large project; a group opens in 0.3 s. Open: auto-accept at scan time, row selection |
| 17 | **Mostly** | A "Versions folded" chip sits beside the lane chips whenever models or reports have versions; it names the folded groups and switches folding with one click; differing copies carry a neutral ≠ instead of a warning dot | Folding is visible from the toolbar. Open: user correction ("not versions") |
| 10 | **Fixed** | "Copy link" on the object page | Open: links in chat answers |
| 20 | **Mostly** | The scan reports its result ("Scan complete: 13,731 objects in 21 s") and the status bar counts seconds while it runs | Open: drop zone, phases, recent projects |
| 19 | **Started** | Keep / Take / Skip tooltips name the models they act on | Open: bottom detail panel, stepper, one filter line |
| 16 | **Partly** | A unit test fails the build when the entry script passes 420 kB or the stylesheet 230 kB, or when the graph library is preloaded (`test/bundleBudget.test.js`) | Open: splitting `App.jsx`, CSS ownership |
| 13 | **Mostly** | A visual's page lists its fields by well (Axis, Values, Legend, …) in report order, with the aggregation and the shown name, when the report file records roles (`field_wells` in the object answer) | Open: per-type pages for tables and models |
| 13 | **Fixed** | The page of a model, table, report or page has a Contents card: what it holds by kind, with data type or size, each row a link (`contents` in the object answer, `e2e/routes.spec.js`); the suggestion badge is no longer cut off | A model page lists its tables and relationships instead of "No description recorded" alone |

Everything else is open.

## What is already good (keep)

Token system and contrast-checked themes · one icon and colour per object type · provenance as line style · docked graph pane and no-flicker selection · Field usage matrix (dense, readable, the best view at scale) · menu bar and status bar · Merge compare grid and guarded apply · Undo on review decisions.
