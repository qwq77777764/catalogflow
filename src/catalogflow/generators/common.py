"""Shared helpers for local CLI-backed listing generators."""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from ..models import Product

_PASSTHROUGH_ENV = {
    "APPDATA",
    "CLAUDE_CONFIG_DIR",
    "CODEX_HOME",
    "COMSPEC",
    "HOME",
    "HOMEDRIVE",
    "HOMEPATH",
    "HTTPS_PROXY",
    "HTTP_PROXY",
    "LANG",
    "LC_ALL",
    "LOCALAPPDATA",
    "NO_PROXY",
    "PATH",
    "PATHEXT",
    "SYSTEMDRIVE",
    "SYSTEMROOT",
    "TEMP",
    "TMP",
    "USERPROFILE",
    "WINDIR",
}
_DLL_LOCK = threading.RLock()


def find_cli(
    command_name: str, override_variable: str, *, command: str | None = None,
) -> str | None:
    """Find a CLI without evaluating a shell command."""

    override = (os.environ.get(override_variable, "") if command is None else command).strip()
    if override:
        candidate = Path(override).expanduser()
        return str(candidate) if candidate.is_file() else shutil.which(override)
    for name in (command_name, f"{command_name}.cmd", f"{command_name}.exe"):
        if executable := shutil.which(name):
            return executable
    return None


def safe_cli_environment() -> dict[str, str]:
    """Pass only OS, proxy, and CLI-login state locations to child processes."""

    environment = {
        key: value for key, value in os.environ.items() if key.upper() in _PASSTHROUGH_ENV
    }
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        root = os.path.normcase(os.path.abspath(bundle))
        for key in environment:
            if key.upper() == "PATH":
                environment[key] = os.pathsep.join(
                    part for part in environment[key].split(os.pathsep)
                    if not _inside_bundle(part, root)
                )
    return environment


def _inside_bundle(path: str, root: str) -> bool:
    try:
        return os.path.commonpath((os.path.normcase(os.path.abspath(path)), root)) == root
    except ValueError:
        return False


@contextmanager
def external_program_environment():
    """Restore Windows DLL search only during process creation, then restore the app."""
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        yield
        return
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetDllDirectoryW.argtypes = [wintypes.DWORD, wintypes.LPWSTR]
    kernel.GetDllDirectoryW.restype = wintypes.DWORD
    kernel.SetDllDirectoryW.argtypes = [wintypes.LPCWSTR]
    kernel.SetDllDirectoryW.restype = wintypes.BOOL
    with _DLL_LOCK:
        length = kernel.GetDllDirectoryW(0, None)
        buffer = ctypes.create_unicode_buffer(length + 1)
        if length:
            kernel.GetDllDirectoryW(len(buffer), buffer)
        previous = buffer.value or None
        if not kernel.SetDllDirectoryW(None):
            raise RuntimeError("External program environment could not be prepared")
        try:
            yield
        finally:
            if not kernel.SetDllDirectoryW(previous):
                raise RuntimeError("Application environment could not be restored")


