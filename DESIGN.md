# PBIBrain — Design

Taken from the code as of 2026-11-16. Where this file and the code disagree, the code is right.

| Source of truth | File |
|---|---|
| Tokens (colour, type, space, radius, motion, shadow) | `frontend/src/theme.css` |
| Primitive styles | `frontend/src/styles/base.css`, `frontend/src/devcenter/devcenter.css` |
| Components (shadcn) | `frontend/src/components/ui/` |
| Shell layout | `frontend/src/components/AppShell.css`, `frontend/src/components/ChatPanel.css` |
| Breakpoints | `frontend/src/styles/responsive.css` |
| Object type colours and icons | `frontend/src/graphPresentation.js`, `frontend/src/objectIcons.js` |
| Rules checked by tests | `frontend/ui-policy.json` |

---

## 1. Principles

- Dense desktop data tool, not a marketing page
- Dark theme by default, light theme maps the same tokens to other values
- **Ink is the only accent.** Primary = near-white in dark mode, near-black in light mode
- Hue is used only for **object type** and **status**
- Status colours never double as type colours
- Tokens only. No raw hex in components
- Opaque `-tint` under text, never a translucent `-soft`
- Motion: only `transform` and `opacity`. Reduced motion = static

---

## 2. Stack

| Part | Choice |
|---|---|
| Framework | React + Vite |
| CSS | Tailwind v4 (`@import "tailwindcss"`, `@theme inline`) + plain CSS per view |
| Components | shadcn/ui, style `new-york`, base `neutral`, CSS variables on, JSX (no TS) |
| Primitives | `radix-ui` |
| Variants | `class-variance-authority` |
| Icons | `lucide-react` |
| Toasts | `sonner` |
| Graph | `@xyflow/react` |
| Animation helpers | `tw-animate-css` |
| Fonts | `@fontsource-variable/inter`, `@fontsource-variable/jetbrains-mono` |

shadcn config: `frontend/components.json` → aliases `@/components`, `@/components/ui`, `@/lib/utils`, CSS in `src/theme.css`.

---

## 3. Colour

### 3.1 Surfaces and lines

| Token | Dark | Light | Use |
|---|---|---|---|
| `--bg` | `#0e0e10` | `#f7f7f5` | App canvas |
| `--bg-sidebar` | `#111113` | `#f0f0ed` | Title bar, side bar |
| `--surface` | `#151517` | `#ffffff` | Cards, dialogs, panes, chat |
| `--surface-2` | `#1a1a1d` | `#fafaf8` | Inputs, menus, popovers, tab list |
| `--surface-3` | `#212124` | `#f1f1ee` | Secondary button, selected row, active tab |
| `--surface-hover` | `#222226` | `#ebebe7` | Hover |
| `--line` | `#26262a` | `#e5e4df` | Default border |
| `--line-strong` | `#333338` | `#d4d3cd` | Popover / dialog border, input in shadcn |
| `--line-focus` | `#45454b` | `#bdbcb6` | Hover border, chat focus ring |
| `--control-border` | `#6b6b73` | `#85858c` | Input, checkbox, switch, segmented border (3:1) |
| `--code-bg` | `#121214` | `#fafaf8` | Code blocks |

### 3.2 Text

| Token | Dark | Light | Use |
|---|---|---|---|
| `--text` | `#ececee` | `#18181a` | Primary text |
| `--text-2` | `#b4b4bb` | `#4d4d55` | Secondary, descriptions, hints |
| `--text-3` | `#8e8e97` | `#66666e` | Tertiary, meta, kbd |
| `--placeholder` | `#9e9ea7` | `#595961` | Input placeholder |
| `--text-inverse` | `#0e0e10` | `#ffffff` | Text on ink |

### 3.3 Ink (accent)

| Token | Dark | Light | Use |
|---|---|---|---|
| `--brand` | `#ececee` | `#18181a` | Primary button, focus ring, checked state, active nav bar |
| `--brand-strong` | `#ffffff` | `#000000` | Primary hover |
| `--brand-ink` | `#0e0e10` | `#ffffff` | Text on `--brand` |
| `--brand-soft` | `rgb(236 236 238 / .08)` | `rgb(24 24 26 / .06)` | Brand badge fill |
| `--brand-tint` | `#262628` | `#f1f1f1` | Opaque brand fill |
| `--brand-glow` | `rgb(236 236 238 / .16)` | `rgb(24 24 26 / .12)` | Text selection |

