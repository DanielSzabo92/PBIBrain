# 05: U1 shared parts

Status: open. Lane: ui. Design step: U1 (docs/DEV_CENTER_UI_DESIGN.md section 13).

Depends on (tickets): [02](02-u0-test-harness.md).

The goal, the code areas, and the acceptance tests are the design text below. Each acceptance test must be an automated test, except the items that the design marks as manual.

### Design text: U1. Shared fixes, tokens, parts

- Goal: the shared parts and tokens exist and pass their gates on a specimen.
- Code areas: `frontend/src/theme.css`, `frontend/src/devcenter/devcenter.css`, `frontend/src/components/ui/` (button, tabs, checkbox, and the new generic parts of section 6.1), a dev-only specimen route, `tests/test_theme_contrast.py`.
- Depends on: U0.
- Acceptance tests:
  - U-fix-1: the contrast test passes `--bad-ink` on `bad` and on `--bad-strong` at 4.5:1 or more in both themes. e2e axe on an old screen with a destructive button has no `color-contrast` violation.
  - U-fix-2: e2e axe on Graph has no `aria-valid-attr-value` violation. The active tab is a fill, not an underline (the ticket 08 prototype still shows an underline; this document wins). The existing e2e suite passes.
  - The contrast test passes each new pair of section 7.4 in both themes.
  - The specimen route (only with `DEVCENTER_FAKE=1`) renders each part in each of its states. e2e axe: 0 violations in both themes. Click test: checkbox, switch, radio, and segmented control change state.
  - e2e keyboard specs for Select, Combobox, Menu, SegmentedControl, Tabs, Dialog, and SidePane (A6, A9, A10).
  - Unit: StatusBadge refuses a tone with no label (A4).
  - Kit gates on the specimen snapshot (section 13 rule), recorded.

## Build record

Worker branch: `worktree-agent-a0a5ad18f03a7b45a`. Base: `446ee4e`.

### What I built

- `frontend/src/theme.css`: the 7.1 tokens (`--ok-tint`, `--warn-tint`, `--bad-tint`, `--info-tint`, `--brand-tint`, `--bad-ink`, `--bad-strong`) in both themes, and the 7.2 aliases (`--cmp-*`, `--proposal*`, `--impact-*`, `--row-*`).
- `frontend/src/devcenter/devcenter.css`: the 7.2 layout tokens and the styles of all new generic parts. It has no hex color and no one-sided border (separators use an inset shadow). `main.jsx` imports it.
- U-fix-1: the destructive Button uses `--bad-ink` on `bad`, hover `--bad-strong`. The old review queue "Remove decision" (outdated saved decision) is now `variant="destructive"`.
- U-fix-2: `Tabs` keeps each `TabsContent` in the DOM (`forceMount`, `hidden` when inactive; the children mount only when the panel is active, unless `keepMounted` is set). A tab row with no panels gives `controls` the id of the region that it changes. Graph uses `controls="graph-canvas"`. The active tab stays a fill.
- Changed parts: Button (`destructive-outline`, `status` with `tone`, `loading` with `loadingText`), Tabs (count pill with a tone), Checkbox (`size="target"` 24 x 24 px, indeterminate, `aria-invalid`). The unchecked Checkbox ink is now `text`, because the kit state gate read the hidden value "on" as `brand-ink` text on `surface-2` (1.05:1).
- New parts in `frontend/src/components/ui/`: Select, Combobox, Menu, Popover with FilterButton, FilterChip, SegmentedControl (toggle and radio mode), Switch, ChoiceRadio, StatusBadge (rules in `status-badge-rules.js`), Tooltip, Notice and Banner, Toast (one polite region, 8 s minimum, held on hover and focus), Dialog and AlertDialog (progress mode, `aria-modal`), SidePane (aside at 1280 px and wider, modal sheet below), StepIndicator and ProgressList, ResultPanel, EmptyState, Skeleton, DataTable, and the shared `field.jsx`.
- Specimen route `/__specimen__` (`frontend/src/devcenter/specimen/`): a lazy chunk. It shows only when `window.__DEVCENTER_FAKE_METHODS__` exists, and only the fake server shim sets it. The fake server serves the production build, so the chunk is in that build. Without the shim, the route shows the app (e2e checks this on port 8765).
- `axe-core@4.10.2` (exact version) is a dev dependency. `frontend/e2e/axe.js` injects it with the A1 tags.
- `tests/test_theme_contrast.py`: new class `NewTokenContrastTest` with each 7.4 pair in both themes, the tint composite check, text on each tint, the wireframe borders, and the destructive Button rule in `app.css`.
- Kit gate harness: `.scratch/dev-center-build/gates/u1/`. A vite IIFE build of the specimen, then `snap.mjs` writes one HTML file for each theme with inline CSS and an inline classic script. Thus `verify_focustrap` can open a real Radix dialog from `file://`.

