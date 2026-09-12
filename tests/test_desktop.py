import errno
import io
import json
import socket
import sys
from types import SimpleNamespace

import pytest

from catalogflow import desktop
from catalogflow.configuration import MemorySecretStore, ProfileRepository


class FakeKernel:
    def __init__(self, wait_result=0):
        self.wait_result = wait_result
        self.calls = []

    def CreateEventW(self, *args):
        self.calls.append("event_created")
        return 1

    def CreateMutexW(self, *args):
        self.calls.append("mutex_created")
        return 2

    def WaitForSingleObject(self, handle, timeout):
        return self.wait_result

    def SetEvent(self, handle):
        self.calls.append("activated")
        return True

    def ReleaseMutex(self, handle):
        self.calls.append("released")
        return True

    def CloseHandle(self, handle):
        self.calls.append(f"closed_{handle}")
        return True


def test_second_instance_activates_primary_without_owning_or_releasing_mutex():
    kernel = FakeKernel(wait_result=0x102)
    guard = desktop.WindowsInstance("synthetic-account", kernel=kernel)
    assert not guard.acquire()
    guard.close()
    assert kernel.calls == [
        "event_created", "mutex_created", "activated", "closed_2", "closed_1",
    ]


@pytest.mark.parametrize("wait_result", [0, 0x80])
def test_normal_and_abandoned_instance_ownership_is_cleaned_up(wait_result):
    kernel = FakeKernel(wait_result=wait_result)
    guard = desktop.WindowsInstance("synthetic-account", kernel=kernel)
    assert guard.acquire()
    assert "synthetic-account" not in guard.name
    assert guard.name.startswith("Global\\CatalogFlow.Desktop.")
    guard.close()
    guard.close()
    assert kernel.calls.count("released") == 1
    assert kernel.calls.count("closed_1") == 1
    assert kernel.calls.count("closed_2") == 1


def test_failed_instance_acquisition_closes_handles_without_releasing_foreign_owner():
    kernel = FakeKernel(wait_result=0xFFFFFFFF)
    guard = desktop.WindowsInstance("synthetic-account", kernel=kernel)
    with pytest.raises(RuntimeError):
        guard.acquire()
    assert "released" not in kernel.calls
    assert "closed_1" in kernel.calls and "closed_2" in kernel.calls


def test_port_conflict_creates_new_service_and_never_contacts_existing_listener(tmp_path):
    with socket.socket() as occupied:
        occupied.bind(("127.0.0.1", 0))
        occupied.listen()
        occupied.settimeout(0.05)
        original_port = occupied.getsockname()[1]
        service = desktop.DesktopService(
            preferred_port=original_port, repository=ProfileRepository(tmp_path),
            secret_store=MemorySecretStore(),
        )
        service.start()
        try:
            assert service.server.server_address[1] != original_port
            assert service.origin.startswith("http://127.0.0.1:")
            with pytest.raises(TimeoutError):
                occupied.accept()
        finally:
            service.close()
        assert not service.thread.is_alive()


def test_unrelated_server_creation_failure_does_not_retry():
    calls = []

    def factory(**kwargs):
        calls.append(kwargs)
        raise OSError(errno.ENOSPC, "synthetic failure")

    with pytest.raises(OSError):
        desktop.DesktopService(factory=factory)
    assert len(calls) == 1


def test_browser_opens_only_new_authenticated_origin_and_token_stays_off_disk(
    tmp_path, monkeypatch, capsys,
):
    opened = []
    monkeypatch.setattr(desktop.webbrowser, "open", lambda url: opened.append(url) or True)
    service = desktop.DesktopService(
        preferred_port=0, repository=ProfileRepository(tmp_path), secret_store=MemorySecretStore(),
    )
    try:
        assert service.open_browser()
        assert opened == [f"{service.origin}/#token={service.server.application.token}"]
        assert not list(tmp_path.iterdir())
        captured = capsys.readouterr()
        assert service.server.application.token not in captured.out + captured.err
    finally:
        service.close()


