---
title: The search page lists project objects only and folds copies in the browser; the search API for agents is unchanged
author: Claude
date: 2026-11-13
branch: claude/product-adversarial-review-wid901
cost: { minutes: 19, tokens: 289994 }
id: l-ae82a686
scope: repo
status: active
src: agent
touches:
  - backend/api/app.py
  - backend/desktop/host.py
  - docs/adversarial-review/README.md
  - frontend/src/App.jsx
  - frontend/src/app.css
  - frontend/src/components/GraphView.jsx
  - frontend/src/components/ObjectContextPreview.jsx
  - frontend/src/components/ReviewDecision.jsx
  - frontend/src/graphLayout.js
  - frontend/src/lineage.js
---

## Decided
- The Search page asks `/api/search?kind=objects`, which leaves out the semantic layer (ids starting `semantic:`: aliases, concepts, assertions). Without it every measure appeared twice, alias first. The parameter is opt-in so MCP tools and agents that call `/api/search` keep getting everything; an explicit `object_type` always wins.
- Copies of one object across models or reports are folded in the browser (`foldSearchResults`: same type and name, each copy in a different model or report), per loaded page. Objects with the same name inside one model stay separate rows.
- The theme follows the operating system until the user picks one (no saved value = system). The e2e config pins `colorScheme: "dark"` because headless Chromium reports light and the suite was written against the dark theme.
- The address of the current view lives in the URL hash (`routes.js`). A move to another view or object pushes a history entry; typing a query, changing a settings tab or refocusing the graph replaces it.
- Models fold as versions only when their names agree apart from a version marker (`versionStem`) and half of the smaller one's objects match. Structure alone folded eight different models stamped from one template into "×8".

## Tried and ruled out
- Removing aliases from `/api/search` for every caller: agents use that route to find aliases on purpose.
- A backend `/api/tree` route for the Inspector tree: the compact lineage payload the graph already loads has every object and CONTAINS edge, so the tree is built from it in the browser (`objectForest`, `treeRows`) and drawn windowed.

## Watch out
- A static import of anything that imports `@xyflow/react` or dagre pulls the 230 kB graph chunk into the first load. `ImpactExplorer` did that from `App.jsx`; it is lazy now. Check `dist/index.html` modulepreload links after touching imports in `App.jsx`.
- `DevCenter` is lazy; the shell reads the open merge session from `devcenter/sharedStore.js`, which must stay free of imports.
- Do not rebuild `frontend/dist` while Playwright runs: the e2e servers serve that folder.

In the code: backend/api/retrieval.py `retrieve_objects(project_objects_only=)`, frontend/src/transport.js `search`, frontend/src/presentation.js `foldSearchResults` / `matchSnippet`, frontend/src/routes.js, frontend/src/versions.js `versionStem`, frontend/src/objectTree.js, frontend/src/components/ObjectTree.jsx, frontend/vite.config.js `manualChunks`.
