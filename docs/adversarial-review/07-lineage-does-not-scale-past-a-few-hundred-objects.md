# 07 · Lineage flow is a 1,440-row strip: Fit does not fit, the minimap is a line

**Severity:** P1 · **Criteria:** performance, layout, easy to navigate

## Evidence

Lineage on the large project (2,479 drawn objects after version folding, 9,768 links):

- First draw 6 s, with a 2.6 s long task; payload 7.5 MB.
- **Fit** lands at 75 % in the middle of the Visuals lane with half the canvas empty and no lane header in sight: ![Fit](evidence/lineage-fit.png)
- Fully zoomed out (8 %) the picture is a sliver 120 px wide and taller than the window: ![Zoomed out](evidence/lineage-zoomed-out.png)
- The minimap shows a one-pixel vertical line. It gives no orientation and covers nodes at narrow widths (`evidence/graph-narrow.png`).
- Lane headers scroll away, so after any pan the user cannot tell which lane they are in.
- Below 55 % zoom nodes become unlabeled dots; with 1,440 visuals in one lane that is a dotted line.

The layout puts every object of a type in one column. That is correct for 100 objects and unusable for 2,500: aspect ratio about 1 : 30.

## Solution

1. **Fold by owner by default above 400 objects.** Tables lane shows tables; Columns and Calculations lanes show one row per table ("Orders · 18 columns", "Orders · 10 measures"); Visuals lane shows one row per page; Pages per report. The large project becomes ~30 × 5 rows. Expanding a row unfolds only that owner. This is the Matrix's existing fold rule (tables fold above 160 rows) applied to Lineage.
2. **Aggregated links** between folded rows with a use count; hover lists the top members.
3. **Fit means "fit width, anchor top-left".** When the content is taller than the viewport at the minimum readable zoom, fit the lanes to the width and scroll to the top. Never centre a tall layout.
4. **Sticky lane headers** pinned to the top edge of the canvas (HTML overlay positioned from the viewport transform), with name, count and a fold toggle.
5. **Replace the minimap** in Lineage with a slim vertical scroll scrubber that marks model/report block boundaries and the selected chain. Keep the minimap only in free-form views, hidden when the bounding box is narrower than 20 px in map space.
6. **Vertical wheel scrolls, Ctrl+wheel zooms** in lane layouts — the convention of every tall document.
7. **Layout in a Web Worker** (`graphLayout.js` / `lineage.js` are pure functions) to remove the 2.6 s main-thread block.
8. Lower zoom floor: 8 % is never legible. Clamp to the zoom at which the folded layout fits.

## Acceptance

- Lineage on the large fixture: first paint < 1.5 s, no long task > 200 ms, the whole folded picture visible at ≥ 55 % zoom.
- After Fit, the lane headers and the first row of every lane are visible.
