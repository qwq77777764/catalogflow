import pytest

from catalogflow.cost_formula import (
    CostFormulaError,
    apply_cost_formula,
    normalize_cost_formula,
)
from catalogflow.pricing import PricingPolicy


@pytest.mark.parametrize(
    ("formula", "expected"),
    [
        ("*5", 42.5), ("/5", 1.7), ("+5", 13.5), ("-5", 3.5),
        ("5", 42.5), ("*3+2", 27.5), ("*3+2/5", 25.9),
        ("*(5+2)/3", 8.5 * 7 / 3), ("*2-1-2", 14), ("/2/5", 0.85),
        (" * .5 + 2 ", 6.25), ("*0.1*10", 8.5), ("*(-2)+20", 3), ("*0", 0),
    ],
)
def test_arithmetic_uses_cost_and_normal_operator_precedence(formula, expected):
    assert apply_cost_formula(formula, 8.5) == pytest.approx(expected)


@pytest.mark.parametrize(
    "formula",
    [
        "", " ", "1 2", "*", "*2+", "**2", "//2", "*2^3", "*2%3",
        "*(2+3", "*2)", "*(2)(3)", "*NaN", "*inf", "*1e3", "*1000001",
        "*２", "×5", "cost*5", "*__import__('os')", "*2;print(1)",
        "*(" + "(" * 13 + "1" + ")" * 14,
        "*1" * 33, " " * 121,
    ],
    ids=lambda value: value[:35],
)
def test_invalid_or_executable_inputs_are_rejected(formula):
    with pytest.raises(CostFormulaError, match="^cost_formula_invalid$"):
        normalize_cost_formula(formula)


@pytest.mark.parametrize("formula", ["/0", "/(3-3)", "*2+1/(2-2)"])
def test_zero_divisors_are_rejected_before_saving(formula):
    with pytest.raises(CostFormulaError, match="^cost_formula_division_by_zero$"):
        PricingPolicy(cost_formula=formula)


@pytest.mark.parametrize(
    ("formula", "cost"), [("-9", 8.5), ("*1000000", 101), ("*1000000/1000000", 101)]
)
def test_invalid_results_and_excessive_intermediate_values_are_rejected(formula, cost):
    with pytest.raises(CostFormulaError, match="^cost_formula_result_out_of_range$"):
        apply_cost_formula(formula, cost)


def test_formula_preserves_freight_fees_floors_and_real_cost_profit():
    policy = PricingPolicy(
        scheme="cost_multiplier", cost_formula="/5", minimum_price=0,
        tax_duties_per_unit=2,
    )
    item = policy.breakdown(10, inbound_shipping=1, last_mile=4)
    assert item.cost_formula == "/5"
    assert item.formula_cost == 2
    assert item.primary_candidate == 9.4
    assert item.final_price == 9.95
    assert item.landed_cost == 17
    assert item.estimated_profit < 0
    floor = PricingPolicy(scheme="cost_multiplier", cost_formula="/5", minimum_price=20)
    assert floor.breakdown(10).price_driver == "minimum_price"
    assert floor.price(10) == 20.95


def test_margin_prices_do_not_apply_plan_b_formula():
    assert PricingPolicy(cost_formula="/5").price(8.5, last_mile=4.71) == 34.95


def test_legacy_numeric_settings_still_load_and_keep_their_prices():
    payload = PricingPolicy(scheme="cost_multiplier", cost_multiplier=7).to_dict()
    del payload["cost_formula"]
    restored = PricingPolicy.from_dict(payload)
    assert restored.cost_formula is None
    assert restored.breakdown(8.5).cost_formula == "*7"
    assert restored.price(8.5) == 59.95
