# Brain Inspector UI audit — lintapple lens

Branch `claude/ui-audit-lintapple`. This audit checks the rendered UI with
[lintapple](../../frontend/node_modules/lintapple/README.md), which measures the page in a real
browser: type sizes, control sizes, gaps and insets, icon sizes, screen bounds, contrast, and the
ARIA / tooltip / label checks it runs through axe. It does not judge visual taste, so this report
adds a few manual observations from the screenshots.

## TL;DR

| | Occurrences | Distinct problems |
|---|---:|---:|
| Before (original code, tuned policy, markers) | **8966** | **1654** |
| After, same exceptions as before (like-for-like) | **1664** | **207** |
| After, final policy (documented exceptions) | **110** | **19** |

All 110 remaining occurrences are either axe `label-consistency` on graph nodes (56, deliberately
left, see P2-6) or `text-contrast` checks that lintapple could not measure (54 "unresolved", P3-2).
In both "after" rows, every remaining problem is listed in
[`lintapple-report.json`](lintapple-report.json).

The "slop" feeling comes mostly from the type system rather than from any one screen: the CSS
used **17 different font sizes** (10, 10.5, 11, 11.5, 12, 12.5, 13, 13.5, 14, 14.5, 15, 16, 19, 22,
24, 26 and 30 px) across about 370 declarations. Text one step apart differed by half a pixel, so
nothing read as a clear level. Headings were sometimes smaller than the text under them. Icons were
15 px, off the lucide 24-unit grid. Action groups used a 6 px gap. Narrow windows cut off four of
the seven navigation destinations.

## How it was run

* **Data:** `tests/ui_audit_server.py` (new). It works like `tests/graph_ui_server.py`, but loads
  a realistic model: 6 tables, 28 columns, 26 measures, 4 relationships, 2 reports with 3 pages and
  12 visuals. That gives 188 objects, 305 edges and 113 review items. The real backend scans the
  data into a temporary Ladybug database.

  ```sh
  python -m tests.ui_audit_server --port 8765           # repo root
  cd frontend && BRAIN_API_URL=http://127.0.0.1:8765 npx vite --port 5173
  node scripts/lint-ui-states.mjs --out report.json --screenshots shots/
  ```
* **Coverage:** `frontend/scripts/lint-ui-states.mjs` (new). It drives 11 states: overview,
  search with results, graph, graph with the details sheet open, inspector browse, inspector
  object, review queue, Development Center, and three settings tabs. It checks each state in
  **both app themes** and at **390×844 and 1440×900**, so 44 page checks in all, and calls
  lintapple's `checkPage` on each one. Each finding is resolved to a readable `tag.class` hint and
  a text snippet, and suppressed findings are counted rather than dropped.
  * Plain `npm run lint:ui` only ever sees the landing view in **dark** theme. The app's theme
    comes from `localStorage` (`App.jsx:134` `readTheme`), not from `prefers-color-scheme`, so
    lintapple's `colorSchemes` setting has no effect on it. The script sets the theme through
    `localStorage`.
* **Markers added:** `data-ui-actions` on 46 button groups and toolbars (topbar, review decisions,
  dialog footers, graph toolbars, and DevCenter rows and panes). `data-ui-stack` on page wrappers.
  `data-ui-container` on the `Card` and `Sheet` primitives (`.ui-dialog` and `.topbar` are added
  through `controlContainers`). `data-ui-number` on changing numbers: nav count, stat tiles, review
  count, review score, queue count and graph zoom. `data-ui-tooltip` is set automatically by the
  `Tooltip` primitive (see the fixes).

## Policy: `frontend/ui-policy.json`

I replaced lintapple's default policy, which is a marketing-site scale (12–64 px with 14/16 px
buttons), with one for a **dense desktop data tool**:

| Setting | Value | Why |
|---|---|---|
| `fontSizes` | 11 12 13 14 16 20 24 | Seven steps that match the `--fs-*` tokens. A unit test keeps the two lists equal. |
| `h1` | 24 | One page-title size. It used to be 22, 24, 26 or 30 depending on the page. |
| `h2` / `h3` | 16, 20 / 13, 14, 16 | Section and panel headings. |
| buttons / tabs / combobox | 12, 13 | 13 by default, 12 for `size="sm"`. Counters and badges inside buttons may be 11. |
| inputs | 13, 14 | Code inputs use 13 px mono. |
| `controlSizeRules` | ≥24 px | WCAG 2.5.8 target size. The app is a desktop (pywebview) tool, so 44 px touch targets would be the wrong goal. |
| `iconSizeRules` | 12, 14, 16 on button, nav and tile icons | Lucide icons are drawn on a 24-unit grid. 15 px gives a 0.625 scale, which blurs the strokes. |
| `minControlGap` / `minLayoutGap` | 8 | Same as `--space-2`. |
| `colorSchemes` | dark, light | |

