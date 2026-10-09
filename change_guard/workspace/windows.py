"""Windows AppContainer isolation. No network capabilities or inherited handles.

The controller grants a unique package SID access to the candidate and explicit
read-only executable directories. Grants and the temporary profile are removed
after the entire job exits. No user account or system-wide policy is changed.
"""
from __future__ import annotations

import ctypes as c
from ctypes import wintypes as w
import os
from pathlib import Path
import subprocess
import uuid

from backend.snapshots.manifest import content_hash, utc_now
from .candidate import IsolationUnavailable, assert_candidate_integrity


class WindowsAppContainer:
    def __init__(self, runtime_roots: tuple[str | Path, ...], *, timeout: int = 300) -> None:
        self.runtime_roots = tuple(Path(root).resolve(strict=True) for root in runtime_roots)
        self.timeout = timeout

    def run(self, candidate: str | Path, command: list[str], *, protected_roots=()) -> dict:
        if os.name != "nt":
            raise IsolationUnavailable("Windows AppContainer requires Windows")
        candidate = Path(candidate).resolve(strict=True)
        assert_candidate_integrity(candidate)
        protected = tuple(Path(root).resolve() for root in protected_roots)
        if not command or not Path(command[0]).is_absolute() or any("\0" in arg for arg in command):
            raise ValueError("Exact absolute executable and argument list required")
        executable = Path(command[0]).resolve(strict=True)
        roots = (*self.runtime_roots, candidate)
        if not any(executable.is_relative_to(root) for root in self.runtime_roots):
            raise ValueError("Executable outside trusted read-only runtime")
        for root in roots:
            if root == Path(root.anchor) or root.is_symlink() or root.stat().st_file_attributes & 0x400:
                raise ValueError("Unsafe isolation grant root")
            if any(item.is_relative_to(root) or (root != candidate and root.is_relative_to(item)) for item in protected):
                raise ValueError("Isolation grant overlaps protected sources or state")
        return _run(candidate, command, self.runtime_roots, self.timeout)


