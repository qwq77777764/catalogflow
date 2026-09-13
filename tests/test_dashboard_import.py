"""Exercise the authenticated HTTP seam, including review and shutdown boundaries."""

import json
import threading
import time
import urllib.error
import urllib.request

import pytest

from catalogflow.configuration import MemorySecretStore, ProfileRepository
from catalogflow.dashboard import DashboardApplication, DashboardServer


@pytest.fixture
def wizard_dashboard(tmp_path):
    application = DashboardApplication(
        ProfileRepository(tmp_path), MemorySecretStore(), "wizard-test-session"
    )
    server = DashboardServer(("127.0.0.1", 0), application)
    application.origin = f"http://127.0.0.1:{server.server_address[1]}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield application
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def request(application, path, payload=None, *, token=None, origin=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(  # noqa: S310 - isolated loopback test server
        application.origin + path, data=data,
        headers={
            "Content-Type": "application/json",
            "X-CatalogFlow-Token": application.token if token is None else token,
            "Origin": application.origin if origin is None else origin,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=3) as response:  # noqa: S310
            assert response.headers["Cache-Control"] == "no-store"
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.load(error)


def preview_request():
    return {
        "source": "alibaba-manual",
        "source_input": {
            "source_id": "wizard-http-clock", "title": "Wood Desk Clock", "currency": "USD",
            "source_url": "https://supplier.example/clock",
            "variants": [{"sku": "CLOCK-OAK", "cost": 8.5, "attributes": {"Finish": "Oak"}}],
            "images": [], "facts": {"material": "wood"},
        },
        "source_profile_id": None, "generator": "deterministic",
        "ai_profile_id": None, "store_profile_id": None,
    }


@pytest.mark.parametrize("path,payload", [
    ("/api/imports/current", None),
    ("/api/imports/unknown", None),
    ("/api/imports/preview", preview_request()),
    ("/api/imports/unknown/draft", {"confirm_hidden_draft": True}),
])
def test_import_endpoints_require_session_and_exact_origin(wizard_dashboard, path, payload):
    assert request(wizard_dashboard, path, payload, token="")[0] == 403
    assert request(wizard_dashboard, path, payload, origin="https://foreign.example")[0] == 403
    assert wizard_dashboard.imports.current() is None
    assert not wizard_dashboard.history.directory.exists()


def test_http_preview_is_read_only_and_uses_saved_report(wizard_dashboard):
    assert request(wizard_dashboard, "/api/imports/current") == (200, {"job": None})
    status, response = request(wizard_dashboard, "/api/imports/preview", preview_request())
    assert status == 202
    job_id = response["job"]["id"]
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        status, response = request(wizard_dashboard, f"/api/imports/{job_id}")
        assert status == 200
        if response["job"]["status"] != "running":
            break
        time.sleep(0.02)
    job = response["job"]
    assert job["status"] == "ready"
    assert job["preview"]["store"] is None
    assert job["preview"]["listing"]["prices_by_sku"]["CLOCK-OAK"] > 8.5
    assert job["result"]["status"] == "previewed"
    _, report = request(wizard_dashboard, "/api/reports/" + job["report_run_id"])
    assert report["items"][0]["source_url"] == "https://supplier.example/clock"
    assert report["items"][0]["status"] == "previewed"
    # A forged target or price cannot turn a preview-only request into a store write.
    status, _ = request(wizard_dashboard, f"/api/imports/{job_id}/draft", {
        "revision": job["revision"], "confirm_hidden_draft": True,
        "store_profile_id": "forged-target", "prices": {"CLOCK-OAK": 1},
    })
    assert status == 400
    assert request(wizard_dashboard, "/api/imports/current")[1]["job"]["status"] == "ready"


def test_import_errors_do_not_expose_internal_details(wizard_dashboard, monkeypatch):
    def unavailable():
        raise RuntimeError("credential-marker / private/local/path")

    monkeypatch.setattr(wizard_dashboard.imports, "current", unavailable)
    assert request(wizard_dashboard, "/api/imports/current") == (
        503, {"error": "import_configuration_failed"}
    )


def test_shutdown_is_rejected_while_import_is_running(wizard_dashboard, monkeypatch):
    monkeypatch.setattr(wizard_dashboard.imports, "prepare_shutdown", lambda: False)
    assert request(wizard_dashboard, "/api/shutdown", {}) == (409, {"error": "workflow_busy"})
    assert request(wizard_dashboard, "/api/imports/current")[0] == 200


@pytest.mark.parametrize("path", [
    "/api/imports/../profiles.json", "/api/imports/%2e%2e", "/api/imports/a/b",
    "/api/imports/current/draft/extra",
])
def test_import_job_paths_do_not_read_files(wizard_dashboard, path):
    assert request(wizard_dashboard, path)[0] == 404
