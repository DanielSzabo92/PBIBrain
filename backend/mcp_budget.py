"""Measured reply budgets for the MCP tools (issue #18).

Every MCP reply passes through :func:`fit_reply`. It has two levels of detail:

- ``compact`` (the default) drops parser detail an agent does not read (DAX syntax trees,
  raw source metadata, AST offsets, nested evidence copies), shortens long strings, and
  keeps the reply under the tool's compact budget.
- ``full`` keeps every field and uses the larger full budget.

When a reply is still over budget, the budget is shared top-down over its fields: small
fields are kept whole and large lists keep a leading slice. Each cut is listed in the
``budget`` block of the reply, so an agent knows the reply is partial and how to page or
narrow. Budgets are characters of compact JSON; ``CHARS_PER_TOKEN`` converts to tokens.
A new tool adds its row to ``TOOL_BUDGETS``.
"""

from __future__ import annotations

import json
from typing import Any

CHARS_PER_TOKEN = 4
DETAILS = ("compact", "full")

# Reply budget in characters of JSON, per tool and detail level.
TOOL_BUDGETS: dict[str, dict[str, int]] = {
    "brain_overview": {"compact": 8_000, "full": 24_000},
    "brain_search": {"compact": 12_000, "full": 32_000},
    "brain_object": {"compact": 12_000, "full": 40_000},
    "brain_context": {"compact": 16_000, "full": 48_000},
    "brain_graph": {"compact": 16_000, "full": 48_000},
    "brain_impact": {"compact": 16_000, "full": 48_000},
    "brain_compare": {"compact": 16_000, "full": 48_000},
    # Issue #14 documented 12,000 characters (about 3,000 tokens) for brain_commonality.
    "brain_commonality": {"compact": 12_000, "full": 32_000},
    # The Development Center agent tools page on their own; this is only the ceiling.
    "devcenter": {"compact": 24_000, "full": 24_000},
}

# The field of each reply that carries the answer; it is served first when a reply is cut.
PRIMARY_FIELDS = {
    "brain_search": "items", "brain_object": "object", "brain_context": "target", "brain_graph": "nodes",
    "brain_impact": "direct_impacts", "brain_commonality": "groups",
}

# Room left in each budget for the ``budget`` and ``freshness`` blocks.
META_RESERVE = 1_200
# Fields compact replies leave out: parser output and raw metadata, never the facts.
COMPACT_DROPPED_KEYS = frozenset({
    "dax_ast", "dax_behaviors", "dax_evidence", "raw_source", "raw_metadata", "ast_location",
    "source_fingerprint", "behavior",
})
COMPACT_STRING_CHARS = 1_500
FULL_STRING_CHARS = 8_000
MAX_LISTED_CUTS = 12
_MIN_STRING = 80


def budget_for(tool: str, detail: str = "compact") -> int:
    if detail not in DETAILS:
        raise ValueError("detail must be 'compact' or 'full'")
    return TOOL_BUDGETS[tool][detail]


def size(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str))


class _Cuts:
    def __init__(self) -> None:
        self.lists: list[dict[str, Any]] = []
        self.list_count = 0
        self.strings = 0
        self.dropped: set[str] = set()

    def list_cut(self, path: str, kept: int, total: int) -> None:
        self.list_count += 1
        if len(self.lists) < MAX_LISTED_CUTS:
            self.lists.append({"path": path or "$", "kept": kept, "total": total})


def _strip(value: Any, cuts: _Cuts, string_chars: int, compact: bool) -> Any:
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if compact and key in COMPACT_DROPPED_KEYS:
                cuts.dropped.add(key)
                continue
            result[key] = _strip(item, cuts, string_chars, compact)
        return result
    if isinstance(value, (list, tuple)):
        return [_strip(item, cuts, string_chars, compact) for item in value]
    if isinstance(value, str) and len(value) > string_chars:
        cuts.strings += 1
        return _cut_string(value, string_chars)
    return value


def _cut_string(value: str, limit: int) -> str:
    limit = max(limit, _MIN_STRING)
    marker = f"… [+{len(value) - limit} chars]"
    return value[: max(limit - len(marker), 0)] + marker


