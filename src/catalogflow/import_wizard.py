"""One local, reviewable import at a time, using the durable import pipeline."""

from __future__ import annotations

import copy
import ipaddress
import json
import math
import threading
import uuid
from dataclasses import asdict, replace
from html.parser import HTMLParser
from urllib.parse import urlsplit

from .configuration import environment_for_profile
from .exporters import WooCommercePublisher
from .generators import (
    ClaudeCliListingGenerator,
    CodexCliListingGenerator,
    DeterministicListingGenerator,
)
from .models import ImportMode, ImportRequest, Listing, Product
from .pipeline import import_products
from .pricing import MAX_MONEY, shipping_cost_for_pricing
from .providers import CjApiSource, extract_cj_product_id
from .providers.json_file import product_from_payload
from .run_history import canonical_url, safe_error
from .validation import validate_listing, validate_product

MAX_INPUT_BYTES = 48 * 1024
_PREVIEW_FIELDS = {
    "source", "source_input", "source_profile_id", "generator", "ai_profile_id",
    "store_profile_id",
}
_EDIT_FIELDS = {"title", "description_html", "category", "tags"}


class ImportWizardError(ValueError):
    """An HTTP-safe diagnostic; no underlying response or exception text is exposed."""

    def __init__(self, code: str, status: int = 400) -> None:
        self.code = code
        self.status = status
        super().__init__(code)


def _require(condition: bool, code: str = "import_invalid_request") -> None:
    if not condition:
        raise ImportWizardError(code)


def _text(value: object, limit: int, *, empty: bool = False) -> bool:
    return (isinstance(value, str) and len(value) <= limit
            and (empty or bool(value.strip()))
            and not any(ord(char) < 32 and char not in "\n\r\t" for char in value))


def _profile_id(value: object) -> None:
    if value is None:
        return
    _require(isinstance(value, str), "import_profile_invalid")
    try:
        _require(str(uuid.UUID(value)) == value, "import_profile_invalid")
    except (ValueError, AttributeError):
        raise ImportWizardError("import_profile_invalid") from None


def _https_url(value: object) -> bool:
    if not _text(value, 2048) or any(char.isspace() for char in value):
        return False
    try:
        parts = urlsplit(value)
        host = (parts.hostname or "").lower().rstrip(".")
        if (parts.scheme != "https" or not host or parts.username is not None
                or parts.password is not None or parts.port not in (None, 443)
                or "\\" in value):
            return False
        try:
            return ipaddress.ip_address(host).is_global
        except ValueError:
            return ("." in host and not host.endswith((".localhost", ".local", ".internal"))
                    and host != "localhost")
    except ValueError:
        return False


def _bounded_json(payload: object, *, limit: int = 64 * 1024) -> None:
    try:
        encoded = json.dumps(payload, allow_nan=False, ensure_ascii=False,
                             separators=(",", ":")).encode("utf-8")
        _require(len(encoded) <= limit)
    except (TypeError, ValueError, RecursionError):
        raise ImportWizardError("import_invalid_request") from None


