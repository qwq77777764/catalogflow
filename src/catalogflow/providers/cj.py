"""Authorized CJdropshipping API source adapter.

The adapter exchanges the operator's own API key for an access token, fetches one
explicitly selected product, and normalizes the response into CatalogFlow's
provider-neutral Product model. Secrets and raw responses are never logged.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from ..models import Product, Variant

_CJ_API_BASE = "https://developers.cjdropshipping.com/api2.0/v1"
_MAX_RESPONSE_BYTES = 2 * 1024 * 1024
_UUID_PATTERN = (
    r"[A-Fa-f0-9]{8}-[A-Fa-f0-9]{4}-[A-Fa-f0-9]{4}-"
    r"[A-Fa-f0-9]{4}-[A-Fa-f0-9]{12}"
)
_PID_PATTERN = rf"(?:{_UUID_PATTERN}|\d{{10,30}})"
_PID_RE = re.compile(_PID_PATTERN)
_PATH_PID_RE = re.compile(rf"(?:^|[-_/])p-({_PID_PATTERN})(?:\.html|/|$)", re.I)


class CjApiError(RuntimeError):
    """A redacted CJ API or normalization failure."""


class CjTransport(Protocol):
    """Injectable JSON transport used by production code and contract tests."""

    def request_json(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        payload: Mapping[str, object] | None = None,
    ) -> dict[str, Any]: ...


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        raise CjApiError("CJ API redirected unexpectedly; refusing to forward credentials")


class UrllibCjTransport:
    """Small fail-closed HTTPS transport with bounded JSON responses."""

    def __init__(self, *, timeout: float = 20.0) -> None:
        self.timeout = timeout
        self._opener = build_opener(_RejectRedirects())

    def request_json(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        payload: Mapping[str, object] | None = None,
    ) -> dict[str, Any]:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != "developers.cjdropshipping.com":
            raise CjApiError("CJ API transport refused an unexpected endpoint")

        body = None
        request_headers = {**headers, "Accept": "application/json"}
        if payload is not None:
            body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
        request = Request(  # noqa: S310 - exact HTTPS host was allowlisted above
            url, data=body, headers=request_headers, method=method
        )
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                raw = response.read(_MAX_RESPONSE_BYTES + 1)
        except CjApiError:
            raise
        except HTTPError as exc:
            raise CjApiError(_http_error_message(exc.code)) from None
        except (URLError, TimeoutError, OSError):
            raise CjApiError("CJ API could not be reached") from None

        if len(raw) > _MAX_RESPONSE_BYTES:
            raise CjApiError("CJ API response exceeded the safe size limit")
        try:
            result = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise CjApiError("CJ API returned an invalid JSON response") from None
        if not isinstance(result, dict):
            raise CjApiError("CJ API returned an unexpected response shape")
        return result


class CjApiSource:
    """Normalize one authorized CJ product-detail response into Product."""

    def __init__(self, api_key: str, *, transport: CjTransport | None = None) -> None:
        if not api_key.strip():
            raise CjApiError("CJ API key is not configured")
        self._api_key = api_key.strip()
        self._transport = transport or UrllibCjTransport()
        self._access_token: str | None = None

    @classmethod
    def from_environment(cls, *, transport: CjTransport | None = None) -> CjApiSource:
        return cls(os.environ.get("CJ_API_KEY", ""), transport=transport)

    def fetch(self, reference: str) -> Product:
        product_id = extract_cj_product_id(reference)
        token = self._get_access_token()
        response = self._transport.request_json(
            "POST",
            f"{_CJ_API_BASE}/product/productDetail/query",
            headers={"CJ-Access-Token": token},
            payload={"id": product_id},
        )
        data = _response_data(response, operation="product detail")
        return _normalize_product(data, expected_id=product_id)

    def _get_access_token(self) -> str:
        if self._access_token:
            return self._access_token
        response = self._transport.request_json(
            "POST",
            f"{_CJ_API_BASE}/authentication/getAccessToken",
            headers={},
            payload={"apiKey": self._api_key},
        )
        data = _response_data(response, operation="authentication")
        token = str(data.get("accessToken") or "").strip()
        if not token:
            raise CjApiError("CJ authentication response did not contain an access token")
        self._access_token = token
        return token


def extract_cj_product_id(reference: str) -> str:
    """Extract a CJ PID from a raw identifier or an authorized product-detail URL."""

    value = reference.strip()
    if not value or len(value) > 2048:
        raise CjApiError("CJ product reference is missing or too long")
    if _PID_RE.fullmatch(value):
        return value

    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not (
        host == "cjdropshipping.com" or host.endswith(".cjdropshipping.com")
    ):
        raise CjApiError("CJ reference must be a product ID or an official HTTPS product URL")

    query = parse_qs(parsed.query)
    for name in ("pid", "productId", "product_id"):
        candidate = str((query.get(name) or [""])[0]).strip()
        if _PID_RE.fullmatch(candidate):
            return candidate

    path_match = _PATH_PID_RE.search(parsed.path)
    if path_match:
        return path_match.group(1)
    candidates = _PID_RE.findall(parsed.path)
    if len(candidates) == 1:
        return candidates[0]
    raise CjApiError("Could not find one unambiguous CJ product ID in the reference")


def _response_data(response: Mapping[str, Any], *, operation: str) -> dict[str, Any]:
    code = response.get("code")
    succeeded = response.get("result") is True or response.get("success") is True
    if code not in {0, 200, "0", "200"} or not succeeded:
        raise CjApiError(_api_error_message(code, operation))
    data = response.get("data")
    if not isinstance(data, dict):
        raise CjApiError(f"CJ {operation} response did not contain an object")
    return data


def _normalize_product(data: Mapping[str, Any], *, expected_id: str) -> Product:
    source_id = _text(data, "id", "pid")
    if not source_id:
        raise CjApiError("CJ product detail is missing its product ID")
    if source_id.casefold() != expected_id.casefold():
        raise CjApiError("CJ product detail returned a different product ID")

    title = _text(data, "nameen", "productNameEn")
    if not title:
        raise CjApiError("CJ product detail is missing an English title")

    raw_variants = data.get("stanProducts") or data.get("variants")
    if not isinstance(raw_variants, list) or not raw_variants:
        raise CjApiError("CJ product detail did not contain any variants")
    dimension_names = _text(data, "variantkeyen", "productKeyEn")
    variants = tuple(
        _normalize_variant(row, dimension_names=dimension_names)
        for row in raw_variants
        if isinstance(row, Mapping)
    )
    if not variants:
        raise CjApiError("CJ product detail did not contain usable variants")

    return Product(
        source="cj",
        source_id=source_id,
        title=title,
        currency="USD",
        variants=variants,
        images=_normalized_images(data, raw_variants),
        facts=_normalized_facts(data),
    )


def _normalize_variant(row: Mapping[str, Any], *, dimension_names: str) -> Variant:
    sku = _text(row, "sku", "variantSku")
    if not sku:
        raise CjApiError("CJ product detail contains a variant without a SKU")
    raw_cost = row.get("sellprice", row.get("variantSellPrice"))
    try:
        cost = float(raw_cost)
    except (TypeError, ValueError):
        raise CjApiError("CJ product detail contains a variant without a valid USD cost") from None
    if cost < 0:
        raise CjApiError("CJ product detail contains a negative variant cost")
    option_values = _text(row, "variantkey", "variantKey")
    return Variant(
        sku=sku,
        cost=cost,
        attributes=_variant_attributes(dimension_names, option_values),
    )


def _variant_attributes(names: str, values: str) -> dict[str, str]:
    if not values:
        return {}
    clean_names = [part.strip().title() for part in names.split("-") if part.strip()]
    clean_values = [part.strip() for part in values.split("-") if part.strip()]
    if clean_names and len(clean_names) == len(clean_values):
        return dict(zip(clean_names, clean_values, strict=True))
    return {"Options": values}


def _normalized_images(
    data: Mapping[str, Any], raw_variants: list[object]
) -> tuple[str, ...]:
    candidates: list[object] = []
    image_list = data.get("newImgList") or data.get("productImageSet")
    if isinstance(image_list, list):
        candidates.extend(image_list)
    raw_images = data.get("img")
    if isinstance(raw_images, str):
        candidates.extend(part.strip() for part in raw_images.split(","))
    candidates.extend((data.get("bigimg"), data.get("bigImage")))
    for row in raw_variants:
        if isinstance(row, Mapping):
            candidates.extend((row.get("img"), row.get("variantImage")))

    images: list[str] = []
    for candidate in candidates:
        value = str(candidate or "").strip()
        parsed = urlparse(value)
        if parsed.scheme == "https" and parsed.hostname and value not in images:
            images.append(value)
    return tuple(images)


def _normalized_facts(data: Mapping[str, Any]) -> dict[str, str]:
    fields = {
        "category": _text(data, "category", "categoryName"),
        "material": _text(data, "materialen", "materialNameEn", "materialNameEnSet"),
        "unit": _text(data, "unit", "productUnit"),
        "product_weight_g": _text(data, "weight", "productWeight"),
        "package_weight_g": _text(data, "packweight", "packingWeight"),
        "packaging": _text(data, "packingen", "packingNameEn", "packingNameEnSet"),
        "logistics_properties": _text(data, "propertyen", "productProEn", "productProEnSet"),
        "customs_code": _text(data, "entryCode"),
        "customs_name": _text(data, "entryNameEn"),
    }
    return {name: value for name, value in fields.items() if value}


def _text(data: Mapping[str, Any], *names: str) -> str:
    for name in names:
        value = data.get(name)
        if isinstance(value, list):
            value = ", ".join(str(item).strip() for item in value if str(item).strip())
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _http_error_message(status: int) -> str:
    if status in {401, 403}:
        return "CJ API authentication or account authorization failed"
    if status == 404:
        return "CJ API product or endpoint was not found"
    if status in {402, 406, 429}:
        return "CJ API rate limit or quota was reached"
    return f"CJ API request failed with HTTP status {status}"


def _api_error_message(code: object, operation: str) -> str:
    if str(code) in {"401", "403", "1600001", "1600002"}:
        return "CJ API authentication or account authorization failed"
    if str(code) in {"402", "406", "429"}:
        return "CJ API rate limit or quota was reached"
    safe_code = re.sub(r"[^A-Za-z0-9_.-]", "", str(code or "unknown"))[:32]
    return f"CJ {operation} request was rejected (code {safe_code})"
