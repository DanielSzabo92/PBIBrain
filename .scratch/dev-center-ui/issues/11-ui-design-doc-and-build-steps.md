# What is in the UI design document, and what are the UI build steps?

Type: grilling
Status: resolved
Blocked by: 01, 02, 03, 04, 05, 06, 07, 08, 09, 10

## Question

Write `docs/DEV_CENTER_UI_DESIGN.md` from the decisions of tickets 01 to 10. Define the UI build steps (U0, U1, ...), their order against the backend build steps S0 to S11, and the acceptance tests of each step.

## Context

- Destination (map): screens, flows, layout, components with the 8 states, copy, a11y contract, and UI build steps with unit, contract (section 14 JSON Schemas), and Playwright e2e tests. Version 1 only. Complete enough to split into UI build tickets.
- Format model: the technical design `docs/DEV_CENTER_TECHNICAL_DESIGN.md` (one home ticket for each decision; section 16 build step shape: goal, code areas, depends on, acceptance tests).
- Backend lanes (section 16): S3 and S4 after S2; S5 and S6 after S3; S10 after S6; S11 after S2. Each U-step names the S-steps whose schemas and endpoints it needs.
- Fog on the map to settle here: shortcut map, UI performance budgets, U-step order.
- Run `design-review` on the full design (6 dimensions, Nielsen heuristics). Put the findings table in the answer and fix the document before close.
- Render gates: each contrast, a11y, and layout claim in the document is measured (ticket 01 setup) or marked UNMEASURED.
- Skills: `design-doctrine`, `design-review`.

## Done when

`docs/DEV_CENTER_UI_DESIGN.md` exists and the orchestrator accepts it. Each U-step has a goal, code areas, dependencies (U and S), and acceptance tests. The map fog is empty or ruled out. The design review has no open high-severity finding.

## Answer

Resolved on 2026-10-31. The orchestrator accepted all 6 recommendations of round 1 (one round), with one change to Q6: there are no pull requests, so each build worker records the kit gate results in its build ticket file and its commit message.

### Output

- `docs/DEV_CENTER_UI_DESIGN.md` (new): the UI baseline for version 1. Sections: scope and design direction, navigation, layout and responsive rule, screens, flows, components and the 8 states, tokens, copy, a11y contract (A1 to A24), data layer, performance budgets, measurement status, UI build steps U0 to U12, out of scope, open risks, home tickets. The technical design is the format model: the document gives the decision, and tickets 01 to 10 give the reasons, prototypes, and full measurements.
- `docs/DEV_CENTER_TECHNICAL_DESIGN.md` (add only, no line removed): new section 14.4 "UI change requests (accepted 2026-10-31)" with UC1 to UC34 (the map list, in order), each with its owner S-step. One sentence in the section 16 intro. One acceptance test for each UC in its owner step: S2 (UC1, UC2, UC4, UC27), S3 (UC20, UC21, UC23 to UC26, UC31), S4 (UC16, UC18, UC19, UC34), S5 (UC3, UC22, UC33), S6 (UC28 to UC31), S9 (UC5 to UC7, UC32), S10 (UC8 to UC12), S11 (UC13 to UC15, UC17).

### Decisions of round 1

1. U-step list and order: U0 Test harness and CI; U1 Shared fixes, tokens, parts; U2 Data layer and copy; U3 Shell, session list, create, work area frame, Sources and Target (S2); U4 Compare grid (S3); U5 Naming rules (S4); U6 Row detail and Merge Choice (S3, S4, S5); U7 Plan view (S5); U8 Impact views and removal policy dialog (S6); U9 Agent and Log (S10); U10 Apply, Undo, format only, change report (S9); U11 Cloud sources and Pull to local (S11); U12 Release checks. UI lanes: U1 and U2 after U0; U4, U5, U7, U11 in parallel after U3.
2. Owner S-step for each of the 34 backend change requests (technical design 14.4).
3. Budgets P1 to P7 (design doc section 11). The ticket 03 value (300 ms) replaces the ticket 10 target (1.5 s). CI uses the median of 5 runs and fails at 2 times the budget; U12 checks 1 times on a development PC.
4. Shortcut map: ticket 09 section 4.3 is final. "/" acts only outside text fields and dialogs. No tab-switch keys and no shortcut help dialog. `aria-keyshortcuts` and the key in the tooltip.
5. Copy: the document gives the rules, key families, and shared texts. The full catalog stays in ticket 09 section 3 until U2 moves it into `frontend/src/devcenter/copy.js`, which is then the source of truth.
6. Kit gates during the build: each U-step that adds a screen runs `verify_states` (light and `--dark`), `verify_target_size`, `slop_tells --strict`, and `verify_focustrap` on a snapshot, through the kit `gate.mjs` wrapper with `DS_REQUIRE_BROWSER=1` (Windows: fake `argv[1]`). The build worker records the results in its build ticket file and commit message. U12 runs the full sweep.

### Map fog

- Shortcut map: settled (design doc 9.3).
- UI performance budgets: settled (design doc 11).
- U-step order: settled (design doc 13).

The map list "Not yet specified" is empty.

### Design review (`ux-ui-agent-skills:design-review`)

