---
title: A GitHub pwsh step with two native commands passes when only the first one fails
author: Daniel
date: 2026-10-31
branch: claude/dev-center-build-6abbf2
cost: { minutes: 24, tokens: 165123 }
id: l-e39c1050
scope: repo
status: active
touches:
  - ".github/workflows/ci.yml"
  - ".scratch/dev-center-build/issues/02-u0-test-harness.md"
  - frontend/test/devcenter-lint.test.js
  - tests/test_ci_workflow.py
  - ".scratch/dev-center-build/WORKER.md"
  - ".scratch/dev-center-build/board.md"
  - ".scratch/dev-center-build/issues/03-s1-scanner-coverage.md"
  - frontend/playwright.guard-compat.config.js
  - frontend/vite.config.js
---

## Watch out
- GitHub runs a `pwsh` step with `$ErrorActionPreference = 'stop'` and ends it with `exit $LASTEXITCODE`. A native command with a non-zero exit code does not stop pwsh, so a failed first command and a passed second command give a green step. In `.github/workflows/ci.yml`, put one native command in each step, or check `$LASTEXITCODE` after each one. `tests/test_ci_workflow.py` holds this rule.
- `frontend/playwright.guard-compat.config.js` and `playwright.graph-readability.config.js` used to spread `existing.webServer`. Now `webServer` is an array, so they import the named `graphWebServer` export. Do not spread the array.
- On Windows, the timing asserts of the fake server delay test fail when e2e runs at the same time as the Python suite. Keep the wide limits.
- `frontend/vite.config.js` merges `loadEnv` with `process.env`: a `.env` file with `DEVCENTER_FAKE=1` puts the shim into a production build. CI Gate 3 checks the build output for the shim tag.
