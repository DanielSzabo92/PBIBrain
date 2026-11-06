---
title: "Two e2e flakes: axe sampling a tab fade-in, and the DevCenter menu focus test"
author: Claude (impeccable UI audit)
date: 2026-11-06
branch: claude/ui-audit-impeccable
id: l-ui-audit-e2e-flakes
scope: repo
status: active
touches:
  - frontend/src/app.css
  - frontend/e2e/devcenter-plan.spec.js
  - frontend/e2e/devcenterParts.spec.js
  - frontend/e2e/axe.js
---

## Watch out
- `devcenter-plan.spec.js` "axe has zero violations…" runs axe right after clicking the Plan tab. While `.ui-tabs-content` faded in (200ms opacity animation), axe read half-faded text as about 4.2–4.49:1 contrast. Tab panels now switch without animation (`app.css` near line 118). If you add an entrance animation back to tab panels, this test will flake again.
- `e2e/axe.js` `setTheme` only adds an init script. It does not reload, so the theme takes effect on the next `page.goto`. A failure labelled "(dark)" can really be the light theme.
- `devcenterParts.spec.js:225` (menu: Escape returns focus to the trigger) failed 3 of 4 times on the untouched baseline (commit 283345b). It is a pre-existing flake, not a regression.
- `graph.spec.js:196` expects at least one `[data-slot="card"]` on Overview. Build Overview containers from the shared `Card` primitive, not plain `<section>`.
