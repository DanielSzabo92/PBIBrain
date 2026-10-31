# Can the design gates run here, and what do they say about the current theme?

Type: task (AFK)
Status: resolved
Blocked by: none

## Question

Make the render gates work on this PC. Then measure the current theme and screens, so that later tickets start from facts and not from claims. Record what was done and the results.

## Context

- Run in `frontend/`: `npm install`, then `npx playwright install chrome`.
- Design kit gates: `C:/Users/Daniel/.claude/plugins/local/ux-ui-agent-skills/scripts/` (`gate.mjs`, `accuracy_report.mjs`, `verify_states.mjs`, `verify_responsive.mjs`, `validate_contrast`, `lint_hardcodes`, `check_no_emoji.py`, `lint_native_select.py`, `slop_tells.mjs`). Read the `design-doctrine` and `design-qa` skills for the commands. Run single render gates with `DS_REQUIRE_BROWSER=1`, so that SKIPPED becomes a failure.
- Measure:
  - Contrast of the text, status, and brand tokens in `frontend/src/theme.css`, dark and light, on each surface token.
  - axe on the existing screens (Overview, Search, Graph, Inspector, Review queue, Settings), both themes. Use the existing Playwright setup (`frontend/playwright.config.js`, fake server `tests/graph_ui_server.py`).
  - Hardcoded colors and native selects in `frontend/src/` (count and place).
  - Responsive overflow of the existing shell from 1024 to 1440 wide.
- Do not fix findings in this ticket. Record them as facts for ticket 09.
- Do not commit `node_modules` or browser files.

## Done when

The answer lists: the commands that worked, the gate versions, each measured value (pass or fail with the real number), and each gate that could not run, with the reason. Measured values replace UNMEASURED in later tickets.

## Answer

Measured on 2026-10-31 on this PC (Windows 11 Pro 10.0.26200). The render gates work. Each value below comes from a gate run in this session. These values replace UNMEASURED in later tickets. Scripts and raw output are in `.scratch/dev-center-ui/gates/`.

### Setup: the commands that worked

1. `npm install` in the kit folder `C:/Users/Daniel/.claude/plugins/local/ux-ui-agent-skills/`. This is the necessary step. The kit render scripts do `import('playwright')` from the kit folder. The kit had no `node_modules`, so each render gate printed SKIPPED. `frontend/node_modules` does not help, because Node resolves the import from the script folder.
2. `npm install` in `frontend/` (result: "up to date").
3. `npx playwright install chrome` in `frontend/`. Google Chrome was already installed at `C:/Program Files/Google/Chrome/Application/chrome.exe`, so the command did nothing (exit 0).
4. Smoke test: `DS_REQUIRE_BROWSER=1 node scripts/measure_render.mjs examples/sample-app/preview.html` in the kit folder. Result: "all 25 text element(s) meet WCAG AA", exit 0 (not SKIPPED).
5. App screens: `npm run build` in `frontend/`, then `python -m tests.graph_ui_server --port 8765` from the repo root (the fake server of `frontend/playwright.config.js`).

### Versions

| Part | Version |
|---|---|
| ux-ui-agent-skills kit | 3.0.0 |
| playwright (kit and frontend) | 1.63.0 |
| axe-core (kit) | 4.10.2 |
| Chrome (channel `chrome`) | 156.0.8078.49 |
| Node | 22.23.1 |
| Python | 3.11.9 |

### How each value was measured

- Token contrast: `gates/theme_contrast.py`. It reads `frontend/src/theme.css` and uses the kit `contrast.py` ratio. The kit `validate_contrast.py` reads only DTCG JSON, so it cannot read `theme.css`.
- axe and page overflow: `gates/measure_app.mjs`. It drives the built app on the fake server. It injects the kit axe-core 4.10.2 with the same rule tags as the kit `axe_audit.mjs` (wcag2a, wcag2aa, wcag21a, wcag21aa, wcag22aa). The kit `axe_audit.mjs` and `verify_responsive.mjs` read only static files, and the app needs its API.
- States, target size, slop tells: `gates/snap.mjs` saves each screen as one static HTML file with inline CSS. Then the kit gates run on these files with `DS_REQUIRE_BROWSER=1`.
- Inspector = the "Net Sales" measure, opened from Search. Search = results for "Net Sales". Screenshots of each screen were examined: each screen opened with real fixture data, in the correct theme.

### 1. Token contrast (theme.css), dark and light

Text tokens on the 6 surface tokens (`bg`, `bg-sidebar`, `surface`, `surface-2`, `surface-3`, `surface-hover`), need 4.5:1:

