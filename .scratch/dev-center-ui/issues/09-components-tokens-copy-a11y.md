# Which new components, tokens, copy, and a11y rules does the Development Center UI need?

Type: grilling
Status: resolved
Blocked by: 01, 03, 04, 05, 06, 07, 08

## Question

Collect the component, token, copy, and a11y needs of tickets 02 to 08 into one set. Which parts are new in `frontend/src/components/ui/`, and what are their specs with the 8 states? Which semantic tokens go into `theme.css`? What is the copy catalog? What is the a11y contract?

## Context

- Charting decisions 3 and 4: one design system; semantic tokens only for new meanings, both themes; icon + text for each status; Radix-based Select and Combobox, no native select in new screens.
- Facts from ticket 01: the measured contrast and axe results of the current theme.
- Token candidates: compare states (6), impact severities (Breaks 3, Needs 4), certainty (certain, possible), wireframe statuses (6), proposal status, plan status (3), source marks (3).
- Copy catalog: backend phrase IDs (compare property phrases, impact reasons) to UI text; error codes of section 12 to plain-word messages; the fixed refusal messages of section 2.1; empty states; confirm dialogs. Obey `ux-writing` and STE. No em dash or en dash.
- a11y contract: WCAG 2.2 AA; keyboard map for the work area and the grid; focus order and focus return after dialogs and sheets; live regions for async results (validate, apply, refresh); screen reader names for state cells, graph nodes, and wireframe boxes; target size; reduced motion.
- Gates to name for each part: `verify_states`, axe, contrast, `lint_hardcodes`, `lint_native_select`, `check_no_emoji`, `slop_tells`, responsive.
- Skills: `design-doctrine`, `design-component`, `ux-writing`, `a11y-audit`.

## Done when

The answer gives: the component inventory (reused, changed, new) with a spec and 8 states for each new part, the token additions with values for both themes and their measured contrast (or UNMEASURED with the reason), the full copy catalog, and the a11y contract with a test for each rule.

## Answer

Resolved on 2026-10-31. The orchestrator accepted all 13 recommendations of round 1 (one round), and added two rules: put the change requests of Q8 to Q11 on the map list, and record the destructive button fix (Q4) and the Tabs fix (Q6) as UI build items, because they also touch the old screens. Specimen: `.scratch/dev-center-ui/prototypes/09/` (`index.html`, `tokens.css`, `token_contrast.py` with its output `token_contrast.txt`, `shots.mjs`, screenshots in `shots/`). The specimen is never shipped.

### Decisions of round 1

1. `--proposal` = `brand-strong`, `--proposal-tint` = `--brand-tint`. The badge is the "bot" icon plus "Proposed".
2. New alias tokens only for the 3 new meanings: compare states (`--cmp-*`), impact and wireframe statuses (`--impact-*`), proposal. Severity, certainty, plan status and source marks use the existing status tones through StatusBadge.
3. One set of opaque hex tints `--ok-tint`, `--warn-tint`, `--bad-tint`, `--info-tint`, `--brand-tint` (the `-soft` token over `surface`). New screens use them for each fill under text. `--*-soft-solid` (06, 08) and `--sel-row` (07) go away. Old screens keep `-soft`.
4. New `--bad-ink` and `--bad-strong`. The shared Button destructive variant uses them (this fixes 2.61:1 in dark). New destructive-outline variant.
5. New SidePane part: `aside` column at 1280 px and wider, modal Radix Dialog sheet below. The old Sheet stays for Graph.
6. The work area reuses Tabs (active = fill). Fix the shared Tabs `aria-controls` failure in the UI build. Graph nested-interactive and the Inspector type chip stay a later task.
7. "Split row" (was "Break match"), "Join with a row" (was "Match with"), "Aligned by" (was "Matched by"), section "Alignment" (was "Match").
8. The backend owns phrase text in `backend/devcenter/contracts/phrases.json`. The UI shows `text` only.
9. Apply errors carry `details.step` and `details.check`. The UI has one sentence for each.
10. `source_remove` keeps the Merge Choices and makes them blocking. The reply gives the count.
11. `naming_rule_edit` refuses a duplicate rule with `action_not_allowed` and `details.existing_rule_id`.
12. No global letter keys. "/" focuses the search field of the active tab. D and M work only with focus in the grid.
13. Text unification as in section 5 ("Changes to earlier tickets").

### Brief Inference

- Domain: dev-tool. Audience: expert BI developer. Tone: calm, utilitarian. Mood: precise.
- Motion depth: subtle feedback only (spinner, sheet slide). All motion stops with `prefers-reduced-motion`.
- Reference anchor: the existing PBIBrain shell (`theme.css`, `components/ui/`). One accent (`brand`). Flat surfaces; shadows only on overlays.

### 1. Component inventory

All parts live in `frontend/src/components/ui/` (generic) or `frontend/src/devcenter/components/` (Development Center only). Each control border uses `control-border` (ticket 01). Focus: 2 px `ring` outline, 2 px offset. Disabled: opacity 0.5 (`--disabled-opacity`) on new parts, plus a visible reason where the tickets give one. No one-sided colored border anywhere. Each status shows icon plus text.

#### 1.1 Reused with no change

| Part | File | Use in the Development Center |
|---|---|---|
| Card | `card.jsx` | Sections of the Sources and Plan tabs |
| Label | `label.jsx` | Field labels |
| Separator | `separator.jsx` | Menu and section dividers |
| Input | `input.jsx` | Text fields (it already uses `control-border` through `.ui-input`) |
| Badge | `badge.jsx` | Base of StatusBadge (StatusBadge adds the icon and the tone) |
| Sheet | `sheet.jsx` | Not used. Graph keeps it. Its 3 px top color bar is a one-sided accent: do not copy it. |
| NativeSelect | `native-select.jsx` | Not used in new screens (charting decision 4). Old screens keep it in version 1. |

#### 1.2 Changed

| Part | Change | Reason | Old screens |
|---|---|---|---|
| Button | Destructive variant: `background: var(--bad)`, `color: var(--bad-ink)`, hover `var(--bad-strong)`. New `destructive-outline` variant: `bad` text and border on `surface`, hover `--bad-tint`. New `status` variant with `tone` (ok, warn, bad): `-tint` fill, status text, `currentColor` border, hover `surface-hover`. New `loading` prop: spinner icon, `aria-busy="true"`, `aria-disabled="true"`, and the label changes to the loading text. | The current destructive text `#fff` on `bad` is 2.61:1 in dark (fails 1.4.3, measured). The generic hover replaced the destructive fill (tickets 04, 07). The state gate cannot measure alpha tints (tickets 01, 06, 08). | Yes: UI build item U-fix-1 |
| Tabs | Each `TabsContent` stays in the DOM (`forceMount`, and `hidden` when inactive), so `aria-controls` always points to a real element. Optional count pill with a tone. The active tab stays a fill (`surface-3`, light `surface`), never an underline. | axe `aria-valid-attr-value` on Graph (ticket 01). The Development Center uses the same Tabs. | Yes: UI build item U-fix-2 |
| Checkbox | A 24 x 24 px hit target around the 16 px box. Indeterminate state (one svg, two paths, the same stroke). Error state on the fieldset. | Target size (tickets 05, 06). Page checkbox mixed state (ticket 05). | Old uses keep 16 px unless they opt in (`size="target"`). |
| `theme.css` | The token additions of section 2. | Charting decision 3. | No visual change (new tokens only; the destructive fix is in Button). |

#### 1.3 New parts: anatomy and ARIA

