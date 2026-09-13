"""The novice journey crosses real authenticated HTTP boundaries without outside services."""

import base64
import json
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
from contextlib import contextmanager

import pytest

from catalogflow import import_wizard
from catalogflow.ai_setup import AISetup
from catalogflow.configuration import MemorySecretStore, ProfileRepository
from catalogflow.dashboard import DashboardApplication, DashboardServer
from catalogflow.generators import DeterministicListingGenerator
from catalogflow.models import Product, ShippingQuote, Variant

CJ_URL = ("https://www.cjdropshipping.com/product/synthetic-clock-p-"
          "11111111-2222-4333-8444-555555555555.html")


@contextmanager
def dashboard(tmp_path):
    app = DashboardApplication(ProfileRepository(tmp_path), MemorySecretStore(), "test-session")
    server = DashboardServer(("127.0.0.1", 0), app)
    app.origin = f"http://127.0.0.1:{server.server_address[1]}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield app
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def request(app, path, payload=None, *, token=None, origin=None):
    req = urllib.request.Request(  # noqa: S310 - test loopback server
        app.origin + path,
        data=None if payload is None else json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "X-CatalogFlow-Token": token or app.token,
                 "Origin": app.origin if origin is None else origin},
    )
    try:
        with urllib.request.urlopen(req, timeout=3) as response:  # noqa: S310
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.load(error)


@pytest.mark.parametrize("path,payload", [
    ("/api/ai-setup", None), ("/api/ai-setup/check", {"provider": "codex"}),
    ("/api/ai-setup/login", {"provider": "codex"}),
    ("/api/ai-setup/test", {"provider": "codex", "confirm_usage": True}),
    ("/api/selection-workflow", None), ("/api/selection-workflow/start", {}),
    ("/api/selection-workflow/import", {"queue": {}}),
])
def test_new_workflow_endpoints_require_session_and_same_origin(tmp_path, path, payload):
    with dashboard(tmp_path) as app:
        assert request(app, path, payload, token=app.token + "invalid")[0] == 403
        assert request(app, path, payload, origin="https://www.alibaba.com")[0] == 403


def test_browser_selection_freeze_to_preview_uses_no_real_services(tmp_path, monkeypatch):
    fetched = []

    class FakeCJ:
        def __init__(self, *args, **kwargs):
            pass

        def fetch(self, reference):
            fetched.append(reference)
            return Product(source="cj", source_id="synthetic-clock", title="Synthetic desk clock",
                           currency="USD",
                           variants=(Variant(sku="SYNTHETIC-OAK", cost=8,
                                             attributes={"Finish": "Oak"},
                                             shipping_quote=ShippingQuote("CN", "US", 1,
                                                                          "Synthetic", 4)),),
                           facts={"Material": "Wood"}, images=(), source_url=reference)

    monkeypatch.setattr(import_wizard, "CjApiSource", FakeCJ)
    with dashboard(tmp_path) as app:
        profile = app.repository.save(provider="cj", label="Synthetic CJ", notes="Test only",
                                      values={}, secrets={"api_key": "synthetic-cj-key"},
                                      secret_store=app.secret_store)
        status, started = request(app, "/api/selection-workflow/start", {})
        assert status == 202
        active = started["active"]
        encoded = active["pairing_code"].split(":", 1)[1]
        pairing = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        assert pairing["token"] != app.token
        payload = {"version": 1, "source": "cj", "product_url": CJ_URL,
                   "page_title": "Synthetic desk clock"}
        collect = urllib.request.Request(  # noqa: S310 - separate loopback collector
            active["endpoint"] + "/api/selections", data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", "X-CatalogFlow-Token": pairing["token"],
                     "X-CatalogFlow-Page-Origin": "https://www.cjdropshipping.com"},
        )
        with urllib.request.urlopen(collect, timeout=3) as response:  # noqa: S310
            assert response.status == 201
        _, state = request(app, "/api/selection-workflow")
        item = state["items"][0]
        assert item["frozen"] is False and not fetched
        assert request(app, "/api/selection-workflow/select", {"id": item["id"]})[0] == 409
        frozen = request(app, "/api/selection-workflow/freeze", {"queue_id": active["queue_id"]})
        assert frozen[0] == 202
        _, selected = request(app, "/api/selection-workflow/select", {"id": item["id"]})
        assert selected["item"]["importable"] is True
        assert not fetched  # Selecting a row never invokes a supplier or AI.
        _, job = request(app, "/api/imports/preview", {
            "source": "cj", "source_input": selected["item"]["url"],
            "source_profile_id": profile.id, "generator": "deterministic",
            "ai_profile_id": None, "store_profile_id": None,
        })
        deadline = time.monotonic() + 4
        while job["job"]["status"] == "running" and time.monotonic() < deadline:
            time.sleep(0.01)
            _, job = request(app, "/api/imports/current")
        assert job["job"]["status"] == "ready"
        assert job["job"]["preview"]["store"] is None
        assert fetched == [CJ_URL]
        assert app.history.recent()
    # Only an explicitly frozen queue can be selected in a new process/session.
    with dashboard(tmp_path) as reopened:
        _, state = request(reopened, "/api/selection-workflow")
        assert state["active"] is None
        assert state["items"][0]["frozen"] is True


