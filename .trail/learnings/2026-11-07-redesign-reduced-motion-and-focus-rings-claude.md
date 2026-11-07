---
title: "The redesign keeps reduced motion fully static and input focus rings 2px, because the e2e audits require both"
author: Claude (visual contract redesign)
date: 2026-11-07
branch: claude/affectionate-fermi-rgourh
id: l-redesign-motion-focus
scope: repo
status: active
touches:
  - frontend/src/app.css
  - frontend/src/graphPresentation.js
  - docs/design/visual-contract.md
---

## Decided
- The binding visual contract is `docs/design/visual-contract.md`. Ink is the only accent. Hue means only object type (glyph + colour from `src/objectIcons.js`) or status.
- The contract's 5s review Undo was not built. Approve and reject have no reverse action in the backend (`backend/api/app.py` `apply_review`), so a real Undo needs a backend "reopen" action first.

## Watch out
- The contract allowed short colour fades under reduced motion, but `e2e/devcenter-a11y.spec.js` (A15) fails on any running transition. Reduced motion must set every transition and animation to 0s.
- The same spec's focus walk needs an outline of at least 2px, or a box-shadow on the element itself. A 1px inset outline or a glow on a wrapper fails.
- `e2e/devcenterParts.spec.js` "Menu: keys open…" still fails about half the time on the untouched baseline.

In the code:
- `frontend/src/app.css`: the `prefers-reduced-motion` block and `.ui-input:focus-visible`.
- `frontend/src/graphPresentation.js`: `DEFAULT_PALETTE` and `lightVariant()`.
