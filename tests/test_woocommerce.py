from catalogflow.exporters.woocommerce import WooCommercePublisher
from catalogflow.models import Listing, Product, Variant


def test_woocommerce_payload_is_always_hidden_draft() -> None:
    product = Product("cj", "demo", "Clock", "USD", (Variant("A", 2),))
    listing = Listing("Desk Clock", "<p>Draft</p>", "Clocks", ("clock",), {"A": 9.95})
    payload = WooCommercePublisher.build_payload(product, listing)
    assert payload["status"] == "draft"
    assert payload["catalog_visibility"] == "hidden"


def test_woocommerce_requires_https() -> None:
    try:
        WooCommercePublisher("http://shop.example", "key", "secret")
    except ValueError as exc:
        assert "HTTPS" in str(exc)
    else:
        raise AssertionError("insecure store URLs must fail")
