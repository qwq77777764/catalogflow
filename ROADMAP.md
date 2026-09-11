# Roadmap

CatalogFlow is developed in small, auditable vertical slices.

## Shipped in 0.4 — Hardened browser selection

- Provide a narrowly matched Alibaba Tampermonkey selector and authenticated loopback receiver.
- Enforce one-time session authentication, exact origin/URL rules, payload/rate/queue limits, and
  an explicit Enter-to-freeze boundary.
- Store only a canonical selected URL and page title; never accept cookies, page HTML, or store/API
  credentials at the browser boundary.

## In preview — CJ official supplier normalization

- Exchange the operator's CJ API key for an in-memory access token and fetch one explicit PID.
- Convert official CJ detail data into normalized facts, variants, USD costs, and images.
- Quote official end-to-end freight per variant and include it in deterministic local pricing.
- Cover the network boundary with an injectable transport and synthetic contract tests.
- Stop explicitly on missing authorization, provider quota exhaustion, or incomplete required data;
  never fall back to scraping.

## Next

- Connect a narrowly scoped CJ browser selector or frozen queue to the same adapter.
- Add variant-level inventory origin selection instead of the current explicit/default origin.
- Add a review UI for comparing returned logistics routes before choosing one.

## Shipped in 0.3 — Local connection center

- Configure named provider profiles and notes from a loopback-only browser dashboard.
- Keep secrets in the operating-system keyring and non-secret metadata outside the repository.
- Reuse default or explicitly selected WooCommerce, Codex, and Claude profiles.
- Present separate store, supplier, and local-AI connection groups, including planned Shopify and
  restricted WP-CLI-over-SSH publishing paths.

## 0.2 — Authorized provider inputs

- Add a CJ official-API adapter with injectable transport and contract tests.
- Publish the normalized product JSON specification.
- Add redacted import diagnostics that never contain credentials or raw responses.
- Stabilize image-assisted Codex and Claude generation across supported CLI releases.

## 0.3 — Reviewable drafts

- Render a human-readable preview and field-level diff before store writes.
- Add idempotency keys and duplicate detection.
- Add a WooCommerce fake server for end-to-end draft tests.

## Later

- Additional store and registry adapters driven by contributor demand.
- Signed releases and a documented compatibility policy.

Public publishing will remain outside CatalogFlow's store interface.
