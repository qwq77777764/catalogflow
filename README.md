# CatalogFlow

[![CI](https://github.com/qwq77777764/catalogflow/actions/workflows/ci.yml/badge.svg)](https://github.com/qwq77777764/catalogflow/actions/workflows/ci.yml)
[![Secret scan](https://github.com/qwq77777764/catalogflow/actions/workflows/secret-scan.yml/badge.svg)](https://github.com/qwq77777764/catalogflow/actions/workflows/secret-scan.yml)
[![CodeQL](https://github.com/qwq77777764/catalogflow/actions/workflows/codeql.yml/badge.svg)](https://github.com/qwq77777764/catalogflow/actions/workflows/codeql.yml)

**Turn authorized CJ or Alibaba product facts and images into reviewable,
original WooCommerce listing drafts with a locally installed Codex or Claude Code CLI.**

[中文说明](README.zh-CN.md) · [First-run walkthrough](docs/first-run.md) · [Visual import guide](docs/visual-import.md) ·
[Connection dashboard](docs/configuration-dashboard.md) ·
[Local AI setup](docs/local-ai.md) ·
[Agent workflow](docs/agent-workflow.md) · [Browser selection queue](docs/browser-queue-workflow.md)

CatalogFlow grew out of a working merchant workflow: select a product while logged in to a
supplier site, send its URL and page title to a queue on the same computer,
press Enter in the CMD window, let a local AI CLI rewrite the listing from the product facts
and images, review the result, and only then create a hidden store draft.

The public repository is a clean-room extraction. It contains no operator credentials,
supplier-page archives, customer data, production store records, or automatic public
publishing.

## Start from the desktop

Open **CatalogFlow.exe** and follow **Getting started**. Select Codex or Claude, click
**Check installation and login**, and follow the official installation or login instructions
when needed. The app can open a supported Windows CLI login window; otherwise it shows a command
to run yourself. It does not install the CLI or complete account sign-in for you. An optional, explicitly
started sample AI test checks a small synthetic task; it can consume account usage. A saved
connection name or a successful sign-in check alone is not a successful model call.

Paste a CJ product link, or click **Start collection**, install the supplied userscript in a
compatible browser extension, and copy its one-line pairing code. On a supported product page,
click **Add to CatalogFlow**, review what will be sent, and paste the code when prompted. Pairing
is held only in that page's memory: another tab, a newly loaded product page, or a refresh needs
the code again. Selected CJ and Alibaba links appear in **Collected products**. Choose
**Finish and confirm collection** before selecting a product for preview. CJ facts come from the
operator's official API; Alibaba selections open a manual product form, because its automatic
supplier adapter is not implemented. No JSON file is required for this form. Existing JSON and
frozen queue files remain supported.

Choose the AI and click **Generate preview**. CatalogFlow hands the product task to the CLI and
returns the result to this window; you do not send a separate chat message to start it. The local
template option works without an AI account. A store is optional, and is needed only if an
operator chooses to create a hidden draft after review. See the [walkthrough](docs/first-run.md).

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
- **Review one product in the browser.** Use a CJ URL/PID, the manual product form, or an
  authorized JSON file, choose a generator, and review each variant's costs, freight, USD price,
  and editable listing copy.
- **Safe by default.** Every run starts as a local preview. A WooCommerce write requires both
  review acknowledgment and the create-draft button in the wizard, or `--draft --yes` in the CLI.
  The adapter can create only `draft + hidden` products.
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

**Windows x64:** download the Windows ZIP from [Releases](https://github.com/qwq77777764/catalogflow/releases),
extract it, and double-click **CatalogFlow.exe**. Python and Git are not required for the EXE.
The Chinese/English launcher opens the import, configuration, pricing, and work-history dashboard;
use its **Exit** button to stop the local service. AI generation still needs your own installed,
signed-in Codex or Claude CLI; template generation needs no AI account. Single-product imports can
be completed in the browser, and CLI arguments remain available. See [Windows guide](docs/windows.md).

For installation from source, Python 3.11 or newer and Git are required.

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
preview for one explicitly selected CJ product; automatic Alibaba/1688 and Zendrop API adapters
remain planned. Authorized Alibaba/1688 facts can already be entered in the manual form. See
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
edits changes the form; click **Save** to apply the selected settings to later previews and CLI runs. Saving
does not update existing previews or store products. Non-secret settings remain in `pricing.json`
beside the local profile metadata, and an absent file keeps the legacy margin defaults. See the
[pricing formulas and worked example](docs/configuration-dashboard.md#visual-pricing-panel).

## Import one product visually

Open the dashboard's import wizard after saving the connections and pricing you want to use:

1. Choose a **CJ product URL/PID** with a saved CJ profile, or choose **Manual product form / JSON**
   and **Fill in a form** to enter verified facts, variants, USD costs, and shipping per unit.
   **Advanced: normalized JSON file** accepts one authorized `alibaba-manual` product object
   (UTF-8, optional BOM, at most 48 KiB). A confirmed browser selection can fill the CJ input or
   the manual form's source reference. Choose Codex, Claude, or template generation. A WooCommerce
   profile is optional for preview; select it now if you intend to create a draft from this preview.
2. Generate the preview in the background. Review the source link, image count and authorized
   image links, each variant's cost and freight, and its calculated USD selling price. Edit the
   listing title, HTML description as text, category, and tags; edits are validated before a write.
3. Check the review acknowledgment and explicitly create a **hidden draft**. The server uses the
   cached product, saved pricing snapshot, selected store, and reviewed listing; confirmation does
   not fetch CJ again, call AI again, or recalculate prices. Results join the existing work reports
   and duplicate protection.

Only one import task runs per dashboard session. Reopen the authenticated page from the launcher
to recover the current task while that server still runs. Unconfirmed previews are held in memory
and cannot be resumed after restarting the application; their written reports remain on disk.
A plain browser refresh may lose session authentication. See the [full guide](docs/visual-import.md)
for connection requirements, review limits, and recovery.

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

The visual **Manual product form / JSON** option lets you enter a product without writing JSON.
Fill in its title, stable product reference, verified facts, variants, USD costs, and shipping per
unit. Authorized image links are optional. Use one `Name: Value` per fact line; use advanced JSON
when a variant needs several separately named attributes.

The CLI and the advanced file input consume normalized JSON, such as the example below. Use
operator-supplied data, an explicit authorized export, or an official supplier API. The browser
selector queues a URL and title; it does not retrieve missing facts. Never put cookies or
credentials in a product file.

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

The result is written to `output/preview.json`, which is ignored by Git. Each CLI import also
archives a separate timestamped work report (TXT and JSON) in your user configuration directory.
The visual wizard writes to the same archive; its preview and draft result remain traceable there.
The dashboard's **Work history** section lists runs and downloads a readable TXT report with
source links, per-item outcomes, timestamps, and any store draft IDs. Repeated previews remain
allowed; completed drafts are protected by a store-scoped history registry. Interrupted or
uncertain writes require review before another attempt. See [Work reports](docs/work-reports.md).
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

## Select CJ or Alibaba products in the browser

The desktop now connects browser selection to the single-product import wizard:

```text
start collection → pair on a supported product page → Add to CatalogFlow
→ review the local queue → finish and confirm → choose one product
→ CJ official API or manual facts → Generate preview → review → optional hidden draft
```

The bundled userscript supports CJ product details on `www.cjdropshipping.com` and
`cjdropshipping.com`, and Alibaba international product details on `www.alibaba.com`.
It does not support 1688 pages or search-result collection. Choose **Start collection**, then
**Install / update collector script** and **Copy pairing code**. Install a compatible userscript
manager separately if your browser does not have one. On each product page, click
**Add to CatalogFlow**, confirm the displayed link/title, and paste the code when prompted.

One paste supplies the receiver address and temporary collection-only token together. The script
remembers them only in the current page's memory, not across tabs, newly loaded pages, or refreshes.
The same code can pair another page while that collector remains active; starting a new collector
requires its new code. Nothing is stored in the extension's synchronized storage.

Return to **Collected products**, inspect the list, and click **Finish and confirm collection**.
Then choose **Use in import wizard** for CJ, or **Fill in product details** for Alibaba. CJ uses
your saved official API connection when you generate the preview. Alibaba requires its missing
facts, costs, freight and authorized images to be supplied in the manual form or normalized JSON;
its automatic supplier adapter remains unimplemented. Neither collection nor confirmation calls
AI or writes to a store.

The optional terminal collector remains available:

```powershell
python -m catalogflow collect
```

It prints a local script installation URL, one-line pairing code, and queue file path. Pair the
same script as above, then press Enter in the terminal to freeze the queue and stop collection.
Enter does not start generation. Open the dashboard to use a confirmed item; if it was already
running before this CLI collection, reopen it after stopping the service or use **Already have a
collection queue file?** to import the snapshot (at most 48 KiB). The queue-file input and product
JSON input are separate formats.

The selector sends only schema version, source, product-detail URL, and page title. It does not
copy page HTML, cookies, images, prices, variants, or authentication data. Closing the app or
cancelling the terminal collector stops receipt without approving unfinished selections. Saved
unfinished queues can be explicitly confirmed after reopening.

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
| WooCommerce REST API | No for previews; yes for hidden-draft writes | Create least-privilege credentials in your own store; save them in the connection profile's OS keyring, or supply local environment variables for the CLI. |

CatalogFlow does not distribute, broker, share, or help bypass access to supplier APIs. API
approval, account eligibility, data rights, quotas, and fees belong to each user and provider.

## Optional hidden-draft write

Multi-variant products retain their individual attributes and prices. Authorized gallery and
variant images use bounded temporary downloads and the WordPress media API. Image uploads require
an additional WordPress username and **application password** with media-upload permission; these
optional fields are available in the WooCommerce profile. The application password stays in the
operating-system keyring. WooCommerce consumer keys alone cannot authenticate the WordPress media
endpoint. Without images, only the normal WooCommerce credentials are needed. Products and
variations remain drafts; uploaded media files can be directly accessible on the store's server.

Use the visual review flow above, or set the three `WOOCOMMERCE_*` variables shown in `.env.example`
in your local environment and explicitly acknowledge a CLI write:

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
