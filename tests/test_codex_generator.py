from catalogflow.generators.codex_cli import CodexCliListingGenerator
from catalogflow.models import Product, ShippingQuote, Variant


def test_codex_prompt_contains_facts_but_not_source_credentials() -> None:
    product = Product(
        "cj",
        "private-source-id",
        "Minimal Clock",
        "USD",
        (
            Variant(
                "SKU-1",
                3.5,
                {"finish": "oak"},
                ShippingQuote("CN", "US", 1, "Synthetic Post", 4.71),
            ),
        ),
        facts={"power": "USB"},
    )
    prompt = CodexCliListingGenerator.build_prompt(product)
    assert "Minimal Clock" in prompt
    assert "USB" in prompt
    assert "private-source-id" not in prompt
    assert "3.5" not in prompt
    assert "4.71" not in prompt
    assert "Synthetic Post" not in prompt
