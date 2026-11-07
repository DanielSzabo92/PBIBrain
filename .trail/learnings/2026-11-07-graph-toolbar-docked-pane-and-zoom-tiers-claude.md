---
title: "The graph pane overlays for one double-click window before it docks, and graph session updates must keep the stored object on a no-op"
author: Claude (graph readability redesign)
date: 2026-11-07
branch: claude/affectionate-fermi-rgourh
id: l-graph-dock-noop
scope: repo
status: active
touches:
  - frontend/src/components/GraphView.jsx
  - frontend/src/components/GraphDetails.jsx
  - frontend/src/app.css
---

## Decided
- The details pane is an `<aside>` docked beside the canvas, not a dialog. In e2e tests, find it with `.graph-detail-pane`, not `getByRole("dialog")`. Toolbar popovers (Types, Display, Filters) are Radix popovers, so they have role `dialog`.
- Containment shows as quiet tree lines, not nested frames. Frames would move existing nodes when a group expands, and `graphExplorer.spec.js` requires stable positions.
- Node text shows a middle-shortened name (`middleEllipsis`, measured with canvas). The full name stays in an sr-only span, so `filter({ hasText })` still finds the node at any zoom.

## Watch out
- The pane must overlay the canvas, with `pointer-events: none`, for about 350ms before it docks. If it docks at once, the canvas shrinks under the pointer, and the second click of a double-click (Show connections) lands on the pane.
- `updateSession` must return the stored session when an update changes nothing. Before, it returned a fresh normalized copy, so `savePlacements` re-rendered App on every layout pass, and the timers in the canvas effects never fired.
- Radix `Popover` triggers with `asChild` need a `forwardRef` component. Without one, the popover stays at `translate(0, -200%)`, off screen.
- At narrow widths, a `position: fixed` pane sits under the title bar and the view header. Keep it absolute inside `.graph-body`.
