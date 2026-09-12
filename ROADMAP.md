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

## Reviewable drafts

- Add a field-level comparison between generated and edited listing copy.
- Add a guided review step for uncertain writes and explicit reconciliation with existing drafts.
- Add explicit cross-restart recovery for unconfirmed previews without bypassing a fresh review.

## Shipped in 0.7 — Work records and complete draft export

- Archive each import in timestamped TXT/JSON reports with source links and per-item outcomes.
- Review local reports in the bilingual dashboard and download TXT copies.
- Preserve store-scoped completed/uncertain draft history and block unsafe duplicate creation.
- Export individual variations and bounded authorized images through authenticated REST APIs.

## Shipped in 0.8 — Windows desktop launcher

- Run the bilingual local dashboard from a standalone Windows x64 EXE without installing Python.
- Keep existing local reports, configuration, and Windows Credential Manager storage.
- Reopen one account-scoped launcher and stop its local server on exit.
- Validate packaged resources, authenticated HTTP behavior, and optional temporary vault storage.
- Report unavailable CJ freight routes and outdated Codex CLI versions with actionable messages.

## Shipped in 0.9 — Visual single-product import

- Start an authorized CJ URL/PID or normalized `alibaba-manual` JSON import in the local dashboard.
- Choose Codex, Claude, or template generation and an optional saved WooCommerce connection.
- Review individual cost, freight, and USD-price snapshots, image links, and editable listing copy.
- Create only a hidden draft after explicit review; confirmation reuses the cached product and
  pricing instead of rerunning supplier retrieval, AI generation, or pricing.
- Run one background task per dashboard session and reuse existing reports and duplicate guards.
- Recover the current task from a reopened authenticated page while the application remains open.

## Later

- Extend the single-product wizard to a separately reviewed batch workflow.
- Add an authorized Alibaba/1688 URL-to-product adapter; manual normalized JSON remains supported.
- Add an explicit migration and reconciliation flow for old private work records.
- Additional store and registry adapters driven by contributor demand.
- Signed releases and a documented compatibility policy.

Public publishing will remain outside CatalogFlow's store interface.
