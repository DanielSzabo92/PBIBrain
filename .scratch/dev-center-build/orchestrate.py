"""Run the Development Center build tickets with no lead session in the loop.

The script does all deterministic work itself: worktrees, setup, test gates, rule scans, merges, the
board, and the cost log. It calls `claude -p` only for the work that needs a model:

    developer  opus   medium  writes the code and the tests (fresh session for each ticket)
    fixer      opus   medium  the same developer session, resumed with the gate or review findings
    reviewer   sonnet medium  reads the ticket, the diff, and the gate results; returns PASS or FAIL
    resolver   sonnet low     only for a merge conflict that the known rules cannot resolve

Usage (from the build worktree root):
    python .scratch/dev-center-build/orchestrate.py            # run until done or blocked
    python .scratch/dev-center-build/orchestrate.py --dry-run  # show the ready tickets only
    python .scratch/dev-center-build/orchestrate.py --only 11  # run one ticket

State is in `orchestrator-state.json` next to this file, so a second run continues the first one.
A usage limit stops the run cleanly; run the script again after the reset.
"""
from __future__ import annotations

import argparse
import concurrent.futures as futures
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]                      # the build worktree
BOARD = HERE / "board.md"
STATE = HERE / "orchestrator-state.json"
COSTLOG = HERE / "orchestrator-cost.jsonl"
INBOX = HERE / "learnings-inbox.md"
WORKTREES = Path("C:/Users/Daniel/Desktop/PBIBrain-wt")   # outside .claude: headless sessions cannot write there
BUILD_BRANCH = "claude/dev-center-build-6abbf2"
LBUG = "C:/Users/Daniel/Desktop/PBIBrain/runtime/native/lbug_shared.dll"

ROLES = {
    "developer": ("opus", "medium"),
    "reviewer": ("sonnet", "medium"),
    "resolver": ("sonnet", "low"),
}
MAX_PARALLEL = 3
MAX_GATE_FIXES = 2
MAX_REVIEWS = 3             # the third review uses opus
TOOLS = [
    "Read", "Edit", "Write", "Grep", "Glob",
    "Bash(git:*)", "Bash(python:*)", "Bash(py:*)", "Bash(npm:*)", "Bash(npx:*)", "Bash(node:*)",
    "Bash(dotnet:*)", "Bash(ls:*)", "Bash(cat:*)", "Bash(grep:*)", "Bash(sed:*)", "Bash(head:*)",
    "Bash(tail:*)", "Bash(mkdir:*)", "Bash(cp:*)", "Bash(mv:*)", "Bash(rm:*)", "Bash(find:*)",
    "Bash(trail:*)", "Bash(graft:*)", "Bash(cd:*)", "Bash(export:*)", "Bash(echo:*)", "Bash(wc:*)",
    "Bash(sort:*)", "Bash(test:*)", "Bash(printf:*)",
]
REVIEW_TOOLS = ["Read", "Grep", "Glob", "Bash(git:*)", "Bash(python:*)", "Bash(npm:*)", "Bash(npx:*)",
                "Bash(grep:*)", "Bash(ls:*)", "Bash(cat:*)"]

LOCK = threading.Lock()
ENV = dict(os.environ, LBUG_C_API_LIB_PATH=LBUG, CI="1", PYTHONUTF8="1")


class UsageLimit(RuntimeError):
    """A stop for all new work: a usage limit, or a CLI that is not signed in."""


# ---------------------------------------------------------------- helpers

def sh(cmd: list[str] | str, cwd: Path = ROOT, timeout: int = 1800, check: bool = False) -> subprocess.CompletedProcess:
    if isinstance(cmd, list):
        cmd = [shutil.which(cmd[0]) or cmd[0], *cmd[1:]]   # npm and npx are .cmd files on Windows
    result = subprocess.run(cmd, cwd=cwd, env=ENV, capture_output=True, text=True, encoding="utf-8",
                            errors="replace", timeout=timeout, shell=isinstance(cmd, str))
    if check and result.returncode:
        raise RuntimeError(f"{cmd} failed: {result.stdout[-2000:]}{result.stderr[-2000:]}")
    return result


