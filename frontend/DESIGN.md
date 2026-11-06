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
- **Body** (400/600, 14px, 1.5): default text; row and panel titles at 600.
- **UI** (500, 13px): controls, tabs, table cells, secondary copy.
- **Meta** (500, 12px): column headers, metadata, captions, field labels.
- **Micro** (500–600, 11px): badges, keycaps, counts. Nothing smaller.

Tokens: `--type-micro … --type-display` in `src/theme.css`. Every
`font-size` in app CSS uses one of them.

### Named Rules
**The No Kicker Rule.** No small uppercase label above a heading. Field labels
above values are sentence case `--type-meta`.

## Layout

Fixed sidebar (≈236px, 212px under 1180px) plus a 52px top bar with a
breadcrumb only. Content pages cap at 960px (forms), 1120px (Overview) or
1240px (tables); Graph and Development Center are full-bleed. Spacing steps are
4/8/12/16/20/24px. Groups are separated by 20–24px; rows inside a group by a
1px rule. Under 760px the sidebar becomes a top strip and multi-column rows
stack.

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

Three radii: 4px (controls, buttons, chips' inner parts, checkboxes), 6px
(inputs, inline evidence blocks), 8px (panels, cards, popovers). Pills
(999px) only for count badges and status chips. No coloured one-sided borders.

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
- **Do** use a `font-size: var(--type-*)` token for every text size.
- **Do** group with rules and alignment before reaching for another container.
- **Do** keep provenance and status labelled in words, with colour as reinforcement.
- **Do** keep numbers tabular (`font-variant-numeric: tabular-nums`).

### Don't:
- **Don't** build a page from same-size icon + heading + text cards.
- **Don't** show counts as hero-metric tiles; say them inline ("20 objects · 25 relationships").
- **Don't** put a coloured `border-left`/`border-right` over 1px on cards, rows or callouts.
- **Don't** add shadows to resting surfaces or bounce/spring easing to anything.
- **Don't** add taglines to the window chrome; the page heading explains the page.