def _manual_product(payload: object) -> Product:
    code = "import_invalid_product"
    _require(isinstance(payload, dict), code)
    _require(set(payload) <= {
        "source", "source_id", "title", "currency", "variants", "images", "facts", "source_url",
    }, code)
    _require(payload.get("source", "alibaba-manual") == "alibaba-manual", code)
    _require(_text(payload.get("source_id"), 200) and _text(payload.get("title"), 500), code)
    _require(payload.get("currency", "USD") == "USD", code)
    source_url = payload.get("source_url", "")
    _require(source_url == "" or _https_url(source_url), code)
    images = payload.get("images", [])
    _require(isinstance(images, list) and len(images) <= 20
             and all(_https_url(value) for value in images), code)
    facts = payload.get("facts", {})
    _require(isinstance(facts, dict) and len(facts) <= 50
             and all(_text(key, 100) and _text(value, 2000, empty=True)
                     for key, value in facts.items()), code)
    variants = payload.get("variants")
    _require(isinstance(variants, list) and 1 <= len(variants) <= 100, code)
    for row in variants:
        _require(isinstance(row, dict) and set(row) <= {
            "sku", "cost", "attributes", "shipping_quote", "image_url",
        }, code)
        _require(_text(row.get("sku"), 200), code)
        cost = row.get("cost")
        _require(type(cost) in (float, int) and 0 <= cost <= MAX_MONEY and math.isfinite(cost),
                 code)
        attributes = row.get("attributes", {})
        _require(isinstance(attributes, dict) and len(attributes) <= 10
                 and all(_text(key, 100) and _text(value, 200)
                         for key, value in attributes.items()), code)
        image_url = row.get("image_url", "")
        _require(image_url == "" or _https_url(image_url), code)
        quote = row.get("shipping_quote")
        if quote is not None:
            _require(isinstance(quote, dict) and set(quote) <= {
                "origin_country", "destination_country", "quantity", "method",
                "total_cost_usd", "estimated_days",
            }, code)
            _require(all(_text(quote.get(key), 100) for key in (
                "origin_country", "destination_country", "method",
            )), code)
            _require(type(quote.get("quantity")) is int and 1 <= quote["quantity"] <= 100, code)
            total = quote.get("total_cost_usd")
            _require(type(total) in (int, float) and 0 <= total <= MAX_MONEY
                     and math.isfinite(total), code)
            _require(_text(quote.get("estimated_days", ""), 100, empty=True), code)
    try:
        product = product_from_payload(payload, source="alibaba-manual")
        _check_product(product)
        return product
    except (ValueError, TypeError, KeyError):
        raise ImportWizardError(code) from None


def _check_product(product: Product) -> None:
    code = "import_invalid_product"
    _require(not validate_product(product), code)
    _require(product.currency == "USD" and 1 <= len(product.variants) <= 100, code)
    _require(_text(product.source_id, 200) and _text(product.title, 500), code)
    _require(len(product.facts) <= 50 and all(
        _text(key, 100) and _text(value, 2000, empty=True)
        for key, value in product.facts.items()
    ), code)
    skus = [variant.sku for variant in product.variants]
    _require(len(set(skus)) == len(skus) and all(_text(sku, 200) for sku in skus), code)
    images = set(product.images) | {v.image_url for v in product.variants if v.image_url}
    _require(len(product.images) <= 20 and len(images) <= 20
             and all(_https_url(value) for value in images), code)
    for variant in product.variants:
        _require(type(variant.cost) in (int, float) and 0 <= variant.cost <= MAX_MONEY
                 and math.isfinite(variant.cost), code)
        _require(len(variant.attributes) <= 10 and all(
            _text(key, 100) and _text(value, 200) for key, value in variant.attributes.items()
        ), code)
        if variant.shipping_quote is not None:
            quote = variant.shipping_quote
            _require(type(quote.quantity) is int and 1 <= quote.quantity <= 100, code)
            _require(type(quote.total_cost_usd) in (int, float)
                     and 0 <= quote.total_cost_usd <= MAX_MONEY
                     and math.isfinite(quote.total_cost_usd), code)


class _DescriptionValidator(HTMLParser):
    """Only inert, balanced product-copy markup; never execute or fetch HTML content."""

    tags = frozenset({
        "p", "br", "strong", "em", "b", "i", "u", "ul", "ol", "li", "h2", "h3", "h4",
        "table", "thead", "tbody", "tr", "th", "td", "caption", "blockquote", "hr",
    })

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []

    def handle_starttag(self, tag, attrs):
        _require(tag in self.tags and not attrs, "import_invalid_edits")
        if tag not in {"br", "hr"}:
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        _require(tag in {"br", "hr"} and not attrs, "import_invalid_edits")

    def handle_endtag(self, tag):
        _require(bool(self.stack) and self.stack[-1] == tag, "import_invalid_edits")
        self.stack.pop()

    def handle_comment(self, data):
        raise ImportWizardError("import_invalid_edits")

    def handle_decl(self, decl):
        raise ImportWizardError("import_invalid_edits")

    def handle_pi(self, data):
        raise ImportWizardError("import_invalid_edits")

    def unknown_decl(self, data):
        raise ImportWizardError("import_invalid_edits")


