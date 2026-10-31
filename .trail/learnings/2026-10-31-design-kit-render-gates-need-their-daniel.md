---
title: "Design kit render gates need their own npm install, and the state gate drops hover alpha"
author: Daniel
date: 2026-10-31
branch: docs/dev-center-spec
cost: { minutes: 1, tokens: 1711 }
id: l-bd8778b4
scope: repo
status: active
touches:
  - ".scratch/dev-center-ui/issues/01-render-gates.md"
---

## Decided
- Run the design kit render gates on the app through the scripts in `.scratch/dev-center-ui/gates/`, because the kit gates read only static HTML files and the app needs its fake API server.

## Watch out
- The kit render gates print SKIPPED when the kit folder has no `node_modules`, because they import `playwright` from the kit folder. `frontend/node_modules` does not help. Run `npm install` in the kit folder first.
- `verify_states.mjs` reads a hover background color without its alpha, so a hover with `var(--ok-soft)` or `var(--bad-soft)` fails with a false 1.00:1. Measure such a hover in the live page.
- A static snapshot with `<base href>` to the fake server fails with 2.23:1 on every page, because the kit gates do not load the linked CSS. Inline the CSS, as `snap.mjs` does.

In the code:
- Kit: `C:/Users/Daniel/.claude/plugins/local/ux-ui-agent-skills/` (version 3.0.0, playwright 1.63.0, axe-core 4.10.2).
- Gate scripts: `.scratch/dev-center-ui/gates/measure_app.mjs`, `snap.mjs`, `theme_contrast.py`.
- Full results: `.scratch/dev-center-ui/issues/01-render-gates.md`.
