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

from .ai_setup import AISetup, AISetupError
from .configuration import (
    PROVIDERS,
    ProfileRepository,
    SecretStore,
    SystemKeyringStore,
    public_profile,
)
from .cost_formula import CostFormulaError
from .exchange_rates import ExchangeRateService, ExchangeRatesUnavailable
from .import_wizard import ImportWizard, ImportWizardError
from .pricing import PricingPolicy, PricingScheme
from .pricing_settings import PricingSettingsRepository
from .queue_workflow import QueueWorkflow, QueueWorkflowError
from .run_history import HistoryRepository

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
        self.history = HistoryRepository(repository.directory)
        self.imports = ImportWizard(
            repository, secret_store, self.pricing_repository, self.history
        )
        self.ai_setup = AISetup(repository)
        self.selections = QueueWorkflow(repository.directory)
        self._lifecycle_lock = threading.RLock()
        self._closed = False

    def prepare_shutdown(self) -> bool:
        with self._lifecycle_lock:
            if self.imports.busy or self.ai_setup.busy:
                return False
            if not self.imports.prepare_shutdown() or not self.ai_setup.prepare_shutdown():
                return False
            self._closed = True
            return True

    def close(self) -> None:
        self.selections.close()
        self.ai_setup.close()

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
            except CostFormulaError as exc:
                comparison[scheme.value] = {"error": str(exc)}
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

    def server_close(self) -> None:
        try:
            super().server_close()
        finally:
            self.application.close()


