"""The deep module: normalize, generate, validate, preview, then optionally draft."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict

from .models import ImportItemResult, ImportMode, ImportReport, ImportRequest
from .ports import ListingGenerator, SourceAdapter, StorePublisher
from .run_history import (
    HistoryRepository,
    RunRecord,
    canonical_url,
    clean_text,
    safe_error,
)
from .validation import validate_listing, validate_product


def import_products(
    requests: Iterable[ImportRequest],
    *,
    sources: Mapping[str, SourceAdapter],
    generator: ListingGenerator,
    mode: ImportMode = ImportMode.DRY_RUN,
    publisher: StorePublisher | None = None,
    history: HistoryRepository | None = None,
) -> ImportReport:
    """Run imports safely; store writes happen only in explicit draft mode."""

    if mode is ImportMode.DRAFT and publisher is None:
        raise ValueError("draft mode requires a StorePublisher")

    run = history.create_run(mode) if history is not None else None
    results: list[ImportItemResult] = []
    interrupted = True
    try:
        for request in requests:
            item = (run.start_item(source=request.source, source_url=request.reference)
                    if run else {})
            result = _import_one(
                request, sources=sources, generator=generator, mode=mode,
                publisher=publisher, history=history, run=run, item=item,
            )
            if run:
                item.update(
                    status=result.status, errors=list(result.errors), store_id=result.store_id,
                    store_url=result.store_url, artifact_path=result.artifact_path,
                )
                # A disk failure stops the batch; existing reservations remain fail-closed.
                run.finish_item(item)
            results.append(result)
        interrupted = False
    finally:
        if run:
            run.finish(interrupted=interrupted)
    return ImportReport(
        mode=mode, items=tuple(results), run_id=run.run_id if run else "",
        report_path=str(run.directory / "report.txt") if run else "",
    )


def _import_one(request, *, sources, generator, mode, publisher, history, run: RunRecord | None,
                item: dict) -> ImportItemResult:
    original_reference = request.reference
    if "://" in request.reference:
        request = ImportRequest(request.source, canonical_url(request.reference))
    source = sources.get(request.source)
    if source is None:
        return ImportItemResult(request, "rejected", errors=("source adapter not configured",))
    reserved = False
    identity = ""
    product = None
    listing = None
    artifact_path = ""
    store_id = None
    store_url = ""
    try:
        if mode is ImportMode.DRAFT and history:
            identity = getattr(publisher, "store_identity", "")
            if not isinstance(identity, str) or not identity.strip():
                raise ValueError("Draft history requires a store identity")
        product = source.fetch(original_reference)
        item.update(
            source_id=clean_text(product.source_id, 200), title=clean_text(product.title, 300),
            source_url=canonical_url(original_reference) or canonical_url(product.source_url),
        )
        if run:
            run.record_product(item)
        errors = validate_product(product)
        if product.source != request.source:
            errors = (*errors, "source does not match the requested adapter")
        if errors:
            return ImportItemResult(request, "rejected", errors=errors)
        if mode is ImportMode.DRAFT and history:
            existing = history.lookup(identity, product.source, product.source_id)
            if existing is not None:
                return ImportItemResult(
                    request, "skipped_duplicate" if existing.status == "duplicate"
                    else "blocked_incomplete", store_id=existing.store_id,
                    store_url=existing.store_url,
                    errors=() if existing.status == "duplicate" else ("review_required",),
                )
        listing = generator.generate(product)
        errors = validate_listing(listing, product)
        if errors:
            return ImportItemResult(request, "rejected", listing=listing, errors=errors)
        item["title"] = clean_text(listing.title, 300)
        if run:
            artifact_path = run.write_artifact(item["index"], {
                "source": product.source, "source_id": item["source_id"],
                "source_url": item["source_url"], "listing": asdict(listing),
            })
        if mode is ImportMode.DRY_RUN:
            return ImportItemResult(
                request, "previewed", listing=listing, artifact_path=artifact_path,
            )
        assert publisher is not None
        if history and run:
            reservation = history.reserve(identity, product.source, product.source_id, run.run_id)
            if reservation.status != "reserved":
                return ImportItemResult(
                    request, "skipped_duplicate" if reservation.status == "duplicate"
                    else "blocked_incomplete", listing=listing, store_id=reservation.store_id,
                    store_url=reservation.store_url, artifact_path=artifact_path,
                    errors=() if reservation.status == "duplicate" else ("review_required",),
                )
            reserved = True
        store_id = str(publisher.create_hidden_draft(product, listing))
        url_builder = getattr(publisher, "product_url", None)
        store_url = (canonical_url(url_builder(store_id), store=True)
                     if callable(url_builder) else "")
        if history and run:
            history.record_draft(
                identity, product.source, product.source_id, run.run_id,
                completed=True, store_id=store_id, store_url=store_url,
            )
            reserved = False
        return ImportItemResult(
            request, "drafted", listing=listing, store_id=store_id,
            store_url=store_url, artifact_path=artifact_path,
        )
    except Exception as exc:  # one failed item must not reveal raw response/credential details
        store_id = clean_text(getattr(exc, "store_id", None), 100) or store_id
        store_url = canonical_url(getattr(exc, "store_url", ""), store=True) or store_url
        if reserved and history and run and product:
            # Only the concrete exporter can guarantee that preflight failed before writing.
            from .exporters.woocommerce import WooCommerceDraftError

            if (isinstance(exc, WooCommerceDraftError)
                    and getattr(exc, "write_started", True) is False and store_id is None):
                history.release_unwritten(identity, product.source, product.source_id, run.run_id)
            else:
                history.record_draft(
                    identity, product.source, product.source_id, run.run_id,
                    completed=False, store_id=store_id, store_url=store_url,
                )
        return ImportItemResult(
            request, "failed", listing=listing, errors=(safe_error(exc),),
            store_id=store_id, store_url=store_url, artifact_path=artifact_path,
        )
