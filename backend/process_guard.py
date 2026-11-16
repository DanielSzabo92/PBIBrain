"""Run an outside program on a short leash: one place for every child process an agent feature starts.

Two features start programs that PBIBrain does not control: the change guard's no-container
agent tier (``change_guard/workspace/candidate.py``) and the subscription CLI providers of the
in-app chat (``backend/chat/cli_providers.py``). Both go through ``run_bounded``:

- the program gets an exact argument list (no shell) and its input on stdin, never in argv, so
  project text can never become a command line (``cmd.exe`` would read quotes and ``&`` in it);
- it runs in its own process group, and a timeout, a Stop or too much output kills the whole
  group, not only the first process (an agent CLI starts helpers that would outlive it);
- stdout and stderr are read with a size cap, so a runaway program cannot fill memory;
- the environment is scrubbed of credentials by name (``scrubbed_environment``) unless the
  caller names the few variables a program needs for its own sign-in.
"""

from __future__ import annotations

import os
import re
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from collections.abc import Callable, Iterable, Mapping, Sequence

DEFAULT_MAX_OUTPUT = 4 * 1024 * 1024
POLL_SECONDS = 0.05

# Variable names that carry a secret: API keys, tokens, passwords, cloud credentials.
SECRET_NAME = re.compile(
    r"(KEY|TOKEN|SECRET|PASSWORD|PASSWD|PWD_|CREDENTIAL|AUTH_|_AUTH$|CONNECTION_?STRING|SAS_|PRIVATE)"
    r"|^(AWS_|AZURE_|ARM_|GOOGLE_APPLICATION|GCLOUD_|NPM_CONFIG__AUTH|PIP_INDEX_URL|DOCKER_)",
    re.IGNORECASE,
)


class ProcessLimit(RuntimeError):
    """The program was stopped: ``reason`` is ``timeout``, ``stopped`` or ``output_limit``."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True)
class Finished:
    returncode: int
    stdout: bytes
    stderr: bytes


def scrubbed_environment(keep: Iterable[str] = (), *, base: Mapping[str, str] | None = None,
                         extra: Mapping[str, str] | None = None) -> dict[str, str]:
    """The environment without secret-looking variables; ``keep`` names exceptions a program needs."""

    source = os.environ if base is None else base
    kept = {name.upper() for name in keep}
    result = {name: value for name, value in source.items() if name.upper() in kept or not SECRET_NAME.search(name)}
    result.update(extra or {})
    return result


def _group_options() -> dict:
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | getattr(subprocess, "CREATE_NO_WINDOW", 0)}
    return {"start_new_session": True}


def kill_tree(process: subprocess.Popen) -> None:
    """Kill the program and every process it started in its group."""

    if process.poll() is not None:
        if os.name != "nt":
            try:
                os.killpg(process.pid, signal.SIGKILL)  # helpers may still run in the group
            except (ProcessLookupError, PermissionError, OSError):
                pass
        return
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)], capture_output=True, timeout=15, check=False)
        else:
            os.killpg(process.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError, subprocess.SubprocessError):
        pass
    try:
        process.kill()
    except OSError:
        pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass


def _reader(stream, sink: list[bytes], total: list[int], limit: int, over: threading.Event) -> None:
    try:
        while True:
            chunk = stream.read(65536)
            if not chunk:
                return
            if total[0] + len(chunk) > limit:
                sink.append(chunk[: max(0, limit - total[0])])
                total[0] = limit
                over.set()
                return
            sink.append(chunk)
            total[0] += len(chunk)
    except (OSError, ValueError):
        return


def run_bounded(command: Sequence[str], *, cwd: str | os.PathLike | None, env: Mapping[str, str], timeout: float,
                input: bytes | None = None, should_stop: Callable[[], bool] | None = None,
                max_output: int = DEFAULT_MAX_OUTPUT) -> Finished:
    """Run ``command`` and wait; raise ``ProcessLimit`` after killing its group on a limit.

    Raises ``OSError`` when the program cannot start.
    """

    if not command or any(not isinstance(arg, str) or "\x00" in arg for arg in command):
        raise ValueError("Exact argument list required")
    process = subprocess.Popen(list(command), cwd=cwd, env=dict(env), stdin=subprocess.PIPE if input is not None else subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, **_group_options())
    out: list[bytes] = []
    err: list[bytes] = []
    total = [0]
    over = threading.Event()
    readers = [threading.Thread(target=_reader, args=(process.stdout, out, total, max_output, over), daemon=True),
               threading.Thread(target=_reader, args=(process.stderr, err, total, max_output, over), daemon=True)]
    for reader in readers:
        reader.start()
    if input is not None:
        def feed() -> None:
            try:
                process.stdin.write(input)
            except (BrokenPipeError, OSError, ValueError):
                pass
            finally:
                try:
                    process.stdin.close()
                except (OSError, ValueError):
                    pass
        threading.Thread(target=feed, daemon=True).start()
    deadline = time.monotonic() + timeout
    reason = ""
    while process.poll() is None:
        if over.is_set():
            reason = "output_limit"
        elif should_stop is not None and should_stop():
            reason = "stopped"
        elif time.monotonic() > deadline:
            reason = "timeout"
        if reason:
            break
        time.sleep(POLL_SECONDS)
    if reason:
        kill_tree(process)
    for reader in readers:
        reader.join(timeout=5)
    for stream in (process.stdout, process.stderr):
        try:
            stream.close()
        except OSError:
            pass
    if not reason and over.is_set():
        reason = "output_limit"
    if os.name != "nt":
        kill_tree(process)  # the program ended; end any helper it left in its group
    if reason:
        messages = {"timeout": f"The program did not finish within {int(timeout)} seconds and was stopped.",
                    "stopped": "The program was stopped.",
                    "output_limit": f"The program wrote more than {max_output} bytes and was stopped."}
        raise ProcessLimit(reason, messages[reason])
    return Finished(process.returncode, b"".join(out), b"".join(err))
