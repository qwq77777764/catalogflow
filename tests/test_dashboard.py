import json
import threading
import urllib.error
import urllib.request

import pytest

from catalogflow.configuration import MemorySecretStore, ProfileRepository
from catalogflow.dashboard import DashboardApplication, DashboardServer
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
    request = urllib.request.Request(  # noqa: S310 - loopback test server
        f"{origin}/api/state",
        headers={"X-CatalogFlow-Token": "test-session-token"},
    )
    try:
        with urllib.request.urlopen(request, timeout=2) as response:  # noqa: S310
            state = json.load(response)
        assert state["pricing"] == PricingPolicy().to_dict()
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
