# Brain Inspector UI audit: impeccable lens

Branch: `claude/ui-audit-impeccable` · Skill: impeccable 4.8.0 (`init`, `document`,
`critique`, `audit`, `distill`, `typeset`, `layout`, `polish`) · Date: 2026-11-06

⚠️ DEGRADED: single-context. The critique playbook wants Assessment A (design
review) and Assessment B (detector) in two isolated sub-agents. This run did both
in one context: the brief required the detector up front, so isolation was
already gone, and three audits were running in parallel. Treat the heuristic
scores as one reviewer's judgement, not a blind dual review.

Product context (`frontend/PRODUCT.md`) and the design system
(`frontend/DESIGN.md`) were written for this run. PRODUCT.md is inferred from
README.md, CONTEXT.md and frontend/README.md with no live interview (the brief
said not to block on questions), and inferred lines are marked.

## How the app was inspected

- Built `frontend/dist` and served it through the repo's own fixture servers:
  `python -m tests.graph_ui_server --port 8765` (a real scanned model + report,
  native graph DB) and `python -m tests.devcenter_ui_server --port 8766`
  (the `default` merge scenario).
- Playwright captured every main view (Overview, Search, Graph, Inspector,
  Review queue, Development Center, Settings) in dark and light, at 1440×900 and
  390×844: 28 captures before and 28 after. A representative set is in
  `screenshots/impeccable/`.
- Ran the impeccable detector two ways: statically over `frontend/src` (regex
  rules), and over the rendered DOM of each view (each view dumped to static
  HTML with the built CSS, so element rules such as nested cards, kickers,
  skipped headings and tiny text could run).

## Verdict in one paragraph

The app is careful underneath: tokens for both themes, real empty, loading and
error states, labelled provenance, axe sweeps, keyboard handling. The "slop"
feeling comes from the surface, not the engineering. Overview in particular is
the 2024 SaaS dashboard template, piece by piece: an uppercase kicker over the
title, four hero-metric stat tiles, a big number in a tinted rounded square, and
three same-size icon-in-a-square cards with ↗ arrows that only repeat the
sidebar. Under that sits a type system with no scale (17 font sizes, half-pixels
included) and 13 border radii, so no two screens feel built from the same parts.
This is a dense tool for experts that sits beside Power BI Desktop, and it
should read like a ledger, not a landing page.

## Design health score (Nielsen, critique)

| # | Heuristic | Score | Key issue |
|---|-----------|-------|-----------|
| 1 | Visibility of system status | 3 | Connection, scan state, review count and graph truncation ("3 visible · 7 in collapsed groups") are all shown. The count is also shown three times on Review (nav badge, banner, table). |
| 2 | Match system / real world | 3 | Uses the CONTEXT.md vocabulary (Target, Donor, Change Plan). "Business concept" and "Role: fact" in Inspector are internal terms. |
| 3 | User control and freedom | 3 | Back links, Escape closes the sheet, filters can be cleared. Review decisions are removable. |
| 4 | Consistency and standards | 1 | 17 font sizes, 13 radii, three different "status" treatments (tinted card, side stripe, icon tile). Before this audit, outline buttons had shadows and primary buttons didn't. |
| 5 | Error prevention | 3 | Destructive merge actions sit behind the Change Plan. Save is disabled until something changes. |
| 6 | Recognition rather than recall | 3 | Type chips on every result, breadcrumb, a legend on the graph. |
| 7 | Flexibility and efficiency | 2 | Ctrl K and `/` exist, but there is no keyboard path through Review approvals, and the Graph puts three toolbar rows between the user and the canvas. |
| 8 | Aesthetic and minimalist design | 1 | Overview was decoration-first: hero tiles, icon tiles, a kicker, duplicate navigation cards. Window chrome carried a tagline per view. |
| 9 | Error recovery | 3 | Errors name the problem and offer retry (inline-error, EmptyState with action). |
| 10 | Help and documentation | 2 | One-line hints exist. No in-app explanation of what fact / inferred / observed mean beyond the legend. |
| **Total** | | **24/40** | **Acceptable: solid underneath, generic on the surface** |

## Technical audit score (audit)

| # | Dimension | Score | Key finding |
|---|-----------|-------|-------------|
| 1 | Accessibility | 3 | axe sweeps and focus handling are in place. Headings skipped levels (h1 → h3 on Overview and Inspector), there was 10.5px functional text, and reduced motion is a global `0s !important` kill (`app.css:47-48`). |
| 2 | Performance | 3 | Views are lazy-loaded. The main chunk is still > 500 kB (Vite warning). |
| 3 | Theming | 3 | Full token set for both themes. 50 hex literals in JS, e.g. `EDGE_COLORS` (`App.jsx:37`) and the `#738294` fallback (`App.jsx:905`), do not change with the theme. |
| 4 | Responsive | 2 | Under 760px the nav becomes a horizontally scrolling strip, and Inspector, Review, Development Center and Settings sit off-screen with nothing to show they exist. This is acceptable for a desktop-first tool, but the strip needs an overflow cue. |
| 5 | Implementation integrity | 2 | Design-system drift (type, radius, shadow) and template scaffolds on Overview. `App.jsx` is a 1,000-line file of one-line JSX, which makes drift easy. |
| **Total** | | **13/20** | **Acceptable** |

