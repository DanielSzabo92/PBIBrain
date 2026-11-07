# PBIBrain Brain Inspector: visual contract (final)

Agreed by A, B, C. Desktop-only, existing stack. Contrast and OKLab ΔE×100 checked with `scratchpad/bscripts/*.py`.

**Principle:** neutral graphite chrome, **ink** the only accent; hue means type (icon + colour) or status (glyph + label).

## 1. Tokens (`src/theme.css`, existing names)

Values are listed as dark / light.

### 1.1 Chrome

| Token | Dark | Light |
|---|---|---|
| `--bg` (page, graph canvas) | #0e0e10 | #f7f7f5 |
| `--bg-sidebar` (title, sidebar, status bar) | #111113 | #f0f0ed |
| `--surface` (panels, nodes) | #151517 | #ffffff |
| `--surface-2` (inputs, popovers) | #1a1a1d | #fafaf8 |
| `--surface-3` (selected, active nav) | #212124 | #f1f1ee |
| `--surface-hover` | #1d1d20 | #f3f3f0 |
| `--line` | #26262a | #e5e4df |
| `--line-strong` | #333338 | #d4d3cd |
| `--line-focus` | #45454b | #bdbcb6 |
| `--control-border` (≥3:1 on `--surface-3`) | #6b6b73 | #85858c |
| `--text` | #ececee | #18181a |
| `--text-2` | #b4b4bb | #4d4d55 |
| `--text-3` (lowest text tone, ≥4.9:1 on `--surface-3`) | #8e8e97 | #66666e |
| `--text-inverse` | #0e0e10 | #ffffff |
| `--code-bg` | #121214 | #fafaf8 |
| `--grid-dot` (20px grid) | #1f1f23 | #e7e6e1 |

### 1.2 Ink accent
The `--brand*` names are kept and remapped:

| Token | Dark | Light |
|---|---|---|
| `--brand` = `--ring` | #ececee | #18181a |
| `--brand-strong` (hover) | #ffffff | #000000 |
| `--brand-ink` (text on a fill) | #0e0e10 | #ffffff |
| `--brand-soft` | rgb(236 236 238/.08) | rgb(24 24 26/.06) |
| `--brand-glow` (selection, input ring) | rgb(236 236 238/.16) | rgb(24 24 26/.12) |
| `--brand-line` | var(--line-strong) | var(--line-strong) |
| `--brand-tint` | var(--surface-3) | var(--surface-3) |

Aliases: `--proposal` → `--text-2` (dashed border), `--cmp-changed` → `--text`, `--row-active` → `--surface-3`. No hue accent anywhere.

### 1.3 Status

| Token | Dark / `-tint` | Light / `-tint` | Glyph |
|---|---|---|---|
| `--ok` | #5ccf9a / #1e2b27 | #157347 / #ecf4f0 | `CircleCheck` |
| `--warn` (stays amber) | #eeb85c / #2f291f | #8a540d / #f6f1ec | `TriangleAlert` |
| `--bad` | #f07f7f / #2f2223 | #bd3030 / #faeeee | `OctagonAlert` |
| `--info` (Merge models cells only) | #6fb6ee / #202831 | #216a9f / #edf3f7 | `Info` |

Text on tint ≥5.1:1. Status never fills a graph node.

### 1.4 Elevation
Resting panels/nodes: 1px `--line`, no shadow. `--shadow-md` menus/popovers; `--shadow-lg` dialogs; `--inset-hi` dark popovers only.

## 2. Type, spacing, radius

- Fonts unchanged: `--font-ui` Segoe UI Variable → Inter; `--font-code` JetBrains Mono. No new packages.
- Sizes unchanged (`ui-policy.json`): 11 kbd/counters · 12 meta · 13 body · 14 emphasis/inputs · 16 dialog/panel titles · 20 view h1/object title · 24 Overview h1 only.
- Weights 400/500/600 (650 → 600). Sentence case; delete `uppercase` + tracking (`.eyebrow`, Review headers → 12/500 `--text-2`).
- `tabular-nums` on `[data-ui-number]`, table cells, status bar, counts, confidence, zoom. `…` and curly quotes.
- `translate="no"` on names, DAX, paths, IDs; path inputs `spellCheck={false}` `autoComplete="off"`.
- Rows: 28 nav/menu · 32 list · 40 two-line · 44 header/graph toolbar. 4px grid.
- Radius: 4 controls/chips · 6 nodes/rows/menus/panels · 8 dialogs/pane/frames. Pills = counts only.

