# Brain Inspector — desktop UI audit

Lens: desktop pro-tool conventions (Windows Fluent, macOS HIG, and the tools PBIBrain users live in:
Power BI Desktop, Tabular Editor, DAX Studio, VS Code). Branch `claude/ui-audit-desktop`.

## How this was audited

- Real backend, real scan: a richer fixture than the e2e one (1 model, 5 tables, 13 measures,
  2 reports, 3 pages, 8 visuals → 97 objects, 158 relationships, 49 review items) served by
  `backend.api.app.create_app`, Vite dev on :5173 proxying `/api`.
- Every main view walked at 1440×900 and 1920×1080, dark and light, mouse and keyboard only.
  Keyboard probes were scripted with Playwright (Tab order, F-keys, Ctrl+digit, Alt, arrows) so
  the results are reproducible, not impressions.
- Screenshots: `docs/ui-audit/screenshots/desktop/before-*.png` and `after-*.png`.

## Verdict

**Before: a generic SaaS web dashboard that happens to run in a window.** The tell-tales:

| Desktop pro tool expects | Brain Inspector had |
| --- | --- |
| Menu bar or command bar holding *every* command, each with its key | No menus. Commands scattered as page-level buttons; "Scan" only on Overview and Settings |
| Status bar with persistent state (connection, counts, progress, last refresh) | Connection dot hidden in sidebar footer; counts only on Overview; scan progress a pill in the top bar; results as floating toasts that vanish in 3 s |
| F5 = refresh data, Ctrl+, = settings, Ctrl+B = side bar, Alt/F10 = menus, Alt+← = back | Only Ctrl+K and "/". **F5 reloaded the whole webview** and threw away the session |
| Dense, full-width work area, 13 px text, 24–30 px rows | 236 px sidebar, 52 px top bar, 28/32 px page padding, centred 960–1240 px columns, 26–30 px page titles, 56 px search rows, 12 px card radii |
| Lists you can drive with arrows, Home/End, Enter | Lists are a column of buttons — Tab through 39 results one by one |
| Docked, resizable panes | Fixed grid columns; details open as an overlay sheet |
| Context menus on objects | None anywhere in the app (`grep onContextMenu` → 0) |

The visual polish is real (tokens, contrast-tested themes, careful empty states), which is why it
"looks nice but feels like slop": it is a marketing-site idiom (hero titles, stat tiles, call-to-action
cards, toasts) applied to a tool people keep open all day next to Power BI Desktop.

## Findings

Severity: **P0** breaks trust or loses work · **P1** core desktop expectation missing · **P2** friction ·
**P3** polish. File:line refers to `main` before this branch unless marked *(after)*.

### Information architecture

- **P1 — No home for commands.** Scan, project change, export, theme, reload live on different pages or
  only as icons: `frontend/src/App.jsx:521-522` (top bar), `:506` (theme in sidebar footer),
  `:537` (Scan only via Overview), `:543` (Settings). A user on the Graph view cannot rescan without
  navigating away. → *Fixed:* File / View / Go / Help menu bar (`src/components/AppShell.jsx`), view
  toolbar with Rescan + Reload on every view.
- **P1 — Overview is a landing page, not a workspace.** Hero title, giant search, stat tiles and three
  "explore" cards (`App.jsx:664-733`) duplicate the nav and the counts. In Power BI Desktop / Tabular
  Editor the first screen is the model explorer. → *Partly fixed* (density); **recommend** replacing it
  with a model tree (Model ▸ Tables ▸ Columns/Measures, Reports ▸ Pages ▸ Visuals) docked on the left of
  Inspector, making "Overview" a Problems/health panel.
- **P2 — Settings mixes app preferences and project configuration.** The "/" key switch sits above the
  project tabs (`App.jsx:543`, `KeyboardSettings` at `:557`). Desktop apps split *Options* (app) from
  *Project properties* (document). → Recommend: File ▸ Project properties… vs Tools ▸ Options….
