"""AI providers of the in-app chat (issue #7). Calls go from the backend, never the page.

Messages use one neutral shape, the Anthropic content blocks: ``text``, ``tool_use``
``{id, name, input}`` and ``tool_result`` ``{tool_use_id, content, is_error}``. Each provider
turns them into its own wire format.

- ``AnthropicProvider`` uses the official ``anthropic`` SDK (optional extra ``[chat]``).
- ``OpenAICompatibleProvider`` speaks ``/chat/completions`` with streaming. It serves both
  OpenAI-compatible cloud endpoints and local ones such as Ollama or LM Studio; with a local
  base URL nothing leaves the machine.

``stream`` yields ``{"type": "text", "text"}`` while the answer arrives and ends with one
``{"type": "message", "content": [...], "stop_reason"}``. ``should_stop`` is checked between
chunks so the Stop button closes the connection.
"""

from __future__ import annotations

import json
from typing import Any
from collections.abc import Callable, Iterator, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, Request, build_opener

MAX_TOKENS = 32_000
TIMEOUT_SECONDS = 120
ANTHROPIC_URL = "https://api.anthropic.com"
# Models that take the server-side refusal fallback in its "default" form on the Claude API.
FALLBACK_MODELS = frozenset({"claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5"})
FALLBACK_BETA = "server-side-fallback-2026-07-01"
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}

Event = dict[str, Any]


class ProviderError(RuntimeError):
    """A provider failure, with a message the user can act on."""


def _http_message(status: int, detail: str = "") -> str:
    if status in {401, 403}:
        return f"The provider refused the API key (HTTP {status}). Check the key in Settings, AI provider."
    if status == 404:
        return "The provider does not know this model or URL (HTTP 404). Check the model and base URL."
    if status == 429:
        return "The provider is rate limiting requests (HTTP 429). Wait a moment and try again."
    text = f"The provider returned HTTP {status}."
    return f"{text} {detail[:300]}" if detail else text


class AnthropicProvider:
    def __init__(self, *, model: str, api_key: str | None, base_url: str = ANTHROPIC_URL) -> None:
        try:
            import anthropic
        except ImportError as exc:
            raise ProviderError('The Anthropic provider needs the optional package: python -m pip install -e ".[chat]"') from exc
        self._sdk = anthropic
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.client = anthropic.Anthropic(api_key=api_key, base_url=self.base_url, max_retries=2, timeout=TIMEOUT_SECONDS)

    def _error(self, exc: Exception) -> ProviderError:
        sdk = self._sdk
        if isinstance(exc, sdk.APIStatusError):
            return ProviderError(_http_message(exc.status_code, getattr(exc, "message", "")))
        if isinstance(exc, sdk.APIConnectionError):
            return ProviderError(f"Could not reach {urlsplit(self.base_url).hostname}. Check the network and the base URL.")
        return ProviderError(str(exc) or exc.__class__.__name__)

    def test(self) -> dict[str, Any]:
        try:
            model = self.client.models.retrieve(self.model)
        except self._sdk.NotFoundError:
            return {"ok": False, "message": f"The key works, but the model {self.model} is not available to it."}
        except self._sdk.APIError as exc:
            return {"ok": False, "message": str(self._error(exc))}
        return {"ok": True, "message": f"Connected. {getattr(model, 'display_name', '') or self.model} is available."}

    def stream(self, *, system: str, messages: Sequence[Mapping[str, Any]], tools: Sequence[Mapping[str, Any]],
               should_stop: Callable[[], bool]) -> Iterator[Event]:
        request: dict[str, Any] = {
            "model": self.model, "max_tokens": MAX_TOKENS, "system": system, "messages": list(messages),
            "tools": [{"name": tool["name"], "description": tool["description"], "input_schema": tool["input_schema"]} for tool in tools],
            # The tools and the system prompt are the same on every turn: a stable, cacheable prefix.
            "cache_control": {"type": "ephemeral"},
        }
        if self.model in FALLBACK_MODELS and self.base_url == ANTHROPIC_URL:
            # A refusal is retried on a fallback model chosen by the server.
            opened = self.client.beta.messages.stream(**request, betas=[FALLBACK_BETA], fallbacks="default")
        else:
            opened = self.client.messages.stream(**request)
        stopped = False
        try:
            with opened as stream:
                for event in stream:
                    if should_stop():
                        stopped = True
                        break
                    if event.type == "text" and event.text:
                        yield {"type": "text", "text": event.text}
                if stopped:
                    yield {"type": "message", "content": [], "stop_reason": "stopped"}
                    return
                final = stream.get_final_message()
        except self._sdk.APIError as exc:
            raise self._error(exc) from exc
        content = [block.model_dump(mode="json", by_alias=True, exclude_none=True) for block in final.content]
        yield {"type": "message", "content": content, "stop_reason": final.stop_reason or "end_turn"}


