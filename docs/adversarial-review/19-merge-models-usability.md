# 19 · Merge models: capable, but dense with jargon and unexplained controls

**Severity:** P2 · **Criteria:** easy and obvious, self-explanatory UI, layout

Reviewed on the e2e fixture ("Sales and finance merge"); the real engine needs the desktop shell.

## Evidence

![Row detail](evidence/merge-row-detail.png)

- **The target column is hidden.** Opening a row's detail covers the model columns; "Combined mod…" is cut and the source columns — the thing being compared — are not visible at all at 1440 px.
- **Keep / Take / Skip** on every row with no legend. Keep what? Take from where? The answer is in the detail pane only.
- **Row detail** lists six radio options with helper sentences, two of them disabled with an explanation of why. The user reads ~70 words to make a three-way choice.
- **Seven tabs** (Compare, Impact, Plan, Agent, Sources, Naming rules, Log) plus a filter row, a chip row, a "Compare: Default | Strict" switch and a keyboard button: four bands of controls above four rows of data.
- Object names use DAX quoting (`'Sales'[Net Sales]`) while the rest of the app shows "Net Sales" with a table path.
- Large empty checkboxes (24 px squares) are the heaviest element in the grid.
- "Valid with 1 warning" is styled as a button in the warning colour; it is not clear that it is clickable or what it opens.
- The view header shows "Change project" here and "Scan sources" on every other view.
- When the server is busy the view shows "Loading the session" and three grey bars with no time-out (measured 23 s, see 04).
- The breadcrumb repeats the h1, the tab and the sidebar item ("Merge models › Sales and finance merge › Compare").

## Solution

1. **Detail as a bottom panel** (resizable, 40 % height) in the style of a diff tool, so the grid keeps all model columns. The panel shows target and source definitions side by side with the diff, and the choice as a segmented control above it.
2. **Direction arrows instead of jargon.** Per row a 3-way control with icons and tooltips: `●` keep target · `←` take from *Finance* (source name in the tooltip and in the column header it points to) · `–` decide later. The chosen cell in the grid is highlighted, so the row itself shows where the value comes from.
3. **Only offer valid choices.** Hide options that do not apply to the row type; put "Add as new name" and "Remove from target" in a `⋯` menu.
4. **A stepper for the process, tabs for tools.** Sources → Compare → Impact → Plan → Apply as a horizontal progress strip with counts and status glyphs (e.g. "Compare · 4 open"); Agent, Naming rules and Log move to a secondary toolbar on the right.
5. **One filter line:** search + `State ▾` `Type ▾` `Marks ▾` `Changed ▾` as compact chips; the "Default / Strict" mode goes into the State menu.
6. **Names as everywhere else:** type chip + "Net Sales" + grey "Sales" path.
7. Checkboxes 16 px, visible on hover/focus and when any row is selected.
8. Validity as a status chip with glyph (contract §9); click opens the list of findings.
9. Loading: skeleton of the grid; after 5 s say what is running and offer Cancel.
10. Drop the breadcrumb; keep the session name as the header title with a session switcher.

## Acceptance

- With a row's detail open at 1440 px, the target and at least two source columns remain visible.
- A first-time user can state what "take" will do for a row without opening anything (usability check with three people).
