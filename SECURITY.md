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

Any future localhost browser bridge must use a random per-session token, an exact origin
allowlist, request-size limits, rate limiting, and SSRF protection. It must not return
tracebacks or local paths to callers.

