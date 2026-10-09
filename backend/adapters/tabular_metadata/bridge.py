"""Trusted TOM subprocess. No scripts or connections supplied by the agent."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
from typing import Any


class MetadataUnavailable(RuntimeError):
    code = "AUTHORITATIVE_METADATA_UNAVAILABLE"


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