### 3.4 Status

| Tone | Text / icon | `-tint` (opaque, under text) | `-soft` (translucent) |
|---|---|---|---|
| `ok` | `#5ccf9a` / `#157347` | `#1e2b27` / `#e9f5f0` | 12% / 10% |
| `warn` | `#eeb85c` / `#8a540d` | `#2f291f` / `#f8f1e7` | 12% / 10% |
| `bad` | `#f07f7f` / `#bd3030` | `#2f2223` / `#fbefef` | 12% / 8% |
| `info` | `#6fb6ee` / `#216a9f` | `#202831` / `#eaf2f9` | 12% / 10% |

Values are dark / light.

| Destructive | Dark | Light |
|---|---|---|
| `--bad-ink` (text on red) | `#0e0e10` | `#ffffff` |
| `--bad-strong` (hover) | `#f49a9a` | `#9f2626` |

### 3.5 Semantic aliases

| Group | Tokens → base |
|---|---|
| Compare | `--cmp-conflict` → bad · `--cmp-renamed`, `--cmp-moved` → info · `--cmp-different` → warn · `--cmp-missing` → text-2 · `--cmp-same` → text-3 · `--cmp-changed` → text |
| Impact | `--impact-removed`, `--impact-breaks` → bad · `--impact-changes` → warn · `--impact-new` → ok · `--impact-unchecked` → info · `--impact-unchanged` → control-border |
| Proposal | `--proposal` → text-2 · `--proposal-tint` → surface-3 |
| Rows | `--row-hover` → surface-hover · `--row-selected`, `--row-active` → surface-3 |

Each has a matching `-tint`.

### 3.6 shadcn variable mapping

| shadcn | App token |
|---|---|
| `--background` / `--foreground` | `--bg` / `--text` |
| `--card` | `--surface` |
| `--popover` | `--surface-2` |
| `--primary` / `--primary-foreground` | `--brand` / `--brand-ink` |
| `--secondary` | `--surface-3` |
| `--muted` (as `--muted-surface`) / `--muted-foreground` | `--surface-2` / `--text-2` |
| `--accent` | `--surface-hover` |
| `--destructive` | `--bad` |
| `--border` | `--line` |
| `--input` | `--line-strong` |
| `--ring` | `--brand` |

### 3.7 Object types (default palette)

| Type | Colour (dark) | Light variant | Lucide icon |
|---|---|---|---|
| Model | `#6ea8fe` | `#2563c9` | `Database` |
| Table | `#4cc2b0` | `#0e8273` | `Table2` |
| Column | `#a2afc2` | `#5d6b80` | `Columns3` |
| Measure | `#c6c95a` | `#6b6d00` | `Sigma` |
| Report | `#e68ac0` | `#b83f86` | `FileChartColumn` |
| Page | `#c49bf2` | `#7c4fc4` | `PanelsTopLeft` |
| Visual | `#f0995e` | `#b4561c` | `ChartColumn` |
| Group: model / report / other | `#6ea8fe` / `#e68ac0` / `#b5ac9c` | — | — |

Other icons: Relationship `Link2` · Calculation group/item `Layers` · Field parameter `ListFilter` · Shared expression `Braces` · DAX function `SquareFunction` · Visual calculation `Calculator` · Filters `Funnel` · Data source `Cylinder` · Partition `Rows3` · Role `ShieldUser` · Workspace `FolderOpen` · Concept / assertion `Lightbulb` · Alias `Tag` · Selector `ToggleLeft` · Conflict `OctagonAlert` · Behavior `Activity`.

- Other palettes (Settings): High contrast, Studio, Coast, Slate
- Light variant missing → `color-mix(in oklch, <colour> 55%, #18181a)`
- Type glyph: icon in type colour on `color-mix(<colour> 14%, transparent)`

### 3.8 Graph and code

