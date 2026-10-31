# Worker brief (all build tickets)

Read this file, then your ticket in `issues/`. The ticket wins where it is more specific.

## Start

1. Find the base commit in your task message. Make sure that your HEAD contains it: `git merge-base --is-ancestor <base> HEAD`. If the command fails, run `git reset --hard <base>` (your worktree is new, so you lose nothing).
2. Run `npm ci --no-audit --no-fund` in `frontend/` if `frontend/node_modules` does not exist. A new worktree has no `node_modules`, and the Python suite then fails on `vite`.
3. Build the TOM bridge: `dotnet build -c Release backend/adapters/tabular_metadata/dotnet/TabularMetadata.csproj`. Without the build, many tests fail with "Build the trusted TOM bridge before model verification".
4. Set `LBUG_C_API_LIB_PATH=C:/Users/Daniel/Desktop/PBIBrain/runtime/native/lbug_shared.dll` in each shell that runs Python tests. The DLL is not in git, so a new worktree does not have it.
5. Any failure of the full suite is yours. The board has the current test totals.
6. Read the design text that your ticket names. Read `CONTEXT.md` for the words. Read `.trail/learnings/` that touch your code areas.
7. Use `graft ask "<question>" --source`, `graft grep`, `graft callers`, and `graft skeleton` before you open whole source files.

## Rules

- Write the code and the automated tests of your ticket. The tests must pass.
- All text in ASD-STE100: comments, docstrings, messages, UI copy, commit message. No emoji. No em dash or en dash in UI copy and phrases.
- ADR 0003: the agent (MCP) and the local HTTP API never get an accepted-state write or an Apply. These exist only in the pywebview JS API (`backend/desktop/host.py` and the `backend/devcenter/` JS API modules).
- Put no tokens, secrets, absolute user paths, or e-mail addresses in files.
- Match the style of the code near your change. The repo uses `unittest` and `jsonschema` (no pytest, no pydantic).
- Shared files (`backend/api/app.py`, `backend/desktop/host.py`, `backend/mcp_server.py`, `frontend/src/devcenter/jsapi-methods.json`, `frontend/src/devcenter/invalidation.js`, `tests/devcenter_ui_server.py`): other workers change them at the same time. Keep your edits to these files small. Put your logic in your own module and register it with one line where the extension point exists.
- Each new JS API call gets a request and a reply JSON Schema in `backend/devcenter/contracts/` (UC4). Each new read reply carries `revision` (UC2).
- Do not change tests of other areas to make them pass. If an old test fails because of a correct change, say so in your report.

## Tests

- Python: `python -m unittest discover -s tests` (full suite, about 30 s). Run your own test module first.
- Frontend unit: `npm test` in `frontend/`.
- Frontend build: `npm run build` in `frontend/`.
- e2e: `npx playwright test <spec>` in `frontend/` (the config starts the servers).
- .NET bridge: `dotnet build` and the existing native tests (`tests/test_native_cli_contract.py`). The .NET 8 SDK is installed.

## Kit gates (U-steps with a screen)

Kit: `C:/Users/Daniel/.claude/plugins/local/ux-ui-agent-skills/`. Snapshots: copy the method of `.scratch/dev-center-ui/gates/snap.mjs` (inline CSS). On Windows, `gate.mjs` does nothing unless `process.argv[1]` is a fake path. Run each gate like this (PowerShell, from the repo root):

```
$env:DS_REQUIRE_BROWSER = "1"
node --input-type=module -e "process.argv = [process.argv[0], '/C:/Users/Daniel/.claude/plugins/local/ux-ui-agent-skills/scripts/gate.mjs', 'verify_states.mjs', '<snapshot.html>']; await import('file:///C:/Users/Daniel/.claude/plugins/local/ux-ui-agent-skills/scripts/gate.mjs');"
```

Gates: `verify_states.mjs` (light, and dark with `--dark`), `verify_target_size.mjs`, `slop_tells.mjs --strict`, `verify_focustrap.mjs`. SKIPPED is not a pass. Caution: `verify_states` drops the alpha of a hover background; use an opaque `-solid` tint token. Record each result in your ticket file under "Build record" and in the commit message.

## Finish

1. Add a "Build record" section at the end of your ticket file: what you built, the test commands, and the pass counts.
2. Run `git status --porcelain --ignored`. The repo `.gitignore` drops `*.pbip`, `*.pbir`, `*.png`, `*.dll`, and more. Add a negation for each test file that you need in git.
3. Commit on your worktree branch. Do not push. Do not open a pull request. End the commit message with:
   `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`
4. If you find a non-obvious cause or a setup trap, write it in your report under "Learning". The lead saves it.
5. Report in 10 lines or less: branch name, commit SHA, test totals, open items. No status talk.

## Rework

A reviewer can return FAIL with numbered findings. Fix each finding, run the tests again, commit, and report the new SHA and one line for each finding.
