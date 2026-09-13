"""Validated, local-only product selections collected from browser helpers."""

from __future__ import annotations

import json
import os
import re
import threading
import uuid
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlsplit, urlunsplit

from .configuration import default_config_directory
from .providers.cj import extract_cj_product_id

MAX_QUEUE_ITEMS = 100
MAX_TITLE_LENGTH = 240
MAX_QUEUE_BYTES = 512 * 1024

SOURCE_RULES: dict[str, dict[str, object]] = {
    "cj": {
        "page_origins": frozenset({"https://www.cjdropshipping.com", "https://cjdropshipping.com"}),
        "hosts": frozenset({"www.cjdropshipping.com", "cjdropshipping.com"}),
        "path_prefixes": ("/product/",),
    },
    "alibaba": {
        "page_origins": frozenset({"https://www.alibaba.com"}),
        "hosts": frozenset({"www.alibaba.com"}),
        "path_prefixes": ("/product-detail/",),
    }
}


@dataclass(frozen=True, slots=True)
class ProductSelection:
    id: str
    source: str
    product_url: str
    page_title: str
    selected_at: str


def new_queue_path() -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return default_config_directory() / "queues" / f"selection-{stamp}-{uuid.uuid4().hex[:8]}.json"


def normalize_selection(source: str, product_url: str, page_title: str) -> ProductSelection:
    if not all(isinstance(value, str) for value in (source, product_url, page_title)):
        raise ValueError("Selection fields must be text")
    if (len(product_url) > 2048 or any(char.isspace() for char in product_url)
            or "\\" in product_url):
        raise ValueError("Product URL is invalid")
    source = source.strip().lower()
    if source not in SOURCE_RULES:
        raise ValueError("Unsupported selection source")
    title = page_title.strip()
    if not title or len(title) > MAX_TITLE_LENGTH:
        raise ValueError(f"Page title must contain 1-{MAX_TITLE_LENGTH} characters")
    if any(ord(character) < 32 or ord(character) == 127 for character in title):
        raise ValueError("Page title contains control characters")

    parsed = urlsplit(product_url.strip())
    rule = SOURCE_RULES[source]
    if parsed.scheme != "https" or parsed.hostname not in rule["hosts"]:
        raise ValueError("Product URL is not an allowed HTTPS supplier detail page")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Product URL contains an invalid port") from exc
    if parsed.username or parsed.password or port not in {None, 443}:
        raise ValueError("Product URL contains credentials or a non-standard port")
    if not any(parsed.path.startswith(prefix) for prefix in rule["path_prefixes"]):
        raise ValueError("Product URL is not a supported product detail page")
    query = ""
    if source == "cj":
        try:
            product_id = extract_cj_product_id(product_url)
            values = parse_qs(parsed.query, max_num_fields=50)
            for name in ("pid", "productId", "product_id"):
                if values.get(name, [None])[0] == product_id:
                    query = f"{name}={product_id}"
                    break
            if not query and not re.search(
                rf"(?<![A-Za-z0-9]){re.escape(product_id)}(?![A-Za-z0-9])", parsed.path,
            ):
                raise ValueError("CJ product identifier is not complete")
        except (ValueError, RuntimeError):
            raise ValueError("CJ selection must identify one product") from None
    canonical_url = urlunsplit(("https", parsed.hostname, parsed.path, query, ""))
    return ProductSelection(
        id=str(uuid.uuid4()),
        source=source,
        product_url=canonical_url,
        page_title=title,
        selected_at=datetime.now(UTC).isoformat(),
    )


