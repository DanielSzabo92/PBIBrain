---
title: "Send the headless claude prompt through stdin on Windows, not as an argument"
author: Daniel
date: 2026-11-01
branch: claude/dev-center-build-6abbf2
cost: { minutes: 28, tokens: 436435 }
id: l-72a7265e
scope: repo
status: active
touches:
  - ".scratch/dev-center-build/orchestrate.py"
  - ".scratch/dev-center-build/board.md"
  - ".scratch/dev-center-build/issues/10-u3-shell-session-list.md"
  - ".scratch/dev-center-build/WORKER.md"
---

## Decided
The build orchestrator sends the `claude -p` prompt through stdin. On Windows, `shutil.which("claude")` gives `claude.CMD`, so `cmd.exe` runs it, and `cmd.exe` cuts the command line at the first newline. A multi-line prompt as an argument drops all the flags after it.

## Watch out
The symptoms do not point at the cause. The sessions ran in the default permission mode, so each Edit, Write, and Bash call needed approval and the session did no work. The reply was plain text, so `session_id` and the cost were empty. The session got only the first line of the task. A one-line probe works, so a probe must use a multi-line prompt.

In the code: `.scratch/dev-center-build/orchestrate.py`, function `claude()`: `subprocess.run(cmd, input=prompt, ...)`. The function now raises an error when the reply has no `session_id` or has `permission_denials`. The session transcript shows the mode: `"permissionMode":"default"` in `~/.claude/projects/<worktree>/<session>.jsonl`.
