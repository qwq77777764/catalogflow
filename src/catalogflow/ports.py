"""Interfaces at the few seams that genuinely vary."""

from __future__ import annotations

from typing import Protocol

from .models import Listing, Product


class SourceAdapter(Protocol):
    def fetch(self, reference: str) -> Product: ...


class ListingGenerator(Protocol):
    def generate(self, product: Product) -> Listing: ...


class StorePublisher(Protocol):
    def create_hidden_draft(self, product: Product, listing: Listing) -> str: ...

