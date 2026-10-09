from __future__ import annotations

from contextlib import contextmanager
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
from backend.snapshots.manifest import canonical_json, content_hash, safe_path, utc_now


class AuditIntegrityError(RuntimeError):
    code = "AUDIT_INTEGRITY"


@contextmanager
def exclusive_lock(path: Path):
    """OS lock releases on process exit; lock existence is not ownership."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        stream.seek(0)
        if stream.read(1) == b"":
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise AuditIntegrityError("Concurrent guard operation") from error
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def durable_write(path: Path, data: bytes, *, exclusive: bool = False, temporary_path: Path | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if exclusive:
        with path.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        return
    temporary = temporary_path or path.with_name(path.name + ".writing")
    temporary.parent.mkdir(parents=True, exist_ok=True)
    with temporary.open("wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


class AuditStore:
    """Agent container never receives this directory or its signing key."""
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).absolute()
        self.root.mkdir(parents=True, exist_ok=True)
        safe_path(self.root, "controller.key")
        with exclusive_lock(self.root / "controller.lock"):
            key_path = self.root / "controller.key"
            if not key_path.exists():
                durable_write(key_path, secrets.token_bytes(32), exclusive=True)
                if os.name != "nt":
                    key_path.chmod(0o600)
            self._key = key_path.read_bytes()
        if len(self._key) != 32:
            raise AuditIntegrityError("Controller key corrupted")

    def sign(self, payload: dict) -> dict:
        return {"payload": payload, "signature": hmac.new(self._key, canonical_json(payload).encode("utf-8"), hashlib.sha256).hexdigest()}

    def verify(self, envelope: dict) -> dict:
        try:
            expected = self.sign(envelope["payload"])["signature"]
            if not hmac.compare_digest(expected, envelope["signature"]):
                raise AuditIntegrityError("Trusted record signature mismatch")
            return envelope["payload"]
        except (KeyError, TypeError) as error:
            raise AuditIntegrityError("Invalid trusted record") from error

    def save(self, relative: str, payload: dict, *, exclusive: bool = False) -> None:
        path = safe_path(self.root, relative)
        durable_write(path, canonical_json(self.sign(payload)).encode("utf-8"), exclusive=exclusive)

    def load(self, relative: str) -> dict:
        return self.verify(json.loads(safe_path(self.root, relative, must_exist=True).read_text(encoding="utf-8")))

    def read(self, operation_id: str) -> list[dict]:
        path = safe_path(self.root, operation_id + "/audit.jsonl")
        previous, records = None, []
        if not path.exists():
            if safe_path(self.root, operation_id + "/audit-head.json").exists():
                raise AuditIntegrityError("Audit history removed")
            return records
        try:
            data = path.read_bytes()
            if data and not data.endswith(b"\n"):
                raise AuditIntegrityError("Incomplete audit write")
            for line in data.splitlines():
                envelope = json.loads(line)
                record = self.verify(envelope)
                if record["previous_hash"] != previous or record["sequence"] != len(records) or record["operation_id"] != operation_id:
                    raise AuditIntegrityError("Audit hash chain broken")
                records.append(record)
                previous = content_hash(envelope)
        except (ValueError, KeyError) as error:
            raise AuditIntegrityError("Audit record corrupted") from error
        head_path = operation_id + "/audit-head.json"
        if records:
            if not safe_path(self.root, head_path).exists():
                raise AuditIntegrityError("Audit head missing")
            head = self.load(head_path)
            if head != {"operation_id": operation_id, "count": len(records), "last_hash": previous}:
                raise AuditIntegrityError("Audit head mismatch or truncated history")
        elif safe_path(self.root, head_path).exists():
            raise AuditIntegrityError("Audit history removed")
        return records

    def append(self, operation_id: str, event: str, payload: dict) -> dict:
        path = safe_path(self.root, operation_id + "/audit.jsonl")
        path.parent.mkdir(parents=True, exist_ok=True)
        with exclusive_lock(path.with_suffix(".lock")):
            existing = self.read(operation_id)
            last = json.loads(path.read_bytes().splitlines()[-1]) if existing else None
            record = {"audit_version": 1, "operation_id": operation_id, "event": event, "timestamp": utc_now(),
                      "sequence": len(existing), "previous_hash": content_hash(last) if last else None, "payload": payload}
            encoded = (canonical_json(self.sign(record)) + "\n").encode("utf-8")
            with path.open("ab") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            # A separate signed head detects removal of a valid final record.
            # An interruption between these writes fails closed on restart.
            self.save(operation_id + "/audit-head.json", {"operation_id": operation_id, "count": len(existing) + 1, "last_hash": content_hash(self.sign(record))})
            return record

    def verify_integrity(self, operation_id: str) -> dict:
        """Retain the actual signed-head and tail-hash integrity comparison."""
        path = safe_path(self.root, operation_id + "/audit.jsonl")
        with exclusive_lock(path.with_suffix(".lock")):
            records = self.read(operation_id)  # verifies each HMAC and every link
            if not records: raise AuditIntegrityError("No audit evidence to verify")
            head = self.load(operation_id + "/audit-head.json")
            tail = content_hash(self.sign(records[-1]))
            matches = head == {"operation_id": operation_id, "count": len(records), "last_hash": tail}
            if not matches: raise AuditIntegrityError("Audit head comparison failed")
            return {"integrity_verified": matches, "head": head, "computed_tail_hash": tail,
                    "terminal_event": records[-1]["event"], "algorithm": "HMAC-SHA256_AND_CONTENT_HASH_CHAIN"}
