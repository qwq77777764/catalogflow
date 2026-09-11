import json

import pytest

from catalogflow.configuration import (
    PROVIDERS,
    MemorySecretStore,
    ProfileRepository,
    environment_for_profile,
    public_profile,
)


def test_provider_catalog_groups_store_source_and_local_ai_connections() -> None:
    categories = {definition["category"] for definition in PROVIDERS.values()}
    assert categories == {"store", "source", "ai"}
    assert PROVIDERS["woocommerce"]["availability"] == "available"
    assert PROVIDERS["wordpress_ssh"]["availability"] == "planned"
    assert PROVIDERS["shopify"]["availability"] == "planned"


def test_profile_metadata_never_contains_secret(tmp_path) -> None:
    repository = ProfileRepository(tmp_path)
    secrets = MemorySecretStore()
    profile = repository.save(
        provider="woocommerce",
        label="US store",
        notes="Hidden drafts only",
        values={"url": "https://store.example"},
        secrets={"consumer_key": "private-key", "consumer_secret": "private-secret"},
        secret_store=secrets,
        is_default=True,
    )

    on_disk = repository.path.read_text(encoding="utf-8")
    assert "private-key" not in on_disk
    assert "private-secret" not in on_disk
    assert json.loads(on_disk)["profiles"][0]["notes"] == "Hidden drafts only"
    assert public_profile(profile, secrets)["configured_secret_fields"] == [
        "consumer_key",
        "consumer_secret",
    ]


def test_profile_resolves_runtime_environment(tmp_path) -> None:
    repository = ProfileRepository(tmp_path)
    secrets = MemorySecretStore()
    profile = repository.save(
        provider="woocommerce",
        label="US store",
        notes="",
        values={"url": "https://store.example"},
        secrets={"consumer_key": "key", "consumer_secret": "secret"},
        secret_store=secrets,
    )

    assert environment_for_profile(profile, secrets) == {
        "WOOCOMMERCE_URL": "https://store.example",
        "WOOCOMMERCE_CONSUMER_KEY": "key",
        "WOOCOMMERCE_CONSUMER_SECRET": "secret",
    }


def test_shopify_profile_keeps_client_secret_out_of_metadata(tmp_path) -> None:
    repository = ProfileRepository(tmp_path)
    secrets = MemorySecretStore()
    profile = repository.save(
        provider="shopify",
        label="Future Shopify store",
        notes="Own-organization Dev Dashboard app",
        values={
            "shop": "example.myshopify.com",
            "client_id": "public-client-id",
        },
        secrets={"client_secret": "private-client-secret"},
        secret_store=secrets,
    )

    on_disk = repository.path.read_text(encoding="utf-8")
    assert "private-client-secret" not in on_disk
    assert environment_for_profile(profile, secrets) == {
        "SHOPIFY_SHOP": "example.myshopify.com",
        "SHOPIFY_CLIENT_ID": "public-client-id",
        "SHOPIFY_CLIENT_SECRET": "private-client-secret",
    }


def test_only_one_default_profile_per_provider(tmp_path) -> None:
    repository = ProfileRepository(tmp_path)
    secrets = MemorySecretStore()
    first = repository.save(
        provider="codex",
        label="First",
        notes="",
        values={},
        secrets={},
        secret_store=secrets,
        is_default=True,
    )
    second = repository.save(
        provider="codex",
        label="Second",
        notes="",
        values={},
        secrets={},
        secret_store=secrets,
        is_default=True,
    )

    profiles = {profile.id: profile for profile in repository.list()}
    assert profiles[first.id].is_default is False
    assert profiles[second.id].is_default is True


def test_blank_secret_keeps_existing_keyring_value(tmp_path) -> None:
    repository = ProfileRepository(tmp_path)
    secrets = MemorySecretStore()
    profile = repository.save(
        provider="cj",
        label="Official CJ",
        notes="",
        values={},
        secrets={"api_key": "original-secret"},
        secret_store=secrets,
    )

    repository.save(
        profile_id=profile.id,
        provider="cj",
        label="Official CJ renamed",
        notes="",
        values={},
        secrets={"api_key": ""},
        secret_store=secrets,
    )

    assert secrets.get(profile.id, "api_key") == "original-secret"


def test_secret_is_rolled_back_when_metadata_write_fails(tmp_path, monkeypatch) -> None:
    repository = ProfileRepository(tmp_path)
    secrets = MemorySecretStore()

    def fail_write(_profiles) -> None:
        raise OSError("simulated metadata failure")

    monkeypatch.setattr(repository, "_write", fail_write)
    with pytest.raises(OSError, match="simulated metadata failure"):
        repository.save(
            provider="zendrop",
            label="Zendrop account",
            notes="",
            values={},
            secrets={"api_token": "temporary-secret"},
            secret_store=secrets,
        )

    assert secrets.values == {}


def test_profile_labels_are_unique_case_insensitively(tmp_path) -> None:
    repository = ProfileRepository(tmp_path)
    secrets = MemorySecretStore()
    repository.save(
        provider="codex",
        label="Local AI",
        notes="",
        values={},
        secrets={},
        secret_store=secrets,
    )

    with pytest.raises(ValueError, match="labels must be unique"):
        repository.save(
            provider="claude",
            label="local ai",
            notes="",
            values={},
            secrets={},
            secret_store=secrets,
        )
