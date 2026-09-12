"""CatalogFlow command-line interface."""

from __future__ import annotations

import argparse
import json
import os
import sys

from .collector import run_collector
from .configuration import ProfileRepository, SystemKeyringStore, environment_for_profile
from .dashboard import run_dashboard
from .doctor import print_doctor_report
from .exporters import WooCommercePublisher, write_preview
from .generators import (
    ClaudeCliListingGenerator,
    CodexCliListingGenerator,
    DeterministicListingGenerator,
)
from .models import ImportMode, ImportRequest
from .pipeline import import_products
from .pricing_settings import PricingSettingsRepository
from .providers import CjApiSource, JsonFileSource
from .run_history import HistoryRepository, safe_error


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a safe local catalog preview",
        epilog=(
            "Use 'catalogflow configure' for connection profiles or "
            "'catalogflow collect' for browser selections."
        ),
    )
    parser.add_argument(
        "product_reference",
        nargs="?",
        help="Authorized normalized JSON, or one CJ URL/PID with --supplier-profile",
    )
    parser.add_argument(
        "--source",
        choices=("cj", "alibaba-manual"),
        help="Supplier represented by the authorized input",
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
    parser.add_argument(
        "--ai-profile",
        help="Connection profile ID or unique label for the selected local AI CLI",
    )
    parser.add_argument(
        "--store-profile",
        help="WooCommerce connection profile ID or unique label used by --draft",
    )
    parser.add_argument(
        "--supplier-profile",
        help="Authorized supplier API profile; currently supported for --source cj",
    )
    return parser


def build_configure_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="catalogflow configure",
        description="Open the loopback-only visual connection center",
    )
    parser.add_argument("--port", type=int, default=0, help="Local port; 0 chooses a free port")
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Print the URL without opening it",
    )
    return parser


def build_collect_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="catalogflow collect",
        description="Collect explicit supplier product selections on this computer",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8766,
        help="Loopback port used by the browser userscript (default: 8766)",
    )
    return parser


def _load_profile(reference: str, expected_provider: str) -> None:
    repository = ProfileRepository()
    profile = repository.find(reference)
    if profile.provider != expected_provider:
        raise SystemExit(
            f"Connection profile belongs to {profile.provider}, expected {expected_provider}"
        )
    os.environ.update(environment_for_profile(profile, SystemKeyringStore()))


def _load_default_profile(provider: str) -> None:
    repository = ProfileRepository()
    profile = repository.default_for(provider)
    if profile:
        os.environ.update(environment_for_profile(profile, SystemKeyringStore()))


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] == "configure":
        args = build_configure_parser().parse_args(arguments[1:])
        run_dashboard(port=args.port, open_browser=not args.no_browser)
        return 0
    if arguments and arguments[0] == "collect":
        args = build_collect_parser().parse_args(arguments[1:])
        run_collector(port=args.port)
        return 0
    parser = build_parser()
    args = parser.parse_args(arguments)
    if args.doctor:
        print_doctor_report()
        return 0
    if not args.product_reference or not args.source:
        parser.error("product_reference and --source are required unless --doctor is used")
    if args.draft and not args.yes:
        raise SystemExit("Refusing store write: --draft also requires --yes")
    if args.ai_profile and args.generator == "deterministic":
        parser.error("--ai-profile requires --generator codex or --generator claude")
    if args.supplier_profile and args.source != "cj":
        parser.error("--supplier-profile currently requires --source cj")
    mode = ImportMode.DRAFT if args.draft else ImportMode.DRY_RUN
    try:
        return _execute_import(args, mode)
    except (OSError, RuntimeError, ValueError):
        # If durable storage fails, stop without printing paths or remote response details.
        # Any existing draft reservation remains in place for manual review.
        print(json.dumps({"ok": False, "mode": mode, "error": "reports_unavailable"}))
        return 1


def _execute_import(args, mode: ImportMode) -> int:
    history = HistoryRepository()
    try:
        source_adapter, generator, publisher = _prepare_import(args)
    except (Exception, SystemExit) as exc:
        run = history.create_run(mode)
        item = run.start_item(source=args.source, source_url=args.product_reference)
        item.update(status="rejected", errors=["configuration_failed", safe_error(exc)])
        run.finish_item(item)
        run.finish()
        print(json.dumps({
            "ok": False, "mode": mode, "error": "configuration_failed",
            "run_id": run.run_id, "report": str(run.directory / "report.txt"),
        }))
        return 1
    report = import_products(
        [ImportRequest(source=args.source, reference=args.product_reference)],
        sources={args.source: source_adapter}, generator=generator, mode=mode,
        publisher=publisher, history=history,
    )
    try:
        destination = write_preview(report, args.output)
    except (OSError, ValueError):
        print(json.dumps({
            "ok": False, "mode": report.mode, "error": "preview_output_failed",
            "run_id": report.run_id, "report": report.report_path,
        }))
        return 1
    print(json.dumps({
        "ok": report.ok, "mode": report.mode, "preview": str(destination),
        "run_id": report.run_id, "report": report.report_path,
    }))
    return 0 if report.ok else 1


class _InvalidSavedPricing(ValueError):
    code = "saved_pricing_invalid"


def _prepare_import(args):
    if args.ai_profile:
        _load_profile(args.ai_profile, args.generator)
    elif args.generator in {"codex", "claude"}:
        _load_default_profile(args.generator)
    if args.store_profile:
        _load_profile(args.store_profile, "woocommerce")
    elif args.draft:
        _load_default_profile("woocommerce")
    publisher = WooCommercePublisher.from_environment() if args.draft else None
    generators = {
        "codex": CodexCliListingGenerator,
        "claude": ClaudeCliListingGenerator,
        "deterministic": DeterministicListingGenerator,
    }
    try:
        pricing_policy = PricingSettingsRepository().load()
    except (RuntimeError, ValueError):
        raise _InvalidSavedPricing from None
    generator = generators[args.generator](policy=pricing_policy)
    if args.supplier_profile:
        _load_profile(args.supplier_profile, "cj")
        source_adapter = CjApiSource.from_environment()
    else:
        source_adapter = JsonFileSource(args.source)
    return source_adapter, generator, publisher


if __name__ == "__main__":
    raise SystemExit(main())
