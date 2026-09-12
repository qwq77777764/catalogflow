import base64
import io
import socket
import urllib.error
from dataclasses import replace
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from catalogflow.exporters.woocommerce import (
    MAX_RESPONSE_BYTES,
    WooCommerceDraftError,
    WooCommercePublisher,
)
from catalogflow.models import Listing, Product, Variant

MEDIA_CREDENTIAL = "synthetic-app-password"


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


@pytest.fixture
def source() -> tuple[Product, Listing]:
    product = Product(
        "cj",
        "demo",
        "Clock",
        "USD",
        (
            Variant("A", 2, {"Color": "Walnut", "Size": "Small"}),
            Variant("B", 3, {"Color": "Black", "Size": "Large"}),
        ),
    )
    listing = Listing("Desk Clock", "<p>Draft</p>", "Clocks", ("clock",), {"A": 9.95, "B": 15.95})
    return product, listing


class FakeStore:
    def __init__(self) -> None:
        self.calls = []
        self.existing = []
        self.fail_variant = None
        self.uploads = []
        self.returned_status = "draft"

    def request(self, method, route, payload=None, *, image_path=None):
        self.calls.append((method, route, payload))
        if image_path is not None:
            self.uploads.append((image_path, image_path.read_bytes()))
            return {"id": 90 + len(self.uploads)}
        if method == "GET" and route.startswith("/wp-json/wc/v3/products?"):
            return self.existing
        if method == "GET":
            name = parse_qs(urlparse(route).query)["search"][0]
            return [{"id": 40 if "categories" in route else 50, "name": name}]
        if route.endswith("/variations"):
            number = sum(call[1].endswith("/variations") for call in self.calls)
            if self.fail_variant == number:
                raise OSError("private provider response must not escape")
            return {"id": 70 + number, "status": self.returned_status}
        return {"id": 60, "status": self.returned_status, "catalog_visibility": "hidden"}


@pytest.fixture
def store(monkeypatch):
    publisher = WooCommercePublisher("https://shop.example", "synthetic-key", "synthetic-secret")
    transport = FakeStore()
    monkeypatch.setattr(publisher, "_request", transport.request)
    return publisher, transport


def test_variable_draft_keeps_each_price_and_exact_options(source, store) -> None:
    product, listing = source
    publisher, transport = store
    assert publisher.create_hidden_draft(product, listing) == "60"
    mutations = [call for call in transport.calls if call[0] in {"POST", "PUT"}]
    parent = mutations[0][2]
    assert parent["type"] == "variable"
    assert "regular_price" not in parent
    assert parent["attributes"] == [
        {"name": "Color", "visible": True, "variation": True, "options": ["Walnut", "Black"]},
        {"name": "Size", "visible": True, "variation": True, "options": ["Small", "Large"]},
    ]
    update = mutations[1][2]
    assert update["categories"] == [{"id": 40}]
    assert update["tags"] == [{"id": 50}]
    variations = [call[2] for call in mutations if call[1].endswith("/variations")]
    assert [v["regular_price"] for v in variations] == ["9.95", "15.95"]
    assert variations[1]["attributes"] == [
        {"name": "Color", "option": "Black"},
        {"name": "Size", "option": "Large"},
    ]
    assert len({parent["sku"], *(v["sku"] for v in variations)}) == 3
    for _, route, payload in mutations:
        assert payload["status"] == "draft"
        if not route.endswith("/variations"):
            assert payload["catalog_visibility"] == "hidden"


def test_single_variant_is_simple_with_its_own_price(source, store) -> None:
    product, listing = source
    product = replace(product, variants=(product.variants[1],))
    listing = replace(listing, prices={"B": 15.95})
    publisher, transport = store
    publisher.create_hidden_draft(product, listing)
    parent = next(payload for method, _, payload in transport.calls if method == "POST")
    assert parent["type"] == "simple"
    assert parent["regular_price"] == "15.95"
    assert parent["attributes"][0]["options"] == ["Black"]
    assert not any(route.endswith("/variations") for _, route, _ in transport.calls)


