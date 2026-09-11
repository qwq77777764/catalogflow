"""The deep module: normalize, generate, validate, preview, then optionally draft."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from .models import ImportItemResult, ImportMode, ImportReport, ImportRequest
from .ports import ListingGenerator, SourceAdapter, StorePublisher
from .validation import validate_listing, validate_product


def import_products(
    requests: Iterable[ImportRequest],
    *,
    sources: Mapping[str, SourceAdapter],
    generator: ListingGenerator,
    mode: ImportMode = ImportMode.DRY_RUN,
    publisher: StorePublisher | None = None,
) -> ImportReport:
    """Run imports safely; store writes happen only in explicit draft mode."""

    if mode is ImportMode.DRAFT and publisher is None:
        raise ValueError("draft mode requires a StorePublisher")

    results: list[ImportItemResult] = []
    for request in requests:
        source = sources.get(request.source)
        if source is None:
            results.append(
                ImportItemResult(request, "rejected", errors=("source adapter not configured",))
            )
            continue
        try:
            product = source.fetch(request.reference)
            errors = validate_product(product)
            if errors:
                results.append(ImportItemResult(request, "rejected", errors=errors))
                continue

            listing = generator.generate(product)
            errors = validate_listing(listing, product)
            if errors:
                results.append(
                    ImportItemResult(request, "rejected", listing=listing, errors=errors)
                )
                continue

            if mode is ImportMode.DRY_RUN:
                results.append(ImportItemResult(request, "previewed", listing=listing))
            else:
                assert publisher is not None
                store_id = publisher.create_hidden_draft(product, listing)
                results.append(
                    ImportItemResult(request, "drafted", listing=listing, store_id=store_id)
                )
        except Exception as exc:  # one bad item must not abort a batch
            results.append(
                ImportItemResult(request, "failed", errors=(type(exc).__name__ + ": " + str(exc),))
            )

    return ImportReport(mode=mode, items=tuple(results))

