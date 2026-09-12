"""Loopback-only visual connection dashboard."""

from __future__ import annotations

import hmac
import json
import secrets
import threading
import webbrowser
from dataclasses import replace
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from .configuration import (
    PROVIDERS,
    ProfileRepository,
    SecretStore,
    SystemKeyringStore,
    public_profile,
)
from .exchange_rates import ExchangeRateService, ExchangeRatesUnavailable
from .pricing import PricingPolicy, PricingScheme
from .pricing_settings import PricingSettingsRepository

MAX_REQUEST_BYTES = 64 * 1024


class DashboardApplication:
    def __init__(
        self,
        repository: ProfileRepository,
        secret_store: SecretStore,
        token: str,
        pricing_repository: PricingSettingsRepository | None = None,
        exchange_rate_service: ExchangeRateService | None = None,
    ) -> None:
        self.repository = repository
        self.secret_store = secret_store
        self.token = token
        self.pricing_repository = pricing_repository or PricingSettingsRepository(
            repository.directory
        )
        self.origin = ""
        self.exchange_rate_service = exchange_rate_service or ExchangeRateService()

    def state(self) -> dict[str, object]:
        providers = [
            {"id": provider_id, **definition}
            for provider_id, definition in PROVIDERS.items()
        ]
        profiles = [
            public_profile(profile, self.secret_store) for profile in self.repository.list()
        ]
        return {
            "providers": providers,
            "profiles": profiles,
            "pricing": self.pricing_repository.load().to_dict(),
            "pricing_defaults": PricingPolicy().to_dict(),
        }

    def save_profile(self, payload: dict[str, object]) -> dict[str, object]:
        values = payload.get("values", {})
        secret_values = payload.get("secrets", {})
        if not isinstance(values, dict) or not isinstance(secret_values, dict):
            raise ValueError("Connection fields must be JSON objects")
        profile_id = str(payload.get("id") or "").strip() or None
        profile = self.repository.save(
            profile_id=profile_id,
            provider=str(payload.get("provider") or ""),
            label=str(payload.get("label") or ""),
            notes=str(payload.get("notes") or ""),
            values={str(key): str(value) for key, value in values.items()},
            secrets={str(key): str(value) for key, value in secret_values.items()},
            is_default=bool(payload.get("is_default", False)),
            secret_store=self.secret_store,
        )
        return public_profile(profile, self.secret_store)

    def save_pricing(self, payload: dict[str, object]) -> dict[str, object]:
        policy = PricingPolicy.from_dict(payload)
        self.pricing_repository.save(policy)
        return policy.to_dict()

    def preview_pricing(self, payload: dict[str, object]) -> dict[str, object]:
        expected = {"settings", "costs"}
        unknown = set(payload) - expected
        missing = expected - set(payload)
        if unknown:
            raise ValueError(f"Unknown pricing preview fields: {', '.join(sorted(unknown))}")
        if missing:
            raise ValueError(f"Missing pricing preview fields: {', '.join(sorted(missing))}")
        settings = payload["settings"]
        costs = payload["costs"]
        if not isinstance(settings, dict) or not isinstance(costs, dict):
            raise ValueError("Pricing preview settings and costs must be JSON objects")
        expected_costs = {"product_cost", "inbound_shipping", "last_mile"}
        unknown_costs = set(costs) - expected_costs
        missing_costs = expected_costs - set(costs)
        if unknown_costs:
            raise ValueError(f"Unknown preview costs: {', '.join(sorted(unknown_costs))}")
        if missing_costs:
            raise ValueError(f"Missing preview costs: {', '.join(sorted(missing_costs))}")
        policy = PricingPolicy.from_dict(settings)
        breakdown = policy.breakdown(
            costs["product_cost"],
            costs["inbound_shipping"],
            costs["last_mile"],
        ).to_dict()
        comparison = {}
        for scheme in PricingScheme:
            if scheme == policy.scheme:
                comparison[scheme.value] = {"breakdown": breakdown}
                continue
            try:
                compared = replace(policy, scheme=scheme).breakdown(
                    costs["product_cost"],
                    costs["inbound_shipping"],
                    costs["last_mile"],
                ).to_dict()
            except ValueError:
                comparison[scheme.value] = {
                    "error": "This scheme is unavailable for the current settings and costs."
                }
            else:
                comparison[scheme.value] = {"breakdown": compared}
        return {"breakdown": breakdown, "comparison": comparison}


class DashboardServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, application: DashboardApplication) -> None:
        self.application = application
        super().__init__(address, DashboardRequestHandler)