### Change to a test of another area

- `frontend/test/devcenter-lint.test.js` (U0): the native-select rule was case-insensitive, so it failed on the JSX part `<Select>`. The rule now ignores `<Select` (capital S, but not `<SELECT`). I added a clean input with `<Select label=...>`. All bad inputs still fail.

### Tests

| Command | Result |
|---|---|
| `python -m unittest tests.test_theme_contrast` | 12 tests OK |
| `python -m unittest discover -s tests` | 366 tests OK |
| `npm test` (frontend) | 41 pass, 0 fail (new: `test/statusBadge.test.js`, 3 tests) |
| `npm run build` | OK |
| `npx playwright test` (full suite, both servers) | 71 passed (new: `devcenterParts.spec.js` 17, `sharedFixes.spec.js` 4) |

I did not run the guarded spec (`playwright.guard.config.js`), because it needs the repo `.venv` and Chrome. This ticket does not change `GuardReview`.

Acceptance tests and where they are:

- U-fix-1: contrast test (`--bad-ink` on `bad` 7.49 and 5.79, on `--bad-strong` 9.25 and 7.56). `sharedFixes.spec.js`: axe `color-contrast` on the review queue with "Remove decision", both themes, also on hover.
- U-fix-2: `sharedFixes.spec.js`: axe `aria-valid-attr-value` on Graph (Overview and Full graph), both themes. Each `aria-controls` target exists. The active tab is a fill with no bottom border. The existing e2e suite passes.
- 7.4 pairs: `NewTokenContrastTest`.
- Specimen: axe 0 violations in both themes. The closed state is checked on the full page. The open Select listbox and the open Dialog are checked inside the overlay. The open Menu, Combobox list, and aside pane are checked on the full page. Click test: checkbox, switch, radio, segmented control.
- Keyboard specs: Select, Combobox, Menu, SegmentedControl (both modes), Tabs, Dialog, AlertDialog, progress mode, Toast (fake clock), SidePane at 1440 x 900 and 1024 x 640.
- Unit: StatusBadge refuses a tone with no label.

### Kit gates (specimen snapshot, `DS_REQUIRE_BROWSER=1`, `gate.mjs` with the fake `argv[1]`)

| Gate | Light | Dark |
|---|---|---|
| `verify_states` | OK, 201 element-states | OK, 201 element-states |
| `verify_target_size` | OK, 148 targets at 414 and 1280 px | OK, 148 targets |
| `slop_tells --strict` | OK, no tells | OK, no tells |
| `verify_focustrap --open=#specimen-open-dialog` (Dialog) | OK, 4 focusables | OK, 4 focusables |
| `verify_focustrap --open=#specimen-open-margin` (SidePane sheet; the gate viewport is 1100 px) | OK, 4 focusables | OK, 4 focusables |

AlertDialog: the gate accepts only `role="dialog"`, and AlertDialog has `role="alertdialog"`. The e2e spec covers its initial focus, trap, Escape, and focus return.

### Rework 1

- Finding 1: the SidePane sheet spec read `boundingBox()` during the `sheet-in` animation (400.00006 px). The spec now waits for each animation of the sheet to finish and compares the computed width. The 400 px limit stays.
- Small finding: `SECTION_7_4_PAIRS` has the pair `bad-strong` on `surface` (fill edge, 3:1): 8.65 dark, 7.56 light.
- Merged `354f742` (S1, S2, U2, and notes). Tests after the merge: Python 441 OK; `npm test` 102 pass; `devcenterParts.spec.js --repeat-each=5` 85 passed; full e2e 71 passed.

### Rework 2

- Finding 1: the Toast spec was flaky, because `page.clock.install()` does not pause the clock, so real time moved on after `runFor`. The spec now installs the clock at a fixed time and pauses it with `pauseAt` after the page loads. Only `runFor` moves time. The checks are the same. No other spec of this ticket uses the fake clock.
- Tests: Toast spec `--repeat-each=20` 20 passed; `devcenterParts.spec.js --repeat-each=10` 170 passed; full e2e 71 passed.

### Open items

- A modal Radix overlay (Select listbox, Dialog, sheet) puts `aria-hidden` on the page behind it (`hideOthers`). axe then reports `aria-hidden-focus` on the full page. The focus trap keeps focus out of that page. The spec checks the open overlay itself. Later U-steps that run A1 on an open dialog must do the same, or the lead must decide to set `inert` on the background.
- `verify_states` measures default, hover, and focus only. The e2e axe runs measure the open, error, and selected states.
