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
from typing import Any
from collections.abc import Mapping
from urllib.parse import urlsplit

from .cli_providers import PRESETS as CLI_PRESETS, find_program, validate_command, validate_model
from .credentials import CredentialStore, credential_name
from .models import EFFORTS, efforts_for

PROVIDERS: dict[str, dict[str, Any]] = {
    "anthropic": {"label": "Anthropic API key", "base_url": "https://api.anthropic.com", "model": "claude-opus-5-5", "needs_key": True},
    "openai": {"label": "OpenAI-compatible endpoint", "base_url": "https://api.openai.com/v1", "model": "", "needs_key": False},
    "local": {"label": "Local endpoint (Ollama, LM Studio)", "base_url": "http://localhost:11434/v1", "model": "llama3.1",
              "needs_key": False},
    # Subscriptions through the vendor's signed-in CLI (backend/chat/cli_providers.py): no key, no URL;
    # an empty model means the CLI's own default.
    **{name: {"label": preset["label"], "base_url": "", "model": "", "needs_key": False, "kind": "cli",
              "executable": preset["executable"], "sign_in": preset["sign_in"]} for name, preset in CLI_PRESETS.items()},
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


FAVOURITES_PER_PROVIDER = 50
SETTING_KEYS = {"enabled", "provider", "model", "base_url", "api_key", "clear_key", "command", "effort", "favourites"}


class ChatSettings:
    """Read and save the ``ai`` settings; the key goes to ``store``.

    Each provider keeps its own profile (model, base URL or program, default effort), so the chat
    can switch between the ones that are set up. ``provider`` is the default one. ``favourites``
    narrows the chat's model picker per provider: ``[{model, effort}]``.
    """

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

    def _raw(self) -> dict[str, Any]:
        """The ``ai`` section with profiles; the flat form of older versions becomes the default's profile."""

        raw = self._file().get("ai")
        raw = dict(raw) if isinstance(raw, Mapping) else {}
        provider = str(raw.get("provider") or DEFAULT_PROVIDER)
        if provider not in PROVIDERS:
            provider = DEFAULT_PROVIDER
        profiles = raw.get("profiles") if isinstance(raw.get("profiles"), Mapping) else {}
        profiles = {key: dict(value) for key, value in profiles.items() if key in PROVIDERS and isinstance(value, Mapping)}
        if provider not in profiles and any(key in raw for key in ("model", "base_url", "command")):
            profiles[provider] = {key: raw[key] for key in ("model", "base_url", "command", "effort") if key in raw}
        favourites = raw.get("favourites") if isinstance(raw.get("favourites"), Mapping) else {}
        return {"enabled": raw.get("enabled") is True, "provider": provider, "profiles": profiles,
                "favourites": {key: value for key, value in favourites.items() if key in PROVIDERS and isinstance(value, list)}}

    def profile(self, provider: str, raw: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """The effective profile of one provider, without the key."""

        raw = raw or self._raw()
        saved = raw["profiles"].get(provider, {})
        defaults = PROVIDERS[provider]
        if is_cli(provider):
            base_url = ""
            try:
                command = validate_command(provider, str(saved.get("command") or ""))
            except ValueError:
                command = ""
        else:
            command = ""
            try:
                base_url = _clean_url(saved.get("base_url")) or defaults["base_url"]
            except ValueError:
                base_url = defaults["base_url"]
        model = str(saved.get("model") if "model" in saved else defaults["model"]).strip()
        effort = str(saved.get("effort") or "")
        if effort not in efforts_for(provider, model):
            effort = ""
        return {"provider": provider, "model": model, "base_url": base_url, "command": command, "effort": effort}

    def stored(self) -> dict[str, Any]:
        """The effective settings of the default provider, without the key."""

        raw = self._raw()
        return {"enabled": raw["enabled"], **self.profile(raw["provider"], raw)}

    def api_key(self, settings: Mapping[str, Any] | None = None) -> str | None:
        current = settings or self.stored()
        if is_cli(current["provider"]):
            return None  # a subscription CLI signs in by itself; no key is ever sent to it
        try:
            return self.store.get(credential_name(current["provider"], current["base_url"]))
        except OSError:
            return None

    def _status(self, profile: Mapping[str, Any]) -> tuple[bool, str]:
        """(has_key, the reason the profile cannot answer or "") ignoring the on/off switch."""

        provider = profile["provider"]
        has_key = bool(self.api_key(profile))
        if is_cli(provider) and find_program(provider, profile["command"]) is None:
            return has_key, f"The {PROVIDERS[provider]['executable']} program was not found. {PROVIDERS[provider]['sign_in']}"
        if not profile["model"] and not is_cli(provider):
            return has_key, "Choose a model in Settings, AI provider."
        if PROVIDERS[provider]["needs_key"] and not has_key:
            return has_key, "Save an API key in Settings, AI provider."
        return has_key, ""

    def favourites(self, raw: Mapping[str, Any] | None = None) -> dict[str, list[dict[str, str]]]:
        raw = raw or self._raw()
        clean: dict[str, list[dict[str, str]]] = {}
        for provider, items in raw["favourites"].items():
            try:
                clean[provider] = _clean_favourites(provider, items)
            except ValueError:
                continue
        return clean

    def public(self) -> dict[str, Any]:
        """What the page sees: never the key, only whether one is saved."""

        raw = self._raw()
        current = {"enabled": raw["enabled"], **self.profile(raw["provider"], raw)}
        has_key, problem = self._status(current)
        reason = "Chat is off. Turn it on in Settings, AI provider." if not current["enabled"] else problem
        profiles = {}
        for key in PROVIDERS:
            item = self.profile(key, raw)
            item_key, item_problem = self._status(item)
            # A provider counts as set up when the user saved it once (or it is the default) and it can answer.
            saved = key in raw["profiles"] or key == raw["provider"]
            profiles[key] = {**item, "has_key": item_key, "configured": saved and not item_problem,
                             "reason": item_problem if saved else "Not set up yet."}
        return {
            **current,
            "has_key": has_key,
            "key_store": self.store.label,
            "key_persistent": self.store.persistent,
            "ready": not reason,
            "reason": reason,
            "profiles": profiles,
            "configured": [key for key, value in profiles.items() if value["configured"]],
            "favourites": self.favourites(raw),
            "providers": [{"id": key, "label": value["label"], "base_url": value["base_url"], "model": value["model"],
                           "needs_key": value["needs_key"], "kind": value.get("kind", "api"),
                           "efforts": list(EFFORTS.get(key, ())),
                           **({"executable": value["executable"], "sign_in": value["sign_in"]} if value.get("kind") == "cli" else {})}
                          for key, value in PROVIDERS.items()],
        }

    def selection(self, provider: Any = None, model: Any = None, effort: Any = None) -> dict[str, Any]:
        """The profile a chat run uses: the default, or the provider, model and effort the chat picked."""

        raw = self._raw()
        if not raw["enabled"]:
            raise ValueError("Chat is off. Turn it on in Settings, AI provider.")
        name = str(provider or raw["provider"])
        if name not in PROVIDERS:
            raise ValueError("The provider must be one of: " + ", ".join(PROVIDERS))
        current = self.profile(name, raw)
        if model is not None:
            current["model"] = _clean_model(name, model)
            current["effort"] = self._favourite_effort(raw, name, current["model"])
        if effort is not None:
            current["effort"] = _clean_effort(name, current["model"], effort)
        _, problem = self._status(current)
        if problem:
            raise ValueError(problem)
        if name != raw["provider"] and name not in raw["profiles"]:
            raise ValueError("Set up this provider in Settings, AI provider first.")
        return current

    def _favourite_effort(self, raw: Mapping[str, Any], provider: str, model: str) -> str:
        for item in self.favourites(raw).get(provider, []):
            if item["model"] == model:
                return item["effort"]
        return ""

    def save(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        unknown = set(payload) - SETTING_KEYS
        if unknown:
            raise ValueError(f"Unknown AI setting: {sorted(unknown)[0]}")
        with self._lock:
            raw = self._raw()
            if "favourites" in payload:
                raw["favourites"] = {**raw["favourites"], **_clean_all_favourites(payload["favourites"])}
            if set(payload) <= {"favourites"}:
                self._write(raw)
                return self.public()
            current = {"enabled": raw["enabled"], **self.profile(raw["provider"], raw)}
            provider = str(payload.get("provider", current["provider"]))
            if provider not in PROVIDERS:
                raise ValueError("The provider must be one of: " + ", ".join(PROVIDERS))
            saved = self.profile(provider, raw)
            enabled = payload.get("enabled", current["enabled"])
            if not isinstance(enabled, bool):
                raise ValueError("enabled must be true or false")
            if is_cli(provider):
                profile = self._cli_profile(payload, saved, provider)
            else:
                profile = self._api_profile(payload, saved, provider)
            profile["effort"] = _clean_effort(provider, profile["model"], payload.get("effort", saved["effort"]))
            raw["profiles"][provider] = profile
            raw["provider"] = provider
            raw["enabled"] = enabled
            self._write(raw)
        return self.public()

    def _api_profile(self, payload: Mapping[str, Any], saved: Mapping[str, Any], provider: str) -> dict[str, Any]:
        base_url = _clean_url(payload.get("base_url", saved["base_url"])) or PROVIDERS[provider]["base_url"]
        model = _clean_model(provider, payload.get("model", saved["model"]))
        key = payload.get("api_key")
        if key is not None and (not isinstance(key, str) or len(key) > MAX_KEY_CHARS or any(ch.isspace() for ch in key.strip())):
            raise ValueError("The API key is not valid")
        name = credential_name(provider, base_url)
        if payload.get("clear_key") is True:
            self.store.delete(name)
        elif isinstance(key, str) and key.strip():
            self.store.set(name, key.strip())
        return {"model": model, "base_url": base_url}

    def _cli_profile(self, payload: Mapping[str, Any], saved: Mapping[str, Any], provider: str) -> dict[str, Any]:
        """A subscription CLI: no key and no URL are accepted; the model and the program path are checked."""

        if isinstance(payload.get("api_key"), str) and payload["api_key"].strip():
            raise ValueError("This provider uses your subscription sign-in in its own program. It takes no API key.")
        if str(payload.get("base_url") or "").strip():
            raise ValueError("This provider runs a program on this computer. It takes no base URL.")
        model = _clean_model(provider, payload.get("model", saved["model"]))
        command = validate_command(provider, str(payload.get("command", saved["command"])))
        return {"model": model, "command": command}

    def _write(self, raw: Mapping[str, Any]) -> None:
        data = self._file()
        data["ai"] = {"enabled": raw["enabled"], "provider": raw["provider"], "profiles": dict(raw["profiles"]),
                      "favourites": dict(raw["favourites"])}
        if self.path is None:
            self._memory = data
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            temporary.replace(self.path)


def _clean_model(provider: str, value: Any) -> str:
    model = str(value or "").strip()
    if len(model) > 200:
        raise ValueError("The model name is too long")
    if is_cli(provider):
        return validate_model(model, spaces=provider == "antigravity")
    if model and any(ch.isspace() or ord(ch) < 32 for ch in model):
        raise ValueError("The model name cannot hold spaces")
    return model


def _clean_effort(provider: str, model: str, value: Any) -> str:
    effort = str(value or "").strip().lower()
    if effort and effort not in efforts_for(provider, model):
        allowed = ", ".join(efforts_for(provider, model)) or "none"
        raise ValueError(f"This model does not take the effort {effort}. It takes: {allowed}")
    return effort


def _clean_favourites(provider: str, items: Any) -> list[dict[str, str]]:
    if not isinstance(items, list) or len(items) > FAVOURITES_PER_PROVIDER:
        raise ValueError(f"Favourites are a list of at most {FAVOURITES_PER_PROVIDER} models per provider")
    clean, seen = [], set()
    for item in items:
        if not isinstance(item, Mapping) or set(item) - {"model", "effort"}:
            raise ValueError("A favourite is {model, effort}")
        model = _clean_model(provider, item.get("model"))
        if model in seen:
            continue
        seen.add(model)
        clean.append({"model": model, "effort": _clean_effort(provider, model, item.get("effort"))})
    return clean


def _clean_all_favourites(value: Any) -> dict[str, list[dict[str, str]]]:
    if not isinstance(value, Mapping):
        raise ValueError("favourites is an object of provider: [{model, effort}]")
    unknown = [key for key in value if key not in PROVIDERS]
    if unknown:
        raise ValueError(f"Unknown provider in favourites: {unknown[0]}")
    return {provider: _clean_favourites(provider, items) for provider, items in value.items()}


def is_cli(provider: str) -> bool:
    return PROVIDERS.get(provider, {}).get("kind") == "cli"
