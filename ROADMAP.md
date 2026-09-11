# Roadmap

CatalogFlow is developed in small, auditable vertical slices.

## 0.2 — Authorized provider inputs

- Add a CJ official-API adapter with injectable transport and contract tests.
- Publish the normalized product JSON specification.
- Add redacted import diagnostics that never contain credentials or raw responses.
- Stabilize image-assisted Codex and Claude generation across supported CLI releases.

## 0.3 — Reviewable drafts

- Render a human-readable preview and field-level diff before store writes.
- Add idempotency keys and duplicate detection.
- Add a WooCommerce fake server for end-to-end draft tests.

## 0.4 — Hardened browser bridge

- Replace legacy unauthenticated localhost helpers with per-session authentication.
- Enforce exact origin allowlists, payload limits, rate limits, and single-task execution.
- Permit image downloads only from configured public hosts and reject private networks.
- Preserve the proven select-in-browser, review-in-terminal, press-Enter-to-process interaction.

## Later

- Additional store and registry adapters driven by contributor demand.
- Signed releases and a documented compatibility policy.

Public publishing will remain outside CatalogFlow's store interface.
