"""Provider profiles, favourite models and thinking effort of the in-app chat.

1. Each provider keeps its own profile (model, URL or program, default effort); the default is
   the one saved last. A settings file of an older version (one flat provider) still loads.
2. Favourite models per provider, each with a default effort, narrow the chat's picker.
3. The chat picks a provider, model and effort per message; only a set-up provider can answer,
   and an effort the model does not take is refused.
4. ``GET chat/models`` lists the models and efforts: live where the provider can list them,
   else the built-in catalog.
5. The effort reaches each provider the way it documents it.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from backend.api.app import create_app
from backend.chat import cli_providers
from backend.chat.cli_providers import PRESETS, SubscriptionCLIProvider
from backend.chat.credentials import MemoryStore
from backend.chat.models import anthropic_efforts, anthropic_live, efforts_for
from backend.chat.providers import OpenAICompatibleProvider, ProviderError
from backend.chat.service import ChatService
from backend.chat.settings import ChatSettings
from tests.chat_fake_provider import ScriptedProvider
from tests.test_agent_guardrails import RecordingRunner


class ProfileTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "settings.json"
        self.settings = ChatSettings(self.path, MemoryStore())

    def test_an_older_flat_settings_file_becomes_the_default_profile(self) -> None:
        self.path.write_text(json.dumps({"ai": {"enabled": True, "provider": "local", "model": "qwen3:8b",
                                                "base_url": "http://localhost:1234/v1"}}), encoding="utf-8")
        public = self.settings.public()
        self.assertEqual(("local", "qwen3:8b", "http://localhost:1234/v1"), (public["provider"], public["model"], public["base_url"]))
        self.assertTrue(public["ready"])
        self.assertEqual(["local"], public["configured"])

    def test_each_provider_keeps_its_profile_and_the_last_saved_is_the_default(self) -> None:
        self.settings.save({"enabled": True, "provider": "local", "model": "qwen3:8b"})
        self.settings.save({"provider": "anthropic", "model": "claude-sonnet-5-5", "api_key": "sk-1", "effort": "high"})
        public = self.settings.public()
        self.assertEqual("anthropic", public["provider"])
        self.assertEqual({"anthropic", "local"}, set(public["configured"]))
        self.assertEqual("qwen3:8b", public["profiles"]["local"]["model"])
        self.assertEqual("high", public["profiles"]["anthropic"]["effort"])
        self.assertFalse(public["profiles"]["openai"]["configured"])
        # Saving the local profile again keeps the Anthropic one.
        self.settings.save({"provider": "local", "model": "llama3.1"})
        self.assertEqual("claude-sonnet-5-5", self.settings.public()["profiles"]["anthropic"]["model"])
        self.assertNotIn("sk-1", self.path.read_text(encoding="utf-8"))

    def test_effort_must_fit_the_model(self) -> None:
        self.assertEqual(("low", "medium", "high", "xhigh", "max"), efforts_for("anthropic", "claude-opus-5-5"))
        self.assertEqual((), efforts_for("anthropic", "claude-haiku-4-5"))
        self.assertEqual(("low", "medium", "high", "max"), anthropic_efforts("claude-sonnet-4-6"))
        self.assertEqual(("low", "medium", "high"), efforts_for("openai", "o4-mini"))
        self.assertEqual((), efforts_for("openai", "gpt-4.1"))
        self.assertEqual((), efforts_for("local", "llama3.1"))
        self.assertIn("minimal", efforts_for("codex", ""))
        with self.assertRaisesRegex(ValueError, "does not take the effort"):
            self.settings.save({"provider": "anthropic", "model": "claude-haiku-4-5", "effort": "low"})
        with self.assertRaisesRegex(ValueError, "does not take the effort"):
            self.settings.save({"provider": "local", "effort": "high"})

    def test_favourites_are_checked_per_provider(self) -> None:
        saved = self.settings.save({"favourites": {"anthropic": [{"model": "claude-opus-5-5", "effort": "xhigh"},
                                                                  {"model": "claude-haiku-5-5", "effort": ""},
                                                                  {"model": "claude-opus-5-5", "effort": "low"}],
                                                   "antigravity": [{"model": "Gemini 3.1 Pro (High)", "effort": ""}]}})
        self.assertEqual([{"model": "claude-opus-5-5", "effort": "xhigh"}, {"model": "claude-haiku-5-5", "effort": ""}],
                         saved["favourites"]["anthropic"])
        self.assertEqual("Gemini 3.1 Pro (High)", saved["favourites"]["antigravity"][0]["model"])
        # A favourites-only save changes no profile and no default.
        self.assertEqual("anthropic", saved["provider"])
        self.assertFalse(saved["enabled"])
        for bad in ({"nope": []}, {"anthropic": "x"}, {"anthropic": [{"model": "claude-haiku-4-5", "effort": "high"}]},
                    {"copilot": [{"model": "gpt; rm -rf /", "effort": ""}]}, {"anthropic": [{"model": "m", "colour": 1}]},
                    {"local": [{"model": f"m{index}", "effort": ""} for index in range(51)]}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.settings.save({"favourites": bad})


class SelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.app = create_app(use_sqlite=False)
        self.addCleanup(self.app.close)
        self.made: list[dict] = []

        def factory(settings, key):
            self.made.append(dict(settings))
            return ScriptedProvider(delay=0.001)

        self.chat = ChatService(self.app, settings_file=Path(temporary.name) / "settings.json", store=MemoryStore(),
                                provider_factory=factory, lock=self.app.request_lock)
        self.app.chat = self.chat
        self.settings = self.chat.settings

    def start(self, **body):
        reply = self.chat.start({"text": "hello", **body})
        run = self.chat._run(reply["run_id"])
        for _ in range(500):
            if run.done:
                break
            run.stop.wait(0.01)
        return self.made[-1]

    def test_the_chat_picks_a_set_up_provider_a_model_and_an_effort(self) -> None:
        self.settings.save({"enabled": True, "provider": "local", "model": "qwen3:8b"})
        self.settings.save({"provider": "anthropic", "model": "claude-opus-5-5", "api_key": "sk-1", "effort": "medium",
                            "favourites": {"anthropic": [{"model": "claude-sonnet-5-5", "effort": "low"}]}})
        self.assertEqual(("anthropic", "claude-opus-5-5", "medium"), tuple(self.start()[key] for key in ("provider", "model", "effort")))
        used = self.start(provider="anthropic", model="claude-sonnet-5-5")
        self.assertEqual(("claude-sonnet-5-5", "low"), (used["model"], used["effort"]), "the favourite's effort is the default")
        used = self.start(provider="anthropic", model="claude-sonnet-5-5", effort="xhigh")
        self.assertEqual("xhigh", used["effort"])
        used = self.start(provider="local")
        self.assertEqual(("local", "qwen3:8b", ""), (used["provider"], used["model"], used["effort"]))

    def test_a_provider_that_is_not_set_up_or_a_wrong_effort_is_refused(self) -> None:
        self.settings.save({"enabled": True, "provider": "local", "model": "qwen3:8b"})
        with self.assertRaisesRegex(ValueError, "Set up this provider"):
            self.chat.start({"text": "hi", "provider": "openai", "model": "gpt-5"})
        with self.assertRaisesRegex(ValueError, "does not take the effort"):
            self.chat.start({"text": "hi", "provider": "local", "effort": "high"})
        with self.assertRaisesRegex(ValueError, "API key"):
            self.chat.start({"text": "hi", "provider": "anthropic"})
        self.settings.save({"enabled": False})
        with self.assertRaisesRegex(ValueError, "Chat is off"):
            self.chat.start({"text": "hi"})

    def test_models_are_live_where_the_provider_lists_them(self) -> None:
        self.settings.save({"enabled": True, "provider": "local", "model": "qwen3:8b"})
        self.chat.provider_factory = lambda settings, key: SimpleNamespace(list_models=lambda: ["qwen3:8b", "llama3.1"])
        reply = self.chat.models("local")
        self.assertEqual(("live", ["qwen3:8b", "llama3.1"]), (reply["source"], [item["id"] for item in reply["models"]]))
        self.assertEqual([], reply["models"][0]["efforts"])

        def broken(settings, key):
            raise ProviderError("Could not reach localhost.")

        self.chat.provider_factory = broken
        reply = self.chat.models("local", refresh=True)
        self.assertEqual(("catalog", "Could not reach localhost."), (reply["source"], reply["error"]))
        claude = self.chat.models("claude_code")
        self.assertEqual("catalog", claude["source"])
        self.assertEqual(["", "opus", "sonnet", "haiku"], [item["id"] for item in claude["models"]][:4])
        self.assertEqual("medium", next(item for item in claude["models"] if item["id"] == "claude-opus-5-5")["default_effort"])
        with self.assertRaises(ValueError):
            self.chat.models("gemini_cli")

    def test_the_anthropic_list_reads_efforts_from_capabilities(self) -> None:
        model = SimpleNamespace(id="claude-new-6", display_name="Claude New 6", capabilities={
            "effort": {"supported": True, "low": {"supported": True}, "medium": {"supported": True},
                       "high": {"supported": True}, "xhigh": {"supported": False}, "max": {"supported": True}}})
        plain = SimpleNamespace(id="claude-haiku-4-5", display_name="Claude Haiku 4.5", capabilities={"effort": {"supported": False}})
        [new, haiku] = anthropic_live([model, plain])
        self.assertEqual((["low", "medium", "high", "max"], "Claude New 6"), (new["efforts"], new["label"]))
        self.assertEqual([], haiku["efforts"])

    def test_the_http_route(self) -> None:
        status, reply = self.app.handle("GET", "/api/chat/models?provider=codex")
        self.assertEqual(200, status, reply)
        self.assertEqual(["minimal", "low", "medium", "high", "xhigh"], reply["efforts"])


class EffortWiringTests(unittest.TestCase):
    def setUp(self) -> None:
        patcher = mock.patch.object(cli_providers, "find_program", lambda preset, command="": "/usr/bin/" + PRESETS[preset]["executable"])
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_cli(self, preset: str, output: bytes = b"OK\n", **options):
        runner = RecordingRunner(output)
        provider = SubscriptionCLIProvider(preset=preset, runner=runner, **options)
        list(provider.stream(system="S", messages=[{"role": "user", "content": [{"type": "text", "text": "q"}]}], tools=[],
                             should_stop=lambda: False))
        return runner.calls[0]

    def test_each_cli_gets_the_effort_its_way(self) -> None:
        call = self.run_cli("claude_code", b'{"type":"result","is_error":false,"result":"OK"}\n', model="opus", effort="xhigh")
        self.assertEqual("xhigh", call["command"][call["command"].index("--effort") + 1])
        self.assertEqual("xhigh", call["env"]["CLAUDE_CODE_EFFORT_LEVEL"])
        call = self.run_cli("codex", effort="high")
        self.assertIn('model_reasoning_effort="high"', call["command"])
        self.assertEqual("-", call["command"][-1], "the prompt still comes from stdin")
        call = self.run_cli("copilot", effort="medium")
        self.assertIn("--reasoning-effort=medium", call["command"])
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_EFFORT_LEVEL": "max"}):
            call = self.run_cli("claude_code", b'{"type":"result","is_error":false,"result":"OK"}\n')
        self.assertNotIn("--effort", call["command"])
        self.assertEqual("max", call["env"]["CLAUDE_CODE_EFFORT_LEVEL"], "no effort picked: the user's own Claude Code setting stays")

    def test_antigravity_takes_display_names_and_no_effort(self) -> None:
        output = b'{"event":"result","result":{"status":"SUCCESS","response":"OK"}}\n'
        call = self.run_cli("antigravity", output, model="Gemini 3.1 Pro (High)")
        self.assertEqual("Gemini 3.1 Pro (High)", call["command"][call["command"].index("--model") + 1])
        with self.assertRaises(ProviderError):
            SubscriptionCLIProvider(preset="antigravity", effort="high")
        with self.assertRaises(ProviderError):
            SubscriptionCLIProvider(preset="codex", effort='high" -c x="y')
        with self.assertRaises(ProviderError):
            SubscriptionCLIProvider(preset="codex", model="Gemini Pro")

    def test_an_openai_compatible_request_carries_reasoning_effort(self) -> None:
        sent = {}

        class Response:
            def __enter__(self):
                return iter([b'data: {"choices":[{"delta":{"content":"OK"},"finish_reason":"stop"}]}\n', b"data: [DONE]\n"])

            def __exit__(self, *args):
                return False

        provider = OpenAICompatibleProvider(model="o4-mini", api_key="k", base_url="https://api.example.com/v1", effort="high")
        provider._open = lambda request: (sent.update(json.loads(request.data)), Response())[1]
        list(provider.stream(system="S", messages=[{"role": "user", "content": [{"type": "text", "text": "q"}]}], tools=[],
                             should_stop=lambda: False))
        self.assertEqual("high", sent["reasoning_effort"])


if __name__ == "__main__":
    unittest.main()
