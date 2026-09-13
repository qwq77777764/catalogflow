import json
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from catalogflow.ai_setup import AISetup, AISetupError, _generator, _guidance, _open_login
from catalogflow.configuration import MemorySecretStore, ProfileRepository
from catalogflow.generators.common import CliDiagnosticError, cli_failure_code, run_external
from catalogflow.models import Listing


def completed(stdout="", stderr="", returncode=0):
    return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)


@pytest.fixture
def repository(tmp_path):
    return ProfileRepository(tmp_path / "profiles")


def setup(repository, results=(), **kwargs):
    iterator = iter(results)
    return AISetup(repository, finder=lambda *args, **kw: "synthetic-cli",
                   runner=lambda *args, **kw: next(iterator), launcher=lambda fn: fn(), **kwargs)


@pytest.mark.parametrize("provider,auth", [
    ("codex", completed(stderr="Logged in using ChatGPT")),
    ("claude", completed(json.dumps({"loggedIn": True, "email": "private@example.test"}))),
])
def test_auth_is_separate_from_version_and_identity_never_returned(repository, provider, auth):
    app = setup(repository, [completed("0.144.0"), auth])
    state = app.check({"provider": provider, "profile_id": None})
    assert state["status"] == "signed_in"
    assert state["usage_verified"] is False
    assert state["version"] == "0.144.0"
    assert "private@example" not in json.dumps(state)
    assert state["busy"] is False


def test_missing_command_never_runs_or_generates(repository):
    app = AISetup(repository, finder=lambda *args, **kw: None, launcher=lambda fn: fn(),
                  runner=lambda *args, **kw: pytest.fail("must not launch"))
    assert app.check({"provider": "codex"})["status"] == "missing"


@pytest.mark.parametrize("provider,auth,status", [
    ("codex", completed(stderr="Not logged in", returncode=1), "logged_out"),
    ("codex", completed("some unrelated output"), "auth_unknown"),
    ("codex", completed(stderr="unknown command 'status'", returncode=2), "outdated"),
    ("claude", completed('{"loggedIn":false}', returncode=1), "logged_out"),
    ("claude", completed('{"loggedIn":"true"}'), "auth_unknown"),
    ("claude", completed('{"email":"hidden@example.test"}', returncode=1), "auth_unknown"),
])
def test_auth_failures_have_specific_redacted_status(repository, provider, auth, status):
    app = setup(repository, [completed("2.1.250 (Claude Code)"), auth])
    state = app.check({"provider": provider})
    assert state["status"] == status
    assert "hidden@example" not in json.dumps(state)


def test_saved_profile_and_default_match_wizard_without_environment_mutation(
    repository, monkeypatch,
):
    profile = repository.save(provider="codex", label="Synthetic selected", notes="",
                              values={"command": "selected-cli", "model": "selected-model"},
                              secrets={}, secret_store=MemorySecretStore(), is_default=True)
    monkeypatch.setenv("CATALOGFLOW_CODEX_COMMAND", "unrelated-cli")
    monkeypatch.setenv("PRIVATE_STORE_TOKEN", "do-not-forward")
    calls = []

    def finder(name, variable, *, command):
        assert name == "codex"
        assert command == "selected-cli"
        return command

    def runner(command, **kwargs):
        calls.append(command)
        assert "PRIVATE_STORE_TOKEN" not in kwargs["env"]
        assert kwargs["timeout"] == 10
        assert kwargs["max_output_bytes"] == 16 * 1024
        assert Path(kwargs["cwd"]).is_dir()
        return completed("codex-cli 0.144.0" if command[-1] == "--version"
                         else "Logged in using ChatGPT")

    app = AISetup(repository, finder=finder, runner=runner, launcher=lambda fn: fn())
    assert app.check({"provider": "codex", "profile_id": profile.id})["status"] == "signed_in"
    assert app.check({"provider": "codex"})["selected_profile_id"] == profile.id
    assert calls[1] == ["selected-cli", "login", "status"]


def test_no_profile_uses_path_exactly_like_wizard(repository):
    calls = []

    def finder(*args, command):
        calls.append(command)
        return None

    app = AISetup(repository, finder=finder, launcher=lambda fn: fn())
    app.check({"provider": "claude", "profile_id": None})
    assert calls == [""]


def test_claude_uses_documented_default_json_without_invented_flag(repository):
    calls = []

    def runner(command, **kwargs):
        calls.append(command)
        return completed("2.1.250 (Claude Code)" if command[-1] == "--version"
                         else '{"loggedIn":true}')

    app = AISetup(repository, finder=lambda *a, **kw: "claude", runner=runner,
                  launcher=lambda fn: fn())
    app.check({"provider": "claude"})
    assert calls[-1] == ["claude", "auth", "status"]


