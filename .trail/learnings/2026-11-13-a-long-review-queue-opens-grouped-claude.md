---
title: "A long review queue opens grouped by pattern, and one decision covers the pattern"
author: Claude
date: 2026-11-13
branch: claude/product-adversarial-review-wid901
cost: { minutes: 30, tokens: 516189 }
id: l-c24be58a
scope: repo
status: active
src: agent
touches:
  - backend/sample_project.py
  - docs/adversarial-review/README.md
  - frontend/e2e/a11yViews.spec.js
  - frontend/src/app.css
  - frontend/src/components/GraphView.jsx
  - frontend/src/components/LaneChips.jsx
  - README.md
  - backend/api/app.py
  - frontend/e2e/graph.spec.js
  - frontend/e2e/reviewLayout.spec.js
---

## Decided
Above 200 open suggestions the review queue shows patterns instead of rows: one group per rule (meaning, other name, behaviour, table role), evidence basis (name, description, formula) and object type. Each group is approved or rejected once, or opened to decide rows one by one. On the 13,731-object project 11,528 rows become 7 groups. Conflicts and decisions whose object is gone are groups too, but only one-at-a-time.

The project-wide "Approve all / Reject all" buttons are hidden while grouped: the per-pattern buttons replace them, and a bulk over 50 still asks once more, naming the pattern.

## Tried and ruled out
- Grouping by object name and suggested value (the eight copies of one measure as one row): 955 groups on the same project, still too many to finish in a sitting. The pattern group shows "N names" instead.
- Server paging of the review snapshot: not done. The snapshot is 42 MB but the queue opens in about a second and grouping needs every item on the client to count patterns.

## Watch out
Browser tests that expect `.review-item` rows right after opening the queue only hold under 200 suggestions; choose "No grouping" in the Group select first on larger fixtures.

In the code: `frontend/src/reviewGroups.js` (`groupReviewItems`, `GROUP_ABOVE`), `ReviewQueue` in `frontend/src/App.jsx` (session field `group`), `frontend/e2e/reviewGroups.spec.js`.
