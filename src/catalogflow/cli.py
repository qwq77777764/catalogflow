"""CatalogFlow command-line interface."""

from __future__ import annotations

import argparse
import json

from .doctor import print_doctor_report
from .exporters import WooCommercePublisher, write_preview
from .generators import (
    ClaudeCliListingGenerator,
    CodexCliListingGenerator,
    DeterministicListingGenerator,
)
from .models import ImportMode, ImportRequest
from .pipeline import import_products
from .providers import JsonFileSource


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create a safe local catalog preview")
    parser.add_argument("product_json", nargs="?", help="Authorized normalized product JSON")
    parser.add_argument(
        "--source",
        choices=("cj", "alibaba-manual"),
        help="Origin represented by the input file",
    )
    parser.add_argument("--output", default="output/preview.json")
    parser.add_argument(
        "--generator",
        choices=("deterministic", "codex", "claude"),
        default="deterministic",
        help="Listing generator; local AI CLIs are opt-in and may consume account usage",
    )
    parser.add_argument(
        "--doctor",
        action="store_true",
        help="Check local Codex/Claude CLI discovery without making an AI request",
    )
    parser.add_argument(
        "--draft",
        action="store_true",
        help="Create a hidden WooCommerce draft (requires --yes and environment credentials)",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Acknowledge the external write performed by --draft",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.doctor:
        print_doctor_report()
        return 0
    if not args.product_json or not args.source:
        parser.error("product_json and --source are required unless --doctor is used")
    if args.draft and not args.yes:
        raise SystemExit("Refusing store write: --draft also requires --yes")
    mode = ImportMode.DRAFT if args.draft else ImportMode.DRY_RUN
    publisher = WooCommercePublisher.from_environment() if args.draft else None
    generators = {
        "codex": CodexCliListingGenerator,
        "claude": ClaudeCliListingGenerator,
        "deterministic": DeterministicListingGenerator,
    }
    generator = generators[args.generator]()
    report = import_products(
        [ImportRequest(source=args.source, reference=args.product_json)],
        sources={args.source: JsonFileSource(args.source)},
        generator=generator,
        mode=mode,
        publisher=publisher,
    )
    destination = write_preview(report, args.output)
    print(json.dumps({"ok": report.ok, "mode": report.mode, "preview": str(destination)}))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
