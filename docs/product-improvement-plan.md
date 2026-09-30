# Product improvement plan

Purpose: shorten the path from finding a Power BI object to understanding it.
Implement each step in order, in the main task. Preserve React Flow, saved
appearance, source data, and the existing review contracts.

1. **Useful home screen.** Put project search first for scanned projects. Show
   compact counts, scan freshness, and one route to the review queue. For an
   empty project, lead with source setup or scanning. Remove storage jargon and
   repeated empty review panels. Source settings open on the Project tab.
2. **Search without losing place.** Retain query, scope, loaded results, and
   position when inspecting an object. Provide a return action. Append later
   result pages; show loading, retry, and filter reset states. Never show a
   previous query's results as a new query's matches.
3. **Readable object details.** Lead with description and a readable formula.
   Show dependencies and direct consumers with human names. Keep technical
   metadata available in disclosures; show evidence and review only when
   present. Distinguish loading/failure from an empty relationship list, and
   make relationships beyond the first ten reachable.
4. **Acceptance.** Build the frontend; run relevant existing contracts and new
   browser workflow checks against the isolated native scan/reopen HTTP server.
   Inspect desktop and narrow screenshots, keyboard navigation, empty/error
   states, pagination, and stale responses. Refresh the context graph. Rebuild
   the portable Windows app with the verified frontend, then run the frozen
   native scan/reopen check.

## Completion

All four steps completed sequentially.

- Frontend production build passed. All 19 existing Node tests passed.
- All 14 browser tests passed against the real HTTP API over an isolated native
  project, including seven new product workflow tests. Coverage includes saved
  search position/focus, pagination and page retry, stale responses, scope
  reset, explicit refresh, object failure/retry, more than ten relationships,
  source setup, and narrow screens with reduced motion.
- The 18 Inspector contract checks passed (one source-parser check required
  restoring the file's LF line endings and was then rerun successfully).
- Reviewed screenshots at 1440px and 390px; no horizontal page overflow in the
  tested home, search, and Inspector flows. Existing graph and color tests pass.
- Rebuilt `dist/PBIBrain/PBIBrain.exe` and
  `dist/PBIBrain-Portable-x64.zip`. The packaged frontend matches the verified
  build byte for byte. Frozen native scan/close/reopen passed: 17 nodes, 23 edges.
- Refreshed the Graft context graph; `git diff --check` passed.

Limits: the native desktop window and installer were not manually tested.
Dependency lists show recorded direct links, not transitive impact or proof
that an object is unused. An unavailable scan timestamp stays explicitly unknown.