@pytest.mark.parametrize("window_fails", [False, True])
def test_window_close_and_failure_both_stop_server_and_release_instance(monkeypatch, window_fails):
    events = []
    guard = SimpleNamespace(
        acquire=lambda: True, close=lambda: events.append("instance_closed"),
    )
    service = SimpleNamespace(
        failed=False, start=lambda: events.append("started"),
        close=lambda: events.append("server_closed"),
    )

    def window(*args):
        events.append("window")
        if window_fails:
            raise RuntimeError("synthetic private details")

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(desktop, "WindowsInstance", lambda: guard)
    monkeypatch.setattr(desktop, "DesktopService", lambda: service)
    monkeypatch.setattr(desktop, "_run_window", window)
    monkeypatch.setattr(desktop, "_show_error", lambda: events.append("safe_error"))
    assert desktop.run_desktop() == int(window_fails)
    assert events[-2:] == ["server_closed", "instance_closed"]
    assert ("safe_error" in events) is window_fails


def test_second_launch_never_creates_another_server_or_window(monkeypatch):
    events = []
    guard = SimpleNamespace(acquire=lambda: False, close=lambda: events.append("closed"))

    def forbidden():
        raise AssertionError("A second launch must not create another server")

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(desktop, "WindowsInstance", lambda: guard)
    monkeypatch.setattr(desktop, "DesktopService", forbidden)
    assert desktop.run_desktop() == 0
    assert events == ["closed"]


def test_arguments_forward_to_cli_without_starting_desktop(monkeypatch):
    captured = []
    monkeypatch.setattr(desktop, "_standard_streams", lambda **kwargs: None)
    monkeypatch.setattr("catalogflow.cli.main", lambda args: captured.append(args) or 7)
    assert desktop.main(["--doctor"]) == 7
    assert captured == [["--doctor"]]


def test_windowless_none_standard_streams_do_not_crash(monkeypatch):
    for name in ("stdin", "stdout", "stderr"):
        monkeypatch.setattr(sys, name, None)
    desktop._standard_streams()
    for name in ("stdin", "stdout", "stderr"):
        assert getattr(sys, name) is not None
        getattr(sys, name).close()


def test_self_test_reports_safe_failure_without_raw_exception(tmp_path, monkeypatch):
    def fail_tk():
        raise RuntimeError("private synthetic error")

    monkeypatch.setattr("tkinter.Tk", fail_tk)
    destination = tmp_path / "check.json"
    assert desktop._self_test(str(destination)) == 1
    text = destination.read_text(encoding="utf-8")
    assert "private synthetic error" not in text
    assert json.loads(text)["ok"] is False


def test_launcher_language_settings_accept_only_supported_values(tmp_path):
    path = tmp_path / "desktop.json"
    assert desktop._load_language(path) == "zh-CN"
    path.write_text('{"language":"en-US"}', encoding="utf-8")
    assert desktop._load_language(path) == "en-US"
    path.write_text('{"language":"untrusted"}', encoding="utf-8")
    assert desktop._load_language(path) == "zh-CN"


def test_desktop_close_uses_atomic_import_shutdown_guard():
    calls = []
    service = object.__new__(desktop.DesktopService)
    service.server = SimpleNamespace(application=SimpleNamespace(imports=SimpleNamespace(
        prepare_shutdown=lambda: calls.append("blocked") or False,
    )))
    assert service.prepare_close() is False
    service.server.application.imports.prepare_shutdown = lambda: calls.append("allowed") or True
    assert service.prepare_close() is True
    assert calls == ["blocked", "allowed"]


def test_self_test_fails_when_unauthenticated_request_is_incorrectly_accepted(
    tmp_path, monkeypatch,
):
    class WinVaultKeyring:
        pass

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr("keyring.get_keyring", WinVaultKeyring)
    monkeypatch.setattr("tkinter.Tk", lambda: SimpleNamespace(
        withdraw=lambda: None, update_idletasks=lambda: None, destroy=lambda: None,
        tk=SimpleNamespace(call=lambda *args: "8.6"),
    ))
    service = SimpleNamespace(
        origin="http://127.0.0.1:12345", start=lambda: None, close=lambda: None,
        thread=SimpleNamespace(is_alive=lambda: False),
        server=SimpleNamespace(application=SimpleNamespace(**{"token": "synthetic-session"})),
    )
    monkeypatch.setattr(desktop, "DesktopService", lambda **kwargs: service)
    monkeypatch.setattr("urllib.request.build_opener", lambda *args: SimpleNamespace(
        open=lambda *args, **kwargs: io.BytesIO(b'{"pricing":{}}'),
    ))
    destination = tmp_path / "check.json"
    assert desktop._self_test(str(destination)) == 1
    checks = json.loads(destination.read_text(encoding="utf-8"))["checks"]
    assert checks["unauthorized_rejected"] is False
    assert checks["authenticated_dashboard"] is True
