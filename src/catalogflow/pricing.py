"""Deterministic pricing policies kept outside every AI prompt."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import ClassVar

from .models import Product, Variant

MAX_MONEY = 1_000_000.0
MAX_FIXED_FEE = 10_000.0
MAX_MULTIPLIER = 100.0


class PricingScheme(StrEnum):
    """Supported deterministic pricing strategies."""

    MARGIN = "margin"
    COST_MULTIPLIER = "cost_multiplier"


def _finite_number(name: str, value: object, *, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite")
    if minimum == 0 and number < 0:
        raise ValueError(f"{name} cannot be negative")
    if not minimum <= number <= maximum:
        raise ValueError(f"{name} must be between {minimum:g} and {maximum:g}")
    return number


def _round_up_to_95(raw_price: float) -> float:
    rounded = math.ceil(raw_price) - 0.05
    if rounded < raw_price:
        rounded += 1.0
    return round(rounded, 2)


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
class PriceBreakdown:
    """Auditable, UI-safe output of one deterministic price calculation."""

    scheme: str
    product_cost: float
    inbound_shipping: float
    last_mile: float
    tax_duties_per_unit: float
    payment_fixed_fee: float
    landed_cost: float
    primary_candidate: float
    minimum_multiplier_candidate: float | None
    minimum_price: float
    raw_price: float
    final_price: float

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class PricingPolicy:
    """Validated settings for deterministic, non-AI pricing."""

    payment_fee_rate: float = 0.035
    payment_fixed_fee: float = 0.40
    return_rate: float = 0.07
    operating_rate: float = 0.05
    target_margin: float = 0.45
    minimum_price: float = 9.95
    minimum_multiplier: float = 2.0
    scheme: PricingScheme | str = PricingScheme.MARGIN
    tax_duties_per_unit: float = 0.0
    cost_multiplier: float = 3.0

    FIELD_NAMES: ClassVar[frozenset[str]] = frozenset(
        {
            "payment_fee_rate",
            "payment_fixed_fee",
            "return_rate",
            "operating_rate",
            "target_margin",
            "minimum_price",
            "minimum_multiplier",
            "scheme",
            "tax_duties_per_unit",
            "cost_multiplier",
        }
    )

    def __post_init__(self) -> None:
        try:
            scheme = PricingScheme(self.scheme)
        except (TypeError, ValueError) as exc:
            choices = ", ".join(item.value for item in PricingScheme)
            raise ValueError(f"scheme must be one of: {choices}") from exc
        object.__setattr__(self, "scheme", scheme)
        for name in (
            "payment_fee_rate",
            "return_rate",
            "operating_rate",
            "target_margin",
        ):
            object.__setattr__(
                self,
                name,
                _finite_number(name, getattr(self, name), minimum=0, maximum=0.95),
            )
        for name, maximum in (
            ("payment_fixed_fee", MAX_FIXED_FEE),
            ("minimum_price", MAX_MONEY),
            ("tax_duties_per_unit", MAX_MONEY),
        ):
            object.__setattr__(
                self,
                name,
                _finite_number(name, getattr(self, name), minimum=0, maximum=maximum),
            )
        for name in ("minimum_multiplier", "cost_multiplier"):
            object.__setattr__(
                self,
                name,
                _finite_number(
                    name,
                    getattr(self, name),
                    minimum=1,
                    maximum=MAX_MULTIPLIER,
                ),
            )
        common_rates = self.payment_fee_rate + self.return_rate + self.operating_rate
        if common_rates >= 1:
            raise ValueError("Payment, return, and operating rates must total less than 1")
        if self.scheme == PricingScheme.MARGIN and common_rates + self.target_margin >= 1:
            raise ValueError("Margin-plan rates leave no positive selling-price divisor")

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> PricingPolicy:
        if not isinstance(payload, Mapping):
            raise ValueError("Pricing settings must be a JSON object")
        supplied = set(payload)
        unknown = supplied - cls.FIELD_NAMES
        missing = cls.FIELD_NAMES - supplied
        if unknown:
            raise ValueError(f"Unknown pricing fields: {', '.join(sorted(unknown))}")
        if missing:
            raise ValueError(f"Missing pricing fields: {', '.join(sorted(missing))}")
        return cls(**{name: payload[name] for name in cls.FIELD_NAMES})

    def to_dict(self) -> dict[str, object]:
        return {
            "scheme": self.scheme.value,
            "payment_fee_rate": self.payment_fee_rate,
            "payment_fixed_fee": self.payment_fixed_fee,
            "return_rate": self.return_rate,
            "operating_rate": self.operating_rate,
            "target_margin": self.target_margin,
            "minimum_price": self.minimum_price,
            "minimum_multiplier": self.minimum_multiplier,
            "tax_duties_per_unit": self.tax_duties_per_unit,
            "cost_multiplier": self.cost_multiplier,
        }

    def price(
        self,
        product_cost: float,
        inbound_shipping: float = 0,
        last_mile: float = 0,
        *,
        tax_duties_per_unit: float | None = None,
    ) -> float:
        return self.breakdown(
            product_cost,
            inbound_shipping,
            last_mile,
            tax_duties_per_unit=tax_duties_per_unit,
        ).final_price

    def breakdown(
        self,
        product_cost: float,
        inbound_shipping: float = 0,
        last_mile: float = 0,
        *,
        tax_duties_per_unit: float | None = None,
    ) -> PriceBreakdown:
        """Return every term used to calculate the final ``.95`` price."""

        costs = {
            "product_cost": product_cost,
            "inbound_shipping": inbound_shipping,
            "last_mile": last_mile,
            "tax_duties_per_unit": (
                self.tax_duties_per_unit
                if tax_duties_per_unit is None
                else tax_duties_per_unit
            ),
        }
        checked = {
            name: _finite_number(name, value, minimum=0, maximum=MAX_MONEY)
            for name, value in costs.items()
        }
        landed_cost = sum(checked.values())
        minimum_multiplier_candidate: float | None = None
        if self.scheme == PricingScheme.MARGIN:
            divisor = 1 - (
                self.payment_fee_rate
                + self.return_rate
                + self.operating_rate
                + self.target_margin
            )
            primary_candidate = (landed_cost + self.payment_fixed_fee) / divisor
            minimum_multiplier_candidate = checked["product_cost"] * self.minimum_multiplier
            raw_price = max(
                primary_candidate,
                minimum_multiplier_candidate,
                self.minimum_price,
            )
        else:
            # Shipping and estimated taxes/duties are deliberately added once, not multiplied.
            primary_candidate = (
                checked["product_cost"] * self.cost_multiplier
                + checked["inbound_shipping"]
                + checked["last_mile"]
                + checked["tax_duties_per_unit"]
                + self.payment_fixed_fee
            )
            raw_price = max(primary_candidate, self.minimum_price)
        if not math.isfinite(raw_price) or raw_price > MAX_MONEY * MAX_MULTIPLIER:
            raise ValueError("Calculated price is outside the supported finite range")
        return PriceBreakdown(
            scheme=self.scheme.value,
            product_cost=checked["product_cost"],
            inbound_shipping=checked["inbound_shipping"],
            last_mile=checked["last_mile"],
            tax_duties_per_unit=checked["tax_duties_per_unit"],
            payment_fixed_fee=self.payment_fixed_fee,
            landed_cost=landed_cost,
            primary_candidate=round(primary_candidate, 6),
            minimum_multiplier_candidate=(
                round(minimum_multiplier_candidate, 6)
                if minimum_multiplier_candidate is not None
                else None
            ),
            minimum_price=self.minimum_price,
            raw_price=round(raw_price, 6),
            final_price=_round_up_to_95(raw_price),
        )