| Part | Kind, base | Anatomy | ARIA and keyboard |
|---|---|---|---|
| Select | atom, Radix Select | label, trigger (value, chevron with 8 px inner padding), listbox (option: check, label, optional second line, optional reason) | trigger `role="combobox"`, `aria-haspopup="listbox"`, `aria-expanded`. Enter, Space, Up, Down open. Typeahead. Home, End. Escape closes and focus goes back to the trigger. |
| Combobox | molecule, Radix Popover plus listbox | label, input `role="combobox"`, listbox with `role="group"` children (each with a header), optional first option `Use new folder "<text>"`, optional warn line | `aria-autocomplete="list"`, `aria-controls`, `aria-activedescendant`. Typing filters. Down opens. Enter selects. Escape closes; a second Escape clears. |
| Menu | molecule, Radix DropdownMenu | trigger button, items (icon, label), groups with a label, separator, destructive item in `bad` | `aria-haspopup="menu"`. Arrows, Home, End, typeahead. Escape closes and returns focus. |
| FilterButton and Popover | molecule, Radix Popover | button (label, value, chevron), popover (`role="dialog"`) with a checkbox list and counts, or a Combobox | `aria-expanded`. sr-only "(active)" when it has a value. Escape closes. |
| FilterChip | atom | label, remove button (24 x 24 px) | remove button `aria-label="Remove filter <label>"` |
| BulkBar | molecule | count, actions, "Clear selection" | `role="region"`, `aria-label="Bulk actions"`. The count also goes to the polite live region. |
| SegmentedControl | atom | 2 to 4 buttons in one track | two modes: toggle buttons (`aria-pressed`, for the view switch and groups) or radio group (`role="radiogroup"`, for "Default" and "Strict"); arrows in radio mode |
| Switch | atom, Radix Switch | track, thumb, label | `role="switch"`, `aria-checked`. Space toggles. |
| ChoiceRadio group | molecule, Radix RadioGroup | fieldset, legend, items (dot, label, badge, reason line, sub-fields of the selected item) | Tab goes into the group. Arrows move and select. A disabled item has `aria-describedby` on its reason. |
| NameField | molecule, Input plus Button | label, input, "Propose name" icon button, hint line, optional "Use proposed name" | `aria-describedby` on the hint. `aria-invalid` on a clash or an empty required name. |
| StatusBadge | atom | icon, word. Tones: ok, warn, bad, info, plain, proposal. | Static `span`. As a tooltip trigger it is a `button` with an `aria-label` that holds the tooltip text. |
| Tooltip | atom, Radix Tooltip | content box (`surface-3`, `line-strong`) | Opens on hover and on focus. Escape closes. The content is never the only place of an action. |
| Notice and Banner | molecule | icon, body, optional list, optional actions. Full hairline `line-strong` border on `surface-2`. | `role="status"` (info, warn, brand) or `role="alert"` (blocking items, errors) |
| Toast | molecule | icon, text, optional action ("Show in folder") | One polite live region (`role="status"`). An error that needs an action never goes only to a toast. |
| Dialog and AlertDialog | organism, Radix Dialog and AlertDialog | title, description, body (scrolls), footer (Cancel, confirm) | `aria-modal`, focus trap, initial focus (Cancel for destructive or bulk actions, else the first field), Escape closes, focus goes back to the trigger. Progress mode: no close button, Escape does nothing. |
| SidePane | organism | header (h2 with `tabindex="-1"`, Previous, Next, Close), scroll body | At 1280 px and wider: `aside` with `aria-labelledby`. Below: Radix Dialog sheet `min(400px, 92vw)`, modal, focus trap, Escape, focus back to the grid row. |
| StepIndicator | atom | ordered list of steps (number or check, label) | `aria-current="step"`. sr-only "(done)". |
| ProgressList | molecule | list of lines (icon, text, state) and a footer line ("Step 8 of 11. 0:09 elapsed.") | The wrapper `div` is `aria-live="polite"` (never the `ul`, ticket 07). sr-only state words. |
| ResultPanel | molecule | icon, title, text, optional table, actions, close | `role="status"` (success, differences) or `role="alert"` (failure) |
| EmptyState | molecule | icon, title, text, primary action | the heading level of its region |
| Skeleton | atom | `surface-3` bars | the region has `aria-busy="true"` plus a visible status text |
| StateCell | atom | state icon, word, optional count "(N)", optional changed dot (sr-only ", changed") | Inside a grid cell. Cell name: "<source>: <state>, <N> properties, changed". |
| CompareGrid | organism (ticket 03) | sticky header, sticky columns, virtual rows, footer | `role="grid"`, `aria-multiselectable`, `aria-rowcount`, `aria-rowindex`, roving `tabindex`. Keys in section 4.3. |
| DataTable | organism | `table` with a hidden caption, sticky actions column, expandable rows | Real table semantics. The scroll container is `position: relative` (ticket 06). |
| ProposalCard and QuestionCard | molecule (ticket 06) | badge, client and time, change in plain words, confidence, reason, "Your choice", actions. Question: fieldset of options with effect lines. | Buttons with verb labels. Question options are a radio group. |
| ImpactItemRow | molecule (ticket 05) | checkbox, status chip, type icon, name button, place, severity, tags; line 2: reason, path, other paths; primary button, row menu | The name button opens the pane. The row menu is a Menu. |
| CompletenessStrip | molecule | status badge, sentence, "Show areas" | `button` with `aria-expanded` and `aria-controls` |
| ImpactNode | atom (ticket 05) | 224 x 76 px button: type, name, status line | One button with nothing focusable inside. `aria-label`: "<type> <name>, <status>, <n> steps from the change". |
| WireframeBox | atom (ticket 05) | button at x, y, width, height; status line (icon, word), title, visual type, "Hidden" tag | Minimum 24 x 24 px. `aria-label` with type, title, status, cause, hidden. `aria-pressed` when selected. |
| PathStepList | atom | vertical ordered list of steps with edge phrases | `ol`. The last step has sr-only "(this object)". |
| CodeDiff | organism (ticket 03) | header (name, mode, languages, "Compare target with"), two panes or unified, line numbers, marks | sr-only "Removed: " and "Added: " on lines. Dialog rules. |

#### 1.4 New parts: the 8 states

"n/a" means that the state does not apply. For a container, hover, focus and active apply to its child controls.

| Part | default | hover | focus | active | disabled | loading | error | selected |
|---|---|---|---|---|---|---|---|---|
| Select | trigger `surface-2`, `control-border` | trigger `surface-hover` | `ring` outline | open: border `brand`, `aria-expanded="true"`; listbox `surface-2`, `line-strong`, `shadow-md` | opacity 0.5; a disabled option has `text-3` plus a reason | listbox line with spinner "Loading" | trigger border `bad`, hint with x icon | `brand` check on the option; active option `surface-hover` |
| Combobox | input `surface-2`, `control-border` | border `text-3` | `ring`, border `brand`, fill `surface` | listbox open as in Select | opacity 0.5 | listbox line "Loading folders" with spinner | listbox line "Cannot load the folder list. You can type a folder." or a field error | check on the option; warn icon plus text on a mismatched option |
| Menu | trigger as Button | item `surface-hover` | item `surface-hover`; `ring` on the trigger | pressed item `surface-3` | item `text-3`, `aria-disabled` | n/a | n/a | checkable items show a check |
| FilterButton | `surface-2`, `control-border` | `surface-hover` | `ring` | open: `aria-expanded="true"` | opacity 0.5 | counts show "Loading" | popover line "Cannot load the values. Try again." | has a value: border `brand`, text `brand-strong`, fill `--brand-tint` |
| FilterChip | `surface-3`, `line-strong` | remove button `surface-hover` | `ring` on the remove button | press | n/a | n/a | n/a | n/a |
| BulkBar | `--brand-tint` fill, `brand` border | child buttons | child buttons | child buttons | buttons disabled in a locked session | action button loading ("Setting Merge Choice") | toast plus row marks | n/a |
| SegmentedControl | track `surface-2`, `control-border`; items `text-2` | item `surface-hover`, `text` | `ring` on the item | press | opacity 0.5 | n/a | n/a | pressed or checked: `surface-3`, inset `control-border`, `text` |
| Switch | track `surface-3`, `control-border`; thumb `text-2` | track border `text-2` | `ring` | press | opacity 0.5 | n/a | n/a | on: track `brand`, thumb `brand-ink` |
| ChoiceRadio | 16 px dot, 1.5 px `control-border` | item `surface-hover` | `ring` on the dot | item `surface-3` while pressed | dot 0.5, label `text-3`, reason `text-2` | `aria-busy`, status "Saving" with spinner | the sub-field shows its error; the item stays selected | `brand` dot, item `surface-3`, sub-fields show |
| NameField | as Input | border `text-3` | `ring`, border `brand` | n/a | opacity 0.5 | hint spinner "Checking the name" | `aria-invalid`, border `bad`, hint x icon in `bad` | n/a; the proposed variant shows the ok hint with the rule names |
| StatusBadge | `-tint` fill, status text, icon | as a trigger: border `currentColor` | `ring` | n/a | n/a | n/a | tone `bad` | n/a |
| Tooltip | `surface-3`, `line-strong`, `text` | opens | opens | n/a | n/a | n/a | n/a | n/a |
| Notice | `surface-2`, `line-strong`, icon in its tone | actions | actions | actions | actions disabled in a locked session | action spinner ("Confirm row") | tone `bad`, `role="alert"` | n/a |
| Toast | `surface-3`, `line-strong`, `shadow-lg` | action hover | action `ring` | n/a | n/a | n/a | warn icon | n/a |
| Dialog | `surface`, `line-strong`, `shadow-lg`, scrim | buttons | trap and initial focus | buttons | confirm disabled until valid (approval checkbox, Repoint candidate) | confirm loading, or progress mode | body Notice `bad` | n/a |
| SidePane | `surface`, `line` | nav buttons ghost hover | the h2 gets focus when the pane opens from the keyboard | n/a | read-only: child change controls disabled, info Notice | `aria-busy`, "Loading row", skeleton | Notice `bad` with "Try again" | the row of the open pane has `aria-selected="true"` and `--row-active` |
| StepIndicator | number in a `control-border` circle, `text-2` | n/a | n/a | n/a | n/a | n/a | step with x icon in `bad` | current: `brand` fill, `brand-ink`, 600 weight; done: `--ok-tint`, check |
| ProgressList | pending: dashed circle `text-3` | n/a | n/a | n/a | n/a | running: spinner in `brand` | failed line: x icon `bad` plus the fix | done: check `ok` |
| ResultPanel | `surface-2`, `line-strong` | buttons | buttons | buttons | Undo hidden when no backup | n/a | failure variant | n/a |
| EmptyState | icon `text-2`, title, text, button | button | button | button | n/a | n/a | error variant: icon `bad`, `role="alert"` | n/a |
| StateCell | icon plus word in the `--cmp-*` color | row `--row-hover` | cell `ring` (roving focus) | n/a | n/a | skeleton cell | n/a | row `--row-selected` (bulk) or `--row-active` (open) |
| CompareGrid | ticket 03 | row `--row-hover` | cell `ring` | n/a | read-only: checkboxes disabled | skeleton rows, 2 px load bar, `aria-busy` | EmptyState error | bulk `--row-selected`; active `--row-active` |
| DataTable | rows on `surface` | row `surface-hover` | `ring` on controls | n/a | row actions disabled with a reason | skeleton rows | inline row alert (`role="alert"`) | checked row `--brand-tint` |
| ProposalCard | `surface-2`, `line-strong` | buttons | buttons | buttons | Accept disabled on a marked row or in a locked session | "Accepting" | hint in `bad` or `warn` | n/a |
| ImpactItemRow | as DataTable | as DataTable | as DataTable | n/a | actions disabled in a locked session | "Updating" in the region bar | inline alert | checked: `--brand-tint` |
| CompletenessStrip | `surface-2`, `line-strong` | `surface-hover` | `ring` | press | n/a | hidden while impact loads | n/a | open: `aria-expanded="true"` |
| ImpactNode | `surface`, `control-border`; cause node `surface-3` | `surface-hover` | `ring` | press | n/a | n/a | n/a | 2 px `brand` border on all sides |
| WireframeBox | status pattern (section 2.3) | inset `text-2` hairline | `ring` | press | n/a | n/a | n/a | 2 px `brand` outline |
| PathStepList | `text`, edge phrase `text-2` | n/a | links `ring` | n/a | n/a | "Loading paths" | "Cannot load the paths. Try again." | n/a |
| CodeDiff | `code-bg`; `-` lines `--bad-tint`, `+` lines `--ok-tint` | n/a | Dialog | n/a | n/a | skeleton lines | EmptyState error | "Compare target with" radio |

Render each part through the kit adapter protocol (`frameworks/adapter-protocol.md`) in the UI build: React with the existing `cva` and Radix pattern of `components/ui/`.

#### 1.5 Gates for each part

