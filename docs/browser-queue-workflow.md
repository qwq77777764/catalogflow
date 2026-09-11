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

The public design is **official-API-first and user-initiated**, not a marketplace crawler. The page
button should submit only the selected product identifier/URL and minimal visible context. The local
source adapter then obtains product facts with credentials the operator received through the
provider's official API process. It must not crawl result pages, bypass authentication/CAPTCHA,
evade rate limits, or silently fall back to scraping. If an official API is unavailable, the operator
must supply structured data they are authorized to use.

The archived Alibaba implementation confirms that the selection control and the receiver were
separate components. The detail-page Tampermonkey userscript displayed `Send to Alibaba CMD` and
posted to a loopback `/add` endpoint. The Python CMD process owned the queue and waited for Enter.
The batch launcher only started the Python receiver. The public replacement should preserve this
division: a minimal browser collector plus a locally authenticated CatalogFlow receiver.

## Current public status

The hardened Alibaba selector and loopback receiver ship in v0.4.0. Start them with:

```powershell
catalogflow collect
```

The command binds to `127.0.0.1:8766` by default, generates a fresh high-entropy token, prints the
local userscript installation URL, and waits for Enter. The userscript runs only on
`https://www.alibaba.com/product-detail/*`, asks for the local URL/token at runtime, and keeps the
token only in memory for that page.

Each accepted payload contains exactly four fields: schema version, source, canonical product URL,
and page title. Query strings and fragments are removed. Duplicate URLs are idempotent. The receiver
rejects unexpected fields, cookies/authorization headers, foreign origins, non-detail URLs,
credentialed URLs, bodies over 16 KiB, more than 30 requests per minute, and queues over 100 items.
The queue is stored outside the repository with a unique session filename and restrictive
permissions where supported.

Pressing Enter freezes the selection queue and stops the receiver. It does not yet call an AI or
write to a store: an official provider adapter must first turn each selected identifier into the
normalized facts/variants/images expected by the existing preview pipeline.

The visual connection dashboard is shipped separately. It configures provider profiles and stores
credentials safely; the collector command owns the page button and session queue.

The old userscripts and Python controller were not copied because they combine site-specific DOM
selectors, browser automation, local unauthenticated endpoints, production configuration, direct
store writes, and private operational assumptions. Publishing that code unchanged would be unsafe
and brittle.

## Enforced design for the public bridge

Any public replacement must satisfy all of these requirements before release:

- bind only to `127.0.0.1`, never `0.0.0.0`;
- generate a new high-entropy session token when the receiver starts;
- require the token on every request and never place it in Git or browser sync storage;
- use exact supplier-origin allowlists, not wildcard CORS;
- accept a small versioned JSON schema with strict body and field limits;
- reject cookies, authorization headers, passwords, API keys, customer data, and raw HTML dumps;
- rate-limit requests, cap queue length, and process only one explicit batch at a time;
- do not accept images at this selection boundary; authorized image URLs belong to the later
  official provider-normalization step and retain the existing private-network protections;
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

## Intended complete interaction

The future bridge should preserve the original simple experience:

```text
start local receiver → open authorized supplier page → add selected items
→ review terminal queue → press Enter → generate → validate → preview
```

The first three steps now work. Official provider normalization is the next vertical slice; until it
ships, use the normalized JSON path described in the README for generation and preview.
