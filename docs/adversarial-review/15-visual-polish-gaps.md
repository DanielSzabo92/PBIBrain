# 15 · It looks tidy, not expensive: visual polish gaps

**Severity:** P2 · **Criteria:** looks proficient, high-end and expensive

The token system and contrast work are solid. What keeps the product from looking premium is hierarchy, repetition and a handful of visible defects.

## Evidence and fixes

| # | Observation | Fix |
|---|---|---|
| 1 | On load a white 2 px box is drawn around the whole "Overview" h1 row (focus moved to the heading programmatically shows a focus ring). See `evidence/overview-large.png`, `evidence/first-run.png`. | Programmatic focus targets get `outline: none` (`:focus:not(:focus-visible)` is not enough here; use `tabindex="-1"` + `[data-focus-target]:focus { outline: none }`). |
| 2 | Three ways to scan on one screen: "Scan sources" (header), "Scan now" (Sources row), "Scan now" (status bar). | One primary scan control in the header. The status bar shows state only. |
| 3 | Everything has the same weight: every card is the same grey outline, every heading 14/600, no primary action. Nothing says "start here". | One ink-filled primary button per view at most. Overview leads with a single health line (✓ Indexed 2 min ago · ⚠ 312 to review · ✕ 2 sources failed), then content. |
| 4 | Overview widgets are four boxed cards holding one grey sentence each; the grid leaves a hole (3 cards + 1). | Replace with one "Needs attention" ledger (contract §9) and a two-column body: top measures · model/report table. No empty cards — a widget with nothing to say is not rendered. |
| 5 | Type chips wrap to two rows and mix real objects with internal ones (Alias, Behavior, Role, Business concept). | Seven core types on one line, glyph + number; the rest under a "+4" overflow. |
| 6 | Graph: zoom control and minimap float over nodes; minimap is an empty box most of the time. | Zoom control joins the toolbar (`− 75 % +` next to Fit). Minimap only when useful (07). |
| 7 | Node names are cut in the middle while the canvas is 75 % empty ("MTD Ca…Amount"). | Width from content up to 280 px before truncating. |
| 8 | Sidebar spends 212 px on seven words. Settings' active bar is offset from the others. | Default to a 48 px icon rail with tooltips (labels on hover/pin); fix the indicator to use one positioned element for all items. |
| 9 | Title bar: brand mark, four menus, search, Chat, project name, all the same grey. Project name is plain text, not obviously a switcher. | Project name becomes a button with a `ChevronsUpDown` glyph and the source-health dot. |
| 10 | Skeletons are flat grey slabs unrelated to the content they replace (Review, Merge). | Skeletons mirror the row grid (chip, two text bars, meter). After 8 s show what is being waited for and a Cancel. |
| 11 | Numbers are not consistently formatted: "13731 objects", "11528", "(11528)" in the graph and review vs "13,731" and "11,528" in the status bar. | One `formatCount()` everywhere; `tabular-nums`. |
| 12 | "Factual" badge is a pill with a dot; contract removed dot pills. | Provenance chip per contract §4. |
| 13 | Motion: views swap instantly with no continuity; the pane and popovers do animate. | 120 ms opacity cross-fade on view change; keep reduced-motion static. |
| 14 | Depth: every surface is within 3 % luminance of the next; popovers barely separate from the canvas. | Raise popover/menu contrast one step (`--surface-2` → a dedicated `--surface-overlay`), keep 1 px `--line-strong` + `--shadow-md`. |

## Acceptance

- A screenshot review of all seven views at 1440×900, both themes, finds no clipped label, no overlapping element and no duplicated control.
- Design lint (`lintapple`) passes with the new rules for counts and single primary action.
