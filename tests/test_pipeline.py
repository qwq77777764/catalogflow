import pytest

from catalogflow.generators import DeterministicListingGenerator
from catalogflow.models import ImportMode, ImportRequest, Product, ShippingQuote, Variant
from catalogflow.pipeline import import_products


class MemorySource:
    def fetch(self, reference: str) -> Product:
        return Product(
            source="cj",
            source_id=reference,
            title="Minimal Desk Clock",
            currency="USD",
            variants=(
                Variant(
                    "CLOCK-1",
                    8.5,
                    shipping_quote=ShippingQuote("CN", "US", 1, "Synthetic Post", 4.71),
                ),
            ),
        )


class PublisherThatMustNotRun:
    def create_hidden_draft(self, product, listing):
        raise AssertionError("dry-run crossed the store-write seam")


def test_default_mode_never_calls_store_publisher() -> None:
    report = import_products(
        [ImportRequest("cj", "demo")],
        sources={"cj": MemorySource()},
        generator=DeterministicListingGenerator(),
        publisher=PublisherThatMustNotRun(),
    )
    assert report.mode is ImportMode.DRY_RUN
    assert report.ok
    assert report.items[0].status == "previewed"
    assert report.items[0].listing is not None
    assert report.items[0].listing.prices == {"CLOCK-1": 34.95}
    assert report.items[0].listing.shipping_quotes["CLOCK-1"].method == "Synthetic Post"


def test_unknown_source_is_rejected_per_item() -> None:
    report = import_products(
        [ImportRequest("unknown", "demo")],
        sources={},
        generator=DeterministicListingGenerator(),
    )
    assert not report.ok
    assert report.items[0].status == "rejected"


def test_cj_product_without_freight_quote_is_rejected_before_pricing() -> None:
    class MissingFreightSource:
        def fetch(self, reference: str) -> Product:
            return Product("cj", reference, "Clock", "USD", (Variant("CLOCK-1", 8.5),))

    report = import_products(
        [ImportRequest("cj", "demo")],
        sources={"cj": MissingFreightSource()},
        generator=DeterministicListingGenerator(),
    )

    assert not report.ok
    assert report.items[0].status == "rejected"
    assert report.items[0].listing is None
    assert "requires a shipping quote" in report.items[0].errors[0]


def test_generator_rejects_direct_cj_pricing_without_freight_quote() -> None:
    product = Product("cj", "demo", "Clock", "USD", (Variant("CLOCK-1", 8.5),))

    with pytest.raises(ValueError, match="require a shipping quote"):
        DeterministicListingGenerator().generate(product)


def test_cj_zero_shipping_quote_is_rejected_at_validation_and_pricing() -> None:
    product = Product(
        "cj",
        "demo",
        "Clock",
        "USD",
        (
            Variant(
                "CLOCK-1",
                8.5,
                shipping_quote=ShippingQuote("CN", "US", 1, "Invalid Free Route", 0),
            ),
        ),
    )

    class ZeroFreightSource:
        def fetch(self, reference: str) -> Product:
            return product

    report = import_products(
        [ImportRequest("cj", "demo")],
        sources={"cj": ZeroFreightSource()},
        generator=DeterministicListingGenerator(),
    )
    assert not report.ok
    assert report.items[0].status == "rejected"
    assert "positive shipping cost" in report.items[0].errors[0]

    with pytest.raises(ValueError, match="positive shipping cost"):
        DeterministicListingGenerator().generate(product)
