"""``brain agent-setup``: put Claude Code, GitHub Copilot (VS Code, Copilot CLI), Codex and
Antigravity on the PBIBrain graph, inside a boundary that the editor enforces.

It writes, into the Power BI project folder that the user opens in the editor:

| File | For | What it does |
| --- | --- | --- |
| ``.mcp.json`` | Claude Code, Copilot CLI | the ``pbibrain`` MCP server (portable format, ``mcpServers``) |
| ``.claude/settings.json`` | Claude Code (Copilot CLI reads it too) | enables that server, pre-approves its tools, registers the hooks |
| ``.vscode/mcp.json`` | VS Code | the ``pbibrain`` MCP server (VS Code format, ``servers``) |
| ``.github/hooks/pbibrain.json`` | VS Code, Copilot CLI, Copilot cloud agent | the hooks (Copilot format) |
| ``.github/agents/pbibrain.agent.md`` | VS Code, Copilot CLI | a **PBIBrain** custom agent whose only tools are ``pbibrain/*`` |
| ``.codex/config.toml`` | Codex (CLI, IDE, app) | the server with its tools approved, web search off |
| ``.codex/hooks.json`` | Codex | the hooks |
| ``.agents/mcp_config.json`` | Antigravity (app, IDE, CLI) | the ``pbibrain`` MCP server |
| ``.agents/hooks.json`` | Antigravity | the hooks (``auto_approve`` for PBIBrain tools, so no approval prompts) |
| ``.agents/rules/pbibrain.md`` | Antigravity | an always-on rule with the grounding rules |
| ``.pbibrain/agent-context.md`` | every client | the grounding rules the session-start hook adds to each new session |

**The hooks are the boundary** (``backend/agent_hook.py``). Before each tool call, the editor runs
the hook and obeys it: PBIBrain tools are approved, harmless editor tools are allowed, and files,
terminal, web, subagents and other servers are denied with a reason that names the PBIBrain tool
to use. At session start the hook adds the grounding rules to the agent's context. Instructions
in markdown are kept as a second line only.

JSON files are merged: other servers and hooks stay, and only the PBIBrain entries are replaced.
A file that is not valid JSON or TOML is left alone and reported. ``.codex/config.toml`` holds
PBIBrain's lines between marker comments. Markdown files are rewritten only when they carry this
tool's marker, unless ``force`` is given.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
from pathlib import Path
from typing import Any

from backend.agent_rules import GROUNDING_RULES, TOOL_PLAYBOOK, WORKFLOW_RULES

SERVER = "pbibrain"
MARKER = "<!-- written by PBIBrain agent-setup; run it again to update, or delete this line to keep your edits -->"
CLIENTS = ("claude", "copilot", "codex", "antigravity")
HOOK_TIMEOUT = 15
TOML_BEGIN = "# >>> PBIBrain agent-setup (rewritten by brain agent-setup; edit outside these lines)"
TOML_END = "# <<< PBIBrain agent-setup"


def project_folder(config_path: Path) -> Path:
    """The folder the user opens in the editor: the parent of ``.pbibrain``, else the config's folder."""

    config_path = config_path.resolve()
    return config_path.parent.parent if config_path.parent.name == ".pbibrain" else config_path.parent


def server_command(config_path: Path) -> dict[str, Any]:
    """How an editor starts the PBIBrain MCP server for this project."""

    config_path = config_path.resolve()
    if getattr(sys, "frozen", False):
        # The installed PBIBrain-Agent.exe (docs/AGENT_GUIDE.md).
        return {"command": sys.executable, "args": ["--config", str(config_path), "mcp"]}
    root = Path(__file__).resolve().parents[1]
    return {"command": sys.executable, "args": ["-m", "backend.agent", "--config", str(config_path), "mcp"],
            "env": {"PYTHONPATH": str(root)}}


def hook_argv(client: str, project: Path, *, event: str = "tool") -> list[str]:
    """The hook program and its arguments: the installed agent, or this checkout's stdlib-only script."""

    tail = ["--client", client, "--project", str(project)] + (["--event", "session"] if event == "session" else [])
    if getattr(sys, "frozen", False):
        return [sys.executable, "agent-hook", *tail]
    return [sys.executable, str(Path(__file__).resolve().with_name("agent_hook.py")), *tail]


