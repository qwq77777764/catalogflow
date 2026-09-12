import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pytest

from catalogflow.exporters.woocommerce import WooCommerceDraftError
from catalogflow.generators import DeterministicListingGenerator
from catalogflow.models import ImportMode, ImportRequest, Product, Variant
from catalogflow.pipeline import import_products
from catalogflow.run_history import HistoryRepository, canonical_url, safe_error


class Source:
    def fetch(self, reference):
        return Product(
            "alibaba-manual", "synthetic-101", "Cotton Basket", "USD",
            (Variant("BASKET-S", 4),), source_url="https://www.example.com/item/101",
        )


class Publisher:
    store_identity = "synthetic-store-one"

    def __init__(self):
        self.calls = 0

    def create_hidden_draft(self, product, listing):
        self.calls += 1
        return "123"

    def product_url(self, identifier):
        return f"https://store.example.com/wp-admin/post.php?post={identifier}&action=edit"


def run(history, publisher=None, *, mode=ImportMode.DRY_RUN, source=None):
    return import_products(
        [ImportRequest("alibaba-manual", "synthetic.json")],
        sources={"alibaba-manual": source or Source()},
        generator=DeterministicListingGenerator(), history=history,
        publisher=publisher, mode=mode,
    )


def test_reports_are_lazy_immutable_timestamped_and_preview_can_repeat(tmp_path):
    history = HistoryRepository(tmp_path / "config")
    assert history.recent() == []
    assert not history.config_directory.exists()
    first = run(history)
    first_text = Path(first.report_path).read_bytes()
    second = run(history)
    assert first.run_id != second.run_id
    assert Path(first.report_path).read_bytes() == first_text
    assert not history.registry_path.exists()
    assert first_text.decode("utf-8").startswith("CatalogFlow 工作记录")
    document = history.read(first.run_id)
    assert document["counts"] == {"previewed": 1}
    assert document["status"] == "completed"
    for value in (document["started_at"], document["finished_at"],
                  document["items"][0]["started_at"], document["items"][0]["finished_at"]):
        assert datetime.fromisoformat(value).utcoffset().total_seconds() == 0
    item = document["items"][0]
    assert item["source_id"] == "synthetic-101"
    assert item["source_url"] == "https://www.example.com/item/101"
    assert Path(item["artifact_path"]).exists()
    assert "description_html" not in json.dumps(document)
    assert history.recent()[0]["run_id"] == second.run_id
    assert history.recent()[0]["item_count"] == 1
    assert "本地预览成功" in history.report_text(first.run_id)
    with pytest.raises(FileExistsError):
        from catalogflow.run_history import RunRecord
        RunRecord(history, first.run_id).finish()


def test_drafts_deduplicate_per_store_without_blocking_preview(tmp_path):
    history = HistoryRepository(tmp_path)
    publisher = Publisher()
    first = run(history, publisher, mode=ImportMode.DRAFT)
    second = run(history, publisher, mode=ImportMode.DRAFT)
    assert first.items[0].status == "drafted"
    assert second.items[0].status == "skipped_duplicate"
    assert second.ok
    assert second.items[0].store_id == "123"
    assert "post=123&action=edit" in second.items[0].store_url
    assert publisher.calls == 1
    assert run(history).items[0].status == "previewed"
    publisher.store_identity = "synthetic-store-two"
    assert run(history, publisher, mode=ImportMode.DRAFT).items[0].status == "drafted"
    assert publisher.calls == 2


def test_atomic_reservation_allows_only_one_competing_writer(tmp_path):
    history = HistoryRepository(tmp_path)
    runs = [history.create_run("draft") for _ in range(8)]
    with ThreadPoolExecutor(max_workers=8) as executor:
        reservations = list(executor.map(
            lambda record: history.reserve("store", "cj", "101", record.run_id), runs,
        ))
    assert [item.status for item in reservations].count("reserved") == 1
    assert [item.status for item in reservations].count("blocked") == 7


