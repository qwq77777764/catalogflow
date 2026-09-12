import json
import os
import socketserver
import threading
import urllib.error
import urllib.request
from http.client import IncompleteRead, RemoteDisconnected

import pytest

from catalogflow import dashboard
from catalogflow.configuration import MemorySecretStore, ProfileRepository
from catalogflow.dashboard import DashboardApplication, DashboardServer
from catalogflow.exchange_rates import ExchangeRateService
from catalogflow.pricing import PricingPolicy


def start_dashboard(tmp_path):
    application = DashboardApplication(
        ProfileRepository(tmp_path), MemorySecretStore(), "test-session-token"
    )
    server = DashboardServer(("127.0.0.1", 0), application)
    application.origin = f"http://127.0.0.1:{server.server_address[1]}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, application.origin


def post_json(origin, path, payload, *, token=None, include_token=True):
    header_token = token if token is not None else "test-session-token"
    request = urllib.request.Request(  # noqa: S310 - loopback test server
        f"{origin}{path}",
        data=json.dumps(payload).encode(),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Origin": origin,
            **({"X-CatalogFlow-Token": header_token} if include_token else {}),
        },
    )
    with urllib.request.urlopen(request, timeout=2) as response:  # noqa: S310
        return json.load(response)


@pytest.mark.parametrize(
    "request_path, content_type, body",
    [
        ("/", "text/html; charset=utf-8", b"<html lang='en-US'></html>"),
        (
            "/assets/dashboard-i18n.js",
            "text/javascript; charset=utf-8",
            'window.languageLabel = "中文 / EN (US)";'.encode(),
        ),
        (
            "/assets/dashboard-i18n.js?lang=en-US",
            "text/javascript; charset=utf-8",
            'window.languageLabel = "中文 / EN (US)";'.encode(),
        ),
        (
            "/assets/dashboard-fx.js",
            "text/javascript; charset=utf-8",
            b"window.CatalogFlowFX = {};",
        ),
        (
            "/assets/dashboard-history.js",
            "text/javascript; charset=utf-8",
            b"window.CatalogFlowHistory = {};",
        ),
    ],
)
def test_dashboard_static_assets_are_available_with_security_headers(
    tmp_path, monkeypatch, request_path, content_type, body
) -> None:
    assets = tmp_path / "assets"
    assets.mkdir()
    filename = (
        "dashboard.html" if request_path == "/" else request_path.split("?")[0].split("/")[-1]
    )
    (assets / filename).write_bytes(body)
    monkeypatch.setattr(dashboard, "__file__", str(assets / "dashboard.py"))
    server, origin = start_dashboard(tmp_path / "profile")
    try:
        with urllib.request.urlopen(f"{origin}{request_path}", timeout=2) as response:  # noqa: S310
            assert response.status == 200
            assert response.read() == body
            assert response.headers["Content-Type"] == content_type
            assert response.headers["Cache-Control"] == "no-store"
            assert response.headers["X-Content-Type-Options"] == "nosniff"
            assert response.headers["X-Frame-Options"] == "DENY"
            assert response.headers["Referrer-Policy"] == "no-referrer"
            directives = {
                parts[0]: set(parts[1:])
                for directive in response.headers["Content-Security-Policy"].split(";")
                if (parts := directive.split())
            }
            assert "'self'" in directives["script-src"]
            assert directives["default-src"] == {"'none'"}
            assert directives["connect-src"] == {"'self'"}
            assert directives["frame-ancestors"] == {"'none'"}
        assert not (tmp_path / "profile").exists()
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.parametrize(
    "request_path",
    [
        "/assets/../dashboard.py",
        "/assets/%2e%2e/dashboard.py",
        "/assets/dashboard-i18n.js/../dashboard.py",
        "/assets/dashboard-fx.js/../dashboard.py",
        "/assets/dashboard-history.js/../dashboard.py",
        "/assets/dashboard.py",
    ],
)
def test_dashboard_static_asset_route_does_not_expose_other_files(
    tmp_path, monkeypatch, request_path
) -> None:
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "dashboard.py").write_text("private-source-marker", encoding="utf-8")
    (tmp_path / "dashboard.py").write_text("private-parent-marker", encoding="utf-8")
    monkeypatch.setattr(dashboard, "__file__", str(assets / "dashboard.py"))
    server, origin = start_dashboard(tmp_path / "profile")
    try:
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(f"{origin}{request_path}", timeout=2)  # noqa: S310
        assert error.value.code == 404
        assert json.load(error.value) == {"error": "not_found"}
    finally:
        server.shutdown()
        server.server_close()