def command_line(argv: list[str], shell: str) -> str:
    """One command line for the shell the editor runs hooks with: posix (sh, Git Bash), powershell or cmd."""

    if shell == "powershell":
        return "& " + " ".join("'" + item.replace("'", "''") + "'" for item in argv)
    if shell == "cmd":
        return " ".join('"' + item + '"' if (" " in item or not item) else item for item in argv)
    # Forward slashes: Git Bash on Windows reads a backslash as an escape.
    return " ".join(shlex.quote(item.replace("\\", "/") if re.match(r"^[A-Za-z]:\\", item) else item) for item in argv)


def _windows() -> bool:
    return os.name == "nt"


def _posix_or(windows_shell: str) -> str:
    return windows_shell if _windows() else "posix"


# File content ----------------------------------------------------------------------------------


def _agent_body() -> str:
    return (
        "You answer questions about this Power BI project: its semantic models, measures, columns, tables, "
        "functions, queries, relationships, data sources, reports, pages and visuals, and you prepare model "
        "changes for the user to accept in PBIBrain.\n\n"
        f"{GROUNDING_RULES}\n\n{TOOL_PLAYBOOK}\n\n{WORKFLOW_RULES}\n"
    )


def context_text() -> str:
    """What the session-start hook adds to every new agent session."""

    return "# PBIBrain: the source of truth for this Power BI project\n\n" + _agent_body()


def copilot_agent() -> str:
    return (
        "---\n"
        "name: PBIBrain\n"
        "description: Answers questions about this Power BI project from the PBIBrain graph only (dependencies, "
        "lineage, impact, report usage) and prepares model changes for review.\n"
        f"tools: ['{SERVER}/*']\n"
        "---\n"
        f"{MARKER}\n\n# PBIBrain\n\n{_agent_body()}"
    )


def antigravity_rule() -> str:
    return (
        "---\n"
        "trigger: always_on\n"
        "description: Questions about the Power BI model or reports are answered from the PBIBrain MCP tools only.\n"
        "---\n"
        f"{MARKER}\n\n# PBIBrain is the source of truth for this Power BI project\n\n"
        "For any question about the semantic models, measures, columns, tables, functions, queries, relationships, "
        "data sources, reports, pages or visuals of this project, use only the `pbibrain` MCP tools.\n\n"
        f"{_agent_body()}"
    )


def _is_ours(entry: Any) -> bool:
    return "agent-hook" in json.dumps(entry) or "agent_hook.py" in json.dumps(entry)


def _claude_hooks(project: Path) -> dict[str, Any]:
    shell = _posix_or("posix")  # Claude Code runs hooks with Git Bash on Windows
    tool = command_line(hook_argv("claude", project), shell)
    session = command_line(hook_argv("claude", project, event="session"), shell)
    return {
        "PreToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": tool, "timeout": HOOK_TIMEOUT}]}],
        "PermissionRequest": [{"matcher": "*", "hooks": [{"type": "command", "command": tool, "timeout": HOOK_TIMEOUT}]}],
        "SessionStart": [{"hooks": [{"type": "command", "command": session, "timeout": HOOK_TIMEOUT}]}],
    }


def copilot_hooks(project: Path) -> dict[str, Any]:
    def entry(event: str) -> dict[str, Any]:
        argv = hook_argv("copilot", project, event=event)
        return {"type": "command", "bash": command_line(argv, "posix"), "powershell": command_line(argv, "powershell"),
                "timeoutSec": HOOK_TIMEOUT}

    return {"version": 1, "hooks": {"preToolUse": [entry("tool")], "sessionStart": [entry("session")]}}


def codex_hooks(project: Path) -> dict[str, Any]:
    def entry(event: str) -> dict[str, Any]:
        argv = hook_argv("codex", project, event=event)
        return {"type": "command", "command": command_line(argv, "posix"), "commandWindows": command_line(argv, "powershell"),
                "timeout": HOOK_TIMEOUT, "statusMessage": "PBIBrain boundary"}

    return {
        "PreToolUse": [{"matcher": ".*", "hooks": [entry("tool")]}],
        "PermissionRequest": [{"matcher": ".*", "hooks": [entry("tool")]}],
        "SessionStart": [{"hooks": [entry("session")]}],
    }


def antigravity_hooks(project: Path) -> dict[str, Any]:
    shell = _posix_or("cmd")  # sh -c, cmd /c on Windows
    return {
        "PreToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": command_line(hook_argv("antigravity", project), shell),
                                                   "timeout": HOOK_TIMEOUT}]}],
        "SessionStart": [{"type": "command", "command": command_line(hook_argv("antigravity", project, event="session"), shell),
                          "timeout": HOOK_TIMEOUT}],
    }