def test_checks_never_generate_and_test_requires_confirmation(repository):
    app = setup(repository, [completed("0.144.0"), completed("Logged in using ChatGPT")],
                generator_factory=lambda *a: pytest.fail("no AI request authorized"))
    with pytest.raises(AISetupError, match="ai_setup_confirmation_required"):
        app.test({"provider": "codex"})
    app.check({"provider": "codex"})


def test_confirmed_test_uses_only_tiny_synthetic_no_images_or_store(repository):
    calls = []

    def generate(product):
        calls.append(product)
        assert product.images == ()
        assert product.source_url == ""
        assert product.title == "Plain ceramic cup"
        assert len(product.variants) == 1
        return Listing("Plain cup", "<p>A white ceramic cup.</p>", "Cups", ("cup",),
                       {"SYNTHETIC-CUP": 9.95})

    app = setup(repository, [completed("0.144.0"), completed("Logged in using ChatGPT")],
                generator_factory=lambda provider, values: SimpleNamespace(generate=generate))
    state = app.test({"provider": "codex", "confirm_usage": True})
    assert state["status"] == "test_passed"
    assert state["usage_verified"] is True
    assert len(calls) == 1
    assert "ceramic" not in json.dumps(state)


def test_logged_out_test_does_not_submit_a_request(repository):
    app = setup(repository, [completed("0.144.0"), completed("Not logged in", returncode=1)],
                generator_factory=lambda *a: pytest.fail("must sign in first"))
    assert app.test({"provider": "codex", "confirm_usage": True})["status"] == "logged_out"


@pytest.mark.parametrize("payload", [
    {"provider": []}, {"provider": {}},
    {"provider": "deterministic"}, {"provider": "codex", "command": "echo secret"},
    {"provider": "codex", "profile_id": "a label"},
    {"provider": "codex", "profile_id": "00000000-0000-0000-0000-000000000000"},
])
def test_invalid_and_missing_profiles_fail_closed(repository, payload):
    with pytest.raises(AISetupError):
        setup(repository).check(payload)


def test_wrong_provider_profile_is_rejected(repository):
    profile = repository.save(provider="claude", label="Claude only", notes="", values={},
                              secrets={}, secret_store=MemorySecretStore())
    with pytest.raises(AISetupError, match="ai_setup_profile_invalid"):
        setup(repository).check({"provider": "codex", "profile_id": profile.id})


def test_busy_jobs_and_shutdown_do_not_leave_untracked_tests(repository):
    work = []
    app = AISetup(repository, finder=lambda *a, **kw: None, launcher=work.append)
    assert app.check({"provider": "codex"})["busy"] is True
    assert app.prepare_shutdown() is False
    with pytest.raises(AISetupError, match="ai_setup_busy"):
        app.login({"provider": "codex"})
    work.pop()()
    assert app.close() is True
    with pytest.raises(AISetupError, match="ai_setup_closed"):
        app.check({"provider": "claude"})


@pytest.mark.parametrize("opened,expected", [
    (True, "login_opened"), (False, "manual_login_required"),
])
def test_login_is_explicit_launch_only_and_never_claims_auth(repository, opened, expected):
    calls = []
    app = setup(repository, login_launcher=lambda *args: calls.append(args) or opened)
    assert app.state()["status"] == "idle"
    assert calls == []
    state = app.login({"provider": "codex"})
    assert state["status"] == expected
    assert state["usage_verified"] is False
    assert calls == [("codex", "synthetic-cli")]


def test_non_native_login_uses_manual_guidance(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: pytest.fail("no shell"))
    assert _open_login("codex", "synthetic.cmd") is False
    monkeypatch.setattr(sys, "platform", "linux")
    assert _open_login("codex", "/synthetic/codex") is False


def test_timeout_and_output_limits_are_redacted(repository):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("private/path", 10, stderr="private@example.test")

    app = AISetup(repository, finder=lambda *a, **kw: "synthetic", runner=timeout,
                  launcher=lambda fn: fn())
    state = app.check({"provider": "codex"})
    assert state["code"] == "ai_check_timeout"
    assert "private" not in json.dumps(state)
    app = setup(repository, [completed("x" * 17000)])
    assert app.check({"provider": "codex"})["status"] == "auth_unknown"


