"""Real OS isolation evidence; no mock receipts, engine emulation or user files."""
from __future__ import annotations
import json
from pathlib import Path
import socket
import sys
import tempfile
import os
import uuid
from backend.snapshots.manifest import content_hash
from change_guard.workspace.windows import WindowsAppContainer


def isolation_proof() -> dict:
    with tempfile.TemporaryDirectory(prefix="pbi-guard-native-proof-") as temporary:
        root = Path(temporary)
        candidate = root / "candidate"
        candidate.mkdir()
        (candidate / "input.json").write_text('{}', encoding="utf-8")
        protected = [root / name for name in ("authoritative", "baseline", "policy", "audit", "unrelated")]
        for path in protected:
            path.mkdir()
            (path / "canary.json").write_text('{"protected":true}', encoding="utf-8")
        before = {str(path / "canary.json"): content_hash((path / "canary.json").read_bytes()) for path in protected}
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        socket.create_connection(("127.0.0.1", port), timeout=2).close()
        connection, _ = listener.accept()
        connection.close()
        script = """
import json, pathlib, socket, subprocess, sys
candidate = pathlib.Path.cwd()
results = {}
for path in json.loads(sys.argv[1]):
    for action in ('read', 'write', 'create'):
        try:
            file = pathlib.Path(path)
            if action == 'read': file.read_bytes()
            elif action == 'write': file.write_text('violated')
            else: (file.parent / 'escape.json').write_text('violated')
            results[path + ':' + action] = 'ALLOWED'
        except PermissionError: results[path + ':' + action] = 'DENIED'
        except Exception as error: results[path + ':' + action] = type(error).__name__
try:
    socket.create_connection(('127.0.0.1', int(sys.argv[2])), timeout=2).close()
    results['network'] = 'ALLOWED'
except PermissionError: results['network'] = 'DENIED'
except TimeoutError: results['network'] = 'BLOCKED_TIMEOUT'
except Exception as error: results['network'] = type(error).__name__
(candidate / 'allowed.json').write_text('{"candidate_write":true}')
try:
    (candidate / 'link.json').hardlink_to(pathlib.Path(json.loads(sys.argv[1])[0]))
    results['hardlink'] = 'ALLOWED'
except PermissionError: results['hardlink'] = 'DENIED'
except Exception as error: results['hardlink'] = type(error).__name__
(candidate / 'proof.json').write_text(json.dumps(results))
sys.exit(0 if all(value == 'DENIED' or (key == 'network' and value == 'BLOCKED_TIMEOUT') for key, value in results.items()) else 3)
"""
        executable = Path(sys._base_executable).resolve()
        runtime_canary = executable.parent / ("guard-proof-" + uuid.uuid4().hex + ".json")
        script = script.replace("(candidate / 'proof.json').write_text(json.dumps(results))", """
try:
    pathlib.Path(sys.argv[3]).write_text('guard proof')
    results['runtime_write'] = 'ALLOWED'
except PermissionError: results['runtime_write'] = 'DENIED'
except Exception as error: results['runtime_write'] = type(error).__name__
import ctypes
kernel = ctypes.WinDLL('kernel32', use_last_error=True)
kernel.OpenProcess.restype = ctypes.c_void_p
handle = kernel.OpenProcess(0x28, False, int(sys.argv[4]))
results['controller_process_write_access'] = 'ALLOWED' if handle else 'DENIED'
if handle:
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel.CloseHandle(handle)
child = 'import pathlib,sys; p=pathlib.Path(sys.argv[1]);\\ntry: p.write_text("escape");sys.exit(3)\\nexcept PermissionError:sys.exit(0)'
result = subprocess.run([sys.executable, '-I', '-c', child, json.loads(sys.argv[1])[0]], capture_output=True)
results['child_protected_write'] = 'DENIED' if result.returncode == 0 else 'FAILED'
subprocess.Popen([sys.executable, '-I', '-c', 'import time,pathlib;time.sleep(10);pathlib.Path("late-write.json").write_text("escape")'])
(candidate / 'proof.json').write_text(json.dumps(results))
""")
        try:
            receipt = WindowsAppContainer((executable.parent,), timeout=30).run(candidate,
                [str(executable), "-I", "-c", script, json.dumps(list(before)), str(port), str(runtime_canary), str(os.getpid())], protected_roots=protected)
        finally:
            listener.close()
            if runtime_canary.exists():
                if runtime_canary.read_text() != "guard proof": raise AssertionError("Unexpected runtime canary contents")
                runtime_canary.unlink()
        after = {path: content_hash(Path(path).read_bytes()) for path in before}
        attempts = json.loads((candidate / "proof.json").read_text())
        verified = receipt["status"] == "PASSED" and before == after and (candidate / "allowed.json").is_file() and all(not (path / "escape.json").exists() for path in protected) and not (candidate / "late-write.json").exists() and receipt["descendants_exited"]
        if not verified:
            raise AssertionError({"receipt": receipt, "attempts": attempts, "protected_unchanged": before == after})
        return {"proof_version": 1, "status": "PASSED", "kind": "REAL_WINDOWS_OS", "receipt": receipt,
                "attempts": [{"target": Path(key.rsplit(":", 1)[0]).parent.name if ":" in key else key, "action": key.rsplit(":", 1)[-1], "result": value} for key, value in attempts.items()],
                "protected_unchanged": True, "candidate_write_verified": True, "listener_control_connection_verified": True, "cleanup_verified": True}


if __name__ == "__main__":
    result = isolation_proof()
    if len(sys.argv) == 2:
        Path(sys.argv[1]).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
