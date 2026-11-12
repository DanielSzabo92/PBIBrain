# 21 · Theme ignores the OS setting; small windows and keyboard gaps

**Severity:** P3 · **Criteria:** easy to use, looks proficient

## Evidence

- **Theme.** With the OS set to light (`prefers-color-scheme: light`) the app starts dark. `public/theme-init.js` reads only `localStorage["pbibrain-theme"]`; nothing in `src/` queries `prefers-color-scheme`. There are two states (dark, light) and no "System".
- **Narrow window (1024×700).** The graph toolbar wraps to three bands (finder + view switch, counts + Fit, lane chips on two lines) and the minimap covers node labels. ![Narrow](evidence/graph-narrow.png)
- **Focus.** On load the h1 is the active element and shows a 2 px focus ring (15).
- **Graph zoom range** is 8 %–200 %; both ends are unusable (07).
- **Lists** are navigated differently per view: arrow keys in search results, J/K in the review queue, its own handler in the palette.
- Review, Search and Merge were not checked with a screen reader in this review; the existing axe e2e covers Merge models only (contract §13 item 1 asks for every view in both themes).

## Solution

1. **Theme: System / Light / Dark.** Default "System"; `theme-init.js` falls back to `matchMedia("(prefers-color-scheme: light)")` when nothing is stored, and listens for changes. In the desktop shell, also follow the OS accent for the title bar (`theme-color` meta is already updated).
2. **Responsive toolbar by priority:** below 1200 px collapse Types/Display/Filters into one "View" button (already done) *and* move counts into its popover; lane chips scroll horizontally in one line instead of wrapping; hide the minimap below 1100 px.
3. **One list behaviour** (a shared `useListNavigation` hook): ↑/↓ and J/K, Home/End, PageUp/PageDown, Enter to open, type-ahead; roving `tabindex` so Tab leaves the list in one press. Apply to search results, palette, review queue, object tree, merge grid.
4. **Focus management:** on view change move focus to `#main-content` (already `tabIndex={-1}`, `outline: none`) and announce the view name through a polite live region instead of focusing the h1.
5. **Extend the axe pass** to Overview, Search, Graph, Inspector, Review and Settings in both themes, plus one reduced-motion run, as the contract's §13 lists.
6. **Window minimum** 960×600 in the desktop shell; below that the sidebar becomes the icon rail automatically.

## Acceptance

- A fresh profile on a light-mode OS starts light.
- At 1024×700 the graph toolbar is one band plus one scrollable chip line; nothing overlaps the canvas content.
- axe reports zero serious violations on all seven views, both themes.