## 3. Object icon and colour map

Create a new `src/objectIcons.js` mapping each type to its icon and group. The graph, Search, Inspector, Review and Merge rows all import it. In `graphPresentation.js`, store `{dark, light}` per type.

| Type | Dark | Light | Icon | Contrast (dark / light) |
|---|---|---|---|---|
| MODEL | #6ea8fe | #2563c9 | `Database` | 7.6 / 5.7 |
| TABLE | #4cc2b0 | #0e8273 | `Table2` | 8.4 / 4.7 |
| COLUMN | #a2afc2 | #5d6b80 | `Columns3` | 8.2 / 5.4 |
| MEASURE | #c6c95a | #6b6d00 | `Sigma` | 10.3 / 5.5 |
| REPORT | #e68ac0 | #b83f86 | `FileChartColumn` | 7.6 / 5.1 |
| PAGE | #c49bf2 | #7c4fc4 | `PanelsTopLeft` | 8.1 / 5.6 |
| VISUAL | #f0995e | #b4561c | `ChartColumn` | 8.2 / 4.9 |
| Other / semantic | #b5ac9c | #7a7163 | per type | 8.1 / 4.8 |

- Every type is at least ΔE 5.0 from every status colour.
- Model to Table is ΔE 15.7 in dark and 18.2 in light.
- Violet (Page) is a data colour only.

**Other icons** (group colour): Relationship `Link2`, Calc group/item `Layers`, Field parameter `ListFilter`, Shared expression `Braces`, UDF `SquareFunction`, Visual calculation `Calculator`, Filters `Funnel`, Concept `Lightbulb`, Alias `Tag`, Role `ShieldUser`, Behavior `Activity`, Selector `ToggleLeft`, Conflict `OctagonAlert`, Workspace `FolderOpen`.

**Type chip:** a 24px square (20px in lists, 16px in tables), radius 4, filled with `color-mix(in srgb, <type> 14%, transparent)`. It holds a 14px glyph in the type colour. This replaces `.artifact-dot`, the `.result-type` pills and `.flow-node::before` stripes.

**GraphColors:** user sets dark; light = `color-mix(in oklch, c 55%, #18181a)`. Warn (not block) below 3:1 or within ΔE 5 of a status/type. Presets "Default", "High contrast". Delete the light `saturate(1.6) brightness(.72)` filter (app.css ~787).

## 4. Provenance (one rule everywhere)

| Evidence | Edge | Border (chip, node, card) | Glyph | Label |
|---|---|---|---|---|
| Fact | solid | solid | `Check` | From source |
| Inferred | dash `6 4` | **dashed** | `CircleDashed` | Suggested |
| Observed | dot `1.5 3`, round caps | dotted | `Eye` | Observed |

- Decisions: approved `BadgeCheck`, rejected `CircleX`, overridden `PenLine`. Remove `Sparkles`/`Bot` (status-badge, notice, NameField, ProposalCard, ImpactItemRow); agent = `Terminal`.

## 5. Icons and actions

16px, stroke 1.75 (14px in nodes/tables), `aria-hidden` when labelled; one glyph per concept:

| Concept | Icon |
|---|---|
| Overview | `House` |
| Search, command center | `Search` |
| Graph | `Waypoints` |
| Inspector, Open in Inspector | `PanelRight` |
| Review queue | `Inbox` |
| **Merge models** | `GitMerge` |
| Settings | `Settings` |
| Scan sources (all places; App.jsx:769 uses `RefreshCw` today) | `ScanLine` |
| Reload (menu only) | `RotateCw` |
| Filters | `ListFilter` |
| Display options | `SlidersHorizontal` |
| Focus | `LocateFixed` |
| Show connections | `Crosshair` |
| Copy | `Copy` → `Check` |

No `ArrowUpRight` for in-app jumps.

## 6. States

