# 08 · Selecting an object on a large lineage hides the nodes and leaves a web of loose lines

**Severity:** P1 · **Criteria:** accomplishes its goals, looks proficient

## Evidence

![Selected visual](evidence/lineage-selected-orphan-edges.png)

Selecting "Rank by Region" (a visual using 2 columns and 3 measures) with the default "Show only related on select":

- Every other node disappears, but **dozens of horizontal edge stubs stay**, attached to nothing.
- None of the five objects the visual depends on is in view; they are thousands of pixels away in their lanes. The trace the feature promises ("everything that feeds it") is not visible.
- The pane lists them correctly, so the data is there — the canvas just cannot show it.

Cause: `relatedOnly` (`GraphView.jsx`) sets React Flow's `hidden` on unrelated nodes but keeps positions (deliberately, to avoid re-layout flicker — issue #53). Edges whose endpoints are hidden are still drawn, and related nodes keep their far-apart lane positions.

## Solution

1. **Hide edges with a hidden endpoint.** In the decoration pass, set `hidden: true` on any edge where either endpoint is hidden or not part of the traced chain.
2. **Trace view instead of in-place hiding.** When the traced chain does not fit the viewport, switch to a compact *trace layout*: only the chain's nodes, laid out in the same lanes but packed (5–40 nodes), animated in 280 ms. A breadcrumb chip "Trace: Rank by Region ✕" in the toolbar returns to the full picture at the previous viewport. This keeps the no-flicker rule: the big layout is never recomputed, a second small layout is shown over it.
3. When the chain does fit (small projects), keep today's dimming.
4. **Path-first pane.** In the docked pane, show the chain as a vertical path (Model › Table › Column › Measure › Visual › Page › Report) with type chips; clicking a step selects it. That gives the answer even before looking at the canvas.
5. Rename the option to "Trace on select" and move it out of the Display popover into a toolbar toggle with the `Crosshair` glyph, since it changes what a click does.

## Acceptance

- After selecting any visual on the large fixture, all of its upstream objects are on screen, connected, with no edge that has an invisible endpoint.
- Esc restores the exact previous viewport.
