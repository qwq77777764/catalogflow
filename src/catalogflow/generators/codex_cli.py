"""Optional Codex CLI adapter with structured output and no credential input."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

from ..media import materialize_authorized_images
from ..models import Listing, Product
from ..pricing import PricingPolicy, shipping_cost_for_pricing
from .common import build_listing_prompt, find_cli, safe_cli_environment


class CodexCliListingGenerator:
    """Generate copy from normalized product facts using an installed Codex CLI."""

    def __init__(
        self,
        *,
        model: str | None = None,
        timeout_seconds: int = 300,
        policy: PricingPolicy | None = None,
    ) -> None:
        self.model = model or os.environ.get("CATALOGFLOW_CODEX_MODEL") or None
        self.timeout_seconds = timeout_seconds
        self.policy = policy or PricingPolicy()

    def generate(self, product: Product) -> Listing:
        executable = find_cli("codex", "CATALOGFLOW_CODEX_COMMAND")
        if not executable:
            raise RuntimeError(
                "Codex CLI was not found. Run 'catalogflow --doctor' and see docs/local-ai.md"
            )

        schema = Path(__file__).parents[1] / "schemas" / "listing.schema.json"
        with tempfile.TemporaryDirectory(prefix="catalogflow_codex_") as temp_dir:
            output = Path(temp_dir) / "listing.json"
            image_paths = materialize_authorized_images(product.images, temp_dir)
            command = [
                executable,
                "exec",
                "--skip-git-repo-check",
                "--sandbox",
                "read-only",
                "--ephemeral",
                "--output-schema",
                str(schema),
                "-o",
                str(output),
            ]
            if self.model:
                command.extend(["-m", self.model])
            for image_path in image_paths:
                command.extend(["-i", str(image_path)])
            command.append("-")
            process = subprocess.run(  # noqa: S603 - fixed executable and argument list
                command,
                input=self.build_prompt(product),
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=self.timeout_seconds,
                check=False,
                env=safe_cli_environment(),
            )
            if process.returncode != 0:
                raise RuntimeError(f"Codex CLI exited with status {process.returncode}")
            if not output.exists():
                raise RuntimeError("Codex CLI did not create structured output")
            data = json.loads(output.read_text(encoding="utf-8"))

        prices = {
            variant.sku: self.policy.price(
                variant.cost,
                last_mile=shipping_cost_for_pricing(product, variant),
            )
            for variant in product.variants
        }
        shipping_quotes = {
            variant.sku: variant.shipping_quote
            for variant in product.variants
            if variant.shipping_quote is not None
        }
        return Listing(
            title=str(data["title"]),
            description_html=str(data["description_html"]),
            category=str(data["category"]),
            tags=tuple(str(tag) for tag in data["tags"]),
            prices=prices,
            shipping_quotes=shipping_quotes,
        )

    @staticmethod
    def build_prompt(product: Product) -> str:
        return build_listing_prompt(product)
