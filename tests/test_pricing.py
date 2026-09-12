import math
from dataclasses import replace

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


def test_breakdown_explains_fees_profit_and_break_even_from_final_price() -> None:
    breakdown = PricingPolicy(
        payment_fee_rate=0.10,
        payment_fixed_fee=0.50,
        return_rate=0.05,
        operating_rate=0.05,
        target_margin=0.30,
        tax_duties_per_unit=1,
    ).breakdown(10, inbound_shipping=2, last_mile=3)

    assert breakdown.final_price == 33.95
    assert breakdown.payment_percentage_fee == pytest.approx(3.395)
    assert breakdown.return_reserve == pytest.approx(1.6975)
    assert breakdown.operating_reserve == pytest.approx(1.6975)
    assert breakdown.estimated_profit == pytest.approx(10.66)
    assert breakdown.estimated_margin == pytest.approx(10.66 / 33.95, abs=0.000001)
    assert breakdown.break_even_price == pytest.approx(20.625)


@pytest.mark.parametrize(
    ("settings", "driver", "raw_price", "rounding_adjustment"),
    [
        ({"minimum_multiplier": 3}, "minimum_multiplier", 30, 0.95),
        ({"minimum_price": 40}, "minimum_price", 40, 0.95),
        ({"minimum_price": 10, "minimum_multiplier": 1}, "formula", 10, 0.95),
        ({"scheme": "cost_multiplier", "cost_multiplier": 2.195}, "formula", 21.95, 0),
    ],
)
def test_breakdown_explains_winning_floor_and_upward_rounding(
    settings, driver, raw_price, rounding_adjustment
) -> None:
    policy = PricingPolicy(
        payment_fee_rate=0,
        payment_fixed_fee=0,
        return_rate=0,
        operating_rate=0,
        target_margin=0,
        **settings,
    )

    breakdown = policy.breakdown(10)

    assert breakdown.price_driver == driver
    assert breakdown.raw_price == pytest.approx(raw_price)
    assert breakdown.rounding_adjustment == pytest.approx(rounding_adjustment)
    assert breakdown.final_price == pytest.approx(raw_price + rounding_adjustment)


def test_cost_multiplier_reports_negative_profit_without_changing_selling_price() -> None:
    policy = PricingPolicy(
        scheme="cost_multiplier",
        cost_multiplier=1,
        payment_fee_rate=0.3,
        return_rate=0.2,
        operating_rate=0.1,
    )
    breakdown = policy.breakdown(10, last_mile=5)
    no_rates = replace(policy, payment_fee_rate=0, return_rate=0, operating_rate=0)

    assert breakdown.final_price == no_rates.price(10, last_mile=5) == 15.95
    assert breakdown.estimated_profit == pytest.approx(-9.02)
    assert breakdown.estimated_margin == pytest.approx(-9.02 / 15.95, abs=0.000001)
    assert breakdown.break_even_price == pytest.approx(38.5)