**Exceptions** each carry a reason in the file, and the driver counts every finding they
suppress (`runs.after.suppressed`):

* **Graph canvas nodes:** clipping, bounds, size and inset findings change with the zoom level.
  Node typography and ARIA are still checked.
* **Vertical nav list, segmented tabs, and result-list rows:** these are list patterns, so the
  8 px control gap does not apply.
* **Icon-only buttons (`data-size^=icon`):** they are square targets of 24 px or more with a 16 px
  glyph. Their size is still checked, and they now carry real tooltips.
* **Visually hidden text and the skip link:** they are clipped on purpose.
* **Switches and checkboxes:** a visible `<label>` names each one, so they need no tooltip.
* **Link-variant buttons:** these are inline text links with no box. Their hit height is held at
  24 px or more.
* **The compact-nav count badge:** it overlaps the button corner, which is the standard badge
  pattern.

The middle row of the TL;DR is there so these exceptions cannot flatter the result. It re-runs the
fixed code with only the one original exception.

## Findings (before), ranked

Counts are occurrences / distinct problems across the 44 checks. File:line references point to
`HEAD` before this branch.

### P0 — broken for some users

1. **Narrow windows hide four of the seven destinations.** At ≤760 px the sidebar becomes a
   horizontal strip with a hidden scrollbar (`app.css:894`, `overflow-x: auto; scrollbar-width:
   none`). Inspector, Review queue, Development Center and Settings fall outside the strip, and
   nothing shows that they are there. lintapple measured them as `control-size 0 × 32px`, with
   76 occurrences of that size result. See `before/overview-390-dark.png`.

### P1 — systemic, drives most of the findings and of the "slop" feel

2. **No type scale.** 4528 / 944 `font-size` findings. There were 17 sizes, and 12 of them were
   used for controls alone. Worst offenders by occurrence:
   * The button base was `text-[13px]` but `sm` was `text-[12.5px]` (`ui/button.jsx:8,24`).
     Tabs were 12.5 (`app.css:110`), badges 11.5 (`app.css:120`) and nav labels 13.5
     (`app.css:221`).
   * Review rows: the type label was 11.5 (`app.css:552`), the score 15 and the target copy 13.5.
   * Search: the result type was 11.5 (`app.css:419`). Graph node names were 15 (`app.css:704`).
   * Page titles were 26 (`app.css:280`), 30 on the overview (`app.css:306`), 22 at narrow
     widths and 22 in DevCenter. Stat tiles were 30 (`app.css:326`).
   * **Headings smaller than body text:** the inspector section headings (`h3.panel-title`, for
     example "Lineage") were 11 px grey uppercase eyebrows (`app.css:203`), styled like captions
     but marked up as headings. `h2.settings-keyboard-title` was 14 px.
3. **Icons off grid.** 1416 / 259 `icon-size` findings. The button primitive forces every svg to
   15 px (`ui/button.jsx:8`, `[&_svg]:size-[15px]`), and the CSS repeats `width: 15px; height:
   15px` and 13 px about 20 times.
4. **Action groups too tight.** 1088 / 183 `control-gap` findings. Review Approve/Reject, the
   topbar, scan actions, the model summary and the graph filter and canvas actions all used
   `gap: 6px` (for example `app.css:563` and `app.css:262`). Search results sat at 0 px with a
   6 px container inset (`app.css:411`): 800 / 139 `control-inset` findings.

### P2 — real defects, local

5. **Icon-only buttons have no visible name.** 148 / 10 `icon-button-tooltip` findings. This
   covers theme toggle, reload, zoom in/out/fit, remove source and sheet close. They used native
   `title=` at best (`App.jsx:506,522`), which keyboard users never see.
6. **Graph node accessible names don't contain the visible text.** 56 / 10 `label-consistency`
   findings. A node shows "Measure / Net Sales" but is announced as "Select Net Sales"
   (`GraphView.jsx:289`). The group toggle shows "3 inside" but is named "Expand Sales". Voice
   control users can't say what they see. *Not fixed here:* about 25 e2e locators depend on these
   names, so the change belongs with an update to those tests. The suggested name is
   `${type} ${name}` for the node and `${name}, ${n} inside` for the toggle.
7. **Hit areas under 24 px.** 248 / 30 `control-size` and 16 `target-size` findings. Checkboxes
   were 16×16 by default (`ui/checkbox.jsx:12`), even though a 24 px `target` variant already
   existed. The switch was 36×22 (`devcenter.css:140`). The graph "Show more" link was 64×18.