| Gate | Parts | Where it runs |
|---|---|---|
| `verify_states` (default, hover, focus), light and `--dark` | every interactive part | kit, manual release check on a specimen page (CI cannot run the kit, ticket 10) |
| axe (ticket 01 rule tags) | every part and every screen | CI e2e (`axe-core@4.10.2`) and kit `axe_audit.mjs` |
| contrast | every token pair of section 2 | CI `tests/test_theme_contrast.py` (moved from ticket 01) |
| `lint_hardcodes` | all new CSS in `frontend/src/devcenter/**` and new `components/ui/*` files | kit; the CI lint test covers hex colors |
| `lint_native_select` | Select, Combobox, FilterButton, every new screen | CI lint test and kit |
| `check_no_emoji` | all copy of section 3 and all new files | CI lint test and kit |
| `slop_tells --strict` | Notice, ResultPanel, cards, SidePane, WireframeBox, ImpactNode | kit |
| responsive (no page overflow from 1024 to 1440, both themes) | every screen; the SidePane mode switch at 1280 px | CI e2e (ticket 10 overflow check) |
| `verify_focustrap` | Dialog, AlertDialog, SidePane sheet | kit, on a snapshot of the built app |
| `verify_keyboard` | Select, Combobox, Menu, SegmentedControl radio mode, CompareGrid, ImpactNode | kit, plus the e2e keyboard specs |
| `verify_target_size` | Checkbox, FilterChip remove, icon buttons, WireframeBox | kit |
| `lint_intent` | each Button use (destructive never primary) | kit |

### 2. Token additions for `theme.css`

Each value below is in `prototypes/09/tokens.css`. Contrast: kit `contrast.py` ratio, through `prototypes/09/token_contrast.py` (output in `token_contrast.txt`, 61 pairs). Ticket 01 measured the existing tokens.

#### 2.1 Primitive-level additions (new values)

| Token | Dark | Light | Meaning |
|---|---|---|---|
| `--ok-tint` | `#1c2b28` | `#e9f5f0` | `ok-soft` over `surface`, opaque |
| `--warn-tint` | `#2d2921` | `#f8f1e7` | `warn-soft` over `surface`, opaque |
| `--bad-tint` | `#2e2225` | `#fbefef` | `bad-soft` over `surface`, opaque |
| `--info-tint` | `#1e2833` | `#eaf2f9` | `info-soft` over `surface`, opaque |
| `--brand-tint` | `#222535` | `#eff0fc` | `brand-soft` over `surface`, opaque |
| `--bad-ink` | `#0b0c0f` | `#ffffff` | text and icon on a `bad` fill |
| `--bad-strong` | `#f49a9a` | `#9f2626` | hover of a `bad` fill |

The computed composite of each `-soft` token over `surface` gives exactly these hex values in both themes (`token_contrast.txt`, first two lines).

#### 2.2 Semantic aliases (both themes follow the aliased token)

| Token | Alias | Used by |
|---|---|---|
| `--cmp-conflict`, `--cmp-conflict-tint` | `bad`, `--bad-tint` | StateCell "Type conflict" |
| `--cmp-missing` | `text-2` | "Missing" |
| `--cmp-renamed`, `--cmp-moved` | `info` | "Renamed", "Moved" |
| `--cmp-different`, `--cmp-different-tint` | `warn`, `--warn-tint` | "Different" |
| `--cmp-same` | `text-3` | "Same", "Not set" |
| `--cmp-changed` | `brand` | changed dot |
| `--proposal`, `--proposal-tint` | `brand-strong`, `--brand-tint` | "Proposed" badge, question badge |
| `--impact-removed`, `--impact-breaks` (+ `-tint`) | `bad`, `--bad-tint` | wireframe, impact status |
| `--impact-changes` (+ `-tint`) | `warn`, `--warn-tint` | wireframe, impact status |
| `--impact-new` (+ `-tint`) | `ok`, `--ok-tint` | wireframe, impact status |
| `--impact-unchecked` (+ `-tint`) | `info`, `--info-tint` | wireframe, impact status |
| `--impact-unchanged` | `control-border` | wireframe |
| `--row-hover`, `--row-selected`, `--row-active` | `surface-hover`, `surface-3`, `--brand-tint` | grid and table rows |

Layout tokens of the Development Center (no color): `--pane-w: 360px`, `--sheet-w: min(400px, 92vw)`, `--row-h: 36px`, `--target-min: 24px`, `--control-h: 32px`, `--space-1` to `--space-6` (4 px steps), `--disabled-opacity: 0.5`. These go into a `devcenter.css` token block, not into `theme.css`, because they are not theme values.

Status tones with no new token (decision 2): severity Critical = `bad`, High = `warn`, Not checked = plain (`surface-3` and `text-2`); certainty Possible = plain with the help icon; plan status Valid = `ok`, Valid with warnings = `warn`, Not valid = `bad`, Checking = plain; source marks = `warn`; naming rule Proposed = `info`, Confirmed = `ok`, Rejected = plain.

#### 2.3 Wireframe status patterns (pattern, icon, and text: never color only)

| Status | Border | Fill | Icon and word |
|---|---|---|---|
| Removed | 1 px solid `--impact-removed` | 45 degree hatch of `--impact-removed-tint` and `surface`; title struck through | trash, "Removed" |
| Breaks | 3 px solid `--impact-breaks` | `surface` | circle-x, "Breaks" |
| Changes | 2 px dashed `--impact-changes` | `surface` | triangle-alert, "Changes" |
| New | 2 px dotted `--impact-new` | `--impact-new-tint` | plus, "New" |
| Not checked | 1 px dashed `--impact-unchecked` | `surface` | circle-help, "Not checked" |
| Unchanged | 1 px solid `--impact-unchanged` | `surface` | no status line |

#### 2.4 Measured contrast (2026-10-31, kit `contrast.py`)

| Pair | Need | Dark | Light |
|---|---|---|---|
| `ok` on `--ok-tint` | 4.5 | 7.61 | 5.25 |
| `warn` on `--warn-tint` | 4.5 | 8.03 | 5.58 |
| `bad` on `--bad-tint` | 4.5 | 5.87 | 5.15 |
| `info` on `--info-tint` | 4.5 | 6.83 | 5.12 |
| `brand` on `--brand-tint` | 4.5 | 5.80 | 4.87 |
| `--proposal` (`brand-strong`) on `--proposal-tint` | 4.5 | 7.47 | 6.41 |
| `text` on each `-tint` (lowest) | 4.5 | 12.39 | 15.81 |
| `text-2` on `--row-active` | 4.5 | 6.30 | 5.63 |
| `text-3` on `--row-active` | 4.5 | 5.24 | 4.79 |
| `text-2` on `--row-selected` | 4.5 | 6.68 | 5.59 |
| `--bad-ink` on `bad` (destructive fill) | 4.5 | 7.49 | 5.79 |
| `--bad-ink` on `--bad-strong` (destructive hover) | 4.5 | 9.25 | 7.56 |
| `bad` text on `surface` (destructive outline) | 4.5 | 7.00 | 5.79 |
| `ring` (`brand`) on `--row-active` | 3.0 | 5.80 | 4.87 |
| `ring` on `--row-selected` | 3.0 | 6.15 | 4.84 |
| `control-border` on `--row-active` | 3.0 | 3.11 | 3.11 |
| `control-border` on `--row-selected` | 3.0 | 3.30 | 3.08 |
| wireframe borders on `surface`: `bad`, `warn`, `ok`, `info`, `control-border` (lowest) | 3.0 | 3.74 | 3.52 |
| Existing `#fff` on `bad` (current Button destructive) | 4.5 | 2.61 FAIL | 5.79 |

All new pairs pass. The only failure is the existing destructive Button in dark, which UI build item U-fix-1 fixes. Low margin: `text-3` on `--row-active` in light (4.79) and `control-border` on `--row-selected` in light (3.08). Do not make these rows darker or lighter without a new measurement.

UNMEASURED, with reason: the "Removed" title text on the hatch (axe and `contrast.py` do not sample a gradient; the title text is `text` and the lighter hatch band is `--bad-tint`, 15.94:1 light and 13.10:1 dark, but the struck line was not measured). Disabled text at opacity 0.5 is exempt (WCAG 1.4.3 inactive components).

### 3. Copy catalog

Rules for all copy: ASD-STE100 and the `ux-writing` skill. Sentence case. Buttons start with a verb and name the object. Errors give what, why, and how to fix. No em dash or en dash, no emoji, no ellipsis character. Numerals for counts. A `<placeholder>` is always a whole value (name, count, path, time), never a part of a sentence. Empty value words: "None" for an empty value, "Not set" for a Merge Choice that is not set, "Not known" for data that the app does not have. Keys are the i18n keys for the UI build.

#### 3.1 Shared messages

| Key | Text | Where |
|---|---|---|
| `shared.stale` | "This session changed in another place. The view shows the latest state. Do the action again." | Toast after `stale_revision` (all tabs). No automatic retry. |
| `shared.network.title` | "Cannot reach PBIBrain" | Error banner in the region |
| `shared.network.body` | "The local API did not answer. Make sure PBIBrain is running, then try again." | |
| `shared.unknown.title` | "Something stopped this action" | Error banner |
| `shared.unknown.body` | "<backend message> Try again. If it fails again, open the Log tab and copy the details." | |
| `shared.try_again` | "Try again" | Button |
| `shared.not_current` | "This data is not current. Try again to load it." | Region that kept its old data |
| `shared.locked.banner` | "Another PBIBrain window has this session open. You can read it, but you cannot change it." / "Try again" | Work area banner |
| `shared.locked.row` | "Open in another window" / "Opens read-only." | Session list |
| `shared.read_only.notice` | "This session is read-only. Another PBIBrain window has it open." | Row detail, panes |
| `shared.session_not_open` | "This session is not open now. Open it again from the list." | Session list banner after `session_not_open` |
| `shared.include_proposals.switch` | "Include open proposals" | Impact toolbar (Plan has the info line only, ticket 08) |
| `shared.include_proposals.banner` | "This view includes <n> open agent proposals. Apply uses only accepted choices." | Info banner |
| `shared.proposed` | "Proposed" | Badge with the bot icon |
| `shared.proposed.tooltip` | "Agent proposes: <choice>" | Tooltip and `aria-label` |
| `shared.empty_value` | "None" | Empty value |
| `shared.not_set` | "Not set" | No Merge Choice |
| `shared.not_known` | "Not known" | No data |
| `shared.clear_filters` | "Clear filters" | Link |
| `shared.remove_filter` | "Remove filter <label>" | Chip button name |
| `shared.clear_selection` | "Clear selection" | Button |
| `shared.close` | "Close" | Button |
| `shared.cancel` | "Cancel" | Button |
| `shared.updating` | "Updating" | Region bar |

