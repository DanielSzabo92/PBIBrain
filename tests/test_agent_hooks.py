"""The editor boundary: the pre-tool hook (backend/agent_hook.py) run as the editors run it, and
the hook files ``brain agent-setup`` writes for Claude Code, Copilot, Codex and Antigravity."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from backend import agent_hook
from backend.agent_setup import TOML_BEGIN, command_line, setup

HOOK = Path(agent_hook.__file__).resolve()


def run_hook(client: str, payload, project: Path | None = None, *, event: str = "tool") -> tuple[dict | None, str, int]:
    argv = [sys.executable, "-I", str(HOOK), "--client", client]
    if project is not None:
        argv += ["--project", str(project)]
    if event == "session":
        argv += ["--event", "session"]
    data = payload if isinstance(payload, str) else json.dumps(payload)
    done = subprocess.run(argv, input=data.encode(), capture_output=True, timeout=30)
    out = done.stdout.decode().strip()
    return (json.loads(out) if out else None), done.stderr.decode(), done.returncode


class HookDecisionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.project = Path(self.temporary.name)
        (self.project / ".pbibrain").mkdir()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_claude_and_codex_get_pbibrain_tools_and_lose_files_and_shell(self):
        out, _, code = run_hook("claude", {"hook_event_name": "PreToolUse", "tool_name": "mcp__pbibrain__brain_dependencies",
                                           "tool_input": {"object": "Sales"}}, self.project)
        self.assertEqual(0, code)
        self.assertEqual("allow", out["hookSpecificOutput"]["permissionDecision"])
        for name, args in (("Read", {"file_path": "Model.SemanticModel/definition/tables/Sales.tmdl"}), ("Grep", {"pattern": "Sales"}),
                           ("Bash", {"command": "cat *.tmdl"}), ("WebFetch", {"url": "https://x"}), ("Task", {"prompt": "look"}),
                           ("mcp__github__get_file_contents", {}), ("mcp__pbibrain_evil__brain_search", {})):
            out, err, code = run_hook("claude", {"hook_event_name": "PreToolUse", "tool_name": name, "tool_input": args}, self.project)
            self.assertEqual(2, code, name)
            self.assertIn("brain_dependencies", err, "the reason names the tool to use instead")
        out, _, code = run_hook("codex", {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "ls"}})
        self.assertEqual(2, code)
        out, _, code = run_hook("codex", {"hook_event_name": "PreToolUse", "tool_name": "mcp__pbibrain__proposal_submit", "tool_input": {}})
        self.assertEqual((None, 0), (out, code), "Codex: no objection; its config approves the server")
        out, _, _ = run_hook("codex", {"hook_event_name": "PermissionRequest", "tool_name": "mcp__pbibrain__proposal_check", "tool_input": {}})
        self.assertEqual("allow", out["hookSpecificOutput"]["decision"]["behavior"])
        out, _, _ = run_hook("claude", {"hook_event_name": "PermissionRequest", "tool_name": "Bash", "tool_input": {}})
        self.assertEqual("deny", out["hookSpecificOutput"]["decision"]["behavior"])

    def test_copilot_shapes(self):
        out, _, code = run_hook("copilot", {"toolName": "pbibrain-brain_search", "toolArgs": '{"query": "Sales"}'}, self.project)
        self.assertEqual((0, "allow"), (code, out["permissionDecision"]))
        out, err, code = run_hook("copilot", {"toolName": "view", "toolArgs": '{"path": "Sales.tmdl"}'}, self.project)
        self.assertEqual((2, "deny"), (code, out["permissionDecision"]))
        self.assertIn("pbibrain tools", out["permissionDecisionReason"])
        out, _, code = run_hook("copilot", {"toolName": "report_intent", "toolArgs": "{}"})
        self.assertEqual((0, "allow"), (code, out["permissionDecision"]))

    def test_antigravity_auto_approves_pbibrain_so_nothing_is_asked(self):
        out, _, code = run_hook("antigravity", {"toolCall": {"name": "pbibrain/brain_object", "args": {}}, "stepIdx": 1}, self.project)
        self.assertEqual((0, "auto_approve"), (code, out["decision"]))
        for name in ("view_file", "grep_search", "run_command", "read_url_content", "invoke_subagent", "list_dir"):
            out, _, code = run_hook("antigravity", {"toolCall": {"name": name, "args": {}}}, self.project)
            self.assertEqual((0, "deny"), (code, out["decision"]), name)

    def test_a_broken_call_is_denied(self):
        _, err, code = run_hook("claude", "this is not json", self.project)
        self.assertEqual(2, code)
        self.assertIn("could not read the call", err)
        out, _, _ = run_hook("antigravity", "[1, 2]", self.project)
        self.assertEqual("deny", out["decision"])

    def test_the_user_can_switch_it_off_and_every_call_is_logged(self):
        (self.project / ".pbibrain" / "agent-policy.json").write_text('{"mode": "off"}', encoding="utf-8")
        out, _, code = run_hook("claude", {"hook_event_name": "PreToolUse", "tool_name": "Read", "tool_input": {}}, self.project)
        self.assertEqual((0, "allow"), (code, out["hookSpecificOutput"]["permissionDecision"]))
        lines = (self.project / ".pbibrain" / "agent-hook.log").read_text(encoding="utf-8").splitlines()
        self.assertEqual({"client": "claude", "tool": "Read", "decision": "allow"},
                         {key: json.loads(lines[-1])[key] for key in ("client", "tool", "decision")})

    def test_session_start_adds_the_saved_rules(self):
        (self.project / ".pbibrain" / "agent-context.md").write_text("# Rules\nUse brain_dependencies.", encoding="utf-8")
        out, _, code = run_hook("claude", {"hook_event_name": "SessionStart"}, self.project, event="session")
        self.assertEqual(0, code)
        self.assertIn("Use brain_dependencies.", out["hookSpecificOutput"]["additionalContext"])
        out, _, _ = run_hook("copilot", {}, self.project, event="session")
        self.assertIn("Use brain_dependencies.", out["additionalContext"])
        out, _, _ = run_hook("antigravity", {}, self.project, event="session")
        self.assertIn("Use brain_dependencies.", out["injectSteps"][0]["systemMessage"]["systemMessage"])

    def test_every_registry_tool_passes_the_boundary(self):
        from backend.tool_registry import build_tools

        names = set(build_tools(object(), freshness=lambda: {}))
        self.assertEqual(set(), names - agent_hook.PBIBRAIN_TOOLS, "a new tool must be added to the hook's list")
        for name in names:
            self.assertEqual("allow_pbibrain", agent_hook.classify(f"mcp__pbibrain__{name}", {})[0], name)


class HookSetupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "Finance Reports"
        (self.root / ".pbibrain").mkdir(parents=True)
        self.config = self.root / ".pbibrain" / "brain.json"
        self.config.write_text('{"version": 1, "sources": []}', encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def read(self, relative: str):
        return json.loads((self.root / relative).read_text(encoding="utf-8"))

    def test_each_client_gets_hooks_that_run(self):
        report = setup(self.config)
        self.assertEqual({"written"}, {item["result"] for item in report["files"]})
        claude = self.read(".claude/settings.json")
        self.assertIn("pbibrain", claude["enabledMcpjsonServers"])
        self.assertIn("mcp__pbibrain", claude["permissions"]["allow"])
        command = claude["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
        done = subprocess.run(command, shell=True, input=json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Glob",
                                                                      "tool_input": {"pattern": "**/*.tmdl"}}).encode(),
                              capture_output=True, timeout=30)
        self.assertEqual(2, done.returncode, done.stderr)
        self.assertIn("SessionStart", claude["hooks"])
        copilot = self.read(".github/hooks/pbibrain.json")
        self.assertEqual(1, copilot["version"])
        entry = copilot["hooks"]["preToolUse"][0]
        self.assertTrue(entry["powershell"].startswith("& '"))
        done = subprocess.run(entry["bash"], shell=True, input=b'{"toolName": "pbibrain-brain_search", "toolArgs": "{}"}',
                              capture_output=True, timeout=30)
        self.assertEqual("allow", json.loads(done.stdout)["permissionDecision"])
        codex = self.read(".codex/hooks.json")["hooks"]
        self.assertEqual(".*", codex["PreToolUse"][0]["matcher"])
        toml = (self.root / ".codex" / "config.toml").read_text(encoding="utf-8")
        self.assertIn('default_tools_approval_mode = "approve"', toml)
        self.assertTrue(toml.startswith(TOML_BEGIN), "top-level keys come before any table")
        agy = self.read(".agents/hooks.json")["pbibrain-boundary"]
        done = subprocess.run(agy["PreToolUse"][0]["hooks"][0]["command"], shell=True,
                              input=b'{"toolCall": {"name": "run_command", "args": {}}}', capture_output=True, timeout=30)
        self.assertEqual("deny", json.loads(done.stdout)["decision"])
        self.assertIn("proposal_check", (self.root / ".pbibrain" / "agent-context.md").read_text(encoding="utf-8"))

    def test_existing_settings_hooks_and_toml_are_kept(self):
        (self.root / ".claude").mkdir()
        (self.root / ".claude" / "settings.json").write_text(json.dumps({
            "permissions": {"allow": ["Bash(npm test)"]},
            "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "./mine.sh"}]}]}}), encoding="utf-8")
        (self.root / ".codex").mkdir()
        (self.root / ".codex" / "config.toml").write_text('model = "gpt-6.1-sol"\n\n[mcp_servers.github]\ncommand = "gh"\n',
                                                         encoding="utf-8")
        setup(self.config)
        again = {item["path"]: item["result"] for item in setup(self.config)["files"]}
        self.assertEqual("unchanged", again[".claude/settings.json"])
        self.assertEqual("unchanged", again[".codex/config.toml"])
        claude = self.read(".claude/settings.json")
        self.assertEqual(["./mine.sh"], [hook["command"] for hook in claude["hooks"]["PreToolUse"][0]["hooks"]])
        self.assertEqual(2, len(claude["hooks"]["PreToolUse"]), "one PBIBrain entry, not one per run")
        self.assertIn("Bash(npm test)", claude["permissions"]["allow"])
        import tomllib

        parsed = tomllib.loads((self.root / ".codex" / "config.toml").read_text(encoding="utf-8"))
        self.assertEqual("gpt-6.1-sol", parsed["model"])
        self.assertEqual("disabled", parsed["web_search"])
        self.assertEqual({"github", "pbibrain"}, set(parsed["mcp_servers"]))
        self.assertNotIn("model", parsed["mcp_servers"]["pbibrain"], "the user's top-level keys stay top-level")

    def test_a_hand_made_server_in_toml_is_not_touched(self):
        (self.root / ".codex").mkdir()
        (self.root / ".codex" / "config.toml").write_text('[mcp_servers.pbibrain]\ncommand = "mine"\n', encoding="utf-8")
        results = {item["path"]: item["result"] for item in setup(self.config, clients=("codex",))["files"]}
        self.assertTrue(results[".codex/config.toml"].startswith("skipped"))

    def test_command_lines_for_each_shell(self):
        argv = ["C:\\Program Files\\PBIBrain\\PBIBrain-Agent.exe", "agent-hook", "--project", "C:\\Reports\\It's"]
        self.assertEqual("& 'C:\\Program Files\\PBIBrain\\PBIBrain-Agent.exe' 'agent-hook' '--project' 'C:\\Reports\\It''s'",
                         command_line(argv, "powershell"))
        self.assertTrue(command_line(argv, "posix").startswith("'C:/Program Files/PBIBrain/PBIBrain-Agent.exe' agent-hook"))
        self.assertTrue(command_line(argv, "cmd").startswith('"C:\\Program Files\\PBIBrain\\PBIBrain-Agent.exe" agent-hook'))


if __name__ == "__main__":
    unittest.main()