| Token | Dark | Light |
|---|---|---|
| `--graph-edge` | `#6b6f7a` | `#8a8f99` |
| `--graph-structure` (ownership) | `#4a4d55` | `#c2c3c6` |
| `--grid-dot` | `#1f1f23` | `#e7e6e1` |
| `--edge-depends-on` | `#8cb9ff` | `#2563c9` |
| `--edge-references` | `#83d7bd` | `#0e8273` |
| `--edge-uses` | `#e8b879` | `#a45d00` |
| `--edge-controlled-by` | `#de9cff` | `#7c4fc4` |
| `--edge-observed-with` | `#8997a7` | `#5d6b80` |

| DAX token | Dark | Light |
|---|---|---|
| `--dax-fn` | `#7cb8ff` | `#1f63c6` |
| `--dax-keyword` | `#c792ea` | `#8a2fb8` |
| `--dax-string` | `#a5d6a7` | `#2b7a34` |
| `--dax-table` | `#f0c27b` | `#a45d00` |
| `--dax-ref` | `#ffcb8b` | `#b15a00` |
| `--dax-number` | `#f78c6c` | `#c2410c` |
| `--dax-comment` | `--text-3` | `--text-3` |

---

## 4. Typography

| Role | Stack |
|---|---|
| UI (`--font-ui`, Tailwind `font-sans`) | Segoe UI Variable Text → Segoe UI Variable → Inter Variable → Segoe UI → system-ui |
| Code (`--font-code`, Tailwind `font-mono`) | JetBrains Mono Variable → Cascadia Code → Consolas → ui-monospace |

Body: 13px, line-height 1.5, `font-feature-settings: "cv11", "ss01", "ss03"`, antialiased.

### Scale — 7 steps, no others allowed

| Token | px | Tailwind | Line height | Use |
|---|---|---|---|---|
| `--fs-micro` | 11 | `text-2xs` | 1.35 | kbd, counters, count pills |
| `--fs-meta` | 12 | `text-xs` | 1.4 | Metadata, hints, small buttons, tabs, badges, field labels |
| `--fs-body` | 13 | `text-sm` | 1.45 | Default text, controls, table cells, code |
| `--fs-emphasis` | 14 | `text-base` | 1.5 | Card / panel / pane titles, prose |
| `--fs-title` | 16 | `text-lg` | 1.4 | Dialog headings |
| `--fs-heading` | 20 | `text-xl` | 1.3 | Page `h1`, object titles |
| `--fs-page` | 24 | `text-2xl` | 1.2 | KPI numbers, large `h1` |

### Weights and details

| Rule | Value |
|---|---|
| Weights | 400 body · 500 controls, labels, badges · 600 titles, headings |
| Headings | `letter-spacing: -0.012em`, `text-wrap: balance` |
| Paragraphs | `text-wrap: pretty` |
| Numbers in counters | `font-variant-numeric: tabular-nums` |
| Allowed per element (`ui-policy.json`) | `h1` 20/24 · `h2` 14/16/20 · `h3` 13/14/16 · badges, kbd, counts 11/12 · graph nodes 11–14 |

---

## 5. Spacing

4px grid.

| Token | px |
|---|---|
| `--space-1` | 4 |
| `--space-2` | 8 |
| `--space-3` | 12 |
| `--space-4` | 16 |
| `--space-5` | 20 |
| `--space-6` | 24 |
| `--space-8` | 32 |

| Rule | Value |
|---|---|
| Gap between controls | ≥ 8px |
| Inset inside control containers | ≥ 8px |
| Gap between layout blocks | ≥ 8px |
| Content padding (normal views) | `16px 20px 32px` |
| Content padding (Graph, Merge) | `8px 10px 10px` |
| Card header / content | `20px 22px 0` / `18px 22px 22px` |
| Dialog padding / gap | 20px / 12px |
| Pane header / body | `12px 12px 12px 16px` / 16px |

---

## 6. Shape

| Token | px | Use |
|---|---|---|
| `--r-2xs` | 2 | Active-nav bar ends |
| `--r-3xs` | 3 | XS type glyph |
| `--r-xs` | 4 | Buttons, checkbox, type glyph, kbd, options |
| `--r-sm` | 6 | Tabs, segments, tooltip, graph node, large button |
| `--r-md` | 8 | Cards, dialogs, menus, popovers, panes, notices, tab list |
| `--r-full` | 9999 | Badges, pills, switch, radio |

Tailwind: `--radius` = 6px → `rounded-sm` 3 · `rounded-md` 5 · `rounded-lg` 6 · `rounded-xl` 10.

