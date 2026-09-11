import json
from types import SimpleNamespace

from catalogflow.generators.claude_cli import ClaudeCliListingGenerator
from catalogflow.models import Product, Variant


def product() -> Product:
    return Product(
        "cj",
        "private-source-id",
        "Minimal Clock",
        "USD",
        (Variant("SKU-1", 3.5, {"finish": "oak"}),),
        facts={"power": "USB"},
    )


def test_claude_prompt_excludes_source_id_and_cost() -> None:
    prompt = ClaudeCliListingGenerator.build_prompt(product())
    assert "Minimal Clock" in prompt
    assert "USB" in prompt
    assert "private-source-id" not in prompt
    assert "3.5" not in prompt


def test_claude_generator_reads_structured_output(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["env"] = kwargs["env"]
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "is_error": False,
                    "structured_output": {
                        "title": "Minimal USB Desk Clock",
                        "description_html": "<h2>Minimal USB Desk Clock</h2>",
                        "category": "Clocks",
                        "tags": ["desk clock", "usb clock"],
                    },
                }
            ),
            stderr="",
        )

    monkeypatch.setattr(
        "catalogflow.generators.claude_cli.find_cli", lambda *_args: "claude"
    )
    monkeypatch.setattr("catalogflow.generators.claude_cli.subprocess.run", fake_run)
    monkeypatch.setenv("PRIVATE_SUPPLIER_API_KEY", "must-not-reach-child")

    listing = ClaudeCliListingGenerator().generate(product())

    assert listing.title == "Minimal USB Desk Clock"
    assert listing.prices == {"SKU-1": 9.95}
    assert "--no-session-persistence" in captured["command"]
    assert "PRIVATE_SUPPLIER_API_KEY" not in captured["env"]