def _shrink(value: Any, budget: int, path: str, cuts: _Cuts, primary: str | None = None) -> Any:
    """Return ``value`` serialized in about ``budget`` characters, cutting from the largest parts.

    ``primary`` names the field of a top-level reply that carries the answer (search items,
    graph nodes); it gets four shares of the budget where the other fields get one.
    """

    current = size(value)
    if current <= budget:
        return value
    if isinstance(value, str):
        cuts.strings += 1
        return _cut_string(value, budget - 2)
    if isinstance(value, dict):
        sizes = {key: size(item) for key, item in value.items()}
        overhead = {key: len(json.dumps(key, ensure_ascii=False)) + 2 for key in value}
        keys = list(value)
        # A map with more keys than fit (per-object confidences, say) keeps a leading slice.
        if sum(overhead[key] + min(sizes[key], 8) for key in keys) > budget - 2:
            room, kept_keys = budget - 2, []
            for key in keys:
                need = overhead[key] + min(sizes[key], 8)
                if need > room:
                    break
                kept_keys.append(key)
                room -= need
            cuts.list_cut(path, len(kept_keys), len(keys))
            keys = kept_keys
        # Water-filling: each field gets a weighted share; fields smaller than their share
        # stay whole and hand the rest to the larger ones.
        remaining = budget - 2 - sum(overhead[key] for key in keys)
        weight = {key: 4 if key == primary else 1 for key in keys}
        order = sorted(keys, key=lambda key: sizes[key] / weight[key])
        shares: dict[str, int] = {}
        for index, key in enumerate(order):
            pending = sum(weight[other] for other in order[index:])
            share = max(remaining * weight[key] // pending, 0)
            shares[key] = min(sizes[key], share)
            remaining -= shares[key]
        return {key: (value[key] if shares[key] >= sizes[key]
                      else _shrink(value[key], max(shares[key], 4), f"{path}.{key}" if path else key, cuts))
                for key in keys}
    if isinstance(value, list):
        kept: list[Any] = []
        used = 2
        for item in value:
            item_size = size(item) + 1
            if used + item_size > budget:
                if not kept and budget - used > 64 and isinstance(item, (dict, list, str)):
                    kept.append(_shrink(item, budget - used, f"{path}[0]", cuts))
                break
            kept.append(item)
            used += item_size
        cuts.list_cut(path, len(kept), len(value))
        return kept
    return value


def fit_reply(payload: Any, *, tool: str, detail: str = "compact", meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """Fit one tool reply into its budget and attach the ``budget`` block (plus ``meta`` blocks)."""

    max_chars = budget_for(tool, detail)
    compact = detail == "compact"
    reply = payload if isinstance(payload, dict) else {"items": payload}
    cuts = _Cuts()
    reply = _strip(reply, cuts, COMPACT_STRING_CHARS if compact else FULL_STRING_CHARS, compact)
    reply = _shrink(reply, max_chars - META_RESERVE, "", cuts, PRIMARY_FIELDS.get(tool))
    # A trimmed result page continues where the kept items end.
    for cut in cuts.lists:
        if cut["path"] == "items" and isinstance(reply.get("offset"), int):
            reply["has_more"] = True
            reply["next_offset"] = reply["offset"] + cut["kept"]
    block: dict[str, Any] = {"detail": detail, "max_chars": max_chars}
    if cuts.dropped:
        block["omitted_fields"] = sorted(cuts.dropped)
    if cuts.list_count or cuts.strings:
        block["truncated"] = True
        if cuts.lists:
            block["trimmed_lists"] = cuts.lists
            if cuts.list_count > len(cuts.lists):
                block["more_trimmed_lists"] = cuts.list_count - len(cuts.lists)
        if cuts.strings:
            block["shortened_strings"] = cuts.strings
        block["hint"] = ("Partial reply. Page with offset/limit, narrow the scope, or ask for one object"
                         + (", or use detail='full'." if compact else "."))
    result = {**reply, **(meta or {}), "budget": block}
    block["chars"] = block["approx_tokens"] = 0
    while True:  # the measured size includes its own digits
        used = size(result)
        if used == block["chars"]:
            return result
        block["chars"], block["approx_tokens"] = used, -(-used // CHARS_PER_TOKEN)
