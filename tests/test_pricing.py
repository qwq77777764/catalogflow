import math

import pytest

from catalogflow.pricing import PricingPolicy, PricingScheme


def test_price_preserves_95_ending_and_margin_floor() -> None:
    price = PricingPolicy().price(8.50)
    assert price == 22.95


def test_price_includes_end_to_end_shipping_cost() -> None:
    price = PricingPolicy().price(8.50, last_mile=4.71)
    assert price == 34.95


def test_negative_cost_is_rejected() -> None:
    try:
        PricingPolicy().price(-1)
    except ValueError as exc:
        assert "negative" in str(exc)
    else:
        raise AssertionError("negative costs must fail")


def test_margin_plan_adds_optional_tax_to_landed_cost() -> None:
    breakdown = PricingPolicy(tax_duties_per_unit=1.0).breakdown(
        8.50, last_mile=4.71
    )

    assert breakdown.landed_cost == 14.21
    assert breakdown.final_price == 37.95


def test_cost_multiplier_adds_shipping_tax_and_fixed_fee_only_once() -> None:
    breakdown = PricingPolicy(
        scheme=PricingScheme.COST_MULTIPLIER,
        cost_multiplier=3,
        tax_duties_per_unit=2,
    ).breakdown(8.50, inbound_shipping=1, last_mile=4.71)

    assert breakdown.primary_candidate == 33.61
    assert breakdown.raw_price == 33.61
    assert breakdown.final_price == 33.95


def test_cost_multiplier_accepts_ten_and_keeps_minimum_price_floor() -> None:
    policy = PricingPolicy(
        scheme="cost_multiplier",
        cost_multiplier=10,
        minimum_price=29.95,
    )

    assert policy.price(2, inbound_shipping=3, last_mile=4) == 29.95


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_non_finite_settings_are_rejected(value: float) -> None:
    with pytest.raises(ValueError, match="finite"):
        PricingPolicy(cost_multiplier=value)


def test_multiplier_range_and_margin_divisor_are_validated() -> None:
    with pytest.raises(ValueError, match="between 1 and 100"):
        PricingPolicy(cost_multiplier=101)
    with pytest.raises(ValueError, match="divisor"):
        PricingPolicy(payment_fee_rate=0.3, return_rate=0.2, target_margin=0.5)


def test_pricing_mapping_rejects_unknown_and_missing_fields() -> None:
    settings = PricingPolicy().to_dict()
    with pytest.raises(ValueError, match="Unknown"):
        PricingPolicy.from_dict({**settings, "surprise": 1})
    settings.pop("minimum_price")
    with pytest.raises(ValueError, match="Missing"):
        PricingPolicy.from_dict(settings)
