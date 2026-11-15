---
title: "Before rewriting a failing browser test, check the UI change was deliberate; many were real defects, and order problems come from the shared server or 40 ms fo…"
author: Claude
date: 2026-11-15
branch: claude/vibrant-franklin-h8aafq
cost: { minutes: 1, tokens: 693 }
id: l-5810ea49
scope: repo
status: active
src: agent
touches:
  - frontend/e2e/graphExplorer.spec.js
  - frontend/e2e/visual.spec.js
  - frontend/playwright.config.js
  - frontend/src/App.jsx
---

## Decided
- Browser specs that fail after a redesign are updated to the current UI only after checking the change was deliberate (git log of the component, a comment saying so). Several "test failures" were real defects and were fixed instead: a save reply overwriting newer form edits, focus lost after a dialog opened from a menu, several tab stops in one grid, toast text below 4.5:1.
- The screenshot comparison runs on its own graph server (port 8768): other specs approve suggestions and rescan on 8765, which changes the counts in the pictures.

## Tried and ruled out
- Reading a failing spec's order problem as a product bug: a test that passes alone and fails in the full run is almost always state left on the shared 8765 server, or a timing race below.

## Watch out
- Sonner mounts a toast from a timer: with page.clock paused, move it on (runFor(1), or poll runFor until the toast shows when a request comes first). The newest toast is .first(), not .last().
- Every view takes focus 40 ms after it opens (App.jsx view-change effect; it now leaves focus alone when the view already put it inside main). Read focus and the focus ring in one evaluate, or wait for the view first.
- The graph pans or refits 40 ms after a selection, an expand or the pane docking, then animates; wait until the viewport transform holds still before the next key or double-click.
- The reduced-motion rule sets 0.001 ms, which getComputedStyle reports as 1e-06s; count only longer durations as motion.
- A server reused from an earlier local run keeps its state; stop it for a clean run.

In the code: frontend/e2e/graphExplorer.spec.js `still`, frontend/e2e/visual.spec.js, frontend/playwright.config.js `visualWebServer`, frontend/src/App.jsx view-change focus effect, frontend/src/styles/base.css reduced-motion block.