def test_legacy_alibaba_selection_enters_manual_review_without_automatic_fetch(tmp_path):
    with dashboard(tmp_path) as app:
        legacy = {"version": 1, "items": [{
            "id": "d6dc4a76-c358-4f52-b731-5b52f2185721", "source": "alibaba",
            "product_url": "https://www.alibaba.com/product-detail/synthetic-clock_10000000001.html",
            "page_title": "Synthetic clock", "selected_at": "2026-01-01T00:00:00+00:00",
        }]}
        status, state = request(app, "/api/selection-workflow/import", {"queue": legacy})
        assert status == 202
        item = state["items"][0]
        assert item["source"] == "alibaba" and item["frozen"] is True
        assert item["importable"] is False
        _, selected = request(app, "/api/selection-workflow/select", {"id": item["id"]})
        assert selected["item"]["url"] == legacy["items"][0]["product_url"]
        assert app.imports.current() is None


def test_ai_readiness_and_test_are_separate_actions_and_busy_work_blocks_shutdown(tmp_path):
    entered = threading.Event()
    release = threading.Event()
    calls = []

    class SyntheticGenerator:
        def generate(self, product):
            assert product.images == () and product.source_id == "synthetic-ai-check"
            entered.set()
            assert release.wait(3)
            return DeterministicListingGenerator().generate(product)

    def runner(command, **kwargs):
        calls.append(command)
        output = "codex-cli 0.154.0" if command[-1] == "--version" else "Logged in using ChatGPT"
        return subprocess.CompletedProcess(command, 0, output, "")

    with dashboard(tmp_path) as app:
        app.ai_setup = AISetup(app.repository, finder=lambda *a, **kw: "synthetic-codex.exe",
                               runner=runner, generator_factory=lambda *a: SyntheticGenerator())
        assert request(app, "/api/ai-setup")[1]["phase"] == "idle"
        assert not calls
        assert request(app, "/api/ai-setup/test", {"provider": "codex"})[0] == 400
        assert request(app, "/api/ai-setup/check", {
            "provider": "codex", "command": "arbitrary-command",
        })[0] == 400
        assert not calls
        assert request(app, "/api/ai-setup/test", {
            "provider": "codex", "profile_id": None, "confirm_usage": True,
        })[0] == 202
        assert entered.wait(3)
        try:
            assert request(app, "/api/shutdown", {})[0] == 409
            assert request(app, "/api/imports/preview", {})[0] == 409
            assert app.imports.current() is None
        finally:
            release.set()
        deadline = time.monotonic() + 3
        while app.ai_setup.busy and time.monotonic() < deadline:
            time.sleep(0.01)
        state = request(app, "/api/ai-setup")[1]
        assert state["status"] == "test_passed" and state["usage_verified"] is True
        assert app.prepare_shutdown() is True
        assert request(app, "/api/selection-workflow/start", {})[0] == 409


def test_stalled_request_body_does_not_hold_workflow_lifecycle_lock(tmp_path):
    with dashboard(tmp_path) as app:
        port = int(app.origin.rsplit(":", 1)[1])
        with socket.create_connection(("127.0.0.1", port), timeout=2) as stalled:
            headers = ("POST /api/selection-workflow/start HTTP/1.0\r\n"
                       f"Origin: {app.origin}\r\nX-CatalogFlow-Token: {app.token}\r\n"
                       "Content-Type: application/json\r\nContent-Length: 2\r\n\r\n")
            stalled.sendall(headers.encode())
            time.sleep(0.05)
            # This independent action must complete while the first body is still missing.
            status, started = request(app, "/api/selection-workflow/start", {})
            assert status == 202 and started["active"] is not None
            stalled.sendall(b"{}")
            assert b"202" in stalled.recv(4096)
