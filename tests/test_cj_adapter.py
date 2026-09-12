from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from catalogflow.providers import CjApiError, CjApiSource, extract_cj_product_id
from catalogflow.providers.cj import UrllibCjTransport


class FakeTransport:
    def __init__(
        self,
        product_data: dict[str, Any],
        freight_responses: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self.product_data = product_data
        self.freight_responses = freight_responses or {
            "variant-1": {
                "code": 200,
                "result": True,
                "data": [
                    {
                        "logisticName": "CJPacket Ordinary",
                        "logisticPrice": 4.71,
                        "logisticAging": "4-9",
                    },
                    {
                        "logisticName": "Synthetic Express",
                        "logisticPrice": 9.0,
                        "logisticAging": "2-4",
                    },
                ],
            },
            "variant-2": {
                "code": 200,
                "result": True,
                "data": [
                    {
                        "logisticName": "CJPacket Ordinary",
                        "totalPostageFee": 6.2,
                        "logisticPrice": 4.0,
                        "taxesFee": 1.0,
                        "clearanceOperationFee": 0.5,
                        "logisticAging": "5-10",
                    }
                ],
            },
        }
        self.calls: list[dict[str, Any]] = []

    def request_json(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        payload: Mapping[str, object] | None = None,
    ) -> dict[str, Any]:
        self.calls.append(
            {"method": method, "url": url, "headers": dict(headers), "payload": payload}
        )
        if url.endswith("/authentication/getAccessToken"):
            return {
                "code": 200,
                "result": True,
                "data": {"accessToken": "synthetic-access-token"},
            }
        if url.endswith("/logistic/freightCalculate"):
            assert payload is not None
            products = payload["products"]
            assert isinstance(products, list)
            variant_id = str(products[0]["vid"])
            return self.freight_responses[variant_id]
        return {"code": 200, "result": True, "data": self.product_data}


def synthetic_product() -> dict[str, Any]:
    return {
        "id": "1442332573555625984",
        "sku": "CJDEMO100",
        "nameen": "Synthetic Bedside Clock",
        "bigimg": "https://images.example.test/main.jpg",
        "newImgList": [
            "https://images.example.test/main.jpg",
            "https://images.example.test/detail.jpg",
        ],
        "category": "Home > Decor > Clocks",
        "materialen": "Wood, ABS",
        "packweight": "420",
        "weight": "350",
        "variantkeyen": "Color-Size",
        "propertyen": "Ordinary",
        "entryCode": "9105110000",
        "entryNameEn": "Alarm clock",
        "stanProducts": [
            {
                "id": "variant-1",
                "sku": "CJDEMO100-WAL-S",
                "sellprice": "8.25",
                "variantkey": "Walnut-Small",
                "img": "https://images.example.test/walnut.jpg",
            },
            {
                "id": "variant-2",
                "sku": "CJDEMO100-BLK-L",
                "sellprice": 9.5,
                "variantkey": "Black-Large",
                "img": "https://images.example.test/black.jpg",
            },
        ],
    }


def test_extracts_product_id_from_raw_id_and_official_urls() -> None:
    product_id = "1442332573555625984"
    uuid_product_id = "000B9312-456A-4D31-94BD-B083E2A198E8"
    assert extract_cj_product_id(product_id) == product_id
    assert extract_cj_product_id(uuid_product_id) == uuid_product_id
    assert (
        extract_cj_product_id(
            f"https://cjdropshipping.com/product/synthetic-item-p-{product_id}.html"
        )
        == product_id
    )
    assert (
        extract_cj_product_id(
            f"https://cjdropshipping.com/product/synthetic-p-{uuid_product_id}.html"
        )
        == uuid_product_id
    )
    assert (
        extract_cj_product_id(f"https://www.cjdropshipping.com/product/detail?pid={product_id}")
        == product_id
    )


def test_rejects_non_cj_urls() -> None:
    with pytest.raises(CjApiError, match="official HTTPS product URL"):
        extract_cj_product_id("https://example.com/product/1442332573555625984")


def test_fetch_authenticates_once_and_normalizes_official_detail_shape() -> None:
    transport = FakeTransport(synthetic_product())
    source = CjApiSource("synthetic-api-key", transport=transport)

    product = source.fetch("1442332573555625984")
    source.fetch("1442332573555625984")

    assert product.source == "cj"
    assert product.source_id == "1442332573555625984"
    assert product.title == "Synthetic Bedside Clock"
    assert product.currency == "USD"
    assert product.variants[0].sku == "CJDEMO100-WAL-S"
    assert product.variants[0].cost == 8.25
    assert product.variants[0].attributes == {"Color": "Walnut", "Size": "Small"}
    assert product.variants[0].shipping_quote is not None
    assert product.variants[0].shipping_quote.total_cost_usd == 4.71
    assert product.variants[0].shipping_quote.method == "CJPacket Ordinary"
    assert product.variants[1].shipping_quote is not None
    assert product.variants[1].shipping_quote.total_cost_usd == 6.2
    assert product.images == (
        "https://images.example.test/main.jpg",
        "https://images.example.test/detail.jpg",
        "https://images.example.test/walnut.jpg",
        "https://images.example.test/black.jpg",
    )
    assert product.facts["material"] == "Wood, ABS"
    assert product.facts["customs_code"] == "9105110000"
    assert len([call for call in transport.calls if "getAccessToken" in call["url"]]) == 1
    assert transport.calls[1]["headers"] == {"CJ-Access-Token": "synthetic-access-token"}
    freight_calls = [call for call in transport.calls if "freightCalculate" in call["url"]]
    assert len(freight_calls) == 4
    assert freight_calls[0]["payload"] == {
        "startCountryCode": "CN",
        "endCountryCode": "US",
        "products": [{"vid": "variant-1", "quantity": 1}],
    }


def test_freight_uses_zip_and_exact_preferred_logistics() -> None:
    transport = FakeTransport(
        synthetic_product(),
        {
            variant_id: {
                "code": 200,
                "result": True,
                "data": [
                    {
                        "logisticName": "Synthetic Express",
                        "logisticPrice": price,
                        "logisticAging": "2-4",
                    }
                ],
            }
            for variant_id, price in (("variant-1", 9.0), ("variant-2", 10.0))
        },
    )
    source = CjApiSource(
        "synthetic-api-key",
        destination_zip="10001",
        preferred_logistics="Synthetic Express",
        transport=transport,
    )

    product = source.fetch("1442332573555625984")

    quote = product.variants[0].shipping_quote
    assert quote is not None
    assert quote.method == "Synthetic Express"
    assert quote.total_cost_usd == 9.0
    freight_call = next(call for call in transport.calls if "freightCalculate" in call["url"])
    assert freight_call["payload"]["zip"] == "10001"


def test_freight_fails_closed_when_preferred_route_is_unavailable() -> None:
    source = CjApiSource(
        "synthetic-api-key",
        preferred_logistics="Missing Route",
        transport=FakeTransport(synthetic_product()),
    )

    with pytest.raises(CjApiError, match="logistics method is unavailable"):
        source.fetch("1442332573555625984")


@pytest.mark.parametrize(
    ("preferred", "freight_options", "expected_code", "expected_reason", "english_reason"),
    [
        (
            "Synthetic Missing Route",
            [{"logisticName": "Synthetic Available Route", "logisticPrice": 4.71}],
            "cj_logistics_unavailable", "该线路不可用于此变体",
            "route is unavailable for this variant",
        ),
        (
            "", [], "cj_freight_unavailable", "未返回该变体的可用运费报价",
            "No usable freight quote was returned for this variant",
        ),
    ],
)
def test_freight_failure_report_preserves_actionable_reason_without_raw_response(
    tmp_path, preferred, freight_options, expected_code, expected_reason, english_reason,
) -> None:
    from catalogflow.models import ImportRequest
    from catalogflow.pipeline import import_products
    from catalogflow.run_history import HistoryRepository

    class GeneratorThatMustNotRun:
        def generate(self, product):
            raise AssertionError("unavailable freight must stop before AI generation")

    transport = FakeTransport(
        synthetic_product(),
        {
            "variant-1": {
                "code": 200, "result": True, "data": freight_options,
                "message": "private-supplier-marker synthetic-api-key",
            },
        },
    )
    source = CjApiSource(
        "synthetic-api-key", preferred_logistics=preferred, transport=transport,
    )
    history = HistoryRepository(tmp_path)
    report = import_products(
        [ImportRequest("cj", "https://cjdropshipping.com/product/detail?pid=1442332573555625984")],
        sources={"cj": source}, generator=GeneratorThatMustNotRun(), history=history,
    )

    assert not report.ok
    assert report.items[0].status == "failed"
    assert report.items[0].errors == (expected_code,)
    assert history.read(report.run_id)["items"][0]["errors"] == [expected_code]
    report_text = Path(report.report_path).read_text(encoding="utf-8")
    assert expected_reason in report_text
    assert english_reason in report_text
    assert "核对" in report_text and "重试" in report_text
    assert "private-supplier-marker" not in report_text
    assert "synthetic-api-key" not in report_text
    assert "synthetic-access-token" not in report_text


def test_freight_quote_limit_stops_before_any_quote_call() -> None:
    transport = FakeTransport(synthetic_product())
    source = CjApiSource("synthetic-api-key", max_freight_quotes=1, transport=transport)

    with pytest.raises(CjApiError, match="freight quote limit"):
        source.fetch("1442332573555625984")

    assert not [call for call in transport.calls if "freightCalculate" in call["url"]]


def test_freight_failure_is_redacted_and_never_becomes_zero_shipping() -> None:
    responses = {
        "variant-1": {
            "code": 429,
            "result": False,
            "message": "quota error containing synthetic-api-key",
            "data": None,
        },
        "variant-2": {"code": 200, "result": True, "data": []},
    }
    source = CjApiSource(
        "synthetic-api-key",
        transport=FakeTransport(synthetic_product(), responses),
    )

    with pytest.raises(CjApiError) as caught:
        source.fetch("1442332573555625984")

    assert "synthetic-api-key" not in str(caught.value)
    assert "quota error" not in str(caught.value)


@pytest.mark.parametrize("bad_price", [0, -1, "invalid", "NaN", "Infinity"])
def test_invalid_or_zero_freight_never_becomes_a_sell_price(bad_price: object) -> None:
    responses = {
        variant_id: {
            "code": 200,
            "result": True,
            "data": [{"logisticName": "Broken Route", "logisticPrice": bad_price}],
        }
        for variant_id in ("variant-1", "variant-2")
    }
    source = CjApiSource(
        "synthetic-api-key",
        transport=FakeTransport(synthetic_product(), responses),
    )

    with pytest.raises(CjApiError, match="no usable shipping option"):
        source.fetch("1442332573555625984")


def test_rejects_mismatched_product_id() -> None:
    data = synthetic_product()
    data["id"] = "9999999999999999999"
    transport = FakeTransport(data)
    source = CjApiSource("synthetic-api-key", transport=transport)

    with pytest.raises(CjApiError, match="different product ID"):
        source.fetch("1442332573555625984")
    assert not [call for call in transport.calls if "freightCalculate" in call["url"]]


def test_api_failure_does_not_echo_provider_message_or_api_key() -> None:
    class FailingTransport(FakeTransport):
        def request_json(self, method, url, *, headers, payload=None):
            return {
                "code": 401,
                "result": False,
                "message": "bad synthetic-api-key",
                "data": None,
            }

    source = CjApiSource("synthetic-api-key", transport=FailingTransport(synthetic_product()))
    with pytest.raises(CjApiError) as caught:
        source.fetch("1442332573555625984")

    assert "synthetic-api-key" not in str(caught.value)
    assert "bad" not in str(caught.value)


def test_unknown_provider_code_is_not_echoed() -> None:
    class FailingTransport(FakeTransport):
        def request_json(self, method, url, *, headers, payload=None):
            return {
                "code": "token-like-provider-value",
                "result": False,
                "data": None,
            }

    source = CjApiSource("synthetic-api-key", transport=FailingTransport(synthetic_product()))
    with pytest.raises(CjApiError) as caught:
        source.fetch("1442332573555625984")

    assert "token-like-provider-value" not in str(caught.value)
    assert str(caught.value) == "CJ authentication request was rejected"


def test_unknown_numeric_provider_code_is_not_echoed() -> None:
    class FailingTransport(FakeTransport):
        def request_json(self, method, url, *, headers, payload=None):
            return {"code": 9876543210, "result": False, "data": None}

    source = CjApiSource("synthetic-api-key", transport=FailingTransport(synthetic_product()))
    with pytest.raises(CjApiError) as caught:
        source.fetch("1442332573555625984")

    assert "9876543210" not in str(caught.value)
    assert str(caught.value) == "CJ authentication request was rejected"


@pytest.mark.parametrize("setting", [0, -1, float("nan"), float("inf")])
def test_production_transport_rejects_invalid_rate_limit_settings(setting: float) -> None:
    with pytest.raises(ValueError, match="request interval"):
        UrllibCjTransport(minimum_interval=setting)


def test_production_transport_paces_request_starts(monkeypatch) -> None:
    transport = UrllibCjTransport(minimum_interval=1.0)
    ticks = iter((100.0, 100.0, 100.25, 101.0))
    sleeps: list[float] = []
    monkeypatch.setattr("catalogflow.providers.cj.time.monotonic", lambda: next(ticks))
    monkeypatch.setattr("catalogflow.providers.cj.time.sleep", sleeps.append)

    transport._respect_rate_limit()
    transport._respect_rate_limit()

    assert sleeps == [0.75]
