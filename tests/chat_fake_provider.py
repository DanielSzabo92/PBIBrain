"""A scripted AI provider for the chat tests and the browser e2e (issue #7). No network.

The last user message picks the script:

- "search <words>": calls brain_search, then answers with an object link to the first hit.
- "propose": reads session_get, submits an object_edit proposal for the selected object, and
  says it is waiting for the user.
- "accept": tries to call a tool that does not exist (``proposal_accept``); the chat refuses it.
- "fail": the provider fails (an HTTP 401-like error).
- "slow": streams many small chunks with a pause, so a Stop can land mid-answer.
- anything else: streams a short answer in a few chunks.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, Callable, Iterator, Mapping, Sequence

from backend.chat.providers import ProviderError


def _last_user_text(messages: Sequence[Mapping[str, Any]]) -> str:
    for message in reversed(messages):
        if message["role"] != "user":
            continue
        texts = [block["text"] for block in message["content"] if block.get("type") == "text"]
        if texts:
            return texts[-1]
    return ""


def _context(messages: Sequence[Mapping[str, Any]]) -> str:
    for message in reversed(messages):
        for block in message["content"] if message["role"] == "user" else []:
            if block.get("type") == "text" and block["text"].startswith("<context>"):
                return block["text"]
    return ""


def _tool_results(messages: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """The tool results of this answer so far (after the last user text turn)."""

    results: list[dict[str, Any]] = []
    for message in reversed(messages):
        blocks = message["content"]
        if message["role"] == "user" and any(block.get("type") == "text" for block in blocks):
            break
        results[:0] = [block for block in blocks if block.get("type") == "tool_result"]
    return results


class ScriptedProvider:
    def __init__(self, delay: float = 0.05) -> None:
        self.delay = delay
        self.calls: list[dict[str, Any]] = []

    def test(self) -> dict[str, Any]:
        return {"ok": True, "message": "Connected. fake-model is available."}

    def _say(self, text: str, should_stop: Callable[[], bool], chunk: int = 12) -> Iterator[dict[str, Any]]:
        for start in range(0, len(text), chunk):
            if should_stop():
                return
            time.sleep(self.delay)
            yield {"type": "text", "text": text[start:start + chunk]}

    def stream(self, *, system: str, messages: Sequence[Mapping[str, Any]], tools: Sequence[Mapping[str, Any]],
               should_stop: Callable[[], bool]) -> Iterator[dict[str, Any]]:
        self.calls.append({"system": system, "messages": json.loads(json.dumps(messages)), "tools": [tool["name"] for tool in tools]})
        text = _last_user_text(messages).strip()
        results = _tool_results(messages)
        lower = text.lower()
        if lower.startswith("fail"):
            raise ProviderError("The provider refused the API key (HTTP 401). Check the key in Settings, AI provider.")
        if lower.startswith("slow"):
            yield from self._say("Counting slowly. " * 40, should_stop, chunk=6)
            yield {"type": "message", "content": [{"type": "text", "text": "Counting slowly."}], "stop_reason": "end_turn"}
            return
        if lower.startswith("accept"):
            if not results:
                yield {"type": "message", "content": [{"type": "tool_use", "id": "call-accept", "name": "proposal_accept",
                                                       "input": {"proposal_id": "p1"}}], "stop_reason": "tool_use"}
                return
            answer = "I cannot accept proposals. Accept or reject them in Merge models."
            yield from self._say(answer, should_stop)
            yield {"type": "message", "content": [{"type": "text", "text": answer}], "stop_reason": "end_turn"}
            return
        if lower.startswith("search"):
            if not results:
                query = text[6:].strip() or "sales"
                yield {"type": "message", "content": [{"type": "tool_use", "id": "call-search", "name": "brain_search",
                                                       "input": {"query": query, "limit": 5}}], "stop_reason": "tool_use"}
                return
            items = json.loads(results[0]["content"]).get("items") or [] if not results[0].get("is_error") else []
            if items:
                first = items[0]
                answer = f"The best match is [{first.get('name')}](object:{first.get('id')}). It has {len(items)} matches in all."
            else:
                answer = "Nothing matched."
            yield from self._say(answer, should_stop)
            yield {"type": "message", "content": [{"type": "text", "text": answer}], "stop_reason": "end_turn"}
            return
        if lower.startswith("propose"):
            if not results:
                yield {"type": "message", "content": [{"type": "text", "text": "Reading the session."},
                                                      {"type": "tool_use", "id": "call-session", "name": "session_get", "input": {}}],
                       "stop_reason": "tool_use"}
                return
            if len(results) == 1:
                session = json.loads(results[0]["content"]) if not results[0].get("is_error") else {}
                match = re.search(r"exact ID (.+?)\.\n", _context(messages) + "\n")
                target = match.group(1) if match else "measure:Sales/Margin"
                name = target.rsplit("/", 1)[-1]
                yield {"type": "message", "content": [{"type": "tool_use", "id": "call-propose", "name": "proposal_submit", "input": {
                    "kind": "object_edit", "target": target, "target_name": name,
                    "payload": {"set": {"description": "Proposed in chat."}}, "confidence": 0.95,
                    "reason": "The description is missing.", "base_revision": int(session.get("revision") or 0)}}],
                       "stop_reason": "tool_use"}
                return
            last = results[-1]
            answer = ("I proposed a new description. Accept or reject it in Merge models."
                      if not last.get("is_error") else f"The proposal was refused: {last['content']}")
            yield from self._say(answer, should_stop)
            yield {"type": "message", "content": [{"type": "text", "text": answer}], "stop_reason": "end_turn"}
            return
        answer = "Hello from the **fake** provider. Ask me to search the project."
        yield from self._say(answer, should_stop)
        yield {"type": "message", "content": [{"type": "text", "text": answer}], "stop_reason": "end_turn"}


def install(app: Any, provider: ScriptedProvider | None = None, *, settings_file: Any = None) -> ScriptedProvider:
    """Give ``app`` a chat that uses the scripted provider and a memory key store."""

    from backend.chat.credentials import MemoryStore
    from backend.chat.service import ChatService

    fake = provider or ScriptedProvider()
    app.chat = ChatService(app, settings_file=settings_file, store=MemoryStore(), provider_factory=lambda settings, key: fake,
                           lock=app.request_lock, use_settings_file=settings_file is not None)
    return fake