#### 3.2 Error codes (technical design section 12, plus client codes)

| Code | Text | Action | Place |
|---|---|---|---|
| `stale_revision` | `shared.stale` | none | Toast (refetch first) |
| `session_not_open` | `shared.session_not_open` | "Open session" on the row | Session list banner |
| `not_found` | "PBIBrain cannot find this <object kind>. It was removed or renamed in another place. Load the view again." | "Load again" | Inline at the control |
| `invalid_payload` | "PBIBrain cannot save this change. Load the row again and try again." | "Load row again" | Inline Notice `bad` |
| `action_not_allowed` | "This action is not possible now: <backend message>" (use the fixed texts below when `details` has a known reason) | none | Inline at the control |
| `action_not_allowed` + `details.existing_rule_id` | "A rule with this scope and check kind exists: <rule>. Edit that rule." | "Edit that rule" | Rule editor field error |
| `user_choice_exists` | "You already set a Merge Choice on this row. Change the choice in the row detail, or reject the proposal." | none | Inline alert (Agent tab, card) |
| `source_changed` | "A source of this row changed after the agent made this proposal. Confirm the row first, then accept or reject the proposal." | "Open row" | Inline alert; on other calls the UI opens Compare with the marks filter |
| `confidence_below_threshold` | "The agent sent this proposal with a confidence below 90%. PBIBrain did not keep it." | none | Log only (agent side) |
| `reason_required` | "The agent sent this proposal with no reason. PBIBrain did not keep it." | none | Log only |
| `naming_rule_violation` | "The agent proposed a name that breaks a confirmed naming rule: <rule>. PBIBrain did not keep it." | none | Log only |
| `network` | `shared.network.*` | "Try again" | Region banner |
| `unknown`, HTTP 5xx | `shared.unknown.*` | "Try again" | Region banner |

#### 3.3 Fixed refusal messages (technical design section 2.1, ticket 07)

| Key | Text | Where |
|---|---|---|
| `refuse.tmsl_target` | "Save as TMDL in Power BI Desktop first." | Target step, disabled TMSL model |
| `refuse.legacy_target` | "Convert to PBIR in Power BI Desktop first." | Target step, disabled PBIR-Legacy report |
| `refuse.pbix` | `Cannot add "<file>". Save as PBIP in Power BI Desktop.` | Add source, inline `bad` banner |
| `refuse.cloud_target` | "Pull to local PBIP first." / "Pull to local PBIP" | Target step, disabled cloud model |
| `refuse.excel_model` | "PBIBrain cannot read Excel, push or live connected models through XMLA." | Cloud picker, disabled item |
| `refuse.legacy_cloud` | "<report> uses the PBIR-Legacy format. PBIBrain reads it for compare and impact only." | Test result line |

#### 3.4 Session list and create (ticket 02)

| Key | Text |
|---|---|
| `list.title` | "Merge sessions" |
| `list.description` | "Combine many models and reports into one target." |
| `list.new` | "New merge session" |
| `list.no_project` | "Open a project to start a merge session" / "Merge sessions are saved in the project folder. Open a PBIP project first." / "Open project" |
| `list.empty` | "No merge sessions yet" / "A merge session loads many models and reports, compares them, and builds one target. Nothing changes until you apply a plan." / "New merge session" |
| `list.columns` | "Name", "Target", "Sources", "Plan", "Last change", "Status" |
| `list.status.ready` | "Ready" |
| `list.status.newer` | "Needs a newer PBIBrain" / "This session was saved by a newer PBIBrain version. Update PBIBrain to open it." |
| `list.status.damaged` | "Cannot read" / "The session file is not valid JSON or has merge conflict marks. Fix the file, then try again." |
| `list.plan.unknown` | "Not known" |
| `create.title` | "New merge session" |
| `create.steps` | "Sources", "Target", "Name and create" |
| `create.sources.title` | "Sources" / "Add each model and report to compare. Sources stay read-only." |
| `create.add_source` | "Add source" (menu: "PBIP project", "Model folder (TMDL)", "model.bim file", "PBIR report", "Cloud model", "Cloud report") |
| `create.remove` | "Remove" |
| `create.next`, `create.back` | "Next", "Back" |
| `create.target.model` | "Target model" |
| `create.target.empty` | "Empty" / "A new model with no objects" |
| `create.target.copy` | "Copy of <source>" / "Copies the folder. <source> stays the same." / "New folder: <path>" / "Change" |
| `create.target.report` | "Target report" |
| `create.target.new_report` | "New empty report" / "Bound to the target model" |
| `create.target.rebind` | "Rebind needed. Bound to <model>." (after create: "Rebind needed. Bound to <model>. <n> fields are not in the target model.") |
| `create.name.label` | "Session name" (default "<target model name> merge") |
| `create.summary` | "Sources", "Target model", "Target report" |
| `create.run` | "Create session" |
| `create.progress` | "Session created", "<source> added", "<source> not added: <reason>", "Set target", "(not run)" |
| `create.partial` | "The session exists, but <n> source was not added. Open the session to add it again." / "Open session" (plural: "<n> sources were not added") |

#### 3.5 Work area header and banners (ticket 02)

| Key | Text |
|---|---|
| `work.tabs` | "Compare", "Impact", "Plan", "Agent", "Sources", "Log" |
| `work.target_model`, `work.target_report` | "Target model: <name>", "Target report: <name>" (no report: "Target report: new empty report") |
| `work.plan.invalid` | "Plan not valid: <n> blocking" |
| `work.plan.warnings` | "Valid with <n> warnings" |
| `work.plan.valid` | "Valid" |
| `work.plan.checking` | "Checking plan" |
| `work.check_sources` | "Check sources" / loading "Checking sources" |
| `work.check_sources.same` | "All sources are the same as at the last check." (toast) |
| `work.more` | "More actions" (menu: "Check sources", "Close session") |
| `work.banner.changed` | "<n> sources changed since the last check. <n> rows need your confirm." / "Show these rows" |
| `work.banner.missing` | "<n> source was not found: <name>. Find it again or remove it." / "Open Sources" |
| `work.banner.desktop` | `In Power BI Desktop, select "Apply external changes" to load the new files.` / "Close" |
| `sources.status.missing` | "Not found" / "Find source" / "Remove" |
| `sources.status.changed` | "Changed" |
| `sources.remove.confirm` | "Remove <source> from this session?" / "<n> Merge Choices take from <source>. They stay, but the plan is not valid until you change them." (0 choices: "No Merge Choice takes from <source>.") / "Remove source" / "Cancel" |

#### 3.6 Compare (ticket 03)

| Key | Text |
|---|---|
| `compare.search` | "Search names" |
| `compare.filters` | "Type", "Table", "Display folder", "State", "Source", "Page", "Changed since", "Marks", "Has proposal", "Has question" |
| `compare.mode` | "Compare" / "Default" / "Strict" |
| `compare.filter.active` | "(active)" (sr-only) |
| `compare.page.none` | "This session has no report source, so no pages." |
| `compare.changed_since` | "Session start", "Last check" |
| `compare.columns` | "Object", "Row state", "Merge Choice", "Marks"; target column "(target)" sr-only |
| `compare.states` | "Type conflict", "Missing", "Renamed", "Moved", "Different", "Same", "Target" |
| `compare.changed` | ", changed" (sr-only) / "Changed since the snapshot" (title) |
| `compare.notes` | "name: <donor name>", "same after rename" |
| `compare.marks` | "Confirm", "Changed" |
| `compare.cell.badges` | "Confirm row first", "Question", "Proposed" |
| `compare.select_row` | "Select <name>" / header "Select loaded rows" |
| `compare.bulk.count` | "<n> selected" |
| `compare.bulk.set` | "Set Merge Choice" (menu: "Keep target", "Take from" group with each donor, "Skip", "Remove from target") |
| `compare.bulk.confirm_rows` | "Confirm <n> rows" |
| `compare.bulk.all_loaded` | "All <n> loaded rows are selected. Select all <total> rows that match the filters" |
| `compare.bulk.all` | "All <total> rows that match the filters are selected." |
| `compare.bulk.dialog.set` | `Set "<choice>" for <n> rows?` / "<n> rows already have a different Merge Choice. This replaces it." / "<n> rows are skipped: the object is missing in <source>." / "Set Merge Choice" |
| `compare.bulk.dialog.remove` | "Remove <n> objects from the target?" / "The plan deletes these objects from the target model when you apply it." / "Each removal uses the Block policy. Objects with dependents stay blocked until you set a policy in the row detail." / "Remove from target" |
| `compare.bulk.toast` | "Merge Choice set for <n> rows. <m> rows skipped." |
| `compare.diff` | "Code diff: <name>" / "Compare target with" / "Removed: " and "Added: " (sr-only) |
| `compare.footer` | "<n> rows", state counts with the state words, "Default compare" or "Strict compare" |
| `compare.loading` | "Loading rows" / after 1 s "Comparing sources" |
| `compare.empty` | "Nothing to compare yet" / "Add at least one source on the Sources tab. Then the app aligns the objects and shows one row for each object." / "Open Sources" |
| `compare.error` | "Could not load the compare" / "<backend message> Check the source on the Sources tab, then try again." / "Try again" |
| `compare.no_match` | "No rows match the filters" / "<n> rows are hidden by the filters. Remove a filter or clear all filters." / "Clear filters" |

#### 3.7 Row detail (ticket 04, with the decision 7 words)