- **P2 — "Inspector" and "Search" are the same list twice** (`App.jsx:538` vs `:540` `SearchView browse`).
  A single Explorer pane + document area removes one nav entry.
- **P3 — Duplicate refresh controls.** The graph has its own *Refresh* (`components/GraphView.jsx:217`)
  next to the global reload; two buttons, two meanings.

### Layout and panes

- **P1 — Body-scrolling web layout, chrome eats 288 px of width.** `app.css:207` 236 px sidebar,
  `:250` 52 px top bar, `:266` 28/32/48 px padding, `:273-276` centred max-width columns that leave
  ~400 px dead at 1920. → *Fixed:* fixed-viewport shell — the window never scrolls, only the content pane does (as in every
  native tool), so no bar ever covers content; 32 px title row + 36 px toolbar + 26 px status bar, 212 px side bar
  collapsible to a 44 px rail, pages start-aligned, data pages full width (`app.css` *(after)* Shell section).
- **P1 — No splitters / docked panes.** Inspector lineage is a fixed grid column; graph details are an
  overlay sheet (`app.css:855` `.ui-sheet`) that covers the canvas. → **Recommend** a resizable
  master/detail split (react-resizable-panels or a 40-line pointer splitter), remembering sizes per view.
- **P2 — Review queue is a card list, ~120 px per item** (`app.css:534-537`, `App.jsx:1001`). With 49+
  items that is 6 000 px of scrolling. A grid (Object · Suggestion · Confidence · Status) with a detail
  pane and Approve = `A`, Reject = `R`, ↑/↓ moves, Space toggles multi-select is the DAX Studio /
  Tabular Editor "Best Practice Analyzer" idiom.
- **P3 — Settings tabs are pill segmented controls** (`app.css` `.ui-tabs-list`), the web idiom; desktop
  property pages use underline tabs or a left category list.

### Keyboard model

- **P0 — F5 reloaded the webview.** In the pywebview host this discards the open project state, current
  view, search session and unsaved drafts. Nothing intercepted it (`App.jsx:451-463` only handled Ctrl+K and
  "/"). → *Fixed:* F5 = reload data in place, Ctrl+F5 = scan sources (`src/shortcuts.js`).
- **P1 — No view switching keys, no menu access key, no Back.** → *Fixed:* Ctrl+1…6 views, Ctrl+, Settings,
  Alt / F10 focuses the menu bar, Alt+F/V/G/H opens a menu, Alt+← goes back from Inspector and restores
  focus on the row you came from, Ctrl+B side bar, Ctrl+Shift+L theme, F1 shortcut sheet.
- **P1 — Lists are not keyboard lists.** Search results, browse list and lineage are flat buttons; ↓ in the
  search box did nothing. → *Fixed:* ↓ from the search field enters results; ↑/↓/Home/End move;
  ↑ from the first row returns to the field; Enter opens (`App.jsx` *(after)* `moveInList`, `listKeys`).
  Still to do: the same for the review queue and graph node list; type-ahead.
- **P2 — Tab order puts 9 chrome stops before content** (skip link, 7 nav buttons, theme, reload) and
  shortcuts were invisible (the only hint was a hover-only "Ctrl K"). → *Fixed:* shortcuts shown in
  menus, side-bar tooltips/hover hints, status bar and an F1 sheet, all from one table so they cannot
  drift. Recommend F6 to cycle panes (side bar → toolbar → content → status bar) as in Windows apps.
- **P3 — Ctrl+1…6 are browser-reserved in Chrome/Edge tabs.** They work in the desktop host (pywebview)
  and in Playwright; in a browser tab Chrome keeps them. Ctrl+K and the menus remain the browser path.

### Density and typography

- **P1 — Marketing scale type.** Page titles 26 px (`app.css:280`), Overview hero 30 px, stat numbers 30 px,
  search input 44 px tall at 14.5 px, result rows 56 px with a 148 px pill column. → *Fixed:* titles 18–20 px,
  stats 22 px, 32 px search field, 30 px one-line result rows (name then scope), 8 px card radius,
  28 px nav rows at 13 px.
