---
title: "Browser tests that load another project must put the fixture back in afterEach, because a timed-out test skips its finally"
author: Claude
date: 2026-11-15
branch: claude/vibrant-franklin-h8aafq
cost: { minutes: 26, tokens: 500444 }
id: l-90531838
scope: repo
status: active
src: agent
touches:
  - HANDOFF.md
  - frontend/src/App.jsx
  - frontend/src/views/ReviewQueue.jsx
  - frontend/src/views/shared.jsx
  - backend/api/app.py
  - backend/projects.py
  - docs/adversarial-review/README.md
  - frontend/e2e/devcenter-compare.spec.js
  - frontend/e2e/devcenter-plan.spec.js
  - frontend/e2e/scanBackground.spec.js
---

## Decided
Specs that point the shared test server at another project (config sources + scan) also register the original config for an afterEach that restores it and rescans. Because all specs share one server per run (workers: 1), a test that times out mid-way and never restores leaves every later spec on the wrong project.

## Tried and ruled out
Reading the failures as regressions: routes.spec ("Net Sales" not found) and the review auto-accept test failed only in the combined core run and passed alone. A baseline run on the old code failed the same routes tests in the same order, so the cause was the leaked project, not the change under test.

## Watch out
A spec that fails only after other specs ran is most likely seeing state an earlier test left on the shared server. Run it alone, then run it right after overhaul.spec.js, before debugging the code.

In the code: frontend/e2e/overhaul.spec.js (`restore` + `test.afterEach`), frontend/playwright.config.js (workers: 1, one graph server on 8765).
