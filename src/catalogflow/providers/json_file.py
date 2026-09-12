"""Authorized manual JSON input for CJ or Alibaba product facts."""

from __future__ import annotations

import json
from pathlib import Path

from ..models import Product, ShippingQuote, Variant


class JsonFileSource:
    """Read normalized, user-provided data without scraping a supplier site."""

    def __init__(self, source: str) -> None:
        self.source = source

    def fetch(self, reference: str) -> Product:
        payload = json.loads(Path(reference).read_text(encoding="utf-8"))
        return product_from_payload(payload, source=self.source)


def product_from_payload(payload: dict[str, object], *, source: str) -> Product:
    """Parse normalized JSON supplied by a file reader or a bounded upload interface."""
    variants = tuple(
        Variant(
            sku=str(row["sku"]),
            cost=float(row["cost"]),
            attributes={str(k): str(v) for k, v in row.get("attributes", {}).items()},
            shipping_quote=_shipping_quote(row.get("shipping_quote")),
            image_url=str(row.get("image_url", "")),
        )
        for row in payload["variants"]
    )
    return Product(
        source=source,
        source_id=str(payload["source_id"]),
        title=str(payload["title"]),
        currency=str(payload.get("currency", "USD")),
        variants=variants,
        images=tuple(str(value) for value in payload.get("images", [])),
        facts={str(k): str(v) for k, v in payload.get("facts", {}).items()},
        source_url=str(payload.get("source_url", "")),
    )


def _shipping_quote(value: object) -> ShippingQuote | None:
    if not isinstance(value, dict):
        return None
    return ShippingQuote(
        origin_country=str(value["origin_country"]),
        destination_country=str(value["destination_country"]),
        quantity=int(value["quantity"]),
        method=str(value["method"]),
        total_cost_usd=float(value["total_cost_usd"]),
        estimated_days=str(value.get("estimated_days", "")),
    )
