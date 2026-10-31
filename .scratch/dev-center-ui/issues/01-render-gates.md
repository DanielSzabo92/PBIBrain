# Can the design gates run here, and what do they say about the current theme?

Type: task (AFK)
Status: open
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
