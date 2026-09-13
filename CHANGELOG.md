# Changelog

All notable changes are documented here.

## Unreleased

## 0.10.0 — 2026-09-13

- Added bilingual first-run guidance with selected-CLI installation and official sign-in checks,
  user-initiated login guidance, and an optional explicitly authorized synthetic AI test. Saved
  profiles, sign-in detection and a successful model request are reported as different states.
- Connected browser selection to a persistent dashboard inbox. Added a narrowly matched CJ detail
  selector alongside Alibaba, a separate collection-only pairing code, explicit queue freezing,
  legacy queue import and single-item handoff to the existing preview wizard. Closing or cancelling
  does not approve an unfinished queue; selection itself never invokes AI or writes a store.
- Added manual product entry for selected Alibaba links, including facts, variants, USD costs,
  unit freight and authorized images, while preserving the advanced JSON input. This supplies the
  missing handoff without claiming an automatic Alibaba/1688 supplier API adapter.
- Preserved authenticated loopback endpoints, bounded inputs, session isolation, safe diagnostics,
  review invalidation and hidden-draft confirmation. Added the setup UI to Windows and wheel assets.
- Fixed Claude subscription sign-in compatibility while keeping hooks, unrequested tools and MCP
  disabled. Isolated Codex working directories and bounded external CLI output. Editing or deleting
  an AI profile now invalidates its previous readiness result, including an in-flight check.

## 0.9.0 — 2026-09-12

- Added a bilingual three-step single-product import wizard to the authenticated local dashboard:
  a CJ URL/PID through a saved official-API profile, or an authorized normalized JSON upload
  (`alibaba-manual`, UTF-8 with optional BOM, up to 48 KiB), followed by Codex, Claude, or template
  generation and review. A store connection is optional for previews.
- Showed per-variant cost, freight, and USD price snapshots, image counts and safe image/source
  links, and editable title, HTML description text, category, and tags before draft confirmation.
- Kept the product, generated listing, saved pricing policy, and selected store in the server
  session. Reviewed confirmation reuses that snapshot without repeating supplier or AI requests
  or recalculating prices, and requires an acknowledgment plus an explicit hidden-draft action.
- Connected visual imports to the existing TXT/JSON reports and store-scoped duplicate protection.
  A single background task and guarded confirmation prevent repeated clicks from creating parallel
  writes. Reopening an authenticated page can recover the running session's task; unconfirmed
  previews do not survive application restart, while archived reports remain available.
- Included the import JavaScript in the explicit Windows release-resource list. Alibaba/1688 URL
  normalization, batch imports in the wizard, SSH store writes, and private-history migration remain
  outside this release.

## 0.8.0 — 2026-09-12

- Added a standalone Windows x64 EXE with a Chinese/English launcher, account-scoped single
  instance, loopback dashboard, reopen/exit controls, and optional offline acceptance checks.
  Existing configuration, reports, and OS-keyring credentials stay outside the executable.
- Added an isolated PyInstaller build with explicit public-resource and binary-source checks,
  third-party licenses, distribution checksums, and packaged-resource validation.
- Sanitized frozen-process DLL search state before launching installed AI CLIs, hid their console
  windows, and added an actionable diagnostic when the configured model requires a newer Codex CLI.
- Made unavailable CJ logistics routes and missing usable freight visible in bilingual run reports.
- Assigned unique numeric public upload names and rejected unrelated SKU-search results before
  associating an existing store product or starting a write.

## 0.7.0 — 2026-09-12

- Restored the earlier operator workflow's timestamped TXT/JSON run reports, per-item source links
  and outcomes, and a bilingual read-only dashboard history viewer with TXT downloads.
- Added durable store-scoped draft reservations and duplicate protection. Repeated previews stay
  available; interrupted or partial writes preserve their evidence and block unsafe recreation.
- Preserved individual product variants and authorized gallery/variant images in WooCommerce
  drafts. WordPress media uploads use separately configured application-password credentials;
  product and variation publication stays disabled.
- Kept old private scripts, reports, registries, and production data outside the public package.

## 0.6.0 — 2026-09-12

- Added an editable Plan B product-cost formula directly in its comparison card, with
  `+`, `-`, `*`, `/`, parentheses, normal operator precedence, and visible calculation steps.
  Shipping, duties, and fixed fees are added once after the formula; price floors and `.95`
  rounding still apply. Both languages preserve formula edits and show specific arithmetic errors.
- Added bounded decimal arithmetic without code evaluation, zero-divisor validation, and
  per-product rejection of negative or excessive formula results. Version-1 numeric pricing
  settings retain their behavior; explicit saves use version 2 with an optional cost formula.
  Saved formulas apply to subsequent CLI variant previews and stay outside AI prompts.

- Aligned the freight converter's three fields in equal-width columns with shared label and
  control rows, so Chinese/English label wrapping and large totals do not misalign the boxes.
  Narrow screens keep a single-column layout with consistent control spacing.

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
