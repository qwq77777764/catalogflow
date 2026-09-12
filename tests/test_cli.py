import json

import pytest

from catalogflow.cli import build_parser, main
from catalogflow.configuration import MemorySecretStore, ProfileRepository
from catalogflow.dashboard import DashboardApplication
from catalogflow.pricing import PricingPolicy
from catalogflow.pricing_settings import PricingSettingsRepository
from catalogflow.run_history import HistoryRepository


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


@pytest.mark.parametrize(
    ("scheme", "formula"),
    [("margin", None), ("cost_multiplier", None), ("cost_multiplier", "*5/2+3-1")],
)
def test_dashboard_saved_pricing_matches_cj_variant_cli_previews(
    scheme, formula, tmp_path, monkeypatch
) -> None:
    config = tmp_path / "config"
    monkeypatch.setenv("CATALOGFLOW_CONFIG_DIR", str(config))

    def external_boundary_forbidden(*args, **kwargs):
        raise AssertionError("A pricing dry-run must not initialize an external provider")

    for boundary in (
        "catalogflow.cli.CodexCliListingGenerator",
        "catalogflow.cli.ClaudeCliListingGenerator",
        "catalogflow.cli.WooCommercePublisher.from_environment",
        "catalogflow.cli.CjApiSource.from_environment",
        "catalogflow.cli.SystemKeyringStore",
    ):
        monkeypatch.setattr(boundary, external_boundary_forbidden)

    application = DashboardApplication(
        ProfileRepository(config), MemorySecretStore(), "synthetic-session-token"
    )
    settings = PricingPolicy(
        scheme=scheme,
        cost_multiplier=3.5,
        cost_formula=formula,
        target_margin=0.35,
        payment_fee_rate=0.04,
        payment_fixed_fee=0.5,
        return_rate=0.08,
        operating_rate=0.06,
        tax_duties_per_unit=1.2,
    ).to_dict()
    saved = application.save_pricing(settings)
    variants = [
        {
            "sku": sku,
            "cost": cost,
            "shipping_quote": {
                "origin_country": "CN",
                "destination_country": "US",
                "quantity": quantity,
                "method": "Synthetic Route",
                "total_cost_usd": shipping_total,
                "estimated_days": "8-12",
            },
        }
        for sku, cost, quantity, shipping_total in (
            ("SYNTHETIC-SMALL", 5, 1, 4.5),
            ("SYNTHETIC-LARGE", 8, 2, 14),
        )
    ]
    source = tmp_path / "synthetic-cj.json"
    source.write_text(
        json.dumps(
            {
                "source_id": "synthetic-cj-product",
                "title": "Synthetic storage basket",
                "currency": "USD",
                "variants": variants,
            }
        ),
        encoding="utf-8",
    )
    expected_prices = {
        variant["sku"]: application.preview_pricing(
            {
                "settings": saved,
                "costs": {
                    "product_cost": variant["cost"],
                    "inbound_shipping": 0,
                    "last_mile": (
                        variant["shipping_quote"]["total_cost_usd"]
                        / variant["shipping_quote"]["quantity"]
                    ),
                },
            }
        )["breakdown"]["final_price"]
        for variant in variants
    }
    saved_file = (config / "pricing.json").read_bytes()
    output = tmp_path / "preview.json"

    result = main([str(source), "--source", "cj", "--output", str(output)])

    preview = json.loads(output.read_text(encoding="utf-8"))
    assert result == 0
    assert preview["mode"] == "dry-run"
    assert len(preview["items"]) == 1
    item = preview["items"][0]
    assert item["status"] == "previewed"
    assert item["store_id"] is None
    assert item["listing"]["prices"] == expected_prices
    assert item["listing"]["shipping_quotes"]["SYNTHETIC-LARGE"]["quantity"] == 2
    assert (config / "pricing.json").read_bytes() == saved_file
    assert set(json.loads(saved_file)["settings"]) == PricingPolicy.FIELD_NAMES


def test_cli_invalid_saved_pricing_stops_before_generation_without_preview(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("CATALOGFLOW_CONFIG_DIR", str(tmp_path / "config"))
    repository = PricingSettingsRepository()
    repository.save(PricingPolicy())
    document = json.loads(repository.path.read_text(encoding="utf-8"))
    document["settings"]["target_margin"] = 0.95
    repository.path.write_text(json.dumps(document), encoding="utf-8")

    def generation_forbidden(*args, **kwargs):
        raise AssertionError("Invalid pricing must be rejected before generation")

    monkeypatch.setattr("catalogflow.cli.DeterministicListingGenerator", generation_forbidden)
    output = tmp_path / "preview.json"
    result = main(
        [str(tmp_path / "not-read.json"), "--source", "alibaba-manual", "--output", str(output)]
    )

    assert not output.exists()
    assert result == 1
    history = HistoryRepository()
    run_id = history.recent()[0]["run_id"]
    assert "Saved pricing settings are invalid" in history.report_text(run_id)


def test_cli_archives_profile_setup_failure_without_echoing_exception(
    tmp_path, monkeypatch, capsys,
):
    monkeypatch.setenv("CATALOGFLOW_CONFIG_DIR", str(tmp_path / "config"))

    def fail_profile(*args):
        raise RuntimeError("private-synthetic-credential")

    monkeypatch.setattr("catalogflow.cli._load_profile", fail_profile)
    assert main(["synthetic.json", "--source", "cj", "--supplier-profile", "missing"]) == 1
    message = json.loads(capsys.readouterr().out)
    assert message["error"] == "configuration_failed"
    history = HistoryRepository()
    assert "private-synthetic-credential" not in history.report_text(message["run_id"])


def test_cli_failed_compatibility_output_keeps_archived_preview(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CATALOGFLOW_CONFIG_DIR", str(tmp_path / "config"))
    source = tmp_path / "product.json"
    source.write_text(json.dumps({
        "source_id": "test-1", "title": "Basket",
        "variants": [{"sku": "SKU-1", "cost": 2}],
    }), encoding="utf-8")

    def fail_output(*args):
        raise PermissionError("private path details")

    monkeypatch.setattr("catalogflow.cli.write_preview", fail_output)
    assert main([str(source), "--source", "alibaba-manual"]) == 1
    message = json.loads(capsys.readouterr().out)
    assert message["error"] == "preview_output_failed"
    document = HistoryRepository().read(message["run_id"])
    assert document["counts"] == {"previewed": 1}
    assert document["items"][0]["artifact_path"]


def test_cli_unwritable_history_fails_without_raw_traceback(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CATALOGFLOW_CONFIG_DIR", str(tmp_path / "config"))

    def unavailable(*args):
        raise PermissionError("private-path-and-credential-marker")

    monkeypatch.setattr(HistoryRepository, "create_run", unavailable)
    assert main(["unused.json", "--source", "alibaba-manual"]) == 1
    output = capsys.readouterr()
    assert json.loads(output.out)["error"] == "reports_unavailable"
    assert output.err == ""
    assert "private-path-and-credential-marker" not in output.out
