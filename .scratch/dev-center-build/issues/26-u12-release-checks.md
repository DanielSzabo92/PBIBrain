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
