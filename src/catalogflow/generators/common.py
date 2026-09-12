"""Shared helpers for local CLI-backed listing generators."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
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


def find_cli(command_name: str, override_variable: str) -> str | None:
    """Find a CLI without evaluating a shell command."""

    override = os.environ.get(override_variable, "").strip()
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
                 check: bool = False, **kwargs) -> subprocess.CompletedProcess:
    """Launch an installed CLI without inheriting frozen DLL paths or a console window."""
    if input is not None:
        kwargs["stdin"] = subprocess.PIPE
    if capture_output:
        kwargs.update(stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if sys.platform == "win32":
        kwargs["creationflags"] = kwargs.get("creationflags", 0) | subprocess.CREATE_NO_WINDOW
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