| Key | Text |
|---|---|
| `row.nav` | "Previous row", "Next row", "Close row detail" |
| `row.meta` | "<type> in <table>" |
| `row.choice.legend` | "Merge Choice" |
| `row.choice.keep` | "Keep target" (target missing: "Do not add (keep target)" / "The target stays without this object.") |
| `row.choice.take` | "Take from <source>" or "Take from source" / disabled "No source has this object." |
| `row.choice.props` | "Take properties from <source>" or "Take properties from source" / disabled "The target does not have this object. Nothing to change." or "Only for measures, columns, and relationships." |
| `row.choice.new_name` | "Add as new name" / disabled "No source has this object." |
| `row.choice.remove` | "Remove from target" / disabled "The target does not have this object." |
| `row.choice.skip` | "Skip" / "No change now. The row stays open." |
| `row.choice.report_group` | "Report measure" |
| `row.choice.promote` | "Promote to target model" / "Creates a model measure and moves the visuals of the target report to it." |
| `row.choice.copy` | "Copy into target report" / "Adds this report measure to the target report." / disabled "This measure is already in the target report." |
| `row.source` | "Source" / option line "<state>: <phrases>" / disabled "Missing. Cannot take from this source." |
| `row.saving` | "Saving" |
| `row.props.legend` | "Properties to take from <source>" / "Different: <phrase>" / "Same" / error "Select at least one property." |
| `row.name` | "New name" / "Change name" / "Propose name" / "Proposed from naming rules: <rule names>." / "Checking the name" |
| `row.name.break` | "This name breaks 1 naming rule: <rule text>. You can keep it." (more: "This name breaks <n> naming rules:" plus a list) |
| `row.name.clash` | `The target already has a <type> "<name>" in <table>. Use a different name. The plan stays not valid until you change it.` / `Use proposed name "<proposed>"` |
| `row.name.empty` | `Type a name. "Add as new name" needs a new name.` |
| `row.folder` | "Display folder" / groups "In target", "In <source>" / `Use new folder "<text>"` / "Loading folders" / "Cannot load the folder list. You can type a folder." |
| `row.alignment.title` | "Alignment" |
| `row.alignment.by` | "Aligned by" / "Same lineage tag", "Same name and type", "Same name, different table", "Same expression, different name (not confirmed)", "Confirmed by you", "Joined by you" |
| `row.rename` | "Possible rename: <old> in <source> and <new> in the target." / "Confirm rename" / "Reject rename" |
| `row.split` | "Split row" / dialog "Split the row of <object>?" / "The row splits into one row for each object. The Merge Choice of this row is removed." / "Split row" / "Cancel" |
| `row.join` | "Join with a row" / dialog "Join <object> with a row" / "Search objects of the same type" / "Join rows" |
| `row.removal.loading` | "Finding objects that use this" |
| `row.removal.none` | "No object uses this. It is removed with no other change." |
| `row.removal.block` | "Removal policy: Block. <n> objects use this <type>. The plan is not valid until you resolve each one." / "Select removal policy" |
| `row.removal.cascade` | "Removal policy: Cascade. <n> other objects are removed with it." / "Change removal policy" |
| `row.removal.repoint` | "Removal policy: Repoint. <n> references go to <object>." (type warning: "The data type is different.") / "Change removal policy" |
| `row.removal.fail` | "Cannot find the objects that use this. Try again." / "Try again" |
| `row.policy.dialog` | "Removal policy for <object>" / "<n> objects use this <type>. Select what happens to them when you remove it." / legend "Policy" |
| `row.policy.block` | "Block" / "Keep the plan not valid until you resolve each object yourself." / "Use Block" |
| `row.policy.cascade` | "Cascade" / "Remove the objects that use it too." / "These objects are also removed or changed:" / effects "Removed", "Field removed from visual", "Visual removed (no field stays)", "Filter removed", "Keeps its own Merge Choice: <choice>" / "Use Cascade (remove <n> objects)" |
| `row.policy.repoint` | "Repoint" / "Replace each reference with one other measure." / "Replace each reference with" / "Data type is different: <candidate type>, not <object type>" / "Use Repoint" |
| `row.policy.fail` | "PBIBrain cannot save this policy. Try again." |
| `row.marks.changed` | "<source> changed since the last check. Examine this row, then confirm it." |
| `row.marks.gone` | "<object> is no longer in <source>. Examine this row, then confirm it." |
| `row.marks.new` | "<object> is new in <source> since the session started. Examine this row, then confirm it." |
| `row.confirm` | "Confirm row" / toast "Row confirmed." |
| `row.blocking` | "<n> blocking items for this row." (1: "1 blocking item for this row.") |
| `row.warnings` | "<n> warnings for this row." (1: "1 warning for this row.") |
| `row.impact_link` | "Show impact of this row" |
| `row.load_fail` | "Cannot load this row. The local API did not answer. Make sure PBIBrain is running, then try again." / "Try again" |
| `row.multi` | "<n> rows selected" / "Use the bar above the grid to set one Merge Choice for all selected rows." / "Name, display folder, properties, and removal policy are set on one row at a time." / "Clear selection" |
| `row.diff` | "Show code diff" |

#### 3.8 Impact (ticket 05)

| Key | Text |
|---|---|
| `impact.scope` | "Whole plan" / "Row: <name>" |
| `impact.groups` | "Breaks", "Needs", "Offers" / "(<n> blocking)" |
| `impact.views` | "Table", "Graph", "Wireframe" |
| `impact.filters` | "Blocking only", "Severity", "Certainty", "Model or report", "Type", "Find object or reason" |
| `impact.status` | "Blocking", "Warning", "Information" |
| `impact.severity` | Breaks: "Breaks", "Changes value", "Needs review". Needs: "Will be added", "Mapped", "Missing", "Name clash" |
| `impact.certainty` | "Certain", "Possible" |
| `impact.tags` | "Possible", "Not changed by this plan", "Proposed", "Hidden", "Information only" |
| `impact.other_paths` | "<n> other paths" / "Show other paths" |
| `impact.actions` | "Include in rewrite", "Repoint", "Cascade", "Keep blocked", "Add from donor", "Map to target", "Drop added object", "Remove field", "Set Cascade", "Current" |
| `impact.bulk` | "<n> selected" |
| `impact.toast` | "<n> item resolved. <m> blocking left." (plural "<n> items resolved.") |
| `impact.pane` | "The plan stays not valid until you resolve this item." / "Shortest path" / "Change: <kind>" / "Cause", "Certainty", "Policy", "Actions" |
| `impact.change_kinds` | "Removed", "Renamed to <name>", "Replaced", "Changed", "Added", "Copied" |
| `impact.completeness` | "Complete" / "All object types and report bindings were checked." / "Incomplete: <n> areas" / "Static impact is a safe superset. Some areas were not checked." / "Show areas", "Hide areas" / "Show 20 more" |
| `impact.areas` | "Not checked object types", "Unresolved bindings", "Remote reports not read", "Bookmarks that refer to a changed object", "Possible only" |
| `impact.graph` | "Impact graph. Tab moves between objects. Enter opens the item." / "Certain", "Possible" / "<n> objects, <m> links" / "Show as table" |
| `impact.graph.node` | "<type> <name>, <status>, <n> steps from the change" / node status "Blocking, breaks", "Warning, changes value", "Information", "On the path" |
| `impact.graph.too_many` | "Too many items for the graph" / "The graph can show 150 objects. These filters give <n> items. Use filters, or open the table." / "Open table" |
| `impact.wireframe` | "<report> (target, after apply)", "<report> (donor, now)", "<report> (not changed by this plan)" / "Drawing", "Visual list" / statuses "Removed", "Breaks", "Changes", "New", "Not checked" / "Filters" / "No change" / priority line "Each visual shows one status, in this order: removed, breaks, changes, new, not checked." |
| `impact.offers` | "Donor report items that use an added model object. Select items to copy into the target report." / "<visual type>, uses <object>" / "Bookmarks are not copied in version 1." / "<n> fields need an action before the copy can work." / "Open Needs" |
| `impact.loading` | "Computing impact for the whole plan" / "Computing impact for row <name>" |
| `impact.error` | "The impact could not be computed" / `The backend stopped with "<error text>". Check the source, then try again.` / "Try again", "Open Sources" |
| `impact.empty.plan` | "Nothing breaks" / "The plan breaks no object in the target model or its reports." |
| `impact.empty.row` | "This row has no impact" / "No object uses <name>, and it needs nothing that the target does not have." / "Show whole plan" |
| `impact.empty.filter` | "No items match these filters." / "Clear filters" |
| `impact.empty.needs` | "The target has everything that the added objects need." |
| `impact.empty.offers` | "No donor report item uses an added object." |
| `impact.large` | "Showing rows <a> to <b> of <total>. The list loads more rows when you scroll (pages of 500)." |
| `impact.paths.load` | "Loading paths" / "Cannot load the paths. Try again." |

#### 3.9 Agent and Log (ticket 06)

| Key | Text |
|---|---|
| `agent.questions` | "Questions (<n>)" / "<n> more open questions. Show them" / "Answered (<n>)" |
| `agent.refresh` | "Last check <time>" / "Refresh" / loading "Checking" |
| `agent.proposals` | "Proposals (<n>)" / filters "Kind", "Status", "Search target" |
| `agent.kinds` | "Merge Choice", "Name", "Alignment", "Removal policy", "Impact action", "Need mapping" |
| `agent.columns` | "Target", "Proposed change", "Confidence", "Reason", "From", "Status", "Actions" |
| `agent.status` | "Ready to accept", "Confirm row first", "Conflicts with your choice" |
| `agent.your_choice` | "Your choice: <choice>" |
| `agent.accept` | "Accept" / "Replace with agent choice" / "Reject" / "Open row" / loading "Accepting", "Rejecting" |
| `agent.accept_selected` | "Accept selected (<n>)" / loading "Accepting <i> of <n>" |
| `agent.accept_all` | "Accept all" / disabled tooltip "No proposal is ready to accept." |
| `agent.accept_all.dialog` | "Accept <n> agent proposals?" / "Each proposal becomes your Merge Choice, name, or mapping. Apply then uses them." / "Nothing is written to the files until you apply the plan." / "Proposals to accept" / "Effect on the plan" / "Now:", "After accept:", "Change: <n> fewer blocking items, <m> more warnings" / "Skipped (<n>)" / "<object>: a source changed. Confirm the row first." / "<object>: you already set a Merge Choice. Decide in the row detail." / loading "Calculating the effect on the plan" / "Accept <n> proposals" |
| `agent.toasts` | "Proposal accepted.", "Proposal rejected.", "Answer saved.", "<n> proposals accepted. <m> skipped.", "<a> of <n> proposals accepted. <m> was not accepted. See the marked row." |
| `agent.new` | "<n> new proposals. Show them" |
| `agent.poll_fail` | "Could not check for new proposals. Try again." / "Refresh" |
| `agent.replaced` | "The agent replaced this proposal." |
| `agent.card` | "Proposed by agent" / "<client>, <time>" / "Confidence" / "Reason" / marked row: "A source of this row changed after the agent made this proposal. Confirm the row first, then accept or reject the proposal." / "Confirm row" |
| `agent.question` | "Question from agent" / "Row: <name>" / "Recommended" / "Sets Merge Choice: <choice>" / "Answer" / loading "Saving answer" / "Open row" |
| `agent.empty` | "No open proposals or questions" / "When an agent connected through MCP proposes a change or asks a question, it shows here. Nothing changes until you accept it." |
| `log.title` | "Session log" |
| `log.filters` | "Author", "Action", "Search target", "Proposal <id>" |
| `log.columns` | "Time", "Author", "Action", "Target", "Before", "After", "Reason", "Proposal" |
| `log.author` | "You", "Agent: <client>" |
| `log.more` | "Showing <n> entries." / "Show more" |
| `log.empty` | "No changes yet" / "Each change to this session, by you or by an agent, shows here with its reason." |

