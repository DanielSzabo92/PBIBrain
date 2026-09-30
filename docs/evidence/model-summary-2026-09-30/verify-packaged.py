"""Read-only summary acceptance through the frozen executable's native API."""

import hashlib
import json
import socket
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

from backend.projects import ProjectService
from tests.fixtures.pbip_sources import write_pbip_project


root = Path(__file__).resolve().parents[3]
exe = root / "dist/PBIBrain/PBIBrain-Agent.exe"
evidence = Path(__file__).parent
with tempfile.TemporaryDirectory(prefix="pbibrain-summary-package-") as temporary:
    folder = Path(temporary)
    project = write_pbip_project(folder / "Finance")
    hashes = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in project.parent.rglob("*") if path.is_file()}
    config = folder / "brain.json"
    ProjectService(config).save_config({"version": 1, "name": "Summary example", "sources": [str(project)],
                                       "database": "brain.lbug", "identity_map": "identity.json"})
    subprocess.run([str(exe), "--config", str(config), "project-scan"], capture_output=True, check=True, timeout=30)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    with (evidence / "packaged-server.log").open("w", encoding="utf-8") as log:
        server = subprocess.Popen([str(exe), "--config", str(config), "serve", "--port", str(port)], stdout=log, stderr=log)
        try:
            origin = f"http://127.0.0.1:{port}/api"
            for attempt in range(50):
                try:
                    with urlopen(origin + "/overview", timeout=1) as response:
                        overview = json.load(response)
                    break
                except OSError:
                    time.sleep(.1)
            else:
                raise RuntimeError("Packaged server did not start")
            model_id = overview["model_ids"][0]
            url = origin + "/model-summary?" + urlencode({"model_id": model_id})
            with urlopen(url, timeout=10) as response:
                summary = json.load(response)
            with urlopen(url, timeout=10) as response:
                assert json.load(response) == summary
            assert overview["storage"] == "ladybug"
            for text in ("'Sales'[DateKey]", "'Date'[DateKey]", "Sales by date"):
                assert text in summary["markdown"]
            assert hashes == {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in hashes}
            (evidence / "model-context.md").write_bytes(summary["markdown"].encode("utf-8"))
            result = {"storage": overview["storage"], "model_id": model_id, "snapshot_id": summary["snapshot_id"],
                      "object_counts": summary["object_counts"], "utf8_bytes": len(summary["markdown"].encode("utf-8")),
                      "source_files_unchanged": len(hashes), "deterministic_export": True,
                      "executable_sha256": hashlib.sha256(exe.read_bytes()).hexdigest()}
            (evidence / "packaged-results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
            print(json.dumps(result))
        finally:
            server.terminate()
            server.wait(timeout=10)
