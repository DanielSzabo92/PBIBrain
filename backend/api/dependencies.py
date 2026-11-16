"""One-call dependency answers straight from the graph, and the objects a question names.

An agent that is asked "what does Sales Amount depend on?" should not search, then inspect,
then walk edges one call at a time, and never fall back to reading TMDL files. This module
answers that question in one read of the graph:

- ``resolve``: a name or an exact ID becomes the graph object(s) it means. ``[Measure]``,
  ``'Table'[Column]`` and ``Table[Column]`` are understood. Several objects with one name come
  back as an ambiguity, never as a silent pick.
- ``dependency_answer``: what the object is built from (upstream: measures it calls, columns
  it reads, the data sources of its table) and what is built on it (downstream: measures and
  columns that use it, and the report visuals and pages that show it), bounded by depth, with
  a one-line summary written from the counts. Every item is a graph fact with its exact ID.
- ``mentioned_objects``: the objects a free-text question names, found by an exact name index
  (no fuzzy guessing), so the chat can hand the model the answer before it calls any tool.
"""

from __future__ import annotations

import re
import threading
import weakref
from collections import deque
from typing import Any
from collections.abc import Iterable

# What an object is built from, and what is built on it, by edge type (from -> to).
UPSTREAM_EDGES = {"DEPENDS_ON", "REFERENCES", "SOURCES_FROM"}
USAGE_EDGES = {"USES"}
# Objects a person names in a question about the model or report.
NAMED_TYPES = {"MEASURE", "COLUMN", "TABLE", "CALCULATION_GROUP", "CALCULATION_ITEM", "HIERARCHY", "PARAMETER",
               "PAGE", "VISUAL", "SECURITY_ROLE", "SHARED_EXPRESSION", "DATA_SOURCE", "PARTITION", "REPORT", "MODEL"}
# When one name means several objects, these are what people usually mean, first.
TYPE_RANK = {"MEASURE": 0, "COLUMN": 1, "TABLE": 2, "CALCULATION_ITEM": 3, "PAGE": 4, "VISUAL": 5}
MAX_DEPTH = 5
MAX_ITEMS = 150
MAX_EXPRESSION = 3_000
MAX_MENTIONS = 3
QUALIFIED = re.compile(r"^\s*'?(?P<table>[^'\[\]]+?)'?\s*\[(?P<name>[^\[\]]+)\]\s*$")
BRACKETED = re.compile(r"^\s*\[(?P<name>[^\[\]]+)\]\s*$")
WORD = re.compile(r"[\w%#&$€£.-]+", re.UNICODE)


def _key(text: str) -> str:
    return " ".join(str(text).casefold().split())


class GraphIndex:
    """Nodes, edges by end, and names, built once per graph revision."""

    def __init__(self, nodes: Iterable[Any], edges: Iterable[Any]) -> None:
        self.nodes = {node.id: node for node in nodes}
        self.outgoing: dict[str, list[Any]] = {}
        self.incoming: dict[str, list[Any]] = {}
        for edge in edges:
            self.outgoing.setdefault(edge.from_id, []).append(edge)
            self.incoming.setdefault(edge.to_id, []).append(edge)
        self.by_name: dict[str, list[str]] = {}
        for node in self.nodes.values():
            if node.type in NAMED_TYPES and node.name and node.status != "rejected":
                self.by_name.setdefault(_key(node.name), []).append(node.id)
        self.longest = max((len(name.split()) for name in self.by_name), default=1)

    def table_name(self, node: Any) -> str | None:
        table = self.nodes.get(str(node.properties.get("table_id") or ""))
        return table.name if table is not None else None

    def owner_name(self, node: Any) -> str | None:
        owner = self.nodes.get(str(node.report_id or node.model_id or ""))
        return owner.name if owner is not None else None

    def brief(self, node: Any, **extra: Any) -> dict[str, Any]:
        item: dict[str, Any] = {"id": node.id, "type": node.type, "name": node.name}
        table = self.table_name(node)
        if table:
            item["table"] = table
        owner = self.owner_name(node)
        if owner:
            item["report" if node.report_id else "model"] = owner
        if node.status != "factual":
            item["status"] = node.status
        item.update(extra)
        return item


_cache_lock = threading.Lock()
# Keyed by the repository object itself (weakly): an id() can be reused by a new repository after
# the old one is gone, and its revision counter starts at 0 again, which would serve a stale index.
_cache: "weakref.WeakKeyDictionary[Any, tuple[Any, GraphIndex]]" = weakref.WeakKeyDictionary()


