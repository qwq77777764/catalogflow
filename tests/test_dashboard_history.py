import json
import threading
import urllib.error
import urllib.request

import pytest

from catalogflow.configuration import MemorySecretStore, ProfileRepository
from catalogflow.dashboard import DashboardApplication, DashboardServer


@pytest.fixture
def history_dashboard(tmp_path):
    application = DashboardApplication(
        ProfileRepository(tmp_path), MemorySecretStore(), "history-test-session"
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


def get_report(application, path, *, token=None, origin=None):
    request = urllib.request.Request(  # noqa: S310 - loopback test server
        application.origin + path,
        headers={
            "X-CatalogFlow-Token": application.token if token is None else token,
            "Origin": origin or application.origin,
        },
    )
    with urllib.request.urlopen(request, timeout=2) as response:  # noqa: S310
        assert response.headers["Cache-Control"] == "no-store"
        return json.load(response)


def test_empty_history_does_not_create_user_files(history_dashboard):
    assert get_report(history_dashboard, "/api/reports") == {"reports": []}
    assert not history_dashboard.history.directory.exists()


@pytest.mark.parametrize("path", ["/api/reports", "/api/reports/invalid/text"])
def test_history_requires_session_and_same_origin(history_dashboard, path):
    with pytest.raises(urllib.error.HTTPError) as error:
        get_report(history_dashboard, path, token="")
    assert error.value.code == 403
    with pytest.raises(urllib.error.HTTPError) as error:
        get_report(history_dashboard, path, origin="https://foreign.example")
    assert error.value.code == 403


@pytest.mark.parametrize(
    "path",
    [
        "/api/reports/..",
        "/api/reports/%2e%2e",
        "/api/reports/%2fprofiles.json/text",
        "/api/reports/invalid/text/extra",
        "/api/reports/invalid",
    ],
)
def test_history_routes_cannot_read_arbitrary_files(history_dashboard, path):
    with pytest.raises(urllib.error.HTTPError) as error:
        get_report(history_dashboard, path)
    assert error.value.code == 404
    assert json.load(error.value) == {"error": "report_not_found"}


def test_history_read_failure_is_redacted(history_dashboard, monkeypatch):
    def unavailable():
        raise OSError("private filesystem marker / credential marker")

    monkeypatch.setattr(history_dashboard.history, "recent", unavailable)
    with pytest.raises(urllib.error.HTTPError) as error:
        get_report(history_dashboard, "/api/reports")
    assert error.value.code == 503
    assert json.load(error.value) == {"error": "reports_unavailable"}


def test_dashboard_reads_durable_run_and_returns_downloadable_txt(history_dashboard):
    run = history_dashboard.history.create_run("dry-run")
    item = run.start_item(
        source="alibaba-manual", source_url="https://supplier.example/product/clock?tracking=test"
    )
    item.update(source_id="synthetic-clock", title="Sample Clock", status="previewed")
    run.finish_item(item)
    run.finish()
    recent = get_report(history_dashboard, "/api/reports")["reports"]
    assert recent[0]["run_id"] == run.run_id
    detail = get_report(history_dashboard, f"/api/reports/{run.run_id}")
    assert detail["items"][0]["status"] == "previewed"
    assert detail["items"][0]["source_url"] == "https://supplier.example/product/clock"
    download = get_report(history_dashboard, f"/api/reports/{run.run_id}/text")
    assert download["filename"].endswith(".txt")
    assert "Sample Clock" in download["text"]
    assert "https://supplier.example/product/clock" in download["text"]
    assert "tracking=test" not in download["text"]
    assert "history-test-session" not in download["text"]
