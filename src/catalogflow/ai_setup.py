"""User-triggered local CLI readiness and a separately confirmed synthetic AI test."""

from __future__ import annotations

import copy
import json
import re
import shlex
import subprocess
import sys
import tempfile
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path

from .generators import ClaudeCliListingGenerator, CodexCliListingGenerator
from .generators.common import (
    CliDiagnosticError,
    cli_failure_code,
    external_program_environment,
    find_cli,
    run_external,
    safe_cli_environment,
)
from .models import Product, Variant
from .validation import validate_listing

_GUIDANCE = {
    "codex": {
        "install_url": "https://developers.openai.com/codex/cli/",
        "login_url": "https://developers.openai.com/codex/auth/",
        "login_command": "codex login",
    },
    "claude": {
        "install_url": "https://code.claude.com/docs/en/setup",
        "login_url": "https://code.claude.com/docs/en/authentication",
        "login_command": "claude auth login",
    },
}
_STATUS_ARGS = {"codex": ["login", "status"], "claude": ["auth", "status"]}
_LOGIN_ARGS = {"codex": ["login"], "claude": ["auth", "login"]}


def _guidance(provider: str, command: str = "") -> dict[str, str]:
    """Quote the user's saved program for display only; never execute a shell string."""
    guidance = dict(_GUIDANCE[provider])
    guidance["login_shell"] = "PowerShell" if sys.platform == "win32" else "terminal"
    if command:
        quoted = ("& '" + command.replace("'", "''") + "'" if sys.platform == "win32"
                  else shlex.quote(command))
        guidance["login_command"] = " ".join([quoted, *_LOGIN_ARGS[provider]])
    return guidance


class AISetupError(ValueError):
    """An HTTP-safe code, with no CLI output or machine-specific details."""

    def __init__(self, code: str, status: int = 400) -> None:
        self.code = code
        self.status = status
        super().__init__(code)


def _version(output: str) -> str:
    for line in output.splitlines():
        match = re.fullmatch(
            r"(?:codex-cli\s+|claude(?: code)?\s+)?"
            r"(\d{1,4}\.\d{1,4}\.\d{1,4}(?:[-+][a-zA-Z0-9.]{1,32})?)"
            r"(?:\s+\(Claude Code\))?", line.strip(), re.IGNORECASE,
        )
        if match:
            return match.group(1)
    return ""


def _auth_status(provider: str, process) -> tuple[str, str]:
    combined = (process.stdout or "") + "\n" + (process.stderr or "")
    failure = cli_failure_code(combined)
    if failure == "ai_cli_upgrade_required":
        return "outdated", failure
    if provider == "claude":
        try:
            data = json.loads(process.stdout or "")
        except (ValueError, TypeError):
            data = None
        if isinstance(data, dict):
            if data.get("loggedIn") is True and process.returncode == 0:
                return "signed_in", "ai_signed_in"
            if data.get("loggedIn") is False and process.returncode == 1:
                return "logged_out", "ai_auth_required"
    elif process.returncode == 0 and re.search(
        r"(?im)^logged in(?: using| with)?\b", combined,
    ):
        return "signed_in", "ai_signed_in"
    if process.returncode != 0 and failure == "ai_auth_required":
        return "logged_out", failure
    return "auth_unknown", "ai_auth_unknown"


def _generator(provider: str, values: dict[str, str]):
    cls = CodexCliListingGenerator if provider == "codex" else ClaudeCliListingGenerator
    # Explicit empty strings match ImportWizard, not environment override variables.
    return cls(command=values.get("command", ""), model=values.get("model", ""),
               timeout_seconds=60)


