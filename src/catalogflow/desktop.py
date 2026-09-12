"""Windows desktop entry point; the authenticated dashboard token stays in memory."""

from __future__ import annotations

import errno
import hashlib
import json
import os
import sys
import threading
import webbrowser
from pathlib import Path

from .configuration import default_config_directory
from .dashboard import create_dashboard_server
from .generators.common import external_program_environment

PREFERRED_PORT = 50183
_COPY = {
    "zh-CN": {
        "heading": "CatalogFlow 本机工作台", "open": "打开可视化界面", "exit": "退出 CatalogFlow",
        "status": "本机服务正在运行", "hint": "关闭浏览器后可重新打开。关闭此窗口将退出本机服务。",
        "browser_error": "未能打开默认浏览器，请检查 Windows 默认浏览器设置后重试。",
    },
    "en-US": {
        "heading": "CatalogFlow local workbench", "open": "Open interface",
        "exit": "Exit CatalogFlow",
        "status": "Local service is running",
        "hint": "Reopen the browser at any time. Closing this window stops the local service.",
        "browser_error": (
            "The default browser could not open. Check Windows browser settings and retry."
        ),
    },
}


def _kernel():
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    signatures = {
        "CreateMutexW": ([wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR], wintypes.HANDLE),
        "CreateEventW": (
            [wintypes.LPVOID, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR], wintypes.HANDLE,
        ),
        "WaitForSingleObject": ([wintypes.HANDLE, wintypes.DWORD], wintypes.DWORD),
        "SetEvent": ([wintypes.HANDLE], wintypes.BOOL),
        "ReleaseMutex": ([wintypes.HANDLE], wintypes.BOOL),
        "CloseHandle": ([wintypes.HANDLE], wintypes.BOOL),
        "GetCurrentProcess": ([], wintypes.HANDLE),
        "LocalFree": ([wintypes.LPVOID], wintypes.LPVOID),
    }
    for name, (arguments, result) in signatures.items():
        function = getattr(kernel, name)
        function.argtypes = arguments
        function.restype = result
    return kernel


def _user_sid() -> str:
    """Use the OS account identity, independent of editable environment variables."""
    import ctypes
    from ctypes import wintypes

    kernel = _kernel()
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    advapi.OpenProcessToken.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE),
    ]
    advapi.OpenProcessToken.restype = wintypes.BOOL
    advapi.GetTokenInformation.argtypes = [
        wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    advapi.GetTokenInformation.restype = wintypes.BOOL
    advapi.ConvertSidToStringSidW.argtypes = [wintypes.LPVOID, ctypes.POINTER(wintypes.LPWSTR)]
    advapi.ConvertSidToStringSidW.restype = wintypes.BOOL
    token = wintypes.HANDLE()
    if not advapi.OpenProcessToken(kernel.GetCurrentProcess(), 8, ctypes.byref(token)):
        raise RuntimeError("Windows account identity is unavailable")
    try:
        size = wintypes.DWORD()
        advapi.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))
        if not size.value:
            raise RuntimeError("Windows account identity is unavailable")
        buffer = ctypes.create_string_buffer(size.value)
        if not advapi.GetTokenInformation(token, 1, buffer, size, ctypes.byref(size)):
            raise RuntimeError("Windows account identity is unavailable")
        sid = ctypes.cast(buffer, ctypes.POINTER(wintypes.LPVOID))[0]
        sid_text = wintypes.LPWSTR()
        if not advapi.ConvertSidToStringSidW(sid, ctypes.byref(sid_text)):
            raise RuntimeError("Windows account identity is unavailable")
        try:
            return sid_text.value
        finally:
            kernel.LocalFree(sid_text)
    finally:
        kernel.CloseHandle(token)


