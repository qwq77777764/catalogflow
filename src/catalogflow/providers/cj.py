"""Authorized CJdropshipping API source adapter.

The adapter exchanges the operator's own API key for an access token, fetches one
explicitly selected product, and normalizes the response into CatalogFlow's
provider-neutral Product model. Secrets and raw responses are never logged.
"""

from __future__ import annotations

import json
import math
import os
import re
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from ..models import Product, ShippingQuote, Variant

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


@dataclass(frozen=True, slots=True)
class _FreightOption:
    row: Mapping[str, Any]
    cost: float


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

    def __init__(self, *, timeout: float = 20.0, minimum_interval: float = 1.0) -> None:
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("CJ API timeout must be a finite positive number")
        if not math.isfinite(minimum_interval) or minimum_interval <= 0:
            raise ValueError("CJ API request interval must be a finite positive number")
        self.timeout = timeout
        self.minimum_interval = minimum_interval
        self._opener = build_opener(_RejectRedirects())
        self._rate_lock = threading.Lock()
        self._last_request_at = 0.0

    def request_json(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        payload: Mapping[str, object] | None = None,
    ) -> dict[str, Any]:
        parsed = urlparse(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "developers.cjdropshipping.com"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port not in {None, 443}
        ):
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
            self._respect_rate_limit()
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

    def _respect_rate_limit(self) -> None:
        with self._rate_lock:
            remaining = self.minimum_interval - (time.monotonic() - self._last_request_at)
            if remaining > 0:
                time.sleep(remaining)
            self._last_request_at = time.monotonic()


class CjApiSource:
    """Normalize one authorized CJ product-detail response into Product."""

    def __init__(
        self,
        api_key: str,
        *,
        origin_country: str = "CN",
        destination_country: str = "US",
        destination_zip: str = "",
        freight_quantity: int = 1,
        preferred_logistics: str = "",
        max_freight_quotes: int = 20,
        transport: CjTransport | None = None,
    ) -> None:
        if not api_key.strip():
            raise CjApiError("CJ API key is not configured")
        if freight_quantity < 1 or freight_quantity > 100:
            raise CjApiError("CJ freight quantity must be between 1 and 100")
        if max_freight_quotes < 1 or max_freight_quotes > 100:
            raise CjApiError("CJ freight quote limit must be between 1 and 100")
        clean_zip = destination_zip.strip()
        if len(clean_zip) > 20 or (clean_zip and not re.fullmatch(r"[A-Za-z0-9 -]+", clean_zip)):
            raise CjApiError("CJ destination ZIP/postal code is invalid")
        self._api_key = api_key.strip()
        self._origin_country = _country_code(origin_country, "origin")
        self._destination_country = _country_code(destination_country, "destination")
        self._destination_zip = clean_zip
        self._freight_quantity = freight_quantity
        self._preferred_logistics = preferred_logistics.strip()
        self._max_freight_quotes = max_freight_quotes
        self._transport = transport or UrllibCjTransport()
        self._access_token: str | None = None

    @classmethod
    def from_environment(cls, *, transport: CjTransport | None = None) -> CjApiSource:
        return cls(
            os.environ.get("CJ_API_KEY", ""),
            origin_country=os.environ.get("CJ_ORIGIN_COUNTRY_CODE", "CN"),
            destination_country=os.environ.get("CJ_TARGET_COUNTRY_CODE", "US"),
            destination_zip=os.environ.get("CJ_TARGET_ZIP", ""),
            freight_quantity=_integer_setting("CJ_FREIGHT_QUANTITY", 1),
            preferred_logistics=os.environ.get("CJ_LOGISTICS", ""),
            max_freight_quotes=_integer_setting("CJ_MAX_FREIGHT_QUOTES", 20),
            transport=transport,
        )

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
        _normalize_product(data, expected_id=product_id)
        freight_quotes = self._freight_quotes(data, token)
        product = _normalize_product(
            data,
            expected_id=product_id,
            freight_quotes=freight_quotes,
        )
        parsed = urlparse(reference)
        source_url = ""
        if parsed.scheme == "https" and parsed.username is None and parsed.password is None:
            query = parse_qs(parsed.query, max_num_fields=50)
            product_query = ""
            for name in ("pid", "productId", "product_id"):
                candidate = str((query.get(name) or [""])[0])
                if _PID_RE.fullmatch(candidate):
                    product_query = f"{name}={candidate}"
                    break
            source_url = parsed._replace(query=product_query, fragment="").geturl()
        return replace(product, source_url=source_url)

    def _freight_quotes(
        self,
        product_data: Mapping[str, Any],
        token: str,
    ) -> dict[str, ShippingQuote]:
        rows = _variant_rows(product_data)
        if len(rows) > self._max_freight_quotes:
            raise CjApiError(
                "CJ product has more variants than the configured freight quote limit"
            )

        quotes: dict[str, ShippingQuote] = {}
        for row in rows:
            variant_id = _text(row, "id", "vid")
            if not variant_id:
                raise CjApiError("CJ product variant is missing the ID required for freight")
            payload: dict[str, object] = {
                "startCountryCode": self._origin_country,
                "endCountryCode": self._destination_country,
                "products": [
                    {
                        "vid": variant_id,
                        "quantity": self._freight_quantity,
                    }
                ],
            }
            if self._destination_zip:
                payload["zip"] = self._destination_zip
            response = self._transport.request_json(
                "POST",
                f"{_CJ_API_BASE}/logistic/freightCalculate",
                headers={"CJ-Access-Token": token},
                payload=payload,
            )
            options = _response_value(response, operation="freight calculation")
            chosen = _choose_freight_option(options, self._preferred_logistics)
            quotes[variant_id] = ShippingQuote(
                origin_country=self._origin_country,
                destination_country=self._destination_country,
                quantity=self._freight_quantity,
                method=_text(chosen.row, "logisticName", "logisticsName"),
                total_cost_usd=chosen.cost,
                estimated_days=_text(chosen.row, "logisticAging", "arrivalTime"),
            )
        return quotes

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
    data = _response_value(response, operation=operation)
    if not isinstance(data, dict):
        raise CjApiError(f"CJ {operation} response did not contain an object")
    return data


