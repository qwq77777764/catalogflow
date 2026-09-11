import json

import pytest

from catalogflow.cli import build_parser, main
from catalogflow.pricing import PricingPolicy
from catalogflow.pricing_settings import PricingSettingsRepository


def test_supplier_profile_is_available_for_one_cj_reference() -> None:
    args = build_parser().parse_args(
        [
            "1442332573555625984",
            "--source",
            "cj",
            "--supplier-profile",
            "My CJ",
        ]
    )

    assert args.product_reference == "1442332573555625984"
    assert args.source == "cj"
    assert args.supplier_profile == "My CJ"


def test_source_choices_remain_closed() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["demo.json", "--source", "untrusted"])


def test_cli_loads_saved_pricing_and_injects_it_into_generator(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("CATALOGFLOW_CONFIG_DIR", str(tmp_path / "config"))
    source = tmp_path / "product.json"
    source.write_text(
        json.dumps(
            {
                "source_id": "test-1",
                "title": "Test product",
                "currency": "USD",
                "variants": [{"sku": "SKU-1", "cost": 2}],
            }
        ),
        encoding="utf-8",
    )
    PricingSettingsRepository().save(
        PricingPolicy(
            scheme="cost_multiplier",
            cost_multiplier=10,
            tax_duties_per_unit=1,
        )
    )
    output = tmp_path / "preview.json"

    result = main(
        [str(source), "--source", "alibaba-manual", "--output", str(output)]
    )

    preview = json.loads(output.read_text(encoding="utf-8"))
    assert result == 0
    assert preview["items"][0]["listing"]["prices"]["SKU-1"] == 21.95
