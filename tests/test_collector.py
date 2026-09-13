import json
import socket
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

import catalogflow.collector as collector_module
from catalogflow.collector import CollectorApplication, CollectorServer
from catalogflow.selection_queue import SelectionQueue, normalize_selection

TOKEN = "synthetic-session-token-that-is-long-enough"  # noqa: S105 - test-only
ALIBABA_ORIGIN = "https://www.alibaba.com"


def start_collector(tmp_path):
    application = CollectorApplication(SelectionQueue(tmp_path / "queue.json"), TOKEN)
    server = CollectorServer(("127.0.0.1", 0), application)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def selection_request(base_url, *, token=TOKEN, origin=ALIBABA_ORIGIN, extra_headers=None):
    payload = json.dumps(
        {
            "version": 1,
            "source": "alibaba",
            "product_url": (
                "https://www.alibaba.com/product-detail/Synthetic_1600000000000.html"
            ),
            "page_title": "Synthetic product",
        }
    ).encode()
    headers = {
        "Content-Type": "application/json",
        "Origin": origin,
        "X-CatalogFlow-Page-Origin": origin,
        "X-CatalogFlow-Token": token,
        **(extra_headers or {}),
    }
    return urllib.request.Request(  # noqa: S310 - loopback test server
        f"{base_url}/api/selections",
        data=payload,
        method="POST",
        headers=headers,
    )


def test_collector_accepts_one_authorized_selection_without_storing_token(tmp_path) -> None:
    server, base_url = start_collector(tmp_path)
    try:
        request = selection_request(base_url)
        with urllib.request.urlopen(request, timeout=2) as response:  # noqa: S310
            result = json.load(response)
        assert response.status == 201
        assert result["created"] is True
        queue_text = (tmp_path / "queue.json").read_text(encoding="utf-8")
        assert TOKEN not in queue_text
    finally:
        server.shutdown()
        server.server_close()


def test_collector_rejects_invalid_session_and_foreign_origin(tmp_path) -> None:
    server, base_url = start_collector(tmp_path)
    try:
        for request in (
            selection_request(base_url, token="wrong-token"),  # noqa: S106 - test-only
            selection_request(base_url, origin="https://untrusted.example"),
        ):
            try:
                urllib.request.urlopen(request, timeout=2)  # noqa: S310
                raise AssertionError("collector accepted an unauthorized request")
            except urllib.error.HTTPError as exc:
                assert exc.code == 403
    finally:
        server.shutdown()
        server.server_close()


def test_collector_rejects_browser_credentials(tmp_path) -> None:
    server, base_url = start_collector(tmp_path)
    request = selection_request(base_url, extra_headers={"Cookie": "session=must-not-pass"})
    try:
        try:
            urllib.request.urlopen(request, timeout=2)  # noqa: S310
            raise AssertionError("collector accepted a Cookie header")
        except urllib.error.HTTPError as exc:
            assert exc.code == 400
    finally:
        server.shutdown()
        server.server_close()