@pytest.mark.parametrize("code,status", [
    ("codex_cli_upgrade_required", "outdated"),
    ("ai_auth_required", "logged_out"),
    ("ai_subscription_or_quota", "test_failed"),
])
def test_provider_errors_map_only_from_stable_codes(repository, code, status):
    def generate(product):
        raise CliDiagnosticError(code)

    app = setup(repository, [completed("0.144.0"), completed("Logged in using ChatGPT")],
                generator_factory=lambda *a: SimpleNamespace(generate=generate))
    state = app.test({"provider": "codex", "confirm_usage": True})
    assert state["status"] == status
    assert state["usage_verified"] is False


def test_generator_factory_matches_profile_and_caps_test_duration():
    generator = _generator("claude", {"command": "selected-cli", "model": "selected-model"})
    assert generator.command == "selected-cli"
    assert generator.model == "selected-model"
    assert generator.timeout_seconds == 60


def test_cli_diagnostics_never_infer_billing_from_a_generic_exit():
    assert cli_failure_code("Process exited with status 1") == "ai_test_failed"
    assert cli_failure_code("private: insufficient_quota") == "ai_subscription_or_quota"


def test_bounded_runner_stops_excessive_synthetic_output():
    with pytest.raises(CliDiagnosticError, match="ai_output_limit"):
        run_external([sys.executable, "-c", "print('x' * 100000)"], capture_output=True,
                     text=True, timeout=5, max_output_bytes=1000)


def test_bounded_runner_returns_small_synthetic_output():
    result = run_external([sys.executable, "-c", "print('synthetic')"], capture_output=True,
                          text=True, timeout=5, max_output_bytes=1000)
    assert result.stdout.strip() == "synthetic"


def test_bounded_runner_times_out_and_reaps_synthetic_process():
    with pytest.raises(subprocess.TimeoutExpired):
        run_external([sys.executable, "-c", "import time; time.sleep(5)"],
                     capture_output=True, text=True, timeout=0.1, max_output_bytes=1000)


def test_bounded_runner_closes_stdin_without_deadlocking():
    result = run_external([sys.executable, "-c", "import sys; print(len(sys.stdin.read()))"],
                          input="synthetic", capture_output=True,
                          text=True, timeout=5, max_output_bytes=1000)
    assert result.stdout.strip() == "9"


def test_timeout_covers_descendants_holding_inherited_pipes(tmp_path):
    finished = tmp_path / "descendant-finished.txt"
    child_code = (
        "import pathlib,time; time.sleep(4); "
        f"pathlib.Path({str(finished)!r}).write_text('must not finish')"
    )
    parent_code = (
        "import subprocess,sys; "
        f"subprocess.Popen([sys.executable,'-c',{child_code!r}],"
        "stdout=sys.stdout,stderr=sys.stderr)"
    )
    started = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired):
        run_external([sys.executable, "-c", parent_code], capture_output=True,
                     text=True, timeout=0.2, max_output_bytes=16384)
    assert time.monotonic() - started < 2
    assert not finished.exists()


def test_native_login_opens_fixed_visible_command_without_capture(tmp_path, monkeypatch):
    calls = []

    class Child:
        def __init__(self, command, **kwargs):
            calls.append(command)
            assert command == [str(tmp_path / "synthetic.exe"), "auth", "login"]
            assert kwargs["creationflags"] == 0x10
            assert "stdout" not in kwargs and "stderr" not in kwargs
            assert "shell" not in kwargs
            assert "PRIVATE_STORE_SECRET" not in kwargs["env"]
            assert Path(kwargs["cwd"]).is_dir()

        def wait(self):
            return 0

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(subprocess, "CREATE_NEW_CONSOLE", 0x10, raising=False)
    monkeypatch.setattr(subprocess, "Popen", Child)
    monkeypatch.setenv("PRIVATE_STORE_SECRET", "never-copy")
    assert _open_login("claude", str(tmp_path / "synthetic.exe")) is True
    assert len(calls) == 1


