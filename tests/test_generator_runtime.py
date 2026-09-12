import ctypes
import json
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from catalogflow.generators import common
from catalogflow.generators.claude_cli import ClaudeCliListingGenerator
from catalogflow.generators.codex_cli import CodexCliError, CodexCliListingGenerator
from catalogflow.models import Product, Variant
from catalogflow.run_history import safe_error


def test_frozen_cli_environment_drops_bundle_paths_and_private_values(tmp_path, monkeypatch):
    bundle = tmp_path / "_internal"
    sibling = tmp_path / "external"
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)
    monkeypatch.setenv("PATH", common.os.pathsep.join([
        str(bundle), str(bundle / "helpers"), str(sibling),
    ]))
    monkeypatch.setenv("SYNTHETIC_STORE_SECRET", "must-not-reach-child")
    environment = common.safe_cli_environment()
    assert environment["PATH"] == str(sibling)
    assert "SYNTHETIC_STORE_SECRET" not in environment


def test_external_process_restores_app_environment_before_waiting(monkeypatch):
    calls = []

    @contextmanager
    def environment():
        calls.append("clear")
        yield
        calls.append("restore")

    class Child:
        returncode = 0

        def __init__(self, command, **kwargs):
            calls.append("spawn")
            assert kwargs["creationflags"] & 0x08000000

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def communicate(self, value, timeout=None):
            assert calls[-1] == "restore"
            calls.append("wait")
            return "safe result", ""

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    monkeypatch.setattr(common, "external_program_environment", environment)
    monkeypatch.setattr(subprocess, "Popen", Child)
    result = common.run_external(["synthetic-cli", "--version"], capture_output=True, text=True)
    assert result.stdout == "safe result"
    assert calls == ["clear", "spawn", "restore", "wait"]


def test_external_timeout_kills_and_reaps_child(monkeypatch):
    calls = []

    class Child:
        returncode = None

        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def communicate(self, value=None, timeout=None):
            if timeout:
                raise subprocess.TimeoutExpired("synthetic-cli", timeout)
            calls.append("reaped")
            return "", ""

        def kill(self):
            calls.append("killed")

    monkeypatch.setattr(subprocess, "Popen", Child)
    with pytest.raises(subprocess.TimeoutExpired):
        common.run_external(["synthetic-cli"], timeout=1)
    assert calls == ["killed", "reaped"]


def test_windows_frozen_dll_directory_is_restored_when_launch_fails(monkeypatch):
    changes = []

    class Function:
        def __init__(self, callback):
            self.callback = callback

        def __call__(self, *args):
            return self.callback(*args)

    def get_directory(length, buffer):
        if buffer is not None:
            buffer.value = "bundle"
        return 7

    kernel = SimpleNamespace(
        GetDllDirectoryW=Function(get_directory),
        SetDllDirectoryW=Function(lambda value: changes.append(value) or True),
    )
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(ctypes, "WinDLL", lambda *args, **kwargs: kernel, raising=False)
    with pytest.raises(OSError):
        with common.external_program_environment():
            raise OSError("synthetic launch failure")
    assert changes == [None, "bundle"]


def test_old_codex_version_has_stable_error_without_raw_provider_stderr(monkeypatch):
    monkeypatch.setattr("catalogflow.generators.codex_cli.find_cli", lambda *args: "codex")
    monkeypatch.setattr("catalogflow.generators.codex_cli.run_external", lambda *args, **kwargs:
                        SimpleNamespace(
                            returncode=1, stdout="",
                            stderr="private details: message requires a newer version of Codex",
                        ))
    product = Product("alibaba-manual", "synthetic", "Clock", "USD", (Variant("SKU", 2),))
    with pytest.raises(CodexCliError) as caught:
        CodexCliListingGenerator().generate(product)
    assert str(caught.value) == "codex_cli_upgrade_required"
    assert safe_error(caught.value) == "codex_cli_upgrade_required"


def test_codex_uses_shared_external_runtime_and_structured_output(monkeypatch):
    monkeypatch.setattr("catalogflow.generators.codex_cli.find_cli", lambda *args: "codex")

    def runner(command, **kwargs):
        output = Path(command[command.index("-o") + 1])
        output.write_text(
            '{"title":"Clock","description_html":"<p>Clock</p>",'
            '"category":"Clocks","tags":["clock"]}', encoding="utf-8",
        )
        assert kwargs["capture_output"] is True
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("catalogflow.generators.codex_cli.run_external", runner)
    product = Product("alibaba-manual", "synthetic", "Clock", "USD", (Variant("SKU", 2),))
    assert CodexCliListingGenerator().generate(product).title == "Clock"


@pytest.mark.parametrize("provider,cls", [
    ("codex", CodexCliListingGenerator), ("claude", ClaudeCliListingGenerator),
])
def test_explicit_cli_profile_never_changes_or_inherits_other_profile_settings(
    monkeypatch, provider, cls,
):
    import os

    monkeypatch.setenv(f"CATALOGFLOW_{provider.upper()}_COMMAND", "wrong-profile-cli")
    monkeypatch.setenv(f"CATALOGFLOW_{provider.upper()}_MODEL", "wrong-profile-model")
    monkeypatch.setenv("SYNTHETIC_STORE_SECRET", "must-not-reach-child")
    before = dict(os.environ)
    lookups = []

    def find(name, variable, *, command):
        lookups.append(command)
        return command or "default-cli"

    def runner(command, **kwargs):
        assert command[0] == "selected-cli"
        assert "wrong-profile-model" not in command
        assert "selected-model" in command
        assert "SYNTHETIC_STORE_SECRET" not in kwargs["env"]
        data = {"title": "Clock", "description_html": "<p>Clock</p>",
                "category": "Clocks", "tags": ["clock"]}
        if provider == "codex":
            Path(command[command.index("-o") + 1]).write_text(json.dumps(data), encoding="utf-8")
        return SimpleNamespace(returncode=0, stderr="", stdout=json.dumps({
            "is_error": False, "structured_output": data,
        }))

    monkeypatch.setattr(f"catalogflow.generators.{provider}_cli.find_cli", find)
    monkeypatch.setattr(f"catalogflow.generators.{provider}_cli.run_external", runner)
    product = Product("alibaba-manual", "synthetic", "Clock", "USD", (Variant("SKU", 2),))
    assert cls(command="selected-cli", model="selected-model").generate(product).title == "Clock"
    assert cls(command="", model="").model is None
    assert lookups == ["selected-cli"]
    assert dict(os.environ) == before


def test_explicit_empty_cli_command_uses_path_instead_of_environment_override(monkeypatch):
    monkeypatch.setenv("SYNTHETIC_COMMAND", "wrong-profile")
    monkeypatch.setattr(common.shutil, "which", lambda value: f"resolved-{value}")
    assert common.find_cli("codex", "SYNTHETIC_COMMAND", command="") == "resolved-codex"
    assert common.find_cli("codex", "SYNTHETIC_COMMAND") == "resolved-wrong-profile"