def _run(candidate, command, runtime_roots, timeout):
    kernel = c.WinDLL("kernel32", use_last_error=True)
    userenv = c.WinDLL("userenv", use_last_error=True)
    advapi = c.WinDLL("advapi32", use_last_error=True)

    class Startup(c.Structure):
        _fields_ = [("cb", w.DWORD), ("reserved", w.LPWSTR), ("desktop", w.LPWSTR), ("title", w.LPWSTR),
                    ("x", w.DWORD), ("y", w.DWORD), ("xsize", w.DWORD), ("ysize", w.DWORD),
                    ("charsx", w.DWORD), ("charsy", w.DWORD), ("fill", w.DWORD), ("flags", w.DWORD),
                    ("show", w.WORD), ("reserved2size", w.WORD), ("reserved2", c.c_void_p),
                    ("stdin", w.HANDLE), ("stdout", w.HANDLE), ("stderr", w.HANDLE)]

    class StartupEx(c.Structure):
        _fields_ = [("startup", Startup), ("attributes", c.c_void_p)]

    class ProcessInfo(c.Structure):
        _fields_ = [("process", w.HANDLE), ("thread", w.HANDLE), ("pid", w.DWORD), ("tid", w.DWORD)]

    class Capabilities(c.Structure):
        _fields_ = [("sid", c.c_void_p), ("capabilities", c.c_void_p), ("count", w.DWORD), ("reserved", w.DWORD)]

    # Declare pointer-sized parameters explicitly; ctypes defaults truncate handles.
    userenv.CreateAppContainerProfile.argtypes = [w.LPCWSTR, w.LPCWSTR, w.LPCWSTR, c.c_void_p, w.DWORD, c.POINTER(c.c_void_p)]
    userenv.CreateAppContainerProfile.restype = c.c_long
    userenv.DeleteAppContainerProfile.argtypes = [w.LPCWSTR]
    userenv.DeleteAppContainerProfile.restype = c.c_long
    userenv.GetAppContainerFolderPath.argtypes = [w.LPCWSTR, c.POINTER(w.LPWSTR)]
    userenv.GetAppContainerFolderPath.restype = c.c_long
    advapi.ConvertSidToStringSidW.argtypes = [c.c_void_p, c.POINTER(w.LPWSTR)]
    advapi.OpenProcessToken.argtypes = [w.HANDLE, w.DWORD, c.POINTER(w.HANDLE)]
    advapi.GetTokenInformation.argtypes = [w.HANDLE, c.c_int, c.c_void_p, w.DWORD, c.POINTER(w.DWORD)]
    kernel.InitializeProcThreadAttributeList.argtypes = [c.c_void_p, w.DWORD, w.DWORD, c.POINTER(c.c_size_t)]
    kernel.UpdateProcThreadAttribute.argtypes = [c.c_void_p, w.DWORD, c.c_size_t, c.c_void_p, c.c_size_t, c.c_void_p, c.c_void_p]
    kernel.DeleteProcThreadAttributeList.argtypes = [c.c_void_p]
    kernel.CreateProcessW.argtypes = [w.LPCWSTR, w.LPWSTR, c.c_void_p, c.c_void_p, w.BOOL, w.DWORD, c.c_void_p, w.LPCWSTR, c.POINTER(StartupEx), c.POINTER(ProcessInfo)]
    kernel.CreateJobObjectW.argtypes = [c.c_void_p, w.LPCWSTR]
    kernel.CreateJobObjectW.restype = w.HANDLE
    kernel.SetInformationJobObject.argtypes = [w.HANDLE, c.c_int, c.c_void_p, w.DWORD]
    kernel.QueryInformationJobObject.argtypes = [w.HANDLE, c.c_int, c.c_void_p, w.DWORD, c.c_void_p]
    kernel.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
    kernel.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
    kernel.TerminateJobObject.argtypes = [w.HANDLE, w.UINT]
    kernel.TerminateProcess.argtypes = [w.HANDLE, w.UINT]
    kernel.GetExitCodeProcess.argtypes = [w.HANDLE, c.POINTER(w.DWORD)]
    kernel.ResumeThread.argtypes = [w.HANDLE]
    kernel.CloseHandle.argtypes = [w.HANDLE]
    kernel.LocalFree.argtypes = [c.c_void_p]
    advapi.FreeSid.argtypes = [c.c_void_p]

    def check(value):
        if not value:
            raise c.WinError(c.get_last_error())
        return value

    name = "PBIBrain.Guard." + uuid.uuid4().hex
    sid, sid_text = c.c_void_p(), w.LPWSTR()
    profile_created, grants, attributes, job, info = False, [], None, None, ProcessInfo()
    try:
        result = userenv.CreateAppContainerProfile(name, name, "Temporary PBIBrain candidate", None, 0, c.byref(sid))
        if result < 0:
            raise IsolationUnavailable("AppContainer profile creation failed: " + hex(result & 0xffffffff))
        profile_created = True
        check(advapi.ConvertSidToStringSidW(sid, c.byref(sid_text)))
        package = sid_text.value
        folder = w.LPWSTR()
        if userenv.GetAppContainerFolderPath(package, c.byref(folder)) < 0:
            raise IsolationUnavailable("AppContainer profile directory unavailable")
        profile = folder.value
        ole = c.WinDLL("ole32")
        ole.CoTaskMemFree.argtypes = [c.c_void_p]
        ole.CoTaskMemFree(folder)
        for root, permission in [(candidate, "(OI)(CI)M"), *((root, "(OI)(CI)RX") for root in runtime_roots)]:
            result = subprocess.run(["icacls", str(root), "/grant", "*" + package + ":" + permission, "/T", "/Q"], capture_output=True, check=False)
            grants.append(root)
            if result.returncode:
                raise IsolationUnavailable("AppContainer file grant failed")
        size = c.c_size_t()
        kernel.InitializeProcThreadAttributeList(None, 1, 0, c.byref(size))
        attributes = c.create_string_buffer(size.value)
        check(kernel.InitializeProcThreadAttributeList(attributes, 1, 0, c.byref(size)))
        capabilities = Capabilities(sid, None, 0, 0)
        check(kernel.UpdateProcThreadAttribute(attributes, 0, 0x20009, c.byref(capabilities), c.sizeof(capabilities), None, None))
        startup = StartupEx()
        startup.startup.cb = c.sizeof(StartupEx)
        startup.attributes = c.cast(attributes, c.c_void_p)
        # Kill every descendant on close; disallow breakaway. Active-process limit
        # allows normal compilers but prevents unlimited forks.
        class BasicLimit(c.Structure):
            _fields_ = [("process_time", c.c_longlong), ("job_time", c.c_longlong), ("flags", w.DWORD),
                        ("min_working", c.c_size_t), ("max_working", c.c_size_t), ("active_processes", w.DWORD),
                        ("affinity", c.c_size_t), ("priority", w.DWORD), ("scheduling", w.DWORD)]
        class ExtendedLimit(c.Structure):
            _fields_ = [("basic", BasicLimit), ("io", c.c_ulonglong * 6), ("process_memory", c.c_size_t),
                        ("job_memory", c.c_size_t), ("peak_process_memory", c.c_size_t), ("peak_job_memory", c.c_size_t)]
        limits = ExtendedLimit()
        limits.basic.flags = 0x2000 | 0x8 | 0x200  # kill-on-close, active-process and job-memory limits
        limits.basic.active_processes = 128
        limits.job_memory = 2 * 1024 ** 3
        job = check(kernel.CreateJobObjectW(None, None))
        check(kernel.SetInformationJobObject(job, 9, c.byref(limits), c.sizeof(limits)))
        environment = {"SystemRoot": os.environ["SystemRoot"], "WINDIR": os.environ["SystemRoot"],
                       "TEMP": str(candidate), "TMP": str(candidate), "PATH": str(Path(command[0]).parent),
                       "USERPROFILE": profile, "LOCALAPPDATA": profile, "APPDATA": profile,
                       "SystemDrive": Path(os.environ["SystemRoot"]).anchor.rstrip("\\"),
                       "COMSPEC": str(Path(os.environ["SystemRoot"]) / "System32" / "cmd.exe")}
        block = c.create_unicode_buffer("\0".join(key + "=" + value for key, value in sorted(environment.items())) + "\0\0")
        line = c.create_unicode_buffer(subprocess.list2cmdline(command))
        check(kernel.CreateProcessW(command[0], line, None, None, False, 0x80000 | 0x4 | 0x400 | 0x8000000,
                                    block, str(candidate), c.byref(startup), c.byref(info)))
        check(kernel.AssignProcessToJobObject(job, info.process))
        token = w.HANDLE()
        check(advapi.OpenProcessToken(info.process, 0x8, c.byref(token)))
        try:
            flag, needed = w.DWORD(), w.DWORD()
            check(advapi.GetTokenInformation(token, 29, c.byref(flag), c.sizeof(flag), c.byref(needed)))
            if flag.value != 1:
                raise IsolationUnavailable("OS did not create an AppContainer token")
            advapi.GetTokenInformation(token, 30, None, 0, c.byref(needed))
            groups = c.create_string_buffer(needed.value)
            check(advapi.GetTokenInformation(token, 30, groups, needed.value, c.byref(needed)))
            if w.DWORD.from_buffer(groups).value:
                raise IsolationUnavailable("Unexpected AppContainer capabilities")
        finally:
            kernel.CloseHandle(token)
        if kernel.ResumeThread(info.thread) == 0xffffffff:
            raise c.WinError(c.get_last_error())
        if kernel.WaitForSingleObject(info.process, timeout * 1000) != 0:
            check(kernel.TerminateJobObject(job, 124))
            raise IsolationUnavailable("AppContainer timed out; job terminated")
        exit_code = w.DWORD()
        check(kernel.GetExitCodeProcess(info.process, c.byref(exit_code)))
        check(kernel.TerminateJobObject(job, 0))  # no surviving descendants may write after verification
        class Accounting(c.Structure):
            _fields_ = [("times", c.c_longlong * 4), ("faults", w.DWORD), ("total", w.DWORD), ("active", w.DWORD), ("terminated", w.DWORD)]
        import time
        deadline = time.monotonic() + 10
        while True:
            accounting = Accounting()
            check(kernel.QueryInformationJobObject(job, 1, c.byref(accounting), c.sizeof(accounting), None))
            if accounting.active == 0: break
            if time.monotonic() >= deadline: raise IsolationUnavailable("Sandbox descendants did not exit")
            time.sleep(0.02)
        manifest = assert_candidate_integrity(candidate)
        return {"isolation_version": 1, "status": "PASSED" if exit_code.value == 0 else "FAILED", "backend": "WINDOWS_APPCONTAINER",
                "candidate_source_hash": content_hash(manifest), "process_exit_code": exit_code.value, "finished_at": utc_now(),
                "network": "NONE", "writable_roots": [str(candidate)], "ephemeral_profile": profile, "runtime_readonly_roots": [str(root) for root in runtime_roots],
                "command_hash": content_hash(command), "token_is_appcontainer": True, "capability_count": 0, "descendants_exited": True, "inherited_handles": False}
    finally:
        if info.process:
            kernel.TerminateProcess(info.process, 125)
        if job:
            kernel.TerminateJobObject(job, 125)
            kernel.CloseHandle(job)
        for handle in (info.thread, info.process):
            if handle:
                kernel.CloseHandle(handle)
        if attributes is not None:
            kernel.DeleteProcThreadAttributeList(attributes)
        failures = []
        if sid_text:
            for root in reversed(grants):
                result = subprocess.run(["icacls", str(root), "/remove:g", "*" + sid_text.value, "/T", "/Q"], capture_output=True, check=False)
                if result.returncode:
                    failures.append("file grant cleanup")
            kernel.LocalFree(sid_text)
        if sid:
            advapi.FreeSid(sid)
        if profile_created and userenv.DeleteAppContainerProfile(name) < 0:
            failures.append("profile cleanup")
        if failures:
            raise IsolationUnavailable("AppContainer cleanup failed: " + ", ".join(failures))