def test_media_bytes_upload_once_then_shared_attachment_ids(source, store, monkeypatch) -> None:
    product, listing = source
    common = "https://images.example/1.jpg"
    product = replace(
        product,
        images=(common,),
        variants=(
            replace(product.variants[0], image_url=common),
            replace(product.variants[1], image_url="https://images.example/2.jpg"),
        ),
    )
    publisher, transport = store
    publisher._media_username = "media-user"
    publisher._media_application_password = MEDIA_CREDENTIAL
    downloaded = []

    def materialize(urls, directory):
        downloaded.extend(urls)
        Path(directory).mkdir(parents=True)
        result = []
        for index, _ in enumerate(urls):
            path = Path(directory) / f"{index:04d}.jpg"
            path.write_bytes(b"synthetic-image")
            result.append(path)
        return result

    monkeypatch.setattr(
        "catalogflow.exporters.woocommerce.materialize_authorized_images", materialize
    )
    publisher.create_hidden_draft(product, listing)
    assert downloaded == [common, "https://images.example/2.jpg"]
    assert len(transport.uploads) == 2
    names = [path.name for path, _ in transport.uploads]
    assert len(set(names)) == 2
    assert all(path.stem.isascii() and path.stem.isdigit() and len(path.stem) > 20
               for path, _ in transport.uploads)
    assert all(data == b"synthetic-image" for _, data in transport.uploads)
    assert all(not path.exists() for path, _ in transport.uploads)
    update = next(payload for method, _, payload in transport.calls if method == "PUT")
    assert update["images"] == [{"id": 91}, {"id": 92}]
    variations = [payload for _, route, payload in transport.calls if route.endswith("/variations")]
    assert [v["image"] for v in variations] == [{"id": 91}, {"id": 92}]
    assert all("src" not in image for image in update["images"])
    parent_index = next(i for i, c in enumerate(transport.calls) if c[0] == "POST")
    upload_index = next(i for i, c in enumerate(transport.calls) if "/media?" in c[1])
    assert parent_index < upload_index


def test_images_require_separate_credentials_before_any_request(source, store) -> None:
    product, listing = source
    publisher, transport = store
    with pytest.raises(
        WooCommerceDraftError, match="wordpress_media_credentials_required"
    ) as error:
        publisher.create_hidden_draft(
            replace(product, images=("https://images.example/1.jpg",)), listing
        )
    assert error.value.write_started is False
    assert transport.calls == []


@pytest.mark.parametrize(
    "image_url",
    [
        "http://images.example/1.jpg",
        "https://user:password@images.example/1.jpg",
        "https://127.0.0.1/1.jpg",
        "https://private.example/1.jpg",
    ],
)
def test_unsafe_images_rejected_before_store_mutation(
    source, store, monkeypatch, image_url
) -> None:
    product, listing = source
    publisher, transport = store
    publisher._media_username = "media-user"
    publisher._media_application_password = MEDIA_CREDENTIAL
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **kw: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))],
    )
    with pytest.raises(WooCommerceDraftError) as error:
        publisher.create_hidden_draft(replace(product, images=(image_url,)), listing)
    assert error.value.write_started is False
    assert error.value.store_id is None
    assert all(method == "GET" for method, _, _ in transport.calls)


def test_duplicate_store_sku_blocks_new_write_and_reports_existing_id(source, store) -> None:
    product, listing = source
    publisher, transport = store
    transport.existing = [{"id": 123, "status": "draft",
                           "sku": publisher.build_payload(product, listing)["sku"]}]
    with pytest.raises(WooCommerceDraftError, match="woocommerce_existing_product") as error:
        publisher.create_hidden_draft(product, listing)
    assert error.value.store_id == "123"
    assert error.value.store_url == "https://shop.example/wp-admin/post.php?post=123&action=edit"
    assert error.value.write_started is True
    assert len(transport.calls) == 1
    query_sku = parse_qs(urlparse(transport.calls[0][1]).query)["sku"][0]
    assert query_sku == publisher.build_payload(product, listing)["sku"]


