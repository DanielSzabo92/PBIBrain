"""Agent proposals, agent questions, and the session log read (technical design sections 12 and 14, build step S10).

Two paths use this module:

- The HTTP proposal routes (``POST proposals``, ``POST questions``). They add a
  proposal or a question with status "proposed" or "open". They never change
  accepted state (ADR 0003).
- The pywebview JS API (``proposal_accept``, ``proposal_reject``,
  ``proposal_accept_all``, ``question_answer``). Only these calls copy a
  proposal into accepted state.

Each proposal kind has one ``_Kind`` record. The record tells where the
accepted state of the kind is, whether a user choice exists on the target, and
how to copy the payload into accepted state.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence
import uuid

from backend.devcenter import contracts
from backend.devcenter.errors import DevCenterError, not_allowed
from backend.devcenter.session.store import utc_now

CONFIDENCE_THRESHOLD = 0.9

STATUS_PROPOSED = "proposed"
STATUS_ACCEPTED = "accepted"
STATUS_REJECTED = "rejected"
STATUS_REPLACED = "replaced"
QUESTION_OPEN = "open"
QUESTION_ANSWERED = "answered"

BLOCKED_SOURCE_CHANGED = "source_changed"
BLOCKED_USER_CHOICE = "user_choice_conflict"

AUTHOR_AGENT = "agent"
AUTHOR_USER = "user"
DEFAULT_CLIENT = "MCP client"

# ``include_proposals`` modes of ``GET plan``, ``GET impact``, and ``POST plan-validate``.
INCLUDE_NONE = None
INCLUDE_ALL = "all"
INCLUDE_READY = "ready"

PROPOSAL_REQUEST = "http/proposals.request.json"
QUESTION_REQUEST = "http/questions.request.json"

LOG_LIMIT_DEFAULT = 50
LOG_LIMIT_MAX = 500


# Proposal kinds ------------------------------------------------------------------


def _merge_choice(payload: Mapping[str, Any]) -> dict[str, Any]:
    choice = payload["choice"]
    return {"kind": choice} if isinstance(choice, str) else copy.deepcopy(dict(choice))


def _apply_merge_choice(document: dict[str, Any], target: str, payload: Mapping[str, Any]) -> tuple[Any, Any]:
    choices = document.setdefault("merge_choices", {})
    before = copy.deepcopy(choices.get(target))
    choices[target] = _merge_choice(payload)
    return before, copy.deepcopy(choices[target])


def _user_name(document: Mapping[str, Any], target: str) -> bool:
    choice = (document.get("merge_choices") or {}).get(target)
    return isinstance(choice, Mapping) and bool(str(choice.get("new_name") or "").strip())


def _apply_name(document: dict[str, Any], target: str, payload: Mapping[str, Any]) -> tuple[Any, Any]:
    choices = document.setdefault("merge_choices", {})
    before = copy.deepcopy(choices.get(target))
    choice = dict(before) if isinstance(before, Mapping) else {"kind": "add_new_name"}
    if payload.get("source_id") and not choice.get("source_id"):
        choice["source_id"] = payload["source_id"]
    choice["new_name"] = payload["name"]
    choices[target] = choice
    return before, copy.deepcopy(choice)


def _user_alignment(document: Mapping[str, Any], target: str, payload: Mapping[str, Any]) -> bool:
    entries = (document.get("alignment_overrides") or {}).get(payload["source_id"]) or []
    if any(item.get("target_key") == payload["target_key"] or item.get("donor_key") == payload["donor_key"] for item in entries):
        return True
    # A break or a confirm removes the Merge Choice of the row (UC21). That replaces a user choice.
    return payload["action"] != "reject_rename" and target in (document.get("merge_choices") or {})


def _apply_alignment(document: dict[str, Any], target: str, payload: Mapping[str, Any]) -> tuple[Any, Any]:
    overrides = document.setdefault("alignment_overrides", {})
    source_id = payload["source_id"]
    entries = list(overrides.get(source_id, []))
    before = {"overrides": copy.deepcopy(entries), "merge_choice": copy.deepcopy((document.get("merge_choices") or {}).get(target))}
    entries = [item for item in entries if not (item.get("target_key") == payload["target_key"] and item.get("donor_key") == payload["donor_key"])]
    entries.append({"kind": payload["action"], "target_key": payload["target_key"], "donor_key": payload["donor_key"]})
    entries.sort(key=lambda item: (item["target_key"], item["donor_key"], item["kind"]))
    overrides[source_id] = entries
    if payload["action"] != "reject_rename":
        document.setdefault("merge_choices", {}).pop(target, None)
    return before, {"overrides": copy.deepcopy(entries)}


def _keyed(store: str, value: Callable[[Mapping[str, Any]], dict[str, Any]]) -> tuple[Callable[..., bool], Callable[..., tuple[Any, Any]]]:
    """Give the user check and the apply function of a kind that keeps one value for each target key."""

    def user(document: Mapping[str, Any], target: str, payload: Mapping[str, Any]) -> bool:
        return target in (document.get(store) or {})

    def apply(document: dict[str, Any], target: str, payload: Mapping[str, Any]) -> tuple[Any, Any]:
        values = document.setdefault(store, {})
        before = copy.deepcopy(values.get(target))
        values[target] = value(payload)
        return before, copy.deepcopy(values[target])

    return user, apply


@dataclass(frozen=True)
class _Kind:
    user_choice: Callable[[Mapping[str, Any], str, Mapping[str, Any]], bool]
    apply: Callable[[dict[str, Any], str, Mapping[str, Any]], tuple[Any, Any]]
    summary: Callable[[Mapping[str, Any], Mapping[str, Any]], str]


def _source_name(document: Mapping[str, Any], source_id: Any) -> str:
    for item in document.get("sources") or []:
        if item.get("source_id") == source_id:
            return str(item.get("display_name") or source_id)
    return str(source_id)


def _choice_summary(document: Mapping[str, Any], payload: Mapping[str, Any]) -> str:
    choice = _merge_choice(payload)
    text = "Merge Choice " + str(choice["kind"]).replace("_", " ")
    if choice.get("source_id"):
        text += " from " + _source_name(document, choice["source_id"])
    if choice.get("new_name"):
        text += ", new name " + str(choice["new_name"])
    return text


_removal_user, _removal_apply = _keyed("removal_policies", lambda p: {"policy": p["policy"], "repoint_target": p.get("repoint_target")})
_need_user, _need_apply = _keyed("need_mappings", lambda p: {"action": p["action"], "target_object": p.get("target_object")})
_item_user, _item_apply = _keyed("item_actions", lambda p: {"action": p["action"]})

KINDS: dict[str, _Kind] = {
    "merge_choice": _Kind(lambda d, t, p: t in (d.get("merge_choices") or {}), _apply_merge_choice, _choice_summary),
    "name": _Kind(lambda d, t, p: _user_name(d, t), _apply_name, lambda d, p: "New name " + str(p["name"])),
    "alignment": _Kind(_user_alignment, _apply_alignment, lambda d, p: "Alignment " + str(p["action"]).replace("_", " ")
                       + " in " + _source_name(d, p["source_id"])),
    "removal_policy": _Kind(_removal_user, _removal_apply, lambda d, p: "Removal policy " + str(p["policy"])),
    "need_mapping": _Kind(_need_user, _need_apply, lambda d, p: "Need " + str(p["action"]).replace("_", " ")),
    "impact_action": _Kind(_item_user, _item_apply, lambda d, p: "Impact action " + str(p["action"]).replace("_", " ")),
}


# State reads -------------------------------------------------------------------


def _marked(document: Mapping[str, Any], target: Any) -> bool:
    return any(mark.get("row_key") == target for mark in document.get("source_marks") or [])


def blocked_state(document: Mapping[str, Any], proposal: Mapping[str, Any]) -> str | None:
    """``source_changed`` on an unconfirmed marked row, ``user_choice_conflict`` when a user choice exists, else None."""

    if _marked(document, proposal["target_id"]):
        return BLOCKED_SOURCE_CHANGED
    if KINDS[proposal["kind"]].user_choice(document, proposal["target_id"], proposal["payload"]):
        return BLOCKED_USER_CHOICE
    return None


def open_proposals(document: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [item for item in document.get("proposals") or [] if item.get("status") == STATUS_PROPOSED]


def proposal_view(document: Mapping[str, Any], proposal: Mapping[str, Any]) -> dict[str, Any]:
    """UC9: each field of one open proposal and its blocked state."""

    return {**copy.deepcopy(dict(proposal)), "blocked": blocked_state(document, proposal)}


def question_view(document: Mapping[str, Any], question: Mapping[str, Any]) -> dict[str, Any]:
    """UC9: each field of one question. An answered question has ``selected_option`` and ``answered_utc``."""

    view = copy.deepcopy(dict(question))
    view["blocked"] = BLOCKED_SOURCE_CHANGED if question.get("status") == QUESTION_OPEN and _marked(document, question["target_id"]) else None
    view.setdefault("selected_option", None)
    view.setdefault("answered_utc", None)
    return view


def session_lists(document: Mapping[str, Any]) -> dict[str, Any]:
    """The ``proposals`` and ``questions`` blocks of ``GET session`` (UC9)."""

    questions = document.get("questions") or []
    return {
        "proposals": {"open": [proposal_view(document, item) for item in open_proposals(document)]},
        "questions": {
            "open": [question_view(document, item) for item in questions if item.get("status") == QUESTION_OPEN],
            "answered": [question_view(document, item) for item in questions if item.get("status") == QUESTION_ANSWERED],
        },
    }


def ready_proposals(document: Mapping[str, Any]) -> list[dict[str, Any]]:
    """UC10 and UC11: the open proposals that ``proposal_accept_all`` accepts."""

    return [item for item in open_proposals(document) if blocked_state(document, item) is None]


def include_mode(value: Any) -> str | None:
    """Read ``include_proposals``: ``true`` gives all open proposals, ``ready`` gives the ready proposals."""

    if isinstance(value, bool):
        return INCLUDE_ALL if value else INCLUDE_NONE
    if value is None:
        return INCLUDE_NONE
    text = str(value).strip().lower()
    if text == INCLUDE_READY:
        return INCLUDE_READY
    if text in {"true", "1", "yes"}:
        return INCLUDE_ALL
    if text in {"false", "0", "no", ""}:
        return INCLUDE_NONE
    raise DevCenterError("invalid_payload", "The value of include_proposals must be true, false, or ready.",
                         {"reason": "invalid_include_proposals", "field": "include_proposals"})


def with_proposals(document: Mapping[str, Any], mode: str | None) -> dict[str, Any]:
    """Give a copy of the document with the proposals of the mode in accepted state.

    ``all`` copies each open proposal that does not replace a user choice.
    ``ready`` copies only the proposals that ``proposal_accept_all`` accepts.
    The copy is for a plan or an impact read only. Apply never uses it.
    """

    view = copy.deepcopy(dict(document))
    if mode is INCLUDE_NONE:
        return view
    if mode == INCLUDE_READY:
        selected = ready_proposals(document)
    else:
        selected = [item for item in open_proposals(document) if blocked_state(document, item) != BLOCKED_USER_CHOICE]
    for proposal in selected:
        KINDS[proposal["kind"]].apply(view, proposal["target_id"], proposal["payload"])
    return view


# Agent writes (HTTP proposal routes) ---------------------------------------------


def _check(name: str, body: Any) -> dict[str, Any]:
    problems = contracts.errors(name, body)
    if problems:
        raise DevCenterError("invalid_payload", "The request is not valid.", {"errors": problems[:20]})
    return dict(body)


def _check_reason(body: Mapping[str, Any]) -> str:
    reason = str(body.get("reason") or "").strip()
    if not reason:
        raise DevCenterError("reason_required", "Give a reason for the proposal.", {"field": "reason"})
    return reason


def _check_revision(devcenter: Any, body: Mapping[str, Any]) -> None:
    revision = devcenter._require_open().document["revision"]
    if body.get("base_revision") != revision:
        raise DevCenterError("stale_revision", "The session changed. Load it again.", {"revision": revision})


def _naming_breaks(devcenter: Any, document: Mapping[str, Any], payload: Mapping[str, Any]) -> list[dict[str, str]]:
    from backend.devcenter.naming import service as naming_service
    from backend.devcenter.naming.proposer import breaks
    from backend.devcenter.naming.objects import format_kind

    target = naming_service._load_target(devcenter, document, required=False)
    if target is None:
        return []
    context = {"table": payload.get("table"), "display_folder": payload.get("display_folder"),
               "format_kind": format_kind(payload.get("format_string"))}
    return breaks(payload["name"], payload["object_type"], context, target.stored)


def _agent_entry(action: str, target: Any, client: str, reason: str, proposal_id: str | None,
                 before: Any = None, after: Any = None) -> dict[str, Any]:
    return {"author": AUTHOR_AGENT, "mcp_client": client, "action": action, "target": target, "before": before,
            "after": after, "reason": reason, "proposal_id": proposal_id}


def proposal_submit(devcenter: Any, body: Any) -> dict[str, Any]:
    """``POST proposals``: add one agent proposal with status "proposed" (section 12)."""

    body = _check(PROPOSAL_REQUEST, body)
    if body["confidence"] < CONFIDENCE_THRESHOLD:
        raise DevCenterError("confidence_below_threshold", "The confidence is below the threshold.",
                             {"confidence": body["confidence"], "threshold": CONFIDENCE_THRESHOLD})
    reason = _check_reason(body)
    kind, target, payload = body["kind"], body["target"], body["payload"]
    client = str(body.get("mcp_client") or DEFAULT_CLIENT)
    with devcenter._lock:
        _check_revision(devcenter, body)
        document = devcenter._require_open().document
        if _marked(document, target):
            raise DevCenterError("source_changed", "The source of this row changed. The user must confirm the row first.", {"target": target})
        if KINDS[kind].user_choice(document, target, payload):
            raise DevCenterError("user_choice_exists", "The user made a choice for this target. An agent proposal cannot replace it.",
                                 {"target": target, "kind": kind})
        if kind == "name":
            found = _naming_breaks(devcenter, document, payload)
            if found:
                raise DevCenterError("naming_rule_violation", "The name breaks a confirmed naming rule.",
                                     {"rule_ids": [item["rule_id"] for item in found], "rules": found})
        proposal = {
            "id": "p-" + uuid.uuid4().hex[:12],
            "kind": kind,
            "target_id": target,
            "target_name": body.get("target_name") or target,
            "payload": copy.deepcopy(payload),
            "summary": KINDS[kind].summary(document, payload),
            "confidence": body["confidence"],
            "reason": reason,
            "mcp_client": client,
            "author": AUTHOR_AGENT,
            "created_utc": utc_now(),
            "status": STATUS_PROPOSED,
        }
        replaced: list[str] = []

        def mutate(draft: dict[str, Any]) -> tuple[Any, Any]:
            for item in draft.setdefault("proposals", []):
                if item.get("status") == STATUS_PROPOSED and item.get("author", AUTHOR_AGENT) == AUTHOR_AGENT \
                        and (item["target_id"], item["kind"]) == (target, kind):
                    item["status"] = STATUS_REPLACED
                    item["replaced_by"] = proposal["id"]
                    replaced.append(item["id"])
            draft["proposals"].append(proposal)
            return None, copy.deepcopy(payload)

        def log() -> list[Mapping[str, Any]]:
            entries = [_agent_entry("proposal_replace", target, client, reason, old, None, {"replaced_by": proposal["id"]})
                       for old in replaced]
            return entries + [_agent_entry("proposal_submit", target, client, reason, proposal["id"], None, copy.deepcopy(payload))]

        saved = devcenter._change(body, "proposal_submit", target, mutate, log=log)
        return {"revision": saved["revision"], "proposal": proposal_view(saved, proposal), "replaced_ids": replaced}


def question_ask(devcenter: Any, body: Any) -> dict[str, Any]:
    """``POST questions``: add one agent question with 2 to 5 options (section 12)."""

    body = _check(QUESTION_REQUEST, body)
    reason = _check_reason(body)
    options = body["options"]
    ids = [item["id"] for item in options]
    if len(set(ids)) != len(ids):
        raise DevCenterError("invalid_payload", "Each option must have a different ID.", {"reason": "duplicate_option_id", "field": "options"})
    if body["recommended_option"] not in ids:
        raise DevCenterError("invalid_payload", "The recommended option is not one of the options.",
                             {"reason": "unknown_option", "field": "recommended_option"})
    client = str(body.get("mcp_client") or DEFAULT_CLIENT)
    target = body["target"]
    with devcenter._lock:
        _check_revision(devcenter, body)
        question = {
            "id": "q-" + uuid.uuid4().hex[:12],
            "target_id": target,
            "target_name": body.get("target_name") or target,
            "text": body["text"],
            "options": copy.deepcopy(options),
            "recommended_option": body["recommended_option"],
            "reason": reason,
            "mcp_client": client,
            "author": AUTHOR_AGENT,
            "created_utc": utc_now(),
            "status": QUESTION_OPEN,
            "selected_option": None,
            "answered_utc": None,
        }

        def mutate(draft: dict[str, Any]) -> tuple[Any, Any]:
            draft.setdefault("questions", []).append(question)
            return None, {"text": question["text"], "options": ids}

        def log() -> list[Mapping[str, Any]]:
            return [_agent_entry("question_ask", target, client, reason, question["id"], None,
                                 {"text": question["text"], "options": ids})]

        saved = devcenter._change(body, "question_ask", target, mutate, log=log)
        return {"revision": saved["revision"], "question": question_view(saved, question)}


# User changes (JS API only, ADR 0003) --------------------------------------------


def _find(items: Sequence[Mapping[str, Any]], item_id: Any, what: str) -> dict[str, Any]:
    for item in items:
        if item.get("id") == item_id:
            return item  # type: ignore[return-value]
    raise DevCenterError("not_found", f"The {what} does not exist.", {f"{what}_id": item_id})


def _open_proposal(document: Mapping[str, Any], proposal_id: Any) -> dict[str, Any]:
    proposal = _find(document.get("proposals") or [], proposal_id, "proposal")
    if proposal.get("status") != STATUS_PROPOSED:
        raise not_allowed("The proposal is not open.", "proposal_not_open", proposal_id=proposal_id, status=proposal.get("status"))
    return proposal


def _user_entry(action: str, proposal: Mapping[str, Any], before: Any, after: Any) -> dict[str, Any]:
    return {"author": AUTHOR_USER, "mcp_client": proposal.get("mcp_client"), "action": action, "target": proposal["target_id"],
            "before": before, "after": after, "reason": proposal.get("reason"), "proposal_id": proposal["id"]}


def proposal_accept(devcenter: Any, request: Mapping[str, Any]) -> dict[str, Any]:
    """UC12: a user accept replaces the earlier user choice on the target. The log keeps before and after."""

    with devcenter._lock:
        entries: list[dict[str, Any]] = []

        def mutate(draft: dict[str, Any]) -> tuple[Any, Any]:
            proposal = _open_proposal(draft, request.get("proposal_id"))
            if _marked(draft, proposal["target_id"]):
                raise DevCenterError("source_changed", "The source of this row changed. Confirm the row first.",
                                     {"proposal_id": proposal["id"], "target": proposal["target_id"]})
            before, after = KINDS[proposal["kind"]].apply(draft, proposal["target_id"], proposal["payload"])
            proposal["status"] = STATUS_ACCEPTED
            proposal["decided_utc"] = utc_now()
            entries.append(_user_entry("proposal_accept", proposal, before, after))
            return before, after

        saved = devcenter._change(request, "proposal_accept", request.get("proposal_id"), mutate, log=lambda: entries)
        _drop_impact_cache(devcenter)
        return {"revision": saved["revision"], "accepted_ids": [request.get("proposal_id")]}


def proposal_reject(devcenter: Any, request: Mapping[str, Any]) -> dict[str, Any]:
    with devcenter._lock:
        entries: list[dict[str, Any]] = []

        def mutate(draft: dict[str, Any]) -> tuple[Any, Any]:
            proposal = _open_proposal(draft, request.get("proposal_id"))
            proposal["status"] = STATUS_REJECTED
            proposal["decided_utc"] = utc_now()
            entries.append(_user_entry("proposal_reject", proposal, STATUS_PROPOSED, STATUS_REJECTED))
            return STATUS_PROPOSED, STATUS_REJECTED

        saved = devcenter._change(request, "proposal_reject", request.get("proposal_id"), mutate, log=lambda: entries)
        return {"revision": saved["revision"], "rejected_ids": [request.get("proposal_id")]}


def proposal_accept_all(devcenter: Any, request: Mapping[str, Any]) -> dict[str, Any]:
    """UC10: accept the ready proposals in one revision. Skip the blocked proposals with a reason code."""

    with devcenter._lock:
        accepted: list[str] = []
        skipped: list[dict[str, str]] = []
        entries: list[dict[str, Any]] = []

        def mutate(draft: dict[str, Any]) -> tuple[Any, Any]:
            # The blocked state comes from the state before this call: a proposal that this call
            # accepts does not block a different proposal of the same call.
            start = copy.deepcopy(draft)
            for proposal in open_proposals(draft):
                reason = blocked_state(start, proposal)
                if reason is not None:
                    skipped.append({"id": proposal["id"], "reason": reason})
                    continue
                before, after = KINDS[proposal["kind"]].apply(draft, proposal["target_id"], proposal["payload"])
                proposal["status"] = STATUS_ACCEPTED
                proposal["decided_utc"] = utc_now()
                accepted.append(proposal["id"])
                entries.append(_user_entry("proposal_accept_all", proposal, before, after))
            return None, {"accepted_ids": list(accepted)}

        current = devcenter._require_open()
        if not any(blocked_state(current.document, item) is None for item in open_proposals(current.document)):
            # Nothing to accept: no new revision. The revision check still applies.
            if request.get("base_revision") != current.document["revision"]:
                raise DevCenterError("stale_revision", "The session changed. Load it again.", {"revision": current.document["revision"]})
            skipped = [{"id": item["id"], "reason": blocked_state(current.document, item)} for item in open_proposals(current.document)]
            return {"revision": current.document["revision"], "accepted_ids": [], "skipped": skipped}
        saved = devcenter._change(request, "proposal_accept_all", None, mutate, log=lambda: entries)
        _drop_impact_cache(devcenter)
        return {"revision": saved["revision"], "accepted_ids": accepted, "skipped": skipped}


def question_answer(devcenter: Any, request: Mapping[str, Any]) -> dict[str, Any]:
    """Record the option that the user selected. An option with a proposal puts that proposal in accepted state."""

    with devcenter._lock:
        entries: list[dict[str, Any]] = []
        applied = {"value": False}

        def mutate(draft: dict[str, Any]) -> tuple[Any, Any]:
            question = _find(draft.get("questions") or [], request.get("question_id"), "question")
            if question.get("status") != QUESTION_OPEN:
                raise not_allowed("The question has an answer.", "question_answered", question_id=question["id"])
            option = next((item for item in question["options"] if item["id"] == request.get("option_id")), None)
            if option is None:
                raise DevCenterError("not_found", "The option does not exist.", {"option_id": request.get("option_id")})
            before = after = None
            proposal = option.get("proposal")
            if proposal:
                if _marked(draft, question["target_id"]):
                    raise DevCenterError("source_changed", "The source of this row changed. Confirm the row first.",
                                         {"question_id": question["id"], "target": question["target_id"]})
                before, after = KINDS[proposal["kind"]].apply(draft, question["target_id"], proposal["payload"])
                applied["value"] = True
            question["status"] = QUESTION_ANSWERED
            question["selected_option"] = option["id"]
            question["answered_utc"] = utc_now()
            entries.append({"author": AUTHOR_USER, "mcp_client": question.get("mcp_client"), "action": "question_answer",
                            "target": question["target_id"], "before": before, "after": after or {"selected_option": option["id"]},
                            "reason": question.get("reason"), "proposal_id": question["id"]})
            return before, after

        saved = devcenter._change(request, "question_answer", request.get("question_id"), mutate, log=lambda: entries)
        if applied["value"]:
            _drop_impact_cache(devcenter)
        return {"revision": saved["revision"], "question_id": request.get("question_id"), "option_id": request.get("option_id"),
                "applied": applied["value"]}


def _drop_impact_cache(devcenter: Any) -> None:
    if hasattr(devcenter, "_cached_impact"):
        devcenter._cached_impact = None


# Log read (UC8) ------------------------------------------------------------------


def _one(query: Mapping[str, Sequence[str]], name: str) -> str | None:
    values = list(query.get(name) or [])
    return str(values[-1]) if values else None


def _number(query: Mapping[str, Sequence[str]], name: str, default: int, maximum: int | None = None) -> int:
    text = _one(query, name)
    if text is None or text == "":
        return default
    if not text.isdigit():
        raise DevCenterError("invalid_payload", f"The value of {name} must be a whole number.", {"reason": "invalid_number", "field": name})
    value = int(text)
    return min(value, maximum) if maximum is not None else value


def _target_matches(target: Any, wanted: str) -> bool:
    if isinstance(target, list):
        return wanted in [str(item) for item in target]
    return target is not None and str(target) == wanted


def log_page(devcenter: Any, query: Mapping[str, Sequence[str]]) -> dict[str, Any]:
    """``GET log``: log entries, newest first. The filters apply to all entries before the paging (UC8)."""

    limit = max(1, _number(query, "limit", LOG_LIMIT_DEFAULT, LOG_LIMIT_MAX))
    offset = _number(query, "offset", 0)
    author, action, target, proposal_id = (_one(query, name) for name in ("author", "action", "target", "proposal_id"))
    if author is not None and author not in {AUTHOR_USER, AUTHOR_AGENT}:
        raise DevCenterError("invalid_payload", "The author must be user or agent.", {"reason": "invalid_author", "field": "author"})
    with devcenter._lock:
        current = devcenter._require_open()
        revision = current.document["revision"]
        entries = current.files.read_log()
    entries.reverse()
    if author:
        entries = [item for item in entries if item.get("author") == author]
    if action:
        entries = [item for item in entries if item.get("action") == action]
    if target:
        entries = [item for item in entries if _target_matches(item.get("target"), target)]
    if proposal_id:
        entries = [item for item in entries if item.get("proposal_id") == proposal_id]
    total = len(entries)
    page = entries[offset:offset + limit]
    return {
        "revision": revision,
        "entries": [_log_view(item) for item in page],
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + limit < total,
    }


def _log_view(entry: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "time_utc": entry.get("time"),
        "author": entry.get("author") if entry.get("author") in {AUTHOR_USER, AUTHOR_AGENT} else AUTHOR_USER,
        "mcp_client": entry.get("mcp_client"),
        "action": str(entry.get("action") or ""),
        "target": entry.get("target"),
        "before": entry.get("before"),
        "after": entry.get("after"),
        "reason": entry.get("reason"),
        "proposal_id": entry.get("proposal_id"),
        "revision_after": entry.get("revision"),
    }
