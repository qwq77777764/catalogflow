from catalogflow.generators import DeterministicListingGenerator
from catalogflow.models import ImportMode, ImportRequest, Product, Variant
from catalogflow.pipeline import import_products


class MemorySource:
    def fetch(self, reference: str) -> Product:
        return Product(
            source="cj",
            source_id=reference,
            title="Minimal Desk Clock",
            currency="USD",
            variants=(Variant("CLOCK-1", 8.5),),
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


def test_unknown_source_is_rejected_per_item() -> None:
    report = import_products(
        [ImportRequest("unknown", "demo")],
        sources={},
        generator=DeterministicListingGenerator(),
    )
    assert not report.ok
    assert report.items[0].status == "rejected"

