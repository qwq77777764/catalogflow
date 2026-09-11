from catalogflow.pricing import PricingPolicy


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