def tail(text: str, lines: int = 40) -> str:
    return "\n".join(text.strip().splitlines()[-lines:])


def log(msg: str) -> None:
    with LOCK:
        print(time.strftime("%H:%M:%S"), msg, flush=True)


def load_state() -> dict:
    return json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {"tickets": {}}


def save_state(state: dict) -> None:
    with LOCK:
        STATE.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8", newline="\n")


def claude(role: str, prompt: str, cwd: Path, *, ticket: str, resume: str | None = None,
           model: str | None = None) -> dict:
    exe = shutil.which("claude") or "claude"
    mdl, effort = ROLES[role]
    mdl = model or mdl
    tools = REVIEW_TOOLS if role == "reviewer" else TOOLS
    cmd = [exe, "-p", prompt, "--model", mdl, "--effort", effort, "--output-format", "json",
           "--permission-mode", "acceptEdits", "--allowedTools", *tools]
    if resume:
        cmd += ["--resume", resume]
    started = time.time()
    proc = subprocess.run(cmd, cwd=cwd, env=ENV, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=3 * 3600)
    out = proc.stdout.strip()
    data: dict = {"result": out}
    for candidate in (out, out[out.find("{"):] if "{" in out else "", out.splitlines()[-1] if out else ""):
        try:
            parsed = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(parsed, dict):
            data = parsed
            break
    text = str(data.get("result", "")) + proc.stderr
    with LOCK, COSTLOG.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps({"time": time.strftime("%Y-%m-%dT%H:%M:%S"), "ticket": ticket, "role": role,
                             "model": mdl, "seconds": round(time.time() - started),
                             "cost_usd": data.get("total_cost_usd"), "usage": data.get("usage"),
                             "turns": data.get("num_turns")}) + "\n")
    if re.search(r"Failed to authenticate|OAuth session expired|not logged in", text, re.I):
        raise UsageLimit("the claude CLI is not signed in: run `claude` once and sign in")
    if re.search(r"session limit|usage limit|rate_limit", text, re.I) and not data.get("session_id"):
        raise UsageLimit(tail(text, 3))
    if data.get("is_error") and re.search(r"limit", text, re.I):
        raise UsageLimit(tail(text, 3))
    return {"text": str(data.get("result", out)), "session_id": data.get("session_id")}


# ---------------------------------------------------------------- board

ROW = re.compile(r"^\| (\d\d) \| (\S+) \| \[([^\]]+)\]\(issues/([^)]+)\) \| ([^|]*) \| (\w+) \|([^|]*)\|([^|]*)\|$", re.M)


def board_rows() -> dict[str, dict]:
    rows = {}
    for m in ROW.finditer(BOARD.read_text(encoding="utf-8")):
        deps = [d.strip() for d in m.group(5).split(",") if d.strip().isdigit()]
        if "all others" in m.group(5):
            deps = ["*"]
        rows[m.group(1)] = {"step": m.group(2), "title": m.group(3), "file": m.group(4), "deps": deps,
                            "state": m.group(6)}
    return rows


def set_board(num: str, state: str, branch: str = "", commit: str = "") -> None:
    with LOCK:
        text = BOARD.read_text(encoding="utf-8")
        def repl(m: re.Match) -> str:
            return (f"| {m.group(1)} | {m.group(2)} | [{m.group(3)}](issues/{m.group(4)}) | {m.group(5)} | {state} |"
                    f" {branch or m.group(7).strip()} | {commit or m.group(8).strip()} |")
        text = ROW.sub(lambda m: repl(m) if m.group(1) == num else m.group(0), text)
        BOARD.write_text(text, encoding="utf-8", newline="\n")


def ready(rows: dict[str, dict], running: set[str]) -> list[str]:
    done = {n for n, r in rows.items() if r["state"] in ("done", "deferred")}
    out = []
    for n, r in sorted(rows.items()):
        if r["state"] in ("done", "deferred") or n in running:
            continue
        deps = [d for d in rows if d != n] if r["deps"] == ["*"] else r["deps"]
        if all(d in done for d in deps):
            out.append(n)
    return out