## Detector output

### Before (HEAD `283345b`)

Static scan, `impeccable detect frontend/src`: **4 anti-patterns + 2 advisories**

```
app.css:504  [side-tab] border-left: 2px solid var(--line-strong)      (.evidence-card)
app.css:590  [side-tab] border-left: 3px solid var(--artifact-color)   (.color-preview-node)
app.css:825  [side-tab] border-left: 2px solid var(--line-strong)      (.detail-evidence)
guard.css:4  [side-tab] border-left: 3px solid var(--primary)          (.guard-warning)
app.css:287  [bounce-easing] toast animation var(--ease-spring)       (advisory)
theme.css:44 [bounce-easing] cubic-bezier(0.34, 1.4, 0.64, 1)          (advisory)
```

Rendered scan, 7 views: **41 findings + 2 advisories**. The ones that matter:

```
overview   [kicker-above-heading] "Project overview" above h1
overview   [icon-tile-stack] 32x32 icon tile above h3 "Graph validation not run"
overview   [skipped-heading] h1 → h3 "Ready for review"
overview   [cramped-padding] .review-card-count
inspector  [skipped-heading] h1 "Net Sales" → h3 "Definition"
inspector  [nested-cards] card inside card;  [cramped-padding] .code-head, .ui-card
graph      [nested-cards] ×3 (toolbar card inside the graph card)
graph      [undersized-ui-text] 10.5px "100%" zoom label            (advisory)
devcenter  [cramped-padding] ×8 (.dc-badge, .ui-filter-chip, .ui-segmented, .dc-row)
devcenter  [repeating-stripes-gradient] .dc-wire-box[data-status=removed] (advisory)
all views  [cramped-padding] .sidebar-footer;  [pulsing-dot] .graph-loader i, .connecting-indicator i
```

Calls on the detector output:
- `pulsing-dot` on `.connecting-indicator` and `.graph-loader` fires on every view
  because the CSS rule exists, not because the element is on screen. Both are
  real loading indicators, used only while waiting, so this is a **false positive
  in context**.
- `repeating-stripes-gradient` on the Development Center "removed" wireframe
  box carries meaning: hatching means "removed", a convention from
  engineering drawings. **Keep it.**
- The `cramped-padding` hits on DevCenter badges and chips are 20px-tall
  inline pills, where flush vertical text is intended. **Low value.**
  `.sidebar-footer` is a real but minor one.
- The rest are **real**, and they agree with the manual review.

### After (this branch)

Static scan: **0 anti-patterns, 0 advisories** (exit 0; was 4 + 2).

Rendered scan, 7 views: **32 findings + 1 advisory** (was 41 + 2).