def _checked_listing(listing: Listing, product: Product) -> None:
    code = "import_invalid_edits"
    _require(_text(listing.title, 80) and _text(listing.description_html, 16000)
             and _text(listing.category, 120), code)
    _require(len(listing.tags) <= 20 and all(_text(tag, 80) for tag in listing.tags), code)
    # These fields are text, so category breadcrumbs and comparisons may contain >.
    # A < can begin HTML markup; description HTML uses the separate strict parser below.
    _require(not any("<" in text for text in (
        listing.title, listing.category, *listing.tags,
    )), code)
    parser = _DescriptionValidator()
    parser.feed(listing.description_html)
    parser.close()
    _require(not parser.stack, code)
    _require(not validate_listing(listing, product), code)
    # Pure exporter validation also checks variant options and finite prices; it does no I/O.
    try:
        WooCommercePublisher.build_payload(product, listing)
    except (ValueError, RuntimeError, TypeError):
        raise ImportWizardError(code) from None


class _CachedSource:
    def __init__(self, product: Product):
        self.product = copy.deepcopy(product)

    def fetch(self, reference: str) -> Product:
        return copy.deepcopy(self.product)


class _CachedGenerator:
    def __init__(self, listing: Listing):
        self.listing = copy.deepcopy(listing)

    def generate(self, product: Product) -> Listing:
        return copy.deepcopy(self.listing)


