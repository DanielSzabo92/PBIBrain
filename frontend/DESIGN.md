---
name: Brain Inspector
description: A quiet, exact instrument for reading a Power BI project's semantic graph.
colors:
  canvas-dark: "#0b0c0f"
  sidebar-dark: "#0e0f13"
  surface-dark: "#131519"
  surface-2-dark: "#181a1f"
  surface-3-dark: "#1f2127"
  line-dark: "#1f2228"
  line-strong-dark: "#2b2f37"
  text-dark: "#ededf0"
  text-2-dark: "#a3a7b1"
  text-3-dark: "#9298a5"
  accent-dark: "#8e97ff"
  canvas-light: "#f6f6f4"
  sidebar-light: "#efefec"
  surface-light: "#ffffff"
  line-light: "#e6e5e1"
  line-strong-light: "#d6d5d0"
  text-light: "#16171b"
  text-2-light: "#5c5f68"
  accent-light: "#4f58e0"
  ok-dark: "#5ccf9a"
  warn-dark: "#eeb85c"
  bad-dark: "#f07f7f"
  info-dark: "#6fb6ee"
  ok-light: "#157347"
  warn-light: "#8a540d"
  bad-light: "#bd3030"
  info-light: "#216a9f"
  dax-fn-dark: "#7cb8ff"
  dax-keyword-dark: "#c792ea"
  dax-string-dark: "#a5d6a7"
  dax-table-dark: "#f0c27b"
  dax-ref-dark: "#ffcb8b"
  dax-number-dark: "#f78c6c"
  dax-fn-light: "#1f63c6"
  dax-keyword-light: "#8a2fb8"
  dax-string-light: "#2b7a34"
  dax-table-light: "#a45d00"
  dax-ref-light: "#b15a00"
  dax-number-light: "#c2410c"
typography:
  display:
    fontFamily: "Segoe UI Variable Text, Segoe UI Variable, Inter Variable, Segoe UI, system-ui, sans-serif"
    fontSize: "24px"
    fontWeight: 650
    lineHeight: 1.2
    letterSpacing: "-0.02em"
  heading:
    fontFamily: "Segoe UI Variable Text, Segoe UI Variable, Inter Variable, Segoe UI, system-ui, sans-serif"
    fontSize: "20px"
    fontWeight: 650
    lineHeight: 1.25
    letterSpacing: "-0.015em"
  title:
    fontFamily: "Segoe UI Variable Text, Segoe UI Variable, Inter Variable, Segoe UI, system-ui, sans-serif"
    fontSize: "16px"
    fontWeight: 600
    lineHeight: 1.35
  body:
    fontFamily: "Segoe UI Variable Text, Segoe UI Variable, Inter Variable, Segoe UI, system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.5
  ui:
    fontFamily: "Segoe UI Variable Text, Segoe UI Variable, Inter Variable, Segoe UI, system-ui, sans-serif"
    fontSize: "13px"
    fontWeight: 500
    lineHeight: 1.45
  meta:
    fontFamily: "Segoe UI Variable Text, Segoe UI Variable, Inter Variable, Segoe UI, system-ui, sans-serif"
    fontSize: "12px"
    fontWeight: 500
    lineHeight: 1.4
  micro:
    fontFamily: "Segoe UI Variable Text, Segoe UI Variable, Inter Variable, Segoe UI, system-ui, sans-serif"
    fontSize: "11px"
    fontWeight: 500
    lineHeight: 1.3
  code:
    fontFamily: "JetBrains Mono Variable, Cascadia Code, Consolas, ui-monospace, monospace"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.6
rounded:
  "2xs": "2px"
  "3xs": "3px"
  xs: "4px"
  sm: "6px"
  md: "8px"
  pill: "999px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "20px"
  xxl: "24px"
components:
  button-primary:
    backgroundColor: "{colors.accent-dark}"
    textColor: "{colors.canvas-dark}"
    rounded: "{rounded.xs}"
    height: "32px"
    padding: "0 12px"
  button-outline:
    backgroundColor: "{colors.surface-2-dark}"
    textColor: "{colors.text-dark}"
    rounded: "{rounded.xs}"
    height: "32px"
  input:
    backgroundColor: "{colors.surface-2-dark}"
    textColor: "{colors.text-dark}"
    rounded: "{rounded.sm}"
    height: "36px"
  panel:
    backgroundColor: "{colors.surface-dark}"
    rounded: "{rounded.md}"
    padding: "14px 16px"