def graph_index(repository: Any) -> GraphIndex:
    """The index of this repository's current graph (rebuilt when the graph revision changes)."""

    revision = getattr(repository, "revision", None)
    stamp = (revision, 0) if revision is not None else (None, len(repository.all_nodes()))
    with _cache_lock:
        try:
            cached = _cache.get(repository)
        except TypeError:  # not weak-referenceable: no cache
            cached = None
        if cached is not None and cached[0] == stamp:
            return cached[1]
    index = GraphIndex(repository.all_nodes(), repository.all_edges())
    with _cache_lock:
        try:
            _cache[repository] = (stamp, index)
        except TypeError:
            pass
    return index


def _scope_ok(node: Any, model_id: str | None, report_id: str | None) -> bool:
    if model_id and node.model_id != model_id:
        return False
    if report_id and node.report_id != report_id:
        return False
    return True


def resolve(index: GraphIndex, text: str, *, model_id: str | None = None, report_id: str | None = None,
            object_type: str | None = None) -> list[Any]:
    """The objects ``text`` names: an exact ID, a name, ``[Name]`` or ``Table[Column]``."""

    text = str(text or "").strip()
    if not text:
        return []
    if text in index.nodes:
        return [index.nodes[text]]
    table: str | None = None
    name = text
    if (match := QUALIFIED.match(text)) is not None:
        table, name = match.group("table").strip(), match.group("name").strip()
    elif (match := BRACKETED.match(text)) is not None:
        name = match.group("name").strip()
    found = [index.nodes[item] for item in index.by_name.get(_key(name), [])]
    found = [node for node in found if _scope_ok(node, model_id, report_id)]
    if object_type:
        found = [node for node in found if node.type == object_type.upper()]
    if table:
        found = [node for node in found if _key(index.table_name(node) or "") == _key(table)] or found
    return sorted(found, key=lambda node: (TYPE_RANK.get(node.type, 9), node.id))


def _walk(index: GraphIndex, start: str, depth: int, *, upstream: bool) -> tuple[list[dict[str, Any]], int]:
    """Breadth-first over dependency edges; usage edges end the walk at the report side."""

    seen = {start}
    found: list[dict[str, Any]] = []
    queue = deque([(start, 0)])
    while queue:
        current, level = queue.popleft()
        if level >= depth:
            continue
        edges = index.outgoing.get(current, []) if upstream else index.incoming.get(current, [])
        for edge in edges:
            types = UPSTREAM_EDGES if upstream else UPSTREAM_EDGES | USAGE_EDGES
            if edge.type not in types:
                continue
            other = edge.to_id if upstream else edge.from_id
            if other in seen or other not in index.nodes:
                continue
            seen.add(other)
            found.append(index.brief(index.nodes[other], depth=level + 1, via=edge.type,
                                     **({"of": index.nodes[current].name} if level else {})))
            if edge.type not in USAGE_EDGES:
                queue.append((other, level + 1))
    return found, len(found)


