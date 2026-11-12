---
title: Selecting an object on a large graph must not re-fit or re-layout the canvas
author: Claude
date: 2026-11-12
branch: claude/ticket-code-cleanup-670qia
cost: { minutes: 20, tokens: 274022 }
id: l-76b30740
scope: repo
status: active
src: agent
touches:
  - frontend/test/issue45.test.js
  - frontend/src/components/GraphView.jsx
---

## Decided
- Issue #53 (flicker and disappearing objects when selecting on a ~1,400-object graph): the canvas now re-fits only when the details pane docks or closes, never on a plain selection. On large pictures (more than 400 laid-out nodes) docking only pans the selected node into view.
- Selection is a cheap decoration pass: node/edge objects are built once per layout (`baseNodes`, `baseEdges`), and a selection only replaces the objects it changes, keeping `data` identity so React Flow skips the rest.
- In Containers (overview) view the layout uses only structural edges (`layoutEdges`); the edges a selection brings in are drawn without running dagre again.
- "Show only related on select" (Display menu, session field `relatedOnly`): hides unrelated nodes with React Flow's `hidden` instead of re-laying out, so positions stay put. Default `null` = on automatically above 400 objects.

## Tried and ruled out
- Filtering the node list on selection: changes the layout, so everything jumps — worse than the flicker.

## Watch out
- The old docked effect listed `selectedId` in its deps and called `fitView` after `reveal`, so every click while docked re-fitted the whole graph; with `onlyRenderVisibleElements` this popped nodes in and out.
- Source-grep tests (`frontend/test/issue45.test.js`, `issue46.test.js`) pin strings like `flow?.fitView`, `wasDocked`, `drawnEdges.length <= 12`.

In the code: frontend/src/components/GraphView.jsx (GraphCanvas, GraphView `layoutEdges`/`relatedOnly`).
