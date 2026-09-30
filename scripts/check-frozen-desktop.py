"""Release gate: scan a real PBIP and reopen it using the frozen executable."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tests.fixtures.pbip_sources import write_pbip_project


def main():
    executable = Path(sys.argv[1]).resolve()
    environment = dict(os.environ)
    for key in ("PYTHONPATH", "PYTHONHOME", "LBUG_C_API_LIB_PATH", "LBUG_PYTHON_BACKEND"):
        environment.pop(key, None)
    with tempfile.TemporaryDirectory(prefix="PBIBrain-frozen-") as temporary:
        for folder_name in ("Finance project", "Audit á (test)", "Audit á # (precreated)", "审计 🧠"):
            project = Path(temporary) / folder_name
            write_pbip_project(project)
            sources = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in project.rglob("*") if p.is_file()}
            config = project / ".pbibrain" / "brain.json"
            config.parent.mkdir()
            config.write_text(json.dumps({"version": 1, "name": "Finance", "sources": ["../Finance.pbip"],
                                         "database": "brain.lbug", "identity_map": "identity-map.json"}), encoding="utf-8")

            def run(*arguments):
                result = subprocess.run([str(executable), "--project", str(project), *arguments],
                                        cwd=temporary, env=environment, capture_output=True, text=True, encoding="utf-8", timeout=120)
                if result.returncode:
                    raise RuntimeError(f"Frozen {' '.join(arguments)} failed: {result.stderr or result.stdout}")
                return json.loads(result.stdout)

            scanned = run("project-scan")
            reopened = run("status", "--json")
            if reopened.get("storage") != "ladybug" or scanned["nodes"] <= 0 or scanned["edges"] <= 0:
                raise RuntimeError(f"Native graph was not created: {scanned}, {reopened}")
            if any(reopened[key] != scanned[key] for key in ("nodes", "edges")):
                raise RuntimeError(f"Frozen reopen changed graph counts: {scanned}, {reopened}")
            if any(hashlib.sha256(p.read_bytes()).hexdigest() != digest for p, digest in sources.items()):
                raise RuntimeError("Scan modified PBIP source files")
            print(f"Frozen native scan/reopen passed: {reopened['nodes']} nodes, {reopened['edges']} edges")



if __name__ == "__main__":
    main()
