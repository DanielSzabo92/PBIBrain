"""Pin Microsoft PBIR schemas and transitive references; development tool only."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urljoin, urldefrag
from urllib.request import urlopen, Request

PREFIX = "https://developer.microsoft.com/json-schemas/"
ROOT = Path(__file__).resolve().parents[1] / "backend/adapters/pbir/schemas"
# The app reads all versions and writes a changed file in its own version
# (design section 9.2). Thus pin each published version of each root family.
# The last version in each list is the current version.
VERSIONS = {
    "report": ("1.0.0", "1.1.0", "1.2.0", "1.3.0", "2.0.0", "2.1.0", "3.0.0", "3.1.0", "3.2.0", "3.3.0"),
    "page": ("1.0.0", "1.1.0", "1.2.0", "1.3.0", "1.4.0", "2.0.0", "2.1.0"),
    "visualContainer": ("1.0.0", "1.1.0", "1.2.0", "1.3.0", "1.4.0", "1.5.0", "1.6.0", "1.7.0", "1.8.0", "2.0.0", "2.1.0", "2.2.0",
                        "2.3.0", "2.4.0", "2.5.0", "2.6.0", "2.7.0", "2.8.0", "2.9.0", "2.10.0", "2.11.0", "2.12.0", "2.13.0"),
    "pagesMetadata": ("1.0.0", "1.1.0"),
    "bookmark": ("1.0.0", "1.1.0", "1.2.0", "1.3.0", "1.4.0", "2.0.0", "2.1.0"),
    "bookmarksMetadata": ("1.0.0",),
    "reportExtension": ("1.0.0",),
    "versionMetadata": ("1.0.0",),
}
ROOTS = ["fabric/item/report/definition/" + family + "/" + version + "/schema.json" for family, versions in VERSIONS.items() for version in versions]
ROOTS += ["fabric/item/report/definitionProperties/" + version + "/schema.json" for version in ("1.0.0", "2.0.0")]

def read(url):
    with urlopen(Request(url, headers={"User-Agent": "PBIBrain-schema-vendor"}), timeout=30) as response:
        return response.read()

def references(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "$ref" and isinstance(item, str): yield item
            elif isinstance(item, (list, dict)): yield from references(item)
    elif isinstance(value, list):
        for item in value: yield from references(item)

def main():
    commit = json.loads(read("https://api.github.com/repos/microsoft/json-schemas/commits/main"))["sha"]
    if not re.fullmatch("[0-9a-f]{40}", commit): raise ValueError("Invalid upstream revision")
    ROOT.mkdir(parents=True, exist_ok=True)
    pending, files = list(ROOTS), {}
    while pending:
        path = pending.pop(0)
        if path in files: continue
        if not path.startswith("fabric/item/report/") or ".." in Path(path).parts: raise ValueError("Unexpected upstream schema path")
        content = read(f"https://raw.githubusercontent.com/microsoft/json-schemas/{commit}/{path}")
        document = json.loads(content)
        canonical = PREFIX + path
        for reference in references(document):
            uri = urldefrag(urljoin(canonical, reference))[0]
            if not uri.startswith(PREFIX): raise ValueError("External schema reference: " + uri)
            target = uri[len(PREFIX):]
            if target != path: pending.append(target)
        target = ROOT / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        files[path] = {"uri": canonical, "sha256": hashlib.sha256(content).hexdigest()}
    license_content = read(f"https://raw.githubusercontent.com/microsoft/json-schemas/{commit}/LICENSE")
    (ROOT / "LICENSE").write_bytes(license_content)
    (ROOT / "manifest.json").write_text(json.dumps({"schema_catalog_version": 1, "upstream": "https://github.com/microsoft/json-schemas", "revision": commit, "files": files,
        "license_sha256": hashlib.sha256(license_content).hexdigest()}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"revision": commit, "schemas": len(files)}))

if __name__ == "__main__": main()
