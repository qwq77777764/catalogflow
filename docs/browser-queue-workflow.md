# Browser selection queue: desktop and CLI

## What the original workflow did

The private production workflow proved a useful interaction model:

1. The operator signs in to CJ or Alibaba/1688 in a normal browser.
2. On a chosen product, a browser-side button sends the visible product URL, title, and authorized
   image references to a receiver bound to `127.0.0.1`.
3. The local terminal displays the collected items.
4. The operator presses Enter to finish selection.
5. A local Codex or Claude CLI rewrites the normalized listing.
6. Validation and human review occur before any optional hidden draft.

This makes product selection visual and keeps the AI integration on the operator's computer.

The public design is **official-API-first and user-initiated**, not a marketplace crawler. The page
button should submit only the selected product identifier/URL and minimal visible context. The local
source adapter then obtains product facts with credentials the operator received through the
provider's official API process. It must not crawl result pages, bypass authentication/CAPTCHA,
evade rate limits, or silently fall back to scraping. If an official API is unavailable, the operator
must supply structured data they are authorized to use.

The public replacement keeps the selection control separate from the local receiver. It adds
explicit desktop actions for queue confirmation and single-product preview. In the current
implementation, Enter or desktop queue confirmation only freezes selections; neither action
starts the AI task.

## Current public status

In v0.10, the desktop's **Collected products** panel starts and controls the receiver; no command
is needed for that path. It supports CJ product details on `www.cjdropshipping.com` and
`cjdropshipping.com`, and Alibaba international product details on `www.alibaba.com`. It does not
collect 1688 pages or search results. Confirmed CJ items fill the CJ import input; Alibaba items
fill the source link, reference and title in the manual product form. The operator supplies the
missing facts. See [First run](first-run.md).

To use the desktop collector:

1. Open CatalogFlow and click **Start collection**. Keep it running while selecting products.
2. Install a compatible userscript browser extension if needed. Click **Install / update
   collector script** and confirm installation in that extension. The EXE does not install a
   browser extension automatically.
3. Click **Copy pairing code**. Open a supported product detail page in the browser with the
   script installed; reload an already-open page after installing the script if necessary.
4. Click **Add to CatalogFlow**, inspect the URL and title in the confirmation dialog, then
   paste the complete one-line code into the pairing prompt. Do not enter an address and token
   separately. An accepted selection displays **Added ✓** or **Already queued**.
5. Return to **Collected products**, inspect the list, and click **Finish and confirm collection**.
   Choose **Use in import wizard** for a CJ item or **Fill in product details** for Alibaba.
6. Check the source, generator, connections and product data, then click **Generate preview**.
   Review the result before any separately confirmed hidden draft.

Pairing is stored only in that product page's memory. A new tab, another newly loaded page, or a
refresh requires pasting the code again. You can reuse the same code on several pages while the
collector is active; after it stops, start another collection and use its new code. The code
contains the loopback address and a collection-only token, not the dashboard's session token,
supplier credentials or AI login. It is not saved in the queue or extension storage.

## Optional command-line collector

The command-line collector remains available:

```powershell
catalogflow collect
```

The command binds to `127.0.0.1:8766` by default, generates a fresh high-entropy token, prints the
local userscript installation URL and pairing code, and waits for Enter. The userscript runs only
on supported CJ `/product/*` and Alibaba `/product-detail/*` detail pages. It asks for a pairing
code on first use in each page, as described above.

Each accepted payload contains exactly four fields: schema version, source, canonical product URL,
and page title. Tracking parameters and fragments are removed; a valid CJ `pid`, `productId`, or
`product_id` query field is retained when needed to identify the product. Duplicate canonical
URLs from the same source are idempotent. The receiver rejects unexpected fields,
cookies/authorization headers, foreign origins, non-detail URLs,
credentialed URLs, bodies over 16 KiB, more than 30 requests per minute, and queues over 100 items.
By default, the queue is stored in the user's configuration directory with a unique session
filename and restrictive permissions where supported.

Pressing Enter freezes the selection queue and stops the receiver. EOF or cancellation stops it
without confirming the queue. Freezing does not call AI, fetch supplier facts, or write a store.
The desktop loads saved queues when its service starts. If it was already running during a
separate CLI collection, stop and reopen it to load that queue, or use **Already have a collection
queue file?**. Refreshing the list alone does not rescan external queue files.

The queue-file input accepts version-1 or version-2 snapshots up to 48 KiB and 100 selections.
Importing a file explicitly freezes a new copy for review; it does not process its items. This
file records selections, not normalized product facts, and belongs in the queue input rather
than the product JSON input. Old version-1 files found on disk have no saved confirmation flag
and are loaded as unfinished until explicitly confirmed.

The dashboard now owns an embedded collector when started there. Its close action stops that
receiver without silently freezing unfinished selections. Persistent unfinished queues can be
explicitly confirmed with **Confirm this unfinished queue** after reopening. Finish any current
collection first if that button is not shown. CLI Enter remains the terminal confirmation boundary.
Requests whose bodies arrive after collection stops are rejected instead of appending late items.

The old userscripts and Python controller were not copied because they combine site-specific DOM
selectors, browser automation, local unauthenticated endpoints, production configuration, direct
store writes, and private operational assumptions. Publishing that code unchanged would be unsafe
and brittle.

## Enforced design for the public bridge

The public receiver enforces these boundaries:

- bind only to `127.0.0.1`, never `0.0.0.0`;
- generate a new high-entropy session token when the receiver starts;
- require the collection token for the selection and queue data APIs; the userscript installation
  URL is public on loopback and contains no token, and allowed-origin CORS preflights carry no token;
- use exact supplier-origin allowlists, not wildcard CORS;
- accept a small versioned JSON schema with strict body and field limits;
- reject cookies, authorization headers, passwords, API keys, customer data, and raw HTML dumps;
- rate-limit selection requests and cap each queue at 100 items; the dashboard runs one embedded
  collector at a time and hands off one confirmed item at a time without automatic batch processing;
- do not accept images at this selection boundary; authorized image URLs belong to the later
  official provider-normalization step and retain the existing private-network protections;
- save queue state in the local configuration directory with restrictive permissions where supported;
- require desktop confirmation or CLI Enter to freeze selections, followed by an explicit
  **Generate preview** action before review and any store write;
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

## Desktop interaction

The desktop connects the selection and preview steps:

```text
start collection → pair on each loaded product page → select a product → finish and confirm
→ choose one item → CJ official facts or Alibaba manual form → generate → review
```

CJ official normalization is supported. Alibaba/1688 automatic normalization is not: the operator
must fill the missing authorized facts in the manual form or supply normalized JSON. There is no
unattended batch processing or automatic store publication.