| Rule | Before | After | Note |
|------|-------:|------:|------|
| kicker-above-heading | 1 | 0 | removed |
| icon-tile-stack | 1 | 0 | removed |
| skipped-heading | 2 | 0 | h3 → h2 on Overview and Inspector |
| nested-cards | 4 | 0 | Resting cards lost their shadow, so the detector no longer reads the Graph toolbar as a card. **Visually the toolbar is still a panel inside a panel (P1 #4, open).** |
| undersized-ui-text | 1 (adv.) | 0 | 11px floor from the type scale |
| cramped-padding | 18 | 18 | Unchanged. `.review-card-count` is gone; `.sidebar-footer` ×7 already has 10px top padding (likely a false positive); DevCenter pills are intentionally flush. |
| pulsing-dot | 14 | 14 | False positive in context (loading indicators; the CSS exists on every page) |
| repeating-stripes-gradient | 1 (adv.) | 1 (adv.) | Keep: the hatching means "removed" |

Every remaining finding is triaged above as a false positive, intentional, or
a known open item.

## Findings (P0–P3)

No P0: nothing blocks a task or loses data.

### P1: makes the product feel generic or hurts every screen

1. **Overview is the SaaS hero-metric template** (`App.jsx` Overview, HEAD
   `App.jsx:684-731`). Its parts: the kicker "Project overview", 4 stat tiles
   (`.stat-tile`, 30px numbers), the review count in a 72px tinted square
   (`.review-card-count`), and 3 icon-tile quick-action cards. Two of those
   cards (Graph, Inspector) repeat the sidebar. A Power BI developer opening
   the tool wants one thing: what needs me, and where is my object. **Fixed:**
   the project name with the counts as one inline line ("1 model · 1 report · 20
   objects · 25 relationships"), a plain 36px search field, and one status panel
   of rule-separated rows (Review → Validation → Sources). Tone shows in the icon
   or count colour. The duplicate navigation cards are gone; "Export agent
   context" became a row action under Sources.
2. **No type scale** (all CSS; 17 distinct sizes: 10, 10.5, 11, 11.5, 12,
   12.5, 13, 13.5, 14, 14.5, 15, 16, 19, 22, 24, 26, 30px). Half-pixel steps
   are noise, not hierarchy. **Fixed:** seven tokens (`--type-micro` 11 →
   `--type-display` 24, `theme.css`), and every `font-size` in `src/**/*.css`
   now uses one. Page titles dropped from 30px to 20px; only the project name
   on Overview uses 24.
3. **Uppercase kickers and tracked micro-labels as headings**
   (`.eyebrow`, `.panel-title`; Overview, Desktop project, Model summary, Guard
   review, onboarding "PBIBrain" above the h1). **Fixed:** kickers removed.
   `.panel-title` ("Definition", "Lineage") is now a 14px/600 sentence-case h2.
   `.eyebrow` / `.field-label` are sentence-case 12px field labels.
4. **Graph toolbar takes three stacked rows before the canvas**
   (`components/GraphView.jsx:220-241`): search + scope chips + filters, then
   view tabs + help sentence + Collapse, then layout + checkboxes + hint. All
   of it sits in a card inside the graph card (detector: nested-cards ×3).
   **Not fixed (needs the GraphView owner):** merge it into one toolbar row
   and a "View" popover; drop the help sentences once the canvas has hover hints.

### P2: drift and friction

5. **Coloured side stripes** on evidence blocks, colour-preview nodes, the graph
   details evidence, and guard warnings (detector side-tab ×4). **Fixed:** a 1px
   full rule with a 6px radius; guard warnings use the warn tint. The Inspector
   lineage rows still use a 3px artifact-colour bar (`.relationship-row`). That
   one encodes data and matches the graph nodes, so it stays.
6. **13 border radii** (3, 4, 5, 6, 8, 9, 10, 11, 12, 14, 16px, 99px, 999px).
   **Fixed:** `--r-xs` 4 / `--r-sm` 6 / `--r-md` 8 plus pills. Buttons are 4px
   (`ui/button.jsx`), and `--radius` is 6px, so the shadcn primitives follow.
7. **Shadows on resting surfaces**: every card, outline button and the active
   nav item had `--shadow-sm` + an inner highlight. **Fixed:** flat at rest.
   Shadows stay only on overlays, the sheet, toasts and the onboarding card.
8. **The Review queue repeats itself** (`App.jsx:970`): the count appears in the
   nav badge, the banner ("10 to review") and the table. Each suggestion for the
   same object is its own row with the same "The source description says …"
   sentence. **Not fixed:** group suggestions by object (one row per object with
   its 2–3 suggestions inline), drop the banner count, and add `j/k` + `a/r`
   keyboard approval for power users.
9. **Inspector suggestion actions are heavy** (`App.jsx:1022`): four controls
   (Approve, Edit, Reject, Set meaning) with mixed styles (outline, ghost,
   ghost, link) on every suggestion, followed by a full-width evidence block.
   **Not fixed:** one Approve button plus a "…" menu, with evidence inline as
   meta text.
10. **Edge colours ignore the theme** (`App.jsx:37` `EDGE_COLORS`, the
    `#738294` fallback at `App.jsx:905`). They are pastel hex values tuned
    for dark mode and too light on the light canvas. **Not fixed:** move them
    to `--edge-*` tokens with light values.
11. **Narrow nav strip has no overflow cue** (`app.css` `@media (max-width:
    760px) .sidebar-nav`). Half the views are off-screen. **Not fixed:** add a
    fade mask, or collapse to a menu button.

### P3: polish

12. **A tagline per view in the window chrome** ("Project health at a glance",
    "One object, fully explained", `VIEW_HINTS`). **Fixed:** removed. The page
    heading already explains the page.
13. **Spring easing** on toasts (`--ease-spring` overshoot 1.4). **Fixed:**
    quint ease-out. The token name is kept as an alias so callers keep working.
14. **Font is not native to the scene.** The desktop build runs in a Windows
    WebView2 window next to Power BI Desktop, which uses Segoe UI. **Changed:**
    `--font-ui` now prefers Segoe UI Variable, with Inter kept as the bundled
    fallback. On Linux and macOS (and in these screenshots) nothing changes;
    on Windows the tool should feel native.
15. **The global reduced-motion kill** (`app.css:47-48`) sets every
    transition to 0s, which also removes useful state feedback. **Not fixed:**
    keep the opacity and colour transitions and drop only the transforms.
16. **"1 models"**: the new inline counts needed plural handling, and it was
    added while building them.
17. **"Graph validation passed" next to "View validation issues (4)"**
    (Overview validation row; seen after the e2e fixtures ran). A pass that
    lists issues reads as a contradiction. **Not fixed:** say "passed with 4
    notes", or show the issue count only when something fails or warns.

## Design direction

**North star: "The Lineage Ledger"** (full spec in `frontend/DESIGN.md`).

- **What it should feel like.** A precise reference instrument that sits beside
  Power BI Desktop, Tabular Editor and VS Code: calm, exact, dense. The user's
  model is the content. The UI is ruled paper.
- **Hierarchy.** One question per screen, answered first. Overview: "what needs
  me?" (status rows). Search: "which object?" (results list). Inspector: "what
  is it, and what touches it?" (definition + lineage). Group with alignment and
  1px rules before adding a container. Cards never sit inside cards.
- **Typography.** One sans family, native first (Segoe UI Variable → Inter),
  in seven steps from 11 to 24px at a ratio of about 1.1 through the UI range.
  Weight does the hierarchy work (400 / 500 / 600 / 650), not size jumps. Mono
  (JetBrains Mono → Cascadia Code) only for DAX, M, paths and IDs. Tabular
  numerals everywhere numbers line up.
- **Colour.** Keep the existing neutral graphite / paper themes and the
  periwinkle accent. **The hue is not the problem; ubiquity is.** Colour
  belongs to data: user-editable artifact colours, provenance line styles,
  status. The accent marks one primary action per region, the current
  selection and focus. It does not tint card borders, number boxes or icon
  tiles.
- **Density.** Desktop-first. 32px controls, 34px nav rows, 14–16px row
  padding, 36px for the one primary search field. Rows over cards. Narrow
  widths must stay usable, but they are not the design target.
- **Elevation and shape.** Flat at rest; shadows only for things that float.
  Radii of 4 / 6 / 8px. No coloured one-sided borders. No hero metrics, kickers
  or icon tiles.
- **Motion.** 120–200ms ease-out on state changes only. No springs, and no
  entrance choreography.

## What changed on this branch

| Area | Change | Files |
|------|--------|-------|
| Tokens | `--type-*` (7 steps), `--r-xs/sm/md`, `--radius` 8 → 6px, Segoe-first `--font-ui`, spring → quint | `src/theme.css` |
| Type and radius | Every `font-size` / `border-radius` px literal mapped to a token (8 CSS files, about 340 declarations) | `src/app.css`, `src/guard.css`, `src/devcenter/**/*.css` |
| Primitives | Buttons 4px radius, 12px small size; outline buttons, cards and the active nav item are flat | `src/components/ui/button.jsx`, `src/app.css` |
| Overview | Kicker, stat tiles, review count box, icon tiles and quick-action cards replaced with inline facts + search + one status panel; headings h3 → h2 | `src/App.jsx` (Overview), `src/app.css` |
| Kickers | Removed from onboarding, Desktop project, Model summary and Guard review; panel titles and field labels are sentence case | `src/App.jsx`, `src/components/ModelSummary.jsx`, `src/components/GuardReview.jsx` |
| Side stripes | 4 one-sided borders → full 1px rules | `src/app.css`, `src/guard.css` |
| Chrome | Per-view taglines removed from the top bar | `src/App.jsx` |
| Motion | Tab panels no longer fade in on switch (instant, like native tabs) | `src/app.css` |
| Docs | PRODUCT.md, DESIGN.md | `frontend/` |

The changes are deliberately systemic: tokens and shared primitives, plus the
one screen that read most as a template. The P1/P2 items left open (Graph
toolbar, Review grouping, Inspector actions, edge tokens, narrow nav) are
structural, and each needs its own reviewed change.

## Tests

- `npm test` (node unit + contract tests): 161/161 before and after.
- `npx playwright test` (main e2e config, 233 tests, fixture servers on 8765/8766):
  - The first run after the redesign had 2 failures.
    `graph.spec.js:196` asserted that Overview renders a shared `Card`
    primitive; fixed by building the status panel from `Card`.
    `devcenterParts.spec.js:225` (menu focus return) is **pre-existing and
    flaky**: it failed 3 of 4 times on the untouched baseline too.
  - `devcenter-plan.spec.js:344` (axe, plan states) then failed intermittently.
    The cause was a race: axe sampled text halfway through the 200ms
    tab-content fade-in, so half-faded text read as low contrast. Tabs now
    switch instantly, like native tabs (`app.css:118`); the test passed 5 of 5
    repeats after that.
  - Final run: **232 passed, 1 failed**. The failure is the known baseline flake `devcenterParts.spec.js:225`.

## Screenshots

`docs/ui-audit/screenshots/impeccable/`, named `<view>-<theme>-<width>-before|after.png`.