class OpenAICompatibleProvider:
    def __init__(self, *, model: str, api_key: str | None, base_url: str) -> None:
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        host = urlsplit(self.base_url).hostname or ""
        # A local endpoint is reached directly, never through a proxy.
        self.opener = build_opener(ProxyHandler({})) if host in LOCAL_HOSTS else build_opener()

    def _request(self, path: str, body: Mapping[str, Any] | None = None) -> Request:
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode("utf-8")
        return Request(f"{self.base_url}/{path}", data=data, headers=headers, method="POST" if data else "GET")

    def _open(self, request: Request) -> Any:
        try:
            return self.opener.open(request, timeout=TIMEOUT_SECONDS)
        except HTTPError as exc:
            try:
                detail = json.loads(exc.read() or b"{}").get("error", "")
                detail = detail.get("message", "") if isinstance(detail, Mapping) else str(detail)
            except (ValueError, AttributeError, OSError):
                detail = ""
            raise ProviderError(_http_message(exc.code, detail)) from exc
        except (URLError, OSError) as exc:
            host = urlsplit(self.base_url).hostname
            raise ProviderError(f"Could not reach {host}. Check the base URL and that the endpoint is running.") from exc

    def test(self) -> dict[str, Any]:
        try:
            with self._open(self._request("models")) as response:
                ids = [str(item.get("id")) for item in json.load(response).get("data") or [] if isinstance(item, Mapping)]
        except ProviderError as exc:
            return {"ok": False, "message": str(exc)}
        except (ValueError, AttributeError):
            return {"ok": False, "message": "The endpoint answered, but not with an OpenAI-compatible model list."}
        if ids and self.model not in ids:
            return {"ok": False, "message": f"Connected, but the endpoint has no model {self.model}. It has: {', '.join(ids[:8])}."}
        return {"ok": True, "message": f"Connected. {self.model} is available." if ids else "Connected."}

    @staticmethod
    def wire_messages(system: str, messages: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        wire: list[dict[str, Any]] = [{"role": "system", "content": system}]
        for message in messages:
            blocks = message["content"] if isinstance(message["content"], list) else [{"type": "text", "text": message["content"]}]
            text = "\n\n".join(block.get("text", "") for block in blocks if block.get("type") == "text")
            if message["role"] == "assistant":
                calls = [{"id": block["id"], "type": "function",
                          "function": {"name": block["name"], "arguments": json.dumps(block.get("input") or {})}}
                         for block in blocks if block.get("type") == "tool_use"]
                item: dict[str, Any] = {"role": "assistant", "content": text or None}
                if calls:
                    item["tool_calls"] = calls
                wire.append(item)
                continue
            for block in blocks:
                if block.get("type") == "tool_result":
                    wire.append({"role": "tool", "tool_call_id": block["tool_use_id"], "content": str(block.get("content", ""))})
            if text:
                wire.append({"role": "user", "content": text})
        return wire

    def stream(self, *, system: str, messages: Sequence[Mapping[str, Any]], tools: Sequence[Mapping[str, Any]],
               should_stop: Callable[[], bool]) -> Iterator[Event]:
        body = {
            "model": self.model, "stream": True, "messages": self.wire_messages(system, messages),
            "tools": [{"type": "function", "function": {"name": tool["name"], "description": tool["description"],
                                                        "parameters": tool["input_schema"]}} for tool in tools],
        }
        text: list[str] = []
        calls: dict[int, dict[str, str]] = {}
        finish = "end_turn"
        with self._open(self._request("chat/completions", body)) as response:
            for raw in response:
                if should_stop():
                    yield {"type": "message", "content": [], "stop_reason": "stopped"}
                    return
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except ValueError:
                    continue
                if isinstance(chunk.get("error"), Mapping):
                    raise ProviderError(f"The provider stopped with an error: {chunk['error'].get('message', '')}"[:400])
                for choice in chunk.get("choices") or []:
                    delta = choice.get("delta") or {}
                    if delta.get("content"):
                        text.append(delta["content"])
                        yield {"type": "text", "text": delta["content"]}
                    for call in delta.get("tool_calls") or []:
                        slot = calls.setdefault(int(call.get("index", len(calls))), {"id": "", "name": "", "arguments": ""})
                        function = call.get("function") or {}
                        slot["id"] = call.get("id") or slot["id"]
                        slot["name"] += function.get("name") or ""
                        slot["arguments"] += function.get("arguments") or ""
                    if choice.get("finish_reason"):
                        finish = {"tool_calls": "tool_use", "length": "max_tokens"}.get(choice["finish_reason"], "end_turn")
        content: list[dict[str, Any]] = [{"type": "text", "text": "".join(text)}] if text else []
        for index, call in sorted(calls.items()):
            try:
                arguments = json.loads(call["arguments"] or "{}")
            except ValueError:
                arguments = {"__invalid_json__": call["arguments"]}
            content.append({"type": "tool_use", "id": call["id"] or f"call_{index}", "name": call["name"],
                            "input": arguments if isinstance(arguments, dict) else {"__invalid_json__": call["arguments"]}})
        yield {"type": "message", "content": content, "stop_reason": "tool_use" if calls else finish}


def create_provider(settings: Mapping[str, Any], api_key: str | None) -> Any:
    if settings["provider"] == "anthropic":
        return AnthropicProvider(model=settings["model"], api_key=api_key, base_url=settings["base_url"])
    return OpenAICompatibleProvider(model=settings["model"], api_key=api_key, base_url=settings["base_url"])