def _toml(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "[" + ", ".join(_toml(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{key} = {_toml(item)}" for key, item in value.items()) + " }"
    return str(value)


# Writers -------------------------------------------------------------------------------------------


def _read_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.exists():
        return {}, None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig") or "{}")
    except ValueError:
        return None, "skipped: not valid JSON, left unchanged"
    if not isinstance(data, dict):
        return None, "skipped: not a JSON object, left unchanged"
    return data, None


def _save_json(path: Path, data: dict[str, Any], existed: bool, before: Any) -> str:
    if existed and before == data:
        return "unchanged"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    return "updated" if existed else "written"


def _merge_json(path: Path, key: str, entry: dict[str, Any]) -> str:
    data, refused = _read_json(path)
    if data is None:
        return refused or "skipped"
    before = json.loads(json.dumps(data))
    servers = data.get(key)
    if servers is not None and not isinstance(servers, dict):
        return f"skipped: '{key}' is not an object, left unchanged"
    data[key] = {**(servers or {}), SERVER: entry}
    return _save_json(path, data, path.exists(), before)


def _merge_hooks(target: dict[str, Any], hooks: dict[str, Any]) -> str | None:
    """Replace PBIBrain's entries in each event list of ``target``; keep everything else."""

    for event, entries in hooks.items():
        current = target.get(event, [])
        if not isinstance(current, list):
            return f"skipped: hooks.{event} is not a list, left unchanged"
        target[event] = [item for item in current if not _is_ours(item)] + entries
    return None


def _write_claude_settings(path: Path, project: Path) -> str:
    data, refused = _read_json(path)
    if data is None:
        return refused or "skipped"
    before = json.loads(json.dumps(data))
    for key, kind in (("permissions", dict), ("hooks", dict), ("enabledMcpjsonServers", list)):
        if key in data and not isinstance(data[key], kind):
            return f"skipped: '{key}' has an unexpected shape, left unchanged"
    enabled = data.setdefault("enabledMcpjsonServers", [])
    if SERVER not in enabled:
        enabled.append(SERVER)
    permissions = data.setdefault("permissions", {})
    allow = permissions.setdefault("allow", [])
    if not isinstance(allow, list):
        return "skipped: 'permissions.allow' is not a list, left unchanged"
    if f"mcp__{SERVER}" not in allow:
        allow.append(f"mcp__{SERVER}")
    problem = _merge_hooks(data.setdefault("hooks", {}), _claude_hooks(project))
    if problem:
        return problem
    return _save_json(path, data, path.exists(), before)


def _write_antigravity_hooks(path: Path, project: Path) -> str:
    data, refused = _read_json(path)
    if data is None:
        return refused or "skipped"
    before = json.loads(json.dumps(data))
    data[f"{SERVER}-boundary"] = antigravity_hooks(project)
    return _save_json(path, data, path.exists(), before)


def _write_codex_hooks(path: Path, project: Path) -> str:
    data, refused = _read_json(path)
    if data is None:
        return refused or "skipped"
    before = json.loads(json.dumps(data))
    hooks = data.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        return "skipped: 'hooks' is not an object, left unchanged"
    problem = _merge_hooks(hooks, codex_hooks(project))
    if problem:
        return problem
    data.setdefault("description", "PBIBrain boundary: only the pbibrain tools in this Power BI project.")
    return _save_json(path, data, path.exists(), before)


def _strip_managed(text: str) -> str:
    return re.sub(rf"(?ms)^{re.escape(TOML_BEGIN)}.*?^{re.escape(TOML_END)}[^\n]*\n?", "", text)


def _write_codex_config(path: Path, command: dict[str, Any]) -> str:
    """Top-level keys go first and the server table last, each in a marked block, so TOML scoping holds."""

    existed = path.exists()
    current = path.read_text(encoding="utf-8") if existed else ""
    rest = _strip_managed(current)
    try:
        import tomllib
    except ImportError:  # Python 3.10: write without the check
        tomllib = None  # type: ignore[assignment]
    parsed: dict[str, Any] = {}
    if tomllib is not None and rest.strip():
        try:
            parsed = tomllib.loads(rest)
        except tomllib.TOMLDecodeError:
            return "skipped: not valid TOML, left unchanged"
    if SERVER in (parsed.get("mcp_servers") or {}):
        return f"skipped: [mcp_servers.{SERVER}] is already set by hand, left unchanged"
    top = [] if "web_search" in parsed else ['web_search = "disabled"  # Codex web search cannot be hooked']
    table = [f"[mcp_servers.{SERVER}]", f"command = {_toml(command['command'])}", f"args = {_toml(command['args'])}"]
    if command.get("env"):
        table.append(f"env = {_toml(command['env'])}")
    table += ['default_tools_approval_mode = "approve"', "required = true"]
    head = "\n".join([TOML_BEGIN, *top, TOML_END]) + "\n" if top else ""
    tail = "\n".join([TOML_BEGIN, *table, TOML_END]) + "\n"
    body = rest.strip("\n")
    text = head + (body + "\n\n" if body else "") + tail
    if tomllib is not None:
        tomllib.loads(text)  # the merge must stay valid
    if existed and text == current:
        return "unchanged"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return "updated" if existed else "written"


def _write_text(path: Path, text: str, force: bool, *, marker: bool = True) -> str:
    if path.exists():
        current = path.read_text(encoding="utf-8", errors="replace")
        if marker and MARKER not in current and not force:
            return "skipped: edited by hand, left unchanged (use --force to replace)"
        if current == text:
            return "unchanged"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return "written"


def setup(config_path: str | Path, *, clients: tuple[str, ...] = CLIENTS, folder: str | Path | None = None,
          force: bool = False) -> dict[str, Any]:
    """Write the editor files; returns {folder, files: [{path, client, result}], next}."""

    config = Path(config_path).resolve()
    if not config.is_file():
        raise ValueError(f"No PBIBrain project found: {config}")
    unknown = set(clients) - set(CLIENTS)
    if unknown:
        raise ValueError(f"Unknown client: {sorted(unknown)[0]}. Use claude, copilot, codex or antigravity.")
    root = Path(folder).resolve() if folder else project_folder(config)
    command = server_command(config)
    results: list[dict[str, str]] = []

    def record(relative: str, client: str, result: str) -> None:
        results.append({"path": relative, "client": client, "result": result})

    record(".pbibrain/agent-context.md", "all",
           _write_text(root / ".pbibrain" / "agent-context.md", context_text(), force, marker=False))
    if "claude" in clients or "copilot" in clients:
        record(".mcp.json", "claude, copilot", _merge_json(root / ".mcp.json", "mcpServers", dict(command)))
    if "claude" in clients:
        record(".claude/settings.json", "claude", _write_claude_settings(root / ".claude" / "settings.json", root))
    if "copilot" in clients:
        record(".vscode/mcp.json", "copilot", _merge_json(root / ".vscode" / "mcp.json", "servers", {"type": "stdio", **command}))
        hooks_path = root / ".github" / "hooks" / "pbibrain.json"
        before = hooks_path.read_text(encoding="utf-8") if hooks_path.exists() else None
        text = json.dumps(copilot_hooks(root), indent=2) + "\n"
        hooks_path.parent.mkdir(parents=True, exist_ok=True)
        if before != text:
            hooks_path.write_text(text, encoding="utf-8")
        record(".github/hooks/pbibrain.json", "copilot", "unchanged" if before == text else ("updated" if before else "written"))
        record(".github/agents/pbibrain.agent.md", "copilot",
               _write_text(root / ".github" / "agents" / "pbibrain.agent.md", copilot_agent(), force))
    if "codex" in clients:
        record(".codex/config.toml", "codex", _write_codex_config(root / ".codex" / "config.toml", command))
        record(".codex/hooks.json", "codex", _write_codex_hooks(root / ".codex" / "hooks.json", root))
    if "antigravity" in clients:
        record(".agents/mcp_config.json", "antigravity", _merge_json(root / ".agents" / "mcp_config.json", "mcpServers", dict(command)))
        record(".agents/hooks.json", "antigravity", _write_antigravity_hooks(root / ".agents" / "hooks.json", root))
        record(".agents/rules/pbibrain.md", "antigravity", _write_text(root / ".agents" / "rules" / "pbibrain.md", antigravity_rule(), force))
    steps = {
        "claude": "Claude Code: run claude in the folder and approve the project settings once; the hooks then hold.",
        "copilot": "VS Code: open and trust the folder, start pbibrain (MCP: List Servers) and use Chat; the hooks in "
                   ".github/hooks apply to every agent there. Copilot CLI: run copilot (or copilot --agent pbibrain) in the folder.",
        "codex": "Codex: trust the project, then open /hooks once and trust the PBIBrain hooks (Codex skips hooks it has not trusted).",
        "antigravity": "Antigravity: open the folder; the hooks, the rule and the pbibrain server load with the workspace.",
    }
    return {"folder": str(root), "files": results, "next": [steps[name] for name in CLIENTS if name in clients]}