def run_external(command: list[str], *, input: str | None = None,
                 capture_output: bool = False, timeout: float | None = None,
                 check: bool = False, max_output_bytes: int | None = None,
                 **kwargs) -> subprocess.CompletedProcess:
    """Launch an installed CLI without inheriting frozen DLL paths or a console window."""
    if input is not None:
        kwargs["stdin"] = subprocess.PIPE
    if capture_output:
        kwargs.update(stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if sys.platform == "win32":
        kwargs["creationflags"] = kwargs.get("creationflags", 0) | subprocess.CREATE_NO_WINDOW
    if max_output_bytes is not None and capture_output:
        return _run_bounded_external(command, input, timeout, max_output_bytes, check, kwargs)
    with external_program_environment():
        process = subprocess.Popen(command, **kwargs)  # noqa: S603 - resolved CLI and fixed args
    with process:
        try:
            stdout, stderr = process.communicate(input, timeout=timeout)
        except BaseException:
            process.kill()
            process.communicate()
            raise
        result = subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
        if check:
            result.check_returncode()
        return result


class CliDiagnosticError(RuntimeError):
    """A stable, public diagnostic that contains no provider output."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def cli_failure_code(output: str) -> str:
    """Inspect bounded output without returning any of its text to callers."""
    text = output[:512 * 1024].lower()
    if any(fragment in text for fragment in (
        "requires a newer version", "unknown option", "unrecognized option",
        "unexpected argument", "unrecognized subcommand", "unknown command",
    )):
        return "ai_cli_upgrade_required"
    if any(fragment in text for fragment in (
        "not logged in", "not authenticated", "authentication_failed", "authentication failed",
        "please log in", "please login", "please run /login", "login required",
    )):
        return "ai_auth_required"
    if any(fragment in text for fragment in (
        "insufficient_quota", "rate_limit", "rate limit", "usage limit", "billing_error",
        "credit balance is too low", "subscription required", "subscription is required",
    )):
        return "ai_subscription_or_quota"
    return "ai_test_failed"


class _ProcessTree:
    """Own descendants as well as the launcher that may hand them its output pipes."""

    def __init__(self):
        self.process = None
        self.job = None
        self.kernel = None
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes

            class BasicLimits(ctypes.Structure):
                _fields_ = [
                    ("ProcessTime", ctypes.c_int64), ("JobTime", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD), ("MinWorkingSet", ctypes.c_size_t),
                    ("MaxWorkingSet", ctypes.c_size_t), ("ActiveProcesses", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("Priority", wintypes.DWORD),
                    ("Scheduling", wintypes.DWORD),
                ]

            class ExtendedLimits(ctypes.Structure):
                _fields_ = [("Basic", BasicLimits), ("IoCounters", ctypes.c_uint64 * 6),
                            ("ProcessMemory", ctypes.c_size_t), ("JobMemory", ctypes.c_size_t),
                            ("PeakProcessMemory", ctypes.c_size_t),
                            ("PeakJobMemory", ctypes.c_size_t)]

            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
            kernel.CreateJobObjectW.restype = wintypes.HANDLE
            kernel.SetInformationJobObject.argtypes = [
                wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD,
            ]
            kernel.SetInformationJobObject.restype = wintypes.BOOL
            kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
            kernel.AssignProcessToJobObject.restype = wintypes.BOOL
            kernel.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
            kernel.TerminateJobObject.restype = wintypes.BOOL
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel.CloseHandle.restype = wintypes.BOOL
            job = kernel.CreateJobObjectW(None, None)
            if not job:
                raise CliDiagnosticError("ai_process_isolation_failed")
            limits = ExtendedLimits()
            limits.Basic.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not kernel.SetInformationJobObject(job, 9, ctypes.byref(limits),
                                                 ctypes.sizeof(limits)):
                kernel.CloseHandle(job)
                raise CliDiagnosticError("ai_process_isolation_failed")
            self.kernel, self.job = kernel, job

    def attach(self, process):
        self.process = process
        if self.job and not self.kernel.AssignProcessToJobObject(self.job, int(process._handle)):
            process.kill()
            process.wait(timeout=2)
            raise CliDiagnosticError("ai_process_isolation_failed")

    def stop(self):
        if self.job:
            self.kernel.TerminateJobObject(self.job, 1)
        elif self.process is not None:
            try:
                os.killpg(self.process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    def close(self):
        self.stop()
        if self.job:
            self.kernel.CloseHandle(self.job)
            self.job = None


def _run_bounded_external(command, value, timeout, limit, check, kwargs):
    tree = _ProcessTree()
    if sys.platform != "win32":
        kwargs["start_new_session"] = True
    try:
        with external_program_environment():
            process = subprocess.Popen(command, **kwargs)  # noqa: S603 - fixed CLI invocation
            tree.attach(process)
        with process:
            try:
                stdout, stderr = _bounded_output(process, value, timeout, limit, tree.stop)
            finally:
                # Kill inherited pipe owners BEFORE Popen closes/waits on its file objects.
                tree.stop()
            result = subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
            if check:
                result.check_returncode()
            return result
    finally:
        tree.close()


def _bounded_output(process, value, timeout, limit, stop_tree):
    """Drain both pipes concurrently, retaining at most the shared byte allowance."""
    buffers = [[], []]
    size = 0
    overflow = threading.Event()
    lock = threading.Lock()
    deadline = time.monotonic() + (timeout if timeout is not None else 60)

    def read(pipe, index):
        nonlocal size
        try:
            while chunk := pipe.read(4096):
                with lock:
                    size += len(chunk.encode("utf-8") if isinstance(chunk, str) else chunk)
                    if size > limit:
                        overflow.set()
                        stop_tree()
                        return
                    buffers[index].append(chunk)
        except (OSError, ValueError):
            overflow.set()

    readers = [threading.Thread(target=read, args=(pipe, index), daemon=True)
               for index, pipe in enumerate((process.stdout, process.stderr))]
    for reader in readers:
        reader.start()
    def write():
        try:
            if value is not None:
                process.stdin.write(value)
            process.stdin.close()
        except (OSError, ValueError):
            pass

    if process.stdin is not None:
        writer = threading.Thread(target=write, daemon=True)
        readers.append(writer)
        writer.start()
    try:
        process.wait(timeout=max(0, deadline - time.monotonic()))
        for reader in readers:
            reader.join(timeout=max(0, deadline - time.monotonic()))
        if any(reader.is_alive() for reader in readers):
            raise subprocess.TimeoutExpired(process.args, timeout)
    finally:
        stop_tree()
        process.wait(timeout=2)
        cleanup_deadline = time.monotonic() + 2
        for reader in readers:
            reader.join(timeout=max(0, cleanup_deadline - time.monotonic()))
    if overflow.is_set() or any(reader.is_alive() for reader in readers):
        raise CliDiagnosticError("ai_output_limit")
    empty = "" if process.text_mode else b""
    return tuple(empty.join(buffer) for buffer in buffers)


def build_listing_prompt(product: Product) -> str:
    """Build a provider-neutral prompt without source IDs, costs, or credentials."""

    facts = {
        "title": product.title,
        "currency": product.currency,
        "facts": product.facts,
        "variant_attributes": [variant.attributes for variant in product.variants],
    }
    return (
        "Create original, brand-neutral English merchandising copy from the authorized "
        "product facts below. Return only JSON matching the supplied schema. Do not mention "
        "supplier platforms, dropshipping, wholesale, shipping promises, medical claims, "
        "brands, licenses, or facts not present in the input. Use 'Not specified' when a "
        "material, measurement, or power detail is unknown.\n\n"
        + json.dumps(facts, ensure_ascii=False, indent=2)
    )
