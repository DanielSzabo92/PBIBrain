"""Convert a TMSL (``model.bim``) source to TMDL, so that it can be a merge target (issue #16).

The app writes a target model in TMDL only. A ``model.bim`` source stays a donor
until the user consents to the conversion (``consent: true``). The conversion:

1. The bridge command ``convert-tmdl`` writes the model as canonical TMDL into a
   staging folder next to ``model.bim`` and proves the TOM round trip.
2. ``model.bim`` is copied into the session folder (``apply/tmsl-backup/<source id>-<time>/``).
3. The staging folder becomes ``definition/`` and ``model.bim`` is removed. A failure
   before this step leaves the source unchanged.
4. The source record gets the new format and a new baseline.
"""

from __future__ import annotations

import copy
import os
from pathlib import Path
import shutil
from typing import Any
from collections.abc import Mapping
import uuid

from backend.adapters.tabular_metadata import ConvertFailed, TabularMetadataAdapter
from backend.devcenter.errors import DevCenterError, not_allowed
from backend.devcenter.session.store import utc_now
from backend.devcenter.sources.kinds import MODEL_BIM, MODEL_TMSL, detect_local_source

BACKUP_FOLDER = "apply/tmsl-backup"


def convert_to_tmdl(devcenter: Any, request: Mapping[str, Any], adapter: Any = None) -> dict[str, Any]:
    adapter = adapter or TabularMetadataAdapter()
    with devcenter._lock:
        source_id = request.get("source_id")
        current = devcenter._require_open()
        record = devcenter._source(current.document, source_id)
        if record["kind"] in {"cloud_model", "cloud_report"} or record.get("model_format") != MODEL_TMSL:
            raise not_allowed("Only a local model.bim source can be converted to TMDL.", "not_tmsl")
        if request.get("consent") is not True:
            raise not_allowed("The conversion rewrites the model folder. Give your consent first.", "consent_required")
        source = devcenter._load(record)
        assert source.model_dir is not None
        bim = source.model_dir / "model.bim"
        if not bim.is_file():
            raise DevCenterError("not_found", "The model.bim file does not exist.", {"reason": "missing"})
        definition = source.model_dir / "definition"
        if definition.exists():
            raise not_allowed("The model folder has a definition folder already.", "definition_exists")
        backup = Path(devcenter.session_folder()) / BACKUP_FOLDER / f"{source_id}-{utc_now().replace(':', '')}" / "model.bim"
        staging = source.model_dir / f".definition-{uuid.uuid4().hex}.tmp"
        state: dict[str, Any] = {"moved": False}

        def mutate(draft: dict[str, Any]) -> tuple[Any, Any]:
            item = devcenter._source(draft, source_id)
            before = copy.deepcopy(item)
            try:
                adapter.convert_tmdl(bim, staging)
            except ConvertFailed as exc:
                raise not_allowed("TOM could not convert the model to TMDL.", "convert_failed", code=exc.code) from exc
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(bim, backup)
            os.replace(staging, definition)
            state["moved"] = True
            bim.unlink()
            path = source.model_dir if record["kind"] == MODEL_BIM else devcenter._absolute(record["path"])
            converted = detect_local_source(path)
            item.update({"kind": converted.kind, "path": devcenter.relative_path(converted.root),
                         "model_path": devcenter.relative_path(converted.model_dir), "model_format": converted.model_format})
            devcenter._record_baseline(draft, source_id, converted)
            return before, {**copy.deepcopy(item), "backup": devcenter.relative_path(backup)}

        try:
            document = devcenter._change(request, "target_convert_tmdl", source_id, mutate)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            if state["moved"]:
                # Put the source back as it was: the TMSL file and no definition folder.
                if not bim.exists() and backup.is_file():
                    shutil.copy2(backup, bim)
                shutil.rmtree(definition, ignore_errors=True)
            raise
        saved = devcenter._source(document, source_id)
        return {"revision": document["revision"], "source": devcenter._source_view(document, saved),
                "backup_path": devcenter.relative_path(backup)}
