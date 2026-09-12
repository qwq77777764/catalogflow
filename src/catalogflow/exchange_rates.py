"""On-demand public USD reference rates; amounts never leave the dashboard."""

from __future__ import annotations

import json
import math
import re
import threading
import time
import urllib.request
from collections.abc import Callable
from datetime import UTC, date, datetime
from http.client import HTTPException

EXCHANGE_RATE_URL = "https://api.frankfurter.dev/v1/latest?base=USD"
SOURCE_URL = "https://frankfurter.dev/"
SUPPORTED_CURRENCIES = (
    "USD", "CNY", "EUR", "GBP", "JPY", "CAD", "AUD", "HKD", "SGD", "CHF", "NZD"
)
MAX_RESPONSE_BYTES = 32 * 1024
REQUEST_TIMEOUT_SECONDS = 8
CACHE_TTL_SECONDS = 60 * 60


class ExchangeRatesUnavailable(RuntimeError):
    """Public reference rates could not be fetched or validated."""


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # A provider redirect must never turn this fixed URL into a downloader.
        raise ExchangeRatesUnavailable("exchange_rates_unavailable")


def _download_rates() -> bytes:
    opener = urllib.request.build_opener(_NoRedirects())
    request = urllib.request.Request(  # noqa: S310 - fixed public HTTPS endpoint
        EXCHANGE_RATE_URL,
        headers={"Accept": "application/json", "User-Agent": "CatalogFlow"},
        method="GET",
    )
    with opener.open(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:  # noqa: S310
        if response.status != 200 or response.geturl() != EXCHANGE_RATE_URL:
            raise ExchangeRatesUnavailable("exchange_rates_unavailable")
        if response.headers.get_content_type() != "application/json":
            raise ExchangeRatesUnavailable("exchange_rates_unavailable")
        length = response.headers.get("Content-Length")
        if length is not None and (not length.isdigit() or int(length) > MAX_RESPONSE_BYTES):
            raise ExchangeRatesUnavailable("exchange_rates_unavailable")
        data = response.read(MAX_RESPONSE_BYTES + 1)
        if len(data) > MAX_RESPONSE_BYTES:
            raise ExchangeRatesUnavailable("exchange_rates_unavailable")
        return data


def _validated_snapshot(data: bytes, today: date) -> dict[str, object]:
    if len(data) > MAX_RESPONSE_BYTES:
        raise ValueError("Oversized rates response")
    payload = json.loads(data)
    if not isinstance(payload, dict) or payload.get("base") != "USD":
        raise ValueError("Invalid base currency")
    amount = payload.get("amount", 1)
    if isinstance(amount, bool) or not isinstance(amount, (int, float)) or amount != 1:
        raise ValueError("Invalid rate unit")
    rate_date = payload.get("date")
    if not isinstance(rate_date, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", rate_date):
        raise ValueError("Invalid rate date")
    if date.fromisoformat(rate_date) > today:
        raise ValueError("Future rate date")
    values = payload.get("rates")
    if not isinstance(values, dict):
        raise ValueError("Invalid rates")
    rates = {"USD": 1.0}
    for currency in SUPPORTED_CURRENCIES[1:]:
        value = values.get(currency)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value <= 0
            or value > 1000000
        ):
            raise ValueError("Invalid currency rate")
        rates[currency] = float(value)
    if "USD" in values and (
        isinstance(values["USD"], bool)
        or not isinstance(values["USD"], (int, float))
        or values["USD"] != 1
    ):
        raise ValueError("Invalid USD rate")
    return {
        "base": "USD",
        "date": rate_date,
        "rates": rates,
        "provider": "Frankfurter",
        "source_url": SOURCE_URL,
    }


class ExchangeRateService:
    """Fetch on explicit use, cache briefly in memory, and fail closed after expiry."""

    def __init__(
        self,
        *,
        fetch: Callable[[], bytes] | None = None,
        clock: Callable[[], float] = time.monotonic,
        today: Callable[[], date] | None = None,
    ) -> None:
        self._fetch = fetch or _download_rates
        self._clock = clock
        self._today = today or (lambda: datetime.now(UTC).date())
        self._cached: dict[str, object] | None = None
        self._expires_at = 0.0
        self._lock = threading.Lock()

    def latest(self) -> dict[str, object]:
        with self._lock:
            if self._cached is None or self._clock() >= self._expires_at:
                # Clear first: a failed refresh cannot silently return expired rates.
                self._cached = None
                try:
                    snapshot = _validated_snapshot(self._fetch(), self._today())
                except (
                    OSError, HTTPException, ValueError, OverflowError, ExchangeRatesUnavailable
                ):
                    raise ExchangeRatesUnavailable("exchange_rates_unavailable") from None
                self._cached = snapshot
                self._expires_at = self._clock() + CACHE_TTL_SECONDS
            # Callers cannot mutate the cached currency map.
            return {**self._cached, "rates": dict(self._cached["rates"])}
