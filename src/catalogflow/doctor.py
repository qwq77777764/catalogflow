"""Read-only checks for optional local AI command-line tools."""

from __future__ import annotations

import json
import subprocess

from .generators.common import find_cli, run_external, safe_cli_environment


def provider_status(name: str, override_variable: str) -> dict[str, str | bool]:
    executable = find_cli(name, override_variable)
    if not executable:
        return {
            "provider": name,
            "installed": False,
            "ready_for_auth_check": False,
            "message": f"not found; see docs/local-ai.md ({override_variable} can override PATH)",
        }
    try:
        process = run_external(
            [executable, "--version"],
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=10,
            check=False,
            env=safe_cli_environment(),
        )
        lines = (process.stdout or process.stderr or "").strip().splitlines()
        version = lines[0] if lines else "No version output"
    except (OSError, subprocess.SubprocessError) as exc:
        return {
            "provider": name,
            "installed": True,
            "ready_for_auth_check": False,
            "message": f"found but --version failed: {type(exc).__name__}",
        }
    return {
        "provider": name,
        "installed": process.returncode == 0,
        "ready_for_auth_check": process.returncode == 0,
        "version": version,
        "message": "installed; CatalogFlow reuses this CLI's own login session",
    }


def doctor_report() -> dict[str, object]:
    return {
        "ok": True,
        "note": "This is a local installation check; it does not make an AI request.",
        "providers": [
            provider_status("codex", "CATALOGFLOW_CODEX_COMMAND"),
            provider_status("claude", "CATALOGFLOW_CLAUDE_COMMAND"),
        ],
    }


def print_doctor_report() -> None:
    print(json.dumps(doctor_report(), ensure_ascii=False, indent=2))
