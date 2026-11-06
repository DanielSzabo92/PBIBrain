# 26: U12 release checks

Status: open. Lane: ui. Design step: U12 (docs/DEV_CENTER_UI_DESIGN.md section 13).

Depends on (tickets): [02](02-u0-test-harness.md), [05](05-u1-shared-parts.md), [06](06-u2-data-layer.md), [10](10-u3-shell-session-list.md), [12](12-u4-compare-grid.md), [13](13-u5-naming-rules-ui.md), [14](14-u11-cloud-ui.md), [18](18-u7-plan-view.md), [19](19-u6-row-detail.md), [22](22-u8-impact-ui.md), [24](24-u9-agent-log-ui.md), [25](25-u10-apply-ui.md), [07](07-s3-alignment-compare.md), [11](11-s5-change-plan.md), [15](15-s6-impact-data.md), [23](23-s9-local-apply.md).

The goal, the code areas, and the acceptance tests are the design text below. Each acceptance test must be an automated test, except the items that the design marks as manual.

## Lead notes

HITL items: the screen reader pass with NVDA and Narrator needs a person; the worker records the automated part and lists the SR pass as open. The budget check at 1 times runs on this PC.

### Design text: U12. Release checks

- Goal: the build meets this document on real engine data.
- Code areas: `tools/record_devcenter_ui_fixtures.py`, `tests/fixtures/devcenter_ui/`, `frontend/e2e/devcenter-a11y.spec.js`.
- Depends on: U0 to U11; S3, S5, S6, S9 (merge lab engine output).
- Acceptance tests:
  - Recorded `default` and `large-5000-rows` fixtures from the merge lab replace the hand files and pass the contract test.
  - A1 to A24 pass on each screen in both themes (`devcenter-a11y.spec.js` holds A1, A7, A11, A15, A18, A21, A22, A23).
  - SR pass with NVDA and Narrator on Compare, row detail, Impact graph and wireframe, Apply dialog; findings recorded.
  - Kit full sweep (`verify_states`, `verify_target_size`, `slop_tells --strict`, `verify_focustrap`, `verify_keyboard`, `lint_hardcodes`, `lint_intent`) on snapshots of each screen; results recorded.
  - Budgets P1 to P7 at 1 times on a development PC, including the jump scroll in the real app.
  - Each UNMEASURED item of section 12 is measured or listed with its reason.

## Build record

Branch `dc/26-u12-release-checks` (base `dc/25-u10-apply-ui`). Linux cloud machine.

What I built:
- `frontend/e2e/devcenter-a11y.spec.js` (33 tests). Screens and states: the session list, the empty session list, Compare, Compare large-5000-rows, row detail, the Impact table, graph, and wireframe, Plan, the invalid Plan, the Apply dialog, the Apply result, Agent, Sources, and Log. On each screen the spec checks A1 (axe in the dark and the light theme), A18 (no page overflow at 1280 x 900), A11 (one polite toast region), A7 (a Tab walk where each focused element has a 2 px ring and is the top element at its center), and A15 (no element in a running transition or animation). It also has an A23 test that uses the app toast with a fake clock (8 s, hover, close), and A22 tests (the graph zoom buttons work, Tab reaches each graph node, and the grid scrolls with the keys and with the wheel). The wheel test also checks P4: the grid box height is less than the viewport height, and the DOM has 80 rows or fewer.
- `tools/record_devcenter_ui_fixtures.py`. It copies the merge lab to a temporary project and makes a session through the JS API. Then it records the GET reads and writes them in the file shape of the fake server. When a read fails, or when the compare has no rows, it writes no file and exits with 2.
- `tests/test_devcenter_ui_record.py` (5 tests). A round trip through the fake server gives equal replies. A failed read goes to the missing list. Without the engine, the tool writes no file. The merge lab session reads pass their contracts. The large scenario stays generated in memory.
- I found and fixed 3 defects with the sweep:
  1. `compare.css`: `.dc-compare-area` had `flex: 1` in a column box with no fixed height. Thus the 5000-row grid became 144,034 px high. The grid did not scroll, the page scrolled, and the rows after about 20 stayed empty. The fix is `flex: none`.
  2. `app.css`: after a page scroll, the sticky top bar hid the focused toolbar controls (A7, WCAG 2.4.11). The fix is `html { scroll-padding-top: 64px }`.
  3. `screens.css`: the Plan step buttons used an undefined `--focus` token, so they had no focus ring. The fix uses `--brand`.

Tests (each run one time):
- `python -m unittest tests.test_devcenter_ui_record tests.test_devcenter_ui_contract tests.test_devcenter_ui_server`: 48 OK.
- `npm test`: 161 pass. `npm run build`: OK.
- `npx playwright test e2e/devcenter-a11y.spec.js`: 33 pass. The related specs `devcenter-compare` and `devcenter-row` also ran: 45 pass. `devcenter-plan.spec.js` "axe has zero violations" failed. This test also fails on the base branch (ticket 25 note). The test changes the theme through localStorage and a reload. Thus the theme labels in the test are wrong, and axe reads the colors while a transition runs. I did not change it, because it is a test of another area.

Not run, because they need Windows:
- The real recording: run `python -m tools.record_devcenter_ui_fixtures` on the PC with the TOM bridge, and then run the contract test. On Linux, `display-folders` gives `model_unreadable`, and the compare is empty. The "recorded fixtures replace the hand files" acceptance test stays open.
- Budgets P1 to P7 at 1 times, which includes the jump scroll in the real app. Run them on the development PC.

Open:
- Kit gates (the full sweep: `verify_states`, `verify_target_size`, `slop_tells --strict`, `verify_focustrap`, `verify_keyboard`, `lint_hardcodes`, `lint_intent`). The kit is not on this machine.
- The SR pass with NVDA and Narrator is a HITL item, and the 2026-11-01 scope cut removed it.
- A21 (200% zoom) is a scope cut, so it has no test.
- Section 12 UNMEASURED items:
  - Focus trap: the dialog specs of U1 to U10 measure it.
  - Live region and reduced motion: this spec measures them (A11, A15).
  - Screen reader output: scope cut.
  - Struck title on the hatch: open (a manual sample on a screenshot).
  - Copy against real MSAL, XMLA, and Fabric errors: cloud UI is out of scope.
- Possible contract gap (not fixed): the fake server diff reply has `target`/`source` text, but S2 `compare-row-diff.reply.json` has `reference_text`/`source_text`. The recorder maps the S2 names to the fake names. Do a check of the UI against the real reply on Windows.

Review: reviewer 1 (sonnet) PASS, no blocking findings. Its notes: the A7 "not hidden" check also passes when an ancestor covers the element, and the recorder reads impact page 1 two times.

Learning: a `flex: 1` item in a column flex box with no fixed height ignores its own `height`, because the flex basis takes the content height. The fake data had only 4 rows, so the 5000-row scenario was the only state that showed the defect.
Learning: an undefined CSS custom property in `outline` removes the focus ring with no warning, because the declaration becomes invalid when the browser computes the value. A computed-style ring check finds this, and axe does not.
Learning: set the theme at run time and then wait for `document.getAnimations()` to end before you run axe, because the color transitions make axe read colors between the two themes.