Log action labels (one for each backend action):

| Action | Label | Action | Label |
|---|---|---|---|
| `session_create` | "Created session" | `naming_rule_confirm` | "Confirmed naming rule" |
| `session_open` | "Opened session" | `naming_rule_reject` | "Rejected naming rule" (user rule: "Deleted naming rule") |
| `session_close` | "Closed session" | `naming_rule_edit` | "Edited naming rule" (no rule ID: "Added naming rule") |
| `source_add` | "Added source" | `naming_rules_copy` | "Copied naming rules" |
| `source_remove` | "Removed source" | `proposal_submit` (agent) | "Proposed <kind>" |
| `source_relink` | "Found source again" | `question_ask` (agent) | "Asked a question" |
| `target_set` | "Set target" | `proposal_accept` | "Accepted proposal" |
| `compare_mode_set` | "Changed compare mode" | `proposal_reject` | "Rejected proposal" |
| `alignment_override` | "Confirmed rename", "Rejected rename", "Split row", "Joined rows" | `proposal_accept_all` | "Accepted proposal (accept all)" (one entry for each proposal) |
| `merge_choice_set` | "Set Merge Choice" | `question_answer` | "Answered question" |
| `merge_choice_bulk_set` | "Set Merge Choice (bulk)" | `format_only_apply` | "Formatted target files" |
| `removal_policy_set` | "Set removal policy" | `apply` | "Applied plan" |
| `need_mapping_set` | "Mapped need" | `undo_apply` | "Undid apply" |
| `impact_action_apply` | "<impact action label>" | `change_report_write` | "Wrote change report" |
| `offer_select` | "Selected offer" | `cloud_connect` | "Connected cloud source" |
| `row_confirm` | "Confirmed row" | `pull_to_local` | "Pulled to local PBIP" |
| `sources_check` | "Checked sources" | `cloud_sign_in` | not logged (no session change) |

#### 3.10 Sources, cloud, and naming rules (ticket 07)

The full ticket 07 table "Copy for each state, error and refusal" is part of this catalog with these keys and with one change: the `stale_revision` row uses `shared.stale`. Keys: `cloud.signin.*` (signed out, window open, closed, admin consent, no network, other error), `cloud.select.*` (account line, no workspaces, no capacity, no models, unsupported model, fallback link, fallback help, bad connection, name not found), `cloud.access.*` (Read, Read/Write; no "change later" line), `cloud.test.*` (header, XMLA failed, no Build permission, model not found, report not readable, other workspaces, write conditions), `cloud.report.refused`, `cloud.added`, `pull.*` (confirm, not empty, done, write failed), `rules.*` (section note, breaks caption, no target, detecting, empty, filter empty, confirm selected stopped), `rules.editor.*` (bad pattern, required field, same rule exists), `rules.copy.*`, `rules.delete.*`. Test result lines: "Signed in as <account>", "Connected through XMLA", "Model read: <n> tables, <n> measures", "Capacity: <type>", "Your role: <role>", "Reports in <workspace>: <n> found, <n> readable." Dialog step names: "Sign in", "Select model" (or "Select report"), "Access type", "Test". Buttons: "Sign in with Microsoft", "Use a different account", "Test connection", "Test again", "Add source", "Select a different report", "Pull to local PBIP", "Change folder", "Pull model", "Confirm", "Confirm selected (<n>)", "Add rule", "Copy rules from", "Save rule", "Copy <n> rules", "Delete rule", "Show all rules", "Change target". Pull progress: "Read the model", "Export as TMDL", "Write the PBIP files", "Add as local source". Rule statuses: "Proposed", "Confirmed", "Rejected". Origins: "Detected", "User". Support: "<n> of <m> <type>", "Not detected". Icon button names: "More actions: <rule phrase>".

#### 3.11 Plan, apply, undo (ticket 08)

The ticket 08 tables "Pre-apply block list", "Result view", "Copy for each state" and the dialog, progress, undo, format and report texts are part of this catalog (keys `plan.*`, `apply.*`, `undo.*`, `format.*`, `report.*`). Additions of this ticket:

Progress step names (section 13): 1 "Sources are the same as at the last check", 2 "Plan is valid", 3 "Power BI Desktop has no unsaved changes", 4 "Target files are in the Power BI Desktop format", 5 "Full check passed", 6 "You approved <n> items", 7 "Write a candidate copy", 8 "Guard check", 9 "Write the files", 10 "Rescan and compare", 11 "Save the new fingerprints". Undo: "Restore the files", "Rescan", "Save the fingerprints".

Apply failure text by `details.step` (decision 9). Result panel: "Nothing was written" / "The <step name> stopped the apply. <reason sentence> Your target files are the same as before." / "Run "Check plan", then apply again. If it fails again, open the Log tab and copy the details."

| `details.step` | Reason sentence |
|---|---|
| 1 source check | "A source changed after the last check. Confirm the marked rows first." |
| 2 plan status | "The plan is not valid now." |
| 3 Desktop check | "Power BI Desktop has unsaved changes in the target. Save or close the target, then apply again." |
| 4 canonical check | "Some target files are not in the Power BI Desktop format. Format them first." |
| 5 full validation | "The full check found a problem: <first failed check>." |
| 7 candidate write | "PBIBrain could not write the candidate copy." |
| 8 guard | see `details.check` below |
| 9 promotion | "PBIBrain could not write the target files. It put back the backup." |
| 10 rescan | "The rescan of the target did not finish." |
| 11 fingerprints | "PBIBrain wrote the files but could not save the new fingerprints. Run "Check sources"." |

| `details.check` (step 8) | Reason sentence |
|---|---|
| `scope` | "The candidate changes an object that is not in the plan." |
| `canonical` | "A changed model file is not equal to the Power BI Desktop format of the plan." |
| `tree_compare` | "The candidate model has a difference that no plan step explains." |
| `pbir` | "A report file change does not match the plan." |
| `policy` | "The merge policy refused the change." |
| `approval` | "An item that needs your approval was not approved." |
| `write` | "The write record does not match the candidate files." |
| `rescan` | "The rescan does not match the plan." |

Undo failure: "Undo stopped. Nothing was restored. <reason sentence>" / "Open Log". Format failure: "Nothing was written" / "The guard found a model change in the formatted files, so it stopped the write." / "Open Log".

Blocking item kind to action (ticket 08 asked for this map; kinds from `GET plan` blocking items and `GET apply/preview`):

| Kind | Block text | Action | Goes to |
|---|---|---|---|
| unconfirmed source marks | "<n> rows changed in their source, and you did not confirm them." / "Examine each row, then confirm its Merge Choice." | "Show these rows" | Compare, marks filter |
| breaks, removed object (policy Block) | "<object> uses <removed object>, which this plan deletes." / "Blocking. Set a removal policy for <removed object>, or keep it." | "Show impact" | Impact, that item |
| breaks, unselected dependent of a renamed object | "<object> uses <old name>, which this plan renames to <new name>." / "Blocking. Include it in the rewrite, or keep the old name." | "Show impact" | Impact, that item |
| need missing | "<object> needs <needed object>, which the target does not have." / "Blocking. Add it from the donor, or map it to a target object." | "Show impact" | Impact, Needs, that item |
| name clash | "Name clash: <name> exists in <source A> and in <source B>." / `Blocking. Give a new name or select "Keep target".` | "Show row" | Compare, that row |
| source of a Merge Choice removed (decision 10) | "The source of this Merge Choice was removed: <source>." / "Blocking. Select a different source or a different Merge Choice." | "Show row" | Compare, that row |
| Desktop unsaved | "Power BI Desktop has unsaved changes in <target>." / "Save or close the target in Power BI Desktop. Then check again." | "Check again" | `GET apply/preview` |
| non-canonical files | "<n> target files are not in the Power BI Desktop format." / "The app must format them first. The model does not change." | "Format files first" | format dialog |
| full validation failure | "<failed check>" / "Blocking. Fix the expression in its source, or change the Merge Choice." | "Show row" | Compare, that row |

#### 3.12 Empty states (all in one place)

| Place | Title / text / action |
|---|---|
| Session list, no project | `list.no_project` |
| Session list, no sessions | `list.empty` |
| Compare, no rows | `compare.empty` |
| Compare, no match | `compare.no_match` |
| Impact, plan / row / filter / Needs / Offers | `impact.empty.*` |
| Plan, no steps | "Nothing to apply" / "The target matches your Merge Choices. Change a Merge Choice in Compare to build a new plan." / "Open Compare" |
| Agent | `agent.empty` |
| Log | `log.empty` |
| Naming rules, no target / detecting / empty / filter | `rules.*` (ticket 07) |
| Cloud picker, no workspaces / no models | `cloud.select.*` (ticket 07) |
| Row detail, nothing open | the pane is not shown (ticket 04) |

#### 3.13 Confirm dialogs (all in one place)

Title asks, the confirm button restates the action and object, Cancel stays "Cancel". No type-to-confirm: each action can be undone (Merge Choices change again; Apply has Undo).

