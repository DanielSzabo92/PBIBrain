## Ticket 10
- Learning: a Radix dialog that the app opens from its own state needs DialogTrigger, because without it focus does not go back to the button when the dialog closes, and verify_focustrap fails.
- Learning: give the gate runner a long time limit, because one verify_states run on a dark snapshot can take more than 3 minutes on Windows and then stops with no result.
- Learning: Toast animations must not animate opacity from zero because axe accessibility contrast checks sample elements during the transition.
- Learning: The test web server serves `frontend/dist` directly because it checks production bundle behavior, which requires a rebuild when CSS changes.

## Ticket 13
- Learning: Align mock server fixtures strictly with S4 schemas (rule_id and support count/total) before implementing UI components to prevent contract validation mismatches.
