"""Shared helpers for local CLI-backed listing generators."""

from __future__ import annotations

import json
import os
import shutil
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

    return {key: value for key, value in os.environ.items() if key.upper() in _PASSTHROUGH_ENV}


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