| Dialog | Title | Confirm (token) | Initial focus |
|---|---|---|---|
| Remove source | "Remove <source> from this session?" | "Remove source" (destructive) | Cancel |
| Bulk set Merge Choice | `Set "<choice>" for <n> rows?` | "Set Merge Choice" (primary) | Cancel |
| Bulk remove | "Remove <n> objects from the target?" | "Remove from target" (destructive) | Cancel |
| Split row | "Split the row of <object>?" | "Split row" (primary) | Cancel |
| Removal policy | "Removal policy for <object>" | "Use Block" (primary), "Use Cascade (remove <n> objects)" (destructive), "Use Repoint" (primary) | the policy radio group |
| Accept all | "Accept <n> agent proposals?" | "Accept <n> proposals" (primary) | Cancel |
| Delete rule | "Delete this rule?" | "Delete rule" (destructive, trash icon) | Cancel |
| Pull to local | "Pull to local PBIP" | "Pull model" (primary) | the folder field |
| Apply | "Apply the plan to <target>?" | "Apply plan" (destructive when the plan deletes objects, else primary) | the approval checkbox, else Cancel |
| Format files | "Format <n> target files?" | "Format files" (primary) | Cancel |
| Undo | "Undo the apply of <time>?" | "Undo apply" (destructive) | Cancel |

#### 3.14 Phrase ID draft for the backend (decision 8)

The backend owns these texts in `backend/devcenter/contracts/phrases.json`. The UI shows `text` only. Draft texts in STE, maximum 60 characters, no dash.

- Compare properties (technical design 4.2): `prop.expression` "expression changed", `prop.format_string` "format string changed", `prop.format_string_expression` "format string expression changed", `prop.display_folder` "display folder changed", `prop.description` "description changed", `prop.hidden` "hidden changed", `prop.data_category` "data category changed", `prop.data_type` "data type changed", `prop.source_column` "source column changed", `prop.summarize_by` "summarize by changed", `prop.sort_by_column` "sort by column changed", `prop.key` "key column changed", `prop.cardinality` "cardinality changed", `prop.cross_filter` "cross filter direction changed", `prop.active` "active state changed", `prop.security_filter` "security filter direction changed", `prop.ref_integrity` "assume referential integrity changed", `prop.levels` "hierarchy levels changed", `prop.model_permission` "model permission changed", `prop.filter_expression` "row filter changed", `prop.ols` "object level security changed", `prop.partition_mode` "partition mode changed", `prop.m_text` "M text changed", `prop.order` "order changed", `prop.kind` "kind changed", `prop.annotations` "annotations changed (strict compare)", `prop.visual.position` "position changed", `prop.visual.type` "visual type changed", `prop.visual.fields` "fields changed", `prop.visual.filters` "filters changed", `prop.visual.formatting` "formatting changed". Short values show as "<phrase>: <old> to <new>" (the UI never uses an arrow character).
- Compare notes: `note.same_after_rename` "same after rename", `note.name_clash` "name clash".
- Impact reasons (ticket 10 backend examples plus the blocking kinds): `reason.uses_removed_measure` "uses a removed measure", `reason.uses_removed_column` "uses a removed column", `reason.uses_renamed_not_rewritten` "uses a renamed column (not rewritten)", `reason.filter_context` "filter context can change", `reason.type_changed` "uses an object with a new data type", `reason.needs_missing` "needs an object that the target does not have", `reason.name_clash` "has the same name as a target object", `reason.mapped` "maps to a target object", `reason.will_be_added` "is added with this plan".
- Edge phrases: `edge.used_by` "used by", `edge.filters` "filters", `edge.in_visual` "in visual", `edge.on_page` "on page", `edge.in_hierarchy` "in hierarchy".

### 4. Accessibility contract (WCAG 2.2 AA)

Each rule has one test. "e2e" means a Playwright spec in `frontend/e2e/devcenter*.spec.js` on the fake server of ticket 10 (both themes where it says so). "unit" means `node --test`. "kit" means a manual release check with the kit gate and `DS_REQUIRE_BROWSER=1`. "SR" means a manual screen reader pass (NVDA and Narrator) before release.

#### 4.1 Rules and tests

| ID | Rule | WCAG | Test |
|---|---|---|---|
| A1 | Zero axe violations (rule tags wcag2a, wcag2aa, wcag21a, wcag21aa, wcag22aa) on each Development Center screen and state, in both themes. | all | e2e: `axe-core@4.10.2` on each screen of tickets 02 to 08 (fixture scenarios), dark and light |
| A2 | Text contrast 4.5:1, large text 3:1, in each state (default, hover, focus, selected, active row). | 1.4.3 | CI `tests/test_theme_contrast.py` for each token pair of section 2; kit `verify_states` light and `--dark` on the specimen |
| A3 | Control boundaries, focus rings, status borders and graph or wireframe marks 3:1 against their background. New controls use `control-border`, never `line`, `line-strong` or `input`. | 1.4.11 | CI contrast test (`control-border` and `ring` on all surfaces and on `--row-*`); CI lint: no `border-input` or `var(--line-strong)` border on an input, select, checkbox or switch in `frontend/src/devcenter/**` |
| A4 | No color-only status: each status has an icon plus a word; wireframe statuses add a pattern. | 1.4.1 | e2e: each `[data-status]` element has an svg and non-empty text; unit: StatusBadge refuses a tone with no label |
| A5 | No one-sided colored border on any card, notice, toast, row or node. | taste rule | CI lint test (ticket 10, item 5); kit `slop_tells --strict` |
| A6 | Keyboard: each action works with the keyboard only, with the keys of section 4.3. No keyboard trap outside modal dialogs. | 2.1.1, 2.1.2 | e2e keyboard specs: grid (ticket 03 key list), tabs, Select, Combobox, Menu, SegmentedControl, ImpactNode arrows, Dialog; kit `verify_keyboard` |
| A7 | Focus is always visible (2 px `ring`, 2 px offset) and never hidden under a sticky header, sticky column, bulk bar, toast or sheet. | 2.4.7, 2.4.11 | e2e: Tab through each screen; for each focused element assert `outline-width` 2 px and that `elementFromPoint` at its center is the element or its child |
| A8 | Focus order follows the visual order: header, banners, tabs, toolbar, main region, side pane. | 2.4.3 | e2e: Tab order snapshot for the Compare, Impact, Plan and Agent screens |
| A9 | Dialog focus: initial focus as in section 3.13; focus stays inside; Escape closes (not in progress mode); focus goes back to the trigger. If the trigger is gone, focus goes to the h1 of the tab. | 2.4.3, 2.1.2 | e2e for each dialog of section 3.13; kit `verify_focustrap` |
| A10 | SidePane focus: opened from the keyboard, focus goes to the pane h2. As a sheet (below 1280 px) it traps focus and Escape closes it. On close, focus goes back to the grid cell or the item that opened it. | 2.4.3 | e2e at 1440 x 900 (column) and 1024 x 640 (sheet) |
| A11 | Live regions. One polite region for toasts and counts (`role="status"`). Async results: validate ("Plan checked. <status>."), apply progress (ProgressList, polite), apply result (ResultPanel, `status` or `alert`), sources check ("Sources checked. <n> changed."), refresh ("<n> new proposals."), bulk selection count. Blocking errors use `role="alert"`. No region repeats a message within 1 s. | 4.1.3 | e2e: read the live region text after each async action (inject delays and faults with the ticket 10 test controls) |
| A12 | Screen reader names: grid cells "<source>: <state>, <n> properties, changed"; row header "<type> <name>, <row state>"; graph nodes "<type> <name>, <status>, <n> steps from the change"; wireframe boxes "<type>, <title>, <status>, <cause>, hidden"; badges as tooltip triggers carry the tooltip text; icon buttons name their object ("More actions: <rule phrase>"). | 4.1.2, 1.1.1 | e2e: `getByRole` with the exact name for sample cells, nodes, boxes and icon buttons; SR pass |
| A13 | Grid semantics: `role="grid"`, `aria-rowcount` = total plus header, `aria-rowindex` on each virtual row, `aria-selected` on selected rows, `aria-multiselectable`. Graph and wireframe have a full text alternative (Table view, Visual list) with the same selection. | 1.3.1 | e2e: attribute checks after a scroll and a filter change; switch view keeps the selection |
| A14 | Target size: each target at least 24 x 24 px, or covered by the spacing exception. | 2.5.8 | kit `verify_target_size` on the specimen and on snapshots; e2e: bounding box check on checkboxes, chip remove buttons, icon buttons, wireframe boxes |
| A15 | Reduced motion: with `prefers-reduced-motion: reduce`, no spin, slide or fade (status text stays). | 2.3.3 (AAA, house rule) | e2e with `reducedMotion: 'reduce'`: computed `animation-name` is `none` on spinners and the sheet |
| A16 | Errors are text, linked to the field (`aria-invalid`, `aria-describedby`), and say how to fix. | 3.3.1, 3.3.3 | e2e: name clash, empty name, no property, bad pattern, bad connection text |
| A17 | Labels: each field has a visible label (never a placeholder only); disabled options and controls show the reason as text. | 3.3.2, 1.3.1 | axe (A1) plus e2e: disabled radio and Select options have `aria-describedby` with non-empty text |
| A18 | No page-level horizontal overflow from 1024 x 640 to 1440 x 900; wide grids and tables scroll inside their own region; scroll regions with sr-only text are `position: relative`. | 1.4.10 (desktop scope) | e2e overflow check at 1024 x 640, 1280 x 900, 1440 x 900, both themes |
| A19 | Status messages from polls do not move focus or change the list under the user (notice "<n> new proposals. Show them"). | 3.2.2, 2.2.1 | e2e: add a proposal through `/__test__/agent-proposal`; focus and the visible list stay the same until "Show them" |
| A20 | No native `<select>`, no emoji, no em dash or en dash in UI copy. | house rules | CI lint test; kit `lint_native_select`, `check_no_emoji` |
| A21 | Text resize to 200% and zoom to 200% at 1440 x 900 keep each action reachable (the app then is 720 CSS px wide: side panes become sheets). | 1.4.4 | e2e: page zoom 2 on Compare and Plan, no lost controls |

#### 4.2 Focus order and focus return

