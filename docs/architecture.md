# Architecture

CatalogFlow exposes one deep module: `import_products`.

The caller supplies requests, source adapters, and a listing generator. The module owns
normalization, deterministic validation, per-item failure isolation, preview behavior,
and the rule that store writes occur only in explicit draft mode.

## Seams

- `SourceAdapter`: real because CJ and authorized manual exports vary.
- `ListingGenerator`: real because offline deterministic and AI-backed implementations vary.
- `StorePublisher`: real because dry-run/in-memory and WooCommerce implementations vary.

Pricing and validation are pure internal policy, not pass-through adapters.

`HistoryRepository` owns per-run reports and store-scoped durable draft reservations. The CLI
always enables it; library callers may explicitly supply it to `import_products`. The repository
records item starts and outcomes before finishing immutable TXT/JSON snapshots. Preview runs do
not reserve store writes. An unfinished reservation blocks another creation instead of guessing
whether the remote request succeeded. The dashboard exposes bounded, authenticated read-only
report routes, not arbitrary filesystem access.

## Safety invariants

1. The default mode is `dry-run`.
2. Draft mode requires a publisher.
3. The WooCommerce adapter always sends `draft` and `hidden`.
4. A failed product does not abort the rest of a batch.
5. Product fixtures must never carry credentials, cookies, or customer data.
