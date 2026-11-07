"""TMDL create, delete and rename coverage for agent edits (issue #17).

The line check in ``backend/diff/tmdl_source.py`` accounts only for scalar replacements. A
created measure, a deleted table file or a renamed column adds or removes whole blocks, and
that check fails closed on them. This proof reuses the merge guard's canonical-file rule
(ADR 0001) instead of extending the line check:

    each created or changed ``.tmdl`` file must be the text Microsoft's model library (TOM)
    writes for the candidate model, and each deleted file must be a file TOM no longer writes.

TOM reads the candidate folder and serializes it again. When the agent's file is that output,
the file holds nothing TOM does not read (no comments, no unknown text), so the TOM object
compare of the guard sees every change in it. The texts are compared with line endings made
equal; line endings carry no model meaning, and an agent on Linux or macOS writes LF.

A file that fails the proof is not rejected here. It goes on to the line check, which accepts
scalar edits to non-canonical files and rejects the rest, so the guard still fails closed.
"""

from __future__ import annotations

from pathlib import Path
import tempfile
from typing import Any

from backend.snapshots import source_manifest


def _model_root(root: Path, relative: str) -> str | None:
    """Walk up from a TMDL file to the folder that holds ``model.tmdl``."""

    folder = Path(relative).parent
    while folder.parts:
        if (root / folder / "model.tmdl").is_file():
            return folder.as_posix()
        folder = folder.parent
    return None


def _same_text(left: bytes, right: bytes) -> bool:
    def normal(value: bytes) -> bytes:
        return value.removeprefix(b"\xef\xbb\xbf").replace(b"\r\n", b"\n")
    return normal(left) == normal(right)


def prove_tmdl_changes(baseline_root: str | Path, candidate_root: str | Path, adapter: Any) -> dict[str, Any]:
    """Prove created, changed and deleted TMDL files by TOM regeneration of the candidate model."""

    from backend.adapters.tabular_metadata import MetadataUnavailable

    baseline_root, candidate_root = Path(baseline_root).absolute(), Path(candidate_root).absolute()
    old = {item["path"]: item["hash"] for item in source_manifest(baseline_root)}
    new = {item["path"]: item["hash"] for item in source_manifest(candidate_root)}
    changed = {path: "created" if path not in old else "deleted" if path not in new else "changed"
               for path in sorted(set(old) | set(new)) if old.get(path) != new.get(path) and path.casefold().endswith(".tmdl")}
    models: dict[str, list[str]] = {}
    violations: list[dict[str, Any]] = []
    for relative, kind in changed.items():
        folder = _model_root(candidate_root, relative) or _model_root(baseline_root, relative)
        if folder is None:
            violations.append({"code": "TMDL_OUTSIDE_MODEL", "file": relative})
            continue
        models.setdefault(folder, []).append(relative)
    proven: list[str] = []
    for folder, files in sorted(models.items()):
        definition = candidate_root / folder
        if not (definition / "model.tmdl").is_file():
            violations.extend({"code": "MODEL_REMOVED", "file": relative} for relative in files)
            continue
        with tempfile.TemporaryDirectory(prefix="tmdl-proof-") as work:
            output = Path(work) / "regenerated"
            try:
                adapter.write_model(definition, output, [])
            except MetadataUnavailable as error:
                violations.extend({"code": "MODEL_LOAD_FAILED", "file": relative, "reason": getattr(error, "code", type(error).__name__)}
                                  for relative in files)
                continue
            for relative in files:
                inner = Path(relative).relative_to(folder)
                expected = output / inner
                if changed[relative] == "deleted":
                    if expected.is_file():
                        violations.append({"code": "DELETED_FILE_STILL_WRITTEN", "file": relative})
                    else:
                        proven.append(relative)
                elif expected.is_file() and _same_text((candidate_root / relative).read_bytes(), expected.read_bytes()):
                    proven.append(relative)
                else:
                    violations.append({"code": "NON_CANONICAL_MODEL_FILE", "file": relative,
                                       "hint": "Write the file as the model library does (no comments, its order and tabs), or format the model first."})
    return {"tmdl_coverage_version": 1, "changed": changed, "proven_sources": sorted(proven), "violations": violations}
