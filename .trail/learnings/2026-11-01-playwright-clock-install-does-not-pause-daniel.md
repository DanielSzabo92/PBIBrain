---
title: "Playwright clock.install() does not pause time, so a timed UI test is flaky until it calls pauseAt"
author: Daniel
date: 2026-11-01
branch: claude/dev-center-build-6abbf2
cost: { minutes: 18, tokens: 24646 }
id: l-f88a2cf8
scope: repo
status: active
touches:
  - ".scratch/dev-center-build/issues/09-s11-cloud-read.md"
  - frontend/e2e/devcenterParts.spec.js
---

## Decided
- In `frontend/e2e/devcenterParts.spec.js`, a timed spec installs the fake clock at a fixed time and calls `page.clock.pauseAt(...)` after the page loads, because `clock.install()` lets real time move on and a toast went away before the `hover()` came.
- A size check of a part with an open animation waits for `getAnimations()` to finish and reads the computed width, because `boundingBox()` during `sheet-in` gave 400.00006 px.

## Watch out
- `clock.install()` also stops animation frames, so `hover()` waits for ever for a stable element; use `{ force: true }`.
- A modal Radix overlay sets `aria-hidden` on the page behind it, so axe on the full page reports `aria-hidden-focus`. Run axe inside the open overlay.
- The kit state gate reads the hidden "on" value of a Radix Checkbox or Switch as text, so an unchecked checkbox uses `text` color.
- Radix Slot merges child props last: a child `id={undefined}` removes the id of `Dialog.Title asChild`, and the dialog has no name.
- `verify_focustrap` loads the snapshot from `file://`, where module scripts do not run; build the specimen as one inline IIFE (`.scratch/dev-center-build/gates/u1/`).
