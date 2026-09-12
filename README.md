# CatalogFlow

[![CI](https://github.com/qwq77777764/catalogflow/actions/workflows/ci.yml/badge.svg)](https://github.com/qwq77777764/catalogflow/actions/workflows/ci.yml)
[![Secret scan](https://github.com/qwq77777764/catalogflow/actions/workflows/secret-scan.yml/badge.svg)](https://github.com/qwq77777764/catalogflow/actions/workflows/secret-scan.yml)
[![CodeQL](https://github.com/qwq77777764/catalogflow/actions/workflows/codeql.yml/badge.svg)](https://github.com/qwq77777764/catalogflow/actions/workflows/codeql.yml)

**Turn authorized CJ or Alibaba product facts and images into reviewable,
original WooCommerce listing drafts with a locally installed Codex or Claude Code CLI.**

[中文说明](README.zh-CN.md) · [Connection dashboard](docs/configuration-dashboard.md) ·
[Local AI setup](docs/local-ai.md) ·
[Agent workflow](docs/agent-workflow.md) · [Browser-to-CMD workflow](docs/browser-queue-workflow.md)

CatalogFlow grew out of a working merchant workflow: select a product while logged in to a
supplier site, send its URL and page title to a queue on the same computer,
press Enter in the CMD window, let a local AI CLI rewrite the listing from the product facts
and images, review the result, and only then create a hidden store draft.

The public repository is a clean-room extraction. It contains no operator credentials,
supplier-page archives, customer data, production store records, or automatic public
publishing.

## Why it is different

- **No OpenAI or Anthropic API key is required.** CatalogFlow can reuse the login already
  managed by an installed Codex CLI or Claude Code CLI.
- **Visual connection center.** Add a provider, your own profile name, notes, and the required
  fields without editing source code. Secrets go to the operating-system keyring, not Git.
- **Image-aware listing generation.** Up to five operator-authorized public HTTPS product
  images are downloaded into a temporary directory, checked against private-network URLs,
  and supplied to the selected local CLI for analysis.
- **The agent is provider-neutral.** Codex, Claude Code, and the deterministic offline demo
  all return the same validated listing shape.
- **Pricing remains deterministic.** The AI never sees source costs and does not decide final
  prices.
- **Safe by default.** Every run starts as a local preview. A WooCommerce write requires both
  `--draft` and `--yes`, and the adapter can create only `draft + hidden` products.
- **No bulk scraper is included.** Product facts must be operator-supplied structured data,
  an explicit authorized export, or data obtained through the operator's official API access.

## What “local AI” means

CatalogFlow starts the `codex` or `claude` command installed on **your computer**. It does not
read API keys from this repository and does not ask an agent to modify CatalogFlow before the
first run. The CLI itself handles account sign-in and usage.

This is not the same as offline inference: unless you configure a supported local model
provider separately, the chosen CLI sends the supplied product facts and authorized images
to its model service under your account. Do not process images or data you are not allowed to
send.

## Install CatalogFlow

Python 3.11 or newer and Git are required.

```powershell
git clone https://github.com/qwq77777764/catalogflow.git
cd catalogflow
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

macOS/Linux activation is `source .venv/bin/activate`.

## Configure connections visually

```powershell
python -m catalogflow configure
```

The browser panel runs only on `127.0.0.1`. Connections are grouped as store publishers,
supplier sources, and local AI. Store choices include the available WooCommerce REST API plus
planned WordPress WP-CLI-over-SSH and Shopify Admin API paths. Give each connection a name and
note, then enter its corresponding fields.
Non-secret metadata stays in the user's configuration directory and secrets go to Windows
Credential Manager, macOS Keychain, or the available Linux keyring. Existing secrets are never
returned to the page.

Use the toolbar's **Language** selector to switch the whole panel between **中文 (CN)** and
**English (US)**. The first visit follows the browser language, falling back to English. The browser
remembers only the language code for the current local address and port. Switching language preserves
entered values and pending edits; core pricing remains in USD and pricing is not saved automatically.

WooCommerce, Codex, and Claude profiles can be used now. The CJ source adapter is available as a
preview for one explicitly selected CJ product; Alibaba/1688 and Zendrop remain planned. See
[docs/configuration-dashboard.md](docs/configuration-dashboard.md) for storage details, profile
selection, and failure behavior.

CatalogFlow is official-API-first, not a bulk crawler. A browser button is a user-initiated product
selector; released supplier adapters must retrieve data through the user's own authorized official
API credentials. They must not enumerate a site, bypass login, CAPTCHA, access controls, or rate
limits. When official API access is unavailable, the safe fallback is operator-supplied structured
data—not silent scraping.

## Choose a pricing plan visually

The local dashboard compares two deterministic plans side by side using the same example costs.
Each result shows the price, fee and reserve deductions, estimated profit per unit and margin,
theoretical break-even price, `.95` adjustment, and any minimum-price constraint that takes effect:

- **Margin plan (default):** adds product cost, per-unit shipping, optional user-estimated taxes or
  duties, payment fees, return reserve, operating reserve, target margin, minimum price, and a
  minimum product-cost multiple. It preserves the original `.95` price ending.
- **Custom cost-formula plan:** edit the formula directly in Plan B's card (default `*3`).
  Use `*5`, `/5`, `+2`, `-2`, `*3+2`, or `*(5+2)/3`; a plain `5` means `*5`.
  The formula applies to product cost with normal operator precedence. Shipping, estimated
  duties, and the fixed payment fee are added once afterward; minimum price and `.95` rounding
  still apply. The card shows the formula subtotal and the additions before the final price.

Plan B does not use percentage fees or reserves to set its price, but the profit estimate deducts
them. It does not automatically achieve the target margin; a low formula result can produce a loss.
Estimated profit covers the entered costs and reserves, not accounting net profit.

All monetary inputs are **USD per unit**. The fixed payment fee assumes one unit per order; shared
fees for multi-unit orders are not allocated. For CJ, use the complete quote's per-unit freight
once; do not duplicate it across inbound and last-mile shipping. Tax/duty values are operator
estimates, with no automatic tax-rate lookup.

The currency converter below the sample costs displays the **last-mile / end-to-end shipping**
amount in a selected currency. It shows the original USD amount, converted amount, rate, source,
and reference date. Its three fields are currency, an editable rate, and the converted total.
The fields share equal widths and aligned control rows in both languages, and stack on narrow screens.
The Frankfurter daily rate is filled automatically and can be edited directly; changing
language preserves your selection and manual input. Reference rates are not live bank quotes.
Conversion is for comparison only: it does not change either pricing plan, store currency, or
saved settings. Shipping amounts and credentials never go to the rate provider. See the
[converter details](docs/configuration-dashboard.md#convert-the-last-mile-shipping-example).

Example product cost and shipping stay in the trial calculation. Restoring defaults or undoing
edits changes the form; click **Save** to apply the selected settings to later CLI runs. Saving
does not update existing previews or store products. Non-secret settings remain in `pricing.json`
beside the local profile metadata, and an absent file keeps the legacy margin defaults. See the
[pricing formulas and worked example](docs/configuration-dashboard.md#visual-pricing-panel).

## Connect Codex or Claude Code without an API key

Choose **one** provider. You do not need both.

### Option A — Codex CLI

Install Codex using the [official Codex CLI guide](https://developers.openai.com/codex/cli/),
then run `codex` once and choose **Sign in with ChatGPT**. Exit after sign-in; CatalogFlow will
call `codex exec` itself.

```powershell
python -m catalogflow --doctor
python -m catalogflow examples/synthetic_product.json --source alibaba-manual --generator codex
```

### Option B — Claude Code CLI

Install Claude Code using the
[official setup guide](https://code.claude.com/docs/en/setup), then run `claude` once and sign
in with a supported Claude/Anthropic account. CatalogFlow uses Claude's non-interactive,
schema-validated print mode and disables shell, edit, write, and web tools.

```powershell
python -m catalogflow --doctor
python -m catalogflow examples/synthetic_product.json --source alibaba-manual --generator claude
```

`--doctor` only runs `--version`; it makes no model request. If a command is installed outside
`PATH`, set `CATALOGFLOW_CODEX_COMMAND` or `CATALOGFLOW_CLAUDE_COMMAND` to that executable's
full path. See [docs/local-ai.md](docs/local-ai.md) for Windows, macOS, Linux, authentication,
PATH, privacy, and troubleshooting details.

## Prepare an authorized product input

CatalogFlow currently consumes normalized JSON. Use operator-supplied structured data, an explicit
authorized export, or an official supplier API. The browser selector queues an identifier/URL; it
does not manufacture missing product facts. Never put cookies or credentials in this file.

```json
{
  "source_id": "your-local-reference",
  "title": "Product title visible to you",
  "currency": "USD",
  "variants": [
    {
      "sku": "YOUR-SKU",
      "cost": 8.5,
      "attributes": {"finish": "walnut"}
    }
  ],
  "images": ["https://public-image-host.example/authorized-image.jpg"],
  "facts": {"material": "verified material", "power": "verified power source"}
}
```

Run a local preview:

```powershell
python -m catalogflow product.json --source alibaba-manual --generator claude
```

The result is written to `output/preview.json`, which is ignored by Git.
Normalized JSON labeled `--source cj` must include a complete provider-neutral `shipping_quote`
for every variant; missing CJ freight is rejected rather than priced as zero. Prefer the official
CJ profile flow below when starting from a CJ URL or PID.

### Preview one CJ product through your own API access

Create a CJ profile in `catalogflow configure` with an API key obtained from your own CJ account.
Then pass one CJ product URL or PID explicitly:

```powershell
python -m catalogflow "CJ_PRODUCT_URL_OR_PID" --source cj `
  --supplier-profile "My CJ" --generator codex
```

The preview adapter exchanges the API key for an access token in memory, calls CJ's official
single-product detail endpoint, and requests an official freight quote for each variant. The
profile defaults to `CN` → `US`, quantity `1`; destination ZIP and an exact preferred logistics
name are optional. Without a preferred name, the lowest valid returned route is recorded in the
local preview. It does not list or crawl the catalog, persist access tokens, log raw provider
responses, or send CJ credentials, costs, or freight to Codex/Claude. Authentication, quota,
missing-route, malformed-data, and mismatched-product failures stop explicitly. See
[docs/cj-adapter.md](docs/cj-adapter.md).

## The CJ/Alibaba browser-to-CMD workflow

The operator workflow behind CatalogFlow uses three replaceable parts:

```text
logged-in CJ/Alibaba page
        │ click “Add to local queue”
        ▼
127.0.0.1 browser collector → local queue → press Enter in CMD
                                              │
                                              ▼
                           Codex CLI / Claude Code CLI
                                              │
                                              ▼
                        validate → preview → hidden draft
```

The clean public Alibaba selector and authenticated local receiver now ship with CatalogFlow.

```powershell
python -m catalogflow collect
```

The command prints a local userscript installation URL, a one-time session token, and the queue
file path. Install the script in Tampermonkey, open an Alibaba product-detail page, click
**Add to CatalogFlow**, and enter the printed receiver URL and token. The token remains only in the
userscript's in-memory closure for that page; it is not written to extension storage. Press Enter
in the terminal to freeze the queue.

This first collector deliberately sends only `source`, product-detail URL, and page title. It does
not copy page HTML, cookies, images, prices, variants, or authentication data. The current collector
targets Alibaba, so its frozen queue is not yet connected to the CJ adapter. Use a CJ URL/PID with
`--supplier-profile` for the CJ API preview, or continue using normalized JSON. Alibaba queue
normalization remains a separate future adapter.

The old private userscript and Python controller were **not copied into this repository** because
they mixed brittle DOM selectors, local automation, production configuration, and store writes.
[docs/browser-queue-workflow.md](docs/browser-queue-workflow.md) documents the new public contract.

## Which APIs are optional?

| Connection | Required for a local preview? | Rule |
|---|---:|---|
| OpenAI API key | No | Use an already signed-in Codex CLI. Never paste a key into this repo. |
| Anthropic API key | No | Use an already signed-in Claude Code CLI. Never paste a key into this repo. |
| CJ API | No for manual input; yes for the CJ preview adapter | Apply through your own legitimate CJ account and follow CJ's current terms, points, and quotas. |
| Alibaba/1688 API | No for manual input; useful for structured catalog data | Apply through your own legitimate Alibaba/1688 account or approved provider and follow its terms. |
| WooCommerce REST API | No for previews; yes for hidden-draft writes | Create least-privilege credentials in your own store and keep them in local environment variables. |

CatalogFlow does not distribute, broker, share, or help bypass access to supplier APIs. API
approval, account eligibility, data rights, quotas, and fees belong to each user and provider.

## Optional hidden-draft write

Set the three `WOOCOMMERCE_*` variables shown in `.env.example` in your local environment,
review the preview, and then explicitly acknowledge the write:

```powershell
python -m catalogflow product.json --source alibaba-manual --generator codex --draft --yes
```

This interface cannot publish publicly. Public publication remains a separate manual action in
the store administrator.

## Agent contract

The reusable listing and image-analysis rules are published in
[docs/agent-workflow.md](docs/agent-workflow.md). The short version:

1. accept only authorized product facts and images;
2. never invent dimensions, material, certification, or safety claims;
3. produce original, brand-neutral English copy in the JSON schema;
4. keep supplier names, source URLs, IDs, costs, and credentials out of public copy;
5. calculate prices locally after generation;
6. stop at preview unless a human explicitly requests a hidden draft.

Repository-level instructions for Codex and Claude contributors are in [AGENTS.md](AGENTS.md).

## Security and contributing

Read [SECURITY.md](SECURITY.md) before adding providers or browser helpers. Never open a public
issue containing a token, store URL, customer record, raw supplier response, or production log.
Small, testable contributions are welcome; see [CONTRIBUTING.md](CONTRIBUTING.md) and
[ROADMAP.md](ROADMAP.md).

## License

[MIT](LICENSE)