8. **ARIA misuse.** 20 / 3 `control-state` findings: `aria-label` was set on a plain `div`
   (`.artifact-legend`, `GraphView.jsx:243`; `.color-preview`, `GraphColors.jsx:63`) and on a
   `span` (`.graph-zoom-value`, `GraphView.jsx:323`), none of which has a role.
9. **The skip link sits outside the viewport** (`app.css:23`, `translateY(-160%)`): 44
   `viewport-bounds` findings.
10. **The Impact Explorer disclosure is a bare ghost button flush against its card edge**
    (`ImpactExplorer.jsx:67`), with no padding and 0 px insets on all sides. It also lacks the
    chevron that "Other relationships" uses, so the two disclosures on the same page look
    different.
11. **Topbar icon buttons have a 7.5 px inset at narrow widths** (44 px topbar).

### P3 — polish and coverage limits

1. `content-inset`: icon buttons were 28 px square with a 15 px glyph (5.5 px inset). The policy
   now has a deliberate exception for these, explained above.
2. `text-contrast` **unresolved** (98 → 54 after the fixes): lintapple can't find the effective
   background for nav count badges, tabs and chips in the graph details sheet, or for the graph
   toolbar hint text. The sheet uses an entry animation and the toolbar sits over the canvas. These
   need a manual contrast check, which this audit did not do.
3. Manual observations (not measured by lintapple):
   * The graph details sheet covers about 30 % of the canvas, and the "Showing 80 of 82…" notice
     runs under it (`after/graph-details-1440-light.png`).
   * The "Uses model" edge label is drawn on top of the edge line.
   * Stat tiles have a hover border (`app.css:323`) but do nothing when clicked, so they look
     interactive when they are not.
   * The overview's disabled "Search" button looks like a muted primary button rather than a
     disabled one.
   * Card radii mix 12 px (cards), 10 px (inputs and banners) and 9 px (tabs and icon tiles)
     against a `--radius` of 8 px. This finding was not acted on.

## What I changed (systemic first)

1. **Type scale tokens** (`theme.css`): `--fs-micro 11 · meta 12 · body 13 · emphasis 14 · title 16
   · heading 20 · page 24`.
   * Tailwind's `text-2xs…2xl` utilities are remapped onto the same tokens, so the shadcn
     primitives and the hand-written CSS share one scale.
   * Every `font-size` in `src/**/*.css` was moved onto a token in one mechanical pass: 10–11 →
     micro, 11.5–12.5 → meta, 13–13.5 → body, 14–15 → emphasis, 19–22 → heading, 24–30 → page.
     A few hand-picked cases followed: DevCenter `h1` to page, inputs to body, section headings to
     emphasis/title, and the narrow-width h1 overrides were removed.
   * The body default is now 13 (it was 14, while most UI text was set to 13 anyway).
   * **Guard:** `frontend/test/type-scale.test.js` fails on any literal `font-size`,
     `text-[Npx]` or off-scale `fontSize`. It also checks that the tokens equal
     `ui-policy.json` `fontSizes`.
2. **Spacing tokens:** `--space-1…8` moved from the DevCenter stylesheet to `theme.css` as the
   app-wide 4 px grid. Every action group now uses `gap: var(--space-2)` (8 px).
3. **Icons:** the button primitive uses 16 px icons (14 px for `size="sm"`), and every hard-coded
   15/13 px icon is now 16/14.
4. **Button primitive:** icon-only buttons (`size="icon*"` with an `aria-label`) render a real
   Radix tooltip from that label automatically, and the native `title` is dropped. The `Tooltip`
   primitive brings its own provider and sets `data-ui-tooltip`, so lintapple and keyboard users
   can find it.
5. **Compact navigation (≤760 px):** icons only, 32 px targets with 8 px gaps, labels kept for
   screen readers and shown as tooltips (`useCompactNav`). The count becomes a corner badge, and
   all seven destinations fit at 390 px. The topbar is 48 px tall at narrow widths.
6. **Primitives:** `Checkbox` defaults to the 24 px `target` variant. The switch is 40×24. The
   sheet close button has a proper name. Link buttons keep a minimum height of 24 px.
7. **Local fixes:**
   * The skip link uses clip-hiding.
   * `role` was added to the legend, the color preview and the zoom readout.
   * `.panel-title` is a real heading (14 px semibold, full-strength text).
   * The Impact Explorer header has 8 px padding and spans the full width.
   * The search result list has an 8 px inset.

Not changed: graph node names (P2-6), contrast (P3-2), radii, the sheet overlap, and stat tile
hover (P3-3).