| From | Action | Focus goes to |
|---|---|---|
| Grid cell | Enter (opens the row detail) | the pane h2 |
| Pane | Close or Escape | the grid cell that opened it |
| Pane | Previous row, Next row | the same button (the pane content changes; the live region says the row name) |
| Any dialog | Cancel, Escape, confirm | the trigger; if the trigger is gone (the row moved after Split row), the new active grid cell |
| Apply dialog | success | the ResultPanel title (`tabindex="-1"`) |
| Bulk action | done | the first selected row cell, or the grid when the selection is clear |
| Tab change | click or arrows | stays on the tab (Radix); Tab moves into the panel |
| Toast action | "Show in folder" | stays on the toast; the toast never takes focus by itself |
| `stale_revision` | refetch | stays on the control that failed (it leaves the loading state) |

#### 4.3 Keyboard map

Global (decision 12): no global letter keys. "/" focuses the search field of the active tab (Compare "Search names", Impact "Find object or reason", Agent "Search target", Log "Search target", Sources rules search). Escape closes the top overlay (menu, popover, tooltip, dialog, sheet), one at a time.

| Region | Keys |
|---|---|
| Tabs | Left, Right, Home, End move between tabs and select them (Radix automatic mode) |
| Compare grid | the ticket 03 map: arrows, Home, End, Ctrl+Home, Ctrl+End, Page Up, Page Down, Enter, Space, Shift+Space, Shift+Up, Shift+Down, Ctrl+A, D (code diff, focus in the grid only), M (Set Merge Choice, rows selected, focus in the grid only), Escape |
| Impact table | Tab between rows and controls; Space toggles the row checkbox; Enter on the name opens the pane |
| Impact graph | Tab in rank order; Right next step, Left previous step, Up and Down same rank; Enter or Space opens the item |
| Wireframe | Tab in reading order; Enter or Space opens the visual |
| Select | Enter, Space, Up, Down open; typeahead; Home, End; Enter selects; Escape closes |
| Combobox | type to filter; Down opens; Up, Down move; Enter selects; Escape closes, second Escape clears |
| Menu | Enter, Space, Down open; arrows; Home, End; typeahead; Escape closes |
| SegmentedControl | toggle mode: Tab and Space; radio mode: arrows |
| Dialog | Tab cycles inside; Escape closes (not in progress mode) |

### 5. Changes to earlier tickets (unified text and tokens)

| Ticket | Was | Now | Reason |
|---|---|---|---|
| 03, 06 | `--proposal` = `brand-strong` (03) or `info` (06); `--proposal-soft` | `--proposal` = `brand-strong`, `--proposal-tint` = `--brand-tint` | Q1: `info` is also Renamed and Moved |
| 03, 05, 06, 07, 08 | `--brand-tint` color-mix (03), hex tints (05), `--*-soft-solid` over `bg` (06, 08), `--sel-row` (07) | hex `--ok-tint`, `--warn-tint`, `--bad-tint`, `--info-tint`, `--brand-tint` over `surface` | Q3: one token for one meaning |
| 05 | `--impact-*-soft` | `--impact-*-tint` | same naming as the tints |
| 04, 07, 08 | destructive hover rule written in each prototype | `--bad-strong`, `--bad-ink` in Button | Q4 |
| 03 | "Decide the active tab style" | Tabs active = fill (`surface-3`, light `surface`) | Q6 |
| 04 | "Break match", "Match with", "Matched by", section "Match", "Matched by you" | "Split row", "Join with a row", "Aligned by", section "Alignment", "Joined by you" | Q7, `CONTEXT.md` |
| 04 | `stale_revision` notice "This row changed in another place. Examine it, then set your Merge Choice again." | `shared.stale` toast only | shared rule |
| 07 | stale toast "The session changed in a different place. PBIBrain loaded the new state. Do the action again." | `shared.stale` | shared rule |
| 04 | proposal card `brand-line` border on `brand-soft` | ticket 06 card: `line-strong` border on `surface-2` | Q13, orchestrator note of ticket 04 |
| 06 | "Keep from <source>" | "Take from <source>" | Q13, ticket 03 and 04 wording |
| 02 | remove-source confirm "Merge Choices that use Sales B stay in the session, but they have no source." | "<n> Merge Choices take from <source>. They stay, but the plan is not valid until you change them." | Q10 |
| 04 | blocking and warning counts "<N> blocking item(s)" | singular and plural forms with no "(s)" | ux-writing: no "(s)" |
| 06 | Log empty value "None" | unchanged, now the rule for all tabs | Q13 |
| 04, 06, 07 | disabled opacity 0.55, 0.5, 0.45 | 0.5 for new parts (Button keeps 0.45) | Q13 |
| 06 | Plan and Impact both get the switch | Impact has the switch; Plan has the info line only (ticket 08 decision 15 is later and wins) | ticket 08 |

### 6. Backend change requests (added to the map list)

1. `backend/devcenter/contracts/phrases.json` (new): each phrase ID (compare properties, compare notes, impact reasons, edge phrases) with its STE text. A contract test checks: no em dash or en dash, no emoji, maximum 60 characters, each ID used by the engine is in the file. Reason: one owner of the phrase text (Q8).
2. `apply`, `format_only_apply`, `undo_apply` errors: `details.step` (section 13 step ID) and `details.check` for the guard (`scope`, `canonical`, `tree_compare`, `pbir`, `policy`, `approval`, `write`, `rescan`). Reason: the result panel gives one plain sentence for each failure; section 12 has no guard codes (Q9).
3. JS API `source_remove`: keep the Merge Choices that take from the removed source. Add one blocking plan item for each (kind `choice_source_removed`). The reply gives the count. Reason: the confirm dialog text and the block list (Q10).
4. JS API `naming_rule_edit`: refuse a rule with the same object type, scope and check kind with `action_not_allowed` and `details.existing_rule_id`. Reason: the "Same rule exists" error of ticket 07 (Q11).

### 7. UI build items for ticket 11

- U-fix-1 (old and new screens): Button destructive variant uses `--bad-ink` and `--bad-strong`. Add the destructive-outline and status variants and the `loading` prop. Test: CI contrast test pair `--bad-ink` on `bad` and on `--bad-strong` in both themes; e2e axe on an old screen that has a destructive button.
- U-fix-2 (old and new screens): Tabs keep each panel in the DOM (`forceMount`, `hidden`). Test: e2e axe on Graph has no `aria-valid-attr-value` violation.
- U-tokens: add section 2 tokens to `theme.css`, the layout block to `devcenter.css`, and the new pairs to `tests/test_theme_contrast.py`.
- U-parts: build the new parts of section 1.3 with a specimen route (dev mode only) that renders each part in each state, for the kit release check.
- Later task (not version 1 Development Center): Graph `nested-interactive` and the Inspector light type chip (4.15:1) of ticket 01.

### 8. Measurements (2026-10-31, Chrome 156.0.8078.49, playwright 1.63.0, axe-core 4.10.2, kit 3.0.0)

Specimen `prototypes/09/index.html`: all new and changed parts of section 1 in their static states (default, disabled, loading, error, selected, open), with real hover and focus from the gates. Gates through the `gate.mjs` wrapper of the orchestrator note, with `DS_REQUIRE_BROWSER=1`.

| Gate | Light | Dark |
|---|---|---|
| `verify_states` (default, hover, focus) | 177 element-states, OK | 177 element-states, OK |
| `axe_audit` | 0 violations | 0 violations |
| `measure_render` | 215 text elements, all AA | 215 text elements, all AA |
| `verify_target_size` (414 and 1280 px) | 138 targets, OK | 138 targets, OK |
| `slop_tells --strict` | LOW only: near-same neutrals `surface-3` and `surface-hover` (existing tokens, ticket 01 fact) | LOW only: the same pair |
| `verify_responsive` (280 to 951 px) | OK, no overflow | (gate runs once) |
| `check_no_emoji` (folder) | OK: no emoji, no em or en dash | |
| `lint_native_select` | OK | |
| `lint_intent` | OK: 8 intent-bearing controls | |
| `lint_hardcodes` | `tokens.css` OK; `index.html` FAIL, 79 px values in the specimen CSS (prototype only; the build uses the layout tokens of section 2.2) | |
| Token contrast (`token_contrast.py`, 61 pairs) | 1 FAIL: the existing destructive Button in dark (2.61:1), fixed by U-fix-1; all new pairs pass | |
| Click test (`shots.mjs`) | checkbox toggles, switch toggles, radio selects, segmented button presses; page overflow 0 px at 1440 | the same |

Fixes that the gates and the screenshots found: (a) the tab row and segmented groups overflowed at 280 and 320 px: the tab row now scrolls in its own row and the segmented groups wrap (ticket 02 rule). (b) The screenshot showed no check mark in the checked box: the svg was `display: none`; now the paths toggle. (c) The disabled checkbox showed the native box (the disabled opacity rule overrode `opacity: 0`); now only the drawn box fades. Screenshots: `prototypes/09/shots/specimen-<theme>-<1440|1024>.png` and `checkbox-<theme>.png` (the repo `.gitignore` excludes `*.png`; run `shots.mjs` from the kit folder to make them again). Examined by eye: both themes at 1440 and 1024.

UNMEASURED, with reason:
- Real Radix focus trap, focus return, Select and Combobox keyboard, Tooltip timing: the specimen is static markup. A9, A10 and A6 run in the UI build e2e and with `verify_focustrap`.
- Screen reader output (A12): needs NVDA and Narrator on the built app.
- Live region timing (A11) and reduced motion (A15) on the real app: e2e in the UI build.
- The "Removed" hatch title (see section 2.4).

### 9. Inputs for ticket 11

- Put U-fix-1, U-fix-2, U-tokens and U-parts first in the UI build order. U-fix-1 and U-fix-2 change old screens, so run the existing e2e suite after them.
- The copy catalog of section 3 becomes `frontend/src/devcenter/copy.js` (keys as given). Unit test: each key has text; no em dash, en dash, emoji or ellipsis character.
- The a11y rules of section 4 become e2e specs (one spec file for each tab plus `devcenter-a11y.spec.js` for A1, A7, A11, A15, A18, A21).
- The four backend change requests of section 6 block: the result panel failure text (2), the remove-source dialog (3), the rule editor duplicate error (4), and the phrase display (1, until then the UI shows the backend `text` as it is).
