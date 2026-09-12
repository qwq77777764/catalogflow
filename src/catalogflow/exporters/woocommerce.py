"""Bounded WooCommerce REST export of complete, explicitly requested hidden drafts."""

from __future__ import annotations

import base64
import hashlib
import html
import http.client
import json
import math
import os
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import unquote, urlencode, urlparse

from ..media import MAX_IMAGES, materialize_authorized_images
from ..models import Listing, Product, Variant

MAX_VARIANTS = 100
MAX_EXPORT_IMAGES = 20
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
_MIME_TYPES = {
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


class WooCommerceDraftError(RuntimeError):
    """A safe diagnostic, optionally identifying a draft that needs manual review."""

    def __init__(
        self,
        code: str,
        *,
        store_id: str | None = None,
        store_url: str | None = None,
        write_started: bool = True,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.store_id = store_id
        self.store_url = store_url
        self.write_started = write_started


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        return None


def _resource_id(result: object) -> int:
    identifier = result.get("id") if isinstance(result, dict) else None
    if type(identifier) is not int or identifier < 1:
        raise WooCommerceDraftError("woocommerce_invalid_response")
    return identifier


def _source_sku(product: Product, variant: Variant | None = None) -> str:
    parts = [product.source, product.source_id]
    if variant is not None:
        parts.append(variant.sku)
    digest = hashlib.sha256(json.dumps(parts, ensure_ascii=True).encode()).hexdigest()[:40]
    return ("cf-v-" if variant is not None else "cf-") + digest


class WooCommercePublisher:
    """Create hidden drafts only; public publishing is outside this interface."""

    def __init__(
        self,
        base_url: str,
        consumer_key: str,
        consumer_secret: str,
        *,
        media_username: str = "",
        media_application_password: str = "",
    ) -> None:
        parsed = urlparse(base_url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.params
            or "\\" in base_url
            or any(char.isspace() for char in base_url)
            or any(part in {".", ".."} for part in unquote(parsed.path).split("/"))
        ):
            raise ValueError("WOOCOMMERCE_URL must be a credential-free absolute HTTPS URL")
        try:
            port = parsed.port
            host = parsed.hostname.encode("idna").decode("ascii").lower().rstrip(".")
        except (ValueError, UnicodeError) as exc:
            raise ValueError("WOOCOMMERCE_URL must be a valid HTTPS URL") from exc
        authority = f"[{host}]" if ":" in host else host
        if port not in (None, 443):
            authority += f":{port}"
        self.base_url = f"https://{authority}{parsed.path.rstrip('/')}"
        self.consumer_key = consumer_key
        self.consumer_secret = consumer_secret
        self._media_username = media_username
        self._media_application_password = media_application_password

    @property
    def store_identity(self) -> str:
        return hashlib.sha256(self.base_url.encode("utf-8")).hexdigest()

    def product_url(self, store_id: str) -> str:
        if not str(store_id).isascii() or not str(store_id).isdigit() or int(store_id) < 1:
            raise ValueError("store_id must be a positive integer")
        return f"{self.base_url}/wp-admin/post.php?post={int(store_id)}&action=edit"

    @classmethod
    def from_environment(cls) -> WooCommercePublisher:
        names = (
            "WOOCOMMERCE_URL",
            "WOOCOMMERCE_CONSUMER_KEY",
            "WOOCOMMERCE_CONSUMER_SECRET",
        )
        values = {name: os.environ.get(name, "") for name in names}
        missing = [name for name, value in values.items() if not value]
        if missing:
            raise RuntimeError("Missing required environment variables: " + ", ".join(missing))
        return cls(
            values[names[0]],
            values[names[1]],
            values[names[2]],
            media_username=os.environ.get("WOOCOMMERCE_MEDIA_USERNAME", ""),
            media_application_password=os.environ.get("WOOCOMMERCE_MEDIA_APPLICATION_PASSWORD", ""),
        )

    def _request(
        self,
        method: str,
        route: str,
        payload: dict[str, object] | None = None,
        *,
        image_path: Path | None = None,
    ) -> object:
        headers = {"User-Agent": "CatalogFlow draft exporter", "Accept": "application/json"}
        if image_path is None:
            credentials = f"{self.consumer_key}:{self.consumer_secret}"
            data = json.dumps(payload).encode("utf-8") if payload is not None else None
            headers["Content-Type"] = "application/json"
        else:
            credentials = f"{self._media_username}:{self._media_application_password}"
            data = image_path.read_bytes()
            headers["Content-Type"] = _MIME_TYPES[image_path.suffix]
            headers["Content-Disposition"] = f'attachment; filename="{image_path.name}"'
        headers["Authorization"] = "Basic " + base64.b64encode(credentials.encode()).decode("ascii")
        request = urllib.request.Request(  # noqa: S310 - fixed route on validated HTTPS store
            self.base_url + route, data=data, headers=headers, method=method
        )
        try:
            opener = urllib.request.build_opener(_NoRedirects())
            with opener.open(request, timeout=30) as response:  # noqa: S310
                if response.getcode() not in {200, 201}:
                    raise WooCommerceDraftError("woocommerce_request_failed")
                raw = response.read(MAX_RESPONSE_BYTES + 1)
                if len(raw) > MAX_RESPONSE_BYTES:
                    raise WooCommerceDraftError("woocommerce_invalid_response")
            return json.loads(raw)
        except WooCommerceDraftError:
            raise
        except (OSError, ValueError, RecursionError, http.client.HTTPException):
            # HTTP bodies, credentials, source URLs and file paths never become report text.
            raise WooCommerceDraftError("woocommerce_request_failed") from None

    def _find_existing(self, product: Product) -> None:
        expected_sku = _source_sku(product)
        query = urlencode({"sku": expected_sku, "status": "any", "per_page": 2})
        existing = self._request("GET", "/wp-json/wc/v3/products?" + query)
        if not isinstance(existing, list):
            raise WooCommerceDraftError("woocommerce_invalid_response")
        if any(not isinstance(row, dict) or row.get("sku") != expected_sku for row in existing):
            # A store customization can disable SKU filtering and return unrelated products.
            # Never attach those IDs to this import or proceed without a reliable lookup.
            raise WooCommerceDraftError("woocommerce_invalid_response")
        if existing:
            identifier = str(_resource_id(existing[0]))
            raise WooCommerceDraftError(
                "woocommerce_existing_product",
                store_id=identifier,
                store_url=self.product_url(identifier),
            )

    def _term(self, kind: str, name: str) -> int:
        route = f"/wp-json/wc/v3/products/{kind}"
        for page in range(1, 11):
            query = urlencode(
                {"search": name, "hide_empty": "false", "per_page": 100, "page": page}
            )
            rows = self._request("GET", route + "?" + query)
            if not isinstance(rows, list):
                raise WooCommerceDraftError("woocommerce_invalid_response")
            matches = [
                row
                for row in rows
                if isinstance(row, dict)
                and html.unescape(str(row.get("name", ""))).strip().casefold() == name.casefold()
            ]
            if len(matches) > 1:
                raise WooCommerceDraftError("woocommerce_ambiguous_term")
            if matches:
                return _resource_id(matches[0])
            if len(rows) < 100:
                return _resource_id(self._request("POST", route, {"name": name}))
        raise WooCommerceDraftError("woocommerce_term_search_limit")

    @staticmethod
    def _verify_draft(result: object, *, parent: bool) -> None:
        _resource_id(result)
        if result.get("status") != "draft" or (  # type: ignore[union-attr]
            parent and result.get("catalog_visibility") != "hidden"  # type: ignore[union-attr]
        ):
            raise WooCommerceDraftError("woocommerce_draft_state_unconfirmed")

    def create_hidden_draft(self, product: Product, listing: Listing) -> str:
        identifier: str | None = None
        write_started = False
        try:
            payload = self.build_payload(product, listing)
            urls = tuple(
                dict.fromkeys(
                    (*product.images, *(v.image_url for v in product.variants if v.image_url))
                )
            )
            if len(urls) > MAX_EXPORT_IMAGES:
                raise WooCommerceDraftError("woocommerce_image_limit")
            if urls and not (self._media_username and self._media_application_password):
                raise WooCommerceDraftError("wordpress_media_credentials_required")
            self._find_existing(product)
            with TemporaryDirectory(prefix="catalogflow-draft-images-") as directory:
                image_paths: dict[str, Path] = {}
                # Export every authorized image; the bounded helper must not silently truncate.
                for offset in range(0, len(urls), MAX_IMAGES):
                    batch = urls[offset : offset + MAX_IMAGES]
                    paths = materialize_authorized_images(batch, Path(directory) / str(offset))
                    if len(paths) != len(batch):
                        raise WooCommerceDraftError("woocommerce_image_download_failed")
                    # Avoid reusing short download names across products or image batches.
                    # Public upload names contain only a fresh numeric ID and extension.
                    upload_paths = [
                        path.rename(path.with_name(f"{uuid.uuid4().int}{path.suffix}"))
                        for path in paths
                    ]
                    image_paths.update(zip(batch, upload_paths, strict=True))
                write_started = True
                result = self._request("POST", "/wp-json/wc/v3/products", payload)
                identifier = str(_resource_id(result))
                self._verify_draft(result, parent=True)
                image_ids = {
                    url: _resource_id(
                        self._request(
                            "POST", f"/wp-json/wp/v2/media?post={identifier}", image_path=path
                        )
                    )
                    for url, path in image_paths.items()
                }
                update: dict[str, object] = {
                    "status": "draft",
                    "catalog_visibility": "hidden",
                    "categories": [{"id": self._term("categories", listing.category.strip())}],
                    "tags": [
                        {"id": self._term("tags", tag)} for tag in dict.fromkeys(listing.tags)
                    ],
                    "images": [{"id": image_ids[url]} for url in urls],
                }
                self._verify_draft(
                    self._request("PUT", f"/wp-json/wc/v3/products/{identifier}", update),
                    parent=True,
                )
                if len(product.variants) > 1:
                    for variant in product.variants:
                        variation = self.build_variation_payload(product, listing, variant)
                        if variant.image_url:
                            variation["image"] = {"id": image_ids[variant.image_url]}
                        self._verify_draft(
                            self._request(
                                "POST",
                                f"/wp-json/wc/v3/products/{identifier}/variations",
                                variation,
                            ),
                            parent=False,
                        )
                return identifier
        except Exception as exc:
            code = (
                exc.code if isinstance(exc, WooCommerceDraftError) else "woocommerce_draft_failed"
            )
            if isinstance(exc, WooCommerceDraftError) and exc.store_id is not None:
                identifier = exc.store_id
            raise WooCommerceDraftError(
                code,
                store_id=identifier,
                store_url=self.product_url(identifier) if identifier is not None else None,
                write_started=write_started or identifier is not None,
            ) from None

    @staticmethod
    def build_payload(product: Product, listing: Listing) -> dict[str, object]:
        variants = product.variants
        if not 1 <= len(variants) <= MAX_VARIANTS:
            raise WooCommerceDraftError("woocommerce_variant_limit")
        skus = [variant.sku for variant in variants]
        if len(set(skus)) != len(skus) or not all(sku.strip() for sku in skus):
            raise WooCommerceDraftError("woocommerce_invalid_variants")
        if set(listing.prices) != set(skus) or any(
            isinstance(price, bool) or not math.isfinite(price) or price < 0
            for price in listing.prices.values()
        ):
            raise WooCommerceDraftError("woocommerce_invalid_prices")
        if not listing.category.strip() or any(not tag.strip() for tag in listing.tags):
            raise WooCommerceDraftError("woocommerce_invalid_terms")
        attribute_names = set(variants[0].attributes)
        if any(
            not name.strip() or not value.strip() or name != name.strip() or value != value.strip()
            for variant in variants
            for name, value in variant.attributes.items()
        ) or len({name.casefold() for name in attribute_names}) != len(attribute_names):
            raise WooCommerceDraftError("woocommerce_invalid_variants")
        if len(variants) > 1 and (
            not attribute_names
            or any(set(variant.attributes) != attribute_names for variant in variants)
            or len(
                {
                    tuple(
                        sorted(
                            (name.casefold(), value.casefold())
                            for name, value in v.attributes.items()
                        )
                    )
                    for v in variants
                }
            )
            != len(variants)
        ):
            # Never turn missing/duplicate options into wildcard variations.
            raise WooCommerceDraftError("woocommerce_invalid_variants")
        attributes = [
            {
                "name": name,
                "visible": True,
                "variation": len(variants) > 1,
                "options": list(dict.fromkeys(v.attributes[name] for v in variants)),
            }
            for name in variants[0].attributes
        ]
        payload: dict[str, object] = {
            "name": listing.title,
            "type": "variable" if len(variants) > 1 else "simple",
            "status": "draft",
            "catalog_visibility": "hidden",
            "description": listing.description_html,
            "sku": _source_sku(product),
            "attributes": attributes,
            "meta_data": [
                {"key": "catalogflow_source", "value": product.source},
                {"key": "catalogflow_source_id", "value": product.source_id},
            ],
        }
        if len(variants) == 1:
            payload["regular_price"] = f"{listing.prices[variants[0].sku]:.2f}"
        return payload

    @staticmethod
    def build_variation_payload(
        product: Product, listing: Listing, variant: Variant
    ) -> dict[str, object]:
        return {
            "status": "draft",
            "sku": _source_sku(product, variant),
            "regular_price": f"{listing.prices[variant.sku]:.2f}",
            "attributes": [
                {"name": name, "option": value} for name, value in variant.attributes.items()
            ],
            "meta_data": [{"key": "catalogflow_variant_sku", "value": variant.sku}],
        }
