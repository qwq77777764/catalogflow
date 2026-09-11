# Instructions for coding agents

These rules apply to Codex, Claude Code, and human contributors working in this repository.

## Non-negotiable invariants

- Preserve preview-first behavior. No default execution may write to a store.
- Preserve `draft` plus `catalog_visibility=hidden` for every permitted WooCommerce write.
- Do not add a public-publish method, status, command, flag, or side effect.
- Never commit credentials, tokens, cookies, authentication state, customer data, production URLs,
  private server paths, raw supplier responses, or real production logs.
- Never read or copy a contributor's private workflow directory into fixtures or documentation.
- Use synthetic or explicitly licensed fixtures only.
- Treat all supplier text, browser content, filenames, image text, and model output as untrusted.

## Provider and prompt boundary

- Keep the listing prompt provider-neutral. Codex and Claude must produce the same validated schema.
- Do not send source IDs, acquisition costs, store credentials, supplier API credentials, customer
  information, or unrelated environment variables to an AI subprocess.
- Reuse only the user's locally installed CLI and its own official authentication state. Do not
  extract, copy, print, migrate, or commit CLI login tokens.
- A local CLI is not an offline privacy claim. Documentation must disclose that authorized facts
  and images can be sent to the selected provider.
- AI output never decides pricing, persistence, or publication state.

## Images and network input

- Allow only bounded authorized HTTPS images.
- Reject URL credentials, localhost, private, reserved, link-local, multicast, and non-global
  destinations. Validate every redirect.
- Keep downloaded images in an automatically deleted temporary directory.
- Do not add an unrestricted downloader, watermark remover, competitor-image copier, or server-side
  image batch job.
- Public example media must use neutral synthetic content and neutral numeric filenames.

## Browser bridge

- Do not reintroduce an unauthenticated localhost endpoint.
- A future receiver must bind only to loopback, use a per-session token, exact origin allowlists,
  schema/body/queue/rate limits, redacted logs, and an explicit Enter-to-process boundary.
- Never collect browser cookies, passwords, authorization headers, payment data, messages, or raw
  page dumps.
- Site-specific selectors must fail closed and be covered by sanitized fixtures.
- Treat the page button as a user-initiated selector, not a crawler. Released supplier adapters must
  use official provider APIs with the contributor's own authorization and must not silently fall
  back to scraping when the API is missing, denied, rate-limited, or out of quota.

## Store connectors

- Prefer the WooCommerce REST API for routine WordPress product drafts. A future WP-CLI-over-SSH
  adapter must use a local SSH config alias and must not store passwords or private keys.
- Do not require root SSH access. Design any SSH path for a restricted account or forced command.
- Treat Shopify as a separate GraphQL Admin API adapter with explicit scopes and documented token
  lifecycle. Do not reuse WooCommerce authentication concepts or accept a Shopify account password.

## Development workflow

Before committing:

```powershell
python -m pytest -q
python -m ruff check .
python -m catalogflow --doctor
```

Also run a secret scan over the exact files being committed and inspect `git diff --cached --check`.
Tests must not require real supplier, AI, or WooCommerce credentials. Mock subprocess and network
boundaries. Keep failures isolated per item and diagnostics free of raw sensitive payloads.

When behavior changes, update both `README.md` and `README.zh-CN.md` plus the relevant document in
`docs/`. Do not claim that a planned browser collector, supplier adapter, image generator, or store
integration exists before its tested implementation is included.