def test_manual_login_guidance_uses_saved_program_with_powershell_quoting(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    guidance = _guidance("codex", "D:/Synthetic O'Brien Tools/codex.cmd")
    assert guidance["login_command"] == "& 'D:/Synthetic O''Brien Tools/codex.cmd' login"
    assert guidance["login_shell"] == "PowerShell"


def test_manual_login_guidance_uses_saved_program_with_posix_quoting(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    guidance = _guidance("claude", "/synthetic tools/claude")
    assert guidance["login_command"] == "'/synthetic tools/claude' auth login"


def test_manual_custom_profile_guidance_does_not_revert_to_global_cli(repository):
    profile = repository.save(provider="codex", label="Selected shim", notes="",
                              values={"command": "selected-shim.cmd"}, secrets={},
                              secret_store=MemorySecretStore())
    app = setup(repository, login_launcher=lambda *args: False)
    state = app.login({"provider": "codex", "profile_id": profile.id})
    assert "selected-shim.cmd" in state["guidance"]["login_command"]
    assert state["guidance"]["login_command"] != "codex login"


def test_profile_command_with_control_character_is_rejected(repository):
    profile = repository.save(provider="codex", label="Invalid selected shim", notes="",
                              values={"command": "synthetic\nsecond-command"}, secrets={},
                              secret_store=MemorySecretStore())
    with pytest.raises(AISetupError, match="ai_setup_profile_invalid"):
        setup(repository).login({"provider": "codex", "profile_id": profile.id})


def save_profile(repository, *, profile=None, provider="codex", command="selected-cli",
                 model="selected-model", default=False, label="Selected connection"):
    return repository.save(provider=provider, label=label, notes="", secrets={},
                           values={"command": command, "model": model},
                           secret_store=MemorySecretStore(),
                           profile_id=profile.id if profile else None, is_default=default)


def successful_test(repository):
    listing = Listing("Plain cup", "<p>A white ceramic cup.</p>", "Cups", ("cup",),
                      {"SYNTHETIC-CUP": 9.95})
    return setup(repository, [completed("0.144.0"), completed("Logged in using ChatGPT")],
                 generator_factory=lambda *a: SimpleNamespace(generate=lambda product: listing))


@pytest.mark.parametrize("change", [{"command": "other-cli"}, {"model": "other-model"}])
def test_saved_connection_edits_invalidate_previous_test_without_calling_ai(repository, change):
    profile = save_profile(repository)
    app = successful_test(repository)
    assert app.test({"provider": "codex", "profile_id": profile.id,
                     "confirm_usage": True})["usage_verified"] is True
    save_profile(repository, profile=profile, **change)
    state = app.state()
    assert state["status"] == "stale"
    assert state["code"] == "ai_connection_changed"
    assert state["usage_verified"] is False
    assert state["busy"] is False
    assert state["version"] == ""


def test_profile_deletion_invalidates_ready_result(repository):
    profile = save_profile(repository)
    app = setup(repository, [completed("0.144.0"), completed("Logged in using ChatGPT")])
    app.check({"provider": "codex", "profile_id": profile.id})
    repository.delete(profile.id, MemorySecretStore())
    assert app.state()["status"] == "stale"


def test_null_selection_default_change_invalidates_ready_result(repository):
    save_profile(repository, default=True)
    app = successful_test(repository)
    app.test({"provider": "codex", "profile_id": None, "confirm_usage": True})
    save_profile(repository, default=True, command="other-cli", label="Other connection")
    assert app.state()["status"] == "stale"


def test_default_created_after_path_check_invalidates_ready_result(repository):
    app = setup(repository, [completed("0.144.0"), completed("Logged in using ChatGPT")])
    app.check({"provider": "codex", "profile_id": None})
    save_profile(repository, default=True)
    assert app.state()["status"] == "stale"


def test_label_only_edit_does_not_invalidate_readiness(repository):
    profile = save_profile(repository)
    app = successful_test(repository)
    app.test({"provider": "codex", "profile_id": profile.id, "confirm_usage": True})
    save_profile(repository, profile=profile, label="Renamed connection")
    assert app.state()["status"] == "test_passed"


def test_profile_changed_during_test_cannot_be_marked_ready_on_completion(repository):
    profile = save_profile(repository)
    work = []
    app = AISetup(repository, finder=lambda *a, **kw: None, launcher=work.append)
    app.check({"provider": "codex", "profile_id": profile.id})
    save_profile(repository, profile=profile, model="other-model")
    assert app.state()["status"] == "stale"
    assert app.busy is True
    assert app.prepare_shutdown() is False
    work.pop()()
    assert app.state()["status"] == "stale"
    assert app.busy is False


def test_new_check_after_profile_change_uses_new_snapshot(repository):
    profile = save_profile(repository)
    results = [completed("0.144.0"), completed("Logged in using ChatGPT")] * 2
    app = setup(repository, results)
    app.check({"provider": "codex", "profile_id": profile.id})
    save_profile(repository, profile=profile, model="other-model")
    assert app.state()["status"] == "stale"
    assert app.check({"provider": "codex", "profile_id": profile.id})["status"] == "signed_in"
