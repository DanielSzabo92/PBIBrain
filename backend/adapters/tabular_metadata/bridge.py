"""Trusted TOM subprocess. No scripts or connections supplied by the agent."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
from typing import Any, Mapping, Sequence


class MetadataUnavailable(RuntimeError):
    code = "AUTHORITATIVE_METADATA_UNAVAILABLE"


class ModelWriteFailed(MetadataUnavailable):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


class CanonicalCheckFailed(MetadataUnavailable):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


class TreeCompareFailed(MetadataUnavailable):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


class TabularMetadataAdapter:
    def __init__(self, bridge: str | Path | None = None, *, timeout: int = 60) -> None:
        self.bridge = Path(bridge) if bridge else Path(__file__).parent / "dotnet" / "bin" / "Release" / "net8.0" / "TabularMetadata.dll"
        self.timeout = timeout

    def read(self, source: str | Path, *, include_documents: bool = False) -> dict[str, Any]:
        if not self.bridge.is_file():
            raise MetadataUnavailable("Build the trusted TOM bridge before model verification")
        try:
            command = ["dotnet", str(self.bridge.resolve()), str(Path(source).resolve())]
            if include_documents:
                command.append("--documents")
            result = subprocess.run(command,
                                    capture_output=True, text=True, encoding="utf-8", timeout=self.timeout, check=False)
            payload = json.loads(result.stdout)
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            raise MetadataUnavailable("TOM bridge failed or timed out") from exc
        if result.returncode or payload.get("status") != "PASSED" or payload.get("adapter_version") != 1:
            raise MetadataUnavailable(payload.get("error", "TOM deserialization failed"))
        if not isinstance(payload.get("database"), dict) or not payload.get("roundtrip_verified"):
            raise MetadataUnavailable("TOM did not prove serialization integrity")
        return payload

    def write_model(self, model_path: str | Path, candidate_path: str | Path,
                    operations: Sequence[Mapping[str, Any]] = ()) -> dict[str, Any]:
        """Apply ordered Change Plan operations to a TOM model in memory and serialize to candidate folder."""
        if not self.bridge.is_file():
            raise ModelWriteFailed("bridge_missing", "Build the trusted TOM bridge before writing models")

        model_resolved = Path(model_path).resolve()
        candidate_resolved = Path(candidate_path).resolve()

        if model_resolved.name.lower() == "definition":
            def_folder = model_resolved
        elif (model_resolved / "definition").is_dir():
            def_folder = (model_resolved / "definition").resolve()
        else:
            def_folder = model_resolved

        if candidate_resolved == def_folder or def_folder in candidate_resolved.parents:
            raise ModelWriteFailed("destination_is_definition_folder",
                                   "Candidate path cannot be the model definition folder or inside it.")

        try:
            command = ["dotnet", str(self.bridge.resolve()), "write-model", str(model_resolved), str(candidate_resolved)]
            ops_json = json.dumps(list(operations))
            result = subprocess.run(command, input=ops_json, capture_output=True, text=True,
                                    encoding="utf-8", timeout=self.timeout, check=False)
            payload = json.loads(result.stdout)
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            raise ModelWriteFailed("write_failed", "TOM model writer bridge failed or timed out") from exc

        if result.returncode or payload.get("status") != "PASSED" or payload.get("adapter_version") != 1:
            code = str(payload.get("code") or "write_failed")
            error = str(payload.get("error") or "TOM model write failed")
            raise ModelWriteFailed(code, error)

        return payload

    def canonical_check(self, model_path: str | Path) -> dict[str, Any]:
        """Check whether all TMDL files in the model folder match TOM canonical serialization."""
        if not self.bridge.is_file():
            raise CanonicalCheckFailed("bridge_missing", "Build the trusted TOM bridge before canonical check")

        model_resolved = Path(model_path).resolve()
        try:
            command = ["dotnet", str(self.bridge.resolve()), "canonical-check", str(model_resolved)]
            result = subprocess.run(command, input="", capture_output=True, text=True,
                                    encoding="utf-8", timeout=self.timeout, check=False)
            payload = json.loads(result.stdout)
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            raise CanonicalCheckFailed("check_failed", "TOM canonical check bridge failed or timed out") from exc

        if result.returncode or payload.get("status") != "PASSED" or payload.get("adapter_version") != 1:
            code = str(payload.get("code") or "check_failed")
            error = str(payload.get("error") or "TOM canonical check failed")
            raise CanonicalCheckFailed(code, error)

        return payload

    def tree_compare(self, baseline_path: str | Path, candidate_path: str | Path) -> dict[str, Any]:
        """Compare two models object by object over the full TOM tree (including Perspectives and Cultures)."""
        if not self.bridge.is_file():
            raise TreeCompareFailed("bridge_missing", "Build the trusted TOM bridge before tree compare")

        baseline_resolved = Path(baseline_path).resolve()
        candidate_resolved = Path(candidate_path).resolve()
        try:
            command = ["dotnet", str(self.bridge.resolve()), "tree-compare",
                       str(baseline_resolved), str(candidate_resolved)]
            result = subprocess.run(command, input="", capture_output=True, text=True,
                                    encoding="utf-8", timeout=self.timeout, check=False)
            payload = json.loads(result.stdout)
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            raise TreeCompareFailed("compare_failed", "TOM tree compare bridge failed or timed out") from exc

        if result.returncode or payload.get("status") != "PASSED" or payload.get("adapter_version") != 1:
            code = str(payload.get("code") or "compare_failed")
            error = str(payload.get("error") or "TOM tree compare failed")
            raise TreeCompareFailed(code, error)

        return payload
