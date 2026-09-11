"""Offline generator used for demos, tests, and safe fallback previews."""

from __future__ import annotations

import html
import re

from ..models import Listing, Product
from ..pricing import PricingPolicy, shipping_cost_for_pricing


class DeterministicListingGenerator:
    def __init__(self, policy: PricingPolicy | None = None) -> None:
        self.policy = policy or PricingPolicy()

    def generate(self, product: Product) -> Listing:
        title = re.sub(r"\s+", " ", product.title).strip()[:80]
        facts = "".join(
            f"<li><strong>{html.escape(key)}:</strong> {html.escape(value)}</li>"
            for key, value in sorted(product.facts.items())
        )
        description = (
            f"<h2>{html.escape(title)}</h2>"
            "<p>A practical product draft generated from authorized source facts.</p>"
            f"<ul>{facts or '<li>Specifications are not provided.</li>'}</ul>"
        )
        prices = {
            variant.sku: self.policy.price(
                variant.cost,
                last_mile=shipping_cost_for_pricing(product, variant),
            )
            for variant in product.variants
        }
        shipping_quotes = {
            variant.sku: variant.shipping_quote
            for variant in product.variants
            if variant.shipping_quote is not None
        }
        words = [word.lower() for word in re.findall(r"[A-Za-z0-9]+", title)]
        tags = tuple(dict.fromkeys(words))[:5]
        return Listing(
            title=title,
            description_html=description,
            category="Uncategorized",
            tags=tags,
            prices=prices,
            shipping_quotes=shipping_quotes,
        )
