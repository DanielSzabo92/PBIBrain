# Board: Development Center build, version 1

Build branch: `claude/dev-center-build-6abbf2` (the `dev-center-build` branch of the lead session). Base: `docs/dev-center-spec`.

Process for each ticket: one worker (Opus 5.5, medium, own worktree) writes the code and the tests. One new independent reviewer (Opus 5.5, medium) returns PASS or FAIL. On FAIL, the same worker fixes the findings and a new reviewer checks again. On PASS, the lead merges into the build branch, runs the full suite, and commits. No push. No pull request. Maximum 4 workers at a time.

Worker rules: [WORKER.md](WORKER.md). Reviewer rules: [REVIEWER.md](REVIEWER.md).

## Lanes and order

Backend lane (technical design section 16): S0, then S1 and S2 in parallel, then S3 and S4 in parallel, then S5, then S6, S7a, and S7b in parallel, then S8, S10, then S9.

Cloud lane: S11 after S2, in parallel with all others. S12 and S13 are version 1.1 (not in this build).

UI lane (UI design section 13): U0, then U1 and U2 in parallel, then U3 (needs S2), then U4, U5, U7, and U11 in parallel as their S-steps permit, then U6, U8, U9, U10, then U12.

## Tickets

| # | Step | Ticket | Depends on | State | Worker branch | Merge commit |
|---|---|---|---|---|---|---|
| 01 | S0 | [Foundations](issues/01-s0-foundations.md) | none | done | worktree-agent-a2f5d1541558f2a6d | 30df5e7, 3199fea |
| 02 | U0 | [Test harness and CI](issues/02-u0-test-harness.md) | none | done | worktree-agent-a4f92e8221c3c04c5 | 2522d6d |
| 03 | S1 | [Scanner coverage](issues/03-s1-scanner-coverage.md) | 01 | running | | |
| 04 | S2 | [Session store and local sources](issues/04-s2-session-store.md) | 01 | running | | |
| 05 | U1 | [Shared fixes, tokens, parts](issues/05-u1-shared-parts.md) | 02 | running | | |
| 06 | U2 | [Data layer and copy](issues/06-u2-data-layer.md) | 02 | running | | |
| 07 | S3 | [Alignment and compare](issues/07-s3-alignment-compare.md) | 03, 04 | open | | |
| 08 | S4 | [Naming rules](issues/08-s4-naming-rules.md) | 04 | open | | |
| 09 | S11 | [Cloud read (fakes)](issues/09-s11-cloud-read.md) | 04 | open | | |
| 10 | U3 | [Shell, session list, create flow](issues/10-u3-shell-session-list.md) | 05, 06, 04 | open | | |
| 11 | S5 | [Change Plan engine](issues/11-s5-change-plan.md) | 07, 08 | open | | |
| 12 | U4 | [Compare grid](issues/12-u4-compare-grid.md) | 10, 07 | open | | |
| 13 | U5 | [Naming rules UI](issues/13-u5-naming-rules-ui.md) | 10, 08 | open | | |
| 14 | U11 | [Cloud sources UI](issues/14-u11-cloud-ui.md) | 10, 09 | open | | |
| 15 | S6 | [Impact data](issues/15-s6-impact-data.md) | 07, 11 | open | | |
| 16 | S7a | [Model writer (bridge)](issues/16-s7a-model-writer.md) | 11 | open | | |
| 17 | S7b | [PBIR writer](issues/17-s7b-pbir-writer.md) | 11 | open | | |
| 18 | U7 | [Plan view](issues/18-u7-plan-view.md) | 10, 11 | open | | |
| 19 | U6 | [Row detail and Merge Choice](issues/19-u6-row-detail.md) | 12, 07, 08, 11 | open | | |
| 20 | S8 | [Guard for merge](issues/20-s8-guard-merge.md) | 16, 17 | open | | |
| 21 | S10 | [Agent MCP tools](issues/21-s10-agent-mcp-tools.md) | 15, 16 | open | | |
| 22 | U8 | [Impact views and removal policy](issues/22-u8-impact-ui.md) | 19, 15 | open | | |
| 23 | S9 | [Local apply](issues/23-s9-local-apply.md) | 15, 20 | open | | |
| 24 | U9 | [Agent and Log](issues/24-u9-agent-log-ui.md) | 19, 22, 21 | open | | |
| 25 | U10 | [Apply, Undo, format only, change report](issues/25-u10-apply-ui.md) | 18, 23 | open | | |
| 26 | U12 | [Release checks](issues/26-u12-release-checks.md) | all others | open | | |

States: open, running, review, rework, done.

## Not in version 1

- S12 Cloud model write and S13 Cloud report write: version 1.1 (technical design section 15.2).

## HITL items (need the user)

| ID | Item | Blocks |
|---|---|---|
| H1 | Task T1: register the Entra app (public client, WAM redirect, Power BI and Fabric scopes), then run the real-tenant checklist. Until then, cloud read uses fakes only. | Release of cloud read against a real tenant (risk R1, R2). Not the build. |
| H2 | Screen reader pass with NVDA and Narrator (U12). | Release sign-off of accessibility. Not the build. |

## Test totals

| After | Python tests | Failures | Frontend unit | e2e |
|---|---|---|---|---|
| Baseline (build start) | 302 | 1 (stale `test_mcp_adapter`) | not run | not run |
| 01 (S0) | 319 | 0 | not run | not run |
| 02 (U0) | 361 | 0 | 38 | 50 main, 7 guard (worker run) |
