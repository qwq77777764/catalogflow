"""Optional Claude Code CLI adapter with structured output and no supplier secrets."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

from ..media import materialize_authorized_images
from ..models import Listing, Product
from ..pricing import PricingPolicy
from .common import build_listing_prompt, find_cli, safe_cli_environment


class ClaudeCliListingGenerator:
    """Generate listing copy through a user's already-authenticated Claude Code CLI."""

    def __init__(
        self,
        *,
        model: str | None = None,
        timeout_seconds: int = 300,
        policy: PricingPolicy | None = None,
    ) -> None:
        self.model = model or os.environ.get("CATALOGFLOW_CLAUDE_MODEL") or None
        self.timeout_seconds = timeout_seconds
        self.policy = policy or PricingPolicy()

    def generate(self, product: Product) -> Listing:
        executable = find_cli("claude", "CATALOGFLOW_CLAUDE_COMMAND")
        if not executable:
            raise RuntimeError(
                "Claude Code CLI was not found. Run 'catalogflow --doctor' and see docs/local-ai.md"
            )

        schema_path = Path(__file__).parents[1] / "schemas" / "listing.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory(prefix="catalogflow_claude_") as temp_dir:
            image_paths = materialize_authorized_images(product.images, temp_dir)
            command = [
                executable,
                "-p",
                "--output-format",
                "json",
                "--json-schema",
                json.dumps(schema, separators=(",", ":")),
                "--max-turns",
                "3" if image_paths else "1",
                "--no-session-persistence",
                "--disallowedTools",
                "Bash,Edit,Write,WebFetch,WebSearch",
            ]
            if image_paths:
                command.extend(["--allowedTools", "Read"])
            else:
                command[-1] += ",Read"
            if self.model:
                command.extend(["--model", self.model])

            prompt = build_listing_prompt(product)
            if image_paths:
                names = ", ".join(path.name for path in image_paths)
                prompt += (
                    "\n\nAuthorized product images are available in the current "
                    "temporary directory: "
                    f"{names}. Use Read only to inspect those images before writing the listing."
                )
            process = subprocess.run(  # noqa: S603 - fixed executable and argument list
                command,
                input=prompt,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=self.timeout_seconds,
                check=False,
                env=safe_cli_environment(),
                cwd=temp_dir,
            )
        if process.returncode != 0:
            raise RuntimeError(f"Claude Code CLI exited with status {process.returncode}")
        envelope = json.loads(process.stdout)
        if envelope.get("is_error"):
            raise RuntimeError("Claude Code CLI returned an error result")
        data = envelope.get("structured_output")
        if not isinstance(data, dict):
            raise RuntimeError("Claude Code CLI did not return structured_output")

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
        return build_listing_prompt(product)
