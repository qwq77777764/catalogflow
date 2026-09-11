import json

import pytest

from catalogflow.selection_queue import SelectionQueue, normalize_selection


def test_selection_normalizes_tracking_data_out_of_product_url() -> None:
    selection = normalize_selection(
        "alibaba",
        "https://www.alibaba.com/product-detail/Synthetic-Clock_1600000000000.html?spm=tracking#details",
        "Synthetic Clock - Alibaba.com",
    )

    assert selection.product_url == (
        "https://www.alibaba.com/product-detail/Synthetic-Clock_1600000000000.html"
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://www.alibaba.com/product-detail/example.html",
        "https://evil.example/product-detail/example.html",
        "https://www.alibaba.com/trade/search?SearchText=clock",
        "https://user:password@www.alibaba.com/product-detail/example.html",
        "https://www.alibaba.com:99999/product-detail/example.html",
    ],
)
def test_selection_rejects_non_detail_or_credentialed_urls(url) -> None:
    with pytest.raises(ValueError):
        normalize_selection("alibaba", url, "Synthetic product")


def test_queue_deduplicates_and_persists_only_validated_selection(tmp_path) -> None:
    queue = SelectionQueue(tmp_path / "queue.json")
    first = normalize_selection(
        "alibaba",
        "https://www.alibaba.com/product-detail/Synthetic_1600000000000.html",
        "Synthetic product",
    )
    second = normalize_selection(
        "alibaba",
        "https://www.alibaba.com/product-detail/Synthetic_1600000000000.html?tracking=1",
        "Same product",
    )

    saved, created = queue.add(first)
    duplicate, duplicate_created = queue.add(second)

    assert created is True
    assert duplicate_created is False
    assert duplicate.id == saved.id
    payload = json.loads(queue.path.read_text(encoding="utf-8"))
    assert payload["version"] == 1
    assert len(payload["items"]) == 1
    assert "tracking" not in payload["items"][0]["product_url"]
