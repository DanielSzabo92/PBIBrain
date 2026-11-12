# 11 · 11,528 suggestions to approve one by one is not a workflow

**Severity:** P1 · **Criteria:** accomplishes its goals

## Evidence

- The scan of 2,400 measures and 4,320 columns produced **11,528 review items** (the overview also reports 16,683 candidate nodes/edges).
- Most are restatements: measure "Rolling 12M Order Lines Amount", description "Rolling 12M of order lines amount", suggestion "Meaning: Rolling 12M of order lines amount", confidence 96 %. The human adds nothing by approving it.
- The eight copies of a measure across model versions are eight separate decisions.
- The only bulk tools are "Approve all (11528)" and "Reject all (11528)" — one click away from each other, no preview of what they cover.
- Search results list an "Alias" object above each real measure with the same name, so the noise leaks out of the queue (see 12).

A reviewer facing "99+" forever stops looking; the trust mechanism the product is built on then does nothing.

## Solution

1. **Auto-accept what needs no judgement.** A suggestion derived from the object's own description or name with confidence ≥ a project threshold (default 90 %) is stored as `accepted_auto`, shown with its own provenance glyph, reversible, and never enters the queue. Expected effect on the test project: 11,528 → a few hundred.
2. **The queue is for disagreement and ambiguity only:** conflicts, stale decisions, low confidence, two objects claiming the same meaning, meaning that differs between versions.
3. **Group by pattern, decide once.** Rows group by rule + shape ("Alias from description · 2,160 measures · 96 %"), expandable to samples. One decision applies to the group; exceptions can be pulled out. Versions of the same object are one row with `×8`.
4. **Safer bulk actions.** Replace the two "all" buttons with a selection model: header checkbox + "Approve 214 selected". Above 50 items show a confirmation naming the scope ("214 aliases in Sales Analytics") and always offer Undo (one token, see 01).
5. **Progress that can end.** Header shows "312 need a decision · 11,216 accepted automatically" with a thin progress bar; the sidebar badge counts only items that need a human.
6. **Settings › Review:** auto-accept threshold, and which suggestion kinds are generated at all.
7. Aliases and behaviours are not "objects": remove them from the Overview type chips and from default search results; show them as properties of their target.

## Acceptance

- On the large fixture the queue opens with < 500 groups and can be emptied in one sitting.
- No bulk action over 50 items runs without a scoped confirmation; all are undoable.
