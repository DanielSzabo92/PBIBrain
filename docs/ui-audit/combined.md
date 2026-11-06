# Combined UI pass: desktop shell + impeccable + lintapple

Three sessions audited the frontend in parallel, each through a different lens, and each
fixed its top findings on its own branch:

| Lens | Branch | Report | What it was best at |
|---|---|---|---|
| desktop-ui-design | `claude/ui-audit-desktop` | [desktop.md](desktop.md) | Structure: the app was a SaaS dashboard in a window. Gave it a real desktop shell and keyboard model. |
| impeccable | `claude/ui-audit-impeccable` | [impeccable.md](impeccable.md) | Taste: named the "slop" tells (hero metrics, kickers, icon tiles, side stripes, 13 radii) and set a design direction. |
| lintapple | `claude/ui-audit-lintapple` | [lintapple.md](lintapple.md) | Rigor: measured the rendered UI against explicit rules (type scale, spacing, targets, tooltips) and made them enforceable. |

This branch (`claude/intelligent-knuth-miku86`) merges all three into one design.

The desktop-ui-design skill was removed from `.claude/skills` after the audit: the registry copy
is a thin Tkinter/Qt checklist, and the desktop conventions this work relies on are captured in
[desktop.md](desktop.md) and `frontend/DESIGN.md`.

## Design direction (one sentence)

A quiet, exact, dense **desktop reference instrument** that sits beside Power BI Desktop:
a desktop shell for structure, impeccable's "Lineage Ledger" for the look, lintapple's
policy to keep it that way. See `frontend/DESIGN.md` (updated for the combined result) and
`frontend/PRODUCT.md`.

## What came from where

**Structure — from desktop**
- App shell: 32px title row (File / View / Go / Help menus + Ctrl+K command centre), 212px side
  bar collapsible to a 44px icon rail (Ctrl+B), 36px per-view toolbar (Rescan, Reload), 26px status
  bar (connection, scan progress, counts, "N to review", last scan, messages, shortcuts, theme).
- Fixed viewport; only `#main-content` scrolls.
- One shortcut table (`src/shortcuts.js`) drives keys, menus, tooltips and the F1 sheet.
  F5 reloads data instead of the page (P0: it used to throw away all session state).
- Arrow / Home / End / Enter in result and lineage lists; Alt+Left back with focus restored.

**Look — from impeccable**
- Overview rebuilt: project title, inline counts, a plain search field, and one status panel with
  rule-separated rows (Review, Validation, Sources). No stat tiles, kickers, icon tiles or CTA cards.
- Three radii (`--r-xs/sm/md` = 4/6/8px), flat surfaces at rest (shadows only on overlays),
  no side-stripe borders, no spring easing, no taglines in the toolbar.
- Font stack leads with Segoe UI Variable (native next to Power BI Desktop), Inter as fallback.

**Rules — from lintapple**
- Seven-step type scale `--fs-micro…--fs-page` (11/12/13/14/16/20/24); every CSS `font-size`
  uses one; Tailwind `text-2xs…2xl` map onto it; `test/type-scale.test.js` and `ui-policy.json`
  enforce the same list. (impeccable proposed the identical scale under `--type-*`; the merge
  keeps one set of names, `--fs-*`.)
- `--space-*` 4px grid; controls in an action group never closer than 8px.
- Button icons on the 16px lucide grid; icon-only buttons get a real tooltip automatically.
- 24px checkbox / 40×24 switch targets, compact icon nav that fits at 390px, ARIA fixes, skip link.
- `data-ui-*` markers so layout rules are actually checked; `npm run lint:ui:states` sweeps
  11 views × 2 themes × 2 widths. `tests/ui_audit_server.py` serves a realistic fixture for it.

## Merge decisions

- **Desktop density wins over web density.** Where desktop and lintapple disagreed on sizes
  (nav row height, toolbar button height), the desktop values stay; lintapple's policy gained two
  documented exceptions for desktop chrome (contiguous menu/status-bar segments; 26px buttons
  centred in the 36px toolbar).
- **Page titles are 20px**, not 24px (impeccable + desktop agree; policy updated). 24px is kept for
  the one project name on Overview. Row/panel titles are 14px h2s (policy updated).
- **Active nav keeps a 2px indicator.** impeccable removes side stripes as an AI tell on cards;
  a selection bar in a side bar is a platform convention (VS Code, Fluent), so it stays there only.
- Impeccable's side-stripe fixes on evidence blocks and the colour-preview node were restored
  after the merge (the detector caught the regression).
- `VIEW_HINTS` taglines were removed (impeccable) — the desktop toolbar referenced them; fixed.
- The policy font list now names the actual stack (Segoe UI Variable first, Inter fallback,
  Cascadia/Consolas for code); without it every element failed `font-family`.
- In the icon rail the review badge sits bottom-right of the icon (VS Code activity-bar style)
  instead of covering it.

## Verification

| Check | Result |
|---|---|
| `npm test` | 169 / 169 pass |
| Playwright e2e (full suite) | 232 / 233 pass. The one failure, `devcenterParts.spec.js:225` (menu focus), also fails on the untouched baseline (reported by all three audit sessions). |
| impeccable detector, static (`frontend/src`) | 0 anti-patterns (was 4 + 2 advisories before the audits) |
| lintapple, 44 states (`npm run lint:ui:states`) | 37 problems / 158 occurrences on visible elements (lintapple branch alone: 19 / 110; original UI: 1654 / 8966). Remaining: 66 contrast checks lintapple could not measure (gradients/overlays), 52 graph-node label-in-name (left alone: e2e locators depend on them), and a handful of graph toolbar/tab insets. |

Notes on lintapple: findings with a measured size of `0px` are controls scrolled out of the
content pane (the desktop shell's fixed viewport makes the pane the only scroller, and lintapple
measures the clipped box). They are counted separately and are not defects.

## Still open (ranked)

1. Docked, resizable Explorer tree + Properties pane instead of the overlay details sheet (desktop P1).
2. Graph toolbar: three stacked rows in a panel inside a panel → one row + a "View" popover (impeccable P1).
3. Review queue as a keyboard grid (j/k, A/R), suggestions grouped by object, count shown once
   (desktop + impeccable P2). Review table headers are still small uppercase.
4. Context menus (Copy DAX reference, Open in graph), registered in `SHORTCUTS`.
5. `EDGE_COLORS` are hex literals that ignore the theme (`App.jsx`).
6. Dev Center hangs on "Loading merge sessions" when `/api/devcenter/session` returns 409.
7. Follow the OS theme (`prefers-color-scheme`) and update axe baselines with it.
8. Graph node accessible names don't contain their visible text (e2e locators depend on them).

## Screenshots

`docs/ui-audit/screenshots/combined/` — Overview, Review, Graph and Search at 1440px in dark and
light, plus 390px. Each audit's before/after shots are in its own folder.