class DashboardRequestHandler(BaseHTTPRequestHandler):
    server: DashboardServer

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(10)

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
        if parsed.path == "/assets/dashboard-history.js":
            self._serve_asset("dashboard-history.js", "text/javascript; charset=utf-8")
            return
        if parsed.path == "/assets/dashboard-import.js":
            self._serve_asset("dashboard-import.js", "text/javascript; charset=utf-8")
            return
        if parsed.path == "/assets/dashboard-setup.js":
            self._serve_asset("dashboard-setup.js", "text/javascript; charset=utf-8")
            return
        if parsed.path in {"/api/ai-setup", "/api/selection-workflow"}:
            if not self._authorized():
                return
            self._serve_workflow(parsed.path)
            return
        if parsed.path.startswith("/api/imports/"):
            if not self._authorized():
                return
            self._serve_import(parsed.path)
            return
        if parsed.path == "/api/reports" or parsed.path.startswith("/api/reports/"):
            if not self._authorized():
                return
            self._serve_report(parsed.path)
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
        if parsed.path.startswith(("/api/ai-setup/", "/api/selection-workflow/")):
            self._serve_workflow(parsed.path, write=True)
            return
        if parsed.path.startswith("/api/imports/"):
            self._serve_import(parsed.path, write=True)
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
            if not self.server.application.prepare_shutdown():
                self._send_json(HTTPStatus.CONFLICT, {"error": "workflow_busy"})
                return
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

    def _serve_workflow(self, path: str, *, write: bool = False) -> None:
        app = self.server.application
        try:
            payload = self._read_json() if write else None
            with app._lifecycle_lock:
                if write and app._closed:
                    self._send_json(HTTPStatus.CONFLICT, {"error": "workflow_closed"})
                    return
                if path == "/api/ai-setup" and not write:
                    result = app.ai_setup.state()
                elif path == "/api/selection-workflow" and not write:
                    result = app.selections.state()
                elif write and path.startswith("/api/ai-setup/"):
                    if app.imports.busy:
                        self._send_json(HTTPStatus.CONFLICT, {"error": "import_busy"})
                        return
                    action = path.removeprefix("/api/ai-setup/")
                    methods = {"check": app.ai_setup.start_check,
                               "test": app.ai_setup.start_test,
                               "login": app.ai_setup.start_login}
                    if action not in methods:
                        self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                        return
                    result = methods[action](payload)
                elif write and path.startswith("/api/selection-workflow/"):
                    action = path.removeprefix("/api/selection-workflow/")
                    if action == "start" and not payload:
                        result = app.selections.start()
                    elif action == "freeze" and not set(payload) - {"queue_id"}:
                        result = app.selections.freeze(payload)
                    elif action == "import" and set(payload) == {"queue"}:
                        result = app.selections.import_payload(payload["queue"])
                    elif action == "select" and set(payload) == {"id"}:
                        result = {"item": app.selections.select(payload["id"])}
                    else:
                        raise ValueError("Unsupported workflow request")
                else:
                    self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                    return
        except (AISetupError, QueueWorkflowError) as exc:
            self._send_json(HTTPStatus(exc.status), {"error": exc.code})
            return
        except (TypeError, ValueError):
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "workflow_invalid_request"})
            return
        except Exception:
            self._send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "workflow_unavailable"})
            return
        self._send_json(HTTPStatus.ACCEPTED if write else HTTPStatus.OK, result)

    def _serve_import(self, path: str, *, write: bool = False) -> None:
        service = self.server.application.imports
        parts = path.removeprefix("/api/imports/").split("/")
        try:
            if write:
                payload = self._read_json()
                app = self.server.application
                with app._lifecycle_lock:
                    if app._closed or app.ai_setup.busy:
                        self._send_json(HTTPStatus.CONFLICT, {"error": "workflow_busy"})
                        return
                    if parts == ["preview"]:
                        job = service.start_preview(payload)
                    elif len(parts) == 2 and parts[1] == "draft":
                        job = service.start_draft(parts[0], payload)
                    else:
                        self._send_json(HTTPStatus.NOT_FOUND, {"error": "import_not_found"})
                        return
            elif not write and parts == ["current"]:
                job = service.current()
            elif not write and len(parts) == 1:
                job = service.get(parts[0])
            else:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "import_not_found"})
                return
        except ImportWizardError as exc:
            self._send_json(HTTPStatus(exc.status), {"error": exc.code})
            return
        except ValueError:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "import_invalid_request"})
            return
        except Exception:
            # Never return supplier responses, credential-store errors, or local paths.
            self._send_json(
                HTTPStatus.SERVICE_UNAVAILABLE, {"error": "import_configuration_failed"}
            )
            return
        self._send_json(HTTPStatus.ACCEPTED if write else HTTPStatus.OK, {"job": job})

    def _serve_report(self, path: str) -> None:
        history = self.server.application.history
        try:
            if path == "/api/reports":
                payload = {"reports": history.recent()}
            else:
                parts = path.removeprefix("/api/reports/").split("/")
                if len(parts) == 1:
                    payload = history.read(parts[0])
                elif len(parts) == 2 and parts[1] == "text":
                    payload = {
                        "text": history.report_text(parts[0]),
                        "filename": f"CatalogFlow-report-{parts[0]}.txt",
                    }
                else:
                    raise ValueError("Invalid report route")
        except (FileNotFoundError, ValueError):
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "report_not_found"})
            return
        except (OSError, RuntimeError):
            self._send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "reports_unavailable"})
            return
        self._send_json(HTTPStatus.OK, payload)

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
        except (json.JSONDecodeError, UnicodeDecodeError, RecursionError) as exc:
            raise ValueError("Request body is not valid JSON") from exc
        except (TimeoutError, OSError) as exc:
            raise ValueError("Request body could not be read") from exc
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


def create_dashboard_server(
    *,
    port: int = 0,
    repository: ProfileRepository | None = None,
    secret_store: SecretStore | None = None,
    pricing_repository: PricingSettingsRepository | None = None,
) -> DashboardServer:
    """Create an authenticated loopback server without starting it or printing its token."""

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
    return server


def run_dashboard(
    *,
    port: int = 0,
    open_browser: bool = True,
    repository: ProfileRepository | None = None,
    secret_store: SecretStore | None = None,
    pricing_repository: PricingSettingsRepository | None = None,
) -> None:
    """Run until Ctrl+C or the dashboard stop button is used."""
    server = create_dashboard_server(
        port=port, repository=repository, secret_store=secret_store,
        pricing_repository=pricing_repository,
    )
    application = server.application
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
