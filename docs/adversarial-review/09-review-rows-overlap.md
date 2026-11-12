# 09 · Review rows: the suggestion chip is drawn on top of the explanation text

**Severity:** P1 · **Criteria:** looks proficient, clean layout

## Evidence

![Overlap](evidence/review-rows-overlap.png)

In every row the dashed "Meaning: …" chip overlaps the object scope on the left and the "Why review this?" sentence on the right. Both strings are unreadable. The header says "Object & suggestion | Why review this?" but the chip sits across the column border.

Cause: `.review-item` is a 4-column grid (`app.css:823`), and the first cell holds three items in a row — expand button, object button, chip. The chip is `flex: none` (`app.css:839`) with no max width, and the object button does not shrink, so the cell overflows into the next column.

The row is also redundant: the object is "Rolling 12M Order Lines Amount", the suggestion is "Meaning: Rolling 12M of order lines amount", and the reason repeats it a third time in a sentence.

## Solution

1. **Give the suggestion its own column:** `grid-template-columns: 28px minmax(180px, 1.2fr) minmax(160px, 1fr) minmax(0, 1.4fr) 96px auto`. Every text cell gets `min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap`, full text in a tooltip.
2. **Chip is the new value only.** Show `→ "Rolling 12M of order lines amount"` with the suggestion kind as a leading glyph (`Tag` alias, `Lightbulb` concept), not the word "Meaning:".
3. **Reason becomes a source glyph + short phrase:** `FileText` "From description", `Type` "From name", `Workflow` "Rule". The long sentence moves to the expanded row.
4. **Confidence:** the number and the 40 px meter only; drop the long bar.
5. **Actions:** icon buttons `Check` / `X` with tooltips "Approve (A)" / "Reject (R)"; the labelled versions appear only on the focused row. This removes 11,528 repeats of the words Approve and Reject.
6. Add the contract's check 10 as a test: an 80-character object name must truncate and never overlap its neighbour (assert bounding boxes of the three cells do not intersect).

## Acceptance

- At 1280, 1440 and 1920 px no two cells of a row intersect.
- A row reads in one pass: object · suggestion · source · confidence · actions.
