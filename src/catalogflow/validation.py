"""Deterministic listing and source validation."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from .models import Listing, Product

_BANNED_PUBLIC_TERMS = {
    "alibaba",
    "1688",
    "cj dropshipping",
    "cjdropshipping",
    "dropshipping",
    "supplier",
    "wholesale",
}
_PRIVATE_HOSTS = {"localhost", "127.0.0.1", "::1"}


def validate_product(product: Product) -> tuple[str, ...]:
    errors: list[str] = []
    if product.source not in {"cj", "alibaba-manual"}:
        errors.append(f"Unsupported source: {product.source}")
    if not product.source_id.strip():
        errors.append("source_id is required")
    if not product.title.strip():
        errors.append("title is required")
    if not product.variants:
        errors.append("at least one variant is required")
    if any(variant.cost < 0 for variant in product.variants):
        errors.append("variant costs cannot be negative")
    return tuple(errors)


def validate_listing(listing: Listing, product: Product) -> tuple[str, ...]:
    errors: list[str] = []
    if not listing.title.strip() or len(listing.title) > 80:
        errors.append("listing title must contain 1-80 characters")
    public_text = " ".join((listing.title, listing.description_html, *listing.tags)).lower()
    for term in sorted(_BANNED_PUBLIC_TERMS):
        if re.search(rf"\b{re.escape(term)}\b", public_text):
            errors.append(f"public listing contains a source-disclosure term: {term}")
    expected_skus = {variant.sku for variant in product.variants}
    if set(listing.prices) != expected_skus:
        errors.append("listing prices must match the product variant SKUs")
    return tuple(errors)


def is_public_http_url(value: str) -> bool:
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    return parsed.scheme in {"http", "https"} and bool(host) and host not in _PRIVATE_HOSTS

