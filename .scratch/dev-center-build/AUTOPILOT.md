# Autopilot: build all remaining Dev Center tickets (Antigravity)

You are the build lead. Work with no user input until no ticket is ready. Do not ask questions; decide and write down the decision in the log.

Build worktree (run all `ag.py` commands here):
`C:/Users/Daniel/Desktop/PBIBrain/.claude/worktrees/dev-center-build-6abbf2`
Helper: `python .scratch/dev-center-build/ag.py <next|start|info|gates|merge|block> [N]`
Log: append one line for each event to `.scratch/dev-center-build/autopilot-log.md` (time, ticket, event).

Models: use NO Claude model. Start each subagent with `Model: "pro"`. Use `"flash"` only for small mechanical tasks. Never use `inherit`.

## Resume first

Read `autopilot-log.md`, `board.md`, and `python ag.py info N` for each ticket in state `running`, `review` or `rework`.
A ticket that already has commits on its branch is not started again. Continue it from where the log stops.
Ticket 10 already has its code in commit `f977b67`. Go directly to gates.

## Loop

Repeat until `ag.py next` prints nothing:

1. `ag.py next`. Take the ready tickets. Skip `deferred` tickets. You can run at most 2 tickets in parallel, each one in its own subagent.
2. `ag.py start N`. This makes the worktree `C:/Users/Daniel/Desktop/PBIBrain-wt/dc-N` and sets it up. Skip this step if the worktree exists.
3. **Developer**: start a `self` subagent with the DEV prompt (below). Wait for its reply. Keep its conversation ID for fixes.
4. **Gates**: `ag.py gates N`. This takes up to 30 min; run it in the background and wait for the notification.
   On failure, send the failure text to the same developer subagent ("Fix each item, run the related tests, commit, and reply with the new SHA"), then run the gates again. After 2 failed fix rounds: `ag.py block N "<reason>"`, log it, and go to the next ticket.
5. **Review**: start a NEW `self` subagent with the REVIEW prompt. It must not be the developer.
   On FAIL: send the findings to the developer subagent, run the gates again, then review again with a new reviewer and include the earlier findings. After 3 FAIL reviews: `ag.py block N`.
6. **Merge**: first, append the developer's `Learning:` lines to `.scratch/dev-center-build/learnings-inbox.md` under `## Ticket N`. Then run `ag.py merge N`.
   If the merge stops on a conflict that the known rules cannot resolve, resolve it in the build worktree. Keep the intent of both sides. Then run `git add` for those files, `git commit --no-edit`, and `ag.py gates N`.
7. Log `N done <commit>` and continue the loop.

At the end, write a summary at the end of the log: done, blocked (with the reasons), and the test totals.

## Hard rules

- Never push. Never open a PR. Never change `orchestrate.py`, `WORKER.md` or `REVIEWER.md`.
- Never commit `.claude/`, `.cursor/`, `.gemini/`, `.mcp.json`, `AGENTS.md`, `GEMINI.md` or `.trail/` (except `.trail/learnings/`).
- A blocked ticket does not stop the run. Continue with the other ready tickets.
- On a usage or rate limit, log it and stop cleanly. The next run continues from the log.

## DEV prompt (replace N, STEP, FILE)

You are the developer of build ticket N (STEP) of the PBIBrain Development Center.
Your worktree is `C:/Users/Daniel/Desktop/PBIBrain-wt/dc-N`. Work and run all commands only there. node_modules and the TOM bridge are set up, so do not set them up again. Set `LBUG_C_API_LIB_PATH=C:/Users/Daniel/Desktop/PBIBrain/runtime/native/lbug_shared.dll` in each shell that runs Python tests.
Read `.scratch/dev-center-build/WORKER.md` and `.scratch/dev-center-build/issues/FILE`. Read only the design sections that the ticket names. Where WORKER.md says `graft`, use `trail` (`trail ask`, `trail grep`, `trail callers`, `trail skeleton`).
If `git status` or `git log <base>..HEAD` shows earlier work, continue it. Do not start again.
Run only your own test modules. Do not run the full Python suite or the full e2e suite; the lead runs all gates after you finish. Run the kit gates at most once for each screen and theme.
Do not commit `.claude/`, `.cursor/`, `.gemini/`, `.mcp.json`, `AGENTS.md`, `GEMINI.md`, or `.trail/`. Stage files by name, not with `git add -A`.
When done: commit on this branch (no push), then reply in at most 8 lines: commit SHA, tests added, open items, and a line "Learning: <fact> because <reason>" for each non-obvious cause or trap.

## REVIEW prompt (replace N, STEP, FILE, BASE)

You are an independent reviewer of build ticket N (STEP) of the PBIBrain Development Center. Do not change code or commit.
Worktree: `C:/Users/Daniel/Desktop/PBIBrain-wt/dc-N`. Read `.scratch/dev-center-build/REVIEWER.md`, the ticket `.scratch/dev-center-build/issues/FILE`, and only the design sections that it names.
The diff: `git diff BASE...HEAD` in that worktree.
The lead already ran all gates on this commit, and they passed: full Python suite, npm test, the build, the changed e2e specs 3 times each, the full e2e suite, and the rule scan. Do not run the full suites again. Run a single test only to prove a finding.
Check: each acceptance test of the ticket has an automated test that checks the stated behavior; ADR 0003; contracts and `revision`; correctness bugs that the tests miss; agreement with the schemas in `backend/devcenter/contracts/`.
(Add here the earlier findings on a second or third review.)
Reply: first line PASS or FAIL. On FAIL, a numbered list: file and line, the problem, the required fix. Only blocking findings. At most 3 lines of notes.
