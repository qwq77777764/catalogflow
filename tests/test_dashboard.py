import json
import threading
import urllib.error
import urllib.request

from catalogflow.configuration import MemorySecretStore, ProfileRepository
from catalogflow.dashboard import DashboardApplication, DashboardServer


def start_dashboard(tmp_path):
    application = DashboardApplication(
        ProfileRepository(tmp_path), MemorySecretStore(), "test-session-token"
    )
    server = DashboardServer(("127.0.0.1", 0), application)
    application.origin = f"http://127.0.0.1:{server.server_address[1]}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, application.origin


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