---

> **Superseded (2026-11):** the binding visual contract is now
> [`docs/design/visual-contract.md`](../docs/design/visual-contract.md), the result of a three-way design
> debate (Anthropic `frontend-design`, Vercel `web-design-guidelines`, `design-taste-frontend`). Ink is the
> only accent; hue means object type (glyph + colour, `src/objectIcons.js`) or status. Where this file and
> the contract disagree, the contract wins.


# Design System: Brain Inspector

## Overview

**Creative North Star: "The Lineage Ledger"**

Brain Inspector is a reference instrument that sits beside Power BI Desktop.
Its job is to make a model's objects, formulas and dependencies legible and
trustworthy, so the interface is a ledger: rows, columns, exact names, exact
numbers, and one clear signal for what needs a decision. It borrows the
calm of a code editor and a well-made Windows tool, not the theatre of a SaaS
marketing dashboard. The user's model is the content; the chrome recedes.

Density is high but ordered. Information is grouped by alignment and thin
rules, not by boxes inside boxes. Colour belongs to data (artifact type,
provenance, status). The one accent marks the primary action on a screen and
the current selection, and nothing else.

Rejected (this audit): hero-metric stat tiles, icon-in-a-square tiles above
headings, uppercase tracked kickers above titles, coloured side stripes on
cards, decorative shadows on resting surfaces, spring/bounce easing, and
taglines in the window chrome.

**Key Characteristics:**
- Ledger, not dashboard: lists and tables with dividers before cards.
- One sans family (Segoe UI Variable on Windows, Inter elsewhere), one mono for code and paths.
- Seven type steps, three radii, flat surfaces.
- Colour encodes data; the accent encodes "act here".

## Colors

Near-neutral graphite (dark) and warm paper (light), with a single periwinkle
accent and four status hues that are always paired with a text label.