- **P2 — Pills everywhere** (type badges, counts, tabs) read as web chips. In dense lists a coloured
  dot + plain text is quieter; kept for now because the e2e colour tests key off them.

### Feedback and status

- **P1 — Transient results only.** "Scan complete", "Suggestion approved" and *failures* ("Review failed.
  Try again.") were a floating toast removed after 3 s (`App.jsx:177-182`, `:527`; `app.css:283-288`).
  → *Fixed:* messages appear in the status bar (same `.toast` role="status" element), failures in the
  error colour. Recommend failures persist until the next action and go to an Output/Problems log.
- **P1 — State was invisible outside Overview.** → *Fixed:* status bar shows connection, scan progress
  (indeterminate bar), project, model/report/object/relationship counts, "N to review" (click → queue),
  last scan time, shortcuts and theme.
- **P1 — Development Center can hang on a skeleton.** With a project open but no merge session the API
  returns 409 on `/api/devcenter/session` and the view shows "Loading merge sessions" indefinitely
  (observed >12 s, `devcenter/screens/SessionList.jsx:75-76`). Needs an empty state / timeout. *Not fixed*
  (outside the shell; flagged for the Dev Center owner).
- **P2 — Scan has no progress, cancel or log.** A long scan shows only a spinner. Desktop convention:
  progress in status bar (now done) + Cancel + an Output pane with per-source lines.

### Platform conventions

- **P1 — No menu bar / command surface** (fixed, above). Keyboard-accessible Radix Menubar with
  mnemonics underlined while the bar has focus, accelerators right-aligned, checkmarks for toggles.
- **P2 — No context menus.** Right-click on a search row, lineage row, graph node or review item should
  offer *Open in Inspector · Show in graph · Copy name · Copy DAX reference ('Table'[Measure]) · Copy ID*.
  `components/ui/menu.jsx` already exists; recommend a `ContextMenu` wrapper on the same styles.
- **P2 — Theme ignores the OS.** Default is dark unless stored (`App.jsx:134-136`). Desktop apps follow
  the system theme with an override. Not changed here because Playwright's default light colour scheme
  would flip every axe/contrast test's baseline — do it with a test update.
- **P2 — Onboarding is a centred marketing card** (`App.jsx:575-616`). A desktop Start page lists recent
  projects (pywebview can persist them) with *Open folder…* and *New project…*, like Power BI Desktop's
  start screen.
- **P3 — Cursor and selection.** Chrome text is selectable and buttons use the hand cursor; native
  chrome uses the arrow and `user-select: none` (applied to the new title row).

## Target shell

```
┌─[◆] File  View  Go  Help ────────[ ⌕ Find measure, table, column or visual  Ctrl+K ]──── Contoso Finance ┐ 32 px title row
├────────────────────┬─────────────────────────────────────────────────────────────────────────────────────┤
│ ▦ Overview         │ ⌕ Search │ Names, formulas and descriptions          [⟳ Rescan]  │  [↻]           │ 36 px view toolbar
│▌⌕ Search    Ctrl+2 ├─────────────────────────────────────────────────────────────────────────────────────┤
│ ⎔ Graph            │                                                                                     │
│ ⬚ Inspector        │   content — full width, start-aligned, 16/20 px padding                            │
│ ☰ Review queue  49 │   lists: 30 px rows, ↑↓ Home End Enter                                             │
│ ⑂ Dev Center       │                                                                                     │
│ ───────────────    │   (next) ┌──────── master ────────┬─║─ detail / properties ─┐                       │
│ ⚙ Settings         │          │ grid / tree             │ ║ docked, resizable     │                       │
│                    │          └─────────────────────────┴─║───────────────────────┘                       │
│ [◧] Ctrl+B          │                                                                                     │
├────────────────────┴─────────────────────────────────────────────────────────────────────────────────────┤
│● Connected │ Contoso Finance │ 1 model · 2 reports · 97 objects · 158 relationships │ 49 to review │ Scanned … ✓ Scan complete  ⌨ ☀ │ 26 px status bar
└──────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

At < 1180 px the side bar narrows; at < 760 px it becomes the icon rail and the menu bar folds into the
command centre (the window still works on a laptop split screen).

## Shortcut map

Single source: `frontend/src/shortcuts.js` (menus, tooltips, F1 sheet and the key handler all read it).

| Area | Key | Command |
| --- | --- | --- |
| Go | Ctrl+1 … Ctrl+6 | Overview, Search, Graph, Inspector, Review queue, Development Center |
| Go | Ctrl+K, `/` | Find object (focus search) |
| Go | Alt+← | Back (Inspector → where you came from, focus restored) |
| File | Ctrl+, | Settings |
| File | Ctrl+F5 | Scan sources |
| View | F5 | Reload data (no page reload) |
| View | Ctrl+B | Toggle side bar (rail) |
| View | Ctrl+Shift+L | Toggle light/dark |
| Help | F1 | Keyboard shortcuts |
| Menus | Alt or F10; Alt+F/V/G/H | Focus menu bar; open a menu; ←/→ between menus |
| Lists | ↓ from field, ↑/↓, Home/End, Enter | Move through results, open |
| Proposed | F6 / Shift+F6 | Cycle panes |
| Proposed | A / R / Space (review grid) | Approve / reject / multi-select |
| Proposed | Shift+F10, context-menu key | Row context menu |
| Proposed | Ctrl+Shift+P | Command palette over the same `SHORTCUTS` table |

## What changed on this branch

- `src/shortcuts.js` + `test/shortcuts.test.js`: the key map, event normaliser, text-field guard, mac glyphs.
- `src/components/AppShell.jsx`: `AppMenuBar` (Radix Menubar, Alt/F10/mnemonics), `StatusBar`, `ShortcutsDialog`.
- `src/App.jsx`: shell restructured (title row → workbench [side bar | toolbar + content] → status bar);
  one command table drives menus, toolbar and keys; F5/Ctrl+F5 intercepted; Alt+← back; collapsible side
  bar remembered in localStorage; arrow-key lists for search/browse results and lineage.
- `src/app.css`: new Shell section (fixed viewport, `#main-content` is the only scroller; search/review
  scroll restore moved from `window` to it); density pass (titles, stat tiles, search field and rows, radii, padding,
  start-aligned full-width pages); responsive rules updated; floating toast removed.