@pytest.mark.parametrize("row", [{"id": 123, "sku": "unrelated-product"}, {"id": 123}, None])
def test_store_ignoring_sku_filter_never_associates_an_unrelated_product(source, store, row):
    product, listing = source
    publisher, transport = store
    transport.existing = [row]
    with pytest.raises(WooCommerceDraftError, match="woocommerce_invalid_response") as error:
        publisher.create_hidden_draft(product, listing)
    assert error.value.store_id is None
    assert error.value.write_started is False
    assert len(transport.calls) == 1


def test_partial_variation_failure_stops_and_keeps_parent_context(source, store) -> None:
    product, listing = source
    product = replace(
        product, variants=(*product.variants, Variant("C", 4, {"Color": "White", "Size": "Large"}))
    )
    listing = replace(listing, prices={**listing.prices, "C": 20.95})
    publisher, transport = store
    transport.fail_variant = 2
    with pytest.raises(WooCommerceDraftError, match="woocommerce_draft_failed") as error:
        publisher.create_hidden_draft(product, listing)
    assert error.value.store_id == "60"
    assert error.value.write_started is True
    assert "private provider" not in str(error.value)
    assert error.value.__suppress_context__ is True
    assert sum(route.endswith("/variations") for _, route, _ in transport.calls) == 2


def test_parent_lost_ack_is_uncertain_without_retry(source, store, monkeypatch) -> None:
    product, listing = source
    publisher, transport = store
    original = transport.request

    def request(method, route, payload=None, **kwargs):
        if method == "POST":
            transport.calls.append((method, route, payload))
            raise TimeoutError("secret raw response")
        return original(method, route, payload, **kwargs)

    monkeypatch.setattr(publisher, "_request", request)
    with pytest.raises(WooCommerceDraftError) as error:
        publisher.create_hidden_draft(product, listing)
    assert error.value.write_started is True
    assert error.value.store_id is None
    assert sum(method == "POST" for method, _, _ in transport.calls) == 1


def test_store_must_confirm_hidden_draft_before_further_writes(source, store) -> None:
    product, listing = source
    publisher, transport = store
    transport.returned_status = "unexpected-status"
    with pytest.raises(WooCommerceDraftError, match="woocommerce_draft_state_unconfirmed") as error:
        publisher.create_hidden_draft(product, listing)
    assert error.value.store_id == "60"
    assert sum(method == "POST" for method, _, _ in transport.calls) == 1


@pytest.mark.parametrize(
    "variants",
    [
        (Variant("A", 1), Variant("B", 2)),
        (Variant("A", 1, {"Color": "Black"}), Variant("B", 2, {"Size": "Large"})),
        (Variant("A", 1, {"Color": "Black"}), Variant("B", 2, {"Color": "Black"})),
        (Variant("A", 1, {"Color": ""}), Variant("B", 2, {"Color": "Black"})),
        (Variant("A", 1, {"Color": "White"}), Variant("A", 2, {"Color": "Black"})),
    ],
)
def test_invalid_variants_never_create_wildcard_or_duplicate_options(
    source, store, variants
) -> None:
    product, listing = source
    publisher, transport = store
    with pytest.raises(WooCommerceDraftError, match="woocommerce_invalid_variants") as error:
        publisher.create_hidden_draft(replace(product, variants=variants), listing)
    assert error.value.write_started is False
    assert transport.calls == []


@pytest.mark.parametrize("price", [float("nan"), float("inf"), -1])
def test_invalid_price_fails_before_store_requests(source, store, price) -> None:
    product, listing = source
    publisher, transport = store
    with pytest.raises(WooCommerceDraftError, match="woocommerce_invalid_prices"):
        publisher.create_hidden_draft(product, replace(listing, prices={"A": price, "B": 5}))
    assert transport.calls == []


def test_term_search_uses_existing_ids_or_explicitly_creates_missing_terms(
    store, monkeypatch
) -> None:
    publisher, _ = store
    calls = []

    def request(method, route, payload=None):
        calls.append((method, route, payload))
        if method == "GET":
            return [{"id": 9, "name": "Clocks &amp; Decor"}]
        return {"id": 15, "name": payload["name"]}

    monkeypatch.setattr(publisher, "_request", request)
    assert publisher._term("categories", "Clocks & Decor") == 9
    assert len(calls) == 1
    assert publisher._term("tags", "wood") == 15
    assert calls[-1] == ("POST", "/wp-json/wc/v3/products/tags", {"name": "wood"})