class DashboardRequestHandler(BaseHTTPRequestHandler):
    server: DashboardServer

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/index.html"}:
            self._serve_asset("dashboard.html", "text/html; charset=utf-8")
            return
        if parsed.path == "/assets/dashboard-i18n.js":
            self._serve_asset("dashboard-i18n.js", "text/javascript; charset=utf-8")
            return
        if parsed.path == "/assets/dashboard-fx.js":
            self._serve_asset("dashboard-fx.js", "text/javascript; charset=utf-8")
            return
        if parsed.path == "/api/exchange-rates":
            if not self._authorized():
                return
            try:
                rates = self.server.application.exchange_rate_service.latest()
            except ExchangeRatesUnavailable:
                self._send_json(
                    HTTPStatus.SERVICE_UNAVAILABLE, {"error": "exchange_rates_unavailable"}
                )
                return
            self._send_json(HTTPStatus.OK, rates)
            return
        if parsed.path == "/api/state":
            if not self._authorized():
                return
            try:
                state = self.server.application.state()
            except RuntimeError:
                self._send_json(
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    {"error": "The operating-system credential store is unavailable."},
                )
                return
            except ValueError:
                self._send_json(
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    {"error": "Saved pricing settings are invalid; edit pricing.json locally."},
                )
                return
            self._send_json(HTTPStatus.OK, state)
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        parsed = urlparse(self.path)
        if not self._authorized():
            return
        if parsed.path == "/api/profiles":
            try:
                payload = self._read_json()
                profile = self.server.application.save_profile(payload)
            except ValueError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            except RuntimeError:
                self._send_json(
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    {"error": "The operating-system credential store is unavailable."},
                )
                return
            self._send_json(HTTPStatus.OK, {"profile": profile})
            return
        if parsed.path == "/api/pricing":
            try:
                pricing = self.server.application.save_pricing(self._read_json())
            except ValueError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            except (OSError, RuntimeError):
                self._send_json(
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    {"error": "Pricing settings could not be saved."},
                )
                return
            self._send_json(HTTPStatus.OK, {"pricing": pricing})
            return
        if parsed.path == "/api/pricing/preview":
            try:
                preview = self.server.application.preview_pricing(self._read_json())
            except ValueError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            self._send_json(HTTPStatus.OK, preview)
            return
        if parsed.path == "/api/shutdown":
            self._send_json(HTTPStatus.OK, {"ok": True})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_DELETE(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        parsed = urlparse(self.path)
        if not self._authorized():
            return
        prefix = "/api/profiles/"
        if not parsed.path.startswith(prefix):
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        profile_id = unquote(parsed.path[len(prefix) :])
        try:
            self.server.application.repository.delete(
                profile_id, self.server.application.secret_store
            )
        except ValueError:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "profile_not_found"})
            return
        except RuntimeError:
            self._send_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"error": "The operating-system credential store is unavailable."},
            )
            return
        self._send_json(HTTPStatus.OK, {"ok": True})

    def _serve_asset(self, filename: str, content_type: str) -> None:
        # Only fixed filenames from the routes above reach the filesystem.
        path = Path(__file__).with_name(filename)
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self._security_headers(content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _authorized(self) -> bool:
        application = self.server.application
        supplied = self.headers.get("X-CatalogFlow-Token", "")
        origin = self.headers.get("Origin")
        if not hmac.compare_digest(supplied, application.token):
            self._send_json(HTTPStatus.FORBIDDEN, {"error": "invalid_session"})
            return False
        if origin and origin != application.origin:
            self._send_json(HTTPStatus.FORBIDDEN, {"error": "invalid_origin"})
            return False
        return True

    def _read_json(self) -> dict[str, object]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("Invalid Content-Length") from exc
        if length <= 0 or length > MAX_REQUEST_BYTES:
            raise ValueError("Request body must contain 1-65536 bytes")
        if self.headers.get_content_type() != "application/json":
            raise ValueError("Content-Type must be application/json")
        try:
            payload = json.loads(self.rfile.read(length))
        except json.JSONDecodeError as exc:
            raise ValueError("Request body is not valid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("Request body must be a JSON object")
        return payload

    def _send_json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._security_headers("application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        try:
            self.end_headers()
            self.wfile.write(data)
        except ConnectionError:
            # Typing a new value cancels the previous preview in the browser.
            # A departed caller is not a server error and needs no traceback.
            return

    def _security_headers(self, content_type: str) -> None:
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; connect-src 'self'; img-src 'self' data:; "
            "style-src 'unsafe-inline'; script-src 'self' 'unsafe-inline'; base-uri 'none'; "
            "form-action 'none'; frame-ancestors 'none'",
        )

    def log_message(self, _format: str, *_args: object) -> None:
        return


def run_dashboard(
    *,
    port: int = 0,
    open_browser: bool = True,
    repository: ProfileRepository | None = None,
    secret_store: SecretStore | None = None,
    pricing_repository: PricingSettingsRepository | None = None,
) -> None:
    """Run until Ctrl+C or the dashboard stop button is used."""

    if not 0 <= port <= 65535:
        raise ValueError("Dashboard port must be between 0 and 65535")
    application = DashboardApplication(
        repository or ProfileRepository(),
        secret_store or SystemKeyringStore(),
        secrets.token_urlsafe(32),
        pricing_repository,
    )
    server = DashboardServer(("127.0.0.1", port), application)
    actual_port = int(server.server_address[1])
    application.origin = f"http://127.0.0.1:{actual_port}"
    dashboard_url = f"{application.origin}/#token={application.token}"
    print(f"CatalogFlow local connection center: {application.origin}/")
    print(f"One-time dashboard URL: {dashboard_url}")
    print("This page is available only on this computer. Press Ctrl+C to stop it.")
    if open_browser:
        webbrowser.open(dashboard_url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
