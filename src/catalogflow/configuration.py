"""Local connection profiles with secrets delegated to the operating-system keyring."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Protocol

PROVIDERS: dict[str, dict[str, object]] = {
    "woocommerce": {
        "name": "WooCommerce",
        "description": "Create hidden product drafts in your own store.",
        "availability": "available",
        "fields": [
            {
                "name": "url",
                "label": "Store URL",
                "type": "url",
                "secret": False,
                "environment": "WOOCOMMERCE_URL",
                "placeholder": "https://store.example",
            },
            {
                "name": "consumer_key",
                "label": "Consumer key",
                "type": "password",
                "secret": True,
                "environment": "WOOCOMMERCE_CONSUMER_KEY",
                "placeholder": "ck_…",
            },
            {
                "name": "consumer_secret",
                "label": "Consumer secret",
                "type": "password",
                "secret": True,
                "environment": "WOOCOMMERCE_CONSUMER_SECRET",
                "placeholder": "cs_…",
            },
        ],
    },
    "cj": {
        "name": "CJdropshipping API",
        "description": "Reserved for the official CJ source adapter.",
        "availability": "planned",
        "fields": [
            {
                "name": "api_key",
                "label": "Official API key",
                "type": "password",
                "secret": True,
                "environment": "CJ_API_KEY",
                "placeholder": "Paste your own approved key",
            }
        ],
    },
    "alibaba": {
        "name": "Alibaba / 1688 Open Platform",
        "description": "Reserved for an authorized Open Platform adapter.",
        "availability": "planned",
        "fields": [
            {
                "name": "app_key",
                "label": "App key",
                "type": "password",
                "secret": True,
                "environment": "ALIBABA_APP_KEY",
                "placeholder": "Your own application key",
            },
            {
                "name": "app_secret",
                "label": "App secret",
                "type": "password",
                "secret": True,
                "environment": "ALIBABA_APP_SECRET",
                "placeholder": "Your own application secret",
            },
            {
                "name": "access_token",
                "label": "Access token (if required)",
                "type": "password",
                "secret": True,
                "environment": "ALIBABA_ACCESS_TOKEN",
                "placeholder": "Optional provider-issued token",
            },
        ],
    },
    "zendrop": {
        "name": "Zendrop API",
        "description": "Reserved for a future authorized source adapter.",
        "availability": "planned",
        "fields": [
            {
                "name": "api_token",
                "label": "API token",
                "type": "password",
                "secret": True,
                "environment": "ZENDROP_API_TOKEN",
                "placeholder": "Paste your own token",
            }
        ],
    },
    "codex": {
        "name": "Codex CLI",
        "description": "Reuse the Codex CLI login already stored on this computer.",
        "availability": "available",
        "fields": [
            {
                "name": "command",
                "label": "Executable path (optional)",
                "type": "text",
                "secret": False,
                "environment": "CATALOGFLOW_CODEX_COMMAND",
                "placeholder": "Leave blank when codex is in PATH",
            },
            {
                "name": "model",
                "label": "Model override (optional)",
                "type": "text",
                "secret": False,
                "environment": "CATALOGFLOW_CODEX_MODEL",
                "placeholder": "Use the CLI default when blank",
            },
        ],
    },
    "claude": {
        "name": "Claude Code CLI",
        "description": "Reuse the Claude Code login already stored on this computer.",
        "availability": "available",
        "fields": [
            {
                "name": "command",
                "label": "Executable path (optional)",
                "type": "text",
                "secret": False,
                "environment": "CATALOGFLOW_CLAUDE_COMMAND",
                "placeholder": "Leave blank when claude is in PATH",
            },
            {
                "name": "model",
                "label": "Model override (optional)",
                "type": "text",
                "secret": False,
                "environment": "CATALOGFLOW_CLAUDE_MODEL",
                "placeholder": "Use the CLI default when blank",
            },
        ],
    },
}


class SecretStore(Protocol):
    def get(self, profile_id: str, field_name: str) -> str | None: ...

    def set(self, profile_id: str, field_name: str, value: str) -> None: ...

    def delete(self, profile_id: str, field_name: str) -> None: ...


class SystemKeyringStore:
    """Store values in Windows Credential Manager, Keychain, or a Linux keyring."""

    service_prefix = "catalogflow"

    @staticmethod
    def _keyring():
        try:
            import keyring
            from keyring.errors import KeyringError
        except ImportError as exc:  # pragma: no cover - packaging installs it
            raise RuntimeError("System keyring support is not installed") from exc
        return keyring, KeyringError

    def _service(self, profile_id: str) -> str:
        return f"{self.service_prefix}/{profile_id}"

    def get(self, profile_id: str, field_name: str) -> str | None:
        keyring, keyring_error = self._keyring()
        try:
            return keyring.get_password(self._service(profile_id), field_name)
        except keyring_error as exc:
            raise RuntimeError("The operating-system keyring is unavailable") from exc

    def set(self, profile_id: str, field_name: str, value: str) -> None:
        keyring, keyring_error = self._keyring()
        try:
            keyring.set_password(self._service(profile_id), field_name, value)
        except keyring_error as exc:
            raise RuntimeError("The operating-system keyring refused the secret") from exc

    def delete(self, profile_id: str, field_name: str) -> None:
        keyring, keyring_error = self._keyring()
        try:
            keyring.delete_password(self._service(profile_id), field_name)
        except keyring_error:
            return


class MemorySecretStore:
    """Test-only keyring replacement."""

    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def get(self, profile_id: str, field_name: str) -> str | None:
        return self.values.get((profile_id, field_name))

    def set(self, profile_id: str, field_name: str, value: str) -> None:
        self.values[(profile_id, field_name)] = value

    def delete(self, profile_id: str, field_name: str) -> None:
        self.values.pop((profile_id, field_name), None)


@dataclass(frozen=True, slots=True)
class ConnectionProfile:
    id: str
    provider: str
    label: str
    notes: str = ""
    values: dict[str, str] = field(default_factory=dict)
    is_default: bool = False


def default_config_directory() -> Path:
    override = os.environ.get("CATALOGFLOW_CONFIG_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    if os.name == "nt" and os.environ.get("APPDATA"):
        return Path(os.environ["APPDATA"]) / "CatalogFlow"
    xdg = os.environ.get("XDG_CONFIG_HOME", "").strip()
    return Path(xdg).expanduser() / "catalogflow" if xdg else Path.home() / ".config/catalogflow"


class ProfileRepository:
    """Persist non-secret labels, notes, and settings in a local JSON file."""

    def __init__(self, directory: str | Path | None = None) -> None:
        self.directory = Path(directory) if directory else default_config_directory()
        self.path = self.directory / "profiles.json"

    def list(self) -> tuple[ConnectionProfile, ...]:
        if not self.path.exists():
            return ()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("CatalogFlow profile metadata is unreadable") from exc
        profiles = []
        for row in payload.get("profiles", []):
            profiles.append(
                ConnectionProfile(
                    id=str(row["id"]),
                    provider=str(row["provider"]),
                    label=str(row["label"]),
                    notes=str(row.get("notes", "")),
                    values={str(k): str(v) for k, v in row.get("values", {}).items()},
                    is_default=bool(row.get("is_default", False)),
                )
            )
        return tuple(profiles)

    def find(self, reference: str) -> ConnectionProfile:
        exact = [item for item in self.list() if item.id == reference]
        matches = exact or [
            item for item in self.list() if item.label.casefold() == reference.casefold()
        ]
        if not matches:
            raise ValueError("Connection profile was not found")
        if len(matches) > 1:
            raise ValueError("Connection profile label is ambiguous; use its ID")
        return matches[0]

    def default_for(self, provider: str) -> ConnectionProfile | None:
        return next(
            (item for item in self.list() if item.provider == provider and item.is_default),
            None,
        )

    def save(
        self,
        *,
        provider: str,
        label: str,
        notes: str,
        values: dict[str, str],
        secrets: dict[str, str],
        secret_store: SecretStore,
        profile_id: str | None = None,
        is_default: bool = False,
    ) -> ConnectionProfile:
        profile_id = profile_id or str(uuid.uuid4())
        profile = _validated_profile(profile_id, provider, label, notes, values, is_default)
        existing_profiles = list(self.list())
        existing = next((item for item in existing_profiles if item.id == profile.id), None)
        if existing and existing.provider != provider:
            raise ValueError("A profile cannot be moved to another provider")
        duplicate_label = next(
            (
                item
                for item in existing_profiles
                if item.id != profile.id and item.label.casefold() == profile.label.casefold()
            ),
            None,
        )
        if duplicate_label:
            raise ValueError("Connection profile labels must be unique")
        secret_names = _secret_field_names(provider)
        unknown = set(secrets) - secret_names
        if unknown:
            raise ValueError("Unknown secret fields: " + ", ".join(sorted(unknown)))
        clean_secrets = {}
        for name, value in secrets.items():
            clean = value.strip()
            if len(clean) > 4096:
                raise ValueError("Connection secret is too long")
            if clean:
                clean_secrets[name] = clean
        original_secrets = {
            name: secret_store.get(profile.id, name) for name in clean_secrets
        }
        written_secret_names: list[str] = []
        profiles = [item for item in existing_profiles if item.id != profile.id]
        if is_default:
            profiles = [
                ConnectionProfile(**{**asdict(item), "is_default": False})
                if item.provider == provider
                else item
                for item in profiles
            ]
        profiles.append(profile)
        try:
            for name, value in clean_secrets.items():
                secret_store.set(profile.id, name, value)
                written_secret_names.append(name)
            self._write(profiles)
        except Exception:
            for name in reversed(written_secret_names):
                try:
                    original = original_secrets[name]
                    if original is None:
                        secret_store.delete(profile.id, name)
                    else:
                        secret_store.set(profile.id, name, original)
                except Exception:  # noqa: S110 - never log keyring operations or values
                    # Preserve the original failure. A later save can replace an orphaned
                    # keyring entry, while masking the write failure would mislead callers.
                    pass
            raise
        return profile

    def delete(self, profile_id: str, secret_store: SecretStore) -> None:
        profile = self.find(profile_id)
        self._write([item for item in self.list() if item.id != profile.id])
        for name in _secret_field_names(profile.provider):
            secret_store.delete(profile.id, name)

    def _write(self, profiles: list[ConnectionProfile]) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        payload = {"version": 1, "profiles": [asdict(item) for item in profiles]}
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        try:
            temporary.chmod(0o600)
        except OSError:
            pass
        temporary.replace(self.path)


def _provider_fields(provider: str) -> tuple[dict[str, object], ...]:
    if provider not in PROVIDERS:
        raise ValueError("Unknown connection provider")
    return tuple(PROVIDERS[provider]["fields"])


def _secret_field_names(provider: str) -> set[str]:
    return {str(item["name"]) for item in _provider_fields(provider) if item["secret"]}


def _validated_profile(
    profile_id: str,
    provider: str,
    label: str,
    notes: str,
    values: dict[str, str],
    is_default: bool,
) -> ConnectionProfile:
    try:
        uuid.UUID(profile_id)
    except ValueError as exc:
        raise ValueError("Invalid connection profile ID") from exc
    label = label.strip()
    notes = notes.strip()
    if not label or len(label) > 80:
        raise ValueError("Profile label must contain 1-80 characters")
    if len(notes) > 500:
        raise ValueError("Profile notes cannot exceed 500 characters")
    allowed_values = {
        str(item["name"]) for item in _provider_fields(provider) if not item["secret"]
    }
    unknown = set(values) - allowed_values
    if unknown:
        raise ValueError("Unknown non-secret fields: " + ", ".join(sorted(unknown)))
    clean_values = {}
    for name, value in values.items():
        clean = str(value).strip()
        if len(clean) > 2048:
            raise ValueError("Connection setting is too long")
        if clean:
            clean_values[name] = clean
    return ConnectionProfile(profile_id, provider, label, notes, clean_values, is_default)


def public_profile(profile: ConnectionProfile, secrets: SecretStore) -> dict[str, object]:
    """Return dashboard-safe metadata without returning any secret value."""

    configured = [
        name
        for name in sorted(_secret_field_names(profile.provider))
        if secrets.get(profile.id, name)
    ]
    return {
        **asdict(profile),
        "configured_secret_fields": configured,
    }


def environment_for_profile(profile: ConnectionProfile, secrets: SecretStore) -> dict[str, str]:
    """Resolve one profile into the environment names consumed by existing adapters."""

    result: dict[str, str] = {}
    for field_definition in _provider_fields(profile.provider):
        name = str(field_definition["name"])
        if field_definition["secret"]:
            value = secrets.get(profile.id, name)
        else:
            value = profile.values.get(name)
        if value:
            result[str(field_definition["environment"])] = value
    return result