class WindowsInstance:
    """One launcher per Windows account, with an activation event and no token file."""

    def __init__(self, identity: str | None = None, *, kernel=None) -> None:
        self.kernel = kernel or _kernel()
        digest = hashlib.sha256((identity or _user_sid()).encode()).hexdigest()
        self.name = "Global\\CatalogFlow.Desktop." + digest
        self.event = None
        self.mutex = None
        self.primary = False

    def acquire(self) -> bool:
        try:
            # Create the event first so a second launch during startup cannot lose activation.
            self.event = self.kernel.CreateEventW(None, False, False, self.name + ".Activate")
            if not self.event:
                raise RuntimeError("Desktop activation is unavailable")
            self.mutex = self.kernel.CreateMutexW(None, False, self.name)
            if not self.mutex:
                raise RuntimeError("Desktop instance control is unavailable")
            result = self.kernel.WaitForSingleObject(self.mutex, 0)
            if result in {0, 0x80}:  # Normal acquisition or an abandoned previous owner.
                self.primary = True
                return True
            if result == 0x102:
                if not self.kernel.SetEvent(self.event):
                    raise RuntimeError("The existing desktop could not be activated")
                return False
            raise RuntimeError("Desktop instance control is unavailable")
        except Exception:
            self.close()
            raise

    def activation_pending(self) -> bool:
        result = self.kernel.WaitForSingleObject(self.event, 0)
        if result not in {0, 0x102}:
            raise RuntimeError("Desktop activation is unavailable")
        return result == 0

    def close(self) -> None:
        if self.mutex:
            if self.primary:
                self.kernel.ReleaseMutex(self.mutex)
            self.kernel.CloseHandle(self.mutex)
            self.mutex = None
        if self.event:
            self.kernel.CloseHandle(self.event)
            self.event = None
        self.primary = False


class DesktopService:
    def __init__(self, *, factory=create_dashboard_server, preferred_port=PREFERRED_PORT,
                 **server_options) -> None:
        try:
            self.server = factory(port=preferred_port, **server_options)
        except OSError as exc:
            if exc.errno not in {errno.EADDRINUSE, errno.EACCES} and getattr(
                exc, "winerror", None,
            ) not in {10048, 10013}:
                raise
            # Bind a fresh authenticated service; never trust whatever owns the preferred port.
            self.server = factory(port=0, **server_options)
        self.failed = False
        self.thread = threading.Thread(
            target=self._serve, name="CatalogFlow-dashboard", daemon=True,
        )

    @property
    def origin(self) -> str:
        return self.server.application.origin

    def _serve(self) -> None:
        try:
            self.server.serve_forever(poll_interval=0.1)
        except Exception:
            self.failed = True
        finally:
            self.server.server_close()

    def start(self) -> None:
        self.thread.start()

    def open_browser(self) -> bool:
        with external_program_environment():
            return webbrowser.open(f"{self.origin}/#token={self.server.application.token}")

    def close(self) -> None:
        if self.thread.is_alive():
            self.server.shutdown()
            self.thread.join(timeout=3)
        else:
            self.server.server_close()

    def prepare_close(self) -> bool:
        """Keep the workbench alive until an in-flight import has finished."""
        return self.server.application.imports.prepare_shutdown()


def _show_error() -> None:
    message = (
        "CatalogFlow 未能启动或已停止。请重新打开；若仍失败，请检查配置目录权限和系统凭据服务。"
        "\n\nCatalogFlow could not start or has stopped. Reopen it; if this continues, "
        "check configuration-folder permissions and Windows Credential Manager."
    )
    try:
        from tkinter import messagebox

        messagebox.showerror("CatalogFlow", message)
    except Exception:
        if sys.platform == "win32":
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, message, "CatalogFlow", 0x10)


def _standard_streams(*, console: bool = False) -> None:
    """PyInstaller windowed executables set standard streams to None."""
    attached = False
    if console and sys.platform == "win32" and any(
        getattr(sys, name) is None for name in ("stdin", "stdout", "stderr")
    ):
        import ctypes

        attached = bool(ctypes.windll.kernel32.AttachConsole(0xFFFFFFFF))
    for name in ("stdin", "stdout", "stderr"):
        if getattr(sys, name) is not None:
            continue
        mode = "r" if name == "stdin" else "w"
        target = ("CONIN$" if name == "stdin" else "CONOUT$") if attached else os.devnull
        try:
            stream = open(target, mode, encoding="utf-8", errors="replace")
        except OSError:
            stream = open(os.devnull, mode, encoding="utf-8")
        setattr(sys, name, stream)


def _load_language(path: Path) -> str:
    try:
        value = json.loads(path.read_text(encoding="utf-8")).get("language")
        return value if value in _COPY else "zh-CN"
    except (OSError, ValueError, AttributeError):
        return "zh-CN"


def _run_window(service: DesktopService, instance: WindowsInstance) -> None:
    import tkinter as tk
    from tkinter import messagebox, ttk

    root = tk.Tk()
    root.title("CatalogFlow")
    root.minsize(470, 230)
    root.resizable(True, False)
    root.columnconfigure(0, weight=1)
    frame = ttk.Frame(root, padding=24)
    frame.grid(sticky="nsew")
    frame.columnconfigure((0, 1), weight=1, uniform="actions")
    language_path = default_config_directory() / "desktop.json"
    language = _load_language(language_path)
    selection = tk.StringVar(value="中文 (CN)" if language == "zh-CN" else "English (US)")
    heading = ttk.Label(frame, font=("Segoe UI", 16, "bold"))
    heading.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))
    chooser = ttk.Combobox(
        frame, state="readonly", textvariable=selection, values=("中文 (CN)", "English (US)"),
        width=18,
    )
    chooser.grid(row=1, column=1, sticky="e")
    status = ttk.Label(frame)
    status.grid(row=1, column=0, sticky="w")
    ttk.Label(frame, text=service.origin).grid(row=2, column=0, columnspan=2, sticky="w")
    hint = ttk.Label(frame, wraplength=460, justify="left")
    hint.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(12, 18))

    def open_interface():
        try:
            opened = service.open_browser()
        except Exception:
            opened = False
        if not opened:
            messagebox.showerror("CatalogFlow", _COPY[language]["browser_error"], parent=root)

    open_button = ttk.Button(frame, command=open_interface)
    open_button.grid(row=4, column=0, sticky="ew", padx=(0, 6))
    def close_window():
        if service.prepare_close():
            root.destroy()
            return
        message = (
            "商品正在处理，请等本次预览或草稿创建完成后再退出。"
            if language == "zh-CN" else
            "An import is running. Wait for the preview or draft operation "
            "to finish before exiting."
        )
        messagebox.showinfo("CatalogFlow", message, parent=root)

    exit_button = ttk.Button(frame, command=close_window)
    exit_button.grid(row=4, column=1, sticky="ew", padx=(6, 0))

    def apply_language(_event=None):
        nonlocal language
        language = "zh-CN" if selection.get() == "中文 (CN)" else "en-US"
        copy = _COPY[language]
        for widget, key in ((heading, "heading"), (status, "status"), (hint, "hint"),
                            (open_button, "open"), (exit_button, "exit")):
            widget.configure(text=copy[key])
        if _event is not None:
            try:
                language_path.parent.mkdir(parents=True, exist_ok=True)
                language_path.write_text(json.dumps({"language": language}), encoding="utf-8")
            except OSError:
                pass  # The current selection works even when preference persistence is unavailable.

    def poll():
        if not service.thread.is_alive():
            root.destroy()
            return
        try:
            activated = instance.activation_pending()
        except RuntimeError:
            service.failed = True
            root.destroy()
            return
        if activated:
            root.deiconify()
            root.lift()
            open_interface()
        root.after(200, poll)

    chooser.bind("<<ComboboxSelected>>", apply_language)
    root.protocol("WM_DELETE_WINDOW", close_window)
    apply_language()
    root.after(100, open_interface)
    root.after(200, poll)
    try:
        root.mainloop()
    finally:
        try:
            root.destroy()
        except tk.TclError:
            pass


def run_desktop() -> int:
    instance = None
    service = None
    try:
        if sys.platform != "win32":
            raise RuntimeError("The desktop launcher requires Windows")
        instance = WindowsInstance()
        if not instance.acquire():
            return 0
        service = DesktopService()
        service.start()
        _run_window(service, instance)
        if service.failed:
            raise RuntimeError("The local service stopped unexpectedly")
        return 0
    except Exception:
        _show_error()
        return 1
    finally:
        if service:
            service.close()
        if instance:
            instance.close()