## Before/after by rule

| Rule | Before | After, same exceptions | After, final policy |
|---|---|---|---|
| font-size | 4528 / 944 | 4 / 1 | 0 / 0 |
| icon-size | 1416 / 259 | 0 / 0 | 0 / 0 |
| control-gap | 1088 / 183 | 478 / 63 | 0 / 0 |
| control-inset | 800 / 139 | 128 / 32 | 0 / 0 |
| content-inset | 400 / 34 | 444 / 36 | 0 / 0 |
| control-size | 248 / 30 | 136 / 19 | 0 / 0 |
| icon-button-tooltip | 148 / 10 | 28 / 3 | 0 / 0 |
| text-contrast (mostly unresolved) | 138 / 22 | 98 / 17 | 54 / 9 |
| viewport-bounds | 96 / 14 | 52 / 13 | 0 / 0 |
| label-consistency | 56 / 10 | 56 / 10 | 56 / 10 |
| control-state | 20 / 3 | 0 / 0 | 0 / 0 |
| target-size | 16 / 3 | 16 / 3 | 0 / 0 |
| content-clipping | 12 / 3 | 224 / 10 | 0 / 0 |
| **Total** | **8966 / 1654** | **1664 / 207** | **110 / 19** |

Reading the middle column:

* `control-gap`, `control-inset`, `content-inset` and `content-clipping` stay high there because
  they are the list, segmented-control, icon-button and visually-hidden patterns that the final
  exceptions cover.
* `content-clipping` and `content-inset` *rise* from the before column because the compact nav
  now has clipped screen-reader labels, and its 16 px icons sit in 32 px buttons.
* The "before" run did not yet have the counter-badge and graph-node `typeRules`, which accept
  11 px badges inside buttons and 14 px node names on a `role=button` node. That accounts for a
  few hundred of the 4528 font-size occurrences. The rest are genuine off-scale sizes.

Before the policy was tuned (lintapple's default 12–64 px policy, no markers), the same 44 checks
gave 7314 / 1502 (the graph-details state failed to open in that first run).

**Screenshots:** [`screenshots/lintapple/before`](screenshots/lintapple/before) and
[`after`](screenshots/lintapple/after), named `<state>-<width>-<theme>.png` at 2× scale. The
before set has no graph-details image because that state's driver step failed in the first run.

**Tests:**

* `npm test`: 163/163 passed (161 existing + 2 new type-scale tests).
* `npx playwright test` (main config, graph + DevCenter fake servers): **230 passed, 3 failed**.
  The same 3 tests fail on the original `src/` (checked by stashing this branch's `src` changes,
  rebuilding and re-running), so this branch did not cause them:
  * `devcenter-agent.spec.js:294` and `devcenter-plan.spec.js:344`: axe `color-contrast` 3.5–4.48:1
    on 12 px secondary text and red status text. The colours measured are mid-theme-switch blends.
  * `devcenterParts.spec.js:225`: menu typeahead focus.
* `playwright.guard*.config.js` and `playwright.graph-readability.config.js` were not run.

## Recommendations for the design system

1. **Type:** keep the seven steps above, and make 13 the default for UI and table text.
   * 14 is for prose such as descriptions and evidence. 12 is for metadata. 11 is only for
     counters, kbd and uppercase eyebrows, and never for a heading.
   * Use one h1 (24 px / 650) per page. Use weight and colour, not half-pixel size changes, to
     separate levels.
   * Show changing numbers with tabular numerals (`data-ui-number` marks them).
2. **Spacing:** use a 4 px grid (`--space-*`). Every control group gets an 8 px gap. Cards get
   16 px padding, and 20 px on the overview. Remove the remaining 5/7/9/10/14/18/22/26 px values
   (about 150 declarations; not done here, to keep the diff reviewable).
3. **Controls:** use three heights, 24 (xs), 28 (sm) and 32 (default), plus 36–44 for the one
   command field.
   * Every hit target is at least 24 px. Icons are 14 or 16 px only.
   * Icon-only buttons always pass through `Button` with an `aria-label`, which gives them a
     tooltip. Do not use native `title`.
   * Checkboxes and switches come only from the primitives.
4. **Radius:** collapse 3/4/5/6/8/9/10/12/14/16 px to three tokens: control 6, card 10 and pill.
   Nested surfaces should use `outer − inset` (mark them with `data-ui-radius` to have lintapple
   check it).
5. **Gate it:** run `scripts/lint-ui-states.mjs` against `tests/ui_audit_server.py` in CI (about
   5 minutes for 44 checks), together with `test/type-scale.test.js`. Pass every new exception
   through review with a written reason, as in the current policy.