- Hover: `--surface-hover`, text `--text-2`→`--text`, nothing moves. Press: `scale(.985)` (drop `translateY` in `.ui-button:active`).
- Selected row `--surface-3`; active nav adds a sliding 2px ink bar.
- Focus (`:focus-visible` only): 2px ink outline, offset 2px, instant; −2px inside lists/nav. Inputs: ink border + `0 0 0 3px var(--brand-glow)`; drop `:focus` at app.css:89.
- Disabled: opacity .45, `not-allowed`, tooltip with reason.

## 7. Motion

| Token | ms | Use |
|---|---|---|
| `--dur-press` | 90 | press scale |
| `--dur-fast` | 120 | colour, hover |
| `--dur` | 180 | popover/menu (fade + 4px drop), indicators, check draw, row fade-out |
| `--dur-pane` | 240 | docked pane (translateX 16→0 + fade), dialogs |
| `--dur-slow` | 280 | graph relayout, group expand, review FLIP |
| `--dur-fit` | 320 | fitView, focus selected |

- Easing: `--ease-out` (.22,1,.36,1) enter; `--ease-in` (.4,0,1,1) exit at 70% duration; `--ease-move` (.65,0,.35,1) travel. Delete `--ease-spring`.
- `transform`/`opacity` only; colour ≤120ms. Never width/height/outline-offset (`.meter i` → `scaleX`, origin left). No `transition: all`; tokenise devcenter screens.css:111,169.
- No loops: delete `breathe`, `pulse-dot`, `shimmer`, dot loaders, `toast-in` scale. Scan bar runs only while scanning; placeholders static 40% rows after 300ms.
- Interruptible: wheel/drag cancels fitView.
- Reduced motion: replace app.css:48 `0s !important`; keep ≤120ms colour/opacity, transforms instant, graph durations 0.

## 8. Shell and navigation

- Sidebar 212px: Overview, Search, Graph, Inspector · divider · Review queue (neutral badge), Merge models · Settings at bottom. Remove `.nav-kbd` (app.css:268); shortcuts in tooltips + F1.
- Project name once: title-bar switcher (absorbs "Change project"); removed from status bar.
- One 44px view header; its title is the `<h1>` 20/600 (replaces breadcrumb + `PageHeading` repeat). Actions: "Scan sources" only; reload (App.jsx:600) → View › Reload (F5).
- Hash routes: `#/overview`, `#/search?q=&model=&report=&type=`, `#/graph?view=&focus=`, `#/inspector/<id>`, `#/review?issue=&type=`, `#/merge`, `#/settings/<section>`; Alt+← back.
- `useTheme` updates `<meta name="theme-color">`.

## 9. Views

**P0 — Graph** (§11).

**P0 — Overview**
- h1 + one line of clickable type chips (glyph, count, label) → filtered Search.
- "Needs attention" ledger: review, validation, sources; one status glyph and ≤1 action each (review action ink-primary).
- Remove inline search (App.jsx:791), 1/2/3 stepper (empty = one sentence + "Add sources"), "Export agent context" (→ File), the sources-row scan button.

**P0 — Review queue**
- One line replaces the banner; items grouped by object.
- Columns: object chip/name/scope · suggestion as dashed chip (`Alias → “Sales Target”`) · one-line evidence · confidence (number in `--text`, 40px `--text-3` meter, number `--warn` <60%) · Approve (outline) / Reject (ghost).
- Decision → "Approved · Undo" for **5s** (also **Z**), then fade 180ms + FLIP 280ms. Keys J/K/A/R/E. `content-visibility:auto` beyond 50 rows.

**P1 — Search:** 44/56 split, results | live preview. 32px rows: 20px chip, name 13/500, mono scope, match snippet. ↑↓ previews, Enter → Inspector. One filter bar. Empty = Recent + type chips.

**P1 — Inspector:** empty state h1 "Inspector" + **Recent objects** ("Browse objects" removed). Title row: chip, name, `Model › Table` path, provenance chip, "Show in graph". Left: definition, DAX on `--code-bg`, evidence collapsed ("3 suggestions · highest 97%"). Right rail 320px: Used by / Depends on; if both empty, one line.

**P1 — Merge models:** keep Compare and glyphs; validity → status chip; stuck skeletons → "Not loaded"; blue dots → labelled "Changed since"; pin Object column; hide status-bar counts at 0 objects.

**P2 — Settings:** 200px section list (Project, Sources, Graph colours, Model summary, Keyboard, Appearance) | form, Save in footer; colour previews in both themes.