def _self_test(destination: str, *, test_keyring: bool = False) -> int:
    """Offline package checks; use isolated data and never run a supplier/AI/store request."""
    import tempfile
    import uuid
    from urllib.error import HTTPError
    from urllib.request import ProxyHandler, Request, build_opener

    from .configuration import MemorySecretStore, ProfileRepository
    from .pricing import PricingPolicy

    checks = {}
    try:
        package = Path(__file__).parent
        assets = ("dashboard.html", "dashboard-i18n.js", "dashboard-fx.js",
                  "dashboard-history.js", "dashboard-import.js", "schemas/listing.schema.json",
                  "browser/catalogflow-collector.user.js")
        checks["assets"] = all((package / name).is_file() for name in assets)
        checks["pricing"] = PricingPolicy().price(8.5, last_mile=4.71) == 34.95
        import tkinter as tk

        window = tk.Tk()
        window.withdraw()
        window.update_idletasks()
        checks["tk"] = bool(window.tk.call("info", "patchlevel"))
        window.destroy()
        import keyring

        checks["keyring_backend"] = type(keyring.get_keyring()).__name__ == "WinVaultKeyring"
        if test_keyring:
            namespace = "catalogflow/package-self-test/" + uuid.uuid4().hex
            value = uuid.uuid4().hex
            try:
                keyring.set_password(namespace, "synthetic", value)
                checks["keyring_roundtrip"] = keyring.get_password(namespace, "synthetic") == value
            finally:
                keyring.delete_password(namespace, "synthetic")
        with tempfile.TemporaryDirectory(prefix="catalogflow_package_check_") as directory:
            service = DesktopService(
                preferred_port=0, repository=ProfileRepository(directory),
                secret_store=MemorySecretStore(),
            )
            service.start()
            opener = build_opener(ProxyHandler({}))
            try:
                checks["unauthorized_rejected"] = False
                try:
                    with opener.open(service.origin + "/api/state", timeout=5):
                        pass
                except HTTPError as exc:
                    checks["unauthorized_rejected"] = exc.code == 403
                request = Request(  # noqa: S310 - only the freshly bound loopback service
                    service.origin + "/api/state",
                    headers={"X-CatalogFlow-Token": service.server.application.token},
                )
                with opener.open(request, timeout=5) as response:
                    checks["authenticated_dashboard"] = "pricing" in json.load(response)
            finally:
                service.close()
            checks["server_stopped"] = not service.thread.is_alive()
        if sys.platform == "win32":
            # Named mutex ownership is recursive within one thread, so use a competing thread.
            primary = WindowsInstance("package-self-test/" + uuid.uuid4().hex)
            try:
                first = primary.acquire()
                competing = []

                def check_competing():
                    secondary = WindowsInstance("unused")
                    secondary.name = primary.name
                    try:
                        competing.append(secondary.acquire())
                    finally:
                        secondary.close()

                thread = threading.Thread(target=check_competing)
                thread.start()
                thread.join(timeout=5)
                checks["single_instance"] = first and competing == [False]
                checks["activation"] = primary.activation_pending()
            finally:
                primary.close()
    except Exception:
        checks["completed"] = False
    result = {"ok": bool(checks) and all(checks.values()), "checks": checks}
    try:
        Path(destination).write_text(json.dumps(result, indent=2), encoding="utf-8")
    except OSError:
        return 1
    return 0 if result["ok"] else 1


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    _standard_streams(console=bool(arguments))
    if arguments and arguments[0] == "--self-test":
        if len(arguments) not in {2, 3} or (
            len(arguments) == 3 and arguments[2] != "--self-test-keyring"
        ):
            return 2
        return _self_test(arguments[1], test_keyring=len(arguments) == 3)
    if arguments:
        from .cli import main as cli_main

        return cli_main(arguments)
    return run_desktop()


if __name__ == "__main__":
    raise SystemExit(main())