| Token | Dark min to max | Light min to max | Result |
|---|---|---|---|
| text | 13.77 to 16.74 | 15.55 to 17.91 | pass |
| text-2 | 6.68 to 8.12 | 5.54 to 6.38 | pass |
| text-3 | 5.56 to 6.76 | 4.71 to 5.42 | pass |
| brand | 6.15 to 7.47 | 4.79 to 5.52 | pass |
| brand-strong | 7.92 to 9.63 | 6.30 to 7.26 | pass |
| ok | 8.31 to 10.10 | 5.10 to 5.87 | pass |
| warn | 8.92 to 10.85 | 5.43 to 6.26 | pass |
| bad | 6.17 to 7.49 | 5.02 to 5.79 | pass |
| info | 7.36 to 8.94 | 5.03 to 5.79 | pass |

The lowest light values are on `bg-sidebar` and `surface-3` (`text-3` 4.71, `brand` 4.79). They pass, but with little margin.

Status text on its own soft tint (badge pattern), need 4.5:1:

| Pair | Dark (on surface / on bg) | Light (on surface / on bg) |
|---|---|---|
| ok on ok-soft | 7.61 / 8.39 | 5.25 / 4.87 |
| warn on warn-soft | 8.03 / 8.87 | 5.58 / 5.19 |
| bad on bad-soft | 5.87 / 6.45 | 5.15 / 4.79 |
| info on info-soft | 6.83 / 7.52 | 5.12 / 4.76 |
| brand on brand-soft | 5.80 / 6.37 | 4.87 / 4.53 |

All pass. `brand` on `brand-soft` over `bg` in light (4.53) is the closest pair.

Text on fills: `brand-ink` on `brand` dark 7.41, light 5.52. `brand-ink` on `brand-strong` dark 9.56, light 7.26. `text-inverse` on `text` 16.74 / 17.91. All pass.

Non-text (WCAG 1.4.11, need 3:1 when the line identifies a control):

| Token | Dark (bg / surface / surface-2) | Light (bg / surface / surface-2) | Result |
|---|---|---|---|
| control-border | 4.01 / 3.74 / 3.57 | 3.25 / 3.52 / 3.34 | pass |
| brand (also `ring`) | 7.47 / 6.98 / 6.65 | 5.10 / 5.52 / 5.24 | pass |
| line-focus | 1.85 / 1.73 / 1.65 | 1.76 / 1.90 / 1.81 | below 3:1 |
| line-strong (also `input`) | 1.46 / 1.36 / 1.30 | 1.36 / 1.47 / 1.40 | below 3:1 |
| line (also `border`) | 1.23 / 1.15 / 1.09 | 1.16 / 1.26 / 1.20 | below 3:1 |

Fact for ticket 09: `line` and `line-strong` are correct only for decorative lines. The shadcn token `input` maps to `line-strong` (1.30 to 1.47). A control that shows its boundary only with `border-input` fails 1.4.11. New controls must use `control-border`.

### 2. axe on the existing screens (1440 x 900)

| Screen | Dark | Light |
|---|---|---|
| Overview | 0 violations | 0 violations |
| Search | 0 | 0 |
| Graph | 2 rules, 5 nodes: FAIL | 2 rules, 5 nodes: FAIL |
| Inspector | 0 | 1 rule, 1 node: FAIL |
| Review queue | 0 | 0 |
| Settings | 0 | 0 |

Findings for ticket 09:

- Graph, both themes, `aria-valid-attr-value` (critical), 2 nodes: the Radix tab triggers `#radix-:r0:-trigger-all` and `#radix-:r5:-trigger-overview`. The probable cause is `aria-controls` that points to a tab panel that is not in the DOM.
- Graph, both themes, `nested-interactive` (serious), 3 nodes: the graph nodes (`div[data-id="model:finance-model"]`, `div[aria-label="Select Sales"]`, `div[data-id="report:sales-report"]`) are interactive and contain focusable children (the "N inside" expand buttons).
- Inspector, light, `color-contrast` (serious), 1 node: `.type-chip` "Measure" is 4.15:1 (`#7e715b` on `#f2efe8`, 12px), need 4.5:1. Cause: `.type-chip` text is `color-mix(artifact color 55%, var(--text))`. The artifact colors are pastel palette values in `graphPresentation.js`, not theme tokens. Other artifact types can give different ratios. Only "Measure" was measured.

### 3. States (kit `verify_states.mjs`, default, hover, focus), on snapshots

| Screen | Element-states | Dark | Light |
|---|---|---|---|
| Overview | 47 | pass | pass |
| Inspector | 92 | pass | pass |
| Review queue | 125 | 20 FAIL (gate error, see below) | 20 FAIL (gate error) |
| Settings | 50 | pass | pass |

