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

## What is already good (keep)

Token system and contrast-checked themes · one icon and colour per object type · provenance as line style · docked graph pane and no-flicker selection · Field usage matrix (dense, readable, the best view at scale) · menu bar and status bar · Merge compare grid and guarded apply · Undo on review decisions.