def test_dashboard_rejects_requests_without_session_token(tmp_path) -> None:
    server, origin = start_dashboard(tmp_path)
    try:
        with urllib.request.urlopen(f"{origin}/api/state", timeout=2):  # noqa: S310
            raise AssertionError("dashboard accepted a request without its session token")
    except urllib.error.HTTPError as exc:
        assert exc.code == 403
    finally:
        server.shutdown()
        server.server_close()


def test_dashboard_rejects_a_foreign_origin(tmp_path) -> None:
    server, origin = start_dashboard(tmp_path)
    request = urllib.request.Request(  # noqa: S310 - loopback test server
        f"{origin}/api/state",
        headers={
            "Origin": "https://untrusted.example",
            "X-CatalogFlow-Token": "test-session-token",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=2):  # noqa: S310
            raise AssertionError("dashboard accepted a request from a foreign origin")
    except urllib.error.HTTPError as exc:
        assert exc.code == 403
    finally:
        server.shutdown()
        server.server_close()


def test_dashboard_saves_profile_without_returning_secret(tmp_path) -> None:
    server, origin = start_dashboard(tmp_path)
    payload = json.dumps(
        {
            "provider": "cj",
            "label": "My official CJ account",
            "notes": "Applied through the provider portal",
            "values": {},
            "secrets": {"api_key": "never-return-this"},
            "is_default": True,
        }
    ).encode()
    request = urllib.request.Request(  # noqa: S310 - loopback test server
        f"{origin}/api/profiles",
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Origin": origin,
            "X-CatalogFlow-Token": "test-session-token",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=2) as response:  # noqa: S310
            result = json.load(response)
        serialized = json.dumps(result)
        assert "never-return-this" not in serialized
        assert result["profile"]["configured_secret_fields"] == ["api_key"]
    finally:
        server.shutdown()
        server.server_close()


def test_dashboard_state_exposes_validated_pricing_defaults(tmp_path) -> None:
    server, origin = start_dashboard(tmp_path)
    saved_policy = PricingPolicy(scheme="cost_multiplier", cost_multiplier=7)
    request = urllib.request.Request(  # noqa: S310 - loopback test server
        f"{origin}/api/state",
        headers={"X-CatalogFlow-Token": "test-session-token"},
    )
    try:
        post_json(origin, "/api/pricing", saved_policy.to_dict())
        saved_bytes = (tmp_path / "pricing.json").read_bytes()
        with urllib.request.urlopen(request, timeout=2) as response:  # noqa: S310
            state = json.load(response)
        assert state["pricing"] == saved_policy.to_dict()
        assert state["pricing_defaults"] == PricingPolicy().to_dict()
        assert (tmp_path / "pricing.json").read_bytes() == saved_bytes
    finally:
        server.shutdown()
        server.server_close()


def test_dashboard_saves_and_previews_cost_multiplier_plan(tmp_path) -> None:
    server, origin = start_dashboard(tmp_path)
    settings = PricingPolicy().to_dict()
    settings.update(
        {"scheme": "cost_multiplier", "cost_multiplier": 10, "tax_duties_per_unit": 1}
    )
    try:
        saved = post_json(origin, "/api/pricing", settings)
        preview = post_json(
            origin,
            "/api/pricing/preview",
            {
                "settings": saved["pricing"],
                "costs": {
                    "product_cost": 2,
                    "inbound_shipping": 3,
                    "last_mile": 4,
                },
            },
        )
        assert (tmp_path / "pricing.json").exists()
        assert preview["breakdown"]["raw_price"] == 28.4
        assert preview["breakdown"]["final_price"] == 28.95
    finally:
        server.shutdown()
        server.server_close()


def test_dashboard_formula_preview_save_and_invalid_request_preserve_settings(tmp_path):
    server, origin = start_dashboard(tmp_path)
    settings = PricingPolicy(scheme="cost_multiplier", cost_formula="*5/2+3-1").to_dict()
    costs = {"product_cost": 8.5, "inbound_shipping": 1, "last_mile": 4.71}
    try:
        result = post_json(origin, "/api/pricing/preview", {"settings": settings, "costs": costs})
        assert result["breakdown"]["formula_cost"] == 23.25
        assert result["breakdown"]["primary_candidate"] == 29.36
        assert result["breakdown"]["final_price"] == 29.95
        assert not (tmp_path / "pricing.json").exists()
        saved = post_json(origin, "/api/pricing", settings)["pricing"]
        assert saved["cost_formula"] == "*5/2+3-1"
        before = (tmp_path / "pricing.json").read_bytes()
        for path in ("/api/pricing", "/api/pricing/preview"):
            invalid = {**settings, "cost_formula": "/(5-5)"}
            body = invalid if path == "/api/pricing" else {"settings": invalid, "costs": costs}
            with pytest.raises(urllib.error.HTTPError) as caught:
                post_json(origin, path, body)
            assert caught.value.code == 400
            assert json.load(caught.value)["error"] == "cost_formula_division_by_zero"
            assert (tmp_path / "pricing.json").read_bytes() == before
        # A valid A preview keeps working when B's result is invalid for this sample cost.
        alternate = {**settings, "scheme": "margin", "cost_formula": "-20"}
        result = post_json(origin, "/api/pricing/preview", {"settings": alternate, "costs": costs})
        assert result["comparison"]["margin"]["breakdown"]["final_price"] > 0
        assert (
            result["comparison"]["cost_multiplier"]["error"]
            == "cost_formula_result_out_of_range"
        )
    finally:
        server.shutdown()
        server.server_close()


def test_pricing_endpoint_rejects_invalid_fields_and_missing_token(tmp_path) -> None:
    server, origin = start_dashboard(tmp_path)
    invalid = {**PricingPolicy().to_dict(), "unexpected": 1}
    try:
        with pytest.raises(urllib.error.HTTPError) as invalid_error:
            post_json(origin, "/api/pricing", invalid)
        assert invalid_error.value.code == 400

        with pytest.raises(urllib.error.HTTPError) as auth_error:
            post_json(
                origin,
                "/api/pricing",
                PricingPolicy().to_dict(),
                include_token=False,
            )
        assert auth_error.value.code == 403
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.parametrize("previously_saved", [False, True])
def test_pricing_preview_compares_schemes_without_changing_saved_settings(
    tmp_path, previously_saved
) -> None:
    server, origin = start_dashboard(tmp_path)
    pricing_path = tmp_path / "pricing.json"
    settings = PricingPolicy(
        scheme="cost_multiplier", cost_multiplier=10, tax_duties_per_unit=1
    ).to_dict()
    try:
        if previously_saved:
            post_json(origin, "/api/pricing", PricingPolicy(minimum_price=50).to_dict())
        saved_bytes = pricing_path.read_bytes() if previously_saved else None

        result = post_json(
            origin,
            "/api/pricing/preview",
            {
                "settings": settings,
                "costs": {"product_cost": 2, "inbound_shipping": 3, "last_mile": 4},
            },
        )

        assert result["breakdown"] == result["comparison"]["cost_multiplier"]["breakdown"]
        assert result["breakdown"]["final_price"] == 28.95
        assert result["comparison"]["margin"]["breakdown"]["final_price"] == 26.95
        assert result["comparison"]["margin"]["breakdown"]["landed_cost"] == 10
        if previously_saved:
            assert pricing_path.read_bytes() == saved_bytes
        else:
            assert not pricing_path.exists()
    finally:
        server.shutdown()
        server.server_close()


def test_pricing_preview_isolates_invalid_alternative_but_rejects_invalid_selection(
    tmp_path,
) -> None:
    server, origin = start_dashboard(tmp_path)
    settings = PricingPolicy(
        scheme="cost_multiplier",
        cost_multiplier=1,
        payment_fee_rate=0.3,
        return_rate=0.2,
        operating_rate=0.1,
    ).to_dict()
    payload = {
        "settings": settings,
        "costs": {"product_cost": 10, "inbound_shipping": 0, "last_mile": 5},
    }
    try:
        result = post_json(origin, "/api/pricing/preview", payload)

        assert result["breakdown"]["final_price"] == 15.95
        assert result["breakdown"]["estimated_profit"] == pytest.approx(-9.02)
        assert result["comparison"]["margin"] == {
            "error": "This scheme is unavailable for the current settings and costs."
        }
        assert result["comparison"]["cost_multiplier"]["breakdown"] == result["breakdown"]

        settings["scheme"] = "margin"
        with pytest.raises(urllib.error.HTTPError) as invalid_error:
            post_json(origin, "/api/pricing/preview", payload)
        assert invalid_error.value.code == 400
        assert not (tmp_path / "pricing.json").exists()
    finally:
        server.shutdown()
        server.server_close()


def test_pricing_save_reports_storage_failure_and_preserves_previous_settings(
    tmp_path, monkeypatch
) -> None:
    server, origin = start_dashboard(tmp_path)
    pricing_path = tmp_path / "pricing.json"

    def unavailable_replace(*_args):
        raise OSError("Synthetic filesystem failure with private path details")

    try:
        post_json(origin, "/api/pricing", PricingPolicy().to_dict())
        saved_bytes = pricing_path.read_bytes()
        monkeypatch.setattr(os, "replace", unavailable_replace)

        with pytest.raises(urllib.error.HTTPError) as save_error:
            post_json(origin, "/api/pricing", PricingPolicy(minimum_price=99.95).to_dict())

        assert save_error.value.code == 503
        assert json.load(save_error.value) == {"error": "Pricing settings could not be saved."}
        assert pricing_path.read_bytes() == saved_bytes
        assert not list(tmp_path.glob(".pricing-*.tmp"))
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.parametrize("disconnect_at", ["headers", "body"])
def test_cancelled_preview_does_not_log_traceback_or_break_later_requests(
    tmp_path, monkeypatch, capsys, disconnect_at
) -> None:
    server, origin = start_dashboard(tmp_path)
    # Join request workers at close so stderr assertions cannot race their cleanup.
    server.daemon_threads = False
    original_write = socketserver._SocketWriter.write
    disconnected = False

    def write_with_one_disconnect(writer, data):
        nonlocal disconnected
        target = (
            data.startswith(b"HTTP/")
            if disconnect_at == "headers"
            else data.startswith(b'{"breakdown"')
        )
        if target and not disconnected:
            disconnected = True
            raise ConnectionAbortedError("Synthetic browser cancelled its previous preview")
        return original_write(writer, data)

    monkeypatch.setattr(socketserver._SocketWriter, "write", write_with_one_disconnect)
    payload = {
        "settings": PricingPolicy().to_dict(),
        "costs": {"product_cost": 8.5, "inbound_shipping": 0, "last_mile": 4.71},
    }
    try:
        with pytest.raises((IncompleteRead, RemoteDisconnected)):
            post_json(origin, "/api/pricing/preview", payload)

        result = post_json(origin, "/api/pricing/preview", payload)
        assert result["breakdown"]["final_price"] == 34.95
    finally:
        server.shutdown()
        server.server_close()

    assert disconnected
    assert capsys.readouterr().err == ""


def test_exchange_rates_require_auth_are_lazy_and_do_not_write_configuration(tmp_path):
    server, origin = start_dashboard(tmp_path)
    calls = []
    rates = {
        code: 1.5 for code in ("CNY", "EUR", "GBP", "JPY", "CAD", "AUD", "HKD", "SGD", "CHF", "NZD")
    }

    def fetch():
        calls.append(True)
        return json.dumps({"base": "USD", "date": "2026-01-02", "rates": rates}).encode()

    server.application.exchange_rate_service = ExchangeRateService(fetch=fetch)

    def get(path, headers):
        request = urllib.request.Request(origin + path, headers=headers)  # noqa: S310
        return urllib.request.urlopen(request, timeout=2)  # noqa: S310

    token = {"X-CatalogFlow-Token": "test-session-token"}
    try:
        with get("/api/state", token) as response:
            assert "pricing" in json.load(response)
        post_json(origin, "/api/pricing/preview", {
            "settings": PricingPolicy().to_dict(),
            "costs": {"product_cost": 8.5, "inbound_shipping": 0, "last_mile": 4.71},
        })
        assert calls == []
        for headers in ({}, {"X-CatalogFlow-Token": "wrong"}, {**token, "Origin": "https://other.example"}):
            with pytest.raises(urllib.error.HTTPError) as failure:
                get("/api/exchange-rates", headers)
            assert failure.value.code == 403
        assert calls == []
        for _ in range(2):
            with get("/api/exchange-rates", {**token, "Origin": origin}) as response:
                result = json.load(response)
                assert result["base"] == "USD"
                assert result["rates"] == {"USD": 1, **rates}
                assert response.headers["Cache-Control"] == "no-store"
        assert calls == [True]
        assert list(tmp_path.iterdir()) == []
    finally:
        server.shutdown()
        server.server_close()


def test_exchange_rate_failure_is_redacted_and_pricing_still_works(tmp_path):
    server, origin = start_dashboard(tmp_path)

    def unavailable():
        raise OSError("Synthetic private network details")

    server.application.exchange_rate_service = ExchangeRateService(fetch=unavailable)
    try:
        request = urllib.request.Request(  # noqa: S310
            origin + "/api/exchange-rates",
            headers={"X-CatalogFlow-Token": "test-session-token"},
        )
        with pytest.raises(urllib.error.HTTPError) as failure:
            urllib.request.urlopen(request, timeout=2)  # noqa: S310
        assert failure.value.code == 503
        assert json.load(failure.value) == {"error": "exchange_rates_unavailable"}
        result = post_json(origin, "/api/pricing/preview", {
            "settings": PricingPolicy().to_dict(),
            "costs": {"product_cost": 8.5, "inbound_shipping": 0, "last_mile": 4.71},
        })
        assert result["breakdown"]["final_price"] == 34.95
        assert list(tmp_path.iterdir()) == []
    finally:
        server.shutdown()
        server.server_close()