---

## 7. Elevation

| Token | Dark | Use |
|---|---|---|
| `--shadow-sm` | `0 1px 2px rgb(0 0 0 / .35)` | Active tab, switch thumb |
| `--shadow-md` | `0 1px 2px …/.3, 0 8px 24px -6px …/.45` | Menus, listboxes, tooltips |
| `--shadow-lg` | `0 2px 4px …/.3, 0 24px 64px -12px …/.6` | Dialogs, sheets, toasts |
| `--inset-hi` | `inset 0 1px 0 rgb(255 255 255 / .04)` | Top highlight |

Light theme uses the same shape at 5–20% alpha. Cards have no shadow; only floating layers do.

Z-order: chat overlay 40 · title bar 45 · scrim 50 · dialog / sheet 51 · menu / listbox 60 · tooltip 70 · skip link 100.

---

## 8. Motion

| Token | Value |
|---|---|
| `--ease-out` | `cubic-bezier(0.22, 1, 0.36, 1)` — default, no overshoot |
| `--ease-in` | `cubic-bezier(0.4, 0, 1, 1)` |
| `--ease-move` | `cubic-bezier(0.65, 0, 0.35, 1)` |
| `--dur-press` | 90ms |
| `--dur-fast` | 120ms — colour changes (max) |
| `--dur-flash` | 150ms |
| `--dur` / `--dur-enter` / `--dur-exit` | 180ms |
| `--dur-pane` | 240ms |
| `--dur-slow` | 280ms |
| `--dur-fit` | 320ms — graph refit |

| Animation | Effect |
|---|---|
| Button press | `scale(0.985)` over 90ms |
| Dialog scrim | `fade-in` |
| Sheet | `sheet-in`: from `translateX(16px)` + opacity 0 |
| Toast | `toast-in`: from `translateY(6px)` |
| Count change | `count-pop`: from `scale(0.92)` |
| Graph node | `node-enter`: from `scale(0.96)` |
| Row | `row-enter`: from `translateY(4px)` |
| Skeleton | appears after 300ms delay |
| Tabs | instant switch, no fade |

Reduced motion: every duration → 0.001ms, no spin, no press scale, no count pop.

---

## 9. Components (shadcn, `frontend/src/components/ui/`)

Every component styles through `ui-*` classes on top of Tailwind and only uses tokens.

### 9.1 Button — `button.jsx`

| Size | Height | Padding | Text | Icon |
|---|---|---|---|---|
| `xs` | 24 | 8 | 12 | 12 |
| `sm` | 28 | 10 | 12 | 14 |
| `default` | 32 | 12 | 13 | 16 |
| `lg` | 40 | 20 | 13 | 16 |
| `icon-xs` / `icon-sm` / `icon` / `icon-lg` | 24 / 28 / 32 / 40 square | — | — | — |

| Variant | Fill | Text | Border | Hover |
|---|---|---|---|---|
| `default` | `--brand` | `--brand-ink` | brand 80% + black | `--brand-strong` |
| `secondary` | `--surface-3` | `--text` | none | `--surface-hover` |
| `outline` | `--surface-2` | `--text` | `--line-strong` | `--surface-3`, `--line-focus` |
| `ghost` | transparent | `--text-2` | none | `--surface-hover`, `--text` |
| `destructive` | `--bad` | `--bad-ink` | `--bad` | `--bad-strong` |
| `destructive-outline` | `--surface` | `--bad` | `--bad` | `--bad-tint` |
| `status` (`tone` ok/warn/bad) | `-tint` | tone | currentColor | `--surface-hover` |
| `link` | none | `--brand` | none | underline, `--brand-strong` |

- Radius 4px (`lg` 6px), weight 500, gap 6px
- Disabled: opacity .45, tooltip still shown
- `loading` → `LoaderCircle` spinner + `loadingText`
- Icon-only buttons get a tooltip from `aria-label`
- Apply / write actions are always `destructive`

### 9.2 Form controls

