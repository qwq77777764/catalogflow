import pytest

from catalogflow.cli import build_parser


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
