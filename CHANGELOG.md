# Changelog

All notable changes are documented here.

## Unreleased

## 0.5.0 — 2026-09-12

- Added Node dashboard regression checks to CI and fixed authenticated pull-request secret scans.
- Added a bilingual last-mile shipping currency converter with selectable currencies, daily
  Frankfurter reference rates, visible rate dates and sources, manual rates, and retry handling.
  Its three fields show the target currency, an automatically filled but directly editable rate,
  and the converted total; restoring reference rates explicitly removes the manual override.
  Conversion stays separate from USD pricing and saved settings; amounts and credentials never
  reach the rate service, and manual inputs survive language changes and late responses.
- Added a whole-dashboard Chinese (CN) / English (US) language selector with bundled translations,
  browser-language defaults, and a per-origin language preference. Switching preserves entered
  values and pending edits, keeps amounts in USD, and does not save pricing automatically.
- Kept pricing edits through connection refreshes and save failures; cleared invalid or outdated
  previews and handled cancelled preview connections without server tracebacks.

- Added a loopback-only visual pricing panel with a default margin plan, editable cost-multiplier
  plan, live breakdown, optional operator tax/duty estimate, and atomic non-secret `pricing.json`
  settings.
- Expanded visual pricing with side-by-side plan comparisons, fee/reserve deductions, estimated
  unit profit and margin, theoretical break-even prices, `.95` adjustments, and price-floor reasons.
  Added explicit unsaved/default-reset controls and dashboard-to-CLI per-variant pricing regression
  coverage while preserving both pricing formulas and the existing settings format.
- Added a preview CJ official API source adapter for one explicit CJ product URL or PID.
- Added in-memory CJ token exchange, fixed-host/no-redirect network enforcement, bounded JSON,
  redacted provider errors, product-ID matching, and synthetic contract tests.
- Added `--supplier-profile` so the adapter loads the operator's own CJ API key from the operating-
  system keyring without sending credentials to a local AI process.
- Added fail-closed per-variant quotes through CJ's official `logistic/freightCalculate` endpoint,
  configurable origin/destination/ZIP/quantity/route settings, and shipping-aware local pricing.
- Added normalized shipping details to local previews while keeping supplier variant IDs and raw
  freight responses inside the adapter boundary.
- Required complete CJ freight quotes at both validation and pricing boundaries; unknown provider
  error codes are no longer echoed into preview files.

## 0.4.0 — 2026-09-11

- Added `catalogflow collect`, an authenticated loopback receiver that freezes a unique local queue
  when the operator presses Enter.
- Added a narrowly matched Alibaba Tampermonkey selector that sends only the chosen detail URL and
  page title and keeps the one-time token in memory rather than extension storage.
- Enforced exact source/origin/URL rules, a 16 KiB body limit, 30-request-per-minute rate limit,
  100-item queue cap, duplicate idempotency, forbidden credential headers, and redacted server logs.
- Kept collection separate from provider normalization: v0.4.0 does not scrape missing facts or
  pretend a selected URL is already a complete listing input.

## 0.3.0 — 2026-09-11

- Added a loopback-only visual connection center with channel names, user labels, notes, dynamic
  fields, default profiles, edit/delete controls, and an explicit stop action.
- Added operating-system keyring storage; secrets are never written to profile metadata or returned
  to the dashboard.
- Added reusable WooCommerce, Codex, and Claude profiles while clearly marking unfinished supplier
  adapters as planned.
- Grouped connections into store, supplier, and local-AI sections; added planned Shopify Admin API
  and restricted WP-CLI-over-SSH profiles without storing SSH passwords or private keys.
- Documented the official-API-first, user-initiated selection model and the no-silent-fallback rule
  when local AI quota or authorized provider access is unavailable.
- Documented the verified separation between the historical Alibaba Tampermonkey selector and its
  Python CMD queue receiver.

## 0.2.0 — 2026-09-11

- Added a structured Claude Code CLI generator alongside Codex and deterministic modes.
- Added bounded authorized-image materialization with public-network and media checks.
- Added `python -m catalogflow --doctor` for read-only local CLI discovery.
- Documented standalone Codex/Claude setup, the sanitized agent contract, and the security design
  for the planned browser-to-CMD queue.

## 0.1.0 — 2026-09-11

- Added the provider-neutral import pipeline and domain model.
- Added deterministic pricing, source-disclosure validation, and per-item isolation.
- Added offline JSON fixtures and an opt-in structured Codex CLI generator.
- Added a WooCommerce adapter restricted to hidden drafts.
- Added English and Chinese documentation, security policy, tests, CI, Gitleaks, and CodeQL.
