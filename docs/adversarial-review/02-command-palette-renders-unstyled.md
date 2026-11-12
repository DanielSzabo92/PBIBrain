# 02 · The command palette (Ctrl+K) renders unstyled

**Severity:** P0 (the headline keyboard feature looks broken) · **Criteria:** looks high-end, easy to use

## Evidence

![Unstyled palette](evidence/command-palette-unstyled.png)

- Icons, labels and arrows stack vertically; there is no input box, no row hover, no grouping.
- Result detail shows raw graph ids glued to the name: `Total Order Lines Amountmodel:model-0`.
- Eight identical names in a row with nothing to tell them apart.

Cause: `frontend/src/components/CommandPalette.jsx` uses class names that have no CSS:
`command-palette-header`, `-body`, `-group`, `-group-title`, `-label`, `-label-group`, `-glyph`, `-icon`, `-arrow`, `-detail`, `-search-icon`, `-shortcut`, `-spinner`, `-esc-badge`.
`frontend/src/app.css:1628-1753` styles a different set: `-input-box`, `-input-icon`, `-list`, `-group-heading`, `-item`, `-item-left`, `-item-icon`, `-item-label`, `-item-sub`, `-item-keys`, `-footer-hints`.
The component was rewritten and the stylesheet was not. No e2e test looks at the palette, so nothing failed.

## Solution

1. Make the two agree. Rename the JSX classes to the ones in `app.css` (the CSS is the newer, token-based set), and delete any rule left without a user.
2. Row anatomy, 32 px: type chip (20 px) · name 13/500 · scope in `--text-3` (`Sales Analytics › Orders`, from `objectScope()` in `presentation.js`, never the raw id) · right-aligned shortcut or `↵`.
3. Group results: **Commands**, then objects grouped by type with a count. Collapse version twins into one row with a `×8` badge, the same language the graph uses.
4. Remove the "Command palette" title and the close button; a palette is an input with a list. Keep an `aria-label` for the dialog.
5. Highlight the matched substring in the name.
6. Add a Playwright screenshot assertion for the open palette in both themes, and assert `getComputedStyle(row).display === "flex"`, so a class mismatch can never ship again.

## Acceptance

- Palette is 640 px wide, input on top, max 10 visible rows, selected row on `--surface-3`.
- No string matching `/^(model|report|table|measure):/` is visible.
- The new e2e check fails if `app.css` palette rules are removed.
