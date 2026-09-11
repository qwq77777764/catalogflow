"""Deterministic pricing policy extracted from the production workflow."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .models import Product, Variant


def shipping_cost_for_pricing(product: Product, variant: Variant) -> float:
    """Return a validated unit shipping cost, requiring it for CJ products."""

    quote = variant.shipping_quote
    if quote is None:
        if product.source == "cj":
            raise ValueError("CJ variants require a shipping quote before pricing")
        return 0.0
    if (
        quote.quantity < 1
        or not math.isfinite(quote.total_cost_usd)
        or quote.total_cost_usd < 0
    ):
        raise ValueError("Shipping quote must have a positive quantity and finite cost")
    if product.source == "cj" and quote.total_cost_usd == 0:
        raise ValueError("CJ variants require a positive shipping cost before pricing")
    return quote.unit_cost_usd


@dataclass(frozen=True, slots=True)
class PricingPolicy:
    payment_fee_rate: float = 0.035
    payment_fixed_fee: float = 0.40
    return_rate: float = 0.07
    operating_rate: float = 0.05
    target_margin: float = 0.45
    minimum_price: float = 9.95
    minimum_multiplier: float = 2.0

    def price(
        self,
        product_cost: float,
        inbound_shipping: float = 0,
        last_mile: float = 0,
    ) -> float:
        if min(product_cost, inbound_shipping, last_mile) < 0:
            raise ValueError("Costs cannot be negative")
        divisor = 1 - (
            self.payment_fee_rate
            + self.return_rate
            + self.operating_rate
            + self.target_margin
        )
        if divisor <= 0:
            raise ValueError("Pricing rates leave no positive selling-price divisor")
        landed = product_cost + inbound_shipping + last_mile + self.payment_fixed_fee
        raw = max(landed / divisor, product_cost * self.minimum_multiplier, self.minimum_price)
        rounded = math.ceil(raw) - 0.05
        if rounded < raw:
            rounded += 1.0
        return round(rounded, 2)
