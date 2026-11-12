# 22 · Nothing in the test suite would have caught any of this

**Severity:** P1 (process) · **Criteria:** production readiness

## Evidence

- All e2e fixtures are tiny: the graph server builds 1 model, 1 table, 2 columns, 2 measures, 1 report (`tests/graph_ui_server.py`); the earlier UI audit used 97 objects. Every problem in 01, 03, 04, 06, 07, 08 and 11 appears only above a few thousand objects.
- No test opens the command palette's layout (02), and no test compares screenshots, so an unstyled dialog and overlapping rows (09) pass CI.
- Source-grep tests (`frontend/test/issue45.test.js`, `issue46.test.js`) pin implementation strings such as `flow?.fitView`; they guard code shape, not behaviour, and will fight the refactors proposed here.
- There are no timing or payload assertions anywhere.

## Solution

1. **A large fixture in the repo's test tooling.** Promote the generator used for this review (`docs/adversarial-review/evidence/large_project_server.py`: 8 models × 30 tables × 18 columns × 300 measures, 24 reports × 6 pages × 10 visuals → 13.7k objects, 42k relationships) to `tests/large_project.py`, parameterised (`--scale 1|5|20`). Add a second, PBIP/TMDL-based variant so the real reader is exercised.
2. **Backend budgets (pytest, marked `perf`):**

   | Endpoint | Budget at 13.7k objects |
   |---|---|
   | `/api/overview` | 100 ms warm |
   | `/api/search` | 100 ms |
   | `/api/objects/<id>` | 50 ms, 20 kB |
   | `/api/review?limit=100` | 150 ms, 100 kB |
   | `/api/graph/summary` | 100 ms, 50 kB |
   | `/api/lineage` | 1.5 s, 600 kB gzip |
   | project scan | 30 s |

3. **Frontend budgets (Playwright against the large server):** per view, time to first content, longest task (`PerformanceObserver('longtask')`), DOM element count (< 5,000), JS heap. The script used here (`walk3.cjs` pattern) is ~60 lines.
4. **Visual regression:** `expect(page).toHaveScreenshot()` for each view, the palette, one popover, the pane and one dialog, dark and light, on the small fixture (stable data). Review diffs in PRs.
5. **Layout invariants** that do not need pixels: no two cells of a row intersect; no text node is clipped without a `title`; every `className` used in JSX has a rule (see 16).
6. **Replace source-grep tests** with behaviour tests ("selecting a node does not change the viewport transform", "no node position changes on select").
7. **CI stages:** unit → e2e small → perf (large, nightly and on `perf` label) → bundle budget (16).
8. **In-app diagnostics** for the field: Help › Diagnostics shows graph size, last scan duration, slowest endpoints of the session, with "Copy report".

## Acceptance

- Reverting any fix from 01–09 makes at least one automated check fail.