def _report_places(index: GraphIndex, visuals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The page and report of each visual that shows the object."""

    places: dict[str, dict[str, Any]] = {}
    for item in visuals:
        for edge in index.incoming.get(item["id"], []):
            page = index.nodes.get(edge.from_id)
            if edge.type == "CONTAINS" and page is not None and page.type == "PAGE":
                entry = places.setdefault(page.id, index.brief(page, visuals=[]))
                entry["visuals"].append(item["name"] or item["id"])
    return list(places.values())


def dependency_answer(index: GraphIndex, node: Any, *, direction: str = "both", depth: int = 1) -> dict[str, Any]:
    if direction not in {"both", "upstream", "downstream"}:
        raise ValueError("direction must be both, upstream or downstream")
    depth = max(1, min(int(depth), MAX_DEPTH))
    answer: dict[str, Any] = {"status": "OK", "object": index.brief(node), "direction": direction, "depth": depth}
    expression = node.properties.get("expression")
    if isinstance(expression, str) and expression.strip():
        answer["object"]["expression"] = expression if len(expression) <= MAX_EXPRESSION else expression[:MAX_EXPRESSION] + " …"
    parts: list[str] = []
    if direction in {"both", "upstream"}:
        upstream, total = _walk(index, node.id, depth, upstream=True)
        answer["upstream"] = upstream[:MAX_ITEMS]
        answer["upstream_total"] = total
        parts.append(f"{node.name} is built from {total} object{'s' if total != 1 else ''}" if total
                     else f"{node.name} uses no other model object")
    if direction in {"both", "downstream"}:
        downstream, total = _walk(index, node.id, depth, upstream=False)
        visuals = [item for item in downstream if item["type"] == "VISUAL"]
        model_side = [item for item in downstream if item["type"] != "VISUAL"]
        answer["downstream"] = model_side[:MAX_ITEMS]
        answer["downstream_total"] = len(model_side)
        answer["report_usage"] = _report_places(index, visuals)[:MAX_ITEMS]
        answer["visual_count"] = len(visuals)
        builds = "model object builds" if len(model_side) == 1 else "model objects build"
        shows = "visual shows" if len(visuals) == 1 else "visuals show"
        parts.append(f"{len(model_side)} {builds} on it and {len(visuals)} {shows} it")
    answer["summary"] = "; ".join(parts) + f" (depth {depth})."
    answer["truncated"] = any(answer.get(key + "_total", 0) > MAX_ITEMS for key in ("upstream", "downstream"))
    answer["note"] = ("Graph facts from the last scan. Use these IDs as they are; do not look for this in project files. "
                      "Raise depth for indirect dependencies.")
    return answer


def dependencies(repository: Any, target: str, *, direction: str = "both", depth: int = 1, model_id: str | None = None,
                 report_id: str | None = None, object_type: str | None = None) -> dict[str, Any]:
    """``GET /api/dependencies``: resolve ``target`` and answer, or say why not."""

    index = graph_index(repository)
    found = resolve(index, target, model_id=model_id, report_id=report_id, object_type=object_type)
    if not found:
        return {"status": "NOT_FOUND", "target": target,
                "note": "No object has this exact name or ID in the graph. Use brain_search for partial names. "
                        "Do not guess an answer for an object the graph does not have."}
    best_rank = TYPE_RANK.get(found[0].type, 9)
    top = [node for node in found if TYPE_RANK.get(node.type, 9) == best_rank]
    if len(top) > 1:
        return {"status": "AMBIGUOUS", "target": target, "candidates": [index.brief(node) for node in found[:20]],
                "note": "Several objects have this name. Ask the user which one, or call again with the exact id or model_id."}
    answer = dependency_answer(index, found[0], direction=direction, depth=depth)
    if len(found) > 1:
        answer["also_named"] = [index.brief(node) for node in found[1:10]]
    return answer


def mentioned_objects(repository: Any, text: str, *, limit: int = MAX_MENTIONS) -> list[list[Any]]:
    """Groups of objects that ``text`` names exactly, longest names first (one group per name)."""

    index = graph_index(repository)
    groups: list[list[Any]] = []
    taken: set[str] = set()
    for match in re.finditer(r"'?([^'\[\]\n]{1,120}?)'?\s*\[([^\[\]\n]{1,120})\]|\[([^\[\]\n]{1,120})\]", text):
        name = match.group(0)
        found = resolve(index, name)
        if found and _key(found[0].name) not in taken:
            taken.add(_key(found[0].name))
            groups.append(found)
    words = WORD.findall(text)
    size = min(index.longest, 8)
    position = 0
    while position < len(words) and len(groups) < limit:
        for length in range(min(size, len(words) - position), 0, -1):
            phrase = _key(" ".join(words[position:position + length]))
            if len(phrase) < 3 or phrase in taken or phrase not in index.by_name:
                continue
            # One plain word ("sales", "date") is an object only when written like a name: capitalised.
            if length == 1 and not words[position][:1].isupper():
                continue
            found = [index.nodes[item] for item in index.by_name[phrase]]
            taken.add(phrase)
            groups.append(sorted(found, key=lambda node: (TYPE_RANK.get(node.type, 9), node.id)))
            position += length - 1
            break
        position += 1
    return groups[:limit]


def mention_block(repository: Any, text: str) -> str:
    """The <graph> block for a chat turn: the named objects with their direct dependency answer."""

    groups = mentioned_objects(repository, text)
    if not groups:
        return ""
    index = graph_index(repository)
    lines = ["Objects this question names, resolved in the PBIBrain graph (facts, depth 1):"]
    for group in groups:
        best = TYPE_RANK.get(group[0].type, 9)
        top = [node for node in group if TYPE_RANK.get(node.type, 9) == best]
        if len(top) > 1:
            choices = "; ".join(f"{node.type} {node.name} in {index.owner_name(node) or '?'} id={node.id}" for node in top[:5])
            lines.append(f"- AMBIGUOUS name '{group[0].name}': {choices}. Ask which one, or use the exact id.")
            continue
        answer = dependency_answer(index, top[0], depth=1)
        upstream = ", ".join(f"{item['name']} ({item['type']})" for item in answer.get("upstream", [])[:15]) or "none"
        downstream = ", ".join(f"{item['name']} ({item['type']})" for item in answer.get("downstream", [])[:15]) or "none"
        pages = ", ".join(f"{place['name']} ({len(place['visuals'])} visual{'s' if len(place['visuals']) != 1 else ''})"
                          for place in answer.get("report_usage", [])[:10]) or "none"
        node = top[0]
        where = f" in table {index.table_name(node)}" if index.table_name(node) else ""
        lines.append(f"- {node.type} {node.name}{where}, id={node.id}. Built from: {upstream}. "
                     f"Used by: {downstream}. Shown on pages: {pages}. {answer['summary']}")
    return "<graph>\n" + "\n".join(lines) + "\n</graph>"
