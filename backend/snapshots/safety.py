"""Reject credential-bearing artifacts before they enter guarded evidence."""
import json
from pathlib import Path
import re
from .manifest import SourceIntegrityError, safe_path

SECRET_KEYS = {"password", "pwd", "impersonationpassword", "accesstoken", "refreshtoken", "clientsecret", "apikey", "accountkey", "credentials", "credentialdetails", "privatekey"}


def assert_no_credentials(root: Path, manifest: list[dict]) -> None:
    def normalized(value: str) -> str:
        return re.sub(r"[^a-z]", "", value.casefold())

    def walk(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if normalized(key) in SECRET_KEYS and child not in (None, "", {}, []):
                    raise SourceIntegrityError("Credential-bearing metadata is forbidden in guarded workspaces")
                walk(child)
            if normalized(str(value.get("name", ""))) in SECRET_KEYS and (value.get("value") or value.get("expression")):
                raise SourceIntegrityError("Secret-valued annotation/parameter is forbidden")
        elif isinstance(value, list):
            for child in value:
                walk(child)
        elif isinstance(value, str) and re.search(r"(?i)(?:password|pwd|client[_ ]?secret|api[_ ]?key|account[_ ]?key)\s*=\s*[^;\s]+|Bearer\s+[A-Za-z0-9._-]{8,}", value):
            raise SourceIntegrityError("Potential literal credential must be removed from guarded inputs")

    for item in manifest:
        path = safe_path(root, item["path"], must_exist=True)
        if path.suffix.casefold() in {".json", ".bim", ".pbip", ".pbir"} or path.name == ".platform":
            walk(json.loads(path.read_text(encoding="utf-8-sig")))
        elif path.suffix.casefold() == ".tmdl":
            text = path.read_text(encoding="utf-8-sig")
            if re.search(r"(?im)^\s*(?:password|impersonationPassword|accessToken|clientSecret|privateKey)\s*:\s*\S", text):
                raise SourceIntegrityError("Credential-bearing TMDL cannot enter guarded workspaces")
            walk(text)
