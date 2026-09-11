# Browser-to-local-CMD queue workflow

## What the original workflow did

The private production workflow proved a useful interaction model:

1. The operator signs in to CJ or Alibaba/1688 in a normal browser.
2. On a chosen product, a browser-side button sends the visible product URL, title, and authorized
   image references to a receiver bound to `127.0.0.1`.
3. The local terminal displays the collected items.
4. The operator presses Enter to begin the batch.
5. A local Codex or Claude CLI rewrites the normalized listing.
6. Validation and human review occur before any optional hidden draft.

This makes product selection visual and keeps the AI integration on the operator's computer.

## Current public status

The clean public release currently starts from a normalized product JSON file. A hardened browser
collector is planned but is not yet shipped. There is no undocumented command that downloaders must
ask Codex or Claude to create for them.

The old userscripts and Python controller were not copied because they combine site-specific DOM
selectors, browser automation, local unauthenticated endpoints, production configuration, direct
store writes, and private operational assumptions. Publishing that code unchanged would be unsafe
and brittle.

## Required design for the public bridge

Any public replacement must satisfy all of these requirements before release:

- bind only to `127.0.0.1`, never `0.0.0.0`;
- generate a new high-entropy session token when the receiver starts;
- require the token on every request and never place it in Git or browser sync storage;
- use exact supplier-origin allowlists, not wildcard CORS;
- accept a small versioned JSON schema with strict body and field limits;
- reject cookies, authorization headers, passwords, API keys, customer data, and raw HTML dumps;
- rate-limit requests, cap queue length, and process only one explicit batch at a time;
- accept only configured public HTTPS image hosts and re-check every redirect against private and
  non-global network ranges;
- write the queue to an ignored local data directory with restrictive permissions;
- make Enter an explicit processing boundary and show a preview before any store write;
- default to local preview and preserve the hidden-draft-only store invariant;
- include synthetic fixtures and contract tests so contributors do not need a real supplier account.

The browser helper must display exactly what will be sent locally. It must never scrape or forward
the user's supplier session, cookies, payment information, messages, or unrelated page content.

## Supplier-specific limitations

CJ and Alibaba/1688 can change page structure at any time. Visible-page collection is useful for
product selection but is not a reliable substitute for official structured data when exact variant
IDs, inventory, package measurements, shipping services, or current prices matter.

Users who need those fields must obtain the relevant official API access through their own lawful
account and follow the provider's current terms, quotas, and fees. CatalogFlow will not bundle,
share, resell, emulate, or bypass supplier credentials.

## Intended future interaction

The future bridge should preserve the original simple experience:

```text
start local receiver → open authorized supplier page → add selected items
→ review terminal queue → press Enter → generate → validate → preview
```

Command names and browser package instructions will be documented only when the hardened receiver
and collector are implemented and tested. Until then, use the normalized JSON path described in the
README.
