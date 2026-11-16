"""The models and thinking efforts each chat provider offers (Settings, AI provider; the chat pickers).

Where the provider can say which models it serves, the list is live: the Anthropic Models API
(with each model's effort levels from its ``capabilities``) and an OpenAI-compatible or local
``GET /models``. The subscription CLIs have no documented list command, so they get a built-in
catalog (Claude Code) or none, and the user adds the model names of their plan as favourites.

Effort is sent the way each provider documents it (checked 2026-11-16):

- Anthropic API: ``output_config.effort`` (low, medium, high, xhigh, max on current models).
- OpenAI-compatible: ``reasoning_effort`` (low, medium, high) on reasoning models only.
- Claude Code: ``--effort`` plus ``CLAUDE_CODE_EFFORT_LEVEL`` (the variable wins when both are set).
- Codex: ``-c model_reasoning_effort="..."`` (minimal, low, medium, high, xhigh).
- Copilot CLI: ``--reasoning-effort`` (low, medium, high), on the models that take it.
- Antigravity and local endpoints: none; Antigravity names the effort in the model ("... (High)").

An empty effort means "the provider's default": nothing is sent.
"""

from __future__ import annotations

import re
from typing import Any

ANTHROPIC_EFFORTS = ("low", "medium", "high", "xhigh", "max")
EFFORTS: dict[str, tuple[str, ...]] = {
    "anthropic": ANTHROPIC_EFFORTS,
    "openai": ("low", "medium", "high"),
    "local": (),
    "claude_code": ANTHROPIC_EFFORTS,
    "codex": ("minimal", "low", "medium", "high", "xhigh"),
    "copilot": ("low", "medium", "high"),
    "antigravity": (),
}

# (id, label, efforts, the model's own default effort). Cached 2026-11-03 from the Models API docs.
ANTHROPIC_CATALOG: tuple[tuple[str, str, tuple[str, ...], str], ...] = (
    ("claude-opus-5-5", "Claude Opus 5.5", ANTHROPIC_EFFORTS, "medium"),
    ("claude-sonnet-5-5", "Claude Sonnet 5.5", ANTHROPIC_EFFORTS, "high"),
    ("claude-haiku-5-5", "Claude Haiku 5.5", ANTHROPIC_EFFORTS, "medium"),
    ("claude-fable-5-2", "Claude Fable 5.2", ANTHROPIC_EFFORTS, "high"),
    ("claude-opus-5", "Claude Opus 5", ANTHROPIC_EFFORTS, "high"),
    ("claude-sonnet-5", "Claude Sonnet 5", ANTHROPIC_EFFORTS, "high"),
    ("claude-opus-4-8", "Claude Opus 4.8", ANTHROPIC_EFFORTS, "high"),
    ("claude-haiku-4-5", "Claude Haiku 4.5", (), ""),
)
CLAUDE_CODE_ALIASES = (("opus", "Opus (latest)"), ("sonnet", "Sonnet (latest)"), ("haiku", "Haiku (latest)"))
_REASONING_OPENAI = re.compile(r"^(o\d|gpt-5)", re.I)


def anthropic_efforts(model: str) -> tuple[str, ...]:
    """The effort levels of an Anthropic model by its id, for a model the live list did not describe."""

    for model_id, _, efforts, _ in ANTHROPIC_CATALOG:
        if model == model_id:
            return efforts
    name = model.lower()
    if re.match(r"claude-(fable|mythos)", name) or re.match(r"claude-(opus|sonnet|haiku)-5", name) or \
            re.match(r"claude-opus-4-[78]", name):
        return ANTHROPIC_EFFORTS
    if re.match(r"claude-(opus|sonnet)-4-6", name):
        return ("low", "medium", "high", "max")
    if re.match(r"claude-opus-4-5", name):
        return ("low", "medium", "high")
    return ()


def efforts_for(provider: str, model: str, live: dict[str, tuple[str, ...]] | None = None) -> tuple[str, ...]:
    """The effort levels the provider accepts for this model ("" model: the provider's default model)."""

    if live and model in live:
        return live[model]
    if provider == "anthropic":
        return anthropic_efforts(model)
    if provider == "openai":
        return EFFORTS["openai"] if _REASONING_OPENAI.match(model or "") else ()
    if provider == "claude_code":
        alias = (model or "").lower()
        if not alias or alias in {name for name, _ in CLAUDE_CODE_ALIASES}:
            return ANTHROPIC_EFFORTS
        return anthropic_efforts(model)
    return EFFORTS.get(provider, ())


def entry(model: str, label: str, efforts: tuple[str, ...], default: str = "", source: str = "catalog") -> dict[str, Any]:
    return {"id": model, "label": label or model or "Default of your plan", "efforts": list(efforts),
            "default_effort": default if default in efforts else "", "source": source}


def catalog(provider: str) -> list[dict[str, Any]]:
    """The built-in list of a provider; empty where only the user knows the names (their plan's models)."""

    if provider == "anthropic":
        return [entry(model, label, efforts, default) for model, label, efforts, default in ANTHROPIC_CATALOG]
    if provider == "claude_code":
        return ([entry("", "Default of your plan", ANTHROPIC_EFFORTS)]
                + [entry(alias, label, ANTHROPIC_EFFORTS) for alias, label in CLAUDE_CODE_ALIASES]
                + [entry(model, label, efforts, default) for model, label, efforts, default in ANTHROPIC_CATALOG])
    if provider in {"codex", "copilot", "antigravity"}:
        return [entry("", "Default of your plan", EFFORTS[provider])]
    return []


def anthropic_live(models: list[Any]) -> list[dict[str, Any]]:
    """Entries from the Anthropic Models API: each model's effort levels come from its capabilities."""

    found = []
    for model in models:
        model_id = str(getattr(model, "id", "") or "")
        if not model_id:
            continue
        capabilities = getattr(model, "capabilities", None) or {}
        effort = capabilities.get("effort") if isinstance(capabilities, dict) else None
        if isinstance(effort, dict) and effort.get("supported"):
            efforts = tuple(level for level in ANTHROPIC_EFFORTS if (effort.get(level) or {}).get("supported"))
        elif isinstance(effort, dict):
            efforts = ()
        else:
            efforts = anthropic_efforts(model_id)
        default = next((value for name, _, _, value in ANTHROPIC_CATALOG if name == model_id), "")
        found.append(entry(model_id, str(getattr(model, "display_name", "") or model_id), efforts, default, "live"))
    return found


def openai_live(provider: str, ids: list[str]) -> list[dict[str, Any]]:
    return [entry(model_id, model_id, efforts_for(provider, model_id), source="live") for model_id in ids if model_id]
