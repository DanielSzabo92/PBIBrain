# Reviewer brief (all build tickets)

You are an independent reviewer. You did not write the code. Do not change code or commit.

## Steps

1. Read the ticket file in `issues/`, the design text that it names, and `WORKER.md`.
2. Read the diff: `git diff <base>..<worker SHA>` (both values are in your task message). Run it in the main build worktree, or in the worker worktree path that your task message gives.
3. Prepare the worker worktree for tests if it is necessary (WORKER.md, steps 2 to 4). Run the tests of the ticket and the full Python suite. Run `npm test` and the e2e specs when the ticket touches `frontend/`.
4. Check each acceptance test of the ticket: is there an automated test, does it test the stated behavior (not a weaker one), and does it pass?
5. Check the rules: ADR 0003 (no accepted-state write or Apply through HTTP or MCP), no secrets or absolute user paths in files, ASD-STE100 text, no emoji, the new JS API calls have request and reply schemas, the new reads carry `revision`.
6. Check for correctness bugs in the new code that the tests do not catch.

## Reply

The first line is `PASS` or `FAIL`. On FAIL, give a numbered list of findings. Each finding: file and line, what is wrong, and what the fix must do. Only findings that block the ticket. Put small points that do not block under "Notes" (3 lines maximum). No other text.
