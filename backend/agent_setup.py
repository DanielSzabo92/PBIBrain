"""``brain agent-setup``: connect GitHub Copilot (VS Code, Copilot CLI) and Antigravity to the graph.

It writes, into the Power BI project folder that the user opens in the editor:

| File | For | What it does |
| --- | --- | --- |
| ``.vscode/mcp.json`` | VS Code | the ``pbibrain`` MCP server (VS Code format, ``servers``) |
| ``.mcp.json`` | Copilot CLI, Copilot harness | the same server (portable format, ``mcpServers``) |
| ``.github/agents/pbibrain.agent.md`` | VS Code, Copilot CLI | a **PBIBrain** custom agent whose only tools are ``pbibrain/*`` |
| ``.agents/mcp_config.json`` | Antigravity (app, IDE, CLI) | the ``pbibrain`` MCP server |
| ``.agents/rules/pbibrain.md`` | Antigravity | an always-on rule: answer model questions from PBIBrain only |

The custom agent is the hard boundary in Copilot: with ``tools: ['pbibrain/*']`` it has no file,
search, terminal or web tool, so a question about the model can only be answered from the graph.
Antigravity has no per-agent MCP tool list that is safe to write yet (an unknown tool name can
hang its subagent), so there the rule carries the same grounding text.

JSON files are merged: other servers stay, and only the ``pbibrain`` entry is replaced. A file
that is not valid JSON is left alone and reported. Markdown files are rewritten only when they
carry this tool's marker, unless ``force`` is given.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from backend.agent_rules import GROUNDING_RULES, TOOL_PLAYBOOK

SERVER = "pbibrain"
MARKER = "<!-- written by PBIBrain agent-setup; run it again to update, or delete this line to keep your edits -->"
CLIENTS = ("copilot", "antigravity")


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


def _agent_body() -> str:
    return (
        "You answer questions about this Power BI project: its semantic models, measures, columns, tables, "
        "relationships, data sources, reports, pages and visuals, and you can propose model changes for the user "
        "to accept in PBIBrain.\n\n"
        f"{GROUNDING_RULES}\n\n{TOOL_PLAYBOOK}\n\n"
        "You have only the PBIBrain tools. You cannot and need not open files, search the workspace, run commands "
        "or browse. A change to the model is a proposal (proposal_submit) in an open Merge models session; the user "
        "accepts or rejects it in PBIBrain. Never say a change was made.\n"
    )


def copilot_agent() -> str:
    return (
        "---\n"
        "name: PBIBrain\n"
        "description: Answers questions about this Power BI project from the PBIBrain graph only (dependencies, "
        "lineage, impact, report usage) and proposes model changes for review.\n"
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
        "For any question about the semantic models, measures, columns, tables, relationships, data sources, "
        "reports, pages or visuals of this project, use only the `pbibrain` MCP tools.\n\n"
        f"{GROUNDING_RULES}\n\n{TOOL_PLAYBOOK}\n\n"
        "Edit project files only when the user asks for an edit, and after editing call brain_pending_changes.\n"
    )


def _merge_json(path: Path, key: str, entry: dict[str, Any]) -> str:
    data: dict[str, Any] = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig") or "{}")
        except ValueError:
            return "skipped: not valid JSON, left unchanged"
        if not isinstance(data, dict):
            return "skipped: not a JSON object, left unchanged"
    servers = data.get(key)
    if servers is not None and not isinstance(servers, dict):
        return f"skipped: '{key}' is not an object, left unchanged"
    existed = isinstance(servers, dict) and SERVER in servers
    data[key] = {**(servers or {}), SERVER: entry}
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    return "updated" if existed else "written"


def _write_text(path: Path, text: str, force: bool) -> str:
    if path.exists():
        current = path.read_text(encoding="utf-8", errors="replace")
        if MARKER not in current and not force:
            return "skipped: edited by hand, left unchanged (use --force to replace)"
        if current == text:
            return "unchanged"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return "written"


def setup(config_path: str | Path, *, clients: tuple[str, ...] = CLIENTS, folder: str | Path | None = None,
          force: bool = False) -> dict[str, Any]:
    """Write the editor files; returns {folder, files: [{path, client, result}]}."""

    config = Path(config_path).resolve()
    if not config.is_file():
        raise ValueError(f"No PBIBrain project found: {config}")
    unknown = set(clients) - set(CLIENTS)
    if unknown:
        raise ValueError(f"Unknown client: {sorted(unknown)[0]}. Use copilot or antigravity.")
    root = Path(folder).resolve() if folder else project_folder(config)
    command = server_command(config)
    results: list[dict[str, str]] = []

    def record(relative: str, client: str, result: str) -> None:
        results.append({"path": relative, "client": client, "result": result})

    if "copilot" in clients:
        record(".vscode/mcp.json", "copilot", _merge_json(root / ".vscode" / "mcp.json", "servers", {"type": "stdio", **command}))
        record(".mcp.json", "copilot", _merge_json(root / ".mcp.json", "mcpServers", dict(command)))
        record(".github/agents/pbibrain.agent.md", "copilot",
               _write_text(root / ".github" / "agents" / "pbibrain.agent.md", copilot_agent(), force))
    if "antigravity" in clients:
        record(".agents/mcp_config.json", "antigravity", _merge_json(root / ".agents" / "mcp_config.json", "mcpServers", dict(command)))
        record(".agents/rules/pbibrain.md", "antigravity", _write_text(root / ".agents" / "rules" / "pbibrain.md", antigravity_rule(), force))
    return {"folder": str(root), "files": results,
            "next": ["VS Code: open the folder, trust it, start the pbibrain server (MCP: List Servers), "
                     "then pick the PBIBrain agent in Chat.",
                     "Copilot CLI: run `copilot --agent pbibrain` in the folder (trust it once).",
                     "Antigravity: open the folder; the rule and the pbibrain server load with the workspace."]}
