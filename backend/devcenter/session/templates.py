"""Merge templates (issue #16, spec section 13): save the Merge Choices of a session, replay them in another one.

A template is a JSON file in ``<project>/.pbibrain/templates/<name>.json``, so it
can be committed with the project. It keeps each Merge Choice by its row key. A
choice that takes from a source keeps the source by its display name, because
source IDs are local to one session. The replay maps each name to the source of
the open session with the same name (case does not matter) and skips each choice
whose source the session does not have. The replay is one session change, so one
undo of the log entry takes it back.

The replay works for new versions of the donors (same names, new files) and for
another target (the choices do not name the target).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
import re
from typing import Any
from collections.abc import Mapping

from backend.devcenter.errors import DevCenterError, not_allowed
from backend.devcenter.session.secrets import check_secrets
from backend.devcenter.session.store import utc_now

TEMPLATE_FOLDER = ".pbibrain/templates"
TEMPLATE_VERSION = 1
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.-]{0,79}$")


def _folder(devcenter: Any) -> Path:
    return Path(devcenter.project_root) / TEMPLATE_FOLDER


def _name(value: Any) -> str:
    name = str(value or "").strip()
    if not _NAME.match(name) or name.endswith("."):
        raise DevCenterError("invalid_payload", "Use letters, digits, spaces, dots, dashes or underscores for the name.",
                             {"field": "name", "reason": "bad_name"})
    return name


def _path(devcenter: Any, name: str) -> Path:
    return _folder(devcenter) / f"{name}.json"


def _read(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise not_allowed("The template file cannot be read.", "template_unreadable") from exc
    if not isinstance(data, dict) or data.get("version") != TEMPLATE_VERSION or not isinstance(data.get("choices"), dict):
        raise not_allowed("The template file is not a merge template.", "template_unreadable")
    return data


def templates_list(devcenter: Any) -> dict[str, Any]:
    items = []
    folder = _folder(devcenter)
    for path in sorted(folder.glob("*.json")) if folder.is_dir() else []:
        try:
            data = _read(path)
        except DevCenterError:
            continue
        items.append({"name": path.stem, "saved_utc": str(data.get("saved_utc") or ""), "choice_count": len(data["choices"]),
                      "source_names": sorted({str(item["source_name"]) for item in data["choices"].values()
                                              if isinstance(item, Mapping) and item.get("source_name")})})
    return {"revision": devcenter.revision, "templates": items}


def template_save(devcenter: Any, request: Mapping[str, Any]) -> dict[str, Any]:
    name = _name(request.get("name"))
    with devcenter._lock:
        current = devcenter._require_open()
        revision = current.document["revision"]
        if request.get("base_revision") != revision:
            raise DevCenterError("stale_revision", "The session changed. Load it again.", {"revision": revision})
        document = current.document
        names = {item["source_id"]: item.get("display_name") or item["source_id"] for item in document["sources"]}
        choices: dict[str, Any] = {}
        for row_key, choice in sorted(document["merge_choices"].items()):
            if not isinstance(choice, Mapping):
                continue
            saved = copy.deepcopy(dict(choice))
            source_id = saved.pop("source_id", None)
            if source_id is not None:
                saved["source_name"] = names.get(source_id, source_id)
            choices[row_key] = saved
        path = _path(devcenter, name)
        if path.exists() and request.get("replace") is not True:
            raise not_allowed("A template with this name exists. Replace it or use another name.", "template_exists")
        payload = {"version": TEMPLATE_VERSION, "name": name, "saved_utc": utc_now(), "choices": choices}
        check_secrets(payload)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        temporary.replace(path)
        return {"revision": revision, "name": name, "path": devcenter.relative_path(path), "choice_count": len(choices)}


def template_apply(devcenter: Any, request: Mapping[str, Any]) -> dict[str, Any]:
    name = _name(request.get("name"))
    path = _path(devcenter, name)
    if not path.is_file():
        raise DevCenterError("not_found", "The template does not exist.", {"reason": "template_not_found"})
    data = _read(path)
    with devcenter._lock:
        applied: list[str] = []
        skipped: list[dict[str, Any]] = []

        def mutate(document: dict[str, Any]) -> tuple[Any, Any]:
            by_name: dict[str, str] = {}
            for item in document["sources"]:
                by_name.setdefault(str(item.get("display_name") or "").casefold(), item["source_id"])
            before, after = {}, {}
            for row_key, saved in sorted(data["choices"].items()):
                if not isinstance(saved, Mapping) or not isinstance(saved.get("kind"), str):
                    skipped.append({"row_key": row_key, "reason": "bad_choice"})
                    continue
                choice = copy.deepcopy(dict(saved))
                source_name = choice.pop("source_name", None)
                if source_name is not None:
                    source_id = by_name.get(str(source_name).casefold())
                    if source_id is None:
                        skipped.append({"row_key": row_key, "reason": "source_not_in_session"})
                        continue
                    choice["source_id"] = source_id
                before[row_key] = copy.deepcopy(document["merge_choices"].get(row_key))
                document["merge_choices"][row_key] = choice
                after[row_key] = copy.deepcopy(choice)
                applied.append(row_key)
            return before, after

        document = devcenter._change(request, "merge_template_apply", name, mutate)
        return {"revision": document["revision"], "name": name, "applied": applied, "skipped": skipped}
