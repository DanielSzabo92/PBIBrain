"""AI provider settings of the in-app chat (issue #7).

The settings are per user, in the ``ai`` section of the PBIBrain settings file
(``%APPDATA%/PBIBrain/settings.json``; ``~/.pbibrain/settings.json`` elsewhere), next to the
``cloud`` section. The API key is never written there: it is in the OS credential store
(``credentials.py``). Chat is off by default and nothing is sent anywhere until the user
turns it on with a provider, a model and, where the provider needs one, a key.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

from .credentials import CredentialStore, credential_name

PROVIDERS: dict[str, dict[str, Any]] = {
    "anthropic": {"label": "Anthropic", "base_url": "https://api.anthropic.com", "model": "claude-opus-5-5", "needs_key": True},
    "openai": {"label": "OpenAI-compatible endpoint", "base_url": "https://api.openai.com/v1", "model": "", "needs_key": False},
    "local": {"label": "Local endpoint (Ollama, LM Studio)", "base_url": "http://localhost:11434/v1", "model": "llama3.1",
              "needs_key": False},
}
DEFAULT_PROVIDER = "anthropic"
MAX_KEY_CHARS = 512


def settings_path() -> Path:
    value = os.environ.get("APPDATA")
    if value:
        return Path(value) / "PBIBrain" / "settings.json"
    return Path.home() / ".pbibrain" / "settings.json"


def _clean_url(value: Any) -> str:
    text = str(value or "").strip().rstrip("/")
    if not text:
        return ""
    parts = urlsplit(text)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise ValueError("The base URL must start with http:// or https://")
    if parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError("The base URL cannot hold a user name, password, query or fragment")
    return text


class ChatSettings:
    """Read and save the ``ai`` settings; the key goes to ``store``."""

    def __init__(self, path: Path | None, store: CredentialStore) -> None:
        self.path = path
        self.store = store
        self._lock = threading.Lock()
        self._memory: dict[str, Any] = {}  # used when there is no settings file

    def _file(self) -> dict[str, Any]:
        if self.path is None:
            return dict(self._memory)
        if not self.path.is_file():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def stored(self) -> dict[str, Any]:
        """The effective settings, without the key."""

        raw = self._file().get("ai")
        raw = raw if isinstance(raw, Mapping) else {}
        provider = str(raw.get("provider") or DEFAULT_PROVIDER)
        if provider not in PROVIDERS:
            provider = DEFAULT_PROVIDER
        defaults = PROVIDERS[provider]
        try:
            base_url = _clean_url(raw.get("base_url")) or defaults["base_url"]
        except ValueError:
            base_url = defaults["base_url"]
        return {"enabled": raw.get("enabled") is True, "provider": provider,
                "model": str(raw.get("model") or defaults["model"]).strip(), "base_url": base_url}

    def api_key(self, settings: Mapping[str, Any] | None = None) -> str | None:
        current = settings or self.stored()
        try:
            return self.store.get(credential_name(current["provider"], current["base_url"]))
        except OSError:
            return None

    def public(self) -> dict[str, Any]:
        """What the page sees: never the key, only whether one is saved."""

        current = self.stored()
        has_key = bool(self.api_key(current))
        needs_key = PROVIDERS[current["provider"]]["needs_key"]
        reason = ""
        if not current["enabled"]:
            reason = "Chat is off. Turn it on in Settings, AI provider."
        elif not current["model"]:
            reason = "Choose a model in Settings, AI provider."
        elif needs_key and not has_key:
            reason = "Save an API key in Settings, AI provider."
        return {
            **current,
            "has_key": has_key,
            "key_store": self.store.label,
            "key_persistent": self.store.persistent,
            "ready": not reason,
            "reason": reason,
            "providers": [{"id": key, "label": value["label"], "base_url": value["base_url"], "model": value["model"],
                           "needs_key": value["needs_key"]} for key, value in PROVIDERS.items()],
        }

    def save(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        allowed = {"enabled", "provider", "model", "base_url", "api_key", "clear_key"}
        unknown = set(payload) - allowed
        if unknown:
            raise ValueError(f"Unknown AI setting: {sorted(unknown)[0]}")
        with self._lock:
            current = self.stored()
            provider = str(payload.get("provider", current["provider"]))
            if provider not in PROVIDERS:
                raise ValueError("The provider must be anthropic, openai or local")
            if provider != current["provider"] and "base_url" not in payload:
                base_url = PROVIDERS[provider]["base_url"]
            else:
                base_url = _clean_url(payload.get("base_url", current["base_url"])) or PROVIDERS[provider]["base_url"]
            model = str(payload.get("model", current["model"] if provider == current["provider"] else PROVIDERS[provider]["model"]))
            model = model.strip()
            if len(model) > 200:
                raise ValueError("The model name is too long")
            enabled = payload.get("enabled", current["enabled"])
            if not isinstance(enabled, bool):
                raise ValueError("enabled must be true or false")
            key = payload.get("api_key")
            if key is not None and (not isinstance(key, str) or len(key) > MAX_KEY_CHARS or any(ch.isspace() for ch in key.strip())):
                raise ValueError("The API key is not valid")
            name = credential_name(provider, base_url)
            if payload.get("clear_key") is True:
                self.store.delete(name)
            elif isinstance(key, str) and key.strip():
                self.store.set(name, key.strip())
            data = self._file()
            data["ai"] = {"enabled": enabled, "provider": provider, "model": model, "base_url": base_url}
            if self.path is None:
                self._memory = data
            else:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                temporary = self.path.with_suffix(".tmp")
                temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                temporary.replace(self.path)
        return self.public()
