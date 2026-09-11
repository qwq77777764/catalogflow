"""Authorized manual JSON input for CJ or Alibaba product facts."""

from __future__ import annotations

import json
from pathlib import Path

from ..models import Product, Variant


class JsonFileSource:
    """Read normalized, user-provided data without scraping a supplier site."""

    def __init__(self, source: str) -> None:
        self.source = source

    def fetch(self, reference: str) -> Product:
        payload = json.loads(Path(reference).read_text(encoding="utf-8"))
        variants = tuple(
            Variant(
                sku=str(row["sku"]),
                cost=float(row["cost"]),
                attributes={str(k): str(v) for k, v in row.get("attributes", {}).items()},
            )
            for row in payload["variants"]
        )
        return Product(
            source=self.source,
            source_id=str(payload["source_id"]),
            title=str(payload["title"]),
            currency=str(payload.get("currency", "USD")),
            variants=variants,
            images=tuple(str(value) for value in payload.get("images", [])),
            facts={str(k): str(v) for k, v in payload.get("facts", {}).items()},
        )