class ImportWizard:
    """Keep one authenticated session's frozen preview and explicit draft confirmation."""

    def __init__(self, repository, secret_store, pricing_repository, history) -> None:
        self.repository = repository
        self.secret_store = secret_store
        self.pricing_repository = pricing_repository
        self.history = history
        self._lock = threading.RLock()
        self._job: dict | None = None
        self._product: Product | None = None
        self._listing: Listing | None = None
        self._publisher = None
        self._request: ImportRequest | None = None
        self._submitted = False
        self._confirmation: dict | None = None
        self._closed = False

    @property
    def busy(self) -> bool:
        with self._lock:
            return self._job is not None and self._job["status"] in {"running", "drafting"}

    def current(self) -> dict | None:
        with self._lock:
            return copy.deepcopy(self._job)

    def prepare_shutdown(self) -> bool:
        """Atomically exclude new work before the dashboard stops its server."""
        with self._lock:
            if self.busy:
                return False
            self._closed = True
            return True

    def get(self, jobid: str) -> dict:
        with self._lock:
            self._check_id(jobid)
            return copy.deepcopy(self._job)

    def _check_id(self, jobid: str) -> None:
        if self._job is None or not isinstance(jobid, str) or self._job["id"] != jobid:
            raise ImportWizardError("import_not_found", 404)

    def start_preview(self, payload: dict) -> dict:
        _require(isinstance(payload, dict) and set(payload) == _PREVIEW_FIELDS)
        _bounded_json(payload)
        _bounded_json(payload["source_input"], limit=MAX_INPUT_BYTES)
        source = payload["source"]
        _require(source in ("cj", "alibaba-manual"), "import_invalid_source")
        _require(payload["generator"] in ("codex", "claude", "deterministic"))
        for field in ("source_profile_id", "ai_profile_id", "store_profile_id"):
            _profile_id(payload[field])
        if payload["generator"] == "deterministic":
            _require(payload["ai_profile_id"] is None, "import_ai_profile_invalid")
        if source == "cj":
            value = payload["source_input"]
            _require(_text(value, 2048), "import_invalid_source")
            try:
                if "://" in value:
                    _require(_https_url(value), "import_invalid_source")
                extract_cj_product_id(value)
            except (ValueError, RuntimeError):
                raise ImportWizardError("import_invalid_source") from None
        else:
            _require(payload["source_profile_id"] is None, "import_profile_invalid")
            _manual_product(payload["source_input"])
        with self._lock:
            if self._closed:
                raise ImportWizardError("import_not_ready", 409)
            if self.busy:
                raise ImportWizardError("import_busy", 409)
            self._product = self._listing = self._publisher = self._request = None
            self._submitted = False
            self._confirmation = None
            self._job = {
                "id": uuid.uuid4().hex, "status": "running", "phase": "fetching",
                "revision": uuid.uuid4().hex, "preview": None, "result": None,
                "error": None, "report_run_id": None,
            }
            self._launch(self._preview_worker, copy.deepcopy(payload))
            return copy.deepcopy(self._job)

    def _launch(self, target, payload) -> None:
        try:
            threading.Thread(target=target, args=(payload,), daemon=False).start()
        except RuntimeError:
            self._job.update(status="failed", phase="finished", error="import_configuration_failed")

    def _profile(self, identifier, provider: str, *, required: bool = False):
        try:
            profile = (self.repository.find(identifier) if identifier is not None
                       else self.repository.default_for(provider))
            if profile is not None:
                _require(profile.provider == provider and (
                    identifier is None or profile.id == identifier
                ), "import_profile_invalid")
            elif required:
                raise ImportWizardError("import_profile_invalid")
            return profile
        except (ValueError, RuntimeError, KeyError):
            raise ImportWizardError("import_profile_invalid") from None

    def _prepare(self, payload):
        policy = self.pricing_repository.load()
        if payload["source"] == "cj":
            profile = self._profile(payload["source_profile_id"], "cj", required=True)
            values = environment_for_profile(profile, self.secret_store)
            source = CjApiSource(
                values.get("CJ_API_KEY", ""),
                origin_country=values.get("CJ_ORIGIN_COUNTRY_CODE", "CN"),
                destination_country=values.get("CJ_TARGET_COUNTRY_CODE", "US"),
                destination_zip=values.get("CJ_TARGET_ZIP", ""),
                freight_quantity=int(values.get("CJ_FREIGHT_QUANTITY", "1")),
                preferred_logistics=values.get("CJ_LOGISTICS", ""),
            )
            reference = payload["source_input"].strip()
        else:
            product = _manual_product(payload["source_input"])
            source = _CachedSource(product)
            reference = canonical_url(product.source_url) or product.source_id
        if payload["generator"] == "deterministic":
            generator = DeterministicListingGenerator(policy=policy)
        else:
            profile = self._profile(payload["ai_profile_id"], payload["generator"])
            values = profile.values if profile else {}
            cls = (CodexCliListingGenerator if payload["generator"] == "codex"
                   else ClaudeCliListingGenerator)
            generator = cls(policy=policy, command=values.get("command", ""),
                            model=values.get("model", ""))
        publisher = None
        store = None
        if payload["store_profile_id"] is not None:
            profile = self._profile(payload["store_profile_id"], "woocommerce", required=True)
            values = environment_for_profile(profile, self.secret_store)
            _require(all(values.get(name) for name in (
                "WOOCOMMERCE_URL", "WOOCOMMERCE_CONSUMER_KEY", "WOOCOMMERCE_CONSUMER_SECRET",
            )), "import_configuration_failed")
            publisher = WooCommercePublisher(
                values["WOOCOMMERCE_URL"], values["WOOCOMMERCE_CONSUMER_KEY"],
                values["WOOCOMMERCE_CONSUMER_SECRET"],
                media_username=values.get("WOOCOMMERCE_MEDIA_USERNAME", ""),
                media_application_password=values.get("WOOCOMMERCE_MEDIA_APPLICATION_PASSWORD", ""),
            )
            store = {"label": profile.label, "base_url": publisher.base_url}
        return policy, source, generator, publisher, store, reference

    def _phase(self, phase: str) -> None:
        with self._lock:
            self._job["phase"] = phase

    def _preview_worker(self, payload: dict) -> None:
        try:
            policy, source, generator, publisher, store, reference = self._prepare(payload)
        except Exception as exc:
            self._configuration_failure(payload, exc)
            return
        captured: dict = {}
        owner = self

        class CaptureSource:
            def fetch(self, value):
                product = source.fetch(value)
                _check_product(product)
                captured["product"] = copy.deepcopy(product)
                return product

        class CaptureGenerator:
            def generate(self, product):
                owner._phase("generating")
                listing = generator.generate(product)
                owner._phase("pricing")
                _checked_listing(listing, product)
                captured["listing"] = copy.deepcopy(listing)
                return listing

        request = ImportRequest(payload["source"], reference)
        try:
            report = import_products(
                [request], sources={payload["source"]: CaptureSource()},
                generator=CaptureGenerator(), history=self.history,
            )
            item = report.items[0]
            with self._lock:
                self._apply_report(report)
                if item.status != "previewed":
                    return
                product = captured["product"]
                listing = captured["listing"]
                self._product, self._listing = product, listing
                self._publisher, self._request = publisher, request
                self._job.update(status="ready", error=None, preview={
                    "product": {
                        "source": product.source, "source_id": product.source_id,
                        "source_url": canonical_url(product.source_url or reference),
                        "title": product.title, "images": list(product.images),
                        "variants": [{
                            "sku": variant.sku, "attributes": copy.deepcopy(variant.attributes),
                            "cost": variant.cost,
                            "shipping_cost": shipping_cost_for_pricing(product, variant),
                            "shipping_quote": (asdict(variant.shipping_quote)
                                               if variant.shipping_quote else None),
                            "image_url": variant.image_url,
                        } for variant in product.variants],
                    },
                    "listing": {
                        "title": listing.title, "description_html": listing.description_html,
                        "category": listing.category, "tags": list(listing.tags),
                        "prices_by_sku": copy.deepcopy(listing.prices),
                    },
                    "pricing": policy.to_dict(), "store": store,
                })
        except Exception:
            self._failed_reports()

    def _apply_report(self, report) -> None:
        item = report.items[0]
        self._job.update(
            status="completed" if report.ok else "failed", phase="finished",
            report_run_id=report.run_id,
            error=None if report.ok else (item.errors[0] if item.errors else "operation_failed"),
            result={"status": item.status, "errors": list(item.errors),
                    "store_id": item.store_id, "store_url": item.store_url},
        )

    def _configuration_failure(self, payload, exc) -> None:
        code = exc.code if isinstance(exc, ImportWizardError) else "import_configuration_failed"
        try:
            run = self.history.create_run(ImportMode.DRY_RUN)
            value = payload["source_input"]
            item = run.start_item(source=payload["source"],
                                  source_url=value if isinstance(value, str) else "")
            item.update(status="rejected", errors=["configuration_failed", safe_error(exc)])
            run.finish_item(item)
            run.finish()
            with self._lock:
                self._job.update(status="failed", phase="finished", error=code,
                                 report_run_id=run.run_id,
                                 result={"status": "rejected", "errors": [code],
                                         "store_id": None, "store_url": ""})
        except Exception:
            self._failed_reports()

    def _failed_reports(self) -> None:
        with self._lock:
            self._job.update(status="failed", phase="finished", error="import_reports_unavailable",
                             result={"status": "failed", "errors": ["import_reports_unavailable"],
                                     "store_id": None, "store_url": ""})

    def start_draft(self, jobid: str, payload: dict) -> dict:
        _require(isinstance(payload, dict) and set(payload) == {
            "revision", "confirm_hidden_draft", "edits",
        })
        _bounded_json(payload)
        _require(payload["confirm_hidden_draft"] is True, "import_confirmation_required")
        with self._lock:
            if self._closed:
                raise ImportWizardError("import_not_ready", 409)
            self._check_id(jobid)
            if (not isinstance(payload["revision"], str)
                    or payload["revision"] != self._job["revision"]):
                raise ImportWizardError("import_revision_mismatch", 409)
            if self._submitted:
                if payload != self._confirmation:
                    raise ImportWizardError("import_not_ready", 409)
                return copy.deepcopy(self._job)
            if self._job["status"] != "ready":
                raise ImportWizardError("import_not_ready", 409)
            if self._publisher is None:
                raise ImportWizardError("import_store_required")
            edits = payload["edits"]
            _require(isinstance(edits, dict) and set(edits) == _EDIT_FIELDS,
                     "import_invalid_edits")
            _require(isinstance(edits["tags"], list) and all(isinstance(tag, str)
                     for tag in edits["tags"]), "import_invalid_edits")
            listing = replace(self._listing, title=edits["title"],
                              description_html=edits["description_html"],
                              category=edits["category"], tags=tuple(edits["tags"]))
            _checked_listing(listing, self._product)
            self._listing = copy.deepcopy(listing)
            self._submitted = True
            self._confirmation = copy.deepcopy(payload)
            self._job["preview"]["listing"].update(copy.deepcopy(edits))
            self._job.update(status="drafting", phase="drafting", result=None, error=None)
            self._launch(self._draft_worker, None)
            return copy.deepcopy(self._job)

    def _draft_worker(self, unused) -> None:
        try:
            report = import_products(
                [self._request], sources={self._product.source: _CachedSource(self._product)},
                generator=_CachedGenerator(self._listing), mode=ImportMode.DRAFT,
                publisher=self._publisher, history=self.history,
            )
            with self._lock:
                self._apply_report(report)
        except Exception:
            self._failed_reports()