The Review queue failures are not real. The gate reports "Approve" and "Reject" hover at 1.00:1 (dark) and 1.70:1 / 1.20:1 (light). A real hover in Chrome gives `rgba(240, 127, 127, 0.12)` behind "Reject" (dark) and `rgba(31, 157, 100, 0.1)` behind "Approve" (light). The gate read the hover background without its alpha. The composited values are 5.15:1 to 7.61:1 (section 1, status on soft tint), so these states pass. Caution: do not trust `verify_states` for a hover background with alpha. Measure it in the live page.

Search and Graph were not given to `verify_states`: their state depends on live search and on the graph canvas, which a static snapshot cannot keep.

### 4. Target size (kit `verify_target_size.mjs`, dark snapshots)

Overview 32, Inspector 64, Review queue 84, Settings 38 targets: all at least 24 x 24 or covered by an exception. Pass.

### 5. Slop tells (kit `slop_tells.mjs`, dark snapshots)

- Overview, Review queue, Settings: no tells.
- Inspector: HIGH, 3 `div.evidence-card` with a 2px border on the left side only (`rgb(43, 47, 55)`). LOW: two near-same neutrals `rgb(14,15,19)` and `rgb(15,16,20)`.
- Seen in screenshots, not flagged by the gate: the Inspector lineage rows and the graph nodes also show a colored bar on the left side only. Fact for ticket 09: do not copy these patterns into the Development Center.

### 6. Hardcoded values (kit `lint_hardcodes.py frontend/src`)

FAIL: 1059 values in 31 files. 995 px, 60 hex, 4 time, 1 other.

- Hex colors (60): `graphPresentation.js` 42 (graph color palettes), `app.css` 13 (for example `#fff` at line 67, `#7cb8ff` and `#c792ea` at lines 431 to 432), `App.jsx` 5.
- Values by file: `app.css` 998, `graphPresentation.js` 42, `button.jsx` 7, `App.jsx` 5, and 1 each in `theme.css`, `guard.css`, `sheet.jsx`, `native-select.jsx`, `input.jsx`, `checkbox.jsx`, `GraphView.jsx`.
- Fact for ticket 09: the px values are mostly the existing `app.css` layout. New Development Center CSS must use tokens. A new lint baseline must count only new files.

### 7. Native selects (kit `lint_native_select.py frontend/src`)

FAIL: 1 native `<select>` element, in `components/ui/native-select.jsx:14`. The wrapper `NativeSelect` has 13 uses: `App.jsx` 8, `ImpactExplorer.jsx` 3, `GraphView.jsx` 1, `ModelSummary.jsx` 1. Old screens keep it in version 1 (map decision 4).

### 8. Emoji and dashes (kit `check_no_emoji.py frontend/src`)

FAIL: 0 emoji, 5 em dashes. 4 are the empty-value text "—" shown in the UI (`App.jsx:70`, `App.jsx:991`, `App.jsx:1023`, `GraphDetails.jsx:12`). 1 is in a CSS comment (`app.css:2`). Fact for ticket 09: the Development Center needs its own empty-value text with no dash.

### 9. Responsive overflow of the shell (dark theme, measured in the live app)

Sizes 1024 x 640, 1024 x 900, 1152 x 900, 1280 x 900, 1366 x 900, 1440 x 900. Six screens at each size: 36 measurements. Page-level horizontal overflow: 0 px on all 36. Elements past the right edge outside a scroll container: 0 on all 36. Pass.

### Gates that could not run, and why

| Gate | Reason |
|---|---|
| kit `validate_contrast.py` on the app theme | It reads only DTCG `tokens/*.json`. The app theme is CSS in `theme.css`. Replaced by `gates/theme_contrast.py` with the kit `contrast.py` formula. |
| kit `axe_audit.mjs` on the app | It reads only static files. Replaced by the same axe-core version and rule tags inside `gates/measure_app.mjs`. |
| kit `verify_responsive.mjs` on the app | It reads only static files, and it measures 280 to 951 px (phone widths). The app has no phone layout (map decision 5). Replaced by the 1024 to 1440 measurement in `gates/measure_app.mjs`. |
| kit `measure_render.mjs` on app screens | Not run on the app. The token table (section 1), axe `color-contrast` (section 2) and `verify_states` (section 3) cover rendered text contrast. |
| kit `accuracy_report.mjs` | It checks the kit itself, not a target app. Not useful for this repo. |
| `verify_states` on Search and Graph | A static snapshot cannot keep live search state or the graph canvas. |
| Snapshot without inline CSS | The first snapshot try used `<base href>` to the fake server. The kit gates did not load the stylesheet (default blue link on black, 2.23:1). Those numbers were discarded. `snap.mjs` now inlines the CSS. |
