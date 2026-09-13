"""Durable selection inbox with a separate, collection-only loopback session."""

from __future__ import annotations

import json
import secrets
import threading
import uuid
from dataclasses import replace
from itertools import islice
from pathlib import Path

from .collector import CollectorApplication, CollectorServer, pairing_code
from .selection_queue import SelectionQueue, new_queue_path, validated_queue_items

MAX_QUEUE_FILES = 100
MAX_IMPORT_BYTES = 48 * 1024


class QueueWorkflowError(ValueError):
    """Stable UI-safe queue diagnostics without paths, source payloads, or pairing secrets."""

    def __init__(self, code: str, status: int = 400) -> None:
        self.code = code
        self.status = status
        super().__init__(code)


class QueueWorkflow:
    def __init__(self, config_dir: str | Path) -> None:
        self.directory = Path(config_dir) / "queues"
        self._lock = threading.RLock()
        self._queues: dict[str, SelectionQueue] = {}
        self._warnings: list[str] = []
        self._server: CollectorServer | None = None
        self._thread: threading.Thread | None = None
        self._active: dict | None = None
        self._closed = False
        self._load()

    def _load(self) -> None:
        try:
            if self.directory.is_symlink():
                self._warnings = ["queue_unavailable"]
                return
            paths = list(islice(self.directory.glob("selection-*.json"), MAX_QUEUE_FILES + 1))
            if len(paths) > MAX_QUEUE_FILES:
                self._warnings.append("queue_archive_limit")
            item_ids: set[str] = set()
            for path in paths[:MAX_QUEUE_FILES]:
                try:
                    if path.is_symlink() or path.resolve().parent != self.directory.resolve():
                        raise ValueError("Unsafe queue file")
                    queue = SelectionQueue(path)
                    ids = {item.id for item in queue.list()}
                    if queue.id in self._queues or ids & item_ids:
                        raise ValueError("Duplicate archive identity")
                    self._queues[queue.id] = queue
                    item_ids.update(ids)
                except (OSError, ValueError, TypeError, KeyError, RecursionError):
                    self._warnings.append("queue_invalid_archive")
        except OSError:
            self._warnings.append("queue_unavailable")

    @staticmethod
    def _public_item(queue, item) -> dict:
        return {
            "queue_id": queue.id, "id": item.id, "source": item.source,
            "url": item.product_url, "title": item.page_title, "selected_at": item.selected_at,
            "frozen": queue.frozen, "importable": queue.frozen and item.source == "cj",
        }

    def state(self) -> dict:
        with self._lock:
            queues, items = [], []
            for queue in sorted(self._queues.values(), key=lambda value: value.created_at,
                                reverse=True):
                selected = queue.list()
                queues.append({
                    "id": queue.id, "created_at": queue.created_at, "frozen": queue.frozen,
                    "frozen_at": queue.frozen_at, "item_count": len(selected),
                })
                items.extend(self._public_item(queue, item) for item in selected)
            return {"active": dict(self._active) if self._active else None,
                    "queues": queues, "items": items,
                    "warnings": list(dict.fromkeys(self._warnings))}

    def _new_queue(self) -> SelectionQueue:
        if self._closed:
            raise QueueWorkflowError("queue_unavailable", 503)
        if self.directory.is_symlink():
            raise QueueWorkflowError("queue_unavailable", 503)
        file_count = sum(1 for _ in islice(self.directory.glob("selection-*.json"),
                                         MAX_QUEUE_FILES + 1))
        if file_count >= MAX_QUEUE_FILES or "queue_archive_limit" in self._warnings:
            raise QueueWorkflowError("queue_archive_limit", 409)
        path = self.directory / new_queue_path().name
        if path.resolve().parent != self.directory.resolve():
            raise QueueWorkflowError("queue_unavailable", 503)
        return SelectionQueue(path)

    def start(self) -> dict:
        with self._lock:
            if self._closed:
                raise QueueWorkflowError("queue_unavailable", 503)
            if self._active is not None:
                return self.state()
            server = None
            try:
                queue = self._new_queue()
                queue.persist()
                self._queues[queue.id] = queue
                application = CollectorApplication(queue, secrets.token_urlsafe(32))
                server = CollectorServer(("127.0.0.1", 0), application)
                endpoint = f"http://127.0.0.1:{server.server_address[1]}"
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                self._server, self._thread = server, thread
                self._active = {"queue_id": queue.id, "endpoint": endpoint,
                                "pairing_code": pairing_code(endpoint, application.token)}
            except QueueWorkflowError:
                raise
            except (OSError, ValueError, RuntimeError):
                if server is not None:
                    server.server_close()
                raise QueueWorkflowError("queue_unavailable", 503) from None
            return self.state()

    def _stop(self) -> None:
        if self._server is not None:
            self._server.application.stop_accepting()
            self._server.shutdown()
            self._server.server_close()
            if self._thread is not None:
                self._thread.join(timeout=2)
        self._server = self._thread = self._active = None

    def freeze(self, payload: dict | None = None) -> dict:
        payload = {} if payload is None else payload
        if not isinstance(payload, dict) or set(payload) - {"queue_id"}:
            raise QueueWorkflowError("queue_invalid_request")
        if "queue_id" in payload and (not isinstance(payload["queue_id"], str)
                                      or not payload["queue_id"]):
            raise QueueWorkflowError("queue_invalid_request")
        with self._lock:
            identifier = payload.get("queue_id") or (self._active or {}).get("queue_id")
            if not isinstance(identifier, str) or identifier not in self._queues:
                raise QueueWorkflowError("queue_not_found", 404)
            queue = self._queues[identifier]
            try:
                # add() and freeze() share the queue lock. No accepted request follows approval.
                queue.freeze()
                if self._active and self._active["queue_id"] == identifier:
                    self._stop()
            except (OSError, ValueError, RuntimeError):
                raise QueueWorkflowError("queue_unavailable", 503) from None
            return self.state()

    def import_payload(self, payload: object) -> dict:
        try:
            serialized = json.dumps(payload, ensure_ascii=False, allow_nan=False,
                                    separators=(",", ":")).encode("utf-8")
            if len(serialized) > MAX_IMPORT_BYTES:
                raise ValueError("Oversized queue")
            selected = validated_queue_items(payload)
        except (ValueError, TypeError, KeyError, RecursionError):
            raise QueueWorkflowError("queue_invalid_request") from None
        with self._lock:
            try:
                queue = self._new_queue()
                # A submitted file is a new selection snapshot, never a live collector.
                for item in selected:
                    queue.add(replace(item, id=str(uuid.uuid4())))
                queue.freeze()
                self._queues[queue.id] = queue
            except QueueWorkflowError:
                raise
            except (OSError, ValueError, RuntimeError):
                raise QueueWorkflowError("queue_unavailable", 503) from None
            return self.state()

    def select(self, identifier: str) -> dict:
        if not isinstance(identifier, str) or len(identifier) > 100:
            raise QueueWorkflowError("queue_invalid_item")
        with self._lock:
            for queue in self._queues.values():
                for item in queue.list():
                    if item.id == identifier:
                        if not queue.frozen:
                            raise QueueWorkflowError("queue_not_frozen", 409)
                        return self._public_item(queue, item)
        raise QueueWorkflowError("queue_not_found", 404)

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._stop()
