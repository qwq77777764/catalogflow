from catalogflow.models import Listing, Product, Variant
from catalogflow.validation import is_public_http_url, validate_listing


def test_source_disclosure_terms_are_rejected() -> None:
    product = Product("cj", "1", "Clock", "USD", (Variant("A", 1),))
    listing = Listing("Wholesale Clock", "<p>Nice.</p>", "Clocks", (), {"A": 9.95})
    assert validate_listing(listing, product)


def test_localhost_url_is_not_public() -> None:
    assert not is_public_http_url("http://127.0.0.1/internal")
    assert is_public_http_url("https://example.com/image.jpg")

