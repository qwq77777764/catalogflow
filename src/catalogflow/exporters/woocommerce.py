"""WooCommerce REST adapter with intentionally safe publication defaults."""

from __future__ import annotations

import base64
import json
import os
import urllib.request
from urllib.parse import urlparse

from ..models import Listing, Product


class WooCommercePublisher:
    """Create hidden drafts only; public publishing is outside this interface."""

    def __init__(self, base_url: str, consumer_key: str, consumer_secret: str) -> None:
        parsed = urlparse(base_url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("WOOCOMMERCE_URL must be an absolute HTTPS URL")
        self.base_url = base_url.rstrip("/")
        self.consumer_key = consumer_key
        self.consumer_secret = consumer_secret

    @classmethod
    def from_environment(cls) -> WooCommercePublisher:
        names = (
            "WOOCOMMERCE_URL",
            "WOOCOMMERCE_CONSUMER_KEY",
            "WOOCOMMERCE_CONSUMER_SECRET",
        )
        values = {name: os.environ.get(name, "") for name in names}
        missing = [name for name, value in values.items() if not value]
        if missing:
            raise RuntimeError("Missing required environment variables: " + ", ".join(missing))
        return cls(values[names[0]], values[names[1]], values[names[2]])

    def create_hidden_draft(self, product: Product, listing: Listing) -> str:
        payload = self.build_payload(product, listing)
        credentials = f"{self.consumer_key}:{self.consumer_secret}".encode()
        request = urllib.request.Request(  # noqa: S310 - base URL is HTTPS-validated
            f"{self.base_url}/wp-json/wc/v3/products",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": "Basic " + base64.b64encode(credentials).decode("ascii"),
                "Content-Type": "application/json",
                "User-Agent": "CatalogFlow/0.1",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
            result = json.load(response)
        return str(result["id"])

    @staticmethod
    def build_payload(product: Product, listing: Listing) -> dict[str, object]:
        lowest_price = min(listing.prices.values())
        return {
            "name": listing.title,
            "status": "draft",
            "catalog_visibility": "hidden",
            "description": listing.description_html,
            "regular_price": f"{lowest_price:.2f}",
            "categories": [{"name": listing.category}],
            "tags": [{"name": tag} for tag in listing.tags],
            "meta_data": [
                {"key": "catalogflow_source", "value": product.source},
                {"key": "catalogflow_source_id", "value": product.source_id},
            ],
        }
