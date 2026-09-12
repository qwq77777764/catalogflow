"""Provider-neutral catalog models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class ImportMode(StrEnum):
    """Controls whether CatalogFlow may cross the store-write seam."""

    DRY_RUN = "dry-run"
    DRAFT = "draft"


@dataclass(frozen=True, slots=True)
class ShippingQuote:
    origin_country: str
    destination_country: str
    quantity: int
    method: str
    total_cost_usd: float
    estimated_days: str = ""

    @property
    def unit_cost_usd(self) -> float:
        return self.total_cost_usd / self.quantity


@dataclass(frozen=True, slots=True)
class Variant:
    sku: str
    cost: float
    attributes: dict[str, str] = field(default_factory=dict)
    shipping_quote: ShippingQuote | None = None
    image_url: str = ""


@dataclass(frozen=True, slots=True)
class Product:
    source: str
    source_id: str
    title: str
    currency: str
    variants: tuple[Variant, ...]
    images: tuple[str, ...] = ()
    facts: dict[str, str] = field(default_factory=dict)
    source_url: str = ""


@dataclass(frozen=True, slots=True)
class Listing:
    title: str
    description_html: str
    category: str
    tags: tuple[str, ...]
    prices: dict[str, float]
    shipping_quotes: dict[str, ShippingQuote] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ImportRequest:
    source: str
    reference: str


@dataclass(frozen=True, slots=True)
class ImportItemResult:
    request: ImportRequest
    status: str
    listing: Listing | None = None
    store_id: str | None = None
    errors: tuple[str, ...] = ()
    store_url: str = ""
    artifact_path: str = ""


@dataclass(frozen=True, slots=True)
class ImportReport:
    mode: ImportMode
    items: tuple[ImportItemResult, ...]
    run_id: str = ""
    report_path: str = ""

    @property
    def ok(self) -> bool:
        return all(item.status in {"previewed", "drafted", "skipped_duplicate"}
                   for item in self.items)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