@pytest.mark.parametrize(
    "url",
    [
        "https://user:password@shop.example",
        "https://shop.example/?key=private",
        "https://shop.example/#private",
        "https://shop.example/../other",
        "https://shop.example/%2e%2e/other",
        "https://shop.example:wrong",
        "https://shop.example\\other",
    ],
)
def test_store_url_rejects_credentials_queries_and_ambiguous_paths(url) -> None:
    with pytest.raises(ValueError):
        WooCommercePublisher(url, "key", "secret")


def test_store_identity_normalizes_equivalent_origins_and_ignores_credentials() -> None:
    first = WooCommercePublisher("https://SHOP.example:443/blog/", "key1", "secret1")
    second = WooCommercePublisher("https://shop.example/blog", "key2", "secret2")
    assert first.store_identity == second.store_identity
    assert (
        first.store_identity
        != WooCommercePublisher("https://shop.example/other", "key", "secret").store_identity
    )
    assert len(first.store_identity) == 64


class FakeResponse(io.BytesIO):
    def getcode(self):
        return 200


def test_transport_uses_separate_auth_for_media_and_refuses_all_redirects(
    monkeypatch, tmp_path
) -> None:
    publisher = WooCommercePublisher(
        "https://shop.example",
        "synthetic-key",
        "synthetic-secret",
        media_username="media-user",
        media_application_password=MEDIA_CREDENTIAL,
    )
    requests = []

    class Opener:
        def open(self, request, timeout):
            requests.append(request)
            assert timeout == 30
            return FakeResponse(b'{"id": 1}')

    def opener(handler):
        assert handler.redirect_request(None, None, 302, "", {}, "https://other.example") is None
        assert handler.redirect_request(None, None, 307, "", {}, "https://shop.example") is None
        return Opener()

    monkeypatch.setattr("urllib.request.build_opener", opener)
    publisher._request("GET", "/wp-json/wc/v3/products?sku=synthetic")
    image = tmp_path / "0001.jpg"
    image.write_bytes(b"synthetic-image")
    publisher._request("POST", "/wp-json/wp/v2/media?post=1", image_path=image)
    auth = [
        base64.b64decode(r.get_header("Authorization").removeprefix("Basic ")).decode()
        for r in requests
    ]
    assert auth == ["synthetic-key:synthetic-secret", "media-user:synthetic-app-password"]
    assert requests[1].data == b"synthetic-image"
    assert requests[1].get_header("Content-disposition") == 'attachment; filename="0001.jpg"'


@pytest.mark.parametrize("failure", ["oversized", "malformed", "http-error"])
def test_transport_response_limits_and_error_redaction(monkeypatch, failure) -> None:
    publisher = WooCommercePublisher("https://shop.example", "key", "secret")

    class Opener:
        def open(self, *args, **kwargs):
            if failure == "http-error":
                raise urllib.error.HTTPError(
                    "https://shop.example/private",
                    403,
                    "secret message",
                    {},
                    io.BytesIO(b"secret body"),
                )
            return FakeResponse(
                b"x" * (MAX_RESPONSE_BYTES + 1) if failure == "oversized" else b"invalid"
            )

    monkeypatch.setattr("urllib.request.build_opener", lambda *a: Opener())
    with pytest.raises(WooCommerceDraftError) as error:
        publisher._request("GET", "/wp-json/wc/v3/products")
    assert "secret" not in str(error.value)
    assert "private" not in str(error.value)