| Component | File | Spec |
|---|---|---|
| Input | `input.jsx` | h 32, px 10, radius 5, `--surface-2`, border `--control-border`; hover border `--text-2`; focus border + 2px `--brand` outline, fill `--surface` |
| Select | `select.jsx` | Radix select; trigger like input; listbox `--surface-2`, radius 8, max-h 320, `--shadow-md`; option min-h 28, check icon 16 |
| Native select | `native-select.jsx` | Same look as input |
| Combobox | `combobox.jsx` | Grouped options, optional "create" item |
| Checkbox | `checkbox.jsx` | Box 16, radius 4; default wrapper `target` = 24×24 hit area; checked → `--brand` fill, `--brand-ink` mark; indeterminate dash |
| Switch | `switch.jsx` | Track 40×24, thumb 18, `--control-border`; checked track `--brand`, thumb `--brand-ink`; label + description beside |
| Radio | `choice-radio.jsx` | Ring 16 in 24 target, dot 8 `--brand`; item padding `6px 8px`, selected `--surface-3`; reason text indented 32 |
| Segmented control | `segmented-control.jsx` | Container border `--control-border`, radius 8, padding 2; segment min-h 26, px 10, 12px/500; on = `--surface-3` + inset border |
| Field / Label | `field.jsx`, `label.jsx` | Label 12/500 `--text`; hint 12 `--text-2`; error hint `--bad` with icon |
| Filter | `filter.jsx` | `FilterButton` (popover multi-select) + removable `FilterChip` |

### 9.3 Display

| Component | File | Spec |
|---|---|---|
| Badge | `badge.jsx` | h 20, px 8, pill, 12/500. Variants: `default` (brand soft), `secondary` (`--surface-3`), `outline`, `destructive` (bad soft), `ghost`, `link` |
| Status badge | `status-badge.jsx` | h 22, px 8, pill, 12/500, icon 14; tones `ok` `warn` `bad` `info` `plain` `proposal` on `-tint` |
| Card | `card.jsx` | `--surface`, border `--line`, radius 8, no shadow; title 14/600 |
| Tabs | `tabs.jsx` | List: `--surface-2`, border `--line`, radius 8, padding 3. Trigger: h 28, px 12, 12/500 `--text-2`; active `--surface-3` (light: `--surface`) + `--shadow-sm` + inset `--line-strong`. Optional count pill h 18, tone-coloured |
| Data table | `data-table.jsx` | Caption, columns, row checkboxes, expandable detail; row h 36 |
| Skeleton | `skeleton.jsx` | Bars in `--surface-3`, `animate-pulse`, optional status label |
| Progress / Steps | `progress.jsx` | Steps: mark 24 circle; current = `--brand` fill; done = `--ok-tint`; error = `--bad`. Line list with spinner per running line |
| Notice / Banner | `notice.jsx` | Grid icon · body · actions; padding `10px 12px`; `--surface-2`, border `--line-strong`, radius 8 (banner: 0); icon 16 in tone colour, text stays `--text` |
| Result panel / Empty state | `result-panel.jsx` | Empty: centred, icon tile 44, title 14/600, text 13 `--text-2` max 380px |
| Breadcrumb | `breadcrumb.jsx` | shadcn breadcrumb |
| Collapsible | `collapsible.jsx` | `Disclosure` |

### 9.4 Overlays

| Component | File | Spec |
|---|---|---|
| Dialog / Alert dialog | `dialog.jsx` | Width `min(520px, 100vw − 32px)`, max-h `100vh − 64px`, padding 20, gap 12, `--surface`, border `--line-strong`, radius 8, `--shadow-lg`. Title 16/600, description 13 `--text-2`, footer right-aligned gap 8, close 28×28 top-right. Scrim `--minimap-mask` |
| Sheet | `sheet.jsx` | Right edge, width `min(400px, 92vw)`, `--shadow-lg`, slide in from right |
| Side pane | `side-pane.jsx` | Width 360, `--surface`, border `--line`, radius 8; header with prev / next / close; title 14/600 |
| Menu | `menu.jsx` | min-w 200, padding 4, `--surface-2`, border `--line-strong`, radius 8, `--shadow-md`. Item min-h 28, icon 16, shortcut right in mono 12 `--text-3`; destructive item `--bad` |
| Context menu | `context-menu.jsx` | Same as menu |
| Tooltip | `tooltip.jsx` | max-w 280, padding `6px 10px`, `--surface-3`, border `--line-strong`, radius 6, 12px, offset 6 |
| Hover card | `hover-card.jsx` | Side top, align start, offset 6 |
| Toast | `toast.jsx` (Sonner) | Fill `--surface-3`, text `--text`, border `--line-strong`, `--shadow-lg`, 13px; tone only in icon; close button 24×24 always shown |