Scope: the full design document, with the prototypes of tickets 02 to 09 as the visual evidence. Screens examined by eye: Compare grid with pane (dark 1440), Plan (light 1024). Users: expert BI developers on a Windows desktop app, window 1024 x 640 to 1440 x 900.

Scores (after the fixes below):

| Dimension | Weight | Score | Note |
|---|---|---|---|
| Visual hierarchy | 20% | 8 | Each screen names one leading element. The Plan strip leads with 18 px status text under a 28 px h1. |
| Consistency | 20% | 8 | One token set, one part library, one copy catalog. The ticket 08 prototype still has an underline tab; the document sets a fill. |
| Accessibility | 20% | 8 | 24 rules with one test each. Screen reader output and focus traps are UNMEASURED until U1 and U12. 1.4.10 is a stated limit. |
| Usability | 20% | 8 | Clear states, confirm rules, undo for Apply. Reject of a proposal cannot be undone. |
| Responsiveness | 10% | 7 | Desktop only by decision (1024 to 1440, no overflow in 1,464 prototype runs). No reflow to 320 px. |
| Performance | 10% | 7 | Budgets P1 to P7 are set. The prototype failed the jump scroll; the light-row rule is not yet proven in the real app. |

Overall: (8 + 8 + 8 + 8) x 0.2 + (7 + 7) x 0.1 = 7.8 of 10. Before the fixes, accessibility was 7 (overall 7.6).

Findings:

| # | Severity | Category | Location | Finding | Recommendation and status | Heuristic |
|---|---|---|---|---|---|---|
| 1 | Critical | A11y | 9.3 shortcut map | "/" is a single-character key that acts outside the focused part. WCAG 2.1.4 (Level A) needs a way to turn it off or remap it. | FIXED: Settings switch "Use the / key to go to search" (stored in `localStorage`); rule A24 with an e2e test; U3 test. D and M act only with focus in the grid (2.1.4 exception). | H7 |
| 2 | Major | Usability, data | 4.8 Remove source | The ticket 09 dialog text needs the count of Merge Choices that take from the source, but no read gives it before the call. | FIXED: the dialog text has no count; the toast gives the count from the `source_remove` reply (UC33). | H9 |
| 3 | Major | A11y | Toast part | No time rule for toasts. A short toast can go away before a user reads it (WCAG 2.2.1). | FIXED: rule A23: at least 8 s, stays on hover and focus, close button, never the only copy of a needed action. | H1 |
| 4 | Major | A11y, responsive | A18 and A21 | A21 (200% zoom = 720 CSS px) conflicted with the 1024 px minimum of A18, and the document claimed WCAG 2.2 AA with no word on 1.4.10. | FIXED: A21 tests 1.4.4 and permits page scroll at 200%; stated limit for 1.4.10 in 9.1; risk UR7. | H4 |
| 5 | Major | A11y | Graph view | The contract had no rule for WCAG 2.5.7 (dragging movements). Graph pan can need a drag. | FIXED: rule A22: zoom in, zoom out, and fit buttons, keys, and Tab to each node. | H7 |
| 6 | Minor | Usability | Long calls | Long calls disable each change control with no visible reason on the disabled controls. | FIXED: a header status line during a long call (section 10). | H1 |
| 7 | Minor | Consistency | Ticket 08 prototype | The Plan prototype shows the active tab as an underline (a one-sided border). | FIXED in the document: the U1 acceptance test sets the fill; the document wins over the prototype. | H4 |
| 8 | Minor | A11y | Wireframe "Removed" | The struck title on the hatch has no contrast value. | OPEN, Minor: U12 measures it (section 12). | none |
| 9 | Minor | A11y | Compare grid | Screen reader output of the virtual grid (5,000 rows) is not known. | OPEN, Minor: U12 SR pass with NVDA and Narrator. | H1 |
| 10 | Enhancement | Usability | Agent tab | A rejected proposal cannot come back; only a new agent proposal or a manual choice. | Backlog: an "Undo" action in the reject toast needs a backend call (not in version 1). | H3 |
| 11 | Enhancement | Efficiency | Session list | No search or filter for many sessions. | Backlog. | H7 |
| 12 | Enhancement | Help | Whole work area | No shortcut help dialog in version 1 (Q4). | Backlog; tooltips with `aria-keyshortcuts` cover version 1. | H10 |
| 13 | Enhancement | Usability | Row detail | Immediate save has no undo button; the Log keeps the old value. | Backlog. | H3 |

No Critical or Major finding is open.

Anti-slop check (`taste/design-taste.md` banned defaults) on the document rules: no one-sided borders, one accent, flat surfaces with shadows only on overlays, no equal-card grids, icon plus word for status, no em dash or emoji. The prototypes passed `slop_tells --strict` with LOW and MED tells only (theme neutrals, one shadow), as tickets 02 to 09 record.

### Measurements for this ticket

- Kit `check_no_emoji.py docs/DEV_CENTER_UI_DESIGN.md`: OK (no emoji, no em or en dash).
- No new render gate ran: this ticket writes documents only. Each value in the design document comes from tickets 01 to 09, or has the mark UNMEASURED (design doc section 12).