### Primary
- **Ledger Periwinkle** (#8e97ff dark / #4f58e0 light): the primary button of
  the current screen, the selected nav item's count, focus rings, links.
  Never a background wash, never a card border.

### Neutral
- **Graphite Canvas** (#0b0c0f) / **Paper Canvas** (#f6f6f4): page background.
- **Panel** (#131519 / #ffffff): the one container surface.
- **Rule** (#1f2228 / #e6e5e1): dividers between rows; the main grouping device.
- **Ink** (#ededf0 / #16171b), **Ink 2** (#a3a7b1 / #5c5f68): primary and secondary text.

### DAX Syntax Palette
Syntax tokens re-map across dark and light themes:
- **Function** (`--dax-fn`): `#7cb8ff` dark / `#1f63c6` light.
- **Keyword** (`--dax-keyword`): `#c792ea` dark / `#8a2fb8` light.
- **String** (`--dax-string`): `#a5d6a7` dark / `#2b7a34` light.
- **Table** (`--dax-table`): `#f0c27b` dark / `#a45d00` light.
- **Column / Ref** (`--dax-ref`): `#ffcb8b` dark / `#b15a00` light.
- **Number** (`--dax-number`): `#f78c6c` dark / `#c2410c` light.
- **Comment** (`--dax-comment`): `var(--text-3)`.

### Named Rules
**The Data Owns Colour Rule.** Artifact colours (user-editable in Settings),
provenance line styles and status hues are the only saturated colour on a
screen besides one accent action. Chrome stays neutral so a user's custom
palette never fights the UI.

**The One Accent Rule.** At most one filled accent control per view region.

## Typography

**Body Font:** Segoe UI Variable Text (with Inter Variable, Segoe UI, system-ui)
**Mono Font:** JetBrains Mono Variable (with Cascadia Code, Consolas)

**Character:** A native Windows voice for a tool used next to Power BI
Desktop; Inter is the bundled fallback so non-Windows renders stay close.
Mono is for DAX, M, file paths and IDs only, never as a "technical" costume.

### Hierarchy
- **Display** (650, 24px, 1.2): the project name on Overview only.
- **Heading** (650, 20px, 1.25): page titles (`.page-heading h1`).
- **Title** (600, 16px): settings panel and empty-state titles.
- **Emphasis** (400/600, 14px, 1.5): prose, inputs; row and panel titles at 600.
- **Body** (400/500, 13px): the default UI size: controls, tabs, table cells, secondary copy.
- **Meta** (500, 12px): column headers, metadata, captions, field labels.
- **Micro** (500–600, 11px): badges, keycaps, counts. Nothing smaller.

Tokens: `--fs-micro`, `--fs-meta`, `--fs-body`, `--fs-emphasis`, `--fs-title`,
`--fs-heading`, `--fs-page` in `src/theme.css` (Tailwind `text-2xs…2xl` map onto
them). Every `font-size` in app CSS uses one of them; `ui-policy.json` and
`test/type-scale.test.js` enforce the same list.

### Named Rules
**The No Kicker Rule.** No small uppercase label above a heading. Field labels
above values are sentence case `--fs-meta`.

## Layout

A desktop workbench shell (see `docs/ui-audit/desktop.md`): a 32px title row
with File/View/Go/Help menus and the Ctrl+K command centre; a 212px side bar
(Ctrl+B collapses it to a 44px icon rail); a 36px per-view toolbar; the content
pane; and a 26px status bar (connection, scan progress, counts, review queue,
messages). The viewport is fixed and only `#main-content` scrolls. Spacing uses
the `--space-*` 4px grid (4/8/12/16/20/24/32); controls inside an action group
are never closer than 8px. Groups are separated by 20–24px; rows inside a group
by a 1px rule. Under 760px the side bar is always the icon rail and the menus
give way to the command centre.

Keyboard: one table in `src/shortcuts.js` drives keys, menus, tooltips and the
F1 sheet. Register any new shortcut there.

## Elevation & Depth

Flat by default. Resting panels, cards and outline buttons carry no shadow;
depth comes from the canvas → panel tonal step and 1px rules. Shadows are
reserved for things that float over content.

### Shadow Vocabulary
- **Overlay** (`--shadow-md`): popovers, menus, the graph details sheet.
- **Modal / toast** (`--shadow-lg`): dialogs and toasts.

### Named Rules
**The Flat-At-Rest Rule.** If it does not float, it has no shadow.

## Shapes

Primary radii: 4px (controls, buttons, chips' inner parts, checkboxes), 6px
(inputs, inline evidence blocks), 8px (panels, cards, popovers). Micro-radii:
2px (`--r-2xs`) and 3px (`--r-3xs`) for glyph badges, progress track caps, and micro-swatches.
Pills (999px) only for count badges and status chips. No coloured one-sided borders.

## Components

### Buttons
- **Shape:** near-square (4px).
- **Primary:** accent fill, ink text; one per region.
- **Outline:** surface-2 fill, strong rule border, no shadow.
- **Ghost:** text-2, surface-hover on hover. Used for secondary row actions.

### Status rows (signature component)
Overview's `.status-panel` is the pattern for "what needs attention": one
bordered panel, rows split by rules, a 28px leading column holding a 16px
icon or a tabular count coloured by tone, a 14px/600 title, a 13px
explanation, and right-aligned actions. Tone is never a stripe or a tinted
card.

### Inputs / Fields
- **Style:** surface-2 fill, control-border stroke, 6px radius, 36px tall for
  primary search, 32px elsewhere.
- **Focus:** 2px accent outline offset 2px, background lifts to panel.

### Navigation
Sidebar items are 34px rows, text-2 at rest, surface-3 fill when current
(no shadow). The review count is the only badge.

## Do's and Don'ts

### Do:
- **Do** use a `font-size: var(--fs-*)` token for every text size.
- **Do** group with rules and alignment before reaching for another container.
- **Do** keep provenance and status labelled in words, with colour as reinforcement.
- **Do** keep numbers tabular (`font-variant-numeric: tabular-nums`).

### Don't:
- **Don't** build a page from same-size icon + heading + text cards.
- **Don't** show counts as hero-metric tiles; say them inline ("20 objects · 25 relationships").
- **Don't** put a coloured `border-left`/`border-right` over 1px on cards, rows or callouts.
- **Don't** add shadows to resting surfaces or bounce/spring easing to anything.
- **Don't** add taglines to the window chrome; the page heading explains the page.
