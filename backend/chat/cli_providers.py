"""Subscription providers of the in-app chat: the Claude Code, GitHub Copilot, Codex and Antigravity CLIs.

A user who pays for Claude (Pro/Max), GitHub Copilot (the VS Code subscription), ChatGPT (Codex)
or Google Antigravity can let the chat answer with that subscription instead of an API key.
PBIBrain starts the vendor's own command-line program (``claude``, ``copilot``, ``codex``,
``agy``), which is signed in already, and uses it as a plain text model.

These programs are full coding agents: they can run shell commands, edit files and browse.
Inside PBIBrain they must not. The CLI is a text generator here and nothing else:

- **PBIBrain owns the tool loop.** The CLI's own tools are turned off with each program's
  flags. The model asks for a PBIBrain tool by writing a ``<tool_call>`` block; the chat
  service runs it through the same registry, allowlist (``TOOL_ROUTES``) and run limits as an
  API provider. So a CLI can read and propose, never accept or apply (ADR 0003).
- **Nothing to reach.** The program runs in a new, empty temporary folder that is deleted
  afterwards, never in the project; its environment is scrubbed of API keys and tokens
  (``backend/process_guard.py``) except the one sign-in variable its vendor documents.
- **No command line from data.** The prompt goes on stdin. Arguments are fixed flags plus a
  checked model name, so project text can never reach ``cmd.exe`` parsing on Windows.
- **On a leash.** Each call has a timeout, the Stop button, and an output cap; any of them
  kills the program's whole process group.
- **Tool results are quoted data.** ``<`` in a tool result is written as ``&lt;``, so text in a
  model description cannot fake a ``<tool_call>`` or close its own result block.

The flags follow the vendors' documented headless modes (checked 2026-11-16):

- Claude Code: ``-p`` with ``--output-format json`` (one ``result`` object); ``--tools ""`` turns
  every built-in tool off and ``--disallowedTools`` names them again; ``--strict-mcp-config`` with an
  empty config loads no MCP server; one turn, no session saved, no slash commands.
- Copilot CLI: a piped prompt without ``-p`` is its non-interactive mode; ``-s`` prints only the
  answer; ``--deny-tool`` with every tool kind (shell, write, read, url, memory) refuses all of
  its tools, and deny wins over any allow; ``--disable-builtin-mcps``, ``--no-custom-instructions``
  and ``--no-ask-user`` drop its GitHub servers, AGENTS.md files and questions.
- Codex CLI: ``codex exec -`` reads the prompt from stdin and prints only the final message on
  stdout. ``--sandbox read-only``, ``--disable shell_tool`` (no command tool at all),
  ``web_search="disabled"``, ``--ignore-user-config`` (no user MCP servers or hooks; the sign-in
  in CODEX_HOME still works), ``--ignore-rules``, ``--ephemeral``, ``--skip-git-repo-check``.
- Antigravity CLI: ``--input-format stream-json`` reads ``{"event": "user", "message": {"content"}}``
  from stdin and needs ``--output-format stream-json``; the answer is the ``response`` of the final
  ``result`` event. ``--sandbox`` (OS containment) and ``--disable-slash-commands``. No ``--mode
  plan``: plan mode writes an implementation plan and waits for its review instead of answering.
  In headless mode a tool that needs approval is soft-denied (the run goes on, nothing is asked),
  and PBIBrain's own tools never go through agy at all, so no approval prompt can appear.

A vendor can change them; "Test connection" sends a multi-line probe so a broken setup shows
before a chat.
"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any
from collections.abc import Callable, Iterator, Mapping, Sequence

from backend.process_guard import ProcessLimit, run_bounded, scrubbed_environment

from .providers import ProviderError

CLI_TIMEOUT_SECONDS = 300
CLI_MAX_OUTPUT = 2 * 1024 * 1024
MODEL_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/@\[\]-]{0,199}")
MODEL_WITH_SPACES = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/@\[\]() -]{0,198}[A-Za-z0-9.)\]]|[A-Za-z0-9]")
EFFORT_PATTERN = re.compile(r"[a-z]{1,12}")
TOOL_CALL = re.compile(r"<tool_call>\s*(.*?)\s*</tool_call>", re.DOTALL)
PROBE = "This is a connection test from PBIBrain.\nReply with the single word OK and nothing else."

# Every Copilot CLI tool kind; denied together, the CLI has no tool left.
_COPILOT_DENY = "shell,write,read,url,memory"
# Claude Code tools named again in --disallowedTools, in case a CLI version ignores --tools "".
_CLAUDE_TOOLS = "Bash,Edit,Write,MultiEdit,NotebookEdit,Read,Glob,Grep,WebFetch,WebSearch,Task,Agent,TodoWrite"

PRESETS: dict[str, dict[str, Any]] = {
    "claude_code": {
        "label": "Claude subscription (Claude Code CLI)",
        "executable": "claude",
        "sign_in": "Install Claude Code and run claude once to sign in with your Claude plan.",
        # A subscription sign-in made with `claude setup-token`; any API key is dropped so the plan is used.
        "keep_env": ("CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CONFIG_DIR"),
    },
    "copilot": {
        "label": "GitHub Copilot subscription (VS Code, Copilot CLI)",
        "executable": "copilot",
        "sign_in": "Install the GitHub Copilot CLI and run copilot once to sign in with the account of your Copilot plan.",
        "keep_env": ("COPILOT_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN", "GH_HOST", "COPILOT_HOME"),
    },
    "codex": {
        "label": "ChatGPT subscription (Codex CLI)",
        "executable": "codex",
        "sign_in": "Install the Codex CLI and run codex once to sign in with ChatGPT.",
        # The ChatGPT sign-in lives in CODEX_HOME (auth.json); no key is passed.
        "keep_env": ("CODEX_HOME",),
    },
    "antigravity": {
        "label": "Google Antigravity subscription (agy CLI)",
        "executable": "agy",
        "sign_in": "Install the Antigravity CLI and run agy once to sign in with your Google account.",
        "keep_env": (),
    },
}


def validate_model(model: str, *, spaces: bool = False) -> str:
    """A model name that is safe as one program argument. ``spaces`` allows Antigravity's display
    names such as "Gemini 3.1 Pro (High)": spaces and parentheses, still no shell character."""

    model = model.strip()
    pattern = MODEL_WITH_SPACES if spaces else MODEL_PATTERN
    if model and not pattern.fullmatch(model):
        extra = ", spaces, ( )" if spaces else ""
        raise ValueError(f"The model name may hold only letters, digits and . _ : / @ [ ] -{extra}")
    return model


def validate_command(preset: str, command: str) -> str:
    """The program setting: empty (find it on PATH), its bare name, or an absolute path to that program."""

    command = str(command or "").strip()
    expected = PRESETS[preset]["executable"]
    if not command or command == expected:
        return command
    path = Path(command)
    if not path.is_absolute():
        raise ValueError(f"Give the full path of the {expected} program, or leave it empty to find it on PATH")
    if path.stem.lower() != expected:
        raise ValueError(f"The program must be {expected} (for example {expected}.exe or {expected}.cmd)")
    return command


def find_program(preset: str, command: str = "") -> str | None:
    """The program to start, or None when it is not installed."""

    command = command or PRESETS[preset]["executable"]
    if Path(command).is_absolute():
        return command if Path(command).is_file() else None
    return shutil.which(command)


# Prompt and reply ------------------------------------------------------------------------------


def _quote(text: str) -> str:
    """Untrusted text inside the transcript: it can never open or close a block."""

    return text.replace("&", "&amp;").replace("<", "&lt;")


def render_prompt(system: str, messages: Sequence[Mapping[str, Any]], tools: Sequence[Mapping[str, Any]]) -> str:
    """The whole conversation as one prompt; the CLI is stateless between calls."""

    catalog = "\n".join(json.dumps({"name": tool["name"], "description": tool["description"],
                                    "input_schema": tool["input_schema"]}, ensure_ascii=False, separators=(",", ":"))
                        for tool in tools)
    parts = [
        system,
        "# How to use tools\n"
        "You have no tools of your own here: no shell, files, web or editing. Do not try to use any. "
        "You can use only the PBIBrain tools listed below. To call them, reply with tool call blocks and nothing else, one per call:\n"
        '<tool_call>{"name": "brain_search", "input": {"query": "Revenue"}}</tool_call>\n'
        "Then stop. The results come back in the next turn as <tool_result> blocks. "
        "A reply without a tool call block is your answer to the user. Never call a tool that is not listed.",
        "# PBIBrain tools (one JSON object per line)\n" + (catalog or "(none in this turn)"),
        "# Conversation",
    ]
    for message in messages:
        blocks = message["content"] if isinstance(message["content"], list) else [{"type": "text", "text": str(message["content"])}]
        for block in blocks:
            kind = block.get("type")
            if kind == "text" and message["role"] == "user":
                parts.append(f"<user>\n{block.get('text', '')}\n</user>")
            elif kind == "text":
                parts.append(f"<assistant>\n{block.get('text', '')}\n</assistant>")
            elif kind == "tool_use":
                call = json.dumps({"name": block.get("name"), "input": block.get("input") or {}}, ensure_ascii=False)
                parts.append(f"<assistant>\n<tool_call>{call}</tool_call>\n</assistant>")
            elif kind == "tool_result":
                status = " error=\"true\"" if block.get("is_error") else ""
                parts.append(f"<tool_result id=\"{_quote(str(block.get('tool_use_id', '')))}\"{status}>\n"
                             f"{_quote(str(block.get('content', '')))}\n</tool_result>")
    parts.append("Write the assistant's next turn now: tool call blocks, or the answer.")
    return "\n\n".join(parts)


def parse_reply(text: str) -> dict[str, Any]:
    """{type: message, content, stop_reason} from the CLI's text, with tool calls as tool_use blocks."""

    content: list[dict[str, Any]] = []
    calls = []
    for index, match in enumerate(TOOL_CALL.finditer(text)):
        raw = match.group(1).strip()
        if raw.startswith("```"):
            raw = raw.strip("`").removeprefix("json").strip()
        try:
            value = json.loads(raw)
        except ValueError:
            value = None
        if isinstance(value, Mapping) and isinstance(value.get("name"), str):
            given = value.get("input", {})
            arguments = given if isinstance(given, Mapping) else {"__invalid_json__": raw[:2000]}
            calls.append({"type": "tool_use", "id": f"cli_{index}", "name": value["name"], "input": dict(arguments)})
        else:
            calls.append({"type": "tool_use", "id": f"cli_{index}", "name": "", "input": {"__invalid_json__": raw[:2000]}})
    prose = TOOL_CALL.sub("", text).strip()
    if prose:
        content.append({"type": "text", "text": prose})
    content.extend(calls)
    return {"type": "message", "content": content, "stop_reason": "tool_use" if calls else "end_turn"}