def _open_login(provider: str, executable: str) -> bool:
    """Open only a native Windows CLI with fixed args; scripts get manual guidance."""
    if sys.platform != "win32" or Path(executable).suffix.lower() != ".exe":
        return False
    # This is a user-owned interactive login window. No stdout, token or identity is captured.
    directory = tempfile.TemporaryDirectory(prefix="catalogflow_login_")
    try:
        with external_program_environment():
            child = subprocess.Popen(  # noqa: S603 - selected executable, fixed login args
                [executable, *_LOGIN_ARGS[provider]],
                cwd=directory.name,
                env=safe_cli_environment(),
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
    except (OSError, RuntimeError):
        directory.cleanup()
        return False

    def cleanup():
        child.wait()
        directory.cleanup()

    threading.Thread(target=cleanup, daemon=True).start()
    return True


class AISetup:
    """One bounded check/test at a time; reading state never launches a CLI."""

    def __init__(self, repository, *, finder=None, runner=None, generator_factory=None,
                 login_launcher=None, launcher=None, clock=None) -> None:
        self.repository = repository
        self._finder = finder or find_cli
        self._runner = runner or run_external
        self._generator_factory = generator_factory or _generator
        self._login_launcher = login_launcher or _open_login
        self._launcher = launcher or self._launch
        self._clock = clock or (lambda: datetime.now(UTC).isoformat())
        self._lock = threading.RLock()
        self._closed = False
        self._selection_snapshot = None
        self._selection_stale = False
        self._job = {"job_id": None, "operation": None, "phase": "idle", "busy": False,
                     "provider": None, "profile_id": None, "selected_profile_id": None,
                     "status": "idle", "code": "", "version": "", "checked_at": None,
                     "usage_verified": False, "guidance": {}}

    @staticmethod
    def _launch(target) -> None:
        threading.Thread(target=target, daemon=False).start()

    @property
    def busy(self) -> bool:
        with self._lock:
            return bool(self._job["busy"])

    def state(self) -> dict[str, object]:
        with self._lock:
            self._invalidate_changed_selection()
            return copy.deepcopy(self._job)

    def _invalidate_changed_selection(self) -> None:
        if self._selection_snapshot is None:
            return
        provider, identifier, previous = self._selection_snapshot
        try:
            profile = (self.repository.find(identifier) if identifier is not None
                       else self.repository.default_for(provider))
            current = self._signature(profile)
        except (ValueError, RuntimeError, OSError, KeyError, TypeError, AttributeError):
            current = None
        if current != previous:
            self._selection_stale = True
        if self._selection_stale:
            self._job.update(status="stale", code="ai_connection_changed",
                             usage_verified=False, version="")

    @staticmethod
    def _signature(profile):
        return ((profile.id, profile.provider, profile.values.get("command", ""),
                 profile.values.get("model", "")) if profile else (None, None, "", ""))

    def prepare_shutdown(self) -> bool:
        with self._lock:
            if self._job["busy"]:
                return False
            self._closed = True
            return True

    def close(self) -> bool:
        return self.prepare_shutdown()

    def check(self, payload) -> dict[str, object]:
        return self._start("check", payload)

    def test(self, payload) -> dict[str, object]:
        return self._start("test", payload)

    def login(self, payload) -> dict[str, object]:
        return self._start("login", payload)

    start_check = check
    start_test = test
    start_login = login

    def _selection(self, operation, payload):
        fields = {"provider", "profile_id"}
        if operation == "test":
            fields.add("confirm_usage")
        if (not isinstance(payload, dict) or set(payload) - fields
                or not isinstance(payload.get("provider"), str)
                or payload["provider"] not in _GUIDANCE):
            raise AISetupError("ai_setup_invalid_request")
        if operation == "test" and payload.get("confirm_usage") is not True:
            raise AISetupError("ai_setup_confirmation_required")
        identifier = payload.get("profile_id")
        if identifier is not None:
            try:
                if not isinstance(identifier, str) or str(uuid.UUID(identifier)) != identifier:
                    raise ValueError
            except (ValueError, AttributeError):
                raise AISetupError("ai_setup_profile_invalid") from None
        provider = payload["provider"]
        try:
            profile = (self.repository.find(identifier) if identifier is not None
                       else self.repository.default_for(provider))
            if profile is not None and (
                profile.provider != provider
                or (identifier is not None and profile.id != identifier)
            ):
                raise ValueError
        except (ValueError, RuntimeError, KeyError):
            raise AISetupError("ai_setup_profile_invalid") from None
        return provider, identifier, profile

    def _start(self, operation, payload):
        with self._lock:
            if self._closed:
                raise AISetupError("ai_setup_closed", 409)
            if self._job["busy"]:
                raise AISetupError("ai_setup_busy", 409)
            provider, identifier, profile = self._selection(operation, payload)
            values = dict(profile.values) if profile else {}
            command = values.get("command", "")
            if any(ord(char) < 32 or ord(char) == 127 for char in command):
                raise AISetupError("ai_setup_profile_invalid")
            self._selection_snapshot = (provider, identifier, self._signature(profile))
            self._selection_stale = False
            self._job = {
                "job_id": str(uuid.uuid4()), "operation": operation, "phase": "running",
                "busy": True, "provider": provider, "profile_id": identifier,
                "selected_profile_id": profile.id if profile else None,
                "status": "testing" if operation == "test" else "checking", "code": "",
                "version": "", "checked_at": None, "usage_verified": False,
                "guidance": _guidance(provider, command),
            }
            try:
                self._launcher(lambda: self._work(operation, provider, values))
            except RuntimeError:
                self._finish("auth_unknown", "ai_auth_unknown")
            return self.state()

    def _finish(self, status, code, **values):
        with self._lock:
            self._job.update(phase="complete", busy=False, status=status, code=code,
                             checked_at=self._clock(), **values)
            self._invalidate_changed_selection()

    def _run(self, executable, args, directory):
        process = self._runner(
            [executable, *args], text=True, encoding="utf-8", errors="replace",
            capture_output=True, check=False, timeout=10, env=safe_cli_environment(),
            cwd=directory, max_output_bytes=16 * 1024,
        )
        output = (process.stdout or "", process.stderr or "")
        if (any(not isinstance(value, str) for value in output)
                or sum(len(value.encode("utf-8")) for value in output) > 16 * 1024):
            raise CliDiagnosticError("ai_output_limit")
        return process

    def _work(self, operation, provider, values):
        try:
            executable = self._finder(provider, f"CATALOGFLOW_{provider.upper()}_COMMAND",
                                      command=values.get("command", ""))
            if not executable:
                self._finish("missing", "ai_cli_missing")
                return
            if operation == "login":
                opened = self._login_launcher(provider, executable)
                self._finish("login_opened" if opened else "manual_login_required",
                             "ai_login_opened" if opened else "ai_login_manual_required")
                return
            with tempfile.TemporaryDirectory(prefix="catalogflow_ai_check_") as directory:
                result = self._run(executable, ["--version"], directory)
                version = _version((result.stdout or "") + "\n" + (result.stderr or ""))
                if result.returncode != 0 or not version:
                    self._finish("auth_unknown", "ai_auth_unknown")
                    return
                with self._lock:
                    self._job["version"] = version
                result = self._run(executable, _STATUS_ARGS[provider], directory)
                status, code = _auth_status(provider, result)
            if operation == "check" or status in {"outdated", "logged_out"}:
                self._finish(status, code)
                return
            # An unknown status does not prove absence of auth. Only this explicit action
            # may make one real provider request; never retry or replace the selected model.
            product = Product("alibaba-manual", "synthetic-ai-check", "Plain ceramic cup",
                              "USD", (Variant("SYNTHETIC-CUP", 1),),
                              facts={"material": "ceramic", "color": "white"})
            listing = self._generator_factory(provider, values).generate(product)
            if validate_listing(listing, product):
                self._finish("test_failed", "ai_test_invalid_output")
            else:
                self._finish("test_passed", "ai_test_passed", usage_verified=True)
        except subprocess.TimeoutExpired:
            self._finish("test_failed" if operation == "test" else "auth_unknown",
                         "ai_test_timeout" if operation == "test" else "ai_check_timeout")
        except Exception as exc:
            code = getattr(exc, "code", "")
            if code in {"ai_cli_upgrade_required", "codex_cli_upgrade_required"}:
                self._finish("outdated", "ai_cli_upgrade_required")
            elif code == "ai_auth_required":
                self._finish("logged_out", code)
            elif code == "ai_subscription_or_quota":
                self._finish("test_failed", code)
            else:
                self._finish("test_failed" if operation == "test" else "auth_unknown",
                             "ai_test_failed" if operation == "test" else "ai_auth_unknown")