# ---------------------------------------------------------------- gates (no model)

SCAN = [
    (re.compile(r"[\u2013\u2014]"), "en or em dash"),
    (re.compile(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]"), "emoji"),
    (re.compile(r"[A-Za-z]:[\\/]+Users[\\/]+\w+", re.I), "absolute user path"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "e-mail address"),
    (re.compile(r"eyJ[\w-]{10,}\.[\w-]{10,}\.|ghp_\w{20,}|AKIA[0-9A-Z]{16}"), "token"),
]
# The session hooks of trail and graft rewrite these files in each new worktree. They are not ticket work.
WIRING = re.compile(r"^(\.claude/|\.cursor/|\.gemini/|\.mcp\.json$|AGENTS\.md$|GEMINI\.md$|\.trail/(?!learnings/))")
SCAN_SKIP = re.compile(r"(^|/)(tests?|e2e|test)/|lint|\.md$|package-lock\.json$")


def gates(wt: Path, base: str) -> list[str]:
    """Return the gate failures. An empty list is a pass."""
    fails = []
    committed_wiring = [p for p in sh(["git", "diff", "--name-only", f"{base}...HEAD"], wt).stdout.split() if WIRING.search(p)]
    if committed_wiring:                     # take hook changes out of the branch
        at_base = [p for p in committed_wiring if sh(["git", "cat-file", "-e", f"{base}:{p}"], wt).returncode == 0]
        new = [p for p in committed_wiring if p not in at_base]
        if at_base:
            sh(["git", "checkout", base, "--", *at_base], wt)
        if new:
            sh(["git", "rm", "-q", "--cached", "--ignore-unmatch", *new], wt)
        sh(["git", "commit", "-q", "-m", "Remove agent wiring changes from the ticket branch\n\n"
            "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"], wt)
    changed = sh(["git", "diff", "--name-only", f"{base}...HEAD"], wt).stdout.split()
    ignored = [l[3:] for l in sh(["git", "status", "--porcelain", "--ignored"], wt).stdout.splitlines()
               if l.startswith("!! ") and re.search(r"^(tests|frontend/(src|e2e|test))/", l[3:])]
    if ignored:
        fails.append("Ignored test or source files that git does not hold: " + ", ".join(ignored[:20]))
    dirty = "\n".join(l for l in sh(["git", "status", "--porcelain"], wt).stdout.splitlines()
                      if not WIRING.search(l[3:]) and not l[3:].startswith(".trail/learnings/"))
    if dirty:
        fails.append("Uncommitted changes:\n" + tail(dirty, 20))
    diff = sh(["git", "diff", f"{base}...HEAD", "--unified=0"], wt).stdout
    current = ""
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            current = line[6:]
        elif line.startswith("+") and not line.startswith("+++") and current and not SCAN_SKIP.search(current):
            for rx, what in SCAN:
                if rx.search(line):
                    fails.append(f"Rule scan: {what} in {current}: {line[:120]}")
    if any(p.endswith(".cs") or p.endswith(".csproj") for p in changed) or not (wt / "backend/adapters/tabular_metadata/dotnet/bin").exists():
        r = sh(["dotnet", "build", "-c", "Release", "backend/adapters/tabular_metadata/dotnet/TabularMetadata.csproj"], wt)
        if r.returncode:
            fails.append("dotnet build failed:\n" + tail(r.stdout))
    r = sh([sys.executable, "-m", "unittest", "discover", "-s", "tests"], wt, timeout=2400)
    if r.returncode:
        bad = [l for l in r.stderr.splitlines() if l.startswith(("ERROR:", "FAIL:"))]
        fails.append("Python suite failed:\n" + "\n".join(bad[:30]) + "\n" + tail(r.stderr, 30))
    if any(p.startswith("frontend/") for p in changed):
        for cmd, name in ((["npm", "test"], "npm test"), (["npm", "run", "build"], "npm run build")):
            r = sh(cmd, wt / "frontend", timeout=900)
            if r.returncode:
                fails.append(f"{name} failed:\n" + tail(r.stdout + r.stderr))
        specs = [p[len("frontend/"):] for p in changed if p.startswith("frontend/e2e/") and p.endswith(".spec.js")]
        if specs:
            r = sh(["npx", "playwright", "test", *specs, "--repeat-each=3"], wt / "frontend", timeout=2400)
            if r.returncode:
                fails.append("e2e (changed specs, 3 runs each, flaky counts as a failure):\n" + tail(r.stdout, 40))
        r = sh(["npx", "playwright", "test"], wt / "frontend", timeout=2400)
        if r.returncode:
            fails.append("e2e full suite failed:\n" + tail(r.stdout, 40))
    return fails


def setup(wt: Path) -> None:
    if not (wt / "frontend/node_modules").exists():
        sh(["npm", "ci", "--no-audit", "--no-fund"], wt / "frontend", check=True, timeout=900)
    sh(["dotnet", "build", "-c", "Release", "backend/adapters/tabular_metadata/dotnet/TabularMetadata.csproj"], wt, check=True)


# ---------------------------------------------------------------- prompts

DEV_PROMPT = """You are the developer of build ticket {num} ({step}) of the PBIBrain Development Center.
Your worktree is ready: node_modules, the TOM bridge, and LBUG_C_API_LIB_PATH are set up. Do not set them up again.
Read `.scratch/dev-center-build/WORKER.md` and `.scratch/dev-center-build/issues/{file}`. Read only the design sections that the ticket names, not the whole documents.
{extra}
Rules for cost: run only your own test modules while you work. Do not run the full Python suite or the full e2e suite; the orchestrator runs all gates after you finish and sends you any failure. Do not run kit gates more than once for each screen and theme.
Do not commit changes to `.claude/`, `.cursor/`, `.gemini/`, `.mcp.json`, `AGENTS.md`, `GEMINI.md`, or `.trail/` (session hooks change them); stage your files by name, not with `git add -A`.
When done: commit on this branch (no push), then reply in at most 8 lines: commit SHA, tests added, open items, and a line "Learning: <fact> because <reason>" for each non-obvious cause or trap."""

FIX_PROMPT = """The orchestrator found these problems in ticket {num}. Fix each one, run the related tests, commit, and reply in at most 6 lines (one line for each item, then the new SHA).

{findings}"""

REVIEW_PROMPT = """You are an independent reviewer of build ticket {num} ({step}) of the PBIBrain Development Center. Do not change code or commit.
Read `.scratch/dev-center-build/REVIEWER.md`, the ticket `.scratch/dev-center-build/issues/{file}`, and only the design sections that it names.
The diff: `git diff {base}...HEAD` in this worktree.
The orchestrator already ran all gates on this commit, and they passed: full Python suite, npm test, the build, the changed e2e specs 3 times each, the full e2e suite, and the rule scan (dashes, emoji, user paths, e-mail, tokens, ignored files). Do not run the full suites again. Run a single test only to prove a finding.
Check: each acceptance test of the ticket has an automated test that checks the stated behavior; ADR 0003; contracts and `revision`; correctness bugs that the tests miss; agreement with the schemas in `backend/devcenter/contracts/` that other tickets use.
{earlier}
Reply: first line PASS or FAIL. On FAIL, a numbered list: file and line, the problem, the required fix. Only blocking findings. At most 3 lines of notes."""


def extra_notes(num: str, st: dict) -> str:
    notes = []
    if st.get("continue_partial"):
        notes.append("An earlier developer stopped in this worktree before it finished. Read `git status` and `git diff` first and continue that work; do not start again.")
    return "\n".join(notes)


# ---------------------------------------------------------------- merge (no model, except hard conflicts)

def resolve_known(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    block = re.compile(r"<<<<<<< [^\n]*\n(.*?)=======\n(.*?)>>>>>>> [^\n]*\n", re.S)
    name = path.as_posix()
    if name.endswith(("backend/devcenter/jsapi.py", "backend/devcenter/http_routes.py", "backend/desktop/host.py",
                      "frontend/src/devcenter/invalidation.js", "packaging/pbibrain.spec")):
        new = block.sub(lambda m: m.group(1) + "".join(l for l in m.group(2).splitlines(True) if l not in m.group(1)), text)
    elif name.endswith("tests/test_devcenter_ui_contract.py"):
        new = block.sub("", text)        # each side removed its own pending methods
    else:
        return False
    path.write_text(new, encoding="utf-8", newline="")
    return "<<<<<<<" not in new


def merge(num: str, row: dict, branch: str) -> str:
    msg = f"Merge ticket {num}: {row['step']} {row['title']}\n\nOrchestrator merge after reviewer PASS.\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
    r = sh(["git", "merge", "--no-ff", branch, "-m", msg])
    if r.returncode:
        conflicted = sh(["git", "diff", "--name-only", "--diff-filter=U"]).stdout.split()
        hard = [f for f in conflicted if not resolve_known(ROOT / f)]
        if hard:
            res = claude("resolver", "Resolve the merge conflicts in these files. Keep the intent of both sides. "
                         "Do not change other files. Do not commit. Reply with one line for each file.\n" + "\n".join(hard),
                         ROOT, ticket=num)
            log(f"{num}: resolver: {tail(res['text'], 5)}")
        sh(["git", "add", "-A"], check=True)
        if sh(["git", "diff", "--name-only", "--diff-filter=U"]).stdout.strip():
            sh(["git", "merge", "--abort"])
            raise RuntimeError("merge conflict not resolved")
        sh(["git", "commit", "--no-edit"], check=True)
    fails = gates(ROOT, "HEAD~1")
    fails = [f for f in fails if not f.startswith(("Uncommitted", "Rule scan"))]
    if fails:
        raise RuntimeError("gates failed on the build branch after the merge:\n" + "\n".join(fails))
    return sh(["git", "log", "--format=%h", "-1"]).stdout.strip()


# ---------------------------------------------------------------- one ticket

def run_ticket(num: str, state: dict) -> None:
    rows = board_rows()
    row = rows[num]
    st = state["tickets"].setdefault(num, {})
    base = sh(["git", "rev-parse", "HEAD"]).stdout.strip()
    branch = st.get("branch") or f"dc/{num}-{row['file'][3:-3]}"
    wt = Path(st.get("worktree") or WORKTREES / f"dc-{num}")
    if not wt.exists():
        sh(["git", "worktree", "add", "-b", branch, str(wt), base], check=True)
        st.update(branch=branch, worktree=str(wt), base=base)
    else:
        st.setdefault("base", sh(["git", "merge-base", "HEAD", BUILD_BRANCH], wt).stdout.strip())
        st.setdefault("branch", sh(["git", "branch", "--show-current"], wt).stdout.strip())
    save_state(state)
    set_board(num, "running", st["branch"])
    setup(wt)

    if not st.get("developer_session"):
        log(f"{num}: developer start")
        res = claude("developer", DEV_PROMPT.format(num=num, step=row["step"], file=row["file"], extra=extra_notes(num, st)),
                     wt, ticket=num)
        st["developer_session"] = res["session_id"]
        st["developer_report"] = res["text"][-3000:]
        save_state(state)

    for attempt in range(MAX_GATE_FIXES + 1):
        fails = gates(wt, st["base"])
        if not fails:
            break
        if attempt == MAX_GATE_FIXES:
            set_board(num, "blocked")
            raise RuntimeError(f"{num}: gates still fail:\n" + "\n".join(fails)[:3000])
        log(f"{num}: gates failed ({len(fails)}); fixer")
        claude("developer", FIX_PROMPT.format(num=num, findings="\n\n".join(fails)[:12000]), wt, ticket=num,
               resume=st["developer_session"])

    earlier = ""
    for review in range(1, MAX_REVIEWS + 1):
        set_board(num, "review", st["branch"])
        model = "opus" if review == MAX_REVIEWS else None
        log(f"{num}: review {review}")
        res = claude("reviewer", REVIEW_PROMPT.format(num=num, step=row["step"], file=row["file"], base=st["base"],
                                                      earlier=earlier), wt, ticket=num, model=model)
        verdict = res["text"].strip()
        st.setdefault("reviews", []).append(verdict[:4000])
        save_state(state)
        if verdict.upper().startswith("PASS"):
            break
        if review == MAX_REVIEWS:
            set_board(num, "blocked")
            raise RuntimeError(f"{num}: FAIL after {MAX_REVIEWS} reviews")
        set_board(num, "rework", st["branch"])
        claude("developer", FIX_PROMPT.format(num=num, findings=verdict[:12000]), wt, ticket=num,
               resume=st["developer_session"])
        for attempt in range(MAX_GATE_FIXES + 1):
            fails = gates(wt, st["base"])
            if not fails:
                break
            if attempt == MAX_GATE_FIXES:
                set_board(num, "blocked")
                raise RuntimeError(f"{num}: gates fail after rework")
            claude("developer", FIX_PROMPT.format(num=num, findings="\n\n".join(fails)[:12000]), wt, ticket=num,
                   resume=st["developer_session"])
        earlier = "Earlier review findings (check that each one is fixed):\n" + verdict[:4000]

    with LOCK:                       # merges run one at a time on the build worktree
        commit = merge(num, row, st["branch"])
        set_board(num, "done", st["branch"], commit)
        learnings = re.findall(r"^Learning:.*$", st.get("developer_report", ""), re.M)
        if learnings:
            with INBOX.open("a", encoding="utf-8", newline="\n") as fh:
                fh.write(f"\n## Ticket {num}\n" + "\n".join(f"- {l[9:].strip()}" for l in learnings) + "\n")
        sh(["git", "add", str(BOARD), str(INBOX) if INBOX.exists() else str(BOARD)])
        sh(["git", "commit", "-m", f"Update the board after ticket {num}\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"])
        st["done"] = commit
        save_state(state)
    log(f"{num}: done at {commit}")


# ---------------------------------------------------------------- main loop

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only", action="append", default=[])
    ap.add_argument("--parallel", type=int, default=MAX_PARALLEL)
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if sh(["git", "branch", "--show-current"]).stdout.strip() != BUILD_BRANCH:
        print("Run the script in the build worktree.", file=sys.stderr)
        return 2
    state = load_state()
    running: dict[str, futures.Future] = {}
    stop = False
    with futures.ThreadPoolExecutor(max_workers=args.parallel) as pool:
        while True:
            rows = board_rows()
            todo = [n for n in ready(rows, set(running)) if rows[n]["state"] not in ("blocked",)]
            if args.only:
                todo = [n for n in todo if n in args.only]
            if args.dry_run:
                print("ready:", ", ".join(todo) or "none")
                return 0
            while not stop and todo and len(running) < args.parallel:
                n = todo.pop(0)
                running[n] = pool.submit(run_ticket, n, state)
            if not running:
                break
            done, _ = futures.wait(running.values(), return_when=futures.FIRST_COMPLETED)
            for n, f in list(running.items()):
                if f in done:
                    del running[n]
                    try:
                        f.result()
                    except UsageLimit as exc:
                        log(f"{n}: usage limit, stop starting new work: {exc}")
                        stop = True
                    except Exception as exc:  # noqa: BLE001 - one ticket must not stop the others
                        log(f"{n}: BLOCKED: {str(exc)[:1500]}")
                        state["tickets"].setdefault(n, {})["blocked"] = str(exc)[:3000]
                        save_state(state)
            if stop and not running:
                break
    rows = board_rows()
    print("summary:", {s: sorted(n for n, r in rows.items() if r["state"] == s) for s in ("done", "blocked", "running", "review", "rework", "open")})
    return 1 if stop else 0


if __name__ == "__main__":
    raise SystemExit(main())