# The provider ----------------------------------------------------------------------------------


class SubscriptionCLIProvider:
    """One chat provider that answers through a signed-in vendor CLI (see the module text)."""

    def __init__(self, *, preset: str, model: str = "", command: str = "", effort: str = "", timeout: float = CLI_TIMEOUT_SECONDS,
                 runner: Callable[..., Any] = run_bounded) -> None:
        if preset not in PRESETS:
            raise ProviderError(f"Unknown subscription provider {preset}")
        self.preset = preset
        self.spec = PRESETS[preset]
        try:
            self.model = validate_model(model, spaces=preset == "antigravity")
            self.command = validate_command(preset, command)
        except ValueError as exc:
            raise ProviderError(str(exc)) from exc
        effort = str(effort or "")
        if effort and (not EFFORT_PATTERN.fullmatch(effort) or preset == "antigravity"):
            raise ProviderError(f"The {self.spec['executable']} program takes no effort {effort}")
        self.effort = effort
        self.timeout = timeout
        self.runner = runner

    # The vendor's headless flags; the CLI's own tools are off in every preset.
    def arguments(self, workdir: Path) -> tuple[list[str], str]:
        """(argv after the program, the input format: text or agy-stream)."""

        model = ["--model", self.model] if self.model else []
        if self.preset == "claude_code":
            (workdir / "mcp.json").write_text('{"mcpServers": {}}', encoding="utf-8")
            effort = ["--effort", self.effort] if self.effort else []
            return ["-p", "--output-format", "json", "--max-turns", "1", "--tools", "", "--disallowedTools", _CLAUDE_TOOLS,
                    "--permission-mode", "default", "--strict-mcp-config", "--mcp-config", str(workdir / "mcp.json"),
                    "--disable-slash-commands", "--no-session-persistence", *model, *effort], "text"
        if self.preset == "codex":
            effort = ["-c", f'model_reasoning_effort="{self.effort}"'] if self.effort else []
            return ["exec", "--sandbox", "read-only", "--disable", "shell_tool", "-c", 'web_search="disabled"',
                    "--ignore-user-config", "--ignore-rules", "--ephemeral", "--skip-git-repo-check", *model, *effort, "-"], "text"
        if self.preset == "copilot":
            # Piped input without -p is Copilot's documented non-interactive mode; no tool is pre-approved,
            # every tool kind is denied, and deny wins over any allow in the user's settings.
            effort = [f"--reasoning-effort={self.effort}"] if self.effort else []
            return ["-s", "--no-custom-instructions", "--disable-builtin-mcps", "--no-ask-user",
                    f"--deny-tool={_COPILOT_DENY}", *model, *effort], "text"
        return ["--input-format", "stream-json", "--output-format", "stream-json", "--sandbox",
                "--disable-slash-commands", *model], "agy-stream"

    def _program(self) -> str:
        program = find_program(self.preset, self.command)
        if program is None:
            raise ProviderError(f"The {self.spec['executable']} program was not found. {self.spec['sign_in']} "
                                "Or set its full path in Settings, AI provider.")
        return program

    def _run(self, prompt: str, should_stop: Callable[[], bool]) -> str:
        program = self._program()
        with tempfile.TemporaryDirectory(prefix="pbibrain-cli-") as folder:
            workdir = Path(folder)
            arguments, mode = self.arguments(workdir)
            if mode == "agy-stream":
                data = (json.dumps({"event": "user", "message": {"content": prompt}}, ensure_ascii=False) + "\n").encode("utf-8")
            else:
                data = prompt.encode("utf-8")
            extra = {"PBIBRAIN_CHAT_SANDBOX": "1", "NO_COLOR": "1"}
            if self.preset == "claude_code" and self.effort:
                # The variable wins over --effort in Claude Code, and some versions ignore the flag.
                extra["CLAUDE_CODE_EFFORT_LEVEL"] = self.effort
            environment = scrubbed_environment(self.spec["keep_env"], extra=extra)
            try:
                finished = self.runner([program, *arguments], cwd=workdir, env=environment, timeout=self.timeout, input=data,
                                       should_stop=should_stop, max_output=CLI_MAX_OUTPUT)
            except ProcessLimit as exc:
                if exc.reason == "stopped":
                    raise
                raise ProviderError(f"The {self.spec['executable']} program was stopped: {exc}") from exc
            except OSError as exc:
                raise ProviderError(f"The {self.spec['executable']} program could not start: {exc.strerror or exc}") from exc
        out = finished.stdout.decode("utf-8", "replace")
        err = finished.stderr.decode("utf-8", "replace").strip()
        return self._reply_text(out, err, finished.returncode)

    def _reply_text(self, out: str, err: str, code: int) -> str:
        name = self.spec["executable"]
        if self.preset == "claude_code":
            try:
                result = json.loads(out.strip().splitlines()[-1] if out.strip() else "{}")
            except ValueError:
                result = {}
            if isinstance(result, Mapping) and result.get("type") == "result":
                if result.get("is_error"):
                    raise ProviderError(f"{name}: {str(result.get('result') or result.get('subtype') or 'error')[:400]}")
                return str(result.get("result") or "")
            raise ProviderError(f"{name} did not answer (exit {code}). {err[:300] or self.spec['sign_in']}")
        if self.preset == "antigravity":
            return self._agy_text(out, err, code)
        if code != 0:
            raise ProviderError(f"{name} stopped with exit code {code}. {err[:300] or self.spec['sign_in']}")
        return out.strip()

    def _agy_text(self, out: str, err: str, code: int) -> str:
        """The ``response`` of the final ``result`` event; the ``text_delta`` pieces when it is missing."""

        result: Mapping[str, Any] | None = None
        pieces: list[str] = []
        for line in out.splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if not isinstance(event, Mapping):
                continue
            if event.get("event") == "result" and isinstance(event.get("result"), Mapping):
                result = event["result"]
            elif event.get("event") == "step_update" and isinstance(event.get("step_update"), Mapping):
                step = event["step_update"]
                if step.get("step_type") == "agent_response" and isinstance(step.get("text_delta"), str):
                    pieces.append(step["text_delta"])
        if result is not None:
            if result.get("status") not in {None, "SUCCESS"}:
                detail = result.get("error") or result.get("status")
                raise ProviderError(f"agy: {str(detail)[:400]}")
            return str(result.get("response") or "".join(pieces))
        if pieces:
            return "".join(pieces)
        raise ProviderError(f"agy did not answer (exit {code}). {err[:300] or self.spec['sign_in']}")

    def test(self) -> dict[str, Any]:
        try:
            text = self._run(PROBE, lambda: False)
        except ProviderError as exc:
            return {"ok": False, "message": str(exc)}
        if not text.strip():
            return {"ok": False, "message": f"{self.spec['executable']} answered with nothing. {self.spec['sign_in']}"}
        return {"ok": True, "message": f"Connected through {self.spec['executable']}. Its own tools are turned off inside PBIBrain."}

    def stream(self, *, system: str, messages: Sequence[Mapping[str, Any]], tools: Sequence[Mapping[str, Any]],
               should_stop: Callable[[], bool]) -> Iterator[dict[str, Any]]:
        try:
            text = self._run(render_prompt(system, messages, tools), should_stop)
        except ProcessLimit:
            yield {"type": "message", "content": [], "stop_reason": "stopped"}
            return
        reply = parse_reply(text)
        prose = "".join(block["text"] for block in reply["content"] if block["type"] == "text")
        if prose:
            yield {"type": "text", "text": prose}
        yield reply
