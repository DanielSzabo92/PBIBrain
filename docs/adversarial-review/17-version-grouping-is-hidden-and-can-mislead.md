# 17 · "Group versions" silently folds different models into one

**Severity:** P2 · **Criteria:** accomplishes its goals, self-explanatory UI

## Evidence

The test project has six different models (Sales, Finance, Supply Chain, HR, Marketing, Customer Service) built on the same table template, plus two real "v2" copies. Lineage shows:

- Lane chip "Models **1**", one node "Customer Service Analytics ×8".
- Every table, column and measure carries "×8" and an amber dot.
- The header says "2479 objects" while the status bar says 13,731.

The rule ("at least half of the smaller model's objects match by type, table and name") is reasonable for copies, but organisations commonly stamp many models from one star-schema template. The user sees one arbitrary model name standing for eight, with no hint that folding happened, and the switch is inside the Display popover ("Group versions").

The amber dot (definitions differ) has no legend and uses the warning colour for something that is not a problem.

## Solution

1. **Stronger evidence before folding.** Treat two models as versions only when structure matches **and** one of: same `logicalId` / lineage tags, names equal after removing version tokens (`v2`, `(copy)`, `- DEV/TEST/PROD`, dates), or same source folder lineage. Otherwise classify as "similar models (shared template)" — reported in the Overview, not folded.
2. **Name the group honestly.** A folded node is titled by the common stem ("Sales Analytics · 2 versions"); never by one member's name.
3. **Make folding visible and one click away.** A toolbar toggle chip `Layers ×2 Versions folded` next to the lane chips; clicking opens the list of groups with a per-group unfold. Counts read "2,479 shown · 13,731 total".
4. **Let the user correct it.** "Not versions" / "These are versions" in the node pane, stored in project overrides.
5. **Difference marker:** replace the amber dot with a neutral `≠` glyph and tooltip "3 of 8 definitions differ"; clicking opens the side-by-side diff (the Merge compare component already exists).

## Acceptance

- The six template-based models in the fixture are shown as six models; the two v2 copies fold with their originals.
- A user can tell from the toolbar alone that folding is active.
