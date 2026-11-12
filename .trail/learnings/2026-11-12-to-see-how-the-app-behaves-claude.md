---
title: "To see how the app behaves at enterprise size, serve a generated 13.7k-object project through the real API; the small test fixtures hide every scale problem"
author: Claude
date: 2026-11-12
branch: claude/product-adversarial-review-wid901
cost: { minutes: 21, tokens: 245518 }
id: l-ec68b0fc
scope: repo
status: active
src: agent
touches:
  - docs/adversarial-review/01-review-queue-freezes-on-large-projects.md
  - docs/adversarial-review/02-command-palette-renders-unstyled.md
  - docs/adversarial-review/03-first-load-takes-11-seconds.md
  - docs/adversarial-review/04-single-threaded-server-blocks-the-ui.md
  - docs/adversarial-review/05-overview-states-things-that-are-false.md
  - docs/adversarial-review/06-graph-opens-on-an-arbitrary-slice.md
  - docs/adversarial-review/07-lineage-does-not-scale-past-a-few-hundred-objects.md
  - docs/adversarial-review/08-selecting-a-node-leaves-orphan-edges.md
  - docs/adversarial-review/09-review-rows-overlap.md
  - docs/adversarial-review/10-no-deep-links-or-history.md
---

## Decided
- The product review of 2026-11-12 ran the production UI build against a generated project (8 models, 24 reports, 13,731 objects, 41,942 relationships, 11,528 review items) served by the real scanner, repository and API. All scale problems appear only there; the e2e fixtures have under 100 objects.
- Findings and solutions are one file per problem in the review folder; fix order is 01-05, 06-09, 22, then the rest.

## Tried and ruled out
- Navigating by hash URL (`/#/graph`, `/#/review`): the hash routes in the visual contract section 8 were never built, so every URL opens Overview. Drive the app by clicking the sidebar buttons.
- `import { chromium } from "playwright"` in an .mjs script outside the frontend folder: not resolvable. Use a .cjs script with `require("playwright")`.

## Watch out
- `frontend/dist` is git-ignored and can be stale; `vite build` fails with "failed to resolve import sonner" until `npm ci` is run in `frontend/`.
- The API server is single-threaded (wsgiref). While `/api/brain` (163 MB on the large project) runs, every other request waits, so Merge models and Settings look hung; that is queueing, not a second bug.
- Overview widgets (most-used measures, hot objects, recently changed) read the browser snapshot, which loads only when Review queue is opened; before that they show "None"/"Clean".
- Lineage "Group versions" folds models that share a table template into one node; a generated project with one template shows "Models 1 x8".
- The command palette JSX and `app.css` use two different class-name sets, so it renders unstyled; no e2e test looks at it.

In the code: docs/adversarial-review/README.md, docs/adversarial-review/evidence/large_project_server.py (run with `--port 8801`; set `app.static_dir` to a fresh build), backend/api/app.py `get_overview` and `make_server`, frontend/src/App.jsx `loadSnapshot`, frontend/src/components/CommandPalette.jsx.