class SelectionQueue:
    """Atomic JSON queue stored outside the Git checkout."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else new_queue_path()
        self._items: list[ProductSelection] = []
        self._lock = threading.Lock()
        self.id = uuid.uuid4().hex
        self.created_at = datetime.now(UTC).isoformat()
        self.frozen = False
        self.frozen_at: str | None = None
        if self.path.exists():
            if self.path.is_symlink() or self.path.stat().st_size > MAX_QUEUE_BYTES:
                raise ValueError("Queue file is unsafe or too large")
            with self.path.open("rb") as stream:
                data = stream.read(MAX_QUEUE_BYTES + 1)
            if len(data) > MAX_QUEUE_BYTES:
                raise ValueError("Queue file is too large")
            payload = json.loads(data)
            self._load(payload)

    def _load(self, payload: object) -> None:
        items = validated_queue_items(payload)
        if payload["version"] == 2:
            identifier = payload.get("id")
            if not isinstance(identifier, str) or uuid.UUID(identifier).hex != identifier:
                raise ValueError("Queue identifier is invalid")
            self.id = identifier
            self.created_at = _timestamp(payload.get("created_at"))
            if type(payload.get("frozen")) is not bool:
                raise ValueError("Queue state is invalid")
            self.frozen = payload["frozen"]
            self.frozen_at = _timestamp(payload.get("frozen_at")) if self.frozen else None
        else:
            # Legacy files did not record approval. Stable identity, explicit freeze required.
            self.id = uuid.uuid5(uuid.NAMESPACE_URL, self.path.name).hex
            self.created_at = items[0].selected_at if items else self.created_at
        self._items = list(items)

    def persist(self) -> None:
        with self._lock:
            self._write()

    def freeze(self) -> None:
        with self._lock:
            if self.frozen:
                return
            self.frozen, self.frozen_at = True, datetime.now(UTC).isoformat()
            try:
                self._write()
            except Exception:
                self.frozen, self.frozen_at = False, None
                raise

    def add(self, selection: ProductSelection) -> tuple[ProductSelection, bool]:
        with self._lock:
            if self.frozen:
                raise ValueError("queue_frozen")
            duplicate = next(
                (
                    item
                    for item in self._items
                    if item.source == selection.source
                    and item.product_url == selection.product_url
                ),
                None,
            )
            if duplicate:
                return duplicate, False
            if len(self._items) >= MAX_QUEUE_ITEMS:
                raise ValueError(f"Selection queue is limited to {MAX_QUEUE_ITEMS} items")
            self._items.append(selection)
            try:
                self._write()
            except Exception:
                self._items.pop()
                raise
            return selection, True

    def list(self) -> tuple[ProductSelection, ...]:
        with self._lock:
            return tuple(self._items)

    def _write(self) -> None:
        if self.path.is_symlink() or self.path.with_suffix(".tmp").is_symlink():
            raise ValueError("Queue file must not be a symlink")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        payload = {
            "version": 2, "id": self.id, "created_at": self.created_at,
            "frozen": self.frozen, "frozen_at": self.frozen_at,
            "items": [asdict(item) for item in self._items],
        }
        serialized = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        if len(serialized) > MAX_QUEUE_BYTES:
            raise ValueError("Queue file exceeds the size limit")
        with temporary.open("wb") as stream:
            stream.write(serialized)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            temporary.chmod(0o600)
        except OSError:
            pass
        temporary.replace(self.path)
        if os.name != "nt":
            try:
                self.path.chmod(0o600)
            except OSError:
                pass


def _timestamp(value: object) -> str:
    if not isinstance(value, str) or len(value) > 50:
        raise ValueError("Queue timestamp is invalid")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("Queue timestamp requires a timezone")
    return parsed.astimezone(UTC).isoformat()


def validated_queue_items(payload: object) -> tuple[ProductSelection, ...]:
    """Accept only bounded selection records, never product data or filesystem paths."""
    if not isinstance(payload, dict) or type(payload.get("version")) is not int:
        raise ValueError("Queue schema is invalid")
    version = payload["version"]
    allowed = ({"version", "items"} if version == 1 else {
        "version", "id", "created_at", "frozen", "frozen_at", "items",
    })
    if version not in (1, 2) or set(payload) != allowed:
        raise ValueError("Queue schema is invalid")
    if version == 2:
        identifier = payload["id"]
        if not isinstance(identifier, str) or uuid.UUID(identifier).hex != identifier:
            raise ValueError("Queue identifier is invalid")
        _timestamp(payload["created_at"])
        if type(payload["frozen"]) is not bool:
            raise ValueError("Queue state is invalid")
        if payload["frozen"]:
            _timestamp(payload["frozen_at"])
        elif payload["frozen_at"] is not None:
            raise ValueError("Queue state is invalid")
    rows = payload.get("items")
    if not isinstance(rows, list) or len(rows) > MAX_QUEUE_ITEMS:
        raise ValueError("Queue item count is invalid")
    result = []
    identities = set()
    ids = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {
            "id", "source", "product_url", "page_title", "selected_at",
        }:
            raise ValueError("Queue selection schema is invalid")
        identifier = row["id"]
        if not isinstance(identifier, str) or str(uuid.UUID(identifier)) != identifier:
            raise ValueError("Queue selection identifier is invalid")
        selected = normalize_selection(row["source"], row["product_url"], row["page_title"])
        identity = (selected.source, selected.product_url)
        if identifier in ids or identity in identities:
            raise ValueError("Queue contains duplicate items")
        ids.add(identifier)
        identities.add(identity)
        result.append(replace(selected, id=identifier, selected_at=_timestamp(row["selected_at"])))
    return tuple(result)
