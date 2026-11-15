---
title: Serve the generated 13.7k-object project from the tools folder to see the app at enterprise size
author: Claude
date: 2026-11-15
branch: claude/vibrant-franklin-h8aafq
cost: { minutes: 1, tokens: 693 }
id: l-99cd566e
scope: repo
status: active
replaces: l-ec68b0fc
src: agent
touches:
  - tools/large_project.py
  - tests/test_scale_budgets_large.py
  - docs/adversarial-review/README.md
---

## Decided
- To see the app at enterprise size, generate and serve the 13,731-object project (8 models, 24 reports, 41,942 relationships, 11,528 review items) through the real scanner and API. The e2e fixtures have under 100 objects and hide every scale problem.
- The review's one-off server script was removed; the generator in the tools folder replaces it and also writes the sources for the scale budget test.

## Watch out
- Serve a fresh build: the UI comes from frontend/dist, which is git-ignored and can be stale.
- The fix-status table in the review README is in the order the work was done; a later row for a finding supersedes an earlier row's "Open" note.

In the code: tools/large_project.py (`python -m tools.large_project --dir bigdata --serve`, port 8801), tests/test_scale_budgets_large.py, docs/adversarial-review/README.md.