## 10. Removals

Periwinkle `--brand`/violet accent · uppercase · weight 650 · dot pills, side stripes · node hover lift · `Sparkles`/`Bot` · Overview search, stepper, hero numbers · Review banner · reload icon · project name ×3 · `.nav-kbd` · graph group tabs, meta strip, hint text (→ F1), always-on edge labels · light saturate filter · `breathe`, `pulse-dot`, `shimmer`, `toast-in` scale, dot loaders · zoom `role=status` (GraphView.jsx:323).

## 11. Graph visual contract

1. **Toolbar (44px)** replaces four bands (GraphView.jsx:211–241, ~250px): Find (240px) · Overview | Connections | Full graph · `Types ▾` (glyph, name, count, checkbox = legend + filter) · `Display ▾` (direction, Relationship labels, Include suggestions, Group by ownership) · `Filters (n) ▾` (model, report, status, edge type, Clear) · "n objects · m links" · Fit. Canvas ≥80% of view height; bottom strip = evidence samples only.
2. **Pane docks** at 360px, pushing the canvas (replaces `.ui-sheet`, app.css:825); re-fits to keep selection visible; Esc closes; `overscroll-behavior: contain`. Actions: Show connections, Open in Inspector.
3. **Nodes:** leaf 168×32, group 200×48; `--surface`, 1px `--line-strong`, radius 6, no shadow; 24px chip + name 13/500 one line, middle ellipsis (full name in tooltip and `aria-label`, e.g. "Measure Net Sales"); groups add `+n ›` ("Expand Finance model (5 inside)"); status = 14px glyph top-right; suggested = dashed border.
4. **States:** hover `--line-focus`, no motion; selected 2px ink ring + 2px `--bg` gap; focus same ring at 4px offset; search match dotted ink ring; on selection non-neighbours .25, their edges .12 (180ms).
5. **Edges:** opaque **#6b6f7a / #8a8f99** (3.6:1 / 3.0:1 on canvas), 1.25px, smoothstep, 6px arrowheads, never type-coloured, dimmed only during selection. Lineage path ink 2px. Labels only on hover/selected path, 12px on `--bg` chip.
6. **Structure:** CONTAINS/BELONGS_TO become nested frames (`--surface` 50%, 1px `--line`, radius 8, header glyph + name 12/600 + count), not edges.
7. **Edge families:** dependency (DEPENDS_ON, REFERENCES, USES, USES_MODEL) by default; filter/relationship in Connections and Full; semantic only with Include suggestions.
8. **Density:** defaults Overview, LR, labels off, suggestions off; auto-collapse >40 visible; rank gap 96, node gap 24; fit minZoom .75 (collapse, don't shrink); minimap >30 nodes.
9. **Semantic zoom:** ≥0.8 full; 0.45–0.8 glyph + name; <0.45 10px type dot, no labels. Never text <11px.
10. **Keys:** arrows → connected node, Enter → Inspector, Space expand, + − 0 zoom, F fit, Esc clears then closes. Every gesture has a key/button.

**As built (2026-11-07):**
- Fit stops at zoom .85, not .75, so 13px names never render under 11px. Full graph fits down to .55.
- Semantic zoom: at .85 and above, names are full size. From .55 to .85, names are counter-scaled to 11px on screen and shortened in the middle. Below .55, a node shows only its glyph, and the hovered or selected node gets a 12px label. Edge labels hide below .92.
- Containment is shown as quiet tree lines (`--graph-structure`, 1px, no arrowhead) rather than nested frames. Nested frames would move nodes when a group expands, which breaks the overview's stable positions.
- Enter on an unselected node selects it, and Enter on the selected node opens the Inspector. Space expands a group, or selects a leaf.
- For its first 350ms the pane overlays the canvas, so the second click of a double-click still reaches the node. After that the pane docks, and the view pans just enough to keep the selection visible.
- Types hide object types in the loaded slice on the client (checkbox, or "Only"). The server-side "Objects" (artifact group) filter moved into Filters.

### 11a. Lineage and Matrix (owner request, 2026-11-07)

**Lineage** replaces "Full graph", and the focused Connections view uses the same layout. Every object sits in the lane of its type, read left to right the way data flows into a report:

Models › Tables › Columns › Calculations (measures, field parameters, calculation groups, UDFs) › Visuals › Visual filters › Pages › Page filters › Reports › Report filters › Meaning (concepts, aliases, roles).

- **Lanes:** empty lanes are skipped, and lanes are top-aligned under one row of lane headers, each showing a name and count.
- **Order within a lane:** objects stay in their model or report block, then grouped by owner (columns by table, visuals by page). Owners are ordered to follow the previous lane, which keeps links straight.
- **Links:** every link is drawn in flow direction, so arrows read "flows into". Inside a lane, a dependency flows from the object that is used to the object that uses it.
- **Selecting an object** traces its whole chain: everything that feeds it and everything it feeds, up to the report. Sibling objects stay dimmed. Only real data flow counts (dependency and ownership links); "observed with", semantic and similarity links do not.
- **Opening view:** when the lanes cannot fit at a readable zoom, the view opens at Models (top-left), not in the middle.

**Matrix** shows impact analysis as a grid: model objects (columns and calculations) down the side, report visuals across the top.

- **Grouping:** rows are grouped by model › table, and columns by report › page. Every group folds. A folded cell shows how many of its pairs are used, shaded by heat.
- **Cells:** a solid mark means direct use (field well, visual filter). An outlined mark means indirect use: through a calculation, or through a page or report filter that applies to the visual. This follows the same solid-versus-outline language as provenance.
- **Several models and reports:** they appear as blocks. Reports are ordered by their bound model, so blocks run down the diagonal. A model/report block whose report is not bound to that model is hatched, so an empty cell always means "not used" and never "cannot be used".
- **"Used by" column:** the count of visuals plus a small bar. Unused objects are flagged in warn colour, and "Hide unused" filters them out.
- **Scope:** the matrix loads up to 1,000 objects. Above that, a notice points to the model and report scope in Filters.
- **Folding defaults:** tables fold when there are more than 160 rows, and pages when there are more than 48 visuals.

## 12. e2e name changes

| Old | New | Update |
|---|---|---|
| "Development Center" (nav, breadcrumb, `shortcuts.js:15`) | "Merge models" | All `e2e/devcenter-*.spec.js` (shell, a11y, agent, apply, compare, impact, plan, row, rules) and devcenterHarness. Add a shared `openMerge(page)` helper. Update `test/devcenter-*` copy asserts. |
| "Rescan" | "Scan sources" | `product.spec.js:47,53` and `productRefinement.spec.js:167,229`. Their `exact` counts stay unique because the Overview row loses its scan button. |
| "Reload Brain" button | View › Reload (F5) | `product.spec.js:29`, `productRefinement.spec.js:114` |
| "Browse objects" | h1 "Inspector" plus Recent objects | `overhaul.spec.js:21,117` |
| "Full inspector" | "Open in Inspector" | `graphSession.spec.js:26`, `graphExplorer.spec.js:51`, `overhaul.spec.js:234` |
| "Explore connections" / "Center graph here" | "Show connections" | graph specs |
| "Impact Explorer" | "Open impact" | `guardedDevelopment.spec.js:14` |
| "Relationship labels" | unchanged, but now inside the Display popover | `graphExplorer.spec.js:149` must open Display first |

Unchanged: Overview, Search, Graph, Inspector, Review queue, Settings, Main navigation, Approve, Reject, Show in graph.

## 13. Accessibility checks

1. Text ≥4.5:1; type colours, edges, control borders, focus ring ≥3:1 — axe on every view, both themes (extend `devcenter-a11y.spec`).
2. Icon-only buttons have `aria-label`; decorative icons `aria-hidden`.
3. Visible `:focus-visible` everywhere; audit `outline:none` at devcenter.css:60,87 and CompareRowDetail.jsx:306,903.
4. Colour never the only cue (type = glyph, status = glyph + label, provenance = line style + label).
5. `aria-live="polite"` on Undo, scan state, search counts; nothing on zoom.
6. 5s Undo (button + Z) on every decision.
7. One e2e pass with `reducedMotion:'reduce'` (§7).
8. Graph keyboard round trip without a mouse.
9. One h1 per view; skip link works.
10. 80-char names truncate (`min-w-0`) with full text in tooltip and `aria-label`.

