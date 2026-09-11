import json

import pytest

from catalogflow.pricing import PricingPolicy, PricingScheme
from catalogflow.pricing_settings import PricingSettingsRepository


def test_missing_file_uses_legacy_compatible_defaults(tmp_path) -> None:
    repository = PricingSettingsRepository(tmp_path)

    policy = repository.load()

    assert policy == PricingPolicy()
    assert policy.price(8.50) == 22.95
    assert not repository.path.exists()


def test_pricing_settings_round_trip_to_non_secret_pricing_json(tmp_path) -> None:
    repository = PricingSettingsRepository(tmp_path)
    policy = PricingPolicy(
        scheme=PricingScheme.COST_MULTIPLIER,
        cost_multiplier=10,
        tax_duties_per_unit=1.25,
    )

    repository.save(policy)

    assert repository.path.name == "pricing.json"
    assert repository.load() == policy
    assert not list(tmp_path.glob(".pricing-*.tmp"))


def test_pricing_file_rejects_unknown_fields(tmp_path) -> None:
    repository = PricingSettingsRepository(tmp_path)
    payload = {"version": 1, "settings": PricingPolicy().to_dict(), "secret": "no"}
    repository.path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="Unknown pricing.json"):
        repository.load()


@pytest.mark.parametrize("invalid", [float("nan"), float("inf")])
def test_pricing_file_rejects_non_finite_values(tmp_path, invalid: float) -> None:
    repository = PricingSettingsRepository(tmp_path)
    settings = PricingPolicy().to_dict()
    settings["minimum_price"] = invalid
    repository.path.write_text(
        json.dumps({"version": 1, "settings": settings}), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="finite"):
        repository.load()
