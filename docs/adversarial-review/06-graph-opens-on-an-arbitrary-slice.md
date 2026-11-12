# 06 · On a large project the Graph opens on 80 arbitrary objects in one column

**Severity:** P0 · **Criteria:** accomplishes its goals, easy and obvious, layout

## Evidence

![Default graph](evidence/graph-default-large.png)

- Default view "Containers" requests `GET /api/graph?depth=1&limit=80` and draws whatever 80 objects come back: a single column of unrelated columns and measures ("Key", "Key", "Owner", "Owner", "Owner", "MTD Ca…Amount").
- Header reads "63 objects · 3 links"; a note in the corner reads "Showing 80 of 13731 objects · Show more". Three different numbers, none explaining what the user is looking at.
- Three quarters of the canvas is empty. Names are cut in the middle although there is room.
- "Show more" would need to be clicked ~170 times to see the project.

The first impression of the product's central view is "this is broken or empty".

## Solution

Make the default view an **aggregated map**, not a sample:

1. **Level 0 = the estate.** One node per model and per report (32 nodes here), grouped as Sources › Models › Reports left to right, linked by USES_MODEL / SOURCES_FROM. Each node shows the name and three counts with glyphs (`▦ 30  ▥ 540  Σ 300` for a model, `▭ 6  ▮ 60` for a report) and a status glyph if it has review or validation issues. Server endpoint: `GET /api/graph/summary` built from the cached counts (03) — a few kB regardless of project size.
2. **Expand in place.** Double-click or Space on a model shows its tables (30 nodes, measure/column counts on each); expanding a table shows its columns and measures. Only the expanded branch is fetched (`GET /api/graph/children?id=`). Auto-collapse siblings beyond ~150 visible nodes.
3. **Always a full answer.** Remove "Showing 80 of N · Show more". The counter becomes "32 of 32 containers · 13,731 objects inside".
4. **Bundle parallel edges.** Between two containers draw one edge with a count ("124 fields used"), thickness by `log(count)`.
5. **Entry from context.** "Show in graph" from Search/Inspector opens Neighbourhood focused on that object; the estate map is only the no-selection default.
6. Node width fits the name up to 280 px (the lineage rule), so "MTD Ca…Amount" is not cut when space is free.

## Acceptance

- Opening Graph on the large fixture shows 32 nodes with counts in < 1 s, filling ≥ 60 % of the canvas at ≥ 85 % zoom.
- No "Showing n of N" notice exists in the default view.