def test_uncertain_parent_is_preserved_and_blocks_automatic_retry(tmp_path):
    class PartialPublisher(Publisher):
        def create_hidden_draft(self, product, listing):
            self.calls += 1
            raise WooCommerceDraftError(
                "woocommerce_draft_failed", store_id="123", store_url=self.product_url("123"),
            )

    history = HistoryRepository(tmp_path)
    publisher = PartialPublisher()
    first = run(history, publisher, mode=ImportMode.DRAFT)
    second = run(history, publisher, mode=ImportMode.DRAFT)
    assert first.items[0].status == "failed"
    assert first.items[0].store_id == "123"
    assert second.items[0].status == "blocked_incomplete"
    assert second.items[0].store_id == "123"
    assert publisher.calls == 1
    assert not second.ok


def test_known_pure_preflight_failure_can_be_fixed_and_retried(tmp_path):
    class PreflightPublisher(Publisher):
        def create_hidden_draft(self, product, listing):
            self.calls += 1
            if self.calls == 1:
                raise WooCommerceDraftError(
                    "wordpress_media_credentials_required", write_started=False,
                )
            return "123"

    history = HistoryRepository(tmp_path)
    publisher = PreflightPublisher()
    first = run(history, publisher, mode=ImportMode.DRAFT)
    assert first.items[0].status == "failed"
    assert "需要配置图片上传凭据" in history.report_text(first.run_id)
    assert run(history, publisher, mode=ImportMode.DRAFT).items[0].status == "drafted"
    assert publisher.calls == 2


def test_unknown_error_cannot_claim_no_write_or_leak_credentials(tmp_path):
    class UnknownFailure(RuntimeError):
        write_started = False

    class FailedPublisher(Publisher):
        def create_hidden_draft(self, product, listing):
            self.calls += 1
            raise UnknownFailure("Bearer synthetic-secret-value")

    history = HistoryRepository(tmp_path)
    publisher = FailedPublisher()
    first = run(history, publisher, mode=ImportMode.DRAFT)
    assert "synthetic-secret-value" not in history.report_text(first.run_id)
    assert "synthetic-secret-value" not in json.dumps(first.to_dict())
    assert run(history, publisher, mode=ImportMode.DRAFT).items[0].status == "blocked_incomplete"
    assert publisher.calls == 1


def test_interruption_retains_item_source_and_reservation(tmp_path):
    class InterruptedPublisher(Publisher):
        def create_hidden_draft(self, product, listing):
            raise KeyboardInterrupt

    history = HistoryRepository(tmp_path)
    with pytest.raises(KeyboardInterrupt):
        run(history, InterruptedPublisher(), mode=ImportMode.DRAFT)
    summary = history.recent()[0]
    assert summary["status"] == "interrupted"
    item = history.read(summary["run_id"])["items"][0]
    assert item["source_id"] == "synthetic-101"
    assert item["status"] == "interrupted"
    assert Path(item["artifact_path"]).exists()
    assert run(history, Publisher(), mode=ImportMode.DRAFT).items[0].status == "blocked_incomplete"


def test_archive_unwritable_prevents_external_source_or_store_work(tmp_path, monkeypatch):
    def fail_write(*args, **kwargs):
        raise PermissionError("synthetic private path")

    monkeypatch.setattr("catalogflow.run_history._write_once", fail_write)
    publisher = Publisher()
    with pytest.raises(PermissionError):
        run(HistoryRepository(tmp_path), publisher, mode=ImportMode.DRAFT)
    assert publisher.calls == 0


def test_missing_publisher_identity_fails_before_store_write(tmp_path):
    publisher = Publisher()
    publisher.store_identity = ""
    report = run(HistoryRepository(tmp_path), publisher, mode=ImportMode.DRAFT)
    assert report.items[0].status == "failed"
    assert publisher.calls == 0


@pytest.mark.parametrize("reference", ["../secret", "a/b", "C:/secret", "", ".."])
def test_read_rejects_traversal_and_invalid_ids(tmp_path, reference):
    with pytest.raises(ValueError):
        HistoryRepository(tmp_path).read(reference)


def test_invalid_local_item_is_not_returned_to_dashboard(tmp_path):
    history = HistoryRepository(tmp_path)
    report = run(history)
    path = history.directory / report.run_id / "item-000001.json"
    path.write_text('{"status": []}', encoding="utf-8")
    with pytest.raises(RuntimeError, match="invalid"):
        history.read(report.run_id)


def test_source_urls_drop_credentials_session_parameters_and_local_targets(tmp_path):
    assert canonical_url("https://user:password@example.com/item/1") == ""
    for url in ("http://127.0.0.1/", "http://127.1/", "http://localhost/", "file:///secret"):
        assert canonical_url(url) == ""
    assert canonical_url("https://example.com/item/1?token=private#secret") == (
        "https://example.com/item/1"
    )

    class UrlSource(Source):
        def fetch(self, reference):
            return replace(super().fetch(reference), source_url="https://example.com/other")

    history = HistoryRepository(tmp_path)
    report = import_products(
        [ImportRequest("alibaba-manual", "https://example.com/original?token=private#secret")],
        sources={"alibaba-manual": UrlSource()}, generator=DeterministicListingGenerator(),
        history=history,
    )
    assert history.read(report.run_id)["items"][0]["source_url"] == (
        "https://example.com/original"
    )
    assert "private" not in json.dumps(report.to_dict())


def test_exception_class_names_and_unknown_codes_cannot_be_used_as_error_payloads():
    secret_exception = type("SyntheticPrivateCredential", (RuntimeError,), {})
    error = secret_exception("sensitive response")
    error.code = "synthetic-secret"
    assert safe_error(error) == "operation_failed"


def test_cj_product_query_identifier_survives_without_session_parameters():
    url = "https://cjdropshipping.com/product?pid=1442332573555625984&token=private#secret"
    assert canonical_url(url) == (
        "https://cjdropshipping.com/product?pid=1442332573555625984"
    )
    assert canonical_url("https://cjdropshipping.com/product?pid=private") == (
        "https://cjdropshipping.com/product"
    )


def test_known_draft_duplicate_skips_ai_generation(tmp_path):
    history = HistoryRepository(tmp_path)
    publisher = Publisher()
    assert run(history, publisher, mode=ImportMode.DRAFT).ok

    class GeneratorThatMustNotRun:
        def generate(self, product):
            raise AssertionError("Known duplicates must not spend AI usage")

    report = import_products(
        [ImportRequest("alibaba-manual", "synthetic.json")],
        sources={"alibaba-manual": Source()}, generator=GeneratorThatMustNotRun(),
        history=history, publisher=publisher, mode=ImportMode.DRAFT,
    )
    assert report.items[0].status == "skipped_duplicate"
    assert report.items[0].listing is None
    assert publisher.calls == 1


def test_source_failures_are_recorded_without_stopping_other_items(tmp_path):
    class SometimesSource(Source):
        def fetch(self, reference):
            if reference == "bad":
                raise ValueError("private-synthetic-provider-response")
            return super().fetch(reference)

    history = HistoryRepository(tmp_path)
    report = import_products(
        [ImportRequest("alibaba-manual", "bad"), ImportRequest("alibaba-manual", "good")],
        sources={"alibaba-manual": SometimesSource()}, generator=DeterministicListingGenerator(),
        history=history,
    )
    assert [item.status for item in report.items] == ["failed", "previewed"]
    assert "private-synthetic-provider-response" not in history.report_text(report.run_id)


def test_report_item_symlink_cannot_escape_run_directory(tmp_path):
    history = HistoryRepository(tmp_path / "config")
    report = run(history)
    external = tmp_path / "outside.json"
    external.write_text('{"synthetic": "outside"}', encoding="utf-8")
    path = history.directory / report.run_id / "item-000001.json"
    path.unlink()
    try:
        path.symlink_to(external)
    except OSError:
        pytest.skip("Creating a symlink requires OS privileges on this host")
    with pytest.raises(RuntimeError, match="outside"):
        history.read(report.run_id)
