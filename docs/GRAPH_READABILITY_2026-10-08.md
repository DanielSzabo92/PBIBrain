# Graph readability — 2026-10-08

The project graph starts with readable, collapsed ownership groups instead of fitting every object and relationship onto the canvas. Expand a report, page, table or other owner to inspect its contents, then follow one object's connections.

## Behavior

- **Overview:** models start open; other owners start folded. Group controls show the number of loaded descendants. Counts distinguish visible objects, collapsed contents and the loaded slice. Missing parents in search/filter results leave matching objects visible.
- **Connections:** double-click an object or choose Connections after selecting it. Expand connections adds another relationship level, up to four. Back to project returns to the previous overview or full graph.
- **Full graph:** retains the existing complete loaded graph, optional ownership regions, relationship filters, labels and suggestions.
- Ownership determines overview placement. Model/report scope links remain visible. A report's canonical `USES_MODEL` arrow still points to its model; placement puts the model before the report. Reports are not counted as model contents.
- Explicit relationship filters keep their matching connections visible in Overview; relationship labels remain available.
- Expanding groups preserves existing card coordinates and zoom. Recent viewports and overview placements remain in the in-memory graph session, including after an Inspector visit. New nodes use available space without overlapping surviving cards.
- Group buttons support keyboard activation without selecting the enclosing object. Names remain readable at the initial overview zoom. Existing theme tokens, palettes, warning states, React Flow and Dagre are reused.
- Fixed card dimensions remain attached to controlled React Flow nodes when session state changes, preserving their measured handle bounds and rendered connections.

The design remains restrained: variance 3/10, motion 2/10, density 7/10. No dependency or factual graph/API change was needed.

## Files

- `frontend/src/components/GraphView.jsx`: modes, expansion controls, session state and viewport behavior.
- `frontend/src/graphLayout.js`: safe presentation forest, loaded-descendant counts, ownership placement and anchored expansion.
- `frontend/src/app.css`: graph toolbar, group controls and readable overview labels.
- `frontend/test/graphLayout.test.js` and `frontend/e2e/graphExplorer.spec.js`: meaningful hierarchy, direction, overlap, interaction and session checks.
- Existing graph, graph-session and overhaul browser tests explicitly choose Full graph where their assertions require every loaded object.
- `tests/test_phase4_inspector_contract.py`: graph import assertion accepts the existing lazy import as well as a static import.
- `frontend/playwright.graph-readability.config.js`: isolated local test port 8875; leaves the existing preview on 8765 alone.

Existing unrelated working-tree edits were preserved.

## Verification

- Production frontend build: passed. Existing `use client`/sourcemap build warnings remain.
- Frontend unit tests: 31 passed.
- Native hierarchy and Inspector contract tests: 24 passed.
- Full browser suite: 46 passed; see `evidence/graph-readability-2026-10-08/browser-tests.log`.
- Final graph checks after explicit-filter refinement: 6 passed; see `evidence/graph-readability-2026-10-08/graph-explorer-final.log`. These cover native ownership expansion, stable coordinates/zoom, keyboard controls, Inspector return, canonical connection direction, dense overview/full-graph switching, narrow screens and relationship filters. Five also ran in the full suite; the relationship-filter check was added afterward.

Reviewed screenshots: `evidence/graph-readability-2026-10-08/graph-overview.png`, `graph-dense-overview.png` and `graph-explorer-mobile.png`.

Browser checks use the production frontend build with the native persisted fixture server. The dense overview test uses an explicitly mocked 80-object slice of 400 matching objects. Screenshots are renderer evidence, not validation of the user's original project or an installed desktop package. The installed package was not rebuilt.