- Existing contracts kept: `navigation "Main navigation"` and its button names, `Reload Brain`,
  `.toast` / `.topbar-scanning` / `.nav-count` selectors, all page headings.

## Trade-offs worth knowing (for the combiner)

- **Status bar is 26 px, not VS Code's 22 px**, because the repo's axe gate enforces WCAG 2.5.8 target
  size (24×24) on its buttons. Keep it ≥ 26 px if anything clickable lives there.
- **Fixed viewport was required, not just nicer**: with sticky bars over a scrolling body, axe flagged
  content scrolled under the bars as "partially obscured" targets in the Dev Center specs.
- **Overview tiles were kept** (only densified) because several e2e specs assert their headings; the real
  fix is the Explorer tree in the next steps, which should replace them rather than restyle them again.
- **Shortcuts are data**, not handlers sprinkled per view: anything a parallel audit adds (command palette,
  context menus) should register in `SHORTCUTS` so menus, F1 sheet and tooltips stay truthful.

## Recommended next steps (in order)

1. Docked, resizable Explorer tree + Properties pane (replaces Overview tiles and the Search/Inspector split).
2. Review queue as a keyboard grid with a detail pane and A/R keys.
3. Context menus with copy-as-DAX-reference.
4. Output/Problems pane for scan logs and persistent errors; Cancel scan.
5. Follow OS theme by default (update axe baselines alongside).
6. F6 pane cycling and a command palette on top of `SHORTCUTS`.

**Verification:** `npm test` 167/167; full Playwright suite (`CI=1 npx playwright test`) 233/233 on the final build.
