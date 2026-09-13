"""Authenticated loopback receiver for user-initiated browser selections."""

from __future__ import annotations

import base64
import hmac
import json
import secrets
import threading
import time
from collections import deque
from collections.abc import Callable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .selection_queue import (
    SOURCE_RULES,
    ProductSelection,
    SelectionQueue,
    normalize_selection,
)

MAX_REQUEST_BYTES = 16 * 1024
READ_TIMEOUT_SECONDS = 10
RATE_LIMIT_COUNT = 30
RATE_LIMIT_WINDOW_SECONDS = 60
ALLOWED_FIELDS = frozenset({"version", "source", "product_url", "page_title"})
FORBIDDEN_HEADERS = ("Authorization", "Cookie", "Proxy-Authorization")


class CollectorApplication:
    def __init__(
        self,
        queue: SelectionQueue,
        token: str,
        on_selection: Callable[[ProductSelection, bool], None] | None = None,
    ) -> None:
        self.queue = queue
        self.token = token
        self.on_selection = on_selection
        self._requests: deque[float] = deque()
        self._rate_lock = threading.Lock()
        self._accept_lock = threading.Lock()
        self._accepting = True

    def stop_accepting(self) -> None:
        """Revoke this collection session, including already accepted slow requests."""
        with self._accept_lock:
            self._accepting = False

    def receive(self, selection: ProductSelection) -> tuple[ProductSelection, bool]:
        with self._accept_lock:
            if not self._accepting:
                raise ValueError("collection_stopped")
            saved, created = self.queue.add(selection)
            if self.on_selection:
                self.on_selection(saved, created)
            return saved, created

    def allowed_page_origins(self) -> frozenset[str]:
        origins: set[str] = set()
        for rule in SOURCE_RULES.values():
            origins.update(rule["page_origins"])
        return frozenset(origins)

    def consume_rate_limit(self) -> bool:
        now = time.monotonic()
        with self._rate_lock:
            while self._requests and now - self._requests[0] >= RATE_LIMIT_WINDOW_SECONDS:
                self._requests.popleft()
            if len(self._requests) >= RATE_LIMIT_COUNT:
                return False
            self._requests.append(now)
            return True


class CollectorServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, application: CollectorApplication) -> None:
        self.application = application
        super().__init__(address, CollectorRequestHandler)

    def server_close(self) -> None:
        self.application.stop_accepting()
        super().server_close()