---

## 10. Layout

### 10.1 Shell

```text
┌──────────────────────── title bar 32 ────────────────────────┐
│ side bar 212 │          content (only scroller)    │ chat    │
│ (rail 44)    │                                     │ ≤400    │
├──────────────────────── status bar 26 ───────────────────────┤
```

| Token | Value |
|---|---|
| `--chrome-title` | 32px — brand, menu bar, command centre (max 440, h 24), project switcher |
| `--chrome-toolbar` | 36px |
| `--chrome-status` | 26px |
| `--sidebar-w` | 212px (188px ≤ 1100px) |
| `--sidebar-rail` | 44px (collapsed, `Ctrl+B`) |
| `--chat-w` | `min(400px, 34vw)`, third grid column |
| `--pane-w` | 360px |
| `--sheet-w` | `min(400px, 92vw)` |
| `--row-h` | 36px |
| `--control-h` | 32px |
| `--target-min` | 24px |

- Nav button: h 28 (rail 32), padding 0 8, gap 9, radius 8; active = 3px `--brand` bar on the left
- Settings sits below a 1px divider at the end of the nav
- Page `h1`: 20/600, line-height 1.3

### 10.2 Breakpoints

| Max width | Change |
|---|---|
| 1200px | Review queue hides extra columns |
| 1100px | Side bar 188px; status-bar scan hidden; chat becomes a fixed overlay on the right; two-column Overview kept (desktop window minimum) |
| 900px | Overview and object workspace → one column |
| 760px | Side bar → icon rail; menus → command centre |
| 360px | Graph toolbar tabs tighten |

Tested viewports: 390×844 and 1440×900, dark and light.

### 10.3 Graph canvas

| Item | Value |
|---|---|
| Node | 168×32, `--surface`, border `--line-strong`, radius 6, padding `0 10 0 3`, gap 8 |
| Node hover | border `--line-focus` |
| Node selected | ring `0 0 0 2px --bg, 0 0 0 4px --brand` |
| Suggested node | dashed `--text-3` border |
| Warning node | border 60% `--warn` |
| Edge | `--graph-edge`, structure lines `--graph-structure` |

---

## 11. Icons

- Library: Lucide only
- Sizes: 12 / 14 / 16 inside buttons and nav (checked); 13–14 in type glyphs; 20 in empty states
- Stroke 1.9 in type glyphs
- Type glyph sizes: 24 (default) · 20 (`-sm`) · 16 (`-xs`)

---

## 12. Accessibility

| Rule | Value |
|---|---|
| Focus ring | 2px solid `--brand`, offset 2 (inputs: offset −1) |
| Chat focus ring | 2px `--line-focus` |
| Hit area | ≥ 24×24 for every button, tab, combobox, input |
| Text contrast | 4.5:1 |
| Control borders | 3:1 (`--control-border`) |
| Skip link | First focusable element |
| Focus never hidden | Content pane is the only scroller, `scroll-padding-top: 12px` |
| Reduced motion | Fully static |
| Scrollbars | Thin, thumb `--line-strong`, hover `--line-focus` |

---

## 13. Copy

- Short. At most two long text runs per view (`e2e/copyBudget.spec.js`)
- Banned: "unlock your potential", "seamlessly", "game-changing"
- Status words, not colour alone (icons + text, `sr-only` labels on steps)

---

## 14. Theme switching

- Dark: default `:root`
- Light: `:root[data-theme="light"]`, set on `<html>` by the app (`Ctrl+Shift+L`)
- Tailwind `dark:` variant: `.dark *`
- Every new colour needs a dark and a light value in `theme.css`

---

## 15. Checks

| Check | Command |
|---|---|
| Visual snapshots (7 views) | `cd frontend && npx playwright test e2e/visual.spec.js` |
| UI policy (sizes, gaps, contrast) | Browser suite, rules from `frontend/ui-policy.json` |
| Copy budget | `e2e/copyBudget.spec.js` |
| Full browser suite | `cd frontend && npm run build && npx playwright test` |