def _response_value(response: Mapping[str, Any], *, operation: str) -> object:
    code = response.get("code")
    succeeded = response.get("result") is True or response.get("success") is True
    if code not in {0, 200, "0", "200"} or not succeeded:
        raise CjApiError(_api_error_message(code, operation))
    data = response.get("data")
    if data is None:
        raise CjApiError(f"CJ {operation} response did not contain data")
    return data


def _variant_rows(data: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    value = data.get("stanProducts") or data.get("variants")
    if not isinstance(value, list) or not value:
        raise CjApiError("CJ product detail did not contain any variants")
    rows = tuple(row for row in value if isinstance(row, Mapping))
    if not rows:
        raise CjApiError("CJ product detail did not contain usable variants")
    return rows


def _choose_freight_option(value: object, preferred_logistics: str) -> _FreightOption:
    candidates: list[_FreightOption] = []
    for row in _collect_freight_options(value):
        cost = _freight_cost(row)
        method = _text(row, "logisticName", "logisticsName")
        if cost is not None and method:
            candidates.append(_FreightOption(row=row, cost=cost))
    if not candidates:
        raise CjApiError("CJ freight calculation returned no usable shipping option")

    preferred = preferred_logistics.casefold()
    if preferred:
        matches = [
            candidate
            for candidate in candidates
            if _text(candidate.row, "logisticName", "logisticsName").casefold() == preferred
        ]
        if not matches:
            raise CjApiError("Configured CJ logistics method is unavailable for a variant")
        candidates = matches
    return min(candidates, key=lambda candidate: candidate.cost)


def _collect_freight_options(value: object) -> tuple[Mapping[str, Any], ...]:
    options: list[Mapping[str, Any]] = []
    if isinstance(value, Mapping):
        if "totalPostageFee" in value or "logisticPrice" in value:
            options.append(value)
        for nested in value.values():
            options.extend(_collect_freight_options(nested))
    elif isinstance(value, list):
        for nested in value:
            options.extend(_collect_freight_options(nested))
    return tuple(options)


def _freight_cost(option: Mapping[str, Any]) -> float | None:
    if "totalPostageFee" in option:
        total = _nonnegative_number(option.get("totalPostageFee"))
        return total if total is not None and total > 0 else None
    if "logisticPrice" not in option:
        return None
    logistic = _nonnegative_number(option.get("logisticPrice"))
    taxes = _nonnegative_number(option.get("taxesFee", 0))
    clearance = _nonnegative_number(option.get("clearanceOperationFee", 0))
    if logistic is None or taxes is None or clearance is None:
        return None
    total = logistic + taxes + clearance
    return total if total > 0 else None


def _nonnegative_number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number < 0:
        return None
    return number


def _country_code(value: str, label: str) -> str:
    code = value.strip().upper()
    if not re.fullmatch(r"[A-Z]{2}", code):
        raise CjApiError(f"CJ {label} country code must contain two letters")
    return code


def _integer_setting(name: str, default: int) -> int:
    value = os.environ.get(name, "").strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        raise CjApiError(f"{name} must be an integer") from None


def _normalize_product(
    data: Mapping[str, Any],
    *,
    expected_id: str,
    freight_quotes: Mapping[str, ShippingQuote] | None = None,
) -> Product:
    source_id = _text(data, "id", "pid")
    if not source_id:
        raise CjApiError("CJ product detail is missing its product ID")
    if source_id.casefold() != expected_id.casefold():
        raise CjApiError("CJ product detail returned a different product ID")

    title = _text(data, "nameen", "productNameEn")
    if not title:
        raise CjApiError("CJ product detail is missing an English title")

    raw_variants = _variant_rows(data)
    dimension_names = _text(data, "variantkeyen", "productKeyEn")
    freight_quotes = freight_quotes or {}
    variants = tuple(
        _normalize_variant(
            row,
            dimension_names=dimension_names,
            shipping_quote=freight_quotes.get(_text(row, "id", "vid")),
        )
        for row in raw_variants
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


def _normalize_variant(
    row: Mapping[str, Any],
    *,
    dimension_names: str,
    shipping_quote: ShippingQuote | None = None,
) -> Variant:
    sku = _text(row, "sku", "variantSku")
    if not sku:
        raise CjApiError("CJ product detail contains a variant without a SKU")
    raw_cost = row.get("sellprice", row.get("variantSellPrice"))
    try:
        cost = float(raw_cost)
    except (TypeError, ValueError):
        raise CjApiError("CJ product detail contains a variant without a valid USD cost") from None
    if not math.isfinite(cost) or cost < 0:
        raise CjApiError("CJ product detail contains a non-finite or negative variant cost")
    option_values = _text(row, "variantkey", "variantKey")
    return Variant(
        sku=sku,
        cost=cost,
        attributes=_variant_attributes(dimension_names, option_values),
        shipping_quote=shipping_quote,
        image_url=_text(row, "img", "variantImage"),
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
    data: Mapping[str, Any], raw_variants: tuple[Mapping[str, Any], ...]
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
    if isinstance(code, bool):
        safe_code = "unknown"
    elif isinstance(code, int):
        safe_code = str(code)
    elif isinstance(code, str) and re.fullmatch(r"[0-9]{1,12}", code.strip()):
        safe_code = code.strip()
    else:
        safe_code = "unknown"
    if safe_code in {"401", "403", "1600001", "1600002"}:
        return "CJ API authentication or account authorization failed"
    if safe_code in {"402", "406", "429"}:
        return "CJ API rate limit or quota was reached"
    return f"CJ {operation} request was rejected"