def test_collector_enforces_rate_limit(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(collector_module, "RATE_LIMIT_COUNT", 1)
    server, base_url = start_collector(tmp_path)
    try:
        with urllib.request.urlopen(  # noqa: S310 - loopback test server
            selection_request(base_url), timeout=2
        ) as first_response:
            assert first_response.status == 201
        try:
            urllib.request.urlopen(selection_request(base_url), timeout=2)  # noqa: S310
            raise AssertionError("collector accepted a request above the rate limit")
        except urllib.error.HTTPError as exc:
            assert exc.code == 429
    finally:
        server.shutdown()
        server.server_close()


def test_userscript_install_route_contains_no_session_token(tmp_path) -> None:
    server, base_url = start_collector(tmp_path)
    try:
        with urllib.request.urlopen(  # noqa: S310 - loopback test server
            f"{base_url}/collector.user.js", timeout=2
        ) as response:
            script = response.read().decode("utf-8")
        assert response.status == 200
        assert TOKEN not in script
    finally:
        server.shutdown()
        server.server_close()


def test_cors_header_is_a_fixed_allowed_origin(tmp_path) -> None:
    server, base_url = start_collector(tmp_path)
    request = selection_request(base_url)
    try:
        with urllib.request.urlopen(request, timeout=2) as response:  # noqa: S310
            assert response.headers["Access-Control-Allow-Origin"] == ALIBABA_ORIGIN
            assert response.headers["Vary"] == "Origin"
    finally:
        server.shutdown()
        server.server_close()


def test_packaged_userscript_is_narrow_and_does_not_persist_session_data() -> None:
    script_path = (
        Path(__file__).parents[1]
        / "src"
        / "catalogflow"
        / "browser"
        / "catalogflow-collector.user.js"
    )
    script = script_path.read_text(encoding="utf-8")
    assert "@match        https://www.alibaba.com/product-detail/*" in script
    assert "@connect      127.0.0.1" in script
    assert "GM_setValue" not in script
    assert "localStorage" not in script
    assert "sessionStorage" not in script
    assert "document.documentElement.innerHTML" not in script
    assert "anonymous: true" in script
    assert "window.confirm(preview)" in script
    assert "product_url: productUrl" in script
    assert "product_url: location.href" not in script


@pytest.mark.parametrize("entered", [True, False])
def test_cli_only_freezes_queue_after_explicit_enter(tmp_path, monkeypatch, capsys, entered):
    queue = SelectionQueue(tmp_path / "queue.json")
    queue.add(normalize_selection("alibaba",
              "https://www.alibaba.com/product-detail/Synthetic_1600000000000.html",
              "Synthetic product"))

    class Server:
        server_address = ("127.0.0.1", 45678)

        def __init__(self, *args):
            pass

        def serve_forever(self):
            pass

        def shutdown(self):
            pass

        def server_close(self):
            pass

    def finish(prompt):
        if not entered:
            raise EOFError
        return ""

    monkeypatch.setattr(collector_module, "SelectionQueue", lambda: queue)
    monkeypatch.setattr(collector_module, "CollectorServer", Server)
    monkeypatch.setattr("builtins.input", finish)
    collector_module.run_collector(port=45678)
    assert SelectionQueue(queue.path).frozen is entered
    assert "CATALOGFLOW1:" in capsys.readouterr().out


def _raw_selection_socket(server, data):
    connection = socket.create_connection(server.server_address, timeout=2)
    headers = (
        "POST /api/selections HTTP/1.1\r\n"
        "Host: 127.0.0.1\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(data)}\r\n"
        f"X-CatalogFlow-Token: {TOKEN}\r\n"
        f"X-CatalogFlow-Page-Origin: {ALIBABA_ORIGIN}\r\n\r\n"
    ).encode()
    connection.sendall(headers + data[:1])
    return connection


def test_collector_body_timeout_is_bounded_and_quiet(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(collector_module, "READ_TIMEOUT_SECONDS", 0.1)
    server, base_url = start_collector(tmp_path)
    try:
        data = selection_request(base_url).data
        with _raw_selection_socket(server, data) as connection:
            response = connection.makefile("rb").read()
        assert b"400 Bad Request" in response
        assert b"invalid_selection" in response
        assert not server.application.queue.list()
    finally:
        server.shutdown()
        server.server_close()
    assert capsys.readouterr().err == ""


def test_collector_deep_json_is_rejected_without_handler_traceback(tmp_path, capsys):
    server, base_url = start_collector(tmp_path)
    request = selection_request(base_url)
    request.data = b'{"source":' + b"[" * 2000 + b"0" + b"]" * 2000 + b"}"
    try:
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request, timeout=2)  # noqa: S310 - loopback
        assert error.value.code == 400
        assert not server.application.queue.list()
    finally:
        server.shutdown()
        server.server_close()
    assert capsys.readouterr().err == ""


def test_stopped_collector_rejects_already_accepted_slow_body(tmp_path, monkeypatch, capsys):
    reading = threading.Event()
    read_json = collector_module.CollectorRequestHandler._read_json

    def tracked_read(handler):
        reading.set()
        return read_json(handler)

    monkeypatch.setattr(collector_module.CollectorRequestHandler, "_read_json", tracked_read)
    server, base_url = start_collector(tmp_path)
    data = selection_request(base_url).data
    try:
        with _raw_selection_socket(server, data) as connection:
            assert reading.wait(2)
            server.application.stop_accepting()
            server.shutdown()
            server.server_close()
            connection.sendall(data[1:])
            response = connection.makefile("rb").read()
        assert b"409 Conflict" in response
        assert b"collection_stopped" in response
        assert not server.application.queue.list()
        assert server.application.queue.frozen is False
    finally:
        server.shutdown()
        server.server_close()
    assert capsys.readouterr().err == ""
