from collections.abc import Mapping
from typing import Any

import pytest

from catalogflow.providers import CjApiError, CjApiSource, extract_cj_product_id


class FakeTransport:
    def __init__(self, product_data: dict[str, Any]) -> None:
        self.product_data = product_data
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


def test_rejects_mismatched_product_id() -> None:
    data = synthetic_product()
    data["id"] = "9999999999999999999"
    source = CjApiSource("synthetic-api-key", transport=FakeTransport(data))

    with pytest.raises(CjApiError, match="different product ID"):
        source.fetch("1442332573555625984")


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
