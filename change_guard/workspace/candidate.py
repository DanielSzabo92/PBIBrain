from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
import uuid
from backend.snapshots.manifest import source_manifest, safe_path, EXCLUDED_DIRECTORIES, SourceIntegrityError, content_hash, utc_now
from backend.snapshots.safety import assert_no_credentials
from change_guard.audit.records import durable_write


class IsolationUnavailable(RuntimeError):
    code = "PROCESS_ISOLATION_UNAVAILABLE"


def create_candidate(source: str | Path, destination: str | Path, pinned_manifest: list[dict]) -> list[dict]:
    source, destination = Path(source).absolute(), Path(destination).absolute()
    if destination == source or destination.is_relative_to(source) or source.is_relative_to(destination):
        raise SourceIntegrityError("Candidate and authoritative roots must be disjoint")
    if source_manifest(source) != pinned_manifest:
        raise SourceIntegrityError("Baseline changed before workspace creation")
    assert_no_credentials(source, pinned_manifest)
    destination.mkdir(parents=True, exist_ok=False)
    for item in pinned_manifest:
        data = safe_path(source, item["path"], must_exist=True).read_bytes()
        if content_hash(data) != item["hash"]:
            raise SourceIntegrityError("Concurrent source modification")
        durable_write(safe_path(destination, item["path"]), data, exclusive=True)
    copied = source_manifest(destination)
    if copied != pinned_manifest or source_manifest(source) != pinned_manifest:
        raise SourceIntegrityError("Candidate copy verification failed")
    return copied


def assert_candidate_integrity(root: str | Path) -> list[dict]:
    root = Path(root)
    for directory, dirs, files in os.walk(root, followlinks=False):
        if set(dirs) & EXCLUDED_DIRECTORIES:
            raise SourceIntegrityError("Agent created a protected/excluded directory")
    manifest = source_manifest(root)
    assert_no_credentials(root, manifest)
    return manifest


class DockerIsolation:
    """Only one writable bind mount. No host home, sources, sockets or secrets.

    A local, trusted, digest-pinned image is required; never automatically pulled.
    Docker absence is NOT_RUN, never permission separation by convention.
    """
    def __init__(self, image: str, *, docker: str = "docker", timeout: int = 300) -> None:
        if not re.fullmatch(r"[a-zA-Z0-9./_-]+@sha256:[0-9a-f]{64}", image):
            raise ValueError("Trusted image must be digest-pinned")
        self.image, self.docker, self.timeout = image, docker, timeout

    def run(self, candidate: str | Path, command: list[str]) -> dict:
        candidate = Path(candidate).absolute()
        assert_candidate_integrity(candidate)
        if not command or any(not isinstance(arg, str) or "\x00" in arg for arg in command) or not shutil.which(self.docker):
            raise IsolationUnavailable("Container runtime unavailable")
        inspected = subprocess.run([self.docker, "image", "inspect", self.image], capture_output=True, timeout=30, check=False)
        if inspected.returncode:
            raise IsolationUnavailable("Trusted pinned image unavailable")
        name = "pbi-guard-" + uuid.uuid4().hex
        arguments = [self.docker, "run", "--rm", "--name", name, "--network=none", "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges",
                     "--user=10000:10000", "--pids-limit=128", "--memory=2g", "--cpus=2", "--tmpfs=/tmp:rw,noexec,nosuid,size=64m",
                     "--mount", f"type=bind,source={candidate},target=/candidate", "--workdir=/candidate", "--entrypoint", command[0], self.image, *command[1:]]
        if "," in str(candidate):
            raise SourceIntegrityError("Unsupported candidate mount path")
        try:
            process = subprocess.run(arguments, capture_output=True, timeout=self.timeout, check=False)
        except subprocess.TimeoutExpired as error:
            subprocess.run([self.docker, "rm", "--force", name], capture_output=True, timeout=30, check=False)
            raise IsolationUnavailable("Agent process timed out and was terminated") from error
        manifest = assert_candidate_integrity(candidate)
        return {"isolation_version": 1, "status": "PASSED" if process.returncode == 0 else "FAILED", "backend": "DOCKER", "image": self.image,
                "candidate_source_hash": content_hash(manifest), "process_exit_code": process.returncode, "finished_at": utc_now(),
                "network": "NONE", "writable_mounts": ["/candidate"], "command_hash": content_hash(command),
                "stdout_hash": content_hash(process.stdout), "stderr_hash": content_hash(process.stderr)}
