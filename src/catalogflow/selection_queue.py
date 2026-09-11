"""Validated, local-only product selections collected from browser helpers."""

from __future__ import annotations

import json
import os
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from .configuration import default_config_directory

MAX_QUEUE_ITEMS = 100
MAX_TITLE_LENGTH = 240

SOURCE_RULES: dict[str, dict[str, object]] = {
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
    canonical_url = urlunsplit(("https", parsed.hostname, parsed.path, "", ""))
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

    def add(self, selection: ProductSelection) -> tuple[ProductSelection, bool]:
        with self._lock:
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
            self._write()
            return selection, True

    def list(self) -> tuple[ProductSelection, ...]:
        with self._lock:
            return tuple(self._items)

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        payload = {"version": 1, "items": [asdict(item) for item in self._items]}
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
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
