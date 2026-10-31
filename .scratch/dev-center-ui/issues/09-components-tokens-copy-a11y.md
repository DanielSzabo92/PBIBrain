# Which new components, tokens, copy, and a11y rules does the Development Center UI need?

Type: grilling
Status: open
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
