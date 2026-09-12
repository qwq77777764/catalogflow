import io
import json
import urllib.request
from datetime import date
from email.message import Message

import pytest

from catalogflow.exchange_rates import (
    CACHE_TTL_SECONDS,
    EXCHANGE_RATE_URL,
    MAX_RESPONSE_BYTES,
    REQUEST_TIMEOUT_SECONDS,
    SUPPORTED_CURRENCIES,
    ExchangeRateService,
    ExchangeRatesUnavailable,
)


def rates_payload():
    return {
        "amount": 1.0,
        "base": "USD",
        "date": "2026-09-11",
        "rates": {
            "CNY": 7.0, "EUR": 0.9, "GBP": 0.8, "JPY": 150.0, "CAD": 1.4,
            "AUD": 1.5, "HKD": 7.8, "SGD": 1.3, "CHF": 0.8, "NZD": 1.6,
            "OTHER": 123,
        },
    }


def service_for(payload):
    return ExchangeRateService(
        fetch=lambda: json.dumps(payload).encode(), today=lambda: date(2026, 9, 12)
    )


def test_exchange_rates_are_usd_reference_data_with_only_supported_currencies():
    result = service_for(rates_payload()).latest()
    assert result == {
        "base": "USD",
        "date": "2026-09-11",
        "rates": {"USD": 1.0, **{
            key: value for key, value in rates_payload()["rates"].items() if key != "OTHER"
        }},
        "provider": "Frankfurter",
        "source_url": "https://frankfurter.dev/",
    }
    assert tuple(result["rates"]) == SUPPORTED_CURRENCIES


@pytest.mark.parametrize(
    "value", [None, True, False, 0, -1, "7.1", float("inf"), float("nan"), 10**1000]
)
def test_exchange_rates_reject_invalid_or_missing_currency_values(value):
    payload = rates_payload()
    if value is None:
        del payload["rates"]["CNY"]
    else:
        payload["rates"]["CNY"] = value
    with pytest.raises(ExchangeRatesUnavailable, match="^exchange_rates_unavailable$"):
        service_for(payload).latest()


@pytest.mark.parametrize(
    "field,value",
    [
        ("base", "EUR"), ("base", None), ("date", "2026-09-13"),
        ("date", "2026-02-30"), ("date", "20260911"), ("date", "2026-9-11"),
        ("date", None), ("rates", []), ("amount", 2), ("amount", True),
    ],
)
def test_exchange_rates_reject_invalid_base_date_and_structure(field, value):
    payload = rates_payload()
    payload[field] = value
    with pytest.raises(ExchangeRatesUnavailable, match="^exchange_rates_unavailable$"):
        service_for(payload).latest()


@pytest.mark.parametrize(
    "data", [b"not json", b"[]", b"\xff", b" " * (MAX_RESPONSE_BYTES + 1)],
    ids=["invalid-json", "array", "invalid-utf8", "oversized"],
)
def test_exchange_rates_reject_malformed_or_oversized_payloads(data):
    service = ExchangeRateService(fetch=lambda: data)
    with pytest.raises(ExchangeRatesUnavailable, match="^exchange_rates_unavailable$"):
        service.latest()


def test_exchange_rates_cache_is_lazy_bounded_and_not_returned_after_refresh_failure():
    elapsed = 0
    calls = 0

    def fetch():
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("Synthetic private network detail must not escape")
        return json.dumps(rates_payload()).encode()

    service = ExchangeRateService(
        fetch=fetch, clock=lambda: elapsed, today=lambda: date(2026, 9, 12)
    )
    assert calls == 0
    first = service.latest()
    first["rates"]["CNY"] = 999
    elapsed = CACHE_TTL_SECONDS - 1
    assert service.latest()["rates"]["CNY"] == 7
    assert calls == 1
    elapsed = CACHE_TTL_SECONDS
    with pytest.raises(ExchangeRatesUnavailable) as failure:
        service.latest()
    assert str(failure.value) == "exchange_rates_unavailable"
    assert failure.value.__suppress_context__
    assert calls == 2
    assert service.latest()["rates"]["CNY"] == 7
    assert calls == 3


class FakeResponse(io.BytesIO):
    def __init__(self, data, *, url=EXCHANGE_RATE_URL, status=200, **headers):
        super().__init__(data)
        self.url = url
        self.status = status
        self.headers = Message()
        self.headers["Content-Type"] = headers.pop("content_type", "application/json")
        for name, value in headers.items():
            self.headers[name] = value
        self.requested_size = None

    def geturl(self):
        return self.url

    def read(self, size=-1):
        self.requested_size = size
        return super().read(size)


def fake_opener(monkeypatch, response):
    observed = {}

    class FakeOpener:
        def open(self, request, *, timeout):
            observed.update(request=request, timeout=timeout)
            return response

    def build_opener(handler):
        observed["handler"] = handler
        return FakeOpener()

    monkeypatch.setattr(urllib.request, "build_opener", build_opener)
    return observed


def test_exchange_rate_download_is_fixed_public_https_bounded_and_has_no_user_data(monkeypatch):
    response = FakeResponse(json.dumps(rates_payload()).encode())
    observed = fake_opener(monkeypatch, response)
    result = ExchangeRateService(today=lambda: date(2026, 9, 12)).latest()
    request = observed["request"]
    assert request.full_url == EXCHANGE_RATE_URL
    assert request.get_method() == "GET"
    assert request.data is None
    assert dict(request.header_items()) == {
        "Accept": "application/json", "User-agent": "CatalogFlow"
    }
    assert observed["timeout"] == REQUEST_TIMEOUT_SECONDS
    assert response.requested_size == MAX_RESPONSE_BYTES + 1
    assert result["rates"]["USD"] == 1
    with pytest.raises(ExchangeRatesUnavailable):
        observed["handler"].redirect_request(
            request, response, 302, "Moved", {}, "http://127.0.0.1/private"
        )


@pytest.mark.parametrize(
    "options,data",
    [
        ({"url": "https://other.example/latest"}, b"{}"),
        ({"status": 302}, b"{}"),
        ({"content_type": "text/html"}, b"{}"),
        ({"Content-Length": str(MAX_RESPONSE_BYTES + 1)}, b"{}"),
        ({"Content-Length": "invalid"}, b"{}"),
        ({}, b" " * (MAX_RESPONSE_BYTES + 1)),
    ],
    ids=["changed-url", "redirect", "html", "oversized-header", "invalid-header", "oversized-body"],
)
def test_exchange_rate_download_rejects_changed_target_or_unbounded_response(
    monkeypatch, options, data
):
    fake_opener(monkeypatch, FakeResponse(data, **options))
    with pytest.raises(ExchangeRatesUnavailable, match="^exchange_rates_unavailable$"):
        ExchangeRateService().latest()
