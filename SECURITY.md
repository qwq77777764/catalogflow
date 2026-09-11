# Security Policy

## Reporting

Do not open a public issue containing credentials, store URLs, customer data, supplier
payloads, or production logs. Report a vulnerability privately through GitHub's
repository security-advisory feature.

## Credential handling

- Use environment variables or an operating-system credential store.
- Never commit `.env`, local configuration, cookies, tokens, or generated output.
- Treat any credential previously stored in source as compromised and rotate it.
- CI and tests must use fakes or synthetic fixtures, never live accounts.

## Store-write invariant

The public interface supports local preview and hidden WooCommerce drafts. A change that
adds public publishing, weakens confirmation, or changes `catalog_visibility` requires a
security review and explicit documentation.

## Local bridge invariant

The localhost browser bridge and any future extensions must use a random per-session token, an exact
origin allowlist, request-size limits, rate limiting, and SSRF protection. It must not return
tracebacks or local paths to callers.

## Provider and SSH invariant

- Released supplier adapters must use the operator's authorized official API credentials. They must
  not crawl result pages, bypass authentication/CAPTCHA/access controls, evade rate limits, or
  silently fall back to scraping.
- A future WP-CLI-over-SSH adapter may reference a local SSH config alias, but must never collect or
  persist SSH passwords or private keys. Documentation and defaults must recommend a restricted
  account or forced command instead of root access.
