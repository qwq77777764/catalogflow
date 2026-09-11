"""Optional Codex CLI adapter with structured output and no credential input."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from ..models import Listing, Product
from ..pricing import PricingPolicy


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
        executable = shutil.which("codex") or shutil.which("codex.cmd")
        if not executable:
            raise RuntimeError("Codex CLI was not found on PATH")

        schema = Path(__file__).parents[1] / "schemas" / "listing.schema.json"
        with tempfile.TemporaryDirectory(prefix="catalogflow_codex_") as temp_dir:
            output = Path(temp_dir) / "listing.json"
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
            )
            if process.returncode != 0:
                raise RuntimeError(f"Codex CLI exited with status {process.returncode}")
            if not output.exists():
                raise RuntimeError("Codex CLI did not create structured output")
            data = json.loads(output.read_text(encoding="utf-8"))

        prices = {variant.sku: self.policy.price(variant.cost) for variant in product.variants}
        return Listing(
            title=str(data["title"]),
            description_html=str(data["description_html"]),
            category=str(data["category"]),
            tags=tuple(str(tag) for tag in data["tags"]),
            prices=prices,
        )

    @staticmethod
    def build_prompt(product: Product) -> str:
        facts = {
            "title": product.title,
            "currency": product.currency,
            "facts": product.facts,
            "variant_attributes": [variant.attributes for variant in product.variants],
        }
        return (
            "Create original, brand-neutral English merchandising copy from the authorized "
            "product facts below. Return only JSON matching the supplied schema. Do not mention "
            "supplier platforms, dropshipping, wholesale, shipping promises, medical claims, "
            "brands, licenses, or facts not present in the input. Use 'Not specified' when a "
            "material, measurement, or power detail is unknown.\n\n"
            + json.dumps(facts, ensure_ascii=False, indent=2)
        )

