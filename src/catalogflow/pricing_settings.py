"""Strict local persistence for non-secret pricing settings."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path

from .configuration import default_config_directory
from .pricing import PricingPolicy

PRICING_SETTINGS_VERSION = 1


class PricingSettingsRepository:
    """Load and atomically save one validated ``pricing.json`` file."""

    def __init__(self, directory: str | Path | None = None) -> None:
        self.directory = Path(directory) if directory else default_config_directory()
        self.path = self.directory / "pricing.json"
        self._lock = threading.RLock()

    def load(self) -> PricingPolicy:
        if not self.path.exists():
            return PricingPolicy()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("CatalogFlow pricing settings are unreadable") from exc
        if not isinstance(payload, dict):
            raise ValueError("pricing.json must contain a JSON object")
        expected = {"version", "settings"}
        unknown = set(payload) - expected
        missing = expected - set(payload)
        if unknown:
            raise ValueError(f"Unknown pricing.json fields: {', '.join(sorted(unknown))}")
        if missing:
            raise ValueError(f"Missing pricing.json fields: {', '.join(sorted(missing))}")
        if payload["version"] != PRICING_SETTINGS_VERSION:
            raise ValueError(
                f"Unsupported pricing.json version: {payload['version']!r}"
            )
        settings = payload["settings"]
        if not isinstance(settings, dict):
            raise ValueError("pricing.json settings must be a JSON object")
        return PricingPolicy.from_dict(settings)

    def save(self, policy: PricingPolicy) -> None:
        if not isinstance(policy, PricingPolicy):
            raise TypeError("policy must be a PricingPolicy")
        payload = {
            "version": PRICING_SETTINGS_VERSION,
            "settings": policy.to_dict(),
        }
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        ) + "\n"
        with self._lock:
            self.directory.mkdir(parents=True, exist_ok=True)
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=".pricing-",
                suffix=".tmp",
                dir=self.directory,
            )
            temporary_path = Path(temporary_name)
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                    handle.write(serialized)
                    handle.flush()
                    os.fsync(handle.fileno())
                try:
                    temporary_path.chmod(0o600)
                except OSError:
                    pass
                os.replace(temporary_path, self.path)
            finally:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass
