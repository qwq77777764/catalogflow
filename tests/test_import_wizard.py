import copy
import json
import threading
import time
from dataclasses import replace

import pytest

from catalogflow import import_wizard as wizard_module
from catalogflow.configuration import MemorySecretStore, ProfileRepository
from catalogflow.exporters.woocommerce import WooCommerceDraftError, WooCommercePublisher
from catalogflow.generators import DeterministicListingGenerator
from catalogflow.import_wizard import ImportWizard, ImportWizardError
from catalogflow.models import Product, ShippingQuote, Variant
from catalogflow.pricing import PricingPolicy
from catalogflow.pricing_settings import PricingSettingsRepository
from catalogflow.providers.json_file import JsonFileSource, product_from_payload
from catalogflow.run_history import HistoryRepository


def manual_input():
    return {
        "source_id": "synthetic-one", "title": "Minimal Desk Clock", "currency": "USD",
        "variants": [{"sku": "DEMO-OAK", "cost": 8.5, "attributes": {"Finish": "Oak"}}],
        "images": [], "facts": {"Material": "Wood"},
        "source_url": "https://www.example.com/product/clock?tracking=discard",
    }


def request(**kwargs):
    return {
        "source": "alibaba-manual", "source_input": manual_input(),
        "source_profile_id": None, "generator": "deterministic", "ai_profile_id": None,
        "store_profile_id": None, **kwargs,
    }


def wait_job(wizard):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        value = wizard.current()
        if value["status"] not in {"running", "drafting"}:
            return value
        time.sleep(0.005)
    pytest.fail("wizard task did not finish")


def confirmation(job, **edits):
    listing = job["preview"]["listing"]
    return {
        "revision": job["revision"], "confirm_hidden_draft": True,
        "edits": {key: copy.deepcopy(listing[key]) for key in (
            "title", "description_html", "category", "tags",
        )} | edits,
    }


@pytest.fixture
def setup(tmp_path, monkeypatch):
    repository = ProfileRepository(tmp_path)
    secret_store = MemorySecretStore()
    pricing = PricingSettingsRepository(tmp_path)
    history = HistoryRepository(tmp_path)
    calls = []

    class Publisher(WooCommercePublisher):
        def create_hidden_draft(self, product, listing):
            calls.append((copy.deepcopy(product), copy.deepcopy(listing), self.base_url))
            return "123"

    monkeypatch.setattr(wizard_module, "WooCommercePublisher", Publisher)
    store = repository.save(
        provider="woocommerce", label="Synthetic store", notes="",
        values={"url": "https://store.example"},
        secrets={"consumer_key": "synthetic-key", "consumer_secret": "synthetic-secret"},
        secret_store=secret_store, is_default=True,
    )
    wizard = ImportWizard(repository, secret_store, pricing, history)
    return wizard, store, calls


def test_preview_does_not_write_store_and_null_store_never_uses_default(setup):
    wizard, store, calls = setup
    started = wizard.start_preview(request())
    job = wait_job(wizard)
    assert job["id"] == started["id"]
    assert job["status"] == "ready"
    assert job["preview"]["store"] is None
    assert job["preview"]["product"]["source_url"] == "https://www.example.com/product/clock"
    assert job["preview"]["product"]["variants"][0]["shipping_cost"] == 0
    assert calls == []
    assert wizard.history.read(job["report_run_id"])["items"][0]["status"] == "previewed"
    with pytest.raises(ImportWizardError, match="import_store_required"):
        wizard.start_draft(job["id"], confirmation(job))


def test_deterministic_manual_preview_reads_no_secret_store(setup, monkeypatch):
    wizard, store, calls = setup

    def no_secret_reads(*args):
        raise AssertionError("a manual preview requested an unrelated credential")

    monkeypatch.setattr(wizard.secret_store, "get", no_secret_reads)
    wizard.start_preview(request())
    assert wait_job(wizard)["status"] == "ready"
    assert calls == []


def test_confirm_uses_frozen_product_price_store_and_no_second_ai_call(setup, monkeypatch):
    wizard, store, calls = setup
    generator_calls = []

    class Generator(DeterministicListingGenerator):
        def __init__(self, **kwargs):
            assert kwargs["command"] == "" and kwargs["model"] == ""
            super().__init__(policy=kwargs["policy"])

        def generate(self, product):
            generator_calls.append(product)
            return super().generate(product)

    monkeypatch.setattr(wizard_module, "CodexCliListingGenerator", Generator)
    wizard.start_preview(request(generator="codex", store_profile_id=store.id))
    job = wait_job(wizard)
    old_prices = copy.deepcopy(job["preview"]["listing"]["prices_by_sku"])
    wizard.pricing_repository.save(PricingPolicy(minimum_price=999))
    wizard.repository.save(
        provider="woocommerce", label="Changed store", notes="",
        values={"url": "https://different.example"}, secrets={},
        secret_store=wizard.secret_store, profile_id=store.id,
    )
    # A browser copy cannot change the server-owned Product or prices.
    job["preview"]["product"]["variants"][0]["cost"] = 999
    job["preview"]["listing"]["prices_by_sku"]["DEMO-OAK"] = 1
    body = confirmation(job, title="Reviewed Desk Clock", category="Clocks")
    wizard.start_draft(job["id"], body)
    finished = wait_job(wizard)
    assert finished["status"] == "completed"
    assert finished["result"]["status"] == "drafted"
    assert len(generator_calls) == len(calls) == 1
    product, listing, target = calls[0]
    assert product.variants[0].cost == 8.5
    assert listing.prices == old_prices
    assert listing.title == "Reviewed Desk Clock"
    assert target == "https://store.example"
    assert wizard.start_draft(job["id"], body) == finished
    assert len(calls) == 1
    assert "synthetic-secret" not in json.dumps(finished)


def test_busy_preview_concurrent_confirmation_and_atomic_shutdown(setup, monkeypatch):
    wizard, store, calls = setup
    entered, release = threading.Event(), threading.Event()

    class Generator(DeterministicListingGenerator):
        def generate(self, product):
            entered.set()
            assert release.wait(5)
            return super().generate(product)

    monkeypatch.setattr(wizard_module, "DeterministicListingGenerator", Generator)
    wizard.start_preview(request(store_profile_id=store.id))
    try:
        assert entered.wait(5)
        assert wizard.busy
        assert wizard.prepare_shutdown() is False
        with pytest.raises(ImportWizardError, match="import_busy"):
            wizard.start_preview(request())
    finally:
        release.set()
    job = wait_job(wizard)
    body = confirmation(job)
    errors = []

    def confirm():
        try:
            wizard.start_draft(job["id"], body)
        except Exception as exc:
            errors.append(exc)

    workers = [threading.Thread(target=confirm) for _ in range(5)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(5)
    assert wait_job(wizard)["result"]["status"] == "drafted"
    assert errors == [] and len(calls) == 1
    assert wizard.prepare_shutdown() is True
    with pytest.raises(ImportWizardError, match="import_not_ready"):
        wizard.start_preview(request())
    with pytest.raises(ImportWizardError, match="import_not_ready"):
        wizard.start_draft(job["id"], body)


@pytest.mark.parametrize("change,code", [
    ({"revision": "not-the-revision"}, "import_revision_mismatch"),
    ({"confirm_hidden_draft": False}, "import_confirmation_required"),
    ({"confirm_hidden_draft": 1}, "import_confirmation_required"),
    ({"store_profile_id": "forged"}, "import_invalid_request"),
    ({"edits": {"prices": {"DEMO-OAK": 1}}}, "import_invalid_edits"),
])
def test_confirmation_rejects_invalid_envelope(setup, change, code):
    wizard, store, calls = setup
    wizard.start_preview(request(store_profile_id=store.id))
    job = wait_job(wizard)
    with pytest.raises(ImportWizardError, match=code):
        wizard.start_draft(job["id"], confirmation(job) | change)
    assert wizard.current()["status"] == "ready"
    assert calls == []


@pytest.mark.parametrize("markup", [
    "<script>alert(1)</script>", "<iframe></iframe>", "<p onclick='alert(1)'>Text</p>",
    "<a href='javascript:alert(1)'>Text</a>", "<style>p{color:red}</style>",
    "<p>Unclosed", "<p><b>Bad</p></b>", "<!--hidden--><p>Text</p>",
    "<!DOCTYPE html><p>Text</p>", "<p style='color:red'>Text</p>",
])
def test_unsafe_or_malformed_html_cannot_cross_confirmation(setup, markup):
    wizard, store, calls = setup
    wizard.start_preview(request(store_profile_id=store.id))
    job = wait_job(wizard)
    with pytest.raises(ImportWizardError, match="import_invalid_edits"):
        wizard.start_draft(job["id"], confirmation(job, description_html=markup))
    assert calls == []


def test_edit_validation_rejects_disclosure_and_invalid_title_types(setup):
    wizard, store, calls = setup
    wizard.start_preview(request(store_profile_id=store.id))
    job = wait_job(wizard)
    for title in (None, "", "x" * 81, "Supplier Wholesale Clock"):
        with pytest.raises(ImportWizardError, match="import_invalid_edits"):
            wizard.start_draft(job["id"], confirmation(job, title=title))
    assert calls == []


def test_wrong_provider_and_configuration_errors_are_reported_without_secrets(setup):
    wizard, store, calls = setup
    wizard.start_preview(request(generator="codex", ai_profile_id=store.id))
    job = wait_job(wizard)
    assert job["status"] == "failed"
    assert job["error"] == "import_profile_invalid"
    assert job["report_run_id"]
    assert calls == []
    assert "synthetic-secret" not in json.dumps(job)
    with pytest.raises(ImportWizardError, match="import_profile_invalid"):
        wizard.start_preview(request(store_profile_id="Synthetic store"))


def test_broken_pricing_and_report_storage_fail_closed(setup, monkeypatch):
    wizard, store, calls = setup

    def broken():
        raise RuntimeError("sensitive-raw-credentials")

    monkeypatch.setattr(wizard.pricing_repository, "load", broken)
    wizard.start_preview(request(store_profile_id=store.id))
    job = wait_job(wizard)
    assert job["error"] == "import_configuration_failed"
    assert "sensitive-raw-credentials" not in json.dumps(job)
    monkeypatch.setattr(wizard.history, "create_run", lambda *_: broken())
    wizard.start_preview(request())
    assert wait_job(wizard)["error"] == "import_reports_unavailable"
    assert calls == []


def test_failure_to_create_draft_report_prevents_any_store_write(setup, monkeypatch):
    wizard, store, calls = setup
    wizard.start_preview(request(store_profile_id=store.id))
    job = wait_job(wizard)

    def unavailable(*args):
        raise OSError("private-report-path")

    monkeypatch.setattr(wizard.history, "create_run", unavailable)
    wizard.start_draft(job["id"], confirmation(job))
    finished = wait_job(wizard)
    assert finished["error"] == "import_reports_unavailable"
    assert calls == []
    assert "private-report-path" not in json.dumps(finished)


def test_unwritten_preflight_failure_releases_reservation_for_new_preview(setup, monkeypatch):
    wizard, store, calls = setup
    original = wizard_module.WooCommercePublisher.create_hidden_draft

    def fail(self, product, listing):
        raise WooCommerceDraftError("wordpress_media_credentials_required", write_started=False)

    monkeypatch.setattr(wizard_module.WooCommercePublisher, "create_hidden_draft", fail)
    wizard.start_preview(request(store_profile_id=store.id))
    job = wait_job(wizard)
    wizard.start_draft(job["id"], confirmation(job))
    assert wait_job(wizard)["result"]["status"] == "failed"
    monkeypatch.setattr(wizard_module.WooCommercePublisher, "create_hidden_draft", original)
    wizard.start_preview(request(store_profile_id=store.id))
    job = wait_job(wizard)
    wizard.start_draft(job["id"], confirmation(job))
    assert wait_job(wizard)["result"]["status"] == "drafted"
    assert len(calls) == 1


def test_partial_store_failure_keeps_reservation_and_repeat_job_skips_ai_on_confirm(
    setup, monkeypatch,
):
    wizard, store, calls = setup
    publish_attempts = []

    def partial(self, product, listing):
        publish_attempts.append(product)
        raise WooCommerceDraftError("woocommerce_draft_failed", store_id="456")

    monkeypatch.setattr(wizard_module.WooCommercePublisher, "create_hidden_draft", partial)
    wizard.start_preview(request(store_profile_id=store.id))
    preview = wait_job(wizard)
    body = confirmation(preview)
    wizard.start_draft(preview["id"], body)
    failed = wait_job(wizard)
    assert failed["status"] == "failed" and failed["result"]["store_id"] == "456"
    assert failed["result"]["errors"] == ["woocommerce_draft_failed"]
    wizard.start_draft(preview["id"], body)
    assert len(publish_attempts) == 1
    wizard.start_preview(request(store_profile_id=store.id))
    second = wait_job(wizard)
    wizard.start_draft(second["id"], confirmation(second))
    assert wait_job(wizard)["result"]["status"] == "blocked_incomplete"
    assert len(publish_attempts) == 1


def test_completed_source_is_skipped_by_draft_pipeline(setup):
    wizard, store, calls = setup
    for expected in ("drafted", "skipped_duplicate"):
        wizard.start_preview(request(store_profile_id=store.id))
        job = wait_job(wizard)
        wizard.start_draft(job["id"], confirmation(job))
        assert wait_job(wizard)["result"]["status"] == expected
    assert len(calls) == 1


def test_new_job_invalidates_old_identifier(setup):
    wizard, store, calls = setup
    wizard.start_preview(request())
    first = wait_job(wizard)
    wizard.start_preview(request())
    wait_job(wizard)
    with pytest.raises(ImportWizardError) as exc:
        wizard.get(first["id"])
    assert exc.value.status == 404


@pytest.mark.parametrize("change", [
    {"currency": "CNY"}, {"variants": []},
    {"variants": [{"sku": "A", "cost": True}]},
    {"variants": [{"sku": "A", "cost": -1}]},
    {"variants": [{"sku": "A", "cost": 1000001}]},
    {"variants": [{"sku": "A", "cost": 1}, {"sku": "A", "cost": 2}]},
    {"images": ["http://images.example/1.jpg"]},
    {"images": ["https://127.0.0.1/1.jpg"]},
    {"images": ["https://user:password@images.example/1.jpg"]},
    {"images": [f"https://images.example/{index}.jpg" for index in range(21)]},
    {"unexpected": "field"},
])
def test_manual_json_validation_limits(setup, change):
    wizard, store, calls = setup
    with pytest.raises(ImportWizardError, match="import_invalid_product"):
        wizard.start_preview(request(source_input=manual_input() | change))
    assert wizard.current() is None and calls == []


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_non_finite_json_rejected_before_background_work(setup, value):
    wizard, store, calls = setup
    data = manual_input()
    data["variants"][0]["cost"] = value
    with pytest.raises(ImportWizardError):
        wizard.start_preview(request(source_input=data))


@pytest.mark.parametrize("reference", [
    "https://evil.example/product-p-123456789012.html",
    "http://www.cjdropshipping.com/product-p-123456789012.html",
    "https://user:password@www.cjdropshipping.com/product-p-123456789012.html",
    "https://www.cjdropshipping.com:8443/product-p-123456789012.html",
    "C:\\private\\product.json", "not-a-pid",
])
def test_cj_reference_rejects_unapproved_url_forms(setup, reference):
    wizard, store, calls = setup
    with pytest.raises(ImportWizardError, match="import_invalid_source"):
        wizard.start_preview(request(source="cj", source_input=reference))


def test_cj_source_fetch_and_generator_only_run_in_preview(setup, monkeypatch):
    wizard, store, calls = setup
    profile = wizard.repository.save(
        provider="cj", label="Synthetic CJ", notes="", values={},
        secrets={"api_key": "synthetic-cj-key"}, secret_store=wizard.secret_store,
    )
    fetches = []

    class CjSource:
        def __init__(self, key, **kwargs):
            assert key == "synthetic-cj-key"

        def fetch(self, reference):
            fetches.append(reference)
            return Product("cj", "123456789012", "Desk Clock", "USD", (
                Variant("A", 8.5, shipping_quote=ShippingQuote("CN", "US", 2, "Post", 10)),
            ))

    monkeypatch.setattr(wizard_module, "CjApiSource", CjSource)
    wizard.start_preview(request(source="cj", source_input="123456789012",
                                 source_profile_id=profile.id, store_profile_id=store.id))
    job = wait_job(wizard)
    assert job["preview"]["product"]["variants"][0]["shipping_cost"] == 5
    wizard.start_draft(job["id"], confirmation(job))
    assert wait_job(wizard)["result"]["status"] == "drafted"
    assert len(fetches) == len(calls) == 1


def test_ai_unsafe_generated_html_fails_preview_without_store_write(setup, monkeypatch):
    wizard, store, calls = setup

    class Unsafe(DeterministicListingGenerator):
        def generate(self, product):
            return replace(super().generate(product), description_html="<script>bad</script>")

    monkeypatch.setattr(wizard_module, "DeterministicListingGenerator", Unsafe)
    wizard.start_preview(request(store_profile_id=store.id))
    job = wait_job(wizard)
    assert job["status"] == "failed"
    assert job["error"] == "import_invalid_edits"
    assert job["preview"] is None and calls == []


def test_plain_text_breadcrumb_and_greater_than_signs_remain_reviewable(setup, monkeypatch):
    wizard, store, calls = setup
    category = "Home & Garden > Decor > Clocks > Wall Clocks"

    class Breadcrumb(DeterministicListingGenerator):
        def generate(self, product):
            return replace(super().generate(product), title="Clock > 10 cm",
                           category=category, tags=("Size > 10 cm",))

    monkeypatch.setattr(wizard_module, "DeterministicListingGenerator", Breadcrumb)
    wizard.start_preview(request(store_profile_id=store.id))
    job = wait_job(wizard)
    assert job["status"] == "ready"
    assert job["preview"]["listing"]["category"] == category
    wizard.start_draft(job["id"], confirmation(job))
    assert wait_job(wizard)["result"]["status"] == "drafted"
    assert calls[0][1].category == category


@pytest.mark.parametrize("edits", [
    {"title": "Clock <script>bad</script>"},
    {"category": "Clocks <img src=x>"},
    {"tags": ["Clock <b>bold</b>"]},
])
def test_html_markup_is_still_rejected_in_plain_text_listing_fields(setup, edits):
    wizard, store, calls = setup
    wizard.start_preview(request(store_profile_id=store.id))
    job = wait_job(wizard)
    with pytest.raises(ImportWizardError, match="import_invalid_edits"):
        wizard.start_draft(job["id"], confirmation(job, **edits))
    assert calls == []


def test_json_file_and_payload_parser_match_without_arbitrary_path_interface(tmp_path, setup):
    payload = manual_input()
    path = tmp_path / "product.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert JsonFileSource("alibaba-manual").fetch(str(path)) == product_from_payload(
        payload, source="alibaba-manual",
    )
    wizard, store, calls = setup
    with pytest.raises(ImportWizardError, match="import_invalid_product"):
        wizard.start_preview(request(source_input=str(path)))


def test_chinese_json_budget_counts_utf8_not_ascii_escaping(setup):
    wizard, store, calls = setup
    data = manual_input()
    data["facts"] = {f"资料{index}": "中文" * 450 for index in range(10)}
    assert len(json.dumps(data, ensure_ascii=False).encode("utf-8")) < 48 * 1024
    assert len(json.dumps(data).encode("utf-8")) > 48 * 1024
    wizard.start_preview(request(source_input=data))
    job = wait_job(wizard)
    assert job["status"] == "ready"