def test_environment_loads_optional_media_credentials(monkeypatch) -> None:
    for name, value in {
        "WOOCOMMERCE_URL": "https://shop.example",
        "WOOCOMMERCE_CONSUMER_KEY": "synthetic-key",
        "WOOCOMMERCE_CONSUMER_SECRET": "synthetic-secret",
        "WOOCOMMERCE_MEDIA_USERNAME": "media-user",
        "WOOCOMMERCE_MEDIA_APPLICATION_PASSWORD": "synthetic-app-password",
    }.items():
        monkeypatch.setenv(name, value)
    publisher = WooCommercePublisher.from_environment()
    assert publisher._media_username == "media-user"
    assert publisher._media_application_password == MEDIA_CREDENTIAL


def test_gallery_larger_than_helper_batch_is_not_silently_truncated(source, store, monkeypatch):
    product, listing = source
    publisher, transport = store
    publisher._media_username = "media-user"
    publisher._media_application_password = MEDIA_CREDENTIAL
    urls = tuple(f"https://images.example/{index}.jpg" for index in range(7))
    batches = []

    def materialize(batch, directory):
        batches.append(batch)
        Path(directory).mkdir(parents=True)
        paths = [Path(directory) / f"{i:04d}.jpg" for i in range(len(batch))]
        for path in paths:
            path.write_bytes(b"synthetic-image")
        return paths

    monkeypatch.setattr(
        "catalogflow.exporters.woocommerce.materialize_authorized_images", materialize
    )
    publisher.create_hidden_draft(replace(product, images=urls), listing)
    assert [len(batch) for batch in batches] == [5, 2]
    assert len(transport.uploads) == 7
    assert all(not path.exists() for path, _ in transport.uploads)


def test_upload_failure_retains_parent_and_stops_before_more_media(source, store, monkeypatch):
    product, listing = source
    publisher, transport = store
    publisher._media_username = "media-user"
    publisher._media_application_password = MEDIA_CREDENTIAL
    original = transport.request
    materialized = []

    def materialize(batch, directory):
        Path(directory).mkdir(parents=True)
        for i, _ in enumerate(batch):
            path = Path(directory) / f"{i:04d}.jpg"
            path.write_bytes(b"synthetic-image")
            materialized.append(path)
        return materialized

    def request(method, route, payload=None, **kwargs):
        if "/media?" in route:
            transport.calls.append((method, route, payload))
            raise WooCommerceDraftError("woocommerce_request_failed")
        return original(method, route, payload, **kwargs)

    monkeypatch.setattr(
        "catalogflow.exporters.woocommerce.materialize_authorized_images", materialize
    )
    monkeypatch.setattr(publisher, "_request", request)
    urls = ("https://images.example/1.jpg", "https://images.example/2.jpg")
    with pytest.raises(WooCommerceDraftError, match="woocommerce_request_failed") as error:
        publisher.create_hidden_draft(replace(product, images=urls), listing)
    assert error.value.store_id == "60"
    assert error.value.write_started is True
    assert sum("/media?" in route for _, route, _ in transport.calls) == 1
    assert not any(route.endswith("/variations") for _, route, _ in transport.calls)
    assert all(not path.exists() for path in materialized)


def test_export_bounds_fail_before_network_requests(source, store):
    product, listing = source
    publisher, transport = store
    urls = tuple(f"https://images.example/{i}.jpg" for i in range(21))
    with pytest.raises(WooCommerceDraftError, match="woocommerce_image_limit") as error:
        publisher.create_hidden_draft(replace(product, images=urls), listing)
    assert error.value.write_started is False
    variants = tuple(Variant(str(i), 2, {"Size": str(i)}) for i in range(101))
    with pytest.raises(WooCommerceDraftError, match="woocommerce_variant_limit") as error:
        publisher.create_hidden_draft(replace(product, variants=variants), listing)
    assert error.value.write_started is False
    assert transport.calls == []


def test_failed_duplicate_query_can_be_retried_without_new_store_write(source, store, monkeypatch):
    product, listing = source
    publisher, _ = store

    def request(*args, **kwargs):
        raise WooCommerceDraftError("woocommerce_request_failed")

    monkeypatch.setattr(publisher, "_request", request)
    with pytest.raises(WooCommerceDraftError) as error:
        publisher.create_hidden_draft(product, listing)
    assert error.value.store_id is None
    assert error.value.write_started is False
