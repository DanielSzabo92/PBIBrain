"""Antigravity helper: the deterministic parts of orchestrate.py, with no `claude -p` calls.

The model work (developer, reviewer) runs in Antigravity. This script does the rest.

Usage (from any folder):
    python .scratch/dev-center-build/ag.py next          # show the ready tickets
    python .scratch/dev-center-build/ag.py start 12      # make the worktree, set up, board = running
    python .scratch/dev-center-build/ag.py info 12       # show worktree, branch and base
    python .scratch/dev-center-build/ag.py gates 12      # run all gates (full suites); exit 1 on failure
    python .scratch/dev-center-build/ag.py merge 12      # merge into the build branch, gates, board = done
    python .scratch/dev-center-build/ag.py block 12 why  # board = blocked, reason in the state file
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import orchestrate as o  # noqa: E402


def _no_model(*_args, **_kwargs):
    raise RuntimeError("merge conflict that the known rules cannot resolve: resolve it by hand in the build worktree")


o.claude = _no_model   # this helper never starts a claude session


def _ticket(num: str) -> tuple[dict, dict]:
    state = o.load_state()
    return state, state["tickets"].setdefault(num, {})


def cmd_next() -> int:
    rows = o.board_rows()
    todo = [n for n in o.ready(rows, set()) if rows[n]["state"] != "blocked"]
    for n in todo:
        print(f"{n}  {rows[n]['step']:5} {rows[n]['state']:8} {rows[n]['title']}")
    return 0


def cmd_start(num: str) -> int:
    row = o.board_rows()[num]
    state, st = _ticket(num)
    base = o.sh(["git", "rev-parse", "HEAD"]).stdout.strip()
    branch = st.get("branch") or f"dc/{num}-{row['file'][3:-3]}"
    wt = Path(st.get("worktree") or o.WORKTREES / f"dc-{num}")
    if not wt.exists():
        o.sh(["git", "worktree", "add", "-b", branch, str(wt), base], check=True)
        st.update(branch=branch, worktree=str(wt), base=base)
    else:
        st.setdefault("worktree", str(wt))
        st.setdefault("base", o.sh(["git", "merge-base", "HEAD", o.BUILD_BRANCH], wt).stdout.strip())
        st.setdefault("branch", o.sh(["git", "branch", "--show-current"], wt).stdout.strip())
    o.save_state(state)
    o.set_board(num, "running", st["branch"])
    o.setup(wt)
    return cmd_info(num)


def cmd_info(num: str) -> int:
    _, st = _ticket(num)
    print(json.dumps({k: st.get(k) for k in ("worktree", "branch", "base", "blocked", "done")}, indent=2))
    return 0


def cmd_gates(num: str) -> int:
    _, st = _ticket(num)
    fails = o.gates(Path(st["worktree"]), st["base"])
    print("\n\n".join(fails) if fails else "GATES PASS")
    return 1 if fails else 0


def cmd_merge(num: str) -> int:
    row = o.board_rows()[num]
    state, st = _ticket(num)
    commit = o.merge(num, row, st["branch"])
    o.set_board(num, "done", st["branch"], commit)
    o.sh(["git", "add", str(o.BOARD), *([str(o.INBOX)] if o.INBOX.exists() else [])])
    o.sh(["git", "commit", "-m", f"Update the board after ticket {num}"])
    st["done"] = commit
    st.pop("blocked", None)
    o.save_state(state)
    print(f"{num}: done at {commit}")
    return 0


def cmd_block(num: str, *reason: str) -> int:
    state, st = _ticket(num)
    st["blocked"] = " ".join(reason)[:3000]
    o.save_state(state)
    o.set_board(num, "blocked")
    print(f"{num}: blocked")
    return 0


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if o.sh(["git", "branch", "--show-current"]).stdout.strip() != o.BUILD_BRANCH:
        print("The build worktree is not on the build branch.", file=sys.stderr)
        return 2
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 2
    cmd, rest = args[0], args[1:]
    handlers = {"next": cmd_next, "start": cmd_start, "info": cmd_info, "gates": cmd_gates, "merge": cmd_merge,
                "block": cmd_block}
    if cmd not in handlers:
        print(__doc__)
        return 2
    return handlers[cmd](*rest)


if __name__ == "__main__":
    raise SystemExit(main())