class CollectorRequestHandler(BaseHTTPRequestHandler):
    server: CollectorServer

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(READ_TIMEOUT_SECONDS)

    def do_OPTIONS(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        origin = self.headers.get("Origin", "")
        if origin not in self.server.application.allowed_page_origins():
            self._send_json(HTTPStatus.FORBIDDEN, {"error": "invalid_origin"})
            return
        self.send_response(HTTPStatus.NO_CONTENT)
        self._security_headers("text/plain; charset=utf-8", origin)
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type, X-CatalogFlow-Token, X-CatalogFlow-Page-Origin",
        )
        self.send_header("Access-Control-Max-Age", "300")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        path = urlparse(self.path).path
        if path == "/collector.user.js":
            self._serve_userscript()
            return
        if path == "/api/queue":
            if not self._authorized():
                return
            items = [
                {
                    "id": item.id,
                    "source": item.source,
                    "product_url": item.product_url,
                    "page_title": item.page_title,
                    "selected_at": item.selected_at,
                }
                for item in self.server.application.queue.list()
            ]
            self._send_json(HTTPStatus.OK, {"version": 1, "items": items})
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if urlparse(self.path).path != "/api/selections":
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        if not self._authorized(require_page_origin=True):
            return
        if not self.server.application.consume_rate_limit():
            self._send_json(HTTPStatus.TOO_MANY_REQUESTS, {"error": "rate_limited"})
            return
        try:
            payload = self._read_json()
            unknown = set(payload) - ALLOWED_FIELDS
            if unknown:
                raise ValueError("Selection contains unsupported fields")
            if type(payload.get("version")) is not int or payload["version"] != 1:
                raise ValueError("Unsupported selection schema version")
            source = str(payload.get("source") or "")
            declared_origin = self.headers.get("X-CatalogFlow-Page-Origin", "")
            rule = SOURCE_RULES.get(source)
            if not rule or declared_origin not in rule["page_origins"]:
                raise ValueError("Selection source does not match the page origin")
            selection = normalize_selection(
                source, payload.get("product_url"), payload.get("page_title"),
            )
            parsed_selection = urlparse(selection.product_url)
            if f"https://{parsed_selection.hostname}" != declared_origin:
                raise ValueError("Selection URL does not match the page origin")
            saved, created = self.server.application.receive(selection)
        except ValueError as exc:
            stopped = str(exc) in {"queue_frozen", "collection_stopped"}
            self._send_json(HTTPStatus.CONFLICT if stopped else HTTPStatus.BAD_REQUEST,
                            {"error": str(exc) if stopped else "invalid_selection"})
            return
        except (OSError, RuntimeError):
            self._send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "queue_unavailable"})
            return
        self._send_json(
            HTTPStatus.CREATED if created else HTTPStatus.OK,
            {"ok": True, "created": created, "id": saved.id},
        )

    def _authorized(self, *, require_page_origin: bool = False) -> bool:
        for header in FORBIDDEN_HEADERS:
            if self.headers.get(header):
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "forbidden_header"})
                return False
        supplied = self.headers.get("X-CatalogFlow-Token", "")
        if not hmac.compare_digest(supplied.encode("utf-8"),
                                   self.server.application.token.encode("utf-8")):
            self._send_json(HTTPStatus.FORBIDDEN, {"error": "invalid_session"})
            return False
        actual_origin = self.headers.get("Origin")
        allowed = self.server.application.allowed_page_origins()
        if actual_origin and actual_origin not in allowed:
            self._send_json(HTTPStatus.FORBIDDEN, {"error": "invalid_origin"})
            return False
        if require_page_origin:
            declared = self.headers.get("X-CatalogFlow-Page-Origin", "")
            if declared not in allowed:
                self._send_json(HTTPStatus.FORBIDDEN, {"error": "invalid_page_origin"})
                return False
            if actual_origin and actual_origin != declared:
                self._send_json(HTTPStatus.FORBIDDEN, {"error": "invalid_page_origin"})
                return False
        return True

    def _read_json(self) -> dict[str, object]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("Invalid Content-Length") from exc
        if length <= 0 or length > MAX_REQUEST_BYTES:
            raise ValueError(f"Request body must contain 1-{MAX_REQUEST_BYTES} bytes")
        if self.headers.get_content_type() != "application/json":
            raise ValueError("Content-Type must be application/json")
        try:
            data = self.rfile.read(length)
            if len(data) != length:
                raise ValueError("Incomplete request body")
            payload = json.loads(data)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError, RecursionError) as exc:
            raise ValueError("Request body is not valid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("Request body must be a JSON object")
        return payload

    def _serve_userscript(self) -> None:
        data = (
            Path(__file__)
            .with_name("browser")
            .joinpath("catalogflow-collector.user.js")
            .read_bytes()
        )
        self.send_response(HTTPStatus.OK)
        self._security_headers("text/javascript; charset=utf-8")
        self.send_header("Content-Disposition", 'inline; filename="catalogflow-collector.user.js"')
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        try:
            self.send_response(status)
            self._security_headers("application/json; charset=utf-8", self.headers.get("Origin"))
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except OSError:
            # The browser may have disconnected while a bounded request was being read.
            self.close_connection = True

    def _security_headers(self, content_type: str, origin: str | None = None) -> None:
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
        )
        # Only fixed literal origins, never an unchecked request-header reflection.
        cors_origins = {
            "https://www.alibaba.com": "https://www.alibaba.com",
            "https://www.cjdropshipping.com": "https://www.cjdropshipping.com",
            "https://cjdropshipping.com": "https://cjdropshipping.com",
        }
        if origin in cors_origins:
            self.send_header("Access-Control-Allow-Origin", cors_origins[origin])
            self.send_header("Vary", "Origin")

    def log_message(self, _format: str, *_args: object) -> None:
        return


def run_collector(*, port: int = 8766) -> None:
    """Collect selections until the operator presses Enter."""

    if not 0 <= port <= 65535:
        raise ValueError("Collector port must be between 0 and 65535")
    queue = SelectionQueue()

    def show_selection(selection: ProductSelection, created: bool) -> None:
        status = "added" if created else "already queued"
        print(f"[{len(queue.list()):03d}] {status}: {selection.page_title}")

    application = CollectorApplication(
        queue,
        secrets.token_urlsafe(32),
        on_selection=show_selection,
    )
    try:
        server = CollectorServer(("127.0.0.1", port), application)
    except OSError as exc:
        raise SystemExit(f"Cannot start the loopback collector on port {port}: {exc}") from exc
    actual_port = int(server.server_address[1])
    base_url = f"http://127.0.0.1:{actual_port}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"CatalogFlow collector: {base_url}")
    print(f"Install/update userscript: {base_url}/collector.user.js")
    print("Pairing code (paste only in the userscript): "
          + pairing_code(base_url, application.token))
    print(f"Local queue file (created on first selection): {queue.path}")
    try:
        input("Select products in the browser, then press Enter here to freeze the queue.\n")
        if queue.list():
            queue.freeze()
    except (EOFError, KeyboardInterrupt):
        pass
    finally:
        application.stop_accepting()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    item_count = len(queue.list())
    if item_count:
        state = "frozen" if queue.frozen else "stopped; explicit freeze still required"
        print(f"Queue {state} with {item_count} item(s): {queue.path}")
    else:
        print("Queue frozen with 0 items; no queue file was created.")


def pairing_code(endpoint: str, token: str) -> str:
    """One in-memory paste value; never store this code in a queue or log artifact."""
    encoded = json.dumps({"endpoint": endpoint, "token": token}, separators=(",", ":"))
    return "CATALOGFLOW1:" + base64.urlsafe_b64encode(encoded.encode("ascii")).decode().rstrip("=")
