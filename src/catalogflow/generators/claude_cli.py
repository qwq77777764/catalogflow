"""Optional Claude Code CLI adapter with structured output and no supplier secrets."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from ..media import materialize_authorized_images
from ..models import Listing, Product
from ..pricing import PricingPolicy, shipping_cost_for_pricing
from .common import (
    CliDiagnosticError,
    build_listing_prompt,
    cli_failure_code,
    find_cli,
    run_external,
    safe_cli_environment,
)


class ClaudeCliListingGenerator:
    """Generate listing copy through a user's already-authenticated Claude Code CLI."""

    def __init__(
        self,
        *,
        model: str | None = None,
        command: str | None = None,
        timeout_seconds: int = 300,
        policy: PricingPolicy | None = None,
    ) -> None:
        self.model = ((os.environ.get("CATALOGFLOW_CLAUDE_MODEL") if model is None else model)
                      or None)
        self.command = command
        self.timeout_seconds = timeout_seconds
        self.policy = policy or PricingPolicy()

    def generate(self, product: Product) -> Listing:
        executable = (find_cli("claude", "CATALOGFLOW_CLAUDE_COMMAND") if self.command is None
                      else find_cli("claude", "CATALOGFLOW_CLAUDE_COMMAND", command=self.command))
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
                "--safe-mode",
                "--settings",
                '{"disableAllHooks":true}',
                "--strict-mcp-config",
                "--mcp-config",
                '{"mcpServers":{}}',
                "-p",
                "--output-format",
                "json",
                "--json-schema",
                json.dumps(schema, separators=(",", ":")),
                "--max-turns",
                "3" if image_paths else "1",
                "--no-session-persistence",
            ]
            if image_paths:
                command.extend(["--tools", "Read", "--allowedTools", "Read"])
            else:
                command.extend(["--tools", ""])
            command.extend(["--disallowedTools", "mcp__*"])
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
            process = run_external(
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
                max_output_bytes=512 * 1024,
            )
        if process.returncode != 0:
            raise CliDiagnosticError(cli_failure_code(
                (process.stderr or "") + (process.stdout or "")
            ))
        envelope = json.loads(process.stdout)
        if envelope.get("is_error"):
            raise CliDiagnosticError(cli_failure_code(json.dumps(envelope)))
        data = envelope.get("structured_output")
        if not isinstance(data, dict):
            raise RuntimeError("Claude Code CLI did not return structured_output")

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
